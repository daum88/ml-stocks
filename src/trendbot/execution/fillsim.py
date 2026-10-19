"""Fill simulator + accounting engine (implements decision D8, spec §7).

The base clock is 5-minute bars. Decisions happen at signal-bar closes; orders,
fills and stops are processed on every 5-minute bar (spec §4 rule 4).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from trendbot.accounting.ledger import Ledger
from trendbot.common.config import PreRegConfig, FeesConfig
from trendbot.strategy.strategy import Strategy, BarSeries, ENTER, EXIT


@dataclass
class _Order:
    place_time: int      # ms, when the limit order is placed
    expiry: int          # ms, end of the current attempt window
    limit: float         # limit price
    attempt: int         # 1 or 2
    atr: float           # ATR at the decision bar (for stop sizing)
    decision_time: int   # ms, the signal close that produced the entry decision


@dataclass
class BacktestResult:
    variant: str
    fills: list = field(default_factory=list)
    equity_5m: list = field(default_factory=list)   # [(close_time_ms, equity, btc_qty, mark_price), ...]
    missed_trades: int = 0
    skipped_min_size: int = 0
    signal_expired: int = 0
    repriced: int = 0
    final_position: str = "flat"
    final_equity: float = 0.0
    final_mark_price: float = 0.0


class Backtester:
    def __init__(self, strategy: Strategy, base5m: BarSeries, prereg: PreRegConfig,
                 fees: FeesConfig):
        self.strategy = strategy
        self.base5m = base5m
        self.prereg = prereg
        self.fees = fees

        self.maker = fees.exchange.maker_fee_pct
        self.taker = fees.exchange.taker_fee_pct
        self.qty_step = fees.order_constraints.quantity_step_btc
        self.min_order_quote = fees.order_constraints.min_order_quote_eur
        self.min_order_base = fees.order_constraints.min_order_base_btc

        c = prereg.costs
        self.half_spread = c.half_spread_pct
        self.haircut = c.through_haircut_pct
        self.entry_slip = c.entry_slip_pct[strategy.name]
        self.exit_slip = c.exit_slip_pct[strategy.name]

        v = strategy.cfg.variants[strategy.name]
        self.trailing_mult = v.trailing_atr_mult
        self.disaster_pct = prereg.strategy.disaster_stop_pct
        self.delay_ms = prereg.execution.action_delay_minutes[strategy.name] * 60_000
        self.risk = prereg.sizing.V2V3_risk_pct
        self.is_v1 = v.sma is not None
        self.sig_interval = strategy.signal.interval_ms

    # ------------------------------------------------------------------ #
    def run(self, start_time_ms: int, end_time_ms: int) -> BacktestResult:
        strat = self.strategy
        sig_close = strat.signal.close_time()
        b5 = self.base5m
        res = BacktestResult(variant=strat.name)

        ledger = Ledger(self.prereg.evaluation.initial_cash_eur)
        position = "flat"
        pending: _Order | None = None
        pending_exit_time: int | None = None
        trailing: float | None = None
        disaster: float | None = None

        # First signal bar with close >= start_time.
        j0 = int(np.searchsorted(sig_close, start_time_ms, side="left"))
        if j0 >= sig_close.shape[0]:
            res.final_equity = ledger.equity(self._last_close())
            return res
        # First 5m bar with open_time >= the first decision close.
        i5m = int(np.searchsorted(b5.open_time, sig_close[j0], side="left"))

        def _process_bar(i: int) -> None:
            nonlocal position, pending, pending_exit_time, trailing, disaster
            o = b5.open_time[i]
            bar = (b5.high[i], b5.low[i], b5.open[i], b5.close[i], bool(b5.is_filled_gap[i]))

            if position == "long":
                eff = max(trailing, disaster) if trailing is not None else disaster
                # Stop first (spec §4 rule 5).
                if not bar[4] and bar[1] <= eff:
                    if bar[2] <= eff:                     # gap open at/below stop
                        base_price = bar[2]
                    else:
                        base_price = eff
                    fill_price = base_price * (1.0 - self.exit_slip)
                    qty = ledger.btc
                    fee = self.taker * fill_price * qty
                    slip = (base_price - fill_price) * qty
                    reason = "trailing_stop" if (trailing is not None and trailing >= disaster) else "disaster_stop"
                    ledger.sell(time_ms=o, price=fill_price, qty=qty, fee=fee,
                                slip_cost=slip, reason=reason, variant=strat.name,
                                decision_time_ms=o, order_time_ms=o, limit_price=eff)
                    position = "flat"; trailing = None; disaster = None
                    pending_exit_time = None
                    return
                # Market signal exit, executed at the first 5m bar at/after the scheduled time.
                if pending_exit_time is not None and o >= pending_exit_time:
                    fill_price = bar[2] * (1.0 - self.exit_slip)
                    qty = ledger.btc
                    fee = self.taker * fill_price * qty
                    slip = (bar[2] - fill_price) * qty
                    ledger.sell(time_ms=o, price=fill_price, qty=qty, fee=fee,
                                slip_cost=slip, reason="signal", variant=strat.name,
                                decision_time_ms=pending_exit_time, order_time_ms=o)
                    position = "flat"; trailing = None; disaster = None
                    pending_exit_time = None
                    return
            else:  # flat
                if pending is not None and o >= pending.place_time and o < pending.expiry:
                    if not bar[4] and bar[1] <= pending.limit * (1.0 - self.haircut):
                        fill_price = pending.limit * (1.0 + self.entry_slip)
                        qty = self._size_entry(ledger, fill_price, pending.atr)
                        if qty is not None and qty > 0:
                            fee = self.maker * fill_price * qty
                            slip = (fill_price - pending.limit) * qty
                            ledger.buy(time_ms=o, price=fill_price, qty=qty, fee=fee,
                                       slip_cost=slip, reason="signal", variant=strat.name,
                                       decision_time_ms=pending.decision_time,
                                       order_time_ms=pending.place_time, limit_price=pending.limit)
                            disaster = fill_price * (1.0 - self.disaster_pct)
                            if self.trailing_mult is not None and pending.atr > 0:
                                trailing = fill_price - self.trailing_mult * pending.atr
                            else:
                                trailing = None
                            position = "long"
                            pending = None
                        else:
                            res.skipped_min_size += 1
                            pending = None
            # equity sample at this 5m bar close
            res.equity_5m.append((o + self.base5m.interval_ms, ledger.equity(bar[3]), ledger.btc, bar[3]))

        # --- main loop over signal bars (decision times) ---
        n_sig = sig_close.shape[0]
        n5 = b5.open_time.shape[0]
        for j in range(j0, n_sig):
            T = sig_close[j]
            if T > end_time_ms:
                break
            # advance 5m bars up to (exclusive) this decision close
            while i5m < n5 and b5.open_time[i5m] < T:
                _process_bar(i5m)
                i5m += 1
            # resolve pending entry expiry at this signal close
            if pending is not None and pending.expiry <= T:
                pending = self._resolve_order(j, pending, res)
            # trailing update + decision
            if position == "long":
                if self.trailing_mult is not None:
                    cand = strat.trailing_candidate(j)
                    if cand > -np.inf:
                        trailing = max(trailing, cand)
                d = strat.decide(j, "long")
                if d.decision == EXIT:
                    pending_exit_time = T + self.delay_ms
            else:
                if pending is None:
                    d = strat.decide(j, "flat")
                    if d.decision == ENTER:
                        place = T + self.delay_ms
                        limit = strat.signal.close[j] * (1.0 - self.half_spread)
                        pending = _Order(place_time=place, expiry=place + self.sig_interval,
                                         limit=limit, attempt=1,
                                         atr=float(strat.atr[j]) if not np.isnan(strat.atr[j]) else 0.0,
                                         decision_time=T)

        # process remaining 5m bars up to end_time (open position / pending order)
        while i5m < n5 and b5.open_time[i5m] < end_time_ms:
            _process_bar(i5m)
            i5m += 1

        # mark-to-market final position with no exit cost (spec §8.2)
        mark = self._last_close()
        res.final_equity = ledger.equity(mark)
        res.final_position = position
        res.final_mark_price = mark
        res.fills = ledger.fills
        return res

    # ------------------------------------------------------------------ #
    def _resolve_order(self, j: int, pending: _Order, res: BacktestResult) -> _Order | None:
        strat = self.strategy
        # Evaluate the re-price condition at the most recent signal bar whose close
        # is <= the order's expiry (spec §7.1).
        sig_close = strat.signal.close_time()
        j_cond = int(np.searchsorted(sig_close, pending.expiry, side="right")) - 1
        if j_cond < 0:
            j_cond = j
        if pending.attempt == 1 and self.prereg.execution.entry_attempts >= 2:
            if strat.reprice_ok(j_cond):
                place = pending.expiry
                limit = strat.signal.close[j_cond] * (1.0 - self.half_spread)
                res.repriced += 1
                return _Order(place_time=place, expiry=place + self.sig_interval,
                              limit=limit, attempt=2, atr=pending.atr,
                              decision_time=pending.decision_time)
            res.signal_expired += 1
            return None
        res.missed_trades += 1
        return None

    def _size_entry(self, ledger: Ledger, fill_price: float, atr: float) -> float | None:
        if self.is_v1:
            # V1: invest 100% of available cash after reserving the entry fee.
            if fill_price <= 0:
                return None
            budget = ledger.cash / (fill_price * (1.0 + self.maker))
        else:
            # V2/V3: stake = equity * risk / stop_distance_fraction.
            if atr <= 0:
                return None
            equity = ledger.equity(fill_price)
            stake = equity * self.risk * fill_price / (self.trailing_mult * atr)
            if stake > equity * self.prereg.sizing.cap_pct_of_equity:
                stake = equity * self.prereg.sizing.cap_pct_of_equity
            budget = stake / fill_price
        qty = np.floor(budget / self.qty_step) * self.qty_step
        if qty <= 0:
            return None
        # affordability + minimum order
        notional = qty * fill_price
        if notional < self.min_order_quote and qty < self.min_order_base:
            return None
        # never exceed cash (fees reserved)
        while qty > 0 and qty * fill_price * (1.0 + self.maker) > ledger.cash + 1e-12:
            qty -= self.qty_step
        if qty <= 0 or qty * fill_price < self.min_order_quote:
            return None
        return float(qty)

    def _last_close(self) -> float:
        if self.base5m.close.shape[0] == 0:
            return self.strategy.signal.close[-1]
        return float(self.base5m.close[-1])
