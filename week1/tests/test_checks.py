"""Plumbing tests on a synthetic file in the raw UNSW-NB15 format.

The fixture checks parsing, windowing, labelling, splitting and report generation.
Its numbers mean nothing and must never be reported.
"""

import json

import numpy as np
import pandas as pd
import pytest

from week1 import checks
from week1.unsw import (COLUMNS, assign_splits, build_meta_edges, is_attacker_ip,
                        load_flows)

ATTACKERS = ["175.45.176.0", "175.45.176.1", "175.45.176.2", "175.45.176.3"]
VICTIMS = ["149.171.126.%d" % i for i in range(10, 20)]
BENIGN = ["59.166.0.%d" % i for i in range(0, 10)]
CATS = ["DoS", "Generic", "Exploits", "Fuzzers", "Reconnaissance", "Shellcode"]


def _row(rng, t, src, dst, cat):
    r = {c: 0 for c in COLUMNS}
    r.update(srcip=src, dstip=dst, sport=int(rng.integers(1024, 65535)),
             dsport=int(rng.integers(1, 1024)), proto="tcp", state="FIN", service="-",
             dur=float(rng.random()), sbytes=int(rng.integers(100, 5000)),
             dbytes=int(rng.integers(100, 5000)), sttl=254 if cat else 31,
             Stime=int(t), Ltime=int(t) + 1,
             attack_cat=cat if cat else "", Label=1 if cat else 0)
    return r


@pytest.fixture(scope="module")
def raw_csv(tmp_path_factory):
    rng = np.random.default_rng(0)
    rows = []
    for day0 in (1421884800, 1424217600):  # 2015-01-22, 2015-02-18
        for w in range(40):
            t0 = day0 + w * 300
            for _ in range(30):
                rows.append(_row(rng, t0 + rng.integers(0, 300), rng.choice(BENIGN),
                                 rng.choice(VICTIMS + BENIGN), None))
            if w % 3:  # attack windows
                for cat in rng.choice(CATS, size=4, replace=False):
                    for _ in range(int(rng.integers(3, 10))):
                        rows.append(_row(rng, t0 + rng.integers(0, 300), rng.choice(ATTACKERS),
                                         rng.choice(VICTIMS[:5]), cat))
            if w % 7 == 0:  # pivot: a victim attacks another victim
                rows.append(_row(rng, t0 + 5, VICTIMS[0], VICTIMS[7], "Exploits"))
    rows.append(_row(rng, day0, ATTACKERS[0], VICTIMS[0], "Worms"))  # excluded class
    p = tmp_path_factory.mktemp("raw") / "UNSW-NB15_1.csv"
    pd.DataFrame(rows, columns=COLUMNS).to_csv(p, header=False, index=False)
    return p


def test_load_and_edges(raw_csv):
    df = load_flows([raw_csv])
    assert "Worms" not in set(df.attack_cat)
    assert set(df.day) == {"2015-01-22", "2015-02-18"}
    e = build_meta_edges(df)
    assert not e.duplicated(["window", "srcip", "dstip"]).any()
    assert e.n_flows.sum() == len(df)
    # plurality label is consistent with malicious flag
    assert ((e.y != 0) == (e.malicious == 1)).all()


def test_splits_cover_each_session_and_stratum(raw_csv):
    e = assign_splits(build_meta_edges(load_flows([raw_csv])))
    assert set(e.split) == {"train", "val", "test"}
    for (_, att), g in e.groupby(["day", "malicious"]):
        assert g.split.nunique() >= 2
    # each window belongs to exactly one split
    assert (e.groupby("window").split.nunique() == 1).all()


def test_split_file_roundtrip(raw_csv, tmp_path):
    e = assign_splits(build_meta_edges(load_flows([raw_csv])))
    spec = {s: sorted(int(w) for w in e[e.split == s].window.unique()) for s in ("train", "val", "test")}
    f = tmp_path / "split.json"
    f.write_text(json.dumps(spec))
    e2 = assign_splits(build_meta_edges(load_flows([raw_csv])), split_file=f)
    assert (e2.set_index(["window", "srcip", "dstip"]).split
            == e.set_index(["window", "srcip", "dstip"]).split).all()


def test_attacker_ip_rule():
    s = pd.Series(["175.45.176.0", "175.45.176.3", "175.45.176.4", "175.45.17.1", "10.0.0.1"])
    assert is_attacker_ip(s).tolist() == [True, True, False, False, False]


def test_scope_uses_only_consecutive_windows_in_split(raw_csv):
    e = assign_splits(build_meta_edges(load_flows([raw_csv])))
    r = checks.scope_baselines(e, "test")
    test_w = set(e[e.split == "test"].window)
    expected_pairs = sum(1 for w in test_w if w + 1 in test_w)
    assert r["n_pairs"] == expected_pairs
    assert r["n_new_exposure"] <= r["n_positive"]


def test_graph_shape_finds_pivot(raw_csv):
    e = assign_splits(build_meta_edges(load_flows([raw_csv])))
    shape = checks.graph_shape(e)
    assert any(VICTIMS[0] in g.get("pivot_nodes", []) for g in shape.values())


def test_end_to_end_report(raw_csv, tmp_path):
    checks.main(["--data", str(raw_csv), "--out", str(tmp_path), "--features", "struct"])
    rep = json.loads((tmp_path / "week1_report.json").read_text())
    assert {"detection", "scope_test", "graph_shape", "label_supply"} <= set(rep)
    assert len(rep["detection"]["rf"]["macro_f1"]) == 3
    assert (tmp_path / "week1_report.md").read_text().startswith("# Week 1 report")
