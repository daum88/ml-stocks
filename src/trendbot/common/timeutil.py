"""Time utilities — UTC only, no wall clock, no local time.

All internal timestamps are integer **milliseconds since epoch** (UTC).
"""
from __future__ import annotations

import numpy as np

# Interval names -> milliseconds (open-time span of one bar).
INTERVAL_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}

# Canonical signal timeframes used by the three variants.
SIGNAL_INTERVALS = {"1d": INTERVAL_MS["1d"], "4h": INTERVAL_MS["4h"], "1h": INTERVAL_MS["1h"]}

# Base clock of the simulator (fills / stops are processed on 5-minute bars).
BASE_INTERVAL = "5m"
BASE_INTERVAL_MS = INTERVAL_MS["5m"]

# Timestamp unit detection by magnitude (spec §3.3): multiplier to milliseconds.
_UNIT_RANGES = [
    (1e18, 1e-6),   # nanoseconds  -> ms
    (1e15, 1e-3),   # microseconds -> ms
    (1e12, 1.0),    # milliseconds -> ms
    (1e9, 1e3),     # seconds      -> ms
]


def parse_interval(interval: str) -> int:
    """Return the interval in milliseconds, raising on an unknown name."""
    try:
        return INTERVAL_MS[interval]
    except KeyError:
        raise ValueError(f"unknown interval {interval!r}; known: {sorted(INTERVAL_MS)}") from None


def detect_ts_unit(values: np.ndarray) -> float:
    """Detect the timestamp unit of an array of values by magnitude (spec §3.3).

    Returns the multiplier that converts the values to milliseconds.
    Raises ValueError if the values are empty, non-positive, or do not match a
    single clear unit (or if a single array mixes units).
    """
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        raise ValueError("cannot detect timestamp unit of an empty array")
    if np.any(arr <= 0):
        raise ValueError("timestamps must be positive")

    def _unit_of(x: float) -> float | None:
        for threshold, mult in _UNIT_RANGES:
            if x >= threshold:
                return mult
        return None

    lo = _unit_of(float(arr.min()))
    hi = _unit_of(float(arr.max()))
    if lo is None or hi is None or lo != hi:
        raise ValueError("timestamp array mixes units or is out of range")
    return lo


def to_ms(values: np.ndarray, unit_mult: float) -> np.ndarray:
    """Convert an integer timestamp array to integer milliseconds."""
    return np.rint(values.astype(np.float64) * unit_mult).astype(np.int64)


def floor_to_interval(ts_ms: np.ndarray | int, interval_ms: int) -> np.ndarray | int:
    """Floor timestamps down to the interval boundary (bar open time)."""
    return (ts_ms // interval_ms) * interval_ms


def close_time(open_time_ms: int, interval_ms: int) -> int:
    """Bar close time = open time + interval (left-closed, left-labeled)."""
    return open_time_ms + interval_ms
