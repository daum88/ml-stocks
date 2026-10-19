"""Report writer — plain-language verdict, criterion tables, charts (spec §10)."""
from __future__ import annotations

import json
import pathlib

import numpy as np

from trendbot.metrics.metrics import daily_grid, resample_daily

DAILY_MS = 86_400_000


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def write_report(result: dict, out_dir: pathlib.Path) -> pathlib.Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    pair = result["pair"]
    lines: list[str] = []
    a = lines.append

    a(f"# Backtest Report — {pair}")
    a("")
    a(f"- Window: {result['window_days']:.1f} days "
      f"({_ts(result['start_ms'])} → {_ts(result['end_ms'])})")
    a(f"- **Selection: {result['selection']}**")
    a("")

    bh = result["bh"]
    a("## Baselines")
    a(f"- Buy-and-hold: CAGR {_fmt_pct(bh['cagr'])}, "
      f"Calmar {bh['calmar'] if bh['calmar'] is not None else 'undefined'}, "
      f"final equity €{bh['final_equity']:.2f}")
    a("- Cash: 0% return (€400 flat)")
    a("")

    a("## Verdict criteria per variant")
    a("")
    a("| Variant | Tier | CAGR | Calmar | MaxDD(d) | Exp | Trips | Missed | C1 | C2 | C3 | C4 | C5 | C6 |")
    a("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for name, (tier, crit) in result["outcomes"].items():
        m = result["details"][name]["metrics"]
        cal_cell = f"{m.calmar:.2f}" if m.calmar is not None else "undef"
        flags = " ".join("✓" if crit[k] else "✗" for k in ["C1", "C2", "C3", "C4", "C5", "C6"])
        a(f"| {name} | **{tier}** | {_fmt_pct(m.cagr)} | {cal_cell} | "
          f"{_fmt_pct(m.max_drawdown_daily)} | {_fmt_pct(m.exposure)} | "
          f"{m.round_trips} | {m.missed_trades} | {flags} |")
    a("")

    a("## Variant details")
    a("")
    for name in ["V1", "V2", "V3"]:
        det = result["details"][name]
        m = det["metrics"]
        a(f"### {name}")
        cal_txt = f"{m.calmar:.2f}" if m.calmar is not None else "undef"
        a(f"- CAGR {_fmt_pct(m.cagr)} · Calmar {cal_txt}")
        a(f"- Max drawdown: daily {_fmt_pct(m.max_drawdown_daily)} · 5m {_fmt_pct(m.max_drawdown_5m)}")
        a(f"- Exposure {_fmt_pct(m.exposure)} · round trips {m.round_trips} · "
          f"missed {m.missed_trades} · skipped(min) {m.skipped_min_size}")
        a(f"- Win rate {_fmt_pct(m.win_rate)} · profit factor "
          f"{m.profit_factor if m.profit_factor is not None else 'undef'} · "
          f"avg hold {m.avg_hold_days:.1f} days · trades/yr {m.trades_per_year:.1f}")
        a(f"- Fee drag {_fmt_pct(m.fee_drag_annualized)} · fees €{m.total_fees:.2f} · "
          f"slippage €{m.total_slippage:.2f}")
        a(f"- Calmar rank {det['calmar_rank']*100:.1f}% · CAGR rank {det['cagr_rank']*100:.1f}%")
        a(f"- Sensitivity Calmars: {[f'{x:.2f}' for x in det['sensitivity_calmars']]}")
        if name == "V1" and "delay0_metrics" in det:
            m0 = det["delay0_metrics"]
            cal0 = f"{m0.calmar:.2f}" if m0.calmar is not None else "undef"
            cal360 = f"{m.calmar:.2f}" if m.calmar is not None else "undef"
            a(f"- V1 delay=0 (sensitivity): CAGR {_fmt_pct(m0.cagr)} · Calmar {cal0}")
            a(f"- V1 delay=360 (governs): CAGR {_fmt_pct(m.cagr)} · Calmar {cal360}")
        a("")

    # charts
    try:
        chart_path = _make_charts(result, out_dir)
        a(f"![charts]({chart_path.name})")
        a("")
    except Exception as e:  # charts are non-essential
        a(f"(chart generation skipped: {e})")
        a("")

    # raw JSON (lean summary — excludes the full per-bar equity curves)
    lean = {
        "pair": pair,
        "start_ms": result["start_ms"],
        "end_ms": result["end_ms"],
        "window_days": result["window_days"],
        "bh": {"cagr": bh["cagr"], "calmar": bh["calmar"], "final_equity": bh["final_equity"]},
        "selection": result["selection"],
        "outcomes": {},
    }
    for name, (tier, crit) in result["outcomes"].items():
        det = result["details"][name]
        m = det["metrics"]
        lean["outcomes"][name] = {
            "tier": tier, "criteria": crit,
            "cagr": m.cagr, "calmar": m.calmar, "max_drawdown_daily": m.max_drawdown_daily,
            "max_drawdown_5m": m.max_drawdown_5m, "exposure": m.exposure,
            "round_trips": m.round_trips, "missed_trades": m.missed_trades,
            "skipped_min_size": m.skipped_min_size, "avg_hold_days": m.avg_hold_days,
            "win_rate": m.win_rate, "profit_factor": m.profit_factor,
            "avg_win": m.avg_win, "avg_loss": m.avg_loss,
            "trades_per_year": m.trades_per_year, "fee_drag_annualized": m.fee_drag_annualized,
            "sharpe": m.sharpe, "sortino": m.sortino, "final_equity": m.final_equity,
            "total_fees": m.total_fees, "total_slippage": m.total_slippage,
            "total_pnl": m.total_pnl,
            "calmar_rank": det["calmar_rank"], "cagr_rank": det["cagr_rank"],
            "sensitivity_calmars": det["sensitivity_calmars"],
        }
    json_path = out_dir / "results.json"
    json_path.write_text(json.dumps(_jsonable(lean), indent=2))

    report_path = out_dir / "report.md"
    report_path.write_text("\n".join(lines))
    return report_path


def _ts(ms: int) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).date().isoformat()


def _jsonable(obj):
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if hasattr(obj, "__dataclass_fields__"):
        return _jsonable(obj.__dict__)
    return obj


def _make_charts(result: dict, out_dir: pathlib.Path) -> pathlib.Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    start, end = result["start_ms"], result["end_ms"]
    grid = daily_grid(start, end)
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))

    # equity curves
    ax = axes[0][0]
    for name in ["V1", "V2", "V3"]:
        eq5m = result["details"][name]["backtest"].equity_5m
        t = np.array([x[0] for x in eq5m], dtype=np.int64)
        e = np.array([x[1] for x in eq5m])
        de = resample_daily(t, e, grid, result["details"][name]["metrics"].final_equity)
        ax.plot(grid, de, label=name, linewidth=1)
    ax.plot(grid, np.full(grid.shape, 400.0), "k--", label="cash")
    ax.set_title("Equity (daily close)")
    ax.legend()

    # drawdown
    ax = axes[0][1]
    for name in ["V1", "V2", "V3"]:
        eq5m = result["details"][name]["backtest"].equity_5m
        t = np.array([x[0] for x in eq5m], dtype=np.int64)
        e = np.array([x[1] for x in eq5m])
        de = resample_daily(t, e, grid, result["details"][name]["metrics"].final_equity)
        peak = np.maximum.accumulate(de)
        ax.plot(grid, (de - peak) / peak, label=name, linewidth=1)
    ax.set_title("Drawdown (daily close)")
    ax.legend()

    # random-baseline histogram (V1)
    ax = axes[1][0]
    for name in ["V1", "V2", "V3"]:
        calmars = np.array(result["shift_results"][name]["calmars"])
        ax.hist(calmars[np.isfinite(calmars)], bins=50, alpha=0.4, label=name)
    ax.set_title("Circular-shift Calmar distribution")
    ax.legend()

    # trades per year
    ax = axes[1][1]
    names = ["V1", "V2", "V3"]
    tpy = [result["details"][n]["metrics"].trades_per_year for n in names]
    ax.bar(names, tpy)
    ax.set_title("Trades per year")

    fig.tight_layout()
    p = out_dir / "charts.png"
    fig.savefig(p, dpi=90)
    plt.close(fig)
    return p
