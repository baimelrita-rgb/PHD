"""Tests of the wrapper on synthetic eCAR-style data.

They need LMDEval's extract_optc.py: set LMDEVAL_DIR to the cloned repository (or to a
logic-identical stub). The numbers in the fixtures mean nothing.
"""

import gzip
import json
import os
from pathlib import Path

import pandas as pd
import pytest

from optc import extract_labeled as X

LMDEVAL = os.environ.get("LMDEVAL_DIR")
pytestmark = pytest.mark.skipif(not LMDEVAL, reason="set LMDEVAL_DIR to the LMDEval repository")


def line(evt_id, host, src, dst, direction, ts="2019-09-23T11:24:54.000-04:00", drop_props=False):
    evt = {"action": "START", "object": "FLOW", "id": evt_id, "hostname": host, "timestamp": ts,
           "properties": {"src_ip": src, "dest_ip": dst, "src_port": "50000", "dest_port": "445",
                          "l4protocol": "6", "direction": direction}}
    if drop_props:
        del evt["properties"]["src_ip"]
    return json.dumps(evt, separators=(",", ":"))


def write_gz(path: Path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as f:
        f.write("\n".join(lines) + "\n")


@pytest.fixture()
def tree(tmp_path):
    root = tmp_path / "ecar"
    # benign flow recorded on both ends -> de-duplicated to the outbound event
    write_gz(root / "benign" / "a.json.gz", [
        line("b1", "SysClient0001", "142.20.56.1", "142.20.56.2", "outbound", "2019-09-20T09:00:00.000-04:00"),
        line("b2", "SysClient0002", "142.20.56.1", "142.20.56.2", "inbound", "2019-09-20T09:00:00.000-04:00"),
    ])
    write_gz(root / "evaluation" / "b.json.gz", [
        line("x1", "SysClient0201", "142.20.56.202", "142.20.57.147", "outbound"),   # lateral movement
        line("x2", "SysClient0402", "142.20.57.147", "142.20.56.204", "outbound"),   # other
        line("e1", "SysClient0201", "142.20.56.202", "8.8.8.8", "outbound"),         # external: dropped
        line("bad", "SysClient0201", "142.20.56.202", "142.20.57.147", "outbound", drop_props=True),
    ])
    write_gz(root / "short" / "c.json.gz", [line("s1", "SysClient0009", "142.20.56.9", "142.20.56.8", "outbound")])
    red = tmp_path / "optc_redteam.csv"
    pd.DataFrame({"id": ["x1", "x2"], "description": ["d1", "d2"],
                  "label": ["Lateral movement", "Other"]}).to_csv(red, index=False)
    return root, red


def run(tree, tmp_path, *extra):
    root, red = tree
    out = tmp_path / "out.csv.gz"
    X.BAD.clear()
    X.FILES["n"] = 0
    X.main(["--lmdeval", LMDEVAL, "--input_dir", str(root), "--redteam", str(red), "--output", str(out), *extra])
    return pd.read_csv(out)


def test_labels_ids_absolute_time_and_dedup(tree, tmp_path):
    df = run(tree, tmp_path)
    assert (df.category == "benign").sum() == 2          # b1 (dedup keeps one) + s1
    lm = df[df.category == "lm"].iloc[0]
    assert lm["id"] == "x1" and lm["day"] == "2019-09-23" and lm["time"] == "2019-09-23 11:24:54"
    assert (df.category == "other").sum() == 1
    assert "e1" not in set(df["id"])                       # external destination dropped
    assert sum(X.BAD.values()) == 1                        # the broken line is counted, not fatal


def test_exclude_short_and_limit(tree, tmp_path):
    df = run(tree, tmp_path, "--exclude", "short")
    assert (df.category == "benign").sum() == 1
    df = run(tree, tmp_path, "--limit-files", "1")
    assert X.FILES["n"] == 1
