"""Solved power flow -> flat measurement vector (what rules see).

Names:
  vm_pu.<bus>            bus voltage magnitude, pu
  loading.<line>         line loading_percent (pandapower definition)
  p_from.<line>          line active power at from end, MW
  trafo_p_hv.<trafo>     transformer active power at HV side, MW
  trafo_loading.<trafo>  transformer loading_percent (pandapower definition)
  sw.<switch>            switch state, 1 closed, 0 open
  line_in.<line>         line in service, 1 or 0
  load_p.<load>          metered load active power, MW   (added: needed by R2, R3)
  sgen_p.<sgen>          metered DER active power, MW    (added: needed by R3)
  storage_p.<storage>    metered storage active power, MW, positive = charging (grids with storage)

Indices are pandapower element indices of the CIGRE MV net.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from . import envelope as E
from . import fastpf as F


@lru_cache(maxsize=1)
def names() -> tuple[str, ...]:
    net = E._base_net()
    n = []
    n += [f"vm_pu.{b}" for b in net.bus.index]
    n += [f"loading.{l}" for l in net.line.index]
    n += [f"p_from.{l}" for l in net.line.index]
    n += [f"trafo_p_hv.{t}" for t in net.trafo.index]
    n += [f"trafo_loading.{t}" for t in net.trafo.index]
    n += [f"sw.{s}" for s in net.switch.index]
    n += [f"line_in.{l}" for l in net.line.index]
    n += [f"load_p.{i}" for i in net.load.index]
    n += [f"sgen_p.{j}" for j in net.sgen.index]
    if E.dims().n_sto:
        n += [f"storage_p.{k}" for k in net.storage.index]
    return tuple(n)


@lru_cache(maxsize=1)
def index() -> dict[str, int]:
    return {k: i for i, k in enumerate(names())}


@lru_cache(maxsize=None)
def _discrete(cfg: E.Config):
    net = E.apply_config(E.base_net(), cfg)
    return net.switch.closed.values.astype(float), net.line.in_service.values.astype(float)


def vector_from_fast(r: dict, cfg: E.Config) -> np.ndarray:
    sw, lin = _discrete(cfg)
    return np.concatenate([
        r["vm_pu"], r["line_loading_percent"], r["line_p_from_mw"], r["trafo_p_hv_mw"],
        r["trafo_loading_percent"], sw, lin, r["p_load"], r["p_sgen"], r["p_sto"],
    ])


def vector_from_net(net) -> np.ndarray:
    lin = net.line.in_service.values
    return np.concatenate([
        net.res_bus.vm_pu.values,
        np.where(lin, net.res_line.loading_percent.values, 0.0),
        np.where(lin, net.res_line.p_from_mw.values, 0.0),
        net.res_trafo.p_hv_mw.values,
        net.res_trafo.loading_percent.values,
        net.switch.closed.values.astype(float),
        lin.astype(float),
        net.load.p_mw.values,
        net.sgen.p_mw.values,
        net.storage.p_mw.values if E.dims().n_sto else np.zeros(0),
    ])


@lru_cache(maxsize=1)
def _slices():
    idx = index()
    vm = [idx[k] for k in names() if k.startswith("vm_pu.")]
    ld = [idx[k] for k in names() if k.startswith("loading.") or k.startswith("trafo_loading.")]
    return np.array(vm), np.array(ld)


def benign_check(m: np.ndarray) -> tuple[bool, float]:
    """Operating limits (bus voltage, line AND transformer loading). Returns (benign, violation) with violation >= 0 (0 iff benign)."""
    vm_i, ld_i = _slices()
    vm = m[vm_i]
    viol = max(0.0, float(np.max(E.V_MIN - vm)), float(np.max(vm - E.V_MAX)))
    viol = max(viol, float(np.max(m[ld_i] - E.LOADING_MAX)) / 100.0)  # loading in units of 100 %
    return viol <= 0.0, viol


def evaluate(x, cfg: E.Config):
    """Fast AC solve -> (converged, benign, violation, measurement vector or None)."""
    ok, r = F.solve_state(x, cfg)
    if not ok:
        return False, False, np.inf, None
    m = vector_from_fast(r, cfg)
    b, v = benign_check(m)
    return True, b, v, m
