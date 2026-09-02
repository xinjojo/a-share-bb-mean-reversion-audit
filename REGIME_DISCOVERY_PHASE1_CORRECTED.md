# REGIME DISCOVERY — PHASE 1 IMPLEMENTATION CORRECTION（修正版）
## 2020-01-01 ~ 2022-12-31 · 104 条预注册 PRIMARY · Registry 未修改

> 本版为外部审计 P0-1/P0-2/P1-1/P1-2/P1-3/P1-4 全部修复后的正式结果。
> Registry SHA256 保持 `5c5e451ad4eb3afd5e632b0019a3e02103e58e375e03cc231c5d8ca52b8c5195`（未修改，104 行）。
> 未打开 Validation(2023-24)/Confirmation(2025-26)；未修改阈值/bin/horizon；未形成策略。

---

## 一、P0-1 — 历史 WARMUP 修正

- **数据**：新增下载 2018-01-01~2019-12-31 全市场日线 + 复权因子 + PIT ST 状态（`data/warmup_daily_2018_2019.parquet`，1,718,712 行，含 214 只退市股历史）。加载范围：**2018-01-02 ~ 2023-02-28**（501 万行），覆盖 BB MA20/Std20(20日)、Trend ret20(20日)、Liquidity MA20(20日)、RV20(20日)、Vol trailing 252 日 rv20 percentile。
- **Discovery 事件仍严格限定 2020-01-01~2022-12-31**，warmup 年份不进 Discovery。
- **NaN → WARMUP**（不再默认 SIDEWAYS/NORMAL）：TREND ret20 NaN→WARMUP；BREADTH ratio NaN→WARMUP；VOL 已有 WARMUP 保持；LIQUIDITY amt_ratio NaN→WARMUP。任何 WARMUP 日不进 Primary cell。

**old vs corrected 审计（2020 年被重新分类天数）：**

| 维度 | 旧实现(无 warmup) 2020 年错分天数 | 修正后 2020 年 WARMUP 天数 |
|---|---|---|
| trend (ret20 NaN) | 20 | 0 |
| breadth (ma20 ratio NaN) | 19 | 0 |
| vol (rv20 percentile <100 历史) | **120** | 0 |
| liq (MA20 amt NaN) | 19 | 0 |

修正后被 WARMUP 排除的 Primary 事件数 = **0**（2020 全年 4 维 regime 全部有效）。
事件总数 373,856(旧) → **385,823**（warmup 使 2020 年初 BB/regime 有效）。

---

## 二、P0-2 — BH FDR 修正

- 修正为：sort p ascending → q=p·m/rank → **从右往左 cumulative-min** → clip≤1 → inverse-map。
- 独立交叉验证：`statsmodels.stats.multitest.multipletests(method='fdr_bh')`，**max_abs(q_own − q_statsmodels) = 1.11e-16** ✓（m=60）。
- FDR 仅应用于 60 个 VALID 格（104 中非 INSUFFICIENT）。

---

## 三、P1-1 — Benchmark 估计不确定性纳入

- PRIMARY benchmark 不变：`same_oversold_unconditional`（同 oversold bin + horizon 的 Discovery 全事件日日级截面均值再平均）。
- 推断改为 **regression contrast**：在事件日集合上回归 `y_t = α + β·D_t + e_t`（D=in-cell），excess = ((n_all−n_r)/n_all)·β；**SE 用 statsmodels Newey-West HAC**（自动带宽 K=⌊4(n/100)^(2/9)⌋），β 与基准组同为样本估计量，benchmark 估计误差进入协方差。t 统计量 = β/SE。
- **block bootstrap 每次 resample 在完整日历上抽 date blocks，重新计算 unconditional benchmark + conditional mean + REGIME_EXCESS**（非固定原样本 bm）。

---

## 四、P1-2 — 真实日历 block bootstrap

- 修正：不再先筛 regime 日期再压成连续序列；改为**完整交易日日历上的 circular block bootstrap**（L=21 固定，B=2000），每次抽整个 date block，block 内携带 date/regime label/oversold daily return/benchmark 数据。
- 预注册 NULL_A/B/C 全部执行（各 ≥5000 次，固定，未看结果调整）。

---

## 五、P1-4 — 命名与门槛

- `n_independent_days` → **`n_event_days`**（5D/10D forward 重叠，不作独立日）。
- 门槛冻结：`n_event_days < 150 → INSUFFICIENT_SAMPLE`（未降）。
- 胜率拆分：`stock_event_win_rate`（事件级）/ `daily_raw_positive_rate`（事件日 raw>0）/ `daily_excess_positive_rate`（事件日 excess>0）。

---

## 六、CORRECTED PHASE 1 汇总（104 格）

| 类别 | 数量 |
|---|---|
| **VALID_SAMPLE** | **60** |
| **INSUFFICIENT_SAMPLE** | **44** |
| **FDR_SIGNIFICANT (bh_q<0.05)** | **3**（全部为负方向） |
| positive_non_significant | 20 |
| negative | 40 |
| min raw_p | 0.0008 |
| min bh_q | 0.0400 |
| NULL_A significant (0.05) | 16 |
| NULL_C significant (0.05) | 11 |
| **HAC + FDR + bootstrap + NULL_A + NULL_C 同时支持** | **0** |

**FDR 显著的 3 格（负方向，LIQUIDITY NORMAL 时超跌反弹显著弱于 unconditional）：**

| 格 | bin | horizon | n_event_days | excess | t | raw_p | bh_q | boot_p | NULL_A | NULL_C |
|---|---|---|---|---|---|---|---|---|---|---|
| P0094 | B3 | 10D | 524 | −0.58% | −3.37 | 0.0008 | **0.040** | 0.998 | 0.0000 | 0.015 |
| P0095 | B4 | 5D | 360 | −0.55% | −3.15 | 0.0018 | **0.040** | 1.000 | 0.007 | 0.032 |
| P0096 | B4 | 10D | 360 | −0.72% | −3.11 | 0.0020 | **0.040** | 1.000 | 0.019 | 0.053 |

> 解读提示：LIQUIDITY NORMAL 为最常见状态，其负 excess 反映"流动性正常时超跌反弹弱于平均"；LIQUIDITY LOW/HIGH 因样本不足（INSUFFICIENT）无法直接对比，**不可据此构造可交易负 Alpha**。此三格是负向稳健证据，非正向机会。

---

## 七、BREADTH LOW 全 8 格追踪（原预注册 <30%，重点验证旧 P0027）

| 格 | bin | horizon | n_event_days | mean_raw | benchmark | excess | win_rate | t | raw_p | **bh_q** | CI | boot_p | NULL_A | NULL_C | status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P0025 | B1 | 5D | 172 | +0.96% | −0.06% | +1.02% | 54.5% | 2.10 | 0.036 | 0.156 | [0.21,1.94]% | 0.006 | 0.041 | 0.007 | VALID |
| P0026 | B1 | 10D | 172 | +1.41% | −0.10% | +1.51% | 54.5% | 2.18 | 0.029 | 0.156 | [0.08,3.07]% | 0.019 | 0.068 | 0.020 | VALID |
| **P0027** | B2 | 5D | 169 | +1.11% | −0.26% | **+1.37%** | 57.8% | 2.72 | 0.0068 | **0.058** | [0.47,2.45]% | 0.001 | 0.010 | 0.001 | VALID |
| P0028 | B2 | 10D | 169 | +1.40% | −0.42% | +1.82% | 58.8% | 2.66 | 0.008 | 0.061 | [0.37,3.37]% | 0.008 | 0.015 | 0.008 | VALID |
| P0029 | B3 | 5D | 163 | +0.16% | −0.69% | +0.85% | 61.8% | 1.55 | 0.122 | 0.296 | [−0.27,1.99]% | 0.065 | 0.062 | 0.063 | VALID |
| P0030 | B3 | 10D | 163 | +0.44% | −0.88% | +1.32% | 63.8% | 1.68 | 0.093 | 0.268 | [−0.34,3.10]% | 0.062 | 0.063 | 0.072 | VALID |
| P0031 | B4 | 5D | 131 | — | — | — | — | — | — | — | — | — | — | — | **INSUFFICIENT** |
| P0032 | B4 | 10D | 131 | — | — | — | — | — | — | — | — | — | — | — | **INSUFFICIENT** |

**旧 P0027（bug 版：excess≈+1.17%, raw_p≈0.035）→ 修正后：excess +1.37%（同方向、更强），raw_p 0.0068，bootstrap(NULL 双) 均支持，但 bh_q=0.058 仍未过 FDR。**
BREADTH LOW 族 B1-B3 × 5D/10D 全部正（+0.85%~+1.82%），bootstrap/NULL_A/NULL_C 方向一致；**FDR 门槛（q<0.05）无一通过**。B4 样本不足（131<150）→ INSUFFICIENT。

---

## 八、审计交叉验证

- **BH FDR**：own vs statsmodels max_abs diff = 1.11e-16 ✓
- **5 个随机 VALID cells**（seed=42，第二套独立实现：dict 累加聚合 + statsmodels HAC）逐项重算 event dates / conditional mean / benchmark / excess / HAC t / raw p：

| id | dim | bin | hz | excess(独立) | 矩阵 | t(独立) | 矩阵 | raw_p(独立) | 矩阵 |
|---|---|---|---|---|---|---|---|---|---|
| P0001 | TREND | UP | B1 5D | −0.0025 | −0.0025 | −0.77 | −0.77 | 0.4401 | 0.4401 |
| P0006 | TREND | UP | B3 10D | −0.0021 | −0.0021 | −0.33 | −0.33 | 0.7451 | 0.7451 |
| P0051 | VOL | LOW | B2 5D | +0.0002 | +0.0002 | 0.04 | 0.04 | 0.9679 | 0.9679 |
| P0064 | VOL | NORMAL | B4 10D | −0.0014 | −0.0014 | −0.18 | −0.18 | 0.8607 | 0.8607 |
| P0016 | TREND | SIDEWAYS | B4 10D | −0.0076 | −0.0076 | −1.17 | −1.17 | 0.2438 | 0.2438 |

**CROSS-CHECK: PASS（5/5 完全一致）**

---

## 九、结论（严格限定）

1. **修正后无任何正向 hypothesis 通过 FDR**（BREADTH LOW 最接近：P0027 q=0.058，仍失败）。
2. **3 个负向 hypothesis 通过 FDR**（LIQUIDITY NORMAL 下超跌反弹显著弱于 unconditional），属负向稳健证据，不可交易。
3. **HAC+FDR+bootstrap+双 structured permutation 同时支持的 cell = 0**。
4. **BREADTH LOW 候选**在修正后仍同方向、更强（P0027 +1.37%, raw_p 0.0068, boot/NULL 全支持），方向跨 B1-B3 一致；但严格多重检验下**未成立**，仅作为 Validation 阶段的预注册待验证信号。
5. 原首版（Phase 1 v1）结果中 FDR=0 的结论在修正后**实质未变**（仍无正向显著），但 v1 的 HAC t / q 值受实现 bug 污染，作废。

完整 104 格矩阵：`results/regime_discovery_matrix_v2.csv`（含 VALID/INSUFFICIENT 全部格与全部统计列）。
代码：`regime_discovery_corrected.py`、`cross_check_phase1.py`、`download_warmup.py`。
未打开 Validation / Confirmation；未修改 Registry；未形成策略。
