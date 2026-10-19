"""Telegram sender — official Bot API `sendMessage`; token from env var (spec §12.6)."""
from __future__ import annotations

import json
import os
import time
import urllib.request


def send_message(chat_id: str, text: str, token: str | None = None) -> bool:
    """Send a Telegram message. The token never appears in logs or the repo."""
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                r.read()
            return True
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Telegram send failed: {last}")
