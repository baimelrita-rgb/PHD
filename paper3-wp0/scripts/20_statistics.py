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


def outcomes(t, alarm, events, strict=None, settle=60.0, added_t=None):
    att = [e for e in events if e["description"] in PROCESS and "benign" not in e["id"]]
    out = {}
    for e in att:
        sel = (t >= e["start"]) & (t <= e.get("recovery", e["end"]))
        if strict is not None:
            rf, added = strict
            prior = added < e["start"]
            a_e = rf[prior].any(axis=0) if prior.any() else np.zeros(len(t), bool)
        elif added_t is not None:
            a_e = alarm & (added_t < e["start"])
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
    ap.add_argument("--tag", default="", help="01-Basic consolidation run to use (e.g. _tc: WP5 per-topology calibration)")
    ap.add_argument("--pool-with", default="split", help="split-day variant whose paired counts are pooled with the recorded days")
    a = ap.parse_args()
    cf = f"consolidation_fires{a.tag}.npz"
    methods = {
        "sherlock": {"classic": ("detector_alarms_physics.npz", "D1", None),
                     "library (strict)": (cf, "lib_prior", "strict"),
                     "combined": (cf, "comb", None),
                     "combined (strict)": (cf, "comb_strict", "strict")},
        "semiurban": {"classic": ("se_residuals.npz", "alarm", None),
                      "library (L = 3)": ("semiurban_fires.npz", "fires_p", None),
                      "combined": ("semiurban_fires.npz", "comb", None),
                      "library (L = 3, strict)": ("semiurban_fires.npz", "fires_p", "topo"),
                      "combined (strict)": ("semiurban_fires.npz", "comb", "topo")},
        "rural": {"classic": ("se_residuals.npz", "alarm", None),
                  "library (L = 3)": ("semiurban_fires.npz", "fires_p", None),
                  "combined": ("semiurban_fires.npz", "comb", None),
                  "library (L = 3, strict)": ("semiurban_fires.npz", "fires_p", "topo"),
                  "combined (strict)": ("semiurban_fires.npz", "comb", "topo")},
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
            if mode == "topo" and "added_t" not in d:
                continue
            added_t = None
            if key in ("comb", "comb_strict"):
                if grid == "sherlock":
                    det = d["det"].astype(bool)
                    al = det | d["lib_prior"].astype(bool)
                else:
                    sb = np.load(C.interim("se_residuals.npz"), allow_pickle=True)
                    det = sb["alarm"].astype(bool)
                    al = det | d["fires_p"].astype(bool)
                if mode == "topo":
                    added_t = np.where(det, -np.inf, d["added_t"])
            else:
                al = d[key].astype(bool)
                if mode == "topo":
                    added_t = d["added_t"]
            if key == "comb_strict":     # detectors, or library rules learned before the attack
                rf = np.vstack([d["rule_fires"].astype(bool), det[None, :]])
                strict = (rf, np.r_[d["added_at"], -np.inf])
            else:
                strict = (d["rule_fires"].astype(bool), d["added_at"]) if mode == "strict" else None
            res[name] = outcomes(t, al, ev, strict, added_t=added_t)
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
            if "strict" in name and name != "library (strict)":
                continue      # strict variants are reported per grid and in the paired tests, not pooled twice
            pk, pn = pooled.get(name.split(" ")[0], (0, 0))
            pooled[name.split(" ")[0]] = (pk + k, pn + n)
    body += "## Detection and false alarms per grid\n\n" + C.md_table(["grid", "method", "detected", "rate [95 % CI]", "false-alarm episodes per benign hour [95 % CI]"], rows)
    prow = []
    for name, (k, n) in pooled.items():
        lo, hi = wilson(k, n)
        prow.append([name, f"{k}/{n}", f"{k / n:.2f} [{lo:.2f}, {hi:.2f}]"])
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
    # pooled McNemar for combined vs classic, and for the strict variant where every grid has it
    b = c = bs = cs = 0
    all_strict = all("combined (strict)" in res for res, _ in results.values())
    for grid, (res, types) in results.items():
        base, o = res["classic"][0], res["combined"][0]
        b += sum(1 for i in base if o[i] and not base[i]); c += sum(1 for i in base if base[i] and not o[i])
        if all_strict:
            os_ = res["combined (strict)"][0]
            bs += sum(1 for i in base if os_[i] and not base[i]); cs += sum(1 for i in base if base[i] and not os_[i])
    trow.append(["pooled", "combined vs classic", b, c, f"{binomtest(b, b + c, 0.5).pvalue if b + c else 1.0:.3f}"])
    if all_strict:
        trow.append(["pooled", "combined (strict) vs classic", bs, cs, f"{binomtest(bs, bs + cs, 0.5).pvalue if bs + cs else 1.0:.3f}"])
    import json
    (C.INTERIM / C.suffixed(f"mcnemar_pooled{a.tag}.json")).write_text(json.dumps({"b": b, "c": c, "bs": bs, "cs": cs, "all_strict": all_strict, "pooled": pooled}))
    other = C.INTERIM / f"mcnemar_pooled{a.tag}_{a.pool_with}.json"
    if S.variant() == "" and other.exists():
        o = json.loads(other.read_text())
        B, Cc = b + o["b"], c + o["c"]
        trow.append([f"recorded test days + {a.pool_with} day", "combined vs classic", B, Cc, f"{binomtest(B, B + Cc, 0.5).pvalue if B + Cc else 1.0:.5f}"])
        if all_strict and o.get("all_strict"):
            Bs, Cs = bs + o["bs"], cs + o["cs"]
            trow.append([f"recorded test days + {a.pool_with} day", "combined (strict) vs classic", Bs, Cs, f"{binomtest(Bs, Bs + Cs, 0.5).pvalue if Bs + Cs else 1.0:.5f}"])
        for name in pooled:
            k, n = pooled[name][0] + o["pooled"][name][0], pooled[name][1] + o["pooled"][name][1]
            lo, hi = wilson(k, n)
            prow.append([f"{name} (recorded days + split day v2)", f"{k}/{n}", f"{k / n:.2f} [{lo:.2f}, {hi:.2f}]"])
        body = body.replace("\n## Pooled over the grids\n\n", "\n## Pooled over the grids\n\n")
    body += "\n## Pooled over the grids\n\n" + C.md_table(["method family", "detected", "rate [95 % CI]"], prow)
    body += "\n## Paired tests (exact McNemar)\n\n" + C.md_table(["grid", "comparison", "only the first detects", "only the classic detects", "p (two-sided)"], trow)
    body += ("\nReading: with 16 to 23 process-attack instances per grid, intervals are wide; a difference of a few instances "
             "is not significant on one grid alone. The pooled test is the paper's main paired evidence.\n")
    C.write_report(f"statistics{a.tag}" + ("" if a.pool_with == "split" else f"_pooled_{a.pool_with}") + ".md", body)
    print(body[-1800:])


if __name__ == "__main__":
    main()
