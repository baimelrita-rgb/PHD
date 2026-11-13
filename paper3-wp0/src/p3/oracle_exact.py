"""Exact oracle: envelope + LinDistFlow + rule in Z3 (linear real arithmetic).

One query per radial topology. SAT gives a counterexample of the LINEAR model, which
is then re-checked on the AC model. UNSAT for every topology is a certificate that is
valid for the linear model only.

Robust mode (owner decision 5): with model-error margins delta (validated by an
adversarial search, see scripts/04 and rules/model_error_bounds.json), every AC
condition is mapped to the weakest linear condition it implies, assuming
|linear - AC| <= delta for each quantity:
  AC vm in [0.9, 1.1]   ->  linear vm in [0.9 - d_vm, 1.1 + d_vm]
  AC vm <  c            ->  linear vm <  c + d_vm         (and > c  -> > c - d_vm)
  AC loading <= 100     ->  linear loading <= 100 + d_ld  (lines, transformers)
  AC loading >  c       ->  linear loading >  c - d_ld
  linear atom sum w_k m_k > c  ->  linear sum > c - sum |w_k| d_k  (d = 0 for metered load/DER)
Then UNSAT means: no benign AC counterexample exists, PROVIDED the AC-to-linear
error stays within delta on the envelope. delta is an empirical bound, so the claim
is "certified relative to LinDistFlow with a validated error bound".

Encoding choices (all keep UNSAT sound for the linear model):
  * vm thresholds: vm < c  <=>  v < c^2 (v = vm^2, c > 0), exact.
  * line apparent power S = sqrt(P^2 + Q^2) is not linear. With K-gon projections
    p_k = P cos(t_k) + Q sin(t_k), t_k = 2 pi k / K:
      S <= c  is relaxed to  p_k <= c for all k            (superset of the true set)
      S >  c  is relaxed to  some p_k > c cos(pi / K)      (superset of the true set)
    Loading percent in the linear model is S / S_max with S_max at 1.0 pu voltage.
  * benign limits: v in [0.81, 1.21] at every bus, loading <= 100 % (relaxed as above).
  * measurements available as linear expressions: vm_pu (threshold atoms only),
    loading (threshold atoms only), p_from, trafo_p_hv, load_p, sgen_p, sw, line_in.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import z3

from . import envelope as E
from . import lindistflow as L
from . import rules as R

K = 16


class NotExpressible(Exception):
    pass


def _lin(z, coeffs, const=0.0):
    return z3.Sum([z3.RealVal(float(c)) * zi for c, zi in zip(coeffs, z) if c != 0.0] + [z3.RealVal(float(const))])


@dataclass
class ExactResult:
    status: str            # "sat" | "unsat" | "not_expressible"
    cfg: E.Config | None
    x: np.ndarray | None
    solve_s: float
    per_cfg: list
    note: str = ""


ZERO_DELTA = {"vm_pu": 0.0, "loading": 0.0, "trafo_loading": 0.0, "p_from": 0.0, "trafo_p_hv": 0.0}


class Encoder:
    def __init__(self, cfg: E.Config, env: E.Envelope = E.ENVELOPE_FULL, delta=None):
        self.cfg = cfg
        self.d = dict(ZERO_DELTA, **(delta or {}))
        self.m = L.model(cfg)
        d = E.dims()
        self.z = [z3.Real(f"s{i}") for i in range(d.n_load)] + [z3.Real(f"g{j}") for j in range(d.n_der)]
        self.bounds = E.cont_bounds(env)
        net = E.apply_config(E.base_net(), cfg)
        self.sw = net.switch.closed.values.astype(float)
        self.lin = net.line.in_service.values.astype(float)
        base = E._base_net()
        self.p_load_nom = base.load.p_mw.values
        self.rated = base.sgen.sn_mva.values
        self.theta = 2 * np.pi * np.arange(K) / K

    def envelope(self):
        cons = []
        for zi, (lo, hi) in zip(self.z, self.bounds):
            cons += [zi >= lo, zi <= hi]
        return cons

    def v_expr(self, b):
        return _lin(self.z, self.m.Av[b], self.m.v0)

    def proj(self, l, k):
        a = np.cos(self.theta[k]) * self.m.AP_line[l] + np.sin(self.theta[k]) * self.m.AQ_line[l]
        return _lin(self.z, a)

    def proj_trafo(self, t, k):
        a = np.cos(self.theta[k]) * self.m.AP_trafo[t] + np.sin(self.theta[k]) * self.m.AQ_trafo[t]
        return _lin(self.z, a)

    def benign(self):
        cons = []
        dv = self.d["vm_pu"]
        for b in range(len(self.m.buses)):
            v = self.v_expr(b)
            cons += [v >= max(E.V_MIN - dv, 0.0) ** 2, v <= (E.V_MAX + dv) ** 2]
        for l in np.where(self.m.line_active)[0]:
            smax = self.m.smax_line[l] * (E.LOADING_MAX + self.d["loading"]) / 100
            cons += [self.proj(l, k) <= smax for k in range(K)]
        for t in range(len(self.m.smax_trafo)):
            smax = self.m.smax_trafo[t] * (E.LOADING_MAX + self.d["trafo_loading"]) / 100
            cons += [self.proj_trafo(t, k) <= smax for k in range(K)]
        return cons

    def linear_meas(self, name):
        kind, i = name.split(".")
        i = int(i)
        n = len(self.z)
        if kind == "p_from":
            return self.m.AP_line[i], 0.0
        if kind == "trafo_p_hv":
            return self.m.AP_trafo[i], 0.0
        if kind == "load_p":
            a = np.zeros(n); a[i] = self.p_load_nom[i]; return a, 0.0
        if kind == "sgen_p":
            a = np.zeros(n); a[E.dims().n_load + i] = self.rated[i]; return a, 0.0
        if kind == "sw":
            return np.zeros(n), self.sw[i]
        if kind == "line_in":
            return np.zeros(n), self.lin[i]
        raise NotExpressible(name)

    def atom(self, a):
        if a["type"] == "discrete":
            _, c = self.linear_meas(a["meas"])
            return z3.BoolVal(abs(c - a["value"]) < 1e-9)
        if a["type"] == "threshold":
            kind, i = a["meas"].split(".")
            i = int(i)
            c = float(a["value"])
            if kind == "vm_pu":
                v = self.v_expr(i)
                dv = self.d["vm_pu"]
                if a["op"] == "<":
                    return v < (c + dv) ** 2
                return v > max(c - dv, 0.0) ** 2
            if kind == "loading":
                dl = self.d["loading"]
                c = c - dl if a["op"] == ">" else c + dl
                if not self.m.line_active[i]:
                    return z3.BoolVal(0.0 < c) if a["op"] == "<" else z3.BoolVal(0.0 > c)
                cap = self.m.smax_line[i] * c / 100
                if a["op"] == ">":
                    return z3.Or([self.proj(i, k) > cap * np.cos(np.pi / K) for k in range(K)])
                return z3.And([self.proj(i, k) < cap for k in range(K)])
            coef, const = self.linear_meas(a["meas"])
            dk = self.d.get(kind, 0.0)
            e = _lin(self.z, coef, const)
            return e < c + dk if a["op"] == "<" else e > c - dk
        if a["type"] == "linear":
            coef = np.zeros(len(self.z)); const = 0.0; slack = 0.0
            for k, w in a["coeffs"].items():
                if k.split(".")[0] in ("vm_pu", "loading", "trafo_loading"):
                    raise NotExpressible(k)
                ck, cc = self.linear_meas(k)
                coef += w * ck; const += w * cc
                slack += abs(w) * self.d.get(k.split(".")[0], 0.0)
            e = _lin(self.z, coef, const)
            return e < a["value"] + slack if a["op"] == "<" else e > a["value"] - slack
        raise ValueError(a)

    def rule(self, rule):
        return z3.Or([z3.And([self.atom(a) for a in c]) for c in R.clauses(rule)])


def _model_x(model, z):
    out = []
    for zi in z:
        val = model.eval(zi, model_completion=True)
        out.append(float(val.as_fraction()) if z3.is_rational_value(val) else float(val.as_decimal(17).rstrip("?")))
    return np.array(out)


def solve(rule, cfgs=None, env=E.ENVELOPE_FULL, timeout_ms=60000, delta=None) -> ExactResult:
    cfgs = E.enumerate_configs() if cfgs is None else cfgs
    t0 = time.time()
    per, first = [], None
    for cfg in cfgs:
        enc = Encoder(cfg, env, delta)
        try:
            phi = enc.rule(rule)
        except NotExpressible as e:
            return ExactResult("not_expressible", None, None, time.time() - t0, per, f"measurement {e} has no linear form")
        s = z3.Solver()
        s.set("timeout", timeout_ms)
        s.add(enc.envelope() + enc.benign() + [phi])
        t1 = time.time()
        r = s.check()
        dt = time.time() - t1
        x = _model_x(s.model(), enc.z) if r == z3.sat else None
        per.append((cfg, str(r), dt, x))
        if r == z3.sat and first is None:
            first = (cfg, x)
    status = "sat" if first else ("unsat" if all(p[1] == "unsat" for p in per) else "unknown")
    return ExactResult(status, first[0] if first else None, first[1] if first else None, time.time() - t0, per)


def load_delta(path):
    import json
    d = json.loads(open(path).read())
    return {k: float(v) for k, v in d["delta"].items()}
