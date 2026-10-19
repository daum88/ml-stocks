"""Truncation invariance + no-lookahead tests (spec §4 rule 7, §11)."""
import numpy as np

from trendbot.indicators.indicators import sma, ema, atr
from trendbot.strategy.strategy import Strategy
from trendbot.common import timeutil
from conftest import mk_bars

D = timeutil.INTERVAL_MS["1d"]
H4 = timeutil.INTERVAL_MS["4h"]


def _rw(n, seed):
    rng = np.random.default_rng(seed)
    return 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))


def test_indicator_truncation_invariance():
    close = _rw(1000, 0)
    for n in (14, 50, 200):
        full_sma = sma(close, n)
        full_ema = ema(close, n)
        for t in (610, 700, 999):   # all >= 3*200 warm-up
            tr = close[: t + 1]
            assert full_sma[t] == sma(tr, n)[t]
            assert full_ema[t] == ema(tr, n)[t]
    high = close + 1; low = close - 1
    full_atr = atr(high, low, close, 14)
    for t in (200, 500, 999):
        assert full_atr[t] == atr(high[: t + 1], low[: t + 1], close[: t + 1], 14)[t]


def test_mutating_future_does_not_change_past_decision(prereg):
    n = 1400
    close = 100.0 + np.arange(n) * 0.5
    sig = mk_bars(np.arange(n) * H4, close, H4)
    daily = mk_bars(np.arange(300) * D, 100.0 + np.arange(300) * 1.0, D)
    strat = Strategy("V2", prereg.strategy, prereg, sig, daily)

    # decision at some bar t in the middle
    t = 700
    d_before = strat.decide(t, "flat").decision

    # mutate the future (everything after t) and rebuild
    close2 = close.copy()
    close2[t + 1 :] *= 10.0
    sig2 = mk_bars(np.arange(n) * H4, close2, H4)
    strat2 = Strategy("V2", prereg.strategy, prereg, sig2, daily)
    d_after = strat2.decide(t, "flat").decision

    assert d_before == d_after


def test_parity_live_and_backtest_share_decision_code(prereg):
    """The live tool and backtester call the same Strategy.decide (spec §12, rule 2)."""
    n = 1400
    close = 100.0 + np.arange(n) * 0.5
    sig = mk_bars(np.arange(n) * H4, close, H4)
    daily = mk_bars(np.arange(300) * D, 100.0 + np.arange(300) * 1.0, D)

    # "backtest" strategy over full history
    bt_strat = Strategy("V2", prereg.strategy, prereg, sig, daily)
    # "live" strategy built from data truncated at each bar must agree
    for t in [500, 700, 900, 1200]:
        live_strat = Strategy("V2", prereg.strategy, prereg,
                              mk_bars(sig.open_time[: t + 1], close[: t + 1], H4), daily)
        for pos in ("flat", "long"):
            assert bt_strat.decide(t, pos).decision == live_strat.decide(t, pos).decision
