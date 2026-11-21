"""Provenance of the 01-Basic rule library: what each source alert episode contributed to a rule, and whether
the rule changed an alert decision in a later attack.

Inputs: the provenance replay `scripts/14_consolidation.py --causal --provenance --tag _prov` (same recording,
detectors D1 and AE, parameters and chronology as the reference run _causal), its structured log
(data/interim/provenance_prov_sherlock.pkl), the per-record detector alarms, and, for evaluation only, the
attack labels. For each rule: source episode, its window and the attack (if any) whose window contains it,
the inputs used to build the rule and where each component came from, timing, later opportunities, firing,
and whether the rule changed the system's decision (an attack detected by the rule and by no detector and no
other active rule). For the two credited rules: ablation (rule removed at scoring time, everything else kept)
and the false-alarm episodes the rule added. Counterfactual for G rules: the same topology, model, noise and
template with a seed that does not depend on the episode, certified and evaluated from the same activation
time. Also the five injected days (causal runs), without provenance log, for firing and decisive credit."""
import importlib.util
import json
import os
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import envelope as E
from p3 import sherlock_io as S
from p3 import synthesis as Y

PROCESS = ["control-and-freeze:control-and-freeze", "drift-off:drift-off", "industroyer:industroyer"]
OUT = C.ROOT / "reports" / "provenance"
SETTLE = 60.0


def setv(v):
    if v:
        os.environ["P3_VARIANT"] = v
    else:
        os.environ.pop("P3_VARIANT", None)
    C.GRID = "sherlock"; E.use_grid("sherlock")


def episodes_of(mask, t):
    st = np.where(np.diff(np.r_[0, mask.astype(int)]) == 1)[0]
    return st


def ben_mask(t, ev):
    near = np.zeros(len(t), bool)
    for e in ev:
        if "benign" not in e["id"]:
            near |= (t >= e["start"] - SETTLE) & (t <= e.get("recovery", e["end"]) + SETTLE)
    return ~near


def window(e):
    return e["start"], e.get("recovery", e["end"])


def source_event(ta, ev):
    for e in ev:
        if e["start"] - 1 <= ta <= window(e)[1]:
            return f"{e['id']} ({e['description'].split(':')[0]})"
    return "no labelled event (benign period)"


def per_rule(t, fires, act, det, ev, names, topo=None, topo_rec=None):
    """firing and decisive credit of every rule on later process attacks"""
    att = [e for e in ev if e["description"] in PROCESS and "benign" not in e["id"]]
    rows = []
    for k, nm in enumerate(names):
        later = [e for e in att if e["start"] > act[k]]
        opp, fired, decisive, earlier = [], [], [], []
        for e in later:
            a, b = window(e)
            sel = (t >= a) & (t <= b)
            if topo is not None and topo[k] is not None:
                if not any(topo_rec[i] == topo[k] for i in np.where(sel)[0]):
                    continue
            opp.append(e["id"])
            fk = fires[k] & sel & (t >= act[k])
            if fk.any():
                fired.append(e["id"])
                others = np.zeros(len(t), bool)
                for j in range(len(names)):
                    if j != k:
                        others |= fires[j] & (t >= act[j])
                if not (det & sel).any() and not (others & sel).any():
                    decisive.append(e["id"])
                elif (det & sel).any() and t[sel][np.argmax(fk[sel])] < t[sel][np.argmax((det & sel)[sel])]:
                    earlier.append(e["id"])
        rows.append({"rule": nm, "later_attacks": len(later), "opportunities": opp, "fired": fired, "decisive": decisive, "earlier_than_detectors": earlier})
    return rows


def main():
    C.parser(__doc__).parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    setv(None)
    P = pickle.loads((C.INTERIM / "provenance_prov_sherlock.pkl").read_bytes())
    t = P["t"]; t0 = t[0]
    a = np.load(C.interim("detector_alarms_physics.npz")); D1, AE = a["D1"].astype(bool), a["AE"].astype(bool)
    det = D1 | AE
    ev = S.load_events(S.root(), "test"); ben = ben_mask(t, ev)
    names = list(P["rules"]); fires = [P["fires"][k] for k in names]; act = [P["rules"][k]["added_at"] for k in names]
    ref = np.load(C.interim("consolidation_fires_causal.npz"), allow_pickle=True)
    same_lib = list(ref["rule_names"]) == names and all(np.array_equal(f, g) for f, g in zip(fires, ref["rule_fires"].astype(bool)))
    # topology per test record (for G opportunities)
    sp = importlib.util.spec_from_file_location("s14", Path(__file__).with_name("14_consolidation.py"))
    s14 = importlib.util.module_from_spec(sp); sp.loader.exec_module(s14)
    _, Mte = s14.records("test", 1)
    cidx = Y.config_index()
    topo_rec = [c.label if c is not None else None for c in (Y.record_config(m, cidx) for m in Mte)]
    topo = [P["rules"][k]["rule"].get("topology") if P["rules"][k]["family"] == "G" else None for k in names]
    pr = per_rule(t, fires, act, det, ev, names, topo, topo_rec)
    # traceability table
    eps = P["episodes"]
    trace = []
    for k, nm in enumerate(names):
        r = P["rules"][nm]; ep = eps[r["episode"]]; tm = r["timing"]
        fam = r["family"]
        if fam == "G":
            parts = r["parts_cert"]
            by_noise = sum(1 for p_ in parts if p_["noise"] >= p_["ac_bound"]); by_bound = len(parts) - by_noise
            content = (f"topology {r['rule']['topology']}; {len(parts)} quantities (bus voltages, line flows), each |m_q - a_q . injections - c_q| > m_q; "
                       f"margin from train noise on {by_noise}, from physics bound on {by_bound}; median margin "
                       f"{np.median([p_['margin'] for p_ in parts if p_['quantity'].startswith('vm')]):.4f} pu (voltage)")
            origin = "event: topology of the alert window (and the episode index sets the search seed); template, coefficients: linearised model of that topology; margins: train noise and oracle bound"
        else:
            si = ep.get("state_inputs", {})
            content = "; ".join(f"{m_}: {b:.3f} -> {x:.3f}" for m_, (b, x) in si.items())
            origin = "event: every atom (which lines went out, which injections dropped to zero) is read from the medians 40-10 s before the alert and in the 60 s alert window; thresholds (0.5 for line state, 1 % of scale for injections) are template"
        p = pr[k]
        trace.append([nm[:42], fam, r["episode"], f"{ep['t'] - t0:.0f}", source_event(ep["t"], ev), ep.get("topology", ""),
                      f"{tm[1] - t0:.0f}", f"{tm[2] - t0:.0f}", "" if not np.isfinite(tm[3]) else f"{tm[3] - t0:.0f}", f"{tm[4] - t0:.0f}",
                      p["later_attacks"], len(p["opportunities"]), ",".join(p["fired"]) or "-", ",".join(p["decisive"]) or "-",
                      ",".join(p["earlier_than_detectors"]) or "-", content, origin])
    # covered episodes
    cov = [[f"{e['t'] - t0:.0f}", source_event(e["t"], ev), ", ".join(x[:30] for x in e["covered_by"])] for e in eps if "covered_by" in e]
    # ablation and FA for decisive rules
    abl, fa_rows = [], []
    for k, nm in enumerate(names):
        others = det.copy()
        for j in range(len(names)):
            if j != k:
                others |= fires[j] & (t >= act[j])
        fk = fires[k] & (t >= act[k])
        for eid in pr[k]["decisive"]:
            e = next(x for x in ev if x["id"] == eid); a_, b_ = window(e); sel = (t >= a_) & (t <= b_)
            with_ = (others | fk)[sel]; wo = others[sel]
            abl.append([eid, e["description"].split(":")[0], nm[:42], f"{t[sel][np.argmax(with_)] - e['start']:.0f} s (this rule)",
                        "missed" if not wo.any() else f"{t[sel][np.argmax(wo)] - e['start']:.0f} s from another source"])
        bact = ben & (t >= act[k])
        bt = bact if topo[k] is None else bact & np.array([x == topo[k] for x in topo_rec])
        e_all = len(episodes_of(fk & ben, t)); e_add = len(episodes_of(fk & ben & ~det, t))
        fa_rows.append([nm[:42], e_all, e_add, f"{bact.sum() * 1 / 3600:.2f}", f"{bt.sum() / 3600:.2f}"])
    # counterfactual G
    cfr = []
    for k, nm in enumerate(names):
        cf = P["counterfactual"].get(nm)
        if cf is None:
            continue
        po, pa = P["rules"][nm]["parts_cert"], cf["parts_alt"] or []
        dm = [abs(x["margin"] - y["margin"]) / max(x["margin"], 1e-12) for x, y in zip(po, pa)] if pa else []
        fa_alt = cf["fires"] & (t >= act[k])
        rows_alt = per_rule(t, [fa_alt if j == k else (fires[j]) for j in range(len(names))], act, det, ev, names, topo, topo_rec)[k]
        cfr.append([nm[:42], "yes" if cf["same_seed_identical"] else "no", cf["verdict"], f"{sum(1 for x in dm if x > 1e-9)}/{len(dm)}",
                    f"{max(dm) * 100:.2f} %" if dm else "", ",".join(pr[k]["fired"]) or "-", ",".join(rows_alt["fired"]) or "-",
                    ",".join(pr[k]["decisive"]) or "-", ",".join(rows_alt["decisive"]) or "-",
                    f"{len(episodes_of(fires[k] & (t >= act[k]) & ben, t))} / {len(episodes_of(fa_alt & ben, t))}"])
    # injected days, causal runs
    inj = []
    for v, lab in (("split", 7), ("split_s8", 8), ("split_s9", 9), ("split_s10", 10), ("split_s11", 11)):
        setv(v)
        d = np.load(C.interim("consolidation_fires_causal.npz"), allow_pickle=True); aa = np.load(C.interim("detector_alarms_physics.npz"))
        evv = S.load_events(S.root(), "test"); dd = aa["D1"].astype(bool) | aa["AE"].astype(bool)
        rr = per_rule(d["t"], list(d["rule_fires"].astype(bool)), list(d["added_at"]), dd, evv, list(d["rule_names"]))
        for x in rr:
            inj.append([lab, str(x["rule"])[:42], x["later_attacks"], ",".join(x["fired"]) or "-", ",".join(x["decisive"]) or "-"])
    setv(None)
    res = {"same_library_as_reference": same_lib, "trace": trace, "covered": cov, "ablation": abl, "fa": fa_rows, "counterfactual": cfr, "injected": inj,
           "episodes": [{k_: v_ for k_, v_ in e.items()} for e in eps]}
    (OUT / "provenance.json").write_text(json.dumps(res, indent=1, default=str))
    body = "# Provenance of the 01-Basic rule library\n\n" + __doc__.split("\n\n", 1)[1] + "\n\n"
    body += f"Replay reproduces the reference library (_causal: same rule names and per-record firing): {'yes' if same_lib else 'NO'}.\n\n"
    body += "## 1. Traceability (s from the start of the test day)\n\n" + C.md_table(
        ["rule", "family", "episode #", "source alert start", "labelled attack containing the source (evaluation only)", "topology of the alert window",
         "synthesis window end", "synthesis + certification done", "calibration done", "acts from", "later process attacks", "opportunities (G: in its topology)",
         "fired in", "decisive in (no detector, no other rule)", "earlier than detectors in", "content", "where the content came from"], trace)
    body += "\n## 2. Alert episodes covered by an existing rule (no new synthesis)\n\n" + C.md_table(["episode start", "labelled attack containing it", "covering rule(s)"], cov)
    body += "\n## 3. Ablation of the decisive rule at scoring time\n\n" + C.md_table(["attack", "type", "rule", "first alarm with the rule", "without the rule (detectors D1, AE and all other rules kept)"], abl)
    body += "\n## 4. False-alarm episodes per rule after activation (benign records)\n\n" + C.md_table(["rule", "episodes", "episodes with no detector alarm", "benign hours active", "benign hours active in its topology"], fa_rows)
    body += "\n## 5. Counterfactual G rules: same topology, model, noise and template, seed independent of the episode, same activation time\n\n" + C.md_table(
        ["rule", "same seed rebuilds the identical candidate", "counterfactual verdict", "margins that differ", "largest relative margin difference",
         "original fired in", "counterfactual fired in", "original decisive in", "counterfactual decisive in", "false-alarm episodes original / counterfactual"], cfr)
    body += "\n## 6. Injected days (causal runs): firing and decisive credit per rule\n\n" + C.md_table(["seed", "rule", "later attacks", "fired in", "decisive in"], inj)
    (OUT / "provenance.md").write_text(body)
    print(body[:4000])


if __name__ == "__main__":
    main()
