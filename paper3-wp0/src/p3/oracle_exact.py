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
from . import linac as LA
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


MODELS = ("lindistflow", "linac")


def model_for(cfg, model="lindistflow"):
    """Linear model used for one configuration. 'auto': LinDistFlow on radial, linearised AC on meshed."""
    if model == "auto":
        model = "lindistflow" if E.is_radial(cfg) else "linac"
    return model


def linear_model(cfg, model="lindistflow"):
    return L.model(cfg) if model_for(cfg, model) == "lindistflow" else LA.model(cfg)


def _delta_for(delta, kind):
    """delta is a quantity dict (one model) or {model: quantity dict}."""
    if delta and kind in delta and isinstance(delta[kind], dict):
        return delta[kind]
    return delta


def atom_key(coeffs: dict) -> str:
    """Sign-normalised key of a linear expression (|error| is the same for e and -e)."""
    items = sorted((k, float(v)) for k, v in coeffs.items())
    sign = 1.0 if items[0][1] >= 0 else -1.0
    return ";".join(f"{k}:{sign * v:.9g}" for k, v in items)


class Encoder:
    def __init__(self, cfg: E.Config, env: E.Envelope | None = None, delta=None, model="lindistflow"):
        self.cfg = cfg
        self.kind = model_for(cfg, model)
        dd = dict(_delta_for(delta, self.kind) or {})
        self.atom_d = dd.pop("linear_atoms", {}) or {}
        self.d = dict(ZERO_DELTA, **dd)
        self.m = linear_model(cfg, self.kind)
        self._t = (lambda c: c * c) if self.m.squared else (lambda c: c)
        d = E.dims()
        self.z = ([z3.Real(f"s{i}") for i in range(d.n_load)] + [z3.Real(f"g{j}") for j in range(d.n_der)]
                  + [z3.Real(f"b{k}") for k in range(d.n_sto)])
        self.bounds = E.cont_bounds(env)
        net = E.apply_config(E.base_net(), cfg)
        self.sw = net.switch.closed.values.astype(float)
        self.lin = net.line.in_service.values.astype(float)
        self.inj = E.injection_maps()
        self.theta = 2 * np.pi * np.arange(K) / K

    def envelope(self):
        cons = []
        for zi, (lo, hi) in zip(self.z, self.bounds):
            cons += [zi == lo] if lo == hi else [zi >= lo, zi <= hi]
        return cons

    def v_expr(self, b):
        return _lin(self.z, self.m.Av[b], self.m.vc[b])

    def proj(self, l, k):
        a = np.cos(self.theta[k]) * self.m.AP_line[l] + np.sin(self.theta[k]) * self.m.AQ_line[l]
        return _lin(self.z, a, np.cos(self.theta[k]) * self.m.cP_line[l] + np.sin(self.theta[k]) * self.m.cQ_line[l])

    def proj_trafo(self, t, k):
        a = np.cos(self.theta[k]) * self.m.AP_trafo[t] + np.sin(self.theta[k]) * self.m.AQ_trafo[t]
        return _lin(self.z, a, np.cos(self.theta[k]) * self.m.cP_trafo[t] + np.sin(self.theta[k]) * self.m.cQ_trafo[t])

    def _range(self, coef, const):
        """Exact min and max of coef @ z + const over the parameter box (interval arithmetic)."""
        lo = np.array([b[0] for b in self.bounds]); hi = np.array([b[1] for b in self.bounds])
        cp, cn = np.maximum(coef, 0), np.minimum(coef, 0)
        return const + cp @ lo + cn @ hi, const + cp @ hi + cn @ lo

    def benign(self):
        """Operating limits as linear constraints. A constraint that holds on the whole box is
        implied by the envelope and is dropped (exact, it removes no state)."""
        cons = []
        self.n_dropped = 0
        dv = self.d["vm_pu"]
        vlo, vhi = self._t(max(E.V_MIN - dv, 0.0)), self._t(E.V_MAX + dv)
        for b in range(len(self.m.buses)):
            mn, mx = self._range(self.m.Av[b], self.m.vc[b])
            v = None
            if mn < vlo:
                v = self.v_expr(b); cons.append(v >= vlo)
            else:
                self.n_dropped += 1
            if mx > vhi:
                v = v if v is not None else self.v_expr(b); cons.append(v <= vhi)
            else:
                self.n_dropped += 1
        cP_l, cP_t = self.m.cP_line, self.m.cP_trafo
        for l in np.where(self.m.line_active)[0]:
            smax = self.m.smax_line[l] * (E.LOADING_MAX + self.d["loading"]) / 100
            for k in range(K):
                c, s_ = np.cos(self.theta[k]), np.sin(self.theta[k])
                _, mx = self._range(c * self.m.AP_line[l] + s_ * self.m.AQ_line[l], c * cP_l[l] + s_ * self.m.cQ_line[l])
                if mx > smax:
                    cons.append(self.proj(l, k) <= smax)
                else:
                    self.n_dropped += 1
        for t in range(len(self.m.smax_trafo)):
            smax = self.m.smax_trafo[t] * (E.LOADING_MAX + self.d["trafo_loading"]) / 100
            for k in range(K):
                c, s_ = np.cos(self.theta[k]), np.sin(self.theta[k])
                _, mx = self._range(c * self.m.AP_trafo[t] + s_ * self.m.AQ_trafo[t], c * cP_t[t] + s_ * self.m.cQ_trafo[t])
                if mx > smax:
                    cons.append(self.proj_trafo(t, k) <= smax)
                else:
                    self.n_dropped += 1
        return cons

    def linear_meas(self, name):
        kind, i = name.split(".")
        i = int(i)
        n = len(self.z)
        if kind == "p_from":
            return self.m.AP_line[i], self.m.cP_line[i]
        if kind == "trafo_p_hv":
            return self.m.AP_trafo[i], self.m.cP_trafo[i]
        if kind == "load_p":
            return self.inj.Apl[i], 0.0
        if kind == "sgen_p":
            return self.inj.Apg[i], 0.0
        if kind == "storage_p":
            return self.inj.Apb[i], 0.0
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
                    return v < self._t(c + dv)
                return v > self._t(max(c - dv, 0.0))
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
            key = atom_key(a["coeffs"])
            if key in self.atom_d:   # validated bound on the error of this expression itself
                slack = min(slack, self.atom_d[key])
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


def _solve_one(args):
    rule, cfg, env, timeout_ms, delta, model = args
    enc = Encoder(cfg, env, delta, model)
    phi = enc.rule(rule)
    sv = z3.Solver()
    sv.set("timeout", timeout_ms)
    sv.add(enc.envelope() + enc.benign() + [phi])
    t1 = time.time()
    r = sv.check()
    dt = time.time() - t1
    x = _model_x(sv.model(), enc.z) if r == z3.sat else None
    return cfg, str(r), dt, x


def solve(rule, cfgs=None, env=None, timeout_ms=60000, delta=None, workers=None, model="lindistflow") -> ExactResult:
    """One Z3 query per configuration the chosen linear model covers (LinDistFlow: radial only;
    linac and auto: all), in parallel processes (fork) when workers > 1."""
    import os
    from concurrent.futures import ProcessPoolExecutor
    import multiprocessing as mp
    cfgs = E.enumerate_configs() if cfgs is None else cfgs
    t0 = time.time()
    radial = [c for c in cfgs if model != "lindistflow" or E.is_radial(c)]
    skipped = len(cfgs) - len(radial)
    if model in ("linac", "auto"):   # build linearisations in the parent so forked workers share them
        for c in radial:
            linear_model(c, model)
    try:
        Encoder(radial[0], env, delta, model).rule(rule)
    except NotExpressible as e:
        return ExactResult("not_expressible", None, None, time.time() - t0, [], f"measurement {e} has no linear form")
    workers = workers or min(os.cpu_count() or 1, 8)
    jobs = [(rule, c, env, timeout_ms, delta, model) for c in radial]
    if workers > 1 and len(jobs) > 4:
        with ProcessPoolExecutor(workers, mp_context=mp.get_context("fork")) as ex:
            per = list(ex.map(_solve_one, jobs, chunksize=max(1, len(jobs) // (4 * workers))))
    else:
        per = [_solve_one(j) for j in jobs]
    sat = [p for p in per if p[1] == "sat"]
    status = "sat" if sat else ("unsat" if all(p[1] == "unsat" for p in per) else "unknown")
    note = f"{skipped} meshed configurations not covered (LinDistFlow is radial only)" if skipped else ""
    first = sat[0] if sat else None
    return ExactResult(status, first[0] if first else None, first[3] if first else None, time.time() - t0, per, note)


def load_delta(path):
    import json
    d = json.loads(open(path).read())
    out = {k: float(v) for k, v in d["delta"].items()}
    if d.get("linear_atoms"):
        out["linear_atoms"] = {k: float(v) for k, v in d["linear_atoms"].items()}
    return out


def load_deltas(paths: dict):
    """{model: path} -> {model: quantity dict}, for model='auto'."""
    return {k: load_delta(p) for k, p in paths.items()}
