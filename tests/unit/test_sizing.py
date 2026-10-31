from hypothesis import given
from hypothesis import strategies as st

from adamantem.risk.sizing import SymbolSpec, size_position

SPEC = SymbolSpec()


def size(equity=500.0, risk=3.0, entry=2000.0, stop=1996.0, lev=20.0, slip=0.0):
    return size_position(equity, risk, entry, stop, SPEC, slip, lev, 50.0)


def test_rounds_down_never_up():
    r = size()  # $15 budget, $4 stop -> 0.0375 lot -> 0.03
    assert r.ok and r.volume == 0.03 and abs(r.risk_money - 12.0) < 1e-9


def test_rejects_when_min_lot_too_risky():
    r = size(risk=1.0, stop=1990.0)  # $5 budget, $10 stop at 0.01 lot = $10
    assert not r.ok and r.reason == "min_lot_exceeds_risk"


def test_min_lot_allowed_up_to_cap():
    # 1% target ($5) but 0.01 lot risks $10 (2%): taken because the cap is 5% ($25)
    r = size_position(500.0, 1.0, 2000.0, 1990.0, SPEC, 0.0, 20.0, 50.0, min_lot_risk_cap_pct=5.0)
    assert r.ok and r.volume == 0.01 and abs(r.risk_money - 10.0) < 1e-9
    # 0.01 lot risking $30 (6%) is still rejected
    r = size_position(500.0, 1.0, 2000.0, 1970.0, SPEC, 0.0, 20.0, 50.0, min_lot_risk_cap_pct=5.0)
    assert not r.ok and r.reason == "min_lot_exceeds_risk"


def test_leverage_cap_limits_volume():
    r = size(entry=4000.0, stop=3999.0)  # 0.15 lot by risk, cap 20x$500/$400k per lot = 0.025
    assert r.ok and r.volume == 0.02


def test_leverage_cap_can_reject():
    r = size(entry=4000.0, stop=3999.0, lev=5.0)  # cap 0.00625 lot
    assert not r.ok and r.reason == "leverage_cap"


@given(
    equity=st.floats(100, 100_000),
    risk=st.floats(0.1, 3.0),
    entry=st.floats(1000, 5000),
    dist=st.floats(0.05, 50),
    slip=st.floats(0, 1),
)
def test_risk_never_exceeds_budget(equity, risk, entry, dist, slip):
    r = size_position(equity, risk, entry, entry - dist, SPEC, slip, 20.0, 50.0,
                      min_lot_risk_cap_pct=5.0)
    if r.ok:
        assert r.risk_money <= equity * max(risk, 5.0 if r.volume == SPEC.volume_min else 0) / 100 + 1e-6
        assert r.volume >= SPEC.volume_min
        assert r.volume * entry * SPEC.contract_size <= 20.0 * equity + 1e-6
