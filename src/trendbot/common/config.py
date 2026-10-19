"""Configuration loading with strict schema validation (spec §2.2).

Every parameter lives in a YAML config file. Loading fails loudly on unknown or
missing keys (pydantic `extra="forbid"`). Percentages are stored as fractions.
"""
from __future__ import annotations

import hashlib
import pathlib
from typing import Any, Dict, List, Optional, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# --------------------------------------------------------------------------- #
# prereg.yaml
# --------------------------------------------------------------------------- #

class VariantConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timeframe: str
    entry: Optional[str] = None
    exit: Optional[str] = None
    sma: Optional[int] = None
    ema_fast: Optional[int] = None
    ema_slow: Optional[int] = None
    trailing_atr_mult: Optional[float] = None


class StrategyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variants: Dict[str, VariantConfig]
    daily_gate_sma: int
    atr_period: int
    disaster_stop_pct: float


class IndicatorsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ema_seed: str
    ema_warmup_mult: int
    atr_warmup_bars: int


class SizingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    V2V3_risk_pct: float
    cap_pct_of_equity: float


class CostsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    half_spread_pct: float
    through_haircut_pct: float
    entry_slip_pct: Dict[str, float]
    exit_slip_pct: Dict[str, float]


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repricing_rule: str
    entry_attempts: int
    action_delay_minutes: Dict[str, int]
    conservative_fill_bias: bool


class EvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    initial_cash_eur: float
    data_window_end: str


class SelectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    V1_default: bool
    replace_margin_cagr: float
    replace_margin_calmar: float
    tie_break: str


class CriteriaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    C1_return_floor_pct_of_bh: float
    C2_exposure_match_penalty_pp: float
    C3_calmar_mult_of_bh: float
    C4_baseline_percentile: float
    C5_sanity_floor_trips: Dict[str, int]
    C6_sensitivity_variants: Dict[str, List[Any]]
    selection: SelectionConfig


class BaselineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    random_shift_draws: int
    random_seed: int


class PreRegConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategy: StrategyConfig
    indicators: IndicatorsConfig
    sizing: SizingConfig
    costs: CostsConfig
    execution: ExecutionConfig
    evaluation: EvaluationConfig
    criteria: CriteriaConfig
    baseline: BaselineConfig


# --------------------------------------------------------------------------- #
# fees.yaml
# --------------------------------------------------------------------------- #

class OrderConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_order_quote_eur: float
    min_order_base_btc: float
    quantity_step_btc: float
    price_tick_eur: float
    max_open_orders: int


class PostOnlyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supported: str
    confirm_method: str


class ExchangeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    market: str
    maker_fee_pct: float
    taker_fee_pct: float


class FeesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exchange: ExchangeConfig
    order_constraints: OrderConstraints
    post_only: PostOnlyConfig


# --------------------------------------------------------------------------- #
# data_sources.yaml
# --------------------------------------------------------------------------- #

class DataSourcesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bitvavo: Dict[str, Any]
    kraken: Dict[str, Any]
    binance: Dict[str, Any]


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #

def _load_yaml(path: pathlib.Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_prereg(path: pathlib.Path) -> PreRegConfig:
    return PreRegConfig.model_validate(_load_yaml(path))


def load_fees(path: pathlib.Path) -> FeesConfig:
    return FeesConfig.model_validate(_load_yaml(path))


def load_data_sources(path: pathlib.Path) -> DataSourcesConfig:
    return DataSourcesConfig.model_validate(_load_yaml(path))


def sha256_of_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
