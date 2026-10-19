#!/usr/bin/env python
"""Phase 2 live-signal tool — once-per-candle: fetch, decide, alert (no orders).

Usage:
  python scripts/run_signal.py --variant V1 --market BTC-EUR [--chat-id CHAT_ID] [--state state.json]

The token is read from the TELEGRAM_BOT_TOKEN environment variable (never logged).
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from trendbot.common.config import load_prereg  # noqa: E402
from trendbot.common import timeutil  # noqa: E402
from trendbot.strategy.strategy import Strategy, BarSeries  # noqa: E402
from trendbot.live import bitvavo, telegram  # noqa: E402
from trendbot.live.state import State, load_state, save_state  # noqa: E402
from trendbot.live.signal import SignalRunner, Alert  # noqa: E402

INTERVAL = {"V1": "1d", "V2": "4h", "V3": "1h"}


def build_strategy(variant: str, prereg, market: str) -> tuple[Strategy, int, int, float]:
    tf = INTERVAL[variant]
    daily_candles = bitvavo.fetch_candles(market, "1d", limit=400)
    sig_candles = bitvavo.fetch_candles(market, tf, limit=1000)
    iv_ms = timeutil.INTERVAL_MS[tf]

    def to_bars(candles, interval_ms):
        c = np.array(candles, dtype=np.float64)
        # drop candles whose close time is in the future (incomplete bar, spec §12.2)
        now = bitvavo.fetch_time()
        open_time = c[:, 0].astype(np.int64)
        keep = open_time + interval_ms <= now
        return BarSeries(open_time=open_time[keep], open=c[keep, 1], high=c[keep, 2],
                         low=c[keep, 3], close=c[keep, 4], volume=c[keep, 5],
                         interval_ms=interval_ms)

    daily = to_bars(daily_candles, timeutil.INTERVAL_MS["1d"])
    sig = to_bars(sig_candles, iv_ms)
    strat = Strategy(variant, prereg.strategy, prereg, sig, daily)
    return strat, iv_ms, sig.open_time[-1] + iv_ms, float(sig.atr[-1])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="V1", choices=["V1", "V2", "V3"])
    ap.add_argument("--market", default="BTC-EUR")
    ap.add_argument("--chat-id", default=None)
    ap.add_argument("--state", default=str(ROOT / "data" / "signal_state.json"))
    ap.add_argument("--dry-run", action="store_true", help="no Telegram, just print")
    args = ap.parse_args()

    prereg = load_prereg(ROOT / "config" / "prereg.yaml")
    state = load_state(pathlib.Path(args.state))

    strat, iv_ms, bar_close_ms, atr = build_strategy(args.variant, prereg, args.market)
    t = len(strat.signal.close) - 1
    decision = strat.decide(t, state.position).decision
    close = float(strat.signal.close[t])
    current = close  # use last close as current price proxy (ticker would be better)

    runner = SignalRunner(args.variant, iv_ms)
    now = bitvavo.fetch_time()
    alerts = runner.process(state, bar_close_ms, decision, close, current, atr, now)

    # daily heartbeat (sent once per UTC day)
    from datetime import datetime, timezone
    today = datetime.fromtimestamp(now / 1000, timezone.utc).date().isoformat()
    if state.last_alert_time_ms is None or today != datetime.fromtimestamp(
            state.last_alert_time_ms / 1000, timezone.utc).date().isoformat():
        alerts.append(Alert("HEARTBEAT", bar_close_ms,
                            f"heartbeat: last bar {bar_close_ms}, position {state.position}"))

    for a in alerts:
        msg = f"[{args.variant}] {a.kind}: {a.message}"
        print(msg, flush=True)
        if not args.dry_run:
            if args.chat_id is None:
                print("  (no --chat-id; skipping send)", flush=True)
            else:
                telegram.send_message(args.chat_id, msg)
        state.last_alert = a.kind
        state.last_alert_time_ms = now

    save_state(pathlib.Path(args.state), state)
    print(f"state saved: processed={state.last_processed_close_ms}, position={state.position}")


if __name__ == "__main__":
    main()
