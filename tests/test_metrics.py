"""Metrics hand-computed tests (spec §8.3, §11)."""
import numpy as np
import pytest

from trendbot.metrics import metrics as M


def test_cagr_hand_computed():
    # 121/100 over exactly one year -> 21%
    assert M.cagr(121.0, 100.0, 365.25) == pytest.approx(0.21)


def test_cagr_zero_and_negative():
    assert M.cagr(100.0, 100.0, 365.25) == pytest.approx(0.0)
    assert M.cagr(50.0, 100.0, 365.25) == pytest.approx(-0.5)


def test_max_drawdown_hand_computed():
    eq = np.array([100.0, 150.0, 100.0, 200.0])
    assert M.max_drawdown(eq) == pytest.approx((150.0 - 100.0) / 150.0)


def test_max_drawdown_zero_when_flat():
    assert M.max_drawdown(np.array([100.0, 100.0, 100.0])) == pytest.approx(0.0)


def test_calmar_undefined_on_zero_drawdown():
    assert M.calmar(0.2, 0.0) is None


def test_calmar_hand_computed():
    assert M.calmar(0.2, 0.1) == pytest.approx(2.0)


def test_daily_grid_alignment():
    grid = M.daily_grid(1704067200000 + 3_600_000, 1704067200000 + 3 * 86_400_000)
    assert grid[0] % M.DAILY_MS == 0
    assert (grid[1] - grid[0]) == M.DAILY_MS


def test_resample_daily_carry_forward():
    times = np.array([10, 100, 200], dtype=np.int64)
    vals = np.array([1.0, 2.0, 3.0])
    grid = np.array([0, 50, 150, 250], dtype=np.int64)
    out = M.resample_daily(times, vals, grid, initial=0.0)
    # grid 0 -> no sample -> initial 0 ; 50 -> last <=50 is 10 -> 1 ; 150 -> 100 -> 2 ; 250 -> 200 -> 3
    assert out.tolist() == pytest.approx([0.0, 1.0, 2.0, 3.0])


def test_round_trips_pairing():
    fills = [
        {"side": "BUY", "price": 100.0, "qty": 1.0, "fee": 0.5, "time_ms": 0},
        {"side": "SELL", "price": 120.0, "qty": 1.0, "fee": 0.6, "time_ms": 10},
        {"side": "BUY", "price": 110.0, "qty": 1.0, "fee": 0.55, "time_ms": 20},
    ]
    trips = M.round_trips(fills)
    assert len(trips) == 1
    assert trips[0]["pnl"] == pytest.approx((120.0 - 0.6) - (100.0 + 0.5))
