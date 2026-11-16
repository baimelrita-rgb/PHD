"""Affine worst-case bound for the state-estimation residual rules (02-Semiurban).

For a topology, the normalised SE residual is affine in the measurements (rn = Rn m + r0n) and the
measurements are, to first order, affine in the envelope parameters around the box centre x0
(Jacobian by finite differences of the AC model). Hence r_aff(x) = g + G (x - x0), with exact
maximum over the envelope box  box_i = |g_i| + sum_k |G_ik| (hi_k - lo_k) / 2.
The remainder |r(x) - r_aff(x)| (Gauss-Newton residual on AC measurements) is bounded by
delta_i = 1.25 x its largest value over n independent uniform benign states and a differential
evolution search on the largest remainder relative to the room left under the margin.
bound_i = box_i + delta_i is an upper bound on |r_i| over the benign envelope, valid up to delta.
The worst corner of the box for each measurement is also returned, so that it can be checked on the
full AC model (a confirmed benign counterexample)."""
from __future__ import annotations

import time

import numpy as np

from . import envelope as E
from . import measure as M
from . import oracle_search as O
from . import state_est as SE


def affine_bound(cfg, s, margin_sub, iters, n=150, budget=100, seed=0):
    t0 = time.time()
    Rn, r0n = s.residual_affine()
    idx = M.index(); cols = [idx[nm] for nm in s.names]
    lo = np.array([b[0] for b in E.cont_bounds()]); hi = np.array([b[1] for b in E.cont_bounds()])
    x0 = (lo + hi) / 2
    _, _, _, m0 = M.evaluate(x0, cfg)
    J = np.zeros((len(m0), len(x0)))
    h = 1e-4 * np.maximum(hi - lo, 1e-9)
    for j in range(len(x0)):
        x = x0.copy(); x[j] += h[j]
        J[:, j] = (M.evaluate(x, cfg)[3] - m0) / h[j]
    J = np.nan_to_num(J); m0 = np.nan_to_num(m0)
    g = Rn @ m0[cols] + r0n
    G = Rn @ J[cols]
    box = np.abs(g) + np.abs(G) @ ((hi - lo) / 2)

    def rem(x, m):
        r, _ = SE.residual_ac(s, m, iters=iters)
        return None if r is None else np.abs(r - (g + G @ (np.asarray(x) - x0)))

    rng = np.random.default_rng(seed)
    worst = np.zeros(len(cols)); got = 0
    while got < n:
        x = lo + rng.random(len(lo)) * (hi - lo)
        ok, ben, _, m = M.evaluate(x, cfg)
        if not ok or not ben:
            continue
        rr = rem(x, m)
        if rr is None:
            continue
        worst = np.fmax(worst, rr); got += 1
    room = np.maximum(margin_sub - box, 1e-9)

    def score(x, m):
        rr = rem(x, m)
        return -1.0 if rr is None else float(np.nanmax(rr / room))
    st = O.de_maximize(score, cfg, E.full(), budget, seed + 1)
    if st.get("best_x") is not None and st.get("best_m") is not None:
        rr = rem(st["best_x"], st["best_m"])
        if rr is not None:
            worst = np.fmax(worst, rr)
    delta = 1.25 * worst
    corner_sign = np.sign(g + 1e-300)
    return {"box": box, "delta": delta, "bound": box + delta, "g": g, "G": G, "x0": x0, "lo": lo, "hi": hi,
            "seconds": time.time() - t0}


def corner_check(cfg, s, margin_sub, ab, iters, k=8):
    """Check the k measurements with the largest box/margin on the full AC model: corner of the box that
    maximises the affine residual, pulled toward the centre until the state is benign. Returns a list of
    (measurement, rule score) for benign AC states."""
    out = []
    ratio = ab["box"] / margin_sub
    for i in np.argsort(-ratio)[:k]:
        for sgn in (1.0, -1.0):
            xc = np.where(sgn * ab["G"][i] > 0, ab["hi"], ab["lo"])
            for t in (1.0, 0.8, 0.6, 0.4, 0.3, 0.2):
                x = ab["x0"] + t * (xc - ab["x0"])
                ok, ben, _, m = M.evaluate(x, cfg)
                if ok and ben:
                    r, _ = SE.residual_ac(s, m, iters=iters)
                    if r is not None:
                        out.append((s.names[i], float(np.nanmax(np.abs(r) / margin_sub))))
                    break
            else:
                continue
            break
    return out
