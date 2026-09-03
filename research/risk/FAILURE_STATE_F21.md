# MATCHED-SHARE ACTIONABILITY / PERFECT-LABEL FIXED-ACTION VALUE — PHASE F2.1

**状态：DEVELOPMENT DIAGNOSTIC — WAITING EXTERNAL AUDIT（未写入 README CURRENT TRUTH）**
**F2.1-A Registry commit：`02c6738c0fe12abe784e970b5d3a38558fa6da89`**
**F2.1 Registry SHA256：`12f8311c52df76ca6fc10cb7f5f43a95bae4e1c9a9dc1f5880bfdcee60357787`**
**开发样本：2020-01-01 ~ 2024-12-31（2025–2026 Confirmation 全程 CLOSED）**

---

## 0. 结论

**F2.1 classification：B — NARROW POSITIVE ACTIONABILITY**

在 **matched-share 基准**（只对 D20 锚点当日已持有的同一批股份 S_anchor、同一资本基准 C_anchor 比较）下：

- **O1（完美最终-loser 标签）**：D20+1 首个可执行 open 全仓清仓 **平均改善 +1.45pp**（day 等权 eventday delta），HAC CI [0.48, 2.42]、calendar block bootstrap CI [0.40, 2.61] —— **显著为正**；
- 但真实分类器网格 **TPR=.50 / FPR=.20 的期望 delta 为 +0.19pp、CI [−0.06, +0.44]（跨 0）**——A gate 失败；
- **break-even 精度极高**：TPR=.50 时 break-even FPR 仅 **0.080**（误杀率超过 8% 即无正期望），break-even precision ≈ **0.96**。

即：完美识别最终失败者后立即清仓**确实有经济价值**（纠正了 F2 的负结论），但该价值窗口**极窄**——执行系统需要接近完美的 precision，任何实质性误杀恢复者都会抹掉全部价值。

## 1. 为什么与 F2 相反（P0 修复的实质）

F2 无效的原因是 **capital-basis mismatch**：
- F2 的 baseline ret0 = final PnL / FINAL TOTAL COST，**分母包含 D20 之后发生的 future adds**（加仓摊薄了亏损率）；
- F2 的 oracle return = early-exit PnL / ANCHOR TOTAL COST，只含锚点已持资本；
- 两者比较了不同股份数、不同资本基准、不同未来资本承诺 → "提前退出有害"是**伪结论**。

**F2.1 污染量化**：D20 样本中 **57.0%（7,174/12,590）存在 D20 后 future add**；ret0 与 matched natural return 的平均差 **+4.77pp**（P95 +17.1pp）——即原 F2 的 baseline 平均被高估约 4.8pp（O1 fail 子集 +3.67pp、recovery 子集 +6.68pp）。

matched natural baseline 本身：**mean −8.58%**（S_anchor 在自然退出点卖出平均亏 8.58%），远深于 F2 显示的 −3.80%。

## 2. 方法（冻结）

- **S_anchor** = anchor_i 当日已持有的股份（layer_i ≤ anchor_i 的层加总）；**C_anchor** = 这些层的实际获取成本（含买入费）。
- **natural_matched_return** = (S_anchor × 自然退出执行价（含滑点）− 卖出费 − C_anchor) / C_anchor。自然退出执行价**直接从本地 replay instrument**（TAKE_PROFIT_DYN / TAKE_PROFIT_UB / FINAL_SETTLE 的实际成交价，float64），**61,828 个 dev episode 全部 exact parity**（pnl 重算与 pnl0 差 <0.01 元，实际 0 误差）。
- **early_return** = S_anchor 在 anchor+1 首个可执行 open（T+1、非停牌、open>跌停价、真实 open×(1−SLIP)）全仓卖出的 matched 收益。
- **matched_delta = early_return − natural_matched_return**（唯一 primary 经济 delta）。future adds 不进入 matched return（I4）。
- 标签不变（完美 hindsight）：O1 final_return≤0、O2 永不 RECOVER_CLOSE、O3 永不 RECOVER_TOUCH。

## 3. 完美标签固定动作结果（D20，n=12,590 / 752 anchor days）

| oracle | failure prevalence | mean natural matched | mean policy | eventday Δ | HAC CI | calendar boot CI |
|---|---|---|---|---|---|---|
| O1 | 63.3% | −8.58% | −8.87% | **+1.45pp** | [0.48, 2.42] | [0.40, 2.61] |
| O2 | 87.9% | −8.58% | −12.41% | −0.34pp | [−1.48, 0.80] | [−1.57, 0.99] |
| O3 | 83.5% | −8.58% | −11.64% | −0.09pp | [−1.20, 1.02] | [−1.28, 1.19] |

- **O1 显著为正**：完美识别最终 loser 后立即清仓有价值。
- **O2/O3 接近 0（不显著）**：这两个标签覆盖 84–88% 的 D20 样本（含大量最终恢复者），提前退出对混合样本无净价值。
- **D30 secondary**：O1 −0.87pp（跨 0）、O2 −2.30pp（显著负）、O3 −2.15pp（显著负）——越深越晚的锚点，清仓价值消失（已错过反弹起点）。

## 4. True-positive / False-positive（matched 口径）

- **TP benefit**（正确退出最终 loser，n=7,974，全部可执行）：mean **−0.46pp**、median −2.92pp、P90 **+14.30pp**。即：约半数最终 loser 提前退出轻微亏损（它们仍会先反弹），但尾部 ~10% 大幅受益；整体近中性。对比 F2 的 −4.13pp（被分母污染夸大）。
- **FP cost**（误杀恢复者，matched 口径）：RECOVER_CLOSE **−25.0pp**、RECOVER_TOUCH **−23.0pp**、FINAL_PROFIT **−17.9pp**（机会成本 17.9–25.0pp）。误杀成本依然巨大。
- **benefit/cost 结构**：TP 近中性（±0.5pp）而 FP 成本 18–25pp —— 任何 FPR>0 都会快速吞噬 TP 的价值，这正是"极窄窗口"的来源。

## 5. Confusion-value grid（matched delta，MC B=2000 anchor-day clustered）

| TPR＼FPR | 0 | .05 | .10 | .20 | .30 | .50 | 1.00 |
|---|---|---|---|---|---|---|---|
| .25 | +0.36 | +0.22 | +0.09 | −0.17 | −0.45 | −0.98 | −2.32 |
| .50 | +0.73 | +0.59 | +0.46 | +0.19 | −0.08 | −0.61 | −1.96 |
| .75 | +1.09 | +0.95 | +0.82 | +0.55 | +0.28 | −0.25 | −1.60 |
| 1.00 | +1.45 | +1.32 | +1.18 | +0.91 | +0.64 | +0.11 | −1.24 |

- **TPR 边际为正**（完美识别有正价值）：TPR=1/FPR=0 → **+1.45pp**。
- **FPR 边际为负**：每 5% 误杀约损失 0.13pp。
- TPR=.50 / FPR=.20：+0.19pp，CI [−0.06, +0.44]（跨 0）；TPR=.75 / FPR=.10：+0.82pp，CI [0.59, 1.03]（显著正）。

## 6. Break-even frontier（day-等权口径，与 MC 网格一致）

| TPR | break-even FPR（线性） | on-grid 最大可行 FPR | break-even precision |
|---|---|---|---|
| .25 | **0.040** | 0.10 | 0.962 |
| .50 | **0.080** | 0.20 | 0.962 |
| .75 | **0.120** | 0.30 | 0.962 |
| 1.00 | **0.160** | 0.50 | 0.962 |

TPR 每单位贡献 +0.236pp（day 等权）、FPR 每单位成本 −1.471pp。**需要 96%+ precision 才可能保本**——这解释了 B（而非 A）：经济上有价值，但执行容错窗口极窄。

## 7. 资本释放（真实存在，与 return 分开报告）

- **A. current-position days saved**：每笔正确退出平均释放 **36.8 天**（median 29），合计 293,537 capital-days。
- **B. future-add capital avoided**：7,174 笔（57.0%）有 future add，合计未来追加资本 **21.69 亿元**（均值 17.2 万/笔）、未来加仓资本占用 **343,569 capital-days**（均值 27.3 天/笔）。—— 提前清仓同时避免了后续加仓的资本承诺；这是独立于 return 的资本效率事实。

## 8. Layer / Market overlay（描述性，不改任何规则）

- **anchor layers**（eventday O1 delta）：layer1 +0.74pp / layer2 +1.47pp / layer3+ +1.13pp —— 各档均为正；future-add 发生率 layer1 68.4% / layer2 72.9% / layer3+ 51.0%。
- **R01**（eventday）：Q1 弱市 +0.17pp、Q2 +1.93、Q3 +1.05、Q4 +2.97、Q5 强市 +2.99 —— 强弱市均为正；**R05**：Q1 +2.32 … Q5 压力市 −0.28 —— 压力极值档略负，其余为正。不建 gate。
- **anchor-close 乐观（不可执行）**：O1 eventday **+2.04pp**（优于 anchor+1 的 +1.45，方向一致）。

## 9. Sanity / Invariants（全部 PASS）

I1 S_anchor 两腿一致 / I2 C_anchor 同一分母 / **I3 自然退出执行价 replay parity exact（61,828/61,828，0 误差）** / I4 future layers 排除出 matched primary / I5 提前执行规则冻结 / I6 费用滑点冻结 / I7 2025+ 未读 / I8 F1/F1.1/F2 Registry SHA 不变 / I9 无 predictor/stop/new exit。

## 10. 措辞边界

- **B 只回答**：D20+1 立即全仓清仓这一个固定动作，在完美标签下有正价值但窗口极窄。
- **禁止**推广为"所有 state-aware exit 都有价值"或"止损可行"——O2/O3 接近 0、D30 显著为负、FPR>8% 即无正期望。
- 所有 oracle/label 为 perfect-hindsight 诊断，**非策略**、不可实盘。

## 11. 交付物

```
research/risk/registries/FAILURE_STATE_F21_MATCHED_ACTION_REGISTRY.csv (+ .sha256, commit 02c6738)
research/risk/failure_state_f21.py
research/risk/FAILURE_STATE_F21.md
results/evidence/f21/ (16 files: natural_exit_parity / episode_matched / future_add_incidence /
  old_vs_corrected_basis / fixed_action_summary / eventday / calendar_bootstrap / tp_benefit /
  fp_cost / confusion_value_grid / break_even_frontier / capital_release / layer_subset /
  market_state / invariants.json / summary.json)
```

**结论一句话**：严格在 matched-share 基准上比较之后，完美识别最终失败者并次日首个可执行 open 全仓退出**平均有正价值（O1 +1.45pp 显著）**，但执行窗口极窄——误杀恢复者成本（18–25pp）远超正确退出的边际收益，真实分类器需要 ≥96% 精度（TPR=.5 时 break-even FPR 仅 8%），因此该 fixed-action 属于 **B — NARROW POSITIVE ACTIONABILITY**，不是可部署策略。
