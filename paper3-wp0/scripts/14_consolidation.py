"""WP1-d: self-consolidation loop on the Sherlock test day, without labels.

The test telemetry is replayed in time order. Alerts come only from detectors: D1 (physics
residual, WP1-a) and the physics-informed autoencoder (scripts/13). Alarm runs closer than
--merge-s are merged into one alert episode. For each episode, in time order:
  1. if the rule library already fires within the first --alert-s seconds, the episode is
     "covered by the library" and nothing is synthesized;
  2. otherwise rules are synthesized from the first --alert-s seconds (family G: grid-wide
     invariants of the alert topology, one rule per topology; family S: state change), the
     oracle certifies them, and certified rules enter the library.
Labels are used only afterwards, for evaluation: which attacks the library caught with rules
learned from earlier alerts, how early compared with the detectors, and the library's false
alarms on benign records."""
import collections
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import envelope as E
from p3 import measure as M
from p3 import oracle_exact as X
from p3 import rules as R
from p3 import sherlock_io as S
from p3 import sherlock_model as SM
from p3 import synthesis as Y


def records(split, step):
    names, net = M.names(), E._base_net()
    T, Mx = [], []
    for i, rec in enumerate(S.iter_state(S.root(), split)):
        if i % step == 0:
            T.append(rec["timestamp"])
            Mx.append(SM.record_measurements(rec["state"], names, net))
    return np.array(T), np.array(Mx)


def fires_all(rule, Mx):
    idx = M.index()
    return np.array([R.margin(rule, m, idx) > 0 for m in Mx])


def episodes(mask, T, merge_s):
    out = []
    on = np.where(mask)[0]
    if not len(on):
        return out
    s = e = on[0]
    for i in on[1:]:
        if T[i] - T[e] <= merge_s:
            e = i
        else:
            out.append((s, e)); s = e = i
    out.append((s, e))
    return out


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--alert-s", type=float, default=60.0)
    ap.add_argument("--merge-s", type=float, default=120.0)
    ap.add_argument("--train-step", type=int, default=10)
    ap.add_argument("--bound-budget", type=int, default=800)
    ap.add_argument("--cert-budget", type=int, default=6000)
    ap.add_argument("--detectors", default="D1,AE")
    ap.add_argument("--min-cfg-records", type=int, default=300)
    ap.add_argument("--settle-s", type=float, default=60.0)
    ap.add_argument("--tag", default="", help="suffix for output files (robustness runs)")
    ap.add_argument("--margin-factor", type=float, default=Y.MARGIN_FACTOR)
    ap.add_argument("--alarms", default="detector_alarms_physics.npz")
    ap.add_argument("--causal", action="store_true",
                    help="chronological activation: synthesis starts when the alert window ends (and the single synthesis "
                         "worker is free); a rule acts only after its synthesis and certification compute time (wall clock, "
                         "this machine) and any calibration window have elapsed")
    ap.add_argument("--topo-cal-s", type=float, default=0.0,
                    help="WP5: per-topology noise calibration. For a topology with fewer than --min-cfg-records train records, "
                         "the first this-many seconds of test records in it without a detector alarm calibrate its noise; its "
                         "grid-wide rule is synthesised with that noise and acts only after the calibration ends (0 = off)")
    ap.add_argument("--artifact", default="", help="red team: SCADA reporting artifact applied to train AND test analog telemetry before "
                    "calibration, synthesis and evaluation, e.g. latency:2 (lag 0..2 s per measurement) or deadband:0.01 (fraction of the training range); "
                    "alert times stay those of the detectors on the recorded telemetry")
    ap.set_defaults(grid="sherlock")
    a = C.init(ap.parse_args())
    Y.MARGIN_FACTOR = a.margin_factor
    t0 = time.time()
    cfgs = E.enumerate_configs()
    cidx = Y.config_index()
    delta = X.load_delta(C.bounds_path("linac"))
    delta.pop("linear_atoms", None)
    if a.artifact:
        import importlib.util
        sp = importlib.util.spec_from_file_location("rt26", Path(__file__).with_name("26_red_team.py"))
        rt = importlib.util.module_from_spec(sp); sp.loader.exec_module(rt)
        kind, val = a.artifact.split(":")
        names_ = M.names()
        cols_ = [i for i, n in enumerate(names_) if n.split(".")[0] in rt.ANALOG]
        Ttr, Mtr = records("train", 1)
        Tte, Mte = records("test", 1)
        rng_ = np.random.default_rng(a.seed + 26)
        if kind == "latency":
            lag_tr = rt.latency(Mtr, cols_, int(val), np.random.default_rng(a.seed + 26))
            Mtr, Mte = lag_tr, rt.latency(Mte, cols_, int(val), np.random.default_rng(a.seed + 26))   # same lag per measurement in both days
        else:
            ranges_ = np.nanmax(Mtr, axis=0) - np.nanmin(Mtr, axis=0)
            Mtr, Mte = rt.deadband(Mtr, cols_, float(val), ranges_), rt.deadband(Mte, cols_, float(val), ranges_)
        Ttr, Mtr = Ttr[::a.train_step], Mtr[::a.train_step]
    else:
        Ttr, Mtr = records("train", a.train_step)
        Tte, Mte = records("test", 1)
    cfg_tr = [Y.record_config(m, cidx) for m in Mtr]
    cfg_te = [Y.record_config(m, cidx) for m in Mte]

    # noise levels on train telemetry (as in scripts/12)
    net = E._base_net()
    slack = int(net.ext_grid.bus.iloc[0])
    quantities = [("vm", b) for b in net.bus.index if b != slack] + [("p", l) for l in net.line.index]
    noise_cfg, noise_glob = collections.defaultdict(dict), collections.defaultdict(float)
    n_cfg_tr = collections.Counter(x for x in cfg_tr if x is not None)
    for c in n_cfg_tr:
        rows = np.array([i for i, x in enumerate(cfg_tr) if x == c])
        for kind, i in quantities:
            if kind == "p" and not Y.LA.model(c).line_active[i]:
                continue
            co, cc = Y.invariant(c, kind, i)
            v = float(np.max(np.abs(Y.residual(co, cc, Mtr[rows]))))
            noise_cfg[c][(kind, i)] = v
            noise_glob[(kind, i)] = max(noise_glob[(kind, i)], v)

    def noise_for(T):
        n = dict(noise_glob)
        if n_cfg_tr.get(T, 0) >= a.min_cfg_records:
            n = {k: max(v, noise_cfg[T].get(k, 0.0)) for k, v in n.items()}
        return n

    al = np.load(C.interim(a.alarms))
    assert np.allclose(al["t"], Tte)
    det = np.zeros(len(Tte), bool)
    for d in a.detectors.split(","):
        det |= al[d.strip()]
    eps = episodes(det, Tte, a.merge_s)

    def topo_cal(T):
        """Online noise calibration in an unfamiliar topology: residual maxima over the first --topo-cal-s seconds of
        test records in T where no detector alarms (no labels). Returns (noise dict, time from which rules may act)."""
        dt = float(np.median(np.diff(Tte)))
        need = int(round(a.topo_cal_s / dt))
        rows = [i for i, x in enumerate(cfg_te) if x == T and not det[i]][:need]
        if len(rows) < need:
            return None, np.inf
        n = dict(noise_glob)
        for kind, i in quantities:
            if kind == "p" and not Y.LA.model(T).line_active[i]:
                continue
            co, cc = Y.invariant(T, kind, i)
            n[(kind, i)] = max(n.get((kind, i), 0.0), float(np.max(np.abs(Y.residual(co, cc, Mte[rows])))))
        return n, float(Tte[rows[-1]])

    library, lib_fire, log = {}, np.zeros(len(Tte), bool), []
    cert_times = []
    worker_free = -np.inf          # --causal: time at which the single synthesis worker becomes free
    grid_done = set()
    for (s, e) in eps:
        ta = Tte[s]
        alert = (Tte >= ta) & (Tte < ta + a.alert_s)
        entry = {"t": float(ta), "len_s": float(Tte[e] - Tte[s])}
        if lib_fire[alert].any():
            entry["action"] = "covered by library"
            log.append(entry)
            continue
        before = (Tte >= ta - 40) & (Tte < ta - 10)
        Tc = collections.Counter(cfg_te[i] for i in np.where(alert)[0]).most_common(1)
        T = Tc[0][0] if Tc else None
        added = []
        cands = []
        arm = {}
        t_work0 = time.time()
        t_start = max(float(ta) + a.alert_s, worker_free)   # --causal: the alert window must be over first
        if T is not None and T not in grid_done:
            nz = noise_for(T)
            if a.topo_cal_s > 0 and n_cfg_tr.get(T, 0) < a.min_cfg_records:
                nz, arm_t = topo_cal(T)
                if nz is None:
                    nz, arm_t = noise_for(T), np.inf      # never calibrated: the rule never acts
            else:
                arm_t = -np.inf
            cg = Y.synthesize_grid_invariants(T, nz, a.bound_budget, a.seed + len(log) * 100)
            arm[id(cg)] = arm_t
            cands.append(cg)
        st = Y.synthesize_state(Mte[before], Mte[alert]) if before.any() else None
        if st is not None:
            cands.append(st)
        for k, cand in enumerate(cands):
            t_c = time.time()
            if cand.family == "G":
                cert = Y.certify_grid(cand, cfgs, delta, a.cert_budget, a.seed + len(log) * 100 + 50)
                grid_done.add(T)
            else:
                cert = Y.certify(cand, cfgs, delta, a.cert_budget, a.seed + len(log) * 100 + 60 + k)
            t_ready = t_start + (time.time() - t_work0)       # synthesis + certification compute so far in this episode
            if cert["verdict"] == "certified":
                key = cand.rule["name"]
                if a.causal:
                    t_act = max(t_ready, arm.get(id(cand), -np.inf))
                else:
                    t_act = max(float(ta), arm.get(id(cand), -np.inf))   # learned at ta; with WP5 also after calibration
                library[key] = {"rule": cert["rule"], "added_at": t_act, "family": cand.family,
                                "timing": [float(ta), float(ta) + a.alert_s, t_ready, float(arm.get(id(cand), -np.inf)), t_act]}
                f = fires_all(cert["rule"], Mte) & (Tte >= arm.get(id(cand), -np.inf))   # never inside its calibration window
                lib_fire |= f & (Tte >= t_act)     # a rule only acts after it was learned (and calibrated)
                library[key]["fires"] = f
            cert_times.append((cand.family, cert["verdict"], time.time() - t_c, len(R.clauses(cand.rule))))
            added.append(f"{cand.rule['name'][:50]}: {cert['verdict']}")
        if a.causal:
            worker_free = t_start + (time.time() - t_work0)
        entry["topology"] = T.label if T else "outside envelope"
        entry["action"] = "; ".join(added) or "no candidate"
        if arm and np.isfinite(max(arm.values())) and max(arm.values()) > ta:
            entry["action"] += f" (topology calibrated online; rule acts from {max(arm.values()) - Tte[0]:.0f} s)"
        log.append(entry)
        print(f"{ta - Tte[0]:8.0f} s  {entry['action'][:110]}")
    wall = time.time() - t0
    # evaluation cost of the final library per telemetry record (all rules, every record)
    idx_ = M.index(); t_e = time.time(); n_e = min(len(Mte), 5000)
    for m in Mte[:n_e]:
        for v in library.values():
            R.margin(v["rule"], m, idx_)
    eval_us = (time.time() - t_e) / max(n_e, 1) * 1e6

    # evaluation with labels
    ev = S.load_events(S.root(), "test")
    att = sorted([e for e in ev if "benign" not in e["id"]], key=lambda e: e["start"])
    near = np.zeros(len(Tte), bool)
    for e in att:
        near |= (Tte >= e["start"] - a.settle_s) & (Tte <= e.get("recovery", e["end"]) + a.settle_s)
    benign = ~near
    # library firing restricted to rules learned before each attack
    rows, per = [], collections.defaultdict(lambda: [0, 0, 0, 0])
    for e in att:
        sel = (Tte >= e["start"]) & (Tte <= e.get("recovery", e["end"]))
        prior = [v for v in library.values() if v["added_at"] < e["start"]]
        lf = np.zeros(len(Tte), bool)
        for v in prior:
            lf |= v["fires"]
        d_hit = bool(det[sel].any()); l_hit = bool(lf[sel].any())
        d_t = Tte[sel][det[sel]][0] - e["start"] if d_hit else None
        l_t = Tte[sel][lf[sel]][0] - e["start"] if l_hit else None
        per[e["description"]][0] += 1
        per[e["description"]][1] += int(d_hit)
        per[e["description"]][2] += int(l_hit)
        per[e["description"]][3] += int(d_hit or l_hit)
        rows.append([e["id"], e["description"], len(prior), "no" if d_t is None else f"{d_t:.0f} s",
                     "no" if l_t is None else f"{l_t:.0f} s",
                     "" if (d_t is None or l_t is None) else f"{d_t - l_t:+.0f} s"])
    lib_all = np.zeros(len(Tte), bool)
    for v in library.values():
        lib_all |= v["fires"]
    body = "# WP1-d: self-consolidation loop (no labels in the loop)\n\n"
    body += (f"Alerts from detectors only ({a.detectors}; D1 = physics residual, AE = physics-informed autoencoder). "
             f"Alarm runs closer than {a.merge_s:.0f} s form one episode; synthesis uses the first {a.alert_s:.0f} s. "
             "Family G: grid-wide invariants of the alert topology (one rule per topology); family S: state change. "
             "Certification: search and robust exact layer (linearised AC); CEGIS on margins. A rule acts only after the "
             f"time it was learned. Wall time {wall:.0f} s.\n\n")
    body += C.md_table(["quantity", "value"], [
        ["alert episodes", len(eps)],
        ["episodes covered by the library (no synthesis needed)", sum(1 for x in log if x["action"] == "covered by library")],
        ["rules in the final library (G / S)", f"{len(library)} ({sum(v['family'] == 'G' for v in library.values())} / {sum(v['family'] == 'S' for v in library.values())})"],
        ["library false alarm rate on benign test records (final library)", f"{lib_all[benign].mean():.5f}"],
        ["detector false alarm rate on benign test records", f"{det[benign].mean():.5f}"],
    ])
    body += "\n## Episode log\n\n"
    body += C.md_table(["time s", "topology", "action"], [[f"{x['t'] - Tte[0]:.0f}", x.get("topology", ""), x["action"][:120]] for x in log])
    body += ("\n## Attacks in time order\n\nLibrary = rules learned from alerts BEFORE the attack started. Last column: how much "
             "earlier the library fires than the detectors (positive = library earlier).\n\n")
    body += C.md_table(["id", "type", "rules known before", "detector first alarm", "library first firing", "library lead"], rows)
    body += "\n## Per attack type\n\n"
    body += C.md_table(["type", "instances", "detectors", "library (learned earlier)", "detectors or library"],
                       [[k, v[0], v[1], v[2], v[3]] for k, v in sorted(per.items())])
    np.savez_compressed(C.interim(f"consolidation_fires{a.tag}.npz"), t=Tte, det=det, lib_prior=lib_fire, lib_all=lib_all,
                        added_at=np.array([v["added_at"] for v in library.values()]),
                        rule_fires=np.array([v["fires"] for v in library.values()]).reshape(len(library), len(Tte)),
                        rule_names=np.array(list(library.keys())),
                        rule_timing=np.array([v["timing"] for v in library.values()]).reshape(len(library), 5),
                        timing_cols=np.array(["alert start", "synthesis window end", "synthesis + certification done", "calibration done", "acts from"]))
    body += "\n## Cost (scalability)\n\n" + C.md_table(["family", "verdict", "certification wall s", "clauses"], [[f, v, f"{t:.1f}", n] for f, v, t, n in cert_times])
    body += (f"\nEvaluating the final library ({len(library)} rules, "
             f"{sum(len(R.clauses(v['rule'])) for v in library.values())} clauses) on one telemetry record: {eval_us:.0f} microseconds "
             f"(mean over {n_e} records, single core).\n")
    (C.INTERIM / C.suffixed(f"consolidation_cost{a.tag}.json")).write_text(json.dumps({"cert": cert_times, "eval_us": eval_us, "n_rules": len(library)}))
    body += f"\nMargin factor {Y.MARGIN_FACTOR}, seed {a.seed}, detector alarms from `{a.alarms}`.\n"
    C.write_report(f"consolidation{a.tag}.md", body)
    R.save({k: v["rule"] for k, v in library.items()}, C.ROOT / "rules" / C.suffixed(f"library{a.tag}.json"))
    print(dict(per), f"library FA {lib_all[benign].mean():.5f}", f"{wall:.0f}s")


if __name__ == "__main__":
    main()
