"""Figures for the paper draft (reports/figures/). Every number is copied from a generated report,
named in the figure's docstring comment. Output: SVG (for the HTML/PDF draft)."""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = Path(__file__).resolve().parents[1] / "reports" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({"font.family": "serif", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
C_CLASSIC, C_LIB, C_COMB, C_ML, C_GRID = "#4c6a8f", "#c0702a", "#2f7d4f", "#9a9a9a", "#d9d9d9"


def fig1_loop():
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    ax.set_xlim(0, 10); ax.set_ylim(-0.6, 3.2); ax.axis("off")
    boxes = [(0.1, "Detectors\n(D1, SE-BDD, ML)", C_GRID), (2.0, "Alert\n60 s window", C_GRID), (3.9, "Covered by\nlibrary?", C_GRID),
             (5.8, "Synthesise\ncandidates\n(P, G, S, SE)", C_GRID), (7.9, "Physics oracle\nsearch + robust\nexact layer", "#f3e2c7")]
    for x, t, c in boxes:
        ax.add_patch(FancyBboxPatch((x, 1.5), 1.75, 1.25, boxstyle="round,pad=0.04", fc=c, ec="#444", lw=0.8))
        ax.text(x + 0.875, 2.125, t, ha="center", va="center", fontsize=8)
    for x0 in (1.85, 3.75, 5.65, 7.65):
        ax.add_patch(FancyArrowPatch((x0, 2.125), (x0 + 0.15, 2.125), arrowstyle="->", mutation_scale=10, lw=0.8))
    ax.text(5.72, 2.85, "no", fontsize=7, ha="center")
    ax.add_patch(FancyBboxPatch((3.9, -0.1), 1.75, 0.8, boxstyle="round,pad=0.04", fc="#dfe9f3", ec="#444", lw=0.8))
    ax.text(4.775, 0.3, "Certified rule\nlibrary", ha="center", va="center", fontsize=8)
    ax.add_patch(FancyArrowPatch((4.775, 1.5), (4.775, 0.75), arrowstyle="<-", mutation_scale=10, lw=0.8))
    ax.text(4.65, 1.12, "yes: already\ncovered", fontsize=7, va="center", ha="right")
    ax.add_patch(FancyArrowPatch((8.775, 1.5), (8.775, 0.3), arrowstyle="-", lw=0.8, color="#2f7d4f"))
    ax.add_patch(FancyArrowPatch((8.775, 0.3), (5.7, 0.3), arrowstyle="->", mutation_scale=10, lw=0.8, color="#2f7d4f"))
    ax.text(7.25, 0.42, "no counterexample: certified", fontsize=7, color="#2f7d4f", ha="center")
    ax.add_patch(FancyArrowPatch((8.0, 1.5), (6.7, 1.5), arrowstyle="->", mutation_scale=10, lw=0.8, color="#b03a32",
                                 connectionstyle="arc3,rad=-0.6"))
    ax.text(7.35, 0.95, "counterexample: refine margin (CEGIS)", fontsize=7, color="#b03a32", ha="center")
    ax.text(0.1, -0.45, "Labels are never used inside the loop; they only score the result afterwards.", fontsize=7, style="italic")
    fig.savefig(OUT / "fig1_loop.svg", bbox_inches="tight"); fig.savefig(OUT / "fig1_loop.png", dpi=150, bbox_inches="tight"); plt.close(fig)


def fig2_cegis():
    """cegis_demo_linac.md (reference grid, 10 iterations) and cegis_demo_linac_sherlock.md (2 iterations)."""
    ref = [0.94281, 0.91736, 0.90546, 0.90244, 0.90233, 0.90221, 0.90167, 0.90141, 0.90127, 0.90109, 0.90066]
    sh = [0.93327, 0.89998]
    fig, ax = plt.subplots(figsize=(3.5, 2.3))
    ax.plot(range(len(ref)), ref, "o-", ms=3.5, color=C_CLASSIC, label="reference CIGRE MV (linearised AC)")
    ax.plot(range(len(sh)), sh, "s-", ms=3.5, color=C_LIB, label="Sherlock 01-Basic (linearised AC)")
    ax.axhline(0.90, ls="--", color="#b03a32", lw=0.9); ax.text(10, 0.9008, "0.90 pu operating limit", color="#b03a32", fontsize=7, ha="right")
    ax.set_xlabel("CEGIS iteration"); ax.set_ylabel(r"threshold $\tau$ of rule R1, pu"); ax.set_ylim(0.895, 0.948)
    ax.legend(fontsize=6.5, frameon=False, loc="upper right")
    fig.savefig(OUT / "fig2_cegis.svg", bbox_inches="tight"); fig.savefig(OUT / "fig2_cegis.png", dpi=150, bbox_inches="tight"); plt.close(fig)


def grouped(ax, rows, title):
    types = ["CFC", "drift-off", "industroyer"]
    cols = [C_CLASSIC, C_LIB, "#6d5bb5"]
    n = len(rows); h = 0.24
    for j, t in enumerate(types):
        ys = [i - h + j * h for i in range(n)]
        vals = [r[1][j][0] / r[1][j][1] for r in rows]
        ax.barh(ys, vals, height=h * 0.92, color=cols[j], label=t if title.startswith("01-Basic") else None)
        for y, r in zip(ys, rows):
            ax.text(r[1][j][0] / r[1][j][1] + 0.02, y, f"{r[1][j][0]}/{r[1][j][1]}", va="center", fontsize=6)
    ax.set_yticks(range(n)); ax.set_yticklabels([r[0] for r in rows], fontsize=7); ax.invert_yaxis()
    ax.set_xlim(0, 1.25); ax.set_xticks([0, 0.5, 1]); ax.set_xticklabels(["0", "50 %", "100 %"], fontsize=7)
    ax.set_title(title, fontsize=8, loc="left")


def fig3_detection():
    """comparison.md and comparison_split.md. Labels carry false alarms per benign record."""
    fig, axs = plt.subplots(1, 3, figsize=(7.4, 2.9))
    grouped(axs[0], [("D1 residual (0.00059)", [[5, 5], [3, 4], [2, 7]]), ("AE physics (0.00100)", [[4, 5], [3, 4], [2, 7]]),
                     ("library, strict (0.00124)", [[4, 5], [4, 4], [2, 7]]), ("combined (0.00171)", [[5, 5], [4, 4], [3, 7]])],
            "01-Basic, recorded day")
    grouped(axs[1], [("SE-BDD (0.00000)", [[3, 5], [4, 9], [0, 9]]), ("AE SE-feat. (0.149)", [[4, 5], [6, 9], [7, 9]]),
                     ("library, L=3 (0.00401)", [[4, 5], [6, 9], [0, 9]]), ("library, 1 rec. (0.0159)", [[5, 5], [7, 9], [7, 9]])],
            "02-Semiurban, recorded day")
    grouped(axs[2], [("SE-BDD (0.00000)", [[1, 7], [1, 7], [0, 7]]), ("AE SE-feat. (0.059)", [[7, 7], [3, 7], [0, 7]]),
                     ("library, L=3 (0.00000)", [[7, 7], [4, 7], [0, 7]]), ("library, 1 rec. (0.0042)", [[7, 7], [6, 7], [0, 7]])],
            "02-Semiurban, additional day")
    fig.legend(fontsize=7, frameon=False, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout(rect=(0, 0.05, 1, 1)); fig.savefig(OUT / "fig3_detection.svg", bbox_inches="tight"); fig.savefig(OUT / "fig3_detection.png", dpi=150, bbox_inches="tight"); plt.close(fig)


def fig4_pooled():
    """statistics.md and statistics_split.md: pooled detection with Wilson 95 % intervals."""
    data = [("recorded test days (61)", [(22, 61, .25, .49), (25, 61, .30, .54), (27, 61, .33, .57)]),
            ("recorded + additional day (103)", [(35, 103, .26, .44), (42, 103, .32, .50), (49, 103, .38, .57)])]
    fig, ax = plt.subplots(figsize=(3.6, 2.3))
    cols = [C_CLASSIC, C_LIB, C_COMB]; names = ["classic detector", "certified library", "combined"]
    for g, (lab, rows) in enumerate(data):
        for k, (a, n, lo, hi) in enumerate(rows):
            x = g * 4 + k; p = a / n
            ax.bar(x, p, color=cols[k], width=0.8, label=names[k] if g == 0 else None)
            ax.errorbar(x, p, yerr=[[p - lo], [hi - p]], fmt="none", ecolor="#222", capsize=2, lw=0.8)
            ax.text(x, hi + 0.02, f"{a}/{n}", ha="center", fontsize=6)
    ax.set_xticks([1, 5]); ax.set_xticklabels([d[0] for d in data], fontsize=7); ax.set_ylim(0, 1); ax.set_ylabel("process attacks detected")
    ax.legend(fontsize=6.5, frameon=False, loc="upper left")
    ax.text(5, 0.92, "McNemar, combined vs classic:\n5 / 0 (p = 0.062); 14 / 0 (p = 0.00012)", fontsize=6, ha="center")
    fig.savefig(OUT / "fig4_pooled.svg", bbox_inches="tight"); fig.savefig(OUT / "fig4_pooled.png", dpi=150, bbox_inches="tight"); plt.close(fig)


if __name__ == "__main__":
    fig1_loop(); fig2_cegis(); fig3_detection(); fig4_pooled()
    print(sorted(p.name for p in OUT.iterdir()))
