"""WP1-a: are Sherlock's attacks visible in the physics?

For every k-th record of the IPAL state (vantage n302, 1 Hz) the reconstructed grid is
solved from the reported injections and states; the residual against the reported bus
voltages and line/transformer flows is recorded. Thresholds are calibrated on train
(no attacks) as safety x the max train residual. Reported: false alarms on benign test
records and detection per attack instance and type."""
import collections
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import sherlock_io as S
from p3 import sherlock_residual as SR

METRICS = ("vm", "p_line", "p_trafo")
UNITS = {"vm": "pu", "p_line": "MW", "p_trafo": "MW"}


def run(root, split, step):
    model, out = None, []
    for i, rec in enumerate(S.iter_state(root, split)):
        if i % step:
            continue
        if model is None:
            model = SR.ResidualModel(rec["state"])
        r = model.residual(rec["state"])
        r["t"] = rec["timestamp"]
        out.append(r)
    return out


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--step", type=int, default=10, help="use every step-th 1 Hz record")
    ap.add_argument("--safety", type=float, default=1.2)
    ap.add_argument("--settle-s", type=float, default=60.0, help="benign test records must be this far from any attack window")
    ap.add_argument("--k-pct", type=float, default=2.0, help="persistence detector: theta = k x train p99.9")
    ap.add_argument("--run-safety", type=float, default=1.5, help="persistence detector: L = ceil(f x longest train run above theta)")
    ap.add_argument("--root", default=None)
    ap.set_defaults(grid="sherlock")
    a = C.init(ap.parse_args())
    root = Path(a.root) if a.root else S.root()
    t0 = time.time()
    tr = run(root, "train", a.step)
    te = run(root, "test", a.step)
    wall = time.time() - t0
    np.savez_compressed(C.interim(f"physics_residual_step{a.step}.npz"),
                        **{f"{s}_{k}": np.array([r[k] for r in d]) for s, d in (("train", tr), ("test", te)) for k in ("t", "conv", *METRICS)})

    def arr(d, k):
        return np.array([r[k] for r in d], dtype=float)

    thr = {m: a.safety * np.nanmax(arr(tr, m)) for m in METRICS}
    ev = [e for e in S.load_events(root, "test") if "benign" not in e["id"]]
    ben_ev = [e for e in S.load_events(root, "test") if "benign" in e["id"]]
    tt = arr(te, "t")
    in_attack = np.zeros(len(tt), bool)
    near = np.zeros(len(tt), bool)
    for e in ev:
        end = e.get("recovery", e["end"])
        in_attack |= (tt >= e["start"]) & (tt <= end)
        near |= (tt >= e["start"] - a.settle_s) & (tt <= end + a.settle_s)
    benign = ~near
    def runs(mask):
        """length of the run of consecutive True ending at each index (records are consecutive at step)"""
        out = np.zeros(len(mask), int)
        c = 0
        for i, x in enumerate(mask):
            c = c + 1 if x else 0
            out[i] = c
        return out

    # D0: single-record threshold at safety x train max.  D1: persistence detector.
    alarm0 = {m: arr(te, m) > thr[m] for m in METRICS}
    theta = {m: a.k_pct * np.nanpercentile(arr(tr, m), 99.9) for m in METRICS}
    L = {m: max(3, int(np.ceil(a.run_safety * runs(arr(tr, m) > theta[m]).max()))) for m in METRICS}
    alarm1 = {m: runs(arr(te, m) > theta[m]) >= L[m] for m in METRICS}
    detectors = {"D0 max threshold": alarm0, "D1 persistence": alarm1}

    body = "# WP1-a: physics visibility of Sherlock attacks\n\n"
    body += ("Reconstructed grid (pandapower CIGRE MV with all DER, 32 switches, transformer parameters and tap changer "
             "identified from data, `rules/sherlock_grid_params.json`). Inputs taken from the IPAL state that the control "
             "center sees (vantage n302): load, DER and storage P and Q, connection, switch and tap states, external grid "
             "voltage. Residual = max abs difference between reported and recomputed bus voltages, line P (from end) and "
             f"transformer P (HV). Every {a.step}th record of the 1 Hz state; power flows by the cached fast solver "
             "(validated against runpp). Attack window = [start, recovery].\n\n"
             "Two detectors, both calibrated on train only (no attacks), fixed before looking at test:\n\n"
             f"- D0: alarm when a residual exceeds {a.safety} x its train maximum.\n"
             f"- D1: alarm when a residual stays above theta = {a.k_pct} x its train 99.9th percentile for at least L "
             f"consecutive records, L = ceil({a.run_safety} x longest train run above theta), at least 3.\n\n")
    body += C.md_table(["quantity", "value"], [
        ["records evaluated train / test", f"{len(tr)} / {len(te)}"],
        ["power flow not converged train / test", f"{int((~arr(tr, 'conv').astype(bool)).sum())} / {int((~arr(te, 'conv').astype(bool)).sum())}"],
        *[[f"{m} ({UNITS[m]}): train p99 / p99.9 / max", f"{np.nanpercentile(arr(tr, m), 99):.3e} / {np.nanpercentile(arr(tr, m), 99.9):.3e} / {np.nanmax(arr(tr, m)):.3e}"] for m in METRICS],
        *[[f"D0 threshold {m}", f"{thr[m]:.3e}"] for m in METRICS],
        *[[f"D1 theta, L for {m}", f"{theta[m]:.3e}, {L[m]} records"] for m in METRICS],
        [f"test benign records (more than {a.settle_s:.0f} s from any attack)", int(benign.sum())],
        ["wall time s", f"{wall:.0f}"],
    ])
    summary = []
    for dname, alarm in detectors.items():
        any_alarm = np.logical_or.reduce([alarm[m] for m in METRICS])
        body += f"\n## {dname}\n\n"
        body += f"False alarm rate on benign test records: {any_alarm[benign].mean():.5f} ({int(any_alarm[benign].sum())} of {int(benign.sum())} records).\n\n"
        if any_alarm[benign].any():
            near_proc = collections.Counter()
            for t in tt[benign & any_alarm]:
                lab = "none within 120 s"
                for e in ben_ev:
                    if e["start"] - 120 <= t <= e["end"] + 120:
                        lab = e["description"]
                near_proc[lab] += 1
            body += C.md_table(["benign procedure within 120 s of the false alarm", "alarm records"], sorted(near_proc.items())) + "\n"
        rows, per_type = [], collections.defaultdict(lambda: [0, 0])
        for e in ev:
            end = e.get("recovery", e["end"])
            sel = (tt >= e["start"]) & (tt <= end)
            hit = bool(any_alarm[sel].any())
            delay = (tt[sel][any_alarm[sel]][0] - e["start"]) if hit else None
            ref = thr if dname.startswith("D0") else theta
            peak = {m: np.nanmax(arr(te, m)[sel]) / ref[m] if sel.any() else np.nan for m in METRICS}
            per_type[e["description"]][0] += 1
            per_type[e["description"]][1] += int(hit)
            rows.append([e["id"], e["description"], ", ".join(e.get("attack_point") or []) or "⟨none⟩", int(sel.sum()),
                         C.fmt(hit), *[f"{peak[m]:.2f}" for m in METRICS], "⟨·⟩" if delay is None else f"{delay:.0f}"])
        refname = "threshold" if dname.startswith("D0") else "theta"
        body += f"Peak columns: max residual in the window divided by the {refname}.\n\n"
        body += C.md_table(["id", "type", "targeted assets", "records", "detected", *[f"peak {m}/{refname}" for m in METRICS], "first alarm after start s"], rows)
        body += "\nPer attack type:\n\n"
        body += C.md_table(["type", "instances", "detected", "rate"], [[k, n, d, f"{d / n:.2f}"] for k, (n, d) in sorted(per_type.items())])
        summary.append((dname, {k: f"{d}/{n}" for k, (n, d) in per_type.items()}, any_alarm[benign].mean()))
    body += ("\nReading: a physics-consistency rule (and therefore any rule the physics oracle certifies) can only catch "
             "attacks that make the telemetry physically inconsistent. Attacks that change the real grid through valid "
             "commands keep the telemetry consistent and need state-transition or context rules instead.\n")
    C.write_report("physics_residual.md", body)
    for dname, pt, fa in summary:
        print(dname, pt, "FA", f"{fa:.5f}")
    print(f"{wall:.0f}s")


if __name__ == "__main__":
    main()
