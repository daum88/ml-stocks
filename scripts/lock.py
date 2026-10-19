#!/usr/bin/env python
"""Create PREREG.lock (spec §10.1). Run this ONLY after finalizing prereg.yaml.

Usage: python scripts/lock.py
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trendbot.report import lock  # noqa: E402


def main() -> None:
    info = lock.write_lock(ROOT / "PREREG.lock", ROOT / "config" / "prereg.yaml", ROOT)
    print("PREREG.lock written:")
    print(f"  commit: {info['commit']}")
    print(f"  prereg sha256: {info['prereg_sha256']}")
    ok, reason = lock.verify_lock(ROOT / "PREREG.lock", ROOT / "config" / "prereg.yaml", ROOT)
    print(f"verify: {reason}" if ok else f"verify FAILED: {reason}")


if __name__ == "__main__":
    main()
