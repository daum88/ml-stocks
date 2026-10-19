# Trading Bot Plan v3.3 — €400 Capital-Efficient, Frequency-Ladder Edition

**Account:** €400 spot, no leverage · **Host:** the MacBook you already own (€0)
**Prepared:** 2026-10-19 · **Replaces:** v3.2
**Status:** Phase 0 is the next action.

> ⚠️ Not financial advice. This plan cannot guarantee profit, and crypto can lose most of its value.
> Only use money you can afford to lose. Tax items must be confirmed with EMTA / a licensed advisor.

---

# 1. What changed from v3.2, and why

| v3.2 | v3.3 | Reason |
|---|---|---|
| Limit fills "if next bar's low touches the limit" | **Fill requires price to trade THROUGH the limit by ≥ 0.05%, simulated on 5-minute bars** | A bar's low sits at or below its open ≈ the prior close ≈ the limit price, so touch-fill fired on almost every bar and the adverse-selection bias wasn't modeled |
| Plain limit orders | **Post-only at the best bid** (verify exchange support in Phase 0) | A limit at last traded price can cross the spread and fill as taker |
| Random-entry baseline (same exits) | **Circular-shift baseline**: shift the strategy's own position series by a random offset (≥1,000 draws); report percentile rank | Random entry was undefined for V1 (a random entry below the SMA exits next day). Shifting preserves trade count, hold times and exposure — tests timing only |
| V2/V3 round trip "0.6%" | **0.70%** (my own model: 0.15+0.15+0.25+0.15). V1 = 0.60% | v3.2's table contradicted its own fee components. V3 drag = 10.5–28%/yr |
| Branch A executes "on signal" | **Pre-registered execution time: 06:00 UTC** (next day for daily signals), modeled in Phase 1 | A human placing orders hours after the 00:00 UTC signal faces 1–2% moves — larger than the modeled costs |
| "≈40–60% allocation" for V2/V3 | **33–50%** (€133–200 at 1% risk) | The v3.2 table's own numbers said 33–50% while the text said 40–60% |
| Drag quoted on full capital | **Drag on invested notional, with the allocation effect stated** | At ~40% allocation, V2/V3 pay roughly half the full-capital drag; both numbers matter |
| "Calendar schedulers do not fire missed jobs" | **cron doesn't; launchd's missed-job behavior unverified — idempotent design makes it harmless either way** | Don't assert unverified OS behavior in a pre-registered plan |
| freqtrade assumed able to implement D8 | **Phase 2 verification item: confirm freqtrade's entry re-pricing, post-only and stoploss order types can implement D8; else fall back to ccxt script or manual** | Branch B is only valid if the engine can execute the exact pre-registered rule |
| Appendix A: "my Sharpe sim was wrong" | Reworded: the **v2 log's 0.1%** was wrong for 12-month windows (my simulation compared a non-annualized monthly Sharpe against the annualized threshold); Review #4's figures are correct | The log should record the error precisely and credit correctly |

---

# 2. The economics at €400 (read this first)

**Fixed costs decide small accounts.** A €5/month VPS is 15% of capital per year.
It stops mattering only when capital is large: €60/yr is 2% of capital at €3,000.

**Fee drag is the frequency tax — corrected model** (Bitvavo base tier; confirm your
own tier in Phase 0). Round trips: V1 = 0.60% (maker entry 0.15 + slippage 0.10, taker
exit 0.25 + slippage 0.10); V2/V3 = 0.70% (0.15 + 0.15 + 0.25 + 0.15):

| Variant | Est. round trips/yr | Round-trip cost | Drag on **invested** capital/yr |
|---|---|---|---|
| V1 daily (SMA-200) | 2–6 | 0.60% | **1.2–3.6%** |
| V2 4h (EMA 50×100) | 6–15 | 0.70% | **4.2–10.5%** |
| V3 1h (EMA 20×50) | 15–40 | 0.70% | **10.5–28%** |

**Allocation effect:** V1 invests 100% when on; V2/V3 at the default 1% risk sizing are
~33–50% allocated (€133–200), so their drag on *total* capital is roughly 40% of the
table above. Fees are paid on invested notional — both views are reported in §10.

**Illustrative annual outcomes** (V1: 4 round trips/yr, 0.6% round-trip, 22% tax on net
gain, no VPS). Scenarios, not forecasts:

| Strategy gross return | Gross P&L | Fees | Tax | Net |
|---|---|---|---|---|
| +40% | +€160 | €10 | €33 | **+€117** |
| +20% | +€80 | €10 | €15 | **+€55** |
| +10% | +€40 | €10 | €7 | **+€23** |
| 0% | €0 | €10 | €0 | **−€10** |
| −20% | −€80 | €10 | €0 | **−€90** |

**The sizing paradox, variant-aware:**

| Variant | Normal stop | 1% risk sizing at €400 | Pre-registered choice (default) |
|---|---|---|---|
| V1 | −25% disaster stop | €16 stake (4%) — trivial | **100% allocated when signal on** |
| V2/V3 | 3×ATR ≈ 2–3% | €133–200 stake (**33–50%**) | **Sizing formula with risk = 1%** |

**Pick exactly one risk% (default 1%) in the pre-registration note.** This is a
deliberate risk decision (§7), bounded by the 30% review trigger.

**Honest expectation.** With a real edge: tens of euros to ~€100/yr at €400. Without an
edge: −€50–100/yr. The dominant lever on absolute earnings is capital; the test's job is
to find out whether an edge exists at all before money is spent. Higher frequency is a
risk multiplier on both sides. Expectation to be tested: V3 likely does not survive the
corrected cost model (10.5–28%/yr drag) once fill bias is modeled — if so, the plan has
answered "does volume pay at €400?" with a clear no.

---

# 3. Locked decisions

| # | Decision |
|---|---|
| D1 | **Falsify first, free.** Vectorized test on 8+ years of free data before any bot, API key or money |
| D2 | **One pre-registered spec family, tested once each** on the full history. Criteria frozen before results (§5). The variants are correlated — the criteria, not a test count, are the false-positive control |
| D3 | **Clean frequency ladder on BTC/EUR:** V1 daily SMA-200 · V2 4h EMA 50×100 · V3 1h EMA 20×50 — identical structure (same daily trend gate, same stop logic), only timeframe and lengths differ |
| D4 | **Baselines:** buy-and-hold, cash, exposure-matched buy-and-hold, and the **circular-shift timing baseline** (position series shifted by random offsets, ≥1,000 draws, percentile rank reported) |
| D5 | **Cheapest compliant exchange wins.** Verify tier, MiCA status, stop-order support, minimum order, **and post-only support**. Bitvavo base 0.15%/0.25% vs Kraken entry tier 0.40%/0.80% (public schedules; confirm your own tier; Kraken documents Post-Only time-in-force) |
| D6 | **No VPS, no Docker, no ML** until capital justifies them (§10). Laptop branch uses caffeinate + exchange stops |
| D7 | **Execution matches frequency:** ≤1 signal/month → manual (Branch A); more → lightweight freqtrade bot on the laptop (Branch B). Branch decided by the Phase 1 winner |
| D8 | **The execution rule (defined once, simulated in Phase 1, followed live):** entries are **post-only** limit orders at the **best bid**, filled in simulation only when price **trades through the limit by ≥ 0.05%** on 5-minute bars; re-priced every bar for up to **2 signal candles**, then cancelled (missed trade logged). Exits and stops are **taker** (market) — no waiting on limit exits. V1 executes at the **pre-registered time 06:00 UTC** (next day after a daily signal); V2/V3 execute at the next bar open. No other ad-hoc behavior |
| D9 | **Exchange-hosted disaster stop on every position**, verified before going live |
| D10 | **Selection rule (pre-registered):** V1 is the default. V2 or V3 replaces it only if it beats V1 on **both** net CAGR and Calmar by ≥ 20% (relative) while passing Tier A itself. If V1 fails Tier A, no variant goes live on the default; V2/V3 would each need Tier A on their own |
| D11 | **"No edge" is a valid result.** Then hold/DCA or do nothing |

---

# 4. The strategy family (pre-registered, all BTC/EUR spot)

Common to all variants:
- Decision only on **closed** candles (daily UTC / 4h / 1h — never the incomplete candle).
- **Daily trend gate:** daily close above SMA(200) required for any entry (identical for
  all three — the ladder isolates frequency, not filters).
- **Trailing stop:** 3×ATR of the variant's timeframe (V2/V3). V1 has no trailing stop —
  the signal itself is the exit; the disaster stop covers offline risk.
- **Disaster stop:** −25% from entry, hosted on the exchange, for all variants.
- Re-entry after a disaster stop: next valid entry signal.
- Data: BTC-USD 2014+ daily (cross-checked vs exchange EUR data 2018+); 4h/1h from
  public sources 2018+; **5-minute bars (public source, e.g. Binance data dumps,
  cross-checked) for the fill simulation**; must span 2018 bear, 2020 crash, 2021 bull,
  2022 bear, 2023–26.

**Cost and fill model in the test (this is D8 in simulation):**
- Entry: post-only limit at the best bid at decision time. Fill only if a 5m bar's low
  trades **through** the limit by ≥ 0.05% (low ≤ limit × 0.9995 for buys). Unfilled →
  re-price at the current best bid each bar, up to 2 signal candles, then cancel
  (missed trade logged). Fees: maker 0.15% + slippage 0.10% (V1) / 0.15% (V2/V3).
- Decision times: V1 = 06:00 UTC (pre-registered human execution time; the daily signal
  is evaluated on the candle closed at 00:00 UTC); V2/V3 = next bar open (bot timing).
- Signal exit: taker at the decision time, fee 0.25% + slippage 0.10% (V1) / 0.15% (V2/V3).
- Stop/trailing/−25% disaster: executes at the stop price as taker with slippage; if the
  bar gaps beyond the stop, fill at the next open (worse case).

| Item | V1 — Daily | V2 — 4h | V3 — 1h |
|---|---|---|---|
| Signal | Daily close × SMA(200) | EMA(50) × EMA(100) on 4h | EMA(20) × EMA(50) on 1h |
| Entry | Close above SMA(200), in EUR | Fast crosses above slow AND daily gate on | Fast crosses above slow AND daily gate on |
| Exit | Close below SMA(200) | Opposite cross, or 3×ATR(4h) trailing stop | Opposite cross, or 3×ATR(1h) trailing stop |
| Est. round trips/yr | 2–6 | 6–15 | 15–40 (Phase 1 counts) |
| Sanity floor over 8 yr (half the low-end estimate) | ≥ 8 | ≥ 24 | ≥ 60 |
| Round-trip cost (modeled) | 0.60% | 0.70% | 0.70% |
| Drag on invested capital | 1.2–3.6%/yr | 4.2–10.5%/yr | 10.5–28%/yr |
| Sensitivity (robustness only, not for selection) | SMA 150/250 | EMA 30×60 / 70×140 | EMA 10×30 / 30×70 |

---

# 5. Pre-registered pass criteria (edit BEFORE running, then freeze in git)

Metrics: net CAGR after costs, max drawdown, **Calmar = CAGR ÷ max drawdown**.

**Tier A — go:**
1. **Absolute return floor:** Net CAGR > 0 AND ≥ 70% of full-window buy-and-hold CAGR
   when B&H CAGR > 0. If B&H CAGR ≤ 0: require strategy CAGR ≥ B&H CAGR (lose less).
2. Net CAGR ≥ exposure-matched buy-and-hold CAGR − 2 percentage points.
3. Calmar ≥ 1.25 × buy-and-hold Calmar.
4. Calmar above the 95th percentile of ≥ 1,000 **circular shifts** of the strategy's own
   position series (random offsets preserve trade count, hold times and exposure — tests
   timing only). **Report the percentile rank**, not just pass/fail.
5. Meets its variant's sanity floor (§4 table).
6. Its sensitivity variants also beat buy-and-hold Calmar.

**Tier B — lower-risk alternative only:** Calmar conditions (3, 4) pass but the return
conditions (1, 2) fail. It reduces drawdown but does **not** earn more than holding. Go
only for the smoother ride, not for earnings.

**Tier C — stop:** anything else. Do not tune. Choose between buy-and-hold/DCA and nothing.

**Selection (D10, pre-registered):** default V1. V2/V3 replace V1 only if they pass Tier A
themselves AND beat V1 on **both** net CAGR and Calmar by ≥ 20% relative. Otherwise the
live variant is V1 (if V1 passes Tier A) — a faster variant that merely ties does not
win, because its extra model risk is uncompensated.

**Caveat on evidence:** BTC has only about two full cycles in the history. Even Tier A is
weak evidence, which is why live capital stays small and reviewed (§8, §11). Variants that
fail only on fee drag (gross edge positive, net negative) are reported as such.

---

# 6. Phases

## Phase 0 — Exchange check (1–2 days, €0)
- [ ] Check fees for **your** account tier at Bitvavo and Kraken (maker AND taker).
- [ ] Verify MiCA authorisation on ESMA's register for the chosen entity.
- [ ] Verify the exchange supports a **stop-loss order on spot** (app or API).
- [ ] Verify **post-only order support** (Kraken documents Post-Only time-in-force;
      Bitvavo to be checked) — D8 depends on it.
- [ ] Verify the minimum order for BTC/EUR and that €400 (and the €10–20 rehearsal
      trade) clears it.
- [ ] Record all of it in DECISIONS.md with sources. Choose the exchange.

## Phase 1 — Falsification (1–2 weeks, €0)
- [ ] Write the pre-registration note (§4 + §5 + D8 + D10 + the chosen risk% for V2/V3)
      and commit it to git **before** running anything.
- [ ] Get daily + 4h + 1h BTC history (free public sources; cross-check vs the exchange)
      **plus 5-minute bars for the fill simulation**. Confirm regime coverage.
- [ ] Vectorized pandas test of V1/V2/V3 with the §4 fill model (post-only entries,
      0.05% trade-through fills on 5m bars, 2-candle timeout, taker exits, trailing
      stops, disaster stop, re-entry rules, V1 at 06:00 UTC).
- [ ] **Count trades per variant**; compute baselines (D4) and the circular-shift
      distribution (≥1,000 shifts; record percentile ranks).
- [ ] Apply §5 once. Write the verdict with numbers. No re-tuning.

**Gate G1:** Tier A / B / C per variant, trade counts, fee drags, and the D10 selection
outcome. C ends the trading-bot track.

## Phase 2 — Operational rehearsal (2–4 weeks, ≤ €20)
- [ ] `signal.py`: fetch closed candles (public endpoint, no keys), compute the winner's
      indicators, compare to a saved state file, send Telegram ENTER / EXIT / HOLD, append
      to a CSV log. (State file + closed-candle logic make it idempotent. **Scheduler
      note:** cron does not fire missed jobs; launchd's missed-interval behavior is
      unverified — the idempotent design makes this harmless either way: the next run
      catches up.)
- [ ] Schedule shortly after each candle close + a daily heartbeat (absence of the
      heartbeat is the alarm — check Telegram daily).
- [ ] Compare its signals with the Phase 1 script on the same history **and** against the
      exchange's own candles. Must match exactly.
- [ ] **Branch decision:** ≤ ~1 signal/month → Branch A; otherwise Branch B.
- [ ] **Branch A rehearsal:** one real €10–20 round trip by hand per D8 (post-only limit,
      2-candle timeout, exchange stop, market exit) at the pre-registered 06:00 UTC time.
      Learn fees, rounding, minimums.
- [ ] **Branch B rehearsal:** freqtrade (Docker, pinned version) on the laptop in
      **dry-run**; **verify freqtrade's entry re-pricing, post-only order types, market
      exits and stoploss_on_exchange can implement D8 exactly — if not, fall back to a
      small ccxt script or stay manual.** Verify its orders match `signal.py`;
      `caffeinate -is` + tmux; test stop placement and updates.

**Gate G2:** signals match, alerts reliable for 2+ weeks, rehearsal completed, fees as
expected, Branch chosen and recorded, D8-implementation verified for Branch B.

## Phase 3 — Live (€400)
- [ ] Fund €400 (only money you can lose).
- [ ] **Branch A (manual):** on ENTER, place the post-only limit at the best bid per D8
      (re-price up to 2 signal candles, then cancel). On fill: set the exchange stop at
      −25%. On EXIT: cancel the stop, sell at market, log. Execute at 06:00 UTC. No
      trading API keys needed.
- [ ] **Branch B (bot):** freqtrade (or the ccxt fallback) live on the laptop, same
      pinned image, `caffeinate -is` in tmux, `stoploss_on_exchange: true`, Telegram
      control, daily heartbeat. Trading-only API key, withdrawals disabled (home IP
      changes → whitelisting not possible; accept that or stay manual).
- [ ] **Staleness rule (Branch B, pre-registered):** on wake/restart, do NOT act on a
      signal whose candle closed more than 2× the variant timeframe ago (V1: 48 h, V2: 8 h,
      V3: 2 h) or where price has moved more than 1×ATR beyond the signal price since the
      signal — wait for the next closed candle. On every restart: first reconcile (position
      open? exchange stop present and at the correct level? update it), then trade.
- [ ] Log every trade (date, price, amount, fees) in a CSV ledger for tax.

## Phase 4 — Review at 12 months (or earlier on a §7 trigger)
Compare net-of-fee, net-of-tax result against buy-and-hold, cash, exposure-matched
buy-and-hold, and the other variants' simulated results over the same live period (did
the family ranking hold?). Decide: continue, resize, switch variant (new pre-registered
test required), switch to DCA, or stop.

---

# 7. Risk framework at €400

1. **Allocation:** V1: 100% in BTC while the signal is on, 100% EUR otherwise. V2/V3:
   sizing formula with the pre-registered risk% (default 1% → **33–50%** allocation). No
   leverage.
2. **Stops:** normal exits per §4 (crosses, 3×ATR trailing); disaster stop −25% at the
   exchange on every position. Worst single-trade loss ≈ −€100, more on gaps or outage.
3. **Drawdown review trigger:** closed-trade equity 30% below peak (€120) → move to EUR
   and full review before re-entering.
4. **Signal discipline:** no overriding the rule by hand, except exiting to EUR in an
   emergency.
5. **Execution discipline:** D8 exactly — post-only entries with 2-candle timeout, taker
   exits and stops, V1 at 06:00 UTC. No ad-hoc orders outside D8.
6. **Keys and custody:** withdrawal permission off any API key; 2FA by app on exchange,
   email, Telegram.
7. **Do not add capital to a losing run.** Add only after a review of a stable stretch.

---

# 8. Operations

- **Host:** the laptop. A once-per-candle job does not need 24/7 uptime, and the exchange
  holds the stops.
- **Failure modes:**

| Failure | Result | Mitigation |
|---|---|---|
| Laptop off for days | Missed signal; stop frozen at last level | Heartbeat; staleness rule on wake (§6 Phase 3); stop protects downside; missed entry = opportunity cost only |
| Telegram or script error | No alert | Heartbeat absence is the alarm; Phase 1 script as manual backup |
| Exchange outage | Cannot trade or stop may not fire | Accept, size is €400 |
| Wrong candle (incomplete or time zone) | Lookahead or false signal | Closed candles only; Phase 2 cross-check vs exchange candles |
| Post-only order never fills | No position (or stranded entry) | D8: re-price up to 2 candles, then cancel; missed trades logged and reviewed |

- **Log everything:** signals, orders, fills, fees in CSV. Keep the repo private and keys
  out of git.

---

# 9. Tax and records (Estonia — confirm with EMTA/advisor)

- The taxable event is the **sale or swap**, not the withdrawal. Staying inside the
  exchange does not defer tax.
- Under the 2025 rules, crypto bought on a **MiCA-authorised platform** is a financial
  asset with a 22% rate on **net realized gains**. Same-year gains and losses offset —
  **the tax rate does not scale with trade count**; only record-keeping does.
  Carry-forward of net losses is **unconfirmed**: assume none until EMTA says otherwise.
- **Investment-account regime:** EMTA's page states MiCA-platform crypto transactions
  *may be carried out in an investment account system* for deferral (the platform itself
  is not the account). Ask EMTA which setups qualify; assume no deferral until confirmed.
- DAC8: exchanges report to the tax authority from 2026. Keep the ledger and statements
  for every year. The CSV ledger is the tax record — keep it accurate even at higher
  trade counts.

---

# 10. Costs

| Item | v3.3 cost |
|---|---|
| Software, data, Telegram | €0 |
| Hosting | €0 (laptop) |
| Trading fees + slippage (modeled, on **invested** notional, full allocation) | V1 ~€5–14/yr (2–6 × 0.60%) · V2 ~€17–42/yr (6–15 × 0.70%) · V3 ~€42–112/yr (15–40 × 0.70%) |
| Allocation effect (V2/V3 at default 1% risk ≈ 33–50% invested) | Fees paid scale down roughly with the allocation fraction (≈40%) |
| Tax | 22% of net realized gains (same-year netted) |
| **Fixed costs total** | **~€0–112/yr depending on the winning variant and allocation** |

**Rule for adding a VPS:** only when fixed costs are ≤ ~2% of capital — about **€3,000**
for a €5/month VPS.

---

# 11. Review and exit rules

- Monthly: update DECISIONS.md, compare equity with buy-and-hold and cash.
- 12 months: formal review (Phase 4).
- Stop and take capital out if: the 30% drawdown trigger fires and the review doesn't
  justify re-entry; any order you did not intend; exchange or regulatory warning; you stop
  wanting to run it.
- If the result is no better than holding after costs and tax, switch to plain
  buy-and-hold/DCA. That is a fine outcome.

---

# 12. Parking lot (not in scope)

| Item | Revisit when |
|---|---|
| ML / FreqAI | There is a proven rule-based edge to filter and capital to justify the complexity |
| Sub-hourly strategies | Round-trip costs eat sub-hourly edges at this size |
| Mean reversion (S2) | Not before a separate pre-registered test |
| ETH or more pairs | After Phase 4, with their own pre-registered test |
| Redis / multi-process stack | Not applicable |
| VPS | Capital ≥ ~€3,000 (§10) |
| Leverage / futures | Not recommended at €400 |
| OÜ | Meaningful capital and a licensed advisor |
| Stocks / IBKR / LLM agent | Separate projects |

---

# 13. First actions this week

1. Phase 0: fees (maker AND taker), MiCA register, stop-order AND post-only support,
   minimum order. Pick the exchange.
2. Write and commit the pre-registration note (§4 + §5 + D8 + D10 + the V2/V3 risk%).
3. Run Phase 1 with the 5m-bar fill model, count trades, apply §5, apply D10, write the
   verdict.
4. Only if the D10 selection yields a live variant: start Phase 2 on its branch.

---

# Appendix A — Complete Review & Disposition Log

| Review | Outcome (accepted → in plan) |
|---|---|
| #1 Roadmap critique | DI is not Mahalanobis (FreqAI docs); threshold units must be explicit; stake from stop distance; kill switch handles positions; exchange-hosted stops; Docker for ARM64 |
| #2 Technical evaluation | M2 Air RAM/thermal analysis; GBDT anti-overfit constraints; walk-forward leakage rules; automated drawdown kill switch. REJECTED: "DI is Mahalanobis"; "Estonia allows no loss deductibility → OÜ in Phase 0" (outdated — MiCA-platform crypto is a financial asset since 1 Jan 2025, EMTA 15.02.2026) |
| #3 Doc audit | Kraken entry tier 0.40/0.80 verified; `--dl-trades` mandatory for Kraken history; protections deprecated config→strategy level and inert at low frequency; `show-trades` not `list-open-trades`; force-exit via API/Telegram; `FREQTRADE__` env pattern; `caffeinate -i` asserts idle-sleep not system-sleep; FreqAI retrains during live; VPS for live execution; random-entry + exposure-matched baselines; event-bound gates |
| #4 Statistical correction | The v2 log's 0.1% false-pass figure was wrong for 12-month windows (my simulation compared a non-annualized monthly Sharpe against the annualized threshold). Review #4's figures are correct: zero-edge false-pass ≈ 12.8% (12 mo), 6.3% (21 mo), ~0.1% (8 yr); heavy tails don't materially widen it. Pre-registration + full-history single run adopted; dry-run moved to the production host; latency trigger downgraded to alert/pause |
| v3.0 draft → plan | Capital-efficiency pivot: no VPS at €400; daily filter; signals-first + manual execution; disaster stop −25%; 30% review trigger; EMTA investment-account wording corrected |
| v3.1 (frequency ladder) | Frequency as a tested variable (V1/V2/V3); maker-only cost model; conditional execution branches; tax-rate-doesn't-scale correction |
| v3.2 review | Fill-bias awareness raised (touch-fill was too lenient — see v3.3); V1-default selection with 20% CAGR+Calmar margin; clean ladder (ADX removed); absolute return floor restored; sanity floors 8/24/60; D8 defined once; staleness + restart reconciliation; Phase 1 = 1–2 weeks; variant-aware sizing |
| v3.3 review | Trade-through fill rule (≥0.05%, on 5m bars); post-only orders; circular-shift baseline replacing undefined random-entry; cost arithmetic corrected to 0.60%/0.70% (V3 drag 10.5–28%/yr); V1 executed at pre-registered 06:00 UTC; allocation 33–50% with drag stated on invested notional; scheduler claim softened; freqtrade-D8 verification added to Phase 2; Appendix A wording corrected |

# Appendix B — Glossary (condensed)

- **Calmar ratio:** annualized return ÷ max drawdown — the primary edge metric here.
- **Exposure-matched buy-and-hold:** B&H scaled to the strategy's average time-in-market.
- **Circular-shift baseline:** the strategy's own position series shifted by random
  offsets (≥1,000 draws) — preserves trade count, hold times and exposure, tests timing
  only; the strategy must beat its 95th percentile (rank reported).
- **Pre-registration:** spec + numeric criteria committed before any data is examined.
- **Fill bias / trade-through:** limit orders fill only when price moves through them;
  a touch at the limit is not enough. Simulated: fill requires a 5m low ≥ 0.05% beyond
  the limit.
- **Post-only:** an order that rests on the book or is cancelled — it can never cross
  the spread and fill as taker. Required for maker fees on entries (D8).
- **Disaster stop:** exchange-hosted stop far from the normal exit (−25%) protecting
  positions while the operator/machine is offline; not a signal.
- **Maker/taker:** maker = resting limit order at the lower fee tier; taker = crossing
  the spread at the higher tier. Entries are post-only maker (D8); exits and stops are
  taker.
- **Fee drag:** round trips/yr × round-trip cost % — the annual cost of frequency,
  paid on invested notional; the gross edge must clear it.
- **Winner's curse:** selecting the best of several candidates overstates its true
  performance; mitigated by the V1-default + 20% margin rule (D10).

---

*End of plan v3.3. Next action: Phase 0 — exchange verification — then write the
pre-registration note BEFORE touching any data.*
