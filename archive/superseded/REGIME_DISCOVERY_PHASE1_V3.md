# REGIME_DISCOVERY_PHASE1_V3 — Inference Correction 结果报告（FACTS ONLY）

> 状态：**UNDER AUDIT / NOT YET ACCEPTED**；Validation(2023-24) / Confirmation(2025-26) **未打开**。
> 本版仅修正 Discovery inference 实现（P1-1/P1-2/P1-3 + HAC lag 核验 + FDR m 处理），未修改 Registry（SHA256 见 §9）、阈值、bins、benchmark、horizons。
> v2 矩阵保留不覆盖；本版产出矩阵 v3 与 v2→v3 diff。

---

## 0. 修正内容（对照外部审计）

| 项 | 审计问题 | 修正 |
|---|---|---|
| P1-1 | NULL_A 在"事件日序列"上 roll D，压缩了日历 | NULL_A 改为在**完整 INFERENCE_CALENDAR** 上 circular shift **regime label series**（事件/outcome 序列固定），保留日历 gaps、regime 持续性、事件聚集结构 |
| P1-2 | bootstrap/NULL_C/事件 mask 使用了 Discovery 外日历（2018-2019 warmup、2023-01~02） | 全部 resampling 基于严格 **INFERENCE_CALENDAR = 2020-01-01~2022-12-31（728 个交易日）**；2018+ 仅用于 PIT 特征（FEATURE_CALENDAR），2023-01~02 仅用于 T+5/T+10 outcome 读取（OUTCOME_LOOKAHEAD） |
| P1-3 | boot_p 定义不规范、方向不对称（负效应 → boot_p≈1） | PRIMARY bootstrap inference 改用 **95% block-bootstrap CI** + `positive_boot_support`/`negative_boot_support`；原 `mean(exc_boot≤0)` 更名 **`boot_prob_nonpositive`**（仅 descriptive directional，不再作为 robust gate） |
| P1-4 | 预注册 §10 写"cluster-robust（按股票）"，实际用日级聚合 | 明确 **PRIMARY = daily cross-sectional aggregate + HAC**；stock-event panel cluster 列为 **SECONDARY CROSS-CHECK**（本轮未运行，不替换 Primary）。详见 `REGIME_PHASE1_METHODOLOGY_CLARIFICATION.md` |
| HAC lag | 自动带宽 `K=⌊4(n/100)^(2/9)⌋` 未在首次 Discovery run 前预注册 | 标记 **POST-HOC IMPLEMENTATION CHOICE**（预注册 `REGIME_RESEARCH_PLAN` v3 仅写 "Newey-West HAC"；首版 `REGIME_DISCOVERY_PHASE1.md` 仅写 "自动带宽"，均无公式）。补固定 lag sensitivity：5D → lag 4,5；10D → lag 9,10，另含自动 K。**只作 sensitivity，不选最好结果** |
| FDR m | 主 BH m=60（仅 VALID/testable），需与 104 对齐说明 | 主 BH 保持 **m=60**（44 insufficient cells 在预注册规则 n_event_days<150 下无 p-value、不可检验，不属于 FDR family）；另生成 **m=104 保守参考**（44 insufficient 视为 p=1），仅 robustness reference，不替换 Primary |

---

## 1. 数据与日期（事实）

- **FEATURE_CALENDAR**：2018-01-02 ~ 2023-02-28（warmup `warmup_daily_2018_2019.parquet` + `combined_daily.parquet` 截断）；rows=5,012,556。
- **INFERENCE_CALENDAR**：**2020-01-02 ~ 2022-12-30，n_days=728**（= 2020-01-01~2022-12-31 的交易日）。
- **OUTCOME_LOOKAHEAD**：事件 T∈[DISC0,DISC1] 的 `open_adj[T+1]`、`close_adj[T+5/T+10]` 允许读取至 2023-01 中旬（2022-12-30 + 10 交易日）；该未来价格仅用于 outcome 计算，不进入任何 Resampling 日历结构。
- **Discovery outcome 严格限定** 2020-01-01~2022-12-31。
- **oversold 事件总数**：385,823；`non_tradable_t1=183`；`otc5 缺失=337`；`otc10 缺失=459`（缺失标记保留，不删除）。

## 2. 统计实现（v3，与 v2 相同的点估计部分保持不变）

- 点估计 / HAC regression contrast / benchmark（`same_oversold_unconditional`）与 v2 **完全相同**（事件日集合未变）。
- 主矩阵列：`hypothesis_id, regime_dimension, regime_bin, oversold_bin, forward_horizon, n_stock_events, n_event_days, n_non_tradable_t1, status, mean_raw_return, benchmark, mean_regime_excess, median_regime_excess, stock_event_win_rate, daily_raw_positive_rate, daily_excess_positive_rate, hac_effect, hac_se, hac_t, raw_p, boot_ci_lo, boot_ci_hi, boot_p, positive_boot_support, negative_boot_support, nullA_p, nullC_p, nullB_p, nullB_note, nw_lag, bh_q`。
- `boot_p` 列 = `boot_prob_nonpositive`（描述性，非 p 值门限）；主 bootstrap 推断用 `boot_ci_lo/boot_ci_hi`（2.5/97.5 百分位）与 `positive_boot_support=(ci_lo>0)` / `negative_boot_support=(ci_hi<0)`。
- bootstrap：circular block，块长 L=21 固定，B=2000，seed=2020，**INFERENCE_CALENDAR**，每次 resample 重算 benchmark+conditional+excess。
- NULL_A：INFERENCE_CALENDAR 上 circular shift regime label（k∈[1,N_INF)），5000 次。
- NULL_C：INFERENCE_CALENDAR 上 regime segment block permutation，5000 次。
- NULL_B：within-date stock permutation（20 次），secondary structure check，`STRUCTURAL_INVARIANT`。
- 主 BH FDR m=60：own 实现与 statsmodels `fdr_bh` 交叉验证 `max_abs=1.110e-16`。
- 参考 BH FDR m=104：44 insufficient 视为 p=1，仅 robustness reference。

## 3. 结果汇总（v3，104 格）

| 指标 | 值 |
|---|---|
| VALID_SAMPLE | 60 |
| INSUFFICIENT_SAMPLE | 44 |
| FDR_SIGNIFICANT（bh_q<0.05, m=60） | **3**（全负向） |
| positive_non_significant | 20 |
| negative | 40 |
| min raw_p | 0.0008 |
| min bh_q（m=60） | 0.0400 |
| positive_boot_support | 4 |
| negative_boot_support | 10 |
| NULL_A_p<0.05 | 16 |
| NULL_C_p<0.05 | 15 |
| FDR + neg_boot + NULL_A + NULL_C 同时支持 | **3** |
| FDR + pos_boot + NULL_A + NULL_C 同时支持 | **0** |
| BH(m=104) FDR_SIGNIFICANT（参考） | **0** |

- 3 个 FDR 显著格（全部负向、LIQUIDITY NORMAL）：
  - **P0094**（B3 10D）：excess −0.576%，raw_p 0.0008，bh_q 0.0400，boot_CI [−1.010%,−0.191%]（neg_support=True），nullA 0.0024，nullC 0.0070。
  - **P0095**（B4 5D）：excess −0.552%，raw_p 0.0018，bh_q 0.0400，boot_CI [−0.919%,−0.213%]（neg_support=True），nullA 0.0154，nullC 0.0126。
  - **P0096**（B4 10D）：excess −0.721%，raw_p 0.0020，bh_q 0.0400，boot_CI [−1.218%,−0.310%]（neg_support=True），nullA 0.0134，nullC 0.0294。
- **正向**：无任何 cell 通过 FDR+pos_boot+双 permutation（=0）。BREADTH LOW 族 P0025/P0026/P0027/P0028 的 bootstrap CI 全正（positive_boot_support=True）且 nullA/nullC 显著，但 **bh_q 均未过 0.05**（0.0581~0.1558）。

## 4. BREADTH LOW 全 8 格（预注册 <30%）

| id | oversold/hz | status | excess | raw_p | bh_q(m60) | boot_CI | pos_support | nullA_p | nullC_p |
|---|---|---|---|---|---|---|---|---|---|
| P0025 | B1/5D | VALID | +1.018% | 0.0363 | 0.1558 | [+0.140%,+1.991%] | True | 0.0360 | 0.0138 |
| P0026 | B1/10D | VALID | +1.508% | 0.0295 | 0.1558 | [+0.014%,+3.086%] | True | 0.0702 | 0.0360 |
| P0027 | B2/5D | VALID | +1.368% | 0.0068 | **0.0581** | [+0.454%,+2.427%] | True | 0.0156 | 0.0032 |
| P0028 | B2/10D | VALID | +1.821% | 0.0081 | **0.0606** | [+0.387%,+3.406%] | True | 0.0280 | 0.0160 |
| P0029 | B3/5D | VALID | +0.850% | 0.1225 | 0.2964 | [−0.284%,+2.000%] | False | 0.1220 | 0.0952 |
| P0030 | B3/10D | VALID | +1.319% | 0.0929 | 0.2678 | [−0.506%,+3.157%] | False | 0.1430 | 0.1180 |
| P0031 | B4/5D | INSUFFICIENT | — | — | — | — | — | — | — |
| P0032 | B4/10D | INSUFFICIENT | — | — | — | — | — | — | — |

（P0031/P0032：n_event_days=131<150 → INSUFFICIENT_SAMPLE，预注册规则，未改。）

## 5. v2 → v3 Change Table（`results/regime_v2_v3_diff.csv`，104 行）

- **status_changed = 0**：VALID/INSUFFICIENT 分布完全不变。
- **bhq_changed_significance = 0**：FDR(m=60) 显著性与 v2 完全相同（仍 P0094/95/96 三个负向，bh_q 全 0.0400）。
- **excess / HAC t / raw_p：0 变化**（`excess_delta` 与 `rawp_delta` 全为 0）——点估计与事件日集合未受 resampling 日历修正影响。
- **NULL_A 显著性翻转 2 格**：P0033（v2 0.0506→v3 0.0408，转显著）、P0037（v2 0.0320→v3 0.0634，转不显著）。
- **NULL_C 显著性翻转 4 格**：P0035（0.0702→0.0226）、P0067（0.0738→0.0266）、P0069（0.1018→0.0364）、P0096（0.0532→0.0294）——均 v2 不显著 → v3 显著。
- **boot 口径变更**：v2 `boot_p<0.05` 为门限（负效应 boot_p≈1 被掩盖）→ v3 主用 95% CI + direction support。**robust 计数由 v2 的 0 → v3 的 3**（P0094/95/96 负向显著格在 CI 口径下获得 negative_boot_support=True；这 3 格在 v2 中因 boot_p≈1.0 被排除在 robust 之外）。
- **BH(m=104) 参考**：0 显著（3 个原显著格在 m=104 下 q≈0.069>0.05）。

## 6. 特别报告

- **BREADTH LOW P0027**（B2 5D）：修正后 excess +1.368%（与 v2 相同），raw_p 0.0068，boot_CI [+0.454%,+2.427%] 全正（pos_support=True）、boot_prob_nonpositive=0.001，nullA 0.0156、nullC 0.0032，均通过；但 **bh_q=0.0581，未过 FDR(m=60)**。即：方向与 bootstrap/permutation 证据一致，FDR 不显著。
- **原 bh_q<0.05 三格**（P0094/95/96）：修正后仍 bh_q=0.0400，且 v3 下 CI 全负、nullA/nullC 显著 → 负向证据更强（非交易信号）。
- **正向 robust = 0**：无任何正向 cell 同时通过 FDR+pos_boot+双 permutation。

## 7. 输出文件

| 文件 | 说明 |
|---|---|
| `regime_discovery_v3.py` | v3 实现（INFERENCE_CALENDAR 严格化、NULL_A 全日历 shift、CI 主推断、fixed-lag sensitivity、FDR m60/m104） |
| `results/regime_discovery_matrix_v3.csv` | 104×31 修正后矩阵 |
| `results/regime_v3_hac_lag_sensitivity.csv` | 每 VALID cell 自动 K vs 固定 lag（5D:4,5 / 10D:9,10）的 raw_p |
| `results/regime_v3_bh104_reference.csv` | m=104 保守参考 FDR |
| `results/regime_v2_v3_diff.csv` | 104 行 v2→v3 逐格对照（excess/HAC t/raw_p/bh_q/boot_CI/NULL_A/NULL_C/status + 变化列） |
| `REGIME_PHASE1_METHODOLOGY_CLARIFICATION.md` | 方法澄清（inference calendar / null 算法 / bootstrap 方向 / HAC lag 状态 / FDR m / cluster mismatch） |

## 8. HAC 固定 lag sensitivity（仅 Discovery，不选优）

`results/regime_v3_hac_lag_sensitivity.csv`：对每个 VALID cell 输出 `lag_auto`（自动 K）、`raw_p_auto`、`lag_fixed`（5D∈{4,5}；10D∈{9,10}）、`raw_p_fixed`。仅作 sensitivity 记录，不用于 hypothesis selection。

## 9. Registry（未修改）

- `HYPOTHESIS_REGISTRY.csv`：104 行 PRIMARY，benchmark 唯一 `same_oversold_unconditional`。
- **SHA256 = `5c5e451ad4eb3afd5e632b0019a3e02103e58e375e03cc231c5d8ca52b8c5195`**（commit `11e2ab2`）。
- 未修改阈值/bins/horizons/benchmark；Validation 与 Confirmation **未打开**。

---

## 附：完整 104 格（v3）

### TREND（24 格）
| id | regime | oversold | hz | status | n_event_days | n_stock_events | excess | raw_p | bh_q | boot_ci | nullA | nullC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P0018 | DOWN | B1 | 10D | VALID_SAMPLE | 179 | 109822 | +0.584% | 0.4080 | 0.6278 | [-0.9418%,+2.3155%] | 0.3774 | 0.4222 |
| P0017 | DOWN | B1 | 5D | VALID_SAMPLE | 179 | 109883 | +0.474% | 0.3027 | 0.5193 | [-0.4604%,+1.5110%] | 0.2234 | 0.2426 |
| P0020 | DOWN | B2 | 10D | VALID_SAMPLE | 176 | 50338 | +0.752% | 0.2930 | 0.5193 | [-0.7638%,+2.5443%] | 0.3300 | 0.3198 |
| P0019 | DOWN | B2 | 5D | VALID_SAMPLE | 176 | 50350 | +0.758% | 0.1211 | 0.2964 | [-0.2320%,+1.9346%] | 0.0958 | 0.0922 |
| P0022 | DOWN | B3 | 10D | VALID_SAMPLE | 157 | 16164 | +0.755% | 0.3414 | 0.5536 | [-0.9910%,+2.5815%] | 0.3910 | 0.3608 |
| P0021 | DOWN | B3 | 5D | VALID_SAMPLE | 157 | 16161 | +0.591% | 0.2837 | 0.5193 | [-0.6224%,+1.8436%] | 0.2392 | 0.2302 |
| P0024 | DOWN | B4 | 10D | INSUFFICIENT_SAMPLE | 116 | 5685 | — | — | — | [—,—] | — | — |
| P0023 | DOWN | B4 | 5D | INSUFFICIENT_SAMPLE | 116 | 5685 | — | — | — | [—,—] | — | — |
| P0010 | SIDEWAYS | B1 | 10D | VALID_SAMPLE | 279 | 95506 | -0.089% | 0.8227 | 0.8815 | [-0.9676%,+0.7312%] | 0.8488 | 0.8688 |
| P0009 | SIDEWAYS | B1 | 5D | VALID_SAMPLE | 279 | 95562 | -0.062% | 0.8083 | 0.8815 | [-0.5639%,+0.4113%] | 0.8216 | 0.8306 |
| P0012 | SIDEWAYS | B2 | 10D | VALID_SAMPLE | 275 | 39072 | -0.150% | 0.7109 | 0.8705 | [-1.0584%,+0.7224%] | 0.7630 | 0.7750 |
| P0011 | SIDEWAYS | B2 | 5D | VALID_SAMPLE | 275 | 39081 | -0.071% | 0.7982 | 0.8815 | [-0.6282%,+0.4491%] | 0.8012 | 0.8230 |
| P0014 | SIDEWAYS | B3 | 10D | VALID_SAMPLE | 260 | 10641 | -0.271% | 0.5699 | 0.7599 | [-1.4148%,+0.8013%] | 0.5808 | 0.6444 |
| P0013 | SIDEWAYS | B3 | 5D | VALID_SAMPLE | 260 | 10640 | -0.001% | 0.9972 | 0.9972 | [-0.7289%,+0.6990%] | 0.9988 | 0.9978 |
| P0016 | SIDEWAYS | B4 | 10D | VALID_SAMPLE | 202 | 2113 | -0.765% | 0.2438 | 0.5193 | [-2.1861%,+0.5382%] | 0.3750 | 0.3932 |
| P0015 | SIDEWAYS | B4 | 5D | VALID_SAMPLE | 202 | 2110 | -0.374% | 0.3924 | 0.6196 | [-1.2417%,+0.4163%] | 0.5196 | 0.5344 |
| P0002 | UP | B1 | 10D | VALID_SAMPLE | 269 | 41190 | -0.296% | 0.5519 | 0.7525 | [-1.4759%,+0.7906%] | 0.5534 | 0.5850 |
| P0001 | UP | B1 | 5D | VALID_SAMPLE | 269 | 41199 | -0.251% | 0.4401 | 0.6287 | [-1.0016%,+0.4039%] | 0.4254 | 0.4076 |
| P0004 | UP | B2 | 10D | VALID_SAMPLE | 262 | 11898 | -0.347% | 0.5107 | 0.7126 | [-1.5964%,+0.7949%] | 0.5240 | 0.5288 |
| P0003 | UP | B2 | 5D | VALID_SAMPLE | 262 | 11905 | -0.434% | 0.2279 | 0.5065 | [-1.3221%,+0.2973%] | 0.1870 | 0.2056 |
| P0006 | UP | B3 | 10D | VALID_SAMPLE | 228 | 2368 | -0.210% | 0.7451 | 0.8815 | [-1.5898%,+1.0969%] | 0.7508 | 0.7260 |
| P0005 | UP | B3 | 5D | VALID_SAMPLE | 228 | 2366 | -0.406% | 0.3211 | 0.5351 | [-1.3035%,+0.4183%] | 0.2730 | 0.2630 |
| P0008 | UP | B4 | 10D | INSUFFICIENT_SAMPLE | 128 | 410 | — | — | — | [—,—] | — | — |
| P0007 | UP | B4 | 5D | INSUFFICIENT_SAMPLE | 128 | 410 | — | — | — | [—,—] | — | — |

### BREADTH（24 格）
| id | regime | oversold | hz | status | n_event_days | n_stock_events | excess | raw_p | bh_q | boot_ci | nullA | nullC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P0042 | HIGH | B1 | 10D | INSUFFICIENT_SAMPLE | 107 | 4806 | — | — | — | [—,—] | — | — |
| P0041 | HIGH | B1 | 5D | INSUFFICIENT_SAMPLE | 107 | 4811 | — | — | — | [—,—] | — | — |
| P0044 | HIGH | B2 | 10D | INSUFFICIENT_SAMPLE | 100 | 1108 | — | — | — | [—,—] | — | — |
| P0043 | HIGH | B2 | 5D | INSUFFICIENT_SAMPLE | 100 | 1108 | — | — | — | [—,—] | — | — |
| P0046 | HIGH | B3 | 10D | INSUFFICIENT_SAMPLE | 70 | 221 | — | — | — | [—,—] | — | — |
| P0045 | HIGH | B3 | 5D | INSUFFICIENT_SAMPLE | 70 | 221 | — | — | — | [—,—] | — | — |
| P0048 | HIGH | B4 | 10D | INSUFFICIENT_SAMPLE | 30 | 43 | — | — | — | [—,—] | — | — |
| P0047 | HIGH | B4 | 5D | INSUFFICIENT_SAMPLE | 30 | 43 | — | — | — | [—,—] | — | — |
| P0026 | LOW | B1 | 10D | VALID_SAMPLE | 172 | 132071 | +1.508% | 0.0295 | 0.1558 | [+0.0136%,+3.0859%] | 0.0702 | 0.0360 |
| P0025 | LOW | B1 | 5D | VALID_SAMPLE | 172 | 132157 | +1.018% | 0.0363 | 0.1558 | [+0.1404%,+1.9911%] | 0.0360 | 0.0138 |
| P0028 | LOW | B2 | 10D | VALID_SAMPLE | 169 | 63785 | +1.821% | 0.0081 | 0.0606 | [+0.3870%,+3.4055%] | 0.0280 | 0.0160 |
| P0027 | LOW | B2 | 5D | VALID_SAMPLE | 169 | 63799 | +1.368% | 0.0068 | 0.0581 | [+0.4536%,+2.4268%] | 0.0156 | 0.0032 |
| P0030 | LOW | B3 | 10D | VALID_SAMPLE | 163 | 20339 | +1.319% | 0.0929 | 0.2678 | [-0.5062%,+3.1574%] | 0.1430 | 0.1180 |
| P0029 | LOW | B3 | 5D | VALID_SAMPLE | 163 | 20334 | +0.850% | 0.1225 | 0.2964 | [-0.2840%,+1.9998%] | 0.1220 | 0.0952 |
| P0032 | LOW | B4 | 10D | INSUFFICIENT_SAMPLE | 131 | 6527 | — | — | — | [—,—] | — | — |
| P0031 | LOW | B4 | 5D | INSUFFICIENT_SAMPLE | 131 | 6527 | — | — | — | [—,—] | — | — |
| P0034 | MID | B1 | 10D | VALID_SAMPLE | 448 | 109641 | -0.447% | 0.1073 | 0.2928 | [-1.1110%,+0.1375%] | 0.1266 | 0.1580 |
| P0033 | MID | B1 | 5D | VALID_SAMPLE | 448 | 109676 | -0.351% | 0.0721 | 0.2421 | [-0.8384%,+0.0521%] | 0.0408 | 0.0516 |
| P0036 | MID | B2 | 10D | VALID_SAMPLE | 444 | 36415 | -0.612% | 0.0350 | 0.1558 | [-1.3012%,-0.0116%] | 0.0416 | 0.0618 |
| P0035 | MID | B2 | 5D | VALID_SAMPLE | 444 | 36429 | -0.450% | 0.0334 | 0.1558 | [-0.9600%,-0.0065%] | 0.0202 | 0.0226 |
| P0038 | MID | B3 | 10D | VALID_SAMPLE | 412 | 8613 | -0.550% | 0.0937 | 0.2678 | [-1.2977%,+0.1496%] | 0.0978 | 0.1230 |
| P0037 | MID | B3 | 5D | VALID_SAMPLE | 412 | 8612 | -0.413% | 0.0726 | 0.2421 | [-0.9435%,+0.0556%] | 0.0634 | 0.0660 |
| P0040 | MID | B4 | 10D | VALID_SAMPLE | 285 | 1638 | -0.577% | 0.2025 | 0.4674 | [-1.6642%,+0.3058%] | 0.3126 | 0.3114 |
| P0039 | MID | B4 | 5D | VALID_SAMPLE | 285 | 1635 | -0.524% | 0.0914 | 0.2678 | [-1.2410%,+0.0677%] | 0.1846 | 0.1764 |

### VOLATILITY（32 格）
| id | regime | oversold | hz | status | n_event_days | n_stock_events | excess | raw_p | bh_q | boot_ci | nullA | nullC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P0074 | EXTREME | B1 | 10D | INSUFFICIENT_SAMPLE | 87 | 31766 | — | — | — | [—,—] | — | — |
| P0073 | EXTREME | B1 | 5D | INSUFFICIENT_SAMPLE | 87 | 31771 | — | — | — | [—,—] | — | — |
| P0076 | EXTREME | B2 | 10D | INSUFFICIENT_SAMPLE | 80 | 17441 | — | — | — | [—,—] | — | — |
| P0075 | EXTREME | B2 | 5D | INSUFFICIENT_SAMPLE | 80 | 17441 | — | — | — | [—,—] | — | — |
| P0078 | EXTREME | B3 | 10D | INSUFFICIENT_SAMPLE | 59 | 7518 | — | — | — | [—,—] | — | — |
| P0077 | EXTREME | B3 | 5D | INSUFFICIENT_SAMPLE | 59 | 7512 | — | — | — | [—,—] | — | — |
| P0080 | EXTREME | B4 | 10D | INSUFFICIENT_SAMPLE | 33 | 3931 | — | — | — | [—,—] | — | — |
| P0079 | EXTREME | B4 | 5D | INSUFFICIENT_SAMPLE | 33 | 3931 | — | — | — | [—,—] | — | — |
| P0066 | HIGH | B1 | 10D | VALID_SAMPLE | 204 | 73954 | -0.238% | 0.6658 | 0.8684 | [-1.4779%,+0.9153%] | 0.8018 | 0.7156 |
| P0065 | HIGH | B1 | 5D | VALID_SAMPLE | 204 | 74016 | -0.642% | 0.1235 | 0.2964 | [-1.6531%,+0.2492%] | 0.1292 | 0.0860 |
| P0068 | HIGH | B2 | 10D | VALID_SAMPLE | 198 | 27436 | -0.713% | 0.2618 | 0.5193 | [-2.3331%,+0.5396%] | 0.3516 | 0.3020 |
| P0067 | HIGH | B2 | 5D | VALID_SAMPLE | 198 | 27446 | -0.906% | 0.0480 | 0.1921 | [-2.1052%,+0.0398%] | 0.0322 | 0.0266 |
| P0070 | HIGH | B3 | 10D | VALID_SAMPLE | 177 | 7388 | -0.707% | 0.2695 | 0.5193 | [-2.0713%,+0.6076%] | 0.3342 | 0.3506 |
| P0069 | HIGH | B3 | 5D | VALID_SAMPLE | 177 | 7389 | -0.927% | 0.0618 | 0.2316 | [-2.1147%,+0.1355%] | 0.0240 | 0.0364 |
| P0072 | HIGH | B4 | 10D | INSUFFICIENT_SAMPLE | 109 | 1517 | — | — | — | [—,—] | — | — |
| P0071 | HIGH | B4 | 5D | INSUFFICIENT_SAMPLE | 109 | 1519 | — | — | — | [—,—] | — | — |
| P0050 | LOW | B1 | 10D | VALID_SAMPLE | 156 | 52784 | +0.572% | 0.4334 | 0.6287 | [-1.2994%,+2.4614%] | 0.5538 | 0.4808 |
| P0049 | LOW | B1 | 5D | VALID_SAMPLE | 156 | 52804 | +0.112% | 0.8223 | 0.8815 | [-1.1332%,+1.1587%] | 0.8164 | 0.7972 |
| P0052 | LOW | B2 | 10D | VALID_SAMPLE | 156 | 21236 | +0.575% | 0.4288 | 0.6287 | [-1.1469%,+2.2703%] | 0.5716 | 0.4834 |
| P0051 | LOW | B2 | 5D | VALID_SAMPLE | 156 | 21248 | +0.021% | 0.9679 | 0.9843 | [-1.2178%,+1.0865%] | 0.9754 | 0.9674 |
| P0054 | LOW | B3 | 10D | INSUFFICIENT_SAMPLE | 149 | 4714 | — | — | — | [—,—] | — | — |
| P0053 | LOW | B3 | 5D | INSUFFICIENT_SAMPLE | 149 | 4710 | — | — | — | [—,—] | — | — |
| P0056 | LOW | B4 | 10D | INSUFFICIENT_SAMPLE | 119 | 913 | — | — | — | [—,—] | — | — |
| P0055 | LOW | B4 | 5D | INSUFFICIENT_SAMPLE | 119 | 909 | — | — | — | [—,—] | — | — |
| P0058 | NORMAL | B1 | 10D | VALID_SAMPLE | 280 | 88014 | -0.442% | 0.2997 | 0.5193 | [-1.3339%,+0.4228%] | 0.3566 | 0.4090 |
| P0057 | NORMAL | B1 | 5D | VALID_SAMPLE | 280 | 88053 | -0.068% | 0.7991 | 0.8815 | [-0.5536%,+0.4128%] | 0.8056 | 0.8104 |
| P0060 | NORMAL | B2 | 10D | VALID_SAMPLE | 279 | 35195 | -0.030% | 0.9476 | 0.9803 | [-0.9153%,+0.8892%] | 0.9524 | 0.9524 |
| P0059 | NORMAL | B2 | 5D | VALID_SAMPLE | 279 | 35201 | +0.113% | 0.6918 | 0.8705 | [-0.3814%,+0.6575%] | 0.7214 | 0.7268 |
| P0062 | NORMAL | B3 | 10D | VALID_SAMPLE | 260 | 9553 | +0.197% | 0.6974 | 0.8705 | [-0.7674%,+1.3297%] | 0.7472 | 0.7380 |
| P0061 | NORMAL | B3 | 5D | VALID_SAMPLE | 260 | 9556 | +0.339% | 0.3029 | 0.5193 | [-0.2598%,+1.0292%] | 0.3024 | 0.3344 |
| P0064 | NORMAL | B4 | 10D | VALID_SAMPLE | 185 | 1847 | -0.141% | 0.8607 | 0.9060 | [-1.7645%,+1.4966%] | 0.8494 | 0.8826 |
| P0063 | NORMAL | B4 | 5D | VALID_SAMPLE | 185 | 1846 | +0.126% | 0.8122 | 0.8815 | [-0.9475%,+1.1836%] | 0.8072 | 0.8626 |

### LIQUIDITY（24 格）
| id | regime | oversold | hz | status | n_event_days | n_stock_events | excess | raw_p | bh_q | boot_ci | nullA | nullC |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P0098 | HIGH | B1 | 10D | INSUFFICIENT_SAMPLE | 72 | 18079 | — | — | — | [—,—] | — | — |
| P0097 | HIGH | B1 | 5D | INSUFFICIENT_SAMPLE | 72 | 18079 | — | — | — | [—,—] | — | — |
| P0100 | HIGH | B2 | 10D | INSUFFICIENT_SAMPLE | 67 | 9057 | — | — | — | [—,—] | — | — |
| P0099 | HIGH | B2 | 5D | INSUFFICIENT_SAMPLE | 67 | 9057 | — | — | — | [—,—] | — | — |
| P0102 | HIGH | B3 | 10D | INSUFFICIENT_SAMPLE | 55 | 3479 | — | — | — | [—,—] | — | — |
| P0101 | HIGH | B3 | 5D | INSUFFICIENT_SAMPLE | 55 | 3481 | — | — | — | [—,—] | — | — |
| P0104 | HIGH | B4 | 10D | INSUFFICIENT_SAMPLE | 40 | 987 | — | — | — | [—,—] | — | — |
| P0103 | HIGH | B4 | 5D | INSUFFICIENT_SAMPLE | 40 | 988 | — | — | — | [—,—] | — | — |
| P0082 | LOW | B1 | 10D | INSUFFICIENT_SAMPLE | 70 | 47586 | — | — | — | [—,—] | — | — |
| P0081 | LOW | B1 | 5D | INSUFFICIENT_SAMPLE | 70 | 47607 | — | — | — | [—,—] | — | — |
| P0084 | LOW | B2 | 10D | INSUFFICIENT_SAMPLE | 70 | 18240 | — | — | — | [—,—] | — | — |
| P0083 | LOW | B2 | 5D | INSUFFICIENT_SAMPLE | 70 | 18245 | — | — | — | [—,—] | — | — |
| P0086 | LOW | B3 | 10D | INSUFFICIENT_SAMPLE | 66 | 3295 | — | — | — | [—,—] | — | — |
| P0085 | LOW | B3 | 5D | INSUFFICIENT_SAMPLE | 66 | 3294 | — | — | — | [—,—] | — | — |
| P0088 | LOW | B4 | 10D | INSUFFICIENT_SAMPLE | 46 | 2248 | — | — | — | [—,—] | — | — |
| P0087 | LOW | B4 | 5D | INSUFFICIENT_SAMPLE | 46 | 2248 | — | — | — | [—,—] | — | — |
| P0090 | NORMAL | B1 | 10D | VALID_SAMPLE | 585 | 180853 | -0.400% | 0.0194 | 0.1166 | [-0.8638%,-0.0026%] | 0.0034 | 0.0254 |
| P0089 | NORMAL | B1 | 5D | VALID_SAMPLE | 585 | 180958 | -0.306% | 0.0061 | 0.0581 | [-0.5838%,-0.0985%] | 0.0000 | 0.0052 |
| P0092 | NORMAL | B2 | 10D | VALID_SAMPLE | 576 | 74011 | -0.442% | 0.0132 | 0.0878 | [-0.9271%,-0.0270%] | 0.0094 | 0.0196 |
| P0091 | NORMAL | B2 | 5D | VALID_SAMPLE | 576 | 74034 | -0.344% | 0.0061 | 0.0581 | [-0.6653%,-0.0970%] | 0.0000 | 0.0052 |
| P0094 | NORMAL | B3 | 10D | VALID_SAMPLE | 524 | 22399 | -0.576% | 0.0008 | 0.0400 | [-1.0097%,-0.1910%] | 0.0024 | 0.0070 |
| P0093 | NORMAL | B3 | 5D | VALID_SAMPLE | 524 | 22392 | -0.345% | 0.0061 | 0.0581 | [-0.6555%,-0.0581%] | 0.0036 | 0.0088 |
| P0096 | NORMAL | B4 | 10D | VALID_SAMPLE | 360 | 4973 | -0.721% | 0.0020 | 0.0400 | [-1.2183%,-0.3100%] | 0.0134 | 0.0294 |
| P0095 | NORMAL | B4 | 5D | VALID_SAMPLE | 360 | 4969 | -0.552% | 0.0018 | 0.0400 | [-0.9193%,-0.2130%] | 0.0154 | 0.0126 |
