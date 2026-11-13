"""Rule-specific error bounds: for every linear rule atom whose measurements carry model
error (p_from, trafo_p_hv), the worst |linear - AC| of the expression ITSELF over benign
states (samples, then joint DE), times the safety factor. Errors of the terms are
correlated, so this is usually far below the sum of per-quantity bounds. Added to the
model's bounds file under "linear_atoms"; the robust encoder uses the smaller of the two."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import envelope as E
from p3 import measure as M
from p3 import oracle_exact as X
from p3 import oracle_search as O
from p3 import rules as R

ERR_KINDS = ("p_from", "trafo_p_hv")


def lin_value(lm, coeffs, x, inj):
    pl, ql, pg, pb = inj(x)
    v = 0.0
    for k, w in coeffs.items():
        kind, i = k.split(".")
        i = int(i)
        v += w * {"p_from": lambda: lm.p_from(x)[i], "trafo_p_hv": lambda: lm.trafo_p(x)[i],
                  "load_p": lambda: pl[i], "sgen_p": lambda: pg[i], "storage_p": lambda: pb[i]}[kind]()
    return v


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--model", default="linac", choices=["lindistflow", "linac"])
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--budget", type=int, default=20000)
    ap.add_argument("--safety", type=float, default=1.25)
    ap.add_argument("--rules", default=None)
    a = C.init(ap.parse_args())
    rules = R.load(a.rules or C.rules_path())
    cfgs = tuple(c for c in E.enumerate_configs() if a.model != "lindistflow" or E.is_radial(c))
    inj = E.injection_maps()
    idx = M.index()
    atoms = {}
    for r in rules.values():
        for cl in R.clauses(r):
            for at in cl:
                if at["type"] == "linear" and any(k.split(".")[0] in ERR_KINDS for k in at["coeffs"]):
                    atoms[X.atom_key(at["coeffs"])] = at["coeffs"]
    X_, ci, _ = E.sample_lhs(E.full(), a.n, seed=a.seed + 4000, configs=cfgs)
    res = C.evaluate_batch(X_, ci, cfgs)
    out, rows = {}, []
    for key, co in atoms.items():
        def err(x, m, c, co=co):
            lm = X.linear_model(c, a.model)
            return abs(lin_value(lm, co, x, inj) - sum(w * m[idx[k]] for k, w in co.items()))
        samp = max(err(X_[i], res["M"][i], cfgs[ci[i]]) for i in np.where(res["benign"])[0])
        st = O.de_maximize_joint(err, cfgs, E.full(), a.budget, a.seed + 4100)
        worst = max(samp, st["best"])
        out[key] = a.safety * worst
        sum_bound = sum(abs(w) * X.load_delta(C.bounds_path(a.model)).get(k.split(".")[0], 0.0) for k, w in co.items())
        rows.append([f"{len(co)} terms", f"{samp:.5f}", f"{st['best']:.5f}", f"{out[key]:.5f}", f"{sum_bound:.5f}"])
    p = C.bounds_path(a.model)
    d = json.loads(p.read_text())
    d["linear_atoms"] = out
    d["linear_atoms_source"] = f"scripts/04b_atom_bounds.py --grid {a.grid} --model {a.model} --seed {a.seed}"
    p.write_text(json.dumps(d, indent=2))
    body = f"# Rule-specific error bounds ({a.model})\n\n"
    body += (f"Linear rule atoms with model-error terms; worst |linear - AC| of the expression over {int(res['benign'].sum())} "
             f"benign samples and a joint DE ({a.budget} power flows); bound = {a.safety} x worst. Last column: the bound "
             "obtained by summing per-quantity bounds (what the encoder used before). Saved under `linear_atoms` in "
             f"`rules/{p.name}`.\n\n")
    body += C.md_table(["atom", "sample max", "worst found by search", "rule-specific bound", "sum of per-quantity bounds"], rows)
    C.write_report(f"atom_bounds_{a.model}.md", body)
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
