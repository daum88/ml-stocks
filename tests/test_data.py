"""Data-layer tests on synthetic CSVs (no network)."""
import numpy as np
import pandas as pd
import pytest

from trendbot.common import timeutil
from trendbot.data import kraken, gaps, validate, store
from trendbot.strategy.strategy import BarSeries

M5 = timeutil.INTERVAL_MS["5m"]


def _write_csv(path, rows):
    with open(path, "w") as f:
        for r in rows:
            f.write(",".join(str(x) for x in r) + "\n")


def test_parse_kraken_csv_seconds_to_ms(tmp_path):
    p = tmp_path / "XBTEUR_5.csv"
    _write_csv(p, [
        (1700000000, 100.0, 101.0, 99.0, 100.5, 1.5, 20),
        (1700000300, 100.5, 102.0, 100.0, 101.5, 2.0, 25),
    ])
    bar = kraken.parse_kraken_csv(p, M5)
    assert bar.open_time[0] == 1700000000 * 1000
    assert bar.open_time[1] == 1700000300 * 1000
    assert bar.close[1] == 101.5


def test_parse_kraken_csv_rejects_mixed_units(tmp_path):
    p = tmp_path / "bad.csv"
    _write_csv(p, [
        (1700000000, 100.0, 101.0, 99.0, 100.5, 1.5, 20),
        (1700000000000, 100.5, 102.0, 100.0, 101.5, 2.0, 25),
    ])
    with pytest.raises(ValueError):
        kraken.parse_kraken_csv(p, M5)


def test_normalize_sorts_and_drops_exact_dups():
    bar = BarSeries(
        open_time=np.array([300000, 100000, 200000, 100000], dtype=np.int64),
        open=np.array([3.0, 1.0, 2.0, 1.0]),
        high=np.array([4.0, 2.0, 3.0, 2.0]),
        low=np.array([2.0, 0.5, 1.0, 0.5]),
        close=np.array([3.5, 1.5, 2.5, 1.5]),
        volume=np.array([1.0, 1.0, 1.0, 1.0]),
        interval_ms=M5,
    )
    out = kraken.normalize(bar)
    assert out.open_time.tolist() == [100000, 200000, 300000]
    assert out.close.tolist() == [1.5, 2.5, 3.5]


def test_normalize_fails_on_conflicting_dups():
    bar = BarSeries(
        open_time=np.array([100000, 100000], dtype=np.int64),
        open=np.array([1.0, 2.0]),
        high=np.array([2.0, 3.0]),
        low=np.array([0.5, 1.0]),
        close=np.array([1.5, 2.5]),
        volume=np.array([1.0, 1.0]),
        interval_ms=M5,
    )
    with pytest.raises(ValueError):
        kraken.normalize(bar)


def test_fill_gaps_inserts_filler_rows():
    bar = BarSeries(
        open_time=np.array([0, M5 * 3], dtype=np.int64),
        open=np.array([10.0, 12.0]),
        high=np.array([11.0, 13.0]),
        low=np.array([9.0, 11.0]),
        close=np.array([10.5, 12.5]),
        volume=np.array([1.0, 1.0]),
        interval_ms=M5,
    )
    out = gaps.fill_gaps(bar)
    assert out.open_time.tolist() == [0, M5, M5 * 2, M5 * 3]
    assert out.is_filled_gap.tolist() == [False, True, True, False]
    # filler rows carry previous close, zero volume
    assert out.close[1] == 10.5 and out.close[2] == 10.5
    assert out.volume[1] == 0.0


def test_structural_checks_pass_and_fail():
    good = BarSeries(
        open_time=np.array([0, M5, M5 * 2], dtype=np.int64),
        open=np.array([10.0, 11.0, 12.0]),
        high=np.array([11.0, 12.0, 13.0]),
        low=np.array([9.0, 10.0, 11.0]),
        close=np.array([10.5, 11.5, 12.5]),
        volume=np.array([1.0, 1.0, 1.0]),
        interval_ms=M5,
    )
    validate.structural_checks(good)  # no raise

    bad = BarSeries(
        open_time=np.array([0, M5, M5 * 2], dtype=np.int64),
        open=np.array([10.0, 11.0, 12.0]),
        high=np.array([9.0, 12.0, 13.0]),  # high < open at bar 0
        low=np.array([9.0, 10.0, 11.0]),
        close=np.array([10.5, 11.5, 12.5]),
        volume=np.array([1.0, 1.0, 1.0]),
        interval_ms=M5,
    )
    with pytest.raises(validate.StructuralError):
        validate.structural_checks(bad)


def test_parquet_roundtrip(tmp_path):
    bar = BarSeries(
        open_time=np.array([0, M5], dtype=np.int64),
        open=np.array([10.0, 11.0]),
        high=np.array([11.0, 12.0]),
        low=np.array([9.0, 10.0]),
        close=np.array([10.5, 11.5]),
        volume=np.array([1.0, 1.0]),
        interval_ms=M5,
        is_filled_gap=np.array([False, False]),
    )
    p = tmp_path / "x.parquet"
    store.write_parquet(bar, p)
    back = store.read_parquet(p, M5)
    assert back.open_time.tolist() == bar.open_time.tolist()
    assert back.close.tolist() == bar.close.tolist()
