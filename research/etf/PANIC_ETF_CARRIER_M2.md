# PHASE R2.0 + M2 — ONE FROZEN BROAD-MARKET ETF CARRIER TEST

## Governance / Registry
- 外审最终结论（前置）：M1.2 = B — NARROW MARKET TRANSLATION；ETF gate = YES — WORTHY OF ONE FROZEN CARRIER TEST（精确含义：不是 ETF signal validated，只允许一次严格冻结的真实可交易宽基 ETF carrier test，不得开启 ETF 参数开发）。
- R2.0 接受 M1.2 B；正式措辞：PANIC80 has a NARROW, STATISTICALLY WEAK, EPISODE-DEPENDENT market-rebound indication。
- Prereg：`research/etf/registries/PANIC_ETF_CARRIER_M2_REGISTRY.csv`，SHA `7ff3333e6ea5897bc4c9bdecacdaf8914d3b1ce4d2a7e72902a5f70790f08e8b`，commit `b32dfed`（M2-A），先于结果。
- 2025–2026 CLOSED；本阶段未读取、未回测。

## Carrier selection（outcome-free，结果前完成）
- 候选（仓库已有、A 股宽基、2020–2024 数据连续）：510300.SH / 159919.SZ / 510310.SH / 510500.SH / 510050.SH / 159915.SZ。
- 元数据 audit（`results/evidence/m2/m2_carrier_audit.csv`）：全部候选 2020–2024 覆盖 ≥99.9%、open/amount 缺失 0；median amount 510300.SH 最高（≈229.9 亿元）。
- **PRIMARY = 510300.SH（华泰柏瑞沪深300ETF，underlying 000300.SH）**：
  1. 沪深300 = 标准全市场代表宽基，与全市场 B20 breadth 来源最匹配；
  2. 2020–2024 完整覆盖（1212/1212 日，0 缺失，0 零成交）；
  3. 2012-05-28 上市，覆盖全部开发期；
  4. A 股宽基中流动性最高（median amount 229.9e4 万）；
  5. 长期沪深300 跟踪、数据可靠。
- 选择仅基于非 outcome 元数据；未计算任何 signal-conditioned ETF 收益（`m2_carrier_choice.json` 明示）。

## Signal / Execution
- PANIC80 完全沿用 M1.2（expanding 80th pct，date<T 参考分布，252 前交易日 warmup）；188 个 panic 日 parity 断言通过。
- T 收盘确认信号 → **T+1 open 买入**（510300 真实 fund_daily open）；T+1 无有效报价 → 跳过（frozen rule，无回补）。
- 持有恰好 5 个交易日：entry = T+1 open（第 1 持有日），exit = 第 5 持有日 close = close(T+5)（exit_idx = entry_idx+4）。
- **单一活跃仓位**：持仓期间新 PANIC 信号忽略（不加仓/不延期/不重置 exit）；仅当仓位完全退出后才允许下一笔（非重叠可执行 carrier test）。
- 100,000 RMB 独立 ETF-only 账户、无杠杆、100 份整数倍（qty = floor(cash/(fill×100))×100）；空仓现金收益 0（无 513500/货基/国债/现金管理）。
- 成本：佣金 0.025% 单边（最低 5 元）+ 滑点 0.10% 单边；ETF 二级市场无印花税（真实规则）；gross/cost/net 均报告。

## Results
### 交易与经济指标（`m2_risk.json` / `m2_summary.json`）
| 指标 | 值 |
|---|---|
| trades | 78 |
| time in market | 32.18% |
| gross total（单笔毛收益之和） | −1.43% |
| net total return（账户） | **−5.309%** |
| total PnL | −5,309 元 |
| CAGR | −1.13% |
| MaxDD | −23.25% |
| Sharpe | −0.059 |
| Sortino | −0.052 |
| Calmar | −0.049 |
| worst trade | −5.40%（2021-07-26 entry） |
| best trade | +6.83%（2022-10-31 entry） |
| max consecutive losses | 4 |
| worst 5-day account move | −6.17% |
| total cost（佣金） | 3,891.5 元（滑点计入成交价；gross−net ≈ 3.9pp） |

### 逐年（`m2_yearly.csv`）
| year | trades | net PnL | net return | mean trade | win |
|---|---|---|---|---|---|
| 2021 | 20 | +8,770 | +8.78% | +0.44% | 65.0% |
| 2022 | 20 | −3,464 | −3.47% | −0.17% | 35.0% |
| 2023 | 19 | −17,320 | −17.35% | −0.91% | 47.4% |
| 2024 | 19 | +6,704 | +6.72% | +0.35% | 47.4% |

正年份：**2/4**（2021、2024）。2023 年单年拖累 −17.35%（panic 后 5 日继续深跌）。

### 基准（`m2_benchmark.json`）
BUY_AND_HOLD 510300（2021-01-04 open 买入 → 2024-12-31 close 卖出，同成本）：gross −23.83%，net **−24.02%**。
→ M2 策略 −5.31% 相对 buy&hold 少亏约 18.7pp，但绝对净收益为负，且大部分时间空仓（time in market 32%）。

### 统计推断
- trade-level bootstrap（B=5000, seed=0）：mean −0.074%，95% CI **[−0.607, +0.457]**（跨 0）。
- calendar-year stratified permutation null（B=5000, seed=0，同年代替非 panic 日、相同成本约定）：observed mean −0.068%；null mean −0.392%（null CI [−0.972, +0.308]）；**empirical p = 0.159**（不显著）。
- matched non-panic delta：panic 5d mean −0.068% vs matched non-panic −0.583%，**delta +0.5144pp**（方向与 M1.2 FWD5 +0.2752pp 一致——panic 后相对普通日确实略好；但绝对均值为负、统计不显著，且 2023 年严重亏损，无法转成经济优势）。

### Cluster-day 诊断（`m2_cluster_diagnostic.csv`，diagnostic only）
78 笔真实 non-overlap 交易中：cluster 第 1 天 67 笔（85.9%）、第 2 天 9 笔、第 3 天 1 笔、第 6 天 1 笔。绝大多数入场在 panic cluster 首日（与"新信号只在前一笔退出后才允许"规则一致，非选择偏差）。

### 集中度（`m2_concentration.json`）
单笔最大盈利 +6,828 元（2022-10-31，占总 PnL −128.6%，因总量为负）；2023 年集中亏损 −17,320（占总亏损 73.5%）。

## Classification
按 Registry 冻结 gate：
- A（net TR>0 + mean trade>0 + boot lower>0 + perm p<0.05 + ≥3/4 年正 + MaxDD 可接受 + 单笔 <50%）：不满足（net 负、p=0.159、2/4 年）。
- B（net>0 + mean>0 + ≥3/4 年正，部分 CI 弱）：不满足（net −5.31% < 0、2/4 年）。
- D（net negative 或 risk materially bad）：**满足（net total return −5.31% < 0）**。

**M2 = D — HARMFUL。**
即使 matched 相对优势（+0.51pp）与 M1.2 方向一致，真实可交易 ETF carrier 在扣成本后绝对净亏、统计不显著、2023 年尾部灾难 → breadth→ETF 的 carrier 转译失败。

## 措辞纪律
- 不写 "validated ETF alpha" / "robust timing signal"。
- M1.2 = B（narrow/weak/episode-dependent market-rebound indication）保持有效；M2 = D 表示该 indication **无法通过单宽基 ETF carrier 转成 after-cost 经济优势**。
- 2020–2024 仍为 development；未读取 2025–2026。

## Invariants（`m2_invariants.json`）
I1–I15 全部断言通过：单 carrier（510300.SH）、carrier 先于 outcome 选定、PANIC80 不变（188 parity）、T+1 open、5 日持有、单一活跃仓位、新信号忽略、无延期、100k 无杠杆、真实 fund_daily OHLC、成本冻结、matched null 存在、无扫描、2025–2026 CLOSED。
