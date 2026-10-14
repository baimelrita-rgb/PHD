import pandas as pd

from optc.label_audit import audit, parse


def _df(rows):
    return pd.DataFrame(rows, columns=["id", "description", "label"])


def test_parse_kinds():
    assert parse("Day 1 - Ping sweep from SysClient0201")["kind"] == "ping_sweep"
    assert parse("Day 1 - DC1 -> multiple targets (invoke_wmi)")["kind"] == "fanout"
    assert parse("Day 2 - DC1 -> SysClient0501 (failed WMI)")["kind"] == "failed_hop"
    assert parse("Day 1 - SysClient0201 -> SysClient0402 (invoke_wmi)")["kind"] == "hop"
    assert parse("Flows from malicious processes")["kind"] == "malicious_process"
    assert parse("something else")["kind"] == "unparsed"


def test_chain_depth_and_fanout_share():
    LM, O = "Lateral movement", "Other"
    d = _df([
        ("1", "Day 1 - SysClient0201 -> SysClient0402 (invoke_wmi)", LM),
        ("2", "Day 1 - SysClient0402 -> SysClient0660 (invoke_wmi)", LM),
        ("3", "Day 1 - SysClient0660 -> DC1 (invoke_wmi)", LM),
        ("4", "Day 1 - DC1 -> multiple targets (invoke_wmi)", LM),
        ("5", "Day 1 - DC1 -> multiple targets (invoke_wmi)", LM),
        ("6", "Day 1 - Ping sweep from SysClient0201", O),
    ])
    r = audit(d)
    assert r["chain_depth_by_day"] == {1: 3}
    assert r["lm_total"] == 5 and r["lm_fanout_flows"] == 2
    assert r["unparsed_descriptions"] == []
