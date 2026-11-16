"""Independent probabilistic validation of the search-validated SE rules (02-Semiurban).

The on-demand oracle certifies each topology's SE rule with a small search budget (40 LHS states
plus differential evolution). Here every certified rule is checked again on N fresh, independent
benign states drawn uniformly over the envelope box of its topology (non-benign draws rejected),
none of which the oracle saw. If none of the N states fires the rule, then by the scenario argument
(the probability that i.i.d. draws all avoid a set of probability p is (1 - p)^N), with confidence
1 - beta the probability that a uniformly drawn benign state fires the rule is at most
    epsilon = 1 - beta ** (1 / N).
If some states fire, the exact Clopper-Pearson upper bound on the firing probability is reported.
The statement is relative to the uniform envelope distribution; it is not a worst-case proof."""
import pickle
import sys
import time
from multiprocessing import get_context
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
from scipy.stats import beta as Beta

from p3 import common as C
from p3 import envelope as E
from p3 import state_est as SE

import importlib.util
_spec = importlib.util.spec_from_file_location("s18", Path(__file__).with_name("18_semiurban_consolidation.py"))
s18 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(s18)

G = {}


def check(job):
    k, n, seed = job
    cfg, margin, verdict = G["rules"][k]
    obs_pos = {nm: i for i, nm in enumerate(G["obs"])}
    s = SE.se(cfg)
    lo = np.array([b[0] for b in E.cont_bounds()]); hi = np.array([b[1] for b in E.cont_bounds()])
    rng = np.random.default_rng(seed)
    ok = fired = drawn = 0
    worst = -np.inf
    t0 = time.time()
    while ok < n:
        x = lo + rng.random(len(lo)) * (hi - lo)
        drawn += 1
        r = s18.residual_of_state(s, obs_pos, x, cfg, G["iters"])
        if r is None:
            continue
        ok += 1
        sc = float(np.nanmax(np.abs(r) / margin))
        worst = max(worst, sc)
        fired += int(sc > 1.0)
    return k, ok, drawn, fired, worst, time.time() - t0


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--n", type=int, default=1500)
    ap.add_argument("--beta", type=float, default=1e-3)
    ap.add_argument("--workers", type=int, default=4)
    ap.set_defaults(grid="semiurban")
    a = C.init(ap.parse_args())
    d = pickle.loads((C.INTERIM / C.suffixed("semiurban_rules.pkl")).read_bytes())
    G.update(d)
    jobs = [(k, a.n, a.seed + 7000 + k) for k, (_, _, v) in enumerate(d["rules"]) if v.startswith(("certified", "proved"))]
    with get_context("fork").Pool(a.workers) as pool:
        res = sorted(pool.map(check, jobs))
    rows, tot_ok, tot_fire = [], 0, 0
    for k, ok, drawn, fired, worst, sec in res:
        cfg = d["rules"][k][0]
        tot_ok += ok; tot_fire += fired
        if fired == 0:
            bound = 1 - a.beta ** (1 / ok)
            stmt = f"{bound:.2e}"
        else:
            bound = Beta.ppf(1 - a.beta, fired + 1, ok - fired)
            stmt = f"{bound:.2e} (Clopper-Pearson, {fired} fired)"
        rows.append([cfg.label[:60], ok, drawn, fired, f"{worst:.3f}", stmt, f"{sec:.0f}"])
        print(rows[-1])
    pooled = 1 - a.beta ** (1 / tot_ok) if tot_fire == 0 else Beta.ppf(1 - a.beta, tot_fire + 1, tot_ok - tot_fire)
    body = "# Independent validation of the search-validated SE rules (02-Semiurban)\n\n" + __doc__.split("\n\n", 1)[1] + "\n\n"
    body += C.md_table(["topology", "benign states N", "draws", "states firing the rule", "largest score (fires above 1)",
                        f"bound on the firing probability, confidence {1 - a.beta:.3f}", "wall s"], rows)
    body += (f"\nAll rules together: {tot_ok} benign states, {tot_fire} firing; pooled bound on the probability that a "
             f"uniformly drawn benign state of a uniformly chosen certified topology fires its rule: {pooled:.2e} "
             f"(confidence {1 - a.beta:.3f}).\n")
    C.write_report("se_rule_validation.md", body)


if __name__ == "__main__":
    main()
