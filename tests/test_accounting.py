"""Accounting identity + baseline determinism tests (spec §8.1, §9.4, §11)."""
import numpy as np
import pytest

from trendbot.strategy.strategy import Strategy
from trendbot.execution.fillsim import Backtester
from trendbot.baselines import baselines
from trendbot.common import timeutil
from conftest import mk_bars, prereg_delay0

D = timeutil.INTERVAL_MS["1d"]
M5 = timeutil.INTERVAL_MS["5m"]


def test_accounting_identity_holds(prereg, fees):
    """final equity = initial + total P&L (net) + btc*mark  (spec §8.1)."""
    cfg = prereg_delay0(prereg)
    close = 100.0 + np.arange(230) * 1.0
    close[220:] = 60.0
    daily = mk_bars(np.arange(230) * D, close, D)
    def ohlc(k):
        return (100.0 + (k % 288) * 0.01, 100.0 + (k % 288) * 0.01 + 0.5,
                100.0 + (k % 288) * 0.01 - 0.5, 100.0 + (k % 288) * 0.01)
    base5m = mk_bars(200 * D + np.arange(6 * 288) * M5,
                     np.array([ohlc(k)[3] for k in range(6 * 288)]), M5,
                     high=np.array([ohlc(k)[1] for k in range(6 * 288)]),
                     low=np.array([ohlc(k)[2] for k in range(6 * 288)]))
    strat = Strategy("V1", cfg.strategy, cfg, daily, daily)
    bt = Backtester(strat, base5m, cfg, fees)
    res = bt.run(start_time_ms=200 * D, end_time_ms=225 * D)

    buys = sum(f["price"] * f["qty"] + f["fee"] for f in res.fills if f["side"] == "BUY")
    sells = sum(f["price"] * f["qty"] - f["fee"] for f in res.fills if f["side"] == "SELL")
    net_pnl = sells - buys
    btc = sum(f["qty"] for f in res.fills if f["side"] == "BUY") - \
          sum(f["qty"] for f in res.fills if f["side"] == "SELL")
    expected = 400.0 + net_pnl + btc * res.final_mark_price
    assert res.final_equity == pytest.approx(expected, rel=1e-9)


def test_circular_shift_same_seed_identical(prereg):
    frac = np.array([0.0, 1.0, 1.0, 0.0, 1.0] * 200)
    rets = np.random.default_rng(0).normal(0.001, 0.01, frac.size)
    f1, c1, g1 = baselines.circular_shift(frac, rets, 0.001, 1000, 42, 365.25)
    f2, c2, g2 = baselines.circular_shift(frac, rets, 0.001, 1000, 42, 365.25)
    assert np.array_equal(f1, f2)
    assert np.array_equal(c1, c2)


def test_circular_shift_different_seed_differs(prereg):
    frac = np.array([0.0, 1.0, 1.0, 0.0] * 500)
    rets = np.random.default_rng(1).normal(0.001, 0.01, frac.size)
    _, c1, _ = baselines.circular_shift(frac, rets, 0.001, 1000, 1, 365.25)
    _, c2, _ = baselines.circular_shift(frac, rets, 0.001, 1000, 2, 365.25)
    assert not np.array_equal(c1, c2)


def test_shift_preserves_position_changes_and_exposure():
    frac = np.array([0.0, 1.0, 1.0, 0.0, 1.0] * 200)
    rets = np.random.default_rng(2).normal(0.001, 0.01, frac.size)
    n_changes_orig = int(np.abs(np.diff(frac)).sum())
    exposure_orig = frac.mean()
    for k in (100, 300, 700):
        f = np.roll(frac, k)
        assert int(np.abs(np.diff(f)).sum()) == n_changes_orig
        assert f.mean() == pytest.approx(exposure_orig)
