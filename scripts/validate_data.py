#!/usr/bin/env python
"""M2: data validation report (spec §3.6) from the stored Parquet tables.

Usage: python scripts/validate_data.py [--pairs XBTEUR,XETHZEUR]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trendbot.common import timeutil  # noqa: E402
from trendbot.data import store, validate, gaps  # noqa: E402

PARQUET = ROOT / "data" / "parquet"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="XBTEUR,XETHZEUR")
    args = ap.parse_args()

    report = {}
    for pair in args.pairs.split(","):
        report[pair] = {}
        for iv, iv_ms in [("5m", timeutil.INTERVAL_MS["5m"]), ("1h", timeutil.INTERVAL_MS["1h"]),
                          ("4h", timeutil.INTERVAL_MS["4h"]), ("1d", timeutil.INTERVAL_MS["1d"])]:
            p = PARQUET / f"{pair}_{iv}.parquet"
            if not p.exists():
                report[pair][iv] = {"missing": True}
                continue
            bar = store.read_parquet(p, iv_ms)
            q = validate.quality_report(bar)
            q["gap_rate"] = gaps.gap_rate(bar)
            q["gap_per_year"] = gaps.gap_stats(bar)
            report[pair][iv] = q

    # cross-source comparison: XBTEUR vs XETHZEUR daily is not meaningful (different assets);
    # here we only report the structural/quality per pair. (Bitvavo cross-check done in §3.1.)
    out = ROOT / "results" / "validation_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f"\nValidation report written to {out}")


if __name__ == "__main__":
    main()
