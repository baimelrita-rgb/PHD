"""Rule DSL (JSON) and evaluator.

A rule is a conjunction of atoms. Atom types:
  {"type": "threshold", "meas": "<name>", "op": "<" | ">", "value": c, "scale": s}
  {"type": "linear", "coeffs": {"<name>": a, ...}, "op": "<" | ">", "value": c, "scale": s}
  {"type": "discrete", "meas": "<name>", "value": v}
No temporal atoms.

Extension (documented deviation): a rule may instead hold "any_of": [[atoms], [atoms]],
a disjunction of conjunctions. It is needed only for R3, whose condition
|d| > m is the disjunction (d > m) or (-d > m). With a plain "atoms" list the rule is a
single conjunction.

Margin: positive iff the rule fires. Atom margin is (value - lhs)/scale for "<" and
(lhs - value)/scale for ">"; discrete atoms give +1 or -1. A conjunction takes the
minimum over atoms, a disjunction the maximum over clauses. "scale" (default 1)
only normalises units so that the search sees comparable magnitudes.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import measure as M


def _lhs(atom, m: np.ndarray, idx) -> float:
    if atom["type"] == "threshold":
        return float(m[idx[atom["meas"]]])
    if atom["type"] == "linear":
        return float(sum(a * m[idx[k]] for k, a in atom["coeffs"].items()))
    raise ValueError(atom["type"])


def atom_margin(atom, m: np.ndarray, idx=None) -> float:
    idx = M.index() if idx is None else idx
    if atom["type"] == "discrete":
        return 1.0 if abs(m[idx[atom["meas"]]] - atom["value"]) < 1e-9 else -1.0
    lhs = _lhs(atom, m, idx)
    s = float(atom.get("scale", 1.0))
    if atom["op"] == "<":
        return (atom["value"] - lhs) / s
    if atom["op"] == ">":
        return (lhs - atom["value"]) / s
    raise ValueError(atom["op"])


def clauses(rule) -> list[list[dict]]:
    if "any_of" in rule:
        return rule["any_of"]
    return [rule["atoms"]]


def margin(rule, m: np.ndarray, idx=None) -> float:
    idx = M.index() if idx is None else idx
    return max(min(atom_margin(a, m, idx) for a in c) for c in clauses(rule))


def fires(rule, m: np.ndarray, idx=None) -> bool:
    return margin(rule, m, idx) > 0.0


def validate(rule):
    idx = M.index()
    for c in clauses(rule):
        assert len(c) >= 1
        for a in c:
            assert a["type"] in ("threshold", "linear", "discrete"), a
            keys = [a["meas"]] if "meas" in a else list(a["coeffs"])
            for k in keys:
                assert k in idx, f"unknown measurement {k}"
            if a["type"] != "discrete":
                assert a["op"] in ("<", ">")
    return True


def load(path) -> dict:
    rules = json.loads(Path(path).read_text())
    for r in rules.values():
        validate(r)
    return rules


def save(rules: dict, path):
    for r in rules.values():
        validate(r)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(rules, indent=2))
