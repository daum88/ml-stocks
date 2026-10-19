"""Signal runner — idempotent once-per-candle processing + staleness rule (spec §12.4–12.5).

It calls the SAME decision code as the backtester (a `Strategy` built from the fetched
candles). It never assumes an order filled; position changes only via human confirm.
"""
from __future__ import annotations

from dataclasses import dataclass

from trendbot.strategy.strategy import ENTER, EXIT, HOLD
from trendbot.live.state import State


@dataclass
class Alert:
    kind: str          # ENTER / EXIT / STALE-EXIT / MISSED-ENTRY / HEARTBEAT / ...
    bar_close_ms: int
    message: str


class SignalRunner:
    def __init__(self, variant_name: str, interval_ms: int, staleness_mult: float = 2.0,
                 staleness_atr_mult: float = 1.0):
        self.variant_name = variant_name
        self.interval_ms = interval_ms
        self.staleness_mult = staleness_mult
        self.staleness_atr_mult = staleness_atr_mult

    def is_stale(self, bar_close_ms: int, signal_close: float, current_price: float,
                 atr: float, now_ms: int) -> bool:
        """Stale if the bar closed > 2×interval ago OR price moved > 1×ATR since (spec §12.5)."""
        if now_ms - bar_close_ms > self.staleness_mult * self.interval_ms:
            return True
        if atr > 0 and abs(current_price - signal_close) > self.staleness_atr_mult * atr:
            return True
        return False

    def process(self, state: State, bar_close_ms: int, decision: str, signal_close: float,
                current_price: float, atr: float, now_ms: int) -> list[Alert]:
        """Process one closed bar exactly once (idempotent). Returns alerts to send."""
        if state.last_processed_close_ms is not None and bar_close_ms <= state.last_processed_close_ms:
            return []

        state.last_processed_close_ms = bar_close_ms
        alerts: list[Alert] = []

        if decision == HOLD:
            return alerts

        stale = self.is_stale(bar_close_ms, signal_close, current_price, atr, now_ms)

        if decision == ENTER and state.position == "flat":
            if stale:
                alerts.append(Alert("MISSED-ENTRY", bar_close_ms, "stale entry suppressed"))
            else:
                alerts.append(Alert("ENTER", bar_close_ms, "enter (place post-only limit)"))
        elif decision == EXIT and state.position == "long":
            # Stale exits are NEVER suppressed (spec §12.5 — stricter than the plan).
            if stale:
                alerts.append(Alert("STALE-EXIT", bar_close_ms, "STALE EXIT — check position now"))
            else:
                alerts.append(Alert("EXIT", bar_close_ms, "exit (market)"))

        return alerts
