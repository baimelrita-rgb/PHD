"""WP1-b step 2: rules for the Sherlock grid, mined from recorded train telemetry, and
their behaviour on the recorded test telemetry.

R1 naive threshold: vm_pu at the feeder-end bus below tau, tau = 1st percentile of that
   bus voltage over the train records (a rule a miner would learn from history).
R2 context rule: loading of line 0 above x AND total downstream load (base topology) below
   y; x = 99th percentile of the line loading, y = 1st percentile of the downstream load,
   both over train records.
R3 power balance: |sum transformer P_hv - sum load P - sum storage P + sum sgen P| > m,
   m = 1.5 x the largest benign residual found over the envelope by LHS and DE search
   (owner decision 4).
Writes rules/rules_sherlock.json and reports/sherlock_rules_sherlock.md."""
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import networkx as nx
import numpy as np

from p3 import common as C
from p3 import envelope as E
from p3 import measure as M
from p3 import oracle_search as O
from p3 import rules as R
from p3 import sherlock_io as S
from p3 import sherlock_model as SM

R2_LINE = 0


def downstream_loads(line_idx):
    net = E.apply_config(E.base_net(), E.base_config())
    g = E.topology_graph(net)
    f, t = int(net.line.at[line_idx, "from_bus"]), int(net.line.at[line_idx, "to_bus"])
    g.remove_edge(f, t)
    side = t if not nx.has_path(g, int(net.ext_grid.bus.iloc[0]), t) else f
    buses = nx.node_connected_component(g, side)
    return [int(i) for i in net.load.index if int(net.load.at[i, "bus"]) in buses]


def records(split, names, net, step):
    T, Mx = [], []
    for i, rec in enumerate(S.iter_state(S.ROOT_DEFAULT, split)):
        if i % step == 0:
            T.append(rec["timestamp"])
            Mx.append(SM.record_measurements(rec["state"], names, net))
    return np.array(T), np.array(Mx)


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--step", type=int, default=1, help="use every step-th 1 Hz record")
    ap.add_argument("--n-lhs", type=int, default=4000)
    ap.add_argument("--calib-budget", type=int, default=20000)
    ap.add_argument("--settle-s", type=float, default=60.0)
    ap.set_defaults(grid="sherlock")
    a = C.init(ap.parse_args())
    names, idx = M.names(), M.index()
    net = E._base_net()

    # bus with the lowest voltage at nominal state in the base configuration
    ok, _, _, m_nom = M.evaluate(np.ones(E.dims().n_cont), E.base_config())
    vm_nom = {b: m_nom[idx[f"vm_pu.{b}"]] for b in range(1, len(net.bus))}
    r1_bus = min(vm_nom, key=vm_nom.get)

    Ttr, Mtr = records("train", names, net, a.step)
    Tte, Mte = records("test", names, net, a.step)

    tau = float(np.percentile(Mtr[:, idx[f"vm_pu.{r1_bus}"]], 1))
    dl = downstream_loads(R2_LINE)
    co_dl = {f"load_p.{i}": 1.0 for i in dl}
    lin = lambda Mx, co: sum(c * Mx[:, idx[k]] for k, c in co.items())
    x_thr = float(np.percentile(Mtr[:, idx[f"loading.{R2_LINE}"]], 99))
    y_thr = float(np.percentile(lin(Mtr, co_dl), 1))

    co = {f"trafo_p_hv.{t}": 1.0 for t in net.trafo.index}
    co.update({f"load_p.{i}": -1.0 for i in net.load.index})
    co.update({f"storage_p.{k}": -1.0 for k in net.storage.index})
    co.update({f"sgen_p.{j}": 1.0 for j in net.sgen.index})
    X, ci, cfgs = E.sample_lhs(E.full(), a.n_lhs, seed=a.seed)
    res = C.evaluate_batch(X, ci, cfgs)
    d_lhs = lin(res["M"][res["benign"]], co)
    st = O.de_maximize_joint(lambda x, m, c: float(sum(w * m[idx[k]] for k, w in co.items())), cfgs, E.full(),
                             a.calib_budget, a.seed + 100)
    m_marg = 1.5 * max(float(d_lhs.max()), float(st["best"]))
    rules = {
        "R1": {"name": "R1 naive threshold (mined from train)",
               "description": f"vm_pu at feeder-end bus {r1_bus} below tau; tau = 1st percentile over train records",
               "atoms": [{"type": "threshold", "meas": f"vm_pu.{r1_bus}", "op": "<", "value": tau, "scale": 0.01}]},
        "R2": {"name": "R2 context rule (mined from train)",
               "description": f"loading of line {R2_LINE} above x AND downstream load (base topology) below y; x = 99th pct, y = 1st pct over train records",
               "atoms": [{"type": "threshold", "meas": f"loading.{R2_LINE}", "op": ">", "value": x_thr, "scale": 10.0},
                         {"type": "linear", "coeffs": co_dl, "op": "<", "value": y_thr, "scale": 1.0}]},
        "R3": {"name": "R3 power balance violation",
               "description": "|sum trafo P_hv - sum load P - sum storage P + sum sgen P| > m; m = 1.5 x max benign residual (LHS and DE)",
               "calibration": {"sample_max_mw": float(d_lhs.max()), "search_max_mw": float(st["best"]),
                               "search_topology": st["best_c"].label, "factor": 1.5},
               "any_of": [[{"type": "linear", "coeffs": co, "op": ">", "value": m_marg, "scale": 0.1}],
                          [{"type": "linear", "coeffs": {k: -v for k, v in co.items()}, "op": ">", "value": m_marg, "scale": 0.1}]]},
    }
    R.save(rules, C.rules_path())

    # behaviour on recorded telemetry
    ev = S.load_events(S.ROOT_DEFAULT, "test")
    att = [e for e in ev if "benign" not in e["id"]]
    near = np.zeros(len(Tte), bool)
    for e in att:
        near |= (Tte >= e["start"] - a.settle_s) & (Tte <= e.get("recovery", e["end"]) + a.settle_s)
    rows, det_rows = [], []
    for name, rule in rules.items():
        f_tr = np.array([R.fires(rule, m, idx) for m in Mtr])
        f_te = np.array([R.fires(rule, m, idx) for m in Mte])
        rows.append([name, f"{f_tr.mean():.4f}", f"{f_te[~near].mean():.4f}"])
        per = collections.defaultdict(lambda: [0, 0])
        for e in att:
            sel = (Tte >= e["start"]) & (Tte <= e.get("recovery", e["end"]))
            per[e["description"]][0] += 1
            per[e["description"]][1] += int(f_te[sel].any())
        det_rows.append([name] + [f"{d}/{n}" for _, (n, d) in sorted(per.items())])
        types = [k for k, _ in sorted(per.items())]
    body = "# WP1-b: Sherlock rules mined from train telemetry\n\n"
    body += C.md_table(["quantity", "value"], [
        ["train / test records used", f"{len(Ttr)} / {len(Tte)} (every {a.step}th, 1 Hz)"],
        ["R1 bus (lowest vm_pu at nominal, base configuration)", f"bus {r1_bus}, {vm_nom[r1_bus]:.4f} pu"],
        ["R1 tau (1st pct of train vm)", f"{tau:.5f}"],
        ["R2 x (99th pct of train line 0 loading, %)", f"{x_thr:.3f}"],
        ["R2 downstream loads (base topology)", ", ".join(map(str, dl))],
        ["R2 y (1st pct of train downstream load, MW)", f"{y_thr:.4f}"],
        [f"R3 max benign residual: LHS ({int(res['benign'].sum())} benign of {a.n_lhs}) / DE ({a.calib_budget} flows), MW",
         f"{d_lhs.max():.5f} / {st['best']:.5f} (`{st['best_c'].label}`)"],
        ["R3 margin m, MW", f"{m_marg:.5f}"],
    ])
    body += "\n## Firing on recorded telemetry\n\nFraction of records where the rule fires (a false alarm, since these records are benign):\n\n"
    body += C.md_table(["rule", "train records", f"benign test records (more than {a.settle_s:.0f} s from attacks)"], rows)
    body += "\nAttack instances with at least one firing record inside the window:\n\n"
    body += C.md_table(["rule"] + types, det_rows)
    body += ("\nThese are recorded data, independent of the oracle. The oracle results for the same rules are in "
             "`oracle_search_sherlock.md` and `oracle_exact_sherlock.md`.\n")
    C.write_report("sherlock_rules.md", body)
    print(f"R1 bus {r1_bus} tau {tau:.5f}; R2 x {x_thr:.2f} y {y_thr:.3f}; R3 m {m_marg:.4f}")
    for r in rows:
        print(r)
    for r in det_rows:
        print(r)


if __name__ == "__main__":
    main()
