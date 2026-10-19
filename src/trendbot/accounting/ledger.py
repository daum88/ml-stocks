"""Accounting ledger — cash/BTC, fills (trade table rows), equity (spec §8.1)."""
from __future__ import annotations


class Ledger:
    def __init__(self, initial_cash: float):
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.btc = 0.0
        self.fills: list[dict] = []

    def buy(self, *, time_ms, price, qty, fee, slip_cost, reason, variant,
            decision_time_ms, order_time_ms, limit_price):
        notional = price * qty
        self.cash -= notional + fee
        self.btc += qty
        self.fills.append(dict(
            time_ms=time_ms, side="BUY", price=price, qty=qty, notional=notional,
            fee=fee, slip_cost=slip_cost, reason=reason, variant=variant,
            decision_time_ms=decision_time_ms, order_time_ms=order_time_ms,
            limit_price=limit_price,
        ))

    def sell(self, *, time_ms, price, qty, fee, slip_cost, reason, variant,
             decision_time_ms, order_time_ms, limit_price=None):
        notional = price * qty
        self.cash += notional - fee
        self.btc -= qty
        self.fills.append(dict(
            time_ms=time_ms, side="SELL", price=price, qty=qty, notional=notional,
            fee=fee, slip_cost=slip_cost, reason=reason, variant=variant,
            decision_time_ms=decision_time_ms, order_time_ms=order_time_ms,
            limit_price=limit_price,
        ))

    def equity(self, mark_price: float) -> float:
        return self.cash + self.btc * mark_price
