"""Config schema tests (spec §2.2, M0)."""
import pathlib

import pytest

from trendbot.common import config

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_load_prereg_valid():
    cfg = config.load_prereg(ROOT / "config" / "prereg.yaml")
    assert cfg.strategy.variants["V1"].timeframe == "1d"
    assert cfg.strategy.variants["V2"].ema_fast == 50
    assert cfg.execution.repricing_rule == "once_at_next_close"
    assert cfg.execution.action_delay_minutes["V1"] == 360
    assert cfg.costs.entry_slip_pct["V1"] == 0.0010
    assert cfg.baseline.random_seed == 42


def test_load_fees_valid():
    cfg = config.load_fees(ROOT / "config" / "fees.yaml")
    assert cfg.exchange.name == "bitvavo"
    assert cfg.exchange.maker_fee_pct == 0.0015
    assert cfg.order_constraints.price_tick_eur == 1.00


def test_load_data_sources_valid():
    cfg = config.load_data_sources(ROOT / "config" / "data_sources.yaml")
    assert "Kraken_OHLCVT_Full.zip.part00" in cfg.kraken["archive"]["parts"]


def test_unknown_key_rejected(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("strategy:\n  variants:\n    V1:\n      timeframe: '1d'\n      BOGUS: 1\n")
    with pytest.raises(Exception):
        config.load_prereg(p)


def test_missing_key_rejected(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("strategy:\n  variants:\n    V1:\n      timeframe: '1d'\n")
    with pytest.raises(Exception):
        config.load_prereg(p)


def test_fee_must_be_fraction(tmp_path):
    """Regression: fees stored as 0.15 (15%) instead of 0.0015 (0.15%) must be rejected."""
    p = tmp_path / "bad_fees.yaml"
    p.write_text(
        "exchange:\n  name: bitvavo\n  market: BTC-EUR\n"
        "  maker_fee_pct: 0.15\n  taker_fee_pct: 0.0025\n"
        "order_constraints:\n  min_order_quote_eur: 5.0\n  min_order_base_btc: 1e-6\n"
        "  quantity_step_btc: 1e-8\n  price_tick_eur: 1.0\n  max_open_orders: 400\n"
        "post_only:\n  supported: LIKELY\n  confirm_method: x\n"
    )
    with pytest.raises(Exception):
        config.load_fees(p)
