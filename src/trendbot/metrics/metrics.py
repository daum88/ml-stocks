"""Metrics — exact definitions per spec §8.3."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

DAILY_MS = 86_400_000


@dataclass
class Metrics:
    cagr: float = 0.0
    max_drawdown_daily: float = 0.0
    max_drawdown_5m: float = 0.0
    calmar: float | None = None
    exposure: float = 0.0
    round_trips: int = 0
    missed_trades: int = 0
    skipped_min_size: int = 0
    avg_hold_days: float = 0.0
    win_rate: float = 0.0
    profit_factor: float | None = None
    avg_win: float = 0.0
    avg_loss: float = 0.0
    trades_per_year: float = 0.0
    fee_drag_annualized: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    final_equity: float = 0.0
    total_fees: float = 0.0
    total_slippage: float = 0.0
    total_pnl: float = 0.0


def cagr(final: float, initial: float, days: float) -> float:
    if initial <= 0 or days <= 0:
        return 0.0
    if final < 0:
        return -1.0
    return (final / initial) ** (365.25 / days) - 1.0


def max_drawdown(equities: np.ndarray) -> float:
    """Largest peak-to-trough fall as a positive fraction."""
    if equities.size == 0:
        return 0.0
    peak = np.maximum.accumulate(equities)
    dd = (peak - equities) / peak
    return float(dd.max())


def calmar(cagr_val: float, mdd: float) -> float | None:
    if mdd <= 0:
        return None
    return cagr_val / mdd


def daily_grid(start_ms: int, end_ms: int) -> np.ndarray:
    """Daily UTC closes (midnights) from the first >= start_ms to the last <= end_ms."""
    first = ((start_ms + DAILY_MS - 1) // DAILY_MS) * DAILY_MS
    last = (end_ms // DAILY_MS) * DAILY_MS
    if last < first:
        return np.array([], dtype=np.int64)
    return np.arange(first, last + DAILY_MS, DAILY_MS, dtype=np.int64)


def resample_daily(times: np.ndarray, values: np.ndarray, grid: np.ndarray,
                   initial: float) -> np.ndarray:
    """Carry-forward resample a 5m series onto daily grid points (last sample <= grid)."""
    out = np.full(grid.shape, initial, dtype=np.float64)
    idx = np.searchsorted(times, grid, side="right") - 1
    valid = idx >= 0
    out[valid] = values[idx[valid]]
    return out


def round_trips(fills: list[dict]) -> list[dict]:
    """Pair BUY/SELL fills into round trips. Unclosed position is ignored here."""
    trips = []
    open_buy = None
    for f in fills:
        if f["side"] == "BUY":
            open_buy = f
        elif f["side"] == "SELL" and open_buy is not None:
            buy = open_buy
            pnl = (f["price"] * f["qty"] - f["fee"]) - (buy["price"] * buy["qty"] + buy["fee"])
            trips.append(dict(
                entry_time=buy["time_ms"], exit_time=f["time_ms"],
                pnl=pnl, entry_price=buy["price"], exit_price=f["price"], qty=f["qty"],
            ))
            open_buy = None
    return trips


def compute_metrics(*, res, initial_cash: float, start_ms: int, end_ms: int,
                    window_days: float) -> Metrics:
    """Compute the full metric set from a BacktestResult."""
    m = Metrics()
    m.final_equity = res.final_equity
    m.missed_trades = res.missed_trades
    m.skipped_min_size = res.skipped_min_size

    fills = res.fills
    m.total_fees = float(sum(f["fee"] for f in fills))
    m.total_slippage = float(sum(f["slip_cost"] for f in fills))
    buy_cost = sum(f["price"] * f["qty"] + f["fee"] for f in fills if f["side"] == "BUY")
    sell_proc = sum(f["price"] * f["qty"] - f["fee"] for f in fills if f["side"] == "SELL")
    m.total_pnl = sell_proc - buy_cost

    # --- equity curves ---
    eq5m = res.equity_5m
    if eq5m:
        t5 = np.array([x[0] for x in eq5m], dtype=np.int64)
        e5 = np.array([x[1] for x in eq5m], dtype=np.float64)
        m.max_drawdown_5m = max_drawdown(e5)
        grid = daily_grid(start_ms, end_ms)
        deq = resample_daily(t5, e5, grid, initial_cash)
        if deq.size:
            m.max_drawdown_daily = max_drawdown(deq)
    else:
        m.max_drawdown_daily = 0.0

    m.cagr = cagr(res.final_equity, initial_cash, window_days)
    m.calmar = calmar(m.cagr, m.max_drawdown_daily)

    # --- exposure (time-weighted BTC value / equity over daily closes) ---
    if eq5m:
        t5 = np.array([x[0] for x in eq5m], dtype=np.int64)
        btc = np.array([x[2] for x in eq5m], dtype=np.float64)
        price = np.array([x[3] for x in eq5m], dtype=np.float64)
        grid = daily_grid(start_ms, end_ms)
        idx = np.searchsorted(t5, grid, side="right") - 1
        valid = idx >= 0
        if valid.any():
            b = btc[idx[valid]]; p = price[idx[valid]]; e = e5[idx[valid]]
            with np.errstate(divide="ignore", invalid="ignore"):
                ex = np.where(e > 0, b * p / e, 0.0)
            m.exposure = float(np.mean(ex))
            # Sharpe / Sortino from daily equity returns
            if deq.size >= 2:
                rets = np.diff(deq) / deq[:-1]
                if rets.size >= 2:
                    std = rets.std(ddof=1)
                    m.sharpe = float(rets.mean() / std * np.sqrt(365.25)) if std > 0 else 0.0
                downside = rets[rets < 0]
                if downside.size >= 2:
                    dstd = downside.std(ddof=1)
                    m.sortino = float(rets.mean() / dstd * np.sqrt(365.25)) if dstd > 0 else 0.0

    # --- round trips ---
    trips = round_trips(fills)
    m.round_trips = len(trips)
    if trips:
        pnls = np.array([t["pnl"] for t in trips])
        holds = np.array([(t["exit_time"] - t["entry_time"]) / DAILY_MS for t in trips])
        m.avg_hold_days = float(holds.mean())
        wins = pnls[pnls > 0]
        losses = pnls[pnls <= 0]
        m.win_rate = float(len(wins) / len(pnls))
        m.avg_win = float(wins.mean()) if wins.size else 0.0
        m.avg_loss = float(losses.mean()) if losses.size else 0.0
        m.profit_factor = float(wins.sum() / abs(losses.sum())) if losses.size and losses.sum() != 0 else None
        years = window_days / 365.25
        m.trades_per_year = float(len(trips) / years) if years > 0 else 0.0

    # --- fee drag (total fees + slippage / avg equity, annualized) ---
    if eq5m:
        avg_eq = float(e5.mean())
        if avg_eq > 0 and window_days > 0:
            m.fee_drag_annualized = float((m.total_fees + m.total_slippage) / avg_eq / (window_days / 365.25))

    return m
