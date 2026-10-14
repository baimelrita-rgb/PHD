"""Week 1 checks of PAPER_PLAN_TRIAD.md that do not need the trained TRIAD/ST-GNN model.

  1. Detection baselines: IP-only rule, LR, RF (5 seeds) on edge features.
  3. Scope baselines on next-window exposure: persistence, BFS-k, degree, random.
  4. Shape of malicious traffic per split (star vs multi-hop).

Checks 2 (old explanation mask, GNNExplainer) need the trained model and are run from
the model repository.

Usage:
  python -m week1.checks --data /path/UNSW-NB15_1.csv ... --out analysis/week1
  [--split-file split.json] [--features struct|struct+flow|struct+flow+ttl]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler, label_binarize

from week1.unsw import (CLASSES, FLOW_STATS, STRUCT_FEATURES, TTL_STATS, assign_splits,
                        build_meta_edges, is_attacker_ip, load_flows)

SEEDS = [42, 43, 44, 45, 46]


def ci95(xs):
    xs = np.asarray(xs, float)
    if len(xs) < 2:
        return float(xs.mean()), 0.0, 0.0
    h = 2.776 * xs.std(ddof=1) / np.sqrt(len(xs))  # t_{0.975, df=4}
    return float(xs.mean()), float(xs.std(ddof=1)), float(h)


def macro_ap(y, proba, n_classes):
    present = np.unique(y)
    yb = label_binarize(y, classes=range(n_classes))
    aps = [average_precision_score(yb[:, c], proba[:, c]) for c in present if yb[:, c].any()]
    return float(np.mean(aps))


# ---------------------------------------------------------------- 1. detection
def detection_baselines(e: pd.DataFrame, feats: list[str]) -> dict:
    tr, te = e[e.split == "train"], e[e.split == "test"]
    labels = sorted(set(tr.y) | set(te.y))
    res = {"features": feats, "n_train_edges": int(len(tr)), "n_test_edges": int(len(te))}

    # IP-only rule (binary): attack iff source in 175.45.176.0/30
    pred = is_attacker_ip(te.srcip).astype(int).to_numpy()
    yb = te.malicious.to_numpy()
    res["ip_only_edge"] = {"binary_f1": float(f1_score(yb, pred)),
                           "ap": float(average_precision_score(yb, pred))}
    wtrue = te.groupby("window").malicious.max()
    wpred = pd.Series(pred, index=te.index).groupby(te.window).max()
    res["ip_only_window"] = {"binary_f1": float(f1_score(wtrue, wpred.loc[wtrue.index]))}

    models = {
        "logreg": lambda s: make_pipeline(StandardScaler(), LogisticRegression(
            max_iter=2000, class_weight="balanced", random_state=s)),
        "rf": lambda s: RandomForestClassifier(n_estimators=300, class_weight="balanced",
                                               n_jobs=-1, random_state=s),
    }
    for name, mk in models.items():
        runs = defaultdict(list)
        for s in SEEDS:
            m = mk(s).fit(tr[feats], tr.y)
            proba = np.zeros((len(te), len(CLASSES)))
            proba[:, m.classes_] = m.predict_proba(te[feats])
            yhat = proba.argmax(1)
            runs["macro_f1"].append(f1_score(te.y, yhat, labels=labels, average="macro", zero_division=0))
            runs["macro_ap"].append(macro_ap(te.y.to_numpy(), proba, len(CLASSES)))
            runs["binary_f1"].append(f1_score(yb, (yhat != 0).astype(int)))
            for c, f in zip(labels, f1_score(te.y, yhat, labels=labels, average=None, zero_division=0)):
                runs[f"f1_{CLASSES[c]}"].append(f)
        res[name] = {k: dict(zip(("mean", "std", "ci95"), ci95(v))) for k, v in runs.items()}
    return res


# ---------------------------------------------------------------- 3. scope
def _involved(edges: pd.DataFrame) -> set:
    mal = edges[edges.malicious == 1]
    return set(mal.srcip) | set(mal.dstip)


def _bfs_dist(edges: pd.DataFrame, seeds: set, k: int) -> dict:
    adj = defaultdict(set)
    for s, d in zip(edges.srcip, edges.dstip):
        adj[s].add(d)
        adj[d].add(s)  # undirected reach
    dist = {n: 0 for n in seeds}
    frontier = set(seeds)
    for h in range(1, k + 1):
        nxt = set()
        for u in frontier:
            for v in adj[u]:
                if v not in dist:
                    dist[v] = h
                    nxt.add(v)
        frontier = nxt
    return dist


def scope_baselines(e: pd.DataFrame, split: str = "test", seed: int = 0) -> dict:
    """Score nodes of G_t for 'involved in an attack at t+1' (consecutive windows only)."""
    s = e[e.split == split]
    by_w = {w: g for w, g in s.groupby("window")}
    ws = sorted(by_w)
    rng = np.random.default_rng(seed)
    rows = []
    n_unscorable = 0
    for w in ws:
        if w + 1 not in by_w:
            continue  # t+1 must exist and be in the same split
        gt, gn = by_w[w], by_w[w + 1]
        nodes = sorted(set(gt.srcip) | set(gt.dstip))
        inv_t, inv_n = _involved(gt), _involved(gn)
        n_unscorable += len(inv_n - set(nodes))
        deg = pd.concat([gt.srcip, gt.dstip]).value_counts()
        d1, d2 = _bfs_dist(gt, inv_t, 1), _bfs_dist(gt, inv_t, 2)
        for n in nodes:
            rows.append({
                "window": w, "node": n, "y": int(n in inv_n), "new": int(n in inv_n and n not in inv_t),
                "persistence": float(n in inv_t),
                "bfs1": 1.0 / (1 + d1[n]) if n in d1 else 0.0,
                "bfs2": 1.0 / (1 + d2[n]) if n in d2 else 0.0,
                "degree": float(deg.get(n, 0)),
                "random": float(rng.random()),
            })
    df = pd.DataFrame(rows)
    res = {"split": split, "n_pairs": int(df.window.nunique()) if len(df) else 0,
           "n_node_instances": int(len(df)), "n_positive": int(df.y.sum()) if len(df) else 0,
           "n_new_exposure": int(df.new.sum()) if len(df) else 0,
           "n_positive_unscorable_not_in_Gt": int(n_unscorable)}
    if len(df) == 0 or df.y.nunique() < 2:
        res["note"] = "not enough positives/negatives to score"
        return res
    for b in ["persistence", "bfs1", "bfs2", "degree", "random"]:
        r = {"ap": float(average_precision_score(df.y, df[b])),
             "auc": float(roc_auc_score(df.y, df[b]))}
        # new-exposure subset: positives that were not involved at t, against all negatives
        sub = df[(df.new == 1) | (df.y == 0)]
        if sub.y.nunique() == 2:
            r["ap_new"] = float(average_precision_score(sub.y, sub[b]))
        # coverage of t+1 positives when flagging the top-b nodes per window
        cov = {}
        for budget in (1, 2, 5, 10):
            hit = tot = 0
            for _, g in df.groupby("window"):
                top = g.sort_values(b, ascending=False).head(budget)
                hit += top.y.sum()
                tot += g.y.sum()
            cov[f"top{budget}"] = float(hit / tot) if tot else None
        r["coverage"] = cov
        res[b] = r
    return res


# ---------------------------------------------------------------- 4. graph shape
def graph_shape(e: pd.DataFrame) -> dict:
    out = {}
    for split, s in e.groupby("split"):
        mal = s[s.malicious == 1]
        if mal.empty:
            out[split] = {"n_malicious_edges": 0}
            continue
        src_counts = mal.srcip.value_counts()
        first_victim = mal.groupby("dstip").window.min()
        as_src = mal.groupby("srcip").window.max()
        pivots = [n for n in first_victim.index if n in as_src.index and as_src[n] >= first_victim[n]]
        out[split] = {
            "n_malicious_edges": int(len(mal)),
            "n_attack_src_ips": int(mal.srcip.nunique()),
            "n_victim_dst_ips": int(mal.dstip.nunique()),
            "share_from_attacker_net": float(is_attacker_ip(mal.srcip).mean()),
            "share_from_top1_src": float(src_counts.iloc[0] / len(mal)),
            "share_from_top4_src": float(src_counts.iloc[:4].sum() / len(mal)),
            "n_pivot_nodes_victim_then_attacker": len(pivots),
            "pivot_nodes": sorted(map(str, pivots))[:20],
            "classes_per_attack_window_mean": float(
                mal.groupby("window").y.nunique().mean()),
        }
    return out


def label_supply(e: pd.DataFrame) -> dict:
    t = e.groupby(["split", "y"]).size().unstack(fill_value=0)
    t.columns = [CLASSES[c] for c in t.columns]
    w = e.groupby("split").window.nunique()
    return {"edges_per_class": t.to_dict(orient="index"), "windows": w.to_dict()}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="+", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=Path("analysis/week1"))
    ap.add_argument("--split-file", type=Path)
    ap.add_argument("--features", default="struct+flow",
                    choices=["struct", "struct+flow", "struct+flow+ttl"])
    a = ap.parse_args(argv)

    feats = {"struct": STRUCT_FEATURES, "struct+flow": STRUCT_FEATURES + FLOW_STATS,
             "struct+flow+ttl": STRUCT_FEATURES + FLOW_STATS + TTL_STATS}[a.features]
    e = assign_splits(build_meta_edges(load_flows(a.data)), split_file=a.split_file)
    a.out.mkdir(parents=True, exist_ok=True)
    report = {
        "inputs": [str(p) for p in a.data], "split_file": str(a.split_file) if a.split_file else None,
        "label_supply": label_supply(e),
        "detection": detection_baselines(e, feats),
        "scope_test": scope_baselines(e, "test"),
        "scope_val": scope_baselines(e, "val"),
        "graph_shape": graph_shape(e),
    }
    (a.out / "week1_report.json").write_text(json.dumps(report, indent=2, default=str))
    (a.out / "week1_report.md").write_text(to_markdown(report))
    print((a.out / "week1_report.md").read_text())


def _fmt(d):
    return f"{d['mean']:.3f} ± {d['std']:.3f} (CI ±{d['ci95']:.3f})"


def to_markdown(r: dict) -> str:
    L = ["# Week 1 report (model-free checks)", ""]
    d = r["detection"]
    L += ["## Detection baselines (test edges)", "",
          f"Features: {', '.join(d['features'])}", "",
          f"- IP-only rule: edge binary F1 = {d['ip_only_edge']['binary_f1']:.3f}, "
          f"window binary F1 = {d['ip_only_window']['binary_f1']:.3f}"]
    for m in ("logreg", "rf"):
        L.append(f"- {m}: macro F1 {_fmt(d[m]['macro_f1'])}; macro AP {_fmt(d[m]['macro_ap'])}; "
                 f"binary F1 {_fmt(d[m]['binary_f1'])}")
    L += ["", "| class | LR F1 | RF F1 |", "|---|---|---|"]
    for c in CLASSES:
        k = f"f1_{c}"
        if k in d["rf"]:
            L.append(f"| {c} | {d['logreg'][k]['mean']:.3f} | {d['rf'][k]['mean']:.3f} |")
    for sp in ("scope_test", "scope_val"):
        s = r[sp]
        L += ["", f"## Next-window exposure baselines ({s['split']})", "",
              f"Window pairs: {s['n_pairs']}, node instances: {s['n_node_instances']}, "
              f"positives: {s['n_positive']}, NEW exposure: {s['n_new_exposure']}, "
              f"positives not in G_t (unscorable): {s['n_positive_unscorable_not_in_Gt']}", ""]
        if "note" in s:
            L.append(s["note"])
            continue
        L += ["| baseline | AP | AUC | AP (new) | cov@1 | cov@5 |", "|---|---|---|---|---|---|"]
        for b in ("persistence", "bfs1", "bfs2", "degree", "random"):
            x = s[b]
            L.append(f"| {b} | {x['ap']:.3f} | {x['auc']:.3f} | {x.get('ap_new', float('nan')):.3f} | "
                     f"{x['coverage']['top1']:.3f} | {x['coverage']['top5']:.3f} |")
    L += ["", "## Malicious-traffic shape", ""]
    for sp, g in r["graph_shape"].items():
        L.append(f"- {sp}: " + ", ".join(f"{k}={v}" for k, v in g.items() if k != "pivot_nodes"))
    L += ["", "## Label supply", "", "```", json.dumps(r["label_supply"], indent=1), "```", ""]
    L += gate(r)
    return "\n".join(L)


def gate(r: dict) -> list[str]:
    """Pre-registered G1 rules from PAPER_PLAN_TRIAD.md, evaluated on model-free numbers."""
    out = ["## Gate G1 (model-free part)", ""]
    s = r["scope_test"]
    if "persistence" in s:
        p = s["persistence"]["ap"]
        out.append(f"- Persistence AP = {p:.3f} -> " + (
            "LANL becomes mandatory for the forward half (>= 0.95)." if p >= 0.95
            else "forward half can be tested on UNSW (< 0.95)."))
    n_new = s.get("n_new_exposure", 0)
    out.append(f"- NEW-exposure positives in test = {n_new} -> " + (
        "report descriptively only (< 30)." if n_new < 30 else "can be scored (>= 30)."))
    rf = r["detection"]["rf"]["macro_f1"]
    out.append(f"- RF macro F1 = {rf['mean']:.3f} ± CI {rf['ci95']:.3f}: compare with the GNN's "
               "clean edge macro F1 from the model repository (G1 condition 1).")
    return out


if __name__ == "__main__":
    main()
