"""WP2-b: on-demand certification and the rule library on 02-Semiurban (partial observability).

Rule family SE, one rule per topology T: fires when, for some monitored measurement i, the
state-estimation residual |r_i| (measured minus AC model at the iterated estimate, in units of
the noise sigma) exceeds a margin m_i. Margin m_i = 1.5 x max(train noise level of i, oracle
bound of i for T). The oracle bound is the largest |r_i| over benign AC states of T (sampling
plus differential evolution on max_i |r_i| / m_i); a state firing the rule is a benign
counterexample and raises the margins (CEGIS). The residual involves AC power flows, so only
the search layer applies: the certificate is AC-validated, not formal.

On demand: the test day is replayed in time order; the first time a topology appears in the
telemetry, its rule is certified (the compute time is reported as latency) and acts from then
on. Detection and false alarms of the library are compared with the SE-BDD detector
(scripts/17), which uses one threshold on max |r| plus persistence."""
import collections
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import envelope as E
from p3 import measure as M
from p3 import oracle_search as O
from p3 import sherlock_io as S
from p3 import state_est as SE

MARGIN_FACTOR = 1.5


def residual_of_state(s, obs_pos, x, cfg, iters):
    """AC benign state x -> measurement vector -> iterated SE residual (aligned to obs)."""
    ok, ben, viol, m = M.evaluate(x, cfg)
    if not ok or not ben:
        return None
    r, _ = SE.residual_ac(s, m, iters=iters)
    if r is None:
        return None
    out = np.full(len(obs_pos), np.nan)
    out[[obs_pos[n] for n in s.names]] = r
    return out


def certify_topology(cfg, noise, obs, obs_pos, n_samples, budget, seed, iters, max_rounds=3):
    s = SE.se(cfg)
    t0 = time.time()
    X, _, _ = E.sample_lhs(E.full(), n_samples, seed=seed, configs=(cfg,))
    bound = np.zeros(len(obs))
    for x in X:
        r = residual_of_state(s, obs_pos, x, cfg, iters)
        if r is not None:
            bound = np.fmax(bound, np.abs(r))
    margin = MARGIN_FACTOR * np.fmax(noise, bound)
    rounds = []
    for rnd in range(1, max_rounds + 1):
        def score(x, m, c, margin=margin):
            r, _ = SE.residual_ac(s, m, iters=iters)
            if r is None:
                return -1.0
            out = np.full(len(obs), np.nan)
            out[[obs_pos[n] for n in s.names]] = r
            return float(np.nanmax(np.abs(out) / margin) - 1.0)      # > 0 means the rule fires
        st = O.de_maximize(lambda x, m: score(x, m, cfg), cfg, E.full(), budget, seed + rnd)
        rounds.append(st["best"])
        if st["best"] <= 0:
            return margin, {"verdict": "certified (search)", "rounds": rounds, "seconds": time.time() - t0}
        r = residual_of_state(s, obs_pos, st["best_x"], cfg, iters)
        bound = np.fmax(bound, np.abs(r))
        margin = MARGIN_FACTOR * np.fmax(noise, bound)
    return margin, {"verdict": "refuted (search)", "rounds": rounds, "seconds": time.time() - t0}


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--n-samples", type=int, default=40)
    ap.add_argument("--budget", type=int, default=150)
    ap.add_argument("--iters", type=int, default=1)
    ap.add_argument("--settle-s", type=float, default=60.0)
    ap.add_argument("--tag", default="")
    ap.add_argument("--noise-from", default=None, help="grid whose per-kind noise floors are transferred (grids without a train day)")
    ap.add_argument("--calib-prefix-s", type=float, default=0.0,
                    help="grids without a train day: calibrate per-measurement noise on the first seconds of the test day (attack free); not evaluated")
    ap.add_argument("--noise-mode", default="perkind", choices=["perkind", "global"],
                    help="with --noise-from: perkind = transferred per-kind floors; global = every margin at least the transferred SE-BDD threshold")
    ap.add_argument("--margin-factor", type=float, default=MARGIN_FACTOR)
    ap.set_defaults(grid="semiurban")
    a = C.init(ap.parse_args())
    globals()["MARGIN_FACTOR"] = a.margin_factor
    t0 = time.time()
    d = np.load(C.interim("se_residuals.npz"), allow_pickle=True)
    obs = list(d["obs"]); obs_pos = {n: k for k, n in enumerate(obs)}
    Ttr, Rtr, Tte, Rte, det = d["train_t"], d["train_R"], d["test_t"], d["test_R"], d["alarm"]
    kinds = np.array([n.split(".")[0] for n in obs])
    if a.calib_prefix_s > 0:      # short benign calibration period on this grid (03-Rural)
        pre = Tte < Tte[0] + a.calib_prefix_s
        Rcal = Rte[pre]
        noise = np.nanmax(np.abs(Rcal), axis=0)
        noise = np.where(np.isfinite(noise), noise, np.nanmax(noise))
        p999 = np.nanpercentile(np.abs(Rcal), 99.9, axis=0)
        floor = {k: float(np.nanmedian(p999[kinds == k])) for k in set(kinds)}
        noise = np.maximum(noise, np.array([floor[k] for k in kinds]))
    elif a.noise_from:      # no train day: per-kind noise floors transferred from another grid of the same dataset
        src = np.load(C.INTERIM / f"se_residuals_{a.noise_from}.npz", allow_pickle=True)
        s_obs = np.array([n.split(".")[0] for n in src["obs"]])
        s_p999 = np.nanpercentile(np.abs(src["train_R"]), 99.9, axis=0)
        floor = {k: float(np.nanmedian(s_p999[s_obs == k])) for k in set(s_obs)}
        noise = np.array([floor.get(k, max(floor.values())) for k in kinds])
        if a.noise_mode == "global":     # margin_i >= transferred global threshold theta
            noise = np.full(len(kinds), float(src["th"]) / MARGIN_FACTOR)
            floor = {"all kinds (theta / margin factor)": float(src["th"]) / MARGIN_FACTOR}
    else:
        noise = np.nanmax(np.abs(Rtr), axis=0)
        noise = np.where(np.isfinite(noise), noise, np.nanmax(noise))
        # noise floor per measurement kind: a measurement idle in every train topology (for example a
        # line without flow) has train noise 0, but carries ordinary noise once a new topology loads it
        p999 = np.nanpercentile(np.abs(Rtr), 99.9, axis=0)
        floor = {k: float(np.nanmedian(p999[kinds == k])) for k in set(kinds)}
        noise = np.maximum(noise, np.array([floor[k] for k in kinds]))
    # topology of each test record, recomputed from the telemetry (same as scripts/17)
    from p3 import sherlock_model as SM
    names, net, idx = M.names(), E._base_net(), M.index()
    other_sw = [int(s_) for s_ in net.switch.index if net.switch.et.at[s_] != "l"]
    fixed = SM.fixed_switch_states()
    step = int(round(np.median(np.diff(Tte)))) if len(Tte) > 1 else 1
    cfg_te = []
    want = set(np.round(Tte, 3))
    for rec in S.iter_state(S.root(), "test"):
        if round(rec["timestamp"], 3) not in want:
            continue
        st = rec["state"]
        if any(not st.get(f"switch.{s_}:is_closed", fixed[s_]) for s_ in other_sw):
            cfg_te.append(None); continue
        m = SM.record_measurements(st, names, net)
        out = tuple(l for l in range(len(net.line)) if m[idx[f"line_in.{l}"]] < 0.5)
        cfg_te.append(E.Config((), None if not out else (out[0] if len(out) == 1 else out), ()))
    assert len(cfg_te) == len(Tte), (len(cfg_te), len(Tte))

    library, log = {}, []
    fires = np.zeros(len(Tte), bool)
    for k, (t, cfg) in enumerate(zip(Tte, cfg_te)):
        if cfg is None:
            continue
        if cfg not in library:
            margin, info = certify_topology(cfg, noise, obs, obs_pos, a.n_samples, a.budget, a.seed + len(library) * 10, a.iters)
            library[cfg] = (margin, info, t)
            log.append([f"{t - Tte[0]:.0f}", cfg.label[:70], info["verdict"], f"{info['seconds']:.0f}", len(info["rounds"])])
            print(log[-1])
        margin, info, _ = library[cfg]
        if info["verdict"].startswith("certified"):
            fires[k] = bool(np.nanmax(np.abs(Rte[k]) / margin) > 1.0) if np.isfinite(Rte[k]).any() else False
    wall = time.time() - t0
    L = int(d["L"])

    def runs(mask):
        out, c = np.zeros(len(mask), int), 0
        for i, x in enumerate(mask):
            c = c + 1 if x else 0
            out[i] = c
        return out
    fires_p = runs(fires) >= L          # deployment setting: same persistence filter as the detector

    ev = S.load_events(S.root(), "test")
    att = [e for e in ev if "benign" not in e["id"]]
    near = np.zeros(len(Tte), bool)
    for e in att:
        near |= (Tte >= e["start"] - a.settle_s) & (Tte <= e.get("recovery", e["end"]) + a.settle_s)
    benign = ~near
    if a.calib_prefix_s > 0:
        benign &= Tte >= Tte[0] + a.calib_prefix_s       # calibration period is not evaluated
    per = collections.defaultdict(lambda: [0, 0, 0, 0, 0])
    rows = []
    for e in att:
        sel = (Tte >= e["start"]) & (Tte <= e.get("recovery", e["end"]))
        dh, lh, lph = bool(det[sel].any()), bool(fires[sel].any()), bool(fires_p[sel].any())
        p_ = per[e["description"]]
        p_[0] += 1; p_[1] += int(dh); p_[2] += int(lh); p_[3] += int(lph); p_[4] += int(dh or lph)
        rows.append([e["id"], e["description"], "yes" if dh else "no", "yes" if lh else "no", "yes" if lph else "no"])
    body = "# WP2-b: on-demand certification and rule library on 02-Semiurban\n\n"
    body += (f"Rule per topology: some monitored measurement's state-estimation residual exceeds its margin "
             f"({MARGIN_FACTOR} x max(train noise, oracle bound)); " + (
                 f"noise per measurement = per-kind floor transferred from {a.noise_from} (" if a.noise_from else
                 "train noise of a measurement is its train maximum, floored at the median over its measurement kind of the train 99.9th percentile (")
             + ", ".join(f"{k} {v:.2f}" for k, v in sorted(floor.items())) + "). Oracle: {a.n_samples} sampled benign AC states plus "
             f"differential evolution ({a.budget} evaluations per round, at most 3 rounds of CEGIS on the margins). The residual "
             "needs AC power flows, so only the search layer applies (AC-validated, not a formal certificate). Topologies are "
             f"certified on demand when they first appear in the test telemetry (every {step} s). Wall time {wall:.0f} s.\n\n")
    body += C.md_table(["quantity", "value"], [
        ["topologies certified on demand", sum(1 for v in library.values() if v[1]["verdict"].startswith("certified"))],
        ["topologies refuted after CEGIS", sum(1 for v in library.values() if not v[1]["verdict"].startswith("certified"))],
        ["certification latency per topology, s (median / max)", f"{np.median([v[1]['seconds'] for v in library.values()]):.0f} / {max(v[1]['seconds'] for v in library.values()):.0f}"],
        ["library false alarm rate, benign test records (single record)", f"{fires[benign].mean():.5f}"],
        [f"library false alarm rate with the detector's persistence filter (L = {L} records)", f"{fires_p[benign].mean():.5f}"],
        ["SE-BDD detector false alarm rate, benign test records", f"{det[benign].mean():.5f}"],
    ])
    body += "\nOn-demand certification log:\n\n" + C.md_table(["time s", "topology", "verdict", "compute s", "rounds"], log)
    types = sorted(per)
    body += "\nDetection per attack type:\n\n" + C.md_table(["type", "instances", "SE-BDD detector", "certified library (single record)", f"library with persistence L = {L}", "detector or library with persistence"],
                                                         [[t, *per[t]] for t in types])
    body += "\nPer instance:\n\n" + C.md_table(["id", "type", "detector", "library", "library with persistence"], rows)
    np.savez_compressed(C.interim(f"semiurban_fires{a.tag}.npz"), t=Tte, det=det, fires=fires, fires_p=fires_p, L=L)
    body += f"\nMargin factor {MARGIN_FACTOR}, seed {a.seed}.\n"
    C.write_report(f"semiurban_consolidation{a.tag}.md", body)
    print({t: per[t] for t in types}, "library FA", f"{fires[benign].mean():.5f}", "with persistence", f"{fires_p[benign].mean():.5f}", "detector FA", f"{det[benign].mean():.5f}", f"{wall:.0f}s")


if __name__ == "__main__":
    main()
