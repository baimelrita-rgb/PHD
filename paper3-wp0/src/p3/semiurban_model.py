"""Reconstructed Sherlock 02-Semiurban grid.

Base: SimBench 1-MV-semiurb--2-sw (switch, line, load, sgen, storage indices as in SimBench).
Additions identified from data (scripts/15a, rules/semiurban_structure.json): 56 new buses
(122..177), each fed from an MV bus by a new 0.63 MVA transformer (2..57) with two switches
(248..359), carrying one sgen and one storage unit moved from the MV bus. Transformer
parameters: SimBench's for 0 and 1 (confirmed by the fit), the median fit of the 56 new
transformers (all the same type) for 2..57."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandapower as pp

STRUCT_PATH = Path(__file__).resolve().parents[2] / "rules" / "semiurban_structure.json"
LV_KV = 0.4


@lru_cache(maxsize=1)
def structure():
    if not STRUCT_PATH.exists():
        raise SystemExit(f"missing {STRUCT_PATH}: run scripts/15a_semiurban_identify.py first")
    return json.loads(STRUCT_PATH.read_text())


def new_trafo_params():
    tp = structure()["trafo"]
    keys = ("sn_mva", "vk_percent", "vkr_percent", "pfe_kw", "i0_percent")
    return {k: float(np.median([tp[str(t)][k] for t in range(2, 58)])) for k in keys}


def base_net():
    import simbench as sb
    net = sb.get_simbench_net("1-MV-semiurb--2-sw")
    net.profiles = {}     # profiles are not used; injections come from data or the envelope
    p = new_trafo_params()
    for s in sorted(structure()["structures"], key=lambda s: s["trafo"]):
        b = pp.create_bus(net, vn_kv=LV_KV, name=f"new bus {s['new_bus']}", index=s["new_bus"])
        assert b == s["new_bus"]
        t = pp.create_transformer_from_parameters(
            net, hv_bus=s["mv_bus"], lv_bus=b, sn_mva=p["sn_mva"], vn_hv_kv=net.bus.vn_kv.at[s["mv_bus"]], vn_lv_kv=LV_KV,
            vkr_percent=p["vkr_percent"], vk_percent=p["vk_percent"], pfe_kw=p["pfe_kw"], i0_percent=p["i0_percent"],
            index=s["trafo"])
        assert t == s["trafo"]
        sw_hv, sw_lv = s["switches"]
        pp.create_switch(net, s["mv_bus"], t, et="t", closed=True, index=sw_hv)
        pp.create_switch(net, b, t, et="t", closed=True, index=sw_lv)
        for e in s["elements"]:
            kind, i = e.split(".")
            getattr(net, kind).at[int(i), "bus"] = b
    net.switch.sort_index(inplace=True)
    net.trafo.sort_index(inplace=True)
    assert list(net.switch.index) == list(range(360)) and list(net.trafo.index) == list(range(58))
    return net


def build(snap, net=None):
    """Set a recorded physical snapshot (W, var; pu; degrees) on the reconstructed grid."""
    v = snap
    net = base_net() if net is None else net
    net.ext_grid.at[0, "vm_pu"] = v["bus.0.MEASUREMENT.voltage"]
    net.ext_grid.at[0, "va_degree"] = v["bus.0.MEASUREMENT.voltage_angle"]
    for kind in ("load", "sgen", "storage"):
        df = getattr(net, kind)
        df["p_mw"] = np.array([v[f"{kind}.{i}.MEASUREMENT.active_power"] for i in df.index]) / 1e6
        df["q_mvar"] = np.array([v[f"{kind}.{i}.MEASUREMENT.reactive_power"] for i in df.index]) / 1e6
        df["in_service"] = np.array([bool(v[f"{kind}.{i}.MEASUREMENT.is_connected"]) for i in df.index])
    net.switch["closed"] = np.array([bool(v[f"switch.{s}.MEASUREMENT.is_closed"]) for s in net.switch.index])
    net.trafo["tap_pos"] = np.array([float(v[f"trafo.{t}.MEASUREMENT.tap_position"]) for t in net.trafo.index])
    return net
