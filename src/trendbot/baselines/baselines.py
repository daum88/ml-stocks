"""Baselines — buy-and-hold, cash, exposure-matched, circular-shift (spec §9)."""
from __future__ import annotations

import numpy as np

from trendbot.metrics.metrics import cagr, calmar, max_drawdown, daily_grid, resample_daily

DAILY_MS = 86_400_000


def price_at_grid(base5m, grid: np.ndarray) -> np.ndarray:
    """5m-bar close price carry-forward resampled onto daily grid points."""
    times = base5m.open_time + base5m.interval_ms   # 5m close times
    return resample_daily(times, base5m.close, grid, initial=float(base5m.close[0]))


def buy_and_hold(base5m, start_ms: int, end_ms: int, initial_cash: float,
                 taker_fee: float, entry_slip: float):
    """One entry at the open of the first 5m bar >= start_ms; marked to market daily."""
    grid = daily_grid(start_ms, end_ms)
    # first 5m bar with open_time >= start_ms
    i0 = int(np.searchsorted(base5m.open_time, start_ms, side="left"))
    if i0 >= base5m.open_time.shape[0]:
        return grid, np.full(grid.shape, initial_cash), initial_cash
    entry_open = float(base5m.open[i0])
    entry_price = entry_open * (1.0 + entry_slip)
    qty = initial_cash / (entry_price * (1.0 + taker_fee))
    cost = qty * entry_price * (1.0 + taker_fee)
    leftover = initial_cash - cost
    prices = price_at_grid(base5m, grid)
    eq = leftover + qty * prices
    final = float(leftover + qty * base5m.close[-1])
    return grid, eq, final


def bh_metrics(base5m, start_ms, end_ms, initial_cash, taker_fee, entry_slip):
    grid, eq, final = buy_and_hold(base5m, start_ms, end_ms, initial_cash, taker_fee, entry_slip)
    days = (end_ms - start_ms) / DAILY_MS
    c = cagr(final, initial_cash, days)
    mdd = max_drawdown(eq) if eq.size else 0.0
    return dict(cagr=c, calmar=calmar(c, mdd), final_equity=final, daily_equity=eq, grid=grid)


def exposure_matched_final(daily_returns: np.ndarray, exposure: float, initial_cash: float) -> float:
    """Compound B&H daily returns scaled by average exposure, frictionless (spec §9.3)."""
    scaled = daily_returns * exposure
    return float(initial_cash * np.prod(1.0 + scaled))


def fraction_series(signal_close_times: np.ndarray, equity_5m: list) -> np.ndarray:
    """Position fraction (BTC value / equity) at each signal bar close (carry-forward)."""
    t5 = np.array([x[0] for x in equity_5m], dtype=np.int64)
    btc = np.array([x[2] for x in equity_5m], dtype=np.float64)
    price = np.array([x[3] for x in equity_5m], dtype=np.float64)
    eq = np.array([x[1] for x in equity_5m], dtype=np.float64)
    idx = np.searchsorted(t5, signal_close_times, side="right") - 1
    out = np.zeros(signal_close_times.shape, dtype=np.float64)
    valid = idx >= 0
    if valid.any():
        with np.errstate(divide="ignore", invalid="ignore"):
            out[valid] = np.where(eq[idx[valid]] > 0,
                                  btc[idx[valid]] * price[idx[valid]] / eq[idx[valid]], 0.0)
    return out


def reconstruct_equity(fraction: np.ndarray, returns: np.ndarray, cost_per_unit: float) -> np.ndarray:
    """Reconstruct an equity curve from a position-fraction series and price returns,
    charging cost_per_unit per unit of position change (spec §9.4)."""
    n = fraction.size
    eq = 1.0
    eqs = [1.0]
    for t in range(1, n):
        change = abs(fraction[t] - fraction[t - 1])
        eq = eq * (1.0 + fraction[t - 1] * returns[t]) - cost_per_unit * change * eq
        eqs.append(eq)
    return np.array(eqs)


def circular_shift(fraction: np.ndarray, returns: np.ndarray, cost_per_unit: float,
                   n_draws: int, seed: int, days: float):
    """≥1000 circular shifts of the position series (spec §9.4).

    Returns (final_equities, calmar_list, cagr_list) — one per draw. Annualization uses
    the same `days` (window length) as the strategy's own CAGR.
    """
    n = fraction.size
    rng = np.random.default_rng(seed)
    lo, hi = int(np.ceil(0.10 * n)), int(np.floor(0.90 * n))
    finals = np.empty(n_draws)
    calmars = np.empty(n_draws)
    cagrs = np.empty(n_draws)
    for i in range(n_draws):
        k = int(rng.integers(lo, hi + 1))
        f = np.roll(fraction, k)
        eqs = reconstruct_equity(f, returns, cost_per_unit)
        finals[i] = eqs[-1]
        c = cagr(float(eqs[-1]), 1.0, days)
        mdd = max_drawdown(eqs)
        calmars[i] = (c / mdd) if mdd > 0 else np.inf
        cagrs[i] = c
    return finals, calmars, cagrs


def percentile_rank(value: float, draws: np.ndarray) -> float:
    """Fraction of draws <= value (spec §9.4)."""
    if draws.size == 0:
        return 1.0
    return float(np.mean(draws <= value))
