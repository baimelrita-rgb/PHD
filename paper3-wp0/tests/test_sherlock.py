import itertools
import pytest
from p3 import sherlock_io as S

pytestmark = pytest.mark.skipif(not S.ROOT_DEFAULT.exists(), reason="Sherlock data not downloaded")


def test_fast_residual_matches_runpp():
    from p3 import sherlock_residual as SR
    recs = list(itertools.islice(S.iter_state(S.ROOT_DEFAULT, "test"), 0, 43000, 4000))
    m = SR.ResidualModel(recs[0]["state"])
    for r in recs:
        a, b = m.residual(r["state"]), m.residual(r["state"], reference=True)
        assert a["conv"] == b["conv"]
        for k in ("vm", "p_line", "p_trafo"):
            assert abs(a[k] - b[k]) < 1e-6


def test_ipal_tap_byte_mapping():
    from p3.sherlock_residual import ipal_to_snapshot_keys
    v = ipal_to_snapshot_keys({"trafo.0:tap_position": 255, "trafo.1:tap_position": 0})
    assert v["trafo.0.MEASUREMENT.tap_position"] == -1 and v["trafo.1.MEASUREMENT.tap_position"] == 0
