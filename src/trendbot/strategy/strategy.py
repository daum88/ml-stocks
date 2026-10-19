"""Strategy decision logic — the SINGLE implementation shared by backtest and live.

A `Strategy` precomputes its indicators once (on closed bars only) and `decide(t,
position)` is a pure function of (bar index, position state). No I/O, no clock.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from trendbot.common.config import PreRegConfig, StrategyConfig
from trendbot.indicators.indicators import sma, ema, atr, cross_up

# Decision codes.
ENTER = "ENTER"
EXIT = "EXIT"
HOLD = "HOLD"


@dataclass
class BarSeries:
    """A single (pair, interval) candle table, sorted ascending, unique open_time.

    open_time is integer milliseconds since epoch (UTC). close_time = open_time +
    interval_ms (derived, never stored). is_filled_gap marks synthetic filler rows.
    """
    open_time: np.ndarray          # int64 ms
    open: np.ndarray               # float64
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    interval_ms: int
    is_filled_gap: Optional[np.ndarray] = None

    def __post_init__(self):
        if self.is_filled_gap is None:
            self.is_filled_gap = np.zeros(self.open_time.shape, dtype=bool)

    def close_time(self) -> np.ndarray:
        return self.open_time + self.interval_ms


@dataclass
class Decision:
    decision: str                       # ENTER / EXIT / HOLD
    diagnostics: dict = field(default_factory=dict)


@dataclass
class Strategy:
    """One variant's decision engine on a fixed dataset."""
    name: str
    cfg: StrategyConfig
    prereg: PreRegConfig
    signal: BarSeries
    daily: BarSeries

    # precomputed signal-timeframe indicator arrays
    fast: np.ndarray = field(init=False)
    slow: np.ndarray = field(init=False)
    atr: np.ndarray = field(init=False)
    gate: np.ndarray = field(init=False)  # bool, aligned to signal bars
    cross: np.ndarray = field(init=False)  # bool, cross-up events (V2/V3)

    def __post_init__(self):
        v = self.cfg.variants[self.name]
        close = self.signal.close
        if v.sma is not None:
            self.slow = sma(close, v.sma)
            self.fast = close.copy()
            self.cross = np.zeros(close.shape, dtype=bool)
        else:
            self.fast = ema(close, v.ema_fast, warmup_mult=self.prereg.indicators.ema_warmup_mult)
            self.slow = ema(close, v.ema_slow, warmup_mult=self.prereg.indicators.ema_warmup_mult)
            self.cross = cross_up(self.fast, self.slow)
        self.atr = atr(self.signal.high, self.signal.low, close,
                       n=self.cfg.atr_period, warmup_bars=self.prereg.indicators.atr_warmup_bars)
        self.gate = self._compute_gate()

    def _compute_gate(self) -> np.ndarray:
        """Daily gate (daily close > SMA(200)), mapped to each signal bar by the most
        recent daily bar whose close_time <= the signal bar's close_time (spec §4 rule 3)."""
        n = self.cfg.daily_gate_sma
        dclose = self.daily.close
        dsma = sma(dclose, n)
        gate_on_daily = ~np.isnan(dsma) & (dclose > dsma)

        # For each signal close time, find the last daily bar closing at or before it.
        sig_close = self.signal.close_time()
        daily_close = self.daily.close_time()
        idx = np.searchsorted(daily_close, sig_close, side="right") - 1
        valid = idx >= 0
        out = np.zeros(sig_close.shape, dtype=bool)
        out[valid] = gate_on_daily[idx[valid]]
        return out

    def decide(self, t: int, position: str) -> Decision:
        """Pure decision at signal bar index t (0-indexed) for the given position.

        position is "flat" or "long". Returns ENTER / EXIT / HOLD + diagnostics.
        """
        v = self.cfg.variants[self.name]
        diag = {"t": t, "close": float(self.signal.close[t])}

        if v.sma is not None:
            # V1: state-based on SMA.
            sma_t = self.slow[t]
            diag["sma"] = float(sma_t) if not np.isnan(sma_t) else None
            if position == "flat":
                if not np.isnan(sma_t) and self.signal.close[t] > sma_t:
                    return Decision(ENTER, diag)
            else:  # long
                if not np.isnan(sma_t) and self.signal.close[t] < sma_t:
                    return Decision(EXIT, diag)
            return Decision(HOLD, diag)

        # V2/V3: event-based entry, state-based exit.
        f, s = self.fast[t], self.slow[t]
        diag["ema_fast"] = float(f) if not np.isnan(f) else None
        diag["ema_slow"] = float(s) if not np.isnan(s) else None
        diag["gate"] = bool(self.gate[t])

        if position == "flat":
            if self.cross[t] and self.gate[t]:
                return Decision(ENTER, diag)
        else:  # long
            if not np.isnan(f) and not np.isnan(s) and f < s:
                return Decision(EXIT, diag)
        return Decision(HOLD, diag)

    def reprice_ok(self, t: int) -> bool:
        """Re-price condition at signal bar t (spec §7.1): the entry condition is still
        true at that close — but WITHOUT requiring the cross event (V2/V3 just need
        fast > slow and the gate on)."""
        v = self.cfg.variants[self.name]
        if v.sma is not None:
            s = self.slow[t]
            return (not np.isnan(s)) and self.signal.close[t] > s
        f, s = self.fast[t], self.slow[t]
        return (not np.isnan(f)) and (not np.isnan(s)) and f > s and bool(self.gate[t])

    def trailing_candidate(self, t: int) -> float:
        """Trailing stop candidate at signal close t: close - trailing_mult * ATR."""
        mult = self.cfg.variants[self.name].trailing_atr_mult
        if mult is None:
            return -np.inf
        a = self.atr[t]
        if np.isnan(a):
            return -np.inf
        return self.signal.close[t] - mult * a

    def first_valid_index(self) -> int:
        """Earliest signal bar index where every indicator of this variant is valid."""
        v = self.cfg.variants[self.name]
        if v.sma is not None:
            return v.sma - 1
        return self.prereg.indicators.ema_warmup_mult * v.ema_slow
