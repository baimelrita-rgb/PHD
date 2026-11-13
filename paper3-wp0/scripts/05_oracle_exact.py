"""T5b: exact oracle (envelope + LinDistFlow + rule in Z3), with AC re-check of every SAT model."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import envelope as E
from p3 import lindistflow as L
from p3 import measure as M
from p3 import oracle_exact as X
from p3 import rules as R


def ac_recheck(rule, x, cfg):
    """Returns (fast AC: conv, benign, fires, margin), (runpp: conv, benign, fires)."""
    ok, ben, viol, m = M.evaluate(x, cfg)
    fast = (ok, ben, ok and R.fires(rule, m), R.margin(rule, m) if ok else np.nan, m)
    net = E.run_reference_pf(x, cfg)
    if net is None:
        return fast, (False, False, False)
    mr = M.vector_from_net(net)
    b, _ = M.benign_check(mr)
    return fast, (True, b, R.fires(rule, mr))


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--rules", default=None)
    ap.add_argument("--report", default="oracle_exact.md")
    a = C.init(ap.parse_args())
    a.rules = a.rules or str(C.rules_path())
    rules = R.load(a.rules)
    cfgs = E.enumerate_configs()
    idx = M.index()
    rows, rc_rows, notes, verdicts = [], [], [], []
    confirmed = {}
    delta = X.load_delta(C.bounds_path())
    for (mode, dl), (name, rule) in [(m, r) for m in (("nominal", None), ("robust", delta)) for r in rules.items()]:
        res = X.solve(rule, cfgs, delta=dl)
        n_sat = sum(p[1] == "sat" for p in res.per_cfg)
        n_unsat = sum(p[1] == "unsat" for p in res.per_cfg)
        if res.note:
            notes.append(f"- {mode}, {name}: {res.note}.")
        rows.append([mode, name, res.status.upper(), f"{n_sat}/{len(res.per_cfg)}", f"{n_unsat}/{len(res.per_cfg)}",
                     C.fmt(res.solve_s, 3), C.fmt(max((p[2] for p in res.per_cfg), default=np.nan), 3)])
        agree = 0
        for cfg, st, dt, x in res.per_cfg:
            if st != "sat":
                continue
            fast, ref = ac_recheck(rule, x, cfg)
            lm = L.model(cfg)
            agree += int(fast[1] and fast[2])
            rc_rows.append([mode, name, f"`{cfg.label}`", f"{lm.vm(x)[11]:.5f}", f"{fast[4][idx['vm_pu.11']]:.5f}" if fast[0] else "⟨·⟩",
                            C.fmt(fast[0]), C.fmt(fast[1]), C.fmt(fast[2]), C.fmt(fast[3]),
                            f"{C.fmt(ref[0])}/{C.fmt(ref[1])}/{C.fmt(ref[2])}"])
        if n_sat:
            notes.append(f"- {mode}, {name}: {agree} of {n_sat} SAT models are benign AND fire the rule on the AC model.")
        confirmed[name] = confirmed.get(name, 0) + agree
        if mode == "robust":
            if res.status == "unsat":
                v = "certified relative to LinDistFlow with the validated error bound delta"
            elif confirmed[name]:
                v = "refuted: a SAT model (nominal or robust) is a confirmed benign AC counterexample"
            else:
                v = "inconclusive in the exact layer: robust SAT, but no SAT model is an AC counterexample; rely on the search layer"
            verdicts.append([name, v])
        print(mode, name, res.status, f"sat {n_sat} unsat {n_unsat} {res.solve_s:.2f}s")
    body = "# T5b exact oracle (Z3, LinDistFlow)\n\n"
    body += ("Encoding in `src/p3/oracle_exact.py`: envelope bounds, LinDistFlow voltages (v = vm^2), benign limits, "
             f"rule; line apparent power through a {X.K}-gon relaxation that over-approximates both the benign set and the "
             "firing set, so UNSAT is a sound certificate for the linear model. One query per topology "
             f"({len(cfgs)} topologies). SAT means at least one topology is SAT.\n\n")
    body += ("Two modes. Nominal: linear model as is (UNSAT certifies the linear model only). Robust: every AC condition is "
             "replaced by the weakest linear condition it implies under the error bounds delta in "
             f"`rules/{C.bounds_path().name}` (" + ", ".join(f"{k} {v:.4g}" for k, v in delta.items()) + "). "
             "Robust UNSAT certifies the AC rule, provided the linear-to-AC error stays within delta on the envelope.\n\n")
    body += C.md_table(["mode", "rule", "result", "topologies SAT", "topologies UNSAT", "total solve time s", "max per query s"], rows)
    body += "\nSee `lindistflow_error.md` for the LinDistFlow error table (G6).\n"
    body += "\n## AC re-check of every SAT model\n\n"
    body += (C.md_table(["rule", "topology", "vm_pu.11 LinDistFlow", "vm_pu.11 AC", "AC converged", "AC benign", "AC fires",
                         "AC margin", "runpp conv/benign/fires"], rc_rows) if rc_rows else "No SAT models.\n")
    body += "\n" + "\n".join(notes) + "\n"
    body += "\n## Verdict per rule (robust mode)\n\n" + C.md_table(["rule", "verdict"], verdicts)
    body += ("\n## R3 in the exact layer\n\n"
             "R3 is syntactically expressible (all its measurements are linear: transformer P, load P, DER P). "
             "But LinDistFlow is lossless: the transformer power equals the sum of downstream net load exactly, so the "
             "R3 residual d is identically 0 in the linear model and R3 can never fire there. Its UNSAT is therefore "
             "vacuous: it certifies nothing about R3 on the real grid, where d equals the network losses. "
             "In robust mode the transformer power error bound enters R3 as slack (two transformers), which is "
             "larger than the margin unless losses are bounded more tightly; the robust verdict above says what happens. "
             "A loss-aware layer (for example loss bounds or a convex relaxation) is needed to certify balance rules.\n")
    C.write_report(a.report, body)


if __name__ == "__main__":
    main()
