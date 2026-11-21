"""Controlled A/B/C experiment on 02-Semiurban (partial observability), chronological and with a frozen
calibration.

One state estimator and one residual matrix (scripts/17), one candidate stream (one rule per topology, in
order of first appearance), persistence L of the detector, the same event windows and scoring.
  A  SE-BDD: one global threshold on max_i |r_i| (scripts/17).
  B  per-channel thresholds m_i = k x noise_i, no physics check (noise_i: train maximum of |r_i|,
     floored per measurement kind, as scripts/18). A topology's rule needs no computation and acts at once.
  C  B plus the physics check: m_i = max(k x noise_i, 1.5 x bound_i(T)). bound_i(T) is the largest benign
     |r_i| found for topology T: search (40 LHS states, differential evolution, as scripts/18), the affine
     box maximum plus a remainder delta, where delta = 1.25 x the largest remainder |r - r_aff| over uniform
     states, a DE search AND the box-corner states of the 32 channels with the largest box maximum relative
     to their search margin (both signs, pulled toward the box centre until the state is benign). The corner
     term is the correction prompted by the corner counterexamples to the stored "proved" margins.
     A topology already present in the calibration records is computed before the test day (engineering
     model); a topology first met in the test day is computed when it appears, and its rule acts only
     after the measured compute time. C never rejects a rule here; it only raises margins (counted).
  C0 the stored library of scripts/18 --prove (reproduction of the published operating point), acting
     after its logged certification time.
The SE loop has no alert feedback (rules are created by topology appearance, not by alerts), so the
isolated comparison and the full system coincide.

Calibration (phase "calibrate", frozen before the test day is read): noise from the first half of the
training records, false-alarm episodes per benign hour on the second half, k grid K_GRID, target
TARGET_EPH; each method takes the smallest k on the grid that meets the target (the largest k if none
does). For C the bounds of the topologies present in the calibration records are used. The test phase
uses noise from all training records with the frozen k.

Regression and hold-out checks of C (phase "test"): (i) the benign corner states that fired the stored
"proved" rules (regenerated as in scripts/34, recorded day); (ii) new states not used to set delta:
64 random box vertices per topology pulled toward the centre until benign, and the corner states of the
channels ranked 33 to 64. A check fails if max_i |r_i| / m_i > 1 on a benign state."""
import hashlib
import json
import os
import pickle
import re
import sys
import time
from multiprocessing import get_context
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import envelope as E
from p3 import measure as M
from p3 import oracle_search as O
from p3 import se_proof as SP
from p3 import sherlock_io as S
from p3 import state_est as SE

K_GRID = [1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0, 10.0, 15.0, 20.0]
TARGET_EPH = 0.5
PROCESS = ["control-and-freeze:control-and-freeze", "drift-off:drift-off", "industroyer:industroyer"]
OUT = C.ROOT / "reports" / "abc"
ITERS = 1
SETTLE = 60.0
G_ = {}


# ------------------------------------------------------------------ helpers
def noise_from(R, kinds):
    noise = np.nanmax(np.abs(R), axis=0)
    noise = np.where(np.isfinite(noise), noise, np.nanmax(noise))
    p999 = np.nanpercentile(np.abs(R), 99.9, axis=0)
    floor = {k: float(np.nanmedian(p999[kinds == k])) for k in set(kinds)}
    return np.maximum(noise, np.array([floor[k] for k in kinds]))


def topologies(split, T):
    from p3 import sherlock_model as SM
    names, net, idx = M.names(), E._base_net(), M.index()
    other_sw = [int(s_) for s_ in net.switch.index if net.switch.et.at[s_] != "l"]
    fixed = SM.fixed_switch_states()
    want = {round(float(x), 3) for x in T}
    out = {}
    for rec in S.iter_state(S.root(), split):
        ts = round(rec["timestamp"], 3)
        if ts not in want:
            continue
        st = rec["state"]
        if any(not st.get(f"switch.{s_}:is_closed", fixed[s_]) for s_ in other_sw):
            out[ts] = None; continue
        m = SM.record_measurements(st, names, net)
        lo = tuple(l for l in range(len(net.line)) if m[idx[f"line_in.{l}"]] < 0.5)
        out[ts] = E.Config((), None if not lo else (lo[0] if len(lo) == 1 else lo), ())
    return [out.get(round(float(x), 3)) for x in T]


def runs(mask, L):
    out, c = np.zeros(len(mask), int), 0
    for i, x in enumerate(mask):
        c = c + 1 if x else 0
        out[i] = c
    return out >= L


def benign_mask(t, ev):
    near = np.zeros(len(t), bool)
    for e in ev:
        if "benign" not in e["id"]:
            near |= (t >= e["start"] - SETTLE) & (t <= e.get("recovery", e["end"]) + SETTLE)
    return ~near


def eph(alarm, t, ben):
    fa = alarm & ben
    eps = int(np.sum(np.diff(np.r_[0, fa.astype(int)]) == 1))
    hours = ben.sum() * float(np.median(np.diff(t))) / 3600
    return eps, hours, (fa[ben].mean() if ben.any() else float("nan"))


def corner_states(cfg, ab, channels, signs=(1.0, -1.0)):
    out = []
    for i in channels:
        for sgn in signs:
            xc = np.where(sgn * ab["G"][i] > 0, ab["hi"], ab["lo"])
            for tt in (1.0, 0.8, 0.6, 0.4, 0.3, 0.2):
                x = ab["x0"] + tt * (xc - ab["x0"])
                ok, ben, _, m = M.evaluate(x, cfg)
                if ok and ben:
                    out.append((int(i), sgn, tt, x, m)); break
    return out


def vertex_states(cfg, ab, n, seed):
    rng = np.random.default_rng(seed); out = []
    for _ in range(n):
        xc = np.where(rng.random(len(ab["x0"])) < 0.5, ab["lo"], ab["hi"])
        for tt in (1.0, 0.8, 0.6, 0.4, 0.3, 0.2):
            x = ab["x0"] + tt * (xc - ab["x0"])
            ok, ben, _, m = M.evaluate(x, cfg)
            if ok and ben:
                out.append((-1, 0.0, tt, x, m)); break
    return out


def physics(job):
    """bound_i(T) for one topology (see module doc). Returns arrays over the topology's monitored channels."""
    key, cfg, seed = job
    noise, obs = G_["noise"], G_["obs"]; pos = {n: i for i, n in enumerate(obs)}
    t0 = time.time()
    s = SE.se(cfg); opos = np.array([pos[n] for n in s.names])
    X, _, _ = E.sample_lhs(E.full(), 40, seed=seed, configs=(cfg,))
    bs = np.zeros(len(opos))

    def resid(x, m=None):
        if m is None:
            ok, ben, _, m = M.evaluate(x, cfg)
            if not ok or not ben:
                return None, None
        r, _ = SE.residual_ac(s, m, iters=ITERS)
        return r, m
    for x in X:
        r, _ = resid(x)
        if r is not None:
            bs = np.fmax(bs, np.abs(r))
    for rnd in range(1, 4):
        mg = 1.5 * np.fmax(noise[opos], bs)

        def score(x, m, mg=mg):
            r, _ = SE.residual_ac(s, m, iters=ITERS)
            return -1.0 if r is None else float(np.nanmax(np.abs(r) / mg) - 1.0)
        st = O.de_maximize(score, cfg, E.full(), 150, seed + rnd)
        if st.get("best_x") is None:
            break
        r, _ = resid(st["best_x"])
        if r is not None:
            bs = np.fmax(bs, np.abs(r))
        if st["best"] <= 0:
            break
    ms = 1.5 * np.fmax(noise[opos], bs)
    ab = SP.affine_bound(cfg, s, ms, ITERS, 150, 100, seed + 77)
    t_aff = time.time() - t0
    rank = np.argsort(-ab["box"] / ms)
    fit = corner_states(cfg, ab, rank[:32])
    rem = np.zeros(len(opos))
    for _, _, _, x, m in fit:
        r, _ = SE.residual_ac(s, m, iters=ITERS)
        if r is not None:
            rem = np.fmax(rem, np.abs(r - (ab["g"] + ab["G"] @ (x - ab["x0"]))))
            bs = np.fmax(bs, np.abs(r))
    delta_aug = np.fmax(ab["delta"], 1.25 * rem)
    bound = np.fmax(bs, ab["box"] + delta_aug)
    return {"key": key, "label": cfg.label, "opos": opos, "bound": bound, "bound_search": bs, "box": ab["box"], "delta": ab["delta"],
            "delta_aug": delta_aug, "rank": rank, "seconds": time.time() - t0, "seconds_affine": t_aff, "n_fit": len(fit),
            "ab": {k: ab[k] for k in ("g", "G", "x0", "lo", "hi")}}


def compute_bounds(cfgs, noise, obs, base_seed, workers):
    G_.update(noise=noise, obs=obs)
    jobs = [(k, c, base_seed + 10 * k) for k, c in enumerate(cfgs)]
    with get_context("fork").Pool(workers) as pool:
        res = pool.map(physics, jobs)
    return sorted(res, key=lambda r: r["key"])


def margins_C(bnd, noise, k, n_obs):
    m = np.full(n_obs, np.inf)
    o = bnd["opos"]
    m[o] = np.maximum(k * noise[o], 1.5 * bnd["bound"])
    return m


def fires_from(Rabs, topo_idx, margin_by_topo, active_from, t, L):
    f = np.zeros(len(t), bool)
    for k, mg in margin_by_topo.items():
        sel = (topo_idx == k) & (t >= active_from.get(k, -np.inf))
        if sel.any():
            f[sel] = np.nanmax(Rabs[sel] / mg, axis=1) > 1.0
    return runs(f, L)


def setvar(variant):
    if variant:
        os.environ["P3_VARIANT"] = variant
    else:
        os.environ.pop("P3_VARIANT", None)
    C.GRID = "semiurban"; E.use_grid("semiurban")


# ------------------------------------------------------------------ phase 1: calibration
def calibrate(variant, workers, seed):
    setvar(variant)
    sb = np.load(C.interim("se_residuals.npz"), allow_pickle=True)
    obs = list(sb["obs"]); kinds = np.array([n.split(".")[0] for n in obs])
    Ttr, Rtr, L = sb["train_t"], sb["train_R"], int(sb["L"])
    h = len(Ttr) // 2
    n_cal = noise_from(Rtr[:h], kinds); n_full = noise_from(Rtr, kinds)
    cfg_tr = topologies("train", Ttr)
    uniq = []
    for c in cfg_tr:
        if c is not None and c not in uniq:
            uniq.append(c)
    t0 = time.time()
    bnds = compute_bounds(uniq, n_full, obs, seed + 5000, workers)
    idx = np.array([uniq.index(c) if c is not None else -1 for c in cfg_tr])
    Rc, Tc, ic = np.abs(Rtr[h:]), Ttr[h:], idx[h:]
    ben = np.ones(len(Tc), bool)
    curves, pick = {}, {}
    for nm in ("B", "C"):
        cur = []
        for k in K_GRID:
            mbt = {j: (np.where(np.isin(np.arange(len(obs)), b["opos"]), k * n_cal, np.inf) if nm == "B" else margins_C(b, n_cal, k, len(obs)))
                   for j, b in enumerate(bnds)}
            f = fires_from(Rc, ic, mbt, {}, Tc, L)
            eps, hrs, rate = eph(f, Tc, ben)
            cur.append([k, eps, hrs, eps / hrs, rate])
        ok = [c[0] for c in cur if c[3] <= TARGET_EPH]
        pick[nm] = min(ok) if ok else max(K_GRID)
        curves[nm] = cur
    th = hashlib.sha256(np.ascontiguousarray(Rtr).tobytes()).hexdigest()[:16]
    frozen = {"variant": variant or "recorded", "k_grid": K_GRID, "target_episodes_per_hour": TARGET_EPH,
              "rule": "smallest k on the grid with calibration episodes per hour <= target; largest k if none",
              "calibration": "noise from the first half of the training records, false alarms on the second half",
              "train_hash": th, "train_topologies": [c.label for c in uniq], "k": pick, "curves": curves,
              "bounds_seconds": [b["seconds"] for b in bnds], "wall_s": time.time() - t0, "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"frozen_{frozen['variant']}.json").write_text(json.dumps(frozen, indent=1))
    (C.INTERIM / f"abc_train_bounds_{frozen['variant']}.pkl").write_bytes(pickle.dumps({"cfgs": uniq, "bounds": bnds, "hash": th}))
    print(json.dumps({k: v for k, v in frozen.items() if k != "curves"}, indent=1))


# ------------------------------------------------------------------ phase 2: test
def cert_latency(report):
    lat = {}
    p = C.ROOT / "reports" / report
    if p.exists():
        for m in re.finditer(r"^\| (\d+) \| (ties=[^|]+) \| ([^|]+) \| (\d+) \|", p.read_text(), re.M):
            lat[m.group(2).strip()] = float(m.group(4))
    return lat


def test(variant, calib, workers, seed):
    setvar(variant)
    vname = variant or "recorded"
    fr = json.loads((OUT / f"frozen_{calib}.json").read_text())
    tb = pickle.loads((C.INTERIM / f"abc_train_bounds_{calib}.pkl").read_bytes())
    ev = S.load_events(S.root(), "test")
    sb = np.load(C.interim("se_residuals.npz"), allow_pickle=True)
    obs = list(sb["obs"]); kinds = np.array([n.split(".")[0] for n in obs]); n_obs = len(obs)
    Ttr, Rtr, T, R, det, L = sb["train_t"], sb["train_R"], sb["test_t"], sb["test_R"], sb["alarm"].astype(bool), int(sb["L"])
    assert hashlib.sha256(np.ascontiguousarray(Rtr).tobytes()).hexdigest()[:16] == tb["hash"], "calibration data differ"
    noise = noise_from(Rtr, kinds)
    cfg_te = topologies("test", T)
    order = []
    for c in cfg_te:
        if c is not None and c not in order:
            order.append(c)
    first = {c: float(T[cfg_te.index(c)]) for c in order}
    tidx = np.array([order.index(c) if c is not None else -1 for c in cfg_te])
    known = {c: b for c, b in zip(tb["cfgs"], tb["bounds"])}
    new = [c for c in order if c not in known]
    nb = compute_bounds(new, noise, obs, seed + 9000, workers) if new else []
    bnd = {}
    for c in order:
        bnd[c] = known[c] if c in known else nb[new.index(c)]
    act_C = {j: (-np.inf if c in known else first[c] + bnd[c]["seconds"]) for j, c in enumerate(order)}
    Rabs = np.abs(R)
    stored = pickle.loads((C.INTERIM / C.suffixed("semiurban_rules.pkl")).read_bytes())["rules"]
    st_m = {c: m for c, m, _ in stored}
    lat = cert_latency("semiurban_consolidation_semiurban" + ("_" + variant if variant else "") + ".md")
    act_C0 = {j: first[c] + lat.get(c.label[:70].strip(), 0.0) for j, c in enumerate(order)}
    kB, kC = fr["k"]["B"], fr["k"]["C"]

    def B_m(k):
        return {j: np.where(np.isin(np.arange(n_obs), bnd[c]["opos"]), k * noise, np.inf) for j, c in enumerate(order)}

    def C_m(k):
        return {j: margins_C(bnd[c], noise, k, n_obs) for j, c in enumerate(order)}
    variants = {"A: SE-BDD, global threshold": (det, None),
                "B: per-channel, k = 1.5": (fires_from(Rabs, tidx, B_m(1.5), {}, T, L), 1.5),
                "C0: stored proved library, k = 1.5 (+cert latency)": (fires_from(Rabs, tidx, {j: st_m[c] for j, c in enumerate(order) if c in st_m}, act_C0, T, L), 1.5),
                "C: per-channel + physics check (corner-augmented), k = 1.5": (fires_from(Rabs, tidx, C_m(1.5), act_C, T, L), 1.5),
                f"B: per-channel, calibrated k = {kB:g}": (fires_from(Rabs, tidx, B_m(kB), {}, T, L), kB),
                f"C: per-channel + physics check, calibrated k = {kC:g}": (fires_from(Rabs, tidx, C_m(kC), act_C, T, L), kC)}
    att = [e for e in ev if e["description"] in PROCESS and "benign" not in e["id"]]
    ben = benign_mask(T, ev)
    res = {}
    for nm, (al, k) in variants.items():
        out, dly, rec = {}, {}, 0
        for e in att:
            sel = (T >= e["start"]) & (T <= e.get("recovery", e["end"]))
            hit = bool(al[sel].any()); out[e["id"]] = hit
            if hit:
                tt = T[sel][np.argmax(al[sel])]; dly[e["id"]] = float(tt - e["start"]); rec += int(tt > e["end"])
        eps, hrs, rate = eph(al, T, ben)
        active = None
        if nm.startswith("C:"):
            active = float(np.mean([(tidx[i] >= 0) and (T[i] >= act_C[tidx[i]]) for i in range(len(T))]))
        elif nm.startswith("C0"):
            active = float(np.mean([(tidx[i] >= 0) and (T[i] >= act_C0[tidx[i]]) for i in range(len(T))]))
        elif nm.startswith("B"):
            active = float(np.mean(tidx >= 0))
        res[nm] = {"k": k, "out": out, "delay": dly, "recovery_first": rec, "eps": eps, "hours": hrs, "rate": rate, "active": active,
                   "per": {p.split(":")[0]: [sum(out[e["id"]] for e in att if e["description"] == p), sum(1 for e in att if e["description"] == p)] for p in PROCESS}}
    # physics-check impact
    impact = []
    for j, c in enumerate(order):
        b = bnd[c]; o = b["opos"]
        impact.append({"topology": c.label, "known_before_test": c in known, "compute_s": b["seconds"],
                       "channels": len(o), "raised_at_1.5": int(np.sum(1.5 * b["bound"] > 1.5 * noise[o])),
                       f"raised_at_k{kC:g}": int(np.sum(1.5 * b["bound"] > kC * noise[o])),
                       "median_ratio": float(np.median((1.5 * b["bound"]) / (1.5 * noise[o]))), "rejected": False})
    # example: an instance B detects and C misses at k = 1.5
    example = None
    bo, co = res["B: per-channel, k = 1.5"]["out"], res["C: per-channel + physics check (corner-augmented), k = 1.5"]["out"]
    for e in att:
        if bo[e["id"]] and not co[e["id"]]:
            sel = np.where((T >= e["start"]) & (T <= e.get("recovery", e["end"])) & (tidx >= 0))[0]
            best = None
            for i in sel:
                c = order[tidx[i]]; mb = B_m(1.5)[tidx[i]]; mc = C_m(1.5)[tidx[i]]
                rb = Rabs[i] / mb
                ch = int(np.nanargmax(rb))
                if rb[ch] > 1 and (best is None or rb[ch] > best[2]):
                    best = (i, ch, float(rb[ch]), float(Rabs[i, ch]), float(mb[ch]), float(mc[ch]), float(noise[ch]))
            if best:
                i, ch, _, r_, mb_, mc_, nz = best
                example = {"event": e["id"], "type": e["description"], "t_rel": float(T[i] - e["start"]), "channel": obs[ch],
                           "residual_sigma": r_, "B_margin": mb_, "C_margin": mc_, "noise": nz}
                break
    # regression and hold-out
    checks = []
    if variant is None:
        for k_, (c, m_st, _) in enumerate(stored):
            if c not in bnd:
                continue
            s = SE.se(c); pos = {n: i for i, n in enumerate(obs)}; o = np.array([pos[n] for n in s.names])
            ab0 = SP.affine_bound(c, s, m_st[o], ITERS, 150, 100, 7 + k_ * 10 + 77)
            cs = corner_states(c, ab0, np.argsort(-ab0["box"] / m_st[o])[:8])
            for kk, lab in ((1.5, "1.5"), (kC, f"{kC:g}")):
                mc = margins_C(bnd[c], noise, kk, n_obs)[o]
                sc_st, sc_new = [], []
                for _, _, _, x, m in cs:
                    r, _ = SE.residual_ac(s, m, iters=ITERS)
                    if r is not None:
                        sc_st.append(float(np.nanmax(np.abs(r) / m_st[o]))); sc_new.append(float(np.nanmax(np.abs(r) / mc)))
                checks.append(["regression (stored-rule corners)", c.label[:60], lab, f"{sum(x > 1 for x in sc_st)}/{len(sc_st)}",
                               f"{sum(x > 1 for x in sc_new)}/{len(sc_new)}", f"{max(sc_new, default=float('nan')):.2f}"])
    for j, c in enumerate(order):
        b = bnd[c]; s = SE.se(c)
        ab = dict(b["ab"]); ab["box"] = b["box"]
        hold = vertex_states(c, ab, 64, seed + 777 + j) + corner_states(c, ab, b["rank"][32:64])
        o = b["opos"]
        for kk, lab in ((1.5, "1.5"), (kC, f"{kC:g}")):
            mc = margins_C(b, noise, kk, n_obs)[o]
            sc = []
            for _, _, _, x, m in hold:
                r, _ = SE.residual_ac(s, m, iters=ITERS)
                if r is not None:
                    sc.append(float(np.nanmax(np.abs(r) / mc)))
            checks.append(["hold-out (random vertices + corners of channels 33-64)", c.label[:60], lab, "", f"{sum(x > 1 for x in sc)}/{len(sc)}", f"{max(sc, default=float('nan')):.2f}"])
    out = {"variant": vname, "calibration": calib, "kB": kB, "kC": kC, "n_topologies": len(order), "n_new": len(new),
           "results": res, "impact": impact, "example": example, "checks": checks, "L": L, "th": float(sb["th"])}
    (OUT / f"abc_{vname}.json").write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps({nm: [sum(r["out"].values()), len(r["out"]), r["eps"], round(r["hours"], 2)] for nm, r in res.items()}, indent=1))
    for c_ in checks:
        print(c_)


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--phase", choices=["calibrate", "test"], required=True)
    ap.add_argument("--variant", default="")
    ap.add_argument("--calib", default="", help="frozen calibration to use (recorded or split)")
    ap.add_argument("--workers", type=int, default=2)
    ap.set_defaults(grid="semiurban")
    a = C.init(ap.parse_args())
    if a.phase == "calibrate":
        calibrate(a.variant or None, a.workers, a.seed)
    else:
        test(a.variant or None, a.calib or (a.variant.split("_")[0] if a.variant else "recorded"), a.workers, a.seed)


if __name__ == "__main__":
    main()
