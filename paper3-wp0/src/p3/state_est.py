"""Linear weighted-least-squares state estimation under partial observability (WP2-b).

For one topology T, the linearised AC model (linac) gives every measurement as an affine
function of the injection parameters x. The control center sees only a subset of the
measurements (monitored bus voltages, line flows, all transformer flows, monitored loads,
DER and storage). Unmonitored loads get pseudo-measurements: their P / nominal is the mean of
the monitored loads with the same SimBench profile. A weak prior at the envelope centre
regularises directions that no measurement sees (for example DER versus storage behind the
same transformer, whose sum is all that is measured).

Everything is linear, so for each topology the measurement residual is an affine map of the
monitored measurement vector y:  r = R y + r0,  and the normalised residual r / sigma is the
bad-data detection statistic. Precomputing R once per topology makes it a matrix-vector
product per record. The same residual is linear in the measurements, so rules on it are
expressible in the rule DSL and certifiable by the oracle.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from . import envelope as E
from . import linac as LA
from . import measure as M

SIGMA = {"vm_pu": 5e-4, "p_from": 2e-3, "trafo_p_hv": 2e-3, "load_p": 5e-4, "sgen_p": 5e-4, "storage_p": 5e-4,
         "load_q": 5e-4}
PSEUDO_REL = 0.01      # pseudo-measurement standard deviation, fraction of the load's nominal P
PRIOR_SIGMA = 1.0      # weak prior on x (envelope centre), in units of x


@lru_cache(maxsize=1)
def observed_names():
    """Measurement names the control center actually receives (first test record of the dataset)."""
    from . import sherlock_io as S
    from . import sherlock_model as SM
    rec = next(iter(S.iter_state(S.root(), "test")))
    m = SM.record_measurements(rec["state"], M.names(), E._base_net())
    idx = M.index()
    kinds = tuple(SIGMA)
    return tuple(n for n in M.names() if n.split(".")[0] in kinds and np.isfinite(m[idx[n]]))


class SE:
    def __init__(self, cfg: E.Config):
        self.cfg = cfg
        lm = LA.model(cfg)
        inj = E.injection_maps()
        net = E._base_net()
        # de-energised buses (islands without supply, e.g. planned maintenance) carry no information:
        # their voltages and the flows of lines touching them are excluded
        from . import fastpf as F
        fs = F.solver(cfg)
        from scipy.sparse.csgraph import breadth_first_order
        from scipy.sparse import csr_matrix
        reach = set(breadth_first_order(csr_matrix(np.abs(fs.Ybus) > 0), int(fs.ref[0]), directed=False, return_predecessors=False))
        live_bus = {int(b) for b, p in zip(net.bus.index, fs.bus_ppc) if int(p) in reach}
        self.dead_buses = sorted(set(int(b) for b in net.bus.index) - live_bus)

        def keep(n):
            kind, i = n.split("."); i = int(i)
            if kind == "vm_pu":
                return i in live_bus
            if kind == "p_from":
                return bool(lm.line_active[i]) and int(net.line.from_bus.at[i]) in live_bus and int(net.line.to_bus.at[i]) in live_bus
            return True
        obs = [n for n in observed_names() if keep(n)]
        self.names = obs
        H, c, sig = [], [], []
        for n in obs:
            kind, i = n.split("."); i = int(i)
            if kind == "vm_pu":
                h, cc = lm.Av[i], lm.vc[i]
            elif kind == "p_from":
                h, cc = lm.AP_line[i], lm.cP_line[i]
            elif kind == "trafo_p_hv":
                h, cc = lm.AP_trafo[i], lm.cP_trafo[i]
            elif kind == "load_p":
                h, cc = inj.Apl[i], 0.0
            elif kind == "sgen_p":
                h, cc = inj.Apg[i], 0.0
            elif kind == "load_q":
                h, cc = inj.Aql[i], inj.cql[i]
            else:
                h, cc = inj.Apb[i], 0.0
            H.append(h); c.append(cc); sig.append(SIGMA[kind])
        H, c, sig = np.array(H), np.array(c), np.array(sig)
        ny, nx_ = H.shape
        # pseudo-measurements for unmonitored loads: G maps y to pseudo values
        pos = {n: k for k, n in enumerate(obs)}
        prof = net.load.profile.values
        p_nom = np.abs(net.load.p_mw.values)
        mon = {int(n.split(".")[1]) for n in obs if n.startswith("load_p.")}
        Hp, Gp, sp = [], [], []
        for i in range(len(net.load)):
            if i in mon:
                continue
            grp = [j for j in mon if prof[j] == prof[i]]
            if not grp:
                continue
            g = np.zeros(ny)
            for j in grp:
                g[pos[f"load_p.{j}"]] = p_nom[i] / p_nom[j] / len(grp)
            Hp.append(inj.Apl[i]); Gp.append(g); sp.append(PSEUDO_REL * p_nom[i])
            if E.dims().n_lq:         # reactive power: same profile group, Q / nominal Q
                q_nom = net.load.q_mvar.values
                monq = [j for j in grp if f"load_q.{j}" in pos and q_nom[j] != 0]
                if monq:
                    gq = np.zeros(ny)
                    for j in monq:
                        gq[pos[f"load_q.{j}"]] = q_nom[i] / q_nom[j] / len(monq)
                    Hp.append(inj.Aql[i]); Gp.append(gq); sp.append(PSEUDO_REL * max(abs(q_nom[i]), 1e-3))
        Hp, Gp, sp = np.array(Hp).reshape(-1, nx_), np.array(Gp).reshape(-1, ny), np.array(sp)
        b = E.cont_bounds()
        x0 = np.array([(lo + hi) / 2 for lo, hi in b])
        # augmented system z = A y + bvec, Haug x + caug ~ z
        Haug = np.vstack([H, Hp, np.eye(nx_)])
        caug = np.r_[c, np.zeros(len(Hp)), np.zeros(nx_)]
        A = np.vstack([np.eye(ny), Gp, np.zeros((nx_, ny))])
        bvec = np.r_[np.zeros(ny), np.zeros(len(Hp)), x0]
        w = 1.0 / np.r_[sig, sp, np.full(nx_, PRIOR_SIGMA)] ** 2
        HtW = Haug.T * w
        K = np.linalg.solve(HtW @ Haug, HtW)                 # x_hat = K (z - caug)
        self.Kx = K @ A
        self.kx0 = K @ (bvec - caug)
        # residual on the real measurements: r = y - (H x_hat + c)
        self.R = np.eye(ny) - H @ self.Kx
        self.r0 = -(H @ self.kx0) - c
        self.sigma = sig
        self.n_pseudo = len(Hp)
        self.redundancy = ny + len(Hp) - np.linalg.matrix_rank(np.vstack([H, Hp]))
        idx = M.index()
        self.cols = np.array([idx[n] for n in obs])

    def residual(self, m):
        """Normalised residuals for a full measurement vector m (unmonitored entries ignored)."""
        y = m[self.cols]
        return (self.R @ y + self.r0) / self.sigma

    def residual_affine(self):
        """Normalised residual as affine map of the measurement vector: rn = Rm @ m[cols] + r0n."""
        return self.R / self.sigma[:, None], self.r0 / self.sigma


@lru_cache(maxsize=None)
def se(cfg: E.Config) -> SE:
    return SE(cfg)


def residual_ac(s: SE, m, iters: int = 2):
    """Iterated estimate: linear WLS, then Gauss-Newton corrections with the same gain, each
    measured against the full AC model at the current estimate. Returns (normalised residual
    against the AC model, x_hat) or (None, None) if a power flow does not converge."""
    from . import fastpf as F
    from . import measure as M_
    y = m[s.cols]
    x = s.Kx @ y + s.kx0
    sol = F.solver(s.cfg)
    for _ in range(iters):
        ok, r = F.solve_state(x, s.cfg)
        if not ok:
            return None, None
        mh = M_.vector_from_fast(r, s.cfg)
        yh = mh[s.cols]
        x = x + s.Kx @ (y - yh)
    ok, r = F.solve_state(x, s.cfg)
    if not ok:
        return None, None
    yh = M_.vector_from_fast(r, s.cfg)[s.cols]
    return (y - yh) / s.sigma, x
