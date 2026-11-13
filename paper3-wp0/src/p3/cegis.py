"""Minimal counterexample-guided refinement for threshold rules of the form vm_pu.b < tau.

Each iteration asks both oracles. Every counterexample gives a value of the guarded
voltage (AC value for the search layer, LinDistFlow value for the exact layer); tau is
moved just below the lowest of them. Stops when the exact layer is UNSAT and the
search layer finds no counterexample, or after max_iter iterations.
"""
from __future__ import annotations

import copy
import time

import numpy as np

from . import envelope as E
from . import lindistflow as L
from . import measure as M
from . import oracle_exact as X
from . import oracle_search as O
from . import rules as R

EPS = 1e-4


def _tau(rule):
    return rule["atoms"][0]["value"]


def _set_tau(rule, tau):
    r = copy.deepcopy(rule)
    r["atoms"][0]["value"] = float(tau)
    return r


def refine_threshold(rule, stage_a_data, cfgs, budget=2000, seed=E.SEED, max_iter=10, eps=EPS, model="lindistflow"):
    atom = rule["atoms"][0]
    assert atom["type"] == "threshold" and atom["op"] == "<" and atom["meas"].startswith("vm_pu.")
    bus = int(atom["meas"].split(".")[1])
    col = M.index()[atom["meas"]]
    Xa, ci, res = stage_a_data
    trace = []
    cur = copy.deepcopy(rule)
    for it in range(1, max_iter + 1):
        t0 = time.time()
        A = O.stage_a(cur, res, Xa, ci, cfgs)
        B = O.stage_b(cur, cfgs, budget=budget, seed=seed + 97 * it)
        ex = X.solve(cur, cfgs, model=model)
        vals = []
        if A.found:
            ben = res["benign"]
            v = res["M"][ben, col]
            vals.append(("search-A", float(v[v < _tau(cur)].min())))
        if B.found:
            vals.append(("search-B", float(B.cex.m[col])))
        ex_vals = [float(X.linear_model(c, model).vm(x)[bus]) for c, st, _, x in ex.per_cfg if st == "sat"]
        if ex_vals:
            vals.append(("exact", min(ex_vals)))
        row = {"iter": it, "tau": _tau(cur), "search_A": A.n_cex, "search_B": B.n_cex,
               "exact": ex.status, "exact_sat_topologies": len(ex_vals),
               "cex_values": vals, "wall_s": time.time() - t0}
        trace.append(row)
        if not A.found and not B.found and ex.status == "unsat":
            row["action"] = "stop: no counterexample in either layer"
            return cur, trace, True
        new_tau = min(v for _, v in vals) - eps
        row["action"] = f"tau -> {new_tau:.5f}"
        cur = _set_tau(cur, new_tau)
    return cur, trace, False
