"""Publication figures for the paper draft (reports/figures/, SVG + PDF + PNG).
Every number is copied from a generated report in reports/ (named per figure). Palette: three
validated categorical slots (blue, orange, aqua) plus neutral inks; text never wears a series colour."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle
from matplotlib.lines import Line2D

OUT = Path(__file__).resolve().parents[1] / "reports" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
BLUE, ORANGE, AQUA, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#6250d6"
INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1", "#fcfcfb"
plt.rcParams.update({"font.family": "Inter", "font.size": 8, "axes.edgecolor": INK2, "axes.labelcolor": INK,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6, "svg.fonttype": "none"})


def save(fig, name):
    for ext in ("svg", "pdf"):
        fig.savefig(OUT / f"{name}.{ext}", bbox_inches="tight", facecolor=SURF)
    fig.savefig(OUT / f"{name}.png", dpi=200, bbox_inches="tight", facecolor=SURF)
    plt.close(fig)


def box(ax, x, y, w, h, title, body="", fc="#f1f0ec", ec=INK2, title_size=7.4, body_size=6.0, lw=0.8, title_color=INK, gap=0.3):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.015,rounding_size=0.06", fc=fc, ec=ec, lw=lw))
    if body:
        ax.text(x + w / 2, y + h - 0.1, title, ha="center", va="top", fontsize=title_size, fontweight="semibold", color=title_color)
        ax.text(x + w / 2, y + h - gap, body, ha="center", va="top", fontsize=body_size, color=INK2, linespacing=1.3)
    else:
        ax.text(x + w / 2, y + h / 2, title, ha="center", va="center", fontsize=title_size, fontweight="semibold", color=title_color)


def arrow(ax, p, q, color=INK2, lw=0.9, style="->", rad=0.0, ls="-"):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle=style, mutation_scale=9, lw=lw, color=color, ls=ls,
                                 connectionstyle=f"arc3,rad={rad}", shrinkA=1, shrinkB=1))


# ---------------------------------------------------------------- Fig 1: end-to-end architecture
def fig1_architecture():
    fig, ax = plt.subplots(figsize=(7.4, 5.6))
    ax.set_xlim(0, 10); ax.set_ylim(0, 6.6); ax.axis("off")
    # lane labels
    for y, lab in ((5.95, "Field and control centre"), (4.35, "Alert and synthesis"), (2.45, "Physics oracle (certification gate)"), (0.72, "Operation")):
        ax.text(0.05, y, lab.upper(), fontsize=6.2, color=MUTED, va="center", fontweight="semibold")
        ax.plot([0.05, 9.95], [y - 0.16, y - 0.16], color=GRID, lw=0.6, zorder=0)
    # row 1
    box(ax, 0.1, 4.75, 1.8, 1.0, "Distribution grid", "RTUs, switches, taps,\nloads, DER, storage")
    box(ax, 2.25, 4.75, 1.9, 1.0, "SCADA telemetry", "IEC 104 at 1 Hz: voltages,\nflows, injections, switch\nand tap states")
    box(ax, 4.5, 4.75, 2.1, 1.0, "Detectors (alert sources)", "D1 power-flow residual\nSE-BDD (partial observability)\nML: autoencoder, isolation forest")
    box(ax, 6.95, 4.75, 2.95, 1.0, "Offline calibration (train day)", "reconstructed grid model, benign\nenvelope, noise per measurement,\ndetector thresholds", fc="#eef3fa")
    arrow(ax, (1.9, 5.25), (2.25, 5.25)); arrow(ax, (4.15, 5.25), (4.5, 5.25))
    # row 2
    box(ax, 2.25, 3.2, 1.9, 0.95, "Alert episode", "60 s of telemetry\nfrom the first alarm")
    box(ax, 4.5, 3.2, 2.1, 0.95, "Covered already?", "a library rule fires\nwithin the window: stop")
    box(ax, 6.95, 3.2, 2.95, 0.95, "Rule synthesis", "P invariant, G grid-wide invariant\nper topology, S state change,\nSE estimation residual")
    arrow(ax, (5.55, 4.75), (5.55, 4.15))
    ax.text(5.62, 4.45, "alarm", fontsize=6.2, color=INK2, va="center")
    arrow(ax, (4.15, 3.67), (4.5, 3.67))
    arrow(ax, (3.2, 4.75), (3.2, 4.15)); ax.text(3.27, 4.45, "window", fontsize=6.2, color=INK2, va="center")
    arrow(ax, (6.6, 3.67), (6.95, 3.67)); ax.text(6.77, 3.9, "no", fontsize=6.2, color=INK2, ha="center")
    # row 3 oracle
    ax.add_patch(FancyBboxPatch((2.25, 1.05), 7.65, 1.65, boxstyle="round,pad=0.015,rounding_size=0.08", fc="#fdf3ea", ec=ORANGE, lw=1.0))
    box(ax, 2.45, 1.25, 2.3, 1.2, "Search layer", "10,000 LHS states and\ndifferential evolution on the\nfull AC power flow", fc=SURF)
    box(ax, 5.0, 1.25, 2.3, 1.2, "Robust exact layer", "Z3 over linearised AC and\nenvelope; atoms shifted by δ;\nUNSAT is a certificate", fc=SURF)
    box(ax, 7.55, 1.25, 2.15, 1.2, "Error bounds δ", "adversarial search × 1.25,\nrule-specific atom bounds,\nscenario bound ε = 3.45e-4", fc=SURF)
    ax.text(9.8, 2.6, "oracle", fontsize=6.2, color=ORANGE, ha="right", va="center", fontweight="semibold")
    arrow(ax, (8.4, 3.2), (8.4, 2.72)); ax.text(8.47, 2.96, "candidate rules", fontsize=6.2, color=INK2, va="center")
    arrow(ax, (7.55, 1.85), (7.3, 1.85), style="->")
    # CEGIS loop back to synthesis
    arrow(ax, (3.6, 2.45), (3.6, 3.2), color=ORANGE, rad=0.0)
    ax.text(3.68, 2.9, "counterexample:\nrefine margin (CEGIS)", fontsize=6.2, color=ORANGE, va="center", bbox=dict(fc=SURF, ec="none", pad=1))
    # row 4
    box(ax, 2.25, 0.08, 2.9, 0.5, "Certified rule library", fc="#e8f5ef", ec=AQUA)
    box(ax, 5.5, 0.08, 2.1, 0.5, "Online per-topology\nnoise calibration (5 min)", fc="#eef3fa", title_size=6.6)
    box(ax, 7.95, 0.08, 1.95, 0.5, "Operator alarms", fc="#f1f0ec")
    arrow(ax, (6.15, 1.25), (4.2, 0.58), color=AQUA)
    ax.text(5.6, 0.86, "no counterexample: certified", fontsize=6.2, color=AQUA, va="center", ha="center",
            bbox=dict(fc=SURF, ec="none", pad=1))
    arrow(ax, (5.15, 0.33), (5.5, 0.33)); arrow(ax, (7.6, 0.33), (7.95, 0.33))
    arrow(ax, (1.0, 4.75), (1.0, 0.33), color=INK2, ls=(0, (2, 2)))
    arrow(ax, (1.0, 0.33), (2.25, 0.33), color=INK2, ls=(0, (2, 2)))
    ax.text(1.08, 2.0, "live telemetry\nmatched against\nthe library", fontsize=6.2, color=INK2, va="center")

    ax.text(0.1, 6.42, "Labels are never used in the loop; they score detection and false alarms afterwards.", fontsize=6.4, color=MUTED, style="italic")
    save(fig, "fig1_architecture")


# ---------------------------------------------------------------- Fig 2: oracle layers and error bounds
def fig2_oracle():
    """linac_error_sherlock.md: max over 1000 samples, worst found by search, delta used."""
    q = ["bus voltage (pu)", "line loading (pp)", "transformer loading (pp)", "line active power (MW)", "transformer active power (MW)"]
    smax = [0.00214, 5.40090, 2.29724, 0.05132, 0.05741]
    worst = [0.00834, 9.40145, 2.30732, 0.19365, 0.21521]
    delta = [0.01042, 11.75181, 2.88415, 0.24206, 0.26902]
    fig, ax = plt.subplots(figsize=(3.6, 2.4))
    y = list(range(len(q)))
    for i in y:
        ax.plot([0, 1], [i, i], color=GRID, lw=6, solid_capstyle="butt", zorder=0)
    ax.scatter([s_ / d for s_, d in zip(smax, delta)], y, marker="o", s=30, color=BLUE, zorder=3, label="max over 1,000 benign samples")
    ax.scatter([w / d for w, d in zip(worst, delta)], y, marker="D", s=26, color=ORANGE, zorder=3, label="worst case found by search")
    for i, d in enumerate(delta):
        ax.text(1.04, i, f"δ = {d:.3g}", va="center", fontsize=6.3, color=INK2)
    ax.axvline(1.0, color=INK2, lw=0.8)
    ax.set_yticks(y); ax.set_yticklabels(q, fontsize=7); ax.invert_yaxis(); ax.tick_params(axis="y", length=0)
    ax.set_xlim(0, 1.35); ax.set_xticks([0, 0.5, 1.0]); ax.set_xticklabels(["0", "0.5 δ", "δ = 1.25 × worst"], fontsize=6.8)
    ax.set_xlabel("linearised-AC error relative to the bound δ (Sherlock 01-Basic)", fontsize=7)
    ax.legend(fontsize=6.3, frameon=False, loc="upper center", bbox_to_anchor=(0.45, -0.28), ncol=2, handletextpad=0.3, columnspacing=1.0)
    save(fig, "fig2_bounds")


# ---------------------------------------------------------------- Fig 3: CEGIS
def fig3_cegis():
    """cegis_demo_linac.md and cegis_demo_linac_sherlock.md."""
    ref = [0.94281, 0.91736, 0.90546, 0.90244, 0.90233, 0.90221, 0.90167, 0.90141, 0.90127, 0.90109, 0.90066]
    sh = [0.93327, 0.89998]
    fig, ax = plt.subplots(figsize=(3.5, 2.4))
    ax.axhspan(0.895, 0.90, color="#f6e0de", lw=0, zorder=0)
    ax.axhline(0.90, color="#b03a32", lw=0.8, zorder=1)
    ax.text(5.0, 0.8975, "below the 0.90 pu operating limit: the rule can no longer fire on a benign state", fontsize=6.0, color="#b03a32", ha="center", va="center")
    ax.plot(range(len(ref)), ref, "-", lw=1.6, color=BLUE, zorder=2)
    ax.scatter(range(len(ref)), ref, s=16, color=BLUE, zorder=3)
    ax.plot(range(len(sh)), sh, "-", lw=1.6, color=ORANGE, zorder=2)
    ax.scatter(range(len(sh)), sh, s=16, color=ORANGE, zorder=3)
    ax.text(10, 0.9032, "reference CIGRE MV", fontsize=6.5, color=INK, ha="right")
    ax.text(1.25, 0.9062, "Sherlock 01-Basic", fontsize=6.5, color=INK, ha="left")
    ax.text(0.25, 0.9430, "τ₀ = 0.9428", fontsize=6.3, color=INK2); ax.text(0.25, 0.9325, "τ₀ = 0.9333", fontsize=6.3, color=INK2)
    ax.set_xlabel("CEGIS iteration"); ax.set_ylabel("threshold τ of rule R1 (pu)")
    ax.set_ylim(0.8945, 0.948); ax.set_xlim(-0.3, 10.4); ax.set_xticks(range(0, 11, 2))
    ax.grid(axis="y", color=GRID, lw=0.5); ax.set_axisbelow(True)
    save(fig, "fig3_cegis")


# ---------------------------------------------------------------- Fig 4: consolidation timeline on 01-Basic
def fig4_timeline():
    """consolidation_tc_sherlock.md (episode log, attacks in time order) and the test-day labels."""
    T = {"industroyer": AQUA, "drift-off": ORANGE, "control-and-freeze": BLUE, "arp-spoof": MUTED, "arp-spoof (excluded)": MUTED}
    attacks = [(0, "industroyer", 4284, 4527, 9, None), (1, "drift-off", 5932, 6449, 79, 91), (2, "industroyer", 7931, 8177, None, None),
               (4, "control-and-freeze", 11492, 11985, 70, 63), (6, "arp-spoof", 15083, 15240, 88, None), (7, "industroyer", 17728, 18030, 9, 273),
               (9, "drift-off", 20862, 21387, 68, 70), (10, "control-and-freeze", 22536, 23221, 105, 267), (11, "industroyer", 24207, 24455, None, 6),
               (13, "control-and-freeze", 26673, 27179, 67, 60), (14, "drift-off", 28588, 29213, 67, 69), (15, "industroyer", 29518, 29814, None, None),
               (17, "control-and-freeze", 31604, 32052, 71, 66), (18, "industroyer", 33537, 33740, None, None), (19, "arp-spoof", 35465, 35624, 65, None),
               (20, "control-and-freeze", 36267, 36903, 232, None), (22, "industroyer", 37939, 38199, None, None), (23, "drift-off", 38792, 39320, None, 61)]
    benign = [9911, 14721, 19736, 25521, 30762, 37600, 40020, 41570, 41822, 42731]
    learned = [(4293, "S"), (4505, "G"), (14729, "G"), (17737, "S"), (19744, "G"), (35530, "G"), (37608, "G"), (41578, "G"), (41846, "G"), (42739, "G")]
    refuted = [14729, 19744, 41578, 41846, 42739]
    covered = [6011, 11562, 12225, 18008, 20930, 26740, 28655, 31675, 40028]
    H = 3600.0
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(7.4, 3.6), sharex=True, gridspec_kw={"height_ratios": [2.3, 1], "hspace": 0.12})
    # attack windows
    for i, (aid, typ, s, e, d, l) in enumerate(attacks):
        ax.add_patch(Rectangle((s / H, 1.0), (e - s) / H, 0.5, fc=T[typ], ec="none", alpha=0.9))
        if d is not None:
            ax.plot([(s + d) / H] * 2, [1.6, 1.95], color=INK, lw=1.0)
        if l is not None:
            ax.plot([(s + l) / H] * 2, [0.55, 0.9], color=INK, lw=1.0)
    for b in benign:
        ax.plot([b / H] * 2, [2.15, 2.45], color=MUTED, lw=0.9)
    for t, fam in learned:
        ax.scatter(t / H, 2.9, marker="^", s=28, color=AQUA if fam == "G" else VIOLET, zorder=3, edgecolor=SURF, lw=0.5)
    ax.scatter([t / H for t in refuted], [3.25] * len(refuted), marker="x", s=22, color="#b03a32", zorder=3, lw=1.0)
    ax.scatter([t / H for t in covered], [2.9] * len(covered), marker="o", s=14, color=INK2, zorder=3)
    ax.set_ylim(0.4, 3.45); ax.set_yticks([0.72, 1.25, 1.78, 2.3, 2.9, 3.25])
    ax.set_yticklabels(["library first fires", "attack window", "detector first alarm", "benign procedure", "alert episode", "candidate refuted"], fontsize=6.8)
    ax.tick_params(axis="y", length=0); ax.spines["left"].set_visible(False)
    for y in (0.95, 1.55, 2.05, 2.6): ax.axhline(y, color=GRID, lw=0.5, zorder=0)
    ax.set_title("Self-consolidation on the 01-Basic test day: alerts, learned rules and detections in time order", loc="left", fontsize=8.5, color=INK)
    handles = [Line2D([], [], marker="s", ls="", color=T[k], ms=6, label=k) for k in ("control-and-freeze", "drift-off", "industroyer", "arp-spoof (excluded)")]
    handles += [Line2D([], [], marker="^", ls="", color=AQUA, ms=6, label="G rule certified"), Line2D([], [], marker="^", ls="", color=VIOLET, ms=6, label="S rule certified"),
                Line2D([], [], marker="o", ls="", color=INK2, ms=4, label="covered by library"), Line2D([], [], marker="x", ls="", color="#b03a32", ms=5, label="candidate refuted")]
    fig.legend(handles=handles, fontsize=6.2, frameon=False, ncol=4, loc="lower center", bbox_to_anchor=(0.5, -0.16), handletextpad=0.4, columnspacing=1.2)
    # library size
    xs, ys = [0.0], [0]
    for t, _ in learned:
        xs += [t / H, t / H]; ys += [ys[-1], ys[-1] + 1]
    xs.append(12.1); ys.append(ys[-1])
    ax2.plot(xs, ys, color=AQUA, lw=1.6); ax2.fill_between(xs, 0, ys, color=AQUA, alpha=0.12, lw=0)
    ax2.set_ylabel("rules in\nlibrary", fontsize=7); ax2.set_ylim(0, 11); ax2.set_yticks([0, 5, 10])
    ax2.set_xlabel("hours into the test day"); ax2.set_xlim(0, 12.1); ax2.set_xticks(range(0, 13, 2))
    ax2.grid(axis="y", color=GRID, lw=0.5); ax2.set_axisbelow(True)
    ax2.text(11.95, 9.2, "10 rules: 8 grid-wide, 2 state", fontsize=6.5, ha="right", color=INK2)
    save(fig, "fig4_timeline")


# ---------------------------------------------------------------- Fig 5: detection per type
def panel(ax, rows, title, show_names=True):
    types = [("CFC", BLUE), ("drift-off", ORANGE), ("industroyer", AQUA)]
    n = len(rows); h = 0.22; gap = 0.03
    for j, (t, c) in enumerate(types):
        ys = [i + (j - 1) * (h + gap) for i in range(n)]
        vals = [r[1][j][0] / r[1][j][1] for r in rows]
        ax.barh(ys, vals, height=h, color=c, zorder=2)
        for y, r, v in zip(ys, rows, vals):
            ax.text(v + 0.03, y, f"{r[1][j][0]}/{r[1][j][1]}", va="center", fontsize=6.2, color=INK2)
    ax.set_yticks(range(n)); ax.set_yticklabels([r[0] for r in rows], fontsize=7); ax.invert_yaxis()
    ax.set_xlim(0, 1.3); ax.set_xticks([0, 0.5, 1]); ax.set_xticklabels(["0", "50 %", "100 %"], fontsize=6.8)
    ax.xaxis.grid(True, color=GRID, lw=0.5); ax.set_axisbelow(True); ax.tick_params(axis="y", length=0)
    ax.set_title(title, loc="left", fontsize=8, color=INK, pad=4)


def fig5_detection():
    """comparison.md and comparison_split.md; false alarms per benign record in the labels."""
    fig, axs = plt.subplots(1, 3, figsize=(7.4, 3.0), gridspec_kw={"wspace": 0.95})
    panel(axs[0], [("D1 residual test\nFA 0.00059", [[5, 5], [3, 4], [2, 7]]), ("autoencoder, physics\nFA 0.00100", [[4, 5], [3, 4], [2, 7]]),
                   ("certified library, strict\nFA 0.00124", [[4, 5], [4, 4], [2, 7]]), ("detectors + library\nFA 0.00171", [[5, 5], [4, 4], [3, 7]])],
          "(a) 01-Basic, recorded day")
    panel(axs[1], [("SE-BDD\nFA 0.00000", [[3, 5], [4, 9], [0, 9]]), ("autoencoder, SE features\nFA 0.149", [[4, 5], [6, 9], [7, 9]]),
                   ("certified library, L = 3\nFA 0.00401", [[4, 5], [6, 9], [0, 9]]), ("certified library, 1 record\nFA 0.0159", [[5, 5], [7, 9], [7, 9]])],
          "(b) 02-Semiurban, recorded day")
    panel(axs[2], [("SE-BDD\nFA 0.00000", [[1, 7], [1, 7], [0, 7]]), ("autoencoder, SE features\nFA 0.059", [[7, 7], [3, 7], [0, 7]]),
                   ("certified library, L = 3\nFA 0.00000", [[7, 7], [4, 7], [0, 7]]), ("certified library, 1 record\nFA 0.0042", [[7, 7], [6, 7], [0, 7]])],
          "(c) 02-Semiurban, additional day")
    handles = [Line2D([], [], marker="s", ls="", color=c, ms=7, label=t) for t, c in (("control-and-freeze", BLUE), ("drift-off", ORANGE), ("industroyer", AQUA))]
    fig.legend(handles=handles, fontsize=7, frameon=False, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.01))
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    save(fig, "fig5_detection")


# ---------------------------------------------------------------- Fig 6: false alarms, log scale
def fig6_false_alarms():
    """comparison.md (three grids). Zero rates are drawn at the left edge and labelled 0."""
    rows = [("01-Basic", [("D1 residual test", 0.00059, BLUE), ("certified library, strict", 0.00124, ORANGE), ("library + per-topology calibration", 0.00056, ORANGE),
                          ("autoencoder, physics features", 0.00100, MUTED), ("autoencoder, raw telemetry", 0.99988, MUTED)]),
            ("02-Semiurban", [("SE-BDD", 0.0, BLUE), ("certified library, L = 3", 0.00401, ORANGE), ("autoencoder, SE features", 0.14888, MUTED), ("autoencoder, raw telemetry", 0.85948, MUTED)]),
            ("03-Rural (zero training)", [("SE-BDD, transferred threshold", 0.00017, BLUE), ("library, transferred noise floors", 0.723, ORANGE), ("library, 30 min calibration", 0.184, ORANGE),
                                         ("autoencoder, SE features (30 min)", 0.14358, MUTED), ("autoencoder, raw (30 min)", 0.43249, MUTED)])]
    fig, axs = plt.subplots(3, 1, figsize=(7.4, 4.2), sharex=True, gridspec_kw={"height_ratios": [5, 4, 5], "hspace": 0.35})
    lo = 1e-4
    for ax, (g, items) in zip(axs, rows):
        for i, (name, v, c) in enumerate(items):
            x = max(v, lo)
            ax.plot([lo, x], [i, i], color=c, lw=4, solid_capstyle="butt", zorder=2)
            lab = "0 (no false alarm)" if v == 0 else (f"{v * 100:.3f} %" if v < 0.01 else f"{v * 100:.1f} %")
            ax.text(x * 1.15, i, lab, va="center", fontsize=6.5, color=INK2)
        ax.set_yticks(range(len(items))); ax.set_yticklabels([n for n, _, _ in items], fontsize=6.8); ax.invert_yaxis()
        ax.set_xscale("log"); ax.set_xlim(lo, 3.0); ax.tick_params(axis="y", length=0)
        ax.xaxis.grid(True, color=GRID, lw=0.5); ax.set_axisbelow(True)
        ax.set_title(g, loc="left", fontsize=8, color=INK, pad=3)
    axs[-1].set_xticks([1e-4, 1e-3, 1e-2, 1e-1, 1]); axs[-1].set_xticklabels(["0.01 %", "0.1 %", "1 %", "10 %", "100 %"], fontsize=7)
    axs[-1].set_xlabel("false alarms per benign record (log scale)", fontsize=7.5)
    handles = [Line2D([], [], color=c, lw=4, label=l) for l, c in (("classic physics detector", BLUE), ("certified rule library", ORANGE), ("machine-learning detector", MUTED))]
    fig.legend(handles=handles, fontsize=7, frameon=False, loc="upper right", bbox_to_anchor=(0.99, 1.0), ncol=3)
    save(fig, "fig6_false_alarms")


# ---------------------------------------------------------------- Fig 7: pooled detection with CIs
def fig7_pooled():
    """statistics.md, statistics_split.md."""
    data = [("recorded test days\n61 instances, 3 grids", [(22, 61, .25, .49), (25, 61, .30, .54), (27, 61, .33, .57)]),
            ("recorded + additional day\n103 instances", [(35, 103, .26, .44), (42, 103, .32, .50), (49, 103, .38, .57)])]
    fig, ax = plt.subplots(figsize=(3.6, 2.5))
    cols = [BLUE, ORANGE, AQUA]; names = ["classic detector", "certified library", "combined"]
    for g, (lab, rows) in enumerate(data):
        for k, (a, n, lo, hi) in enumerate(rows):
            x = g * 3.6 + k * 0.95; p = a / n
            ax.bar(x, p, color=cols[k], width=0.8, zorder=2, label=names[k] if g == 0 else None)
            ax.errorbar(x, p, yerr=[[p - lo], [hi - p]], fmt="none", ecolor=INK, capsize=2.5, lw=0.8, zorder=3)
            ax.text(x, hi + 0.025, f"{a}/{n}", ha="center", fontsize=6.3, color=INK2)
    ax.set_xticks([0.95, 4.55]); ax.set_xticklabels([d[0] for d in data], fontsize=6.8)
    ax.set_ylim(0, 1.0); ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0]); ax.set_yticklabels(["0", "25 %", "50 %", "75 %", "100 %"], fontsize=7)
    ax.set_ylabel("process attacks detected", fontsize=7.5)
    ax.yaxis.grid(True, color=GRID, lw=0.5); ax.set_axisbelow(True)
    ax.legend(fontsize=6.5, frameon=False, loc="upper left", ncol=1, handlelength=1.0)
    ax.text(5.5, 0.93, "combined vs classic (McNemar)\n5 / 0 only-one detects, p = 0.062\n14 / 0, p = 0.00012", fontsize=6.2, ha="right", va="top", color=INK2)
    save(fig, "fig7_pooled")


# ---------------------------------------------------------------- Fig 8: what calibration does
def fig8_calibration():
    """comparison.md, comparison_split.md (WP5 rows); semiurban_consolidation_*_rural.md."""
    fig, axs = plt.subplots(1, 2, figsize=(7.4, 2.4), gridspec_kw={"wspace": 0.55})
    ax = axs[0]
    groups = ["recorded day", "additional day"]
    before, after = [0.00124, 0.01432], [0.00056, 0.00346]
    x = [0, 1]
    ax.bar([i - 0.2 for i in x], before, width=0.36, color=MUTED, label="train-day noise only", zorder=2)
    ax.bar([i + 0.2 for i in x], after, width=0.36, color=ORANGE, label="+ 5 min online calibration per new topology", zorder=2)
    for i in x:
        ax.text(i - 0.2, before[i] * 1.15, f"{before[i] * 100:.2f} %", ha="center", fontsize=6.3, color=INK2)
        ax.text(i + 0.2, after[i] * 1.15, f"{after[i] * 100:.2f} %", ha="center", fontsize=6.3, color=INK2)
    ax.set_yscale("log"); ax.set_ylim(2e-4, 1.5e-1); ax.set_yticks([1e-3, 1e-2]); ax.set_yticklabels(["0.1 %", "1 %"], fontsize=7)
    ax.set_xticks(x); ax.set_xticklabels(groups, fontsize=7); ax.set_ylabel("library false alarms per benign record", fontsize=7)
    ax.yaxis.grid(True, color=GRID, lw=0.5); ax.set_axisbelow(True)
    ax.legend(fontsize=6.2, frameon=False, loc="upper left", ncol=1)
    ax.set_title("(a) 01-Basic: per-topology calibration, detection unchanged", loc="left", fontsize=8, color=INK)
    ax = axs[1]
    items = [("SE-BDD, threshold transferred", 0.00017, BLUE), ("library, noise floors transferred", 0.723, ORANGE),
             ("library, transferred global margin", 0.00017, ORANGE), ("library, 30 min local calibration", 0.184, ORANGE)]
    for i, (n, v, c) in enumerate(items):
        ax.plot([1e-4, v], [i, i], color=c, lw=4, solid_capstyle="butt", zorder=2)
        ax.text(v * 1.2, i, f"{v * 100:.3f} %" if v < 0.01 else f"{v * 100:.1f} %", va="center", fontsize=6.3, color=INK2)
    ax.set_yticks(range(len(items))); ax.set_yticklabels([n for n, _, _ in items], fontsize=6.8); ax.invert_yaxis()
    ax.set_xscale("log"); ax.set_xlim(1e-4, 3); ax.set_xticks([1e-4, 1e-3, 1e-2, 1e-1, 1]); ax.set_xticklabels(["0.01 %", "0.1 %", "1 %", "10 %", "100 %"], fontsize=6.8)
    ax.tick_params(axis="y", length=0); ax.xaxis.grid(True, color=GRID, lw=0.5); ax.set_axisbelow(True)
    ax.set_xlabel("false alarms per benign record", fontsize=7)
    ax.set_title("(b) 03-Rural: what transfers without local data", loc="left", fontsize=8, color=INK)
    save(fig, "fig8_calibration")


if __name__ == "__main__":
    fig1_architecture(); fig2_oracle(); fig3_cegis(); fig4_timeline(); fig5_detection(); fig6_false_alarms(); fig7_pooled(); fig8_calibration()
    print(sorted(p.name for p in OUT.iterdir() if p.suffix == ".png"))
