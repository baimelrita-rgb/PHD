"""WP4d: an additional, independent test day (semi-synthetic split day).

Sherlock has one test day per scenario. For 01-Basic (grid sherlock) and 02-Semiurban, the
recorded TRAIN day (attack free) is split at its midpoint:
  * first half  -> new train split (every calibration is redone on it: envelope, D1, SE-BDD,
                   ML detectors, library noise floors);
  * second half -> new test split, with attacks injected into the recorded telemetry.
Output: data/split/<grid>/ with {train,test}.<vantage>.state.gz, ipal/{train,test}/events.json
and a link to the original raw/ folder (ground-truth snapshots, used only for planning records
and for the physical effect of injected switching). Use with P3_VARIANT=split.

Attack models (modelled on the measured anatomy of the real attacks, reports/attack_anatomy.md;
all parameters drawn from a seeded generator and saved in events.json):
  drift-off           telemetry only: the voltage readings of 1 to 3 neighbouring buses ramp
                      linearly from 0 to D at the end of the window (D log-uniform in
                      [--drift-lo, --drift-hi] pu, random sign).
  control-and-freeze  every telemetry field of a small area (a bus and its neighbours, their
                      lines, switches and injections) is frozen at its value at the start; with
                      probability 0.5 a line inside the area is also opened physically, which
                      the operator cannot see in the frozen fields.
  industroyer         a physical change through valid commands: either one line opened at both
                      ends or 1 to 3 producing generators disconnected. Telemetry stays
                      physically consistent.
Physical changes are applied as a delta: for the ground-truth snapshot nearest in time (every
--delta-s seconds) the AC power flow of the reconstructed grid is solved with and without the
change; the difference is added to every reported network field (voltages, angles, line and
transformer flows and currents, loading, external grid, bus injections), so the recorded noise
and model mismatch are kept. Switch and connection flags are set directly."""
import gzip
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandapower as pp

from p3 import common as C
from p3 import sherlock_io as S

VANTAGE = {"sherlock": "n302", "semiurban": "n406"}
ORIG = {"sherlock": S.ROOT_DEFAULT, "semiurban": S.ROOT_SEMI}
DUR = {"drift-off": (480, 630), "control-and-freeze": (360, 690), "industroyer": (170, 310)}
DESC = {"drift-off": "drift-off:drift-off", "control-and-freeze": "control-and-freeze:control-and-freeze",
        "industroyer": "industroyer:industroyer"}


def lines(path):
    p = subprocess.Popen(["zcat", str(path)], stdout=subprocess.PIPE, bufsize=1 << 20)
    for ln in p.stdout:
        yield ln
    p.wait()


def ts_of(ln: bytes) -> float:
    i = ln.index(b'"timestamp":') + 12
    j = ln.index(b",", i)
    return float(ln[i:j])


class Grid:
    """Reconstructed grid built from a ground-truth snapshot; AC power flow with and without a change."""

    def __init__(self, grid):
        self.grid = grid
        self.z, self.idx = S.physical_index(ORIG[grid], "train")
        self.t = np.array([a for a, _ in self.idx])
        if grid == "semiurban":
            from p3 import semiurban_model as SU
            self.su = SU
            self.net = SU.base_net("semiurban")
        else:
            from p3 import sherlock_model as SM
            self.sm = SM
            self.trafo, self.tap = SM.load_params()
        self._snap = {}

    def snapshot(self, t):
        k = int(np.clip(np.searchsorted(self.t, t), 0, len(self.t) - 1))
        if k not in self._snap:
            self._snap = {k: S.read_snapshot(self.z, self.idx[k][1])["values"]}
        return self._snap[k]

    def build(self, v):
        if self.grid == "semiurban":
            return self.su.build(v, self.net, "semiurban")
        net, _, _ = self.sm.build(v, self.trafo, self.tap)
        return net

    def line_switches(self, net):
        out = {}
        for s, et, el in zip(net.switch.index, net.switch.et.values, net.switch.element.values):
            if et == "l":
                out.setdefault(int(el), []).append(int(s))
        return out

    @staticmethod
    def fields(net):
        nz = lambda a: np.nan_to_num(np.asarray(a, float))
        f = {}
        for b, vm, va, p, q in zip(net.bus.index, nz(net.res_bus.vm_pu), nz(net.res_bus.va_degree), nz(net.res_bus.p_mw), nz(net.res_bus.q_mvar)):
            f[f"bus.{b}:voltage"] = vm; f[f"bus.{b}:voltage_angle"] = va
            f[f"bus.{b}:active_power"] = p * 1e6; f[f"bus.{b}:reactive_power"] = q * 1e6
        rl = net.res_line
        for j, l in enumerate(net.line.index):
            for key, col, sc in (("active_power_from", "p_from_mw", 1e6), ("reactive_power_from", "q_from_mvar", 1e6),
                                 ("active_power_to", "p_to_mw", 1e6), ("reactive_power_to", "q_to_mvar", 1e6),
                                 ("current_from", "i_from_ka", 1e3), ("current_to", "i_to_ka", 1e3),
                                 ("voltage_from", "vm_from_pu", 1.0), ("voltage_to", "vm_to_pu", 1.0)):
                f[f"line.{l}:{key}"] = float(np.nan_to_num(rl[col].values[j])) * sc
        rt = net.res_trafo
        for j, t in enumerate(net.trafo.index):
            for key, col, sc in (("active_power_hv", "p_hv_mw", 1e6), ("reactive_power_hv", "q_hv_mvar", 1e6),
                                 ("active_power_lv", "p_lv_mw", 1e6), ("reactive_power_lv", "q_lv_mvar", 1e6),
                                 ("current_hv", "i_hv_ka", 1e3), ("current_lv", "i_lv_ka", 1e3),
                                 ("loading", "loading_percent", 1.0), ("voltage_hv", "vm_hv_pu", 1.0), ("voltage_lv", "vm_lv_pu", 1.0)):
                f[f"trafo.{t}:{key}"] = float(np.nan_to_num(rt[col].values[j])) * sc
        f["external_grid.0:active_power"] = float(net.res_ext_grid.p_mw.values[0]) * 1e6
        f["external_grid.0:reactive_power"] = float(net.res_ext_grid.q_mvar.values[0]) * 1e6
        return f

    def delta(self, t, change):
        """Field-wise (with change) minus (without), for the snapshot nearest to t; None if a flow fails."""
        v = self.snapshot(t)
        net = self.build(v)
        try:
            pp.runpp(net)
            f0 = self.fields(net)
            if change["kind"] == "line":
                net.switch.loc[change["switches"], "closed"] = False
            else:
                net.sgen.loc[change["sgens"], "in_service"] = False
            pp.runpp(net)
            f1 = self.fields(net)
        except Exception:
            return None
        return {k: f1[k] - f0[k] for k in f0}


def neighbourhood(net, b, rng, kmax):
    nb = {b}
    adj = {}
    for fb, tb in zip(net.line.from_bus.values, net.line.to_bus.values):
        adj.setdefault(int(fb), set()).add(int(tb)); adj.setdefault(int(tb), set()).add(int(fb))
    cand = sorted(adj.get(b, ()))
    rng.shuffle(cand)
    nb |= set(cand[: kmax - 1])
    return sorted(nb), adj


def area(net, b, size, rng):
    """Buses reached from b through lines, transformers and bus couplers (breadth first, random order), up to size."""
    adj = {}
    edges = list(zip(net.line.from_bus.values, net.line.to_bus.values)) + list(zip(net.trafo.hv_bus.values, net.trafo.lv_bus.values))
    edges += [(bb, el) for bb, et, el in zip(net.switch.bus.values, net.switch.et.values, net.switch.element.values) if et == "b"]
    for x, y in edges:
        adj.setdefault(int(x), set()).add(int(y)); adj.setdefault(int(y), set()).add(int(x))
    seen, front = [b], [b]
    while front and len(seen) < size:
        nxt = []
        for x in front:
            nb = sorted(adj.get(x, ()) - set(seen))
            rng.shuffle(nb)
            for y in nb:
                if len(seen) < size and y not in seen:
                    seen.append(y); nxt.append(y)
        front = nxt
    return sorted(seen)


def plan(grid, G, first_state, t0, t1, benign, rng, a):
    """Schedule attacks in [t0, t1] away from benign procedures; draw their parameters."""
    net = G.build(G.snapshot(t0))
    lsw = G.line_switches(net)
    monitored_sw = {int(k.split(".")[1].split(":")[0]) for k in first_state if k.startswith("switch.") and k.endswith(":is_closed")}
    obs_bus = sorted(int(k.split(".")[1].split(":")[0]) for k in first_state if k.startswith("bus.") and k.endswith(":voltage"))
    cand_lines = [l for l, ss in sorted(lsw.items()) if len(ss) >= 1 and all(s in monitored_sw for s in ss)
                  and bool(net.line.in_service.at[l]) and all(net.switch.closed.at[s] for s in ss)]
    events, t, k, order = [], t0 + a.gap_lo, 0, []
    while True:
        if not order:
            order = list(rng.permutation(list(DUR)))
        typ = order[0]
        dur = float(rng.uniform(*DUR[typ]))
        if t + dur > t1:
            break
        if any(t - 300 <= be["end"] and t + dur + 300 >= be["start"] for be in benign):
            t += 60.0
            continue
        order.pop(0)
        e = {"id": str(k), "description": DESC[typ], "start": t, "end": t + dur, "recovery": t + dur, "params": {}}
        if typ == "drift-off":
            b = int(rng.choice([x for x in obs_bus if x != 0]))
            if a.attack_model == "v1":
                buses, adj = neighbourhood(net, b, rng, int(rng.integers(1, 4)))
                D = float(np.exp(rng.uniform(np.log(a.drift_lo), np.log(a.drift_hi)))) * float(rng.choice([-1, 1]))
            else:   # v2: magnitude and bus count of a measured real drift-off instance of this grid (scripts/22a), magnitude +-20 %
                real = json.loads((C.ROOT / "rules" / "drift_magnitudes.json").read_text())[grid]
                k_inst = int(rng.integers(len(real["max_signed_offset_pu"])))
                D = float(real["max_signed_offset_pu"][k_inst]) * float(rng.uniform(0.8, 1.2))
                buses = area(net, b, max(1, int(real["buses_above_0.005"][k_inst])), rng)
            buses = [x for x in buses if x in obs_bus and x != 0] or [b]
            e["params"] = {"buses": buses, "final_offset_pu": D}
            e["attack_point"] = [f"bus.{x}:voltage" for x in buses]
        elif typ == "control-and-freeze":
            b = int(rng.choice([x for x in obs_bus if x != 0]))
            if a.attack_model == "v1":
                buses, adj = neighbourhood(net, b, rng, 3)
            else:
                buses = [x for x in area(net, b, a.fb_eff, rng) if x != 0]
            area_lines = [l for l in net.line.index if int(net.line.from_bus.at[l]) in buses and int(net.line.to_bus.at[l]) in buses]
            phys = None
            if a.attack_model == "v1":
                inside, p_phys = [l for l in area_lines if l in cand_lines], 0.5
            else:   # v2: a line touching the frozen area, as in the real attacks (3 of 5 opened switches while frozen)
                inside = [l for l in cand_lines if int(net.line.from_bus.at[l]) in buses or int(net.line.to_bus.at[l]) in buses]
                area_lines = sorted(set(area_lines) | set(inside))
                p_phys = 0.6
            if inside and rng.random() < p_phys:
                l = int(rng.choice(inside))
                phys = {"kind": "line", "line": l, "switches": lsw[l]}
            e["params"] = {"buses": buses, "lines": [int(x) for x in area_lines], "physical": phys}
            e["attack_point"] = [] if phys is None else [f"switch.{s}:closed" for s in phys["switches"]]
        else:
            v = G.snapshot(t)
            prod = [i for i in net.sgen.index if v[f"sgen.{i}.MEASUREMENT.is_connected"] and v[f"sgen.{i}.MEASUREMENT.active_power"] > 1e3
                    and f"sgen.{i}:is_connected" in first_state]
            if prod and rng.random() < 0.4:
                n = int(min(len(prod), rng.integers(1, 4)))
                sg = [int(x) for x in rng.choice(prod, n, replace=False)]
                phys = {"kind": "sgen", "sgens": sg}
                e["attack_point"] = [f"sgen.{i}:connected" for i in sg]
            else:
                l = int(rng.choice(cand_lines))
                phys = {"kind": "line", "line": l, "switches": lsw[l]}
                e["attack_point"] = [f"switch.{s}:closed" for s in lsw[l]]
            e["params"] = {"physical": phys}
        events.append(e)
        k += 1
        t += dur + float(rng.uniform(a.gap_lo, a.gap_hi))
    return events, net


def inject(st, ts, e, G, cache, a, frozen_ref):
    p = e["params"]
    typ = e["description"].split(":")[0]
    if typ == "drift-off":
        frac = (ts - e["start"]) / (e["end"] - e["start"])
        for b in p["buses"]:
            st[f"bus.{b}:voltage"] = st[f"bus.{b}:voltage"] + p["final_offset_pu"] * frac
        return
    phys = p.get("physical")
    if typ == "control-and-freeze" and e["id"] not in frozen_ref:     # frozen at the pre-attack values
        frozen_ref[e["id"]] = {k: v for k, v in st.items() if frozen_key(k, p)}
    if phys is not None:
        slot = int((ts - e["start"]) // a.delta_s)
        key = (e["id"], slot)
        if key not in cache:
            cache[key] = G.delta(e["start"] + slot * a.delta_s, phys)
        d = cache[key]
        if d is not None:
            for k, dv in d.items():
                if k in st and st[k] is not None:
                    st[k] = st[k] + dv
        if phys["kind"] == "line":
            for s in phys["switches"]:
                for f in ("closed", "is_closed"):
                    if f"switch.{s}:{f}" in st:
                        st[f"switch.{s}:{f}"] = False
        else:
            for i in phys["sgens"]:
                for f in ("connected", "is_connected"):
                    if f"sgen.{i}:{f}" in st:
                        st[f"sgen.{i}:{f}"] = False
                for f in ("active_power", "reactive_power"):
                    if f"sgen.{i}:{f}" in st:
                        st[f"sgen.{i}:{f}"] = 0.0
    if typ == "control-and-freeze":
        for k, v in frozen_ref[e["id"]].items():
            st[k] = v


def frozen_key(k, p):
    elem = k.split(":")[0]
    kind, _, i = elem.partition(".")
    if not i.isdigit():
        return False
    i = int(i)
    if kind == "bus":
        return i in p["buses"]
    if kind == "line":
        return i in p["lines"]
    if kind == "switch":
        return i in p.get("_sw", ())
    if kind in ("load", "sgen", "storage"):
        return i in p.get(f"_{kind}", ())
    return False


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--grids", default="sherlock,semiurban")
    ap.add_argument("--delta-s", type=float, default=10.0)
    ap.add_argument("--drift-lo", type=float, default=0.005)
    ap.add_argument("--drift-hi", type=float, default=0.05)
    ap.add_argument("--attack-model", default="v2", choices=["v1", "v2"],
                    help="v1: guessed drift range, 3-bus freeze; v2: drift magnitudes measured on the real attacks, larger frozen area")
    ap.add_argument("--freeze-buses", type=int, default=0, help="v2 frozen-area size (0: 3 on 01-Basic, 10 on 02-Semiurban)")
    ap.add_argument("--gap-lo", type=float, default=240.0)
    ap.add_argument("--gap-hi", type=float, default=480.0)
    a = ap.parse_args()
    rows = []
    for grid in a.grids.split(","):
        t_start = time.time()
        rng = np.random.default_rng(a.seed + (0 if grid == "sherlock" else 100))
        a.fb_eff = a.freeze_buses or (3 if grid == "sherlock" else 10)
        src, v = ORIG[grid], VANTAGE[grid]
        out = S.SPLIT_DIR / grid
        for sp in ("train", "test"):
            (out / "ipal" / sp).mkdir(parents=True, exist_ok=True)
        if not (out / "raw").exists():
            os.symlink(src / "raw", out / "raw")
        G = Grid(grid)
        first = json.loads(next(lines(src / f"train.{v}.state.gz")))
        tA, tZ = G.t[0], G.t[-1]
        mid = 0.5 * (tA + tZ)
        bev = S.load_events(src, "train")
        ev_tr = [e for e in bev if e["start"] < mid]
        ben_te = [e for e in bev if e["start"] >= mid]
        events, net = plan(grid, G, first["state"], mid + 600.0, tZ - 300.0, ben_te, rng, a)
        # element sets of each frozen area
        for e in events:
            p = e["params"]
            if "lines" in p:
                p["_sw"] = [int(s) for s, et, el in zip(net.switch.index, net.switch.et.values, net.switch.element.values)
                            if (et == "l" and int(el) in p["lines"]) or (et == "b" and int(net.switch.bus.at[s]) in p["buses"])]
                for kind in ("load", "sgen", "storage"):
                    df = getattr(net, kind)
                    p[f"_{kind}"] = [int(i) for i in df.index if int(df.bus.at[i]) in p["buses"]]
        (out / "ipal" / "train" / "events.json").write_text(json.dumps(ev_tr, indent=1))
        (out / "ipal" / "test" / "events.json").write_text(json.dumps(events + ben_te, indent=1))
        cache, frozen, n_tr, n_te, n_inj = {}, {}, 0, 0, 0
        win = sorted(events, key=lambda e: e["start"])
        with gzip.open(out / f"train.{v}.state.gz", "wb", compresslevel=1) as ftr, \
                gzip.open(out / f"test.{v}.state.gz", "wb", compresslevel=1) as fte:
            j = 0
            for ln in lines(src / f"train.{v}.state.gz"):
                ts = ts_of(ln)
                if ts < mid:
                    ftr.write(ln); n_tr += 1
                    continue
                n_te += 1
                while j < len(win) and ts > win[j]["end"]:
                    j += 1
                if j < len(win) and win[j]["start"] <= ts <= win[j]["end"]:
                    rec = json.loads(ln)
                    inject(rec["state"], ts, win[j], G, cache, a, frozen)
                    rec["malicious"] = True
                    fte.write((json.dumps(rec, separators=(",", ":")) + "\n").encode())
                    n_inj += 1
                else:
                    fte.write(ln)
        fails = sum(1 for d in cache.values() if d is None)
        by = {}
        for e in events:
            by[e["description"]] = by.get(e["description"], 0) + 1
        mx = {}
        for (eid, _), d in cache.items():
            if d:
                mx[eid] = max(mx.get(eid, 0.0), max(abs(d[k]) for k in d if k.endswith(":voltage")))
        for e in events:
            e["params"]["max_abs_dv_pu"] = mx.get(e["id"])
        (out / "ipal" / "test" / "events.json").write_text(json.dumps(events + ben_te, indent=1))
        wall = time.time() - t_start
        print(grid, a.attack_model, f"mid {mid:.0f} train {n_tr} test {n_te} injected {n_inj} attacks {by} flow failures {fails}/{len(cache)} {wall:.0f}s")
        rows.append([grid, f"{(mid - tA) / 3600:.2f} h / {(tZ - mid) / 3600:.2f} h", n_tr, n_te, n_inj,
                     ", ".join(f"{k.split(':')[0]} {n}" for k, n in sorted(by.items())), len(ben_te), f"{fails} / {len(cache)}", f"{wall:.0f}"])
        erow = []
        for e in events:
            p = e["params"]
            typ = e["description"].split(":")[0]
            if typ == "drift-off":
                det = f"buses {p['buses']}, final offset {p['final_offset_pu']:+.4f} pu"
            elif typ == "control-and-freeze":
                ph = p["physical"]
                det = f"frozen buses {p['buses']}" + (f", line {ph['line']} opened" if ph else ", no physical change")
            else:
                ph = p["physical"]
                det = f"line {ph['line']} opened" if ph["kind"] == "line" else f"sgens {ph['sgens']} disconnected"
            dv = p.get("max_abs_dv_pu")
            erow.append([e["id"], typ, f"{e['end'] - e['start']:.0f}", det, "⟨·⟩" if dv is None else f"{dv:.4f}"])
        C.GRID = grid
        C.write_report("split_day_events.md", f"# WP4d: injected attacks on the {grid} split day\n\n"
                       "Parameters drawn by `scripts/22_split_day.py` (seeded). Last column: largest true bus-voltage change "
                       "caused by the physical action (power-flow delta), where there is one.\n\n"
                       + C.md_table(["id", "type", "duration s", "parameters", "max physical dV pu"], erow))
        C.GRID = C.DEFAULT_GRID
    body = "# WP4d: semi-synthetic split day\n\n" + (__doc__.split("\n\n", 1)[1]) + "\n\n"
    body += C.md_table(["grid", "first half / second half", "train records", "test records", "records with injection",
                        "attacks", "benign procedures in test half", "power-flow failures (delta slots)", "wall s"], rows)
    C.write_report("split_day.md", body)


if __name__ == "__main__":
    main()
