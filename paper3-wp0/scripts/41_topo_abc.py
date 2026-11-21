"""Physics floor against per-(channel, topology) noise thresholds on 02-Semiurban.

Variants, all on the same state-estimation residuals (scripts/17), topologies, persistence L = 3 and
scoring windows:
  A       SE-BDD, one global threshold (scripts/17).
  B       m_i = k x noise_i, noise_i per channel over all topologies.
  C       m_i = max(k x noise_i, 1.5 x bound_i(T)), bound as scripts/36 (search, affine box, remainder
          with box-corner states).
  B_top   m_i(T) = k x noise_i(T): noise per (channel, topology) when topology T has at least N_MIN
          records in the noise-estimation window, otherwise the fallback noise_i of B.
  C_top   m_i(T) = max(k x noise_i(T), 1.5 x bound_i(T)), with exactly the noise of B_top.
B_top vs C_top is the main comparison: it isolates the physics floor.

Protocol P2 (new, frozen before the test day is read):
  noise estimation  first half of the training records (window stored in the freeze file);
  k selection       second half of the training records;
  test              the test day, with the noise and k frozen (no re-estimation).
N_MIN is fixed on the estimation window only: the smallest n on N_GRID such that, for every topology with at
least 2n records in the estimation window, the maximum |r| over its first n records times 1.5 covers the
maximum over its remaining records on at least 99 % of channels (the largest n on the grid if none passes).
Noise per (channel, T) = maximum |r| over T's estimation records, floored by the per-kind floor of B.
k is chosen per variant and target (0.5 main; 0.25 and 1.0 sensitivity) by one rule: the smallest k on
K_GRID whose false-alarm episodes per hour on the selection window is at most the target (the largest k
if none is). Every record whose topology is known (all records of the training day) is used for selection.

Realistic operation: the physics rule of a topology that was present in the training records is computed
before the test day; that of a topology first met in the test day acts only after its measured compute time
(taken from the scripts/36 run, so the timing is identical across variants). B and B_top need no compute.
Results are computed on the whole test day (waiting included), and separately on the records where the
physics rule of the record's topology is active (both methods active), to separate a miss caused by a high
threshold from a miss caused by waiting.

Protocol P1 (reproduction): noise from all training records and the k frozen in reports/abc/frozen_*.json,
as scripts/36; it must reproduce the published B and C counts before anything new is read."""
import csv
import hashlib
import importlib.util
import json
import os
import pickle
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import sherlock_io as S

_sp = importlib.util.spec_from_file_location("a36", Path(__file__).with_name("36_semiurban_abc.py"))
a36 = importlib.util.module_from_spec(_sp); sys.modules["a36"] = a36; _sp.loader.exec_module(a36)

K_GRID = a36.K_GRID
TARGETS = [0.5, 0.25, 1.0]
N_GRID = [60, 120, 240, 360, 720]          # records of 5 s: 5, 10, 20, 30, 60 minutes
OUT = C.ROOT / "reports" / "topo"
SUFFIX = [""]
TAG = [""]             # post-hoc sensitivity runs (e.g. "_n240"): separate freeze and result files
NMIN_OVERRIDE = [None]          # "_fix": bounds with the remainder correction of scripts/42
DAYS = ["recorded", "split", "split_s8", "split_s9", "split_s10", "split_s11"]


def calib_of(day):
    return "recorded" if day == "recorded" else "split"


def git_hash():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=C.ROOT, text=True).strip()
    except Exception:
        return "unknown"


# ------------------------------------------------------------------ data and cached physics bounds
def load_day(day, workers=4):
    a36.setvar(None if day == "recorded" else day)
    sb = np.load(C.interim("se_residuals.npz"), allow_pickle=True)
    obs = list(sb["obs"]); kinds = np.array([n.split(".")[0] for n in obs])
    cache = C.INTERIM / f"topo_cache_{day}{SUFFIX[0]}.pkl"
    if cache.exists():
        cc = pickle.loads(cache.read_bytes())
    else:
        cfg_tr = a36.topologies("train", sb["train_t"]); cfg_te = a36.topologies("test", sb["test_t"])
        tb = pickle.loads((C.INTERIM / f"abc_train_bounds_{calib_of(day)}.pkl").read_bytes())
        known = {c: b for c, b in zip(tb["cfgs"], tb["bounds"])}
        order = []
        for c in cfg_te:
            if c is not None and c not in order:
                order.append(c)
        new = [c for c in order if c not in known]
        noise_full = a36.noise_from(sb["train_R"], kinds)
        nb = a36.compute_bounds(new, noise_full, obs, 7 + 9000, workers) if new else []   # same seeds as scripts/36
        for c, b in zip(new, nb):
            known[c] = b
        res36 = json.loads((C.ROOT / "reports" / "abc" / f"abc_{day}.json").read_text())
        lat = {x["topology"]: x["compute_s"] for x in res36["impact"]}
        cc = {"cfg_tr": cfg_tr, "cfg_te": cfg_te, "bounds": known, "order": order, "new": new, "lat": lat}
        cache.write_bytes(pickle.dumps(cc))
    return sb, obs, kinds, cc


def margins(variant, k, noise_g, noise_t, bnd, opos_all, n_obs):
    """Margin vector for one topology. noise_t: per-(channel, topology) noise or None (fallback)."""
    nz = noise_g if noise_t is None else noise_t
    m = np.full(n_obs, np.inf)
    o = bnd["opos"]
    if variant in ("B", "B_top"):
        m[o] = k * nz[o]
    else:
        m[o] = np.maximum(k * nz[o], 1.5 * bnd["bound"])
    return m


def fires(Rabs, tid, mby, act, t, L, mask=None):
    f = np.zeros(len(t), bool)
    for j, mg in mby.items():
        sel = (tid == j) & (t >= act.get(j, -np.inf))
        if sel.any():
            f[sel] = np.nanmax(Rabs[sel] / mg, axis=1) > 1.0
    if mask is not None:
        f &= mask
    return a36.runs(f, L)


def local_noise(Rabs, cfgs, kinds, floor, n_min):
    """per-topology noise from records of each topology; returns {cfg: (noise vector, count)}"""
    out = {}
    cnt = {}
    for c in cfgs:
        if c is not None:
            cnt[c] = cnt.get(c, 0) + 1
    for c, n in cnt.items():
        if n >= n_min:
            sel = np.array([x == c for x in cfgs])
            nz = np.nanmax(Rabs[sel], axis=0)
            nz = np.where(np.isfinite(nz), nz, 0.0)
            out[c] = (np.maximum(nz, floor), n)
    return out, cnt


def kind_floor(Rabs, kinds):
    p999 = np.nanpercentile(Rabs, 99.9, axis=0)
    fl = {k: float(np.nanmedian(p999[kinds == k])) for k in set(kinds)}
    return np.array([fl[k] for k in kinds])


# ------------------------------------------------------------------ phase prepare: cache + P1 reproduction
def prepare(workers):
    rows = []
    for day in DAYS:
        sb, obs, kinds, cc = load_day(day, workers)
        fr = json.loads((C.ROOT / "reports" / "abc" / f"frozen_{calib_of(day)}.json").read_text())
        res36 = json.loads((C.ROOT / "reports" / "abc" / f"abc_{day}.json").read_text())
        T, Rabs, L = sb["test_t"], np.abs(sb["test_R"]), int(sb["L"])
        n_obs = len(obs); noise = a36.noise_from(sb["train_R"], kinds)
        order, bounds = cc["order"], cc["bounds"]
        tid = np.array([order.index(c) if c is not None else -1 for c in cc["cfg_te"]])
        first = {j: float(T[np.argmax(tid == j)]) for j in range(len(order))}
        act = {j: (-np.inf if c not in cc["new"] else first[j] + cc["lat"][c.label]) for j, c in enumerate(order)}
        ev = S.load_events(S.root(), "test"); ben = a36.benign_mask(T, ev)
        att = [e for e in ev if e["description"] in a36.PROCESS and "benign" not in e["id"]]
        for var, k, key in (("B", fr["k"]["B"], [n for n in res36["results"] if n.startswith("B: per-channel, calibrated")][0]),
                            ("C", fr["k"]["C"], [n for n in res36["results"] if n.startswith("C: per-channel + physics check, calibrated")][0])):
            mby = {j: margins(var, k, noise, None, bounds[c], None, n_obs) for j, c in enumerate(order)}
            f = fires(Rabs, tid, mby, act if var == "C" else {}, T, L)
            out = {e["id"]: bool(f[(T >= e["start"]) & (T <= e.get("recovery", e["end"]))].any()) for e in att}
            eps, hrs, _ = a36.eph(f, T, ben)
            ref = res36["results"][key]
            diff = [i for i in out if out[i] != ref["out"][i]]
            rows.append([day, var, f"{k:g}", f"{sum(out.values())}/{len(out)}", f"{sum(ref['out'].values())}/{len(ref['out'])}", f"{eps} / {ref['eps']}",
                         f"{hrs:.1f}", "yes" if (not diff and eps == ref["eps"]) else f"NO: events {diff}"])
            print(rows[-1], flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    body = "# Step 1: reproduction of the published A/B/C operating points (protocol P1)\n\n"
    body += C.md_table(["day", "variant", "k (frozen)", "detected now", "detected in scripts/36", "false-alarm episodes now / then", "benign hours", "reproduced"], rows)
    (OUT / "step1_reproduction.md").write_text(body)


# ------------------------------------------------------------------ phase calibrate (P2)
def choose_nmin(Rabs, cfgs):
    cnt = {}
    for i, c in enumerate(cfgs):
        if c is not None:
            cnt.setdefault(c, []).append(i)
    detail = []
    for n in N_GRID:
        ok_all, tested = True, 0
        for c, idx in cnt.items():
            if len(idx) < 2 * n:
                continue
            tested += 1
            a_ = np.nanmax(Rabs[idx[:n]], axis=0); b_ = np.nanmax(Rabs[idx[n:]], axis=0)
            fin = np.isfinite(a_) & np.isfinite(b_)
            cov = float(np.mean(1.5 * a_[fin] >= b_[fin]))
            detail.append([n, c.label[:50], len(idx), f"{cov:.3f}"])
            ok_all &= cov >= 0.99
        if tested and ok_all:
            return n, detail
    return N_GRID[-1], detail


def calibrate(calib):
    day = calib
    sb, obs, kinds, cc = load_day(day)
    Ttr, Rtr, L = sb["train_t"], np.abs(sb["train_R"]), int(sb["L"])
    h = len(Ttr) // 2
    cfg_tr = cc["cfg_tr"]; n_obs = len(obs)
    est_c, sel_c = cfg_tr[:h], cfg_tr[h:]
    noise_g = a36.noise_from(sb["train_R"][:h], kinds)
    floor = kind_floor(Rtr[:h], kinds)
    n_min, nmin_detail = choose_nmin(Rtr[:h], est_c)
    if NMIN_OVERRIDE[0] is not None:
        n_min = NMIN_OVERRIDE[0]
    loc, cnt_est = local_noise(Rtr[:h], est_c, kinds, floor, n_min)
    topo_sel = []
    for c in sel_c:
        if c is not None and c not in topo_sel:
            topo_sel.append(c)
    tid = np.array([topo_sel.index(c) if c is not None else -1 for c in sel_c])
    Rs, Ts = Rtr[h:], Ttr[h:]
    ben = np.ones(len(Ts), bool)
    curves, pick = {}, {}
    for var in ("B", "C", "B_top", "C_top"):
        cur = []
        for k in K_GRID:
            mby = {j: margins(var, k, noise_g, (loc[c][0] if (var.endswith("_top") and c in loc) else None), cc["bounds"][c], None, n_obs)
                   for j, c in enumerate(topo_sel)}
            f = fires(Rs, tid, mby, {}, Ts, L)
            eps, hrs, _ = a36.eph(f, Ts, ben)
            cur.append([k, eps, round(hrs, 3), eps / hrs])
        curves[var] = cur
        for tg in TARGETS:
            okk = [c for c in cur if c[3] <= tg]
            ch = okk[0] if okk else cur[-1]
            pick[f"{var}@{tg}"] = {"k": ch[0], "met": bool(okk), "cal_episodes": ch[1], "cal_hours": ch[2]}
    frozen = {"calibration": calib, "code_version": git_hash(), "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "windows": {"noise estimation": [float(Ttr[0]), float(Ttr[h - 1])], "k selection": [float(Ttr[h]), float(Ttr[-1])],
                          "estimation hours": h * 5 / 3600, "selection hours": (len(Ttr) - h) * 5 / 3600},
              "train_hash": hashlib.sha256(np.ascontiguousarray(sb["train_R"]).tobytes()).hexdigest()[:16],
              "k_grid": K_GRID, "targets": TARGETS, "rule": "smallest k on the grid with selection-window episodes per hour <= target; largest k if none",
              "n_min": n_min, "n_grid": N_GRID, "n_min_rule": "smallest n such that, for every topology with >= 2n estimation records, 1.5 x max|r| over its first n records covers the max over the rest on >= 99 % of channels",
              "n_min_detail": nmin_detail, "local_topologies": {c.label: n for c, (_, n) in loc.items()},
              "estimation_counts": {c.label: n for c, n in cnt_est.items()}, "selection_topologies": [c.label for c in topo_sel],
              "fallback": "noise of B (per channel, all estimation records) for topologies with fewer than n_min estimation records or new in the test day",
              "pick": pick, "curves": curves}
    OUT.mkdir(parents=True, exist_ok=True)
    frozen["n_min_override (post hoc sensitivity)"] = NMIN_OVERRIDE[0]
    (OUT / f"frozen_P2_{calib}{TAG[0]}.json").write_text(json.dumps(frozen, indent=1))
    pickle.dump({"noise_g": noise_g, "loc": loc, "floor": floor}, open(C.INTERIM / f"topo_noise_{calib}{TAG[0]}.pkl", "wb"))
    print(json.dumps({k: frozen[k] for k in ("n_min", "local_topologies", "estimation_counts", "pick", "windows")}, indent=1))


# ------------------------------------------------------------------ phase test
def test_day(day):
    sb, obs, kinds, cc = load_day(day)
    calib = calib_of(day)
    fr = json.loads((OUT / f"frozen_P2_{calib}{TAG[0]}.json").read_text())
    nz = pickle.load(open(C.INTERIM / f"topo_noise_{calib}{TAG[0]}.pkl", "rb"))
    assert hashlib.sha256(np.ascontiguousarray(sb["train_R"]).tobytes()).hexdigest()[:16] == fr["train_hash"]
    T, Rabs, L, det = sb["test_t"], np.abs(sb["test_R"]), int(sb["L"]), sb["alarm"].astype(bool)
    n_obs = len(obs); order, bounds = cc["order"], cc["bounds"]
    tid = np.array([order.index(c) if c is not None else -1 for c in cc["cfg_te"]])
    first = {j: float(T[np.argmax(tid == j)]) for j in range(len(order))}
    act = {j: (-np.inf if c not in cc["new"] else first[j] + cc["lat"][c.label]) for j, c in enumerate(order)}
    phys_active = np.array([(j >= 0) and (T[i] >= act[j]) for i, j in enumerate(tid)])
    has_topo = tid >= 0
    ev = S.load_events(S.root(), "test"); ben = a36.benign_mask(T, ev)
    att = [e for e in ev if e["description"] in a36.PROCESS and "benign" not in e["id"]]
    seen = {c for c in cc["cfg_tr"] if c is not None}

    def mby(var, k):
        return {j: margins(var, k, nz["noise_g"], (nz["loc"][c][0] if (var.endswith("_top") and c in nz["loc"]) else None), bounds[c], None, n_obs)
                for j, c in enumerate(order)}

    def evaluate(f, mask=None):
        out, dly = {}, {}
        for e in att:
            sel = (T >= e["start"]) & (T <= e.get("recovery", e["end"]))
            if mask is not None:
                sel &= mask
            hit = bool(f[sel].any()); out[e["id"]] = hit
            if hit:
                dly[e["id"]] = float(T[sel][np.argmax(f[sel])] - e["start"])
        bm = ben if mask is None else ben & mask
        eps, hrs, rate = a36.eph(f & bm, T, bm)
        return out, dly, eps, hrs, rate
    rows, alarms, margins_used = [], {}, {}
    variants = [("A", None, None)]
    for tg in TARGETS:
        for var in ("B", "C", "B_top", "C_top"):
            variants.append((var, tg, fr["pick"][f"{var}@{tg}"]["k"]))
    for var, tg, k in variants:
        if var == "A":
            f = det; active = None
        else:
            m = mby(var, k); margins_used[(var, tg)] = m
            f = fires(Rabs, tid, m, act if var.startswith("C") else {}, T, L)
            active = float(np.mean(phys_active if var.startswith("C") else has_topo))
        alarms[(var, tg)] = f
        for scope, mask in (("whole test day", None), ("both active", phys_active)):
            out, dly, eps, hrs, rate = evaluate(f, mask)
            per = {p.split(":")[0]: [sum(out[e["id"]] for e in att if e["description"] == p), sum(1 for e in att if e["description"] == p)] for p in a36.PROCESS}
            rows.append({"day": day, "scope": scope, "variant": var, "target": tg, "k": k, "detected": sum(out.values()), "instances": len(out),
                         "per_type": per, "fa_episodes": eps, "benign_hours": hrs, "fa_per_hour": eps / hrs if hrs else float("nan"),
                         "benign_records_flagged": rate, "active_share": active, "out": out, "delay": dly})
    # paired: B_top vs C_top (main), B vs C, A vs B_top, per target, whole day
    pairs, onesided = [], []
    for tg in TARGETS:
        for a_, b_ in (("B_top", "C_top"), ("B", "C"), ("A", "B_top")):
            ra = next(r for r in rows if r["variant"] == a_ and (a_ == "A" or r["target"] == tg) and r["scope"] == "whole test day")
            rb = next(r for r in rows if r["variant"] == b_ and r["target"] == tg and r["scope"] == "whole test day")
            oa, ob = ra["out"], rb["out"]
            only_a = [i for i in oa if oa[i] and not ob[i]]; only_b = [i for i in oa if ob[i] and not oa[i]]; both = [i for i in oa if oa[i] and ob[i]]
            pairs.append([day, tg, f"{a_} vs {b_}", len(only_a), ",".join(only_a), len(only_b), ",".join(only_b), len(both),
                          f"{np.median([ra['delay'][i] for i in both]):.0f}" if both else "", f"{np.median([rb['delay'][i] for i in both]):.0f}" if both else ""])
            if a_ == "A":
                continue
            for side, ids, fv in ((a_, only_a, alarms[(a_, tg)]), (b_, only_b, alarms[(b_, tg)])):
                for i in ids:
                    e = next(x for x in att if x["id"] == i)
                    sel = np.where((T >= e["start"]) & (T <= e.get("recovery", e["end"])) & fv)[0]
                    r0 = sel[0]; j = tid[r0]; c = order[j]
                    ma, mb_ = margins_used[(a_, tg)][j], margins_used[(b_, tg)][j]
                    ratio = Rabs[r0] / (ma if side == a_ else mb_)
                    ch = int(np.nanargmax(ratio))
                    reason = ""
                    if side == a_ and b_.startswith("C"):
                        reason = "waiting for physics rule" if not phys_active[r0] else ("physics floor above residual" if Rabs[r0, ch] <= mb_[ch] else "persistence")
                    onesided.append([day, tg, f"{a_} vs {b_}", side, i, e["description"].split(":")[0], c.label, "seen in calibration" if c in seen else "new in test",
                                     obs[ch], f"{Rabs[r0, ch]:.3f}", f"{ma[ch]:.3f}", f"{mb_[ch]:.3f}", f"{T[r0] - e['start']:.0f}", reason])
    # by topology class: detection of events whose window lies in seen vs new topologies (whole day)
    cls = []
    for tg in (0.5,):
        for var in ("A", "B", "C", "B_top", "C_top"):
            r = next(x for x in rows if x["variant"] == var and (var == "A" or x["target"] == tg) and x["scope"] == "whole test day")
            for lab, test in (("seen in calibration", True), ("new in test", False)):
                ids = []
                for e in att:
                    sel = (T >= e["start"]) & (T <= e.get("recovery", e["end"])) & has_topo
                    if sel.any():
                        js = np.bincount(tid[sel]); c = order[int(np.argmax(js))]
                        if (c in seen) == test:
                            ids.append(e["id"])
                bm = ben & np.array([(j >= 0) and ((order[j] in seen) == test) for j in tid])
                eps, hrs, _ = a36.eph(alarms[(var, None if var == "A" else tg)] & bm, T, bm)
                cls.append([day, tg, var, lab, f"{sum(r['out'][i] for i in ids)}/{len(ids)}", eps, f"{hrs:.2f}"])
    # test-day curve for the figure
    curve = []
    for var in ("B", "C", "B_top", "C_top"):
        for k in K_GRID:
            f = fires(Rabs, tid, mby(var, k), act if var.startswith("C") else {}, T, L)
            out, _, eps, hrs, _ = evaluate(f)
            curve.append([day, var, k, sum(out.values()), len(out), eps, hrs])
    res = {"rows": rows, "pairs": pairs, "onesided": onesided, "classes": cls, "curve": curve,
           "n_topologies": len(order), "n_new": len(cc["new"]), "n_local": sum(1 for c in order if c in nz["loc"])}
    (OUT / f"result_{day}{SUFFIX[0]}{TAG[0]}.json").write_text(json.dumps(res, default=lambda o: o if not isinstance(o, np.generic) else o.item()))
    for r in rows:
        if r["scope"] == "whole test day":
            print(day, r["variant"], r["target"], r["k"], f"{r['detected']}/{r['instances']}", r["fa_episodes"], f"{r['benign_hours']:.1f}")


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--phase", choices=["prepare", "calibrate", "test"], required=True)
    ap.add_argument("--calib", default="recorded")
    ap.add_argument("--day", default="recorded")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--nmin", type=int, default=None, help="POST HOC sensitivity: override N_MIN (separate files)")
    ap.add_argument("--fix", action="store_true", help="use the bounds corrected by scripts/42 (k and noise stay frozen)")
    ap.set_defaults(grid="semiurban")
    a = C.init(ap.parse_args())
    if a.fix:
        SUFFIX[0] = "_fix"
    if a.nmin is not None:
        NMIN_OVERRIDE[0] = a.nmin; TAG[0] = f"_n{a.nmin}"
    if a.phase == "prepare":
        prepare(a.workers)
    elif a.phase == "calibrate":
        calibrate(a.calib)
    else:
        test_day(a.day)


if __name__ == "__main__":
    main()
