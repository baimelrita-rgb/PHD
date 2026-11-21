"""Reproduction audit: per injection seed, library alone against the classic detector (a test that can go
either way, unlike combined = classic OR library), per grid and pooled, with the exact McNemar test.
01-Basic: library = rules active at the time (lib_prior), classic = D1. 02-Semiurban: library with
persistence L = 3, classic = SE-BDD. Instances share one benign base day per grid."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
from scipy.stats import binomtest

from p3 import common as C
from p3 import envelope as E
from p3 import sherlock_io as S

PROCESS = ["control-and-freeze:control-and-freeze", "drift-off:drift-off", "industroyer:industroyer"]


def outc(t, al, ev):
    return {e["id"]: bool(al[(t >= e["start"]) & (t <= e.get("recovery", e["end"]))].any())
            for e in ev if e["description"] in PROCESS and "benign" not in e["id"]}


def main():
    C.parser(__doc__).parse_args()
    rows, tot = [], {"sherlock": [0, 0], "semiurban": [0, 0], "all": [0, 0]}
    for seed, v in ((7, "split"), (8, "split_s8"), (9, "split_s9"), (10, "split_s10"), (11, "split_s11")):
        os.environ["P3_VARIANT"] = v
        cells = []
        bb = cc = 0
        for g in ("sherlock", "semiurban"):
            C.GRID = g; E.use_grid(g); ev = S.load_events(S.root(), "test")
            if g == "sherlock":
                d = np.load(C.interim("consolidation_fires.npz")); a = np.load(C.interim("detector_alarms_physics.npz"))
                t, lib, cls = d["t"], d["lib_prior"].astype(bool), a["D1"].astype(bool)
            else:
                d = np.load(C.interim("semiurban_fires.npz")); sb = np.load(C.interim("se_residuals.npz"))
                t, lib, cls = d["t"], d["fires_p"].astype(bool), sb["alarm"].astype(bool)
            L_, K_ = outc(t, lib, ev), outc(t, cls, ev)
            b = sum(L_[i] and not K_[i] for i in L_); c = sum(K_[i] and not L_[i] for i in L_)
            tot[g][0] += b; tot[g][1] += c; bb += b; cc += c
            cells.append(f"{sum(L_.values())} vs {sum(K_.values())} of {len(L_)} ({b} / {c})")
        tot["all"][0] += bb; tot["all"][1] += cc
        p = binomtest(bb, bb + cc, 0.5).pvalue if bb + cc else 1.0
        rows.append([seed, *cells, f"{bb} / {cc}", f"{p:.4f}"])
    os.environ.pop("P3_VARIANT", None); C.GRID = C.DEFAULT_GRID
    pr = lambda x: binomtest(x[0], sum(x), 0.5).pvalue if sum(x) else 1.0
    rows.append(["all seeds (descriptive)", f"{tot['sherlock'][0]} / {tot['sherlock'][1]}, p = {pr(tot['sherlock']):.2e}",
                 f"{tot['semiurban'][0]} / {tot['semiurban'][1]}, p = {pr(tot['semiurban']):.2e}", f"{tot['all'][0]} / {tot['all'][1]}", f"{pr(tot['all']):.4f}"])
    body = "# Audit: library alone vs classic detector, per injection seed\n\n" + __doc__ + "\n\n"
    body += C.md_table(["seed", "01-Basic: library vs D1 detected (only library / only D1)", "02-Semiurban: library vs SE-BDD (only library / only SE-BDD)",
                        "pooled only library / only classic", "McNemar p"], rows)
    (C.ROOT / "reports" / "audit" / "seed_library_vs_classic.md").write_text(body)
    print(body)


if __name__ == "__main__":
    main()
