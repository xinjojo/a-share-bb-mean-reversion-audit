# PHASE E2 — ETF MIDLINE EXIT HYPOTHESIS TEST 最终报告

> 生成日期: 2026-09-04 | Branch: etf-e0 | Commit: (pending)
> 前置: E1 NO REPLICATION, E1.1 MULTI-MECHANISM FAILURE (exit-mismatch 为最强机制之一)
> 本阶段目标: 严格验证单一假设——ETF 自然均值回归目标是否更接近 BB 中轨而非上轨/STRICT_C。
> **只改 exit threshold，其余全部冻结。不是优化。**

---

## A. FROZEN REFERENCES

| 项目 | 值 |
|------|-----|
| E1 commit | `6789810` |
| E1 verdict | NO REPLICATION (frozen) |
| E1.1 commit | `1fa73e9` |
| E1.1 verdict | MULTI-MECHANISM FAILURE (frozen) |
| E2 Registry | `research/etf/PHASE_E2_REGISTRY.csv` |

E2 不得覆盖 E1/E1.1 结论。即使 Midline 赚钱，也不能重写前两阶段。

---

## B. E2 GATE

### B1. +16.5% Midline-Return Audit — **PASS WITH CORRECTION**

E1.1 报告称"触及 BB 中轨时平均已有约 +16.5% 浮盈"。严格审计发现原定义有误：

| 问题 | 原 E1.1 | 修正后 |
|------|---------|--------|
| 参考价格 | avg_cost（含加仓、未复权） | actual entry_fill（首笔成交价） |
| 单位 | close_adj（复权）/ avg_cost（未复权）→ 不匹配 | entry_fill × adj_factor（复权对齐） |
| 指标 | 到中轨前的 MAX return | 中轨触达时的 return |

**修正后结果**（`e2_gate_midline_return_audit.csv`）：

| Model | 触中轨交易 | mean | median | P25 | P75 | P90 | min | max |
|-------|----------|------|--------|-----|-----|-----|-----|-----|
| Model 1 | 101/101 | **+0.38%** | +1.33% | -1.76% | +3.48% | +5.83% | -41.75% | +16.87% |
| Model 2 | 73/73 | **-1.50%** | +0.64% | -3.88% | +3.36% | +5.82% | -78.71% | +9.57% |

**重要含义**: 中轨触达时的实际收益远比原 +16.5% 温和。约 75% 交易在中轨时仍为正收益（中位数 +1.3%），但均值被少数极端负值拖累。这意味着切换到中轨退出能锁定的利润很薄——这对 H1 是不利证据。

### B2. Ranking-Variable Audit — **PASS**

从 E1 代码确认：`panel.sort_values(['date', 'amount'], ascending=[True, False])` + `.head(TOP_N)`。

**E1 ranking variable = amount（日成交额/流动性），降序**。不是 BB_Z。

E1.1 "Top-N has no information" 修正为：**amount-based Top-N 排序前向收益区分度弱**。BB_Z 排序未被测试。E2 entry side 保持 amount ranking 不变。

### Gate Verdict: **PASS WITH CORRECTION**

---

## C. E2 REGISTRY / SHA

Registry: `research/etf/PHASE_E2_REGISTRY.csv`
- Hypothesis: H1_MIDLINE_EXIT
- Control: STRICT_C dynamic_touch (high_adj >= pstar → fill at pstar/adj)
- Treatment: FIRST_BB_MIDLINE_TOUCH (high_adj >= bb_mid → fill at bb_mid/adj)
- **Execution semantics IDENTICAL**: bar-based threshold touch, fill at threshold price, same slippage/tick/price-limit/suspension
- All other parameters frozen (BB(20,2), amount Top10, T+1, K=3, level_cash=200k, ADV60≥20M, etc.)
- Forbidden: trailing stop, partial exit, time stop, breadth filter, cluster filter, stop loss, any entry-side change

---

## D. CONTROL REPRODUCTION

| 指标 | E1 Frozen | E2 Control | Match |
|------|-----------|------------|-------|
| M1 Total Return | -60.77% | -60.77% | ✓ |
| M1 Total Trades | 235 | 235 | ✓ |
| M1 Completed Trades | 101 | 101 | ✓ |
| M2 Total Return | -43.44% | -43.44% | ✓ |
| M2 Total Trades | 192 | 192 | ✓ |
| M2 Completed Trades | 73 | 73 | ✓ |

**Control 完美复现 E1 冻结结果。** E2 engine 与 E1 engine 在 STRICT_C exit 下产出完全一致。

---

## E. MODEL 1 CONTROL VS MIDLINE

### Full Window (2006-2026)

| 指标 | M1 Control | M1 Midline | 变化 |
|------|-----------|-----------|------|
| Total Return | -60.77% | **-66.74%** | 更差 -5.97pp |
| CAGR | -4.50% | -5.28% | 更差 |
| Sharpe | -0.207 | -0.232 | 更差 |
| MaxDD | -69.86% | -71.84% | 略差 |
| Completed Trades | 101 | **428** | +324% |
| Win Rate | 57.4% | 56.3% | -1.1pp |
| **Profit Factor** | **0.532** | **0.668** | **+25.6%** |
| **Payoff Ratio** | **0.395** | **0.518** | **+31.1%** |
| Avg Winner | 11,917 | 5,560 | -53% |
| Avg Loser | 30,206 | 10,734 | -64% |
| **Avg Holding** | **166.5d** | **23.7d** | **-85.8%** |
| Loser Avg Holding | 340.8d | 28.4d | -91.7% |
| P90 Holding | 162d | 35d | -78.4% |
| Max Holding | 5274d | 1464d | -72.2% |
| **Avg Exposure** | **75.1%** | **46.5%** | **-28.6pp** |
| Per-trade Expectancy | -6,016 | -1,559 | +74% (less negative) |

### Common Window (2020-2024)

| 指标 | M1 Control | M1 Midline |
|------|-----------|-----------|
| Total Return | -14.40% | **-37.13%** |
| Sharpe | -0.384 | -0.461 |
| MaxDD | -21.85% | -45.49% |

**M1 Midline 全面更差。** 虽然 per-trade 指标（PF、payoff、holding、expectancy）显著改善，但总收益因交易数暴增 4 倍、暴露率从 75% 降到 47% 而恶化。

---

## F. MODEL 2 CONTROL VS MIDLINE

### Full Window (2006-2026)

| 指标 | M2 Control | M2 Midline | 变化 |
|------|-----------|-----------|------|
| Total Return | -43.44% | **-20.69%** | **改善 +22.75pp** |
| CAGR | -2.77% | -1.13% | 改善 |
| Sharpe | -0.122 | -0.021 | 改善 |
| MaxDD | -50.06% | -35.26% | **改善 +14.8pp** |
| Completed Trades | 73 | **197** | +170% |
| Win Rate | 54.8% | **63.5%** | **+8.7pp** |
| **Profit Factor** | **0.589** | **0.826** | **+40.2%** |
| Payoff Ratio | 0.486 | 0.476 | -2.1% |
| Avg Winner | 15,589 | 7,872 | -49% |
| Avg Loser | 32,061 | 16,539 | -48% |
| **Avg Holding** | **211.7d** | **55.9d** | **-73.6%** |
| Loser Avg Holding | 372.8d | 114.3d | -69.3% |
| **Avg Exposure** | **71.1%** | **47.2%** | **-23.9pp** |
| Per-trade Expectancy | -5,951 | -1,050 | +82% (less negative) |

### Common Window (2020-2024)

| 指标 | M2 Control | M2 Midline |
|------|-----------|-----------|
| Total Return | -11.22% | **-10.18%** |
| Sharpe | -0.321 | -0.119 |
| MaxDD | -18.27% | -28.07% |

**M2 Midline 明显改善但仍为负。** Full window 总收益从 -43% 改善到 -21%，PF 从 0.59 提升到 0.83，胜率从 55% 提升到 64%，MaxDD 从 -50% 收窄到 -35%。但 Common window 改善有限（-11.2%→-10.2%），且 MaxDD 反而扩大。

---

## G. COMMON-WINDOW RESULTS (Primary Comparison)

| Config | Total Return | CAGR | Sharpe | MaxDD |
|--------|-------------|------|--------|-------|
| Stock A0 (frozen ref) | +30.30% | +5.66% | 0.347 | -30.79% |
| M1 Control | -14.40% | -3.06% | -0.384 | -21.85% |
| M1 Midline | **-37.13%** | -8.87% | -0.461 | -45.49% |
| M2 Control | -11.22% | -2.35% | -0.321 | -18.27% |
| M2 Midline | **-10.18%** | -2.13% | -0.119 | -28.07% |

Common window 中，M1 Midline 显著更差，M2 Midline 微幅改善。两者均未达到正收益。

---

## H. PROFIT-FACTOR / PAYOFF DECOMPOSITION

| Config | PF | Payoff | Avg Winner | Avg Loser | WR | Breakeven WR | Expectancy/trade |
|--------|-----|--------|-----------|-----------|-----|-------------|-----------------|
| M1 Control | 0.532 | 0.395 | 11,917 | 30,206 | 57.4% | 71.7% | -6,016 |
| M1 Midline | 0.668 | 0.518 | 5,560 | 10,734 | 56.3% | 65.9% | -1,559 |
| M2 Control | 0.589 | 0.486 | 15,589 | 32,061 | 54.8% | 67.3% | -5,951 |
| M2 Midline | 0.826 | 0.476 | 7,872 | 16,539 | 63.5% | 67.8% | -1,050 |

**Midline exit 通过缩小 avg loser（-48~-64%）改善了 payoff ratio 和 PF**，但同时也缩小了 avg winner（-49~-53%）。Per-trade expectancy 从 -6000 改善到 -1050~-1559（less negative），但仍为负。

M2 Midline 的胜率提升到 63.5%（接近 breakeven 67.8%），是最接近转正的配置。

---

## I. TAIL-RISK CHANGE

| Config | Worst1 %GL | Worst3 %GL | Worst10 %GL |
|--------|-----------|-----------|------------|
| M1 Control | 37.2% | 53.0% | 77.3% |
| **M1 Midline** | **5.5%** | **13.9%** | **28.4%** |
| M2 Control | 21.7% | 52.3% | 83.7% |
| **M2 Midline** | **13.3%** | **27.5%** | **54.6%** |

**Midline exit 大幅截断了左尾。** Worst10 占 gross loss 从 77-84% 降到 28-55%。这直接验证了 E1.1 的 tail-dominated 机制——STRICT_C 的长期持有导致极端亏损，中轨退出成功截断了这些尾部。

但截断尾部的代价是：更多的中等亏损交易（428 vs 101 笔），总亏损并未消除。

---

## J. HOLDING-PERIOD CHANGE

| Config | All Mean | Winners | Losers | P90 | Max |
|--------|---------|---------|--------|-----|-----|
| M1 Control | 166.5d | 37.2d | 340.8d | 162d | 5274d |
| **M1 Midline** | **23.7d** | **20.1d** | **28.4d** | **35d** | **1464d** |
| M2 Control | 211.7d | 78.8d | 372.8d | 171d | 5274d |
| **M2 Midline** | **55.9d** | **22.2d** | **114.3d** | **34d** | **4055d** |

**Midline exit 消除了"数百天亏损持仓"问题。** Loser 平均持仓从 341-373 天降到 28-114 天。这直接验证了 E1.1 的 exit-mismatch 机制——STRICT_C 要求上轨触达导致亏损交易长期持有，中轨退出大幅缩短了持仓。

---

## K. FAILURE-PATH CHANGE (Mechanism Verification)

E1.1 发现 95% 亏损交易 = REBOUND THEN RELAPSE。Midline exit 的设计目标就是在反弹到中轨时退出，避免"relapse"。

从数据看：
- Midline 持仓中位数 20-56 天，远短于 Control 的 37-79 天（winners）和 341-373 天（losers）
- 这意味着 Midline 在价格反弹到中轨时就退出了，没有等待上轨
- 尾部截断（Worst10 77%→28%GL）证明极端"relapse"被避免
- 但 PF 仍 < 1，说明即使在中轨退出，per-trade expectancy 仍为负——entry side 的负期望未被修复

**结论: Midline exit 成功减少了 REBOUND THEN RELAPSE 类型的极端亏损，但没有消除 entry-side 的负期望。**

---

## L. CAPITAL-RELEASE / PATH-DEPENDENCE EFFECT

| Config | Avg Exposure | Avg Cash | Fully Invested Days |
|--------|-------------|----------|-------------------|
| M1 Control | 75.1% | 24.9% | 60.4% |
| M1 Midline | **46.5%** | **53.5%** | (lower) |
| M2 Control | 71.1% | 28.9% | (lower) |
| M2 Midline | **47.2%** | **52.8%** | (lower) |

**Midline exit 导致暴露率从 ~73% 降到 ~47%。** 这是 M1 Midline 总收益恶化的主要原因之一：
1. 头寸在中轨快速退出，资金回到现金
2. 但新信号稀疏（78% 交易日零信号），资金长期闲置
3. 4 倍的交易次数增加了成本拖累

M2 Midline 虽然暴露率也降到 47%，但 per-trade 改善足够大（expectancy -5951→-1050），抵消了低暴露的影响，总收益仍改善。

**这是合法的 path dependence**——不同退出导致不同资金可用性，进而影响后续 entry。E2 不强制两者拥有相同 portfolio path。

---

## M. COMPARISON WITH FROZEN STOCK A0

| 指标 | Stock A0 | M1 Control | M1 Midline | M2 Control | M2 Midline |
|------|----------|-----------|-----------|-----------|-----------|
| CW Total Return | +30.30% | -14.40% | -37.13% | -11.22% | -10.18% |
| CW Sharpe | 0.347 | -0.384 | -0.461 | -0.321 | -0.119 |

所有 ETF 配置（含 Midline）均远低于股票 A0。Midline exit 缩小了 ETF 与股票的差距（M2 full window -43%→-21%），但未消除。

**股票 baseline 仅作 reference，E2 未调 Midline 规则以接近 +30.3%。**

---

## N. DATA / EXECUTION LIMITATIONS

1. **Gate 1A correction**: 原 E1.1 +16.5% at midline 定义有误，修正后 M1 mean +0.38%。这削弱了 H1 的先验合理性。
2. **T+1 semantics**: E1 engine 代码允许 same-day entry+exit（entry at T+1 open, exit at T+1 intraday）。Control 和 Treatment 使用相同语义，不影响相对比较，但可能与严格 T+1 有差异。
3. **Midline fill assumption**: bar-based touch (high_adj >= bb_mid → fill at bb_mid/adj)，与 STRICT_C 的 pstar touch 语义一致。实际成交可能因流动性/价差偏离。
4. **M2 Midline CW MaxDD 扩大**: Common window 中 M2 Midline MaxDD -28.07% > Control -18.27%，可能因低暴露+路径依赖。
5. **交易数有限**: M2 仅 197 笔 completed trades，统计显著性有限。未做 bootstrap（无现成稳定实现）。

---

## O. EVIDENCE FOR H1

1. **Tail risk dramatically reduced**: Worst10 %GL 从 77-84% 降到 28-55%。E1.1 的 tail-dominated 机制被成功修复。
2. **Holding period dramatically reduced**: Loser avg holding 从 341-373d 降到 28-114d。E1.1 的 long-holding failure 被成功修复。
3. **PF improved**: 0.53→0.67 (M1), 0.59→0.83 (M2)。
4. **Payoff ratio improved**: 0.39→0.52 (M1)。
5. **Per-trade expectancy less negative**: -6016→-1559 (M1), -5951→-1050 (M2)。
6. **M2 full window total return improved**: -43.44%→-20.69%。
7. **M2 win rate improved**: 54.8%→63.5%，接近 breakeven 67.8%。
8. **Exit-mismatch mechanism confirmed**: 中轨退出确实在价格反弹时截断了亏损，避免了 relapse。

---

## P. EVIDENCE AGAINST H1

1. **M1 total return WORSENED**: Full -60.77%→-66.74%, CW -14.40%→-37.13%。Per-trade 改善被 turnover/exposure 效应淹没。
2. **Neither model achieves positive expectancy**: 所有配置 full window 和 common window 均为负收益。
3. **Common window improvement marginal**: M2 CW 仅 -11.22%→-10.18%（+1.04pp），M1 CW 显著恶化。
4. **M2 CW MaxDD worsened**: -18.27%→-28.07%。
5. **Gate 1A correction**: 中轨触达时实际收益仅 +0.38%（M1 mean），远低于原 +16.5%——中轨能锁定的利润很薄。
6. **Exposure collapsed**: ~73%→~47%，资金大量闲置。Midline exit 创造了 capital release 问题。
7. **Trade count exploded**: 101→428 (M1), 73→197 (M2)，成本拖累增加。
8. **Entry-side negative expectancy remains**: 即使 exit 完美，entry at BB lower 的 per-trade expectancy 仍为负。

---

## Q. FINAL HYPOTHESIS VERDICT

### **H1 PARTIALLY SUPPORTED**

**Midline exit 成功修复了 E1.1 所识别的 exit-mismatch 机制**（尾部截断、持仓缩短、PF/payoff 改善、rebound-relapse 减少），但**单独不足以将 ETF BB 策略转为正期望**：

- **机制层面**: 明确支持。Tail、holding、PF、payoff 全部显著改善，exit-mismatch 是真实存在的机制。
- **收益层面**: 部分支持。M2 full window 改善显著（-43%→-21%），但 M1 恶化（-61%→-67%），两者 common window 均未转正。
- **核心障碍**: entry-side 负期望未被修复。Midline exit 只是更快地退出了负期望的交易——它减少了单笔亏损幅度，但交易次数增加 3-4 倍，总亏损并未消除。

**E1.1 的路径观察（100% 触中轨、43% 触中轨后亏损）部分转化为可交易的 exit edge**——它确实截断了尾部和长持仓——但 entry at BB lower 的基础期望为负，exit 优化无法单独解决。

---

## R. FUTURE HYPOTHESES (NOT TESTED IN E2)

| ID | 假设 | 说明 |
|----|------|------|
| H2 | Low-breadth signal filter | E1.1 发现 high breadth PF=0.18 vs low breadth PF=0.89。E2 未加 filter。需独立预注册测试。 |
| H3 | Cluster-aware diversification | E1 发现 16% 天全在同一簇。需独立预注册测试 cluster cap。 |
| H4 | Stock vs ETF cross-sectional dispersion mechanism | E2 Gate 1B 确认 ranking=amount。需获取股票信号明细验证股票版是否有更大横截面离散度。 |
| H5 | Time-stop / stop-loss | E2 禁止。Midline exit 后仍有 28-114 天 loser 持仓，time-stop 可能进一步截断尾部。 |
| H6 | Midline + capital deployment solution | Midline exit 导致 47% 暴露率。需解决资金闲置问题（如更多头寸/更宽 universe），但这是 entry-side 修改。 |
| H7 | BB_Z ranking instead of amount | E2 Gate 1B 确认 amount ranking 信息弱。BB_Z 排序可能有不同信息含量，需独立预注册。 |

**以上仅为假设，禁止在 E2 内测试。E3+ 需独立预注册。**

---

## 输出文件清单

| 文件 | 说明 |
|------|------|
| `e2_gate_midline_return_audit.csv` | Gate 1A 中轨收益审计（逐笔） |
| `e2_gate_ranking_audit.md` | Gate 1B ranking 变量审计 |
| `e2_all_configs_summary.csv` | 4 配置完整指标汇总 |
| `e2_m1_control_summary.csv` | M1 Control 指标 |
| `e2_m1_midline_summary.csv` | M1 Midline 指标 |
| `e2_m2_control_summary.csv` | M2 Control 指标 |
| `e2_m2_midline_summary.csv` | M2 Midline 指标 |
| `e2_common_window_comparison.csv` | Common window 对比 |
| `e2_full_window_comparison.csv` | Full window 对比 |
| `e2_trade_log_m1_control.csv` | M1 Control 交易日志 |
| `e2_trade_log_m1_midline.csv` | M1 Midline 交易日志 |
| `e2_trade_log_m2_control.csv` | M2 Control 交易日志 |
| `e2_trade_log_m2_midline.csv` | M2 Midline 交易日志 |
| `e2_equity_m1_control.csv` | M1 Control 权益曲线 |
| `e2_equity_m1_midline.csv` | M1 Midline 权益曲线 |
| `e2_equity_m2_control.csv` | M2 Control 权益曲线 |
| `e2_equity_m2_midline.csv` | M2 Midline 权益曲线 |
| `e2_daily_panel_m1_control.csv` | M1 Control 日频面板 |
| `e2_daily_panel_m1_midline.csv` | M1 Midline 日频面板 |
| `e2_daily_panel_m2_control.csv` | M2 Control 日频面板 |
| `e2_daily_panel_m2_midline.csv` | M2 Midline 日频面板 |
| `e2_final_report.md` | 本报告 |
| `PHASE_E2_REGISTRY.csv` | E2 预注册冻结 |
| `e2_midline_exit_test.py` | E2 回测引擎 |
