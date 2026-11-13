"""Benign operating envelope and sampler, for a selectable grid.

Grids (see GRIDS, select with use_grid(name); default "cigre_pv_wind"):
  * cigre_pv_wind  WP0 reference grid, pandapower create_cigre_network_mv(with_der="pv_wind").
                   Loads: P scaling s in [0.2, 1.2], power factor kept. DER in [0, 1] of rated.
                   Topologies: tie switches S1 S2 S3 with at most one line out. No tap changer.
  * sherlock       Reconstructed Sherlock 01-Basic grid (src/p3/sherlock_model.py). Per-element
                   bounds derived from train data (rules/sherlock_envelope.json, scripts/10a).
                   Load Q fixed at nominal (as recorded). DER and storage P in observed ranges.
                   Topologies: connected with at most one closed loop (Sherlock operates meshed after
                   maintenance), up to two lines out. Taps: positions observed in train.

Continuous parameters x = [load P scaling (n_load), DER scaling (n_der), storage scaling (n_sto),
load Q scaling (n_load, only for grids with load_q = "free")];
injections are affine in x (injection_maps()).

A sampled state is benign iff the AC power flow converges and
  bus vm_pu in [0.90, 1.10] for all buses, line loading_percent <= 100 and
  transformer loading_percent <= 100 (added after WP0 round 1, owner decision 6).
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from typing import Callable

import networkx as nx
import numpy as np
import pandapower as pp
import pandapower.networks as pn
from scipy.stats import qmc

SEED = 7
V_MIN, V_MAX = 0.90, 1.10
LOADING_MAX = 100.0
TIE_SWITCH_NAMES = ("S1", "S2", "S3")
ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Envelope:
    name: str
    load_scale: tuple = (0.2, 1.2)     # (lo, hi) for all loads, or a tuple of per-load (lo, hi)
    der_scale: tuple = (0.0, 1.0)
    sto_scale: tuple = (0.0, 1.0)
    lq_scale: tuple = ()               # load Q / nominal bounds (grids with load_q = "free")
    allow_reconfiguration: bool = True


@dataclass(frozen=True)
class GridSpec:
    name: str
    builder: Callable
    envelopes: Callable             # () -> dict name -> Envelope
    max_outages: int = 1
    tap_options: tuple = ((),)      # tuples of tap positions per transformer; () keeps the model's own
    max_loops: int = 0              # 0: radial only; 1: connected with at most one closed loop
    configs_fn: Callable | None = None   # explicit configuration list (large grids: topologies from data)
    load_q: str = "pf"              # "pf": q scales with p; "fixed": q stays nominal; "free": own parameter


def _cigre_builder():
    return pn.create_cigre_network_mv(with_der="pv_wind")


def _cigre_envelopes():
    return {"full": Envelope("full"), "narrow": Envelope("narrow", load_scale=(0.6, 0.9))}


SHERLOCK_ENV_PATH = ROOT / "rules" / "sherlock_envelope.json"


def _sherlock_builder():
    from . import sherlock_model as SM
    return SM.base_net()


def _sherlock_envelopes():
    if not SHERLOCK_ENV_PATH.exists():
        raise SystemExit(f"missing {SHERLOCK_ENV_PATH}: run scripts/10a_sherlock_envelope.py first")
    d = json.loads(SHERLOCK_ENV_PATH.read_text())
    tup = lambda xs: tuple(tuple(b) for b in xs)
    full = Envelope("full", tup(d["load"]), tup(d["sgen"]), tup(d["storage"]))
    return {"full": full}


def _sherlock_taps():
    if not SHERLOCK_ENV_PATH.exists():
        return ((0, 0),)
    return tuple(tuple(t) for t in json.loads(SHERLOCK_ENV_PATH.read_text())["taps"])


SEMI_ENV_PATH = ROOT / "rules" / "semiurban_envelope.json"


def _sb_env_path(name):
    return ROOT / "rules" / f"{name}_envelope.json"


def _sb_builder(name):
    def f():
        from . import semiurban_model as SU
        net = SU.base_net(name)
        net.switch["closed"] = True     # topology is expressed by lines out of service
        return net
    return f


def _sb_json(name):
    p = _sb_env_path(name)
    if not p.exists():
        raise SystemExit(f"missing {p}: run scripts/16a_semiurban_envelope.py --grid {name} first")
    return json.loads(p.read_text())


def _sb_envelopes(name):
    def f():
        d = _sb_json(name)
        tup = lambda xs: tuple(tuple(b) for b in xs)
        return {"full": Envelope("full", tup(d["load"]), tup(d["sgen"]), tup(d["storage"]), tup(d.get("load_q_bounds", ())))}
    return f


def _sb_configs(name):
    def f():
        d = _sb_json(name)
        return tuple(Config((), None if not t else (int(t[0]) if len(t) == 1 else tuple(int(x) for x in t)), ()) for t in d["topologies"])
    return f


GRIDS = {
    "cigre_pv_wind": lambda: GridSpec("cigre_pv_wind", _cigre_builder, _cigre_envelopes),
    "sherlock": lambda: GridSpec("sherlock", _sherlock_builder, _sherlock_envelopes, max_outages=2,
                                 tap_options=_sherlock_taps(), load_q="fixed", max_loops=1),
    "semiurban": lambda: GridSpec("semiurban", _sb_builder("semiurban"), _sb_envelopes("semiurban"), load_q="free", configs_fn=_sb_configs("semiurban")),
    "rural": lambda: GridSpec("rural", _sb_builder("rural"), _sb_envelopes("rural"), load_q="free", configs_fn=_sb_configs("rural")),
}
_GRID = GRIDS["cigre_pv_wind"]()


def grid() -> GridSpec:
    return _GRID


def use_grid(name: str):
    """Switch the active grid and clear every cache that depends on it."""
    global _GRID
    _GRID = GRIDS[name]()
    for f in (_base_net, enumerate_configs, dims, _envelopes, injection_maps):
        f.cache_clear()
    from . import fastpf, linac, lindistflow, measure
    fastpf._CACHE.clear()
    lindistflow.model.cache_clear()
    linac.model.cache_clear()
    for f in (measure.names, measure.index, measure._discrete, measure._slices):
        f.cache_clear()
    return _GRID


@lru_cache(maxsize=1)
def _envelopes():
    return _GRID.envelopes()


def full() -> Envelope:
    return _envelopes()["full"]


def narrow() -> Envelope:
    return _envelopes()["narrow"]


# backward compatible names (reference grid)
ENVELOPE_FULL = _cigre_envelopes()["full"]
ENVELOPE_NARROW = _cigre_envelopes()["narrow"]


def build_net():
    return _GRID.builder()


@lru_cache(maxsize=1)
def _base_net():
    return build_net()


def base_net():
    return copy.deepcopy(_base_net())


@dataclass(frozen=True)
class Config:
    """Discrete state: closed tie switches, lines out (None, an index or a tuple), tap positions."""
    closed_ties: tuple[str, ...]
    line_out: int | tuple | None
    taps: tuple = ()

    @property
    def lines_out(self) -> tuple:
        if self.line_out is None:
            return ()
        if isinstance(self.line_out, tuple):
            return self.line_out
        return (int(self.line_out),)

    @property
    def label(self) -> str:
        t = "+".join(self.closed_ties) if self.closed_ties else "none"
        o = "+".join(f"L{l}" for l in self.lines_out) or "none"
        s = f"ties={t};out={o}"
        if self.taps:
            s += ";tap=" + ",".join(str(p) for p in self.taps)
        return s


def tie_switch_index(net) -> dict[str, int]:
    """Named tie switches S1 to S3 (CIGRE grids); empty for grids without them."""
    out = {}
    for n in TIE_SWITCH_NAMES:
        hit = net.switch.index[net.switch.name == n]
        if len(hit):
            out[n] = int(hit[0])
    return out


def apply_config(net, cfg: Config):
    ties = tie_switch_index(net)
    for name, idx in ties.items():
        net.switch.at[idx, "closed"] = name in cfg.closed_ties
    net.line["in_service"] = True
    for l in cfg.lines_out:
        net.line.at[l, "in_service"] = False
    if cfg.taps:
        net.trafo["tap_pos"] = np.array(cfg.taps)
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
    for si in net.switch.index[(net.switch.et == "b") & net.switch.closed]:      # closed bus-bus couplers
        g.add_edge(int(net.switch.at[si, "bus"]), int(net.switch.at[si, "element"]), kind="coupler", idx=int(si))
    return g


@lru_cache(maxsize=1)
def enumerate_configs() -> tuple[Config, ...]:
    """All tie / outage combinations (<= max_outages lines out) that are connected with at
    most max_loops closed loops (0 = radial), times the tap options. Configurations with the same active line set are the
    same electrical topology; the first (simplest) representation is kept."""
    if _GRID.configs_fn is not None:
        return _GRID.configs_fn()
    net = base_net()
    lines = list(net.line.index)
    found, seen = [], set()
    for k in range(len(TIE_SWITCH_NAMES) + 1):
        for ties in combinations(TIE_SWITCH_NAMES, k):
            for n_out in range(_GRID.max_outages + 1):
                for outs in combinations(lines, n_out):
                    lo = None if n_out == 0 else (int(outs[0]) if n_out == 1 else tuple(int(o) for o in outs))
                    cfg = Config(tuple(ties), lo)
                    apply_config(net, cfg)
                    key = frozenset(active_lines(net))
                    g = topology_graph(net)
                    ok = nx.is_connected(g) and (g.number_of_edges() - g.number_of_nodes() + 1) <= _GRID.max_loops
                    if key not in seen and ok:
                        seen.add(key)
                        found.append(cfg)
    # stable sort: number of closed ties, then lines out (keeps the WP0 order on the reference grid)
    found.sort(key=lambda c: (len(c.closed_ties), c.lines_out))
    out = []
    for c in found:
        for t in _GRID.tap_options:
            out.append(Config(c.closed_ties, c.line_out, tuple(t)))
    return tuple(out)


def is_radial(cfg: Config) -> bool:
    return nx.is_tree(topology_graph(apply_config(base_net(), cfg)))


def base_config() -> Config:
    return enumerate_configs()[0]


@dataclass
class Dims:
    n_load: int
    n_der: int
    n_sto: int = 0
    n_lq: int = 0

    @property
    def n_cont(self) -> int:
        return self.n_load + self.n_der + self.n_sto + self.n_lq


@lru_cache(maxsize=1)
def dims() -> Dims:
    net = _base_net()
    n_sto = len(net.storage) if "storage" in net and len(net.storage) else 0
    return Dims(len(net.load), len(net.sgen), n_sto, len(net.load) if _GRID.load_q == "free" else 0)


def _expand(b, n):
    if len(b) == 2 and not isinstance(b[0], (tuple, list)):
        return [tuple(map(float, b))] * n
    assert len(b) == n, (len(b), n)
    return [tuple(map(float, x)) for x in b]


def cont_bounds(env: Envelope | None = None) -> list[tuple[float, float]]:
    env = full() if env is None else env
    d = dims()
    return (_expand(env.load_scale, d.n_load) + _expand(env.der_scale, d.n_der) + (_expand(env.sto_scale, d.n_sto) if d.n_sto else [])
            + (_expand(env.lq_scale, d.n_lq) if d.n_lq else []))


def sample_lhs(env: Envelope | None, n: int, seed: int = SEED, configs=None):
    """Latin hypercube over continuous parameters plus one extra LHS dimension that
    selects the discrete configuration uniformly. Returns (X, cfg_index, configs)."""
    env = full() if env is None else env
    configs = enumerate_configs() if configs is None else configs
    if not env.allow_reconfiguration:
        configs = (base_config(),)
    d = dims()
    u = qmc.LatinHypercube(d=d.n_cont + 1, seed=seed).random(n)
    b = cont_bounds(env)
    lo = np.array([x[0] for x in b]); hi = np.array([x[1] for x in b])
    X = lo + u[:, : d.n_cont] * (hi - lo)
    ci = np.minimum((u[:, -1] * len(configs)).astype(int), len(configs) - 1)
    return X, ci, configs


def split_x(x):
    d = dims()
    x = np.asarray(x)
    return x[: d.n_load], x[d.n_load: d.n_load + d.n_der], x[d.n_load + d.n_der: d.n_load + d.n_der + d.n_sto]


@dataclass
class InjectionMaps:
    """Element injections as affine maps of x: value = A @ x + c (MW, Mvar).
    Loads and storage consume (positive = consumption); sgen generate."""
    Apl: np.ndarray
    Aql: np.ndarray
    cql: np.ndarray
    Apg: np.ndarray
    Apb: np.ndarray

    def __call__(self, x):
        x = np.asarray(x)
        return self.Apl @ x, self.Aql @ x + self.cql, self.Apg @ x, self.Apb @ x


@lru_cache(maxsize=1)
def injection_maps() -> InjectionMaps:
    net = _base_net()
    d = dims()
    n = d.n_cont
    Apl = np.zeros((d.n_load, n)); Aql = np.zeros((d.n_load, n)); cql = np.zeros(d.n_load)
    for i in range(d.n_load):
        Apl[i, i] = net.load.p_mw.values[i]
        if _GRID.load_q == "pf":
            Aql[i, i] = net.load.q_mvar.values[i]
        elif _GRID.load_q == "free":
            Aql[i, d.n_load + d.n_der + d.n_sto + i] = net.load.q_mvar.values[i]
        else:
            cql[i] = net.load.q_mvar.values[i]
    Apg = np.zeros((d.n_der, n))
    for j in range(d.n_der):
        Apg[j, d.n_load + j] = net.sgen.sn_mva.values[j]
    Apb = np.zeros((d.n_sto, n))
    for k in range(d.n_sto):
        p_nom = abs(float(net.storage.p_mw.values[k]))       # SimBench stores discharge as negative p_mw
        Apb[k, d.n_load + d.n_der + k] = p_nom if p_nom > 0 else float(net.storage.sn_mva.values[k])
    return InjectionMaps(Apl, Aql, cql, Apg, Apb)


def apply_state(net, x, cfg: Config):
    """Set loads, DER, storage and topology on a pandapower net (used by the reference solver)."""
    pl, ql, pg, pb = injection_maps()(x)
    net.load["p_mw"] = pl
    net.load["q_mvar"] = ql
    net.sgen["p_mw"] = pg
    net.sgen["q_mvar"] = 0.0
    if dims().n_sto:
        net.storage["p_mw"] = pb
        net.storage["q_mvar"] = 0.0
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
