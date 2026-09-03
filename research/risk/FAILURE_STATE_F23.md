# POLICY-VALUE SAMPLING INFERENCE — PHASE F2.3

**状态：DEVELOPMENT DIAGNOSTIC — WAITING EXTERNAL AUDIT（未写入 README CURRENT TRUTH）**
**R0.7 commit：`79ce71845ca90636fae6ee0f99462c1a5e854371`（F2.2 point 数学 ACCEPTED；policy-value CI/safe frontier 待 F2.3）**
**F2.3-A Registry commit：`73b9c192de07febcc49fc5208eb3f2f5a4be73d5`**
**F2.3 Registry SHA256：`c0f4d1d2bd46a7c5bca01752020dec121404984feb8273984a5164f56942f83c`**
**样本：2020-2024 Development，D20 anchors（2025–2026 CLOSED）**

---

## 0. 结论

**F2.3 完成 policy-value 的历史采样推断；F2.1/F2.2/F2.3 最终 classification 仍为 B — NARROW POSITIVE ACTIONABILITY。**

- 确定性政策日值 `V_d(t,f) = t·A_d + f·B_d`（无需随机 classifier flag）；point = mean(V_d) 与 `tA+fB` **机器精度一致（<1e-12）**。
- **Perfect-label O1（TPR=1/FPR=0）parity PASS**：point +1.4485803535、HAC CI [+0.4767, +2.4205]、calendar bootstrap CI [+0.4027, +2.6072] —— 与 F2.1 冻结参考值完全一致。
- **纳入历史 anchor-day 采样不确定性后，统计显著窗口显著收窄**：calendar-safe frontier 为 **0.00 / 0.05 / 0.10 / 0.10**（TPR .25/.50/.75/1），HAC-safe 一致（confirmatory）。
- 旧 f21 randomization interval 降级为 **conditional randomization interval（reference only）**：其 safe frontier（0.05/0.10/0.30/0.30）**系统性偏宽**，不能再作 primary safe frontier。
- point break-even（0.13496/0.26993/0.40489/0.53986）与 break-even precision（0.76190）**冻结未变**。

## 1. 为什么抽样 CI 比 randomization 更宽

- 旧 f21 CI：在**固定历史样本**上反复随机 TP/FP flag（B=2000）——只反映 classifier 随机化的条件分布，**不包含**"历史这些 anchor 日只是众多可能历史中的一次实现"的采样不确定性。
- F2.3 primary：`V_d` 序列本身携带全部经济信息（T+1 可执行 open 成交、matched 自然退出、752 个 anchor 日的收益实现），对其做 **full-calendar moving-block bootstrap（L=21, B=2000, seed=0）**，把历史采样不确定性计入。V_d 日序列标准差大（±几 pp），block 重采样后 CI 显著变宽。
- 结果：之前 randomization 下"显著正"的格点（如 TPR=.75/FPR=.30：randomization CI [+0.041, +0.524]）在 sampling 下变为跨 0（CAL [−0.599, +1.227]）。

## 2. 全网格（point / HAC / calendar bootstrap）

| TPR＼FPR | 0 | .05 | .10 | .20 | .30 | .50 | 1.00 |
|---|---|---|---|---|---|---|---|
| **.25** point | +0.362 | +0.228 | +0.094 | −0.175 | −0.443 | −0.979 | −2.321 |
| CAL CI | **[0.10,0.65]** | [−0.05,0.53] | [−0.20,0.41] | [−0.50,0.17] | [−0.81,−0.06] | [−1.46,−0.51] | [−3.11,−1.60] |
| **.50** point | +0.724 | +0.590 | +0.456 | +0.188 | −0.081 | −0.617 | −1.959 |
| CAL CI | **[0.20,1.30]** | **[0.05,1.19]** | [−0.09,1.06] | [−0.40,0.82] | [−0.69,0.58] | [−1.31,0.12] | [−2.93,−1.02] |
| **.75** point | +1.086 | +0.952 | +0.818 | +0.550 | +0.281 | −0.255 | −1.597 |
| CAL CI | **[0.30,1.96]** | **[0.15,1.84]** | **[0.00,1.72]** | [−0.29,1.47] | [−0.60,1.23] | [−1.18,0.74] | [−2.76,−0.39] |
| **1.00** point | +1.449 | +1.314 | +1.180 | +0.912 | +0.644 | +0.107 | −1.235 |
| CAL CI | **[0.40,2.61]** | **[0.25,2.49]** | **[0.11,2.37]** | [−0.18,2.12] | [−0.48,1.88] | [−1.08,1.40] | [−2.62,0.25] |

（HAC CI 与 CAL CI 方向一致、宽度相近；下界见 key cells 表。）

## 3. Key cells（10 个重点格点）

| cell | point | HAC CI | Calendar CI | Randomization CI（ref） |
|---|---|---|---|---|
| .25 / .05 | +0.228 | [−0.024, +0.480] | [−0.046, +0.531] | [+0.016, +0.427] |
| .25 / .10 | +0.094 | [−0.170, +0.358] | [−0.200, +0.409] | [−0.120, +0.319] |
| .50 / .10 | +0.456 | [−0.049, +0.961] | [−0.092, +1.062] | [+0.201, +0.708] |
| **.50 / .20** | +0.188 | [−0.341, +0.716] | [−0.399, +0.818] | [−0.055, +0.440] |
| .50 / .30 | −0.081 | [−0.638, +0.476] | [−0.685, +0.576] | [−0.352, +0.194] |
| .75 / .20 | +0.550 | [−0.218, +1.318] | [−0.288, +1.469] | [+0.310, +0.780] |
| **.75 / .30** | +0.281 | [−0.511, +1.074] | [−0.599, +1.227] | [+0.041, +0.524] |
| .75 / .50 | −0.255 | [−1.107, +0.596] | [−1.181, +0.742] | [−0.501, +0.005] |
| 1.00 / .30 | +0.644 | [−0.388, +1.676] | [−0.485, +1.879] | [+0.516, +0.761] |
| 1.00 / .50 | +0.107 | [−0.978, +1.192] | [−1.081, +1.396] | [−0.028, +0.244] |

**观察**：所有非完美格点的 sampling CI 均大幅宽于 randomization CI；`.75/.30` 与 `1.00/.30` 由 randomization 显著正变为 sampling 跨 0。

## 4. Safe frontier（三种口径）

| TPR | **Calendar-safe（PRIMARY）** | HAC-safe（confirmatory） | Randomization-safe（reference only） |
|---|---|---|---|
| .25 | **0.00**（仅 FPR=0） | 0.00 | 0.05 |
| .50 | **0.05** | 0.05 | 0.10 |
| .75 | **0.10** | 0.10 | 0.30 |
| 1.00 | **0.10** | 0.10 | 0.30 |

point break-even（F2.2 冻结）与统计显著 frontier 现在分得很清楚：例如 TPR=.75 时 point 可容忍 FPR 40%，但统计显著只能容忍 10%。

## 5. Classification（规则未改）

- A gate：TPR=.50/FPR=.20 calendar CI lower = **−0.399 < 0**（HAC lower −0.341 < 0）→ **A FAIL**。
- Perfect-label O1：calendar CI [+0.403, +2.607]（lower>0）且 HAC CI [+0.477, +2.420]（lower>0）→ **B**。
- **FINAL = B — NARROW POSITIVE ACTIONABILITY**（与 F2.1/F2.2 一致，现在带完整历史采样推断支撑）。

## 6. Parity / Invariants（全部 PASS）

- **I4**：28 个 cell 的 |point − (tA+fB)| 全部 < 1e-12。
- **I5**：TPR=1/FPR=0 精确复现 O1 eventday 序列（point 1.4485803535；HAC [0.4767,2.4205]；CAL [0.4027,2.6072]）。
- **I2/I3**：A/B 与 F2.2 冻结值逐位一致（<1e-12）；point break-even/precision 未动。
- **I6**：full-calendar moving block L=21、B=2000、seed=0。
- **I7**：primary sampling CI 不含任何 classifier 随机抽取（V_d 确定性）。
- **I1/I8/I9/I10**：matched_delta 未变；F1/F1.1/F2/F2.1/F2.2 Registry SHA 全不变；2025+ 未读；无 predictor/stop/new timing。

## 7. 措辞边界

- "TPR=.75/FPR=.30 显著正"（旧 randomization 口径）**不再成立**——sampling 下跨 0。
- 正确表述：**统计显著只能容忍 FPR ≤ 5%（TPR=.5）或 ≤ 10%（TPR=.75/1）**；point 意义上容忍度更高（0.27/0.40/0.54）。
- 仍为 perfect-hindsight 诊断、非策略、不可实盘；不得推广为"state-aware exit 可行"。

## 8. 交付物

```
research/risk/registries/FAILURE_STATE_F23_POLICY_VALUE_INFERENCE_REGISTRY.csv (+ .sha256, commit 73b9c19)
research/risk/failure_state_f23.py
research/risk/FAILURE_STATE_F23.md
results/evidence/f23/ (8 files: policy_day_values / grid_hac / grid_calendar_bootstrap /
  randomization_vs_sampling / safe_frontier / key_cells / invariants.json / summary.json)
```

**结论一句话**：把历史 anchor-day 采样不确定性真正算进去以后（full-calendar block bootstrap），failure-state 立即清仓的统计显著窗口为 TPR=.5→FPR≤5%、TPR=.75/1→FPR≤10%（point 意义上仍 27%/40%/54%）；完美标签 O1 依旧显著正（+1.45pp，CAL [0.40,2.61]），因此最终评级 **B — NARROW POSITIVE ACTIONABILITY**：正价值存在但仅对接近完美的识别精度成立，不能支持可部署策略。
