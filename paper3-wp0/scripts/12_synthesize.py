"""WP1-c: synthesize rules from alerts on the Sherlock grid, certify them with the oracle,
and evaluate them on held-out telemetry.

Alert for an attack instance = the first --alert-s seconds of its window (a stand-in for a
detector alarm). The synthesizer sees only the alert records, the 30 s before them, train
telemetry (noise levels) and the oracle; never the rest of the window, other attacks or
ground truth. Evaluation: firing on the rest of the window, on other instances of the same
attack type, and false alarms on benign test and train records."""
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


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--alert-s", type=float, default=60.0)
    ap.add_argument("--train-step", type=int, default=10)
    ap.add_argument("--bound-budget", type=int, default=1500, help="DE power flows per invariant for the AC residual bound")
    ap.add_argument("--cert-budget", type=int, default=6000, help="search power flows per certification round")
    ap.add_argument("--settle-s", type=float, default=60.0)
    ap.add_argument("--alert-mode", default="detector", choices=["detector", "start"],
                    help="detector: alert starts at the first D1 physics-residual alarm in the window (attack start if none); start: at the attack start")
    ap.add_argument("--min-cfg-records", type=int, default=300, help="train records needed to use a topology-specific noise level")
    ap.set_defaults(grid="sherlock")
    a = C.init(ap.parse_args())
    t0 = time.time()
    cfgs = E.enumerate_configs()
    cidx = Y.config_index()
    delta = X.load_delta(C.bounds_path("linac"))
    delta.pop("linear_atoms", None)
    Ttr, Mtr = records("train", a.train_step)
    Tte, Mte = records("test", 1)
    cfg_tr = [Y.record_config(m, cidx) for m in Mtr]
    cfg_te = [Y.record_config(m, cidx) for m in Mte]

    # noise levels: largest |invariant residual| on train telemetry, per configuration and globally
    net = E._base_net()
    slack_bus = int(net.ext_grid.bus.iloc[0])
    quantities = [("vm", b) for b in net.bus.index if b != slack_bus] + [("p", l) for l in net.line.index]
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

    ev = S.load_events(S.root(), "test")
    att = [e for e in ev if "benign" not in e["id"]]
    near = np.zeros(len(Tte), bool)
    for e in att:
        near |= (Tte >= e["start"] - a.settle_s) & (Tte <= e.get("recovery", e["end"]) + a.settle_s)
    benign_te = ~near
    windows = {e["id"]: (Tte >= e["start"]) & (Tte <= e.get("recovery", e["end"])) for e in att}

    # D1 physics-residual detector alarms (WP1-a, same calibration: theta = 2 x train p99.9, L = ceil(1.5 x longest train run))
    d1 = np.load(C.interim("physics_residual_step1.npz"))

    def runs(mask):
        out, c = np.zeros(len(mask), int), 0
        for i, x in enumerate(mask):
            c = c + 1 if x else 0
            out[i] = c
        return out
    d1_alarm = np.zeros(len(d1["test_t"]), bool)
    for m_ in ("vm", "p_line", "p_trafo"):
        th = 2.0 * np.nanpercentile(d1[f"train_{m_}"], 99.9)
        L = max(3, int(np.ceil(1.5 * runs(d1[f"train_{m_}"] > th).max())))
        d1_alarm |= runs(d1[f"test_{m_}"] > th) >= L
    d1_t = d1["test_t"]

    results, library = [], {}
    for e in att:
        t_al = e["start"]
        src = "attack start"
        if a.alert_mode == "detector":
            sel = (d1_t >= e["start"]) & (d1_t <= e.get("recovery", e["end"])) & d1_alarm
            if sel.any():
                t_al, src = float(d1_t[sel][0]), "D1 alarm"
        alert = (Tte >= t_al) & (Tte < t_al + a.alert_s)
        before = (Tte >= e["start"] - 40) & (Tte < e["start"] - 10)
        rest = windows[e["id"]] & (Tte >= t_al + a.alert_s)
        alert_cfgs = collections.Counter(cfg_te[i] for i in np.where(alert)[0])
        T = alert_cfgs.most_common(1)[0][0] if alert_cfgs else None
        cands = []
        if T is not None:
            rows = np.array([i for i in np.where(alert)[0] if cfg_te[i] == T])
            # noise level: global train maximum, or the topology-specific one if larger and well estimated
            noise = dict(noise_glob)
            if n_cfg_tr.get(T, 0) >= a.min_cfg_records:
                noise = {k: max(v, noise_cfg[T].get(k, 0.0)) for k, v in noise.items()}
            cands += Y.synthesize_invariants(Mte[rows], T, noise, a.bound_budget, a.seed + int(e["id"]) * 100)
        st = Y.synthesize_state(Mte[before], Mte[alert]) if before.any() and alert.any() else None
        if st is not None:
            cands.append(st)
        if not cands:
            results.append({"id": e["id"], "type": e["description"], "topology": T.label if T else "outside envelope",
                            "candidate": "none", "verdict": "no candidate", "alert": f"{src} +{t_al - e['start']:.0f} s"})
            continue
        for k, cand in enumerate(cands):
            cert = Y.certify(cand, cfgs, delta, a.cert_budget, a.seed + int(e["id"]) * 100 + 50 + k)
            row = {"id": e["id"], "type": e["description"], "topology": T.label if T else "outside envelope",
                   "alert": f"{src} +{t_al - e['start']:.0f} s",
                   "candidate": cand.rule["name"], "family": cand.family, "verdict": cert["verdict"],
                   "rounds": len(cert["trace"]),
                   "info": {kk: (vv if not isinstance(vv, dict) else None) for kk, vv in cand.info.items()}}
            if cert["verdict"] == "certified":
                f = fires_all(cert["rule"], Mte)
                ftr = fires_all(cert["rule"], Mtr)
                same = [x for x in att if x["description"] == e["description"] and x["id"] != e["id"]]
                row.update({
                    "rest_detected": bool(f[rest].any()) if rest.any() else None,
                    "rest_fraction": float(f[rest].mean()) if rest.any() else None,
                    "other_same_type": f"{sum(bool(f[windows[x['id']]].any()) for x in same)}/{len(same)}",
                    "other_any_type": f"{sum(bool(f[windows[x['id']]].any()) for x in att if x['id'] != e['id'])}/{len(att) - 1}",
                    "fa_test": float(f[benign_te].mean()), "fa_train": float(ftr.mean())})
                library[f"{e['id']}:{cand.rule['name']}"] = cert["rule"]
            results.append(row)
        print(e["id"], e["description"], [(r["candidate"][:40], r["verdict"]) for r in results if r["id"] == e["id"]])
    wall = time.time() - t0
    R.save(library, C.ROOT / "rules" / C.suffixed("synthesized.json"))
    (C.INTERIM / C.suffixed("synthesis_results.json")).write_text(json.dumps(results, indent=2, default=str))

    body = "# WP1-c: rules synthesized from alerts, certified by the oracle\n\n"
    body += (f"Grid: Sherlock (reconstructed). Alert = {a.alert_s:.0f} s of telemetry starting at "
             + ("the first D1 physics-residual alarm inside the attack window, or at the attack start when D1 does not fire "
                "(stand-in for another detector). " if a.alert_mode == "detector" else "the attack start. ")
             + "Noise level = largest invariant residual on train telemetry, globally, or per topology when that topology "
             f"has at least {a.min_cfg_records} train records and its level is larger. The synthesizer "
             "uses only the alert records, the 30 s before, train telemetry (every "
             f"{a.train_step}th record, for noise levels) and the oracle. Family P: physical invariant (reported quantity "
             "minus the linearised AC prediction from metered injections, topology at the alert), margin = "
             f"{Y.MARGIN_FACTOR} x max(oracle AC residual bound, train noise). Family S: state change (line out, load or "
             "DER to zero). Certification: joint DE search "
             f"({a.cert_budget} power flows per round) and the robust exact layer (linearised AC, rule-specific bound "
             f"{Y.BOUND_SAFETY} x AC bound); CEGIS on the margin for family P (at most 5 rounds). Wall time {wall:.0f} s.\n\n")
    rows = []
    for r in results:
        rows.append([r["id"], r["type"], r.get("alert", ""), r["topology"], r["candidate"][:60], r.get("family", ""), r["verdict"], r.get("rounds", ""),
                     "" if r.get("rest_detected") is None else f"{C.fmt(r['rest_detected'])} ({r['rest_fraction']:.2f})",
                     r.get("other_same_type", ""), r.get("other_any_type", ""),
                     "" if "fa_test" not in r else f"{r['fa_test']:.4f}", "" if "fa_train" not in r else f"{r['fa_train']:.4f}"])
    body += C.md_table(["attack id", "type", "alert start", "topology at alert", "candidate rule", "family", "verdict", "rounds",
                        "rest of window: detected (fraction)", "other instances, same type", "other instances, any type",
                        "false alarms, benign test", "false alarms, train"], rows)
    # per type summary
    per = collections.defaultdict(lambda: {"n": 0, "cert": 0, "rest": 0})
    for e in att:
        rr = [r for r in results if r["id"] == e["id"]]
        per[e["description"]]["n"] += 1
        per[e["description"]]["cert"] += int(any(r["verdict"] == "certified" for r in rr))
        per[e["description"]]["rest"] += int(any(r.get("rest_detected") for r in rr))
    body += "\n## Per attack type\n\n"
    body += C.md_table(["type", "instances", "at least one certified rule", "certified rule fires on the rest of the window"],
                       [[k, v["n"], v["cert"], v["rest"]] for k, v in sorted(per.items())])
    verd = collections.Counter(r["verdict"] for r in results)
    body += "\nVerdicts over all candidates: " + ", ".join(f"{k} {v}" for k, v in sorted(verd.items())) + ".\n"
    body += f"\nCertified rules saved to `rules/{C.suffixed('synthesized.json')}` ({len(library)} rules).\n"
    C.write_report("synthesis.md", body)
    print(dict(per), dict(verd), f"{wall:.0f}s")


if __name__ == "__main__":
    main()
