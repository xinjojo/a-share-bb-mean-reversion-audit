# BREAK-EVEN / PRECISION REMEDIATION — PHASE F2.2

**状态：DEVELOPMENT DIAGNOSTIC — WAITING EXTERNAL AUDIT（未写入 README CURRENT TRUTH）**
**R0.6 commit：`a01aa7f307d801151c478c3198f3224630cf1415`（F2.1 break-even 模块标 INVALID，核心证据保留）**
**F2.2-A Registry commit：`a829298379956e79d34fb3ce57a15542d55df6ef`**
**F2.2 Registry SHA256：`aff9c4295fceec450a54ea7bc2bfbc8055761d396081d778d4e1ff616b6095d8`**
**样本：2020-2024 Development，D20 anchors（2025–2026 CLOSED）**

---

## 0. 结论

**F2.2 修正了 F2.1 的 break-even/precision 数学 bug；F2.1/F2.2 最终 classification 仍为 B — NARROW POSITIVE ACTIONABILITY。**

- **A（day-等权 failure 单位贡献）= +1.4486pp**；**B（day-等权 recovery 单位贡献）= −2.6833pp**（B 为负符合预期：误杀恢复者平均损失）。
- 解析期望 `TPR*A + FPR*B` 与 anchor-day 等权 MC 网格**严格一致**（max |diff| = 0.0071pp < 0.02pp gate；grid 复现与 f21 的 diff = 0.000000）。
- **修正后的 point break-even FPR：TPR=.25 → 0.135；.50 → 0.270；.75 → 0.405；1.00 → 0.540。**
- **修正后的 break-even precision = 0.762**（各 TPR 相同，因 root 与 TPR 成比例）。
- **CI-safe frontier（95% CI lower > 0）：TPR=.25 → 0.05；.50 → 0.10；.75 → 0.30；1.00 → 0.30。**
- 旧 "precision ≈ 96%"、旧 "TPR=.5 只容忍 FPR 8%" **正式撤销**（来源：错误的 pref_d×mean_d 分解）。

## 1. Root cause（审计确认）

F2.1 的 day_agg 分解错误：
```
pref_d = fail_n / n
mean_d = Σ(all matched_delta) / n     # ← 混合了 failure 和 recovery delta
a = mean(pref_d * mean_d)              # ← 错误
b = -mean((1-pref_d) * mean_d)         # ← 错误
```
`mean_d` 把两类 delta 混在一起，导致与 MC 期望不一致，并产生 "TPR=.5 break-even FPR=0.080" 与 "TPR=.5/FPR=.2 expected +0.19" 的逻辑矛盾。

正确分解（F2.2 采用，严格匹配独立随机 exit flag 的 day-等权 MC 期望）：
```
A_d = Σ_{fail}(matched_delta) / n_d      （当天无 failure → 0）
B_d = Σ_{rec}(matched_delta) / n_d       （当天无 recovery → 0）
E[day_delta | TPR, FPR] = TPR * mean(A_d) + FPR * mean(B_d)
```
752 个 anchor day 全部等权（I5）。

## 2. 正确数字（F2.2）

### 2.1 Analytic components
| 量 | 值 |
|---|---|
| A（failure 单位贡献，day-等权） | **+1.4486pp** |
| B（recovery 单位贡献，day-等权） | **−2.6833pp** |
| episode prevalence π = N_fail/N_total | **0.63336**（7,974/12,590） |

### 2.2 Point break-even frontier（修正）
| TPR | point break-even FPR（raw，clip 展示相同） | grid 线性插值 |
|---|---|---|
| .25 | **0.13497** | 0.13595 |
| .50 | **0.26993** | 0.27043 |
| .75 | **0.40489** | 0.40638 |
| 1.00 | **0.53986** | 0.54050 |

公式 `FPR_be(TPR) = TPR*A/(−B)`。TPR=.5 时 break-even FPR = 0.270 > 0.20，**通过 contradiction assert**（与 TPR=.5/FPR=.2 MC expected +0.19pp 自洽）。

### 2.3 Precision（episode-level prevalence，corrected）
| TPR | FPR=0 | .05 | .10 | .20 | .30 | .50 | 1.00 | break-even |
|---|---|---|---|---|---|---|---|---|
| .25 | 1.000 | .896 | .812 | .684 | .590 | .463 | .302 | **.762** |
| .50 | 1.000 | .945 | .896 | .812 | .742 | .633 | .463 | **.762** |
| .75 | 1.000 | .963 | .928 | .866 | .812 | .722 | .564 | **.762** |
| 1.00 | 1.000 | .972 | .945 | .896 | .852 | .776 | .633 | **.762** |

**break-even precision = 0.762**（各 TPR 相同，如实报告：root 与 TPR 成比例时 precision 与 TPR 无关）。

### 2.4 CI-safe frontier（statistically positive，95% CI lower > 0）
| TPR | 最大 safe FPR（grid） | 说明 |
|---|---|---|
| .25 | **0.05** | FPR=.10 时 expected +0.094 但 CI [−0.120, +0.319] 跨 0 |
| .50 | **0.10** | FPR=.20 时 expected +0.191 但 CI [−0.055, +0.440] 跨 0 |
| .75 | **0.30** | FPR=.30 时 expected +0.284，CI [**+0.041**, +0.524] 显著正 |
| 1.00 | **0.30** | FPR=.50 时 expected +0.109 但 CI 跨 0 |

**point-positive ≠ statistically-positive**：TPR=.5 时 point break-even 容忍 FPR 27%，但统计显著只能容忍 FPR ≤10%。

### 2.5 关键 grid 格点
| cell | expected Δ | CI | 解读 |
|---|---|---|---|
| TPR=.50 / FPR=.20 | +0.191pp | [−0.055, +0.440] | point 正但统计不显著（A gate 失败的主因） |
| TPR=.75 / FPR=.30 | +0.284pp | [+0.041, +0.524] | **point 正且统计显著**（safe frontier 内的代表点） |
| TPR=.25 / FPR=.10 | +0.094pp | [−0.120, +0.319] | 跨 0 |

## 3. 验证

- **I2 grid 复现**：重算 MC（seed42 B=2000）与 f21_confusion_value_grid.csv 的 max |diff| = **0.000000pp**（同一逻辑同一 seed，逐格一致）。
- **I3 analytic-MC parity**：28 个 cell 的 max |analytic − MC| = **0.0071pp** < 0.02pp gate。
- **Contradiction test**：TPR=.5/FPR=.2 MC expected (+0.191) > 0 → point break-even (0.270) > 0.20，**PASS**（旧值 0.08 会被拦截）。
- **I1** matched_delta 原样复用 F2.1；**I4** precision 用 episode prevalence 0.63336（非 day-等权均值）；**I5** 全部 752 anchor days；**I6** classification 规则未改；**I7** 2025+ 未读（纯复用 f21 CSV）；**I8** F1/F1.1/F2/F2.1 Registry SHA 全不变；**I9** 无 predictor/stop/new timing。

## 4. 分类（规则不变）

A gate：TPR=.50 / FPR=.20 CI lower = **−0.055 < 0** → A fail。
O1 perfect-label（TPR=1/FPR=0）：expected +1.449pp，CI [+0.398, +2.607] 显著正 → B。
**FINAL classification = B — NARROW POSITIVE ACTIONABILITY**（F2.1/F2.2 一致）。

## 5. 修正前后对比（F2.1 旧 vs F2.2 新）

| 指标 | F2.1（错误分解） | F2.2（正确分解） |
|---|---|---|
| TPR 单位贡献 a/A | 0.2359pp | **1.4486pp** |
| FPR 单位成本 b/B | 1.4706pp | **2.6833pp** |
| TPR=.5 break-even FPR | 0.080（矛盾） | **0.270** |
| break-even precision | 0.962（作废） | **0.762** |
| grid / MC | — | 复现 0 误差、parity 0.007pp |

## 6. 措辞边界

- "TPR=.5 只容忍 FPR 8%" 已撤销；正确表述：**point break-even FPR = 27%，统计显著只容忍 10%**。
- "break-even precision ≈ 96%" 已撤销；正确表述：**break-even precision ≈ 76%**。
- 必须区分 **point break-even** 与 **CI-safe frontier**（两者不同：TPR=.75 时 point 容忍 40%、统计显著容忍 30%；TPR=.5 时 point 27%、统计显著 10%）。
- 仍是 perfect-hindsight 诊断、非策略、不可实盘；F2.1 的 O1 matched-share core evidence（+1.45pp 显著）**未被否定**，本阶段只修 break-even/precision 模块。

## 7. 交付物

```
research/risk/registries/FAILURE_STATE_F22_BREAK_EVEN_REGISTRY.csv (+ .sha256, commit a829298)
research/risk/failure_state_f22.py
research/risk/FAILURE_STATE_F22.md
results/evidence/f22/ (7 files: day_components / expected_value_formula / mc_analytic_parity /
  break_even_frontier / precision_frontier / safe_frontier / summary.json)
```

**结论一句话**：修正 break-even 数学后，D20 failure-state 立即清仓在完美标签下价值成立（TPR 单位贡献 +1.45pp、显著），point 意义上 TPR=.5 可容忍 FPR 27%、统计显著只能容忍 10%（TPR=.75 时显著容忍 30%）；所需 precision 从旧的 96% 修正为 **76%**——窗口比旧结果宽，但仍属"窄正价值"（B），不可部署。
