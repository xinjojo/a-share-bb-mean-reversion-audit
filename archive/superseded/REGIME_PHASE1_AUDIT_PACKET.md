# REGIME_PHASE1_AUDIT_PACKET — corrected Phase 1 审计包（FACTS ONLY）

> 本文件仅汇编 corrected Phase 1 的**可验证事实**（公式 / 日期 / 观测单元 / 估计器 / 统计实现 / 状态表 / 代码映射）。
> 不新增解释性结论，不修改任何结果。Registry 未修改（SHA256 见 §13）。
> 状态：**UNDER AUDIT / NOT YET ACCEPTED**；Validation(2023-24) 未打开。

---

## 0. 审计包清单（11 项）

| # | 项 | 文件 | commit |
|---|---|---|---|
| 1 | 主实现 | `regime_discovery_corrected.py` | fa58758 |
| 2 | 独立交叉验证 | `cross_check_phase1.py` | fa58758 |
| 3 | 104 格矩阵 | `results/regime_discovery_matrix_v2.csv` | fa58758 |
| 4 | 修正版报告 | `REGIME_DISCOVERY_PHASE1_CORRECTED.md` | fa58758 |
| 5 | 研究设计 | `REGIME_RESEARCH_PLAN.md`（v3） | 11e2ab2 |
| 6 | 预注册 | `HYPOTHESIS_REGISTRY.csv`（104 行 PRIMARY） | 11e2ab2 |
| 7 | Registry SHA256 | `5c5e451ad4eb3afd5e632b0019a3e02103e58e375e03cc231c5d8ca52b8c5195` | 11e2ab2 |
| 8 | NULL_A / NULL_B / NULL_C | `regime_discovery_corrected.py` L289-327 | fa58758 |
| 9 | HAC | `regime_discovery_corrected.py` `nw_se()` L173-181 | fa58758 |
| 10 | block bootstrap | `regime_discovery_corrected.py` `block_resample_idx()` L183-193 + L273-287 | fa58758 |
| 11 | benchmark contrast | `regime_discovery_corrected.py` L256-271（regression contrast） | fa58758 |

---

## 1. Exact Formulas（`regime_discovery_corrected.py` L49-55, L105-133）

- `close_adj = close × adj_factor`（后复权）；`open_adj = open × adj_factor`。
- `ret = pct_change(close_adj)`（按 ts_code）。
- `ma20 = rolling(20, min_periods=20).mean(close_adj)`；`std20 = rolling(20, min_periods=20).std(close_adj, ddof=1)`。
- `bb_z = (close_adj − ma20) / std20`。
- **oversold 互斥 bins**（`np.select`，L109-112）：
  - B1: `−2.0 < z ≤ −1.5`；B2: `−2.5 < z ≤ −2.0`；B3: `−3.0 < z ≤ −2.5`；B4: `z ≤ −3.0`。
- **因果 outcome**（L117-130）：`otc5 = close_adj[T5] / open_adj[T1] − 1`；`otc10 = close_adj[T10] / open_adj[T1] − 1`。T1 = 下一交易日 open；T5/T10 = 其后第 5/10 交易日。
- **Regime（每日，L72-103，NaN→WARMUP）**：
  - TREND：`idx20 = idx/idx.shift(20) − 1`；UP `>+0.03`；DOWN `<−0.03`；SIDEWAYS 其余；`idx`=全A等权净值（§4 指数）。
  - BREADTH：`ratio = n_above / denom`（denom=当日 PIT eligible 非 ST 股票数；n_above=ma20 非空且 close_adj>ma20 数），`clip≤1.0`；LOW `<0.30`；HIGH `>0.70`；MID 其余。
  - VOLATILITY：`rv20 = rolling(20).std(mkt_ret) × sqrt(245)`；`pctile = mean(rv20[T−252..T−1] < rv20[T])`（min_periods=100 历史值，否则 WARMUP）；LOW `≤0.20`；NORMAL `≤0.60`；HIGH `≤0.90`；EXTREME `>0.90`。
  - LIQUIDITY：`market_amount = Σ(amount, PIT eligible 非 ST, 千元)`；`amt_ratio = market_amount / MA20(market_amount)`（min_periods=20）；LOW `<0.80`；HIGH `>1.20`；NORMAL 其余。
- **PIT universe（L57-64）**：`eligible = (date ≥ elig_date) & (~is_st_pit) & close_adj.notna()`；`elig_date` = `trade_dates[bisect_left(list_date) + 59]`（上市后第 60 个交易日）。

## 2. Exact Sample Dates

- 加载数据：**2018-01-02 ~ 2023-02-28**（`warmup_daily_2018_2019.parquet` 2018-01-02~2019-12-31 ＋ `combined_daily.parquet` 截断至 2023-02-28，L30-40）。
- **Discovery outcome 严格限定 2020-01-01 ~ 2022-12-31**（`DISC0/DISC1`，L18，事件提取 L107）。
- warmup 年份不进 Discovery。

## 3. Warmup Dates

- `data/warmup_daily_2018_2019.parquet`：**2018-01-02 ~ 2019-12-31**，1,718,712 行，含 214 只退市股历史（供 BB MA20/Std20、Trend ret20、Liquidity MA20、RV20、Vol trailing 252 日 percentile 初始化）。
- 2020 年 4 维 regime WARMUP 天数（修正后，见 corrected 报告 §一）：trend=0、breadth=0、vol=0、liq=0；被 WARMUP 排除的 Primary 事件数 = 0。

## 4. Exact Observation Unit

- **事件（stock-day）**：Discovery 期内 `eligible & bb_z.notna()` 且落入某 oversold bin 的股票-日。
- **统计单元（event-day）**：每个事件日 `t` 的日级截面均值 `y_t = mean(otc over 当日事件股票)`（L146-161）；`n_event_days` = 该 cell 内事件日数；`n_stock_events` = 该 cell 内股票事件数。
- **门槛（冻结）**：`n_event_days < 150` 或 `n_stock_events == 0` → `INSUFFICIENT_SAMPLE`（L252-254）。

## 5. Exact Benchmark Estimator（L256-271）

- **PRIMARY benchmark 唯一冻结**：`same_oversold_unconditional`（Registry 全 104 行该字段唯一）。
- `bm = mean(y_ev)`：同 (oversold_bin, horizon) 全部事件日（不区 regime）的日截面均值再平均（原样本）。
- `excess_obs = mean_r − bm`（L260）。
- **回归对比**：在事件日集合上回归 `y_t = α + β·D_t + e_t`（D = in-cell 指示，L268）；因 `bm` 含 in-cell 日，数学等价 `excess_obs = ((n_all − n_r)/n_all)·β`（n_all=事件日总数，n_r=cell 内事件日数）。
- `hac_effect = β`，`hac_se = SE(β)`（HAC），`hac_t = β/SE`，`raw_p = 2·t.sf(|t|, n_all − 2)`（L269-271）。

## 6. Exact HAC Lag Rule（`nw_se` L173-181）

- 带宽 `K = ⌊4·(n/100)^(2/9)⌋`，clip 至 `[0, n−2]`（n = 事件日数）。
- 实现：`statsmodels OLS(y~const+D).fit(cov_type='HAC', cov_kwds={'maxlags': K})`，取 `bse[1]`。
- 实际 `nw_lag` 值已写入矩阵每格。

## 7. Exact Block Bootstrap Scheme（L183-199, L273-287）

- **circular block bootstrap**，完整交易日历上，块长 `L=21`（固定），`B=2000`（固定）。
- 索引预生成：`block_resample_idx(N_CAL, 21, 2000, rng(seed=2020))`——每块从日历随机起点取 L 天（模 N 循环），B×N 矩阵共享（L183-199）。
- **每次 resample 重新计算**：`bmb = mean(yb | 事件日)`（benchmark 重估）→ `cellb = 事件日 & regime` → `exc_boot = mean(yb | cellb) − bmb`（L273-284）。
- `ci_lo/ci_hi` = 2.5/97.5 百分位；`boot_p = mean(exc_boot ≤ 0)`（L286-287）。
- 未按结果调整块长/次数。

## 8. Exact Permutation Schemes（L288-327）

- **NULL_A（circular shift，5000 次，L289-298）**：对事件日集合上的 D（in-cell 指示）相对 outcome 序列做循环移位 `D_s = np.roll(D, k)`（k ∈ [1, n_all−1]），`permA = mean(y_ev | D_s) − bm`；`nullA_p = mean(|permA| ≥ |excess_obs|)`（双侧）。打破 regime↔outcome 关联、保留 outcome 自身时间依赖。
- **NULL_B（within-date 股票置换，secondary structure check，L310-327）**：事件值按股票列 pivot 后逐列 shuffle（20 次），重算日截面均值。因 regime 为市场-wide 同日标签，日截面均值在股票内置换下不变 → `nullB_note = STRUCTURAL_INVARIANT`（`np.allclose` 于 excess_obs，atol=1e-12）；`nullB_p` 为结构恒等诊断，非 regime 主 null。
- **NULL_C（regime-segment block permutation，5000 次，L201-225, L299-309）**：对每个 dim，按 regime label 连续 run（segment）切分，随机重排 segment 顺序（保持 segment 长度与 Regime 持续性），重建 regime 序列 → `cellc = 事件日 & new_regime`，`permC = mean(y | cellc) − bm`；`nullC_p = mean(|permC| ≥ |excess_obs|)`。
- 次数全部固定（NPERM=5000，NULL_B 内部 20），未看结果调整。

## 9. Exact BH-FDR Implementation（L341-359）

- 仅对 **VALID_SAMPLE 的 raw_p**（m=60）应用。
- 自身实现：`sort p ascending` → `q_sorted = p·m/rank` → **从右往左 cumulative-min**（`np.minimum.accumulate(q_sorted[::-1])[::-1]`）→ `clip[0,1]` → inverse-map 回原 hypothesis。
- **独立交叉验证**：`statsmodels.stats.multitest.multipletests(p, alpha=0.05, method='fdr_bh')`，断言 `max_abs(q_own − q_statsmodels) < 1e-10`（实际 = 1.11e-16）。
- 矩阵 `bh_q` 取 statsmodels 结果。

## 10. Missing / Suspension / Delist Handling

- **T+1 停牌/不可交易**：`non_tradable_t1 = open_adj_T1.isna()`（L126）——标记并单独统计 `n_non_tradable_t1`（L251）；otc 因 open_adj_T1 NaN 为 NaN，不进均值（不偷偷删除只留赢家，缺失作为标记保留）。
- **T+5/T+10 缺失**：`miss5/miss10 = close_adj_T5/T10.isna()`（L129-130）——otc NaN 不进均值。
- **退市**：数据含退市股历史（warmup 214 只；combined 侧 339 只含 delist_date）；退市后无行情自然无事件。PIT 用 `list_date`（上市满 60 交易日）+ `is_st_pit`。
- **ST**：`is_st_pit` 排除出 universe/breadth 分母/事件（L41, L64）。
- **上市不足 60 交易日**：`date < elig_date` → 排除。
- **北交所**：无北交所涨跌幅特殊规则（本阶段仅统计研究，不涉交易执行）。

## 11. 104 Hypotheses Status Table（完整，结果直接来自矩阵 CSV）

### TREND（24 格）
| id | regime | oversold | hz | status | n_event_days | n_stock_events | excess | raw_p | bh_q |
|---|---|---|---|---|---|---|---|---|---|
| P0018 | DOWN | B1 | 10D | VALID_SAMPLE | 179 | 109822 | +0.584% | 0.4080 | 0.6278 |
| P0017 | DOWN | B1 | 5D | VALID_SAMPLE | 179 | 109883 | +0.474% | 0.3027 | 0.5193 |
| P0020 | DOWN | B2 | 10D | VALID_SAMPLE | 176 | 50338 | +0.752% | 0.2930 | 0.5193 |
| P0019 | DOWN | B2 | 5D | VALID_SAMPLE | 176 | 50350 | +0.758% | 0.1211 | 0.2964 |
| P0022 | DOWN | B3 | 10D | VALID_SAMPLE | 157 | 16164 | +0.755% | 0.3414 | 0.5536 |
| P0021 | DOWN | B3 | 5D | VALID_SAMPLE | 157 | 16161 | +0.591% | 0.2837 | 0.5193 |
| P0024 | DOWN | B4 | 10D | INSUFFICIENT_SAMPLE | 116 | 5685 | — | — | — |
| P0023 | DOWN | B4 | 5D | INSUFFICIENT_SAMPLE | 116 | 5685 | — | — | — |
| P0010 | SIDEWAYS | B1 | 10D | VALID_SAMPLE | 279 | 95506 | −0.089% | 0.8227 | 0.8815 |
| P0009 | SIDEWAYS | B1 | 5D | VALID_SAMPLE | 279 | 95562 | −0.062% | 0.8083 | 0.8815 |
| P0012 | SIDEWAYS | B2 | 10D | VALID_SAMPLE | 275 | 39072 | −0.150% | 0.7109 | 0.8705 |
| P0011 | SIDEWAYS | B2 | 5D | VALID_SAMPLE | 275 | 39081 | −0.071% | 0.7982 | 0.8815 |
| P0014 | SIDEWAYS | B3 | 10D | VALID_SAMPLE | 260 | 10641 | −0.271% | 0.5699 | 0.7599 |
| P0013 | SIDEWAYS | B3 | 5D | VALID_SAMPLE | 260 | 10640 | −0.001% | 0.9972 | 0.9972 |
| P0016 | SIDEWAYS | B4 | 10D | VALID_SAMPLE | 202 | 2113 | −0.765% | 0.2438 | 0.5193 |
| P0015 | SIDEWAYS | B4 | 5D | VALID_SAMPLE | 202 | 2110 | −0.374% | 0.3924 | 0.6196 |
| P0002 | UP | B1 | 10D | VALID_SAMPLE | 269 | 41190 | −0.296% | 0.5519 | 0.7525 |
| P0001 | UP | B1 | 5D | VALID_SAMPLE | 269 | 41199 | −0.251% | 0.4401 | 0.6287 |
| P0004 | UP | B2 | 10D | VALID_SAMPLE | 262 | 11898 | −0.347% | 0.5107 | 0.7126 |
| P0003 | UP | B2 | 5D | VALID_SAMPLE | 262 | 11905 | −0.434% | 0.2279 | 0.5065 |
| P0006 | UP | B3 | 10D | VALID_SAMPLE | 228 | 2368 | −0.210% | 0.7451 | 0.8815 |
| P0005 | UP | B3 | 5D | VALID_SAMPLE | 228 | 2366 | −0.406% | 0.3211 | 0.5351 |
| P0008 | UP | B4 | 10D | INSUFFICIENT_SAMPLE | 128 | 410 | — | — | — |
| P0007 | UP | B4 | 5D | INSUFFICIENT_SAMPLE | 128 | 410 | — | — | — |

### BREADTH（24 格）
| id | regime | oversold | hz | status | n_event_days | n_stock_events | excess | raw_p | bh_q |
|---|---|---|---|---|---|---|---|---|---|
| P0042 | HIGH | B1 | 10D | INSUFFICIENT_SAMPLE | 107 | 4806 | — | — | — |
| P0041 | HIGH | B1 | 5D | INSUFFICIENT_SAMPLE | 107 | 4811 | — | — | — |
| P0044 | HIGH | B2 | 10D | INSUFFICIENT_SAMPLE | 100 | 1108 | — | — | — |
| P0043 | HIGH | B2 | 5D | INSUFFICIENT_SAMPLE | 100 | 1108 | — | — | — |
| P0046 | HIGH | B3 | 10D | INSUFFICIENT_SAMPLE | 70 | 221 | — | — | — |
| P0045 | HIGH | B3 | 5D | INSUFFICIENT_SAMPLE | 70 | 221 | — | — | — |
| P0048 | HIGH | B4 | 10D | INSUFFICIENT_SAMPLE | 30 | 43 | — | — | — |
| P0047 | HIGH | B4 | 5D | INSUFFICIENT_SAMPLE | 30 | 43 | — | — | — |
| P0026 | LOW | B1 | 10D | VALID_SAMPLE | 172 | 132071 | +1.508% | 0.0295 | 0.1558 |
| P0025 | LOW | B1 | 5D | VALID_SAMPLE | 172 | 132157 | +1.018% | 0.0363 | 0.1558 |
| P0028 | LOW | B2 | 10D | VALID_SAMPLE | 169 | 63785 | +1.821% | 0.0081 | 0.0606 |
| P0027 | LOW | B2 | 5D | VALID_SAMPLE | 169 | 63799 | +1.368% | 0.0068 | 0.0581 |
| P0030 | LOW | B3 | 10D | VALID_SAMPLE | 163 | 20339 | +1.319% | 0.0929 | 0.2678 |
| P0029 | LOW | B3 | 5D | VALID_SAMPLE | 163 | 20334 | +0.850% | 0.1225 | 0.2964 |
| P0032 | LOW | B4 | 10D | INSUFFICIENT_SAMPLE | 131 | 6527 | — | — | — |
| P0031 | LOW | B4 | 5D | INSUFFICIENT_SAMPLE | 131 | 6527 | — | — | — |
| P0034 | MID | B1 | 10D | VALID_SAMPLE | 448 | 109641 | −0.447% | 0.1073 | 0.2928 |
| P0033 | MID | B1 | 5D | VALID_SAMPLE | 448 | 109676 | −0.351% | 0.0721 | 0.2421 |
| P0036 | MID | B2 | 10D | VALID_SAMPLE | 444 | 36415 | −0.612% | 0.0350 | 0.1558 |
| P0035 | MID | B2 | 5D | VALID_SAMPLE | 444 | 36429 | −0.450% | 0.0334 | 0.1558 |
| P0038 | MID | B3 | 10D | VALID_SAMPLE | 412 | 8613 | −0.550% | 0.0937 | 0.2678 |
| P0037 | MID | B3 | 5D | VALID_SAMPLE | 412 | 8612 | −0.413% | 0.0726 | 0.2421 |
| P0040 | MID | B4 | 10D | VALID_SAMPLE | 285 | 1638 | −0.577% | 0.2025 | 0.4674 |
| P0039 | MID | B4 | 5D | VALID_SAMPLE | 285 | 1635 | −0.524% | 0.0914 | 0.2678 |

### VOLATILITY（32 格）
| id | regime | oversold | hz | status | n_event_days | n_stock_events | excess | raw_p | bh_q |
|---|---|---|---|---|---|---|---|---|---|
| P0074 | EXTREME | B1 | 10D | INSUFFICIENT_SAMPLE | 87 | 31766 | — | — | — |
| P0073 | EXTREME | B1 | 5D | INSUFFICIENT_SAMPLE | 87 | 31771 | — | — | — |
| P0076 | EXTREME | B2 | 10D | INSUFFICIENT_SAMPLE | 80 | 17441 | — | — | — |
| P0075 | EXTREME | B2 | 5D | INSUFFICIENT_SAMPLE | 80 | 17441 | — | — | — |
| P0078 | EXTREME | B3 | 10D | INSUFFICIENT_SAMPLE | 59 | 7518 | — | — | — |
| P0077 | EXTREME | B3 | 5D | INSUFFICIENT_SAMPLE | 59 | 7512 | — | — | — |
| P0080 | EXTREME | B4 | 10D | INSUFFICIENT_SAMPLE | 33 | 3931 | — | — | — |
| P0079 | EXTREME | B4 | 5D | INSUFFICIENT_SAMPLE | 33 | 3931 | — | — | — |
| P0066 | HIGH | B1 | 10D | VALID_SAMPLE | 204 | 73954 | −0.238% | 0.6658 | 0.8684 |
| P0065 | HIGH | B1 | 5D | VALID_SAMPLE | 204 | 74016 | −0.642% | 0.1235 | 0.2964 |
| P0068 | HIGH | B2 | 10D | VALID_SAMPLE | 198 | 27436 | −0.713% | 0.2618 | 0.5193 |
| P0067 | HIGH | B2 | 5D | VALID_SAMPLE | 198 | 27446 | −0.906% | 0.0480 | 0.1921 |
| P0070 | HIGH | B3 | 10D | VALID_SAMPLE | 177 | 7388 | −0.707% | 0.2695 | 0.5193 |
| P0069 | HIGH | B3 | 5D | VALID_SAMPLE | 177 | 7389 | −0.927% | 0.0618 | 0.2316 |
| P0072 | HIGH | B4 | 10D | INSUFFICIENT_SAMPLE | 109 | 1517 | — | — | — |
| P0071 | HIGH | B4 | 5D | INSUFFICIENT_SAMPLE | 109 | 1519 | — | — | — |
| P0050 | LOW | B1 | 10D | VALID_SAMPLE | 156 | 52784 | +0.572% | 0.4334 | 0.6287 |
| P0049 | LOW | B1 | 5D | VALID_SAMPLE | 156 | 52804 | +0.112% | 0.8223 | 0.8815 |
| P0052 | LOW | B2 | 10D | VALID_SAMPLE | 156 | 21236 | +0.575% | 0.4288 | 0.6287 |
| P0051 | LOW | B2 | 5D | VALID_SAMPLE | 156 | 21248 | +0.021% | 0.9679 | 0.9843 |
| P0054 | LOW | B3 | 10D | INSUFFICIENT_SAMPLE | 149 | 4714 | — | — | — |
| P0053 | LOW | B3 | 5D | INSUFFICIENT_SAMPLE | 149 | 4710 | — | — | — |
| P0056 | LOW | B4 | 10D | INSUFFICIENT_SAMPLE | 119 | 913 | — | — | — |
| P0055 | LOW | B4 | 5D | INSUFFICIENT_SAMPLE | 119 | 909 | — | — | — |
| P0058 | NORMAL | B1 | 10D | VALID_SAMPLE | 280 | 88014 | −0.442% | 0.2997 | 0.5193 |
| P0057 | NORMAL | B1 | 5D | VALID_SAMPLE | 280 | 88053 | −0.068% | 0.7991 | 0.8815 |
| P0060 | NORMAL | B2 | 10D | VALID_SAMPLE | 279 | 35195 | −0.030% | 0.9476 | 0.9803 |
| P0059 | NORMAL | B2 | 5D | VALID_SAMPLE | 279 | 35201 | +0.113% | 0.6918 | 0.8705 |
| P0062 | NORMAL | B3 | 10D | VALID_SAMPLE | 260 | 9553 | +0.197% | 0.6974 | 0.8705 |
| P0061 | NORMAL | B3 | 5D | VALID_SAMPLE | 260 | 9556 | +0.339% | 0.3029 | 0.5193 |
| P0064 | NORMAL | B4 | 10D | VALID_SAMPLE | 185 | 1847 | −0.141% | 0.8607 | 0.9060 |
| P0063 | NORMAL | B4 | 5D | VALID_SAMPLE | 185 | 1846 | +0.126% | 0.8122 | 0.8815 |

### LIQUIDITY（24 格）
| id | regime | oversold | hz | status | n_event_days | n_stock_events | excess | raw_p | bh_q |
|---|---|---|---|---|---|---|---|---|---|
| P0098 | HIGH | B1 | 10D | INSUFFICIENT_SAMPLE | 72 | 18079 | — | — | — |
| P0097 | HIGH | B1 | 5D | INSUFFICIENT_SAMPLE | 72 | 18079 | — | — | — |
| P0100 | HIGH | B2 | 10D | INSUFFICIENT_SAMPLE | 67 | 9057 | — | — | — |
| P0099 | HIGH | B2 | 5D | INSUFFICIENT_SAMPLE | 67 | 9057 | — | — | — |
| P0102 | HIGH | B3 | 10D | INSUFFICIENT_SAMPLE | 55 | 3479 | — | — | — |
| P0101 | HIGH | B3 | 5D | INSUFFICIENT_SAMPLE | 55 | 3481 | — | — | — |
| P0104 | HIGH | B4 | 10D | INSUFFICIENT_SAMPLE | 40 | 987 | — | — | — |
| P0103 | HIGH | B4 | 5D | INSUFFICIENT_SAMPLE | 40 | 988 | — | — | — |
| P0082 | LOW | B1 | 10D | INSUFFICIENT_SAMPLE | 70 | 47586 | — | — | — |
| P0081 | LOW | B1 | 5D | INSUFFICIENT_SAMPLE | 70 | 47607 | — | — | — |
| P0084 | LOW | B2 | 10D | INSUFFICIENT_SAMPLE | 70 | 18240 | — | — | — |
| P0083 | LOW | B2 | 5D | INSUFFICIENT_SAMPLE | 70 | 18245 | — | — | — |
| P0086 | LOW | B3 | 10D | INSUFFICIENT_SAMPLE | 66 | 3295 | — | — | — |
| P0085 | LOW | B3 | 5D | INSUFFICIENT_SAMPLE | 66 | 3294 | — | — | — |
| P0088 | LOW | B4 | 10D | INSUFFICIENT_SAMPLE | 46 | 2248 | — | — | — |
| P0087 | LOW | B4 | 5D | INSUFFICIENT_SAMPLE | 46 | 2248 | — | — | — |
| P0090 | NORMAL | B1 | 10D | VALID_SAMPLE | 585 | 180853 | −0.400% | 0.0194 | 0.1166 |
| P0089 | NORMAL | B1 | 5D | VALID_SAMPLE | 585 | 180958 | −0.306% | 0.0061 | 0.0581 |
| P0092 | NORMAL | B2 | 10D | VALID_SAMPLE | 576 | 74011 | −0.442% | 0.0132 | 0.0878 |
| P0091 | NORMAL | B2 | 5D | VALID_SAMPLE | 576 | 74034 | −0.344% | 0.0061 | 0.0581 |
| P0094 | NORMAL | B3 | 10D | VALID_SAMPLE | 524 | 22399 | −0.576% | 0.0008 | 0.0400 |
| P0093 | NORMAL | B3 | 5D | VALID_SAMPLE | 524 | 22392 | −0.345% | 0.0061 | 0.0581 |
| P0096 | NORMAL | B4 | 10D | VALID_SAMPLE | 360 | 4973 | −0.721% | 0.0020 | 0.0400 |
| P0095 | NORMAL | B4 | 5D | VALID_SAMPLE | 360 | 4969 | −0.552% | 0.0018 | 0.0400 |

### 汇总计数（104 格，事实）
- VALID_SAMPLE = **60**；INSUFFICIENT_SAMPLE = **44**。
- FDR_SIGNIFICANT（bh_q < 0.05）= **3**，全部为负方向：P0094（LIQUIDITY NORMAL B3 10D, excess −0.576%）、P0095（B4 5D, −0.552%）、P0096（B4 10D, −0.721%）。
- 非显著方向：positive_non_significant = 20；negative = 40。
- min raw_p = 0.0008；min bh_q = 0.0400。
- NULL_A_p<0.05 数 = 16；NULL_C_p<0.05 数 = 11；boot_p<0.05 数 = 4。
- HAC+FDR+bootstrap+NULL_A+NULL_C 同时支持 = **0**。
- BREADTH LOW 全 8 格：P0025-P0030 VALID（全部正 excess +0.85%~+1.82%），P0031/P0032 B4 INSUFFICIENT（131<150）。
- 旧 P0027 修正后：excess +1.368%（同方向更强），raw_p 0.0068，bh_q 0.0581（未过 FDR）。

## 12. Code / File / Function Mapping

| 功能 | 文件 | 行/函数 |
|---|---|---|
| 数据加载（warmup+combined+PIT ST） | `regime_discovery_corrected.py` | L30-45 |
| 特征（adj/ret/ma20/std20/bb_z） | 同 | L49-55 |
| PIT universe（list_date+60交易日/ST/退市） | 同 | L57-64 |
| 全A等权指数 | 同 | L66-70 |
| Regime 4 维（NaN→WARMUP） | 同 | L72-103 |
| oversold 事件与因果 outcome | 同 | L105-133 |
| WARMUP 审计 | 同 | L135-144 |
| 日级截面聚合 day_series | 同 | L146-161 |
| HAC（`nw_se`） | 同 | L173-181 |
| circular block bootstrap 索引 | 同 | L183-199 |
| NULL_C segment 构建 | 同 | L201-225 |
| 104 cells 计算（含 NULL_A/B/C、bootstrap、benchmark contrast） | 同 | L227-338 |
| BH FDR（own + statsmodels 交叉验证） | 同 | L341-359 |
| 汇总/输出矩阵 | 同 | L361-381 |
| 独立交叉验证（dict 累加 + statsmodels HAC，5 VALID cells seed=42） | `cross_check_phase1.py` | `indep_cell` L95-132；PASS 判定 L134-154 |
| 104 格矩阵 | `results/regime_discovery_matrix_v2.csv` | — |
| 修正版报告 | `REGIME_DISCOVERY_PHASE1_CORRECTED.md` | — |
| 研究设计 v3 | `REGIME_RESEARCH_PLAN.md` | — |
| 预注册 104 条 | `HYPOTHESIS_REGISTRY.csv` | — |

**交叉验证结果**（`cross_check_phase1.py`，seed=42，5 随机 VALID cells：P0001/P0006/P0051/P0064/P0016）：event dates / conditional mean / benchmark / excess / HAC t / raw p 与矩阵完全一致 → `CROSS-CHECK: PASS`。BH：own vs statsmodels `max_abs diff = 1.11e-16`。

## 13. Registry 信息（事实）

- `HYPOTHESIS_REGISTRY.csv`：104 行 PRIMARY，`family=PRIMARY` 全部；`benchmark` 字段全 104 行唯一 = `same_oversold_unconditional`；`test` 全 104 行 = `t_HAC+FDR(BH)_q005+block_bootstrap`；`fdr_family=PRIMARY`。
- 维度构成：TREND 24（3 bins×4 oversold×2 hz）＋ BREADTH 24 ＋ LIQUIDITY 24 ＋ VOLATILITY 32（4 bins）＝ **104**。
- **Registry SHA256 = `5c5e451ad4eb3afd5e632b0019a3e02103e58e375e03cc231c5d8ca52b8c5195`**（commit `11e2ab2`）；`regime_discovery_corrected.py` 启动时断言 hash 与 104 行（L23-28），hash 不符即拒绝运行。

## 14. 状态与边界（事实）

- `REGIME DISCOVERY PHASE 1 (corrected)`：**UNDER AUDIT / NOT YET ACCEPTED**（首版 `regime_discovery.py` 已 superseded）。
- Validation（2023-2024）**NOT OPENED**；Confirmation（2025-2026）**NOT OPENED**；2026-09 后真 OOS 无数据。
- 本审计包不含任何策略设计或参数建议；未修改 Registry / thresholds / bins / horizon。
