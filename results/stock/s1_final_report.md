# PHASE S1 — Stock Signal Mechanism Validation

**RESEARCH STATUS**: MECHANISM AUDIT / ADAPTIVE HISTORICAL RESEARCH / NOT STRATEGY OPTIMIZATION

**S1 Registry**: `research/stock/PHASE_S1_REGISTRY.csv`

**E5.1 Gate**: PASS WITH CORRECTION (date alignment verified, all E5 conclusions unchanged)

---

## A. Research Question

What does the frozen stock BB Mean Reversion baseline actually earn? Is it:
- The raw BB oversold signal itself?
- Amount ranking / Top-N selection?
- STRICT_C upper-band exit capture?
- K=3 pyramid / add logic?
- Breadth / dispersion conditioning?

**NO OPTIMIZATION.** Only mechanism diagnostics on frozen configuration.

---

## B. Frozen Stock Baseline

| Parameter | Value |
|-----------|-------|
| Engine | STRICT_C (dynamic intraday upper-band touch / Pstar) |
| BB | window=20, sigma=2.0 |
| Entry | close_adj < bb_lower |
| Ranking | amount descending, Top-N=10 |
| Execution | T close signal → T+1 open fill |
| Exit | STRICT_C: first intraday touch of dynamic upper band (Pstar) |
| Pyramid | K=3, max_levels=5, level_cash=200k |
| Cost | commission 0.025% min ¥5, slippage 10bp, stamp tax historical |
| Official G0 result | +30.30% total, CAGR +5.66%, MaxDD -30.79%, Sharpe 0.347, 76 trades, WR 68.4%, PF 1.304 |

**Trade log used**: `strict_c_trades.csv` filtered to 2020-2024 → 74 trades, WR 68.9%, total PnL ¥265,582.

**Stock panel**: E5.1 corrected — 2,618 full-data stocks, ETF trading calendar, 2020-2024. 150,012 signal rows.

---

## C. Raw Signal Expectancy (B2)

All BB oversold signals, NO ranking, NO portfolio. Fixed-horizon forward returns.

| Horizon | Count | Mean (%) | Median (%) | WR (%) | P10 (%) | P90 (%) | Std (%) |
|---------|-------|----------|------------|--------|---------|---------|---------|
| 1d | 149,761 | +0.03 | +0.15 | 51.8 | -3.46 | +3.41 | 3.23 |
| 3d | 149,710 | +0.53 | +0.33 | 52.9 | -5.16 | +6.67 | 5.68 |
| 5d | 149,113 | +1.13 | +0.62 | 54.7 | -5.83 | +8.75 | 6.93 |
| 10d | 148,068 | +1.52 | +0.69 | 53.9 | -8.66 | +12.69 | 10.25 |
| **20d** | **147,745** | **+2.71** | **+1.18** | **54.8** | **-10.77** | **+17.46** | **13.17** |
| 40d | 147,155 | +4.12 | +1.79 | 55.3 | -15.13 | +25.00 | 18.97 |
| 60d | 147,106 | +5.12 | +1.76 | 54.5 | -17.40 | +30.08 | 23.10 |

**Finding C1: Raw BB oversold signal has strongly positive drift at all horizons ≥3d.** 20d mean +2.71%, median +1.18%. The signal itself is the primary source of edge.

**Finding C2: Signal decay is monotonic** — 1d +0.03% → 5d +1.13% → 20d +2.71% → 60d +5.12%. Mean reversion accumulates over ~1-2 months. Median plateaus around 40-60d (+1.76-1.79%), suggesting mean reversion completes by ~40d.

---

## D. Amount Ranking Contribution (B4-B5)

### Top-N (amount) vs All Signals vs Non-Selected

| Horizon | All signals mean | Top-N amount mean | Non-selected mean | Top-N − All | Top-N − Non-sel |
|---------|-----------------|-------------------|-------------------|-------------|-----------------|
| 5d | +1.13% | **-0.14%** | +1.23% | -1.27pp | -1.37pp |
| 10d | +1.52% | +0.00% | +1.64% | -1.52pp | -1.64pp |
| 20d | +2.71% | **+0.04%** | +2.91% | -2.67pp | -2.87pp |
| 40d | +4.12% | +0.83% | +4.36% | -3.29pp | -3.53pp |

### Random Top-N Control (20d, per-day methodology)

| Metric | Value |
|--------|-------|
| Mean daily percentile | **43.1%** |
| Median daily percentile | 38.6% |
| % days actual > random median | **42.3%** |
| Pooled actual mean | +0.041% |
| Pooled random expected mean | +0.438% |
| Diff (actual − random) | **-0.397pp** |

**Finding D1: Amount ranking is ACTIVELY HARMFUL.** Top-N amount underperforms all signals by -2.67pp at 20d, and underperforms non-selected by -2.87pp. In 57.7% of days, amount Top-N is below the random median.

**Finding D2: High-amount oversold stocks are large-cap/systemic names with weaker mean reversion.** Amount ranking selects exactly the subset with the worst recovery. This is consistent with E5 finding that amount ranking is also harmful for ETFs.

**Finding D3: The stock baseline's edge does NOT come from amount ranking.** If anything, amount ranking drags performance down. The edge comes from the signal itself + exit capture.

---

## E. Exit Capture (B6)

MAE/MFE and BB band hits for 66 actual trades with full price path.

| Metric | All Trades | Winners (45) | Losers (21) |
|--------|-----------|--------------|-------------|
| Median MAE | -9.3% | -6.6% | **-18.8%** |
| Median MFE | +4.7% | +6.1% | +2.4% |
| Hit BB midline | **100.0%** | 100% | 100% |
| Hit BB upper | **98.5%** | 100% | 95.2% |
| MFE>0 but final loss | — | — | **76.2%** |
| Median hold days | 30 | **23** | **50** |

**Finding E1: STRICT_C exit is highly effective at capturing rebounds.** 98.5% of trades hit the upper band. 100% hit midline. The dynamic Pstar exit correctly identifies when mean reversion has completed.

**Finding E2: Losers are rare but painful.** Only 21/66 (31.8%) are losers, but their median MAE is -18.8% and they hold for 50 days (vs 23 for winners). 76.2% of losers had positive MFE before relapsing.

**Finding E3: Stock exit works far better than ETF exit.** Stock upper hit rate 98.5% vs ETF 60%. Stock loser median hold 50d vs ETF 341d. Stock MFE>0-but-lost 76.2% vs ETF 95%. Stocks don't get trapped in multi-hundred-day losing positions.

---

## F. Path Classification (B7)

| Classification | Count | % |
|----------------|-------|---|
| CLEAN_MEAN_REVERSION | 42 | 63.6% |
| CRASH_CONTINUATION | 12 | 18.2% |
| OTHER | 6 | 9.1% |
| REBOUND_THEN_RELAPSE | 6 | 9.1% |

**Finding F1: 63.6% of stock trades are clean mean reversion** — signal → rebound → upper-band exit → profit. Only 9.1% are rebound-then-relapse (vs ETF where 95% of losers were this type).

**Finding F2: Stock failure mode is CRASH_CONTINUATION (18.2%)**, not rebound-then-relapse. When stocks fail, they tend to keep falling immediately rather than bouncing first. This is fundamentally different from ETF failure.

---

## G. Profit Factor Decomposition (B8)

| Metric | Value |
|--------|-------|
| Total trades | 74 |
| Winners | 51 (68.9%) |
| Losers | 23 (31.1%) |
| Gross profit | ¥1,432,120 |
| Gross loss | ¥1,166,538 |
| **Profit Factor** | **1.228** |
| Avg winner | ¥28,081 |
| Avg loser | ¥50,720 |
| **Payoff ratio** | **0.554** |
| Breakeven win rate | 64.4% |
| Actual win rate | 68.9% |
| **Excess over breakeven** | **+4.5pp** |
| Expectancy per trade | +¥3,589 |

**Finding G1: Stock strategy wins through HIGH WIN RATE, not high payoff.** Payoff ratio is only 0.554 (avg winner is half the avg loser). The 68.9% win rate exceeds the 64.4% breakeven by 4.5pp, producing PF=1.228.

**Finding G2: This is fundamentally different from ETF.** ETF M2 LowBreadth: WR 68.1%, PF 0.937, payoff ~0.39. ETF has similar win rate but much worse payoff, so it can't break even. Stock's better payoff (0.554 vs 0.39) comes from better exit capture and shorter loser holds.

---

## H. K=3 Pyramid / Add Attribution (B9)

By `levels_used` (number of add lots including initial):

| Levels | Count | Total PnL | Mean PnL | Mean Return | WR | Mean Hold |
|--------|-------|-----------|----------|-------------|-----|-----------|
| 1 | 21 | +¥305,188 | +¥14,533 | **+7.37%** | **85.7%** | 20d |
| 2 | 27 | +¥650,048 | +¥24,076 | +6.43% | 81.5% | 34d |
| 3 | 18 | -¥53,464 | -¥2,970 | -0.56% | 55.6% | 38d |
| 4 | 4 | -¥120,858 | -¥30,215 | -3.70% | 25.0% | 57d |
| **5** | **4** | **-¥515,331** | **-¥128,833** | **-13.89%** | **0.0%** | **110d** |

**Finding H1: K=3 pyramid is DANGEROUS at higher levels.** Level 1 (no adds): 85.7% WR, +7.37%. Level 2: 81.5% WR, +6.43%. Level 3: 55.6% WR, -0.56%. Level 4: 25% WR, -3.70%. **Level 5: 0% WR, -13.89%, 110-day average hold.**

**Finding H2: Adding to losing positions is the primary risk mechanism.** When a position needs 4-5 levels (i.e., keeps dropping and triggering adds), it almost always ends in a large loss. The K=3 add logic amplifies losers rather than averaging into winners.

**Finding H3: The stock baseline would likely perform BETTER without K=3 adds.** Level 1-2 trades are highly profitable (81-86% WR, +6-7% mean). Level 3-5 trades destroy value. This is a mechanism finding, not a recommendation — no optimization in S1.

---

## I. Breadth Conditioning (B11)

Raw signal 20d return by signal_ratio bins:

| Breadth Bin | Count | Mean 20d (%) | Median 20d (%) | WR (%) | Std (%) |
|-------------|-------|---------------|-----------------|--------|---------|
| 0-5% | 30,224 | **-0.06** | -1.33 | 43.8 | 12.0 |
| 5-10% | 24,787 | +1.20 | +0.12 | 50.3 | 12.2 |
| 10-25% | 45,968 | +1.67 | +0.57 | 52.4 | 12.6 |
| **25%+** | **49,033** | **+6.09** | **+4.26** | **65.9** | 14.1 |

**Finding I1: STOCK BREADTH EFFECT IS OPPOSITE TO ETF.** For stocks, HIGH breadth (systemic selloff) produces the strongest mean reversion (+6.09% at 20d, 65.9% WR). LOW breadth (idiosyncratic oversold) produces NEGATIVE expectancy (-0.06%, 43.8% WR).

**Finding I2: This is the most important stock-vs-ETF mechanism difference.** For ETFs, E3 found high-breadth PF=0.18 vs low-breadth PF=0.89 (high breadth = bad). For stocks, high breadth = excellent. The reason: stock systemic selloffs create widespread oversold conditions that reverse strongly (individual stocks recover even when the index falls), while ETF systemic selloffs reflect index-level declines that persist.

**Finding I3: The stock baseline implicitly benefits from high-breadth environments.** Amount Top-N selects large-cap stocks which are more likely to have signals during systemic selloffs, and those are the best environments. But amount ranking still underperforms within those environments.

---

## J. Dispersion Conditioning (B12)

Raw signal 20d return by signal-day BB_Z std tercile:

| Dispersion | Count | Mean 20d (%) | Median 20d (%) | WR (%) |
|------------|-------|---------------|-----------------|--------|
| LOW | 50,073 | +3.52 | +1.09 | 53.9 |
| MID | 50,345 | +1.09 | +0.15 | 50.4 |
| HIGH | 49,561 | **+3.58** | **+2.30** | **60.1** |

**Finding J1: U-shaped dispersion pattern.** Both LOW and HIGH dispersion days have good expectancy (+3.5%), while MID dispersion days are weakest (+1.09%). HIGH dispersion has the highest WR (60.1%) and median (+2.30%).

**Finding J2: High dispersion + high breadth = best stock environment.** When many stocks are oversold (high breadth) AND they have diverse BB_Z values (high dispersion), stock mean reversion is strongest. This is consistent with the signal being most powerful during genuine systemic stress with cross-sectional variation.

---

## K. Stock vs ETF Mechanism Comparison (B14)

| Mechanism | Stock | ETF (M2 LowBreadth) | Difference |
|-----------|-------|---------------------|------------|
| Raw signal 20d mean | **+2.71%** | +1.62% | Stock +1.09pp |
| Raw signal 20d median | **+1.18%** | +0.28% | Stock +0.90pp |
| Raw signal 20d WR | 54.8% | 51.5% | Stock +3.3pp |
| Signal 20d std | 13.2% | 8.9% | Stock more dispersion |
| Median breadth | **1.64%** | 6.05% | ETF 3.7x more systemic |
| BB_Z signal std | 0.252 | 0.171 | Stock 1.47x more dispersion |
| Amount Top-N 20d | +0.04% | +0.70% | Both weak |
| Amount random 20d | +0.44% | +1.16% | Both > actual |
| Amount daily percentile | 43.1% | 42.8% | **Both harmful** |
| PF baseline | **1.228** | 0.937 | Stock >1, ETF <1 |
| Win rate | 68.9% | 68.1% | Similar |
| Payoff ratio | **0.554** | 0.39 | Stock much better |
| Breakeven WR | 64.4% | 71.7% | Stock easier to beat |
| Mid hit rate | 100% | 100% | Same |
| **Upper hit rate** | **98.5%** | **60%** | **Stock far better** |
| MFE>0 but lost | 76.2% | 95% | Stock fewer relapses |
| Winner median hold | 23d | 37d | Stock faster |
| **Loser median hold** | **50d** | **341d** | **Stock no trapped losers** |
| High-breadth signal 20d | **+6.09%** | (PF 0.18) | **OPPOSITE effect** |

---

## L. Primary Mechanism Verdict

# MULTI-COMPONENT EDGE

**Primary components (by evidence strength):**

1. **SIGNAL-DOMINATED EDGE** — Raw BB oversold signal has strongly positive drift at all horizons ≥3d (20d +2.71%, 60d +5.12%). This is the foundation.

2. **EXIT-CAPTURE DOMINATED EDGE** — STRICT_C upper-band exit captures 98.5% of rebounds. Loser holds are short (50d median vs ETF 341d). Payoff ratio 0.554 is better than ETF 0.39 because exit works.

3. **SELECTION NOT CONTRIBUTING (amount harmful)** — Amount Top-N underperforms all signals by -2.67pp at 20d. Daily percentile 43.1%. Ranking is a drag, not a source of edge.

4. **PYRAMID HIGHER LEVELS HARMFUL** — Level 4-5 trades are massively unprofitable (0% WR at Level 5). K=3 adds amplify losers.

**Secondary mechanism:**
- **High-breadth systemic selloffs** are the best environment for stock mean reversion (+6.09% at 20d), opposite to ETF.
- **High dispersion days** also favor stock signals.

---

## M. Why ETF Fails — Mechanism Explanation

S1 directly explains E1's NO REPLICATION:

1. **ETF raw signal is weaker** — 20d mean +1.62% vs stock +2.71%, median +0.28% vs +1.18%. ETF oversold signals have less drift.

2. **ETF exit fails** — Only 60% hit upper band (vs 98.5% stock). ETF losers get trapped for 341 days (vs 50 stock). 95% of ETF losers rebound then relapse (vs 76% stock).

3. **ETF payoff is worse** — 0.39 vs 0.554. With similar win rates (~68%), ETF can't beat breakeven (71.7% needed vs stock 64.4%).

4. **ETF breadth effect is opposite** — High breadth (systemic selloff) is the WORST environment for ETFs (PF 0.18), but BEST for stocks (+6.09%). ETFs can't benefit from the strongest mean-reversion environments.

5. **Amount ranking is harmful for both** — But for stocks, the signal+exit is strong enough to overcome it. For ETFs, it isn't.

**Conclusion: ETF failure is primarily an ASSET-LEVEL problem** — weaker signal drift, worse exit capture, opposite breadth effect. No amount of ranking optimization (E4) or exit modification (E2) or breadth filtering (E3) can fully fix this because the underlying asset-level mean reversion is weaker and structurally different.

---

## N. Limitations

1. Trade log has 74 trades (2020-2024) vs G0's 76 — small sample for trade-level stats.
2. Stock panel uses 2,618 full-data stocks (50% of total) — survivorship-biased toward continuously-listed stocks.
3. No stock_basic/list_date/ST PIT/ADV60 filter — eligibility uses n_days>=20 proxy.
4. K=3 attribution uses levels_used as proxy, not detailed lot-level PnL.
5. Breadth/dispersion conditioning is descriptive, not causal.
6. All results on 2020-2024 common window — no out-of-sample validation.

---

## O. Output Files

- `results/stock/s1_raw_signal_expectancy.csv`
- `results/stock/s1_signal_decay.csv`
- `results/stock/s1_amount_vs_random.csv`
- `results/stock/s1_random_topn_summary.csv`
- `results/stock/s1_exit_capture.csv`
- `results/stock/s1_path_classification.csv`
- `results/stock/s1_profit_factor_decomposition.csv`
- `results/stock/s1_add_lot_attribution.csv`
- `results/stock/s1_breadth_analysis.csv`
- `results/stock/s1_dispersion_analysis.csv`
- `results/stock/s1_stock_vs_etf_mechanism_table.csv`
- `results/stock/s1_verdict.csv`
- `results/stock/s1_stock_trades_2020_2024.csv`
- `research/stock/PHASE_S1_REGISTRY.csv`
