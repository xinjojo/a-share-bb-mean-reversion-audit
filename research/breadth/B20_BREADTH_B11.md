# PHASE B1.1 — BREADTH STATISTICAL INFERENCE + CAPTURE-SEMANTICS REMEDIATION

**DEVELOPMENT DIAGNOSTIC（WAITING EXTERNAL AUDIT）** — 统计修复 + capture 语义修正

- Registry: `research/breadth/registries/B20_BREADTH_B11_REMEDIATION_REGISTRY.csv`
- Registry SHA256: `33052e7a6e607646612baafa1c4bee7c556314eec45076221613871a913dc0c9`
- Prereg commit: `bb3e123` (B1.1-A)
- Governance: B1 external audit HOLD → B1 原 B 降级为 PROVISIONAL B；本阶段修复后重新分类
- Sample / 定义：与 B1 完全一致（1110 signal days、frozen qcut labels、B20 n=63,785、PIT denominator、outcomes、market variable、yearly logic、classification gates 全部未改）

---

## 1. 修复 1 — Q5-Q1 calendar bootstrap（estimand 修正）

- **旧实现（撤销）**：Q5 return 记正、Q1 return 记负，对混合序列取 overall mean —— 不是冻结的 `mean(Q5)−mean(Q1)` estimand；旧 CI [+0.335, +2.307] 偏窄。
- **正确实现**：每个 replicate 内 `delta_b = mean(sampled Q5) − mean(sampled Q1)`（两组各 ≥1 天，否则 NA）；保留 multiplicity；L=21、B=2000、seed=0、full 2020–2024 trading calendar；quintile label 完全冻结（bootstrap 内不重切）。

| 指标 | 值 |
|---|---|
| 全样本 point（mean Q5 − mean Q1）| **+2.664291 pp**（与 B1 一致，tol<1e-12 断言通过）|
| bootstrap mean | +2.674 pp |
| bootstrap median | +2.677 pp |
| **PRIMARY CI（P2.5/P97.5）** | **[+1.102, +4.185]**（显著为正）|
| toy parity | Q5=[5,6]、Q1=[1,2] → estimand=**4.0**（signed combined=2.0，已被拒绝）✓ |

## 2. 修复 2 — Multivariate HAC sandwich

- 标准 Newey-West matrix：`Cov(β) = (X'X)⁻¹ S (X'X)⁻¹`，X=[1, RK01, MKT_RET]，L=10。
- statsmodels OLS HAC(maxlags=10) 独立 parity：**完全一致**（b1 CI 逐位吻合）。

| 系数 | OLS point | SE（matrix）| HAC 95% CI | statsmodels CI |
|---|---|---|---|---|
| b1 (rank01 breadth) | **+3.283183** | 1.1499 | **[+1.030, +5.537]** | [+1.030, +5.537] |
| b2 (MKT_RET) | −0.259462 | 17.6579 | [−34.868, +34.349] | 一致 |
| intercept | — | — | — | — |

- **旧 conditional CI [+3.267, +3.299] 正式撤销**：该 CI 错误复用了循环末尾 b2 的 var_k，极窄且不可靠。
- b1 点估计仍 ≈ +3.283（OLS 不变），修正后 CI 显著为正（lower +1.030）。

## 3. 修复 3 — Univariate rank-slope HAC（matrix 重算）

| 指标 | 值 |
|---|---|
| 旧 CI（B1 实现）| [−0.0131, +0.0190]（跨 0）—— 正式撤销 |
| **修正后 matrix HAC CI** | **[+0.00130, +0.00463]（显著为正）** |

修正后主 rank-slope HAC 不再跨 0 —— 这是从 B 升到 A 的关键条件之一。

## 4. Yearly / monotonicity / tail parity

- Yearly（与 B1 完全 parity）：Spearman 2020–2024 = +0.135 / +0.270 / +0.140 / +0.112 / +0.177（**5/5 正**）；Q5−Q1 逐年全正。
- Monotonicity：Q1→Q5 DAY_MEAN_RETURN 单调递增 ✓（parity）。
- Tail：Q5 的 MAE30 9.1% < Q1 12.5%、HOLD90 3.1% < 4.9%（高广度日 tail 更优，parity）✓。

## 5. Capture semantics（J1 / J2）

### J1 — FULL_MARKET_SIGNAL_CAPTURE_RATIO（正式更名）
= A0 actual new entries / 全市场独立 B20 信号：

| Q | Q1 | Q2 | Q3 | Q4 | Q5 |
|---|---|---|---|---|---|
| ratio | 1.78% | 0.87% | 0.24% | 0.18% | **0.037%** |

此指标**不再称为**"纯 K3 admission capture rate"。

### J2 — ACTUAL_PIPELINE_CAPTURE（frozen P5 ledger）

| Q | pipeline candidates | admitted | blocked_K | blocked_HELD | K_block_rate | admission_rate |
|---|---|---|---|---|---|---|
| Q1 | 20 | 11 | 10 | 5 | 50.0% | 55.0% |
| Q2 | 75 | 17 | 50 | 13 | 66.7% | 22.7% |
| Q3 | 95 | 11 | 60 | 21 | 63.2% | 11.6% |
| Q4 | 136 | 19 | 85 | 32 | 62.5% | 14.0% |
| Q5 | 201 | 17 | 131 | 44 | **65.2%** | **8.5%** |

**关键事实**：Q5 日全市场 B20 信号 46,310 个，但实际进入 amount Top10 pipeline 的只有 **201 个**（amount 横截面截断挡掉 99.6%）；pipeline 内被 K 挡 131 个（65.2%）、被持仓挡 44 个、成交 17 个。

### 两个经济问题的回答

1. **高 breadth 日独立 B20 signal quality 是否更高？→ YES**（修正统计后更强：bootstrap CI [+1.10,+4.18]、rank HAC [+0.0013,+0.0046]、conditional b1 CI [+1.03,+5.54]、5/5 年正、tail 更优）。
2. **高 breadth 日是否因 K3 机械损失更多 admissible candidates？→ 部分支持，且须精确化**：不是"46,310 全被 K 挡"。真实漏斗是两级：**amount Top10 横截面截断（Q5 日 46,310 → 201，-99.6%）+ K3 容量（pipeline 内 65.2% 被 K 挡）**。K_block_rate 各分位均 ~50–67%（Q5 略高），admission_rate Q5 最低（8.5%）。"17/46,310"不能作为"全部 K3 挡掉"的证据。

## 6. 分类（严格原 B1 A/B/C/D gate，修正后证据）

**A — STRONG BREADTH VALUE**

全部原 A 条件修正后成立：
1. 方向正且稳定 ✓（Q5−Q1 = +2.664pp）
2. rank-slope HAC CI lower > 0 ✓（[+0.00130, +0.00463]）
3. Q5−Q1 calendar bootstrap CI lower > 0 ✓（[+1.102, +4.185]）
4. ≥3/5 年正 ✓（5/5）
5. Q1→Q5 单调 ✓
6. 控制 market daily return 后 b1 > 0 且 HAC CI 正 ✓（[+1.030, +5.537]）
7. tail 无恶化 ✓（反而更优）

## 7. P7 gate

- B1.1 = **A** → **允许 P7（PANIC-DAY CAPACITY ARCHITECTURE）**。
- 但 J2 显示真实 bottleneck 是**两级漏斗**：amount Top10 横截面截断（最大损失）→ K3 容量。P7 若只做 dynamic K，能释放的只有 pipeline 内被 K 挡的部分（Q5 日 131/201）；真正的"机会大头"在 amount 截断层。P7 设计必须依据 J2 机制（例如 basket/并行准入或容量层与 amount 截断的联合设计），不能想当然只加 K。

## 8. Invariants

全部通过：B20 n=63,785 未变；quintile labels 未变（与 b1_quintiles.csv 边界 1e-12 断言一致）；estimand = meanQ5−meanQ1；toy=4.0；multivariate HAC 用全 X；OLS parity（statsmodels 逐位一致）；无 portfolio rerun；P5 block semantics 未改；无新阈值；2025–2026 CLOSED。
