"""Diagnose the R3 counterexample found at larger search budgets (stop condition 2).

Question: is the envelope wrong, or the rule? R3 fires when the substation power
balance residual d (= network losses for a correct measurement set) exceeds m.
m was set to 1.5 x the largest loss seen in 2000 LHS samples. This script maximises
d over benign states with DE per topology and compares the maxima with m."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import envelope as E
from p3 import measure as M
from p3 import oracle_search as O
from p3 import rules as R


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--budget-per-topology", type=int, default=3000)
    a = ap.parse_args()
    rules = R.load(C.RULES_PATH)
    r3 = rules["R3"]
    atom = r3["any_of"][0][0]
    co = atom["coeffs"]
    # diagnostic of the round-1 procedure: margin from the sample maximum only
    m_thr = 1.5 * r3["calibration"]["sample_max_mw"]
    # a rule whose margin is simply d (fires when d > 0): maximising it maximises losses
    loss_rule = {"atoms": [{"type": "linear", "coeffs": co, "op": ">", "value": 0.0, "scale": 0.1}]}
    idx = M.index()
    vm_cols = [idx[k] for k in M.names() if k.startswith("vm_pu.")]
    ld_cols = [idx[k] for k in M.names() if k.startswith("loading.")]
    sA = np.load(C.INTERIM / f"oracle_stageA_seed{a.seed}.npz")
    dA = sum(c * sA["M"][sA["benign"]][:, idx[k]] for k, c in co.items())
    t0 = time.time()
    rows, best = [], (-np.inf, None, None)
    for i, cfg in enumerate(E.enumerate_configs()):
        st = O._de_one(loss_rule, cfg, E.full(), a.budget_per_topology, a.seed + 100 + i)
        dmax = 0.1 * st["best"]
        m = st["best_m"]
        s, g, _ = E.split_x(st["best_x"])
        rows.append([f"`{cfg.label}`", st["n"], C.fmt(dmax, 4), C.fmt(dmax > m_thr),
                     C.fmt(m[vm_cols].min(), 4), C.fmt(m[ld_cols].max(), 2), C.fmt(s.mean(), 3), C.fmt(g.mean(), 3)])
        if dmax > best[0]:
            best = (dmax, cfg, st)
    wall = time.time() - t0
    dmax, cfg, st = best
    rc = O.recheck_reference(loss_rule, O.Counterexample("diag", cfg, st["best_x"], 0, st["best_m"]))
    body = "# R3 diagnostic (stop condition 2, round 1 procedure)\n\n"
    body += C.md_table(["quantity", "value"], [
        ["round-1 margin (1.5 x sample max), MW", C.fmt(m_thr, 5)],
        ["current R3 margin (1.5 x max(sample, search)), MW", C.fmt(atom["value"], 5)],
        ["max loss in the 2000-sample calibration set (from rules.md), MW", C.fmt(m_thr / 1.5, 5)],
        ["max loss in Stage A, 10000 LHS samples, MW", C.fmt(dA.max(), 5)],
        ["max benign loss found by DE (this script), MW", C.fmt(dmax, 5)],
        ["topology of that state", f"`{cfg.label}`"],
        ["ratio max found / calibration max", C.fmt(dmax / (m_thr / 1.5), 3)],
        ["runpp re-check of that state: converged, benign, d", f"{C.fmt(rc[0])}, {C.fmt(rc[1])}, {C.fmt(0.1 * rc[3], 5)}"],
        ["DE power flows / wall time s", f"{sum(r[1] for r in rows)} / {wall:.1f}"],
    ])
    body += "\nPer topology (DE maximising d over benign states):\n\n"
    body += C.md_table(["topology", "power flows", "max d MW", "d > m (R3 fires)", "min vm_pu at that state",
                        "max line loading %", "mean load scale", "mean DER"], rows)
    body += ("\nOutcome: the round-1 calibration (sample maximum) was too small. Since round 2, `02b_build_rules.py` "
             "calibrates m by search; the current R3 in `rules/rules.json` uses that margin.\n")
    C.write_report("r3_diagnostic.md", body)
    print(f"m={m_thr:.4f} calib max={m_thr/1.5:.4f} LHS10k max={dA.max():.4f} DE max={dmax:.4f} ({cfg.label})")


if __name__ == "__main__":
    main()
