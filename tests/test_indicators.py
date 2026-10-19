"""Hand-computed indicator tests (spec §11)."""
import numpy as np
import pytest

from trendbot.indicators.indicators import (
    sma, ema, atr, true_range, cross_up, fast_above_slow,
)
from trendbot.common import timeutil


# --- timeutil ---------------------------------------------------------------
def test_detect_ts_unit_seconds_ms_us_ns():
    assert timeutil.detect_ts_unit(np.array([1_700_000_000])) == 1e3      # seconds
    assert timeutil.detect_ts_unit(np.array([1_700_000_000_000])) == 1.0   # ms
    assert timeutil.detect_ts_unit(np.array([1_700_000_000_000_000])) == 1e-3  # us
    assert timeutil.detect_ts_unit(np.array([1_700_000_000_000_000_000])) == 1e-6  # ns


def test_detect_ts_unit_rejects_empty_and_mixed():
    with pytest.raises(ValueError):
        timeutil.detect_ts_unit(np.array([]))
    with pytest.raises(ValueError):
        timeutil.detect_ts_unit(np.array([0, 1]))
    with pytest.raises(ValueError):
        timeutil.detect_ts_unit(np.array([1_700_000_000, 1_700_000_000_000]))


def test_floor_to_interval_and_close_time():
    assert timeutil.floor_to_interval(3_700_000, timeutil.INTERVAL_MS["1h"]) == 3_600_000
    assert timeutil.floor_to_interval(3_600_000, timeutil.INTERVAL_MS["1h"]) == 3_600_000
    assert timeutil.close_time(0, timeutil.INTERVAL_MS["1h"]) == 3_600_000


# --- SMA --------------------------------------------------------------------
def test_sma_hand_computed():
    v = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    out = sma(v, 3)
    assert np.isnan(out[0]) and np.isnan(out[1])
    assert out[2] == pytest.approx(2.0)
    assert out[3] == pytest.approx(3.0)
    assert out[4] == pytest.approx(4.0)


def test_sma_too_short_all_nan():
    out = sma(np.array([1.0, 2.0]), 5)
    assert np.all(np.isnan(out))


# --- EMA --------------------------------------------------------------------
def test_ema_seed_is_sma_of_first_n():
    v = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    out = ema(v, 3, warmup_mult=0)  # no warm-up masking -> expose seed
    # seed at index 2 = (1+2+3)/3 = 2.0
    assert out[2] == pytest.approx(2.0)
    # alpha = 2/4 = 0.5
    assert out[3] == pytest.approx(0.5 * 4.0 + 0.5 * 2.0)  # 3.0
    assert out[4] == pytest.approx(0.5 * 5.0 + 0.5 * 3.0)  # 4.0


def test_ema_warmup_masks_until_3n():
    v = np.arange(1.0, 11.0)  # 10 values
    out = ema(v, 3)  # warm-up until index 9 (3n)
    assert np.all(np.isnan(out[:9]))
    assert not np.isnan(out[9])


def test_ema_not_seeded_with_first_value():
    # If wrongly seeded with the first value, EMA would differ from SMA-seed.
    v = np.array([100.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    out = ema(v, 3, warmup_mult=0)
    # SMA-seed at index 2 = (100+1+1)/3 = 34.0
    assert out[2] == pytest.approx(34.0)
    # A "seed with first value" implementation would give 100 here.
    assert out[2] != pytest.approx(100.0)


# --- ATR --------------------------------------------------------------------
def test_atr_hand_computed():
    close = np.array([10.0, 11.0, 12.0])
    high = np.array([12.0, 13.0, 14.0])
    low = np.array([9.0, 10.0, 11.0])
    tr = true_range(high, low, close)
    # TR[0] = max(3, |12-10|=2, |9-10|=1) = 3 ; TR[1] = max(3,2,1)=3 ; TR[2] = max(3,2,1)=3
    assert tr[0] == pytest.approx(3.0)
    assert tr[1] == pytest.approx(3.0)
    assert tr[2] == pytest.approx(3.0)

    out = atr(high, low, close, n=2, warmup_bars=0)
    assert np.isnan(out[0])
    assert out[1] == pytest.approx(3.0)  # seed = mean(3,3)
    assert out[2] == pytest.approx(3.0)  # Wilder: (3*1 + 3)/2


def test_atr_warmup_masks_until_100():
    rng = np.random.default_rng(0)
    n = 120
    close = rng.uniform(50, 60, n)
    high = close + rng.uniform(0, 2, n)
    low = close - rng.uniform(0, 2, n)
    out = atr(high, low, close, n=14, warmup_bars=100)
    assert np.all(np.isnan(out[:100]))
    assert np.all(~np.isnan(out[100:]))


# --- cross detection --------------------------------------------------------
def test_cross_up_exact_bar():
    fast = np.array([1.0, 2.0, 3.0, 4.0])
    slow = np.array([2.0, 2.0, 3.0, 5.0])
    out = cross_up(fast, slow)
    # bar0: 1<=2 (below); bar1: 2>2? no (2<=2, not >); bar2: 3>3? no; bar3: 4>5? no
    assert not out.any()


def test_cross_up_strict_inequality_no_cross_on_equality():
    # Equality does not cross (strict inequality required).
    fast = np.array([1.0, 2.0, 2.0, 3.0])
    slow = np.array([1.0, 2.0, 2.0, 2.0])
    out = cross_up(fast, slow)
    # bar1: prev 1<=1 true, cur 2>2 false -> no
    # bar2: prev 2<=2 true, cur 2>2 false -> no
    # bar3: prev 2<=2 true, cur 3>2 true -> cross
    assert list(out) == [False, False, False, True]


def test_cross_up_detects_single_event():
    fast = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    slow = np.array([2.0, 2.0, 2.0, 2.0, 2.0, 2.0])
    out = cross_up(fast, slow)
    assert out.tolist() == [False, False, True, False, False, False]


def test_cross_up_nan_never_crosses():
    fast = np.array([np.nan, 2.0, 3.0])
    slow = np.array([1.0, 1.0, 4.0])
    assert not cross_up(fast, slow).any()


def test_fast_above_slow_strict_and_nan():
    assert fast_above_slow(np.array([2.0, 3.0]), np.array([1.0, 3.0])).tolist() == [True, False]
    assert fast_above_slow(np.array([np.nan, 3.0]), np.array([1.0, 1.0])).tolist() == [False, True]
