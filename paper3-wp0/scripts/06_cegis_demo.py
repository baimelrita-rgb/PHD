"""T6: counterexample-guided refinement of R1, with the iteration trace and how much
of the original firing region remains."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import cegis as G
from p3 import common as C
from p3 import envelope as E
from p3 import measure as M
from p3 import rules as R


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--budget", type=int, default=2000)
    ap.add_argument("--max-iter", type=int, default=10)
    a = ap.parse_args()
    rules = R.load(C.RULES_PATH)
    r1 = rules["R1"]
    f = C.INTERIM / f"oracle_stageA_seed{a.seed}.npz"
    if not f.exists():
        raise SystemExit(f"missing {f}: run scripts/03_oracle_search.py --seed {a.seed} first")
    d = np.load(f)
    res = {k: d[k] for k in ("conv", "benign", "viol", "M")}
    cfgs = E.enumerate_configs()
    final, trace, done = G.refine_threshold(r1, (d["X"], d["ci"], res), cfgs, budget=a.budget, seed=a.seed,
                                            max_iter=a.max_iter)
    tau0, tau1 = r1["atoms"][0]["value"], final["atoms"][0]["value"]
    col = M.index()["vm_pu.11"]
    v_ben = res["M"][res["benign"], col]
    rows = [[t["iter"], f"{t['tau']:.5f}", t["search_A"], t["search_B"], t["exact"].upper(), t["exact_sat_topologies"],
             "; ".join(f"{k} {v:.5f}" for k, v in t["cex_values"]) or "⟨none⟩", t["action"], f"{t['wall_s']:.1f}"]
            for t in trace]
    retained = max(0.0, (tau1 - E.V_MIN) / (tau0 - E.V_MIN))
    body = "# T6 counterexample-guided refinement of R1\n\n"
    body += (f"Rule: `vm_pu.11 < tau`. Each iteration: search oracle (Stage A, 10000 cached LHS samples; Stage B, DE "
             f"with {a.budget} power flows) and exact oracle (Z3, LinDistFlow). tau moves {G.EPS} pu below the lowest "
             "counterexample voltage (AC value for search, LinDistFlow value for exact). "
             f"Stop at no counterexample in both layers, or after {a.max_iter} iterations.\n\n")
    body += C.md_table(["iter", "tau", "Stage A cex", "Stage B cex evals", "exact", "exact SAT topologies",
                        "counterexample vm_pu.11", "action", "wall s"], rows)
    body += "\n## Outcome\n\n"
    body += C.md_table(["quantity", "value"], [
        ["converged (no counterexample in both layers)", C.fmt(done)],
        ["iterations", len(trace)],
        ["initial tau", f"{tau0:.5f}"],
        ["final tau", f"{tau1:.5f}"],
        ["benign lower voltage limit", f"{E.V_MIN:.2f}"],
        ["lowest benign vm_pu.11 in Stage A samples", f"{v_ben.min():.5f}"],
        ["share of the original firing band [0.90, tau0) left: (tau_final - 0.90) / (tau0 - 0.90), floored at 0", f"{retained:.4f}"],
        ["Stage A benign samples where the original R1 fires", int((v_ben < tau0).sum())],
        ["Stage A benign samples where the final R1 fires", int((v_ben < tau1).sum())],
    ])
    body += ("\nReading: the firing band is measured inside the voltages the envelope calls benign. "
             "If the final tau is at or below 0.90 pu, the refined rule fires only on states that already violate the "
             "operating limit. A voltage limit alarm already catches those, so as an intrusion rule it is useless.\n")
    C.write_report("cegis_demo.md", body)
    print(f"tau0 {tau0:.5f} -> {tau1:.5f}, iterations {len(trace)}, converged {done}, retained {retained:.4f}")


if __name__ == "__main__":
    main()
