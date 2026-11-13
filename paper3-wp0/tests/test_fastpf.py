import numpy as np
from p3 import envelope as E, measure as M


def test_fast_solver_matches_runpp():
    X, ci, cfgs = E.sample_lhs(E.ENVELOPE_FULL, 32, seed=3)
    for x, c in zip(X, ci):
        ok, _, _, m = M.evaluate(x, cfgs[c])
        net = E.run_reference_pf(x, cfgs[c])
        assert ok == (net is not None)
        if ok:
            assert np.max(np.abs(M.vector_from_net(net) - m)) < 1e-5
