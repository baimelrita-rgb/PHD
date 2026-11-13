"""Reconstructed Sherlock 01-Basic grid: pandapower CIGRE MV (with_der="all") plus
the 32 recorded switches, identified transformer parameters and transformer taps.
Identification code lives in scripts/07 and scripts/08; identified values are stored
in rules/sherlock_grid_params.json."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandapower as pp
import pandapower.networks as pn

from . import sherlock_io as S

PARAMS_PATH = Path(__file__).resolve().parents[2] / "rules" / "sherlock_grid_params.json"


def load_params():
    if PARAMS_PATH.exists():
        d = json.loads(PARAMS_PATH.read_text())
        return {int(k): v for k, v in d["trafo"].items()}, d.get("tap")
    return None, None


def apply_tap(net, tap):
    """tap = {"side": "hv"|"lv", "step_percent": x, "neutral": 0, "min": a, "max": b}."""
    for t in net.trafo.index:
        net.trafo.at[t, "tap_side"] = tap["side"]
        net.trafo.at[t, "tap_neutral"] = tap.get("neutral", 0)
        net.trafo.at[t, "tap_min"] = tap["min"]
        net.trafo.at[t, "tap_max"] = tap["max"]
        net.trafo.at[t, "tap_step_percent"] = tap["step_percent"]
        net.trafo.at[t, "tap_step_degree"] = 0.0
        if "tap_changer_type" in net.trafo.columns:
            net.trafo.at[t, "tap_changer_type"] = "Ratio"
        net.trafo.at[t, "tap_pos"] = 0


P_DEAD_W = 1.0   # |P| and |Q| below 1 W/var at a line end = no flow at that end (measurement check only)


def switch_map(net):
    """Sherlock switch index -> (bus, line). Switches 0..7 are pandapower's own (same order).
    Inferred from the data (see report): switch 8+2l is the from end of line l, 9+2l the to end,
    for lines 0..11 (lines 12..14 already carry pandapower's tie switches)."""
    m = {}
    for l in range(12):
        m[8 + 2 * l] = (int(net.line.at[l, "from_bus"]), l, "from")
        m[9 + 2 * l] = (int(net.line.at[l, "to_bus"]), l, "to")
    return m


def fit_trafo(z, members):
    """Least squares on recorded transformer losses (disjoint snapshots, tap 0):
    P_loss = pfe + vkr * Sn * (S/Sn)^2,  Q_loss = q0 + vk_x * Sn * (S/Sn)^2, S from HV side."""
    out = {}
    for t in (0, 1):
        A, bp, bq = [], [], []
        for mname in members:
            v = S.read_snapshot(z, mname)["values"]
            if v[f"trafo.{t}.MEASUREMENT.tap_position"] != 0:
                continue
            P = v[f"trafo.{t}.MEASUREMENT.active_power_hv"] / 1e6
            Q = v[f"trafo.{t}.MEASUREMENT.reactive_power_hv"] / 1e6
            x = (P * P + Q * Q) / v[f"trafo.{t}.MEASUREMENT.voltage_hv"] ** 2 / 25.0
            A.append([1.0, x]); bp.append(v[f"trafo.{t}.MEASUREMENT.active_power_loss"] / 1e6)
            bq.append(v[f"trafo.{t}.MEASUREMENT.reactive_power_loss"] / 1e6)
        A = np.array(A)
        cp = np.linalg.lstsq(A, np.array(bp), rcond=None)[0]
        cq = np.linalg.lstsq(A, np.array(bq), rcond=None)[0]
        vkr = 100 * cp[1]
        vkx = 100 * cq[1]
        out[t] = {"vkr_percent": vkr, "vk_percent": float(np.hypot(vkr, vkx)), "pfe_kw": 1e3 * cp[0],
                  "i0_percent": 100 * float(np.hypot(cp[0], cq[0])) / 25.0, "n": len(bp),
                  "resid_kw": 1e3 * float(np.max(np.abs(np.array(bp) - A @ cp)))}
    return out


def build(snap, trafo_params=None, tap=None):
    v = snap
    net = pn.create_cigre_network_mv(with_der="all")
    if trafo_params:
        for t, prm in trafo_params.items():
            for k in ("vkr_percent", "vk_percent", "pfe_kw", "i0_percent"):
                net.trafo.at[t, k] = prm[k]
    if tap:
        apply_tap(net, tap)
        for t in net.trafo.index:
            net.trafo.at[t, "tap_pos"] = int(v[f"trafo.{t}.MEASUREMENT.tap_position"])
    net.ext_grid.at[0, "vm_pu"] = v["bus.0.MEASUREMENT.voltage"]
    net.ext_grid.at[0, "va_degree"] = v["bus.0.MEASUREMENT.voltage_angle"]
    for kind, df in (("load", net.load), ("sgen", net.sgen), ("storage", net.storage)):
        for i in df.index:
            df.at[i, "p_mw"] = v[f"{kind}.{i}.MEASUREMENT.active_power"] / 1e6
            df.at[i, "q_mvar"] = v[f"{kind}.{i}.MEASUREMENT.reactive_power"] / 1e6
            df.at[i, "in_service"] = bool(v[f"{kind}.{i}.MEASUREMENT.is_connected"])
    for sidx in net.switch.index:  # pandapower's own 8 switches
        net.switch.at[sidx, "closed"] = bool(v[f"switch.{sidx}.MEASUREMENT.is_closed"])
    opened, checks = [], []
    for sidx, (bus, l, end) in switch_map(net).items():
        closed = bool(v[f"switch.{sidx}.MEASUREMENT.is_closed"])
        pp.create_switch(net, bus, l, et="l", closed=closed)
        if not closed:
            opened.append(f"sw{sidx}=L{l}:{end}")
            # consistency check of the mapping: an open end must carry no power
            checks.append(abs(v[f"line.{l}.MEASUREMENT.active_power_{end}"]) < P_DEAD_W)
    opened += [f"sw{i}" for i in range(8) if not v[f"switch.{i}.MEASUREMENT.is_closed"]]
    return net, tuple(sorted(opened)), checks


def noise_floor(snap, net):
    """Same physical voltage recorded twice (bus voltage and line end voltage): max abs difference."""
    d = [abs(snap[f"line.{l}.MEASUREMENT.voltage_from"] - snap[f"bus.{int(net.line.at[l, 'from_bus'])}.MEASUREMENT.voltage"])
         for l in net.line.index]
    return max(d)




def base_net():
    """Reconstructed Sherlock grid in its nominal state: CIGRE MV (all DER), identified
    transformer and tap parameters, the 24 extra line-end switches (all closed), taps at 0."""
    trafo, tap = load_params()
    if trafo is None:
        raise SystemExit(f"missing {PARAMS_PATH}: run scripts/08_identify_taps.py first")
    net = pn.create_cigre_network_mv(with_der="all")
    for t, prm in trafo.items():
        for k in ("vkr_percent", "vk_percent", "pfe_kw", "i0_percent"):
            net.trafo.at[t, k] = prm[k]
    if tap:
        apply_tap(net, tap)
    for sidx, (bus, l, end) in switch_map(net).items():
        pp.create_switch(net, bus, l, et="l", closed=True)
    assert list(net.switch.index) == list(range(32))
    return net


def fixed_switch_states():
    """Known state of switches without telemetry (constant in the recording): 02-Semiurban only,
    read once from the first train ground-truth snapshot (planning records)."""
    from . import envelope as E
    if E.grid().name != "semiurban":
        return None
    global _FIXED
    try:
        return _FIXED
    except NameError:
        pass
    from . import sherlock_io as S
    z, idx = S.physical_index(S.ROOT_SEMI, "train")
    v = S.read_snapshot(z, idx[0][1])["values"]
    _FIXED = {int(k.split(".")[1]): bool(val) for k, val in v.items() if k.startswith("switch.") and k.endswith("MEASUREMENT.is_closed")}
    return _FIXED


_NETCACHE = {}


def record_measurements(state: dict, names, net) -> "np.ndarray":
    """IPAL state record -> measurement vector in the order of measure.names().
    Line loading is recomputed from the reported end currents (IPAL has no line loading field)."""
    key = id(net)
    if key not in _NETCACHE:
        ls = {}
        for s_, et, el in zip(net.switch.index, net.switch.et.values, net.switch.element.values):
            if et == "l":
                ls.setdefault(int(el), []).append(int(s_))
        _NETCACHE[key] = ((net.line.max_i_ka * net.line.df * net.line.parallel).values * 1e3, ls)
    imax_a, line_sw = _NETCACHE[key]
    out = np.zeros(len(names))
    nan = float("nan")
    fixed = fixed_switch_states()
    _st = state

    class _S(dict):          # unmonitored values read as NaN; unmonitored switches use their fixed state
        def __missing__(self, k):
            if k.startswith("switch.") and k.endswith(":is_closed") and fixed is not None:
                return fixed.get(int(k.split(".")[1].split(":")[0]), True)
            if k.endswith(":is_closed"):
                return True
            return nan
    state = _S(_st)
    for j, n in enumerate(names):
        kind, i = n.split(".")
        i = int(i)
        if kind == "vm_pu":
            out[j] = state[f"bus.{i}:voltage"]
        elif kind == "loading":
            out[j] = max(state[f"line.{i}:current_from"], state[f"line.{i}:current_to"]) / imax_a[i] * 100
        elif kind == "p_from":
            out[j] = state[f"line.{i}:active_power_from"] / 1e6
        elif kind == "trafo_p_hv":
            out[j] = state[f"trafo.{i}:active_power_hv"] / 1e6
        elif kind == "trafo_loading":
            out[j] = state[f"trafo.{i}:loading"]
        elif kind == "sw":
            out[j] = float(bool(state[f"switch.{i}:is_closed"]))
        elif kind == "line_in":
            out[j] = float(all(bool(state[f"switch.{s_}:is_closed"]) for s_ in line_sw.get(i, ())))
        elif kind == "tap":
            p_ = state[f"trafo.{i}:tap_position"]
            out[j] = float(p_ - 256 if p_ > 127 else p_)
        elif kind == "load_p":
            out[j] = state[f"load.{i}:active_power"] / 1e6
        elif kind == "sgen_p":
            out[j] = state[f"sgen.{i}:active_power"] / 1e6
        elif kind == "load_q":
            out[j] = state[f"load.{i}:reactive_power"] / 1e6
        elif kind == "storage_p":
            out[j] = state[f"storage.{i}:active_power"] / 1e6
        else:
            raise KeyError(n)
    return out
