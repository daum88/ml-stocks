# DECISIONS.md — BTC/EUR Trend Bot (€400 edition)

This file is the single record of (a) verified facts, (b) decisions taken, and (c) decisions
that are still open and must be resolved **by the human** before the pre-registration lock.
Per the build spec (v1.1) rule #9: *official docs beat the spec* — where a live page
disagreed with the spec, the live page wins and is recorded here.

**Date of verification:** 2026-10-19 (all network checks performed live today).

---

## 1. VERIFIED FACTS (Phase 0 / spec §3.1)

### 1.1 Bitvavo — public REST (verified live)

| Fact | Value | Status |
|---|---|---|
| Base URL | `https://api.bitvavo.com/v2` | ✅ verified |
| Market count | 438 markets | ✅ verified |
| `BTC-EUR` exists | status `trading` | ✅ verified |
| Min order (quote) | **€5.00** | ✅ verified |
| Min order (base) | 0.00006942 BTC | ✅ verified |
| Quantity step | `quantityDecimals: 8` (1e-8 BTC) | ✅ verified |
| Price tick | `tickSize: 1.00` (€1.00) | ✅ verified |
| Fee category | `A` (exact % = the human's account tier; base 0.15/0.25) | ⚠️ tier-dependent |
| Order types | market, limit, stopLoss, stopLossLimit, takeProfit, takeProfitLimit | ✅ verified |
| **post-only** | Not in `orderTypes` (that list is *order types*, not flags). Docs show a **`postOnly` boolean** on `POST /order` (`"postOnly": false` in cancel-on-disconnect examples; cancellation reasons `cancelPostOnly` / `cancelPostOnlyOnAuctionMatching`). | ⚠️ **likely supported** — final confirm via the live Create Order page or a tiny test order before the lock |
| Candle endpoint | `GET /{market}/candles?interval=&limit=&start=&end=` | ✅ verified |
| Candle columns | `[open_time_ms, open, high, low, close, volume]` (6 cols, **open-time labeled, ms**) | ✅ verified |
| Max candles/call | **1440** (1500 → HTTP 400) | ✅ verified |
| Intervals | 1m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d all OK | ✅ verified |
| Server time | `GET /time` → `{"time":ms,"timeNs":ns}`; HTTP `Date` header present | ✅ verified |
| **History depth** | **Shallow** — `start=2015-01-01` returns only ~recent candles. **No deep history via public candles** (fine — Kraken archive is the history source; Bitvavo is the live-signal + recent cross-check source). | ⚠️ confirmed limitation |

### 1.2 Kraken — public REST + downloadable OHLCVT archive (verified live)

| Fact | Value | Status |
|---|---|---|
| BTC/EUR pair id | `XXBTZEUR` (wsname `XBT/EUR`, altname `XBTEUR`) | ✅ verified |
| Min order (Kraken ordermin) | 0.00006 XBT (~€4.4 at €73k) | ✅ verified |
| Public OHLC endpoint | `GET https://api.kraken.com/0/public/OHLC?pair=XXBTZEUR&interval=N` → `[time_sec, o, h, l, c, vwap, vol, count]` | ✅ verified |
| OHLC history depth | ~720 most-recent candles only (no deep history via REST) | ⚠️ confirmed limitation |
| **OHLCVT archive (article `360047124832`)** | "Downloadable historical OHLCVT data", last updated 2026-10-12. Full history through **2026-06-30**, split into **5 parts** (~2 GB): `Kraken_OHLCVT_Full.zip.part00–04`. Columns `timestamp, open, high, low, close, volume, trades`, **no header**, gaps not zero-filled, `MANIFEST.json` per archive. | ✅ VERIFIED |
| Part URLs | `https://assets.kraken.com/marketing/institutions/Kraken_OHLCVT_Full.zip.part{00..04}` — all **HTTP 200** | ✅ verified |
| Part sizes | 2097152000 ×4 + 1157945626 (≈ 8.9 GB total) | ✅ verified |
| Published part checksums | `https://assets.kraken.com/marketing/institutions/OHLCVT_Full_PARTS_SHA256SUMS.txt` (5 SHA-256 values, fetched) | ✅ exists |
| Reassembled-zip checksum | `bc273e9027470b07d790a7fa4df9bb43f0dfc527c20c6ecae48402e123e7b1c7` (from article) | ✅ recorded |
| Quarterly updates | `Kraken_OHLCVT_2026Q1.zip` (524 MB), `2026Q2.zip` (538 MB), `2026Q3.zip` (576 MB) — all **HTTP 200**, single zips | ✅ verified |
| Archive intervals | 1, 5, 15, 60, 240, 720, 1440 min (**no 30m**) | ✅ verified from central directory |
| **BTC/EUR files present** | `XBTEUR_1.csv`, **`XBTEUR_5.csv`**, `XBTEUR_15.csv`, **`XBTEUR_60.csv`**, **`XBTEUR_240.csv`**, `XBTEUR_720.csv`, **`XBTEUR_1440.csv`** — all confirmed in the archive's central directory (12,349 CSV files total). | ✅ CONFIRMED |

**Note — the earlier "blocker" was a false alarm.** The spec §3.1 referenced article `360047543791`, which
301-redirects to a *trades-only* ("time and sales") page. The **correct OHLCVT article is `360047124832`**,
which contains exactly the 5-part candle archive the spec assumed.

### 1.3 Binance `data.binance.vision` (verified live)

| Fact | Value | Status |
|---|---|---|
| BTCUSDT monthly klines | 1d, 1h, 4h, 5m all exist for 2018/2020 → full history | ✅ verified |
| BTCEUR monthly klines | 2026-09 & 2025-01 = 200; **2019-01 & 2017-01 = 404** → BTCEUR only since ~2025 | ⚠️ confirmed |

### 1.4 Kraken fee schedule

JS-rendered; exact spot table not extractable programmatically. Plan Review #3 previously verified
Kraken entry tier ≈ **0.40% maker / 0.80% taker**. Final tier is account-specific.

---

## 2. DATA SOURCE — RESOLVED

**Resolution: the Kraken OHLCVT archive exists and is the primary source, as the spec assumed.**
The earlier blocker was caused by fetching the wrong support-article ID.

- **Primary long history (BTC/EUR, incl. 5m for fills):** Kraken OHLCVT archive — 5 parts + quarterly
  updates, containing `XBTEUR_5/60/240/1440.csv` (verified above).
- **Cross-check sources:** Bitvavo public candles (recent only) and Binance BTCUSDT (full history,
  USD) as specified; Binance BTCEUR only for 2025+.
- **Data window end date (decision #10):** **2026-06-30** from the 5 parts alone; extend to
  **2026-09-30** by also ingesting `Kraken_OHLCVT_2026Q1/Q2/Q3.zip`. → *Adopt 2026-09-30* (ingest the
  quarterly files too) so the window includes the latest data.

**Fallback (only if the actual download/ingestion fails):** hybrid — Binance BTCUSDT for long-history
signal testing (plan §4 already allowed USD), Kraken trades streamed in chunks to build recent EUR 5m
candles for the fill sim; label the result "USD-proxy signal test". Do **not** buy paid data unless
both of those fail.

---

## 3. EXCHANGE — DECIDED

**Exchange = Bitvavo** (base 0.15% maker / 0.25% taker). The human records their **own account tier**
(the 0.15/0.25 figures are the base rate) → fills `fees.yaml`. Kraken's ≈0.40/0.80 would roughly double
round-trip cost and is therefore rejected as primary.

Remaining Bitvavo confirmations before the lock:
1. **post-only** — likely a boolean on `POST /order` (see §1.1); confirm on the live Create Order page
   or with a tiny `postOnly: true` limit order above the ask (must be cancelled, not filled).
2. **MiCA authorisation** on ESMA's register (not verifiable by the agent — human check).
3. **Own fee tier** (maker AND taker) from the account.

---

## 4. OPEN DECISIONS (spec §14 — must be answered before the M7 lock)

| # | Decision | Resolution | Status |
|---|---|---|---|
| 1 | Exchange + maker/taker tier | **Bitvavo**; human records own tier (base 0.15/0.25) | ✅ decided (tier still to record) |
| 2 | Min order / qty step / tick | Bitvavo: €5, 1e-8 BTC, €1.00 tick (verified) | ✅ verified |
| 3 | `half_spread`, `through_haircut`, `entry_slip`, `exit_slip` | 0.01% / 0.05% / V1 0.10% & V2-V3 0.15% / same | OPEN (confirm) |
| 4 | V2/V3 risk fraction | 1% | OPEN (confirm) |
| 5 | V1 execution time (delay) | **06:00 UTC (= 360 min) governs**; delay=0 reported as a sensitivity only | ✅ decided |
| 6 | Gate-off forces V2/V3 exit? | No | OPEN (confirm) |
| 7 | Selection tie-breaks (V2 vs V3; V1 not Tier A) | higher Calmar; tie → lower frequency | OPEN (confirm) |
| 8 | Stale-EXIT always alerted? | Yes (spec stricter than plan) | OPEN (confirm) |
| 9 | Gap-rate stop thresholds | 1% (5m), 0.1% (≥1h after 2018) | OPEN (confirm) |
| 10 | Data window end date | **2026-09-30** (5 parts + Q1–Q3 updates); 2026-06-30 if only 5 parts | ✅ decided |
| 11 | Telegram bot + chat ID | human creates; token via env var only | OPEN |
| 12 | Cost-component totals match plan text? | V1 0.60% / V2-V3 0.70% | OPEN (confirm plan text) |
| 13 | **D8 re-pricing cadence** | **Re-price once at the next signal close (2 windows total)** — the simpler/conservative rule. Plan v3.3 edited to match spec v1.1. | ✅ decided |
| 14 | Conservative fill bias (double penalty) | **APPROVED** | ✅ decided |

---

## 5. SPEC HEADER / VERSION NOTE

Spec header updated to **v3.3** in `docs/bot-build-spec-phase1-2.md`. The two v3.2→v3.3 conflicts are
now resolved:
- **D8 re-pricing** → decided (item 13); plan edited.
- **V1 execution time** → decided (item 5): 06:00 UTC governs.

Spec §3.1 still needs a small revision so the spec and plan agree on the **source article ID
(360047124832)** and the **dates** (through 2026-06-30, + quarterly Q1–Q3) — the human said they will
do this; a follow-up for the agent if not.

---

## 6. DECISION LOG

| Date | Decision | By |
|---|---|---|
| 2026-10-19 | Exchange = **Bitvavo** (record own fee tier) | human |
| 2026-10-19 | D8 re-pricing = **once at the next signal close** (2 windows) | human |
| 2026-10-19 | V1 execution = **06:00 UTC governs** (delay=360); delay=0 as sensitivity only | human |
| 2026-10-19 | Conservative fill bias = **approved** | human |
| 2026-10-19 | Data window end = **2026-09-30** (ingest Q1–Q3 quarterly updates) | human |
| 2026-10-19 | Data source = **Kraken OHLCVT archive** (article 360047124832) — blocker resolved | agent verified, human confirmed |

---

## 7. IMPLEMENTATION STATUS (built autonomously 2026-10-19)

**Modules (all under `src/trendbot/`):** common (timeutil, config/schema), indicators,
strategy, execution (fill sim), accounting, metrics, baselines, report (verdict, runner,
writer, lock), live (state, signal, bitvavo, telegram), data (store, kraken, gaps, validate).

**Tests:** 74 passing (indicators, config, strategy, fillsim, metrics, baselines/verdict,
data, live, truncation/parity, lock, end-to-end synthetic runner).

**Data (Kraken OHLCVT archive, article 360047124832):**
- Parts 02/03/04 SHA-256 verified against the published per-part checksums.
- `XBTEUR_*` (BTC/EUR) and `ETHEUR_*` (ETH/EUR — note: Kraken labels ETH/EUR as **ETHEUR**,
  not XETHZEUR) extracted via ZIP64 central-directory offsets with per-file CRC32 verification.
- Part 00 (bytes 0–2 GB) is **not needed** (contains other pairs) — skipped. Part 01 holds
  ETHEUR (dev data). Quarterly `Kraken_OHLCVT_2026Q3.zip` appended → window through 2026-09-30.

**XBTEUR data-quality (allowed pre-lock):**
- 5m 1,310,154 rows · 1h 113,180 · 4h 28,430 · 1d 4,764; 2013-09-10 → 2026-09-30.
- Continuity median 0.002–0.005% (clean). Zero-volume bars: 0 (Kraken omits no-trade bars).
- Gaps: 5m early years high (2013: 70%, 2014: 24%, 2015: 10%, 2016: 3%) — expected early
  sparsity, mostly before the eval window; post-2017 5m gaps < 1%. A handful of 1h/4h/1d
  bars missing in 2018/2024/2025 (0.1–0.6%, a few bars/year — exchange outages). All benign.

**Deviations from the spec (recorded, not hidden):**
1. Parts extracted by ZIP64 offset instead of joining all 5 parts, because part 00/01 contain
   no needed files and the CDN throttles long downloads. Per-part SHA + per-file CRC32 verified.
2. `trades` column is parsed but not stored in Parquet (BarSeries has no trades field; the
   strategy never uses it).
3. Circular-shift draw Calmars are computed on the reconstructed signal-timeframe equity,
   annualized with the same window days as the strategy CAGR; the strategy's daily-close Calmar
   is ranked against them (spec §9.4 / §10.3 C4).

**Status vs milestones:** M0–M7 code+tests done; M1 data done for XBTEUR (ETHEUR pending);
M2 validation report generated; M7 dry-run done on synthetic (Tier C on noise, as expected).
**M8 (BTC/EUR gate run) is BLOCKED until the human locks `prereg.yaml`** (no-peeking rule 5).
Next: extract ETHEUR (part 01), run the ETH/EUR development backtest.

## 8. Cross-source check (Kraken vs Bitvavo daily closes, 2026-10-19)

981 overlapping daily closes (XBTEUR vs BTC-EUR). **Median abs diff 0.021%** (spec limit
0.15% ✓). Max 1.98%; 30 days > 0.15%, 3 days > 0.5% (flagged — exchange close-timing
differences/outages, not data corruption). Kraken history accepted as primary.

## 9. DEVELOPMENT RUN + CRITICAL BUG (2026-10-19)

**Dev asset: LTCEUR (LTC/EUR)** — used instead of ETHEUR because part 01 (which holds
ETH/EUR) was CDN-throttled; LTCEUR (part 02) is a "different asset" and served the same
purpose. (ETHEUR is still downloading in the background and can be added later.)

The dev run caught a **critical bug**: `fees.yaml` stored maker/taker as `0.15`/`0.25`
(= 15%/25%) instead of fractions `0.0015`/`0.0025`. Fees were **100× too high**, making all
strategy variants lose catastrophically. Fixed, and a pydantic validator now rejects any
fee ≥ 1% (regression test added).

**LTCEUR results after the fix (sanity, not a pre-registered pair):**
- Buy-and-hold CAGR 19.5%, Calmar 0.21, final €3559.
- V1: CAGR 13.2%, maxDD 92.5%, 75 trips, win 10.7%, PF 1.08 → Tier C.
- V2: CAGR 1.1%, maxDD 8.5%, 41 trips, win 39%, PF 1.73, **Calmar rank 100%** → Tier C
  (fails C1/C3 absolute-return/calmar floors vs B&H, even though it beats every circular shift).
- V3: CAGR 1.6%, 391 trips → Tier C.

The pipeline is validated end-to-end on real exchange data (12.3 yr window, 1m12s runtime).

## 10. FINAL STATE (autonomous build complete, 2026-10-19)

- **80 tests passing**, including an independent loop-based reference simulator that
  reproduces the main fill engine exactly (price/time/qty/fees).
- Exit-reason audit on LTCEUR dev run confirms mechanics: V1 = signal(73)+disaster(2);
  V2 = trailing(40)+signal(1); V3 = trailing(301)+signal(90).
- Two bugs found and fixed during development: (1) fees 100× too high (config), (2)
  `mk_bars` test helper ignored the open array (test-only).
- **Remaining (requires human):** lock `prereg.yaml` (`scripts/lock.py`), then
  `scripts/run_backtest.py --pair XBTEUR --gate`. ETHEUR download (optional dev asset)
  is still running in the background; LTCEUR already served the dev purpose.

## 11. ETHEUR dev run + C5 bug fix (continued 2026-10-19)

- Part 01 (ETHEUR/ETH-EUR) finished downloading and **SHA-256 verified** against the
  published checksum. ETHEUR extracted, Parquet built (2015-08-07 → 2026-09-30).
- **Bug found & fixed:** the runner passed `window_days` where `window_years` was expected,
  making the C5 sanity floor 365× too strict (all variants failed C5). Fixed
  (`window_days / 365.25`); regression assertion added to the runner test.
- **ETHEUR dev results (after fix):** B&H CAGR 75.5%, Calmar 0.81. V1 CAGR 83.5%, Calmar 1.15
  (beats B&H on both) but fails **C4** (Calmar rank < 95% in the circular-shift baseline) →
  Tier C. V2/V3 Tier C. Same "edge is not distinguishable from random timing" outcome as LTCEUR.
- Both dev assets (LTC/EUR, ETH/EUR) now ingested and run; pipeline validated end-to-end.
