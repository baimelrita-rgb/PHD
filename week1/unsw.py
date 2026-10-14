"""Load the raw, IP-inclusive UNSW-NB15 export and build windowed meta-edges.

Input: UNSW-NB15_1.csv ... UNSW-NB15_4.csv (no header, 49 columns, official order).
Output: a meta-edge table with one row per (window, srcip, dstip), its plurality label,
and the window/split it belongs to.

The split here follows the paper's description (per capture session, attack/benign
stratified, 70/15/15 over windows). For numbers that go into the paper, pass the
pipeline's own split with --split-file so both use identical windows.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

COLUMNS = [
    "srcip", "sport", "dstip", "dsport", "proto", "state", "dur", "sbytes", "dbytes",
    "sttl", "dttl", "sloss", "dloss", "service", "Sload", "Dload", "Spkts", "Dpkts",
    "swin", "dwin", "stcpb", "dtcpb", "smeansz", "dmeansz", "trans_depth", "res_bdy_len",
    "Sjit", "Djit", "Stime", "Ltime", "Sintpkt", "Dintpkt", "tcprtt", "synack", "ackdat",
    "is_sm_ips_ports", "ct_state_ttl", "ct_flw_http_mthd", "is_ftp_login", "ct_ftp_cmd",
    "ct_srv_src", "ct_srv_dst", "ct_dst_ltm", "ct_src_ltm", "ct_src_dport_ltm",
    "ct_dst_sport_ltm", "ct_dst_src_ltm", "attack_cat", "Label",
]

CLASSES = ["Benign", "DoS", "Generic", "Exploits", "Fuzzers", "Reconnaissance", "Shellcode"]
EXCLUDED = {"Backdoor", "Analysis", "Worms"}  # below the 50-edge support threshold (paper Sec. 5.1)
ATTACKER_NET = "175.45.176."  # 175.45.176.0/30 hosts .0-.3
WINDOW_SECONDS = 300

# Flow statistics aggregated per meta-edge. sttl/dttl/ct_state_ttl are kept out of the
# default set: in UNSW-NB15 the TTL values alone separate attack from benign traffic.
FLOW_STATS = ["dur", "sbytes", "dbytes", "Spkts", "Dpkts", "Sload", "Dload",
              "smeansz", "dmeansz", "Sjit", "Djit", "Sintpkt", "Dintpkt", "tcprtt"]
TTL_STATS = ["sttl", "dttl", "ct_state_ttl"]


def _clean_cat(s: pd.Series) -> pd.Series:
    s = s.fillna("").astype(str).str.strip()
    s = s.replace({"": "Benign", "Backdoors": "Backdoor"})
    return s


def load_flows(paths: list[Path]) -> pd.DataFrame:
    frames = [pd.read_csv(p, header=None, names=COLUMNS, low_memory=False,
                          encoding="latin-1") for p in paths]
    df = pd.concat(frames, ignore_index=True)
    df["attack_cat"] = _clean_cat(df["attack_cat"])
    df.loc[df["Label"].astype(int) == 0, "attack_cat"] = "Benign"
    df = df[~df["attack_cat"].isin(EXCLUDED)].copy()
    unknown = set(df["attack_cat"]) - set(CLASSES)
    if unknown:
        raise ValueError(f"unexpected attack categories: {sorted(unknown)}")
    for c in FLOW_STATS + TTL_STATS + ["Stime"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df[FLOW_STATS + TTL_STATS] = df[FLOW_STATS + TTL_STATS].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    df = df.dropna(subset=["Stime"])
    df["window"] = (df["Stime"] // WINDOW_SECONDS).astype(np.int64)
    df["day"] = pd.to_datetime(df["Stime"], unit="s").dt.date.astype(str)
    df["y"] = df["attack_cat"].map({c: i for i, c in enumerate(CLASSES)}).astype(int)
    return df


def build_meta_edges(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (window, srcip, dstip) with plurality label and aggregated stats."""
    g = df.groupby(["window", "srcip", "dstip"], sort=True)
    agg = g[FLOW_STATS + TTL_STATS].mean()
    agg["n_flows"] = g.size()
    agg["n_sports"] = g["sport"].nunique()
    agg["n_dports"] = g["dsport"].nunique()
    agg["n_protos"] = g["proto"].nunique()
    counts = df.groupby(["window", "srcip", "dstip", "y"]).size().unstack(fill_value=0)
    counts = counts.reindex(columns=range(len(CLASSES)), fill_value=0)
    agg["y"] = counts.values.argmax(axis=1)  # plurality; ties -> lowest index
    agg["n_attack_flows"] = counts.drop(columns=0).sum(axis=1)
    agg["day"] = g["day"].first()
    e = agg.reset_index()
    e["malicious"] = (e["y"] != 0).astype(int)
    _add_structural(e)
    return e


def _add_structural(e: pd.DataFrame) -> None:
    """Per-window graph features, computed only from the window's own edge list."""
    out_deg = e.groupby(["window", "srcip"])["dstip"].transform("nunique")
    in_deg = e.groupby(["window", "dstip"])["srcip"].transform("nunique")
    src_flows = e.groupby(["window", "srcip"])["n_flows"].transform("sum")
    dst_flows = e.groupby(["window", "dstip"])["n_flows"].transform("sum")
    win_edges = e.groupby("window")["n_flows"].transform("size")
    win_flows = e.groupby("window")["n_flows"].transform("sum")
    e["src_out_deg"] = out_deg
    e["dst_in_deg"] = in_deg
    e["src_flow_share"] = src_flows / win_flows
    e["dst_flow_share"] = dst_flows / win_flows
    e["edge_flow_share"] = e["n_flows"] / win_flows
    e["win_n_edges"] = win_edges
    # reverse edge present in the same window
    keys = set(zip(e["window"], e["srcip"], e["dstip"]))
    e["has_reverse"] = [int((w, d, s) in keys) for w, s, d in zip(e["window"], e["srcip"], e["dstip"])]


STRUCT_FEATURES = ["n_flows", "n_sports", "n_dports", "n_protos", "src_out_deg", "dst_in_deg",
                   "src_flow_share", "dst_flow_share", "edge_flow_share", "win_n_edges", "has_reverse"]


def assign_splits(e: pd.DataFrame, seed: int = 0, frac=(0.70, 0.15, 0.15),
                  split_file: Path | None = None) -> pd.DataFrame:
    """Map each window to train/val/test."""
    if split_file is not None:
        spec = json.loads(Path(split_file).read_text())
        wmap = {int(w): s for s in ("train", "val", "test") for w in spec[s]}
        e["split"] = e["window"].map(wmap)
        missing = e["split"].isna().sum()
        if missing:
            raise ValueError(f"{missing} edges fall in windows absent from {split_file}")
        return e
    rng = np.random.default_rng(seed)
    win = e.groupby("window").agg(day=("day", "first"), attack=("malicious", "max")).reset_index()
    wmap = {}
    for (_, _), grp in win.groupby(["day", "attack"]):
        ws = np.sort(grp["window"].to_numpy())  # chronological within a session/stratum
        n = len(ws)
        n_tr, n_va = int(round(frac[0] * n)), int(round(frac[1] * n))
        for w in ws[:n_tr]:
            wmap[w] = "train"
        for w in ws[n_tr:n_tr + n_va]:
            wmap[w] = "val"
        for w in ws[n_tr + n_va:]:
            wmap[w] = "test"
    del rng
    e["split"] = e["window"].map(wmap)
    return e


def is_attacker_ip(ip: pd.Series) -> pd.Series:
    ip = ip.astype(str)
    last = pd.to_numeric(ip.str.rsplit(".", n=1).str[-1], errors="coerce")
    return ip.str.startswith(ATTACKER_NET) & last.between(0, 3)
