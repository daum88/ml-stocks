"""Shared test helpers."""
import pathlib

import numpy as np
import pytest

from trendbot.common.config import load_prereg, load_fees
from trendbot.strategy.strategy import BarSeries

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def prereg():
    return load_prereg(ROOT / "config" / "prereg.yaml")


@pytest.fixture(scope="session")
def fees():
    return load_fees(ROOT / "config" / "fees.yaml")


def prereg_delay0(prereg):
    """Copy of prereg with all action delays set to 0 (simplifies execution tests)."""
    cfg = prereg.model_copy(deep=True)
    cfg.execution.action_delay_minutes = {"V1": 0, "V2": 0, "V3": 0}
    return cfg


def mk_bars(open_times_ms, close, interval_ms, high=None, low=None, volume=None):
    """Build a BarSeries from open times and closes (O/H/L/C defaults to close)."""
    close = np.asarray(close, dtype=np.float64)
    high = np.asarray(high, dtype=np.float64) if high is not None else close.copy()
    low = np.asarray(low, dtype=np.float64) if low is not None else close.copy()
    vol = np.asarray(volume, dtype=np.float64) if volume is not None else np.ones(close.shape)
    return BarSeries(
        open_time=np.asarray(open_times_ms, dtype=np.int64),
        open=close.copy(),
        high=high,
        low=low,
        close=close,
        volume=vol,
        interval_ms=interval_ms,
    )


def run_decisions(strat, position="flat", start=None, stop=None):
    """Simulate flat->enter->long->exit->flat, returning [(t, decision), ...]."""
    events = []
    for t in range(start or 0, stop if stop is not None else strat.signal.close.shape[0]):
        d = strat.decide(t, position)
        if d.decision == "ENTER":
            events.append((t, "ENTER"))
            position = "long"
        elif d.decision == "EXIT":
            events.append((t, "EXIT"))
            position = "flat"
    return events
