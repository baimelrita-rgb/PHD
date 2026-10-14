"""Audit of LMDEval's optc_redteam.csv (columns: id, description, label) without the raw flows.

The `id` is the eCAR event id of a FLOW START event; the description encodes the day, the
source host, the destination (host, IP or 'multiple targets') and the method. This script
rebuilds the documented attack graph from the descriptions only. Everything that needs
timestamps or the destination of 'multiple targets' rows has to come from the raw flows
and is listed in the report as pending.

Usage: python -I optc/label_audit.py path/to/optc_redteam.csv --out analysis/optc
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

EDGE = re.compile(r"^Day (?P<day>\d+) - (?P<src>\S+) -> (?P<dst>.+?) \((?P<method>[^)]+)\)$")
SWEEP = re.compile(r"^Day (?P<day>\d+) - Ping sweep from (?P<src>\S+)$")
MULTI = ("multiple targets", "multiple hosts")


def parse(desc: str) -> dict:
    m = SWEEP.match(desc)
    if m:
        return {"kind": "ping_sweep", "day": int(m["day"]), "src": m["src"], "dst": "(sweep)", "method": "icmp/scan"}
    m = EDGE.match(desc)
    if m:
        dst = m["dst"]
        method = m["method"]
        kind = "fanout" if dst in MULTI else "hop"
        if "failed" in method:
            kind = "failed_hop"
            method = method.replace("failed ", "")
        return {"kind": kind, "day": int(m["day"]), "src": m["src"], "dst": dst, "method": method}
    if desc.startswith("Flows from malicious processes"):
        return {"kind": "malicious_process", "day": None, "src": None, "dst": None, "method": None}
    return {"kind": "unparsed", "day": None, "src": None, "dst": None, "method": None}


def norm(h):
    return None if not isinstance(h, str) else re.sub(r"(?i)^sysclient", "SysClient", h)


def audit(df: pd.DataFrame) -> dict:
    p = pd.DataFrame([parse(d) for d in df.description])
    d = pd.concat([df.reset_index(drop=True), p], axis=1)
    d["src"] = d["src"].map(norm)
    d["dst"] = d["dst"].map(norm)
    lm = d[d.label == "Lateral movement"]
    out = {
        "rows": int(len(d)), "unique_ids": int(d.id.nunique()),
        "label_counts": d.label.value_counts().to_dict(),
        "unparsed_descriptions": sorted(d[d.kind == "unparsed"].description.unique().tolist()),
        "kind_by_label": d.groupby(["kind", "label"]).size().unstack(fill_value=0).to_dict(orient="index"),
        "days_with_labeled_rows": sorted(int(x) for x in d.day.dropna().unique()),
        "lm_flows_by_day": {int(k): int(v) for k, v in lm.groupby("day").size().items()},
    }
    # documented hop edges (successful and failed), per day
    hops = d[d.kind.isin(["hop", "failed_hop"])]
    edges = (hops.groupby(["day", "src", "dst", "method", "kind", "label"]).size()
             .rename("flows").reset_index().sort_values(["day", "src", "dst"]))
    out["hop_edges"] = edges.to_dict(orient="records")
    # fan-out share of lateral-movement flows
    fan = lm[lm.kind == "fanout"]
    out["lm_total"] = int(len(lm))
    out["lm_fanout_flows"] = int(len(fan))
    out["lm_fanout_share"] = float(len(fan) / len(lm)) if len(lm) else None
    out["lm_fanout_by_day"] = {int(k): int(v) for k, v in fan.groupby("day").size().items()}
    # chain depth per day on successful hop edges (longest directed path, cycles cut)
    out["chain_depth_by_day"] = {}
    for day, g in hops[hops.kind == "hop"].groupby("day"):
        adj: dict[str, set] = {}
        for s, t in zip(g.src, g.dst):
            adj.setdefault(s, set()).add(t)

        def longest(u, seen):
            best = 0
            for v in adj.get(u, ()):
                if v not in seen:
                    best = max(best, 1 + longest(v, seen | {v}))
            return best
        out["chain_depth_by_day"][int(day)] = max(longest(s, {s}) for s in adj)
    # hosts that act as the source of a labeled hop or fan-out
    out["hop_sources"] = sorted({s for s in hops.src.dropna()} | {s for s in fan.src.dropna()})
    return out


def to_markdown(r: dict) -> str:
    L = ["# OpTC label audit (optc_redteam.csv only; no raw flows)", "",
         f"Rows: {r['rows']} (unique ids: {r['unique_ids']}). Labels: {r['label_counts']}.",
         f"Days that have any labeled row: {r['days_with_labeled_rows']} (Day 3 has none in this file).", ""]
    if r["unparsed_descriptions"]:
        L += [f"**Unparsed descriptions: {r['unparsed_descriptions']}**", ""]
    L += ["## Flows by kind and label", "", "| kind | Lateral movement | Other |", "|---|---:|---:|"]
    for k, v in r["kind_by_label"].items():
        L.append(f"| {k} | {v.get('Lateral movement', 0)} | {v.get('Other', 0)} |")
    L += ["", f"Lateral-movement flows: {r['lm_total']}; of them fan-out (one host to many targets): "
          f"{r['lm_fanout_flows']} ({r['lm_fanout_share']:.0%}). By day: {r['lm_fanout_by_day']}.", "",
          "## Documented hop edges", "", "| day | src | dst | method | kind | label | flows |", "|---|---|---|---|---|---|---:|"]
    for e in r["hop_edges"]:
        L.append(f"| {int(e['day'])} | {e['src']} | {e['dst']} | {e['method']} | {e['kind']} | {e['label']} | {e['flows']} |")
    L += ["", f"Longest successful hop chain per day: {r['chain_depth_by_day']}.", "",
          "## Pending (needs the raw FLOW START events joined on `id`)", "",
          "- timestamps of every labeled flow, hence first-compromise time per host;",
          "- the destinations hidden behind 'multiple targets / hosts' (the fan-out rows);",
          "- the number of distinct compromised hosts per day;",
          "- the benign graph (nodes, windows, base rate) for the train/test design."]
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", type=Path)
    ap.add_argument("--out", type=Path, default=Path("analysis/optc"))
    a = ap.parse_args(argv)
    df = pd.read_csv(a.csv)
    assert {"id", "description", "label"} <= set(df.columns), df.columns
    r = audit(df)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "label_audit.json").write_text(json.dumps(r, indent=2, default=str))
    (a.out / "label_audit.md").write_text(to_markdown(r))
    print(to_markdown(r))


if __name__ == "__main__":
    main()
