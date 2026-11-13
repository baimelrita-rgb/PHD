"""T3: derive the three hand-written rules R1, R2, R3 from envelope samples and save
them as JSON (rules/rules.json). All thresholds come from samples drawn here."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import networkx as nx
import numpy as np

from p3 import common as C
from p3 import envelope as E
from p3 import measure as M
from p3 import rules as R

R1_BUS = 11       # feeder-end bus: lowest voltage at nominal load in the base topology (see report)
R2_LINE = 0       # Line 1-2, head of feeder 1


def downstream_loads(line_idx: int) -> list[int]:
    """Loads at buses downstream of a line in the BASE topology (away from the source)."""
    net = E.apply_config(E.base_net(), E.base_config())
    g = E.topology_graph(net)
    f, t = int(net.line.at[line_idx, "from_bus"]), int(net.line.at[line_idx, "to_bus"])
    g.remove_edge(f, t)
    src = int(net.ext_grid.bus.iloc[0])
    side = t if not nx.has_path(g, src, t) else f
    buses = nx.node_connected_component(g, side)
    return [int(i) for i in net.load.index if int(net.load.at[i, "bus"]) in buses], sorted(buses)


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--n", type=int, default=2000)
    a = ap.parse_args()
    idx = M.index()

    # feeder end bus check at nominal state, base topology
    ok, _, _, m_nom = M.evaluate(np.ones(E.dims().n_cont), E.base_config())
    vm_nom = {b: m_nom[idx[f"vm_pu.{b}"]] for b in range(1, 15)}
    lowest = min(vm_nom, key=vm_nom.get)
    assert lowest == R1_BUS, (lowest, vm_nom)

    # narrow training envelope (load scaling [0.6, 0.9] only; DER and topology as full)
    Xn, cin, cfgs = E.sample_lhs(E.ENVELOPE_NARROW, a.n, seed=a.seed + 1000)
    rn = C.evaluate_batch(Xn, cin, cfgs)
    Bn = rn["M"][rn["benign"]]

    # R1
    v_end = Bn[:, idx[f"vm_pu.{R1_BUS}"]]
    tau = float(np.percentile(v_end, 1))

    # R2
    dl, dbuses = downstream_loads(R2_LINE)
    coeffs_dl = {f"load_p.{i}": 1.0 for i in dl}
    load_dl = sum(Bn[:, idx[k]] for k in coeffs_dl)
    ld = Bn[:, idx[f"loading.{R2_LINE}"]]
    x_thr = float(np.percentile(ld, 99))
    y_thr = float(np.percentile(load_dl, 1))
    r2_narrow_fires = int(np.sum((ld > x_thr) & (load_dl < y_thr)))

    # R3: substation balance  d = sum trafo P_hv - sum load P + sum DER P  (= losses)
    net = E._base_net()
    co = {f"trafo_p_hv.{t}": 1.0 for t in net.trafo.index}
    co.update({f"load_p.{i}": -1.0 for i in net.load.index})
    co.update({f"sgen_p.{j}": 1.0 for j in net.sgen.index})
    Xf, cif, _ = E.sample_lhs(E.ENVELOPE_FULL, a.n, seed=a.seed)   # same draw as 02_envelope_smoke
    rf = C.evaluate_batch(Xf, cif, cfgs)
    Bf = rf["M"][rf["benign"]]
    d = sum(c * Bf[:, idx[k]] for k, c in co.items())
    m_marg = 1.5 * float(d.max())
    co_neg = {k: -c for k, c in co.items()}

    rules = {
        "R1": {"name": "R1 naive threshold",
               "description": f"vm_pu at feeder-end bus {R1_BUS} below tau; tau = 1st percentile over the narrow envelope",
               "atoms": [{"type": "threshold", "meas": f"vm_pu.{R1_BUS}", "op": "<", "value": tau, "scale": 0.01}]},
        "R2": {"name": "R2 context rule",
               "description": f"loading of line {R2_LINE} above x AND total downstream load (base topology) below y; x = 99th pct, y = 1st pct over the narrow envelope",
               "atoms": [{"type": "threshold", "meas": f"loading.{R2_LINE}", "op": ">", "value": x_thr, "scale": 10.0},
                         {"type": "linear", "coeffs": coeffs_dl, "op": "<", "value": y_thr, "scale": 1.0}]},
        "R3": {"name": "R3 power balance violation",
               "description": "|sum transformer P_hv - sum load P + sum DER P| > m; m = 1.5 x max loss over the full envelope sample",
               "any_of": [[{"type": "linear", "coeffs": co, "op": ">", "value": m_marg, "scale": 0.1}],
                          [{"type": "linear", "coeffs": co_neg, "op": ">", "value": m_marg, "scale": 0.1}]]},
    }
    R.save(rules, C.RULES_PATH)

    body = "# T3 rules\n\nSaved to `rules/rules.json`. DSL in `src/p3/rules.py`.\n\n"
    body += C.md_table(["quantity", "value"], [
        ["feeder-end bus (lowest vm_pu at nominal load, base topology)", f"bus {lowest}, vm_pu {vm_nom[lowest]:.4f}"],
        ["narrow envelope samples / benign", f"{a.n} / {int(rn['benign'].sum())} (seed {a.seed + 1000})"],
        ["R1 tau (1st pct of vm_pu.11, narrow)", C.fmt(tau, 5)],
        ["R2 line", f"line {R2_LINE} ({net.line.at[R2_LINE, 'name']})"],
        ["R2 downstream buses (base topology)", ", ".join(map(str, dbuses))],
        ["R2 downstream loads", ", ".join(str(i) for i in dl)],
        ["R2 x (99th pct loading %, narrow)", C.fmt(x_thr, 3)],
        ["R2 y (1st pct downstream load MW, narrow)", C.fmt(y_thr, 4)],
        ["R2 narrow samples where R2 fires", r2_narrow_fires],
        ["R3 full-envelope samples / benign", f"{a.n} / {int(rf['benign'].sum())} (seed {a.seed})"],
        ["R3 observed loss d: min, max MW", f"{d.min():.5f}, {d.max():.5f}"],
        ["R3 margin m = 1.5 x max loss, MW", C.fmt(m_marg, 5)],
    ])
    body += ("\nNotes.\n\n"
             "1. R2 and R3 need metered load and DER powers, so `load_p.*` and `sgen_p.*` were added to the measurement vector.\n"
             "2. R3 is written for the whole substation (both transformers) rather than one feeder, because tie switches move loads between feeders.\n"
             "3. R3 |d| > m is a disjunction; the DSL holds it as `any_of` with two conjunctive clauses.\n"
             "4. The R2 downstream set is fixed in the base topology. Reconfiguration can change which loads are actually downstream.\n")
    C.write_report("rules.md", body)
    print(f"tau={tau:.5f} x={x_thr:.3f} y={y_thr:.4f} m={m_marg:.5f}")


if __name__ == "__main__":
    main()
