"""Search oracle on the full AC model.

Looks for a benign state (AC power flow converges, operating limits hold) in which
the rule fires. Such a state is a benign counterexample (a false alarm).

Stage A: Latin hypercube samples of the envelope.
Stage B: differential evolution maximising the rule margin over the continuous
         envelope parameters, one run per discrete topology, under a hard total
         budget of power flows per rule.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import differential_evolution
from scipy.stats import qmc

from . import envelope as E
from . import measure as M
from . import rules as R

PENALTY_NONCONV = 1e3


@dataclass
class Counterexample:
    stage: str
    cfg: E.Config
    x: np.ndarray
    margin: float
    m: np.ndarray


@dataclass
class SearchResult:
    found: bool
    n_pf: int
    wall_s: float
    best_margin: float
    cex: Counterexample | None = None
    n_cex: int = 0
    per_cfg: list = field(default_factory=list)


def stage_a(rule, res, X, ci, cfgs) -> SearchResult:
    """Uses precomputed batch results (C.evaluate_batch) so several rules share the power flows."""
    t0 = time.time()
    idx = M.index()
    best, best_i, n_cex = -np.inf, None, 0
    first = None
    for i in np.where(res["benign"])[0]:
        mg = R.margin(rule, res["M"][i], idx)
        if mg > 0:
            n_cex += 1
            if first is None:
                first = i
        if mg > best:
            best, best_i = mg, i
    i = best_i if n_cex else None
    cex = None
    if n_cex:
        cex = Counterexample("A", cfgs[ci[i]], X[i], best, res["M"][i])
    return SearchResult(n_cex > 0, len(X), time.time() - t0, best, cex, n_cex)


def _de_one(rule, cfg, env, budget, seed, npop=15):
    idx = M.index()
    bounds = E.cont_bounds(env)
    lo = np.array([b[0] for b in bounds]); hi = np.array([b[1] for b in bounds])
    npop = max(5, min(npop, budget))
    init = lo + qmc.LatinHypercube(d=len(bounds), seed=seed).random(npop) * (hi - lo)
    st = {"n": 0, "best": -np.inf, "best_x": None, "best_m": None, "n_cex": 0}

    def f(x):
        if st["n"] >= budget:
            return 1e6
        st["n"] += 1
        ok, ben, viol, m = M.evaluate(x, cfg)
        if not ok:
            return PENALTY_NONCONV
        if not ben:
            return 10.0 + 100.0 * viol
        mg = R.margin(rule, m, idx)
        if mg > 0:
            st["n_cex"] += 1
        if mg > st["best"]:
            st["best"], st["best_x"], st["best_m"] = mg, np.array(x), m
        return -mg

    maxiter = max(0, -(-(budget - npop) // npop))  # ceil; the counter enforces the exact budget
    differential_evolution(f, bounds, init=init, maxiter=maxiter, polish=False, seed=seed,
                           tol=0, atol=0, updating="immediate")
    return st


def stage_b(rule, cfgs, env=E.ENVELOPE_FULL, budget=2000, seed=E.SEED) -> SearchResult:
    t0 = time.time()
    k = len(cfgs)
    per = [budget // k + (1 if i < budget % k else 0) for i in range(k)]
    best, bx, bm, bc, n_pf, n_cex = -np.inf, None, None, None, 0, 0
    per_cfg = []
    for i, (cfg, b) in enumerate(zip(cfgs, per)):
        st = _de_one(rule, cfg, env, b, seed + i)
        n_pf += st["n"]; n_cex += st["n_cex"]
        per_cfg.append((cfg.label, st["n"], st["best"], st["n_cex"]))
        if st["best"] > best:
            best, bx, bm, bc = st["best"], st["best_x"], st["best_m"], cfg
    cex = Counterexample("B", bc, bx, best, bm) if best > 0 else None
    return SearchResult(best > 0, n_pf, time.time() - t0, best, cex, n_cex, per_cfg)


def recheck_reference(rule, cex: Counterexample):
    """Re-solve a counterexample with pandapower runpp. Returns (converged, benign, fires, margin)."""
    net = E.run_reference_pf(cex.x, cex.cfg)
    if net is None:
        return False, False, False, float("nan")
    m = M.vector_from_net(net)
    ben, _ = M.benign_check(m)
    mg = R.margin(rule, m)
    return True, ben, mg > 0, mg
