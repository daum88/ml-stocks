# BTC/EUR Trend Bot — Phases 1–2 (€400 edition)

Falsification-first trend-following bot for BTC/EUR spot. Three pre-registered variants
(V1 daily SMA-200 · V2 4h EMA 50×100 · V3 1h EMA 20×50), simulated on free public data
before any real money.

## Status

**Phase 0 in progress.** Public-source verification is done and recorded in
[`DECISIONS.md`](DECISIONS.md). **A critical data-source blocker is open (see §2 there) —
data ingestion (M1) is blocked pending a human decision.**

## Documents

- `docs/trading-bot-master-plan.md` — the strategy & governance plan (v3.3)
- `docs/bot-build-spec-phase1-2.md` — the engineering build spec (v1.1)
- `DECISIONS.md` — verified facts, decisions, and open items (source of truth)

## Layout (per spec §1)

```
config/   prereg.yaml, fees.yaml, data_sources.yaml
src/      (data, indicators, strategy, execution, accounting, metrics,
           baselines, report, live, common)
tests/    unit / golden / property / parity tests
scripts/  fetch-data, validate-data, build-parquet, run-backtest, make-report,
          run-signal, confirm-fill
data/     gitignored raw downloads + Parquet
results/  immutable run outputs
```

## Next actions (blocked on human decisions — see DECISIONS.md §2–§4)

1. Resolve the candle data source (Kraken OHLCVT archive is gone).
2. Choose the exchange + confirm the account fee tier (fills `fees.yaml`).
3. Reconcile plan-v3.3 vs spec-v1.1 on D8 re-pricing and V1 execution time.
4. Then: M0 completion (env, schemas), M1 (ingestion), … lock at M7.
