# FAILURE-STATE PREDICTOR FEASIBILITY — PHASE F3

**状态：DEVELOPMENT DIAGNOSTIC — WAITING EXTERNAL AUDIT（未写入 README CURRENT TRUTH）**
**R0.8 commit：`a791ac002f91a7c3c306ed1574961cdc3ce2b646`（F2.1/F2.2/F2.3 正式 ACCEPTED → B — NARROW POSITIVE ACTIONABILITY）**
**F3-A Registry commit：`e7b390bc9ffd284bbe2010dfa1eab413454adbe8`**
**F3 Registry SHA256：`803e15245746a90d542de1bd18889686dacf6e926b3ac931717c68335db2a032`**
**样本：2020-2024 Development，D20 anchors（2025–2026 CLOSED）**

---

## 0. 结论

**F3 classification = C — PREDICTIVE BUT ECONOMICALLY INSUFFICIENT。**

- 前瞻预测关系**存在**：M0/M1 四个时间外推 fold 的 test AUC 全部 >0.55（M1：0.587 / 0.639 / 0.628 / 0.788）；OOF（2021–2024 严格样本外）M1 AUC **0.720**、PR-AUC **0.786**。
- 但**没有任何 model-target 组合进入 F2.3 冻结的经济可行区域**：
  - STABLE_SAFE：**0/6 组合**（所有 SAFE_REGION gate 全 fail）；
  - STABLE_POINT：**0/6 组合**（2021–2023 所有预注册 model-target 的 point EV 均为负；2024 年 M0 T50/T75 与 M1 T50/T75/T90 为正，但没有任何组合满足 STABLE_POINT/STABLE_SAFE）。
- 根因：O1 failure prevalence **63.3%** 下，模型排序力（AUC 0.6–0.7）不足以维持足够 precision；F2.3 经济门槛要求 TPR/FPR 收益比 > **1.85**（A=+1.45pp vs B=−2.68pp），T50 目标需 FPR ≤ **0.27**，而 test FPR 实际为 0.12–0.64。

## 1. 预注册设计（冻结，未偏离）

- 标签：O1_FAILURE = frozen natural `final_return <= 0`（hindsight label；特征全部 anchor-time causal）。
- 特征：仅 4 个 F1.1 冻结非冗余代表——`F_DAYS_UNDERWATER`（PATH_DURATION）、`F_RET20`（TREND）、`F_REB5`（RECOVERY）、`F_INTRADAY_RANGE`（VOLATILITY）。`F_DAYS_SINCE_LOW` 禁止入模；R01/R05/layer 仅 secondary overlay。
- 模型：M0=单特征 logistic；M1=四特征线性 logistic（L2 C=1.0，lbfgs，无交互/多项式/树/调参）。
- 评估：expanding-window 时间外推 2020→21、2020-21→22、2020-22→23、2020-23→24；imputation/standardization/threshold 全部 train-fold-only。
- Targets：T50/T75/T90（train TPR 最近目标；tie → 更高 threshold），冻结后应用到 next-year test。

## 2. Fold 结果

| model-target | 2021 AUC / TPR / FPR / EV | 2022 AUC / TPR / FPR / EV | 2023 AUC / TPR / FPR / EV | 2024 AUC / TPR / FPR / EV |
|---|---|---|---|---|
| M0-T50 | .578 / .410 / .321 / **−0.27** | .646 / .495 / .311 / **−0.12** | .588 / .766 / .636 / **−0.60** | .777 / .502 / .141 / **+0.35** |
| M0-T75 | .578 / .768 / .708 / −0.79 | .646 / .770 / .591 / −0.47 | .588 / .880 / .837 / −0.97 | .777 / .706 / .276 / +0.28 |
| M0-T90 | .578 / .921 / .887 / −1.05 | .646 / .893 / .750 / −0.72 | .588 / .940 / .908 / −1.07 | .777 / .881 / .537 / −0.17 |
| M1-T50 | .587 / .528 / .397 / −0.30 | .639 / .424 / .262 / −0.09 | .628 / .805 / .647 / −0.57 | .788 / .490 / .116 / **+0.40** |
| M1-T75 | .587 / .772 / .691 / −0.74 | .639 / .746 / .558 / −0.42 | .628 / .901 / .777 / −0.78 | .788 / .683 / .247 / +0.33 |
| M1-T90 | .587 / .938 / .904 / −1.07 | .639 / .910 / .782 / −0.78 | .628 / .948 / .864 / −0.95 | .788 / .828 / .416 / +0.08 |

- 逐年 EV：仅 **2024** 达标（M0/M1 的 T50、T75 正；M1-T90 微正 +0.08）；2021–2023 全部负。**单一年份驱动，无跨年稳定性。**
- SAFE_REGION gates（T50 需 FPR≤0.05、T75/T90 需 FPR≤0.10）：**0/24 通过**——test FPR 系统性偏高 3–13 倍。

## 3. OOF 汇总（2021–2024 严格样本外拼接）

| model-target | AUC | PR-AUC | TPR | FPR | precision | frozen point EV (pp) |
|---|---|---|---|---|---|---|
| M0-T50 | 0.708 | 0.782 | 0.527 | 0.235 | 0.787 | **+0.133** |
| M0-T75 | 0.708 | 0.782 | 0.764 | 0.448 | 0.738 | −0.096 |
| M0-T90 | 0.708 | 0.782 | 0.901 | 0.661 | 0.692 | −0.469 |
| M1-T50 | 0.720 | 0.786 | 0.526 | 0.218 | 0.800 | **+0.178** |
| M1-T75 | 0.720 | 0.786 | 0.752 | 0.419 | 0.748 | −0.034 |
| M1-T90 | 0.720 | 0.786 | 0.890 | 0.606 | 0.708 | −0.336 |

- OOF 最强组合（M1-T50）：TPR 0.526 / FPR 0.218 / precision 0.800 / EV +0.18pp —— **point 正但统计显著门槛（calendar-safe FPR≤0.05）差 4 倍以上**；T75/T90 的 EV 全负。
- OOF aggregate 是描述性汇总，不替代 fold stability gate（本 phase gate 全 fail）。

## 4. 校准（描述性，M1）

| 预测区间 | n | 预测均值 | 实际失败率 |
|---|---|---|---|
| 0.0–0.2 | 10 | 0.160 | 0.200 |
| 0.2–0.4 | 308 | 0.349 | **0.182**（高估） |
| 0.4–0.6 | 2120 | 0.515 | **0.317**（高估） |
| 0.6–0.8 | 6808 | 0.705 | 0.666（良好） |
| 0.8–1.0 | 2556 | 0.858 | 0.816（略高估） |

低概率区间系统性高估失败概率（prevalence 63% 的边际分布所致），不做 calibration fitting。

## 5. 系数符号稳定性（M1，standardized）

| fold | DAYS_UNDERWATER | RET20 | REB5 | INTRADAY_RANGE |
|---|---|---|---|---|
| 2021 | +0.457 | −0.558 | −0.012 | −0.326 |
| 2022 | +0.476 | −0.243 | −0.050 | −0.154 |
| 2023 | +0.535 | −0.137 | +0.001 | −0.245 |
| 2024 | +0.605 | −0.142 | +0.000 | −0.285 |

与 F1.1 预期 3/4 一致：DAYS_UNDERWATER 全正、RET20 全负、INTRADAY_RANGE 全负；**REB5 不显著、符号不稳定**。描述性，非调参依据。

## 6. D30 transfer（SECONDARY，不进入 primary classification）

每 fold D20 训练模型直接应用同 test year D30 anchors（不重训）：

- M1 AUC：0.584 / 0.712 / 0.722 / 0.807 —— 排序力基本保留（2024 最强）。
- T50 TPR/FPR：0.869/0.830、0.889/0.713、0.922/0.765、0.584/0.137 —— **FPR 同样系统性偏高**（2024 例外），与 D20 一致：排序存在、经济达标缺稳。

## 7. Market overlay（secondary 描述，M1-T50 OOF）

- R01 Q1（历史弱市）实际失败率最低 0.584、FNR 最高 0.516；R01 Q4 实际失败率最高 0.787。
- R05 Q5（低 limit-down share）实际失败率最低 0.539、FPR 0.167；R05 Q2 FPR 最高 0.442。
- 仅描述，不建 gate。

## 8. 为什么"可预测"但"经济不足"

1. **排序力真实但有限**：AUC 0.58–0.79（OOF 0.72）——F1.1 的 anchor-day 前瞻信息确实存在。
2. **高 prevalence 放大 precision 需求**：failure 占 63%，T50 目标下 test FPR 需 ≤0.27 才 EV>0（且统计显著需 ≤0.05）；实际 FPR 0.12–0.64。
3. **经济杠杆不对称**：A=+1.45pp vs B=−2.68pp，误杀一个恢复者 ≈ 抵消 1.85 个正确退出；要求 operating point 极高 precision。
4. **逐年不稳**：2021–2023 所有 model-target 的 EV 全负（AUC 0.59–0.65）；2024 年 M0 T50/T75、M1 T50/T75/T90 为正（AUC 0.79），但仍无 STABLE_POINT/STABLE_SAFE。

## 9. Invariants（全部 PASS）

I1 anchor-time features；I2 imputer train-only；I3 scaler train-only；I4 thresholds train-only；I5 test year 不入 fit/threshold；I6 chronological folds；I7 无 2025 读取（anchor_date max=2024-09-11）；I8 F1/F1.1/F2/F2.1/F2.2/F2.3 Registry SHA 不变；I9 M1 仅 4 冻结特征；I10 M0 仅 DAYS_UNDERWATER；I11 无 hyperparameter scan；I12 A/B 冻结。

## 10. 措辞边界

- 不得称"deployable-candidate"（A 才允许）；不得称"找到止损/卖出策略"；不得因 2024 单年正 EV 宣称经济可行。
- F3 = **C**：predictor 关系存在（AUC/校准/系数方向），但逐年时间外推下经济门槛（F2.3 frozen）无一稳定达标。

## 11. 交付物

```
research/risk/registries/FAILURE_STATE_F3_PREDICTOR_REGISTRY.csv (+ .sha256, commit e7b390b)
research/risk/failure_state_f3.py
research/risk/FAILURE_STATE_F3.md
results/evidence/f3/ (12 files: fold_metrics / fold_thresholds / fold_economic / fold_coefficients /
  oof_predictions / oof_metrics / calibration / anchor_day / stability_gate / d30_transfer /
  market_overlay / summary.json + invariants.json)
```

**结论一句话**：F1.1 的 failure-state 前瞻可识别性在真实分类器中成立（OOF AUC 0.72），但 F2.3 冻结的经济门槛（TPR/FPR 收益比 >1.85、统计显著 FPR ≤5–10%）在 63% failure prevalence 下要求过高 precision——4 个时间外推年仅 2024 年出现正 EV（M0 T50/T75、M1 T50/T75/T90），无任何预注册 model-target 组合通过 STABLE_POINT/STABLE_SAFE，故 **C — PREDICTIVE BUT ECONOMICALLY INSUFFICIENT**。
