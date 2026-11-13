"""LinDistFlow for the radial configurations of the CIGRE MV grid.

Per radial topology (a spanning tree rooted at the external grid bus 0):
  P_b = sum of net active load in the subtree below branch b   (lossless)
  Q_b = same for reactive power
  v_child = v_parent - 2 (r_b P_b + x_b Q_b),   v = |V|^2,   v_0 = vm_ext_grid^2
Branches are lines and transformers, impedances in pu on sn_mva = 1 MVA and the bus
nominal voltage. Ignored: losses, line charging, transformer magnetising branch
(zero in this model), phase shift (no effect on magnitudes in a radial network).

Everything is affine in the envelope parameters x = (load scalings s, DER outputs g):
  v = v0 + Av @ x,  P_line = AP @ x,  Q_line = AQ @ x.
"""
from __future__ import annotations

from functools import lru_cache

import networkx as nx
import numpy as np

from . import envelope as E


class LinDistFlow:
    def __init__(self, cfg: E.Config):
        self.cfg = cfg
        net = E.apply_config(E.base_net(), cfg)
        base = E._base_net()
        self.sn = float(net.sn_mva)
        g = E.topology_graph(net)
        assert nx.is_tree(g)
        root = int(net.ext_grid.bus.iloc[0])
        self.v0 = float(net.ext_grid.vm_pu.iloc[0]) ** 2
        buses = list(net.bus.index)
        nb = len(buses)
        pos = {b: i for i, b in enumerate(buses)}
        parent, br_r, br_x, br_kind, br_idx = {}, {}, {}, {}, {}
        for p, c in nx.bfs_edges(g, root):
            e = g.edges[p, c]
            parent[c] = p
            if e["kind"] == "line":
                li = e["idx"]
                zb = net.bus.vn_kv.at[c] ** 2 / self.sn
                par = net.line.parallel.at[li]
                r = net.line.r_ohm_per_km.at[li] * net.line.length_km.at[li] / par / zb
                x = net.line.x_ohm_per_km.at[li] * net.line.length_km.at[li] / par / zb
            else:
                ti = e["idx"]
                ratio = self.sn / net.trafo.sn_mva.at[ti]
                zk = net.trafo.vk_percent.at[ti] / 100 * ratio
                r = net.trafo.vkr_percent.at[ti] / 100 * ratio
                x = np.sqrt(zk ** 2 - r ** 2)
            br_r[c], br_x[c], br_kind[c], br_idx[c] = r, x, e["kind"], e["idx"]
        children = [b for b in buses if b != root]
        # subtree indicator T[b_child, bus] and path indicator Path[bus, b_child]
        T = np.zeros((nb, nb))
        Path = np.zeros((nb, nb))
        for c in children:
            for d in nx.descendants(nx.bfs_tree(g, root), c) | {c}:
                T[pos[c], pos[d]] = 1.0
            b = c
            while b != root:
                Path[pos[c], pos[b]] = 1.0
                b = parent[b]
        r = np.array([br_r.get(b, 0.0) for b in buses])
        x = np.array([br_x.get(b, 0.0) for b in buses])
        nL, nG = E.dims().n_load, E.dims().n_der
        Lp = np.zeros((nb, nL)); Lq = np.zeros((nb, nL)); Gp = np.zeros((nb, nG))
        for i in base.load.index:
            Lp[pos[base.load.bus.at[i]], i] = base.load.p_mw.at[i] / self.sn
            Lq[pos[base.load.bus.at[i]], i] = base.load.q_mvar.at[i] / self.sn
        for j in base.sgen.index:
            Gp[pos[base.sgen.bus.at[j]], j] = base.sgen.sn_mva.at[j] / self.sn
        # net load injection (positive = consumption) as affine maps of x
        Pin = np.hstack([Lp, -Gp])
        Qin = np.hstack([Lq, np.zeros((nb, nG))])
        self.APb = T @ Pin          # P flowing into each child bus (row = child bus), pu
        self.AQb = T @ Qin
        self.Av = -2.0 * Path @ (r[:, None] * self.APb + x[:, None] * self.AQb)
        self.pos, self.buses = pos, buses
        # per line: P, Q at from end (sign per pandapower from/to), zero if not active
        nl = len(net.line)
        self.AP_line = np.zeros((nl, Pin.shape[1])); self.AQ_line = np.zeros((nl, Pin.shape[1]))
        self.line_active = np.zeros(nl, bool)
        for c in children:
            if br_kind[c] == "line":
                li = br_idx[c]
                sign = 1.0 if int(net.line.from_bus.at[li]) == parent[c] else -1.0
                self.AP_line[li] = sign * self.APb[pos[c]] * self.sn
                self.AQ_line[li] = sign * self.AQb[pos[c]] * self.sn
                self.line_active[li] = True
        self.AP_trafo = np.zeros((len(net.trafo), Pin.shape[1]))
        for c in children:
            if br_kind[c] == "trafo":
                self.AP_trafo[br_idx[c]] = self.APb[pos[c]] * self.sn
        vn = net.bus.vn_kv.values[[pos[int(b)] for b in net.line.from_bus]]
        self.smax_line = np.sqrt(3) * vn * (net.line.max_i_ka * net.line.df * net.line.parallel).values  # MVA at 1 pu

    def v(self, x):
        return self.v0 + self.Av @ x

    def vm(self, x):
        return np.sqrt(np.maximum(self.v(x), 0.0))

    def loading_percent(self, x):
        P, Q = self.AP_line @ x, self.AQ_line @ x
        return np.where(self.line_active, np.hypot(P, Q) / self.smax_line * 100, 0.0)


@lru_cache(maxsize=None)
def model(cfg: E.Config) -> LinDistFlow:
    return LinDistFlow(cfg)
