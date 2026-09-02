# THIRD-PARTY AUDIT BRIEF — A-Share BB Lower-Band Mean-Reversion Backtest Project

> **Purpose of this file:** to let a third-party model that has **never seen this project's conversation history**
> understand, from this file + the public GitHub repository alone, what the project is, what data it uses,
> what strategy it tests, and where the research currently stands — and then to independently audit it from scratch.
>
> **This file is a FACT PACK + REPOSITORY MAP.** It is not an argument that any result is correct, not an audit
> roadmap, not a summary of any auditor's opinions, and not a defense of the code. Where something is contested,
> it is marked `STATUS: DISPUTED / UNDER AUDIT` rather than settled.
>
> Repository: https://github.com/xinjojo/a-share-bb-mean-reversion-audit
> Generated: 2026-09-02

---

## 1. PROJECT PURPOSE

In the most plain terms, this project started with one idea to test:

> Among A-share (Chinese domestic stock market) stocks with high turnover (good liquidity), when a stock's
> price becomes oversold below its Bollinger Band lower band, buy it, and exit after mean reversion returns.

The research goal is **not** to prove the strategy makes money. The research goal is to examine whether this
style of mean reversion has real, tradeable, stable, and extrapolatable historical evidence.

The project's own historical conclusion process (see §7) is that the specific first-generation strategy hypothesis
did **not** pass strict red-team verification. The project has therefore moved to a second phase: studying the
*conditions* under which such oversold mean reversion may or may not work (see §8-§11).

---

## 2. ORIGINAL STRATEGY (first generation, as the user originally specified)

This is the strategy definition the user gave at the start. **Do not conflate the INVALID historical code with
the user's original intent.**

### 2.1 Universe and ranking
- Universe: all A-share common stocks (主板/创业板/科创板/北交所), default excluding ST / *ST (parameterized).
- New listings excluded until `min_listing_days` = 60 trading days after `list_date` (real list date, not backtest slice start).
- Daily ranking: by **turnover amount (`amount`)** descending. Strategy (when first defined) took `top_n = 1`;
  later variants used `top_n = 10` (frozen baseline; see §7).
- NOTE: ranking is by turnover amount, **not** market cap, not volume, not turnover rate. Uses that day's real historical
  `amount` only (no future data).

### 2.2 Entry signal
- Bollinger Band: `period = 20`, `std_multiplier = 2`, `ddof = 1`.
  - `Middle = MA(Close, 20)`
  - `Std = rolling_std(Close, 20, ddof=1)`
  - `Lower = Middle − 2·Std`
- Buy signal: `Close < Lower` (close of day T below that day's lower band).

### 2.3 Position sizing and pyramiding
- Account capital: 100%.
- Max 5 levels, each level = 20% of total capital.
- Level 1 = first buy (20%), levels 2-5 are adds (each +20%), max total 100%.
- "5 levels" includes the first buy: 20 / 40 / 60 / 80 / 100%.
- Add condition: while holding, if a later day again satisfies `Close < Lower`, add another 20%, up to 5 levels.
- Average cost is recomputed from actual executed shares, actual prices, and actual transaction fees
  (weighted average of actual share counts and prices, including buy fees).
- If a 20% target cannot buy at least 100 shares (one lot), that trade is skipped.

### 2.4 Exit — user's ORIGINAL intent (important)
The user's original exit intent is a **dynamic intraday Bollinger upper-band touch**:

- During day T, the intraday price path `P(t)` is treated as a "provisional close".
- The Bollinger Upper is recomputed in real time with that provisional close:
  `Upper_t = mean(prev_19_closes + P(t)) + 2·std(prev_19_closes + P(t))`, ddof=1.
- Exit the moment `P(t) >= Upper_t` first occurs.

This is **NOT**:
- (A) using a fixed T-1 upper band and selling when T's `high` touches it, nor
- (B) confirming at T close that `close >= BB_upper[T]` then selling at T+1 open, nor
- (C) the INVALID historical code that computed `BB_upper[T]` from the final `close[T]` and then checked
  `high[T] >= BB_upper[T]` (that would know the day's final close before the intraday touch).

For a fixed set of 19 prior closes `x1..x19`, this defines a fixed-point price `P*` such that
`P* = Upper(P*)`. The math used by the project (see `run_strict_c_math.py`) derives the analytic root of
`g(P) = P − Upper(P)`; because `g` is increasing on the relevant domain, `P < P* ⇒ g<0`, `P >= P* ⇒ g>=0`,
so a daily `high >= P*` proves an intraday touch of `P*` without needing minute data (daily approximation).

### 2.5 Other rules (as specified)
- Single-position focus in the original spec: at most one stock held at a time (later frozen baseline uses K=3 concurrent, see §7).
- T+1: shares bought on day T cannot be sold on day T; `sellable_shares = 0` on the buy day.
- 100-share lot minimum; buy quantities are integer multiples of 100.
- Limit up/down: bid/ask must respect exchange limit prices (main board ±10%, ST ±5%, 创业板/科创板 ±20%,
  Beijing Stock Exchange ±30%; corrected implementation is based on point-in-time stock type, not a fixed 9.5% threshold).
- Suspension: no trading on suspended days.
- ST/*ST: excluded by default; the exclusion is parameterized and uses point-in-time ST status (not current snapshot name).
- Fees (all parameterized): commission (with minimum), stamp tax (sell side only), transfer fee, slippage.
- Later (frozen baseline): shared cash pool, K=3 concurrent positions, ETF (513500 S&P 500 ETF) cash deployment so
  capital is effectively always fully invested (see §7).

---

## 3. DATA

All market data source: **Tushare Pro** (paid plan B; the token is held by the development agent's environment,
**not in the repository**).

### 3.1 Main daily file (in the local environment; K-line slices are in the repo — see §14)
- Merged daily panel `combined_daily.parquet`: **2020-01-02 ~ 2026-08-31**, **7,731,551 rows**.
  (The backtest trading period runs to 2026-08-25; the file extends to 08-31. README states 5,765 stocks;
  KLINE_DATA.md states 5,725 — the two docs differ slightly on the stock count; the row count 7,731,551 is consistent.)
- Per-stock fields: `date, ts_code, open, high, low, close, vol, amount, pre_close, adj_factor,
  is_limit_down, is_red`.
- `amount` unit = **thousand CNY (千元)** (Tushare `daily.amount` raw unit).
- `adj_factor` = Tushare adjustment factor; **adjusted price convention: `close_adj = close × adj_factor`** (backward-adjusted to the latest date, i.e. the current data set's factor as of the file's last date).

### 3.2 Warmup history (local environment only, not in repo)
- `warmup_daily_2018_2019.parquet`: 2018-01-01 ~ 2019-12-31, **1,718,712 rows**, columns
  `ts_code/date/open/high/low/close/pre_close/vol/amount/adj_factor/is_st_pit`. Used so that 2020 features
  (BB20, ret20, RV20, liquidity MA20, vol percentile) are valid from the first Discovery day.

### 3.3 Supporting datasets (local environment; source Tushare Pro)
- `pit_st_daily.parquet`: point-in-time ST/*ST status per (ts_code, date), rebuilt from historical name-change records.
- `raw/stock_basic.parquet`: `ts_code, list_date` (list_date string like `19910403`).
- `raw/trade_cal_full.parquet`: full A-share trading calendar (note: raw rows are in reverse date order; must be sorted).
- `raw/namechange_full.parquet`: name-change / ST-status history (2010-2026).
- `raw/daily/`: per-stock daily parquet slices (2020 onward only).
- ETF: 513500 (标普500 ETF) daily data — `open/high/low/close` (market quotes) + `unit_nav` (fund NAV);
  merged into `etf_513500_merged.parquet`. See `KLINE_DATA.md`.

### 3.4 Raw vs adjusted prices — what each is used for
- **Raw prices (`open/high/low/close`)** are used for actual transaction prices and fee/tax/slippage cash flows
  (e.g. `Pstar_raw = Pstar_adj / adj_factor[T]` at execution; execution ticks, limit-up/down levels, T+1).
- **Adjusted prices (`close_adj = close × adj_factor`)** are used for signal features (BB bands, RSI, returns, z-scores)
  so that signals are dividend/split-adjusted. The P* dynamic upper band is computed on the adjusted series
  (`x_k = close_raw[k]·adj_factor[k]`, i.e. each day's own factor), then converted back to a raw execution price.

### 3.5 Survivorship
- The combined panel **includes delisted stocks' history** (214 delisted stocks present in the dataset as of build time).
- **Known caveat:** the dataset is built from Tushare daily queries; any stock delisted before data collection may still
  be partially or fully missing. This is a **known limitation** of data completeness; it is not asserted to be zero.

---

## 4. EXECUTION SEMANTICS (A-share simulation constraints)

The engine simulates, for the frozen baseline, the following real constraints. A key distinction is
`signal_time` (when information is known) vs `execution_time` (when a trade executes):

- **signal_time**: end of day T, after `close[T]`, `amount[T]`, and BB[T] are final.
- **T+1**: shares bought on day T are sellable from day T+1; sellable shares are tracked per lot.
- **100-share lots**; buy quantities are integer multiples of 100.
- **Price tick**: 0.01 CNY (legal quote tick; `legal_trigger = ceil(Pstar_raw / 0.01) * 0.01` for the exit threshold).
- **Limit up/down**: entry/exit must be at a fillable price; corrected implementation uses point-in-time board-based
  limit rules, not a fixed 9.5% threshold; `open_fill` uses a conservative bound that does not use the day's final
  OHLC (a one-word board day's full-day `open==high==low==close` is **not** used to decide a 09:30 fill).
- **Suspension**: no trades on suspended days.
- **Next-open**: where a version executes at T+1 open, the execution price is the next day's open, and ETF funding is
  also executed at T+1 open (no 15:00 signal funding at 09:30 price).
- **Intraday-high exit**: the dynamic P* touch uses day-T `high` (daily approximation; exact intraday path is unknown
  from daily data). This is marked an APPROXIMATION where applicable.
- **Fees/tax/slippage**: commission, sell-side stamp tax, transfer fee, and slippage (both stock and ETF legs) are
  charged in actual cash flows. Slippage applies after the market-reachability check (limit-down no-fill is decided on
  the reference price *before* applying slippage).
- **ETF funding timing**: event-driven `ensure_cash_open()` / `ensure_cash_close()` / rebalance functions — funding
  price must be consistent with the moment the cash need becomes known (no time travel).

---

## 5. HISTORICAL VERSION MAP

The project went through many versions. Each entry states only what semantics it tested, its main difference, its
reported result, and its current status. **Failure history is intentionally kept, not deleted.**

| Version | Semantics tested | Main difference vs prior | Reported result | Current status |
|---|---|---|---|---|
| ORIGINAL / INVALID historical (also `V0_BASELINE_oldlimit` in round5 summaries) | K=3 + ETF full invest, exit `high[T] >= BB_upper[T]` where `BB_upper[T]` uses final `close[T]` | same-bar future info in the exit rule; fixed 9.5% limit-down; zero slippage in one variant | ≈ +354.9% (README) / +383.6% (round5 `V0_BASELINE_oldlimit`, 103 trades, win 75.7%) | **INVALID HISTORICAL BACKTEST** — same-bar future information in exit, plus execution/PIT issues listed below; not usable |
| STRICT_A | `high[T] >= BB_upper[T-1]`, sell at known prior upper | removes same-bar future in exit | ~ +126% (P0 family) | DIAGNOSTIC (causal-exit bound 1) |
| STRICT_B | T close confirm → T+1 open exit | causal exit bound 2 | ~ +109% | DIAGNOSTIC (causal-exit bound 2) |
| STRICT_V2 (Round5.1) | All Round5.1 fixes (PIT ST, PIT list_date, event-driven ETF, corrected limits) | first full "strict" combo; K=3 | combo A +45.1% / B +74.4%; pure stock A +5.2% / B +23.4% | **ARCHIVED / SUPERSEDED** (README closure was written on this; superseded by STRICT_C semantic restoration) |
| STRICT_C | Dynamic intraday P* touch (user's original exit intent), analytic root | semantic restoration; no P0 adj fix yet | combo +89.15% / pure +49.6% | ARCHIVED (superseded by corrected) |
| STRICT_C_CORRECTED | P0 adj-factor fix: `x_k = close_raw[k]·adj_factor[k]` (each day's own factor), `Pstar_raw = Pstar_adj/adj_factor[T]` | fixes cross-corporate-action window errors | combo ≈ +83-89%, pure +58% family | ARCHIVED (superseded by executable-tick naming) |
| **STRICT_C_EXECUTABLE_TICK** | + tick=0.01 legal quote: `legal_trigger = ceil(Pstar_raw/0.01)*0.01`; `open>=trigger`→sell at open, elif `high>=trigger`→sell at trigger, else no exit | A-share tick-constrained main executable semantics | **combo +82.66% / pure +58.20%** (see §7) | **CURRENT EXECUTABLE REFERENCE (first generation)** |
| optimistic tick (+65.06%) | `sell_ref = ceil(Pstar_raw/0.01)*0.01` even when high never reached that tick | non-fillable exit | +65.06% | **INVALID_DIAGNOSTIC** (not a legal execution bound) |
| continuous P* (+70.09%) | un-ticked real-valued P* | math reference only | +70.09% | NON_EXECUTABLE_REFERENCE (math reference only) |

Reasons the original ~+354.9% / +383% is INVALID (formally confirmed during Round1-5):
- **same-bar future information** in the exit rule (`high[T]` vs `BB_upper[T]` that includes `close[T]`);
- **ETF execution timing** (15:00 cash need funded at 09:30 open price);
- **PIT ST status** (current snapshot `name` used instead of point-in-time status);
- **listing ≥60-day** (backtest slice start misused as list date for stocks listed before 2020);
- other issues recorded in the REDTEAM reports.

---

## 6. CURRENT FIRST-GENERATION RESULT

Main version: **STRICT_C_EXECUTABLE_TICK** (frozen parameters: K=3 / top_n=10 / BB(20,2) / max_levels=5 /
level_cash=200,000 / initial cash 1,000,000 / slippage 10bp both legs / historical stamp tax / corrected point-in-time
limit rules / PIT ST / real list-date ≥60 days / T+1 / lot 100 / final settlement / ETF full-invest (NAV-based mark)).
Backtest period: 2020-01-02 ~ 2026-08-25.

| Metric | combo (with ETF cash management) | pure stock (ETF leg disabled) |
|---|---|---|
| Total Return | **+82.66%** | **+58.20%** |
| CAGR | 9.60% | 7.22% |
| Max Drawdown | −37.21% | −30.79% |
| Sharpe | 0.49 | 0.41 |
| Trade count | 97 | 98 |
| Win rate | 67.0% | 68.4% |
| Stock realized PnL (CNY) | +477,062 | +581,979 |

**OOS / split (from `REDTEAM_STRICT_C_CORRECTED.md`):**
- Train 2020-2023: combo +37.79% (sh 0.45) / pure +29.71% (sh 0.39)
- Test / Retrospective Stability Check 2024-2026: combo +26.73% (sh 0.46) / **pure +0.68% (sh 0.15)**
- Year-by-year (combo): 2020 +25.4% / 2021 +26.7% / 2022 +2.1% / **2023 −15.9%** / 2024 +3.4% / 2025 +30.3% / **2026 −0.9%**

**Official rating (verbatim):**
> **D — NO EVIDENCE OF ROBUST / REPEATABLE / EXTRAPOLATABLE ALPHA**

The rating means exactly: existing historical evidence is insufficient to show the stock Alpha is stable across
market regimes, repeatable, and extrapolatable. It **must not** be rewritten as "the strategy has no Alpha",
"the strategy cannot make money", or "the strategy has failed". Note also that **2024-2026 is NOT a pristine OOS**
(it was observed during the research; it is only a Retrospective Stability Check). Full attribution: over the full
sample, stock leg +47.7% > ETF/cash +35.0%; over the Test segment, combo +26.73% vs pure +0.68%, i.e. the Test-segment
combo gain is dominated by the ETF leg.

---

## 7. WHY REGIME RESEARCH EXISTS

The open research question (asked, not answered, here):

> Why does this oversold mean reversion appear to work in some years / market environments and fail in others?

The project froze a research design to study this *statistically* before writing any new strategy.

**Frozen regime dimensions** (definitions and thresholds fixed in `HYPOTHESIS_REGISTRY.csv` and
`REGIME_RESEARCH_PLAN.md`):
- **Trend**: all-A equal-weight index 20-day return; UP `ret20>+3%`, DOWN `<−3%`, else SIDEWAYS; NaN → WARMUP.
- **Breadth**: fraction of point-in-time-eligible stocks with `close_adj > MA20`; LOW `<0.30`, MID `0.30-0.70`, HIGH `>0.70`.
- **Volatility**: RV20 (20-day realized vol) percentile vs trailing 252-day history (min 100 obs, else WARMUP);
  LOW `≤0.20`, NORMAL `0.20-0.60`, HIGH `0.60-0.90`, EXTREME `>0.90`.
- **Liquidity**: all-A total `amount` / its MA20; LOW `<0.80`, NORMAL `0.80-1.20`, HIGH `>1.20`; NaN → WARMUP.

**Mutually-exclusive oversold (BB z-score) bins:**
- B1: `−2.0 < z ≤ −1.5`
- B2: `−2.5 < z ≤ −2.0`
- B3: `−3.0 < z ≤ −2.5`
- B4: `z ≤ −3.0`

**Causal forward outcomes** (5D and 10D):
- `causal_otc[N] = close_adj[T+N] / open_adj[T+1] − 1` (signal confirmed after T close; first tradeable price T+1 open).
- Secondary reference: `ret_open_to_open_N = open_adj[T+1+N]/open_adj[T+1] − 1` (descriptive only).
- The primary benchmark per hypothesis is **`same_oversold_unconditional`**: for a given (oversold bin, horizon),
  the Discovery-window mean daily cross-sectional causal_otc over all dates in that oversold bin, not conditioning
  on regime. Primary effect = conditional − same-oversold-unconditional.

---

## 8. DATA SPLIT

- **Discovery:** 2020-01-01 ~ 2022-12-31 (analysis window; warmup data before 2020 is used only to make features valid).
- **Validation:** 2023-01-01 ~ 2024-12-31 — **VALIDATION NOT OPENED** (as of this brief).
- **Retrospective Confirmation:** 2025-01-01 ~ 2026-08-25 — **NOT OPENED as a Confirmation gate** (as of this brief).
  It was observed historically during first-generation work; it is not a pristine OOS (see §6).
- **True Future OOS:** 2026-09-01 onward — **NOT YET AVAILABLE** (no future data exists yet as of 2026-09-02).

Per the research plan, Validation may only be opened after a pre-registered Registry is frozen and Discovery hypotheses
are fixed; Confirmation only tests pre-registered hypotheses that pass Discovery + Validation; no parameter or regime
threshold may be changed after Discovery.

---

## 9. HYPOTHESIS REGISTRY

- File: `HYPOTHESIS_REGISTRY.csv` — **104 PRIMARY hypotheses**, pre-registered **before** any Discovery results were read.
- SHA256: `5c5e451ad4eb3afd5e632b0019a3e02103e58e375e03cc231c5d8ca52b8c5195`
- Registry was frozen at commit `11e2ab2`. It is **not to be modified or regenerated**; any modification must be a new
  registry version/hash and a new research family.
- A template (`HYPOTHESIS_REGISTRY_TEMPLATE.csv`) documents the required fields; the frozen registry fills 104 rows.

---

## 10. CURRENT RESEARCH STATUS

- **First generation:** archived; final executable reference `STRICT_C_EXECUTABLE_TICK`; rating D (see §6).
- **Regime Discovery Phase 1** (Discovery 2020-2022) was run once, then the external auditor rejected the first
  statistical implementation and required a correction pass (warmup history, NaN→WARMUP, BH FDR fix, benchmark
  uncertainty, real-calendar block bootstrap, structured permutations, naming). The correction pass was implemented and
  committed (`fa58758`). As of this brief, the **correction has been submitted but not yet accepted** by the external
  auditor.
- Therefore:
  > **REGIME DISCOVERY PHASE 1: UNDER AUDIT / NOT YET ACCEPTED**
- The earlier Phase-1 v1 result ("0 FDR significant") is a **PRELIMINARY / SUPERSEDED RESULT**; it must not be cited
  as the final accepted conclusion. The corrected matrix (`results/regime_discovery_matrix_v2.csv`) is the pending
  result; its headline counts as submitted: VALID 60 / INSUFFICIENT 44 / FDR-significant 3 (all negative, LIQUIDITY
  NORMAL) / none of the 104 passing all of HAC+FDR+bootstrap+both structured permutations simultaneously.
  These numbers are **submitted, not yet accepted**; the third party should re-derive them.

---

## 11. KNOWN INVALID / SUPERSEDED / DIAGNOSTIC-ONLY RESULTS

To prevent publication bias, the complete failure history is listed here (details in the REDTEAM files):

- Original / `V0_BASELINE_oldlimit` ≈ +354.9% / +383.6% — **INVALID** (same-bar future info in exit, ETF timing,
  PIT ST, listing-60d issues).
- `P0_FIX` ≈ +110.85%, `P0+CORRECTLD` ≈ +82.49%, `STRICT_V1` ≈ +62.62% — **SUPERSEDED** (STRICT_V1 later found to
  retain ETF open time-travel + listing bug; Round5.1 marked it invalid as a strict result).
- `STRICT_V2` combo +45% / +74% — **ARCHIVED/SUPERSEDED** by the STRICT_C semantic restoration (and pure-stock legs
  were ~+5% / +23%, below ETF buy&hold).
- `STRICT_C` (+89.15% / +49.6%) — **ARCHIVED** (P0 adj-factor issue).
- optimistic-tick +65.06% — **INVALID_DIAGNOSTIC** (non-fillable execution bound).
- continuous-P* +70.09% — **NON_EXECUTABLE_REFERENCE** (math reference only).
- Phase-1 v1 regime matrix (0 FDR significant) — **PRELIMINARY / SUPERSEDED** pending correction acceptance.
- All pre-Round5 DOE outputs (e.g. `bb_sensitivity`, `bb_stop_grid`, `etf_ratio_scan`, `walk_forward`, `full_market_scan`,
  `analyze_*`, `strategy_*`) were produced on the earlier INVALID engine and are **not to be used for parameter selection**.

---

## 12. REPOSITORY MAP

Navigation table (purpose only — this file does **not** assert any of them is correct):

| File / dir | Purpose |
|---|---|
| `README.md` | Project overview; closure statement of first generation (written at Round5.1/STRICT_V2 stage) |
| `AUDIT_GUIDE.md` | Audit reference material for a prior audit round (2026-09-01; core claims + reconciliation) |
| `BACKTEST_INVARIANTS.md` | 15 backtest invariants distilled from the bugs found (no-future, PIT, T+1, cash conservation, etc.) |
| `tests/test_backtest_invariants.py` | 28 automated invariant tests (claimed PASS) |
| `experiment_fast.py` | Fast multi-position backtest engine (source of the original/INVALID + P0 family numbers) |
| `round5_audit.py` (in repo? — see note) | Round5 strict engine (PIT ST / listing / ETF timing fixes) |
| `run_strict_c.py`, `run_strict_c_math.py`, `strict_c_attribution.py`, `strict_c_corrected.py`, `semantic_touch.py` | STRICT_C dynamic-P* engine, math, attribution, corrected, semantic compare |
| `REGIME_RESEARCH_PLAN.md` | Second-generation research design (regime × oversold → conditional returns) |
| `HYPOTHESIS_REGISTRY.csv`, `HYPOTHESIS_REGISTRY_TEMPLATE.csv` | Frozen 104 primary hypotheses (+ template) |
| `regime_discovery.py` | Phase 1 v1 Discovery implementation (superseded pending correction) |
| `regime_discovery_corrected.py`, `cross_check_phase1.py` | Corrected Discovery implementation + independent cross-check |
| `download_warmup.py` | Warmup (2018-2019) download script (requires Tushare token) |
| `REGIME_DISCOVERY_PHASE1.md` | v1 Phase 1 report (preliminary/superseded) |
| `REGIME_DISCOVERY_PHASE1_CORRECTED.md` | Corrected Phase 1 report (submitted, not yet accepted) |
| `REDTEAM_ROUND*.md`, `REDTEAM_STRICT*.md`, `REDTEAM_AUDIT_REPLY.md` | Per-round red-team audit reports (Round1..5, 5.1, STRICT_C family) |
| `CALLCHAIN.md`, `RESULTS_LATEST.md`, `TRADING_SYSTEM_STEPBYSTEP.md` | Call-chain, latest-results, step-by-step trading system docs |
| `results/` | CSV/JSON results: `regime_discovery_matrix.csv` (v1), `regime_discovery_matrix_v2.csv` (corrected, pending), `round5/*` (STRICT family), `trades.csv`, `equity_curve.csv`, `parameter_scan_*`, `yearly_returns.csv`, etc. |
| `results/round5/strict_c_executable_tick_{equity,trades,pure_equity,pure_trades}.csv` | STRICT_C_EXECUTABLE_TICK final outputs |
| `results/round5/strict_oos.json`, `strict_summary.json`, `p*_*.json/csv` | OOS / round5 experiment outputs |
| `data/kline/*.parquet`, `data/kline/etf_513500_merged.parquet`, `merge_kline.py`, `KLINE_DATA.md` | K-line market data slices (2020-2026) + schema doc |
| `engine/`, `data_loader/`, `backtest/`, `config/`, `analysis/`, `tests/` | Structured code directories (some may be partial) |
| Legacy strategy/DOE scripts | `strategy_*.py`, `bb_*.py`, `analyze_*.py`, `full_market_*.py`, `etf_*.py`, `test_*.py`, `walk_forward.py`, etc. — earlier engine; see §11 status |

> NOTE: `round5_audit.py` is referenced by README; whether it is present in the repo should be verified by the auditor
> from the repository tree directly.

---

## 13. REPRODUCTION ENTRY POINTS

**NOT FULLY REPRODUCIBLE FROM THE PUBLIC REPOSITORY.** The public repo contains code, docs, results, and K-line
market-data slices, but **not** the full merged panel or all local inputs, and **not** the Tushare token.

Missing / required to fully reproduce (not in the public repo):
- `data/combined_daily.parquet` (full 2020-2026 panel) — rebuildable from `data/kline/*.parquet` slices + `merge_kline.py`
  (but the repo's slices may or may not include all derived columns used by engines, e.g. `is_limit_down` flags, and do
  not include warmup 2018-2019 or `pit_st_daily.parquet`).
- `data/pit_st_daily.parquet` (point-in-time ST status) — rebuildable only with Tushare `namechange` history + token.
- `data/warmup_daily_2018_2019.parquet` — download script `download_warmup.py` provided, requires Tushare token.
- `data/raw/stock_basic.parquet`, `data/raw/trade_cal_full.parquet`, `data/raw/namechange_full.parquet` (Tushare).
- Tushare Pro token (never committed).

Known commands (require the local data + token):
- First-gen executable reference: `python run_strict_c.py` (frozen params in file; writes `results/round5/strict_c_executable_tick_*`).
- Invariant tests: `pytest tests/test_backtest_invariants.py` (or the file's runner).
- Regime Discovery (corrected): `python regime_discovery_corrected.py` (writes `results/regime_discovery_matrix_v2.csv`);
  cross-check: `python cross_check_phase1.py`.
- Warmup download: `python download_warmup.py` (requires `TUSHARE_TOKEN` env var).

Data schemas and conventions are documented in `KLINE_DATA.md`, `README.md`, and `REGIME_RESEARCH_PLAN.md`.

---

## 14. OPEN ISSUES (factual status only)

- **REGIME DISCOVERY statistical implementation:** UNDER AUDIT (correction submitted, acceptance pending).
- **Validation 2023-2024:** NOT OPENED.
- **Confirmation 2025-2026:** NOT OPENED as a gate; historically observed only (retrospective, not pristine OOS).
- **True future OOS:** NOT YET AVAILABLE (2026-09 onward).
- **Survivorship / data completeness:** KNOWN LIMITATION (delisted stocks partially included; exact coverage not proven).
- **Point-in-time ST status:** rebuilt from name-change history; regarded as best-effort, not asserted perfect.
- **Intraday execution:** daily-data approximation (intraday P* touch inferred from daily high); marked APPROXIMATION.
- **ETF NAV vs market-close marking:** the first-gen combo uses NAV-based marking; a market-close variant exists; the
  difference is documented in the round5 P2 outputs.

---

## 15. THE ONLY TASK FOR THE THIRD PARTY

You are not asked to continue this research or optimize the strategy.

You are asked to independently audit it.

Assume that both the development Agent and the existing external auditor may be wrong.

Do not inherit their conclusions.

Use the repository, code, data definitions and mathematical logic to form your own assessment.
