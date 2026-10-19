#!/usr/bin/env python
"""Generate a synthetic pair dataset (for M7 dry-run; no real data, no network)."""
from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trendbot.common import timeutil  # noqa: E402
from trendbot.data import store  # noqa: E402
from trendbot.strategy.strategy import BarSeries  # noqa: E402

D = timeutil.INTERVAL_MS["1d"]
H4 = timeutil.INTERVAL_MS["4h"]
H1 = timeutil.INTERVAL_MS["1h"]
M5 = timeutil.INTERVAL_MS["5m"]


YEAR_MS = 365.25 * 86_400_000


def gen(interval_ms, n, seed, annual_drift=0.08, annual_vol=0.60):
    """Geometric random walk with annualized drift/vol scaled to the bar interval."""
    rng = np.random.default_rng(seed)
    dt = interval_ms / YEAR_MS
    mu = annual_drift * dt
    sigma = annual_vol * np.sqrt(dt)
    log_rets = rng.normal(mu - 0.5 * sigma ** 2, sigma, n)
    close = 100.0 * np.exp(np.cumsum(log_rets))
    open_ = np.empty(n)
    open_[0] = close[0]
    open_[1:] = close[:-1]
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.002, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.002, n))
    return BarSeries(open_time=np.arange(n, dtype=np.int64) * interval_ms,
                     open=open_, high=high, low=low, close=close,
                     volume=np.ones(n), interval_ms=interval_ms)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", default="XETHZEUR")
    ap.add_argument("--days", type=int, default=260)
    ap.add_argument("--out", default=str(ROOT / "data" / "parquet"))
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    bars = {
        "1d": gen(D, args.days, 1),
        "4h": gen(H4, args.days * 6, 2),
        "1h": gen(H1, args.days * 24, 3),
        "5m": gen(M5, args.days * 288, 4),
    }
    for iv, b in bars.items():
        store.write_parquet(b, out / f"{args.pair}_{iv}.parquet")
    store.write_parquet(bars["5m"], out / f"{args.pair}_5m_filled.parquet")
    print(f"wrote synthetic {args.pair} data to {out}")


if __name__ == "__main__":
    main()
