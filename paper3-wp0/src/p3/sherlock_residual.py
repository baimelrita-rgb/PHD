"""Physics residual of SCADA telemetry on the reconstructed Sherlock grid.

The IPAL state (what the control center sees, vantage n302) reports injections
(loads, DER, storage), switch and tap states, AND network quantities (bus voltages,
line flows). Rebuild the grid from the injections, solve an AC power flow, and compare
the computed network quantities with the reported ones. Consistent telemetry gives a
residual at the measurement noise level; falsified or frozen telemetry need not.
"""
from __future__ import annotations

import numpy as np
import pandapower as pp

from . import fastpf as F
from . import sherlock_model as SM


def ipal_to_snapshot_keys(state: dict) -> dict:
    """'load.0:active_power' -> 'load.0.MEASUREMENT.active_power' (the snapshot naming used by sherlock_model)."""
    out = {}
    for k, v in state.items():
        elem, attr = k.split(":", 1)
        out[f"{elem}.MEASUREMENT.{attr}"] = v
    for t in (0, 1):  # tap positions are unsigned bytes in IPAL: 255 means -1
        key = f"trafo.{t}.MEASUREMENT.tap_position"
        if key in out and out[key] is not None and out[key] > 127:
            out[key] = out[key] - 256
    return out


class ResidualModel:
    def __init__(self, first_state: dict):
        self.trafo, self.tap = SM.load_params()
        v = ipal_to_snapshot_keys(first_state)
        self.net, _, _ = SM.build(v, self.trafo, self.tap)
        assert list(self.net.switch.index) == list(range(32))
        self._cache = {}

    def update(self, v: dict):
        net = self.net
        net.ext_grid["vm_pu"] = v["bus.0.MEASUREMENT.voltage"]
        net.ext_grid["va_degree"] = v["bus.0.MEASUREMENT.voltage_angle"]
        for kind, df in (("load", net.load), ("sgen", net.sgen), ("storage", net.storage)):
            n = len(df)
            df["p_mw"] = np.array([v[f"{kind}.{i}.MEASUREMENT.active_power"] for i in range(n)]) / 1e6
            df["q_mvar"] = np.array([v[f"{kind}.{i}.MEASUREMENT.reactive_power"] for i in range(n)]) / 1e6
            df["in_service"] = np.array([bool(v[f"{kind}.{i}.MEASUREMENT.is_connected"]) for i in range(n)])
        net.switch["closed"] = np.array([bool(v[f"switch.{s}.MEASUREMENT.is_closed"]) for s in range(len(net.switch))])
        if self.tap:
            net.trafo["tap_pos"] = np.array([int(v[f"trafo.{t}.MEASUREMENT.tap_position"]) for t in range(len(net.trafo))])

    def _solver(self):
        key = (tuple(self.net.switch.closed.values), tuple(self.net.trafo.tap_pos.values))
        if key not in self._cache:
            self._cache[key] = F.FastNet(self.net)
        return self._cache[key]

    def residual(self, state: dict, reference: bool = False):
        """Max abs residuals: bus voltage (pu), line P from end (MW), transformer P HV (MW).
        reference=True solves with pandapower runpp instead of the cached fast solver."""
        v = ipal_to_snapshot_keys(state)
        self.update(v)
        net = self.net
        if reference:
            try:
                pp.runpp(net)
            except pp.LoadflowNotConverged:
                return {"conv": False, "vm": np.nan, "p_line": np.nan, "p_trafo": np.nan}
            vm, pl, pt = net.res_bus.vm_pu.values, np.nan_to_num(net.res_line.p_from_mw.values), net.res_trafo.p_hv_mw.values
        else:
            fs = self._solver()
            inj = {k: (getattr(net, k).p_mw.values, getattr(net, k).q_mvar.values, getattr(net, k).in_service.values.astype(float))
                   for k in ("load", "sgen", "storage")}
            V = fs.solve(inj, float(net.ext_grid.vm_pu.iloc[0]), float(net.ext_grid.va_degree.iloc[0]))
            if V is None:
                return {"conv": False, "vm": np.nan, "p_line": np.nan, "p_trafo": np.nan}
            r = fs.results(V)
            vm, pl, pt = r["vm_pu"], r["line_p_from_mw"], r["trafo_p_hv_mw"]
        vm_rep = np.array([v[f"bus.{b}.MEASUREMENT.voltage"] for b in net.bus.index])
        p_rep = np.array([v[f"line.{l}.MEASUREMENT.active_power_from"] / 1e6 for l in net.line.index])
        t_rep = np.array([v[f"trafo.{t}.MEASUREMENT.active_power_hv"] / 1e6 for t in net.trafo.index])
        return {"conv": True,
                "vm": float(np.max(np.abs(vm - vm_rep))),
                "p_line": float(np.max(np.abs(pl - p_rep))),
                "p_trafo": float(np.max(np.abs(pt - t_rep)))}
