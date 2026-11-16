"""Improvement A2: can the search-validated SE rules of 02-Semiurban be proved? (pre-registered gate)

For topology T the normalised state-estimation residual is affine in the measurements,
rn = Rn m + r0n (linear WLS with pseudo-measurements; `state_est.SE.residual_affine`), and the
measurements are, to first order, affine in the envelope parameters x around the box centre x0
(Jacobian by finite differences of the AC model, as the linearised AC model of the 15-bus grid).
So r_aff(x) = g + G (x - x0), and its exact maximum over the envelope box is
    box_i = |g_i| + sum_k |G_ik| (hi_k - lo_k) / 2,
an upper bound over the benign set, which lies inside the box. The remainder
    gap_i(x) = |r_i(x) - r_aff,i(x)|
(the rule uses the Gauss-Newton-corrected residual on AC measurements) is bounded by
delta_i = 1.25 x the largest gap found over N independent uniform benign states and a differential
evolution search on the largest normalised gap, as for the linear model on the 15-bus grid.
Measurement i is PROVED for the rule when box_i + delta_i <= margin_i: no benign state of the
envelope can make that residual exceed its margin, up to the validated delta.
Gate (fixed before running): if fewer than 80 % of monitored measurements are proved, search
validation stays, and the fraction is reported; margins are not raised after seeing detections."""
import pickle
import sys
import time
from multiprocessing import get_context
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import envelope as E
from p3 import measure as M
from p3 import oracle_search as O
from p3 import state_est as SE

G_ = {}


def prove(job):
    k, n, budget, seed = job
    cfg, margin, verdict = G_["rules"][k]
    obs = G_["obs"]; pos = {nm: i for i, nm in enumerate(obs)}
    s = SE.se(cfg)
    Rn, r0n = s.residual_affine()
    idx = M.index(); cols = [idx[nm] for nm in s.names]; opos = [pos[nm] for nm in s.names]
    lo = np.array([b[0] for b in E.cont_bounds()]); hi = np.array([b[1] for b in E.cont_bounds()])
    x0 = (lo + hi) / 2
    t0 = time.time()
    ok, ben, _, m0 = M.evaluate(x0, cfg)
    J = np.zeros((len(m0), len(x0)))
    h = 1e-4 * np.maximum(hi - lo, 1e-9)
    for j in range(len(x0)):
        x = x0.copy(); x[j] += h[j]
        _, _, _, mj = M.evaluate(x, cfg)
        J[:, j] = (mj - m0) / h[j]
    g = Rn @ m0[cols] + r0n
    Gm = Rn @ J[cols]
    box = np.abs(g) + np.abs(Gm) @ ((hi - lo) / 2)
    mg = margin[opos]

    names = M.names()
    lim_v = [i for i, nm in enumerate(names) if nm.startswith("vm_pu.")]
    lim_l = [i for i, nm in enumerate(names) if nm.startswith(("loading.", "trafo_loading."))]
    lim_rows = lim_v + lim_l
    J = np.nan_to_num(J); m0 = np.nan_to_num(m0)
    lin_err = np.zeros(len(lim_rows))

    def gap(x):
        ok_, ben_, _, m = M.evaluate(x, cfg)
        if not ok_ or not ben_:
            return None
        r, _ = SE.residual_ac(s, m, iters=G_["iters"])
        if r is None:
            return None
        lin_err[:] = np.fmax(lin_err, np.abs(np.nan_to_num(m[lim_rows]) - (m0[lim_rows] + J[lim_rows] @ (x - x0))))
        return np.abs(r - (g + Gm @ (x - x0)))

    rng = np.random.default_rng(seed)
    worst = np.zeros(len(opos)); got = 0
    while got < n:
        x = lo + rng.random(len(lo)) * (hi - lo)
        gp = gap(x)
        if gp is None:
            continue
        worst = np.fmax(worst, gp); got += 1
    room = np.maximum(mg - box, 1e-9)

    def score(x, m_):
        r, _ = SE.residual_ac(s, m_, iters=G_["iters"])
        if r is None:
            return -1.0
        return float(np.nanmax(np.abs(r - (g + Gm @ (np.asarray(x) - x0))) / room))
    st = O.de_maximize(score, cfg, E.full(), budget, seed + 1)
    if st.get("best_x") is not None:
        gp = gap(st["best_x"])
        if gp is not None:
            worst = np.fmax(worst, gp)
    delta = 1.25 * worst
    proved = (box + delta) <= mg
    # refinement: the benign set also satisfies the operating limits; with the linearised limits relaxed
    # by their own validated error (1.25 x the largest sampled linearisation error), the exact maximum of
    # the affine residual over this polytope is a linear program, a tighter bound that is still sound
    from scipy.optimize import linprog
    d_lim = 1.25 * lin_err
    nv, nl = len(lim_v), len(lim_l)
    Jv, Jl = J[lim_v], J[lim_l]
    A_ub = np.vstack([Jv, -Jv, Jl])
    b_ub = np.r_[1.10 + d_lim[:nv] - m0[lim_v], -(0.90 - d_lim[:nv]) + m0[lim_v], 100.0 + d_lim[nv:] - m0[lim_l]]
    keep = np.abs(A_ub).sum(axis=1) > 0
    A_ub, b_ub = A_ub[keep], b_ub[keep]
    bounds = list(zip(lo - x0, hi - x0))
    poly = box.copy()
    for i in np.where(~proved)[0]:
        best = 0.0
        for sgn in (1.0, -1.0):
            res = linprog(-sgn * Gm[i], A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")
            if res.status != 0:
                best = np.inf; break
            best = max(best, sgn * g[i] - res.fun)
        poly[i] = min(box[i], best)
    proved_poly = (poly + delta) <= mg
    return (k, int(proved.sum()), len(proved), float(np.median(box / mg)), float(np.median(delta / mg)),
            float(np.mean(box <= mg)), time.time() - t0, int(proved_poly.sum()))


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--n", type=int, default=600)
    ap.add_argument("--budget", type=int, default=200)
    ap.add_argument("--workers", type=int, default=4)
    ap.set_defaults(grid="semiurban")
    a = C.init(ap.parse_args())
    d = pickle.loads((C.INTERIM / C.suffixed("semiurban_rules.pkl")).read_bytes())
    G_.update(d)
    jobs = [(k, a.n, a.budget, a.seed + 9100 + k) for k, (_, _, v) in enumerate(d["rules"]) if v.startswith("certified")]
    with get_context("fork").Pool(a.workers) as pool:
        res = sorted(pool.map(prove, jobs))
    rows, tp, tn, tq = [], 0, 0, 0
    for k, p, n, mb, md, fbox, sec, pq in res:
        tp += p; tn += n; tq += pq
        rows.append([d["rules"][k][0].label[:58], f"{p}/{n}", f"{p / n:.2f}", f"{pq}/{n}", f"{pq / n:.2f}", f"{fbox:.2f}", f"{mb:.2f}", f"{md:.2f}", f"{sec:.0f}"])
        print(rows[-1])
    frac, fracq = tp / tn, tq / tn
    gate = lambda f: "passed" if f >= 0.8 else "not passed: search validation stays"
    body = "# Improvement A2: proving the SE rules of 02-Semiurban\n\n" + __doc__.split("\n\n", 1)[1] + "\n\n"
    body += ("Refinement (decided after the box result, before any detection was looked at): the benign set also satisfies "
             "the operating limits (bus voltage in [0.90, 1.10] pu, line and transformer loading at most 100 %). With the "
             "linearised limits relaxed by their own validated error (1.25 x the largest sampled linearisation error), the "
             "exact maximum of the affine residual over this polytope is a linear program; it is a tighter upper bound that "
             "is still sound for the benign set. Margins are unchanged.\n\n")
    body += C.md_table(["topology", "proved, box", "share", "proved, limits polytope", "share",
                        "share with box maximum alone below margin", "median box maximum / margin", "median delta / margin", "wall s"], rows)
    body += (f"\nAll topologies: box bound {tp} of {tn} measurement checks proved ({frac:.2f}), gate (80 %): {gate(frac)}; "
             f"limits polytope {tq} of {tn} ({fracq:.2f}), gate: {gate(fracq)}.\n")
    C.write_report("se_rule_proof.md", body)


if __name__ == "__main__":
    main()
