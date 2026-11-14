"""WP2-c: the paper's comparison table, robustness over seeds and ablations.

Reads saved per-record alarms / firings (no recomputation):
  01-Basic (grid sherlock):  detector_alarms_{raw,physics}[tag]_sherlock.npz (D1, AE, IF),
                             consolidation_fires[tag]_sherlock.npz (certified library learned online)
  02-Semiurban:              se_residuals_semiurban.npz (SE-BDD), detector_alarms_{raw,physics}_semiurban.npz,
                             semiurban_fires[tag]_semiurban.npz (certified library, on demand)
Metrics per method: instances detected per attack type, mean delay of the first alarm, false alarm rate per
benign record and false alarm episodes per benign hour. Benign = more than 60 s from any attack window.
Missing inputs are reported as unknown."""
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C
from p3 import envelope as E
from p3 import sherlock_io as S

TYPES = ["control-and-freeze:control-and-freeze", "drift-off:drift-off", "industroyer:industroyer", "arp-spoof:arp-spoof-dos"]
SHORT = {"control-and-freeze:control-and-freeze": "CFC", "drift-off:drift-off": "drift-off",
         "industroyer:industroyer": "industroyer", "arp-spoof:arp-spoof-dos": "arp-spoof (excl.)"}


def runs(mask):
    out, c = np.zeros(len(mask), int), 0
    for i, x in enumerate(mask):
        c = c + 1 if x else 0
        out[i] = c
    return out


def load(path, key):
    p = C.INTERIM / path
    if not p.exists():
        return None
    d = np.load(p, allow_pickle=True)
    return (d["t"] if "t" in d else d["test_t"]), d[key].astype(bool)


def evaluate(t, alarm, events, settle=60.0, strict=None):
    """strict = (rule_fires, added_at): an attack counts as detected by the library only through rules
    learned before the attack started (no credit for rules learned from that attack's own alert)."""
    att = [e for e in events if "benign" not in e["id"]]
    near = np.zeros(len(t), bool)
    for e in att:
        near |= (t >= e["start"] - settle) & (t <= e.get("recovery", e["end"]) + settle)
    benign = ~near
    dt = float(np.median(np.diff(t)))
    det, delays = collections.Counter(), collections.defaultdict(list)
    n = collections.Counter(e["description"] for e in att)
    for e in att:
        sel = (t >= e["start"]) & (t <= e.get("recovery", e["end"]))
        if strict is not None:
            rf, added = strict
            prior = added < e["start"]
            alarm_e = rf[prior].any(axis=0) if prior.any() else np.zeros(len(t), bool)
        else:
            alarm_e = alarm
        if alarm_e[sel].any():
            det[e["description"]] += 1
            delays[e["description"]].append(float(t[sel][alarm_e[sel]][0] - e["start"]))
    fa = alarm & benign
    episodes = int(np.sum(np.diff(np.r_[0, fa.astype(int)]) == 1))
    hours = benign.sum() * dt / 3600
    allp = [d for k, v in delays.items() if k != TYPES[3] for d in v]
    return {"det": det, "n": n, "fa_rate": float(fa.sum() / max(benign.sum(), 1)), "fa_per_h": episodes / max(hours, 1e-9),
            "delay": float(np.mean(allp)) if allp else float("nan")}


def row(name, r):
    if r is None:
        return [name] + ["⟨·⟩"] * (len(TYPES) + 3)
    return ([name] + [f"{r['det'][t]}/{r['n'][t]}" for t in TYPES] +
            [f"{r['delay']:.0f}" if np.isfinite(r["delay"]) else "⟨·⟩", f"{r['fa_rate']:.5f}", f"{r['fa_per_h']:.2f}"])


HEAD = ["method"] + [SHORT[t] for t in TYPES] + ["mean delay s (process attacks)", "false alarms per benign record", "false alarm episodes per benign hour"]


def main():
    ap = C.parser(__doc__)
    a = ap.parse_args()
    body = "# WP2-c: comparison of detection methods, robustness and ablations\n\n"
    if S.variant() == "split":
        body = ("# WP4d: comparison on the semi-synthetic split day\n\nSecond half of each recorded train day with injected "
                "attacks (`split_day.md`); every calibration redone on the first half only. Rows without saved alarms are ⟨·⟩.\n\n")
    body += ("All numbers recomputed here from saved per-record alarms. Benign records: more than 60 s from any attack "
             "window. 01-Basic: 1 Hz records. 02-Semiurban: every 5th record (5 s). Mean delay: first alarm after attack "
             "start, averaged over detected process-attack instances (arp-spoof excluded per owner decision 1).\n\n")
    out = {}
    grids = [("sherlock", "01-Basic (CIGRE MV, 15 buses, fully observed)"), ("semiurban", "02-Semiurban (SimBench, 178 buses, about 40 % unmonitored)")]
    if (C.INTERIM / "se_residuals_rural.npz").exists() and S.variant() != "split":
        grids.append(("rural", "03-Rural (SimBench, 99 buses; zero-training transfer: no Rural data used for calibration, ML trained on the first 30 min only)"))
    for grid, label in grids:
        E.use_grid(grid)
        C.GRID = grid
        ev = S.load_events(S.root(), "test")
        rows, res = [], {}

        def add(name, x, strict=None):
            r = evaluate(*x, ev, strict=strict) if x is not None else None
            res[name] = (r, x)
            rows.append(row(name, r))
        if grid == "sherlock":
            add("Classic residual test (D1, full power flow)", load(C.suffixed("detector_alarms_physics.npz"), "D1"))
            add("ML: autoencoder, raw telemetry", load(C.suffixed("detector_alarms_raw.npz"), "AE"))
            add("ML: Isolation Forest, physics-informed", load(C.suffixed("detector_alarms_physics.npz"), "IF"))
            add("ML: autoencoder, physics-informed", load(C.suffixed("detector_alarms_physics.npz"), "AE"))
            add("Detectors D1 or AE (alert source)", load(C.suffixed("consolidation_fires.npz"), "det"))
            add("Certified library, rules active at the time (incl. learned during the same attack)", load(C.suffixed("consolidation_fires.npz"), "lib_prior"))
            pth = C.INTERIM / C.suffixed("consolidation_fires.npz")
            dd = np.load(pth) if pth.exists() else None
            if dd is not None and "rule_fires" in dd:
                add("Certified library only, strict (rules learned before the attack)", (dd["t"], dd["lib_prior"].astype(bool)),
                    strict=(dd["rule_fires"].astype(bool), dd["added_at"]))
            else:
                add("Certified library only, strict (rules learned before the attack)", None)
            cf = load(C.suffixed("consolidation_fires.npz"), "det")
            lf = load(C.suffixed("consolidation_fires.npz"), "lib_prior")
            add("Combined: detectors or certified library", (cf[0], cf[1] | lf[1]) if cf and lf else None)
            pt = C.INTERIM / C.suffixed("consolidation_fires_tc.npz")
            if pt.exists():     # WP5: per-topology online noise calibration
                dt_ = np.load(pt)
                add("WP5: certified library with per-topology calibration, strict", (dt_["t"], dt_["lib_prior"].astype(bool)),
                    strict=(dt_["rule_fires"].astype(bool), dt_["added_at"]))
                add("WP5: combined, detectors or library with per-topology calibration", (dt_["t"], dt_["det"].astype(bool) | dt_["lib_prior"].astype(bool)))
        else:
            add("Classic bad-data detection (SE-BDD, state estimation)", load(C.suffixed("se_residuals.npz"), "alarm"))
            add("ML: autoencoder, raw telemetry", load(C.suffixed("detector_alarms_raw.npz"), "AE"))
            add("ML: Isolation Forest, SE-residual features", load(C.suffixed("detector_alarms_physics.npz"), "IF"))
            add("ML: autoencoder, SE-residual features", load(C.suffixed("detector_alarms_physics.npz"), "AE"))
            add("Certified library, single record", load(C.suffixed("semiurban_fires.npz"), "fires"))
            add("Certified library, persistence L = 3", load(C.suffixed("semiurban_fires.npz"), "fires_p"))
            sb = load(C.suffixed("se_residuals.npz"), "alarm")
            lp0 = load(C.suffixed("semiurban_fires.npz"), "fires_p")
            add("Combined: SE-BDD or certified library (L = 3)", (sb[0], sb[1] | lp0[1]) if sb and lp0 else None)
            ae = load(C.suffixed("detector_alarms_physics.npz"), "AE")
            lp = load(C.suffixed("semiurban_fires.npz"), "fires_p")
            if sb and lp:
                comb = sb[1] | lp[1] | (ae[1] if ae is not None and len(ae[1]) == len(sb[1]) else False)
                add("Combined: SE-BDD or AE or certified library (L = 3)", (sb[0], comb))
            else:
                add("Combined: SE-BDD or AE or certified library (L = 3)", None)
        body += f"## {label}\n\n" + C.md_table(HEAD, rows) + "\n"
        out[grid] = res

        # persistence ablation on the certified library (single-record firings)
        key = ("consolidation_fires.npz", "lib_prior") if grid == "sherlock" else ("semiurban_fires.npz", "fires")
        base = load(C.suffixed(key[0]), key[1])
        if base is not None:
            prow = []
            for L in (1, 3, 5):
                prow.append(row(f"library, persistence L = {L}", evaluate(base[0], runs(base[1]) >= L, ev)))
            body += "Persistence ablation (certified library):\n\n" + C.md_table(HEAD, prow) + "\n"

        # seeds and margin-factor ablation
        srow, mrow = [], []
        for tag, lab in (("", "seed 7"), ("_s8", "seed 8"), ("_s9", "seed 9")):
            f = (f"consolidation_fires{tag}.npz", "lib_prior") if grid == "sherlock" else (f"semiurban_fires{tag}.npz", "fires_p")
            x = load(C.suffixed(f[0]), f[1])
            srow.append(row(f"library, {lab}", evaluate(*x, ev) if x is not None else None))
            if grid == "sherlock":
                xd = load(C.suffixed(f"detector_alarms_physics{tag}.npz"), "AE")
                srow.append(row(f"AE physics-informed, {lab}", evaluate(*xd, ev) if xd is not None else None))
        for tag, lab in (("_m125", "1.25"), ("", "1.5 (default)"), ("_m20", "2.0")):
            f = (f"consolidation_fires{tag}.npz", "lib_prior") if grid == "sherlock" else (f"semiurban_fires{tag}.npz", "fires_p")
            x = load(C.suffixed(f[0]), f[1])
            mrow.append(row(f"library, margin factor {lab}", evaluate(*x, ev) if x is not None else None))
        body += "Seed robustness (oracle search seeds; ML training seeds):\n\n" + C.md_table(HEAD, srow) + "\n"
        body += "Margin factor ablation (certified library):\n\n" + C.md_table(HEAD, mrow) + "\n"
    C.GRID = C.DEFAULT_GRID
    C.write_report("comparison.md", body)
    print(body[:3000])


if __name__ == "__main__":
    main()
