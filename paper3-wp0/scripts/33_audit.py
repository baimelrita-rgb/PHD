"""Reproduction audit (pre-submission): event-level reconstruction and the A/B/C ablation.

Part 1, frozen scoring protocol and event table. For every process-attack instance of the recorded
test days (01-Basic, 02-Semiurban, 03-Rural) and of the main additional day (seed 7, 01-Basic and
02-Semiurban), the outcome of every detector and rule source is recomputed from the saved per-record
alarms, with the first alarm time and the activation time of the library rule. Strict credit is given
three ways: (a) as in the paper (rule learned or topology first met before the attack start),
(b) as (a) plus the measured certification compute time (the rule only acts once certification has
finished; 02-Semiurban and 03-Rural, where the replay itself applies the rule from the first record of
its topology), (c) first detection inside the recovery phase only, flagged.

Part 2, A/B/C on 02-Semiurban (recorded day and additional day). One state estimator, one residual
matrix (scripts/17), one candidate stream (one rule per topology, in order of first appearance), the
same persistence L and the same scoring:
  A  SE-BDD: one global threshold on max_i |r_i| (scripts/17), as published;
  B  per-channel, per-topology thresholds without the oracle: m_i = k x noise_i (noise_i as in
     scripts/18: train maximum, floored per measurement kind);
  C  B plus the physics check: m_i = max(k x noise_i, the proved margin part) taken from the stored
     rules of scripts/18 --prove (1.5 x the affine bound plus remainder).
Since C >= B channel by channel, C fires on a subset of B's records: C - B can only remove alarms.
Operating points: (i) the original k = 1.5; (ii) a matched false-alarm budget chosen on calibration
data only: noise recalibrated on the first half of the training records, k chosen as the smallest value
on a fixed grid whose false-alarm episodes per benign hour on the second half of the training records is
at most the target (fixed in advance: 0.5 episodes per hour), separately for B and C, frozen, then
applied to the test day with noise from the full training records. The full test-day curve over k is
reported as a description, not used for selection."""
import csv
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
from scipy.stats import binomtest

from p3 import common as C
from p3 import envelope as E
from p3 import sherlock_io as S

_sp = importlib.util.spec_from_file_location("st20", Path(__file__).with_name("20_statistics.py"))
st20 = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(st20)
PROCESS = st20.PROCESS
OUT = C.ROOT / "reports" / "audit"
K_GRID = [1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0, 10.0, 15.0, 20.0]
TARGET_EPH = 0.5          # fixed before running: false-alarm episodes per benign hour on calibration data
SETTLE = 60.0


def setgrid(grid, variant):
    if variant:
        os.environ["P3_VARIANT"] = variant
    else:
        os.environ.pop("P3_VARIANT", None)
    C.GRID = grid; E.use_grid(grid)


def runs(mask, L):
    out, c = np.zeros(len(mask), int), 0
    for i, x in enumerate(mask):
        c = c + 1 if x else 0
        out[i] = c
    return out >= L


def benign_mask(t, ev):
    near = np.zeros(len(t), bool)
    for e in ev:
        if "benign" not in e["id"]:
            near |= (t >= e["start"] - SETTLE) & (t <= e.get("recovery", e["end"]) + SETTLE)
    return ~near


def fa_stats(alarm, t, ben):
    fa = alarm & ben
    eps = int(np.sum(np.diff(np.r_[0, fa.astype(int)]) == 1))
    hours = ben.sum() * float(np.median(np.diff(t))) / 3600
    return fa[ben].mean() if ben.any() else float("nan"), eps, hours


def first(alarm, t, e):
    sel = (t >= e["start"]) & (t <= e.get("recovery", e["end"]))
    if not alarm[sel].any():
        return None, None
    i = np.argmax(alarm[sel]); tt = t[sel][i]
    return float(tt - e["start"]), bool(tt > e["end"])


def cert_latency(report):
    """compute seconds per topology label, from the on-demand certification log of scripts/18."""
    lat = {}
    txt = (C.ROOT / "reports" / report).read_text()
    for m in re.finditer(r"^\| (\d+) \| (ties=[^|]+) \| ([^|]+) \| (\d+) \|", txt, re.M):
        lat[m.group(2).strip()] = float(m.group(4))
    return lat


# ------------------------------------------------------------------ part 1
def events_basic(variant, day):
    setgrid("sherlock", variant)
    ev = S.load_events(S.root(), "test")
    d = np.load(C.interim("consolidation_fires.npz"))
    a = np.load(C.interim("detector_alarms_physics.npz"))
    t = d["t"]; assert np.allclose(t, a["t"])
    rf, added = d["rule_fires"].astype(bool), d["added_at"]
    lib = d["lib_prior"].astype(bool); D1 = a["D1"].astype(bool); AE = a["AE"].astype(bool)
    comb = D1 | AE | lib
    rows = []
    for e in ev:
        if e["description"] not in PROCESS or "benign" in e["id"]:
            continue
        prior = added < e["start"]
        strict = rf[prior].any(axis=0) if prior.any() else np.zeros(len(t), bool)
        r = {"grid": "01-Basic", "day": day, "seed": 7 if variant else "", "id": e["id"], "type": e["description"].split(":")[0],
             "start": e["start"], "end": e["end"], "recovery": e.get("recovery", e["end"])}
        for nm, al in (("classic D1", D1), ("AE", AE), ("library", lib), ("library strict", strict), ("combined", comb),
                       ("combined strict", D1 | AE | strict)):
            dt, rec = first(al, t, e)
            r[nm] = "" if dt is None else f"{dt:.0f}" + (" (recovery)" if rec else "")
        rules_hit = [k for k in range(len(added)) if rf[k][(t >= e["start"]) & (t <= r["recovery"])].any()]
        r["rules firing (learned at s)"] = "; ".join(f"R{k}@{added[k] - t[0]:.0f}" for k in rules_hit)
        r["source of combined-only credit"] = ""
        if r["combined"] and not r["classic D1"]:
            r["source of combined-only credit"] = "+".join(s for s, k in (("AE", "AE"), ("library", "library")) if r[k])
        rows.append(r)
    ben = benign_mask(t, ev)
    fa = {nm: fa_stats(al, t, ben) for nm, al in (("classic D1", D1), ("AE", AE), ("library", lib), ("combined", comb))}
    return rows, fa


def events_se(grid, variant, day, report):
    setgrid(grid, variant)
    ev = S.load_events(S.root(), "test")
    d = np.load(C.interim("semiurban_fires.npz"), allow_pickle=True)
    sb = np.load(C.interim("se_residuals.npz"), allow_pickle=True)
    t = d["t"]; det = sb["alarm"].astype(bool); lib = d["fires_p"].astype(bool); added = d["added_t"]
    lat = cert_latency(report)
    rules = __import__("pickle").loads((C.INTERIM / C.suffixed("semiurban_rules.pkl")).read_bytes())["rules"]
    first_seen = sorted(set(added[np.isfinite(added)]))
    assert len(first_seen) == len(rules), (len(first_seen), len(rules))
    lat_by_t = {ft: lat.get(cfg.label[:70].strip(), lat.get(cfg.label.strip(), np.nan)) for ft, (cfg, _, _) in zip(first_seen, rules)}
    active = added + np.array([lat_by_t.get(x, 0.0) if np.isfinite(x) else np.inf for x in added])
    lib_lat = lib & (active <= t)          # rule acts only once certification compute has finished
    rows = []
    for e in ev:
        if e["description"] not in PROCESS or "benign" in e["id"]:
            continue
        sel = (t >= e["start"]) & (t <= e.get("recovery", e["end"]))
        strict_p = lib & (added < e["start"])
        strict_l = lib & (active < e["start"])
        r = {"grid": "02-Semiurban" if grid == "semiurban" else "03-Rural", "day": day, "seed": 7 if variant else "", "id": e["id"],
             "type": e["description"].split(":")[0], "start": e["start"], "end": e["end"], "recovery": e.get("recovery", e["end"])}
        for nm, al in (("classic SE-BDD", det), ("library", lib), ("library strict (paper)", strict_p),
                       ("library strict (+cert latency)", strict_l), ("combined", det | lib), ("combined strict (+cert latency)", det | strict_l)):
            dt, rec = first(al, t, e)
            r[nm] = "" if dt is None else f"{dt:.0f}" + (" (recovery)" if rec else "")
        tops = sorted(set(added[sel][np.isfinite(added[sel])]))
        r["topology rule first seen / active (s)"] = "; ".join(f"{x - t[0]:.0f}/{x + lat_by_t.get(x, 0) - t[0]:.0f}" for x in tops)
        r["source of combined-only credit"] = "library" if (r["combined"] and not r["classic SE-BDD"]) else ""
        rows.append(r)
    ben = benign_mask(t, ev)
    fa = {nm: fa_stats(al, t, ben) for nm, al in (("classic SE-BDD", det), ("library", lib), ("library (+cert latency)", lib_lat), ("combined", det | lib))}
    return rows, fa


# ------------------------------------------------------------------ part 2
def noise_from(R, kinds):
    noise = np.nanmax(np.abs(R), axis=0)
    noise = np.where(np.isfinite(noise), noise, np.nanmax(noise))
    p999 = np.nanpercentile(np.abs(R), 99.9, axis=0)
    floor = {k: float(np.nanmedian(p999[kinds == k])) for k in set(kinds)}
    return np.maximum(noise, np.array([floor[k] for k in kinds]))


def abc(variant, day):
    setgrid("semiurban", variant)
    ev = S.load_events(S.root(), "test")
    sb = np.load(C.interim("se_residuals.npz"), allow_pickle=True)
    d = np.load(C.interim("semiurban_fires.npz"), allow_pickle=True)
    rules = __import__("pickle").loads((C.INTERIM / C.suffixed("semiurban_rules.pkl")).read_bytes())["rules"]
    obs = list(sb["obs"]); kinds = np.array([n.split(".")[0] for n in obs])
    Ttr, Rtr, Tte, Rte, det, L = sb["train_t"], sb["train_R"], sb["test_t"], sb["test_R"], sb["alarm"].astype(bool), int(sb["L"])
    added = d["added_t"]; t = Tte
    first_seen = sorted(set(added[np.isfinite(added)]))
    topo = np.array([first_seen.index(x) if np.isfinite(x) else -1 for x in added])
    noise = noise_from(Rtr, kinds)
    Cm = np.vstack([m for _, m, _ in rules])                    # stored proved margins per topology
    assert np.allclose(Cm.min(axis=0) * 0 + Cm, Cm)
    bound_part = np.where(Cm > 1.5 * noise * (1 + 1e-9), Cm, 0.0)   # channels where the physics bound set the margin
    ratio = np.abs(Rte)

    def fires(margins):                                         # margins: (topologies, channels)
        f = np.zeros(len(t), bool)
        for k in range(len(rules)):
            sel = topo == k
            if sel.any():
                f[sel] = np.nanmax(ratio[sel] / margins[k], axis=1) > 1.0
        return runs(f, L)
    # sanity: C at k = 1.5 reproduces the stored library alarms
    C15 = fires(np.maximum(1.5 * noise[None, :], bound_part))
    repro = bool(np.array_equal(C15, d["fires_p"].astype(bool)))
    ben = benign_mask(t, ev)
    att = [e for e in ev if e["description"] in PROCESS and "benign" not in e["id"]]

    def score(al):
        out = {e["id"]: bool(al[(t >= e["start"]) & (t <= e.get("recovery", e["end"]))].any()) for e in att}
        r, eps, hrs = fa_stats(al, t, ben)
        return out, r, eps, hrs

    # matched budget on calibration only: noise on first half of train, choose k on second half
    h = len(Ttr) // 2
    n1 = noise_from(Rtr[:h], kinds)
    tr_ben = np.ones(len(Ttr) - h, bool)
    # topology of training records is not stored; the training day's SE residual is per its own topology,
    # so the calibration uses the same per-channel margins for every training record (B: k x noise;
    # C: max(k x noise, the largest proved bound part over test topologies seen, per channel, as a
    # conservative stand-in for the training topologies' bound)
    Rcal = np.abs(Rtr[h:]); Tcal = Ttr[h:]
    bp_max = bound_part.max(axis=0)

    def cal_eph(margin_vec):
        f = runs(np.nanmax(Rcal / margin_vec, axis=1) > 1.0, L)
        _, eps, hrs = fa_stats(f, Tcal, tr_ben)
        return eps / hrs if hrs else float("nan")
    pick = {}
    for nm, mk in (("B", lambda k: k * n1), ("C", lambda k: np.maximum(k * n1, bp_max))):
        curve = [(k, cal_eph(mk(k))) for k in K_GRID]
        ok = [k for k, v in curve if v <= TARGET_EPH]
        pick[nm] = (min(ok) if ok else None, curve)
    variants = {"A SE-BDD (global threshold)": det}
    for k in sorted(set([1.5] + [v[0] for v in pick.values() if v[0] is not None])):
        variants[f"B per-channel, k = {k:g}"] = fires(np.repeat((k * noise)[None, :], len(rules), axis=0))
        variants[f"C per-channel + physics check, k = {k:g}"] = fires(np.maximum(k * noise[None, :], bound_part))
    res = {nm: score(al) for nm, al in variants.items()}
    curve = []
    for k in K_GRID:
        for nm, mg in (("B", np.repeat((k * noise)[None, :], len(rules), axis=0)), ("C", np.maximum(k * noise[None, :], bound_part))):
            out, r, eps, hrs = score(fires(mg))
            curve.append([day, nm, k, f"{sum(out.values())}/{len(out)}", f"{r:.5f}", f"{eps / hrs:.2f}"])
    # rules the physics check changed: channels whose margin was raised, per topology
    raised = [(cfg.label, int((bound_part[k] > 0).sum()), float(np.nanmedian(np.where(bound_part[k] > 0, bound_part[k] / (1.5 * noise), np.nan))))
              for k, (cfg, _, _) in enumerate(rules)]
    return {"day": day, "repro": repro, "res": res, "att": att, "pick": pick, "curve": curve, "raised": raised,
            "L": L, "th": float(sb["th"]), "n_topo": len(rules), "C15": C15}


def mcn(a, b):
    ids = list(a)
    x = sum(a[i] and not b[i] for i in ids); y = sum(b[i] and not a[i] for i in ids)
    p = binomtest(x, x + y, 0.5).pvalue if x + y else 1.0
    return x, y, p


def main():
    C.parser(__doc__).parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    body = "# Reproduction audit: event table and A/B/C ablation\n\n" + __doc__.split("\n\n", 1)[1] + "\n\n"
    # ---------- protocol
    proto = {"process attack types": PROCESS, "attack window": "start to recovery (end if no recovery)",
             "benign records": f"more than {SETTLE:.0f} s from any non-benign event window (start - 60 s to recovery + 60 s)",
             "false-alarm episode": "maximal run of consecutive alarmed benign records",
             "01-Basic": "1 Hz records; combined = D1 or AE (alert source) or library rules active at the time; classic = D1",
             "02-Semiurban / 03-Rural": "every 5th record (5 s); persistence L = 3 records for SE-BDD and library; classic = SE-BDD",
             "strict (paper)": "01-Basic: rule learned before attack start; SE grids: topology first met before attack start",
             "strict (+cert latency)": "SE grids: topology first met + measured certification compute time before attack start",
             "Sherlock alarm-start metric": "computed separately in scripts/24 (Table IX); not used here",
             "post hoc choices": ["03-Rural noise mode 'global' (margins floored at the transferred SE-BDD threshold), chosen after the per-kind transfer gave 0.723 false alarms",
                                  "01-Basic split day: tap range padded after an unseen tap position stopped synthesis",
                                  "02-Semiurban: margins raised to the affine bound after corner counterexamples (gate of 80 % had failed)",
                                  "additional-day attack model v2 after measuring real attack magnitudes"]}
    (OUT / "frozen_protocol.json").write_text(json.dumps(proto, indent=1))
    # ---------- event table
    rows, fas = [], {}
    r_, f_ = events_basic(None, "recorded"); rows += r_; fas["01-Basic recorded"] = f_
    r_, f_ = events_se("semiurban", None, "recorded", "semiurban_consolidation_semiurban.md"); rows += r_; fas["02-Semiurban recorded"] = f_
    r_, f_ = events_se("rural", None, "recorded", "semiurban_consolidation_rural.md"); rows += r_; fas["03-Rural recorded"] = f_
    r_, f_ = events_basic("split", "additional (seed 7)"); rows += r_; fas["01-Basic additional"] = f_
    r_, f_ = events_se("semiurban", "split", "additional (seed 7)", "semiurban_consolidation_semiurban_split.md"); rows += r_; fas["02-Semiurban additional"] = f_
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(OUT / "event_table.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(rows)
    # reference totals
    def cls(r):
        return bool(r.get("classic D1") or r.get("classic SE-BDD"))
    tot = []
    for lab, sel in (("recorded", lambda r: r["day"] == "recorded"), ("additional (seed 7)", lambda r: r["day"] != "recorded"), ("pooled", lambda r: True)):
        rs = [r for r in rows if sel(r)]
        c = sum(cls(r) for r in rs); cb = sum(bool(r["combined"]) for r in rs)
        cbs = sum(bool(r.get("combined strict") or r.get("combined strict (+cert latency)")) for r in rs)
        lb = sum(bool(r["library"]) for r in rs)
        x = sum(bool(r["library"]) and not cls(r) for r in rs); y = sum(cls(r) and not r["library"] for r in rs)
        pl = binomtest(x, x + y, 0.5).pvalue if x + y else 1.0
        tot.append([lab, len(rs), f"{c}/{len(rs)}", f"{lb}/{len(rs)}", f"{cb}/{len(rs)}", f"{cbs}/{len(rs)}", f"{x} / {y}, p = {pl:.4f}"])
    body += "## 1. Reference totals reproduced from the saved alarms\n\n"
    body += C.md_table(["set", "instances", "classic", "library alone", "combined", "combined strict (SE grids: + certification latency)",
                        "library vs classic: only library / only classic, exact McNemar"], tot)
    extra = [[r["grid"], r["day"], r["id"], r["type"], r["source of combined-only credit"], r.get("rules firing (learned at s)", r.get("topology rule first seen / active (s)", "")),
              r.get("library strict") or r.get("library strict (+cert latency)") or "no credit"]
             for r in rows if r["source of combined-only credit"]]
    body += "\n## 2. Instances only the combined system detects (classic misses), with the source of the credit\n\n"
    body += C.md_table(["grid", "day", "event id", "type", "source", "rules / topology timing", "strict first alarm s after start"], extra)
    fr = []
    for k, v in fas.items():
        for nm, (rate, eps, hrs) in v.items():
            fr.append([k, nm, f"{rate:.5f}", eps, f"{hrs:.2f}", f"{eps / hrs:.2f}"])
    body += "\n## 3. Benign exposure and false alarms\n\n" + C.md_table(["set", "source", "false alarms per benign record", "episodes", "benign hours", "episodes per hour"], fr)
    # ---------- A/B/C
    body += "\n## 4. A/B/C ablation on 02-Semiurban\n\n"
    for variant, day in ((None, "recorded"), ("split", "additional (seed 7)")):
        R = abc(variant, day)
        body += f"### {day}\n\nC at k = 1.5 reproduces the stored library alarms: {'yes' if R['repro'] else 'NO'}. Topologies {R['n_topo']}, persistence L = {R['L']}, SE-BDD threshold {R['th']:.2f}.\n\n"
        rows_ = []
        base = R["res"]["A SE-BDD (global threshold)"][0]
        for nm, (out, rate, eps, hrs) in R["res"].items():
            k = sum(out.values()); n = len(out)
            per = {}
            for e in R["att"]:
                per.setdefault(e["description"].split(":")[0], [0, 0]); per[e["description"].split(":")[0]][0] += out[e["id"]]; per[e["description"].split(":")[0]][1] += 1
            x, y, p = mcn(out, base)
            rows_.append([nm, f"{k}/{n}", ", ".join(f"{a} {v[0]}/{v[1]}" for a, v in sorted(per.items())), f"{rate:.5f}", f"{eps / hrs:.2f}", f"{x} / {y}, p = {p:.3f}" if nm[0] != "A" else ""])
        body += C.md_table(["variant", "detected", "per type", "false alarms per benign record", "episodes per benign hour", "vs A: only this / only A, McNemar"], rows_)
        names = list(R["res"])
        pairs = []
        for k in sorted(set(float(n.split("k = ")[1]) for n in names if "k = " in n)):
            b = R["res"][f"B per-channel, k = {k:g}"]; c = R["res"][f"C per-channel + physics check, k = {k:g}"]
            changed = [e for e in b[0] if b[0][e] != c[0][e]]
            pairs.append([f"{k:g}", f"{sum(c[0].values()) - sum(b[0].values()):+d}", ", ".join(changed) or "none",
                          f"{c[1] - b[1]:+.5f}", f"{c[2] / c[3] - b[2] / b[3]:+.2f}"])
        body += "\nC minus B at the same k (same candidates, same calibration; only the physics check differs):\n\n"
        body += C.md_table(["k", "detected (C - B)", "instances whose outcome changed", "false alarms per record (C - B)", "episodes per hour (C - B)"], pairs)
        body += f"\nMatched budget, chosen on calibration data only (target {TARGET_EPH} false-alarm episodes per hour on the second half of the training records, noise from the first half): "
        body += "; ".join(f"{nm}: k = {v[0]}" if v[0] is not None else f"{nm}: no k on the grid meets the target" for nm, v in R["pick"].items()) + ".\n\n"
        body += "Calibration curves (episodes per hour on the calibration half, by k): " + "; ".join(
            f"{nm}: " + ", ".join(f"{k:g}:{v:.2f}" for k, v in c[1]) for nm, c in R["pick"].items()) + "\n\n"
        body += "Test-day curve over k (description only, not used to choose anything):\n\n" + C.md_table(["day", "variant", "k", "detected", "false alarms per record", "episodes per hour"], R["curve"])
        body += "\nChannels whose margin the physics check raised above 1.5 x noise, per topology (median ratio proved margin / (1.5 x noise)):\n\n"
        body += C.md_table(["topology", "channels raised", "median ratio"], [[a[:60], b, f"{c:.2f}"] for a, b, c in R["raised"]])
    C.GRID = C.DEFAULT_GRID; os.environ.pop("P3_VARIANT", None)
    (OUT / "audit.md").write_text(body)
    print(body)


if __name__ == "__main__":
    main()
