"""Independent reference simulator cross-check (spec §11).

A deliberately simple, slow, loop-based reference for V1 (no trailing stop) is compared
against the main engine on a small synthetic dataset. Every trade must match exactly.
"""
import numpy as np
import pytest

from trendbot.strategy.strategy import Strategy
from trendbot.execution.fillsim import Backtester
from trendbot.common import timeutil
from conftest import mk_bars, prereg_delay0

D = timeutil.INTERVAL_MS["1d"]
M5 = timeutil.INTERVAL_MS["5m"]


def _sma(vals, n, i):
    if i < n - 1:
        return None
    return sum(vals[i - n + 1:i + 1]) / n


def reference_v1(daily_close, daily_t, f5m, cfg, fees):
    """Independent reference: explicit loops, no reuse of the main engine's fill code."""
    hs = cfg.costs.half_spread_pct
    hc = cfg.costs.through_haircut_pct
    slip = cfg.costs.entry_slip_pct["V1"]
    exit_slip = cfg.costs.exit_slip_pct["V1"]
    maker = fees.exchange.maker_fee_pct
    taker = fees.exchange.taker_fee_pct
    qty_step = fees.order_constraints.quantity_step_btc
    import math
    dis = cfg.strategy.disaster_stop_pct
    N = 200
    cash = cfg.evaluation.initial_cash_eur
    btc = 0.0
    trades = []
    pending = None  # (place, limit, attempt)
    pos = None      # (entry_price, disaster)

    # decision at daily index d (flat only); returns entry limit or None
    def decide_enter(d):
        s = _sma(daily_close, N, d)
        return (daily_close[d] > s) if s is not None else False

    # build 5m iterator starting at the first decision close
    start = daily_t[N - 1] + D  # decision at bar N-1 close
    j = 0
    while j < len(f5m) and f5m[j][0] < start:
        j += 1

    d = N - 1  # daily index
    while d < len(daily_close):
        T = daily_t[d] + D  # close time of daily bar d
        # process 5m bars up to T
        while j < len(f5m) and f5m[j][0] < T:
            t, o, h, l, c = f5m[j]
            if pos is not None:
                if l <= pos[1]:  # disaster stop
                    px = o if o <= pos[1] else pos[1]
                    px = px * (1 - exit_slip)
                    fee = taker * px * btc
                    cash += px * btc - fee
                    trades.append(("SELL", t, px, btc))
                    btc = 0.0
                    pos = None
            elif pending is not None:
                if t >= pending[0] and l <= pending[1] * (1 - hc):
                    px = pending[1] * (1 + slip)
                    qty = math.floor(cash / (px * (1 + maker)) / qty_step) * qty_step
                    fee = maker * px * qty
                    cash -= px * qty + fee
                    btc = qty
                    trades.append(("BUY", t, px, qty))
                    pos = (px, px * (1 - dis))
                    pending = None
            j += 1
        # resolve pending expiry / make decision at T
        if pending is not None and T >= pending[0] + D:
            if pending[2] == 1 and decide_enter(d):
                pending = (T, daily_close[d] * (1 - hs), 2)
            else:
                pending = None
        if pos is None and pending is None:
            if decide_enter(d):
                pending = (T, daily_close[d] * (1 - hs), 1)
        d += 1
    return trades


def test_reference_matches_main_engine(prereg, fees):
    cfg = prereg_delay0(prereg)
    rng = np.random.default_rng(7)
    daily_close = 100.0 + np.arange(230) * 0.6
    daily_close[215:] = 70.0
    daily_t = np.arange(230) * D

    # 5m bars: smooth oscillating price with a downward drift after day 215
    n5 = 230 * 288
    t5 = np.arange(n5) * M5
    close5 = 100.0 + (t5 // D) * 0.6
    close5[t5 // D >= 215] = 70.0
    close5 = close5 + rng.normal(0, 0.3, n5)
    open5 = np.empty(n5); open5[0] = close5[0]; open5[1:] = close5[:-1]
    high5 = np.maximum(open5, close5) + 0.4
    low5 = np.minimum(open5, close5) - 0.4

    daily = mk_bars(daily_t, daily_close, D)
    base5m = mk_bars(t5, close5, M5, high=high5, low=low5, open_=open5)
    strat = Strategy("V1", cfg.strategy, cfg, daily, daily)
    bt = Backtester(strat, base5m, cfg, fees)
    res = bt.run(start_time_ms=daily_t[199] + D, end_time_ms=daily_t[229] + D)

    ref = reference_v1(daily_close, daily_t, list(zip(t5, open5, high5, low5, close5)), cfg, fees)

    main = [(f["side"], f["time_ms"], round(f["price"], 6), round(f["qty"], 8)) for f in res.fills]
    ref2 = [(s, t, round(px, 6), round(q, 8)) for (s, t, px, q) in ref]
    assert main == ref2, f"main={main}\nref ={ref2}"
