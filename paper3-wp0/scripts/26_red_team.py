"""Red-team checks on the deployed 01-Basic library (rules learned online, with per-topology calibration).

(A) SCADA reporting artifacts (power-systems reviewer). Sherlock's telemetry is a synchronous
    snapshot of a steady-state co-simulation; real SCADA reports with latency and deadbands. The
    library learned on the recorded day is evaluated, unchanged, on the benign test records with
    artifacts applied to every analog measurement (voltages, flows, loadings, injections):
      latency  - each measurement lags by a fixed random 0..D records (seeded), D in {1, 2, 5} s;
      deadband - a measurement is re-reported only when it moves by more than a fraction of its
                 training range since its last report, fraction in {0.5, 1, 2} %.
    Switch, line and tap states are not altered. Reported: false alarms per benign record (more
    than 60 s from any attack), rules acting from the time they were learned, as in the main runs.

(B) Stealth budget (security reviewer). An attacker who knows the library can falsify a reading
    by up to its margin without firing a rule. The margin of every voltage and line-flow clause
    of every grid-wide rule is recovered from the stored rule (each quantity has a clause pair
    q - f(x) > c + m and -(q - f(x)) > -c + m, so m is half their sum) and compared with the
    measurement noise floor and with the magnitudes of the real drift-off attacks."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import envelope as E
from p3 import measure as M
from p3 import sherlock_io as S
from p3 import sherlock_model as SM

ANALOG = ("vm_pu", "loading", "p_from", "trafo_p_hv", "trafo_loading", "load_p", "sgen_p", "storage_p", "load_q")


def records(split, step):
    names, net = M.names(), E._base_net()
    T, Mx = [], []
    for i, rec in enumerate(S.iter_state(S.root(), split)):
        if i % step == 0:
            T.append(rec["timestamp"]); Mx.append(SM.record_measurements(rec["state"], names, net))
    return np.array(T), np.array(Mx)


def rule_margin_matrix(rule, Mx, idx):
    """Vectorised rule margin over records (same semantics as rules.margin)."""
    best = np.full(len(Mx), -np.inf)
    for clause in (rule["any_of"] if "any_of" in rule else [rule["atoms"]]):
        ok = np.ones(len(Mx), bool); cm = np.full(len(Mx), np.inf)
        for a in clause:
            if a["type"] == "discrete":
                ok &= np.abs(Mx[:, idx[a["meas"]]] - a["value"]) < 1e-9
                continue
            if a["type"] == "threshold":
                lhs = Mx[:, idx[a["meas"]]]
            else:
                lhs = sum(w * Mx[:, idx[k]] for k, w in a["coeffs"].items())
            sc = float(a.get("scale", 1.0))
            am = (a["value"] - lhs) / sc if a["op"] == "<" else (lhs - a["value"]) / sc
            cm = np.minimum(cm, am)
        cm = np.where(ok, cm, -1.0)
        best = np.maximum(best, cm)
    return best


def library_fires(rules, added, Mx, T, idx):
    f = np.zeros(len(Mx), bool)
    for r, t0 in zip(rules, added):
        f |= (rule_margin_matrix(r, Mx, idx) > 0) & (T >= t0)
    return f


def latency(Mx, cols, D, rng):
    out = Mx.copy()
    lag = rng.integers(0, D + 1, len(cols))
    for c, l in zip(cols, lag):
        if l:
            out[l:, c] = Mx[:-l, c]
    return out


def deadband(Mx, cols, frac, ranges):
    out = Mx.copy()
    for c in cols:
        db = frac * ranges[c]
        if db <= 0:
            continue
        x = Mx[:, c]; y = np.empty_like(x); last = x[0]
        for i, v in enumerate(x):
            if not np.isfinite(v) or abs(v - last) > db:
                last = v
            y[i] = last
        out[:, c] = y
    return out


def main():
    ap = C.parser(__doc__)
    ap.add_argument("--tag", default="_tc")
    ap.set_defaults(grid="sherlock")
    a = C.init(ap.parse_args())
    idx = M.index(); names = M.names()
    lib = json.loads((C.ROOT / "rules" / C.suffixed(f"library{a.tag}.json")).read_text())
    rules = list(lib.values())
    cf = np.load(C.interim(f"consolidation_fires{a.tag}.npz"))
    added = cf["added_at"]
    T, Mx = records("test", 1)
    _, Mtr = records("train", 10)
    ev = S.load_events(S.root(), "test")
    near = np.zeros(len(T), bool)
    for e in ev:
        if "benign" not in e["id"]:
            near |= (T >= e["start"] - 60) & (T <= e.get("recovery", e["end"]) + 60)
    benign = ~near
    att = [e for e in ev if "benign" not in e["id"] and e["description"] != "arp-spoof:arp-spoof-dos"]
    cols = [i for i, n in enumerate(names) if n.split(".")[0] in ANALOG]
    ranges = np.nanmax(Mtr, axis=0) - np.nanmin(Mtr, axis=0)
    rng = np.random.default_rng(a.seed + 26)

    def summary(f):
        det = sum(bool(f[(T >= e["start"]) & (T <= e.get("recovery", e["end"]))].any()) for e in att)
        return f"{f[benign].mean():.5f}", f"{det}/{len(att)}"

    rows = []
    base = library_fires(rules, added, Mx, T, idx)
    rows.append(["none (recorded telemetry)", *summary(base)])
    for D in (1, 2, 5):
        rows.append([f"latency 0 to {D} s per measurement", *summary(library_fires(rules, added, latency(Mx, cols, D, rng), T, idx))])
    for frac in (0.005, 0.01, 0.02):
        rows.append([f"deadband {frac * 100:.1f} % of the training range", *summary(library_fires(rules, added, deadband(Mx, cols, frac, ranges), T, idx))])
    for r in rows:
        print(r)

    # (B) stealth budget
    marg = {"vm_pu": [], "p_from": []}
    for r in rules:
        if "any_of" not in r:
            continue
        pairs = {}
        for clause in r["any_of"]:
            for at in clause:
                if at["type"] != "linear":
                    continue
                tgt = [k for k, w in at["coeffs"].items() if abs(abs(w) - 1.0) < 1e-12 and k.split(".")[0] in marg]
                if tgt:
                    pairs.setdefault(tgt[0], []).append(at["value"])
        for k, vals in pairs.items():
            if len(vals) == 2:
                marg[k.split(".")[0]].append((vals[0] + vals[1]) / 2)
    drift = json.loads((C.ROOT / "rules" / "drift_magnitudes.json").read_text())["sherlock"]["max_signed_offset_pu"]
    brow = []
    for k, unit in (("vm_pu", "pu"), ("p_from", "MW")):
        v = np.array(marg[k])
        if len(v):
            brow.append([k, unit, len(v), f"{np.min(v):.4f}", f"{np.median(v):.4f}", f"{np.max(v):.4f}"])
    print(brow)
    body = "# Red-team checks on the deployed 01-Basic library\n\n" + __doc__.split("\n\n", 1)[1] + "\n\n"
    body += f"## (A) SCADA reporting artifacts\n\nLibrary `library{a.tag}_sherlock.json` ({len(rules)} rules), unchanged.\n\n"
    body += C.md_table(["artifact applied to analog measurements", "library false alarms per benign record", "process attacks detected (rules learned before or during)"], rows)
    body += "\n## (B) Stealth budget of the grid-wide rules\n\n" + C.md_table(["quantity", "unit", "clauses", "smallest margin", "median margin", "largest margin"], brow)
    body += (f"\nFor comparison: measurement noise floor 0.0005 pu (same voltage recorded twice, `sherlock_model_check.md`); "
             f"real drift-off attacks on this grid moved a voltage reading by {', '.join(f'{abs(x):.4f}' for x in drift)} pu "
             f"(`drift_magnitude.md`). A falsification below a quantity's margin in every record does not fire the library; "
             "a physically consistent falsification of every reading at once (Liu et al.) is undetectable by any consistency rule.\n")
    C.write_report("red_team.md", body)


if __name__ == "__main__":
    main()
