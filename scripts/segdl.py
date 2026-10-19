#!/usr/bin/env python
"""Segmented downloader — fresh connection per chunk (avoids CDN long-connection throttling).

Usage: python scripts/segdl.py URL DEST [--chunk 200MB] [--threads 6]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import pathlib
import sys
import urllib.request


def content_length(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return int(r.headers["Content-Length"])


def fetch_range(url: str, start: int, end: int) -> bytes:
    req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}",
                                               "User-Agent": "Mozilla/5.0"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.read()
        except Exception as e:
            if attempt == 4:
                raise
            print(f"  retry range {start}-{end}: {e}", flush=True)


def segmented_download(url: str, dest: pathlib.Path, chunk: int, threads: int) -> None:
    total = content_length(url)
    ranges = []
    start = 0
    while start < total:
        end = min(start + chunk - 1, total - 1)
        ranges.append((start, end))
        start = end + 1
    print(f"Downloading {dest.name}: {total/1e6:.0f} MB in {len(ranges)} chunks", flush=True)

    with open(dest, "wb") as f:
        f.truncate(total)

    done = 0
    def work(r):
        data = fetch_range(url, r[0], r[1])
        return r[0], data

    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as ex:
        futures = {ex.submit(work, r): r for r in ranges}
        for fut in concurrent.futures.as_completed(futures):
            start, data = fut.result()
            with open(dest, "r+b") as f:
                f.seek(start)
                f.write(data)
            done += 1
            if done % max(1, len(ranges) // 10) == 0 or done == len(ranges):
                print(f"  {dest.name}: {done}/{len(ranges)} chunks", flush=True)
    print(f"  DONE {dest.name}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("dest")
    ap.add_argument("--chunk", type=int, default=200 * 1024 * 1024)
    ap.add_argument("--threads", type=int, default=6)
    args = ap.parse_args()
    segmented_download(args.url, pathlib.Path(args.dest), args.chunk, args.threads)


if __name__ == "__main__":
    main()
