"""WP4a: uncertainty and paired significance for the main comparison.

Per method and grid: per-instance detection outcomes (process attacks only: control-and-freeze,
drift-off, industroyer), Wilson 95 % intervals for detection rates (per grid and pooled over grids),
exact McNemar tests between methods on the same attack instances (two-sided binomial test on the
discordant pairs), and exact Poisson (Garwood) 95 % intervals for false-alarm episodes per benign
hour (episodes, not records, because records within an episode are not independent).
Reads the same saved alarms as scripts/19_comparison.py."""
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
from scipy.stats import binomtest, chi2

from p3 import common as C
from p3 import envelope as E
from p3 import sherlock_io as S

spec = importlib.util.spec_from_file_location("cmp19", Path(__file__).with_name("19_comparison.py"))
cmp19 = importlib.util.module_from_spec(spec); spec.loader.exec_module(cmp19)
PROCESS = ["control-and-freeze:control-and-freeze", "drift-off:drift-off", "industroyer:industroyer"]


def wilson(k, n, z=1.96):
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def garwood(k, alpha=0.05):
    lo = 0.0 if k == 0 else chi2.ppf(alpha / 2, 2 * k) / 2
    hi = chi2.ppf(1 - alpha / 2, 2 * k + 2) / 2
    return lo, hi


def outcomes(t, alarm, events, strict=None, settle=60.0):
    att = [e for e in events if e["description"] in PROCESS and "benign" not in e["id"]]
    out = {}
    for e in att:
        sel = (t >= e["start"]) & (t <= e.get("recovery", e["end"]))
        if strict is not None:
            rf, added = strict
            prior = added < e["start"]
            a_e = rf[prior].any(axis=0) if prior.any() else np.zeros(len(t), bool)
        else:
            a_e = alarm
        out[e["id"]] = bool(a_e[sel].any())
    near = np.zeros(len(t), bool)
    for e in events:
        if "benign" not in e["id"]:
            near |= (t >= e["start"] - settle) & (t <= e.get("recovery", e["end"]) + settle)
    benign = ~near
    fa = alarm & benign
    eps = int(np.sum(np.diff(np.r_[0, fa.astype(int)]) == 1))
    hours = benign.sum() * float(np.median(np.diff(t))) / 3600
    return out, eps, hours


def main():
    ap = C.parser(__doc__)
    a = ap.parse_args()
    methods = {
        "sherlock": {"classic": ("detector_alarms_physics.npz", "D1", None),
                     "library (strict)": ("consolidation_fires.npz", "lib_prior", "strict"),
                     "combined": ("consolidation_fires.npz", "comb", None)},
        "semiurban": {"classic": ("se_residuals.npz", "alarm", None),
                      "library (L = 3)": ("semiurban_fires.npz", "fires_p", None),
                      "combined": ("semiurban_fires.npz", "comb", None)},
        "rural": {"classic": ("se_residuals.npz", "alarm", None),
                  "library (L = 3)": ("semiurban_fires.npz", "fires_p", None),
                  "combined": ("semiurban_fires.npz", "comb", None)},
    }
    results = {}
    for grid, ms in methods.items():
        E.use_grid(grid); C.GRID = grid
        if not (C.INTERIM / C.suffixed(ms["classic"][0])).exists():
            continue
        ev = S.load_events(S.root(), "test")
        res = {}
        for name, (f, key, mode) in ms.items():
            d = np.load(C.interim(f), allow_pickle=True)
            t = d["t"] if "t" in d else d["test_t"]
            if key == "comb":
                if grid == "sherlock":
                    al = d["det"].astype(bool) | d["lib_prior"].astype(bool)
                else:
                    sb = np.load(C.interim("se_residuals.npz"), allow_pickle=True)
                    al = sb["alarm"].astype(bool) | d["fires_p"].astype(bool)
            else:
                al = d[key].astype(bool)
            strict = (d["rule_fires"].astype(bool), d["added_at"]) if mode == "strict" else None
            res[name] = outcomes(t, al, ev, strict)
        results[grid] = (res, {e["id"]: e["description"] for e in ev})
    C.GRID = C.DEFAULT_GRID

    body = "# WP4a: confidence intervals and paired tests\n\n"
    body += ("Process attacks only (control-and-freeze, drift-off, industroyer). Detection: Wilson 95 % interval over attack "
             "instances. False alarms: exact Poisson (Garwood) 95 % interval on false-alarm episodes per benign hour. Paired "
             "comparison: exact McNemar test (two-sided binomial on the instances where exactly one method detects). "
             "'combined' = classic detector or the certified library (01-Basic: detectors D1 or AE or library; "
             "02-Semiurban and 03-Rural: SE-BDD or library with persistence 3).\n\n")
    rows, pooled = [], {}
    for grid, (res, types) in results.items():
        for name, (out, eps, hours) in res.items():
            k, n = sum(out.values()), len(out)
            lo, hi = wilson(k, n)
            flo, fhi = garwood(eps)
            rows.append([grid, name, f"{k}/{n}", f"{k / n:.2f} [{lo:.2f}, {hi:.2f}]", f"{eps / hours:.2f} [{flo / hours:.2f}, {fhi / hours:.2f}]"])
            pk, pn = pooled.get(name.split(" ")[0], (0, 0))
            pooled[name.split(" ")[0]] = (pk + k, pn + n)
    body += "## Detection and false alarms per grid\n\n" + C.md_table(["grid", "method", "detected", "rate [95 % CI]", "false-alarm episodes per benign hour [95 % CI]"], rows)
    prow = []
    for name, (k, n) in pooled.items():
        lo, hi = wilson(k, n)
        prow.append([name, f"{k}/{n}", f"{k / n:.2f} [{lo:.2f}, {hi:.2f}]"])
    body += "\n## Pooled over the three grids\n\n" + C.md_table(["method family", "detected", "rate [95 % CI]"], prow)
    trow = []
    for grid, (res, types) in results.items():
        names = list(res)
        base = res[names[0]][0]
        for other in names[1:]:
            o = res[other][0]
            b = sum(1 for i in base if o[i] and not base[i])       # other detects, classic does not
            c = sum(1 for i in base if base[i] and not o[i])
            p = binomtest(b, b + c, 0.5).pvalue if b + c else 1.0
            trow.append([grid, f"{other} vs {names[0]}", b, c, f"{p:.3f}"])
    # pooled McNemar for combined vs classic
    b = c = 0
    for grid, (res, types) in results.items():
        base, o = res["classic"][0], res["combined"][0]
        b += sum(1 for i in base if o[i] and not base[i]); c += sum(1 for i in base if base[i] and not o[i])
    trow.append(["pooled", "combined vs classic", b, c, f"{binomtest(b, b + c, 0.5).pvalue if b + c else 1.0:.3f}"])
    body += "\n## Paired tests (exact McNemar)\n\n" + C.md_table(["grid", "comparison", "only the first detects", "only the classic detects", "p (two-sided)"], trow)
    body += ("\nReading: with 16 to 23 process-attack instances per grid, intervals are wide; a difference of a few instances "
             "is not significant on one grid alone. The pooled test is the paper's main paired evidence.\n")
    C.write_report("statistics.md", body)
    print(body[-1800:])


if __name__ == "__main__":
    main()
