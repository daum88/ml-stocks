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
| Fee category | `A` (exact % still needs the human's account tier) | ⚠️ tier-dependent |
| Order types | market, limit, stopLoss, stopLossLimit, takeProfit, takeProfitLimit | ✅ verified |
| **post-only** | **NOT in `orderTypes`** — request-side `postOnly` flag unverified | ❌ UNVERIFIED (D8 depends on it) |
| Candle endpoint | `GET /{market}/candles?interval=&limit=&start=&end=` | ✅ verified |
| Candle columns | `[open_time_ms, open, high, low, close, volume]` (6 cols, **open-time labeled, ms**) | ✅ verified |
| Max candles/call | **1440** (1500 → HTTP 400) | ✅ verified |
| Intervals | 1m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d all OK | ✅ verified |
| Server time | `GET /time` → `{"time":ms,"timeNs":ns}`; HTTP `Date` header present | ✅ verified |
| **History depth** | **Shallow** — `start=2015-01-01` returns only ~recent candles (oldest 2026-10-15 for 1d). **No deep history via public candles.** | ⚠️ confirmed limitation |

### 1.2 Kraken — public REST + downloadable archive (verified live)

| Fact | Value | Status |
|---|---|---|
| BTC/EUR pair id | `XXBTZEUR` (wsname `XBT/EUR`, altname `XBTEUR`) | ✅ verified |
| Min order (Kraken ordermin) | 0.00006 XBT (~€4.4 at €73k) | ✅ verified |
| Public OHLC endpoint | `GET https://api.kraken.com/0/public/OHLC?pair=XXBTZEUR&interval=N` | ✅ verified |
| OHLC row format | `[time_sec, open, high, low, close, vwap, volume, count]` (**seconds**, 8 fields) | ✅ verified |
| OHLC intervals | 5 and 1440 confirmed; format standard | ✅ verified |
| **OHLC history depth** | **~720 most-recent candles only.** `since=2015-01-01` still returns 2024-10-29 → 2026-10-19. **Deep history NOT available via public OHLC.** | ⚠️⚠️ confirmed limitation |
| **Downloadable OHLCVT archive** | **The spec's OHLCVT article URL now 301-redirects to "Downloadable historical market data (time and sales)"** — that page describes **trade/tick data only**, NOT OHLC candles. | ❌⚠️ CRITICAL — see §2 |

### 1.3 Binance `data.binance.vision` (verified live)

| Fact | Value | Status |
|---|---|---|
| BTCUSDT monthly klines | 1d, 1h, 4h, 5m all exist for 2018/2020 → full history available | ✅ verified |
| BTCEUR monthly klines | 2026-09 and 2025-01 = 200 (exists); **2019-01 and 2017-01 = 404** → BTCEUR only since ~2025 | ⚠️ confirmed |

### 1.4 Kraken fee schedule

The fee page is JS-rendered; the exact spot maker/taker table could not be extracted
programmatically. The plan (Review #3) previously verified **Kraken entry tier ≈ 0.40% maker
/ 0.80% taker**. The page now also advertises "Cross-platform Fee Tiers". Final tier is
**account-specific — the human must check their own account.**

---

## 2. CRITICAL BLOCKER — primary candle data source

The spec §3.1 designates **"Kraken OHLCVT archive"** as the **primary long-history BTC/EUR
candle source** (incl. 5m for fills). The verification above shows:

1. The spec's OHLCVT support-article URL now redirects to a **time-and-sales (trades-only)**
   page. Its columns are `timestamp, price, volume, type, order_type, misc, trade_id` (with
   a header) — i.e. **raw trades, not OHLC candles**.
2. The trades archive is split into **14 parts** (`Kraken_Trades_Full.zip.part00`…`part13`,
   ~2 GB each, ≈28 GB total) through **2026-09-30** (spec said "5 parts" / "2026-06-30" —
   both outdated), with quarterly updates `Kraken_Trades_2026Q1/Q2/Q3.zip` and published
   SHA-256 sums.
3. Kraken's public **REST OHLC returns only ~720 recent candles** per interval — no deep
   history.
4. Bitvavo public candles are **recent-only**.
5. Binance **BTCEUR exists only since ~2025** (404 for 2017/2019). Binance **BTCUSDT** has
   full history, but is USD, not EUR.

**Consequence:** as of today there is **no free public EUR-denominated BTC candle archive
covering 2018–2026** that matches the spec's assumption. The spec §3.1 is explicit:
*"If any source cannot be obtained, stop and report; do not substitute another source
silently."* → **This is a stop-and-report point.**

**Options to consider (human decision required — do not proceed until resolved):**

- **A. Confirm the OHLCVT archive still exists somewhere.** (One more targeted search of
  Kraken support / asset URLs before declaring it gone — flagged as a follow-up.)
- **B. Aggregate candles from Kraken's trades archive** (~28 GB raw trades → build 5m/1h/4h/1d
  OHLCV). Feasible but violates the spec's ~3 GB RAM budget and the "read in chunks" rule;
  would need a dedicated chunked aggregation pipeline and a scope/memory review.
- **C. Use Binance BTCUSDT (USD) for long history** and accept the EUR/USD mismatch, with
  EUR cross-checks only on 2025+ (Binance BTCEUR) and recent Bitvavo/Kraken EUR data. The
  plan §4 actually allowed "BTC-USD 2014+ daily cross-checked vs exchange EUR data 2018+",
  but the spec tightened this to EUR-only — needs an explicit plan-vs-spec decision.
- **D. A paid or third-party EUR dataset** (not free; violates "cheapest/free" assumptions —
  needs explicit sign-off and source verification).

**This decision blocks M1 (data ingestion) and therefore everything after it.**

---

## 3. Exchange choice implication (plan D5)

The plan's entire cost model uses **Bitvavo base 0.15% maker / 0.25% taker**. If the chosen
exchange ends up Kraken (≈0.40/0.80), round-trip cost roughly **doubles** (V1 ≈1.2%+,
V2/V3 ≈1.4%+), which would radically change the falsification results (V3's 10.5–28%/yr
drag → ~30–80%/yr). Key tensions for the human:

1. **Post-only (D8):** Kraken documents Post-Only time-in-force; Bitvavo's order-type list
   has no post-only entry and its request-side `postOnly` flag is **unverified**. If Bitvavo
   lacks true post-only, the cheaper fee may be unobtainable for maker entries.
2. **Minimum order:** Bitvavo €5 / Kraken 0.00006 XBT — both clear €400 trivially. ✅
3. **MiCA status, stop-order support, own-tier fees:** all still need the human's account
   check (not verifiable by me).

**Open human decision: choose the exchange (and record maker/taker tier) → fills `fees.yaml`.**

---

## 4. OPEN DECISIONS (spec §14 — must be answered before the M7 lock)

Defaults below are proposals from the plan/spec. **Bold** items are the ones that also block
the pre-registration note.

| # | Decision | Proposed default | Status |
|---|---|---|---|
| 1 | Exchange + maker/taker tier | Bitvavo base 0.15/0.25 (unconfirmed tier) | **OPEN** |
| 2 | Min order / qty step / tick | Bitvavo: €5, 1e-8 BTC, €1.00 tick (verified) | ✅ verified, record in `fees.yaml` |
| 3 | `half_spread`, `through_haircut`, `entry_slip`, `exit_slip` | 0.01% / 0.05% / V1 0.10% & V2-V3 0.15% / same | OPEN (confirm) |
| 4 | V2/V3 risk fraction | 1% | OPEN (confirm) |
| 5 | `action_delay_minutes` + which result governs Branch A | delay=0 and 360 both reported; plan says V1 = 06:00 UTC | **OPEN (plan vs spec conflict)** |
| 6 | Gate-off forces V2/V3 exit? | No | OPEN (confirm) |
| 7 | Selection tie-breaks (V2 vs V3; V1 not Tier A) | higher Calmar; tie → lower frequency | **OPEN** |
| 8 | Stale-EXIT always alerted? | Yes (spec is stricter than plan) | OPEN (confirm) |
| 9 | Gap-rate stop thresholds | 1% (5m), 0.1% (≥1h after 2018) | OPEN (confirm) |
| 10 | Data window end date | depends on source (see §2) | **OPEN — blocked by §2** |
| 11 | Telegram bot + chat ID | human creates; token via env var only | OPEN |
| 12 | Cost-component totals match plan text? | V1 0.60% / V2-V3 0.70% | OPEN (confirm plan text) |
| 13 | **D8 re-pricing cadence** | plan v3.3: "re-priced **every bar**, up to 2 candles"; spec v1.1: re-price **once at next signal close**. **One doc must change.** | **OPEN — spec says agent must NOT choose** |
| 14 | Conservative fill bias (double penalty) | approve? | **OPEN** |

---

## 5. SPEC HEADER / VERSION NOTE

The spec's header line still reads *"written against v3.2"*; the current plan is **v3.3**.
Most v3.3 corrections (trade-through fill, 0.60/0.70 costs, circular-shift baseline) are
already absorbed into the spec body, but the header must be updated and **item 13 (D8
re-pricing) and item 5 (V1 execution time) must be reconciled between the two documents**
before handing the spec to the coding agent.

---

## 6. DECISION LOG

*(Empty — no decisions have been formally made yet. Phase 0 is in progress.)*
