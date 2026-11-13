"""T5a: LinDistFlow bus voltage error against full AC power flow on benign samples."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import envelope as E
from p3 import lindistflow as L
from p3 import measure as M


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--adv-budget", type=int, default=1000, help="DE power flows per topology for the worst-case search")
    a = ap.parse_args()
    X, ci, cfgs = E.sample_lhs(E.ENVELOPE_FULL, a.n, seed=a.seed + 3000)
    res = C.evaluate_batch(X, ci, cfgs)
    idx = M.index()
    vcols = [idx[f"vm_pu.{b}"] for b in range(15)]
    lcols = [idx[f"loading.{l}"] for l in range(15)]
    errs = {k: [] for k in range(len(cfgs))}
    lerr = {k: [] for k in range(len(cfgs))}
    for i in np.where(res["benign"])[0]:
        m = L.model(cfgs[ci[i]])
        errs[ci[i]].append(np.abs(m.vm(X[i]) - res["M"][i, vcols]))
        lerr[ci[i]].append(np.abs(m.loading_percent(X[i]) - res["M"][i, lcols]))
    rows, allv, alll = [], [], []
    for k, c in enumerate(cfgs):
        e = np.concatenate(errs[k]) if errs[k] else np.array([np.nan])
        le = np.concatenate(lerr[k]) if lerr[k] else np.array([np.nan])
        allv.append(e); alll.append(le)
        rows.append([f"`{c.label}`", len(errs[k]), f"{e.mean():.5f}", f"{np.percentile(e, 95):.5f}", f"{e.max():.5f}",
                     f"{le.max():.2f}"])
    e = np.concatenate(allv); le = np.concatenate(alll)
    rows.append(["**all**", int(res["benign"].sum()), f"{e.mean():.5f}", f"{np.percentile(e, 95):.5f}", f"{e.max():.5f}", f"{le.max():.2f}"])
    # signed error at the R1 bus, to show the bias direction
    sgn = [L.model(cfgs[ci[i]]).vm(X[i])[11] - res["M"][i, idx["vm_pu.11"]] for i in np.where(res["benign"])[0]]
    body = "# T5a LinDistFlow voltage error against AC power flow\n\n"
    body += (f"{a.n} Latin hypercube samples of the full envelope (seed {a.seed + 3000}), {int(res['benign'].sum())} benign. "
             "Error = |vm_LinDistFlow - vm_AC| over all 15 buses of every benign sample, in pu. "
             "Last column: max abs error of the linear-model line loading (S/S_max at 1 pu) in percentage points.\n\n")
    body += C.md_table(["topology", "benign samples", "mean abs err pu", "95th pct pu", "max abs err pu", "max loading err pp"], rows)
    body += (f"\nG6 criterion (max abs error below 0.01 pu on the benign envelope): "
             f"**{'pass' if e.max() < 0.01 else 'fail'}** (max {e.max():.5f} pu).\n\n"
             f"Signed error at bus 11 (LinDistFlow minus AC): min {min(sgn):.5f}, mean {np.mean(sgn):.5f}, max {max(sgn):.5f} pu. "
             "A positive value means LinDistFlow over-estimates the voltage.\n")
    # adversarial worst case: DE maximising the voltage error over benign states, per topology
    from scipy.optimize import differential_evolution
    from scipy.stats import qmc
    bounds = E.cont_bounds(E.ENVELOPE_FULL)
    lo = np.array([b[0] for b in bounds]); hi = np.array([b[1] for b in bounds])
    adv = []
    for k, c in enumerate(cfgs):
        lm = L.model(c)
        st = {"n": 0, "best": 0.0}

        def f(x):
            if st["n"] >= a.adv_budget:
                return 1e6
            st["n"] += 1
            ok, ben, viol, mm = M.evaluate(x, c)
            if not ok or not ben:
                return 1.0 + viol
            err = float(np.max(np.abs(lm.vm(x) - mm[vcols])))
            st["best"] = max(st["best"], err)
            return -err

        init = lo + qmc.LatinHypercube(d=len(bounds), seed=a.seed + k).random(15) * (hi - lo)
        differential_evolution(f, bounds, init=init, maxiter=-(-(a.adv_budget - 15) // 15), polish=False,
                               seed=a.seed + k, tol=0, atol=0)
        adv.append([f"`{c.label}`", st["n"], f"{st['best']:.5f}"])
    wmax = max(float(r[2]) for r in adv)
    body += ("\n## Worst case found by search\n\n"
             f"Differential evolution maximising the max-bus voltage error over benign states, {a.adv_budget} power flows per topology.\n\n")
    body += C.md_table(["topology", "power flows", "max abs err found pu"], adv)
    body += (f"\nWorst benign error found by search: {wmax:.5f} pu "
             f"({'below' if wmax < 0.01 else 'above'} 0.01 pu).\n")
    C.write_report("lindistflow_error.md", body)
    print(f"max err {e.max():.5f}  p95 {np.percentile(e,95):.5f}  worst found {wmax:.5f}")


if __name__ == "__main__":
    main()
