"""Indicators — exact definitions per spec §5.

- SMA(n): arithmetic mean of the last n closes (incl. current bar), valid from the nth bar.
- EMA(n): alpha = 2/(n+1); seed = SMA of first n closes placed at the nth bar; warm-up
  discards values until bar index 3*n (0-indexed) to remove seed influence.
- ATR(14): True Range = max(high-low, |high-prev_close|, |low-prev_close|); first ATR =
  mean of first 14 TRs; then Wilder smoothing ATR_t = (ATR_{t-1}*13 + TR_t)/14; warm-up
  discards values until 100 bars.

Convention: indicators are computed on a full array and returned with NaN for invalid
(warm-up) positions. NaNs never trigger signals (the decision logic treats NaN as invalid).
"""
from __future__ import annotations

import numpy as np


def sma(values: np.ndarray, n: int) -> np.ndarray:
    """Simple moving average. Valid from the nth bar (0-indexed index n-1)."""
    values = np.asarray(values, dtype=np.float64)
    if n <= 0:
        raise ValueError("n must be > 0")
    out = np.full(values.shape, np.nan, dtype=np.float64)
    if values.size < n:
        return out
    csum = np.cumsum(np.insert(values, 0, 0.0))
    out[n - 1 :] = (csum[n:] - csum[:-n]) / n
    return out


def ema(values: np.ndarray, n: int, warmup_mult: int = 3) -> np.ndarray:
    """Exponential moving average, SMA-seeded, with 3*n warm-up (spec §5)."""
    values = np.asarray(values, dtype=np.float64)
    if n <= 0:
        raise ValueError("n must be > 0")
    out = np.full(values.shape, np.nan, dtype=np.float64)
    if values.size < n:
        return out
    alpha = 2.0 / (n + 1.0)
    # Seed = SMA of first n closes, placed at the nth bar (index n-1).
    out[n - 1] = values[:n].mean()
    for t in range(n, values.size):
        out[t] = alpha * values[t] + (1.0 - alpha) * out[t - 1]
    # Warm-up: invalid until bar index warmup_mult*n (0-indexed).
    first_valid = warmup_mult * n
    if first_valid < values.size:
        out[:first_valid] = np.nan
    else:
        out[:] = np.nan
    return out


def true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """True Range per bar (spec §5)."""
    high = np.asarray(high, dtype=np.float64)
    low = np.asarray(low, dtype=np.float64)
    close = np.asarray(close, dtype=np.float64)
    prev_close = np.empty_like(close)
    prev_close[0] = close[0]  # first TR has no previous close: use current close
    prev_close[1:] = close[:-1]
    tr = np.maximum.reduce(
        [high - low, np.abs(high - prev_close), np.abs(low - prev_close)]
    )
    return tr


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = 14,
        warmup_bars: int = 100) -> np.ndarray:
    """Average True Range, Wilder-smoothed, valid from `warmup_bars` bars (spec §5)."""
    high = np.asarray(high, dtype=np.float64)
    low = np.asarray(low, dtype=np.float64)
    close = np.asarray(close, dtype=np.float64)
    tr = true_range(high, low, close)
    out = np.full(tr.shape, np.nan, dtype=np.float64)
    if tr.size < n:
        return out
    out[n - 1] = tr[:n].mean()
    for t in range(n, tr.size):
        out[t] = (out[t - 1] * (n - 1) + tr[t]) / n
    first_valid = warmup_bars
    if first_valid < tr.size:
        out[:first_valid] = np.nan
    else:
        out[:] = np.nan
    return out


def cross_up(fast: np.ndarray, slow: np.ndarray) -> np.ndarray:
    """Cross-up event at bar t: fast_t > slow_t and fast_{t-1} <= slow_{t-1} (spec §5).

    Returns a boolean array. Bars with NaN in either series never produce a cross.
    """
    fast = np.asarray(fast, dtype=np.float64)
    slow = np.asarray(slow, dtype=np.float64)
    out = np.zeros(fast.shape, dtype=bool)
    if fast.size < 2:
        return out
    prev_fast, prev_slow = fast[:-1], slow[:-1]
    cur_fast, cur_slow = fast[1:], slow[1:]
    valid = ~(np.isnan(cur_fast) | np.isnan(cur_slow) | np.isnan(prev_fast) | np.isnan(prev_slow))
    out[1:] = valid & (cur_fast > cur_slow) & (prev_fast <= prev_slow)
    return out


def fast_above_slow(fast: np.ndarray, slow: np.ndarray) -> np.ndarray:
    """Fast-above-slow state at bar t: fast_t > slow_t (strict; NaN -> False)."""
    fast = np.asarray(fast, dtype=np.float64)
    slow = np.asarray(slow, dtype=np.float64)
    valid = ~(np.isnan(fast) | np.isnan(slow))
    return valid & (fast > slow)
