#!/usr/bin/env python
"""Phase 2 confirm-fill — human updates position state explicitly (spec §12.3).

The tool never assumes an order filled. Position changes only via this command.

Usage:
  python scripts/confirm_fill.py entry --price 100.0 --amount 0.001
  python scripts/confirm_fill.py exit
  python scripts/confirm_fill.py none
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trendbot.live.state import load_state, save_state  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["entry", "exit", "none"])
    ap.add_argument("--price", type=float)
    ap.add_argument("--amount", type=float)
    ap.add_argument("--state", default=str(ROOT / "data" / "signal_state.json"))
    args = ap.parse_args()

    state = load_state(pathlib.Path(args.state))
    now = int(time.time() * 1000)
    if args.action == "entry":
        if args.price is None or args.amount is None:
            print("entry requires --price and --amount", file=sys.stderr)
            sys.exit(1)
        state.position = "long"
        state.entry_price = args.price
        state.entry_amount = args.amount
        state.entry_time_ms = now
        state.pending_order_note = None
    elif args.action == "exit":
        state.position = "flat"
        state.entry_price = None
        state.entry_amount = None
        state.entry_time_ms = None
    else:  # none
        state.pending_order_note = "none"
    save_state(pathlib.Path(args.state), state)
    print(f"state: position={state.position}, entry_price={state.entry_price}")


if __name__ == "__main__":
    main()
