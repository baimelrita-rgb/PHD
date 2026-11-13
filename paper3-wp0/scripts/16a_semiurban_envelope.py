"""WP2-b step 1: benign envelope of the reconstructed 02-Semiurban grid, from train data.

Same principles as 01-Basic (scripts/10a):
  * load P: train min / max of P / nominal, widened by --load-margin;
  * controllable elements (sgen, storage): physical range (sgen [0, 1] of rated, storage
    [-1, 1] of nominal), because operators change setpoints;
  * load Q: fixed at nominal or following P, whichever the train data shows;
  * topologies: the 360-switch grid has far too many switching states to enumerate, so the
    envelope uses the distinct line-outage sets seen in train (data-driven), and the
    coverage of benign test records is measured.
Writes rules/semiurban_envelope.json and reports/semiurban_envelope_semiurban.md."""
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import envelope as E
from p3 import sherlock_io as S
from p3 import semiurban_model as SU


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--load-margin", type=float, default=0.01)
    ap.add_argument("--noise-tol", type=float, default=1e-3)
    ap.add_argument("--settle-s", type=float, default=60.0)
    ap.add_argument("--step", type=int, default=5)
    a = ap.parse_args()
    net = SU.base_net()
    root = S.ROOT_SEMI
    p_nom = np.abs(net.load.p_mw.values); q_nom = net.load.q_mvar.values
    g_nom = net.sgen.sn_mva.values; b_nom = np.abs(net.storage.p_mw.values)
    lsw = {}
    for s_ in net.switch.index:
        if net.switch.et.at[s_] == "l":
            lsw.setdefault(int(net.switch.element.at[s_]), []).append(int(s_))
    other_sw = [int(s_) for s_ in net.switch.index if net.switch.et.at[s_] != "l"]

    # unmonitored switches (no telemetry) never change state in the recording; their fixed state
    # is known network configuration (planning records), read once from the first train snapshot
    z0, idx0 = S.physical_index(root, "train")
    snap0 = S.read_snapshot(z0, idx0[0][1])["values"]
    fixed_sw = {s_: bool(snap0[f"switch.{s_}.MEASUREMENT.is_closed"]) for s_ in net.switch.index}

    def closed(state, s_):
        v = state.get(f"switch.{s_}:is_closed")
        return fixed_sw[s_] if v is None else bool(v)

    def topo(state):
        if any(not closed(state, s_) for s_ in other_sw):
            return None
        return tuple(sorted(l for l, ss in lsw.items() if any(not closed(state, s_) for s_ in ss)))

    nan = float("nan")

    def ratios(state):
        """Unmonitored elements (no telemetry at the control center) give NaN."""
        g = lambda k: state.get(k, nan)
        pl = np.array([g(f"load.{i}:active_power") for i in net.load.index]) / 1e6
        ql = np.array([g(f"load.{i}:reactive_power") for i in net.load.index]) / 1e6
        pg = np.array([g(f"sgen.{j}:active_power") for j in net.sgen.index]) / 1e6
        pb = np.array([g(f"storage.{k}:active_power") for k in net.storage.index]) / 1e6
        return pl / p_nom, ql / np.where(q_nom == 0, 1, q_nom), pg / g_nom, pb / np.where(b_nom == 0, 1, b_nom)

    lo = hi = None
    q_fixed_dev, q_pf_dev = 0.0, 0.0
    tcount = collections.Counter()
    first = None
    for i, rec in enumerate(S.iter_state(root, "train")):
        first = first or rec["state"]
        if i % a.step:
            continue
        rl, rq, rg, rb = ratios(rec["state"])
        lo = rl if lo is None else np.fmin(lo, rl)
        hi = rl if hi is None else np.fmax(hi, rl)
        q_fixed_dev = max(q_fixed_dev, float(np.nanmax(np.abs(rq - 1.0))))
        q_pf_dev = max(q_pf_dev, float(np.nanmax(np.abs(rq - rl))))
        tcount[topo(rec["state"])] += 1
    load_q = "fixed" if q_fixed_dev <= q_pf_dev else "pf"
    # unmonitored loads: bounds of the monitored loads with the same SimBench profile
    unmon = [i for i in range(len(lo)) if not np.isfinite(lo[i])]
    prof = net.load.profile.values
    for i in unmon:
        grp = [j for j in range(len(lo)) if prof[j] == prof[i] and np.isfinite(lo[j])]
        lo[i], hi[i] = min(lo[j] for j in grp), max(hi[j] for j in grp)
    topologies = [list(t) for t, _ in tcount.most_common() if t is not None]
    env = {"source": "scripts/16a_semiurban_envelope.py (train IPAL state)", "load_q": load_q,
           "load": [[float(lo[i]) - a.load_margin, float(hi[i]) + a.load_margin] for i in range(len(lo))],
           "sgen": [[0.0, 1.0] for _ in net.sgen.index],
           "storage": [[-1.0, 1.0] for _ in net.storage.index],
           "topologies": topologies,
           "observed_train": {"load_lo": lo.tolist(), "load_hi": hi.tolist()}}
    E.SEMI_ENV_PATH.write_text(json.dumps(env, indent=2))

    # coverage on benign test records
    ev = S.load_events(root, "test")
    att = [(e["start"] - a.settle_s, e.get("recovery", e["end"]) + a.settle_s) for e in ev if "benign" not in e["id"]]
    known = set(tuple(t) for t in topologies)
    n_ben = n_topo = n_cont = 0
    unseen = collections.Counter()
    blo = np.r_[[b[0] for b in env["load"]], [b[0] for b in env["sgen"]], [b[0] for b in env["storage"]]]
    bhi = np.r_[[b[1] for b in env["load"]], [b[1] for b in env["sgen"]], [b[1] for b in env["storage"]]]
    for i, rec in enumerate(S.iter_state(root, "test")):
        if i % a.step:
            continue
        t = rec["timestamp"]
        if any(s <= t <= e for s, e in att):
            continue
        n_ben += 1
        tp = topo(rec["state"])
        if tp in known:
            n_topo += 1
        else:
            unseen[tp] += 1
        rl, rq, rg, rb = ratios(rec["state"])
        r = np.r_[rl, rg, rb]
        ok = ~np.isfinite(r) | ((r >= blo - a.noise_tol) & (r <= bhi + a.noise_tol))   # unmonitored: not checkable
        n_cont += int(np.all(ok))
    free = int(np.sum(np.r_[hi - lo + 2 * a.load_margin, np.ones(len(net.sgen)), 2 * np.ones(len(net.storage))] > 1e-9))
    body = "# WP2-b: 02-Semiurban benign envelope from train data\n\n"
    body += C.md_table(["quantity", "value"], [
        ["continuous parameters (loads / sgen / storage)", f"{len(net.load)} / {len(net.sgen)} / {len(net.storage)}, {free} free"],
        ["unmonitored elements (no telemetry): loads / sgen / storage", f"{len(unmon)} / {int(sum(1 for j in net.sgen.index if f'sgen.{j}:active_power' not in first))} / {int(sum(1 for k in net.storage.index if f'storage.{k}:active_power' not in first))}"],
        ["unmonitored switches", f"{sum(1 for s_ in net.switch.index if f'switch.{s_}:is_closed' not in first)} (state fixed in the recording, taken from the first train ground-truth snapshot as known configuration)"],
        ["unmonitored load bounds", "taken from monitored loads with the same SimBench profile (train spread within a profile at most 0.0035 of nominal)"],
        ["load Q model chosen from data", f"{load_q} (max deviation: fixed {q_fixed_dev:.4f}, following P {q_pf_dev:.4f})"],
        ["topologies (distinct line-outage sets seen in train)", len(topologies)],
        ["train records sampled", f"every {a.step}th, {sum(tcount.values())} records"],
        [f"benign test records sampled (more than {a.settle_s:.0f} s from attacks)", n_ben],
        ["benign test records whose topology is in the envelope", f"{n_topo} ({n_topo / max(n_ben, 1):.3f})"],
        [f"benign test records with every monitored continuous parameter inside (tolerance {a.noise_tol})", f"{n_cont} ({n_cont / max(n_ben, 1):.3f})"],
        ["distinct test topologies not seen in train", len(unseen)],
    ])
    body += "\nTrain topologies (lines out of service, records):\n\n"
    body += C.md_table(["lines out", "train records"], [["outside: non-line switch open" if t is None else (", ".join(map(str, t)) or "none"), v] for t, v in tcount.most_common()])
    if unseen:
        body += "\nBenign test topologies outside the envelope (lines out, records):\n\n"
        body += C.md_table(["lines out", "benign test records"], [[("outside: non-line switch open" if t is None else ", ".join(map(str, t)) or "none"), v] for t, v in unseen.most_common(10)])
    C.write_report("semiurban_envelope_semiurban.md", body)
    print(f"load_q {load_q}; topologies {len(topologies)}; test benign topo coverage {n_topo}/{n_ben}; continuous {n_cont}/{n_ben}; unseen {len(unseen)}")


if __name__ == "__main__":
    main()
