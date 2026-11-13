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
    ap.set_defaults(grid="sherlock")
    a = C.init(ap.parse_args())
    Y.MARGIN_FACTOR = a.margin_factor
    t0 = time.time()
    cfgs = E.enumerate_configs()
    cidx = Y.config_index()
    delta = X.load_delta(C.bounds_path("linac"))
    delta.pop("linear_atoms", None)
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

    library, lib_fire, log = {}, np.zeros(len(Tte), bool), []
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
        if T is not None and T not in grid_done:
            cands.append(Y.synthesize_grid_invariants(T, noise_for(T), a.bound_budget, a.seed + len(log) * 100))
        st = Y.synthesize_state(Mte[before], Mte[alert]) if before.any() else None
        if st is not None:
            cands.append(st)
        for k, cand in enumerate(cands):
            if cand.family == "G":
                cert = Y.certify_grid(cand, cfgs, delta, a.cert_budget, a.seed + len(log) * 100 + 50)
                grid_done.add(T)
            else:
                cert = Y.certify(cand, cfgs, delta, a.cert_budget, a.seed + len(log) * 100 + 60 + k)
            if cert["verdict"] == "certified":
                key = cand.rule["name"]
                library[key] = {"rule": cert["rule"], "added_at": float(ta), "family": cand.family}
                f = fires_all(cert["rule"], Mte)
                lib_fire |= f & (Tte >= ta)        # a rule only acts after it was learned
                library[key]["fires"] = f
            added.append(f"{cand.rule['name'][:50]}: {cert['verdict']}")
        entry["topology"] = T.label if T else "outside envelope"
        entry["action"] = "; ".join(added) or "no candidate"
        log.append(entry)
        print(f"{ta - Tte[0]:8.0f} s  {entry['action'][:110]}")
    wall = time.time() - t0

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
                        rule_fires=np.array([v["fires"] for v in library.values()]).reshape(len(library), len(Tte)))
    body += f"\nMargin factor {Y.MARGIN_FACTOR}, seed {a.seed}, detector alarms from `{a.alarms}`.\n"
    C.write_report(f"consolidation{a.tag}.md", body)
    R.save({k: v["rule"] for k, v in library.items()}, C.ROOT / "rules" / C.suffixed(f"library{a.tag}.json"))
    print(dict(per), f"library FA {lib_all[benign].mean():.5f}", f"{wall:.0f}s")


if __name__ == "__main__":
    main()
