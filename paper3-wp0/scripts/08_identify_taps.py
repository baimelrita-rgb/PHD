"""Identify Sherlock's transformer parameters and tap changer from recorded data.

1. Transformer impedance and iron losses: least squares on recorded losses (tap 0
   snapshots), as in T7.
2. Tap changer side and step size: grid search on snapshots where the recorded tap
   position is nonzero; fit on one half, validate on the other half. The error is
   the bus voltage error of a full AC power flow.
3. Tap range: only the positions seen in the data are known (lower bound on the real range).
Writes rules/sherlock_grid_params.json and reports/sherlock_taps.md."""
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandapower as pp

from p3 import common as C
from p3 import sherlock_io as S
from p3 import sherlock_model as SM


def vm_err(snap, tp, tap):
    net, _, _ = SM.build(snap, tp, tap)
    pp.runpp(net)
    rec = np.array([snap[f"bus.{b}.MEASUREMENT.voltage"] for b in net.bus.index])
    return np.abs(net.res_bus.vm_pu.values - rec)


class Cached:
    """One network per snapshot; candidate tap parameters only change trafo columns."""
    def __init__(self, snaps, tp, lo, hi):
        self.items = []
        for s in snaps:
            net, _, _ = SM.build(s, tp, {"side": "hv", "step_percent": 1.0, "neutral": 0, "min": lo, "max": hi})
            rec = np.array([s[f"bus.{b}.MEASUREMENT.voltage"] for b in net.bus.index])
            self.items.append((net, rec))

    def score(self, side, step):
        e = []
        for net, rec in self.items:
            net.trafo["tap_side"] = side
            net.trafo["tap_step_percent"] = float(step)
            pp.runpp(net, init="results" if net.get("converged", False) else "auto")
            e.append(np.abs(net.res_bus.vm_pu.values - rec).mean())
        return float(np.mean(e))


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--n-tap", type=int, default=40, help="tap != 0 snapshots (half fit, half validation)")
    ap.add_argument("--n-fit-trafo", type=int, default=300)
    ap.add_argument("--root", default=str(S.ROOT_DEFAULT))
    a = ap.parse_args()
    root = Path(a.root)
    z, idx = S.physical_index(root, "train")
    rng = np.random.default_rng(a.seed + 500)
    order = rng.permutation(len(idx))
    tap_snaps, zero_members, seen = [], [], set()
    for k in order:
        v = S.read_snapshot(z, idx[k][1])["values"]
        tp_pos = (v["trafo.0.MEASUREMENT.tap_position"], v["trafo.1.MEASUREMENT.tap_position"])
        seen.add(tp_pos)
        if tp_pos != (0, 0) and len(tap_snaps) < a.n_tap:
            tap_snaps.append(v)
        elif tp_pos == (0, 0) and len(zero_members) < a.n_fit_trafo:
            zero_members.append(idx[k][1])
        if len(tap_snaps) >= a.n_tap and len(zero_members) >= a.n_fit_trafo:
            break
    tp = SM.fit_trafo(z, zero_members)
    fit, val = tap_snaps[: a.n_tap // 2], tap_snaps[a.n_tap // 2:]
    # positions over the whole recording (IPAL state, 1 Hz); 255 is -1 stored as unsigned byte
    pos_all = set()
    for split in ("train", "test"):
        with gzip.open(root / f"{split}.n302.state.gz", "rt") as f:
            for line in f:
                s = json.loads(line)["state"]
                for t in (0, 1):
                    p = s.get(f"trafo.{t}:tap_position")
                    pos_all.add((split, t, p - 256 if p is not None and p > 127 else p))
    lo = min(p for _, _, p in pos_all if p is not None)
    hi = max(p for _, _, p in pos_all if p is not None)

    cache = Cached(fit, tp, lo, hi)

    def score(side, step, snaps):
        return cache.score(side, step)

    rows = []
    best = (np.inf, None, None)
    for side in ("hv", "lv"):
        for step in np.arange(0.5, 5.01, 0.5):
            e = score(side, step, fit)
            rows.append((side, step, e))
            if e < best[0]:
                best = (e, side, step)
    _, side, step0 = best
    for step in np.arange(step0 - 0.45, step0 + 0.451, 0.05):
        e = score(side, step, fit)
        if e < best[0]:
            best = (e, side, float(step))
    e_fit, side, step = best
    tap = {"side": side, "step_percent": round(step, 3), "neutral": 0, "min": lo, "max": hi}
    ev_val = np.concatenate([vm_err(s, tp, tap) for s in val])
    ev_none = np.concatenate([vm_err(s, tp, None) for s in val])   # ignoring the tap
    SM.PARAMS_PATH.write_text(json.dumps({
        "source": "identified from Sherlock 01-Basic train ground truth by scripts/07 and scripts/08",
        "trafo": {str(k): {kk: float(vv) for kk, vv in v.items()} for k, v in tp.items()},
        "tap": tap}, indent=2))
    best_other = min(e for s_, st, e in rows if s_ != side)
    body = "# Sherlock transformer tap changer, identified from data\n\n"
    body += C.md_table(["quantity", "value"], [
        ["tap positions seen in the IPAL state (train and test, 1 Hz), after mapping 255 to -1", ", ".join(sorted({f"T{t}={p}" for _, t, p in pos_all if p is not None}))],
        ["position range used (seen, a lower bound on the real range)", f"[{lo}, {hi}]"],
        ["tap != 0 snapshots: fit / validation", f"{len(fit)} / {len(val)} (train ground truth, seed {a.seed + 500})"],
        ["identified tap side", side],
        ["identified step, % per position", f"{step:.3f}"],
        ["fit mean abs bus voltage error at the optimum, pu", f"{e_fit:.2e}"],
        ["best fit mean error with the other side, pu", f"{best_other:.2e}"],
        ["validation: bus voltage mean / max abs error, pu (identified tap)", f"{ev_val.mean():.2e} / {ev_val.max():.2e}"],
        ["validation: bus voltage mean / max abs error, pu (tap ignored)", f"{ev_none.mean():.2e} / {ev_none.max():.2e}"],
    ])
    body += "\nCoarse grid (fit set, mean abs bus voltage error):\n\n"
    body += C.md_table(["side", "step %", "mean abs err pu"], [[s_, f"{st:.2f}", f"{e:.2e}"] for s_, st, e in rows])
    body += ("\nUnknown: the real tap range beyond the positions used in the recording (⟨·⟩), and whether the tap "
             "changer has a dead band or a controller. Parameters are saved to `rules/sherlock_grid_params.json`.\n")
    C.write_report("sherlock_taps.md", body)
    print(f"tap side {side} step {step:.3f}%  val mean {ev_val.mean():.2e} max {ev_val.max():.2e}  (ignored: {ev_none.mean():.2e})")


if __name__ == "__main__":
    main()
