"""Run-once guard (PREREG.lock) tests (spec §10.1, §11)."""
import json
import pathlib

from trendbot.report import lock


def test_lock_roundtrip_and_verify(tmp_path):
    prereg = tmp_path / "prereg.yaml"
    prereg.write_text("strategy: {variants: {V1: {timeframe: 1d}}}\n")
    lock_path = tmp_path / "PREREG.lock"

    # no lock -> verify fails
    ok, reason = lock.verify_lock(lock_path, prereg, tmp_path)
    assert not ok

    # create lock (no git repo -> commit is None)
    lock.write_lock(lock_path, prereg, tmp_path)
    ok, reason = lock.verify_lock(lock_path, prereg, tmp_path)
    assert ok, reason

    # tamper with prereg -> verify fails
    prereg.write_text("strategy: {variants: {V1: {timeframe: 4h}}}\n")
    ok, reason = lock.verify_lock(lock_path, prereg, tmp_path)
    assert not ok
    assert "hash" in reason


def test_lock_contains_hashes(tmp_path):
    prereg = tmp_path / "prereg.yaml"
    prereg.write_text("x: 1\n")
    lock_path = tmp_path / "PREREG.lock"
    lock.write_lock(lock_path, prereg, tmp_path)
    data = json.loads(lock_path.read_text())
    assert "prereg_sha256" in data
