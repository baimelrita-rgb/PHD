"""Fast AC power flow for the envelope searches.

pandapower's runpp costs about 25 ms per call on this grid, mostly bookkeeping. The
oracle needs tens of thousands of power flows. This module takes pandapower's own
internal case (net._ppc: bus, branch, Ybus built by pandapower's makeYbus) once per
discrete configuration and solves the same AC equations with a dense Newton-Raphson.
Results are checked against pp.runpp in tests/test_fastpf.py.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandapower as pp
from pandapower.pypower.makeYbus import makeYbus

from . import envelope as E

TOL = 1e-8   # pu mismatch, as pandapower default tolerance_mva=1e-8 with sn_mva=1
MAX_IT = 20


@dataclass
class Solution:
    converged: bool
    V: np.ndarray | None = None  # complex, internal ppc ordering


class FastAC:
    def __init__(self, cfg: E.Config):
        self.cfg = cfg
        net = E.apply_state(E.base_net(), np.ones(E.dims().n_cont), cfg)
        pp.runpp(net, numba=True)
        self.net = net
        ppc = net._ppc
        self.baseMVA = float(ppc["baseMVA"])
        bus = ppc["bus"].copy()
        branch = ppc["branch"].copy()
        Ybus, Yf, Yt = makeYbus(self.baseMVA, bus, branch)
        self.Ybus = np.asarray(Ybus.todense())
        self.Yf = np.asarray(Yf.todense())
        self.Yt = np.asarray(Yt.todense())
        self.branch = branch
        self.nb = bus.shape[0]
        btype = bus[:, 1].real.astype(int)
        self.ref = np.where(btype == 3)[0]
        self.pq = np.where(btype == 1)[0]
        self.iso = np.where(btype == 4)[0]
        assert len(self.ref) == 1
        self.vref = complex(net._ppc["gen"][0, 5].real, 0.0)  # VG of ext grid
        bl = net._pd2ppc_lookups["bus"]
        self.load_bus = bl[net.load.bus.values]
        self.sgen_bus = bl[net.sgen.bus.values]
        self.bus_ppc = bl[net.bus.index.values]
        self.vn_kv = bus[:, 9].real
        f0, f1 = net._pd2ppc_lookups["branch"]["line"]
        t0, t1 = net._pd2ppc_lookups["branch"]["trafo"]
        self.line_br = np.arange(f0, f1)
        self.trafo_br = np.arange(t0, t1)
        self.br_status = branch[:, 10].real > 0
        self.fbus = branch[:, 0].real.astype(int)
        self.tbus = branch[:, 1].real.astype(int)
        self.imax_ka = (net.line.max_i_ka * net.line.df * net.line.parallel).values
        base = E._base_net()
        self.p_load_nom = base.load.p_mw.values
        self.q_load_nom = base.load.q_mvar.values
        self.sgen_rated = base.sgen.sn_mva.values
        self._V0 = ppc["bus"][:, 7].real * np.exp(1j * np.deg2rad(ppc["bus"][:, 8].real))

    def injections(self, x):
        s, g = E.split_x(x)
        pl = self.p_load_nom * s
        ql = self.q_load_nom * s
        pg = self.sgen_rated * g
        S = np.zeros(self.nb, dtype=complex)
        np.add.at(S, self.load_bus, -(pl + 1j * ql))
        np.add.at(S, self.sgen_bus, pg)
        return S / self.baseMVA, pl, ql, pg

    def solve(self, x) -> tuple[Solution, dict]:
        Sbus, pl, ql, pg = self.injections(x)
        V = self._V0.copy()
        V[self.ref] = self.vref
        pq, ref = self.pq, self.ref
        pvpq = pq  # no PV buses in this grid
        Y = self.Ybus
        conv = False
        for _ in range(MAX_IT):
            mis = V * np.conj(Y @ V) - Sbus
            F = np.r_[mis[pvpq].real, mis[pq].imag]
            if np.max(np.abs(F)) < TOL:
                conv = True
                break
            Ibus = Y @ V
            Vn = V / np.abs(V)
            dS_dVm = V[:, None] * np.conj(Y * Vn[None, :])
            dS_dVm[np.diag_indices_from(dS_dVm)] += np.conj(Ibus) * Vn
            dS_dVa = -1j * V[:, None] * np.conj(Y * V[None, :])
            dS_dVa[np.diag_indices_from(dS_dVa)] += 1j * V * np.conj(Ibus)
            A = dS_dVa[np.ix_(pvpq, pvpq)]
            B = dS_dVm[np.ix_(pvpq, pq)]
            J = np.block([[A.real, B.real], [A.imag, B.imag]])
            dx = np.linalg.solve(J, -F)
            Va = np.angle(V)
            Vm = np.abs(V)
            Va[pvpq] += dx[: len(pvpq)]
            Vm[pq] += dx[len(pvpq):]
            V = Vm * np.exp(1j * Va)
            if not np.all(np.isfinite(V)):
                break
        return Solution(conv, V if conv else None), {"p_load": pl, "q_load": ql, "p_sgen": pg}

    def results(self, V):
        """pandapower-equivalent result quantities from a converged voltage vector."""
        If = self.Yf @ V
        It = self.Yt @ V
        Sf = V[self.fbus] * np.conj(If) * self.baseMVA
        St = V[self.tbus] * np.conj(It) * self.baseMVA
        vm = np.abs(V)
        i_f = np.abs(Sf) / (np.sqrt(3) * vm[self.fbus] * self.vn_kv[self.fbus])
        i_t = np.abs(St) / (np.sqrt(3) * vm[self.tbus] * self.vn_kv[self.tbus])
        lb = self.line_br
        i_ka = np.maximum(i_f[lb], i_t[lb])
        loading = np.where(self.br_status[lb], i_ka / self.imax_ka * 100.0, 0.0)
        return {
            "vm_pu": vm[self.bus_ppc],
            "line_loading_percent": loading,
            "line_p_from_mw": np.where(self.br_status[lb], Sf[lb].real, 0.0),
            "trafo_p_hv_mw": Sf[self.trafo_br].real,
        }


_CACHE: dict[E.Config, FastAC] = {}


def solver(cfg: E.Config) -> FastAC:
    if cfg not in _CACHE:
        _CACHE[cfg] = FastAC(cfg)
    return _CACHE[cfg]


def solve_state(x, cfg: E.Config):
    """Returns (converged, raw result dict incl. injections)."""
    s = solver(cfg)
    sol, inj = s.solve(x)
    if not sol.converged:
        return False, None
    r = s.results(sol.V)
    r.update(inj)
    return True, r
