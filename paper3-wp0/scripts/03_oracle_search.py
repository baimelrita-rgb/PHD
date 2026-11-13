"""T4: search oracle on the full AC model for R1, R2, R3 (Stage A LHS, Stage B DE)."""
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


def describe(cex, rule):
    if cex is None:
        return "⟨none⟩"
    s, g = E.split_x(cex.x)
    idx = M.index()
    keys = sorted({k for c in R.clauses(rule) for a in c for k in ([a["meas"]] if "meas" in a else a["coeffs"])})
    shown = [k for k in keys if not k.startswith("load_p.")][:4]
    vals = ", ".join(f"{k}={cex.m[idx[k]]:.4f}" for k in shown)
    if any(k.startswith("load_p.") for k in keys):
        lin = [a for c in R.clauses(rule) for a in c if a["type"] == "linear"]
        for a in lin[:1]:
            vals += f", linear lhs={sum(v * cex.m[idx[k]] for k, v in a['coeffs'].items()):.4f}"
    return (f"topology `{cex.cfg.label}`; load scale min/mean/max {s.min():.3f}/{s.mean():.3f}/{s.max():.3f}; "
            f"DER min/mean/max {g.min():.3f}/{g.mean():.3f}/{g.max():.3f}; {vals}")


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--n-lhs", type=int, default=10000)
    ap.add_argument("--budget", type=int, default=2000)
    ap.add_argument("--report", default="oracle_search.md")
    ap.add_argument("--rules", default=str(C.RULES_PATH))
    a = ap.parse_args()
    rules = R.load(a.rules)

    t0 = time.time()
    X, ci, cfgs = E.sample_lhs(E.ENVELOPE_FULL, a.n_lhs, seed=a.seed + 2000)
    res = C.evaluate_batch(X, ci, cfgs)
    t_lhs = time.time() - t0
    np.savez_compressed(C.INTERIM / f"oracle_stageA_seed{a.seed}.npz", X=X, ci=ci, **res)

    rows, details, prows = [], [], []
    for name, rule in rules.items():
        A = O.stage_a(rule, res, X, ci, cfgs)
        B = O.stage_b(rule, cfgs, budget=a.budget, seed=a.seed)
        found_by = "A" if A.found else ("B" if B.found else "none")
        best = A if A.found else B
        rc = O.recheck_reference(rule, best.cex) if best.cex is not None else None
        t_rule = t_lhs / len(rules) + A.wall_s + B.wall_s
        rows.append([name, C.fmt(A.found or B.found), found_by,
                     f"{A.n_cex}/{int(res['benign'].sum())}", C.fmt(A.best_margin), B.n_cex, C.fmt(B.best_margin),
                     a.n_lhs + B.n_pf, C.fmt(t_lhs / len(rules) + A.wall_s, 2), C.fmt(B.wall_s, 2), C.fmt(t_rule, 2),
                     "⟨n/a⟩" if rc is None else f"conv {C.fmt(rc[0])}, benign {C.fmt(rc[1])}, fires {C.fmt(rc[2])}"])
        details.append(f"- **{name}** ({rule['name']}): Stage A best: {describe(A.cex, rule) if A.found else 'no firing benign sample'}. "
                       f"Stage B best: {describe(B.cex, rule) if B.found else 'no firing benign state, best margin ' + C.fmt(B.best_margin)}.")
        prows += [[name, lab, n, C.fmt(bm), nc] for lab, n, bm, nc in B.per_cfg]
        print(name, "found_by", found_by, "A", A.n_cex, "B", B.n_cex, f"{t_rule:.1f}s")

    body = "# T4 search oracle on the full AC model\n\n"
    body += (f"Stage A: {a.n_lhs} Latin hypercube samples of the full envelope (seed {a.seed + 2000}), shared by all rules. "
             f"Stage B: differential evolution per topology ({len(cfgs)} topologies), hard budget {a.budget} power flows per rule "
             f"split evenly, population 15 initialised by LHS, no polishing, seed {a.seed}+topology index. "
             "Margin is positive iff the rule fires, in the units set by each atom's `scale`. "
             "Non-benign states are penalised, so every reported counterexample is benign by construction; "
             "the best counterexample is also re-solved with pandapower `runpp` (last column).\n\n")
    body += C.md_table(["rule", "counterexample found", "found by stage", "Stage A firing benign samples", "Stage A best margin",
                        "Stage B firing evaluations", "Stage B best margin", "power flows", "Stage A time share s",
                        "Stage B time s", "time per certification s", "runpp re-check of best counterexample"], rows)
    body += ("\nStage A time is split evenly across the rules because the samples are shared. "
             "Time per certification = Stage A share + Stage B. Measured on this container's CPU, not a laptop.\n\n")
    body += "## Counterexample states\n\n" + "\n".join(details) + "\n\n"
    body += "## Stage B per topology\n\n" + C.md_table(["rule", "topology", "power flows", "best margin", "firing evaluations"], prows)
    C.write_report(a.report, body)


if __name__ == "__main__":
    main()
