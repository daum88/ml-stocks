"""Bitvavo public REST client for the live-signal tool (spec §12.2)."""
from __future__ import annotations

import time
import urllib.error
import urllib.request
import json

BASE = "https://api.bitvavo.com/v2"


def fetch_candles(market: str, interval: str, limit: int = 1440) -> list[list]:
    """Fetch recent candles. Returns [[open_time_ms, o, h, l, c, volume], ...] oldest-first."""
    url = f"{BASE}/{market}/candles?interval={interval}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
            # newest-first from the API -> reverse to oldest-first
            data = sorted(data, key=lambda x: x[0])
            return data
        except urllib.error.HTTPError as e:
            if e.code == 429:
                # back off hard on rate limit (spec §12.2: never hammer)
                time.sleep(30 * (attempt + 1))
                continue
            raise
        except Exception:
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("failed to fetch Bitvavo candles after retries")


def fetch_time() -> int:
    with urllib.request.urlopen(f"{BASE}/time", timeout=15) as r:
        return int(json.loads(r.read())["time"])
