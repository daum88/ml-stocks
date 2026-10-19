"""State file — human-readable JSON, atomic writes (spec §12.3)."""
from __future__ import annotations

import json
import os
import pathlib
import tempfile
from dataclasses import dataclass, asdict

SCHEMA_VERSION = 1


@dataclass
class State:
    last_processed_close_ms: int | None = None
    position: str = "flat"                 # "flat" | "long"
    entry_price: float | None = None
    entry_amount: float | None = None
    entry_time_ms: int | None = None
    pending_order_note: str | None = None
    last_alert: str | None = None
    last_alert_time_ms: int | None = None
    consecutive_errors: int = 0
    schema_version: int = SCHEMA_VERSION


def load_state(path: pathlib.Path) -> State:
    if not path.exists():
        return State()
    data = json.loads(path.read_text())
    return State(**{k: v for k, v in data.items() if k in State.__dataclass_fields__})


def save_state(path: pathlib.Path, state: State) -> None:
    """Atomic write: write to a temp file, then replace (crash-safe)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".state.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(asdict(state), f, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
