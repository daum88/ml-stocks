#!/usr/bin/env python
"""Run the full backtest + verdict for a pair and write the report.

Usage:
  python scripts/run_backtest.py --pair XETHZEUR           # development (allowed pre-lock)
  python scripts/run_backtest.py --pair XBTEUR --gate      # the one real run (requires lock)

The gate run refuses to proceed unless PREREG.lock matches prereg.yaml and the tree is clean.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trendbot.common.config import load_prereg, load_fees, sha256_of_file  # noqa: E402
from trendbot.report import runner, writer, lock  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", default="XETHZEUR")
    ap.add_argument("--gate", action="store_true", help="real BTC/EUR gate run (requires lock)")
    ap.add_argument("--parquet-dir", default=str(ROOT / "data" / "parquet"))
    args = ap.parse_args()

    prereg = load_prereg(ROOT / "config" / "prereg.yaml")
    fees = load_fees(ROOT / "config" / "fees.yaml")

    if args.gate:
        ok, reason = lock.verify_lock(ROOT / "PREREG.lock", ROOT / "config" / "prereg.yaml", ROOT)
        if not ok:
            print(f"GATE REFUSED: {reason}", file=sys.stderr)
            sys.exit(1)

    print(f"Running backtest for {args.pair} ...", flush=True)
    result = runner.evaluate(args.pair, pathlib.Path(args.parquet_dir), prereg, fees)

    # run metadata (spec §2.2): commit, config hashes, manifest hash, library versions
    import platform
    import pandas as pd
    import numpy as np
    from trendbot.report import lock as lockmod
    meta = {
        "git_commit": lockmod.current_commit(ROOT),
        "prereg_sha256": sha256_of_file(ROOT / "config" / "prereg.yaml"),
        "fees_sha256": sha256_of_file(ROOT / "config" / "fees.yaml"),
        "python": platform.python_version(),
        "pandas": pd.__version__,
        "numpy": np.__version__,
    }
    manifest = ROOT / "data" / "parquet" / f"manifest_{args.pair}.json"
    if manifest.exists():
        meta["data_manifest_sha256"] = sha256_of_file(manifest)
    result["run_metadata"] = meta

    out_dir = ROOT / "results" / f"{args.pair}_{result['end_ms']}"
    report_path = writer.write_report(result, out_dir)

    if args.gate:
        # make results read-only (spec §10.1)
        for p in out_dir.rglob("*"):
            if p.is_file():
                p.chmod(0o444)
        out_dir.chmod(0o555)

    print(f"\nSelection: {result['selection']}")
    print(f"Report: {report_path}")
    print("Tiers: " + ", ".join(f"{k}={v[0]}" for k, v in result["outcomes"].items()))


if __name__ == "__main__":
    main()
