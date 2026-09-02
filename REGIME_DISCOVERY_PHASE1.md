# REGIME DISCOVERY — PHASE 1（2020-01-01 ~ 2022-12-31）
## 预注册 104 条 PRIMARY hypothesis 全量执行结果
仅 Discovery；未打开 Validation/Confirmation；未修改 Registry（SHA256 冻结）。

---

## 一、Registry 核验与方法

- HYPOTHESIS_REGISTRY.csv：104 行 PRIMARY，SHA256 = `5c5e451ad4eb3afd5e632b0019a3e02103e58e375e03cc231c5d8ca52b8c5195` ✓（运行前核验一致）
- 数据：`combined_daily.parquet`（2020-01-02~2023-02-28 加载，Discovery 事件窗口仅 2020-01-01~2022-12-31），含 214 只退市股历史行情（无幸存者偏差）
- PIT universe：上市满 60 交易日（真实 list_date，trade_cal 推进）+ 非 ST(PIT) + 当日有效行情；不用 delist_date 回填（避免 PIT 泄漏）
- 全A等权指数：每日 = PIT eligible 股票当日收益等权均值（无当日成交额权重反馈）
- Regime（冻结公式）：TREND ret20>+3%/-3%；BREADTH MA20 上占比 <0.30/0.30-0.70/>0.70；VOLATILITY rv20=std(mkt_ret T-19..T)×√245 的 PIT 百分位(≤0.20/0.20-0.60/0.60-0.90/>0.90, min_periods=100 否则 WARMUP)；LIQUIDITY 全A成交额/MA20 <0.80/0.80-1.20/>1.20
- Oversold：BB_zscore 互斥 bins B1(-2.0,-1.5] / B2(-2.5,-2.0] / B3(-3.0,-2.5] / B4(≤-3.0)
- Outcome（P0 修正后）：causal_otc = close_adj[T+5|T+10] / open_adj[T+1] − 1（T+1 open 起可交易；T+1 停牌单独标记 182 事件，不纳入 return 统计）
- Benchmark：same_oversold_unconditional = 同 (oversold_bin, horizon) 下 Discovery 全事件日级截面均值再平均
- 统计：日级聚合（处理同日横截面相关）；HAC t（Newey-West 自动带宽）；raw p（t 分布）；FDR（BH q=0.05，全 104）；circular block bootstrap（L=21, B=2000）
- 门槛：n_independent_days < 150 → INSUFFICIENT_SAMPLE

---

## 二、104 格汇总

| 类别 | 数量 |
|---|---|
| VALID_SAMPLE | **50** |
| INSUFFICIENT_SAMPLE | **54** |
| **FDR_SIGNIFICANT (q<0.05)** | **0** |
| 方向为正但不显著 | 15 |
| 方向为负 | 35 |

各维度 VALID：TREND 20 / BREADTH 14 / LIQUIDITY 8 / VOLATILITY 8。
各 oversold bin VALID：B1 14 / B2 14 / B3 14 / B4 8。
各 horizon VALID：5D 25 / 10D 25。

oversold 事件总数（Discovery）：373,856；T+1 停牌 182（单独标记）；otc5 缺失 334 / otc10 缺失 458（缺失不纳入，数量单独报告）。

INSUFFICIENT_SAMPLE 分布（54）：BREADTH HIGH 8、BREADTH LOW 2、LIQUIDITY HIGH 8、LIQUIDITY LOW 8、TREND DOWN 2、TREND UP 2、VOLATILITY EXTREME 8、VOLATILITY HIGH 8、VOLATILITY LOW 8 —— 主要是极端 regime（EXTREME/HIGH/LOW）+ 极端 oversold 档位独立日不足 150。

---

## 三、最强的可观测模式（待验证，非结论）

在 50 个 VALID 格中，唯一跨 oversold bin 一致为正、且 HAC t 较大的族是：

**BREADTH LOW（市场宽度 <30%，即多数股票在 MA20 之下/弱势市）时的超跌反弹**

| 格 | bin | horizon | 独立日 | excess | 胜率 | HAC t | raw p | FDR q | boot_p | 95% CI |
|---|---|---|---|---|---|---|---|---|---|---|
| P0027 | B2 | 5D | 165 | +1.17% | 56.1% | 2.12 | 0.035 | 0.846 | 0.006 | [0.24%, 2.05%] |
| P0028 | B2 | 10D | 165 | +1.51% | 57.1% | 2.00 | 0.048 | 0.846 | 0.043 | [-0.23%, 3.07%] |
| P0026 | B1 | 10D | 168 | +1.19% | 53.9% | 1.55 | 0.123 | 0.846 | 0.064 | — |
| P0025 | B1 | 5D | 168 | +0.81% | 53.9% | 1.47 | 0.143 | 0.846 | 0.040 | — |
| P0030 | B3 | 10D | 159 | +1.02% | 59.5% | 1.17 | 0.242 | 0.846 | 0.142 | — |

**但没有任何一格通过 FDR（最小 q=0.830）**。TREND DOWN 档为弱正（excess +0.2%~+0.6%，t<1），其余大多数格（TREND UP/SIDEWAYS、BREADTH MID、VOLATILITY NORMAL、LIQUIDITY NORMAL）方向为负。

---

## 四、Phase 1 结论（严格限定）

1. **Discovery 区间内，没有任何 regime×oversold×horizon 组合通过 FDR 多重检验**（FDR_SIGNIFICANT = 0）。
2. 50 个 VALID 格中 35 格方向为负、15 格为正但不显著。
3. 出现一个**跨档一致的候选模式**：BREADTH LOW（弱势市场）下超跌反弹 excess 为正（最大 +1.51% 10D），方向与金融直觉一致，但**未通过多重检验校正**，且集中在一个 regime 假设族内。
4. 按预注册纪律：**本结果仅作 Discovery 发现，不得据此选参数或形成策略**；该候选模式进入 Validation 阶段的预注册验证名单（仅作待验证信号，不视为已成立）。

完整 104 格矩阵：`results/regime_discovery_matrix.csv`（含 VALID 与 INSUFFICIENT 全部格）。

未打开 Validation（2023-2024）；未打开 Confirmation（2025-2026）；未修改 Registry；未形成交易策略。
