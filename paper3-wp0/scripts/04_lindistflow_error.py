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
    ap.add_argument("--adv-budget", type=int, default=1000, help="DE power flows per topology and quantity for the worst-case search")
    ap.add_argument("--safety", type=float, default=1.25, help="safety factor on the worst error found")
    a = C.init(ap.parse_args())
    radial = tuple(c for c in E.enumerate_configs() if E.is_radial(c))   # LinDistFlow is radial only
    X, ci, cfgs = E.sample_lhs(E.full(), a.n, seed=a.seed + 3000, configs=radial)
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
    # adversarial worst case per linearised quantity: DE maximising |linear - AC| over benign states
    import json
    pcols = [idx[f"p_from.{l}"] for l in range(15)]
    tcols = [idx[f"trafo_p_hv.{t}"] for t in range(2)]
    tlcols = [idx[f"trafo_loading.{t}"] for t in range(2)]
    quantities = {
        "vm_pu": lambda lm, x, mm: np.abs(lm.vm(x) - mm[vcols]),
        "loading": lambda lm, x, mm: np.abs(lm.loading_percent(x) - mm[lcols]),
        "trafo_loading": lambda lm, x, mm: np.abs(lm.trafo_loading_percent(x) - mm[tlcols]),
        "p_from": lambda lm, x, mm: np.abs(lm.p_from(x) - mm[pcols]),
        "trafo_p_hv": lambda lm, x, mm: np.abs(lm.trafo_p(x) - mm[tcols]),
    }
    units = {"vm_pu": "pu", "loading": "percentage points", "trafo_loading": "percentage points",
             "p_from": "MW", "trafo_p_hv": "MW"}
    # sample maxima for every quantity
    samp = {q: 0.0 for q in quantities}
    for i in np.where(res["benign"])[0]:
        lm = L.model(cfgs[ci[i]])
        for q, fn in quantities.items():
            samp[q] = max(samp[q], float(np.max(fn(lm, X[i], res["M"][i]))))
    worst = {q: 0.0 for q in quantities}
    adv = []
    from p3 import oracle_search as O
    joint = len(cfgs) > 40
    for q, fn in quantities.items():
        if joint:   # many configurations: one joint DE per quantity, same total budget per quantity as 40 runs
            st = O.de_maximize_joint(lambda x, mm, c, fn=fn: float(np.max(fn(L.model(c), x, mm))), cfgs, E.full(),
                                     a.adv_budget * 40, a.seed)
            worst[q] = max(worst[q], max(st["best"], 0.0))
        for k, c in enumerate(cfgs if not joint else ()):
            lm = L.model(c)
            st = O.de_maximize(lambda x, mm, lm=lm, fn=fn: float(np.max(fn(lm, x, mm))), c, E.full(),
                               a.adv_budget, a.seed + k)
            worst[q] = max(worst[q], max(st["best"], 0.0))
        adv.append([q, units[q], f"{samp[q]:.5f}", f"{worst[q]:.5f}", f"{a.safety * max(worst[q], samp[q]):.5f}"])
    wmax = worst["vm_pu"]
    delta = {q: a.safety * max(worst[q], samp[q]) for q in quantities}
    C.bounds_path().write_text(json.dumps({
        "source": f"scripts/04_lindistflow_error.py --seed {a.seed}: max(sample max, DE worst case) x {a.safety}",
        "adv_budget_per_topology": a.adv_budget, "safety_factor": a.safety, "delta": delta}, indent=2))
    body += ("\n## Worst case found by search, and the error bounds used by the robust exact layer\n\n"
             f"Differential evolution maximising the max abs linear-minus-AC error over benign states, "
             f"{a.adv_budget} power flows per topology and quantity ({'one joint DE over all radial configurations with 40 x that budget' if joint else 'one DE per topology'}). delta = {a.safety} x max(sample max, worst found); "
             f"saved to `rules/{C.bounds_path().name}`. delta is an empirical bound, not a proof.\n\n")
    body += C.md_table(["quantity", "unit", f"max over {int(res['benign'].sum())} samples", "worst found by search", "delta used"], adv)
    body += (f"\nWorst benign voltage error found by search: {wmax:.5f} pu "
             f"({'below' if wmax < 0.01 else 'above'} 0.01 pu).\n")
    C.write_report("lindistflow_error.md", body)
    print(f"max err {e.max():.5f}  p95 {np.percentile(e,95):.5f}  worst found {wmax:.5f}")


if __name__ == "__main__":
    main()
