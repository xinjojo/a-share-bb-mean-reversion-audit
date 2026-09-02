# INDEPENDENT TRADE REPLAY — ALL A SHARES

> 研究问题（唯一）：在当前已审计的 **STRICT_C_EXECUTABLE_TICK** 因果/执行语义下，"成交额筛选 + Bollinger 超跌均值回归"作为**一笔笔互相独立的交易**，本身是否有稳定正向 expectancy。
> 这不是组合构建实验，不计算 100 万本金复利收益；不涉及 K / ETF / 资金竞争。
> 每只股票的每次 signal→entry→exit 作为一笔独立 trade（只测 SIGNAL/TRADE EDGE）。

---

## 1. 交易定义

- **PRIMARY**：信号 = 当日全市场成交额 **Top10**（候选：上市满 60 交易日 & 非 ST[PIT]）中的股票，且 `close_adj < BB_lower(20,2)` 且当日非跌停 → 触发 initial entry。
- **SECONDARY**：所有 PIT eligible A 股满足上述超跌条件即触发（不限制 Top10）。
- 信号日 **T** 收盘确认 → **T+1 open** 成交；开盘涨停买不进则顺延（pending 保留至首个可成交 open）。
- 加仓：持仓中 `close_adj < BB_lower` 且非跌停、距上次加仓 ≥1 交易日、未达 5 层 → T+1 open 加一层（每层 200,000 元）。停牌日 pending 顺延（与原组合引擎"停牌日丢弃"的差异见 §9）。
- 退出：PRIMARY 主 = **STRICT_C 动态盘中 P\***（见 §2）；对照 = STRICT_A（前一日历日已知上轨）/ STRICT_B（收盘确认→T+1 open）。
- 统计单元：**TRADE_EPISODE**（initial entry → final exit）为 PRIMARY；**ENTRY_LAYER**（每层独立经济收益）单独输出。

## 2. 沿用已审计语义（STRICT_C_EXECUTABLE_TICK）

| 项 | 实现 |
|---|---|
| PIT ST | `data/pit_st_daily.parquet` 的 `is_st_pit`（namechange 重建） |
| 上市满 60 日 | `stock_basic.list_date` + 1990 起完整交易日历，`first_eligible_i = pos(list_date)+60` |
| correct price limits | 科创 20% / 创业 20%(2020-08-24 后) / ST 5% / 主板 10%；**北交所沿用审计版 10%**（未特判 30%，见 §9） |
| T+1 | 买入次日方可卖出（`hold>=1`） |
| 100 股整数倍 | `qty = floor(level_cash/buy_price/100)*100` |
| 费用 | 佣金 0.025%(min 5 元) + 过户费 0.001%（买卖）；印花税卖出：2023-08-28 前 0.1%、后 0.05% |
| 滑点 | 10bp；买入 `open*(1+slip)`，卖出 `ref*(1-slip)` |
| 动态 P\* | `P\* = analytic_Pstar(x)`，`x_k = close_raw[k]*adj_factor[k]`（各日自己复权因子，ddof=1）；`P*_raw = P*_adj/adj[T]` |
| tick | `threshold = ceil(P*_raw/0.01)*0.01`；`open_adj>=threshold*adj[T]` → ref=open（gap-through），否则 ref=threshold（touch） |
| 跌停可成交 | 先判市场可达性（`ref<=limit_down_px` 不卖），再应用滑点（ref_first） |
| 期末清仓 | 每只股票用其**最后有数据日 close** 结算（含费用），计入 episode |
| 数据 | `combined_daily.parquet` 2020-01-02 ~ 2026-08-25，1611 交易日，5725 只有数据股票；BB 无 warmup（与 STRICT_C 组合引擎同口径） |

**禁止恢复**：final-close BB upper hindsight、同 Bar 未来信息、current-name ST、fake listing、retroactive ETF、future OHLC next-open fill。

## 3. PRIMARY — Headline（STRICT_C dynamic touch, 299 episodes）

| 指标 | 值 |
|---|---|
| total trade episodes | **299** |
| mean return | **+5.00%** |
| median return | **+5.23%** |
| win rate | **75.9%** |
| P10 / P25 / P75 / P90 | -6.74% / +0.65% / +10.35% / +17.28% |
| mean holding days | 34.5 |
| median holding days | 28.0 |
| mean PnL after all costs | +9,825 元/episode（每层 20 万、平均 2.2 层/笔，平均投入约 44 万） |
| profit factor | **1.60** |
| expected return per trade | **+5.00%** |

## 4. PRIMARY — 年度稳定性与时间切分

| 年份 | n | mean | median | win% | P10 | P90 |
|---|---|---|---|---|---|---|
| 2020 | 33 | +6.71 | +5.22 | 87.9 | -0.75 | +16.32 |
| 2021 | 58 | +4.52 | +5.40 | 75.9 | -15.30 | +20.77 |
| 2022 | 59 | +4.75 | +4.75 | 71.2 | -6.31 | +15.43 |
| 2023 | 45 | +2.13 | +3.63 | 68.9 | -14.47 | +10.50 |
| 2024 | 50 | +6.60 | +6.76 | 80.0 | -3.71 | +16.61 |
| 2025 | 34 | +8.41 | +5.36 | 88.2 | +0.20 | +22.05 |
| 2026 YTD | 20 | +1.03 | +1.41 | 55.0 | -12.34 | +13.60 |

**7 个年份（含 2026 YTD）mean 全部为正。** 2026 年样本仅 20 笔，为最弱但仍正的年份。

| 切分 | n | mean | median | win% | profit factor |
|---|---|---|---|---|---|
| 2020-2023 | 195 | +4.41 | +4.92 | 74.9 | 1.27 |
| 2024-2026 | 104 | +6.12 | +5.45 | 77.9 | 3.33 |

**edge 未随时间衰减**：近年（2024-2026）均值与盈亏比反而高于早期（+6.12% vs +4.41%）。

## 5. PRIMARY — 日级聚合（EVENT_DAY_LEVEL + HAC）

每个 signal date 取当日所有 episode return 的截面均值，构建 daily series。

| 指标 | 值 |
|---|---|
| n event days | 249 |
| mean daily cross-sectional return | **+4.87%** |
| median | +5.20% |
| positive-day rate | 75.1% |
| Newey-West HAC t | **6.41** |
| HAC p | ≈0 |
| 95% CI | **[+3.39, +6.36]**（全正） |

**Block bootstrap**（circular block L=21, B=2000, 保持事件日时间结构）：mean CI **[+3.28, +6.50]**，`P(mean≤0)=0.000%`。

## 6. PRIMARY — 集中度与截面

| 集中度 | 值 |
|---|---|
| top 1% 盈利交易对总 PnL 贡献 | 23.2% |
| top 5% | 66.5% |
| worst 1% | -852k 元 |
| 去掉 best 1% 后 mean / median | +4.68% / +5.21% |
| 去掉 best 5% 后 mean / median | +4.07% / +4.76% |
| 去掉贡献最大 10 只股票后 mean / median | +3.93% / +4.70% |
| 去掉贡献最大行业（白酒）后 mean / median | +4.92% / +5.31% |

**结论：收益不依赖极少数超级赢家**（去掉 best 5% 后仍 +4.07%）。

| 截面 | n | mean | median | win% |
|---|---|---|---|---|
| amount Q5（Top10 全落于当日成交额前 20%，符合定义） | 299 | +5.00 | +5.23 | 75.9 |
| oversold B2 (-2.5<z≤-2) | 186 | +5.23 | +5.43 | 75.3 |
| oversold B3 (-3<z≤-2.5) | 84 | +4.27 | +3.81 | 77.4 |
| oversold B4 (z≤-3) | 29 | +5.65 | +6.92 | 75.9 |

**market cap quintile：UNAVAILABLE**（combined_daily 无 total_mv/circ_mv 字段，未用 current 分类冒充 PIT）。industry 分层基于 `stock_basic` 当前快照（非 PIT），仅描述性。

## 7. ENTRY_LAYER（PRIMARY, 每层独立经济收益）

| level | n | mean PnL | win% |
|---|---|---|---|
| 1 | 299 | +1,245 | 58.9 |
| 2 | 211 | +4,713 | 62.1 |
| 3 | 115 | +7,343 | 67.8 |
| 4 | 64 | +5,837 | 62.5 |
| 5 | 39 | +9,048 | 59.0 |

加仓层（L2-L5）均正。注意 ENTRY_LAYER 是**分层级**口径（每层按其份额分配最终卖出净收入，减去该层成本），不是 episode 数。

## 8. 退出语义对照（同一批 entry 信号规则）

| 退出模式 | n | mean | median | win% | profit factor | mean hold |
|---|---|---|---|---|---|---|
| STRICT_C dynamic touch（主） | 299 | +5.00 | +5.23 | 75.9 | 1.60 | 34.5 |
| STRICT_A prev-day BB upper | 307 | +4.57 | +4.75 | 75.9 | 1.67 | 31.6 |
| STRICT_B close-confirm→next-open | 284 | +6.08 | +5.81 | 73.2 | 1.56 | 46.6 |

三种严格因果退出均呈正 edge，**独立交易 edge 不依赖特定退出定义**（INVALID final-close hindsight 版本仅作 INVALID_HISTORICAL_REFERENCE，不用于结论）。

## 9. SECONDARY（all eligible oversold, 89,188 episodes）

| 指标 | 值 |
|---|---|
| total episodes | **89,188** |
| mean / median return | +5.24% / +5.45% |
| win rate | 77.6% |
| P10 / P90 | -5.83% / +16.57% |
| mean / median hold | 31.1 / 25.0 天 |
| profit factor | **1.79** |

逐年 mean：2020 +4.36 / 2021 +5.80 / 2022 +5.81 / 2023 +3.11 / 2024 +5.90 / 2025 +8.15 / **2026 +2.74（7 年均正）**。
EVENT_DAY：n=1496 事件日，mean_daily **+3.89%**，HAC t=14.10，95% CI **[+3.35, +4.43]**；block bootstrap CI **[+3.22, +4.60]**，P(≤0)=0%。
子集：delisted（在库退市股）1,227 笔 mean +0.58%（win 69.4%）；北交所 .BJ 1,291 笔 mean +3.93%；非退市非北交所 86,670 笔 mean +5.33%。单股 episode 最多 29 笔/6 年（无极端聚集）。

## 10. 幸存者偏差（如实报告，不声称消除）

- 数据内：5765 只在库（2020 起），其中 **15 只 2020 后退市股完全缺失**（000018/000587/000939/002260/002450/002604/300028/300104/300216/600074/600240/600385 + 3 只北交所转板）；另有 **147 只在库退市股数据提前截断**（早于退市日 1~4 个月断档），仅 82 只覆盖到退市日±5 日。
- PRIMARY 299 笔中 **0 笔 delisted、0 笔 .BJ**（Top10 成交额口径天然避开小盘退市股与北交所）。
- SECONDARY 中在库退市股 1,227 笔（mean +0.58%），未拖累整体；但缺失/截断的退市股最后暴跌段**可能被低估**，方向为**高估 edge**。
- 结论：survivorship completeness 为 **KNOWN LIMITATION**，无法从当前数据完全排除。

## 11. 其他数据限制

- 数据仅 2020-01-02 起，BB/P\* 无 warmup，2020 年初约 20 个交易日内信号稀疏（与 STRICT_C 组合引擎同口径）。
- 停牌日 pending 顺延至复牌日执行（原组合引擎为简化在停牌日丢弃；独立 replay 采用顺延，方向更保守，不夸大 edge）。
- 北交所（2025 起才有 .BJ 数据）涨跌停按审计版 10% 判定，未按 30% 特判；仅影响 SECONDARY 中 1,291 笔（mean +3.93%）。
- 期末清仓用每只股票最后有数据日 close（原组合引擎对最后日无数据的持仓残留不计值，独立 replay 显式结算，避免价值丢失）。

## 12. 结论分类

**A — ROBUST SIGNAL-LEVEL EDGE**

依据（均在 STRICT_C_EXECUTABLE_TICK 严格因果语义下）：
1. PRIMARY 299 笔独立交易：mean +5.00%、median +5.23%、win 75.9%、PF 1.60。
2. **7 个年份 mean 全部为正**，2024-2026（+6.12%）不低于 2020-2023（+4.41%），**edge 未衰减**。
3. EVENT_DAY 层面 HAC t=6.41、block bootstrap CI 全正、P(≤0)=0%。
4. 集中度低：去掉 best 5% 仍 +4.07%，去掉 top10 股票仍 +3.93%。
5. 三种严格退出定义均正（+4.57%~+6.08%），不依赖特定退出。
6. SECONDARY（89,188 笔）与 PRIMARY 结论一致，互为交叉验证。

**严谨限定**：
- 本结论只针对**独立交易层的 signal/trade edge**，**不改变第一代组合级评级 D**（组合收益受 K=3、共享资金池、ETF funding path 等组合构建问题主导，是另一层研究）。
- 数据仅到 2026-08-25；2026 仅 YTD 且为最弱年份（PRIMARY 20 笔 +1.03%）。未来实盘/paper trading 前仍需：真正 PIT 股票池 + 成交冲击容量测试 + 未观察数据的 forward test。
- 本实验未做费用/滑点压力扫描（固定 10bp）；更高的真实成交成本需单独敏感性验证。
