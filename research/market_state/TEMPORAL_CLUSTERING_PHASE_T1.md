# TEMPORAL CLUSTERING DIAGNOSTIC — PHASE T1

**STRICT_C FULL-MARKET SECONDARY (+ PRIMARY benchmark) — pure time-clustering audit**
**Status: completed (Phase T1). No Validation opened. Registry untouched (SHA256 `5c5e451a…`).**

---

## 0. Question

Do winning/losing trades of the frozen `V2A_FROZEN_STRICT` (STRICT_C_EXECUTABLE_TICK)
independent-trade sample cluster in time — i.e. do profits and losses concentrate in
distinct performance states rather than being randomly scattered over the 2020–2026 axis?

**This is an OUTCOME DIAGNOSTIC.** Outcomes are backfilled to `signal_date` for the sole purpose of
describing historical clustering. Nothing here is a tradeable real-time indicator, and no market-state
explanation (Trend/Breadth/Vol/Liquidity/volume/index/crowding) is introduced — that is Phase T2.

---

## 1. Samples (frozen, read-only)

| Sample | Definition | Episodes | Signal days |
|---|---|---|---|
| **SECONDARY (primary)** | V2A_FROZEN_STRICT, all PIT-eligible A-shares, `close_adj < BB lower`, T+1 open entry, dynamic P*, tick, limits, fees/slippage, max 5 layers | 89,046 realized (+124 censored, excluded) | **1,494** (2020-02-06 … 2026-08-24) |
| **PRIMARY (benchmark)** | same semantics, signal restricted to that day's amount Top-10 | 299 | 249 |

Primary series: **signal-day cross-sectional mean final return** `R_mean(t)` (plus median, win rate,
loss rate, mean MAE, mean hold, N per day). All permutation inference uses **signal DAY** as the
permutation unit (each day's full cross-section preserved); 89k episodes are never shuffled individually.

---

## 2. Headline results

### 2.1 Runs / sequencing (daily R_mean sign)

- 1,494 signal days: **1,224 positive (81.9%) / 270 negative (18.1%)**.
- Actual runs = **317**, vs expected ≈ 443 under random ordering
  (Wald–Wolfowitz **z = −11.05, p < 1e-16**).
- Permutation null (10,000 shuffles of the day sequence): observed run count is at the
  **0.0th percentile** of the null → **empirical p = 0.0001**.
- **Longest positive run = 65 signal days** (empirical p = 0.0008);
  **longest negative run = 13 signal days** (empirical p = 0.0001).
- Sum of squared run lengths 27,386 vs null 12,611 (p < 0.0001): clustering spans many run lengths,
  not one isolated streak.
- Mean |ΔR between adjacent signal days| = 3.98 vs null 5.80 (p < 0.0001): consecutive days are
  much more alike than chance.

### 2.2 Autocorrelation (R_mean)

| lag | 1 | 2 | 3 | 5 | 10 | 20 | 40 | 60 | 120 |
|---|---|---|---|---|---|---|---|---|---|
| ACF | **0.428** | 0.399 | 0.310 | **0.237** | 0.135 | 0.061 | −0.089 | −0.047 | 0.024 |

Permutation 95% band ≈ [−0.049, +0.051] at every lag → lag 1–20 all far above the null band;
lag 40/60 sit at/inside the band (weak negative). Sign-of-day ACF lag1 = 0.286; win-rate ACF lag1 = 0.390.
**Day-to-day dependence is strong at the 1–20 day scale and decays toward ~40–60 days.**

### 2.3 Conditional persistence

| Conditional quantity | Observed | Unconditional / null | perm p |
|---|---|---|---|
| P(day t+1 positive \| day t positive) | **87.1%** | 81.9% (null 81.9%) | 0.0002 |
| P(day t+1 negative \| day t negative) | **41.5%** | 18.0% (null) | 0.0002 |
| P(next-5d mean > 0 \| current M20 > 0) | 88.6% | 94.2% (null) | 1.00 (NOT elevated) |
| P(next-20d mean < 0 \| current M20 < 0) | **19.3%** | 2.5% (null) | 0.0002 |

Positive days strongly persist; **negative days cluster** (P(neg|neg) is 2.3× the random expectation).
The 20-day rolling-mean sign does carry weak forward information only on the negative side
(P(next-20 mean < 0) rises from ~2.5% to ~19% when current M20 < 0). This is historical dependence
only — not claimed as a tradeable predictor.

### 2.4 Multi-scale block variance ratio

| Block length (signal days) | 5 | 10 | 20 | 40 | 60 | 120 |
|---|---|---|---|---|---|---|
| observed/permutation block-mean variance | 2.43 | 3.79 | **5.09** | 6.94 | **9.57** | 4.54 |
| permutation p | <0.0002 | <0.0002 | <0.0002 | <0.0002 | <0.0002 | <0.0002 |
| % positive blocks | 85% | 89% | 93% | 92% | 92% | 100% |

Block-mean dispersion is **2.4×–9.6× larger than a random reshuffling** at every scale from 5 to 120
days → clustering exists simultaneously at short and medium horizons (peak ratio ~40–60 days).

### 2.5 Calendar pattern (description only)

- Worst months: 2024-05 (−4.96), 2026-05 (−3.01), 2022-01 (−1.13), 2021-12 (−0.87), 2022-02 (−0.25),
  2023-02 (−0.23), 2024-06 (−0.15), 2026-02 (−0.13).
- Best months: 2024-02 (+26.9), 2024-09 (+14.7), 2022-10 (+9.4), 2025-01 (+8.95), 2024-01 (+8.70).
- No calendar-month seasonality is claimed; months simply reflect the performance segments below.

### 2.6 Change-point detection (PERFORMANCE SEGMENTS, not regime)

Two independent, pre-registered methods:

- **A. PELT (mean shift), BIC-style penalty = 2·var·ln(n) = 497.2 (pre-fixed)** → **21 change points**.
- **B. CUSUM binary segmentation, permutation-calibrated 5% threshold = 22.2 (B=1000, pre-fixed)**
  → **15 change points**.

Both methods agree on every major breakpoint:
`2021-12-13 · 2022-03-08/09 · 2023-01-16 · 2024-01-05 · 2024-02-02 · 2024-03-05 ·
2024-09-03 · 2024-10-23 · 2025-12-22 · 2026-07-20` (PELT adds a few single-day extremes).

**Negative performance segments (PELT, mean daily R ≤ 0):**

| Segment | Calendar days | n signal days | mean daily R | win-day % |
|---|---|---|---|---|
| 2020-02-24 → 2020-02-25 | 1 | 2 | −12.13% | 0% |
| 2020-09-18 | 0 | 1 | −36.15% | 0% |
| **2021-12-13 → 2022-03-07** | **84** | 53 | −1.56% | 41.5% |
| 2024-05-09 → 2024-05-14 | 5 | 4 | −17.46% | 0% |
| **2024-05-15 → 2024-07-01** | **47** | 33 | −1.15% | 36.4% |

The 2025-12-22 → 2026-07-17 segment (207 cal days) is *weak-but-positive* (+1.39% daily mean,
60% win days) — the recent 2026 deterioration shows up as compressed edge / lower win rate rather
than a deeply negative regime.

**Cluster duration of negative performance segments:** the two material ones last
**~47 and ~84 calendar days**; single-day negative spikes are rare events.

### 2.7 Quality drawdowns (rolling strategy-quality index, Q20/Q60 < 0)

- **Q20 < 0**: 11 distinct intervals. Three material ones:
  **2024-05-10 → 2024-07-01** (36 signal days, min Q20 = −5.28),
  **2021-12-31 → 2022-02-10** (24 days, min −3.70),
  **2026-05-12 → 2026-06-09** (21 days, min −3.18).
- **Q60 < 0**: only **2** intervals (2022-02-22→2022-03-16, 16 days; 2024-06-11→2024-08-01, 38 days).
  → 60-day-scale quality drawdowns are rare and short; the bad phases are **weeks, not quarters**.

### 2.8 Effective sample size — the 89k illusion

| Estimate | N_eff (signal days) |
|---|---|
| ACF first-zero-crossing (k=30) | **176** |
| ACF Geyer monotone (k=30) | **183** |
| Block bootstrap L=10 / 21 / 40 / 60 | 401 / 291 / 208 / 227 |

**Effective independent signal days ≈ 175–400**, versus 1,494 nominal signal days and 89,046 episodes.
The episode-level count massively overstates independent information; even the signal-day count is
~4–8× too high. Any naive iid-based inference on 89k episodes is invalid.

### 2.9 Cross-sectional synchronization

Day quality buckets (by R_mean percentile):

| Bucket | n days | n episodes | daily win % | daily disp | daily P50 | episode MAE | hold days | episode win % |
|---|---|---|---|---|---|---|---|---|
| Bottom 10% | 150 | 3,114 | **31.6%** | 12.22 | −4.79 | −23.15 | 45.0 | 39.2% |
| 10–25% | 224 | 9,672 | 55.0% | 10.03 | +1.04 | −18.11 | 40.9 | 57.5% |
| 25–75% | 746 | 48,195 | 76.8% | 8.10 | +4.24 | −11.91 | 31.5 | 77.0% |
| 75–90% | 224 | 17,014 | 88.6% | 8.03 | +7.51 | −9.34 | 26.0 | 88.6% |
| Top 10% | 150 | 11,051 | **94.0%** | 10.35 | +13.40 | −9.51 | 25.0 | 92.3% |

Bad days are **broadly synchronized**: on bottom-10% days the daily win rate collapses to ~32%,
dispersion is the highest (many stocks lose together, not one outlier), and episodes drawn into those
windows are deeper (MAE −23%) and longer-held (45 days). This supports a market-wide state, not
idiosyncratic tail luck.

### 2.10 PRIMARY (Top-10) vs SECONDARY

- Overlap 247 days. **Pearson 0.343, Spearman 0.285** between PRIMARY and SECONDARY daily outcomes.
- PRIMARY mean daily return on SECONDARY **bottom-10% days = −5.68%** vs **+5.40%** on other days.
- → the time clustering is a **common property of the whole signal family**, not something specific
  to low-turnover names.

### 2.11 Leave-one-year-out stability

Drop each year (2020…2026) and recompute the core statistics:

| dropped | runs (WW z) | lag1 ACF | block20 var ratio (perm p) | PELT cps | max pos / neg run |
|---|---|---|---|---|---|
| 2020 | −10.53 | 0.452 | 5.64 (0.001) | 16 | 65 / 13 |
| 2021 | −10.44 | 0.447 | 5.14 (0.001) | 20 | 65 / 13 |
| 2022 | −9.38 | 0.421 | 5.24 (0.001) | 20 | 65 / 13 |
| 2023 | −10.36 | 0.424 | 4.91 (0.001) | 18 | 65 / 13 |
| 2024 | −10.20 | 0.365 | 4.42 (0.001) | 17 | 65 / 13 |
| 2025 | −10.23 | 0.428 | 5.43 (0.001) | 19 | 45 / 13 |
| 2026 | −10.07 | 0.435 | 5.18 (0.001) | 18 | 65 / 8 |

Clustering evidence **survives dropping any single year** → **NOT YEAR-DEPENDENT**;
it is a persistent feature across 2020–2026.

---

## 3. Answering the four original questions

1. **Is there temporal clustering?** Yes — overwhelming (runs z −11, lag-1 ACF 0.43, all below
   10,000-permutation nulls).
2. **At what time scales?** 1–20 signal days (ACF), peaking block variance at ~40–60 days; quality
   states persist for **weeks to ~3 months**, rarely longer than 60 days at the Q60 scale.
3. **More than random?** Yes, by every statistic, with permutation p ≤ 0.001; robust to dropping
   any year.
4. **How many effective independent observations?** **~175–400 effective signal days**, not 1,494,
   and not 89,046 episodes.

---

## 4. Classification

### A — STRONG TEMPORAL CLUSTERING

Multiple independent statistics (Wald–Wolfowitz runs, 10,000-day permutation, ACF, persistence,
block variance-ratio, two change-point methods) all reject random temporal ordering, and the
clustering is present across every year (leave-one-year-out). Profitability and losses of this
signal are **strongly state-dependent rather than randomly distributed over time**.

Caveats that do not change the classification:
- Outcome-backfilled diagnostic; no tradeable predictive claim is made here.
- The positive base rate is already 82%; the most decision-relevant structure is that **bad periods
  cluster** (negative runs, negative segments, Q20 drawdowns, and synchronized daily losses).
- The recent (2025-12→2026-07) state is "compressed/weakened edge" (still positive) rather than a
  deep negative regime.

**Proposal (not executed):** proceed to **Phase T2 — Market-State Explanation**, which may only
then introduce Trend/Breadth/Vol/Liquidity/crowding/index state using only information knowable at T.
No filter, no strategy change, no Validation opening, no Registry change until the external auditor
authorizes T2.

---

## 5. Files

- Script: `temporal_clustering_phase_t1.py`
- Results: `results/temporal_daily_series.csv`, `temporal_runs.csv`, `temporal_permutation_null.csv`,
  `temporal_acf.csv`, `temporal_persistence.csv`, `temporal_block_analysis.csv`, `temporal_monthly.csv`,
  `temporal_quarterly.csv`, `temporal_change_points.csv`, `temporal_segments.csv`,
  `temporal_segments_duration.csv`, `temporal_effective_sample_size.csv`, `temporal_quality_drawdowns.csv`,
  `temporal_crosssection_quality.csv`, `temporal_primary_secondary.csv`, `temporal_leave_one_year_out.csv`
- Figures: `figures/daily_signal_return_series.png`, `temporal_acf.png`, `temporal_runs.png`,
  `temporal_block_variance.png`, `monthly_strategy_quality_heatmap.png`, `quarterly_strategy_return.png`,
  `temporal_change_points.png`, `temporal_quality_drawdowns.png`, `primary_secondary_temporal_compare.png`

## 6. Pre-registered / frozen methodological decisions

- Permutation unit = **signal day** (cross-section preserved); B = 10,000 for the main null,
  5,000 for block/persistence, 2,000 for ACF band, 1,000 for CUSUM calibration and LYO block p.
- PELT penalty: **2·var(R_mean)·ln(N)**, fixed before run. CUSUM threshold: 5% permutation quantile, fixed.
- N_eff: ACF first-zero-crossing + Geyer monotone, plus block-bootstrap sensitivity (range reported).
- Positive day = R_mean > 0; negative = R_mean ≤ 0.
- Registry SHA256 unchanged: `5c5e451ad4eb3afd5e632b0019a3e02103e58e375e03cc231c5d8ca52b8c5195`.
- Validation 2023–2024 and Confirmation 2025–2026 not opened; no parameters altered.
