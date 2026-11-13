"""Linearised AC power flow (first-order expansion at an operating point), for radial AND
meshed configurations.

At the operating point x0 (centre of the envelope box) the AC power flow is solved with the
fast solver; the Newton-Raphson Jacobian J maps injection changes to state changes:
    [d theta_pq; d Vm_pq] = J^-1 [d P_pq; d Q_pq].
Injections are affine in x (envelope.injection_maps), so bus voltage magnitudes and branch
flows (from-end P and Q, linearised numerically in the state) are affine in x:
    vm = vc + Av @ x,  P_line = AP @ x + cP,  Q_line = AQ @ x + cQ  (same for transformers).
Unlike LinDistFlow this works in voltage magnitude (not squared), keeps line charging, losses
and meshes at the operating point. Error against the full AC model is measured in
scripts/04 (--model linac) and enters the robust exact layer as delta.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from . import envelope as E
from . import fastpf as F


def _jacobian(Y, V, pq):
    Ibus = Y @ V
    Vn = V / np.abs(V)
    dVm = V[:, None] * np.conj(Y * Vn[None, :])
    dVm[np.diag_indices_from(dVm)] += np.conj(Ibus) * Vn
    dVa = -1j * V[:, None] * np.conj(Y * V[None, :])
    dVa[np.diag_indices_from(dVa)] += 1j * V * np.conj(Ibus)
    A, B = dVa[np.ix_(pq, pq)], dVm[np.ix_(pq, pq)]
    return np.block([[A.real, B.real], [A.imag, B.imag]])


class LinAC:
    squared = False   # thresholds compare vm directly (LinDistFlow uses v = vm^2)

    def __init__(self, cfg: E.Config, x0=None):
        self.cfg = cfg
        s = F.solver(cfg)
        b = E.cont_bounds()
        self.x0 = np.array([(lo + hi) / 2 for lo, hi in b]) if x0 is None else np.asarray(x0)
        sol, _ = s.solve(self.x0)
        if not sol.converged:
            raise RuntimeError(f"no AC solution at the linearisation point for {cfg.label}")
        V0 = sol.V
        pq = s.pq
        n = len(pq)
        nx_ = len(self.x0)
        # injection sensitivity (pu): S(x) affine
        S0 = s.injections(np.zeros(nx_))[0]
        dS = np.stack([s.injections(np.eye(nx_)[k])[0] - S0 for k in range(nx_)], axis=1)
        J = _jacobian(s.Ybus, V0, pq)
        dX = np.linalg.solve(J, np.vstack([dS[pq].real, dS[pq].imag]))     # (2n, nx)
        Vm0, Va0 = np.abs(V0), np.angle(V0)
        # bus voltage magnitude
        Avm = np.zeros((len(V0), nx_))
        Avm[pq] = dX[n:]
        self.Av = Avm[s.bus_ppc]
        self.vc = Vm0[s.bus_ppc] - self.Av @ self.x0
        # branch from-end flows, linearised numerically in the state (theta_pq, Vm_pq)

        def flows(Va, Vm):
            V = Vm * np.exp(1j * Va)
            Sf = V[s.fbus] * np.conj(s.Yf @ V) * s.baseMVA
            return np.r_[Sf.real, Sf.imag]

        f0 = flows(Va0, Vm0)
        G = np.zeros((len(f0), 2 * n))
        eps = 1e-6
        for k in range(2 * n):
            Va, Vm = Va0.copy(), Vm0.copy()
            if k < n:
                Va[pq[k]] += eps
            else:
                Vm[pq[k - n]] += eps
            G[:, k] = (flows(Va, Vm) - f0) / eps
        Af = G @ dX
        cf = f0 - Af @ self.x0
        nbr = len(s.fbus)
        AP, AQ, cP, cQ = Af[:nbr], Af[nbr:], cf[:nbr], cf[nbr:]
        lb, tb = s.line_br, s.trafo_br
        on = s.br_status[lb]
        self.line_active = on
        self.AP_line = np.where(on[:, None], AP[lb], 0.0); self.cP_line = np.where(on, cP[lb], 0.0)
        self.AQ_line = np.where(on[:, None], AQ[lb], 0.0); self.cQ_line = np.where(on, cQ[lb], 0.0)
        self.AP_trafo, self.cP_trafo = AP[tb], cP[tb]
        self.AQ_trafo, self.cQ_trafo = AQ[tb], cQ[tb]
        net = s.net
        vn = net.bus.vn_kv.values[net.line.from_bus.values]
        self.smax_line = np.sqrt(3) * vn * (net.line.max_i_ka * net.line.df * net.line.parallel).values
        self.smax_trafo = net.trafo.sn_mva.values.astype(float)
        self.buses = list(net.bus.index)

    def vm(self, x):
        return self.vc + self.Av @ x

    def v(self, x):
        return self.vm(x) ** 2

    def loading_percent(self, x):
        P, Q = self.AP_line @ x + self.cP_line, self.AQ_line @ x + self.cQ_line
        return np.where(self.line_active, np.hypot(P, Q) / self.smax_line * 100, 0.0)

    def trafo_loading_percent(self, x):
        return np.hypot(self.AP_trafo @ x + self.cP_trafo, self.AQ_trafo @ x + self.cQ_trafo) / self.smax_trafo * 100

    def p_from(self, x):
        return self.AP_line @ x + self.cP_line

    def trafo_p(self, x):
        return self.AP_trafo @ x + self.cP_trafo


@lru_cache(maxsize=None)
def model(cfg: E.Config) -> LinAC:
    return LinAC(cfg)
