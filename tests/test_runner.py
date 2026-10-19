"""End-to-end integration test: synthetic data through the full runner (spec §11)."""
import pathlib

import numpy as np
import pytest

from trendbot.common import timeutil
from trendbot.data import store
from trendbot.strategy.strategy import BarSeries
from trendbot.report import runner

D = timeutil.INTERVAL_MS["1d"]
H4 = timeutil.INTERVAL_MS["4h"]
H1 = timeutil.INTERVAL_MS["1h"]
M5 = timeutil.INTERVAL_MS["5m"]


def _gen(interval_ms, n, seed, drift=0.0005, vol=0.01):
    """Geometric random walk with drift; aligned open_times from epoch 0."""
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, n)
    close = 100.0 * np.exp(np.cumsum(rets))
    open_ = np.empty(n); high = np.empty(n); low = np.empty(n)
    open_[0] = close[0]
    for i in range(1, n):
        open_[i] = close[i - 1]
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.002, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.002, n))
    return BarSeries(
        open_time=np.arange(n, dtype=np.int64) * interval_ms,
        open=open_, high=high, low=low, close=close,
        volume=np.ones(n), interval_ms=interval_ms,
    )


def _write_synthetic(tmp_path):
    n5m = 260 * 288
    bars = {
        "1d": _gen(D, 260, 1),
        "4h": _gen(H4, 260 * 6, 2),
        "1h": _gen(H1, 260 * 24, 3),
        "5m": _gen(M5, n5m, 4),
    }
    for iv, b in bars.items():
        store.write_parquet(b, tmp_path / f"XBTEUR_{iv}.parquet")
    store.write_parquet(bars["5m"], tmp_path / "XBTEUR_5m_filled.parquet")
    return bars


def test_runner_end_to_end(prereg, fees, tmp_path):
    _write_synthetic(tmp_path)
    result = runner.evaluate("XBTEUR", tmp_path, prereg, fees)
    assert set(result["outcomes"].keys()) == {"V1", "V2", "V3"}
    for name, (tier, criteria) in result["outcomes"].items():
        assert tier in ("A", "B", "C")
        assert set(criteria.keys()) == {"C1", "C2", "C3", "C4", "C5", "C6"}
    assert isinstance(result["selection"], str)
    assert result["window_days"] > 0
    assert result["bh"]["final_equity"] > 0
