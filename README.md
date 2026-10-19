# BTC/EUR Trend Bot — Phases 1–2 (€400 edition)

Falsification-first trend-following system for BTC/EUR spot. Three pre-registered variants
(V1 daily SMA-200 · V2 4h EMA 50×100 · V3 1h EMA 20×50) are simulated on free public data
**before** any real money. No order placement in Phases 1–2.

## Status

Fully implemented and tested (74 tests). Data ingested and validated for **XBTEUR** (BTC/EUR)
and (pending) **ETHEUR** (ETH/EUR, dev asset). **The BTC/EUR gate run is intentionally NOT
run yet** — the pre-registration must be locked first (no-peeking rule).

## Documents

- `docs/trading-bot-master-plan.md` — strategy & governance plan (v3.3)
- `docs/bot-build-spec-phase1-2.md` — engineering build spec (v1.1, header updated to v3.3)
- `DECISIONS.md` — verified facts, decisions, open items, implementation status (source of truth)

## Layout

```
config/     prereg.yaml, fees.yaml, data_sources.yaml
src/trendbot/
  common/     time utilities (UTC), config schema (pydantic)
  data/       kraken ingest, gaps, validate, parquet store
  indicators/ sma, ema, atr, cross (exact spec §5 definitions)
  strategy/   decision logic (single impl shared by backtest + live)
  execution/  5m-bar fill simulator (D8)
  accounting/ ledger
  metrics/    cagr, drawdown, calmar, exposure, round trips, fee drag
  baselines/  buy-and-hold, cash, exposure-matched, circular-shift
  report/     verdict (Tier A/B/C + D10), runner, writer, lock
  live/       state, signal runner, bitvavo, telegram (Phase 2)
scripts/    ingest, build_parquet, validate_data, run_backtest, run_signal, lock, gen_synthetic, segdl, extract_members
tests/      74 tests (synthetic only — no network needed)
data/       gitignored raw + parquet
results/    immutable run outputs
```

## Quick start

```bash
# 1. Environment (Python 3.12)
/opt/homebrew/bin/python3.12 -m venv .venv && .venv/bin/pip install -r requirements.lock

# 2. Tests (synthetic data, no network)
PYTHONPATH=src .venv/bin/python -m pytest tests/ -q

# 3. Ingest Kraken data (download ~9 GB; parts 02/03/04 + Q3 suffice for XBTEUR;
#    part 01 for ETHEUR; part 00 is not needed)
.venv/bin/python scripts/ingest.py --pairs XBTEUR,ETHEUR

# 4. Data validation report
.venv/bin/python scripts/validate_data.py --pairs XBTEUR

# 5. DEVELOPMENT backtest on ETH/EUR (allowed pre-lock)
.venv/bin/python scripts/run_backtest.py --pair ETHEUR

# 6. THE GATE RUN on BTC/EUR — only after locking prereg.yaml
.venv/bin/python scripts/lock.py                          # human freezes prereg.yaml
.venv/bin/python scripts/run_backtest.py --pair XBTEUR --gate

# 7. Phase 2 live signal (once per candle, no orders)
TELEGRAM_BOT_TOKEN=... .venv/bin/python scripts/run_signal.py --variant V1 --chat-id CHAT_ID
```

## Key correctness rules enforced

- **No lookahead** — decisions use only bars with close time ≤ T (truncation-invariance tested).
- **No invented numbers** — every parameter lives in `config/*.yaml`, schema-validated.
- **One strategy implementation** — backtest and live call the same `Strategy.decide`.
- **Deterministic** — fixed seeds; no wall-clock in strategy/backtest.
- **No peeking** — BTC/EUR strategy results are gated behind `PREREG.lock`.
- **Conservative fills** — limit entries fill only on a ≥0.05% trade-through AND at a
  worse-than-limit price (double bias, deliberately against the strategy).
