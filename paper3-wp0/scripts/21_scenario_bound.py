"""WP4b: probabilistic (scenario-approach) bound on the linearised AC model error.

Draw N independent benign states, uniform over the envelope (continuous box, configuration index
uniform; non-benign draws rejected), and record the max abs linear-minus-AC error per quantity.
For the maximum of N i.i.d. samples: with confidence at least 1 - beta, the probability that a new
benign state (same distribution) has an error above that maximum is at most
    epsilon = 1 - beta ** (1 / N)   (about ln(1 / beta) / N).
The delta used by the robust exact layer (rules/model_error_bounds_linac*.json) is compared with the
sample maximum: if delta >= max, the same statement holds for delta. This complements the
adversarial search (an empirical worst case) with a provable, distribution-based guarantee; it is
not a worst-case proof."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import envelope as E
from p3 import linac as LA
from p3 import measure as M


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--n", type=int, default=20000, help="benign samples per grid")
    ap.add_argument("--beta", type=float, default=1e-3)
    a = ap.parse_args()
    rows = []
    for grid in ("cigre_pv_wind", "sherlock"):
        E.use_grid(grid); C.GRID = grid
        idx = M.index()
        cfgs = E.enumerate_configs()
        vcols = [idx[f"vm_pu.{b}"] for b in range(15)]
        lcols = [idx[f"loading.{l}"] for l in range(15)]
        tlc = [idx[f"trafo_loading.{t}"] for t in range(2)]
        pcols = [idx[f"p_from.{l}"] for l in range(15)]
        tcols = [idx[f"trafo_p_hv.{t}"] for t in range(2)]
        mx = {q: 0.0 for q in ("vm_pu", "loading", "trafo_loading", "p_from", "trafo_p_hv")}
        n_ok, drawn, seed = 0, 0, a.seed + 9000
        while n_ok < a.n:
            X, ci, _ = E.sample_lhs(E.full(), 2000, seed=seed, configs=cfgs)
            rng = np.random.default_rng(seed)        # independent uniform draws (LHS rows are not i.i.d.)
            lo = np.array([b[0] for b in E.cont_bounds()]); hi = np.array([b[1] for b in E.cont_bounds()])
            X = lo + rng.random(X.shape) * (hi - lo)
            ci = rng.integers(0, len(cfgs), len(X))
            seed += 1
            for x, c in zip(X, ci):
                drawn += 1
                ok, ben, _, m = M.evaluate(x, cfgs[c])
                if not ok or not ben:
                    continue
                lm = LA.model(cfgs[c])
                mx["vm_pu"] = max(mx["vm_pu"], float(np.max(np.abs(lm.vm(x) - m[vcols]))))
                mx["loading"] = max(mx["loading"], float(np.max(np.abs(lm.loading_percent(x) - m[lcols]))))
                mx["trafo_loading"] = max(mx["trafo_loading"], float(np.max(np.abs(lm.trafo_loading_percent(x) - m[tlc]))))
                mx["p_from"] = max(mx["p_from"], float(np.max(np.abs(lm.p_from(x) - m[pcols]))))
                mx["trafo_p_hv"] = max(mx["trafo_p_hv"], float(np.max(np.abs(lm.trafo_p(x) - m[tcols]))))
                n_ok += 1
                if n_ok >= a.n:
                    break
        eps = 1 - a.beta ** (1 / n_ok)
        delta = json.loads(C.bounds_path("linac").read_text())["delta"]
        for q, v in mx.items():
            rows.append([grid, q, n_ok, f"{v:.5f}", f"{delta[q]:.5f}", "yes" if delta[q] >= v else "no", f"{eps:.2e}"])
        print(grid, n_ok, drawn, {q: round(v, 5) for q, v in mx.items()}, f"eps {eps:.2e}")
    C.GRID = C.DEFAULT_GRID
    body = "# WP4b: scenario-approach bound on the linearised AC model error\n\n"
    body += (f"N independent benign states per grid, uniform over the envelope (configuration uniform; non-benign draws "
             f"rejected). With confidence at least 1 - beta = {1 - a.beta:.3f}, the probability that a new benign state drawn "
             "the same way has an error above the sample maximum is at most epsilon = 1 - beta^(1/N). The robust exact layer "
             "uses delta (adversarial worst case x 1.25); where delta >= sample maximum, the guarantee holds for delta as well. "
             "The guarantee is relative to the sampling distribution; it is not a worst-case proof.\n\n")
    body += C.md_table(["grid", "quantity", "N", "sample max", "delta used", "delta >= sample max", "epsilon"], rows)
    C.write_report("scenario_bound.md", body)


if __name__ == "__main__":
    main()
