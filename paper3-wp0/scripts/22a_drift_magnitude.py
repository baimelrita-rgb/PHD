"""WP4d: measured magnitude of the real drift-off attacks (anatomy for the injected attack model).
For each drift-off instance of a recorded test day: every 5th record in [start, end], reported bus
voltage minus the true one (nearest ground-truth snapshot); per instance the largest |difference|
over buses and records, and the number of buses whose difference exceeds 0.005 pu."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np

from p3 import common as C
from p3 import sherlock_io as S

ROOTS = {"sherlock": S.ROOT_DEFAULT, "semiurban": S.ROOT_SEMI, "rural": S.ROOT_RURAL}


def main():
    a = C.parser(__doc__).parse_args()
    rows, out = [], {}
    for g, r in ROOTS.items():
        ev = [e for e in S.load_events(r, "test") if e["description"] == "drift-off:drift-off"]
        z, idx = S.physical_index(r, "test")
        tt = np.array([x for x, _ in idx])
        mags = []
        for i_rec, rec in enumerate(S.iter_state(r, "test")):
            if i_rec % 5:
                continue
            ts = rec["timestamp"]
            for e in ev:
                if e["start"] <= ts <= e["end"]:
                    k = int(np.clip(np.searchsorted(tt, ts), 0, len(tt) - 1))
                    v = S.read_snapshot(z, idx[k][1])["values"]
                    d = {int(key.split(".")[1].split(":")[0]): val - v[f"bus.{key.split('.')[1].split(':')[0]}.MEASUREMENT.voltage"]
                         for key, val in rec["state"].items() if key.startswith("bus.") and key.endswith(":voltage") and val is not None}
                    m = e.setdefault("_m", [0.0, set()])
                    for b, x in d.items():
                        if abs(x) > abs(m[0]):
                            m[0] = x
                        if abs(x) > 0.005:
                            m[1].add(b)
        for e in ev:
            m = e.get("_m", [0.0, set()])
            mags.append(m[0])
            rows.append([g, e["id"], f"{m[0]:+.4f}", len(m[1])])
        out[g] = {"max_signed_offset_pu": mags, "buses_above_0.005": [len(e.get("_m", [0, set()])[1]) for e in ev]}
        print(g, [round(x, 4) for x in mags])
    (C.ROOT / "rules" / "drift_magnitudes.json").write_text(json.dumps(out, indent=1))
    C.write_report("drift_magnitude.md", "# WP4d: measured magnitude of the real drift-off attacks\n\n" + __doc__.split("\n", 1)[1] + "\n\n"
                   + C.md_table(["grid", "id", "largest reported minus true bus voltage, pu", "buses above 0.005 pu"], rows))


if __name__ == "__main__":
    main()
