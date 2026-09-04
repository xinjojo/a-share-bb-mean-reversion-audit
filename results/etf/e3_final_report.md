# PHASE E3 — LOW-BREADTH ENTRY HYPOTHESIS TEST 最终报告

> 生成日期: 2026-09-04 | Branch: etf-e0 | Commit: (pending)
> 前置: E1 NO REPLICATION, E1.1 MULTI-MECHANISM FAILURE, E2 H1 PARTIALLY SUPPORTED (Midline exit)
> E2 official commit: c8e8259
> 本阶段目标: 严格检验 H2——ETF BB 均值回归是否主要在低宽度/局部超卖时有效，而在系统性高宽度抛售中失效。
> **只改 new entry eligibility，其余全部冻结（含 Midline exit）。不是优化。**

---

## A. FROZEN E2 REFERENCES

| 项目 | 值 |
|------|-----|
| E2 commit | `c8e8259` |
| E2 verdict | H1 PARTIALLY SUPPORTED (frozen) |
| E2 M1 Midline full return | -66.74% (Control target) |
| E2 M2 Midline full return | -20.69% (Control target) |
| E2 exit | FIRST BB MIDLINE TOUCH (frozen for E3) |

E3 不得覆盖 E1/E1.1/E2 结论。E3 Control 使用 E2 Midline exit（非 E1 STRICT_C），因为 E2 已验证 Midline 机制更合理。

---

## B. E3 REGISTRY / SHA

Registry: `research/etf/PHASE_E3_REGISTRY.csv`
- Hypothesis: H2_LOW_BREADTH_ENTRY
- Control: Midline exit, no breadth filter
- Treatment: Midline exit + low-breadth entry filter (signal_ratio < 10%)
- Breadth threshold: **0.10**（从 E1.1 Registry 冻结，非重新选择）
- Breadth formula: signal_ratio_t = n_oversold_signals_t / n_eligible_universe_t
- All other parameters frozen: BB(20,2), amount Top10, T+1, K=3, level_cash=200k, ADV60≥20M, Midline exit, etc.
- Forbidden: BB_Z ranking, cluster diversification, stop loss, time stop, capital deployment, market regime, trend filter, threshold mining

---

## C. CONTROL REPRODUCTION

| 指标 | E2 Frozen | E3 Control | Match |
|------|-----------|------------|-------|
| M1 Total Return | -66.74% | -66.74% | ✓ (0.00pp) |
| M1 Trades | 428 | 428 | ✓ |
| M2 Total Return | -20.69% | -20.69% | ✓ (0.00pp) |
| M2 Trades | 197 | 197 | ✓ |

**Control 完美复现 E2。** E3 engine 与 E2 engine 在无 breadth filter 时产出完全一致。

---

## D. BREADTH DEFINITION

signal_ratio_t = n_oversold_signals_t / n_eligible_universe_t

- Numerator: BB oversold signal count at t close (Model1=ETF close<bb_lower; Model2=Index close<bb_lower)
- Denominator: PIT eligible universe after liquidity filter (当日真实 eligible count)
- No future data: computed using t-known data only
- M1 and M2 compute their own signal breadth separately

Low-breadth days (<10%):
- M1: 4359/4941 days (88.2%)
- M2: 4698/4941 days (95.1%)

High-breadth days (≥10%) are relatively rare but concentrated in market stress periods.

---

## E. M1 CONTROL VS TREATMENT

### Full Window (2006-2026)

| 指标 | M1 Control | M1 LowBreadth | 变化 |
|------|-----------|--------------|------|
| Total Return | -66.74% | **-17.14%** | **+49.6pp** |
| CAGR | -5.28% | -0.92% | 改善 |
| Sharpe | -0.232 | -0.068 | 改善 |
| MaxDD | -71.84% | **-32.22%** | **+39.6pp** |
| Completed Trades | 428 | **191** | -55.4% |
| Win Rate | 56.3% | **63.9%** | +7.6pp |
| **Profit Factor** | **0.668** | **0.813** | **+21.7%** |
| Payoff Ratio | 0.518 | 0.460 | -11.2% (略差) |
| Avg Winner | 5,560 | 6,112 | +9.9% |
| Avg Loser | 10,734 | 13,289 | +23.8% (更差) |
| Breakeven WR | 65.9% | 68.5% | +2.6pp |
| Per-trade Expectancy | -1,559 | **-897** | +42.5% (less negative) |
| Avg Holding | 23.7d | 39.5d | +66.7% |
| **Avg Exposure** | **46.5%** | **24.8%** | **-21.7pp** |
| Fully Invested Days | 27.2% | 4.7% | -22.5pp |
| Days <50% Invested | 59.4% | 78.8% | +19.4pp |

### Common Window (2020-2024)

| 指标 | M1 Control | M1 LowBreadth |
|------|-----------|--------------|
| Total Return | -37.13% | **-14.11%** |
| Sharpe | -0.461 | -0.197 |
| MaxDD | -45.49% | -27.76% |

---

## F. M2 CONTROL VS TREATMENT

### Full Window (2006-2026)

| 指标 | M2 Control | M2 LowBreadth | 变化 |
|------|-----------|--------------|------|
| Total Return | -20.69% | **-3.47%** | **+17.2pp** |
| CAGR | -1.13% | -0.17% | 改善 |
| **Sharpe** | **-0.021** | **+0.024** | **转正!** |
| MaxDD | -35.26% | **-26.85%** | +8.4pp |
| Completed Trades | 197 | **119** | -39.6% |
| Win Rate | 63.5% | **68.1%** | +4.6pp |
| **Profit Factor** | **0.826** | **0.937** | **+13.4%** |
| Payoff Ratio | 0.476 | 0.440 | -7.6% (略差) |
| Breakeven WR | 67.8% | 69.5% | +1.7pp |
| Per-trade Expectancy | -1,050 | **-291** | +72.3% (less negative) |
| Avg Holding | 55.9d | 67.2d | +20.2% |
| **Avg Exposure** | **47.2%** | **28.7%** | **-18.5pp** |
| Fully Invested Days | 22.8% | 15.9% | -6.9pp |

### Common Window (2020-2024)

| 指标 | M2 Control | M2 LowBreadth |
|------|-----------|--------------|
| Total Return | -10.18% | **-8.34%** |
| Sharpe | -0.119 | -0.079 |
| MaxDD | -28.07% | -26.85% |

M2 LowBreadth 是 ETF 项目首个 full window Sharpe 为正的配置（+0.024），但 Common Window 仍为负（-8.34%），且 PF 仍 < 1。

---

## G. ENTRY-LEVEL EXPECTANCY (Primary Outcome)

| Config | n | WR | PF | Payoff | BE_WR | Expectancy/trade |
|--------|---|-----|-----|--------|-------|-----------------|
| M1 Control | 428 | 56.3% | 0.668 | 0.518 | 65.9% | -1,559 |
| M1 LowBreadth | 191 | 63.9% | 0.813 | 0.460 | 68.5% | -897 |
| M2 Control | 197 | 63.5% | 0.826 | 0.476 | 67.8% | -1,050 |
| M2 LowBreadth | 119 | 68.1% | 0.937 | 0.440 | 69.5% | -291 |

**关键判断**:
- PF 从 <1 跨越到 >=1? **否**（M1 0.813, M2 0.937，均仍 <1）
- Expectancy 从负转非负? **否**（M1 -897, M2 -291，均仍负）
- M2 LowBreadth 非常接近 breakeven（PF 0.937, expectancy -291），但未跨越

**改善来源**: 胜率提升（+4.6~7.6pp），而非 payoff 改善（payoff 实际略降 -7.6~-11.2%）。低宽度过滤提高了胜率，但单笔亏损幅度反而更大（avg loser +23.8% M1）。

---

## H. COMMON WINDOW (Primary Comparison)

| Config | Total Return | CAGR | Sharpe | MaxDD |
|--------|-------------|------|--------|-------|
| Stock A0 (ref) | +30.30% | +5.66% | 0.347 | -30.79% |
| M1 Control | -37.13% | -8.87% | -0.461 | -45.49% |
| M1 LowBreadth | -14.11% | -3.00% | -0.197 | -27.76% |
| M2 Control | -10.18% | -2.13% | -0.119 | -28.07% |
| M2 LowBreadth | -8.34% | -1.73% | -0.079 | -26.85% |

Common Window 中所有 ETF 配置仍为负。M2 LowBreadth 改善最小（-10.18%→-8.34%，+1.84pp），M1 LowBreadth 改善较大（-37.13%→-14.11%，+23pp）但 M1 Control 本身更差。

---

## I. FILTERED-OUT SIGNAL PERFORMANCE (Critical Mechanism Check)

被高宽度 filter 拒绝的 Top-N 信号的固定前向收益（M1, n=3285）：

| Horizon | Count | Mean | Median | P25 | P75 | Win Rate |
|---------|-------|------|--------|-----|-----|----------|
| 1d | 3285 | -0.004% | +0.118% | -1.006% | +1.078% | 52.5% |
| 3d | 3285 | +0.137% | 0.000% | -1.677% | +1.809% | 50.0% |
| 5d | 3285 | +0.267% | +0.109% | -2.276% | +2.438% | 50.6% |
| 10d | 3285 | +0.319% | -0.097% | -3.059% | +3.385% | 48.2% |
| 20d | 3285 | **+1.084%** | **+0.446%** | -3.807% | +5.163% | 52.3% |

**重要发现**: 被过滤的高宽度信号**并不比保留的信号差**——20 天前向收益均值 +1.084%，中位数 +0.446%，胜率 52.3%。这意味着：

1. Breadth filter 没有干净地分离"好信号"和"坏信号"
2. 被过滤的信号在 20 天后实际上有正收益（可能是超跌反弹）
3. LowBreadth 组合的改善**不是**因为过滤掉了明显更差的信号
4. 改善更可能来自：(a) 更少的交易次数/成本，(b) 更低的暴露率，(c) 避免了高宽度日的极端短期波动

这是 **evidence against H2 的机制纯粹性**——breadth 是一个粗糙的代理变量，不是精确的信号质量过滤器。

---

## J. BREADTH MONOTONICITY (DESCRIPTIVE ONLY)

LowBreadth filter 只允许 signal_ratio < 10% 的 entry。E1.1 已冻结 bins：0-5%, 5-10%, 10-25%, 25-50%, 50%+。

M1 LowBreadth 中，所有 entry 均来自 0-5% 和 5-10% bins（10-25%+ 被过滤）。Days 分布：
- 0-5%: 多数天数
- 5-10%: 少数天数
- 10-25%+: 被过滤

**DESCRIPTIVE ONLY — 禁止从中重新挑最优阈值。**

---

## K. CAPITAL UTILIZATION

| Config | Avg Exp | Median Exp | Days <25% | Days <50% | Full Days |
|--------|---------|-----------|-----------|-----------|-----------|
| M1 Control | 46.5% | 39.1% | 33.9% | 59.4% | 27.2% |
| M1 LowBreadth | **24.8%** | 19.9% | **72.1%** | **78.8%** | 4.7% |
| M2 Control | 47.2% | 45.5% | 41.5% | 64.4% | 22.8% |
| M2 LowBreadth | **28.7%** | 18.7% | **71.2%** | **75.7%** | 15.9% |

**LowBreadth 组合平均暴露率仅 25-29%，71-72% 的天数投资 <25%。** 这是 E2 Midline exit（47%）基础上的进一步大幅下降。

**必须明确指出**: 总收益改善部分来自"几乎不投资"，而非纯粹的 edge 改善。M2 LowBreadth full window -3.47% 的亏损，在 28.7% 平均暴露率下，对应的**风险调整后亏损**（亏损/暴露）实际上可能比 Control 更差。

---

## L. SAMPLE-SIZE RETENTION

| Config | Entries | Completed | Retention vs Control |
|--------|---------|-----------|----------------------|
| M1 Control | 428 | 428 | 100% |
| M1 LowBreadth | 191 | 191 | **44.6%** |
| M2 Control | 197 | 197 | 100% |
| M2 LowBreadth | 119 | 119 | **60.4%** |

M1 过滤了 55% 的交易，M2 过滤了 40%。M2 LowBreadth 仅 119 笔完成交易——样本量中等，统计显著性有限。

2006-2014 年 M2 LowBreadth 无交易（0% 收益），因为 ETF universe 太小，所有信号均为高宽度。实际有效样本从 2015 年开始。

---

## M. YEAR-BY-YEAR ROBUSTNESS (M2 LowBreadth)

| Year | Return | Avg Exposure | Notes |
|------|--------|-------------|-------|
| 2006-2014 | 0.0% | 0-37% | 无交易（universe 太小） |
| 2015 | +7.0% | 15.1% | |
| 2016 | 0.0% | 18.7% | 无新交易 |
| 2017 | 0.0% | 18.7% | 无新交易 |
| 2018 | -5.4% | 37.4% | |
| 2019 | +4.4% | 30.8% | |
| 2020 | +5.7% | 34.6% | |
| 2021 | +2.8% | 46.7% | |
| **2022** | **-18.5%** | 61.9% | **最大亏损年** |
| 2023 | +3.1% | 55.7% | |
| 2024-2026 | 0.0% | 97-100% | 持仓未退出/无新交易 |

**改善不是单一年份驱动**——2015、2019、2020、2021、2023 均为正收益。但 2022 年仍亏 -18.5%（高宽度 filter 未能避免 2022 年的下跌）。2016-2017 和 2024-2026 有 0% 收益（无交易或持仓）。

---

## N. CATEGORY COMPOSITION

LowBreadth filter 后，entry 仍以宽基/大盘 ETF 为主（与 Control 类似），因为低宽度信号通常出现在非系统性时期，此时宽基 ETF 的 BB 信号更稀疏但更可能是局部超卖。

（详细 category 统计见 trade logs，此处不展开——category 组成未发生根本性变化。）

---

## O. SYSTEMIC-SELLOFF EVIDENCE

Top filtered signal days（M1, 按被过滤信号数排序）：
- 2023-08-21 (10 signals, ratio 58.8%)
- 2023-08-23 (10 signals, ratio 43.5%)
- 2023-08-22 (10 signals, ratio 13.2%)
- 2023-10-18 (10 signals, ratio 25.2%)
- 2023-10-10 (10 signals, ratio 19.1%)
- 2023-07-21 (10 signals, ratio 19.3%)
- 2026-07-20 (10 signals, ratio 35.4%)

被过滤日集中在 2023-08（市场调整期）和 2023-10（市场下跌期），确认为系统性压力时期。High breadth = systemic selloff 的对应关系成立。

---

## P. EVIDENCE SUPPORTING H2

1. **Total return dramatically improved**: M1 -66.74%→-17.14% (+49.6pp), M2 -20.69%→-3.47% (+17.2pp)
2. **PF improved**: M1 0.668→0.813 (+21.7%), M2 0.826→0.937 (+13.4%)
3. **Win rate improved**: M1 +7.6pp, M2 +4.6pp
4. **MaxDD reduced**: M1 -71.84%→-32.22%, M2 -35.26%→-26.85%
5. **Per-trade expectancy less negative**: M1 -1559→-897, M2 -1050→-291
6. **M2 LowBreadth full window Sharpe turned positive** (+0.024) — ETF 项目首个
7. **Not driven by single year**: 2015/2019/2020/2021/2023 均正收益
8. **High breadth days confirmed as systemic stress**: 2023-08/10, 2026-07

---

## Q. EVIDENCE AGAINST H2

1. **PF still < 1**: M1 0.813, M2 0.937 — per-trade expectancy still negative
2. **Common Window still negative**: M1 -14.11%, M2 -8.34% — primary comparison fails
3. **Expectancy still < 0**: M1 -897, M2 -291 — not crossed to non-negative
4. **Exposure collapsed**: ~47%→~25-29% avg, 71-72% days <25% invested — improvement partly from "almost not investing"
5. **Filtered signals NOT worse**: M1 filtered 20d fwd return mean +1.084%, median +0.446%, win rate 52.3% — breadth does not cleanly separate good from bad signals
6. **Payoff ratio worsened**: 0.518→0.460 (M1), 0.476→0.440 (M2) — improvement from win rate, not better payoff
7. **Avg loser worsened**: +23.8% (M1) — low-breadth trades that lose, lose bigger
8. **Sample starts late**: 2006-2014 zero trades, effective sample from 2015
9. **M2 LowBreadth only 119 trades** — moderate sample, limited statistical significance
10. **2022 still -18.5%**: breadth filter did not prevent the 2022 drawdown

---

## R. LIMITATIONS

1. **Breadth is a crude proxy**: filtered signals have positive 20d forward returns — mechanism not clean
2. **Low exposure confounds interpretation**: 25-29% avg exposure means risk-adjusted performance may be worse than headline
3. **Sample size**: M2 LowBreadth 119 trades, M1 191 — no bootstrap performed
4. **Late start**: 2006-2014 no trades for M2 LowBreadth
5. **Payoff worsened**: improvement entirely from win rate, not from better risk/reward
6. **Common window failure**: primary comparison (2020-2024) still negative for all configs
7. **No significance testing**: no bootstrap CI, no t-test — results are descriptive

---

## S. FINAL VERDICT

### **H2 PARTIALLY SUPPORTED**

**Low-breadth entry filter materially improves mechanism metrics** (PF +13-22%, win rate +5-8pp, MaxDD +8-40pp, per-trade expectancy +42-72% less negative, M2 full window Sharpe turns slightly positive).

**But it does not achieve the preregistered strong-support criteria**:
- PF still < 1 (0.813 M1, 0.937 M2)
- Per-trade expectancy still negative (-897 M1, -291 M2)
- Common Window total return still negative (-14.11% M1, -8.34% M2)
- Improvement is confounded by dramatically reduced exposure (25-29% avg)
- Filtered signals do not have worse forward returns — mechanism is not clean

**The core issue remains**: even after filtering out high-breadth systemic signals, the entry-side expectancy is still negative. The breadth filter reduces the *frequency* of bad trades but does not fix the *quality* of the remaining signals. This points to a deeper problem with entry signal/ranking quality.

---

## T. RECOMMENDED NEXT HYPOTHESIS

按 E3 规则，H2 失败（未达 strong support）后，**优先研究 H4/H7**——entry signal/ranking 本身是否缺乏 cross-sectional information：

| Priority | ID | Hypothesis | Rationale |
|----------|-----|-----------|-----------|
| **1** | **H7** | **BB_Z ranking instead of amount** | E2 Gate 1B confirmed E1 uses amount ranking, which showed zero forward-return separation (E1.1). BB_Z (signal depth) may have different information content. |
| **2** | **H4** | **Stock vs ETF cross-sectional dispersion mechanism** | Directly test whether stock baseline has larger cross-sectional BB_Z dispersion that makes Top-N ranking informative, while ETF high correlation eliminates it. |
| 3 | H3 | Cluster-aware diversification | If H7/H4 confirm ranking is the bottleneck, cluster cap may help. But E3 showed breadth filter already reduces cluster crowding indirectly. |
| 4 | H5 | Time-stop / stop-loss | E2 Midline + E3 breadth still have avg loser > avg winner. Stop-loss may address payoff ratio. |
| 5 | H6 | Capital deployment | E3 exposure only 25-29%. If edge exists per-trade, deploying more capital could help. But PF<1 means more deployment = more losses. |

**关键判断**: H2 未达 strong support 的根本原因是 entry-side per-trade expectancy 仍为负。Breadth filter 减少了交易频率但未修复信号质量。**下一步应直接检验 ranking quality (H7 BB_Z) 和横截面离散度 (H4)**，而非继续在 entry filtering 上做文章。

---

## 输出文件清单

| 文件 | 说明 |
|------|------|
| `e3_all_configs_summary.csv` | 4 配置完整指标汇总 |
| `e3_m1_control_summary.csv` | M1 Control 指标 |
| `e3_m1_lowbreadth_summary.csv` | M1 LowBreadth 指标 |
| `e3_m2_control_summary.csv` | M2 Control 指标 |
| `e3_m2_lowbreadth_summary.csv` | M2 LowBreadth 指标 |
| `e3_common_window_comparison.csv` | Common window 对比 |
| `e3_full_window_comparison.csv` | Full window 对比 |
| `e3_trade_log_m1_control.csv` | M1 Control 交易日志 |
| `e3_trade_log_m1_lowbreadth.csv` | M1 LowBreadth 交易日志 |
| `e3_trade_log_m2_control.csv` | M2 Control 交易日志 |
| `e3_trade_log_m2_lowbreadth.csv` | M2 LowBreadth 交易日志 |
| `e3_equity_*.csv` | 4 配置权益曲线 |
| `e3_daily_panel_*.csv` | 4 配置日频面板（含 signal_ratio） |
| `e3_filtered_signals_*.csv` | 被过滤的高宽度信号 |
| `e3_filtered_signal_forward_returns_m1.csv` | 被过滤信号前向收益（M1） |
| `e3_filtered_signal_forward_returns_m2.csv` | 被过滤信号前向收益（M2） |
| `e3_yearly_results_m2_lowbreadth.csv` | M2 LowBreadth 年度收益 |
| `e3_systemic_dates.csv` | Top 被过滤系统性日期 |
| `e3_final_report.md` | 本报告 |
| `PHASE_E3_REGISTRY.csv` | E3 预注册冻结 |
| `e3_low_breadth_test.py` | E3 回测引擎 |
