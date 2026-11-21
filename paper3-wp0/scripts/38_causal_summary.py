"""Chronological rerun: effect of causal rule activation, the timing of every extra detection, and the
reconciliation of the library-alone count.

01-Basic: the full consolidation loop was rerun with --causal (scripts/causal_runs.sh): a rule acts only
after its alert window (60 s) has ended, the single synthesis worker is free, and its synthesis,
certification (wall clock) and any calibration are done. Because activation is later, a later alert can
stop being "covered by the library" and create a new rule, so the libraries themselves can differ.
02-Semiurban and 03-Rural: rules are created by topology appearance, not by alerts (no feedback), so the
causal library is the stored one acting from first appearance + logged certification time.
Counts per set: classic, library alone (as active at the time), library strict (active before the attack
starts), combined, combined strict; false-alarm episodes per benign hour. Original rows use the stored
runs (no tag); causal rows use _causal (01-Basic) or the latency-shifted library (SE grids).
The library-alone count in the paper (Table VII) is the strict variant on 01-Basic and the
persistence-filtered library on the SE grids; the audit report counted the non-strict 01-Basic library."""
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

PROCESS = ["control-and-freeze:control-and-freeze", "drift-off:drift-off", "industroyer:industroyer"]
SETTLE = 60.0


def setv(grid, v):
    if v:
        os.environ["P3_VARIANT"] = v
    else:
        os.environ.pop("P3_VARIANT", None)
    C.GRID = grid; E.use_grid(grid)


def ben_mask(t, ev):
    near = np.zeros(len(t), bool)
    for e in ev:
        if "benign" not in e["id"]:
            near |= (t >= e["start"] - SETTLE) & (t <= e.get("recovery", e["end"]) + SETTLE)
    return ~near


def eph(al, t, ben):
    fa = al & ben
    eps = int(np.sum(np.diff(np.r_[0, fa.astype(int)]) == 1)); hrs = ben.sum() * float(np.median(np.diff(t))) / 3600
    return eps, hrs


def basic(v, tag):
    setv("sherlock", v)
    ev = S.load_events(S.root(), "test")
    d = np.load(C.interim(f"consolidation_fires{tag}.npz"), allow_pickle=True); a = np.load(C.interim("detector_alarms_physics.npz"))
    t = d["t"]; D1 = a["D1"].astype(bool); det = d["det"].astype(bool); lib = d["lib_prior"].astype(bool)
    rf, added = d["rule_fires"].astype(bool), d["added_at"]
    att = [e for e in ev if e["description"] in PROCESS and "benign" not in e["id"]]
    o = {k: {} for k in ("classic", "library", "library strict", "combined", "combined strict")}
    for e in att:
        sel = (t >= e["start"]) & (t <= e.get("recovery", e["end"]))
        prior = added < e["start"]
        st = rf[prior].any(axis=0) if prior.any() else np.zeros(len(t), bool)
        for k, al in (("classic", D1), ("library", lib), ("library strict", st), ("combined", det | lib), ("combined strict", det | st)):
            o[k][e["id"]] = bool(al[sel].any())
    ben = ben_mask(t, ev)
    fa = {k: eph(al, t, ben) for k, al in (("classic", D1), ("library", lib), ("combined", det | lib))}
    return o, fa, len(added), d


def se(grid, v, causal):
    setv(grid, v)
    ev = S.load_events(S.root(), "test")
    d = np.load(C.interim("semiurban_fires.npz"), allow_pickle=True); sb = np.load(C.interim("se_residuals.npz"), allow_pickle=True)
    t = d["t"]; det = sb["alarm"].astype(bool); lib = d["fires_p"].astype(bool); added = d["added_t"].copy()
    if causal:
        rep = C.ROOT / "reports" / ("semiurban_consolidation_" + grid + (f"_{v}" if v else "") + ".md")
        lat = {m.group(2).strip(): float(m.group(4)) for m in re.finditer(r"^\| (\d+) \| (ties=[^|]+) \| ([^|]+) \| (\d+) \|", rep.read_text(), re.M)}
        import pickle
        rules = pickle.loads((C.INTERIM / C.suffixed("semiurban_rules.pkl")).read_bytes())["rules"]
        fs = sorted(set(added[np.isfinite(added)]))
        lt = {x: lat.get(c.label[:70].strip(), 0.0) for x, (c, _, _) in zip(fs, rules)}
        act = np.array([x + lt.get(x, 0.0) if np.isfinite(x) else np.inf for x in added])
        lib = lib & (t >= act)       # persistence runs restarting at activation are not re-applied: conservative only if
        added = act                  # a run straddles activation; counted as active from activation
    att = [e for e in ev if e["description"] in PROCESS and "benign" not in e["id"]]
    o = {k: {} for k in ("classic", "library", "library strict", "combined", "combined strict")}
    for e in att:
        sel = (t >= e["start"]) & (t <= e.get("recovery", e["end"]))
        st = lib & (added < e["start"])
        for k, al in (("classic", det), ("library", lib), ("library strict", st), ("combined", det | lib), ("combined strict", det | st)):
            o[k][e["id"]] = bool(al[sel].any())
    ben = ben_mask(t, ev)
    fa = {k: eph(al, t, ben) for k, al in (("classic", det), ("library", lib), ("combined", det | lib))}
    return o, fa


def cnt(o, k):
    return sum(o[k].values())


def main():
    C.parser(__doc__).parse_args()
    body = "# Chronological rerun: causal rule activation\n\n" + __doc__.split("\n\n", 1)[1] + "\n\n"
    rows, pooled = [], {}
    sets = [("01-Basic", "recorded", None, "basic"), ("02-Semiurban", "recorded", None, "semiurban"), ("03-Rural", "recorded", None, "rural"),
            ("01-Basic", "additional seed 7", "split", "basic"), ("02-Semiurban", "additional seed 7", "split", "semiurban")]
    for s_ in (8, 9, 10, 11):
        sets += [("01-Basic", f"additional seed {s_}", f"split_s{s_}", "basic"), ("02-Semiurban", f"additional seed {s_}", f"split_s{s_}", "semiurban")]
    for grid, day, v, kind in sets:
        for mode in ("original", "causal"):
            if kind == "basic":
                o, fa, nr, _ = basic(v, "" if mode == "original" else "_causal")
            else:
                o, fa = se(kind, v, mode == "causal"); nr = ""
            n = len(o["classic"])
            x = sum(o["library"][i] and not o["classic"][i] for i in o["classic"]); y = sum(o["classic"][i] and not o["library"][i] for i in o["classic"])
            rows.append([grid, day, mode, nr, f"{cnt(o, 'classic')}/{n}", f"{cnt(o, 'library')}/{n}", f"{cnt(o, 'library strict')}/{n}",
                         f"{cnt(o, 'combined')}/{n}", f"{cnt(o, 'combined strict')}/{n}", f"{x} / {y}",
                         f"{fa['classic'][0] / fa['classic'][1]:.2f}", f"{fa['library'][0] / fa['library'][1]:.2f}", f"{fa['combined'][0] / fa['combined'][1]:.2f}",
                         f"{fa['combined'][0]} in {fa['combined'][1]:.1f} h"])
            grp = "recorded" if day == "recorded" else ("additional seed 7" if day.endswith(" 7") else "other seeds")
            P = pooled.setdefault((grp, mode), {k: [0, 0] for k in ("classic", "library", "library strict", "combined", "combined strict")})
            for k in P:
                P[k][0] += cnt(o, k); P[k][1] += n
    body += C.md_table(["grid", "day", "run", "rules (01-Basic)", "classic", "library alone", "library strict", "combined", "combined strict",
                        "library vs classic: only library / only classic", "classic FA ep/h", "library FA ep/h", "combined FA ep/h", "combined FA episodes"], rows)
    pr = []
    for (grp, mode), P in pooled.items():
        pr.append([grp, mode] + [f"{P[k][0]}/{P[k][1]}" for k in P])
    for mode in ("original", "causal"):
        tot = {k: [pooled[("recorded", mode)][k][0] + pooled[("additional seed 7", mode)][k][0], pooled[("recorded", mode)][k][1] + pooled[("additional seed 7", mode)][k][1]] for k in pooled[("recorded", mode)]}
        pr.append(["recorded + additional seed 7 (paper's 103)", mode] + [f"{tot[k][0]}/{tot[k][1]}" for k in tot])
    body += "\n## Pooled\n\n" + C.md_table(["set", "run", "classic", "library alone", "library strict", "combined", "combined strict"], pr)
    body += ("\nReconciliation: the paper's library-alone count uses 'library strict' on 01-Basic and the persistence-filtered library on the "
             "SE grids; the audit report used the non-strict 01-Basic library. Both are shown above.\n")
    # timing of the extra detections on the recorded day (causal runs)
    tr = []
    _, _, _, d = basic(None, "_causal")
    setv("sherlock", None); ev = {e["id"]: e for e in S.load_events(S.root(), "test")}
    t0 = d["t"][0]; rt = d["rule_timing"]; names = d["rule_names"]; rf = d["rule_fires"].astype(bool); t = d["t"]
    a = np.load(C.interim("detector_alarms_physics.npz")); D1 = a["D1"].astype(bool)
    for eid, e in ev.items():
        if e["description"] not in PROCESS or "benign" in eid:
            continue
        sel = (t >= e["start"]) & (t <= e.get("recovery", e["end"]))
        if D1[sel].any():
            continue
        for k in range(len(names)):
            if rt[k, 4] < e["start"] and rf[k][sel].any():
                fa_ = t[sel][np.argmax(rf[k][sel])]
                tr.append(["01-Basic", eid, e["description"].split(":")[0], "(alert topology)", str(names[k])[:40], f"{rt[k, 1] - t0:.0f}", f"{rt[k, 2] - t0:.0f}",
                           "" if not np.isfinite(rt[k, 3]) else f"{rt[k, 3] - t0:.0f}", f"{rt[k, 4] - t0:.0f}", f"{e['start'] - t0:.0f}", f"{fa_ - e['start']:.0f}"])
                break
    setv("semiurban", None)
    dd = np.load(C.interim("semiurban_fires.npz"), allow_pickle=True); sb = np.load(C.interim("se_residuals.npz"), allow_pickle=True)
    rep = (C.ROOT / "reports" / "semiurban_consolidation_semiurban.md").read_text()
    lat = {m.group(2).strip(): float(m.group(4)) for m in re.finditer(r"^\| (\d+) \| (ties=[^|]+) \| ([^|]+) \| (\d+) \|", rep, re.M)}
    import pickle
    rules = pickle.loads((C.INTERIM / C.suffixed("semiurban_rules.pkl")).read_bytes())["rules"]
    t = dd["t"]; t0 = t[0]; added = dd["added_t"]; lib = dd["fires_p"].astype(bool); det = sb["alarm"].astype(bool)
    fs = sorted(set(added[np.isfinite(added)])); lab = {x: c.label for x, (c, _, _) in zip(fs, rules)}
    for e in S.load_events(S.root(), "test"):
        if e["description"] not in PROCESS or "benign" in e["id"]:
            continue
        sel = (t >= e["start"]) & (t <= e.get("recovery", e["end"]))
        act = np.array([x + lat.get(lab.get(x, "")[:70].strip(), 0.0) if np.isfinite(x) else np.inf for x in added])
        hit = lib & (act < e["start"]) & sel
        if det[sel].any() or not hit.any():
            continue
        i = np.argmax(hit); x = added[i]
        tr.append(["02-Semiurban", e["id"], e["description"].split(":")[0], lab[x][:45], f"SE rule #{fs.index(x)}", f"{x - t0:.0f} (topology first seen)",
                   f"{act[i] - t0:.0f}", "", f"{act[i] - t0:.0f}", f"{e['start'] - t0:.0f}", f"{t[i] - e['start']:.0f}"])
    body += "\n## Extra detections on the recorded days (classic misses, strict and causal), with timing (s from the start of the test day)\n\n"
    body += C.md_table(["grid", "event", "type", "topology", "rule", "synthesis window end", "synthesis + certification done", "calibration done",
                        "acts from", "attack start", "first alarm, s after start"], tr)
    os.environ.pop("P3_VARIANT", None); C.GRID = C.DEFAULT_GRID
    C.write_report("causal_summary.md", body)
    print(body)


if __name__ == "__main__":
    main()
