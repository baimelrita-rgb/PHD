"""Benign operating envelope for the CIGRE MV reference grid, and a sampler.

Envelope (all parameters explicit, see ENVELOPE_FULL and ENVELOPE_NARROW):
  * per-load active power scaling s_i in [lo, hi] of nominal, independent per load,
    power factor kept (q scaled by the same factor)
  * per-DER active output g_j in [0, 1] of rated (q = 0, as in the base model)
  * discrete topology: tie switches S1, S2, S3 and at most one planned line outage,
    restricted to configurations that are connected and radial (a spanning tree
    over buses 0..14 using transformers and active lines)
  * transformer taps: the pandapower CIGRE MV model has NO tap changer
    (tap_pos, tap_min, tap_max are NaN). Taps are therefore fixed. Recorded as an
    open item for the owner.

A sampled state is benign iff the AC power flow converges and
  bus vm_pu in [0.90, 1.10] for all buses and line loading_percent <= 100.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import combinations

import networkx as nx
import numpy as np
import pandapower as pp
import pandapower.networks as pn
from scipy.stats import qmc

SEED = 7
V_MIN, V_MAX = 0.90, 1.10
LOADING_MAX = 100.0
TIE_SWITCH_NAMES = ("S1", "S2", "S3")


@dataclass(frozen=True)
class Envelope:
    name: str
    load_scale: tuple[float, float] = (0.2, 1.2)
    der_scale: tuple[float, float] = (0.0, 1.0)
    allow_reconfiguration: bool = True  # tie switch + single planned outage configs


ENVELOPE_FULL = Envelope("full")
ENVELOPE_NARROW = Envelope("narrow", load_scale=(0.6, 0.9))


def build_net():
    """Fresh copy of the reference grid."""
    return pn.create_cigre_network_mv(with_der="pv_wind")


@lru_cache(maxsize=1)
def _base_net():
    return build_net()


def base_net():
    return copy.deepcopy(_base_net())


@dataclass(frozen=True)
class Config:
    """Discrete topology: set of closed tie switches and an optional line outage."""
    closed_ties: tuple[str, ...]
    line_out: int | None

    @property
    def label(self) -> str:
        t = "+".join(self.closed_ties) if self.closed_ties else "none"
        o = "none" if self.line_out is None else f"L{self.line_out}"
        return f"ties={t};out={o}"


def tie_switch_index(net) -> dict[str, int]:
    return {n: int(net.switch.index[net.switch.name == n][0]) for n in TIE_SWITCH_NAMES}


def apply_config(net, cfg: Config):
    ties = tie_switch_index(net)
    for name, idx in ties.items():
        net.switch.at[idx, "closed"] = name in cfg.closed_ties
    net.line["in_service"] = True
    if cfg.line_out is not None:
        net.line.at[cfg.line_out, "in_service"] = False
    return net


def active_lines(net) -> list[int]:
    """Lines that are in service and have every line switch closed."""
    out = []
    for li in net.line.index:
        if not net.line.at[li, "in_service"]:
            continue
        sw = net.switch[(net.switch.et == "l") & (net.switch.element == li)]
        if len(sw) and not sw.closed.all():
            continue
        out.append(int(li))
    return out


def topology_graph(net) -> nx.Graph:
    g = nx.Graph()
    g.add_nodes_from(int(b) for b in net.bus.index)
    for ti in net.trafo.index[net.trafo.in_service]:
        g.add_edge(int(net.trafo.at[ti, "hv_bus"]), int(net.trafo.at[ti, "lv_bus"]), kind="trafo", idx=int(ti))
    for li in active_lines(net):
        g.add_edge(int(net.line.at[li, "from_bus"]), int(net.line.at[li, "to_bus"]), kind="line", idx=li)
    return g


@lru_cache(maxsize=1)
def enumerate_configs() -> tuple[Config, ...]:
    """All tie/outage combinations (<= 1 outage) that are connected and radial."""
    net = base_net()
    lines = list(net.line.index)
    found = []
    seen = set()
    for k in range(len(TIE_SWITCH_NAMES) + 1):
        for ties in combinations(TIE_SWITCH_NAMES, k):
            for out in [None] + lines:
                cfg = Config(tuple(ties), None if out is None else int(out))
                apply_config(net, cfg)
                g = topology_graph(net)
                key = frozenset(active_lines(net))
                if nx.is_tree(g) and key not in seen:
                    # configurations with identical active line sets are the same
                    # electrical topology; keep the first (simplest) representation
                    seen.add(key)
                    found.append(cfg)
    apply_config(net, Config((), None))
    # base config first
    found.sort(key=lambda c: (len(c.closed_ties), -1 if c.line_out is None else c.line_out))
    return tuple(found)


def base_config() -> Config:
    return Config((), None)


@dataclass
class Dims:
    n_load: int
    n_der: int

    @property
    def n_cont(self) -> int:
        return self.n_load + self.n_der


@lru_cache(maxsize=1)
def dims() -> Dims:
    net = _base_net()
    return Dims(len(net.load), len(net.sgen))


def cont_bounds(env: Envelope) -> list[tuple[float, float]]:
    d = dims()
    return [env.load_scale] * d.n_load + [env.der_scale] * d.n_der


def sample_lhs(env: Envelope, n: int, seed: int = SEED, configs=None):
    """Latin hypercube over continuous parameters plus one extra LHS dimension that
    selects the discrete configuration uniformly. Returns (X, cfg_index)."""
    configs = enumerate_configs() if configs is None else configs
    if not env.allow_reconfiguration:
        configs = (base_config(),)
    d = dims()
    sampler = qmc.LatinHypercube(d=d.n_cont + 1, seed=seed)
    u = sampler.random(n)
    lo = np.array([b[0] for b in cont_bounds(env)])
    hi = np.array([b[1] for b in cont_bounds(env)])
    X = lo + u[:, : d.n_cont] * (hi - lo)
    ci = np.minimum((u[:, -1] * len(configs)).astype(int), len(configs) - 1)
    return X, ci, configs


def split_x(x):
    d = dims()
    return np.asarray(x[: d.n_load]), np.asarray(x[d.n_load : d.n_cont])


def apply_state(net, x, cfg: Config):
    """Set loads, DER and topology on a pandapower net (used by the reference solver)."""
    base = _base_net()
    s, g = split_x(x)
    net.load["p_mw"] = base.load.p_mw.values * s
    net.load["q_mvar"] = base.load.q_mvar.values * s
    net.sgen["p_mw"] = base.sgen.sn_mva.values * g
    net.sgen["q_mvar"] = 0.0
    apply_config(net, cfg)
    return net


def run_reference_pf(x, cfg: Config):
    """Full pandapower AC power flow. Returns solved net or None if not converged."""
    net = apply_state(base_net(), x, cfg)
    try:
        pp.runpp(net, numba=True)
    except pp.LoadflowNotConverged:
        return None
    return net
