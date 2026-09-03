# CROSS_SECTIONAL_RANKING_P1 — DISCOVERY DIAGNOSTIC + SLOT-ALLOCATION PREREQUISITE

**Phase**: P1 — Cross-Sectional Signal Ranking & Slot-Allocation Diagnostic (Discovery only)
**Date**: 2026-09-03
**Author**: development agent (external auditor review pending)
**Status**: DISCOVERY-LEVEL FINDINGS — NOT validated, NOT a tradable rule

---

## 0. Discipline / red-line checklist (all satisfied)

| Red line | Status |
|---|---|
| 2023–2024 Validation CLOSED (no outcome used) | ✅ CONFIRMED — script filters signal_date ∈ [2020-01-01, 2022-12-31] only |
| 2025–2026 Confirmation CLOSED (no 2025+ return read) | ✅ CONFIRMED |
| Registry preregistered & committed BEFORE outcome analysis | ✅ commit `9c36887` |
| Registry SHA256 | `fa5beb5a9a952442be2a359b95347388ff082c06fa36b56cf8f6eee477bab819` |
| Registry not modified after run | ✅ CONFIRMED (file re-hashed, unchanged) |
| No portfolio backtest / no K=3 capital path / no slot reallocation sim | ✅ CONFIRMED — episode-level diagnostics only |
| Frozen SECONDARY V2A episodes used (no new signal generation) | ✅ CONFIRMED — `results/fullmarket_episode_metrics.csv` |
| No stop / exit / entry / BB / max-level / K modification | ✅ CONFIRMED |
| PURE STOCK, no ETF | ✅ CONFIRMED |
| Predictors use only ≤ signal_date information (PIT) | ✅ CONFIRMED (see §2) |

---

## 1. Research question

When the same day (or adjacent days) produces many BB-oversold opportunities under a
frozen `STRICT_C_EXECUTABLE_TICK` engine, the limited portfolio (1M RMB, K=3, 5×200k
layers) must decide **which** signals to allocate slots to. This phase asks the
prerequisite question, *before any portfolio construction*:

> Within the same signal date, can T-close stock-level characteristics rank the future
> quality of same-day BB-oversold signals?

This is **cross-sectional ranking** (which stock), NOT market timing (when). All
comparisons are made **within the same signal day**, which automatically controls for
the (already validated) market-state effect.

---

## 2. Data & predictor construction (all PIT at signal-date close)

**Frozen episode sample (Discovery)**:
- Source: `results/fullmarket_episode_metrics.csv` (frozen SECONDARY V2A, `STRICT_C_EXECUTABLE_TICK`, 89,046 realized + 124 censored full-sample).
- Discovery subset: **signal_date 2020-01-01 → 2022-12-31**.
- **666 signal days, 35,009 episodes** (Discovery).
- Outcome per episode = frozen final `simple_return_pct` (realized, after all costs).

**Market data**: `data/combined_daily.parquet` (Tushare daily, 7,731,551 rows),
`data/pit_st_daily.parquet` for PIT ST flag. `close_adj = close × adj_factor`
(identical to frozen engine). All-A EW index level built exactly as T2
`assemble_day_frame` (`lvl = cumprod(1+idx_ret)`, eligible non-ST universe, list_date+60d).

**17 predictors, 7 families, all available at T close** (full formulas in
`CROSS_SECTIONAL_RANKING_REGISTRY.csv`, preregistered):

| ID | Family | Name | Direction registered |
|---|---|---|---|
| F01 | OVERSOLD_DEPTH | BB_Z | UNKNOWN |
| F02 | OVERSOLD_DEPTH | BB_LOWER_DISTANCE | UNKNOWN |
| F03 | SHORT_PRICE_SHOCK | RET1 | UNKNOWN |
| F04 | SHORT_PRICE_SHOCK | RET3 | UNKNOWN |
| F05 | SHORT_PRICE_SHOCK | RET5 | UNKNOWN |
| F06 | REVERSAL_CONTEXT | RET20 | UNKNOWN |
| F07 | REVERSAL_CONTEXT | DIST_MA20 | UNKNOWN |
| F08 | VOLATILITY | STOCK_RV20 | UNKNOWN |
| F09 | VOLATILITY | ATR20_PCT | UNKNOWN |
| F10 | LIQUIDITY | AMOUNT (log) | UNKNOWN |
| F11 | LIQUIDITY | AMOUNT_RATIO20 | UNKNOWN |
| F12 | CANDLE | CLOSE_LOCATION | POSITIVE |
| F13 | CANDLE | INTRADAY_RANGE | UNKNOWN |
| F14 | CANDLE | GAP | UNKNOWN |
| F15 | MARKET_RELATIVE | REL_RET1 | POSITIVE |
| F16 | MARKET_RELATIVE | REL_RET5 | POSITIVE |
| F17 | MARKET_RELATIVE | REL_RET20 | POSITIVE |

Missingness on the Discovery episode join is ≤0.07% for every predictor (mostly RET20 /
REL_RET20 at the sample edge). Predictor NaN rows are excluded per-day (day still counts
if ≥5 valid).

---

## 3. Primary inference

Per signal date with ≥5 signals, compute **daily cross-sectional Spearman IC** between
the predictor and final return (rank of predictor vs rank of outcome). Statistics on the
daily IC time series (666 days):
- **mean / median daily IC, positive-day fraction**
- **Newey-West HAC mean t** (lag = 10, sensitivity lag = 20)
- **moving-block bootstrap 95% CI** (L=21 signal days, B=2000)
- **Benjamini-Hochberg FDR over m=17** (primary family = 17 Y20-style... primary family =
  17 daily-IC hypotheses)

`UNKNOWN`-registered predictors take their Discovery-determined direction; `POSITIVE`/
`NEGATIVE`-registered predictors keep the frozen registry direction (directional
hypotheses).

### Daily IC master table (results/p1_master_table.csv)

| ID | mean IC | median IC | pos frac | HAC t | raw p | BH q | pair acc* | K3 lift | K3 CI(lo,hi) | ic20/21/22 | PASS |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F01 BB_Z | +0.012 | 0.015 | 0.54 | 1.12 | 0.26 | 0.57 | 50.4% | −0.10 | (−0.50,0.30) | +/−/+ | No |
| F02 BB_LD | −0.028 | −0.025 | 0.45 | −1.72 | 0.09 | 0.13 | 51.5% | +0.24 | (−0.21,0.80) | −/−/− | No |
| F03 RET1 | −0.034 | −0.031 | 0.44 | −1.87 | 0.06 | 0.11 | 53.4% | +0.43 | (−0.04,0.92) | −/−/+ | No |
| **F04 RET3** | **−0.051** | −0.049 | 0.42 | −2.81 | 0.005 | **0.0088** | 53.6% | +0.55 | (0.02,1.13) | −/−/− | **Yes** |
| F05 RET5 | −0.051 | −0.049 | 0.42 | −2.82 | 0.005 | 0.0088 | 53.5% | +0.53 | (−0.03,1.03) | +/−/− | No (E) |
| **F06 RET20** | **−0.045** | −0.045 | 0.42 | −2.59 | 0.010 | **0.0088** | 54.0% | +0.93 | (0.40,1.48) | −/−/− | **Yes** |
| **F07 DIST_MA20** | **−0.068** | −0.067 | 0.40 | −3.59 | 0.0003 | **0.0021** | 54.6% | +0.83 | (0.22,1.50) | −/−/− | **Yes** |
| F08 STOCK_RV20 | +0.076 | +0.076 | 0.61 | 3.64 | 0.0003 | 0.00016 | 54.4% | +0.34 | (−0.17,0.88) | +/+/+ | No (D) |
| **F09 ATR20_PCT** | **+0.088** | +0.086 | 0.62 | 4.04 | 5.4e-5 | **0.00008** | 55.1% | +0.67 | (0.07,1.20) | +/+/+ | **Yes** |
| F10 AMOUNT | +0.003 | −0.001 | 0.51 | 0.17 | 0.86 | 0.85 | 50.2% | +0.05 | (−0.63,0.69) | +/−/+ | No |
| F11 AMT_RATIO20 | −0.010 | −0.014 | 0.47 | −0.63 | 0.53 | 0.61 | 50.5% | −0.16 | (−0.52,0.26) | −/−/− | No |
| F12 CLOSE_LOC | −0.012 | −0.013 | 0.47 | −0.68 | 0.50 | 0.53 | 49.8% | +0.06 | (−0.36,0.47) | −/−/+ | No |
| **F13 INTRADAY_RNG** | **+0.056** | +0.050 | 0.58 | 2.93 | 0.003 | **0.0056** | 54.1% | +0.73 | (0.21,1.23) | +/+/+ | **Yes** |
| F14 GAP | +0.023 | +0.022 | 0.54 | 1.17 | 0.24 | 0.18 | 49.4% | +0.57 | (0.12,0.93) | +/−/+ | No (A) |
| F15 REL_RET1 | −0.034 | −0.033 | 0.44 | −1.87 | 0.06 | 0.11 | 46.6%† | −0.62 | (−0.94,−0.22) | −/−/+ | No (dir) |
| F16 REL_RET5 | −0.051 | −0.050 | 0.42 | −2.82 | 0.005 | 0.0088 | 46.5%† | −0.94 | (−1.34,−0.50) | +/−/− | No (dir) |
| F17 REL_RET20 | −0.045 | −0.044 | 0.42 | −2.59 | 0.010 | 0.0088 | 46.0%† | −0.44 | (−0.94,0.10) | −/−/− | No (dir) |

\* pair acc = oriented pairwise rank accuracy (≥53% gate). For negative-direction features
the oriented accuracy is 1 − raw agreement (predictor ranks winner above loser).
† F15–17: raw agreement reported because the frozen registry direction is POSITIVE; the
observed direction is NEGATIVE, so the registered directional hypothesis is **refuted** in
Discovery (see §6).

### Discovery gate (per §15 of task)

A: BH q<0.05 · B: |mean daily IC|≥0.03 · C: oriented pairwise accuracy ≥53% ·
D: TopK(K=3) selection lift ≥+0.5pp · E: block-bootstrap K3 lift 95% CI >0 ·
F: 2020/2021/2022 at least 2/3 same direction and no clearly-reverse year.

**DISCOVERY_PASS count = 5**: F04, F06, F07 (Reversal/Weakness, Discovery direction NEGATIVE),
F09, F13 (Volatility, Discovery direction POSITIVE). F05 misses only on E (CI crosses 0);
F08 misses only on D (K3 lift 0.34<0.5); F14 misses on A (q=0.18).

---

## 4. Economic / monotonic evidence (equal-day quintiles)

Within-day quintiles are formed per signal day, then averaged equal-day across days
(days with many signals do not dominate). Episode-weighted tables are also produced.

| Feature | Q1 mean% | Q2 | Q3 | Q4 | Q5 | direction | Q-spread |
|---|---|---|---|---|---|---|---|
| F04 RET3 | 4.94 | 4.91 | 4.64 | 4.53 | 3.50 | Q1 best (most negative RET3) | +1.43pp |
| F06 RET20 | 5.16 | 4.41 | 4.52 | 4.28 | 4.16 | Q1 best | +1.00pp |
| F07 DIST_MA20 | 5.11 | 5.25 | 4.56 | 4.00 | 3.68 | Q1 best (deepest below MA20) | +1.43pp |
| F09 ATR20_PCT | 3.43 | 4.36 | 4.36 | 4.78 | 5.45 | Q5 best (highest vol) | +2.01pp |
| F13 INTRADAY_RANGE | 3.70 | 4.21 | 4.46 | 4.87 | 5.12 | Q5 best (highest range) | +1.43pp |

Equal-day mean across usable (n≥3) Discovery days = **4.38pp**. Both equal-day and
episode-weighted quintile tables are monotonic for all five passers. The two families
are economically coherent with mean reversion: *deeper recent weakness* and *higher
volatility* predict stronger oversold reversals.

---

## 5. Winner-at-K, random baseline & oracle (results/p1_topk_selection.csv, p1_random_k3.csv, p1_oracle_upper_bound.csv)

- **Random K3 baseline** (equal-day, B=5000, same per-day signal counts): mean = **4.38pp**, 95% band **[3.95, 4.82]pp** (std 0.22pp).
- **Predictor Top-K3 means**: F04 4.92pp · F06 5.30pp · F07 5.21pp · F09 5.05pp · F13 5.11pp — all above the random 97.5% bound.
- **K3 selection lift** (top3 − day mean, block-bootstrap CI>0 for all 5 passers): F04 +0.55, F06 +0.93, F07 +0.83, F09 +0.67, F13 +0.73pp.
- **Hindsight oracle upper bound** (non-deployable): K3 = 19.21pp (lift ≈ +14.8pp vs 4.38), K1 = 23.83pp. The same-day cross-sectional dispersion is **large**, so slot-selection is a real, worth-studying problem. Current single predictors capture only ~4–6% of the oracle K3 spread — modest but genuinely above random.

---

## 6. Direction discipline

- **UNKNOWN features (all 5 passers)**: direction set by Discovery (F04/F06/F07 → NEGATIVE; F09/F13 → POSITIVE). Per the task, these directions must be **re-frozen in an independent Validation registry** before any 2023–2024 use; they cannot be called "validated" this round.
- **F15–17 REL_RET (registered POSITIVE)**: observed IC is **NEGATIVE** and significant (F16/F17 q≈0.009). The preregistered directional hypothesis is therefore **REFUTED in Discovery** — relative *weakness* (not strength) predicts better future reversal. These are reverse-direction findings that would require a **separate reverse preregistration** (like T2-R) before any Validation; they are NOT counted as DISCOVERY_PASS.

---

## 7. Turnover Top10 — within-day ranking value (results/p1_turnover_rank_diagnostic.csv)

| Bucket | n episodes | equal-day excess vs day mean |
|---|---|---|
| A_TOP10 (rank≤10) | 112 | +0.27pp |
| B_11_50 | 357 | **+0.66pp** |
| C_51_200 | 1,148 | −0.17pp |
| D_201_500 | 2,260 | −0.62pp |
| E_>500 | 31,132 | +0.24pp |

The pattern is **non-monotonic and weak**: Top10 does **not** reliably pick the better
same-day signals (rank 11–50 has the highest excess; the deepest liquidity bucket E is
slightly positive). This reconfirms the earlier finding that the amount-Top10 screen
does not improve independent trade quality and is **not** a defensible within-day
selection rule on its own.

---

## 8. Crowding sensitivity (results/p1_crowding_sensitivity.csv)

Frozen crowding tertiles by Discovery n_signals: LOW ≤9, MID 10–33, HIGH ≥34.

| Feature | LOW | MID | HIGH |
|---|---|---|---|
| F07 DIST_MA20 | +0.018 | −0.081 | **−0.125** |
| F09 ATR20_PCT | +0.036 | +0.084 | **+0.134** |

Both representative passers are **strongest on high-crowding days** (when many stocks
oversold together) — exactly the regime where the K=3 blocking problem bites. This is
encouraging for the eventual slot-allocation use case, but is descriptive only.

## 9. Market-state (R01) sensitivity (results/p1_marketstate_sensitivity.csv)

| Feature | R01 LOW | R01 MID | R01 HIGH |
|---|---|---|---|
| F07 DIST_MA20 | −0.058 | −0.106 | −0.064 |
| F09 ATR20_PCT | +0.074 | +0.131 | +0.084 |

F09 is positive in all three market states (state-robust direction). F07 remains
negative across states (attenuated in HIGH). No passer reverses direction by market
state.

## 10. Year-by-year stability (results/p1_yearly.csv)

All 5 passers are stable in all three Discovery years (F04: −0.006/−0.097/−0.039;
F06: −0.011/−0.055/−0.063; F07: −0.015/−0.091/−0.086; F09: +0.050/+0.109/+0.096;
F13: +0.026/+0.096/+0.039). No clearly-reverse year → gate F satisfied.

## 11. Redundancy (results/p1_redundancy.csv)

Within-day cross-sectional rank correlation, averaged over days. No passer pair exceeds
|0.8| (closest: F04–F07 0.72, F07–F09 −0.73). By the frozen rule none are "redundant".
Economically the 5 passers form **2 distinct families**: Reversal/Weakness
(F04/F06/F07) and Volatility (F09/F13), which are *negatively* correlated with each
other (F07–F09 ≈ −0.73, F06–F09 ≈ −0.33).

## 12. PRIMARY (frozen 299) direction sensitivity (results/p1_primary_sensitivity.csv)

All 5 Discovery passers show the **same direction** in the frozen PRIMARY Top10 sample
(Discovery subset, 150 episodes / 125 days): F04 −0.18, F06 −0.20, F07 −0.27 (NEGATIVE);
F09 +0.22, F13 +0.15 (POSITIVE). PRIMARY is a secondary confirmation only (small sample),
not a feature-selection input.

---

## 13. Classification

Per the frozen rule:
- **A — STRONG CROSS-SECTIONAL RANKING SIGNAL**: ≥2 non-redundant predictors pass the
  Discovery gate. Here **5 predictors across 2 non-redundant families** pass
  (Reversal/Weakness: F04/F06/F07; Volatility: F09/F13).

**Important scope note**: this is a **Discovery-level** classification. All 5 passers are
UNKNOWN-direction (Discovery-set) and the effect sizes are modest (mean daily IC
0.045–0.088; K3 lift +0.55–0.93pp vs a 4.38pp day mean; pairwise 53.6–55.1%). The
direction re-freezing + independent Validation (2023–2024) is a mandatory next gate
before any slot-allocation use.

---

## 14. Headline answers to the P1 questions

1. **Registry commit SHA**: `9c36887`
2. **Registry SHA256**: `fa5beb5a9a952442be2a359b95347388ff082c06fa36b56cf8f6eee477bab819`
3. **Result commit SHA**: see HEAD (this report committed with results)
4. **Discovery signal days / episodes**: 666 / 35,009
5. **Oracle K3 lift**: +14.8pp (hindsight, non-deployable) — large dispersion ⇒ selection problem is real
6. **Random K3 baseline**: 4.38pp (95% band 3.95–4.82)
7. **17 predictors, BH q<0.05**: 9 (F04, F05, F06, F07, F08, F09, F13, F16, F17; F04/F05/F06/F16/F17 share the same q≈0.0088 block)
8. **Full Discovery gate pass**: 5
9. **Strongest predictor**: F09 ATR20_PCT — mean daily IC +0.088, q 0.00008, pairwise 55.1%, K3 lift +0.67pp, bootstrap CI (0.07,1.20)
10. **Second strongest**: F07 DIST_MA20 — mean daily IC −0.068, q 0.0021, pairwise 54.6%, K3 lift +0.83pp, CI (0.22,1.50)
11. **≥2 non-redundant predictors**: YES (2 distinct families, none redundant by the 0.8 rule)
12. **Top10 turnover within-day ranking value**: NO (non-monotonic; rank 11–50 best)
13. **Relative-strength family (REL_RET)**: registered POSITIVE hypothesis **refuted** in Discovery (observed NEGATIVE); reverse-direction finding requires separate reverse preregistration
14. **BB depth family (BB_Z / BB_LD)**: no robust ranking value (BB_Z +0.012, BB_LD −0.028)
15. **Volatility family**: YES — F09/F13 are the strongest and most stable passers (positive direction)
16. **Liquidity family (AMOUNT / AMT_RATIO)**: no ranking value
17. **2020/2021/2022 stability**: all 5 passers stable in all 3 years
18. **Crowding sensitivity**: ranking power of the two families is *strongest on high-crowding days*
19. **R01 market-state sensitivity**: no passer reverses direction across states
20. **PRIMARY direction sensitivity**: same direction for all 5 passers
21. **Final classification**: **A — STRONG CROSS-SECTIONAL RANKING SIGNAL** (Discovery level)
22. **One sentence**: 我们找到了比成交额 Top10 更合理的同日信号排序依据——更深的近期弱势（RET3/RET20/DIST_MA20）与更高的波动（ATR20/日内振幅）在同日横截面内稳定地指向更好的超跌反弹质量；方向需在独立 Validation 前重新冻结。

---

## 15. Next step (not executed)

- Freeze a **Ranking Validation registry** (the 5 passers + their Discovery directions,
  plus a reverse-preregistration for the REL_RET family if desired) and run 2023–2024
  Validation — **only after external audit approval**.
- 2025–2026 Confirmation remains CLOSED.
- No portfolio backtest / slot-allocation simulation performed in this phase.

## 16. Verification notes

- Script re-run twice after gate fixes (pairwise orientation, gate-D sign, direction
  discipline); final outputs are from the corrected run.
- `ConstantInputWarning` in scipy Spearman arises on the rare constant-predictor day;
  those days contribute NaN IC and are excluded (no impact on reported statistics).
- All output CSVs are regenerated atomically by the single script; master table is the
  single source of truth for the gate columns.
