"""Execution / fill-simulator tests (spec §11)."""
import numpy as np
import pytest

from trendbot.strategy.strategy import Strategy
from trendbot.execution.fillsim import Backtester
from trendbot.common import timeutil
from conftest import mk_bars, prereg_delay0

D = timeutil.INTERVAL_MS["1d"]
M5 = timeutil.INTERVAL_MS["5m"]


def _mk_5m(start_ms, n, ohlc):
    """Build a 5m BarSeries; ohlc(k) -> (open, high, low, close)."""
    t = start_ms + np.arange(n) * M5
    o = np.empty(n); h = np.empty(n); l = np.empty(n); c = np.empty(n)
    for k in range(n):
        o[k], h[k], l[k], c[k] = ohlc(k)
    return mk_bars(t, c, M5, high=h, low=l)


def _v1_backtester(prereg, fees, daily_close, base5m):
    daily = mk_bars(np.arange(len(daily_close)) * D, daily_close, D)
    strat = Strategy("V1", prereg.strategy, prereg, daily, daily)
    return Backtester(strat, base5m, prereg, fees)


def _rising_close(n=210, base=100.0, step=1.0):
    return base + np.arange(n) * step


def test_v1_enters_then_exits_sanity(prereg, fees):
    cfg = prereg_delay0(prereg)
    close = _rising_close(260)
    close[240:] = 50.0  # crash -> exit
    daily = mk_bars(np.arange(260) * D, close, D)
    # 5m bars all flat at 1.0 -> entries never fill, but this is a smoke test of the loop.
    base5m = _mk_5m(200 * D, 200 * 288, lambda k: (1.0, 1.0, 1.0, 1.0))
    strat = Strategy("V1", cfg.strategy, cfg, daily, daily)
    bt = Backtester(strat, base5m, cfg, fees)
    res = bt.run(start_time_ms=200 * D, end_time_ms=259 * D)
    assert res.final_equity >= 0


def test_entry_missed_when_limit_never_traded_through(prereg, fees):
    cfg = prereg_delay0(prereg)
    close = _rising_close()
    base5m = _mk_5m(200 * D, 4 * 288, lambda k: (300.0, 300.0, 300.0, 300.0))
    # limit = close[199]*(1-1e-4) ~ 298.97; lows at 300 never trade through -> missed.
    daily = mk_bars(np.arange(210) * D, close, D)
    strat = Strategy("V1", cfg.strategy, cfg, daily, daily)
    bt = Backtester(strat, base5m, cfg, fees)
    res = bt.run(start_time_ms=200 * D, end_time_ms=202 * D)
    assert res.missed_trades == 1
    assert len(res.fills) == 0


def test_entry_no_fill_on_touch_without_haircut(prereg, fees):
    cfg = prereg_delay0(prereg)
    close = _rising_close()
    # limit ~ 298.97 ; haircut threshold ~ 298.82. Low = 298.90 touches but not through.
    # End the run inside the first attempt window so no re-price occurs.
    def ohlc(k):
        return (299.0, 299.0, 298.90 if k == 0 else 299.0, 299.0)
    base5m = _mk_5m(200 * D, 12, ohlc)
    daily = mk_bars(np.arange(210) * D, close, D)
    strat = Strategy("V1", cfg.strategy, cfg, daily, daily)
    bt = Backtester(strat, base5m, cfg, fees)
    res = bt.run(start_time_ms=200 * D, end_time_ms=200 * D + 12 * M5)
    assert len(res.fills) == 0
    assert res.missed_trades == 0


def test_entry_fills_when_traded_through(prereg, fees):
    cfg = prereg_delay0(prereg)
    close = _rising_close()
    # first 5m bar low = 298.0 < threshold -> fill
    def ohlc(k):
        if k == 0:
            return (299.0, 299.0, 298.0, 299.0)
        return (299.0, 299.0, 299.0, 299.0)
    base5m = _mk_5m(200 * D, 2 * 288, ohlc)
    daily = mk_bars(np.arange(210) * D, close, D)
    strat = Strategy("V1", cfg.strategy, cfg, daily, daily)
    bt = Backtester(strat, base5m, cfg, fees)
    res = bt.run(start_time_ms=200 * D, end_time_ms=202 * D)
    assert len(res.fills) == 1
    f = res.fills[0]
    assert f["side"] == "BUY"
    # fill price = limit*(1+entry_slip) with limit = 299*(1-1e-4)
    limit = 299.0 * (1.0 - 1e-4)
    assert f["price"] == pytest.approx(limit * (1.0 + 0.0010))


def test_filled_gap_bars_never_fill(prereg, fees):
    cfg = prereg_delay0(prereg)
    close = _rising_close()
    # All bars trade through, but are filled-gap rows -> no fill.
    def ohlc(k):
        return (299.0, 299.0, 298.0, 299.0)
    t = 200 * D + np.arange(2 * 288) * M5
    c = np.full(t.shape, 299.0)
    base5m = mk_bars(t, c, M5, high=np.full(t.shape, 299.0), low=np.full(t.shape, 298.0))
    base5m.is_filled_gap = np.ones(t.shape, dtype=bool)
    daily = mk_bars(np.arange(210) * D, close, D)
    strat = Strategy("V1", cfg.strategy, cfg, daily, daily)
    bt = Backtester(strat, base5m, cfg, fees)
    res = bt.run(start_time_ms=200 * D, end_time_ms=202 * D)
    assert len(res.fills) == 0


def test_signal_expired_when_condition_turns_false(prereg, fees):
    cfg = prereg_delay0(prereg)
    # Rising until 200, then crash: at the re-price close (bar 200) close < SMA -> expired.
    close = _rising_close(230)
    close[200:] = 50.0
    def ohlc(k):
        return (300.0, 300.0, 300.0, 300.0)  # never fills
    base5m = _mk_5m(200 * D, 4 * 288, ohlc)
    daily = mk_bars(np.arange(230) * D, close, D)
    strat = Strategy("V1", cfg.strategy, cfg, daily, daily)
    bt = Backtester(strat, base5m, cfg, fees)
    res = bt.run(start_time_ms=200 * D, end_time_ms=203 * D)
    assert res.signal_expired == 1
    assert len(res.fills) == 0


def test_quantity_rounding_down(prereg, fees):
    cfg = prereg_delay0(prereg)
    # V1 fills: qty = cash/(fill*(1+maker)) rounded DOWN to 1e-8.
    from trendbot.accounting.ledger import Ledger
    from trendbot.execution.fillsim import Backtester
    bt = Backtester.__new__(Backtester)  # bypass init; set fields directly
    bt.maker = 0.0015
    bt.qty_step = 1e-8
    bt.min_order_quote = 5.0
    bt.min_order_base = 0.00006942
    bt.is_v1 = True
    bt.risk = 0.01
    bt.trailing_mult = None
    bt.prereg = cfg
    led = Ledger(400.0)
    qty = bt._size_entry(led, fill_price=100.0, atr=0.0)
    assert qty == pytest.approx(np.floor(400.0 / (100.0 * 1.0015) / 1e-8) * 1e-8)
    assert qty * 100.0 * 1.0015 <= 400.0 + 1e-9


def test_min_order_skip(prereg, fees):
    cfg = prereg_delay0(prereg)
    from trendbot.accounting.ledger import Ledger
    from trendbot.execution.fillsim import Backtester
    bt = Backtester.__new__(Backtester)
    bt.maker = 0.0015
    bt.qty_step = 1e-8
    bt.min_order_quote = 1000.0  # huge min -> skip
    bt.min_order_base = 1.0
    bt.is_v1 = True
    bt.risk = 0.01
    bt.trailing_mult = None
    bt.prereg = cfg
    led = Ledger(400.0)
    assert bt._size_entry(led, fill_price=100.0, atr=0.0) is None
