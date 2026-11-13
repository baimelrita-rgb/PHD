"""WP1-c step 0: what does each Sherlock test attack do to the telemetry?

For every attack window, the IPAL state (what the control center sees) is compared with
the physical ground truth (raw/test/physical.zip, nearest snapshot in time). A field is
"falsified" when reported and true values differ by more than a noise threshold. The
true grid state just before and inside the window is also compared, to see real changes
(switching, DER disconnection). Ground truth is used for analysis only, never by rules."""
import bisect
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import sherlock_io as S

TOL = {"voltage": 2e-3, "active_power": 0.02e6, "reactive_power": 0.02e6, "active_power_from": 0.02e6,
       "active_power_hv": 0.02e6, "is_closed": 0.5, "is_connected": 0.5}


def snap_key(k):   # 'bus.3:voltage' -> 'bus.3.MEASUREMENT.voltage'
    e, a = k.split(":", 1)
    return f"{e}.MEASUREMENT.{a}"


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--root", default=str(S.ROOT_DEFAULT))
    ap.add_argument("--n-ctrl", type=int, default=12)
    a = ap.parse_args()
    root = Path(a.root)
    z, idx = S.physical_index(root, "test")
    ts = [t for t, _ in idx]
    ev = [e for e in S.load_events(root, "test") if "benign" not in e["id"]]
    win = [(e["start"], e.get("recovery", e["end"])) for e in ev]
    # benign control windows (300 s, at least 120 s from any attack), same comparison
    rng = np.random.default_rng(a.seed)
    t0_, t1_ = ts[0] + 600, ts[-1] - 600
    ctrl = []
    while len(ctrl) < a.n_ctrl:
        s0 = float(rng.uniform(t0_, t1_))
        if all(s0 + 300 < s - 120 or s0 > e + 120 for s, e in win) and all(abs(s0 - c0) > 300 for c0, _ in ctrl):
            ctrl.append((s0, s0 + 300))
    n_att = len(ev)
    ev = ev + [{"id": f"ctrl{k}", "description": "benign control window", "start": c0, "end": c1} for k, (c0, c1) in enumerate(ctrl)]
    win = win + ctrl
    fals = [collections.Counter() for _ in ev]
    nrec = [0] * len(ev)
    npairs = [0] * len(ev)
    real = [set() for _ in ev]
    before = [None] * len(ev)
    for rec in S.iter_state(root, "test"):
        t = rec["timestamp"]
        for i, (s, e) in enumerate(win):
            if before[i] is None and s - 30 <= t < s - 25:
                j = min(bisect.bisect_left(ts, t), len(ts) - 1)
                before[i] = S.read_snapshot(z, idx[j][1])["values"]
            if not (s <= t <= e):
                continue
            nrec[i] += 1
            if nrec[i] % 5:          # every 5th record is enough to see the pattern
                continue
            j = min(bisect.bisect_left(ts, t), len(ts) - 1)
            truth = S.read_snapshot(z, idx[j][1])["values"]
            npairs[i] += 1
            for k, v in rec["state"].items():
                attr = k.split(":", 1)[1]
                if attr not in TOL or not isinstance(v, (int, float, bool)):
                    continue
                tv = truth.get(snap_key(k))
                if tv is None:
                    continue
                if abs(float(v) - float(tv)) > TOL[attr]:
                    fals[i][k.split(":")[0].split(".")[0] + ":" + attr] += 1
            if before[i] is not None:
                for k in ("is_closed", "is_connected"):
                    for kk, tv in truth.items():
                        if kk.endswith("MEASUREMENT." + k) and before[i].get(kk) is not None and bool(tv) != bool(before[i][kk]):
                            real[i].add(kk.split(".MEASUREMENT")[0] + (" opened" if not tv else " closed"))
    # baseline: rate per field kind (deviating pairs per compared record) in benign control windows
    base = collections.Counter()
    nb = sum(npairs[n_att:])
    for i in range(n_att, len(ev)):
        base.update(fals[i])
    base_rate = {k: v / max(nb, 1) for k, v in base.items()}
    rows = []
    for i, e in enumerate(ev[:n_att]):
        rate = {k: v / max(npairs[i], 1) for k, v in fals[i].items()}
        lift = sorted(((r / max(base_rate.get(k, 0.0), 0.05), k, r) for k, r in rate.items()), reverse=True)
        top = ", ".join(f"{k} {r:.1f}/rec (x{l:.0f})" for l, k, r in lift if l >= 3 and r >= 0.2)[:160] or "none above baseline"
        rows.append([e["id"], e["description"], ", ".join(e.get("attack_point") or []) or "⟨none⟩", nrec[i], top,
                     ", ".join(sorted(real[i])[:6]) or "none"])
    body = "# WP1-c step 0: attack anatomy (telemetry versus ground truth)\n\n"
    body += ("Deviation: reported (IPAL, vantage n302) minus true (nearest physical snapshot) beyond a noise threshold "
             f"({', '.join(f'{k} {v:g}' for k, v in TOL.items())}; W and var for powers), every 5th record. Snapshot timing "
             f"alone produces deviations, so the same comparison is run on {a.n_ctrl} benign control windows (300 s, at least "
             "120 s from attacks). Listed per attack: field kinds whose deviation rate (deviating elements per compared record) "
             "is at least 3 times the benign rate (benign floor 0.05) and at least 0.2. Real changes: switch or connection "
             "states of the true grid inside the window that differ from 25 to 30 s before it.\n\n")
    body += "Benign control rates (deviating elements per compared record): " + ", ".join(f"{k} {v:.2f}" for k, v in sorted(base_rate.items())) + "\n\n"
    body += C.md_table(["id", "type", "targeted assets (label)", "records", "fields deviating above the benign rate", "real state changes"], rows)
    C.write_report("attack_anatomy.md", body)
    for r in rows:
        print(r[0], r[1], "|", r[4][:90], "|", r[5][:80])


if __name__ == "__main__":
    main()
