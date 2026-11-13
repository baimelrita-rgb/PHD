import numpy as np
import pytest
from p3 import envelope as E, measure as M, synthesis as Y


@pytest.fixture(autouse=True)
def reference_grid():
    E.use_grid("cigre_pv_wind")
    yield
    E.use_grid("cigre_pv_wind")


def test_invariant_residual_small_at_linearisation_point():
    cfg = E.base_config()
    x0 = Y.LA.model(cfg).x0
    ok, ben, _, m = M.evaluate(x0, cfg)
    assert ok
    for kind, i in (("vm", 11), ("p", 0)):
        co, c = Y.invariant(cfg, kind, i)
        assert abs(Y.residual(co, c, m)) < 1e-6


def test_invariant_rule_fires_on_falsified_voltage():
    cfg = E.base_config()
    x0 = Y.LA.model(cfg).x0
    _, _, _, m = M.evaluate(x0, cfg)
    co, c = Y.invariant(cfg, "vm", 11)
    rule = Y.invariant_rule(cfg, co, c, 0.005, "t", 0.01)
    from p3 import rules as R
    assert not R.fires(rule, m)
    m2 = m.copy(); m2[M.index()["vm_pu.11"]] -= 0.02     # drift-off style falsification
    assert R.fires(rule, m2)
