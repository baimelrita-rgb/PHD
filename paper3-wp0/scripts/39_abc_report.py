"""Results of the controlled A/B/C experiment on 02-Semiurban (scripts/36), one row per day, seed and variant,
with paired comparisons (event ids), delay on commonly detected events, first detections in the recovery
phase, availability of the library, and the effect of the physics check. Reads reports/abc/abc_*.json."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
from scipy.stats import binomtest

from p3 import common as C

DAYS = [("recorded", "recorded", ""), ("split", "injected", 7), ("split_s8", "injected", 8), ("split_s9", "injected", 9),
        ("split_s10", "injected", 10), ("split_s11", "injected", 11)]


def short(nm):
    return nm.split(":")[0]


def main():
    C.parser(__doc__).parse_args()
    body = "# A/B/C experiment on 02-Semiurban: results\n\n"
    body += ("Definitions and protocol: `scripts/36_semiurban_abc.py` (docstring). Calibration frozen before the test day: "
             "`reports/abc/frozen_recorded.json` (recorded day), `reports/abc/frozen_split.json` (injected days; all seeds share the "
             "same calibration half-day). Persistence L = 3 records (5 s per record) for every variant. Benign records: more than 60 s from "
             "any attack window. The recorded day is the main result; the injected seeds share one benign base half-day and test "
             "sensitivity to the choice and strength of injected events, not independent days.\n\n")
    main_rows, pair_rows, phys_rows, chk_rows = [], [], [], []
    tot = {}
    for v, kind, seed in DAYS:
        f = C.ROOT / "reports" / "abc" / f"abc_{v}.json"
        if not f.exists():
            continue
        d = json.loads(f.read_text()); R = d["results"]
        names = list(R)
        A, B15, C0, C15, Bk, Ck = names
        for nm in names:
            r = R[nm]; n = len(r["out"]); k = sum(r["out"].values())
            per = ", ".join(f"{p} {a}/{b}" for p, (a, b) in r["per"].items())
            fa = f"{r['eps']} in {r['hours']:.1f} h" + ("" if r["eps"] else "") + f" ({r['eps'] / r['hours']:.2f}/h)"
            calib = "frozen calibration" if "calibrated" in nm else ("published setting" if nm[0] in "BC" else "scripts/17")
            main_rows.append([kind, seed, short(nm), "" if r["k"] is None else f"{r['k']:g}", calib, f"{k}/{n}", per, fa,
                              f"{r['rate'] * 100:.3f} %", r["recovery_first"], "" if r["active"] is None else f"{r['active'] * 100:.1f} %"])
            tot.setdefault((kind if kind == "recorded" else "injected (5 seeds)", nm.split(",")[0].split(":")[0] + (" calibrated" if "calibrated" in nm else (" k=1.5" if "1.5" in nm else ""))), [0, 0, 0, 0.0])
            t_ = tot[(kind if kind == "recorded" else "injected (5 seeds)", nm.split(",")[0].split(":")[0] + (" calibrated" if "calibrated" in nm else (" k=1.5" if "1.5" in nm else "")))]
            t_[0] += k; t_[1] += n; t_[2] += r["eps"]; t_[3] += r["hours"]
        for a_, b_, lab in ((A, B15, "A vs B (k = 1.5)"), (B15, C15, "B vs C (k = 1.5)"), (A, Bk, "A vs B (calibrated)"), (Bk, Ck, "B vs C (calibrated)"), (C0, C15, "C0 (stored) vs C (corrected), k = 1.5")):
            oa, ob = R[a_]["out"], R[b_]["out"]
            only_a = [i for i in oa if oa[i] and not ob[i]]; only_b = [i for i in oa if ob[i] and not oa[i]]
            both = [i for i in oa if oa[i] and ob[i]]
            p = binomtest(len(only_b), len(only_a) + len(only_b), 0.5).pvalue if only_a or only_b else 1.0
            da = [R[a_]["delay"][i] for i in both]; db = [R[b_]["delay"][i] for i in both]
            pair_rows.append([kind, seed, lab, f"{len(only_a)} ({', '.join(only_a) or '-'})", f"{len(only_b)} ({', '.join(only_b) or '-'})", f"{p:.3f}",
                              len(both), f"{np.median(da):.0f} / {np.median(db):.0f}" if both else "-"])
        imp = d["impact"]
        known = sum(1 for x in imp if x["known_before_test"])
        phys_rows.append([kind, seed, len(imp), known, sum(1 for x in imp if x["rejected"]),
                          f"{int(np.median([x['raised_at_1.5'] for x in imp]))} of {int(np.median([x['channels'] for x in imp]))}",
                          f"{int(np.median([x[[k for k in x if k.startswith('raised_at_k') and k != 'raised_at_1.5'][0]] for x in imp]))}",
                          f"{np.median([x['median_ratio'] for x in imp]):.2f}", f"{np.median([x['compute_s'] for x in imp if not x['known_before_test']] or [0]):.0f}"])
        for c in d["checks"]:
            chk_rows.append([kind, seed] + c)
        if d["example"]:
            ex = d["example"]
            body_ex = (f"- {kind} {seed}: event {ex['event']} ({ex['type'].split(':')[0]}), {ex['t_rel']:.0f} s after its start, channel `{ex['channel']}`: "
                       f"|r| = {ex['residual_sigma']:.3f} sigma; noise term {ex['noise']:.3f}; B margin {ex['B_margin']:.3f} (fires), C margin {ex['C_margin']:.3f} "
                       f"(the physics bound of this unmonitored-adjacent channel is large, so C does not fire).\n")
            phys_rows[-1].append(body_ex)
    body += "## 1. Main table\n\n" + C.md_table(["day", "seed", "variant", "k", "how k was set", "detected", "per type", "false-alarm episodes (benign hours)",
                                                 "benign records flagged", "first detections in recovery", "library active (share of records)"], main_rows)
    tr = [[a, b, f"{v[0]}/{v[1]}", f"{v[2]} in {v[3]:.1f} h ({v[2] / v[3]:.2f}/h)"] for (a, b), v in tot.items()]
    body += "\n## 2. Totals over the injected seeds (descriptive; shared benign base day)\n\n" + C.md_table(["set", "variant", "detected", "false-alarm episodes"], tr)
    body += "\n## 3. Paired comparisons (event ids)\n\n" + C.md_table(["day", "seed", "comparison", "only first", "only second", "exact McNemar p", "both detect", "median delay s, first / second (common events)"], pair_rows)
    body += "\n## 4. Effect of the physics check\n\n" + C.md_table(["day", "seed", "rules checked", "computed before the test day", "rejected",
                                                                    "channels raised at k = 1.5 (median per topology)", "channels raised at calibrated k", "median ratio 1.5 x bound / (1.5 x noise)",
                                                                    "median compute s (new topologies)"], [r[:9] for r in phys_rows])
    ex = [r[9] for r in phys_rows if len(r) > 9]
    if ex:
        body += "\nExample of a margin change that explains an outcome (B detects, C misses):\n\n" + "".join(ex)
    body += "\n## 5. Regression and hold-out checks of C (benign states; fails if the rule fires)\n\n"
    body += C.md_table(["day", "seed", "check", "topology", "k", "stored rule fails", "C fails", "largest score"], chk_rows)
    C.write_report("abc_results.md", body)
    print(body[:6000])


if __name__ == "__main__":
    main()
