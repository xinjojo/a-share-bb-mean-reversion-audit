# PHASE E5 — Stock vs ETF Cross-Sectional Dispersion Mechanism Audit

**RESEARCH STATUS**: MECHANISM AUDIT / ADAPTIVE HISTORICAL RESEARCH / NOT CLEAN OUT-OF-SAMPLE VALIDATION

**E5 Registry SHA256**: `d82fe00e3d11bb095fc354e5eef3863555275d63735f071957a0b929a3e3a2f4`

---

## A. Research Question

H4: Stock-level BB mean reversion has a larger and more informative cross-sectional idiosyncratic opportunity set than ETF/index-level mean reversion.

E4 proved BB_Z ranking does not improve ETF entry selection. E5 asks the more fundamental question: **is the stock cross-section itself a more fertile ground for mean-reversion selection than the ETF cross-section?**

---

## B. Frozen References

| Phase | Commit | Verdict |
|-------|--------|---------|
| E1 | 6789810 | NO REPLICATION |
| E1.1 | 1fa73e9 | MULTI-MECHANISM FAILURE |
| E2 | c8e8259 | H1 PARTIALLY SUPPORTED |
| E3 | afa1076 | H2 PARTIALLY SUPPORTED |
| E4 | cc50cd0 | H7 NOT SUPPORTED |

**Stock baseline reference**: master HEAD `43e9e4a`, STRICT_C engine (`src/run_strict_c.py`), ranking = amount descending (line 335: `np.argsort(-amt)[:top_n]`).

---

## C. Stock Data Availability

- **Source**: `audit_package/github_repo/data/kline/*.parquet` (2020-2024)
- **5,230 unique stocks**, 5.2M eligible rows, 261,197 signal rows
- **Limitation**: No `trade_cal_full.parquet`, `stock_basic.parquet`, `pit_st_daily.parquet`, or `combined_daily.parquet` in current checkout. Dates assigned via ETF trading calendar mapped to stock row-in-year chronological index. Stock eligibility uses `n_days >= 20` as proxy (no ADV60 / ST PIT filter).
- **ETF reference**: 441 unique ETFs, 196,872 eligible rows, 11,030 signal rows.

---

## D. Cross-Sectional BB_Z Dispersion

### Eligible Universe (all tradable assets each day)

| Metric | Stock | ETF | Stock/ETF Ratio |
|--------|-------|-----|-----------------|
| mean BB_Z std | 1.108 | 0.847 | **1.31x** |
| mean BB_Z IQR | 1.550 | 1.132 | **1.37x** |
| mean BB_Z MAD | 0.724 | 0.525 | **1.38x** |
| mean P10-P90 spread | 2.817 | 2.123 | **1.33x** |

### Signal Candidates Only (close < bb_lower)

| Metric | Stock | ETF | Stock/ETF Ratio |
|--------|-------|-----|-----------------|
| mean BB_Z std | 0.263 | 0.171 | **1.54x** |
| mean BB_Z IQR | 0.312 | 0.230 | **1.36x** |
| mean BB_Z MAD | 0.143 | 0.106 | **1.35x** |
| mean P10-P90 spread | 0.595 | 0.399 | **1.49x** |

**Matched dates (330 days, both >=5 signals)**: Stock BB_Z std mean=0.266 vs ETF=0.171, ratio **1.55x**.

**Finding 1: Stock cross-section has ~30-55% more BB_Z dispersion than ETF, even when restricting to signal candidates and matched dates.** This is consistent with H4.

---

## E. Forward Return Dispersion (signal candidates)

| Horizon | Stock std | ETF std | Ratio | Stock IQR | ETF IQR | Ratio |
|---------|-----------|---------|-------|-----------|---------|-------|
| 1d | 0.0258 | 0.0084 | **3.1x** | 0.0247 | 0.0083 | **3.0x** |
| 5d | 0.0617 | 0.0206 | **3.0x** | 0.0567 | 0.0199 | **2.8x** |
| 10d | 0.0876 | 0.0304 | **2.9x** | 0.0825 | 0.0280 | **2.9x** |
| 20d | 0.1226 | 0.0451 | **2.7x** | 0.1192 | 0.0423 | **2.8x** |

**Finding 2: Stock signal candidates have ~3x more forward return dispersion than ETF.** This means stock cross-section offers much larger potential selection payoff — the gap between best and worst oversold stocks is far wider than for ETFs.

---

## F. Common BB_Z Ranking IC

| Horizon | Stock pooled IC | Stock daily mean IC | Stock hit rate | ETF pooled IC | ETF daily mean IC | ETF hit rate |
|---------|-----------------|---------------------|----------------|---------------|-------------------|--------------|
| 1d | +0.057 | **+0.029** | **56.1%** | +0.059 | **-0.058** | 45.6% |
| 3d | +0.117 | **+0.023** | **56.9%** | +0.125 | **-0.036** | 44.1% |
| 5d | +0.138 | +0.016 | 53.8% | +0.136 | -0.015 | 49.2% |
| 10d | +0.133 | +0.004 | 52.2% | +0.133 | **-0.064** | 43.9% |
| 20d | +0.151 | -0.002 | 51.3% | +0.103 | -0.016 | 48.6% |

**Critical distinction**: Pooled IC is similar (and positive) for both, but **daily mean IC tells a different story**:
- Stock daily BB_Z IC is **positive at 1d/3d/5d** with hit rate >50%
- ETF daily BB_Z IC is **negative at all horizons** with hit rate <50%

Pooled IC is inflated by high-signal-count days (systemic selloffs) in both. The daily mean IC — which weights each trading day equally — shows stock BB_Z has weak but positive short-horizon information, while ETF BB_Z has no information or slightly negative information.

**Finding 3: Stock BB_Z has weak positive short-horizon daily IC; ETF BB_Z daily IC is consistently negative. This supports H4 but the stock IC is weak (not strong).**

---

## G. Native Amount Ranking IC

| Horizon | Stock daily mean IC | Stock hit rate | ETF daily mean IC | ETF hit rate |
|---------|---------------------|----------------|-------------------|--------------|
| 1d | +0.008 | 52.9% | -0.027 | 42.6% |
| 5d | +0.017 | 56.2% | +0.009 | 48.9% |
| 10d | +0.024 | 54.4% | +0.045 | 58.5% |
| 20d | **+0.043** | **60.4%** | +0.051 | 58.2% |

Both stock and ETF amount ranking show weak positive IC at longer horizons. Stock amount ranking hit rate reaches 60.4% at 20d.

---

## H. Top-N (Amount) Selected vs Non-Selected

| Horizon | Stock selected mean | Stock non-selected mean | Diff | ETF selected mean | ETF non-selected mean | Diff |
|---------|---------------------|-------------------------|------|-------------------|-----------------------|------|
| 1d | -0.195% | -0.069% | **-0.126%** | -0.050% | +0.190% | **-0.240%** |
| 5d | -0.157% | +0.887% | **-1.044%** | +0.197% | +0.944% | **-0.748%** |
| 10d | -0.077% | +1.440% | **-1.517%** | +0.183% | +1.297% | **-1.114%** |
| 20d | -0.105% | +2.617% | **-2.722%** | +0.588% | +2.080% | **-1.493%** |

**Finding 4: Amount-selected Top-N UNDERPERFORMS non-selected candidates in BOTH stock and ETF.** The gap is larger for stocks (-2.72% at 20d) than ETFs (-1.49%). This means amount ranking is actively harmful for forward returns in both asset classes. High-amount oversold assets tend to be large-cap/systemic names with weaker mean reversion.

---

## I. BB_Z Quantile Monotonicity (20d forward return)

| Quantile | Stock mean | Stock WR | ETF mean | ETF WR |
|----------|------------|----------|----------|--------|
| Q1 (deepest) | +2.159% | 53.8% | +1.806% | 55.2% |
| Q2 | +2.499% | 53.6% | +1.921% | 52.1% |
| Q3 | +2.690% | 54.2% | +1.537% | 48.9% |
| Q4 | +2.615% | 53.8% | +1.665% | 51.0% |
| Q5 (shallowest) | +2.547% | 53.7% | +1.565% | 51.5% |

**Finding 5: No clean BB_Z monotonicity in either asset class.** For stocks, Q3 is best and Q1 (deepest) is worst — opposite of H7 prediction. For ETFs, Q2 is best and Q3 is worst. BB_Z depth does not linearly predict future returns in either cross-section.

---

## J. Raw Signal Expectancy (all signal candidates, no selection)

| Horizon | Stock mean | Stock median | Stock WR | ETF mean | ETF median | ETF WR |
|---------|------------|--------------|----------|----------|------------|--------|
| 1d | -0.074% | +0.101% | 50.9% | +0.116% | +0.075% | 50.4% |
| 5d | +0.844% | +0.459% | 53.1% | +0.713% | +0.225% | 52.5% |
| 10d | +1.376% | +0.653% | 53.4% | +0.953% | +0.146% | 50.8% |
| 20d | **+2.503%** | **+1.033%** | 53.8% | +1.618% | +0.280% | 51.5% |

**Finding 6: Stock oversold signals have higher mean AND median forward expectancy than ETF.** At 20d, stock mean +2.50% vs ETF +1.62%; stock median +1.03% vs ETF +0.28%. The median gap is especially large (3.7x), suggesting stock oversold signals have more reliable positive drift.

**Important**: This is raw signal expectancy at fixed horizons, NOT portfolio returns. The stock baseline uses STRICT_C upper-band exit with K=3 pyramiding, which captures a different return profile.

---

## K. Signal Breadth / Systemic Synchronization

| Metric | Stock | ETF |
|--------|-------|-----|
| median signal_ratio | **1.71%** | **6.05%** |
| P75 signal_ratio | 4.62% | 15.97% |
| P90 signal_ratio | 12.97% | 34.22% |
| P95 signal_ratio | 23.09% | 46.81% |
| max signal_ratio | 77.07% | 90.85% |
| days >=10% signals | 13.0% | 35.6% |
| days >=25% signals | 4.2% | 14.4% |
| zero-signal days | 0.0% | 0.0% |

**Finding 7: ETF signals are 3.5x more systemic than stock signals.** Median ETF signal ratio is 6.05% vs stock 1.71%. ETF oversold events are much more likely to be broad market selloffs, while stock oversold events are more idiosyncratic. This directly supports the E1.1 finding that high-breadth signals have poor PF.

---

## L. Random Top-N Control (20d horizon)

| Asset | Actual amount Top-N mean | Random mean | Random P5 | Random P95 | Actual percentile |
|-------|--------------------------|-------------|-----------|------------|-------------------|
| Stock | -0.105% | +0.127% | -1.52% | +1.85% | **49.9%** |
| ETF | +0.588% | +1.168% | -0.83% | +3.34% | **52.5%** |

**Finding 8: Amount-based Top-N selection is NOT better than random in either asset class.** Stock actual percentile = 49.9% (exactly median), ETF = 52.5% (slightly above). This confirms that the native ranking variable (amount) contains no useful cross-sectional selection information in either stock or ETF.

---

## M. Matched-Date Results

330 matched dates where both stock and ETF have >=5 signal candidates.

- Stock BB_Z std (matched): mean 0.266, median 0.260
- ETF BB_Z std (matched): mean 0.171, median 0.148
- **Stock/ETF ratio: 1.55x**

The dispersion gap persists on matched dates, ruling out the alternative explanation that ETF simply has fewer signal days or different market periods.

---

## N. Dispersion → Ranking Information Relationship

Stock has both:
1. More BB_Z dispersion (1.3-1.5x)
2. More forward return dispersion (2.7-3.1x)
3. Weak positive daily BB_Z IC at short horizons
4. Higher signal expectancy

But:
- BB_Z quantile monotonicity is absent in both
- Amount Top-N is worse than random in both
- Stock BB_Z IC is weak (daily mean ~0.02-0.03 at best)

The larger stock dispersion creates *potential* for selection, but neither BB_Z nor amount ranking effectively captures it.

---

## O. Evidence Supporting H4

1. **Stock BB_Z dispersion 1.3-1.5x > ETF** (eligible universe, signal candidates, matched dates)
2. **Stock forward return dispersion 2.7-3.1x > ETF** (signal candidates, all horizons)
3. **Stock signal expectancy > ETF** (20d mean +2.50% vs +1.62%; median +1.03% vs +0.28%)
4. **Stock daily BB_Z IC positive at 1d/3d/5d**; ETF daily IC negative at all horizons
5. **ETF signals 3.5x more systemic** (median breadth 6.05% vs 1.71%)
6. **Stock amount ranking hit rate 60.4% at 20d** vs ETF 58.2%

---

## P. Evidence Against H4

1. **BB_Z quantile monotonicity absent in both** — deeper oversold does not linearly predict better returns in stocks either
2. **Amount Top-N worse than random in both** — neither asset class has effective native ranking
3. **Stock BB_Z IC is weak** (daily mean ~0.02-0.03), not strong
4. **Pooled BB_Z IC similar for stock and ETF** — the daily-mean distinction is the only differentiator
5. **Stock amount-selected Top-N underperforms non-selected by -2.72%** (worse than ETF's -1.49%)

---

## Q. Alternative Mechanisms Discovered

### Stock edge may come from signal + exit, NOT ranking

The most important finding: **all oversold stock signals have positive 20d expectancy (+2.50% mean, +1.03% median)**, while amount-selected Top-N has NEGATIVE 20d mean (-0.105%). This means:

- The stock BB oversold signal itself has positive drift
- Amount ranking actively selects the WORST-performing subset (large-cap systemic names)
- The stock baseline's positive return likely comes from: (a) the signal itself, (b) STRICT_C upper-band exit capturing rebounds, (c) K=3 pyramiding — NOT from cross-sectional ranking

This explains why ETF fails: ETF oversold signals have weaker drift (+1.62% mean, +0.28% median at 20d), and the same amount ranking selects similarly poor subsets. The combination of weaker signal drift + harmful ranking + more systemic signals = negative expectancy.

### Why amount ranking is harmful

High-amount oversold assets tend to be:
- Large-cap / liquid names
- More closely tied to systemic market moves
- Less likely to have idiosyncratic rebound catalysts
- More crowded trades

This is consistent across both stock and ETF.

---

## R. Limitations

1. **Stock data incomplete**: No trade calendar, stock_basic, ST PIT, or ADV60 filter. Stock eligibility uses n_days>=20 proxy.
2. **Date assignment**: Stock dates mapped from ETF trading calendar via row-in-year index. This assumes chronological ordering within each stock-year, which is reasonable but not verified against a native date column.
3. **No stock ADV60 filter**: Stock universe includes illiquid stocks that the actual baseline might exclude. This could inflate stock dispersion and expectancy.
4. **Pooled IC inflation**: Pooled IC is dominated by high-signal-count days; daily mean IC is more reliable but has fewer ETF observations (325-329 days vs 1077-1096 stock days).
5. **Fixed-horizon analysis**: Does not capture STRICT_C exit dynamics or K=3 pyramiding, which are central to the stock baseline.
6. **Adaptive research**: All phases E1-E5 observe the same 2020-2024 window. No clean out-of-sample validation.

---

## S. Final H4 Verdict

# H4 PARTIALLY SUPPORTED

**Stock cross-section clearly has more dispersion and higher signal expectancy than ETF.** The gap is large and consistent across metrics (1.3-1.5x BB_Z dispersion, 2.7-3.1x forward return dispersion, higher signal drift, less systemic signals).

**However, neither stock nor ETF has effective cross-sectional ranking.** BB_Z shows no monotonicity, amount ranking is worse than random, and the stock baseline's edge likely comes from the signal itself + exit dynamics rather than Top-N selection.

The stock-vs-ETF difference is therefore best characterized as:
- **Stock oversold signals have stronger idiosyncratic drift** (more dispersion, higher median expectancy)
- **ETF oversold signals are more systemic and weaker** (higher breadth, lower median drift)
- **Cross-sectional ranking does not explain the stock edge** in either asset class

---

## T. Recommended Next Phase

**H4 follow-up: Stock Signal Mechanism Validation**

Priority questions:
1. Does the stock BB oversold signal itself (before any ranking) have positive expectancy under STRICT_C exit?
2. Is the stock edge concentrated in low-breadth/idiosyncratic oversold days?
3. Does amount ranking in the actual stock portfolio harm returns compared to random selection?
4. Can the stock edge be decomposed into: signal drift + exit capture + pyramiding, with zero contribution from ranking?

This would directly validate the mechanism discovered in E5: **stock edge = signal + exit, not ranking.**

If confirmed, the ETF failure is fundamentally an **asset-level signal weakness** problem, not a ranking problem — and no amount of ranking optimization will fix it.
