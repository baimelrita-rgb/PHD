"""Reviewer M9: our methods scored with the Sherlock dataset paper's recommended metrics (Wagner et al.,
CODASPY 2025, Sec. 3.5), on the 01-Basic test day, so they can be set beside the five published IIDSs
in that paper's Table 3.

Definitions (copied from the dataset paper): an alarm is a continuous run of alarm records.
  Detected attacks: number of attacks (all 18, arp-spoof included) during which an alarm STARTS.
                    Alarms starting before the attack are false alarms; alarms starting in the
                    recovery phase (end to recovery) are ignored.
  False alarms:     number of alarms starting during normal operation; in brackets, how many of them
                    start during a benign procedure or within 120 s after it.
  Average TTD:      mean time from attack start to the first alarm start, over detected attacks.
The published numbers are copied from the dataset paper (Table 3); they were obtained "after heavily
filtering measurements that are affected by switching operations and maintenance", which we do not do."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import envelope as E
from p3 import sherlock_io as S

PUBLISHED = [("PASAD", "0/18", "1 (0)", "⟨·⟩"), ("Invariant", "0/18", "1 (0)", "⟨·⟩"), ("Seq2SeqNN", "7/18", "10 (0)", "149.63"),
             ("SIMPLE", "16/18", "33 (33)", "81.43"), ("GeCo", "15/18", "94 (30)", "75.89")]


def score(t, alarm, events):
    att = [e for e in events if "benign" not in e["id"]]
    ben = [e for e in events if "benign" in e["id"]]
    starts = np.where(np.diff(np.r_[0, alarm.astype(int)]) == 1)[0]
    ts = t[starts]
    det, ttd, fa, fa_b = 0, [], 0, 0
    used = np.zeros(len(ts), bool)
    for e in att:
        inside = (ts >= e["start"]) & (ts <= e["end"])
        if inside.any():
            det += 1
            ttd.append(float(ts[inside][0] - e["start"]))
        used |= (ts >= e["start"]) & (ts <= e.get("recovery", e["end"]))
    for x, u in zip(ts, used):
        if u:
            continue
        fa += 1
        if any(b["start"] <= x <= b["end"] + 120 for b in ben):
            fa_b += 1
    return f"{det}/{len(att)}", f"{fa} ({fa_b})", (f"{np.mean(ttd):.2f}" if ttd else "⟨·⟩")


def main():
    C.parser(__doc__).parse_args()
    E.use_grid("sherlock"); C.GRID = "sherlock"
    ev = S.load_events(S.root(), "test")
    da = np.load(C.interim("detector_alarms_physics.npz"))
    cf = np.load(C.interim("consolidation_fires.npz"))
    ct = np.load(C.interim("consolidation_fires_tc.npz"))
    rows = []
    for name, t, al in [
            ("D1 residual test (ours, classic)", da["t"], da["D1"]),
            ("autoencoder, physics features (ours, ML)", da["t"], da["AE"]),
            ("certified library (ours)", cf["t"], cf["lib_prior"]),
            ("certified library + per-topology calibration (ours)", ct["t"], ct["lib_prior"]),
            ("combined: D1 or AE or library (ours)", cf["t"], cf["det"] | cf["lib_prior"]),
            ("combined, with per-topology calibration (ours)", ct["t"], ct["det"] | ct["lib_prior"])]:
        rows.append([name, *score(np.asarray(t), np.asarray(al).astype(bool), ev)])
    body = "# Reviewer M9: comparison with published IIDSs on 01-Basic (dataset paper's metrics)\n\n" + __doc__.split("\n\n", 1)[1] + "\n\n"
    body += C.md_table(["IIDS", "detected attacks", "false alarms (by benign events)", "average TTD s"],
                       [[f"{n} (published, Table 3 of the dataset paper)", d, f, t] for n, d, f, t in PUBLISHED] + rows)
    C.write_report("sherlock_metrics.md", body)
    print(body[-1600:])


if __name__ == "__main__":
    main()
