"""Improvement A1: reporting-robust margins (pre-registered in improvement_plan.md).

Every non-discrete atom of a rule is a weighted sum of readings, lhs = sum_j w_j m_j. If each
reading may lag by up to Delta seconds and is reported with deadband b_j, the reported lhs differs
from the synchronous one by at most
    sum_j |w_j| (V_j(t) + b_j),
where V_j(t) is the variation of reading j over the last Delta seconds (bounded here by the range of
its reported values over the last Delta + 1 records, which the control centre observes). The atom
margin is reduced by this amount, so the rule fires only when the inconsistency exceeds what
reporting alone can explain. The physics certificate concerns the static margin and is unchanged;
Delta and b are declared configuration values, not tuned on test data.

Evaluated on the 01-Basic test day: the library learned online (per-topology calibration), on the
recorded telemetry and under the reporting artifacts of the red team (`26_red_team.py`), with the
lag of each reading drawn exactly as in `14_consolidation.py --artifact` (fresh generator, seed+26).
Reported: library false alarms per benign record, process attacks detected by the library and by
detectors or library (detector alarms as computed on the recorded telemetry)."""
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import measure as M
from p3 import sherlock_io as S

sp = importlib.util.spec_from_file_location("rt26", Path(__file__).with_name("26_red_team.py"))
rt = importlib.util.module_from_spec(sp); sp.loader.exec_module(rt)


def window_range(Mx, w):
    """max - min of each column over the last w records (w = 1: zero)."""
    if w <= 1:
        return np.zeros_like(Mx)
    from numpy.lib.stride_tricks import sliding_window_view
    pad = np.vstack([np.repeat(Mx[:1], w - 1, axis=0), Mx])
    win = sliding_window_view(pad, w, axis=0)
    return np.nanmax(win, axis=-1) - np.nanmin(win, axis=-1)


def robust_rule_margin(rule, Mx, idx, V, B):
    best = np.full(len(Mx), -np.inf)
    for clause in (rule["any_of"] if "any_of" in rule else [rule["atoms"]]):
        ok = np.ones(len(Mx), bool); cm = np.full(len(Mx), np.inf)
        for a in clause:
            if a["type"] == "discrete":
                ok &= np.abs(Mx[:, idx[a["meas"]]] - a["value"]) < 1e-9
                continue
            coeffs = {a["meas"]: 1.0} if a["type"] == "threshold" else a["coeffs"]
            lhs = sum(w * Mx[:, idx[k]] for k, w in coeffs.items())
            slack = sum(abs(w) * (V[:, idx[k]] + B[idx[k]]) for k, w in coeffs.items())
            sc = float(a.get("scale", 1.0))
            am = (a["value"] - lhs - slack) / sc if a["op"] == "<" else (lhs - a["value"] - slack) / sc
            cm = np.minimum(cm, am)
        best = np.maximum(best, np.where(ok, cm, -1.0))
    return best


def fires(rules, added, Mx, T, idx, V, B):
    f = np.zeros(len(Mx), bool)
    for r, t0 in zip(rules, added):
        f |= (robust_rule_margin(r, Mx, idx, V, B) > 0) & (T >= t0)
    return f


def main():
    ap = C.parser(__doc__)
    ap.set_defaults(grid="sherlock")
    a = C.init(ap.parse_args())
    idx = M.index(); names = M.names()
    T, Mx = rt.records("test", 1)
    _, Mtr = rt.records("train", 10)
    ranges = np.nanmax(Mtr, axis=0) - np.nanmin(Mtr, axis=0)
    cols = [i for i, n in enumerate(names) if n.split(".")[0] in rt.ANALOG]
    ev = S.load_events(S.root(), "test")
    near = np.zeros(len(T), bool)
    for e in ev:
        if "benign" not in e["id"]:
            near |= (T >= e["start"] - 60) & (T <= e.get("recovery", e["end"]) + 60)
    benign = ~near
    att = [e for e in ev if "benign" not in e["id"] and e["description"] != "arp-spoof:arp-spoof-dos"]

    def lib(tag):
        rules = list(json.loads((C.ROOT / "rules" / C.suffixed(f"library{tag}.json")).read_text()).values())
        d = np.load(C.interim(f"consolidation_fires{tag}.npz"))
        return rules, d["added_at"], d["det"].astype(bool)

    def score(f, det):
        hit = lambda m: sum(bool(m[(T >= e["start"]) & (T <= e.get("recovery", e["end"]))].any()) for e in att)
        return f"{f[benign].mean():.5f}", f"{hit(f)}/{len(att)}", f"{hit(f | det)}/{len(att)}"

    zeroB = np.zeros(Mx.shape[1])
    rows = []
    cases = [("recorded telemetry", None, 0), ("latency 0 to 1 s", ("latency", 1), 0), ("latency 0 to 2 s", ("latency", 2), 0),
             ("latency 0 to 5 s", ("latency", 5), 0), ("deadband 0.5 %", ("deadband", 0.005), 0), ("deadband 1 %", ("deadband", 0.01), 0),
             ("deadband 2 %", ("deadband", 0.02), 0)]
    rules, added, det = lib("_tc")
    for label, art, _ in cases:
        if art is None:
            Mt, delta, B = Mx, 0, zeroB
        elif art[0] == "latency":
            Mt = rt.latency(Mx, cols, art[1], np.random.default_rng(a.seed + 26)); delta, B = art[1], zeroB
        else:
            Mt = rt.deadband(Mx, cols, art[1], ranges); delta = 0
            B = np.zeros(Mx.shape[1]); B[cols] = art[1] * ranges[cols]
        plain = fires(rules, added, Mt, T, idx, np.zeros_like(Mt), zeroB)
        robust = fires(rules, added, Mt, T, idx, window_range(Mt, delta + 1), B)
        rows.append([label, "clean day", *score(plain, det), *score(robust, det)])
        print(rows[-1])
    # robust margins with a declared Delta on the recorded telemetry: the cost of the protection
    for dlt in (1, 2, 5):
        robust = fires(rules, added, Mx, T, idx, window_range(Mx, dlt + 1), zeroB)
        rows.append([f"recorded telemetry, declared Delta = {dlt} s", "clean day", "⟨·⟩", "⟨·⟩", "⟨·⟩", *score(robust, det)])
        print(rows[-1])
    # library calibrated on a feed with the same artifact (14 --artifact) plus robust margins
    for tag, label, art in (("_tc_lat2", "latency 0 to 2 s", ("latency", 2)), ("_tc_db1", "deadband 1 %", ("deadband", 0.01))):
        rules2, added2, det2 = lib(tag)
        if art[0] == "latency":
            Mt = rt.latency(Mx, cols, 2, np.random.default_rng(a.seed + 26)); V = window_range(Mt, 3); B = zeroB
        else:
            Mt = rt.deadband(Mx, cols, 0.01, ranges); V = np.zeros_like(Mt); B = np.zeros(Mx.shape[1]); B[cols] = 0.01 * ranges[cols]
        plain = fires(rules2, added2, Mt, T, idx, np.zeros_like(Mt), zeroB)
        robust = fires(rules2, added2, Mt, T, idx, V, B)
        rows.append([label, "same feed", *score(plain, det2), *score(robust, det2)])
        print(rows[-1])
    body = "# Improvement A1: reporting-robust margins (01-Basic)\n\n" + __doc__.split("\n\n", 1)[1] + "\n\n"
    body += C.md_table(["telemetry", "margins calibrated on", "plain: library false alarms", "plain: library detects", "plain: detectors or library",
                        "robust: library false alarms", "robust: library detects", "robust: detectors or library"], rows)
    C.write_report("robust_margins.md", body)


if __name__ == "__main__":
    main()
