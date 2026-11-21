"""Paper-ready outputs of the B_top / C_top experiment (scripts/41, 42): main table per day and variant, paired
event table, seen versus new topologies, N_MIN sensitivity, effect of the remainder correction, one figure
(detection rate against realised false-alarm load, with the operating points chosen on calibration) and CSVs."""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from p3 import common as C

IN = C.ROOT / "reports" / "topo"
DAYS = [("recorded", "recorded day"), ("split", "injected, seed 7"), ("split_s8", "injected, seed 8"), ("split_s9", "injected, seed 9"),
        ("split_s10", "injected, seed 10"), ("split_s11", "injected, seed 11")]
VARS = ["A", "B", "C", "B_top", "C_top"]


def load(day, suffix=""):
    f = IN / f"result_{day}{suffix}.json"
    return json.loads(f.read_text()) if f.exists() else None


def row(res, var, tg, scope="whole test day"):
    for r in res["rows"]:
        if r["variant"] == var and r["scope"] == scope and (var == "A" or r["target"] == tg):
            return r


def med_delay(ra, rb):
    both = [i for i in ra["out"] if ra["out"][i] and rb["out"][i]]
    if not both:
        return "", "", 0
    return f"{np.median([ra['delay'][i] for i in both]):.0f}", f"{np.median([rb['delay'][i] for i in both]):.0f}", len(both)


def main():
    C.parser(__doc__).parse_args()
    body = "# Physics floor against per-(channel, topology) noise thresholds, 02-Semiurban: results\n\n"
    body += ("Protocol and definitions: `scripts/41_topo_abc.py` (docstring). Calibration frozen before the test in "
             "`reports/topo/frozen_P2_recorded.json` and `frozen_P2_split.json` (git commit d321af5). Every day is shown separately; the "
             "injected days share one recorded benign half-day and are not independent days. Zero false alarms are written as "
             "'0 in X benign hours'.\n\n")
    main_csv, pair_csv, cls_csv, curve_csv = [], [], [], []
    tabs = {}
    for scope in ("whole test day", "both active"):
        rows = []
        for day, lab in DAYS:
            res = load(day)
            if res is None:
                continue
            for tg in (0.5, 0.25, 1.0):
                for var in VARS:
                    if var == "A" and tg != 0.5:
                        continue
                    r = row(res, var, tg, scope)
                    ref = row(res, "B_top" if var == "C_top" else ("B" if var == "C" else None), tg, scope) if var in ("C", "C_top") else None
                    d1, d2, nb = med_delay(ref, r) if ref else ("", "", "")
                    fa = f"{r['fa_episodes']} in {r['benign_hours']:.2f} h" + (f" ({r['fa_episodes'] / r['benign_hours']:.2f}/h)" if r["fa_episodes"] else "")
                    rec = [lab, "" if var == "A" else tg, var, "" if r["k"] is None else f"{r['k']:g}", f"{r['detected']}/{r['instances']}",
                           ", ".join(f"{p} {a}/{b}" for p, (a, b) in r["per_type"].items()), fa,
                           "" if r["active_share"] is None else f"{r['active_share'] * 100:.1f} %",
                           f"{d1} / {d2} ({nb})" if nb else ""]
                    rows.append(rec)
                    main_csv.append([scope, day, "" if var == "A" else tg, var, r["k"], r["detected"], r["instances"], r["fa_episodes"],
                                     round(r["benign_hours"], 3), round(r["fa_episodes"] / r["benign_hours"], 3), round(r["benign_records_flagged"], 6),
                                     r["active_share"], d1, d2])
        tabs[scope] = rows
    hdr = ["day", "target (episodes/h)", "variant", "k (frozen)", "detected", "per type", "false-alarm episodes in benign hours", "share of time active",
           "median delay s, B-variant / C-variant (common events)"]
    body += "## 1. Main table, whole test day (waiting for physics rules included)\n\n" + C.md_table(hdr, tabs["whole test day"])
    body += "\n## 2. Same, restricted to records where the physics rule of the record's topology is active (both methods active)\n\n" + C.md_table(hdr, tabs["both active"])
    # totals over the 5 injected days at the main target
    tot = []
    for var in VARS:
        d = n = e = 0; h = 0.0
        for day, _ in DAYS[1:]:
            res = load(day)
            r = row(res, var, 0.5)
            d += r["detected"]; n += r["instances"]; e += r["fa_episodes"]; h += r["benign_hours"]
        tot.append([var, f"{d}/{n}", f"{e} in {h:.1f} h ({e / h:.2f}/h)"])
    body += "\n## 3. Five injected days together, target 0.5 (descriptive; one shared benign base day)\n\n" + C.md_table(["variant", "detected", "false-alarm episodes"], tot)
    # paired
    prow = []
    for day, lab in DAYS:
        res = load(day)
        for p in res["pairs"]:
            prow.append([lab] + p[1:])
            pair_csv.append([day] + p[1:])
    body += "\n## 4. Paired comparisons (whole test day)\n\n" + C.md_table(["day", "target", "comparison", "only first", "ids", "only second", "ids", "both", "median delay first", "median delay second"], prow)
    orow = []
    for day, lab in DAYS:
        res = load(day)
        for o in res["onesided"]:
            if o[1] == 0.5 and o[2] in ("B_top vs C_top", "B vs C"):
                orow.append([lab] + o[2:])
    body += "\n## 5. Instances detected by only one method (target 0.5): topology, channel, residual, both thresholds, alarm time\n\n"
    body += C.md_table(["day", "comparison", "detected only by", "event", "type", "topology", "topology class", "channel", "|r| (sigma)",
                        "threshold of first method", "threshold of second method", "first alarm s after start", "why the second method missed"], orow)
    with open(IN / "onesided_events.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["day", "target", "comparison", "detected_only_by", "event", "type", "topology", "topology_class", "channel", "residual_sigma",
                                        "threshold_first", "threshold_second", "first_alarm_s", "reason"])
        for day, _ in DAYS:
            for o in load(day)["onesided"]:
                w.writerow([day] + o[1:])
    crow = []
    for day, lab in DAYS:
        for c in load(day)["classes"]:
            crow.append([lab] + c[2:])
            cls_csv.append([day] + c[1:])
    body += "\n## 6. Events and false alarms by topology class (target 0.5)\n\n" + C.md_table(["day", "variant", "topology class", "detected", "false-alarm episodes", "benign hours"], crow)
    # N_MIN sensitivity
    srow = []
    for day, lab in DAYS:
        res = load(day, "_n240")
        if res is None:
            continue
        for var in ("B_top", "C_top"):
            r = row(res, var, 0.5)
            srow.append([lab, var, f"{r['k']:g}", f"{r['detected']}/{r['instances']}", f"{r['fa_episodes']} in {r['benign_hours']:.2f} h", res["n_local"]])
    body += "\n## 7. POST HOC sensitivity: N_MIN = 240 records (20 min) instead of the rule's 720 (target 0.5)\n\n" + C.md_table(["day", "variant", "k", "detected", "false-alarm episodes", "test topologies with local noise"], srow)
    # remainder correction
    frow = []
    for day, lab in DAYS:
        a, b = load(day), load(day, "_fix")
        if b is None:
            continue
        for var in ("C", "C_top"):
            for tg in (0.5,):
                ra, rb = row(a, var, tg), row(b, var, tg)
                lost = [i for i in ra["out"] if ra["out"][i] and not rb["out"][i]]
                gained = [i for i in ra["out"] if rb["out"][i] and not ra["out"][i]]
                frow.append([lab, var, f"{ra['detected']} -> {rb['detected']}", ",".join(lost) or "none", ",".join(gained) or "none",
                             f"{ra['fa_episodes']} -> {rb['fa_episodes']}"])
    body += "\n## 8. Effect of the remainder correction (scripts/42; k and noise frozen)\n\n" + C.md_table(["day", "variant", "detected before -> after", "events no longer detected", "events newly detected", "false-alarm episodes before -> after"], frow)
    for nm in ("edge_reproduce.json", "edge_check.json"):
        f = IN / nm
        if f.exists():
            e = json.loads(f.read_text())
            body += f"\n`{nm}`: {e['states']} regression states, {len(e['fails'])} above 1, largest score {e['max_score']:.3f}"
            if "holdout_states" in e:
                ch = sum(x[1] for x in e["thresholds_changed"]); tot_ch = sum(x[2] for x in e["thresholds_changed"])
                body += (f"; new states never used to choose the correction: {e['holdout_states']}, {e['holdout_fails']} above 1, largest score {e['holdout_max']:.3f}; "
                         f"thresholds changed by the correction (recorded-day topologies, k = 1.5): {ch} of {tot_ch} channel-topology pairs")
            body += ".\n"
    # curve + figure
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(1, 2, figsize=(7.4, 3.0))
    col = {"B": "#7f7f7f", "C": "#d95f02", "B_top": "#1f77b4", "C_top": "#2ca02c"}
    for ax, sel, title in ((axs[0], ["recorded"], "(a) recorded test day"), (axs[1], [d for d, _ in DAYS[1:]], "(b) five injected days (shared base day)")):
        for var in ("B", "C", "B_top", "C_top"):
            pts = {}
            for day in sel:
                for c in load(day)["curve"]:
                    if c[1] == var:
                        p = pts.setdefault(c[2], [0, 0, 0, 0.0]); p[0] += c[3]; p[1] += c[4]; p[2] += c[5]; p[3] += c[6]
                        curve_csv.append([day] + c[1:])
            ks = sorted(pts)
            x = [pts[k][2] / pts[k][3] for k in ks]; y = [pts[k][0] / pts[k][1] for k in ks]
            wide = var in ("B", "C")
            ax.plot(x, y, "-", lw=5 if wide else 1.2, color=col[var], alpha=0.35 if wide else 0.95, label=var + (" (wide)" if wide else ""), marker=None if wide else "o", ms=2.5, zorder=1 if wide else 3)
            for tg, mk in ((0.5, "*"), (0.25, "v"), (1.0, "^")):
                d = n = e = 0; h = 0.0
                for day in sel:
                    r = row(load(day), var, tg); d += r["detected"]; n += r["instances"]; e += r["fa_episodes"]; h += r["benign_hours"]
                ax.plot([e / h], [d / n], mk, ms=9 if mk == "*" else 6, color=col[var], markeredgecolor="black", markeredgewidth=0.6)
        d = n = e = 0; h = 0.0
        for day in sel:
            r = row(load(day), "A", None); d += r["detected"]; n += r["instances"]; e += r["fa_episodes"]; h += r["benign_hours"]
        ax.plot([e / h], [d / n], "s", color="black", ms=5, label="A (SE-BDD)")
        ax.set_xscale("symlog", linthresh=0.1); ax.set_xlim(-0.02, 30); ax.set_ylim(0, 1)
        ax.set_xlabel("false-alarm episodes per benign hour (test)", fontsize=7.5); ax.set_ylabel("process attacks detected", fontsize=7.5)
        ax.set_title(title, fontsize=8, loc="left"); ax.tick_params(labelsize=7); ax.grid(alpha=0.3, lw=0.5)
    axs[0].legend(fontsize=6.5, frameon=False, loc="lower right")
    fig.text(0.5, -0.05, "Lines: test-day curve over k = 1 to 20 (description). Wide pale lines B and C lie under B_top and C_top: no test topology had enough\n"
             "calibration records for local noise, so both fall back to B's noise. Markers: operating points frozen on calibration (star 0.5, triangles 0.25 / 1.0 episodes per hour).",
             ha="center", fontsize=6.5)
    fig.tight_layout()
    fig.savefig(IN / "fig_detection_vs_load.png", dpi=200, bbox_inches="tight"); fig.savefig(IN / "fig_detection_vs_load.svg", bbox_inches="tight")
    body += "\n## 9. Figure\n\n![](topo/fig_detection_vs_load.png)\n\n`reports/topo/fig_detection_vs_load.png` (lines: test-day curve over k, description only; markers: frozen operating points).\n"
    for nm, hdr_, data in (("main_table.csv", ["scope", "day", "target", "variant", "k", "detected", "instances", "fa_episodes", "benign_hours", "fa_per_hour", "benign_records_flagged", "active_share", "median_delay_B", "median_delay_C"], main_csv),
                           ("paired.csv", ["day", "target", "comparison", "only_first", "ids_first", "only_second", "ids_second", "both", "median_delay_first", "median_delay_second"], pair_csv),
                           ("topology_classes.csv", ["day", "target", "variant", "class", "detected", "fa_episodes", "benign_hours"], cls_csv),
                           ("curve.csv", ["day", "variant", "k", "detected", "instances", "fa_episodes", "benign_hours"], curve_csv)):
        with open(IN / nm, "w", newline="") as fh:
            w = csv.writer(fh); w.writerow(hdr_); w.writerows(data)
    body += ("\n## Reproduction\n\n```\npython3 scripts/41_topo_abc.py --phase prepare\npython3 scripts/41_topo_abc.py --phase calibrate --calib recorded\n"
             "python3 scripts/41_topo_abc.py --phase calibrate --calib split\nscripts/topo_runs.sh\npython3 scripts/42_edge_fix.py --phase reproduce\n"
             "python3 scripts/42_edge_fix.py --phase fix\npython3 scripts/42_edge_fix.py --phase check\n"
             "for D in recorded split split_s8 split_s9 split_s10 split_s11; do python3 scripts/41_topo_abc.py --phase test --day $D --fix; done\n"
             "python3 scripts/41_topo_abc.py --phase calibrate --calib recorded --nmin 240   # post hoc, likewise --calib split and --phase test --nmin 240\n"
             "python3 scripts/43_topo_report.py\n```\n")
    C.write_report("topo_results.md", body)
    print(body[:3000])


if __name__ == "__main__":
    main()
