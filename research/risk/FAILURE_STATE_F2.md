# FAILURE-STATE ACTIONABILITY / PERFECT-INFORMATION VALUE BOUND — PHASE F2

**状态：DEVELOPMENT DIAGNOSTIC — WAITING EXTERNAL AUDIT（未写入 README CURRENT TRUTH）**
**F2-A Registry commit：`4e088fbf93adbe5c3340971d659fcc9843fb212e`**
**F2 Registry SHA256：`9ed07a575ae65bbda3d63321e676431231d00548bb8977fb443764163b85642a`**
**开发样本：2020-01-01 ~ 2024-12-31（2025–2026 Confirmation 全程 CLOSED）**

---

## 0. 结论

**F2 classification：D — ACTIONABILITY NEGATIVE**

即使 F1/F1.1 已确认 failure/recovery 状态前瞻可识别（A），在冻结执行语义（D20 锚点后第一个可执行 open 卖出）下，**即使拥有完美 oracle 也无法改善 expectancy——平均反而显著变差**。真实执行系统的容错空间为负（break-even FPR 无解）。这是一个 **oracle upper bound / actionability bound / value-of-information diagnostic**，不是策略。

## 1. 为什么（机制）

BB 策略的 edge 恰恰来自深跌后的均值回归反弹。D20 锚点是**日内最低点首次触达**，其后即使最终失败的 episode 也通常先反弹，而自然 BB 退出（动态 P* TP / BB exit）**发生在反弹之后**。因此在 D20 后立刻卖出（anchor+1 open），等于卖在反弹前的低点区域，系统性错失自然路径——即使"知道"它是最终 loser 或永不恢复者。

这与整条研究链自洽：S0（11 档固定止损全部有害）→ F1（D20 后仍有 36.7% 最终盈利）→ F2（完美 oracle 提前退出仍有害）。

## 2. Oracle 定义与执行（冻结）

- **O0**：自然冻结 BB 退出（baseline）。
- **O1** PERFECT FINAL-LOSER：最终自然 return≤0 → 提前退出；否则自然。
- **O2** PERFECT NON-RECOVERY-CLOSE：永不 RECOVER_CLOSE → 提前退出；否则自然。
- **O3** PERFECT NON-RECOVERY-TOUCH：永不 RECOVER_TOUCH → 提前退出；否则自然。
- **Primary 执行**：anchor+1 第一个可执行 open（T+1、非停牌、open>limit_down_px 可卖），按真实 open×（1−SLIP），卖出费用与 frozen engine 一致。
- **Sensitivity**：anchor-close（不可执行乐观参考）。

## 3. 完美 oracle headline（D20，n=12,590，752 anchor days）

| oracle | failure prevalence | mean baseline | mean oracle | eventday Δ | day-level HAC CI | calendar boot CI |
|---|---|---|---|---|---|---|
| O1 | 63.3% | −3.80% | −6.42% | **−2.28pp** | [−3.04, −1.52] | [−3.03, −1.44] |
| O2 | 87.9% | −3.80% | −11.76% | **−5.19pp** | [−6.19, −4.19] | [−6.26, −4.09] |
| O3 | 83.5% | −3.80% | −10.77% | **−4.81pp** | [−5.78, −3.85] | [−5.87, −3.74] |

**全部显著为负**。退出比例越高（O2/O3），伤害越大。

**Anchor-close 乐观 sensitivity（不可执行）**：O1 在锚点当日收盘卖出 eventday Δ 仍为 **−1.69pp**（优于 anchor+1 的 −2.28，但仍显著有害）——提前离场方向整体无价值。

## 4. True-positive benefit / False-positive cost

**True-positive benefit**（正确提前退出最终 loser，n=7,974）：
- mean **−4.13pp**（oracle 提前退出最终 loser 平均反而多亏 4.13pp）、median −6.07pp、P90 +9.16pp。
- 即：约 90% 的最终 loser 在 D20 后反弹，提前退出有害；仅尾部 ~10% 真继续崩者提前退出受益。

**False-positive cost**（误杀本可恢复/盈利者，oracle−natural）：
- RECOVER_CLOSE：mean **−30.3pp**（median −29.5）
- RECOVER_TOUCH：mean **−28.3pp**
- FINAL_PROFIT：mean **−24.6pp**（median −22.4, P90 −13.5）

**benefit/cost 比率**：|TP|/|FP| ≈ 4.1/24.6~30.3 ≈ **0.14~0.17**，且 TP 本身为负——误杀成本远超任何"正确退出"收益，且正确退出本身也无收益。

## 5. Confusion-value grid（无 predictor 的经济价值曲线）

| TPR＼FPR | 0 | .05 | .10 | .20 | .30 | .50 | 1.00 |
|---|---|---|---|---|---|---|---|
| .25 | −0.57 | −0.78 | −0.97 | −1.36 | −1.77 | −2.56 | −4.56 |
| .50 | −1.14 | −1.34 | −1.54 | −1.94 | −2.34 | −3.13 | −5.13 |
| .75 | −1.71 | −1.91 | −2.11 | −2.51 | −2.90 | −3.70 | −5.70 |
| 1.00 | −2.28 | −2.48 | −2.68 | −3.08 | −3.48 | −4.27 | −6.27 |

**全部 28 个 cell 均为负**：TPR 越大越负（正确退出也有害），FPR 越大越负。任何真实分类器（任意 TPR/FPR 组合）都产生负 delta。
- TPR=.50 / FPR=.20：expected Δ **−1.94pp**，CI [−2.21, −1.66]（显著负）
- TPR=.75 / FPR=.10：expected Δ **−2.11pp**，CI [−2.34, −1.89]（显著负）

## 6. Break-even frontier（无解）

| TPR | break-even FPR | grid 上最大可容忍 FPR | break-even precision |
|---|---|---|---|
| .25 | **−0.073**（无解） | 0 | 1.20（>1，无解） |
| .50 | **−0.145**（无解） | 0 | 1.20 |
| .75 | **−0.218**（无解） | 0 | 1.20 |
| 1.00 | **−0.291**（无解） | 0 | 1.20 |

即使 FPR=0（零误杀、只退出确认的失败者），expected delta 仍为负——因为正确退出本身有害。**break-even FPR 为负说明不存在任何值得部署的提前退出执行系统。**

## 7. 资本释放（真实存在但不足以构成价值）

- 每笔正确退出的失败者平均释放 **36.8 天**（median 29 天），合计 293,537 capital-days。
- 这是"potential capital-release value"，但独立 episode expectancy 为负；按 pre-registration，不得据此宣称 K=3 组合改善（未做组合回测）。

## 8. Layer subset（描述性，不改 layers）

| bucket | n | O1 mean Δ | baseline |
|---|---|---|---|
| layer 1 | 984 | −5.28pp | +0.41% |
| layer 2 | 2,669 | −3.50pp | +0.25% |
| layer 3+ | 8,937 | −2.06pp | −5.47% |

加仓越少，提前退出越有害（单层仓位自然反弹路径最充分）；layer 3+ 已深度平均加仓、baseline 本身差，提前退出的相对伤害较小。全部为负。

## 9. R01/R05 overlay（描述性，不建 gate）

- R01 弱市 Q1 Δ −2.84pp vs 强市 Q5 −1.93pp；R05 压力 Q5 −3.46pp vs 低压力 Q1 −1.19pp——各档均为负，方向不改变结论。

## 10. Sanity

- 2025–2026 未读取（锚点/退出/收益全部 ≤2024-12-31，硬 i<N2024 限制）。
- F1 / F1.1 / F2 三个 Registry SHA256 均 assert 未变。
- 无 predictor、无 stop、无 exit 修改、无 threshold 优化、无 ML/composite。
- oracle 为 hindsight upper-bound，禁止称 strategy。

## 11. 交付物

```
research/risk/registries/FAILURE_STATE_F2_ACTIONABILITY_REGISTRY.csv (+ .sha256, commit 4e088fb)
research/risk/failure_state_f2.py
research/risk/FAILURE_STATE_F2.md
results/evidence/f2/f2_oracle_episode.csv
results/evidence/f2/f2_oracle_summary.csv
results/evidence/f2/f2_eventday.csv
results/evidence/f2/f2_calendar_bootstrap.csv
results/evidence/f2/f2_tp_benefit.csv
results/evidence/f2/f2_fp_cost.csv
results/evidence/f2/f2_confusion_value_grid.csv
results/evidence/f2/f2_break_even_frontier.csv
results/evidence/f2/f2_precision_recall.csv
results/evidence/f2/f2_capital_days.csv
results/evidence/f2/f2_layer_subset.csv
results/evidence/f2/f2_market_state.csv
results/evidence/f2/f2_summary.json
```

**结论一句话**：failure state 可识别（F1/F1.1 A），但按当前冻结执行语义，提前退出在平均意义下**连完美 oracle 都是负价值**（F2 D）——真实执行系统不仅需要不可能达到的精度，而且正确退出本身就在破坏 BB 的均值回归 edge。
