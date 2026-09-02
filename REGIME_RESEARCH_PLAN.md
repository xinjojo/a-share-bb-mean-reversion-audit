# REGIME_RESEARCH_PLAN — 市场状态 × 超跌程度 → 条件收益研究设计（v2，外部预审修订版）

> 状态：**设计稿 v2，未开始执行**。本阶段不调参、不产生交易策略、不输出"最佳策略"。
> 本版已按外部审计预审意见（CONDITIONAL PASS）修正 4 个方法论问题：
> P0 前瞻收益起点改为因果口径；P1 2025-2026 改名 Retrospective Confirmation；P2 假设家族预注册（PRIMARY/SECONDARY 分层）；P3 Permutation 保持市场结构。
> 预审通过后方可进入 **REGIME DISCOVERY — Phase 1**。

---

## 0. 研究问题（唯一问题）

> 在 A 股市场，当一只股票进入不同程度的"超跌状态"后，其未来收益分布，**在哪些市场 Regime（趋势/宽度/波动/流动性 × 超跌类型）下显著为正、在哪些 Regime 下为负或无效？**

本阶段只绘制 **REGIME_ALPHA_MATRIX**（条件 Alpha 矩阵），不找"能赚钱的策略"。

---

## 1. 数据需求

### 1.1 核心数据（已有）
- `data/combined_daily.parquet`：2020-01-02 ~ 2026-08-25，全 A 日线（open/high/low/close/volume/amount/adj_factor/pre_close），amount 单位=千元
- `data/pit_st_daily.parquet`：PIT ST 状态
- `data/raw/stock_basic.parquet`：list_date / delist_date / 当前 name
- `data/raw/trade_cal_full.parquet`：1990 起完整交易日历
- `data/etf_513500_merged.parquet`：场内 OHLCV

### 1.2 必须补齐
| 数据 | 用途 | 状态 |
|---|---|---|
| 历史退市股日线（2020 后约 15+ 只） | 消除 survivorship bias | ❌ NEED_EXTERNAL_DATA |
| 指数历史（沪深300/中证500/中证1000/全A） | Regime 趋势/波动/宽度 | ⏳ 待下载 |
| 每日涨跌停家数、连板高度、炸板率 | 情绪（SECONDARY） | ⏳ 由日线派生 |
| 个股退市日 | 资格/剔除退市后 | ⏳ 待下载 |

### 1.3 数据质量门槛
- 信号/特征用后复权 `close_adj = close × adj_factor`（PIT 已验证 signal_diff=0）
- **前瞻收益亦用后复权**（`open_adj`、`close_adj`），保证跨除权除息连续
- 全区间交易日对齐 `trade_cal_full`

---

## 2. PIT 要求（强制，同 v1）

所有"超跌事件"在 T 日构造时只允许 T 日及之前可知的信息：PIT ST（`pit_st_daily`）、上市满 60 交易日（list_date+完整日历）、退市区间截断、涨跌停制度（PIT ST 派生）、Regime 标签 rolling 右对齐（禁止事后打标/中心平滑）。

---

## 3. Regime 定义候选（A-F，同 v1，但 PRIMARY/SECONDARY 分层见 §8）

### A. 指数趋势
- 指数：全A（成交额加权自建）**（PRIMARY）**；沪深300/中证500/中证1000/等权全A（SECONDARY）
- 定义：`close > MA20 > MA60` 排列、指数 20 日收益、DMA
- 状态：上涨 / 震荡 / 下跌（20 日收益阈值，稳健性 ±20% 扰动）

### B. 市场宽度（PRIMARY：MA20 above ratio）
- MA20 以上股票占比（**PRIMARY**）；MA60 以上占比、上涨占比、创新高/新低比例（SECONDARY）
- 状态：高位（>70%）/ 中位 / 低位（<30%）

### C. 市场波动率（PRIMARY：20D realized vol）
- 全A 指数 20 日 realized vol（日收益 std×√245）（**PRIMARY**）；VIX 类/分位（SECONDARY）
- 状态：低 / 正常 / 高 / 极端（历史分位 20/60/90 切）

### D. 市场情绪（SECONDARY）
- 涨停家数、跌停家数、连板高度、炸板率、成交额环比；状态：冰点 / 正常 / 亢奋

### E. 流动性（PRIMARY：全A成交额）
- 全市场成交额、成交额 20 日趋势（**PRIMARY**）；缩量/放量细化（SECONDARY）
- 状态：地量 / 正常 / 天量

### F. 超跌类型（SECONDARY，用于归因解释，不做 primary 假设）
- 正常回调 / 快速恐慌下跌 / 连续阴跌 / 系统性股灾 / 个股独立暴跌

---

## 4. 超跌特征（PRIMARY / SECONDARY）

- **PRIMARY OVERSOLD FEATURE：BB_zscore = (close - MA20)/std20**（`rolling(20).mean()`/`.std()`，ddof=1，右对齐），档位：≤ -1.5 / -2.0 / -2.5 / -3.0（4 档）
- SECONDARY：distance_to_MA20/MA60、RSI(14)、N日收益、N日最大回撤、ATR(14)/close、realized_vol(20)、volume_change、amount_rank

---

## 5. Forward Return 定义（v2，P0 修正）

> **原则：超跌信号在 T 日收盘后确定，最早可交易价格从 T+1 open 开始。**

### 5.1 DESCRIPTIVE_RETURN（仅描述，非主指标）
```
desc_r[N] = close_adj[T+N] / close_adj[T] - 1
```
**明确标注 `NON_TRADABLE_REFERENCE`**：因为它隐含"15:00 知道信号→按 15:00 close 成交"。仅用于描述价格路径，不进入 Alpha 显著性检验。

### 5.2 CAUSAL_RETURN（主指标，v2 新增）
- **PRIMARY OUTCOME（预注册）**：
  ```
  causal_otc[N] = close_adj[T+N] / open_adj[T+1] - 1     # open→close, N∈{5,10}
  ```
  信号在 T close 后确定 → 从 **T+1 open** 起算收益 → T+N close 结算。
- **SECONDARY OUTCOME**：
  ```
  causal_oto[N] = open_adj[T+1+N] / open_adj[T+1] - 1    # open→open, N∈{5,10}
  ```
  作为对照（不受 T+N 收盘跳空影响）。

### 5.3 T+1 无法交易处理
- 若 T+1 停牌、一字涨停（买不进）等：**单独标记 `NOT_TRADABLE` 分组**（含 stock-days 数与占比），不偷删。
- 主统计保留全部观测（含 NOT_TRADABLE）作为"描述性全部样本"；另报"可交易子样本"（剔除 T+1 无法买入），两者**分别报告**，禁止只保留可成交赢家。

---

## 6. 样本独立性处理（同 v1）

- 主统计：以（日期, 超跌档位）截面均值为观测单位（日级时间序列，解决同日相关）
- 显著性：Newey-West HAC + 按股票 cluster-robust 标准误
- Bootstrap：日级 block / event-cluster / Regime-block 三种全部报告

---

## 7. 样本划分（v2，P1 修正：改名 + 冻结未来）

| 阶段 | 区间 | 用途 | 性质 |
|---|---|---|---|
| **Discovery** | 2020-01-01 ~ 2022-12-31 | 生成 Alpha Matrix，形成假设 | 探索 |
| **Validation** | 2023-01-01 ~ 2024-12-31 | 只验证预注册假设 | 复现检验 |
| **Retrospective Confirmation** | 2025-01-01 ~ 2026-08-25 | 只回答"历史第三阶段是否继续维持" | **不再叫 OOS**（旧策略已观察过） |
| **FUTURE_OOS（真正未看数据）** | **2026-09-01 onward**（或未来累计 6-12 个月新数据 / paper trading） | 最终泛化证明 | pristine OOS |

**硬规则**：
- 2025-2026 参与了旧策略观察 → 只作 Retrospective Confirmation，**不得**用作未来策略的最终泛化证明
- 进入策略开发后，**2020-2026 全部正式成为 development history**；任何参数/Regime 选择只要看过这些数据，其任何部分都不再是 pristine OOS
- 真正策略证据只来自 FUTURE_OOS / paper trading / forward test

---

## 8. Multiple Testing 预注册（v2，P2 修正）

### 8.1 HYPOTHESIS_REGISTRY（强制预注册）
正式运行前生成 `HYPOTHESIS_REGISTRY.csv`（模板见同目录文件），每行一个 `hypothesis_id`，字段：
```
hypothesis_id, family(PRIMARY/SECONDARY), regime_dimension, regime_variable,
regime_definition, threshold, oversold_feature, oversold_threshold,
forward_horizon, outcome_type(otc/oto), benchmark, discovery_test
```
**运行 Discovery 后禁止新增 hypothesis_id 再假装属于原 FDR family。**

### 8.2 PRIMARY FAMILY（预注册，先验证最核心问题）
| 维度 | 变量（固定一种） | 档数 |
|---|---|---|
| 市场趋势 | 全A（成交额加权自建指数），20日收益档 | 3（涨/震荡/跌） |
| 市场宽度 | MA20 above ratio | 3（高/中/低） |
| 市场波动 | 全A 20D realized volatility | 4（低/正常/高/极端） |
| 市场流动性 | 全A 成交额 | 3（地量/正常/天量） |
| 超跌 | **BB_zscore** | 4（-1.5/-2/-2.5/-3） |
| 前瞻 | **5D / 10D**（open→close） | 2 |

**Primary hypothesis 粒度 =（维度 × 维度档位 × 超跌档 × forward）**，单维度检验（不跨维度笛卡尔组合）。
- 趋势 1×3×4×2 = 24
- 宽度 1×3×4×2 = 24
- 波动 1×4×4×2 = 32
- 流动性 1×3×4×2 = 24
**PRIMARY 合计 = 104 个 hypothesis**（详见 §12）。

### 8.3 SECONDARY FAMILY（分开注册、分开报告、单独 FDR）
其他指数（300/500/1000/等权全A）、MA60 distance、RSI、ATR、N日收益/回撤、情绪（涨停/跌停/连板）、更多 forward（1D/3D/20D）、T+1 可交易子样本、NOT_TRADABLE 描述等。
**不得与 Primary 混在一个 FDR family，不得事后把 Secondary 亮点升格为 Primary。**

### 8.4 显著性判定
- 单格：日级截面均值 t 检验（HAC），报告 t、p、mean/median excess、win rate、95% CI
- 多重比较：**PRIMARY 内部 FDR(BH) q=0.05**（主）+ Bonferroni（参考）；SECONDARY 单独 FDR
- 同时要求 Discovery 显著 **且** Validation 复现（方向一致、效应量不塌缩）**且** Confirmation 不反转，才进入候选

---

## 9. Permutation / Null 分布（v2，P3 修正：保持市场结构）

> 主 null 必须保留时间与横截面结构，禁止以完全随机打乱（date, stock）为主 null（它会破坏同日相关/波动聚集/共同冲击，构造过于容易战胜的假零分布）。

| Null | 设计 | 保持的结构 |
|---|---|---|
| **NULL_A（主）** | 日级 block / circular block permutation（按日块整体重排） | 同日横截面结构、波动聚集、Regime 时序 |
| **NULL_B** | 同日内对"超跌标签/股票"做受约束置换 | 当天市场状态与收益横截面 |
| **NULL_C** | Regime 持续段 block permutation | Regime 持续性 |
| 完全随机 permutation | 仅作辅助参考 | — |

最终显著性**必须同时**考虑：HAC + block bootstrap + FDR；不因某一种显著就判成立。

---

## 10. 效应量门槛（v2 修改：不用年化折算）

- 保留 `独立日数 ≥ 150`
- **效应量主口径**（不用 5D/10D 年化折算，避免重叠收益年化夸大）：
  - `mean excess return` / `median excess return` / `win rate` / `95% CI`
  - `effect / transaction cost` 比（成本模型复用 BACKTEST_INVARIANTS R11）
  - 示例：5D 平均超额 +0.8%，成本约 0.15% → effect/cost ≈ 5.3×

---

## 11. 最终研究流程（v2，STEP 0-7）

```
STEP 0   冻结 HYPOTHESIS_REGISTRY（PRIMARY 104 + SECONDARY 预注册）
STEP 1   只看 Discovery 2020-2022 → 生成 Discovery Alpha Matrix
STEP 2   冻结 Discovery 产生的假设（禁止改 Regime定义/阈值/forward/超跌定义）
STEP 3   打开 Validation 2023-2024 → 只验证预注册假设
STEP 4   仅 Discovery+Validation 均成立的假设，才打开 Confirmation 2025-2026
STEP 5   Confirmation 只回答"第三阶段是否继续维持"，不可再调任何规则
STEP 6   三阶段均成立 → 进入策略工程阶段；此时 2020-2026 全部成为 development data
STEP 7   真正策略证据来自 FUTURE_OOS（2026-09-01 onward）/ paper trading / forward test
```

---

## 12. 预计 PRIMARY hypothesis 总数

**104**，构成（单维度 × 档位 × 超跌档 × forward，不跨维度组合）：
- 趋势（1 指数 × 3 档）× 4 超跌 × 2 forward = 24
- 宽度（1 指标 × 3 档）× 4 超跌 × 2 forward = 24
- 波动（1 指标 × 4 档）× 4 超跌 × 2 forward = 32
- 流动性（1 指标 × 3 档）× 4 超跌 × 2 forward = 24

（SECONDARY 数量不预统计，单独注册、单独 FDR。）

---

## 13. 明确不做的（本轮边界，同 v1）
- ❌ 不调 BB 参数 / 不找最佳超跌阈值
- ❌ 不构造可交易策略 / 不做组合回测
- ❌ 不在全样本上直接检验（必须 Discovery → Validation → Confirmation）
- ❌ 不把"某年某格赚钱"当作 Alpha 证据
- ❌ 不以完全随机 permutation 作为主 null
