# Build Specification — BTC/EUR Trend Bot, Phases 1–2

**Companion to:** Trading Bot Plan (€400 edition), written against v3.3 · **Spec version:** 1.1 · **Date:** 2026-10-19
**Audience:** an autonomous coding agent (and the human reviewing it).
**This document contains no code on purpose.** It says *what* to build, *how it must behave*, and *how to prove it is correct*. Where an exact number is needed, it comes from `prereg.yaml` / `fees.yaml` (see §2), never from the agent's judgment.

---

# 0. Mission, scope, and the rules the agent must obey

## 0.1 What to build

1. **Data pipeline** — download, normalize, validate and store BTC/EUR history (daily, 4h, 1h, 5m).
2. **Simulation engine** — implements the three pre-registered strategy variants (V1 daily, V2 4h, V3 1h), the entry/exit execution rule (plan decision D8), cost model, accounting, metrics, baselines, sensitivity runs.
3. **Verdict generator** — applies the plan's Tier A/B/C criteria and selection rule (D10) mechanically and writes a report.
4. **Phase 2 live-signal tool** — a once-per-candle script that computes the chosen variant's signal from public exchange data and sends Telegram alerts. It places **no orders**.

## 0.2 What NOT to build (non-goals)

- No order placement, no private/authenticated exchange API calls, no API keys of any kind in Phases 1–2.
- No freqtrade integration yet (Branch B is described in §12.8 only as future requirements).
- No VPS/Docker setup, no ML, no other pairs, no intraday-under-5m logic, no leverage/shorting.
- No hyperparameter search. Parameters are fixed in the pre-registration file.

## 0.3 Hard rules for the agent

1. **Never invent a number.** Every parameter lives in a config file. If a needed value is missing, stop and ask (list in §14).
2. **One strategy implementation.** The backtester and the live-signal tool must call the *same* decision code (§6). No re-implementation in the live script.
3. **No lookahead, ever.** Follow the time rules in §4 exactly. Tests in §11 enforce this.
4. **Tests before real data.** Build and pass the full synthetic test suite before running anything on real BTC/EUR data.
5. **No peeking at strategy performance on the real validation data before the lock.** Develop and debug on synthetic data and on a *different* asset (ETH/EUR) — never print BTC/EUR strategy performance until the pre-registration is locked (§10). Data-quality checks on BTC/EUR are allowed and required.
6. **Public endpoints only.** No secrets in the repo, in logs, or in chat. The only secret in Phase 2 is the Telegram bot token, read from an environment variable.
7. **Respect rate limits and errors.** Back off on HTTP 429, never loop on errors, never hammer an endpoint.
8. **Determinism.** Fixed random seeds, no wall-clock dependence inside strategy/backtest code, identical inputs → byte-identical outputs.
9. **Official docs beat this spec.** If an exchange or data-provider doc disagrees with a fact here, trust the doc, record it in `DECISIONS.md`, and ask the human if a number changes.
10. **Small verified steps.** One milestone at a time (§13), commit after each, never start the next until the "done when" checks pass.
11. **Memory budget:** the whole pipeline must run in under ~3 GB of RAM on an 8 GB MacBook Air (M2). Read data in chunks; never load multiple years of 1-minute data.

---

# 1. Repository layout (what goes where)

Plain-language layout; the agent chooses file names that follow this structure.

| Area | Contents |
|---|---|
| `config/` | `prereg.yaml` (all strategy/cost/criteria parameters), `fees.yaml` (exchange tier fees, min order, tick/lot sizes), `data_sources.yaml` (URLs, expected files, checksums once known) |
| `src/<package>/data/` | download, extract, normalize, validate, store (Parquet), resample |
| `src/<package>/indicators/` | SMA, EMA, ATR (exact definitions in §5) |
| `src/<package>/strategy/` | pure decision logic for V1/V2/V3 (state machine, §6) |
| `src/<package>/execution/` | fill simulator (D8), costs, order lifecycle (§7) |
| `src/<package>/accounting/` | cash/BTC ledger, equity curve, trade table |
| `src/<package>/metrics/` | CAGR, drawdown, Calmar, exposure, secondary stats (§8) |
| `src/<package>/baselines/` | buy-and-hold, exposure-matched, cash, shifted-position random baseline (§9) |
| `src/<package>/report/` | verdict logic, tables, charts, report writer (§10) |
| `src/<package>/live/` | signal runner, state file, Telegram, scheduler notes (§12) |
| `src/<package>/common/` | time utilities (UTC only), logging, config loading with schema validation |
| `tests/` | unit, golden, property-style and parity tests (§11) |
| `scripts/` (CLI entry points) | fetch-data, validate-data, build-parquet, run-backtest, make-report, run-signal, confirm-fill |
| `data/` | **gitignored** raw downloads and Parquet |
| `results/` | immutable run outputs (never overwritten) |
| root | `DECISIONS.md`, `PREREG.lock`, `README`, dependency lock file |

---

# 2. Environment and configuration

## 2.1 Environment

- macOS arm64, **Python 3.12** (pyenv), a dedicated virtual environment, **no Docker**.
- Dependencies (pin exact versions in a lock file at install time): a data-frame library, a numerical library, a Parquet library, an HTTP client, a YAML parser, a schema-validation library, a plotting library, and a test runner. Nothing else without asking.
- TA-Lib is **optional** and used only in one cross-check test (§11); the pipeline must not depend on it (it is hard to install on macOS).
- Time handling is **UTC only**. Never use local time anywhere in logic. (Estonia changes DST on 2026-10-25; UTC avoids all DST bugs.)

## 2.2 Configuration files (single source of truth)

- `prereg.yaml` — everything the pre-registration freezes: variant definitions and lengths, ATR multiples, disaster-stop percent, risk% for V2/V3, cost components, fill-model parameters, evaluation start rule, Tier A/B thresholds, selection margin, sanity floors, sensitivity variants, random-draw count and seed.
- `fees.yaml` — filled by the human after Phase 0: maker/taker fee for the chosen exchange tier, minimum order size, quantity step, price tick, and the chosen exchange name.
- Config loading must **validate against a schema** and fail loudly on unknown or missing keys.
- Every run records: git commit hash, hash of `prereg.yaml`, hash of `fees.yaml`, data manifest hash, library versions.

---

# 3. Data layer

## 3.1 Sources (verified facts vs things to verify)

| Source | Role | Verified facts | Must verify before relying on it |
|---|---|---|---|
| **Kraken OHLCVT archive** (Kraken support article "Downloadable historical OHLCVT data") | **Primary long history, BTC/EUR, incl. 5m for fills** | Full history through 2026-06-30 is split into five parts (~2 GB each) that must be joined into one ZIP before extracting; quarterly update ZIPs are listed (2026 Q1–Q3); CSVs have **no header** and the columns are `timestamp, open, high, low, close, volume, trades`; only intervals that had trades appear (**gaps are not zero-filled**); archives carry a `MANIFEST.json`; checksums are published for the parts and the joined ZIP | Exact BTC/EUR file name inside the archive (the page does not list pairs — inspect the archive and `MANIFEST.json`; Kraken often labels BTC as `XBT`); **timestamp unit** (not stated — detect by magnitude); the page lists timeframes inconsistently (one list omits 30 minutes) — confirm 5, 60, 240, 1440 exist for the pair; first-trade date of the pair |
| **Bitvavo REST (public)** | Cross-check on recent data; basis for the live-signal tool | Base URL `https://api.bitvavo.com/v2`; public endpoint `GET /{market}/candles` exists; public endpoints need no key | Candle query parameters, **max candles per call**, supported intervals, timestamp convention, whether the newest returned candle is still open (assume it may be), per-endpoint rate-limit weight for candles |
| **Binance public data** (`data.binance.vision`) | Second cross-check (BTCUSDT; BTCEUR only if it exists) | Monthly kline ZIPs follow `…/data/spot/monthly/klines/{SYMBOL}/{interval}/{SYMBOL}-{interval}-{YYYY-MM}.zip`; each has a `.CHECKSUM` file; CSV columns: open time, open, high, low, close, volume, close time, quote volume, trades, taker-buy base, taker-buy quote, ignore; **spot data from 2025-01-01 uses microsecond timestamps** | Whether BTCEUR exists and since when; timestamp unit before 2025; daily-file URL pattern; USDT ≠ EUR (differences include the EUR/USD rate) |

If any source cannot be obtained, stop and report; do not substitute another source silently.

## 3.2 Canonical data schema (what every stored candle table must look like)

- One table per (pair, interval), stored as Parquet, sorted ascending, unique index.
- Index/key: **`open_time`** = candle **open** time, UTC, integer **milliseconds** since epoch (normalized — see 3.3).
- Columns: open, high, low, close, volume, trades (if available), and a boolean **`is_filled_gap`** (true for synthetic rows, see 3.4).
- Derived on load, never stored as truth: `close_time = open_time + interval`.
- Prices are 64-bit floats; do not round.

## 3.3 Ingestion rules (Kraken archive, in order)

1. Download all parts and the quarterly ZIPs; verify **SHA-256 against the values published on the live page** (parts file and joined ZIP). Abort on mismatch.
2. Join parts into one ZIP, verify, extract into its own empty directory.
3. Read `MANIFEST.json`; record it in the data manifest.
4. Locate the BTC/EUR files for 5, 60, 240, 1440 minutes; log their names.
5. Parse CSV with the six/seven documented columns and **no header**.
6. **Normalize timestamps to milliseconds by magnitude:** values around 1e9 are seconds, 1e12 milliseconds, 1e15 microseconds, 1e18 nanoseconds. Fail if a value doesn't match one clear unit, or if one file mixes units.
7. Sort, drop exact duplicates, fail on duplicate timestamps with different values.
8. Append the quarterly update files in order; fail on overlaps with conflicting values.
9. Store Parquet and write a data manifest (file names, row counts, first/last timestamp, hashes).

The Binance and Bitvavo ingestion follow the same normalize → validate → store steps. For Binance, apply the same magnitude-based unit detection (microseconds appear for 2025+).

## 3.4 Gap policy (important for correctness)

- Kraken omits intervals with no trades. **Do not silently interpolate.**
- Build a gap report: count and list of missing intervals per year per timeframe.
- For simulation continuity create explicit filler rows only where needed: open=high=low=close=previous close, volume=0, `is_filled_gap = true`. A filled-gap bar **can never trigger a fill or a stop** in the simulator (no trades happened), but it keeps time series aligned.
- If any year has a gap rate above a threshold set by the human (default: 1% of bars for 5m, 0.1% for ≥1h after 2018), report it prominently and stop for human review.

## 3.5 Resampling and alignment

- All bars are aligned to UTC: 1h on the hour; 4h at 00,04,08,12,16,20 UTC; daily at 00:00 UTC.
- Labeling convention: **left-closed, left-labeled** (a bar is labeled by its open time and contains `[open, open+interval)`).
- Prefer native Kraken 240 and 1440 bars. Also resample 4h from 1h and daily from 1h, and **compare** with native bars: report mismatches (price differences and counts). Mismatches above a tolerance (default: close differs by more than 0.01% on more than 0.5% of bars) must stop the pipeline for human review.
- Never mix timeframes silently: every table's interval is part of its name.

## 3.6 Data validation report (required output before any backtest)

Structural checks (hard fail):
- monotonic increasing, unique timestamps, aligned to the interval boundary;
- `high ≥ max(open, close)`, `low ≤ min(open, close)`, all prices > 0, no NaN;
- volume ≥ 0; no negative or absurd values.

Quality checks (report, human decides):
- gap table (3.4); bars with return beyond ±20% (list them); bars with zero volume;
- continuity: median and 99th percentile of `|open_{t+1} − close_t| / close_t`;
- **cross-source comparison on overlapping periods:** daily closes Kraken-EUR vs Bitvavo-EUR (defaults: median absolute difference ≤ 0.15%; flag any day above 0.5%); Kraken-EUR vs Binance (USDT-based, expect larger differences — report only);
- coverage by regime: row counts per year, and explicit confirmation that 2018 bear, 2020 crash, 2021 bull, 2022 bear, and 2023–26 are all present.

The report is a human-readable file; the human approves it (a recorded decision in `DECISIONS.md`) before M3 starts.

---

# 4. Time semantics (the lookahead firewall — read twice)

Definitions:
- A bar with open time `O` and interval `I` **closes at `O + I`**. Its OHLC values are *unknown* before that moment.
- A **decision time** `T` is always a bar close time of that variant's signal timeframe.
- At decision time `T` the strategy may use **only bars with close time ≤ T**.

Rules:
1. **Signals are computed at the close, executed afterwards.** A decision at `T` can only affect orders from `T` onward. Nothing earlier than `T` may depend on it.
2. **Never use an incomplete bar.** In live data, drop any candle whose close time is later than "now". In backtests this means indicators at bar `t` use bars up to and including `t` only, and the action happens after `t` closes.
3. **Daily gate for intraday variants:** at an intraday decision time `T`, the gate is evaluated on the **most recent *daily* bar with close time ≤ T**. At 00:00 UTC that is the day that just ended; at any other hour it is yesterday's daily bar. **Never use today's partial daily bar.**
4. **Base clock for the simulator = 5-minute bars.** Decisions occur only at timeframe closes, but orders, fills and stops are processed on every 5-minute bar. This resolves intrabar ordering (a 1h bar's low and high have no known order; 5m bars constrain it).
5. **Conservative tie-breaks inside one 5m bar:** if a stop level and an exit are both touchable in the same 5m bar, assume the stop triggers first. If a limit entry and a stop could both apply (only in the re-entry case), assume the stop applies first.
6. **No local time, no wall clock** inside strategy, simulator, metrics.
7. **Truncation invariance (testable property):** for any indicator or signal, computing it on data truncated at time `T` must give the same value at `T` as computing it on the full dataset. Tests must verify this (§11).

---

# 5. Indicator definitions (exact)

All indicators use closing prices unless stated.

- **SMA(n):** arithmetic mean of the last n closes, including the current bar. Defined from the nth bar.
- **EMA(n):** smoothing factor `alpha = 2 / (n + 1)`. **Seed** = the simple average of the first n closes, placed at the nth bar; then the standard recursion. (This is the TA-Lib convention; do **not** use "seed with the first value" — the numbers differ for a long time.) **Warm-up:** treat EMA values as invalid until bar index `3 × n`, to remove seed influence.
- **ATR(14):** True Range = max(high−low, |high−previous close|, |low−previous close|). First ATR = simple average of the first 14 TRs; then **Wilder smoothing** (`ATR_t = (ATR_{t−1} × 13 + TR_t) / 14`). **Warm-up:** treat values as invalid until 100 bars.
- **Cross-up event** (fast over slow) at bar t: `fast_t > slow_t` and `fast_{t−1} ≤ slow_{t−1}`. **Fast-above-slow state:** `fast_t > slow_t`. Use strict inequalities exactly as written.

Verification approach (no code here, but required): hand-computed small examples for each indicator in the test suite, plus (optional) agreement with TA-Lib on the same data to within floating-point tolerance.

---

# 6. Strategy decision logic (single implementation shared by backtest and live)

Design: a **pure decision function** — given the closed bars available at `T`, the current position state, and the config, it returns one of: ENTER, EXIT, HOLD (and diagnostic values). It performs no I/O, reads no clock, places no orders. The simulator and the live-signal tool both call it.

## 6.1 Variant definitions (all from `prereg.yaml`)

| | V1 Daily | V2 4h | V3 1h |
|---|---|---|---|
| Decision timeframe | daily | 4h | 1h |
| Entry condition (when flat) | daily close > SMA(200) (**state-based**) | cross-up EMA(50) over EMA(100) **and** daily gate on (**event-based**) | cross-up EMA(20) over EMA(50) **and** daily gate on (**event-based**) |
| Signal exit (when long) | daily close < SMA(200) | fast EMA below slow EMA (state) | fast EMA below slow EMA (state) |
| Trailing stop | none | 3×ATR(14) on 4h | 3×ATR(14) on 1h |
| Disaster stop | −25% of entry fill price (all variants) | same | same |
| Daily gate | (the signal itself) | daily close > SMA(200), most recent closed daily bar | same |

The V1 entry being state-based means that after a disaster-stop exit, V1 re-enters at the next daily close that is above SMA(200) (plan: "next valid entry signal"). V2/V3 re-enter only on a *new* cross-up. Do not "harmonize" these.

## 6.2 Gate semantics for V2/V3

The gate applies to **entries only**. A gate turning off while a V2/V3 position is open does **not** force an exit (exits are the cross-down or the stops), unless the human decides otherwise (listed in §14).

## 6.3 Stop mechanics

- **Initial stop at entry:** `fill_price − 3 × ATR` using the ATR value of the most recent closed signal bar before the fill.
- **Trailing update (V2/V3):** at each later signal-bar close, `candidate = close − 3 × ATR`; the stop becomes `max(current stop, candidate)`. **It never moves down.** The new level is active from the next 5m bar.
- **Disaster stop:** `0.75 × entry fill price`, fixed.
- **Effective stop** = the higher of trailing and disaster stops.
- A stop is **hit** on the first 5m bar whose low ≤ stop level (non-filled-gap bars only).

## 6.4 Sizing

- **V1:** invest 100% of available cash (after reserving the entry fee) when entering.
- **V2/V3:** `stake_EUR = equity × r / stop_distance_fraction`, where `r` is the pre-registered risk fraction (default 1%) and `stop_distance_fraction = (entry price − initial stop) / entry price`; cap at 100% of equity.
- Round the BTC quantity **down** to the exchange quantity step; if the result is below the exchange's minimum order, **skip the trade and log it** as "below minimum".
- Never leverage, never short, never hold two positions.

---

# 7. Execution and fill simulator (implements decision D8)

All parameters below are config values; the numbers in brackets are the plan's defaults.

## 7.1 Entry (maker limit with timeout)

1. At decision time `T` with an ENTER decision: limit price `p = close_T × (1 − half_spread)` (`half_spread` default 0.01% — a placeholder for the best bid; human to confirm). In live trading this must be a **post-only order at the best bid** so it cannot cross the spread (verify the exchange supports it).
2. **Attempt 1 window:** `(T, T + I]` where `I` is the signal interval. On each 5m bar in the window (non-filled-gap bars only), the order **fills if the bar's low is below `p × (1 − through_haircut)`** (default haircut 0.05% — price must trade *through* the limit, not merely touch it). Fill price = `p × (1 + entry_slip)` (slip defaults: V1 0.10%, V2/V3 0.15% — an intentional conservative haircut for adverse selection). Fee = maker fee × notional.
3. If unfilled at `T + I` and the **entry condition is still true** at that close (V1: still above SMA; V2/V3: fast still above slow **and** gate still on — the cross event itself is no longer required), cancel and re-price at the new close (**attempt 2**, window `(T+I, T+2I]`). If the condition is false, cancel and log "signal expired".
4. If unfilled after attempt 2: cancel, log **"missed trade"** (these are counted and reported).
5. Partial fills are ignored in simulation (a fill is complete); the real exchange may partially fill — noted as a known simplification.

**Two modeling choices the human must approve before the lock (§14 items 13–14):**
- **Re-pricing cadence.** The spec re-prices **once**, at the next signal-bar close (two windows total), not on every bar or every 5 minutes. This matches plan v3.2 §4 ("re-price at the next close, up to 2 signal candles total"). If the current plan's D8 wording says something different (for example "re-priced every bar"), the plan and this spec disagree — resolve it by changing one of them and recording the decision in `DECISIONS.md`. The agent must not choose.
- **Conservative fill price.** Real limit orders fill at the limit price **or better**. This model instead fills **worse** than the limit (`p × (1 + entry_slip)`) and *also* requires the through-the-limit haircut, so adverse selection is penalized twice. That bias is deliberate: it makes false positives less likely in a falsification test. The cost is the opposite error — a real edge, especially for the faster variants, can look weaker than it would be live. State the approved bias in `DECISIONS.md`.

## 7.2 Signal exit (market, taker)

- EXIT decision at `T`: sell the whole position at the **open of the first 5m bar at or after `T`**, price = `open × (1 − exit_slip)`, fee = taker fee × proceeds.

## 7.3 Stop exits (market, taker)

- When a stop is hit: if the 5m bar **opens at or below** the stop level, fill at that open (gap case); otherwise fill at the stop level. Then apply `exit_slip` and the taker fee.

## 7.4 Manual-delay option (for Branch A)

Parameter `action_delay_minutes` (default 0). When > 0, **entry orders are placed and signal exits executed this many minutes after `T`** (stops stay on the exchange and are not delayed). The plan's V1 manual branch should be run with a human-realistic delay (default sensitivity value: 360 minutes, i.e., a 06:00 UTC reaction to the 00:00 UTC signal). Both delay=0 and delay>0 results are reported; the pre-registration says which one governs the live branch decision.

## 7.5 Costs summary (from plan v3.2 components)

Round-trip cost = entry fee + entry slip + exit fee + exit slip. With the plan defaults: V1 = 0.15 + 0.10 + 0.25 + 0.10 = **0.60%**; V2/V3 = 0.15 + 0.15 + 0.25 + 0.15 = **0.70%**. (The simulator uses the *components*. If the plan's text still shows lower totals — v3.2 showed about 0.5%/0.6% — those totals understate the modeled cost and the plan's text should be corrected.) Fee values come from `fees.yaml`; if the real tier differs, only config changes.

---

# 8. Accounting and metrics

## 8.1 Ledger

- State: cash (EUR) and BTC quantity. Initial cash: configurable (default €400). Fees are paid from cash. No interest on cash.
- Every fill creates a trade-table row: decision time, order times, fill time, side, price, quantity, fee, slippage cost, reason (signal, trailing stop, disaster stop), variant.
- **Accounting identity (tested):** final equity = initial cash + Σ trade P&L − Σ fees − Σ slippage costs (with open positions marked to market).

## 8.2 Evaluation window

- **Single global start date for all variants, baselines and sensitivities** = the earliest decision time at which **every** indicator of **every** variant (including sensitivity variants) is valid. End = last complete bar of the dataset (document it; likely 2026-09-30 or 2026-06-30, depending on which Kraken quarterly files exist).
- An open position at the end is **marked to market with no exit cost**; buy-and-hold is treated identically (entry cost only), so the comparison is fair.

## 8.3 Metrics (exact definitions)

- **Equity curve for comparisons:** equity sampled at every **daily UTC close** (strategy, buy-and-hold, baselines all on this same grid).
- **CAGR:** `(final equity / initial equity) ^ (365.25 / days in window) − 1`.
- **Max drawdown:** largest peak-to-trough fall of the daily-close equity curve, as a positive fraction. Also report intraday (5m-close) max drawdown as secondary.
- **Calmar:** `CAGR / max drawdown`. If max drawdown is zero, report "undefined" (never divide by zero or invent a value).
- **Exposure:** time-weighted average of `BTC value / equity` over daily closes.
- **Round trips:** completed entry→exit pairs; also report missed trades, trades skipped for minimum size, average hold time, win rate, profit factor, average win/loss, and trades per year.
- **Fee drag:** total fees + slippage divided by average equity, annualized.
- **Secondary (report only, not for gating):** Sharpe and Sortino from daily returns annualized with 365 days.

---

# 9. Baselines (exactly as the plan defines, made precise)

1. **Buy-and-hold:** one entry at the open of the first 5m bar at the evaluation start, paying the taker fee plus V1's entry slippage, held to the end and marked to market (no exit cost).
2. **Cash:** equity stays at the initial amount (0% return).
3. **Exposure-matched buy-and-hold:** take the buy-and-hold **daily returns**, scale each by the strategy's average exposure `e`, and compound. **Frictionless** (a deliberately harder baseline).
4. **Random-timing baseline (position-shift test) — the plan's "random-entry" baseline, defined this way because plain random entries break for V1:**
   - Take the strategy's **position-fraction series** (fraction of equity in BTC) on its decision timeframe.
   - For each draw, **circularly shift** the series by a random number of bars between 10% and 90% of its length. This preserves the number of trades, durations and exposure and destroys the timing relationship to price.
   - Re-compute equity from price returns and the shifted positions; charge costs **per position change** using the strategy's *average realized cost* per unit of position change.
   - ≥ **1,000 draws**, fixed seed from `prereg.yaml`.
   - Compute each draw's Calmar (daily-close basis). Report the **percentile rank** of the strategy's Calmar (fraction of draws with Calmar ≤ the strategy's) and also the rank by CAGR.

---

# 10. Pre-registration enforcement and the verdict generator

## 10.1 Lock and run-once protocol

1. The human finalizes `prereg.yaml` and commits it. The agent produces **`PREREG.lock`** containing the commit hash and the file hash.
2. The backtest runner **refuses to run** (for the real BTC/EUR gate run) unless `PREREG.lock` matches the current files and the working tree is clean.
3. Real-data results are written to a new timestamped directory under `results/` and made **read-only**. A second gate run requires an explicit "exploratory re-run" flag with a mandatory reason; its outputs are stamped **EXPLORATORY — INVALID FOR GATE** in every file and chart.
4. The agent never edits thresholds after a run.

## 10.2 Required run outputs

Metrics JSON per variant (and per sensitivity variant), trade tables, daily-close equity curves, the random-baseline draw results, the data manifest, the config hashes, and the generated report.

## 10.3 Verdict logic (mechanical — implement exactly; thresholds from `prereg.yaml`)

For each variant:

- **C1 (absolute return floor):** if buy-and-hold CAGR > 0: strategy CAGR > 0 **and** ≥ 70% of buy-and-hold CAGR. If buy-and-hold CAGR ≤ 0: strategy CAGR ≥ buy-and-hold CAGR.
- **C2:** strategy CAGR ≥ exposure-matched buy-and-hold CAGR − 2 percentage points.
- **C3:** if buy-and-hold Calmar > 0: strategy Calmar ≥ 1.25 × buy-and-hold Calmar. If buy-and-hold Calmar ≤ 0: strategy Calmar > buy-and-hold Calmar.
- **C4:** percentile rank of the strategy's Calmar in the shifted-position baseline ≥ 95% (report the exact rank).
- **C5 (sanity floor):** round trips ≥ floor (8 / 24 / 60 for V1/V2/V3 per 8 years, scaled by the actual window length in years / 8).
- **C6 (robustness):** each pre-registered sensitivity variant (V1: SMA 150, 250; V2: EMA 30×60, 70×140; V3: EMA 10×30, 30×70) has Calmar above buy-and-hold Calmar (no 1.25 multiplier).
- **Tier A:** C1–C6 all true. **Tier B:** C3, C4, C5 true and (C1 or C2 false). **Tier C:** otherwise.

**Selection (decision D10):**
- If V1 is Tier A: V1 is the default live variant. V2 or V3 replaces it only if it is Tier A **and** its net CAGR ≥ 1.2 × V1's net CAGR **and** its Calmar ≥ 1.2 × V1's Calmar. If both V2 and V3 qualify, pick the higher Calmar (tie → the lower-frequency one). *(The plan does not specify this tie rule — flagged in §14.)*
- If V1 is not Tier A: no default. V2/V3 must each be Tier A on their own; pick the higher Calmar. *(Also flagged in §14.)*
- Output one of: "live variant = X", "Tier B only — human decision", or "Tier C — stop trading-bot track".

The report states these results in plain language with all the numbers, a table of every criterion per variant, the delay=0 vs delay>0 comparison for V1, the missed-trade counts, and the charts: equity curves vs baselines, drawdowns, trades per year, fee drag, random-baseline histogram with the strategy's position marked.

---

# 11. Test plan (the main defense against mistakes)

All tests run on **synthetic data**; none need network access.

**Time and lookahead**
- Truncation invariance for every indicator and for the decision function (§4 rule 7).
- Gate test: an intraday decision at 05:00 UTC must use yesterday's daily close, not today's partial.
- Changing future bars after `T` must not change any decision at or before `T` (mutate the future, re-run, compare).

**Indicators**
- Hand-computed SMA/EMA/ATR examples; EMA seeding and warm-up handling; (optional) TA-Lib agreement.

**Strategy logic**
- Flat series → no trades. Steadily rising series → V1 enters once and never exits; rise-then-fall → one round trip with hand-computed fees.
- Cross detection on a hand-built series: exact bar of the cross; strict-inequality edge cases (equality does not cross).
- V1 re-entry after a disaster stop happens at the next daily close above SMA; V2/V3 re-entry waits for a new cross-up.
- Trailing stop never decreases.

**Execution simulator**
- A limit price that is never traded through → "missed trade" logged, no position.
- Price touching the limit but not trading through by the haircut → no fill.
- Gap-down bar opening below the stop → fill at the open, not at the stop.
- Filled-gap rows never fill orders or trigger stops.
- Re-pricing after attempt 1 happens at the new close only if the condition still holds.
- **Signal-expired path:** the entry condition turns false by the end of attempt 1 → the order is cancelled at that close, "signal expired" is logged, no position is opened and no re-price occurs.
- Minimum-order skip and quantity-step rounding.
- Stop-before-exit tie-break in the same 5m bar.
- With the action delay set, entries/exits happen at the delayed time and stops don't.

**Accounting and metrics**
- The accounting identity holds on every test scenario.
- **Zero-cost** run equals a frictionless hand calculation; **doubling costs** strictly lowers final equity.
- CAGR/drawdown/Calmar match hand-computed values, including the zero-drawdown "undefined" case and negative-CAGR handling.

**Baselines**
- The position shift preserves the number of position changes and exposure exactly.
- The same seed gives identical draws; different seeds differ.
- Buy-and-hold equals price ratio adjusted for the single entry cost.

**Verdict logic**
- A table of crafted metric sets with known expected tiers and selections (including edge cases exactly on each threshold, B&H ≤ 0 cases, and the V1-default rule).

**Parity (Phase 2)**
- The live-signal tool and the backtester, fed identical data, produce **identical decisions** for every bar over the full history.
- The run-once guard rejects a modified `prereg.yaml`.

**Independent cross-check**
- A deliberately simple, slow, loop-based reference simulator for a small synthetic dataset must agree with the main engine on every trade (price, time, fees). Differences are bugs in one of them.

The milestone gate (§13): **no real-data backtest until all of the above pass.**

---

# 12. Phase 2 — live-signal tool

## 12.1 Responsibilities

Once per candle close: fetch recent public candles, compute the chosen variant's decision with the **same decision code**, compare with the saved state, send a Telegram message when something needs a human action, and log everything. It never touches an account.

## 12.2 Inputs and data fetching

- Public Bitvavo candles for the chosen market and the intervals needed (the daily series for SMA(200) with a safety buffer, plus the decision timeframe). The number of candles per request and the interval names come from the **verified** Bitvavo docs (§3.1 "must verify").
- Always drop candles whose close time is in the future relative to "now" (the newest candle may be open).
- Back off on HTTP 429 (Bitvavo reports 1,000 weight points per minute and blocks unauthenticated callers by IP for 15 minutes on breach — so stay far below it); never retry in a tight loop.
- Compare the local clock with the exchange's HTTP `Date` response header; alert if the difference exceeds 2 seconds.

## 12.3 State file (human-readable JSON; atomic writes)

Fields: last processed bar close time; current position state (`flat` or `long`) with the human-confirmed entry price/amount/time; pending-order note; last alert sent and time; consecutive-error count; schema version.

- **The tool never assumes an order filled.** Position state changes only through an explicit human command (`confirm-fill` entry/exit with price and amount, or `confirm-none`) because Branch A executes by hand.
- Writes must be atomic (write new file, then replace) so a crash cannot corrupt state.

## 12.4 Idempotency and catch-up

- Each closed bar is processed **exactly once** (tracked by last processed close time).
- After downtime, process missed bars in order, then apply the **staleness rule** (§12.5) to any resulting action. Never send duplicate alerts for the same bar.

## 12.5 Staleness rule (from the plan, made precise)

- A signal is stale if its bar closed more than 2× the variant interval ago (V1: 48 h, V2: 8 h, V3: 2 h) or the price has moved more than 1×ATR beyond the signal bar's close since.
- **Stale ENTER:** suppress the entry, log it, send an informational "missed entry" message.
- **Stale EXIT:** **do not suppress.** Send an urgent "stale exit — check your position now" alert. *(This is stricter than the plan's wording, which doesn't distinguish entries from exits; flagged in §14 for human approval.)*

## 12.6 Telegram

- Use the official Telegram Bot API `sendMessage` method with the bot token from an environment variable and a chat ID from config (confirm the exact request format in the official docs; do not guess).
- Message types: ENTER, EXIT, STALE-EXIT (urgent), MISSED-ENTRY, DAILY HEARTBEAT (fixed time, includes last processed bar and current state), ERROR, DATA-ANOMALY, CLOCK-SKEW.
- Each ENTER/EXIT message contains: the bar close time, the decision, key indicator values, the limit price to use and the stop level to set (per D8), and a reminder of the 2-candle timeout rule.
- On send failure: retry a few times with backoff, then append to a local alert log; never crash silently.
- **The token must never appear in logs, errors, or the repo.**

## 12.7 Scheduling

- Schedule shortly after each candle close (e.g., a minute or two after the hour/00:00 UTC, so the exchange has published the candle).
- Because the tool is idempotent, missed runs are safe. **Verify empirically** how the chosen macOS scheduler (launchd calendar jobs vs cron) behaves after sleep/wake — do not assume; write the finding in `DECISIONS.md`.
- A daily heartbeat means a silent failure is noticed within a day.

## 12.8 Branch B requirements (future — do not build now)

If the Phase 1 winner trades more often than about once a month, a freqtrade-based bot follows. When that time comes, the requirements are: a pinned freqtrade version; the strategy imports the shared decision code; **signal parity** (not P&L parity — freqtrade's engine differs) verified against the Phase 1 engine; and the following freqtrade capabilities must be **verified in the official docs for the pinned version** before design: entry price control and entry re-pricing/timeouts, order types for exits and stop-loss (market), exchange-hosted stop-loss and how trailing updates replace the exchange order, 1d/4h/1h timeframe handling, and dry-run behavior.

---

# 13. Milestones, acceptance, and human checkpoints

| # | Milestone | Done when | Human checkpoint |
|---|---|---|---|
| M0 | Repo skeleton, environment, config schemas, `DECISIONS.md`, `prereg.yaml` template | Environment reproducible from the lock file; schema validation rejects bad configs | — |
| M1 | Data ingestion (Kraken primary for BTC/EUR, plus ETH/EUR for development runs; Bitvavo and Binance for BTC cross-checks) | Checksums verified; canonical Parquet tables exist; manifest written | — |
| M2 | Data validation report (§3.6) | Report generated; structural checks pass | **Human approves data quality** |
| M3 | Indicators + time-semantics utilities + their tests | Indicator, truncation and gate tests pass | — |
| M4 | Decision logic V1/V2/V3 + tests | Strategy tests pass on synthetic data | — |
| M5 | Execution simulator + accounting + tests (incl. the loop-based reference simulator) | All execution/accounting tests and the cross-check agree | — |
| M6 | Metrics + baselines + verdict logic + tests | Metric, baseline and verdict tests pass | — |
| M7 | Report writer + run-once guard + dry run on **synthetic and ETH/EUR data** | End-to-end run produces a full report; guard blocks edits | **Human locks `prereg.yaml` (creates `PREREG.lock`)** |
| M8 | The one real BTC/EUR run | Results directory written read-only; verdict generated | **Human reads the verdict** |
| M9 | `signal` tool + state, Telegram, heartbeat, parity test | Parity test passes over full history; alerts delivered in a live test | — |
| M10 | Operational rehearsal tooling | Runs unattended for 2+ weeks per plan Phase 2; findings in `DECISIONS.md` | **Human decision on branch (A/B)** |

---

# 14. Decisions the agent must NOT guess (ask the human)

Defaults in brackets are proposals, to be confirmed or changed **before** the pre-registration lock.

1. Chosen exchange and the exact fee tier (maker/taker) — from Phase 0.
2. Minimum order size, quantity step, price tick for BTC/EUR on that exchange.
3. `half_spread` for the limit price [0.01%], `through_haircut` [0.05%], `entry_slip` and `exit_slip` values [V1 0.10%; V2/V3 0.15%].
4. Risk fraction for V2/V3 sizing [1%].
5. `action_delay_minutes` for the Branch A sensitivity run [360] and which result governs the Branch A decision — **answer this in the pre-registration note before the lock, never after seeing results**, otherwise the delay becomes a tuning knob.
6. Whether the daily gate turning off should force a V2/V3 exit [No].
7. Selection tie-breaks: V2 vs V3 when both qualify; behavior when V1 is not Tier A [higher Calmar].
8. Staleness: whether stale EXIT signals are always alerted [Yes].
9. Gap-rate thresholds that stop the pipeline [1% of 5m bars; 0.1% of ≥1h bars after 2018].
10. Data window end date (depends on which Kraken quarterly updates exist).
11. Telegram bot creation and chat ID (human creates; agent only reads the token from the environment).
12. Confirm the plan's text matches the component costs (round trip 0.60% for V1, 0.70% for V2/V3 under the default parameters, §7.5). v3.2 did not; a later version may.
13. **Re-pricing cadence** (§7.1): approve "one re-price at the next signal close" or choose another rule, and make the plan's D8 wording match whichever is chosen.
14. **Conservative fill bias** (§7.1): approve the deliberately worse-than-limit fill price plus through-the-limit haircut, knowing it biases against real edges as well as false ones.

---

# 15. Common mistakes — checklist the agent must self-audit before each milestone

1. Using the bar's own close to fill an order *within the same bar* in which the decision was made.
2. Using today's partial daily candle for the gate; using any candle with close time later than "now".
3. Timestamp units: Binance microseconds (2025+), Kraken unit unstated — always detect by magnitude and assert.
4. Treating Kraken gaps as zero-volume trades; or interpolating prices that never traded.
5. EMA seeded with the first value instead of the SMA of the first n; skipping warm-up discards.
6. Resampling with the wrong label/closure (a bar must be labeled by its open time and be left-closed).
7. Charging fees twice, or on the wrong notional; forgetting slippage on stops; rounding quantities *up*.
8. Letting equity go negative or leveraging by accident; holding two positions.
9. Differing evaluation start dates across variants/baselines; different cost models for strategy vs buy-and-hold.
10. Computing drawdown or Calmar on a different grid for the strategy than for the baselines.
11. Peeking at real BTC/EUR strategy results before the lock; tuning anything after a run.
12. Overwriting results; running without the lock file; editing `prereg.yaml` after the lock.
13. Any wall-clock or local-time dependence in strategy/backtest code; DST effects.
14. Reading large datasets fully into memory; forgetting seeds; non-deterministic ordering.
15. Logging or committing the Telegram token or any key; adding a trading-permission API key "just to test."
16. Re-implementing the strategy in the live tool instead of calling the shared decision code.
17. Assuming a manual order filled; changing position state without the human's confirm command.
18. Treating an unverified fact in §3.1/§12 as true instead of checking the official documentation.

---

# 16. Reference: external facts used by this spec

**Verified from official pages while writing this spec**
- **Bitvavo REST:** base `https://api.bitvavo.com/v2`; private requests need headers for access key, timestamp (ms), HMAC-SHA256 signature (hex; signed string = timestamp + method + path + body, empty body for GET) and an optional access window (default 10,000 ms, max 60,000 ms). API key permissions: read, trade, withdraw. **The docs warn that API withdrawals need no 2FA or email confirmation — so a key must never have withdraw permission.** Rate limit: 1,000 weight points per minute by default; HTTP 429 with error code 105 on breach (authenticated callers blocked 1 minute, unauthenticated 15 minutes per IP); responses carry `bitvavo-ratelimit-limit`, `-remaining`, `-resetat`. Endpoints seen: `GET /{market}/candles`, `GET /markets`, `GET /ticker/price`, `GET /ticker/book`, `GET /ticker/24h`, `POST /order`, `DELETE /order`, `GET /ordersOpen`, `GET /order`, `PUT /order`, `GET /orders`, `DELETE /orders`. Order types: market, limit, stopLoss, stopLossLimit, takeProfit, takeProfitLimit. Order statuses: awaitingTrigger, new, partiallyFilled, filled, expired, canceled.
- **Kraken OHLCVT archive and Binance public data:** as in the §3.1 table.

**Not confirmed (verify in official docs before depending on them)**
- Bitvavo: candle request parameters/limit/intervals/timestamp convention; the **request-side `postOnly` parameter** (the order response shows a `postOnly` field and the lifecycle page mentions post-only cancellations, but the page I read did not define the request parameter); minimum order sizes; weights of endpoints other than create-order; whether a server-time endpoint exists.
- Kraken: the exact BTC/EUR file names, timestamp unit, available timeframes, and the pair's start date.
- Binance: BTCEUR availability and history start; timestamp unit before 2025; daily-file URL pattern.
- Telegram Bot API request format and limits (standard but not re-checked here).
- freqtrade capabilities listed in §12.8.

---

*End of specification v1.1. First action for the agent: M0, then stop at the first human checkpoint (M2) with the data validation report.*
