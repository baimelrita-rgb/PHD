"""Regenerate all manuscript figures (Figs. 1-8) in a consistent journal style.

Output: figures/out/fig{N}.pdf (vector, for submission) and fig{N}.png (600 dpi,
for embedding in the Word manuscript).

Style: Liberation Sans (metric-compatible with Arial), 7-9 pt at final print
size, Okabe-Ito colour-blind-safe accents, one colour per head used
consistently across all figures:
    Detection = blue, Blast-Radius = orange, Explainability = green.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Circle

OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

plt.rcParams.update({
    "font.family": "Liberation Sans",
    "font.size": 8,
    "mathtext.fontset": "stixsans",
    "pdf.fonttype": 42,  # embed TrueType, editable text
    "svg.fonttype": "none",
    "axes.linewidth": 0.6,
})

INK = "#222222"
GREY = "#6b6b6b"
# (edge, fill) pairs
NEUTRAL = ("#555555", "#f2f2f2")
INPUT = ("#555555", "#ffffff")
ENC = ("#3a3a3a", "#e4e4e4")
DET = ("#0072B2", "#dcebf5")
BLAST = ("#D55E00", "#fbe5d6")
EXPL = ("#009E73", "#d9f0e8")
MITRE = ("#7a5195", "#ece3f2")

W_FULL = 6.3  # inches, matches the width used in the manuscript


def canvas(w, h):
    fig = plt.figure(figsize=(w, h))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, title=None, body=None, style=NEUTRAL, dashed=False,
        title_size=8, body_size=7, bold=True, align="center", lw=0.8, r=0.05,
        zorder=2, title_dy=None):
    """Rounded box with optional bold title and body text; (x, y) = lower-left."""
    ec, fc = style
    p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                       ec=ec, fc=fc, lw=lw, ls=(0, (3, 2)) if dashed else "-",
                       zorder=zorder)
    ax.add_patch(p)
    cx = x + w / 2 if align == "center" else x + 0.08
    ha = "center" if align == "center" else "left"
    if title and body:
        ty = y + h - (title_dy if title_dy is not None else 0.14)
        ax.text(cx, ty, title, ha=ha, va="center", fontsize=title_size,
                fontweight="bold" if bold else "normal", color=INK, zorder=zorder + 1)
        ax.text(cx, (y + ty - 0.1) / 2 + 0.0, body, ha=ha, va="center",
                fontsize=body_size, color=INK, zorder=zorder + 1, linespacing=1.35)
    elif title:
        ax.text(cx, y + h / 2, title, ha=ha, va="center", fontsize=title_size,
                fontweight="bold" if bold else "normal", color=INK,
                zorder=zorder + 1, linespacing=1.3)
    return p


def group(ax, x, y, w, h, label, style=NEUTRAL, dashed=False, label_size=8):
    """Light container with a label in its upper-left corner."""
    ec, _ = style
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.07",
                                ec=ec, fc="none", lw=0.7,
                                ls=(0, (4, 2)) if dashed else "-", zorder=1))
    ax.text(x + 0.08, y + h - 0.1, label, ha="left", va="top", fontsize=label_size,
            fontweight="bold", color=ec, zorder=3)


def arrow(ax, p1, p2, color=INK, lw=0.8, dashed=False, conn=None, head=6, z=4):
    kw = dict(arrowstyle=f"-|>,head_length={head/10},head_width={head/20}",
              mutation_scale=8, color=color, lw=lw, shrinkA=0, shrinkB=0, zorder=z,
              linestyle=(0, (3, 2)) if dashed else "-")
    if conn:
        kw["connectionstyle"] = conn
    ax.add_patch(FancyArrowPatch(p1, p2, **kw))


def poly_arrow(ax, pts, **kw):
    """Orthogonal multi-segment arrow through pts; arrowhead on the last segment."""
    color = kw.get("color", INK)
    lw = kw.get("lw", 0.8)
    ls = (0, (3, 2)) if kw.get("dashed") else "-"
    xs, ys = zip(*pts[:-1])
    ax.plot(list(xs) + [pts[-2][0]], list(ys) + [pts[-2][1]], color=color, lw=lw,
            ls=ls, zorder=4, solid_capstyle="butt")
    arrow(ax, pts[-2], pts[-1], **kw)


def node(ax, x, y, r, label, style, size=7, z=5):
    ec, fc = style
    ax.add_patch(Circle((x, y), r, ec=ec, fc=fc, lw=0.8, zorder=z))
    ax.text(x, y, label, ha="center", va="center", fontsize=size, color=INK, zorder=z + 1)


def save(fig, n):
    fig.savefig(OUT / f"fig{n}.pdf")
    fig.savefig(OUT / f"fig{n}.png", dpi=600)
    plt.close(fig)


# --------------------------------------------------------------------------
# Fig. 1  Dynamic threat graph construction
# --------------------------------------------------------------------------
def fig1():
    fig, ax = canvas(W_FULL, 3.15)

    # Sources
    group(ax, 0.05, 0.35, 1.55, 2.7, "(a) Telemetry sources")
    srcs = ["EDR / endpoint logs", "Identity logs\n(Kerberos, LDAP, SSO)",
            "Network flow records", "Security events / alerts"]
    ys = [2.35, 1.75, 1.15, 0.55]
    for s, y in zip(srcs, ys):
        box(ax, 0.15, y - 0.2, 1.35, 0.42, s, style=INPUT, bold=False, title_size=7)

    # Aggregation
    group(ax, 1.85, 0.35, 1.5, 2.7, "(b) Entity aggregation")
    box(ax, 1.95, 1.25, 1.3, 1.1, "Temporal entity\naggregation",
        body="$\\Phi:\\mathcal{E}\\rightarrow V_{\\mathrm{meta}}$  (Eq. 1)\n"
             "window $\\Delta\\tau$ = 5 min\npooling (Eq. 2)",
        style=ENC, title_dy=0.25)
    box(ax, 1.95, 0.5, 1.3, 0.55, "Meta-nodes and\nmeta-edges", style=NEUTRAL,
        bold=False, title_size=7)
    arrow(ax, (2.6, 1.25), (2.6, 1.05))
    # fan-in arrows
    for y in ys:
        ax.plot([1.5, 1.72], [y, y], color=INK, lw=0.6, zorder=4)
    ax.plot([1.72, 1.72], [ys[-1], ys[0]], color=INK, lw=0.6, zorder=4)
    arrow(ax, (1.72, 1.8), (1.95, 1.8), lw=0.6)

    # Graph snapshot
    group(ax, 3.6, 0.35, 2.65, 2.7, "(c) Dynamic threat graph  $G_t=(V_t, E_t, \\mathbf{X}_t)$")
    U, H, P, I, D = (4.15, 2.25), (5.0, 2.25), (5.0, 1.35), (5.85, 1.35), (5.85, 2.25)
    node(ax, *U, 0.22, "User", MITRE, size=6.5)
    node(ax, *H, 0.22, "Host", DET, size=6.5)
    node(ax, *P, 0.22, "Process", NEUTRAL, size=6)
    node(ax, *I, 0.22, "IP", BLAST, size=6.5)
    node(ax, *D, 0.22, "Domain", EXPL, size=6)
    arrow(ax, (U[0] + 0.22, U[1]), (H[0] - 0.22, H[1]), lw=0.7)
    ax.text(4.575, 2.33, "logged_in_to\n[$t_1$]", ha="center", va="bottom", fontsize=6)
    arrow(ax, (H[0], H[1] - 0.22), (P[0], P[1] + 0.22), lw=0.7)
    ax.text(4.95, 1.8, "spawned [$t_2$]", ha="right", va="center", fontsize=6)
    arrow(ax, (P[0] + 0.22, P[1]), (I[0] - 0.22, I[1]), lw=0.7)
    ax.text(5.425, 1.1, "connected_to [$t_3$]", ha="center", va="top", fontsize=6)
    arrow(ax, (I[0], I[1] + 0.22), (D[0], D[1] - 0.22), lw=0.7, dashed=True)
    ax.text(5.9, 1.8, "resolves\n[$t_4$]", ha="left", va="center", fontsize=6)
    # snapshot strip
    for k, lab in enumerate(["$G_{t-1}$", "$G_t$", "$G_{t+1}$"]):
        x0 = 3.85 + k * 0.75
        ax.add_patch(FancyBboxPatch((x0, 0.5), 0.6, 0.4, boxstyle="round,pad=0,rounding_size=0.03",
                                    ec=GREY, fc="#ffffff" if k != 1 else "#e4e4e4", lw=0.6, zorder=2))
        ax.text(x0 + 0.3, 0.7, lab, ha="center", va="center", fontsize=7, zorder=3)
        if k < 2:
            arrow(ax, (x0 + 0.6, 0.7), (x0 + 0.75, 0.7), lw=0.6, color=GREY)
    ax.text(6.15, 0.7, "time", ha="right", va="center", fontsize=6, color=GREY, style="italic")

    arrow(ax, (3.25, 1.8), (3.6, 1.8))
    ax.text(W_FULL / 2, 0.12,
            "Node and edge types shown are those supported by the framework; the feasibility "
            "study (Section 5) instantiates IP nodes and flow meta-edges only.",
            ha="center", va="center", fontsize=6.5, color=GREY, style="italic")
    save(fig, 1)


# --------------------------------------------------------------------------
# Fig. 2  Feature engineering pipeline
# --------------------------------------------------------------------------
def fig2():
    fig, ax = canvas(W_FULL, 2.85)
    top, h = 2.75, 1.85
    y0 = top - h
    # Node features
    group(ax, 0.05, y0, 2.35, h, "Node features (Sec. 3.3)", style=DET)
    rows = [("Distance to crown jewels", "$d_{\\mathrm{CJ}}(i)=\\min_{c\\in C}\\,\\mathrm{dist}(i,c)$", "Eq. 8"),
            ("Approx. eigenvector centrality", "power-iteration step", "Eq. 4"),
            ("Temporal burstiness", "degree vs. EMA, standardised", "Eq. 5"),
            ("Local connectivity", "in/out-degree, weighted freq.", "")]
    for k, (a, b, e) in enumerate(rows):
        yy = top - 0.5 - k * 0.36
        ax.text(0.15, yy + 0.06, a, fontsize=7, fontweight="bold", va="center")
        ax.text(0.15, yy - 0.09, b, fontsize=6.5, va="center", color=INK)
        ax.text(2.3, yy + 0.06, e, fontsize=6.5, va="center", ha="right", color=GREY)
        if k < 3:
            ax.plot([0.15, 2.3], [yy - 0.2, yy - 0.2], color="#cccccc", lw=0.5)

    # Edge features
    group(ax, 2.55, y0, 2.0, h, "Edge features (Eq. 6)", style=BLAST)
    ax.text(3.55, top - 0.5, "$\\mathbf{x}_{ij}=[\\,\\phi_{\\mathrm{struct}}(i,j)\\;\\|\\;\\mathrm{T2V}(t)\\;\\|\\;\\mathbf{e}_{\\mathrm{mitre}}(t)\\,]$",
            ha="center", va="center", fontsize=7.2)
    items = [("$\\phi_{\\mathrm{struct}}$", "structural relations"),
             ("T2V$(t)$", "Time2Vec encoding [6]"),
             ("$\\mathbf{e}_{\\mathrm{mitre}}$", "ATT&CK embedding (optional)")]
    for k, (a, b) in enumerate(items):
        yy = top - 0.88 - k * 0.3
        box(ax, 2.65, yy - 0.12, 0.55, 0.24, a, style=("#999999", "#ffffff"), bold=False, title_size=7)
        ax.text(3.28, yy, b, fontsize=6.5, va="center")

    # Aggregation & training signal
    group(ax, 4.7, y0, 1.55, h, "Structure & training", style=MITRE)
    box(ax, 4.8, top - 0.95, 1.35, 0.6, "Meta-node aggregation",
        body="$\\Phi$ (Eqs. 1, 7)", style=("#999999", "#ffffff"), title_size=7, title_dy=0.17, body_size=6.5)
    box(ax, 4.8, y0 + 0.1, 1.35, 0.6, "Causal consistency",
        body="$\\mathcal{L}_{\\mathrm{causal}}$ (Eq. 9)\ntraining signal", style=("#999999", "#ffffff"),
        title_size=7, dashed=True, title_dy=0.15, body_size=6.3)

    # Encoder
    box(ax, 2.35, 0.05, 1.6, 0.42, "ST-GNN encoder (Sec. 3.4)", style=ENC, title_size=7.5)
    poly_arrow(ax, [(1.225, y0), (1.225, 0.26), (2.35, 0.26)])
    arrow(ax, (3.55, y0), (3.55, 0.47))
    poly_arrow(ax, [(5.475, y0 + 0.1), (5.475, 0.26), (3.95, 0.26)], dashed=True, color=GREY)
    save(fig, 2)


# --------------------------------------------------------------------------
# Fig. 3  MITRE-aware ST-GNN engine
# --------------------------------------------------------------------------
def fig3():
    fig, ax = canvas(W_FULL, 3.6)
    # Left: semantic MITRE branch
    group(ax, 0.05, 1.05, 2.3, 2.45, "Semantic ATT&CK branch (Sec. 3.5)", style=MITRE)
    box(ax, 0.15, 2.7, 2.1, 0.45, "ATT&CK technique descriptions", style=INPUT, bold=False, title_size=7)
    box(ax, 0.15, 2.0, 2.1, 0.5, "Text encoder (ATTACK-BERT)",
        body="$E(v_i)\\in\\mathbb{R}^{d}$", style=MITRE, title_size=7.2, title_dy=0.15)
    box(ax, 0.15, 1.15, 2.1, 0.65, "Attack state graph",
        body="edge $v_i\\!\\rightarrow\\!v_j$ if $\\cos(E(v_i),E(v_j))>\\theta$\n(Eq. 12)",
        style=MITRE, title_size=7.2, title_dy=0.15)
    arrow(ax, (1.2, 2.7), (1.2, 2.5))
    arrow(ax, (1.2, 2.0), (1.2, 1.8))

    # Middle: encoder
    group(ax, 2.55, 1.05, 2.0, 2.45, "Spatiotemporal encoder (Sec. 3.4)")
    box(ax, 2.65, 2.7, 1.8, 0.45, "Threat graph $G_t$, features $\\mathbf{X}_t$, $\\mathbf{x}_{ij}$",
        style=INPUT, bold=False, title_size=6.8)
    box(ax, 2.65, 1.75, 1.8, 0.75, "GAT layers ($\\times L$)",
        body="attention $\\alpha_{ij}$ over\n$[W h_i \\| W h_j \\| \\mathbf{e}^{t}_{ij}]$ (Eqs. 10-11)",
        style=ENC, title_size=7.2, title_dy=0.15)
    box(ax, 2.65, 1.15, 1.8, 0.42, "EMA node memory (Sec. 3.8)", style=NEUTRAL, bold=False, title_size=6.8)
    arrow(ax, (3.55, 2.7), (3.55, 2.5))
    arrow(ax, (3.3, 1.57), (3.3, 1.75))
    arrow(ax, (3.8, 1.75), (3.8, 1.57))
    # MITRE embedding into edge features
    poly_arrow(ax, [(2.25, 2.25), (2.45, 2.25), (2.45, 2.92), (2.65, 2.92)], color=MITRE[0], lw=0.7)
    ax.text(2.48, 2.58, "$\\mathbf{e}_{\\mathrm{mitre}}$", ha="left", va="center", fontsize=6.5, color=MITRE[0])

    # Right: embeddings
    box(ax, 4.75, 1.85, 1.5, 0.75, "Shared\nrepresentation",
        body="$h_i^{(L)}$,  $z_{G_t}$", style=ENC, title_size=7.2, title_dy=0.22)
    arrow(ax, (4.45, 2.12), (4.75, 2.12))

    # Heads row
    hy, hh = 0.1, 0.72
    heads = [(0.6, "Detection Head", "window / edge classes\n(Sec. 3.6.1)", DET),
             (2.55, "Blast-Radius Head", "node risk $\\hat p_i$\n(Sec. 3.6.2)", BLAST),
             (4.5, "Explainability Head", "edge mask $m_{ij}$\n(Sec. 3.6.3)", EXPL)]
    ax.plot([5.5, 5.5], [1.85, 0.95], color=INK, lw=0.8, zorder=4)
    ax.plot([1.35, 5.5], [0.95, 0.95], color=INK, lw=0.8, zorder=4)
    for x, t, b, st in heads:
        box(ax, x, hy, 1.5, hh, t, body=b, style=st, title_size=7.5, title_dy=0.16)
        arrow(ax, (x + 0.75, 0.95), (x + 0.75, hy + hh))
    # T_mitre to explainability
    ax.plot([0.25, 0.25], [1.15, 0.03], color=MITRE[0], lw=0.7, ls=(0, (3, 2)), zorder=4)
    ax.plot([0.25, 6.2], [0.03, 0.03], color=MITRE[0], lw=0.7, ls=(0, (3, 2)), zorder=4)
    ax.plot([6.2, 6.2], [0.03, 0.46], color=MITRE[0], lw=0.7, ls=(0, (3, 2)), zorder=4)
    arrow(ax, (6.2, 0.46), (6.0, 0.46), color=MITRE[0], lw=0.7, dashed=True)
    ax.text(0.38, 0.55, "$T_{\\mathrm{mitre}}$: $\\mathcal{L}_{\\mathrm{causal}}$, annotation",
            ha="center", va="center", fontsize=6, color=MITRE[0], rotation=90)
    save(fig, 3)


# --------------------------------------------------------------------------
# Fig. 4  Detection head (window-level) + per-edge head
# --------------------------------------------------------------------------
def fig4():
    fig, ax = canvas(W_FULL, 2.2)
    bw, bh = 1.15, 0.62
    # top: window-level
    ax.text(0.05, 2.15, "(a) Window-level Detection Head", fontsize=8, fontweight="bold", color=DET[0], va="top")
    y = 1.3
    xs = [0.05, 1.35, 2.65, 3.95, 5.15]
    box(ax, xs[0], y, bw, bh, "Node embeddings", body="$\\{h_i^{(L)}\\}_{i\\in V_t}$", style=ENC, title_size=7, title_dy=0.17)
    box(ax, xs[1], y, bw, bh, "READOUT", body="mean / attention\npooling (Eq. 13)", style=DET, title_size=7, title_dy=0.15)
    box(ax, xs[2], y, bw, bh, "Linear layer", body="$W_{\\mathrm{det}} z_{G_t}+b_{\\mathrm{det}}$\n(Eq. 14)", style=DET, title_size=7, title_dy=0.15)
    box(ax, xs[3], y, 1.05, bh, "Output", body="softmax (single-label)\nor sigmoid (multi-label)", style=DET, title_size=7, title_dy=0.15, body_size=6.3)
    box(ax, xs[4], y, 1.1, bh, "Loss", body="CE (Eq. 15) or BCE\nvs. multi-hot $\\mathbf{y}_w$", style=("#999999", "#ffffff"), title_size=7, title_dy=0.15, body_size=6.3)
    for a, b in zip(xs[:-1], xs[1:]):
        w = bw if a != xs[3] else 1.05
        arrow(ax, (a + w, y + bh / 2), (b, y + bh / 2))

    # bottom: per-edge
    ax.text(0.05, 1.0, "(b) Per-edge classification head (rare-class recovery)", fontsize=8, fontweight="bold", color=DET[0], va="top")
    y = 0.1
    box(ax, xs[0], y, bw, bh, "Edge representation", body="$[\\,h_i \\| h_j \\| \\mathbf{x}_{ij}\\,]$", style=ENC, title_size=7, title_dy=0.17)
    box(ax, xs[1], y, 2.45, bh, "Shared edge classifier (MLP)", body="applied to every meta-edge $(i,j)\\in E_t$, no pooling", style=DET, title_size=7, title_dy=0.17)
    box(ax, xs[3], y, 1.05, bh, "Output", body="softmax over $K$\nclasses per edge", style=DET, title_size=7, title_dy=0.15, body_size=6.3)
    box(ax, xs[4], y, 1.1, bh, "Loss", body="CE vs. edge\nplurality label", style=("#999999", "#ffffff"), title_size=7, title_dy=0.15, body_size=6.3)
    arrow(ax, (xs[0] + bw, y + bh / 2), (xs[1], y + bh / 2))
    arrow(ax, (xs[1] + 2.45, y + bh / 2), (xs[3], y + bh / 2))
    arrow(ax, (xs[3] + 1.05, y + bh / 2), (xs[4], y + bh / 2))
    save(fig, 4)


# --------------------------------------------------------------------------
# Fig. 5  Blast-radius head
# --------------------------------------------------------------------------
def fig5():
    fig, ax = canvas(W_FULL, 2.7)
    y, bh = 1.45, 0.75
    box(ax, 0.05, y, 1.15, bh, "Shared\nrepresentation", body="$h_i^{(L)}$,  $z_{G_t}$", style=ENC, title_size=7, title_dy=0.22)
    box(ax, 1.45, y, 1.2, bh, "Concatenate", body="$[\\,h_i^{(L)} \\| z_{G_t}\\,]$\nper node $i$", style=BLAST, title_size=7, title_dy=0.17)
    box(ax, 2.9, y, 1.2, bh, "$f_{\\mathrm{blast}}$ (MLP)", body="shared across nodes\n$s_i$ (Eq. 16)", style=BLAST, title_size=7, title_dy=0.17)
    box(ax, 4.35, y, 0.85, bh, "Sigmoid", body="$\\hat p_i=\\sigma(s_i)$\n(Eq. 17)", style=BLAST, title_size=7, title_dy=0.17)
    box(ax, 5.45, y, 0.8, bh, "Ranked\nat-risk\nnodes", style=("#999999", "#ffffff"), title_size=7)
    for a, b in [(1.2, 1.45), (2.65, 2.9), (4.1, 4.35), (5.2, 5.45)]:
        arrow(ax, (a, y + bh / 2), (b, y + bh / 2))

    # label generation + loss
    box(ax, 0.05, 0.1, 2.6, 0.95, "Look-ahead label  $y_i^{\\mathrm{future}}$",
        body="1 if node $i$ is compromised for the first time\nin $(t, t+\\Delta]$; nodes already compromised\nat $t$ are excluded (Sec. 4.1, App. B.2)",
        style=("#999999", "#ffffff"), title_size=7, title_dy=0.16, body_size=6.3)
    box(ax, 2.9, 0.1, 1.2, 0.95, "$\\mathcal{L}_{\\mathrm{blast}}$", body="node-wise BCE\n(Eq. 18)", style=("#999999", "#ffffff"), title_size=7.5, title_dy=0.2)
    arrow(ax, (2.65, 0.575), (2.9, 0.575))
    poly_arrow(ax, [(4.775, y), (4.775, 1.25), (3.5, 1.25), (3.5, 1.05)])
    ax.text(4.12, 1.29, "$\\hat p_i$", fontsize=6.5, ha="center", va="bottom", color=GREY)
    arrow(ax, (5.85, y), (5.85, 1.05), dashed=True, color=GREY)
    # design-target box
    box(ax, 4.35, 0.1, 1.9, 0.95, "Propagation paths (design target)",
        body="constrained by topology and\nATT&CK transitions $T_{\\mathrm{mitre}}$",
        style=("#999999", "#ffffff"), dashed=True, title_size=6.8, title_dy=0.16, body_size=6.3)
    ax.plot([], [])
    ax.text(W_FULL / 2, 2.55, "Implemented and jointly trained; not evaluated in this paper (Sec. 5.4).",
            ha="center", va="center", fontsize=6.5, color=GREY, style="italic")
    save(fig, 5)


# --------------------------------------------------------------------------
# Fig. 6  Explainability head
# --------------------------------------------------------------------------
def fig6():
    fig, ax = canvas(W_FULL, 1.75)
    y, bh = 0.75, 0.78
    specs = [(0.05, 1.05, "Edge\nrepresentation", "$[\\,h_i\\|h_j\\|\\mathbf{x}_{ij}\\,]$", ENC),
             (1.3, 1.0, "Mask scorer", "$m_{ij}=\\sigma(g(\\cdot))$\n(Eq. 19)", EXPL),
             (2.5, 1.0, "Threshold", "$m_{ij}>\\tau$\n(Eq. 20)", EXPL),
             (3.7, 1.15, "ATT&CK\nannotation", "tactics via $T_{\\mathrm{mitre}}$", MITRE),
             (5.05, 1.2, "Explanation\nsubgraph", "$E^{\\mathrm{expl}}_t$, attack story", ("#999999", "#ffffff"))]
    for x, w, t, b, st in specs:
        box(ax, x, y, w, bh, t, body=b, style=st, title_size=7, title_dy=0.22, body_size=6.3)
    for (x, w, *_), (x2, *__) in zip(specs[:-1], specs[1:]):
        arrow(ax, (x + w, y + bh / 2), (x2, y + bh / 2))
    # losses
    box(ax, 1.3, 0.05, 1.0, 0.45, "$\\mathcal{L}_{\\mathrm{sparsity}}$ (Eq. 21)", style=("#999999", "#ffffff"), title_size=6.8, bold=False)
    box(ax, 2.5, 0.05, 2.35, 0.45, "$\\mathcal{L}_{\\mathrm{causal}}$ vs. $T_{\\mathrm{mitre}}$ (Eq. 9)", style=("#999999", "#ffffff"), title_size=6.8, bold=False)
    arrow(ax, (1.8, 0.5), (1.8, y), dashed=True, color=GREY)
    arrow(ax, (3.0, 0.5), (3.0, y), dashed=True, color=GREY)
    ax.text(5.65, 0.27, "dashed: training signal", fontsize=6, color=GREY, ha="center", va="center", style="italic")
    save(fig, 6)


# --------------------------------------------------------------------------
# Fig. 7  Framework overview with planned anomaly-detection layer
# --------------------------------------------------------------------------
def fig7():
    fig, ax = canvas(W_FULL, 3.0)
    # pipeline row
    y, bh = 2.05, 0.7
    row = [(0.05, 1.05, "Telemetry", "EDR, identity,\nnetwork, alerts", INPUT),
           (1.3, 1.1, "Graph\nconstruction", "meta-nodes/edges\n(Secs. 3.1-3.2)", NEUTRAL),
           (2.6, 1.1, "Feature\nengineering", "graph metrics, T2V,\nATT&CK (Sec. 3.3)", NEUTRAL),
           (3.9, 1.1, "ST-GNN\nencoder", "GAT + EMA memory\n(Secs. 3.4, 3.8)", ENC)]
    for x, w, t, b, st in row:
        box(ax, x, y, w, bh, t, body=b, style=st, title_size=7, title_dy=0.2, body_size=6.2)
    for (x, w, *_), (x2, *__) in zip(row[:-1], row[1:]):
        arrow(ax, (x + w, y + bh / 2), (x2, y + bh / 2))
    box(ax, 5.25, 2.2, 1.0, 0.4, "ATT&CK\nknowledge", style=MITRE, title_size=6.5)
    arrow(ax, (5.25, 2.4), (5.0, 2.4), color=MITRE[0], lw=0.7)

    # heads
    hy, hh = 0.95, 0.65
    heads = [(0.05, "Detection Head", DET, False), (1.6, "Blast-Radius Head", BLAST, False),
             (3.15, "Explainability Head", EXPL, False)]
    ax.plot([4.45, 4.45], [y, 1.8], color=INK, lw=0.8, zorder=4)
    ax.plot([0.8, 5.45], [1.8, 1.8], color=INK, lw=0.8, zorder=4)
    for x, t, st, d in heads:
        box(ax, x, hy, 1.5, hh, t, style=st, title_size=7.2)
        arrow(ax, (x + 0.75, 1.8), (x + 0.75, hy + hh))
    box(ax, 4.7, hy, 1.55, hh, "Graph anomaly\ndetection layer",
        body="autoencoder / one-class", style=("#888888", "#ffffff"), dashed=True,
        title_size=7, title_dy=0.2, body_size=6.2)
    arrow(ax, (5.45, 1.8), (5.45, hy + hh), dashed=True, color=GREY)

    # loss + outputs
    box(ax, 0.05, 0.08, 4.6, 0.55, "Composite loss  $\\mathcal{L}=\\mathcal{L}_{\\mathrm{detect}}+\\alpha\\mathcal{L}_{\\mathrm{blast}}+\\beta\\mathcal{L}_{\\mathrm{sparsity}}+\\gamma\\mathcal{L}_{\\mathrm{causal}}$  (Eq. 22)",
        style=("#999999", "#ffffff"), title_size=7, bold=False)
    for x in (0.8, 2.35, 3.9):
        arrow(ax, (x, hy), (x, 0.63))
    box(ax, 4.7, 0.08, 1.55, 0.55, "Rarity score\n(e.g. top 0.5%)", style=("#888888", "#ffffff"), dashed=True, title_size=6.6, bold=False)
    arrow(ax, (5.475, hy), (5.475, 0.63), dashed=True, color=GREY)
    save(fig, 7)


# --------------------------------------------------------------------------
# Fig. 8  Per-class F1, window vs. edge level (values from Table 2)
# --------------------------------------------------------------------------
def fig8():
    import numpy as np
    classes = ["Benign", "DoS", "Generic", "Exploits", "Fuzzers", "Recon.", "Shellcode", "Macro"]
    win_m = [0.842, 0.853, 0.878, 0.916, 0.901, 0.916, 0.641, 0.849]
    win_s = [0.116, 0.085, 0.055, 0.064, 0.054, 0.064, 0.081, 0.066]
    edg_m = [1.000, 0.963, 0.941, 0.999, 1.000, 0.999, 0.943, 0.978]
    edg_s = [0.000, 0.050, 0.057, 0.001, 0.000, 0.001, 0.070, 0.018]

    def clip_err(m, s):
        m, s = np.array(m), np.array(s)
        return np.vstack([s, np.minimum(s, 1 - m)])  # F1 cannot exceed 1

    fig, ax = plt.subplots(figsize=(W_FULL, 2.6))
    fig.subplots_adjust(left=0.085, right=0.99, top=0.86, bottom=0.14)
    x = np.arange(len(classes))
    w = 0.38
    ekw = dict(elinewidth=0.6, capthick=0.6, ecolor=INK)
    ax.bar(x - w / 2, win_m, w, yerr=clip_err(win_m, win_s), capsize=1.8, color=DET[0],
           ec="none", label="Window level (multi-label Detection Head)", error_kw=ekw)
    ax.bar(x + w / 2, edg_m, w, yerr=clip_err(edg_m, edg_s), capsize=1.8, color=BLAST[0],
           ec="none", label="Meta-edge level (per-edge classification head)", error_kw=ekw)
    ax.axvline(6.5, color=GREY, lw=0.6, ls=(0, (2, 2)))
    ax.set_xticks(x, classes)
    ax.set_ylim(0, 1.05)
    ax.set_yticks(np.arange(0, 1.01, 0.2))
    ax.set_ylabel("F1 score")
    ax.tick_params(length=2.5, width=0.6, labelsize=7.5)
    ax.yaxis.grid(True, color="#dddddd", lw=0.5)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2, frameon=False, fontsize=7.5,
              handlelength=1.2, columnspacing=1.5)
    save(fig, 8)


if __name__ == "__main__":
    for f in (fig1, fig2, fig3, fig4, fig5, fig6, fig7, fig8):
        f()
    print("written to", OUT)
