"""Backtest orchestration: run variants + sensitivities + baselines + verdict (spec §8–§10)."""
from __future__ import annotations

import pathlib

import numpy as np

from trendbot.common.config import PreRegConfig, FeesConfig, load_prereg, load_fees
from trendbot.common import timeutil
from trendbot.strategy.strategy import Strategy, BarSeries
from trendbot.execution.fillsim import Backtester
from trendbot.metrics.metrics import compute_metrics, Metrics
from trendbot.baselines import baselines
from trendbot.data import store
from trendbot.report import verdict


def load_bars(pair: str, parquet_dir: pathlib.Path) -> dict[str, BarSeries]:
    """Load the stored Parquet tables for a pair."""
    out = {}
    for iv, iv_ms in [("1d", timeutil.INTERVAL_MS["1d"]), ("4h", timeutil.INTERVAL_MS["4h"]),
                      ("1h", timeutil.INTERVAL_MS["1h"]), ("5m", timeutil.INTERVAL_MS["5m"])]:
        p = parquet_dir / f"{pair}_{iv}.parquet"
        out[iv] = store.read_parquet(p, iv_ms)
    p5 = parquet_dir / f"{pair}_5m_filled.parquet"
    if p5.exists():
        out["5m_filled"] = store.read_parquet(p5, timeutil.INTERVAL_MS["5m"])
    else:
        out["5m_filled"] = out["5m"]
    return out


def global_start(bars: dict[str, BarSeries], prereg: PreRegConfig) -> int:
    """Earliest decision time where every indicator of every variant (+sensitivities) is valid."""
    daily = bars["1d"]
    candidates = [int(daily.close_time()[249])]   # V1 sensitivity SMA(250) + daily gate SMA(200)
    # V2 base (EMA 100) and sensitivity (EMA 140), on 4h
    h4 = bars["4h"]
    candidates.append(int(h4.close_time()[3 * 100]))
    candidates.append(int(h4.close_time()[3 * 140]))
    # V3 base (EMA 50) and sensitivity (EMA 70), on 1h
    h1 = bars["1h"]
    candidates.append(int(h1.close_time()[3 * 50]))
    candidates.append(int(h1.close_time()[3 * 70]))
    return max(candidates)


def _strategy_for(name: str, prereg: PreRegConfig, bars: dict[str, BarSeries],
                  override: dict | None = None) -> Strategy:
    cfg = prereg.model_copy(deep=True)
    if override:
        v = cfg.strategy.variants[name].model_copy(deep=True)
        for k, val in override.items():
            setattr(v, k, val)
        cfg.strategy.variants[name] = v
    tf = cfg.strategy.variants[name].timeframe
    signal = bars[tf]
    daily = bars["1d"]
    return Strategy(name, cfg.strategy, cfg, signal, daily), cfg


def run_variant(name: str, prereg: PreRegConfig, fees: FeesConfig, bars: dict[str, BarSeries],
                start_ms: int, end_ms: int, window_days: float, override: dict | None = None,
                delay: int | None = None):
    strat, cfg = _strategy_for(name, prereg, bars, override)
    if delay is not None:
        cfg.execution.action_delay_minutes[name] = delay
    base5m = bars["5m_filled"]
    bt = Backtester(strat, base5m, cfg, fees)
    res = bt.run(start_ms, end_ms)
    m = compute_metrics(res=res, initial_cash=cfg.evaluation.initial_cash_eur,
                        start_ms=start_ms, end_ms=end_ms, window_days=window_days)
    return strat, cfg, res, m


def circular_shift_rank(strat: Strategy, res, prereg: PreRegConfig, window_days: float):
    """Return (calmar_rank, cagr_rank) of the strategy's Calmar in the shifted-position baseline."""
    sig_close = strat.signal.close_time()
    fraction = baselines.fraction_series(sig_close, res.equity_5m)
    close = strat.signal.close
    returns = np.zeros(close.shape)
    returns[1:] = close[1:] / close[:-1] - 1.0
    total_cost = sum(f["fee"] + f["slip_cost"] for f in res.fills)
    delta = np.abs(np.diff(fraction)).sum()
    cost_per_unit = total_cost / delta if delta > 0 else 0.0
    _, calmars, cagrs = baselines.circular_shift(
        fraction, returns, cost_per_unit, prereg.baseline.random_shift_draws,
        prereg.baseline.random_seed, window_days)
    # strategy's own Calmar (daily-close basis from metrics) is passed in by caller via rank
    return calmars, cagrs


def evaluate(pair: str, parquet_dir: pathlib.Path, prereg: PreRegConfig, fees: FeesConfig) -> dict:
    bars = load_bars(pair, parquet_dir)
    start_ms = global_start(bars, prereg)
    # data window end: last complete daily bar of the dataset
    end_ms = int(bars["5m"].close_time()[-1] // timeutil.INTERVAL_MS["1d"] * timeutil.INTERVAL_MS["1d"])
    window_days = (end_ms - start_ms) / timeutil.INTERVAL_MS["1d"]

    initial = prereg.evaluation.initial_cash_eur

    # --- baselines ---
    bh = baselines.bh_metrics(bars["5m_filled"], start_ms, end_ms, initial,
                              fees.exchange.taker_fee_pct, prereg.costs.entry_slip_pct["V1"])
    # exposure-matched needs the strategy's exposure (use V1 as reference for now; recomputed per variant)
    base = {"bh_cagr": bh["cagr"], "bh_calmar": bh["calmar"]}

    # --- variants ---
    outcomes = {}
    details = {}
    shift_results = {}
    for name in ["V1", "V2", "V3"]:
        strat, cfg, res, m = run_variant(name, prereg, fees, bars, start_ms, end_ms, window_days)
        calmars, cagrs = circular_shift_rank(strat, res, prereg, window_days)
        calmar_rank = baselines.percentile_rank(m.calmar if m.calmar is not None else -1.0, calmars)
        cagr_rank = baselines.percentile_rank(m.cagr, cagrs)
        # sensitivity variants (C6)
        sens_calmars = []
        for sname, desc, ov in _sensitivity_overrides(name, prereg):
            _, _, sres, sm = run_variant(name, prereg, fees, bars, start_ms, end_ms, window_days, ov)
            sens_calmars.append(sm.calmar if sm.calmar is not None else 0.0)
        # exposure-matched baseline for this variant's exposure
        em_cagr = _exposure_matched(prereg, fees, bars, start_ms, end_ms, initial, m.exposure)
        base_v = verdict.Baselines(bh_cagr=bh["cagr"], bh_calmar=bh["calmar"],
                                   exposure_matched_cagr=em_cagr)
        vo = verdict.evaluate_variant(name, m.cagr, m.calmar, m.round_trips, calmar_rank,
                                      cagr_rank, sens_calmars, base_v, prereg,
                                      window_days / 365.25)
        outcomes[name] = vo
        details[name] = {"metrics": m, "backtest": res, "calmar_rank": calmar_rank,
                         "cagr_rank": cagr_rank, "sensitivity_calmars": sens_calmars}
        # V1: also report the delay=0 result (spec §7.4 / §10.2 — delay>0 governs).
        if name == "V1":
            _, _, res0, m0 = run_variant("V1", prereg, fees, bars, start_ms, end_ms,
                                         window_days, delay=0)
            details[name]["delay0_metrics"] = m0
        shift_results[name] = {"calmars": calmars.tolist(), "cagrs": cagrs.tolist()}

    selection = verdict.select(outcomes, prereg)
    return dict(pair=pair, start_ms=start_ms, end_ms=end_ms, window_days=window_days,
                bh=bh, outcomes={k: (v.tier, v.criteria) for k, v in outcomes.items()},
                selection=selection, details=details, shift_results=shift_results)


def _sensitivity_overrides(name: str, prereg: PreRegConfig):
    cr = prereg.criteria.C6_sensitivity_variants.get(name, [])
    out = []
    if name == "V1":
        for n in cr:
            out.append((name, f"V1_SMA{n}", {"sma": n}))
    else:
        for (f, s) in cr:
            out.append((name, f"{name}_EMA{f}x{s}", {"ema_fast": f, "ema_slow": s}))
    return out


def _exposure_matched(prereg, fees, bars, start_ms, end_ms, initial, exposure):
    from trendbot.metrics.metrics import cagr
    base5m = bars["5m_filled"]
    grid = baselines.daily_grid(start_ms, end_ms)
    prices = baselines.price_at_grid(base5m, grid)
    rets = np.zeros(prices.shape)
    rets[1:] = prices[1:] / prices[:-1] - 1.0
    final = baselines.exposure_matched_final(rets, exposure, initial)
    return cagr(final, initial, (end_ms - start_ms) / timeutil.INTERVAL_MS["1d"])
