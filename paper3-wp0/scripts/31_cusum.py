"""Improvement A3: temporal accumulation (CUSUM) on the certified residuals (01-Basic; pre-registered).

Each grid-wide rule holds, per quantity q, a clause pair q-part: w.m > c + mq and -w.m > -c + mq,
so the certified residual is e_t = w.m_t - c and the rule fires on a single record when |e_t| > mq.
Normalised z_t = |e_t| / mq. A one-sided CUSUM per quantity,
    S_t = max(0, S_{t-1} + z_t - kappa_q)   (reset when the rule's topology guard is false),
alarms when S_t > h_q. kappa_q = 99th percentile and h_q = 1.5 x the largest S over calibration
records: the attack-free training records in the rule's topology when it has at least 300 of them,
otherwise the first 300 s of test records in that topology without a detector alarm (the online
calibration of the main loop). No test label is used. A rule's CUSUM acts from the time the rule
acts. The guarantee is calibrated, not certified.
Stealth budget: a constant offset o on quantity q is flagged within 600 s if
o >= mq (kappa_q + h_q / 600); compared with the single-record margin mq."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import measure as M
from p3 import sherlock_io as S

import importlib.util
_sp = importlib.util.spec_from_file_location("rt26", Path(__file__).with_name("26_red_team.py"))
rt = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(rt)


def quantities(rule):
    """(guard atoms, list of (name, weights dict, c, m)) of a grid-wide rule."""
    guard, pairs = None, {}
    for clause in rule.get("any_of", []):
        disc = [a for a in clause if a["type"] == "discrete"]
        guard = guard or disc
        for a in clause:
            if a["type"] != "linear":
                continue
            tgt = [k for k, w in a["coeffs"].items() if abs(abs(w) - 1.0) < 1e-12 and k.split(".")[0] in ("vm_pu", "p_from")]
            if tgt:
                pairs.setdefault(tgt[0], []).append(a)
    out = []
    for q, ats in pairs.items():
        if len(ats) != 2:
            continue
        plus = ats[0] if ats[0]["coeffs"][q] > 0 else ats[1]
        minus = ats[1] if plus is ats[0] else ats[0]
        m = (plus["value"] + minus["value"]) / 2; c = (plus["value"] - minus["value"]) / 2
        if m > 0:
            out.append((q, plus["coeffs"], c, m))
    return guard or [], out


def guard_mask(guard, Mx, idx):
    g = np.ones(len(Mx), bool)
    for a in guard:
        g &= np.abs(Mx[:, idx[a["meas"]]] - a["value"]) < 1e-9
    return g


def zmat(qs, Mx, idx):
    return np.column_stack([np.abs(sum(w * Mx[:, idx[k]] for k, w in coeffs.items()) - c) / m for _, coeffs, c, m in qs])


def cusum(Z, mask, kappa):
    S = np.zeros_like(Z); s = np.zeros(Z.shape[1])
    for i in range(len(Z)):
        s = np.maximum(0.0, s + Z[i] - kappa) if mask[i] else np.zeros_like(s)
        S[i] = s
    return S


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--tag", default="_tc")
    ap.add_argument("--kappa-fixed", type=float, default=None, help="EXPLORATORY (post hoc): kappa fixed at this fraction of the margin for every quantity")
    ap.set_defaults(grid="sherlock")
    a = C.init(ap.parse_args())
    idx = M.index()
    lib = json.loads((C.ROOT / "rules" / C.suffixed(f"library{a.tag}.json")).read_text())
    d = np.load(C.interim(f"consolidation_fires{a.tag}.npz"))
    added, det, lib_prior = d["added_at"], d["det"].astype(bool), d["lib_prior"].astype(bool)
    T, Mx = rt.records("test", 1)
    Ttr, Mtr = rt.records("train", 1)
    assert np.allclose(T, d["t"])
    cus = np.zeros(len(T), bool)
    budget = []
    for (name, rule), t0 in zip(lib.items(), added):
        guard, qs = quantities(rule)
        if not qs:
            continue
        g_te = guard_mask(guard, Mx, idx)
        g_tr = guard_mask(guard, Mtr, idx)
        if g_tr.sum() >= 300:
            Zc = zmat(qs, Mtr[g_tr], idx); act_from = t0
        else:
            cal = np.where(g_te & ~det)[0][:300]
            if len(cal) < 300:
                continue
            Zc = zmat(qs, Mx[cal], idx); act_from = max(t0, T[cal[-1]])
        kappa = np.nanpercentile(Zc, 99, axis=0) if a.kappa_fixed is None else np.full(len(qs), a.kappa_fixed)
        h = np.maximum(1.5 * np.nanmax(cusum(Zc, np.ones(len(Zc), bool), kappa), axis=0), 0.5)
        Z = zmat(qs, Mx, idx)
        Sx = cusum(Z, g_te, kappa)
        cus |= (Sx > h).any(axis=1) & (T >= act_from)
        for (q, _, _, m), k_, h_ in zip(qs, kappa, h):
            budget.append((q.split(".")[0], m, m * (k_ + h_ / 600.0)))
    ev = S.load_events(S.root(), "test")
    near = np.zeros(len(T), bool)
    for e in ev:
        if "benign" not in e["id"]:
            near |= (T >= e["start"] - 60) & (T <= e.get("recovery", e["end"]) + 60)
    ben = ~near
    att = [e for e in ev if "benign" not in e["id"] and e["description"] != "arp-spoof:arp-spoof-dos"]

    def det_by(f):
        per = {}
        for e in att:
            hit = bool(f[(T >= e["start"]) & (T <= e.get("recovery", e["end"]))].any())
            k = e["description"].split(":")[0]
            per.setdefault(k, [0, 0]); per[k][0] += int(hit); per[k][1] += 1
        return ", ".join(f"{k} {v[0]}/{v[1]}" for k, v in sorted(per.items()))
    rows = []
    for lab, f in (("library, single record", lib_prior), ("CUSUM on certified residuals", cus), ("library or CUSUM", lib_prior | cus),
                   ("detectors or library", det | lib_prior), ("detectors or library or CUSUM", det | lib_prior | cus)):
        rows.append([lab, f"{f[ben].mean():.5f}", det_by(f)])
        print(rows[-1])
    near_zero = []
    for e in att:
        p = e.get("params", {})
        if e["description"].startswith("drift-off") and abs(p.get("final_offset_pu", 1.0)) < 0.005:
            sel = (T >= e["start"]) & (T <= e.get("recovery", e["end"]))
            near_zero.append([e["id"], f"{p['final_offset_pu']:+.4f}", "yes" if lib_prior[sel].any() else "no", "yes" if cus[sel].any() else "no"])
    brow = []
    for k, unit in (("vm_pu", "pu"), ("p_from", "MW")):
        v = np.array([(m, o) for q, m, o in budget if q == k])
        if len(v):
            brow.append([k, unit, len(v), f"{np.median(v[:, 0]):.4f}", f"{np.median(v[:, 1]):.4f}", f"{np.median(v[:, 1] / v[:, 0]):.2f}"])
    body = "# Improvement A3: CUSUM on certified residuals (01-Basic)\n\n" + __doc__.split("\n\n", 1)[1] + "\n\n"
    body += f"Library `library{a.tag}`, test day `{S.root().name}` ({S.variant() or 'recorded'}).\n\n"
    body += C.md_table(["alarm source", "false alarms per benign record", "process attacks detected"], rows)
    if near_zero:
        body += "\nNear-zero drift-off instances (injected, additional day):\n\n" + C.md_table(["id", "final offset pu", "library", "CUSUM"], near_zero)
    body += "\nStealth budget (constant offset flagged within 600 s, medians over quantities):\n\n" + C.md_table(
        ["quantity", "unit", "quantities", "single-record margin", "CUSUM, 600 s", "ratio"], brow)
    if a.kappa_fixed is not None:
        body = body.replace("# Improvement A3", f"# EXPLORATORY (post hoc, kappa = {a.kappa_fixed}) Improvement A3")
    C.write_report(f"cusum{a.tag}" + ("" if a.kappa_fixed is None else f"_k{int(a.kappa_fixed * 100)}") + ".md", body)


if __name__ == "__main__":
    main()
