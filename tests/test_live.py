"""Live signal runner tests: idempotency, staleness, alerts (spec §12, §11 parity)."""
import pytest

from trendbot.live.state import State, load_state, save_state
from trendbot.live.signal import SignalRunner
from trendbot.strategy.strategy import ENTER, EXIT, HOLD

H1 = 3_600_000


def _runner():
    return SignalRunner("V3", H1)


def test_idempotent_same_bar_processed_once():
    r = _runner()
    s = State()
    a1 = r.process(s, 1000, ENTER, 100.0, 100.0, 5.0, now_ms=1000)
    assert len(a1) == 1
    a2 = r.process(s, 1000, ENTER, 100.0, 100.0, 5.0, now_ms=2000)
    assert a2 == []  # already processed


def test_catch_up_missed_bars_in_order():
    r = _runner()
    s = State(last_processed_close_ms=1000)
    a = r.process(s, 2000, ENTER, 100.0, 100.0, 5.0, now_ms=2100)
    assert len(a) == 1
    assert s.last_processed_close_ms == 2000


def test_stale_enter_suppressed():
    r = _runner()
    s = State()
    # bar closed > 2h ago -> stale
    a = r.process(s, 1000, ENTER, 100.0, 100.0, 5.0, now_ms=1000 + 3 * H1)
    assert [x.kind for x in a] == ["MISSED-ENTRY"]


def test_stale_exit_never_suppressed():
    r = _runner()
    s = State(position="long", entry_price=100.0)
    a = r.process(s, 1000, EXIT, 100.0, 100.0, 5.0, now_ms=1000 + 3 * H1)
    assert [x.kind for x in a] == ["STALE-EXIT"]


def test_price_moved_more_than_atr_is_stale():
    r = _runner()
    assert r.is_stale(1000, 100.0, 110.0, 5.0, now_ms=1100) is True   # 10 > 1*5
    assert r.is_stale(1000, 100.0, 102.0, 5.0, now_ms=1100) is False  # 2 <= 5


def test_state_roundtrip_atomic(tmp_path):
    p = tmp_path / "state.json"
    s = State(position="long", entry_price=100.0, last_processed_close_ms=123)
    save_state(p, s)
    s2 = load_state(p)
    assert s2.position == "long"
    assert s2.entry_price == 100.0
    assert s2.last_processed_close_ms == 123
    assert s2.schema_version == 1


def test_load_missing_state_defaults():
    s = load_state(tmp_path := __import__("pathlib").Path("/tmp/does-not-exist-xyz.json"))
    assert s.position == "flat"
    assert s.last_processed_close_ms is None
