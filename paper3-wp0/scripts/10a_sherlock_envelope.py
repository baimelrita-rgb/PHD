"""WP1-b step 1: benign envelope of the Sherlock grid derived from train data.

Continuous bounds: per element, the min and max over all train records (IPAL state,
1 Hz) of load P / nominal P, sgen P / rated, storage P / nominal. Load Q is constant at
nominal in the recording and stays fixed. Taps: positions seen in train. Topologies:
radial configurations with up to two lines out (enumerated by envelope.py).
Coverage is then measured on train and on the benign test records."""
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import networkx as nx
import numpy as np

from p3 import common as C
from p3 import envelope as E
from p3 import sherlock_io as S
from p3 import sherlock_model as SM


def record_config(state, net, cache):
    key_sw = tuple(bool(state[f"switch.{s}:is_closed"]) for s in range(32))
    taps = tuple(int(state[f"trafo.{t}:tap_position"]) - (256 if state[f"trafo.{t}:tap_position"] > 127 else 0) for t in range(2))
    if key_sw not in cache:
        net.switch["closed"] = np.array(key_sw)
        net.line["in_service"] = True
        g = E.topology_graph(net)
        cache[key_sw] = (frozenset(E.active_lines(net)), nx.is_tree(g), nx.is_connected(g))
    return cache[key_sw], taps


def ratios(state, net):
    pl = np.array([state[f"load.{i}:active_power"] for i in range(len(net.load))]) / 1e6 / net.load.p_mw.values
    pg = np.array([state[f"sgen.{j}:active_power"] for j in range(len(net.sgen))]) / 1e6 / net.sgen.sn_mva.values
    pb = np.array([state[f"storage.{k}:active_power"] for k in range(len(net.storage))]) / 1e6 / net.storage.p_mw.values
    return pl, pg, pb


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--settle-s", type=float, default=60.0)
    ap.add_argument("--noise-tol", type=float, default=1e-3, help="coverage check tolerance (measurement noise on P ratios)")
    ap.add_argument("--load-margin", type=float, default=0.01, help="absolute margin on observed load scaling")
    a = ap.parse_args()
    net = SM.base_net()
    root = S.ROOT_DEFAULT
    lo = hi = None
    taps_seen, train_cfg, cache = collections.Counter(), collections.Counter(), {}
    for rec in S.iter_state(root, "train"):
        r = np.concatenate(ratios(rec["state"], net))
        lo = r if lo is None else np.minimum(lo, r)
        hi = r if hi is None else np.maximum(hi, r)
        (key, tree, conn), taps = record_config(rec["state"], net, cache)
        taps_seen[taps] += 1
        train_cfg[(key, tree, taps)] += 1
    nL, nG = len(net.load), len(net.sgen)
    env = {"source": "train IPAL state min/max per element (scripts/10a_sherlock_envelope.py)",
           "load": [[float(lo[i]) - a.load_margin, float(hi[i]) + a.load_margin] for i in range(nL)],
           # controllable elements: full physical range (operators change setpoints)
           "sgen": [[0.0, 1.0] for j in range(nG)],
           "storage": [[-1.0, 1.0] for k in range(len(net.storage))],
           "observed_train": {"lo": lo.tolist(), "hi": hi.tolist()},
           "taps": sorted([list(t) for t in taps_seen])}
    E.SHERLOCK_ENV_PATH.write_text(json.dumps(env, indent=2))
    C.init(type("A", (), {"grid": "sherlock"})())
    cfgs = E.enumerate_configs()
    known = {(frozenset(E.active_lines(E.apply_config(E.base_net(), c))), c.taps) for c in cfgs}

    radial_known = {(frozenset(E.active_lines(E.apply_config(E.base_net(), c))), c.taps) for c in cfgs if E.is_radial(c)}

    def cov(counter):
        tot = sum(counter.values())
        inside = sum(v for (k, tree, t), v in counter.items() if (k, t) in known)
        meshed = sum(v for (k, tree, t), v in counter.items() if not tree)
        in_radial = sum(v for (k, tree, t), v in counter.items() if (k, t) in radial_known)
        return tot, inside, meshed, in_radial

    # benign test records: topology and continuous coverage
    ev = S.load_events(root, "test")
    att = [(e["start"] - a.settle_s, e.get("recovery", e["end"]) + a.settle_s) for e in ev if "benign" not in e["id"]]
    test_cfg, n_ben, outside = collections.Counter(), 0, np.zeros(len(lo), int)
    worst = np.zeros(len(lo))
    blo = np.array([b[0] for b in env["load"] + env["sgen"] + env["storage"]])
    bhi = np.array([b[1] for b in env["load"] + env["sgen"] + env["storage"]])
    n_all_inside = 0
    for rec in S.iter_state(root, "test"):
        t = rec["timestamp"]
        if any(s <= t <= e for s, e in att):
            continue
        n_ben += 1
        r = np.concatenate(ratios(rec["state"], net))
        o = (r < blo - a.noise_tol) | (r > bhi + a.noise_tol)
        outside += o
        n_all_inside += int(not o.any())
        worst = np.maximum(worst, np.maximum(blo - r, r - bhi))
        (key, tree, conn), taps = record_config(rec["state"], net, cache)
        test_cfg[(key, tree, taps)] += 1
    tr, te = cov(train_cfg), cov(test_cfg)
    names = [f"load.{i}" for i in range(nL)] + [f"sgen.{j}" for j in range(nG)] + [f"storage.{k}" for k in range(len(net.storage))]
    body = "# WP1-b: Sherlock benign envelope from train data\n\n"
    body += (f"Load bounds = min and max of P / nominal over all train records, widened by {a.load_margin}. "
             "Controllable elements get their physical range: sgen P in [0, 1] of rated, storage P in [-1, 1] of nominal "
             "(operators change setpoints; test contains benign setpoint changes not seen in train). Load Q fixed at nominal "
             "(constant in the recording). Taps: positions seen in train. Topologies: connected with at most one closed loop, "
             "up to two lines out (Sherlock runs meshed after maintenance). Saved to `rules/sherlock_envelope.json`.\n\n")
    body += C.md_table(["quantity", "value"], [
        ["continuous parameters (free / fixed)", f"{int((hi > lo).sum())} / {int((hi <= lo).sum())}"],
        ["tap positions seen in train (trafo 0, trafo 1)", ", ".join(str(t) for t in sorted(taps_seen))],
        ["discrete configurations (topologies x taps): all / radial", f"{len(cfgs)} / {sum(E.is_radial(c) for c in cfgs)}"],
        ["train records: total / topology inside / meshed / inside the radial part", f"{tr[0]} / {tr[1]} / {tr[2]} / {tr[3]}"],
        [f"benign test records (more than {a.settle_s:.0f} s from attacks): total / topology inside / meshed / radial part", f"{te[0]} / {te[1]} / {te[2]} / {te[3]}"],
        [f"benign test records with every continuous parameter inside the envelope (tolerance {a.noise_tol} for measurement noise)", f"{n_all_inside} / {n_ben}"],
    ])
    body += "\nPer-element bounds and test coverage:\n\n"
    body += C.md_table(["element", "lo", "hi", "benign test records outside", "max excursion"],
                       [[n, f"{lo[i]:.4f}", f"{hi[i]:.4f}", int(outside[i]), f"{worst[i]:.4f}"] for i, n in enumerate(names)])
    C.write_report("sherlock_envelope.md", body)
    print(f"configs {len(cfgs)} (radial {sum(E.is_radial(c) for c in cfgs)}); train topo inside {tr[1]}/{tr[0]}; "
          f"test benign topo inside {te[1]}/{te[0]} (radial part {te[3]}); continuous inside {n_all_inside}/{n_ben}")


if __name__ == "__main__":
    main()
