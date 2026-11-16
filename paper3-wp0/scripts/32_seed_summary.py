"""Improvement B2: the additional day regenerated with five injection seeds (7 = main, 8 to 11).

Each seed draws new attack times, targets and magnitudes (attack model v2) on the same benign base
half-day; every calibration is rerun per seed (scripts/seeds_runs.sh). Per seed: process attacks
detected by the classic detector, the certified library and the combination, pooled over 01-Basic
and 02-Semiurban, and the exact McNemar test of combined against classic on that seed's instances.
The last row pools the five seeds; their instances share one benign base day, so the pooled test is
descriptive, not an independent replication."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scipy.stats import binomtest

from p3 import common as C


def main():
    C.parser(__doc__).parse_args()
    rows, B, Cc, agg = [], 0, 0, {}
    for seed, v in ((7, "split"), (8, "split_s8"), (9, "split_s9"), (10, "split_s10"), (11, "split_s11")):
        f = C.INTERIM / f"mcnemar_pooled_{v}.json"
        if not f.exists():
            rows.append([seed, "⟨·⟩", "⟨·⟩", "⟨·⟩", "⟨·⟩", "not run"]); continue
        d = json.loads(f.read_text())
        b, c = d["b"], d["c"]; B += b; Cc += c
        p = binomtest(b, b + c, 0.5).pvalue if b + c else 1.0
        cell = lambda k: f"{d['pooled'][k][0]}/{d['pooled'][k][1]}"
        for k in ("classic", "library", "combined"):
            agg.setdefault(k, [0, 0]); agg[k][0] += d["pooled"][k][0]; agg[k][1] += d["pooled"][k][1]
        rows.append([seed, cell("classic"), cell("library"), cell("combined"), f"{b} / {c}", f"{p:.4f}"])
    P = binomtest(B, B + Cc, 0.5).pvalue if B + Cc else 1.0
    rows.append(["all seeds (descriptive)", *(f"{agg[k][0]}/{agg[k][1]}" for k in ("classic", "library", "combined")), f"{B} / {Cc}", f"{P:.2e}"])
    body = "# Improvement B2: five injection seeds for the additional day\n\n" + __doc__.split("\n\n", 1)[1] + "\n\n"
    body += C.md_table(["seed", "classic", "certified library", "combined", "only combined / only classic", "McNemar p"], rows)
    C.write_report("seed_summary.md", body)
    print(body[-900:])


if __name__ == "__main__":
    main()
