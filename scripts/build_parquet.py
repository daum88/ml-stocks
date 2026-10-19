#!/usr/bin/env python
"""Parse extracted Kraken CSVs (full + Q3), normalize, gap-fill, store Parquet (spec §3.3).

Usage: python scripts/build_parquet.py --pair XBTEUR [--full-dir data/csv] [--q3-dir data/csv_q3]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trendbot.common import timeutil  # noqa: E402
from trendbot.data import kraken, gaps, store, validate  # noqa: E402

INTERVAL_MIN = {"5m": 5, "1h": 60, "4h": 240, "1d": 1440}
PARQUET = ROOT / "data" / "parquet"


def build_pair(pair: str, full_dir: pathlib.Path, q3_dir: pathlib.Path) -> list[dict]:
    manifest = []
    for iv, iv_min in INTERVAL_MIN.items():
        full_csv = full_dir / f"{pair}_{iv_min}.csv"
        q3_csv = q3_dir / f"{pair}_{iv_min}.csv"
        if not full_csv.exists():
            print(f"  SKIP {pair}_{iv}: {full_csv} not present", flush=True)
            continue
        interval_ms = timeutil.INTERVAL_MS[iv]
        bar = kraken.parse_kraken_csv(full_csv, interval_ms)
        if q3_csv.exists():
            q3 = kraken.parse_kraken_csv(q3_csv, interval_ms)
            bar = kraken.append_quarterly(bar, q3)
        validate.structural_checks(bar)
        q = validate.quality_report(bar)
        gr = gaps.gap_rate(bar)
        store.write_parquet(bar, PARQUET / f"{pair}_{iv}.parquet")
        if iv == "5m":
            filled = gaps.fill_gaps(bar)
            store.write_parquet(filled, PARQUET / f"{pair}_5m_filled.parquet")
        print(f"  {iv}: {q['rows']} rows, gap {gr*100:.3f}%, "
              f"big-move {q['bars_abs_return_gt_20pct']}, zero-vol {q['zero_volume_bars']}",
              flush=True)
        manifest.append({
            "pair_interval": f"{pair}_{iv}", "rows": q["rows"],
            "first": q["first"], "last": q["last"], "gap_rate": gr,
            "first_date": _ts(q["first"]), "last_date": _ts(q["last"]),
            "sha256": store.sha256_file(PARQUET / f"{pair}_{iv}.parquet"),
        })
    return manifest


def _ts(ms: int) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).date().isoformat()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", default="XBTEUR")
    ap.add_argument("--full-dir", default=str(ROOT / "data" / "csv"))
    ap.add_argument("--q3-dir", default=str(ROOT / "data" / "csv_q3"))
    args = ap.parse_args()

    PARQUET.mkdir(parents=True, exist_ok=True)
    print(f"Building parquet for {args.pair} ...", flush=True)
    manifest = build_pair(args.pair, pathlib.Path(args.full_dir), pathlib.Path(args.q3_dir))
    if manifest:
        store.write_manifest(manifest, PARQUET / f"manifest_{args.pair}.json")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
