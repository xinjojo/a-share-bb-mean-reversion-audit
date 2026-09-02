# REDTEAM_STRICT_C — DYNAMIC INTRADAY BOLLINGER TOUCH（原策略语义复原审计）

日期: 2026-09-02
状态: 第一代策略正式最终结案（STRICT_C 为原语义复原终版）
前置: Registry SHA256 保持 `5c5e451ad4eb3afd5e632b0019a3e02103e58e375e03cc231c5d8ca52b8c5195`（本轮未触碰 HYPOTHESIS_REGISTRY，未运行 Regime Discovery）。

---

## 0. 目的

外部审计确认 STRICT_V2_A/B 均未精确对应用户原始退出意图。用户原意：
- T 日盘中价格 P(t) 变化，实时上轨 Upper(P)=mean(prev19 closes+P)+2·sd(prev19 closes+P, ddof=1) 随之变化；
- 首次出现 P(t) ≥ Upper(P) 立即卖出（盘中动态 touch，非固定 T-1 上轨、非 T 收盘确认、非含当日 close 的同Bar上轨）。

STRICT_C 用数学保证：在日线数据上也能精确判断"盘中是否曾触碰动态上轨"，从而在不改 T+1/费用/滑点/涨跌停/PIT 等基础设施的前提下复原原语义。

---

## 1. 数学验证

### 1.1 模型
给定前 19 个收盘价 x1..x19，S=Σx，T=Σx²。定义
Upper(P) = (S+P)/20 + 2·sqrt(SS(P)/19),  SS(P) = (19/20)P² − (1/10)SP + T − (1/20)S²
临界价 P* 满足 P* = Upper(P*)。

### 1.2 解析解
平方整理得二次方程：
**5339·P² − 562·S·P + (99·S² − 1600·T) = 0**
判别式 Δ = 1,798,400·(19T − S²) ≥ 0（由 Cauchy S²≤19T 恒成立），故**恒有实解**。
取较大根且满足 P ≥ S/19（原平方条件非负侧）：
P* = (562·S + √Δ) / 10678

### 1.3 单调性 / 唯一性（数值+解析联合证明）
g(P) = P − Upper(P)。
- g(0) < 0（P=0 时上轨为正）；
- P→∞ 时 g(P) ~ 0.95·P → +∞，故至少一根；
- 二次方程恰两根，其中满足 P ≥ S/19 者唯一（另一根落在负平方增根侧）；
- 1000 个真实窗口扫描 (0,P*) 恒 g<0、[P*,50·P*] 恒 g>0，无第二零点、无 P*≤0、无异常/多解。

**结论**：P < P* ⇒ P < Upper(P)（未触碰）；P ≥ P* ⇒ P ≥ Upper(P)（已触碰）。故日线 high ≥ P* 即等价于盘中曾触碰动态上轨——不需要分钟线。

### 1.4 数值对照（真实数据）
- 全相等窗口 x=c ⇒ P*=c（解析=numeric=理论，误差 <1e-9）；
- 1000 个真实 20 日窗口：analytic vs brentq numeric **max|Δ|=4.73e-11**，全部通过 1e-6 阈值；无解/多解/P*≤0/数值不稳定：0 例。

### 1.5 执行映射（STRICT_C）
每持仓 T 日（T+1 起）：
- high_adj < P*：不卖；
- open_adj ≥ P*：gap-through，按 open 卖（开盘已越过触发线，不能假设按 P* 成交）；
- open_adj < P* ≤ high_adj：按 P* 成交；
- 卖出价统一再扣卖出滑点；若 sell_price ≤ limit_down_px：跌停卖不出，顺延；
- 沿用 STRICT_V2 全部修复（PIT ST / PIT list_date+60交易日 / correct涨跌停 / T+1 lot-level / 佣金/印花税/过户费 / 10bp 双腿滑点 / 事件驱动 ETF / 期末清仓同步）。

---

## 2. 触发差异（INVALID current 同Bar vs STRICT_C dynamic，同数据口径 prepare_v51）

| 指标 | 数值 |
|---|---|
| INVALID(同口径) 卖出笔数 | 85 |
| 其中 dynamic 同日触发 | 67（78.8%）|
| 其中 dynamic 从未触发（**假触发**：current 用当日最终上轨、close 大跌把上轨拉低致 high 触到假上轨）| 18（21.2%）|
| prev 语义同日触发 | 73（85.9%）|
| STRICT_C 卖出笔数 | 93 |
| 其中 current 首触发同日 | 68（73.1%）|
| 其中 current 更早触发（INVALID 会提前卖）| 25（26.9%），平均早 **6.43 天**，极值早 133 天 |
| 同日触发者卖出价差 current−dynamic | 均值 **−0.25%**（INVALID 略低卖），中位 −0.16% |

**解读**：差异主要不在"每笔卖价"，而在**触发日期与触发真实性**——21% 的 INVALID 卖出是假触发，27% 的 STRICT_C 交易在 INVALID 语义下被提前卖出（平均早 6.4 天）。

---

## 3. 收益（K=3 / Top10 / BB(20,2) / max_levels=5 / level_cash=20万 / 初资100万 / 2020-01-02~2026-08-25）

### 3.1 组合（ETF 满仓现金管理）
| 版本 | Total | CAGR | MaxDD | Sharpe | 交易数 | 胜率 | 股票已实现PnL |
|---|---|---|---|---|---|---|---|
| INVALID_REPORT（报告口径, current, nav, snapshot ST, old limit）| +383.7% | 27.1% | — | — | 103 | 75.7% | 202.1万 |
| INVALID_同口径（current, prepare_v51）| +40.7% | 5.3% | — | — | 86 | 60.5% | 15.7万 |
| STRICT_A（prev）| +45.1% | 5.8% | −40.5% | 0.35 | 100 | 68.0% | 18.5万 |
| STRICT_B（confirm→T+1 open）| +74.4% | 8.8% | −39.2% | 0.46 | 73 | 63.0% | 15.0万 |
| **STRICT_C（dynamic touch）** | **+89.1%** | **10.2%** | −39.6% | 0.52 | 96 | 68.8% | **54.6万** |
| 标普500ETF(513500) buy&hold | +26.6% | — | — | — | — | — | — |

### 3.2 纯股票（etf_enabled=False，剔除现金管理）
| 版本 | Total | CAGR | MaxDD | Sharpe | 交易数 | 胜率 | 股票PnL |
|---|---|---|---|---|---|---|---|
| STRICT_A | +5.15% | 0.77% | −39.9% | 0.16 | 100 | 70.0% | 5.2万 |
| STRICT_B | +23.40% | 3.25% | −39.9% | 0.25 | 72 | 62.5% | 23.4万 |
| **STRICT_C** | **+49.60%** | **6.32%** | −35.5% | 0.38 | 96 | 68.8% | **49.6万** |

### 3.3 归因（combo 期末拆解）
- 组合总收益 +89.1%（期末 189.1 万）；
- 股票已实现 PnL 54.6 万 = 初始资金的 **54.6%**；
- ETF+现金贡献（含空仓期标普持仓与买卖）34.6 万 = **34.6%**；
- 纯股票累计 +49.6%。

### 3.4 逐笔归因：INVALID(同口径) vs STRICT_C
| 项 | INVALID | STRICT_C |
|---|---|---|
| 笔数（非结算）| 85 | 93 |
| 已实现PnL合计 | 23.7万 | 61.9万（+38.1万）|
| 平均/笔 | 2,793 | 6,655 |
| 平均持仓 | 30.6天 | 34.8天 |
| 盈利笔（平均）| 52（3.09万）| 65（2.93万）|
| 亏损笔（平均）| 33（−4.15万）| 28（−4.58万）|
| 盈亏比 | 1.17 | **1.48** |

**回答"为什么不是每笔少卖1%、结果却差几百pp"**：
1. 同日触发者卖出价差**仅 0.25%**——差异不是卖价；
2. 真正差异是**触发日期与真实性**：21% INVALID 卖出是假触发（current 用含当日 close 的最终上轨，close 大跌把上轨拉低 → 假卖出），27% 交易被 current 提前 6.4 天卖出；
3. 退出日改变 → 资金复用与 ETF 再配置路径全变 → 股票盈亏比 1.17→1.48、股票 PnL +38 万、组合 +48pp；
4. 旧报告"354.9→45/74 差几百pp"是**多项修复叠加**（listing/ST/correct limit/复权/ETF时序）的结果，不是单一退出语义；本轮在固定其余全部修复后，**仅退出语义 current→dynamic 贡献组合约 +48pp**。

---

## 4. 跨期稳定性（STRICT_C combo 分年 + Train/Test）

| 年份 | combo 收益 |
|---|---|
| 2020 | +29.7% |
| 2021 | +29.3% |
| 2022 | +4.5% |
| 2023 | −15.7% |
| 2024 | +3.3% |
| 2025 | +25.7% |
| 2026 | −0.8% |

Train 2020-2023 / Test 2024-2026：
| 口径 | Train | Test |
|---|---|---|
| combo | +48.9% (ann 10.6%, sh 0.53) | +23.5% (ann 8.4%, sh 0.43) |
| **纯股票** | +28.7% (ann 6.6%, sh 0.38) | **+1.26% (ann 0.48%, sh 0.16)** |

**结论**：组合 Test 正收益主要来自 ETF 满仓现金管理（2024-2026 标普上涨）；**纯股票 STRICT_C 样本外 +1.26%≈0**，跨期不稳定（2023 −15.7%、2026 −0.8%），Sharpe 0.38（全期纯股）/0.16（Test 纯股）。

---

## 5. 评级

STRICT_C 未"意外恢复出非常强的结果"（纯股累计 49.6% 优于 A/B，但 Test 纯股仅 +1.26%、分年两负、Sharpe 低）。因此：
- 不标 NEW MATERIAL FINDING；
- **第一代策略正式最终结案**；
- 延续 **D — No evidence**：修复所有已知因果/PIT/执行问题、并用用户原始"盘中动态上轨触碰"语义复原后，仍无稳定、可重复、可外推的 A 股股票 Alpha；
- 组合收益的可见部分中，股票均值回归提供的超额有限，收益大头来自标普500ETF 现金管理（34.6% vs 股票 54.6%，且 OOS 股票≈0）。

---

## 6. 产物与复现

- 数学验证：`run_strict_c_math.py`（解析解 + brentq 对照 + 1000 窗口）
- STRICT_C 引擎：`run_strict_c.py`（`run_fast_multi_strict_c`，基于 STRICT_V2 基础设施）
- 语义对照：`semantic_touch.py`
- 归因/纯股/分年/Train-Test：`strict_c_attribution.py`
- 结果 CSV：`results/round5/strict_c_trades.csv`、`strict_c_equity.csv`、`strict_c_pure_*.csv`、`strict_c_matrix.csv`、`semantic_*.csv`

复现：`python3 run_strict_c_math.py && python3 run_strict_c.py all && python3 semantic_touch.py && python3 strict_c_attribution.py`

Registry 未修改（SHA256 `5c5e451a...` 不变），未运行任何 Discovery 统计。
