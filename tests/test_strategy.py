"""Strategy decision-logic tests on synthetic data (spec §11)."""
import numpy as np

from trendbot.strategy.strategy import Strategy, ENTER, EXIT, HOLD
from trendbot.common import timeutil
from conftest import mk_bars

D = timeutil.INTERVAL_MS["1d"]
H4 = timeutil.INTERVAL_MS["4h"]
H1 = timeutil.INTERVAL_MS["1h"]


def _rising_daily(n=300, base=100.0, step=1.0):
    t = np.arange(n) * D
    close = base + np.arange(n) * step
    return mk_bars(t, close, D)


def _flat_then_jump(n=1400, jump_at=1300, base=100.0, jump_to=150.0, step=0.5):
    t = np.arange(n) * H4
    close = np.full(n, base)
    close[jump_at:] = jump_to + np.arange(n - jump_at) * step
    return mk_bars(t, close, H4)


def test_v1_flat_series_no_trades(prereg):
    sig = mk_bars(np.arange(300) * D, np.full(300, 100.0), D)
    strat = Strategy("V1", prereg.strategy, prereg, sig, sig)
    for t in range(199, 300):
        assert strat.decide(t, "flat").decision == HOLD
        assert strat.decide(t, "long").decision == HOLD  # close == SMA -> no exit


def test_v1_rising_enters_once_never_exits(prereg):
    sig = _rising_daily()
    strat = Strategy("V1", prereg.strategy, prereg, sig, sig)
    enters, exits = [], []
    pos = "flat"
    for t in range(199, 260):
        d = strat.decide(t, pos)
        if d.decision == ENTER:
            enters.append(t)
            pos = "long"
        elif d.decision == EXIT:
            exits.append(t)
            pos = "flat"
    assert enters == [199]
    assert exits == []


def test_v1_rise_then_fall_one_round_trip(prereg):
    n = 260
    close = 100.0 + np.arange(n) * 1.0   # rising
    close[240:] = 50.0                    # then crash below SMA
    sig = mk_bars(np.arange(n) * D, close, D)
    strat = Strategy("V1", prereg.strategy, prereg, sig, sig)
    enters, exits = [], []
    pos = "flat"
    for t in range(199, n):
        d = strat.decide(t, pos)
        if d.decision == ENTER:
            enters.append(t)
            pos = "long"
        elif d.decision == EXIT:
            exits.append(t)
            pos = "flat"
    assert len(enters) == 1 and len(exits) == 1
    assert enters[0] < exits[0]


def test_v2_cross_entry_requires_gate_and_event(prereg):
    # Flat then jump: one cross-up. Gate on via rising daily.
    sig = _flat_then_jump()
    daily = _rising_daily()
    strat = Strategy("V2", prereg.strategy, prereg, sig, daily)

    n_cross = int(strat.cross.sum())
    assert n_cross == 1
    t_cross = int(np.argmax(strat.cross))
    assert t_cross == 1300  # the cross is at the jump bar, not during warm-up

    # gate on at the cross bar
    assert bool(strat.gate[t_cross]) is True
    assert strat.decide(t_cross, "flat").decision == ENTER
    # before the cross, no entry
    assert strat.decide(t_cross - 1, "flat").decision == HOLD


def test_v2_ree_entry_waits_for_new_cross(prereg):
    sig = _flat_then_jump()
    daily = _rising_daily()
    strat = Strategy("V2", prereg.strategy, prereg, sig, daily)
    t_cross = int(np.argmax(strat.cross))
    # After the cross bar, fast > slow (state) but no new event -> no entry.
    assert strat.fast[t_cross + 1] > strat.slow[t_cross + 1]
    assert bool(strat.cross[t_cross + 1]) is False
    assert strat.decide(t_cross + 1, "flat").decision == HOLD


def test_v2_exit_when_fast_below_slow(prereg):
    # Rising then crash -> fast crosses below slow.
    n = 400
    close = 100.0 + np.arange(n) * 0.5
    close[340:] = 40.0
    sig = mk_bars(np.arange(n) * H4, close, H4)
    daily = _rising_daily()
    strat = Strategy("V2", prereg.strategy, prereg, sig, daily)
    # find a bar after the crash where fast < slow
    crash = False
    for t in range(340, n):
        if not np.isnan(strat.fast[t]) and strat.fast[t] < strat.slow[t]:
            assert strat.decide(t, "long").decision == EXIT
            crash = True
            break
    assert crash


def test_gate_uses_most_recent_closed_daily(prereg):
    """An intraday decision at 05:00 UTC uses yesterday's daily close, not today's (spec §4 rule 3)."""
    n = 205
    close = np.full(n, 100.0)
    close[202] = 120.0   # "yesterday" -> gate ON (above SMA)
    close[203] = 50.0    # "today"    -> gate OFF (but its bar has not closed at 05:00)
    daily = mk_bars(np.arange(n) * D, close, D)

    # 1h signal bar at 05:00 on day 203 (open_time = 203 days + 5h).
    sig_open = 203 * D + 5 * H1
    sig = mk_bars(np.array([sig_open]), np.array([150.0]), H1)

    strat = Strategy("V3", prereg.strategy, prereg, sig, daily)
    assert bool(strat.gate[0]) is True   # uses daily bar 202 (close 120 > SMA), not 203
