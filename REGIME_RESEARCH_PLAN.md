# REGIME_RESEARCH_PLAN — 市场状态 × 超跌程度 → 条件收益研究设计（v3，预注册封板版）

> 状态：**设计稿 v3，已预注册封板，未开始执行**。本阶段不调参、不产生交易策略、不输出"最佳策略"。
> 本版完成最后一轮预注册封板：P4 PRIMARY benchmark 唯一冻结、P5 超跌互斥 bins、P6 全部 Regime 公式/阈值/信息集写死。
> **已生成 `HYPOTHESIS_REGISTRY.csv`（104 条 PRIMARY 预注册，含 SHA256 哈希）并 Git commit。**
> 预审通过后正式进入 **REGIME DISCOVERY — Phase 1**（届时只允许看 2020-2022）。

---

## 0. 研究问题（唯一问题）

> 在 A 股市场，当一只股票进入不同程度"超跌状态"后，其未来收益，**在哪些市场 Regime 下显著优于"同超跌程度、不区分 Regime"的基准？**

本阶段只绘制 **REGIME_ALPHA_MATRIX**（条件 Alpha 矩阵），不找"能赚钱的策略"。

---

## 1. 数据需求（同 v2）

- 已有：`combined_daily.parquet`（2020-01-02~2026-08-25, 全A日线, amount=千元）、`pit_st_daily.parquet`、`stock_basic.parquet`、`trade_cal_full.parquet`、`etf_513500_merged.parquet`
- 待补齐：历史退市股日线（❌ NEED_EXTERNAL_DATA）、指数历史（⏳）、情绪指标（⏳, SECONDARY 用）
- 质量门槛：信号/收益用后复权（`close_adj=close×adj_factor`、`open_adj=open×adj_factor`）；交易日对齐 `trade_cal_full`

---

## 2. PIT 要求（强制）

所有"超跌事件"T 日构造只用 T 日及之前可知信息：PIT ST、上市满 60 交易日、退市区间截断、涨跌停制度（PIT ST 派生）、所有 Regime 标签 rolling 右对齐（含 T，无 center 平滑、无事后打标）。

---

## 3. 观测 Universe（冻结）

```
universe[T] = { 股票 s : 当日有效行情
                AND s.list_date 后已满 60 个交易日（trade_cal_full）
                AND s 在 T 日未退市
                AND NOT is_st_pit[T] }
```
- ST 从观测 universe 与 breadth 分母中**一律排除**（口径统一，避免 ST 涨跌停/退市噪声，与旧策略一致）
- 退市区间截断：仅保留上市→退市之间

---

## 4. 全A 市场指数构造（冻结，P6-额外）

```
mkt_ret[T] = mean_{s in universe[T]} ( close_adj[s,T] / close_adj[s,T-1] - 1 )   # 等权截面均值
idx[T]     = ∏_{k<=T} (1 + mkt_ret[k])                                           # 等权净值
```
- **等权**（PIT eligible 且非 ST）；**不用 T 日成交额加权**（避免"用 T 日最终成交额给 T 日收益加权"的 contemporaneous weighting bias）
- 市场成交额**单独**留给 LIQUIDITY Regime，不与趋势指数机械耦合
- 若 `|universe[T]| < 50`，该日不进入任何 Regime 计算，标 `INSUFFICIENT_UNIVERSE`

---

## 5. Forward Return（因果口径，P0 已修，冻结）

- **PRIMARY OUTCOME（预注册）**：`causal_otc[N] = close_adj[T+N] / open_adj[T+1] - 1`，N ∈ {5, 10}
- SECONDARY OUTCOME：`causal_oto[N] = open_adj[T+1+N]/open_adj[T+1]-1`
- DESCRIPTIVE_RETURN `close[T+N]/close[T]-1` 标 `NON_TRADABLE_REFERENCE`，不进显著性检验
- T+1 停牌/一字涨停买不进 → 标 `NOT_TRADABLE` 分组，与可交易子样本分别报告，不偷删

---

## 6. PRIMARY benchmark 唯一冻结（P4 已修）

- **PRIMARY benchmark（唯一）**：`same_oversold_unconditional`
  - 定义：在 Discovery 区间内，**同一 oversold bin、不区分 Regime** 的日级截面平均 `causal_otc[N]`
- **PRIMARY effect（REGIME_EXCESS）**：
  ```
  REGIME_EXCESS = conditional causal_otc[N] − same_oversold_unconditional causal_otc[N]
  ```
  回答"Regime 有没有额外解释力"，而非"市场本身上涨导致的伪 Alpha"。
- 辅助/诊断（**全部 SECONDARY，不得替代主 benchmark**）：`RAW_RETURN`（conditional causal_otc）、`INDEX_EXCESS`（conditional causal_otc − 同期市场指数收益）、`ZERO_TEST`（H0 mean=0）
- **Registry 中 PRIMARY benchmark 字段全部唯一为 `same_oversold_unconditional`**

---

## 7. 超跌特征与互斥 bins（P5 已修）

**PRIMARY OVERSOLD FEATURE**：`BB_zscore = (close_adj − MA20)/std20`
- `MA20 = rolling(20).mean()`、`std20 = rolling(20).std()`，pandas 右对齐、`min_periods=20`、**`ddof=1`**
- **互斥 severity bins（每个事件同日只属于一个 bin）**：

| bin | 范围 |
|---|---|
| B1 | -2.0 < z ≤ -1.5 |
| B2 | -2.5 < z ≤ -2.0 |
| B3 | -3.0 < z ≤ -2.5 |
| B4 | z ≤ -3.0 |

- 累计阈值（z ≤ -1.5 / -2 / -2.5 / -3）**仅保留为 SECONDARY robustness**
- **INSUFFICIENT_SAMPLE 规则（提前规定，运行后不得改动）**：某 Primary cell 独立日 < 150 → 直接标 `INSUFFICIENT_SAMPLE`，**不改阈值、不合并 bins、不优化**

---

## 8. PRIMARY REGIME FAMILY（P6 已修：公式+阈值+信息集全部冻结）

> 每个 Regime 变量公式、阈值、信息集在 Discovery 开跑前**全部写死**；±20% 阈值扰动仅作 robustness SECONDARY，禁止据此反向选阈值。

### A. TREND（3 档）
```
idx = §4 全A等权净值
ret20[T] = idx[T] / idx[T-20] - 1            # 信息集: T日收盘, 含T
UP        : ret20 > +0.03
SIDEWAYS  : -0.03 <= ret20 <= +0.03
DOWN      : ret20 < -0.03
```

### B. BREADTH（3 档）
```
denom[T] = |universe[T]|
n_above[T] = count_{s in universe[T]} ( close_adj[s,T] > MA20(close_adj[s])[T] )
ma20_above_ratio[T] = n_above[T] / denom[T]   # ST 排除, 与 universe 口径一致
LOW  : ratio < 0.30
MID  : 0.30 <= ratio <= 0.70
HIGH : ratio > 0.70
```

### C. VOLATILITY（4 档，PIT percentile）
```
rv20[T] = std( mkt_ret[T-19..T] ) * sqrt(245)   # 全A市场日收益20日波动
pctile[T] = mean( rv20[T-252 .. T-1] < rv20[T] ) # 经验分位, trailing 252 固定
min_periods: T-252..T-1 内有效 rv20 观测 >= 100, 否则 Regime = WARMUP (不进 Primary)
LOW     : pctile <= 0.20
NORMAL  : 0.20 < pctile <= 0.60
HIGH    : 0.60 < pctile <= 0.90
EXTREME : pctile > 0.90
```
（PIT：只用 T 日之前已发生的 rv20 历史；**禁止**用 2020-2026 全样本分位回头给 2020 打标签）

### D. LIQUIDITY（3 档）
```
market_amount[T] = sum_{s in universe[T]} amount[s,T]        # 千元
amt_ratio[T] = market_amount[T] / MA20(market_amount)[T]      # 与自身20日均量比, 消除市场规模趋势
LOW    : amt_ratio < 0.80
NORMAL : 0.80 <= amt_ratio <= 1.20
HIGH   : amt_ratio > 1.20
```

---

## 9. HYPOTHESIS_REGISTRY（P2 已修 + 本轮封板）

- 正式文件：`HYPOTHESIS_REGISTRY.csv`（**104 行 PRIMARY**，已生成；模板 `HYPOTHESIS_REGISTRY_TEMPLATE.csv`）
- 字段（全部唯一确定，无 `/`、任选、候选、x待定）：
  `hypothesis_id, family, regime_dimension, regime_variable, regime_formula, regime_bin, oversold_feature, oversold_bin, oversold_range, forward_horizon, outcome_type, benchmark, test, fdr_family`
- **104 构成**：TREND 3×4×2=24 + BREADTH 3×4×2=24 + VOLATILITY 4×4×2=32 + LIQUIDITY 3×4×2=24
- **Registry SHA256**：见提交记录（用于证明 Discovery 结果出来后 Registry 未被偷改）
- **SECONDARY FAMILY**：其他指数/RSI/ATR/MA60/情绪/更多 horizon/累计 oversold 等，**单独注册、单独 FDR**，不得与 Primary 混用

---

## 10. 显著性检验与 Null（P3 已修，冻结）

- 单格：日级截面均值 t 检验（Newey-West HAC）+ cluster-robust（按股票）
- 多重比较：PRIMARY 内部 FDR(BH) q=0.05 主 + Bonferroni 参考；SECONDARY 单独 FDR
- Null（保持市场结构，**完全随机打乱 (date,stock) 仅作辅助**）：
  - NULL_A（主）：日级 block / circular block permutation
  - NULL_B：同日内受约束置换（保持当天横截面）
  - NULL_C：Regime 持续段 block permutation
- **必须同时**考虑 HAC + block bootstrap + FDR，不因某一种显著判成立

---

## 11. 效应量门槛（冻结）

- 独立日 ≥ 150（不足标 INSUFFICIENT_SAMPLE）
- 主口径：mean/median excess、win rate、95% CI、`effect/transaction_cost` 比（成本模型复用 BACKTEST_INVARIANTS R11）；**不用年化折算**

---

## 12. 样本划分（P1 已修，冻结）

| 阶段 | 区间 | 性质 |
|---|---|---|
| Discovery | 2020-01-01 ~ 2022-12-31 | 探索 |
| Validation | 2023-01-01 ~ 2024-12-31 | 复现检验（只验证预注册假设） |
| Retrospective Confirmation | 2025-01-01 ~ 2026-08-25 | 只回答"是否维持"，不可调规则 |
| FUTURE_OOS | 2026-09-01 onward / paper trading | pristine OOS（真正泛化证明） |

进入策略开发后 2020-2026 全部成为 development history。

---

## 13. 研究流程（冻结）

```
STEP 0   Registry 封板（104 行 PRIMARY + SHA256 + commit）   ← 本轮已完成
STEP 1   只看 Discovery 2020-2022 → Discovery Alpha Matrix
STEP 2   冻结 Discovery 假设（禁止改任何定义/阈值）
STEP 3   打开 Validation，只验证预注册假设
STEP 4   仅 D+V 均成立者打开 Retrospective Confirmation
STEP 5   Confirmation 只回答是否维持
STEP 6   三阶段成立 → 策略工程（2020-2026 成 development）
STEP 7   真正证据来自 FUTURE_OOS / paper trading / forward test
```

---

## 14. 明确不做（边界）
- ❌ 不调参/不找最佳阈值/不构造策略/不做组合回测
- ❌ 不在全样本直接检验（必须 Discovery→Validation→Confirmation）
- ❌ 不以完全随机 permutation 为主 null
- ❌ 不因某 cell 样本不足事后合并 bins / 改阈值
