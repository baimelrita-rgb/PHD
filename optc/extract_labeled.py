"""Run LMDEval's OpTC extraction unchanged, but keep what the audit needs.

LMDEval's `extract_optc.py` writes (timestamp relative to the first processed event, src, dst,
ports, proto, label 0/1). That drops the event id, the lateral-movement / other distinction and
the absolute time. This wrapper imports LMDEval's own functions (same filtering, same IP-to-host
mapping, same de-duplication) and only replaces two things:
  * `process_flow`: labels each event 'lm' / 'other' / 'benign' and keeps its id; lines that
    cannot be parsed are counted and reported instead of aborting the run;
  * `make_flow_list`: keeps the absolute time (seconds since 1970-01-01 in the dataset's local
    time, as in LMDEval's ORIGIN) and adds `time` and `day`.

It runs with a single process: LMDEval's parallel workers would not see the replaced functions.

Usage:
  python optc/extract_labeled.py --lmdeval /path/to/LMDEval --input_dir /path/to/ecar-bro \
      --redteam /path/to/LMDEval/optc_redteam.csv --addresses /path/to/LMDEval/optc_known_addresses.json \
      --output optc_labeled.csv.gz [--limit-files 3] [--exclude short]

Validation target (Larroche, Table 4): about 1354 malicious events, 244 of them lateral movement.
If the run reports 0 labeled events, the input folder does not carry the same event ids.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from pathlib import Path

import pandas as pd

BAD: collections.Counter = collections.Counter()
FILES = {"n": 0}


def make_process_flow(E, cats):
    def process_flow(line, flows, hosts, malicious_ids):
        try:
            evt = json.loads(line)
            p = evt["properties"]
            ts = E.make_timestamp(evt["timestamp"])
            evt_id = evt["id"]
            hostname = evt["hostname"]
            src_ip, dst_ip = p["src_ip"], p["dest_ip"]
            src_port, dst_port = int(p["src_port"]), int(p["dest_port"])
            proto = int(p["l4protocol"])
            outbound = p["direction"] == "outbound"
        except (KeyError, ValueError, TypeError) as exc:
            BAD[f"{type(exc).__name__}: {str(exc)[:40]}"] += 1
            return
        if not E.include_ip(src_ip) or not E.include_ip(dst_ip):
            return
        cat = cats.get(evt_id)
        label = 0 if cat is None else (cat, evt_id)  # keeps LMDEval's 3-tuple layout
        flows[(src_ip, dst_ip, src_port, dst_port, proto)].append((ts, outbound, label))
        if outbound:
            hosts[src_ip] = hostname
        else:
            hosts[dst_ip] = hostname
    return process_flow


def make_flow_list(flows, addr_to_host):
    rows = []
    for (sip, dip, sport, dport, proto), events in flows.items():
        for ts, _, lab in events:
            cat, eid = ("benign", "") if lab == 0 else lab
            rows.append((ts, sip, dip, sport, dport, proto, cat, eid))
    df = pd.DataFrame(rows, columns=["ts", "src", "dst", "src_port", "dst_port", "proto", "category", "id"])
    for col in ("src", "dst"):
        df[col] = df[col].map(lambda a: addr_to_host.get(a, a))
    t = pd.to_datetime(df["ts"], unit="s")
    df["time"] = t.dt.strftime("%Y-%m-%d %H:%M:%S")
    df["day"] = t.dt.strftime("%Y-%m-%d")
    return df.sort_values("ts", kind="stable").reset_index(drop=True)


def summarize(df: pd.DataFrame) -> str:
    L = [f"rows: {len(df)}", f"files processed: {FILES['n']}",
         f"unparseable FLOW START lines: {sum(BAD.values())} {dict(BAD.most_common(5))}",
         "events by category:", df.category.value_counts().to_string()]
    lab = df[df.category != "benign"]
    if len(lab):
        L += ["labeled events by day and category:", lab.groupby(["day", "category"]).size().to_string()]
    L += [f"days present: {sorted(df.day.unique())[:12]}{' ...' if df.day.nunique() > 12 else ''}"]
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lmdeval", type=Path, required=True, help="path to the cloned LMDEval repository")
    ap.add_argument("--input_dir", type=Path, required=True, help="folder with benign/ short/ evaluation/ log files")
    ap.add_argument("--redteam", type=Path, required=True)
    ap.add_argument("--addresses", type=Path, default=None)
    ap.add_argument("--output", type=Path, default=Path("optc_labeled.csv.gz"))
    ap.add_argument("--limit-files", type=int, default=0, help="process only the first N files (dry run)")
    ap.add_argument("--exclude", nargs="*", default=[], help="sub-folder names to skip, e.g. short")
    a = ap.parse_args(argv)

    sys.path.insert(0, str(a.lmdeval))
    import extract_optc as E

    red = pd.read_csv(a.redteam)
    cats = {i: ("lm" if lab == "Lateral movement" else "other") for i, lab in zip(red["id"], red["label"])}
    addr = json.loads(a.addresses.read_text()) if a.addresses else {}

    E.process_flow = make_process_flow(E, cats)
    E.make_flow_list = make_flow_list

    # keep the original once, so that repeated calls in one process do not stack wrappers
    orig_evts = getattr(E, "_labeled_orig_process_evts", E.process_evts)
    E._labeled_orig_process_evts = orig_evts

    def counted(filepath, malicious_ids):
        if a.limit_files and FILES["n"] >= a.limit_files:
            return {}, {}
        FILES["n"] += 1
        return orig_evts(filepath, malicious_ids)
    E.process_evts = counted

    real_walk = getattr(os, "_labeled_orig_walk", os.walk)
    os._labeled_orig_walk = real_walk
    os.walk = real_walk
    if a.exclude:
        def walk(top, *args, **kwargs):
            for dp, dn, fn in real_walk(top, *args, **kwargs):
                dn[:] = [d for d in dn if d not in a.exclude]
                yield dp, dn, fn
        os.walk = walk

    df = E.extract_optc_dataset(str(a.input_dir), set(cats), addr, n_jobs=1)
    df.to_csv(a.output, index=False)
    print(summarize(df))
    print(f"\nwritten: {a.output}")


if __name__ == "__main__":
    main()
