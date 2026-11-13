import numpy as np
import pytest
from p3 import measure as M, rules as R


def vec(**kv):
    m = np.zeros(len(M.names()))
    idx = M.index()
    for k, v in kv.items():
        m[idx[k.replace("__", ".")]] = v
    return m


R1 = {"atoms": [{"type": "threshold", "meas": "vm_pu.11", "op": "<", "value": 0.95}]}
R2 = {"atoms": [{"type": "threshold", "meas": "loading.0", "op": ">", "value": 70.0},
                {"type": "linear", "coeffs": {"load_p.1": 1.0, "load_p.2": 1.0}, "op": "<", "value": 1.0}]}
R3 = {"any_of": [[{"type": "linear", "coeffs": {"trafo_p_hv.0": 1.0, "load_p.0": -1.0}, "op": ">", "value": 0.1}],
                 [{"type": "linear", "coeffs": {"trafo_p_hv.0": -1.0, "load_p.0": 1.0}, "op": ">", "value": 0.1}]]}
RD = {"atoms": [{"type": "discrete", "meas": "sw.4", "value": 1.0},
                {"type": "threshold", "meas": "vm_pu.11", "op": "<", "value": 0.95}]}


def test_threshold():
    assert R.fires(R1, vec(vm_pu__11=0.94))
    assert not R.fires(R1, vec(vm_pu__11=0.96))
    assert not R.fires(R1, vec(vm_pu__11=0.95))  # strict
    assert R.margin(R1, vec(vm_pu__11=0.94)) == pytest.approx(0.01)


def test_conjunction_linear():
    assert R.fires(R2, vec(loading__0=80, load_p__1=0.3, load_p__2=0.3))
    assert not R.fires(R2, vec(loading__0=80, load_p__1=0.6, load_p__2=0.6))
    assert not R.fires(R2, vec(loading__0=60, load_p__1=0.3, load_p__2=0.3))


def test_disjunction_abs():
    assert R.fires(R3, vec(trafo_p_hv__0=10.5, load_p__0=10.0))
    assert R.fires(R3, vec(trafo_p_hv__0=9.5, load_p__0=10.0))
    assert not R.fires(R3, vec(trafo_p_hv__0=10.05, load_p__0=10.0))


def test_discrete():
    assert R.fires(RD, vec(sw__4=1.0, vm_pu__11=0.9))
    assert not R.fires(RD, vec(sw__4=0.0, vm_pu__11=0.9))


def test_saved_rules_validate():
    from p3 import common as C
    if C.RULES_PATH.exists():
        rules = R.load(C.RULES_PATH)
        assert set(rules) == {"R1", "R2", "R3"}


def test_robust_encoding_zero_delta_equals_nominal():
    from p3 import envelope as E, oracle_exact as X
    cfg = E.base_config()
    for rule in (R1, R2):
        a = X.solve(rule, (cfg,)).status
        b = X.solve(rule, (cfg,), delta=dict(X.ZERO_DELTA)).status
        assert a == b
