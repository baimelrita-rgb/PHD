"""Rule synthesis from an alert, and certification by the physics oracle (WP1-c).

An alert is a short time window of telemetry (default: the first 60 s of an attack). The
synthesizer sees only the alert records, train history and the oracle.

Family P, physical invariants. For the topology T seen during the alert, the linearised AC
model at T predicts every bus voltage and line flow from the metered injections. The
invariant residual of a quantity q is
    r_q = q - (A_T x(m) + c_T),     x(m) = metered injections / their nominal scale,
which is linear in the measurement vector. Rule: [topology atoms of T] AND |r_q| > margin.
The margin is 1.5 x the larger of (a) the largest benign AC residual the oracle finds for T
(search) and (b) the largest residual on train telemetry (noise, asynchrony). The quantity
whose alert residuals exceed the margin by most is chosen (one voltage and one flow invariant).

Family S, state rules. Discrete changes between the 30 s before the alert and the alert:
lines going out of service, loads or DER falling to (near) zero. Rule: conjunction of the
new state atoms. The oracle decides whether that state is reachable in the benign envelope.

Certification: search layer (joint DE) and robust exact layer (linearised AC, rule-specific
bounds). A search counterexample raises the margin (CEGIS, at most 5 rounds)."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import numpy as np

from . import envelope as E
from . import linac as LA
from . import measure as M
from . import oracle_exact as X
from . import oracle_search as O
from . import rules as R

MARGIN_FACTOR = 1.5
BOUND_SAFETY = 1.25


def config_index():
    """(active line set, taps) -> Config, for every configuration of the envelope."""
    out = {}
    for c in E.enumerate_configs():
        key = (frozenset(E.active_lines(E.apply_config(E.base_net(), c))), tuple(int(t) for t in c.taps))
        out[key] = c
    return out


def record_config(m, cidx):
    idx = M.index()
    net = E._base_net()
    act = frozenset(l for l in net.line.index if m[idx[f"line_in.{l}"]] > 0.5)
    taps = tuple(int(round(m[idx[f"tap.{t}"]])) for t in net.trafo.index) if f"tap.0" in idx else ()
    return cidx.get((act, taps))


def injection_scales():
    """Per continuous parameter k: (measurement name, scale) with measurement = scale * x_k."""
    inj = E.injection_maps()
    d = E.dims()
    out = []
    for i in range(d.n_load):
        out.append((f"load_p.{i}", inj.Apl[i, i]))
    for j in range(d.n_der):
        out.append((f"sgen_p.{j}", inj.Apg[j, d.n_load + j]))
    for k in range(d.n_sto):
        out.append((f"storage_p.{k}", inj.Apb[k, d.n_load + d.n_der + k]))
    return out


def invariant(cfg, kind, i):
    """Residual r = coeffs . m - c for quantity (kind, i) in configuration cfg."""
    lm = LA.model(cfg)
    if kind == "vm":
        a, c, target = lm.Av[i], lm.vc[i], f"vm_pu.{i}"
    else:
        a, c, target = lm.AP_line[i], lm.cP_line[i], f"p_from.{i}"
    coeffs = {target: 1.0}
    for k, (name, scale) in enumerate(injection_scales()):
        if a[k] != 0.0 and scale != 0.0:
            coeffs[name] = coeffs.get(name, 0.0) - a[k] / scale
    return coeffs, float(c)


def residual(coeffs, c, Mx):
    idx = M.index()
    return sum(w * Mx[..., idx[k]] for k, w in coeffs.items()) - c


def topology_atoms(cfg):
    net = E.apply_config(E.base_net(), cfg)
    act = set(E.active_lines(net))
    atoms = [{"type": "discrete", "meas": f"line_in.{l}", "value": 1.0 if l in act else 0.0} for l in net.line.index]
    atoms += [{"type": "discrete", "meas": f"tap.{t}", "value": float(p)} for t, p in enumerate(cfg.taps)]
    return atoms


def invariant_rule(cfg, coeffs, c, margin, name, scale):
    topo = topology_atoms(cfg)
    neg = {k: -w for k, w in coeffs.items()}
    return {"name": name, "family": "P", "topology": cfg.label, "margin": margin, "const": c,
            "any_of": [topo + [{"type": "linear", "coeffs": coeffs, "op": ">", "value": margin + c, "scale": scale}],
                       topo + [{"type": "linear", "coeffs": neg, "op": ">", "value": margin - c, "scale": scale}]]}


def ac_bound(cfg, coeffs, c, budget, seed):
    """Largest benign |AC residual| of the invariant in configuration cfg (DE search)."""
    idx = M.index()
    st = O.de_maximize(lambda x, m: abs(sum(w * m[idx[k]] for k, w in coeffs.items()) - c), cfg, E.full(), budget, seed)
    return max(0.0, float(st["best"]))


@dataclass
class Candidate:
    family: str
    rule: dict
    info: dict = field(default_factory=dict)


def synthesize_invariants(alert_M, cfg, noise, budget, seed, top=3):
    """noise[(kind, i)]: largest |residual| on train telemetry. Returns up to one candidate per kind."""
    out = []
    net = E._base_net()
    for kind, items, scale in (("vm", [b for b in net.bus.index if b != int(net.ext_grid.bus.iloc[0])], 0.01),
                               ("p", list(net.line.index), 0.1)):
        scored = []
        for i in items:
            if kind == "p" and not LA.model(cfg).line_active[i]:
                continue
            coeffs, c = invariant(cfg, kind, i)
            r = np.abs(residual(coeffs, c, alert_M))
            scored.append((float(np.median(r)) / max(noise.get((kind, i), 1e-6), 1e-6), i, coeffs, c, r))
        scored.sort(key=lambda s: -s[0])
        best = None
        for k, (_, i, coeffs, c, r) in enumerate(scored[:top]):
            b = ac_bound(cfg, coeffs, c, budget, seed + 31 * k + (0 if kind == "vm" else 7))
            margin = MARGIN_FACTOR * max(noise.get((kind, i), 0.0), b)
            score = float(np.median(r)) / margin if margin > 0 else 0.0
            if best is None or score > best[0]:
                best = (score, i, coeffs, c, margin, b)
        if best and best[0] > 1.0:
            score, i, coeffs, c, margin, b = best
            name = f"P-{kind}{i}@{cfg.label}"
            out.append(Candidate("P", invariant_rule(cfg, coeffs, c, margin, name, scale),
                                 {"quantity": f"{'vm_pu' if kind == 'vm' else 'p_from'}.{i}", "ac_bound": b,
                                  "noise": noise.get((kind, i), 0.0), "margin": margin, "alert_score": score,
                                  "coeffs": coeffs, "const": c}))
    return out


def synthesize_state(before_M, alert_M):
    """Discrete changes from before the alert to the alert (median over each window)."""
    idx = M.index()
    net = E._base_net()
    inj = injection_scales()
    b, a = np.median(before_M, axis=0), np.median(alert_M, axis=0)
    atoms, changes = [], []
    for l in net.line.index:
        k = idx[f"line_in.{l}"]
        if b[k] > 0.5 and a[k] < 0.5:
            atoms.append({"type": "discrete", "meas": f"line_in.{l}", "value": 0.0}); changes.append(f"line {l} out")
    for name, scale in inj:
        if scale <= 0:
            continue
        k = idx[name]
        if b[k] > 0.05 * scale and a[k] < 0.01 * scale:
            atoms.append({"type": "threshold", "meas": name, "op": "<", "value": 0.01 * scale, "scale": max(0.01 * scale, 1e-3)})
            changes.append(f"{name} to zero")
    if not atoms:
        return None
    return Candidate("S", {"name": "S-" + "+".join(changes), "family": "S", "atoms": atoms}, {"changes": changes})


def certify(cand: Candidate, cfgs, delta, budget, seed, max_rounds=5):
    """Search (joint DE) and robust exact layer (linearised AC). Family P: raise the margin on a
    search counterexample (CEGIS). Returns verdict dict."""
    rule = copy.deepcopy(cand.rule)
    trace = []
    for rnd in range(1, max_rounds + 1):
        d = copy.deepcopy(delta)
        if cand.family == "P":
            # rule-specific bound: the linear model value of the expression is the constant c,
            # so |linear - AC| is the AC residual itself, bounded by the oracle search
            d.setdefault("linear_atoms", {})[X.atom_key(cand.info["coeffs"])] = BOUND_SAFETY * cand.info["ac_bound"]
        S_ = O.stage_b(rule, cfgs, budget=budget, seed=seed + rnd)
        ex = X.solve(rule, cfgs, delta=d, model="linac")
        n_sat = sum(p[1] == "sat" for p in ex.per_cfg)
        trace.append({"round": rnd, "search_cex": S_.found, "search_best": S_.best_margin, "exact": ex.status, "exact_sat": n_sat})
        if not S_.found and ex.status == "unsat":
            return {"verdict": "certified", "rule": rule, "trace": trace}
        if cand.family != "P" or not S_.found:
            break
        # CEGIS: margin just above the counterexample residual
        r_cex = abs(residual(cand.info["coeffs"], cand.info["const"], S_.cex.m))
        new_m = 1.1 * r_cex
        cand.info["ac_bound"] = max(cand.info["ac_bound"], r_cex)
        cand.info["margin"] = new_m
        rule = invariant_rule(_cfg_by_label(cand.rule["topology"]), cand.info["coeffs"], cand.info["const"], new_m,
                              cand.rule["name"], rule["any_of"][0][-1]["scale"])
    last = trace[-1]
    if last["search_cex"]:
        verdict = "refuted (search)"
    elif last["exact"] == "sat":
        # state atoms (topology, metered injections) carry no model error, so a SAT model is a benign state
        verdict = "refuted (exact)" if cand.family == "S" else "inconclusive"
    else:
        verdict = "inconclusive"
    return {"verdict": verdict, "rule": rule, "trace": trace}


def _cfg_by_label(label):
    for c in E.enumerate_configs():
        if c.label == label:
            return c
    raise KeyError(label)


def synthesize_grid_invariants(cfg, noise, budget, seed):
    """Family G: one rule for topology cfg with a clause pair per bus voltage and per line flow,
    each with its own margin 1.5 x max(oracle AC residual bound, train noise). Fires when ANY
    quantity is inconsistent with the metered injections, so it generalises across elements."""
    net = E._base_net()
    slack = int(net.ext_grid.bus.iloc[0])
    clauses, parts = [], []
    k = 0
    for kind, items, scale in (("vm", [b for b in net.bus.index if b != slack], 0.01), ("p", list(net.line.index), 0.1)):
        for i in items:
            if kind == "p" and not LA.model(cfg).line_active[i]:
                continue
            coeffs, c = invariant(cfg, kind, i)
            b = ac_bound(cfg, coeffs, c, budget, seed + 13 * k)
            k += 1
            margin = MARGIN_FACTOR * max(noise.get((kind, i), 0.0), b)
            r = invariant_rule(cfg, coeffs, c, margin, "", scale)
            clauses += r["any_of"]
            parts.append({"quantity": f"{'vm_pu' if kind == 'vm' else 'p_from'}.{i}", "coeffs": coeffs, "const": c,
                          "ac_bound": b, "margin": margin, "scale": scale})
    rule = {"name": f"G@{cfg.label}", "family": "G", "topology": cfg.label, "any_of": clauses}
    return Candidate("G", rule, {"parts": parts})


def _grid_rule(cfg, parts, name):
    clauses = []
    for p in parts:
        clauses += invariant_rule(cfg, p["coeffs"], p["const"], p["margin"], "", p["scale"])["any_of"]
    return {"name": name, "family": "G", "topology": cfg.label, "any_of": clauses}


def certify_grid(cand: Candidate, cfgs, delta, budget, seed, max_rounds=5):
    """Certify a family G rule. Every part gets its rule-specific bound; a search counterexample
    raises the margin of the part it violates (CEGIS)."""
    cfg = _cfg_by_label(cand.rule["topology"])
    parts = copy.deepcopy(cand.info["parts"])
    trace = []
    for rnd in range(1, max_rounds + 1):
        rule = _grid_rule(cfg, parts, cand.rule["name"])
        d = copy.deepcopy(delta)
        d.setdefault("linear_atoms", {})
        for p in parts:
            d["linear_atoms"][X.atom_key(p["coeffs"])] = BOUND_SAFETY * p["ac_bound"]
        S_ = O.stage_b(rule, cfgs, budget=budget, seed=seed + rnd)
        ex = X.solve(rule, cfgs, delta=d, model="linac")
        trace.append({"round": rnd, "search_cex": S_.found, "exact": ex.status})
        if not S_.found and ex.status == "unsat":
            return {"verdict": "certified", "rule": rule, "trace": trace, "parts": parts}
        if not S_.found:
            break
        for p in parts:   # raise every part the counterexample violates
            r = abs(residual(p["coeffs"], p["const"], S_.cex.m))
            if r > p["margin"]:
                p["ac_bound"] = max(p["ac_bound"], r)
                p["margin"] = 1.1 * r
    return {"verdict": "refuted (search)" if trace[-1]["search_cex"] else "inconclusive", "rule": rule, "trace": trace, "parts": parts}
