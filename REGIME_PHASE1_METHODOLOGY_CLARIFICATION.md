# REGIME_PHASE1_METHODOLOGY_CLARIFICATION — Discovery Inference 方法澄清（FACTS）

> 本文记录 corrected Phase 1（v2）→ v3 的 inference 方法定义，回应外部审计 P1-1~P1-4、HAC lag 与 FDR m 处理。
> 仅作方法与实现事实澄清；不修改 Registry（SHA256 见 §8）、阈值、bins、benchmark、horizons；不打开 Validation。

---

## 1. Inference Calendar（P1-2，已实现）

**三层日历严格分离：**

| 层 | 日期范围 | 用途 |
|---|---|---|
| FEATURE_CALENDAR | 2018-01-02 ~ 2023-02-28 | 计算 PIT 特征：BB MA20/Std20、Trend ret20、Liquidity MA20、RV20、Vol trailing 252 日 percentile |
| OUTCOME_LOOKAHEAD | 2020-01-02 ~ 2023-01-中旬 | 读取事件 T 的 `open_adj[T+1]`、`close_adj[T+5/T+10]`（未来价格仅作 outcome，不入 resampling） |
| **INFERENCE_CALENDAR** | **2020-01-02 ~ 2022-12-30（728 个交易日）** | **所有 bootstrap block indices、NULL_A、NULL_C、事件 mask** 的日历结构 |

- Discovery outcome 事件严格限定 `DISC0=2020-01-01 ~ DISC1=2022-12-31`。
- 2018-2019 warmup 年份与 2023-01~02 **不进入** Discovery inference 的 resampling 日历结构。
- v2 曾用 `N_CAL = len(all_days)`（2018~2023-02）作为 bootstrap/NULL_C 日历长度 → 已修正为 `N_INF=728`。

## 2. NULL_A — Exact Algorithm（P1-1，已实现）

**目的**：打破"Regime ↔ 未来 outcome"关联，同时保留日历 gaps、regime 持续性、事件聚集结构。

**v3 算法**（`regime_discovery_v3.py`）：
1. `rv_inf = regime[dim]` 在 INFERENCE_CALENDAR 上的 label 数组（长度 N_INF=728）。
2. 对 `b ∈ 1..5000`：`k = rng.integers(1, N_INF)`；`rv_shifted = np.roll(rv_inf, k)`（**完整日历循环移位**）。
3. `cells = evmask & (rv_shifted == rbin)`（事件 mask 固定，只移动 regime 相对位置）。
4. `permA = y_all[cells].mean() − bm`（bm = 原样本 same-oversold unconditional；oversold bin 事件集合不随 regime shift 改变，故 benchmark 不变）。
5. `nullA_p = mean(|permA| ≥ |excess_obs|)`（双侧）。

**与 v2 差异**：v2 在"事件日序列"上 `np.roll(D, k)`（删除无事件日，压缩日历）→ v3 在完整 Discovery 交易日历上移动 regime label。

## 3. NULL_C — Exact Algorithm（P1-2，已实现）

**目的**：保持 Regime segment 长度与持续性，置换 segment 与未来 outcome 的对应关系。

**v3 算法**：
1. 在 INFERENCE_CALENDAR 上按连续相同 regime label 切 segment runs `[(s0,e0),(s1,e1),...]`。
2. 对 `b ∈ 1..5000`：`order = rng.permutation(nseg)`；按 order 拼接各 segment 重建长度 N_INF 的 label 数组 `newrv`。
3. `cellc = evmask & (newrv == rbin)`；`permC = y_all[cellc].mean() − bm`。
4. `nullC_p = mean(|permC| ≥ |excess_obs|)`（双侧）。

**与 v2 差异**：v2 的 segments 基于 all_days（2018~2023-02）→ v3 基于 INFERENCE_CALENDAR。

## 4. Bootstrap — Exact Algorithm 与方向定义（P1-3，已实现）

**算法**（INFERENCE_CALENDAR）：
1. 预生成 `boot_idx = block_resample_idx(N_INF, L=21, B=2000, rng(seed=2020))`（circular block，块长 21 固定，2000 次固定）。
2. 对每次 resample `b`：`yb=y_all[idx]`、`rb=regime_bool[(dim,rbin)][idx]`、`evb=~isnan(yb)`；
   若 `evb.sum()≥2`：`bmb=yb[evb].mean()`（**benchmark 重估**）、`cellb=evb&rb`；若 `cellb.sum()≥2`：`exc_boot=yb[cellb].mean()−bmb`。
3. `boot_ci_lo/boot_ci_hi = percentile(exc_boot, [2.5, 97.5])`（**PRIMARY bootstrap inference**）。
4. `positive_boot_support = (boot_ci_lo > 0)`；`negative_boot_support = (boot_ci_hi < 0)`。

**方向定义**：
- `boot_prob_nonpositive = mean(exc_boot ≤ 0)` —— **仅 descriptive directional statistic**（矩阵列名 `boot_p`），**不再作为 robust gate**。
- 原因（v2 问题）：对负效应，`mean(exc≤0)≈1`，导致负显著效应被 v2 的 `boot_p<0.05` 门限排除，产生方向不对称。
- v3 主推断以 **95% CI 是否越过 0** 判断 bootstrap 支持；未选择单/双侧构造（不根据结果挑）。

## 5. HAC Lag — 状态（POST-HOC + Sensitivity）

**事实**：
- 预注册设计 `REGIME_RESEARCH_PLAN` v3 §10 仅写"Newey-West HAC"；首版运行报告 `REGIME_DISCOVERY_PHASE1.md` 仅写"自动带宽"——**均未冻结具体 lag 公式**。
- 具体自动公式 `K = ⌊4·(n/100)^(2/9)⌋`（clip [0, n−2]）首次出现在 corrected（v2）实现。
- 因此标记：**POST-HOC IMPLEMENTATION CHOICE**（不谎称 preregistered）。

**Sensitivity（仅 Discovery，不选优）**：`results/regime_v3_hac_lag_sensitivity.csv`，对每个 VALID cell 输出：
- `lag_auto`（自动 K）+ `raw_p_auto`；
- `lag_fixed`（5D ∈ {4,5}；10D ∈ {9,10}）+ `raw_p_fixed`。
- 主矩阵 raw_p 仍用自动 K（与 v2 可比）；fixed-lag 仅作 sensitivity 记录。

## 6. FDR — m=60 vs 104（已实现）

**主（Primary）**：BH FDR 仅应用于 **60 个 testable（VALID_SAMPLE）Primary hypotheses**（m=60）。理由：
- 预注册规则 `n_event_days < 150 → INSUFFICIENT_SAMPLE`（§7/§11 冻结）使 44 个 cell **不可检验、无 p-value**；
- 因此 FDR family = 60 个可检验 Primary，**不是全部 104 个注册 cell**。
- 主 BH 实现与 statsmodels `fdr_bh` 交叉验证：`max_abs = 1.110e-16`。

**参考（Robustness Reference，不替换 Primary）**：`results/regime_v3_bh104_reference.csv`——将 44 个 insufficient cell 视为 p=1，对 **104** 做 BH。仅作保守参考。

## 7. PREREQ MISMATCH — daily aggregate vs stock cluster（P1-4）

**预注册文本**（`REGIME_RESEARCH_PLAN` §10）："单格：日级截面均值 t 检验（Newey-West HAC）+ cluster-robust（按股票）"。

**实际实现**：Primary 观测单元 = **每日 stock-event 截面均值**（已聚合为 daily series），无法再按股票 cluster。

**明确口径**：
- **PRIMARY**：daily cross-sectional aggregate + Newey-West HAC（`regime_discovery_v3.py` 主矩阵）。
- **SECONDARY CROSS-CHECK**（若后续实现，需统计可靠）：stock-event panel regression + date cluster + stock cluster / two-way cluster。**不得替换 Primary，不得改变 hypothesis selection。**
- 本轮未运行 SECONDARY panel；先在本文记录 mismatch。Registry/Registry test 字段（`t_HAC+FDR(BH)_q005+block_bootstrap`）未改。

## 8. Registry（未修改）

- `HYPOTHESIS_REGISTRY.csv`：104 行 PRIMARY；benchmark 全 104 唯一 `same_oversold_unconditional`；test 全 104 = `t_HAC+FDR(BH)_q005+block_bootstrap`。
- **SHA256 = `5c5e451ad4eb3afd5e632b0019a3e02103e58e375e03cc231c5d8ca52b8c5195`**（commit `11e2ab2`）。

## 9. 未变 / 未做

- 未修改：Registry、regime thresholds、oversold bins、benchmark、horizons。
- 未打开：Validation（2023-2024）、Confirmation（2025-2026）。
- 未做：策略设计、调参、按结果选 lag / 选方法。
