# PHASE E4 — BB_Z RANKING HYPOTHESIS TEST 最终报告

> 生成日期: 2026-09-04 | Branch: etf-e0 | Commit: (pending)
> 前置: E1 NO REPLICATION, E1.1 MULTI-MECHANISM FAILURE, E2 H1 PARTIALLY SUPPORTED, E3 H2 PARTIALLY SUPPORTED
> E3 official commit: afa1076
> **RESEARCH STATUS: ADAPTIVE HISTORICAL HYPOTHESIS TEST — NOT A CLEAN OUT-OF-SAMPLE CONFIRMATION**

---

## A. FROZEN REFERENCES

| 阶段 | Commit | Verdict |
|------|--------|---------|
| E1 | 6789810 | NO REPLICATION |
| E1.1 | 1fa73e9 | MULTI-MECHANISM FAILURE |
| E2 | c8e8259 | H1 PARTIALLY SUPPORTED (Midline exit) |
| E3 | afa1076 | H2 PARTIALLY SUPPORTED (Low-Breadth entry) |

E3 最接近盈亏平衡配置: M2 + Midline + LowBreadth = -3.47% full, Sharpe +0.024, PF 0.937

---

## B. ADAPTIVE-RESEARCH DISCLOSURE

从 E4 开始，所有结论标注为 **ADAPTIVE HISTORICAL HYPOTHESIS TEST**。E1–E3 已反复观察同一历史区间并据此产生 H7。即使 E4 结果很好，也不得声称 independent out-of-sample proof。最终仍需 future blind test / genuinely untouched sample 确认。

---

## C. REGISTRY / SHA

Registry: `research/etf/PHASE_E4_REGISTRY.csv`
- Hypothesis: H7_BB_Z_RANKING
- Control: amount ranking (E3 original)
- Treatment: BB_Z ascending (most negative first)
- BB_Z = (close - MA20) / rolling_std(20), more negative = deeper oversold
- Tie-breaker: BB_Z → amount → lexicographic code (deterministic)
- All other parameters frozen from E3 (Midline exit, LowBreadth <10%, BB(20,2), etc.)
- Forbidden: signal threshold change, hybrid ranking, cluster filter, capital deployment fix, threshold mining

---

## D. CONTROL REPRODUCTION

| 指标 | E3 Frozen | E4 Control | Match |
|------|-----------|------------|-------|
| M1 Amount Total Return | -17.14% | -17.14% | ✓ (0.00pp) |
| M1 Amount Trades | 191 | 191 | ✓ |
| M1 Amount PF | 0.813 | 0.813 | ✓ |
| M2 Amount Total Return | -3.47% | -3.47% | ✓ (0.00pp) |
| M2 Amount Trades | 119 | 119 | ✓ |
| M2 Amount PF | 0.937 | 0.937 | ✓ |

**Control 完美复现 E3。** （修复了 E4 引擎初版中高宽度日跳过 ADD 的 bug。）

---

## E. EXACT BB_Z DEFINITION

```
BB_Z_t = (price_t - MA20_t) / rolling_std20_t
```
- Model 1: price = ETF close_adj, MA/std from ETF close_adj
- Model 2: price = Index close, MA/std from Index close
- rolling_std: ddof=0 (consistent with existing BB implementation, std = (bb_mid - bb_lower) / 2)
- Sorting: ascending (most negative = deepest oversold = highest priority)
- No future data: MA20 and std computed with rolling window ending at t

---

## F. BB_Z vs AMOUNT IC (Spearman Rank Correlation)

### M1 (ETF signal, n=1962 low-breadth candidates)

| Horizon | IC(amount) pooled | IC(BB_Z) pooled | IC(amount) daily mean | IC(BB_Z) daily mean | IC(BB_Z) hit rate |
|---------|-------------------|-----------------|----------------------|---------------------|-------------------|
| 1d | -0.026 | **-0.041** | +0.017 | -0.033 | 49.0% |
| 3d | -0.009 | -0.004 | +0.026 | +0.008 | 49.4% |
| 5d | -0.005 | -0.001 | -0.004 | +0.017 | 51.0% |
| 10d | -0.032 | -0.003 | -0.055 | -0.030 | 47.2% |
| 20d | +0.004 | +0.014 | -0.062 | +0.012 | 50.6% |

### M2 (Index signal, n=1416 low-breadth candidates)

| Horizon | IC(amount) pooled | IC(BB_Z) pooled | IC(amount) daily mean | IC(BB_Z) daily mean | IC(BB_Z) hit rate |
|---------|-------------------|-----------------|----------------------|---------------------|-------------------|
| 1d | +0.044 | +0.042 | -0.016 | -0.023 | 45.6% |
| 3d | +0.045 | +0.041 | -0.011 | -0.036 | 48.1% |
| 5d | +0.032 | +0.028 | -0.057 | -0.047 | 44.8% |
| 10d | +0.051 | +0.049 | +0.007 | +0.028 | 50.3% |
| 20d | +0.054 | +0.029 | +0.042 | **-0.055** | 42.5% |

**IC 结论**:
- M1 BB_Z IC 全部接近零或为负（pooled -0.04 到 +0.01，daily mean -0.06 到 +0.02）
- M2 BB_Z pooled IC 弱正（+0.03~+0.05），但 **daily mean IC 在 20d 为 -0.055，hit rate 仅 42.5%**——被少数大日驱动
- Amount IC 与 BB_Z IC 无显著差异——两者都缺乏稳定横截面预测力
- **BB_Z 没有比 amount 更高的 IC**

---

## G. BB_Z QUANTILE MONOTONICITY

### M1 (20d forward return)

| Quantile | Label | Count | Mean | Median | Win Rate |
|----------|-------|-------|------|--------|----------|
| Q1 | deepest oversold | 328 | **-0.224%** | -0.583% | 44.8% |
| Q2 | | 226 | +0.341% | -0.504% | 46.0% |
| Q3 | | 235 | +0.184% | -0.716% | 45.1% |
| Q4 | | 226 | +0.278% | -0.737% | 46.5% |
| Q5 | least oversold | 290 | **+0.389%** | -0.834% | 43.8% |

**M1: 最深超卖 (Q1) 的 20d 收益反而最差 (-0.224%)，最浅超卖 (Q5) 最好 (+0.389%)。与 H7 假设方向相反！**

### M2 (20d forward return)

| Quantile | Label | Count | Mean | Median | Win Rate |
|----------|-------|-------|------|--------|----------|
| Q1 | deepest oversold | 182 | **+1.324%** | +0.345% | 51.6% |
| Q2 | | 128 | +0.472% | +0.302% | 53.1% |
| Q3 | | 129 | +0.287% | -0.292% | 45.0% |
| Q4 | | 128 | +0.412% | +0.114% | 50.8% |
| Q5 | least oversold | 160 | +0.158% | -0.601% | 47.5% |

**M2: Q1 (最深) 确实最高 (+1.324%)，但非单调**（Q2<Q1, Q3<Q2, Q4>Q3）。且中位数差异很小。

---

## H. SELECTED vs NON-SELECTED

### M1 (20d)

| Ranking | Selected Mean | Non-selected Mean | Diff |
|---------|--------------|-------------------|------|
| Amount | -0.001% | +0.001% | -0.002% |
| BB_Z | -0.013% | +0.278% | **-0.291%** |

BB_Z selected Top-N 实际上比 non-selected 差 0.291%！

### M2 (20d)

| Ranking | Selected Mean | Non-selected Mean | Diff |
|---------|--------------|-------------------|------|
| Amount | +0.435% | +1.387% | -0.952% |
| BB_Z | +0.443% | +0.791% | -0.349% |

两种 ranking 的 selected 都不如 non-selected。Top-N 选择没有正向信息。

---

## I. M1 PORTFOLIO RESULTS (Full Window)

| 指标 | M1 Amount (Control) | M1 BB_Z (Treatment) | BB_Z vs Amount |
|------|---------------------|---------------------|----------------|
| Total Return | -17.14% | **-29.65%** | **-12.5pp (更差)** |
| CAGR | -0.92% | -1.72% | 更差 |
| Sharpe | -0.068 | -0.165 | 更差 |
| MaxDD | -32.22% | -40.76% | 更差 |
| Trades | 191 | 179 | -12 |
| Win Rate | 63.9% | 59.2% | -4.7pp |
| **Profit Factor** | **0.813** | **0.667** | **-18.0% (更差)** |
| Payoff Ratio | 0.460 | 0.460 | 相同 |
| Per-trade Expectancy | -897 | **-1,656** | 更差 |
| Avg Holding | 39.5d | 33.2d | -6.3d |
| Avg Exposure | 24.8% | 21.7% | -3.1pp |

### M1 Common Window (2020-2024)

| 指标 | M1 Amount | M1 BB_Z |
|------|-----------|---------|
| Total Return | -14.11% | **-28.09%** |
| Sharpe | -0.197 | -0.536 |
| MaxDD | -27.76% | -36.25% |

---

## J. M2 PORTFOLIO RESULTS (Full Window)

| 指标 | M2 Amount (Control) | M2 BB_Z (Treatment) | BB_Z vs Amount |
|------|---------------------|---------------------|----------------|
| Total Return | -3.47% | **-9.51%** | **-6.0pp (更差)** |
| CAGR | -0.17% | -0.49% | 更差 |
| Sharpe | +0.024 | -0.013 | 转正→转负 |
| MaxDD | -26.85% | -29.20% | 更差 |
| Trades | 119 | 148 | +29 |
| Win Rate | 68.1% | 63.5% | -4.6pp |
| **Profit Factor** | **0.937** | **0.872** | **-6.9% (更差)** |
| Payoff Ratio | 0.440 | 0.501 | +13.8% (略好) |
| Per-trade Expectancy | -291 | **-643** | 更差 |
| Avg Holding | 67.2d | 51.0d | -16.2d |
| Avg Exposure | 28.7% | 23.9% | -4.8pp |

### M2 Common Window (2020-2024)

| 指标 | M2 Amount | M2 BB_Z |
|------|-----------|---------|
| Total Return | -8.34% | **-12.76%** |
| Sharpe | -0.079 | -0.177 |
| MaxDD | -26.85% | -29.20% |

---

## K. ENTRY EXPECTANCY (Primary Outcome)

| Config | n | WR | PF | Payoff | BE_WR | Expectancy |
|--------|---|-----|-----|--------|-------|-----------|
| M1 Amount | 191 | 63.9% | 0.813 | 0.460 | 68.5% | -897 |
| M1 BB_Z | 179 | 59.2% | 0.667 | 0.460 | 68.5% | **-1,656** |
| M2 Amount | 119 | 68.1% | 0.937 | 0.440 | 69.5% | -291 |
| M2 BB_Z | 148 | 63.5% | 0.872 | 0.501 | 66.6% | **-643** |

**BB_Z 在两个模型中均降低了 PF 和 per-trade expectancy。没有任何配置达到 expectancy >= 0 或 PF >= 1。**

---

## L. COMMON WINDOW (Primary Comparison)

| Config | Total Return | Sharpe | MaxDD |
|--------|-------------|--------|-------|
| Stock A0 (ref) | +30.30% | 0.347 | -30.79% |
| M1 Amount | -14.11% | -0.197 | -27.76% |
| M1 BB_Z | -28.09% | -0.536 | -36.25% |
| M2 Amount | -8.34% | -0.079 | -26.85% |
| M2 BB_Z | -12.76% | -0.177 | -29.20% |

Common Window 中 BB_Z 在两个模型均更差。

---

## M. YEAR-BY-YEAR STABILITY (M2)

| Year | M2 Amount | M2 BB_Z |
|------|-----------|---------|
| 2015 | +7.0% | +9.1% |
| 2018 | -5.4% | -5.7% |
| 2019 | +4.4% | +3.5% |
| 2020 | +5.7% | +6.3% |
| 2021 | +2.8% | +0.5% |
| 2022 | -18.5% | -17.6% |
| 2023 | +3.1% | +4.8% |
| 2024 | 0.0% | -5.2% |
| 2025 | 0.0% | -5.3% |
| 2026 | 0.0% | +3.0% |

BB_Z 在 2015/2020/2023 略好，但在 2021/2024/2025 明显更差。不是单一年份驱动——BB_Z 在多年份均更差。

---

## N. EXPOSURE / TURNOVER

| Config | Avg Exp | Median Exp | Days <25% |
|--------|---------|-----------|-----------|
| M1 Amount | 24.8% | 19.9% | 72.1% |
| M1 BB_Z | 21.7% | 0.0% | 71.0% |
| M2 Amount | 28.7% | 18.7% | 71.2% |
| M2 BB_Z | 23.9% | 18.3% | 71.5% |

暴露率相近（21-29%），BB_Z 略低。**BB_Z 的更差表现不是由暴露率差异解释的**——在相似暴露下，BB_Z 的 per-trade 质量更差。

---

## O. LIQUIDITY SAFETY

BB_Z ranking 仅在已通过 ADV60≥2000万流动性过滤的候选中选择。Treatment 没有系统性掉入流动性尾部（ADV60 过滤在 ranking 之前应用）。

---

## P. CATEGORY / CLUSTER COMPOSITION

BB_Z ranking 选择的 ETF 与 Amount ranking 有重叠但不完全相同。M2 BB_Z 交易数更多（148 vs 119），因为 BB_Z 选择的 ETF 往往更快触及中轨退出（avg holding 51d vs 67d），释放资金后产生更多后续 entry。但这没有转化为更好的收益——更快的周转意味着更多交易成本和更差的 per-trade 质量。

---

## Q. EVIDENCE FOR H7

1. M2 BB_Z quantile Q1 (最深超卖) 20d mean return +1.324%，高于 Q5 +0.158%
2. M2 BB_Z payoff ratio 略好于 Amount (0.501 vs 0.440)
3. M2 BB_Z 在 2015/2020/2023 年份略好

---

## R. EVIDENCE AGAINST H7

1. **Portfolio: BB_Z 在两个模型均更差** — M1 -17%→-30%, M2 -3.5%→-9.5%
2. **PF 下降** — M1 0.813→0.667, M2 0.937→0.872
3. **Per-trade expectancy 更差** — M1 -897→-1656, M2 -291→-643
4. **M1 BB_Z IC 为负或接近零** — pooled -0.04~+0.01, daily mean -0.06~+0.02
5. **M1 最深超卖 Q1 收益反而最差** (-0.224% vs Q5 +0.389%) — 与假设方向相反
6. **BB_Z selected Top-N 不如 non-selected** (M1 diff -0.291%, M2 diff -0.349%)
7. **M2 BB_Z daily IC hit rate 仅 42.5%** (20d) — 不足 50%
8. **Win rate 下降** — M1 -4.7pp, M2 -4.6pp
9. **Common Window 均更差**
10. **多年份更差** — 不是单一年份驱动

---

## S. LIMITATIONS

1. **Adaptive historical test** — H7 由 E1-E3 观察产生，非独立样本
2. **Low-breadth filter 限制了候选池** — 仅分析 signal_ratio <10% 的候选
3. **M2 BB_Z 样本 148 笔** — 中等样本量
4. **未做 bootstrap significance** — 结果为描述性
5. **BB_Z 使用 (bb_mid - bb_lower)/2 反推 std** — 与直接 rolling std 可能有微小差异
6. **Exposure 仍低 (21-29%)** — 所有配置均受低暴露困扰

---

## T. FINAL VERDICT

### **H7 NOT SUPPORTED**

**BB_Z ranking does not contain more cross-sectional mean-reversion information than amount ranking.**

在纯横截面诊断中：
- M1 BB_Z IC 接近零或为负，最深超卖反而未来收益最差
- M2 BB_Z 有弱正 pooled IC 但 daily mean IC 为负，hit rate <50%
- 两种 ranking 的 selected Top-N 均不如 non-selected

在 portfolio 测试中：
- BB_Z 在 M1 和 M2 均显著更差（总收益 -6~-12pp，PF -7~-18%）
- Per-trade expectancy 更负
- 胜率下降
- 不是暴露率或单一年份驱动

**核心结论**: ETF/index 层面的 BB 超卖候选中，"超卖有多深"（BB_Z）并不比"成交额有多大"（amount）更有预测力。事实上，M1 中更深的超卖反而对应更差的未来收益。这表明 ETF/index 横截面缺乏可排名的 idiosyncratic mean-reversion information——高相关性使得所有 ETF 在超卖时同步运动，BB_Z 的横截面差异主要是噪声。

---

## U. RECOMMENDED NEXT PHASE

按 E4 规则，H7 Not Supported → 优先 **H4: Stock vs ETF cross-sectional dispersion mechanism audit**。

需要直接检验：股票 baseline 是否拥有更大的 BB_Z 横截面离散度，使 Top-N 排序真正有信息；而 ETF/index 高相关性消除了这种离散度。

| Priority | ID | Hypothesis | Rationale |
|----------|-----|-----------|-----------|
| **1** | **H4** | **Stock vs ETF cross-sectional dispersion** | E4 证明 ETF BB_Z 无信息；需对比股票层面是否有更大离散度使 ranking 有效 |
| 2 | H3 | Cluster-aware diversification | 若 H4 确认 ETF 横截面离散度不足，cluster cap 可能是唯一改善路径 |
| 3 | H5 | Time-stop / stop-loss | E2/E3 仍有 avg loser > avg winner；stop-loss 可能改善 payoff |
| 4 | H6 | Capital deployment | 所有配置暴露率仅 21-29%；但 PF<1 意味着更多部署=更多亏损 |

---

## 输出文件清单

| 文件 | 说明 |
|------|------|
| `e4_all_configs_summary.csv` | 4 配置完整指标 |
| `e4_m1_amount_summary.csv` / `e4_m1_bb_z_summary.csv` | M1 各配置 |
| `e4_m2_amount_summary.csv` / `e4_m2_bb_z_summary.csv` | M2 各配置 |
| `e4_common_window_comparison.csv` | Common window 对比 |
| `e4_full_window_comparison.csv` | Full window 对比 |
| `e4_ranking_ic_m1.csv` / `e4_ranking_ic_m2.csv` | Spearman IC |
| `e4_bbz_quantiles_m1.csv` / `e4_bbz_quantiles_m2.csv` | BB_Z 五分位单调性 |
| `e4_selected_vs_nonselected_m1.csv` / `..._m2.csv` | Selected vs non-selected |
| `e4_trade_log_m1_amount.csv` / `e4_trade_log_m1_bb_z.csv` | M1 交易日志 |
| `e4_trade_log_m2_amount.csv` / `e4_trade_log_m2_bb_z.csv` | M2 交易日志 |
| `e4_equity_*.csv` | 4 配置权益曲线 |
| `e4_final_report.md` | 本报告 |
| `PHASE_E4_REGISTRY.csv` | E4 预注册冻结 |
| `e4_bbz_ranking_test.py` | E4 回测引擎 |
