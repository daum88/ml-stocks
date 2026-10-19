#!/usr/bin/env python
"""M1: Kraken OHLCVT ingestion — verify, join, extract, parse, normalize, store, validate.

Usage: python scripts/ingest.py [--pairs XBTEUR,XETHZEUR] [--skip-download-check]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trendbot.common import timeutil  # noqa: E402
from trendbot.data import kraken, gaps, store, validate  # noqa: E402

RAW = ROOT / "data" / "raw"
PARQUET = ROOT / "data" / "parquet"
BASE_URL = "https://assets.kraken.com/marketing/institutions"
PARTS = [f"Kraken_OHLCVT_Full.zip.part{i:02d}" for i in range(5)]
CHECKSUMS = "OHLCVT_Full_PARTS_SHA256SUMS.txt"
FULL_ZIP = "Kraken_OHLCVT_Full.zip"
Q3_ZIP = "Kraken_OHLCVT_2026Q3.zip"
REASSEMBLED_SHA = "bc273e9027470b07d790a7fa4df9bb43f0dfc527c20c6ecae48402e123e7b1c7"
INTERVAL_MIN = {"5m": 5, "1h": 60, "4h": 240, "1d": 1440}


def download(url: str, dest: pathlib.Path) -> None:
    if dest.exists():
        return
    print(f"  downloading {url} ...", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=600) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)


def verify_parts() -> None:
    sums_path = RAW / CHECKSUMS
    if not sums_path.exists():
        download(f"{BASE_URL}/{CHECKSUMS}", sums_path)
    expected = {}
    for line in sums_path.read_text().splitlines():
        h, name = line.strip().split()
        expected[name] = h
    print("Verifying part SHA-256 checksums ...", flush=True)
    for name in PARTS:
        p = RAW / name
        if not p.exists():
            raise FileNotFoundError(f"missing {p}")
        got = store.sha256_file(p)
        if got != expected[name]:
            raise ValueError(f"checksum mismatch for {name}: got {got}")
        print(f"  OK {name}", flush=True)
    print("All parts verified.", flush=True)


def ingest_pair(pair: str, out: dict) -> None:
    print(f"\n=== ingesting {pair} ===", flush=True)
    for iv, iv_min in INTERVAL_MIN.items():
        members = [kraken.member_names(pair, iv_min)]
        full_files = kraken.extract_members(RAW / FULL_ZIP, members, RAW / "extract_full")
        q3_files = kraken.extract_members(RAW / Q3_ZIP, members, RAW / "extract_q3")

        interval_ms = timeutil.INTERVAL_MS[iv]
        bar = kraken.parse_kraken_csv(full_files[0], interval_ms)
        q3 = kraken.parse_kraken_csv(q3_files[0], interval_ms)
        bar = kraken.append_quarterly(bar, q3)

        validate.structural_checks(bar)
        q = validate.quality_report(bar)
        print(f"  {iv}: {q['rows']} rows, {q['first']}..{q['last']}, "
              f"big-move bars {q['bars_abs_return_gt_20pct']}, zero-vol {q['zero_volume_bars']}",
              flush=True)

        # gap report
        gs = gaps.gap_stats(bar)
        gr = gaps.gap_rate(bar)
        print(f"    gap rate {gr*100:.3f}%  (per-year missing: "
              f"{ {y: gs[y]['missing'] for y in sorted(gs)} })", flush=True)

        # store raw (gapped) + gap-filled (for 5m fill sim)
        store.write_parquet(bar, PARQUET / f"{pair}_{iv}.parquet")
        if iv == "5m":
            filled = gaps.fill_gaps(bar)
            store.write_parquet(filled, PARQUET / f"{pair}_5m_filled.parquet")

        out[f"{pair}_{iv}"] = {
            "rows": int(bar.open_time.size),
            "first": int(bar.open_time[0]),
            "last": int(bar.open_time[-1]),
            "gap_rate": float(gr),
            "sha256": store.sha256_file(PARQUET / f"{pair}_{iv}.parquet"),
        }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="XBTEUR,XETHZEUR")
    args = ap.parse_args()
    pairs = args.pairs.split(",")

    RAW.mkdir(parents=True, exist_ok=True)
    PARQUET.mkdir(parents=True, exist_ok=True)

    print("Step 1/5: ensure parts present", flush=True)
    for name in PARTS + [Q3_ZIP]:
        download(f"{BASE_URL}/{name}", RAW / name)

    print("Step 2/5: verify parts", flush=True)
    verify_parts()

    print("Step 3/5: join parts into full zip", flush=True)
    if not (RAW / FULL_ZIP).exists():
        kraken.join_parts(RAW, RAW / FULL_ZIP)
    got = store.sha256_file(RAW / FULL_ZIP)
    if got != REASSEMBLED_SHA:
        raise ValueError(f"reassembled zip checksum mismatch: {got}")
    print("  full zip verified OK", flush=True)

    print("Step 4/5: parse + store", flush=True)
    manifest = []
    for pair in pairs:
        ingest_pair(pair, manifest)
    store.write_manifest(manifest, PARQUET / "manifest.json")
    print("\nStep 5/5: done. Manifest:", flush=True)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
