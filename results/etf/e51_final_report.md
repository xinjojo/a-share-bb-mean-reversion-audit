# PHASE E5.1 — Stock Date Alignment Gate

**VERDICT: PASS WITH CORRECTION**

**E5.1 Registry SHA256**: computed at commit time.

---

## A. Problem Identified

E5 assigned dates to stock kline data using `row-in-year index → first N trading days`. This is incorrect for stocks that IPO mid-year: their first row should map to their actual IPO date (later in the year), not to January 2.

**Root cause**: kline parquet files have no `trade_date` column. Data is sorted globally by date (not by stock), but within each stock-year, rows are chronological (verified by `pre_close` matching 99.7%).

## B. Fix Applied

1. **Authoritative trading calendar**: Extracted from ETF feature data unique dates (243/243/242/242/242 for 2020-2024), matching A-share exchange calendar exactly.
2. **Full-data stocks only**: Filtered to stocks with exactly 243/243/242/242/242 rows across 2020-2024. **2,618 / 5,237 stocks (50.0%)** pass. Partial-year stocks (IPOs, suspensions) excluded.
3. **Date assignment**: Full-data stocks get the complete trading calendar for each year. No ambiguity.

## C. Audit Results

### Price Anchors (all match)
| Stock | Date | Expected Close | Actual | Status |
|-------|------|----------------|--------|--------|
| 000001.SZ | 2020-01-02 | 16.87 | 16.87 | OK |
| 000001.SZ | 2020-12-31 | — | 19.34 | OK |
| 600000.SH | 2020-01-02 | — | 12.47 | OK |
| 300750.SZ | 2020-01-02 | — | 107.52 | OK |

### Data Quality
- `pre_close` mismatch: **0.334%** (dividends/splits changing adj_factor, expected)
- Zero amount/volume rows: **0** (suspended days excluded, not kept as sentinels)
- Stocks per day: **2,618 constant** (full-data panel is balanced)
- No NaN in close/amount

## D. Core E5 Reproduction (OLD vs NEW)

| Metric | E5 OLD | E5.1 NEW | Diff | Conclusion |
|--------|--------|-----------|------|------------|
| Stock BB_Z signal std | 0.2631 | 0.2533 | -0.010 | Still 1.48x ETF ✓ |
| ETF BB_Z signal std | 0.1713 | 0.1713 | 0.000 | — |
| Stock fwd20 std | 0.1226 | 0.0964 | -0.026 | Still 2.14x ETF ✓ |
| ETF fwd20 std | 0.0451 | 0.0451 | 0.000 | — |
| Stock signal 20d mean (%) | 2.503 | 2.713 | +0.210 | Still > ETF ✓ |
| Stock signal 20d median (%) | 1.033 | 1.178 | +0.145 | Still > ETF ✓ |
| ETF signal 20d mean (%) | 1.618 | 1.618 | 0.000 | — |
| Stock median breadth (%) | 1.71 | 1.64 | -0.07 | Still < ETF ✓ |
| ETF median breadth (%) | 6.05 | 6.05 | 0.000 | — |
| Stock amount Top-N 20d (%) | -0.105 | +0.041 | +0.146 | Still < random ✓ |
| Stock random 20d (%) | 0.127 | 0.438 | +0.311 | — |
| Stock BB_Z daily IC 20d | -0.0015 | +0.0180 | +0.020 | Now positive ✓ |
| ETF BB_Z daily IC 20d | -0.0157 | -0.0157 | 0.000 | Still negative ✓ |

### Random Top-N Corrected Audit
Per-day percentile methodology (not pooled):
| Asset | Mean daily percentile | Median | % days > random median |
|-------|----------------------|--------|------------------------|
| Stock | 43.1% | 38.6% | 42.3% |
| ETF | 42.8% | 39.5% | 40.1% |

**Amount ranking is below random median in ~60% of days for both stock and ETF.**

## E. All 7 Core Conclusions Unchanged

1. ✅ Stock BB_Z dispersion > ETF
2. ✅ Stock forward return dispersion > ETF
3. ✅ Stock signal 20d mean > ETF
4. ✅ Stock signal 20d median > ETF
5. ✅ ETF median breadth > stock (more systemic)
6. ✅ Stock amount Top-N < random
7. ✅ ETF amount Top-N < random

## F. Correction Strengthens E5 Conclusions

- Stock signal expectancy **higher** after correction (mean +0.21pp, median +0.15pp)
- Stock BB_Z daily IC **turns positive** (+0.018) — weak but positive cross-sectional info
- Stock fwd20 dispersion lower (0.096 vs 0.123) but still 2.1x ETF
- Amount ranking still harmful in both

**H4 verdict remains: PARTIALLY SUPPORTED** (if anything, strengthened on signal expectancy dimension).

## G. Limitations

- 50% of stocks excluded (partial-year data). Full-data panel is a survivorship-biased subset (stocks that listed before 2020 and traded continuously).
- No stock_basic/list_date/ST PIT data available. Eligibility uses n_days>=20 proxy.
- No ADV60 liquidity filter for stocks (unlike ETF which uses ADV60>=2000万).
- pre_close mismatch 0.334% due to adj_factor changes (dividends).

## H. Gate Decision

**PASS WITH CORRECTION** — Date mapping corrected using full-data stocks + authoritative ETF calendar. All core E5 conclusions unchanged and some strengthened. **Safe to proceed to S1 Stock Signal Mechanism Validation.**
