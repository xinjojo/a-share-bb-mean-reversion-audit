# STOP_LOSS_SEMANTICS_S0.md — 固定止损复权语义修复（Adjusted-Space Stop Semantics Remediation）

> **阶段：** S0 — SEMANTICS REMEDIATION + EXACT REPLICATION（不是优化、不是新策略）
> **样本：** 2020–2024 DEVELOPMENT ONLY（dev SECONDARY episodes n=61,828；signal≤2024-12-31 且 exit≤2024-12-31）
> **2025–2026 Confirmation：** CLOSED（I6，全脚本从未读取）
> **Registry：** `research/execution/registries/STOP_LOSS_SEMANTICS_S0_REGISTRY.csv`（SHA256 `7e8416fd4fc3a3f67da41d020747ffda34aaf8b1e230ddf574c131ab30f36273`，pre-reg `b352f77`，结果前 commit+push）
> **状态：** **A — OLD PHASE-A CONCLUSION ROBUST TO SEMANTICS FIX**（DEVELOPMENT DIAGNOSTIC，等待外部审计）
> **Canonical 上游：** `research/execution/STOP_LOSS_COUNTERFACTUAL_PHASE_A.md`（Phase A，PROVISIONAL / SEMANTICS ISSUE）
> **关键结论（一句话）：** 修正复权语义后，"固定止损无用"的 Phase A 结论**仍然成立**——11 档 adjusted-space 固定止损全线仍显著差于 no-stop baseline，且 adjusted 与 old raw 结果差异极小（<0.03pp），语义修复没有改变方向性结论。

---

## 1. 背景：Phase A 遗留的语义问题

Phase A 旧实现（`stop_loss_counterfactual_phase_a.py` 的 `run_cf`）使用：

```
stop_raw = first_entry_raw * (1 + stop_pct)
```

然后在整个持仓期直接与 **raw OHLC** 比较。这在持仓期内发生：

- 分红 / 送转 / 拆股
- `adj_factor` 变化

时，raw 价格会因除权而跳变，导致 stop 触发判断在错误的价格坐标系中进行（错误触发或漏触发）。该问题此前被标记为 **PROVISIONAL / SEMANTICS ISSUE**，从未正式关闭。

S0 的目标**不是优化 stop**，而是：把 stop 触发判断移到 **adjusted price space**（`entry_adj = entry_raw × entry_adj_factor`；`stop_adj = entry_adj × (1+s)`；逐日 `low_adj_d = low_raw_d × adj_factor_d`），在**完全冻结的原始阈值网格**下做精确复刻，回答：方向性结论是否稳健。

---

## 2. 冻结网格与语义（与 Registry 完全一致）

- **Frozen grid（11 档，Phase A canonical §1 权威列表，不得新增）：** −10 / −12.5 / −15 / −17.5 / −20 / −22.5 / −25 / −27.5 / −30 / −35 / −40%
- **Same-bar 歧义：** 日线同一天 stop 与 dynamic TP 均可触发时，Primary = **STOP_FIRST**；TP_FIRST 作为 sensitivity bound（两者差异微小，见 §7）。
- **Gap 执行：** `open_adj_d < stop_adj` 时按 `open_raw_d` + frozen slippage/cost 成交；否则按理论 `stop_raw_d = stop_adj / adj_factor_d` + tick/涨跌停/T+1/停牌可成交语义。
- **信息时点：** 全部 ≤ T close；I6 强制 fetch 边界截断在 2024-12-31（`MAX_READ_I = N2024`）。
- **执行规则：** 与 frozen STRICT_C 完全一致（T+1、100 股 lot、PIT ST、listing≥60、dynamic P\*、fees、slippage 10bp）。

---

## 3. 旧引擎精确复刻（Old Raw Parity）

对 61,828 个 dev SECONDARY episode，用逐字复刻 Phase A raw 逻辑（`run_cf_old`，前 9 列、无 adj 列）与 canonical `stop_phaseA_episode_detail.csv.gz`（SECONDARY、dev keys）逐条比对（22 个 stop×bound 组合，共 1,360,216 行）：

- **20/22 组合完全 exact**（`max_abs_ret_diff ≈ 7.1e-15`，机器精度级）。
- **唯一差异：−25% 档 1 个 episode（002789.SZ / 2024-02-02）在 STOP_FIRST 与 TP_FIRST 各 1 条 mismatch。**

### 3.1 002789 差异 — 2025 边界污染（如实披露，非引擎 bug）

| 项 | canonical（全样本 2020–2026） | S0 dev（截断 2024-12-31） |
|---|---|---|
| cf_ret（−25%） | **−27.109%** | **−4.278%** |
| mae_cf | **−30.561%** | −25.102% |
| trig / gap | 1 / 1 | 1 / 0（pending=1） |
| 触发依赖价格 | **2025-01-24 low=6.36**（=base×0.6944，精确对应 mae −30.56%） | 2024 年内 min low=7.52 |

根因：该 episode 的 stop layer 因 **T+1 未解锁 + 2024 年内跌停/停牌无法成交**，在 canonical 全样本语义下延迟到 **2025-01-24**（low=6.36）才以 gap 价 6.45 成交，造成 −27.11% 大亏；S0 按 I6 红线严格截断 2024-12-31，该 layer 以 2024 年内最后一次可结算价结算（−4.28%）。**同一引擎（`run_cf_old`）+ 同一 rows，仅 fetch 边界不同即可复现 canonical 精确结果**，证明差异完全来自"canonical 全样本结果中该 episode 依赖 2025 价格"这一**已知边界差异**，而非实现 bug。

S0 parity 逻辑据此增加 **BOUNDARY_2025 判定**：canonical `mae_cf` 深于 dev 窗口内可达最低（`canon_mae < dev_mae`）或 `canon_trig=1 & dev_trig=0`，即判为 canonical 依赖 2025+ 价格，从严格 parity 中**排除并单独披露**（不读 2025，仅用 dev 可达底比较）。最终：

```
OLD PARITY PASS = True
true_mismatch = 0
boundary_2025 = 2（=1 episode × STOP_FIRST/TP_FIRST）
```

> 文档层面如实记录 canonical 该单点结果依赖 2025 数据；**不修改历史 CSV**。

---

## 4. Adj-factor 语义审计（`s0_adjfactor_semantics_audit.csv`）

- **factor_changed episodes：** **7,492 / 61,828 = 12.12%**（持仓期内 `adj_factor` 发生变化的 episode 占比，即旧 raw 语义可能受影响的范围）。
- **old-only 触发（raw 触发、adjusted 不触发）：** **460**（全部集中在 factor_changed 子集内）
- **new-only 触发（raw 不触发、adjusted 触发）：** **0**
- **both 触发且触发日期标记一致：** **12,590**
- **触发状态完全一致（同触发/同不触发）：** 61,368 / 61,828 = **99.26%**

含义：旧 raw 语义的"错误额外触发"（460 例）全部发生在 adj_factor 变化的 episode 上，adjusted 语义消除了这些误触发；**不存在"adjusted 反而多触发"的案例**。旧 bug 的边界非常清楚：**仅影响 factor_changed 子集（12.12%）**。

---

## 5. 主结果：11 档 threshold — baseline / old raw / new adjusted

（`s0_threshold_summary.csv`；Primary = STOP_FIRST；mean episode return，%）

| stop_pct | baseline | old raw | adjusted | d_adj_base | d_adj_old |
|---|---|---|---|---|---|
| −10% | 5.099 | 2.393 | **2.407** | **−2.692** | +0.014 |
| −12.5% | 5.099 | 2.745 | **2.761** | −2.338 | +0.017 |
| −15% | 5.099 | 2.979 | **2.997** | −2.103 | +0.017 |
| −17.5% | 5.099 | 3.169 | **3.187** | −1.912 | +0.018 |
| −20% | 5.099 | 3.298 | **3.316** | −1.783 | +0.018 |
| −22.5% | 5.099 | 3.431 | **3.452** | −1.647 | +0.021 |
| −25% | 5.099 | 3.547 | **3.564** | −1.536 | +0.016 |
| −27.5% | 5.099 | 3.617 | **3.635** | −1.464 | +0.018 |
| −30% | 5.099 | 3.723 | **3.740** | −1.360 | +0.017 |
| −35% | 5.099 | 3.965 | **3.979** | −1.120 | +0.014 |
| −40% | 5.099 | 4.240 | **4.251** | −0.848 | +0.012 |

- **baseline（no stop）：mean 5.099% / median 5.471% / win 77.89% / PF 1.754 / hold 25 天。**
- **11 档 adjusted 均值全部低于 baseline**（`d_adj_base`：−2.692 ~ −0.848 pp），无一档超越 no-stop。
- **adjusted 与 old raw 差异极小**：`d_adj_old` = +0.012 ~ +0.021 pp（adjusted 平均略优约 0.016 pp，源于消除 460 例误触发），`max |d_adj_old| = 0.021 pp`——**语义修复对总体均值几乎无影响**。

> **措辞（铁律）：** 这里**不是说"某个阈值更好/最佳止损是 X%"**。只能说：**在预注册的历史网格（−10…−40%）下，每一档 adjusted-space 固定止损的均值收益都低于 no-stop baseline**。

---

## 6. 事件日统计（`s0_eventday.csv`）与 bootstrap（`s0_bootstrap.csv`）

对每档 adjusted（STOP_FIRST）做事件日（1,097 个 signal day）日级截面均值 + HAC + block bootstrap（L=21, B=2000, seed=0）：

| stop_pct | daily_mean | delta_daily_mean（adj−baseline） | delta HAC 95% CI |
|---|---|---|---|
| −10% | 1.847 | −2.195 | **[−2.656, −1.734]** |
| −12.5% | 2.122 | −1.920 | [−2.375, −1.464] |
| −15% | 2.288 | −1.754 | [−2.213, −1.295] |
| −17.5% | 2.448 | −1.594 | [−2.047, −1.142] |
| −20% | 2.594 | −1.448 | [−1.904, −0.993] |
| −22.5% | 2.695 | −1.348 | [−1.799, −0.896] |
| −25% | 2.824 | −1.218 | [−1.655, −0.780] |
| −27.5% | 2.950 | −1.092 | [−1.501, −0.684] |
| −30% | 3.028 | −1.014 | [−1.402, −0.627] |
| −35% | 3.240 | −0.802 | [−1.136, −0.468] |
| −40% | 3.429 | −0.614 | [−0.873, −0.354] |

**11 档的 adjusted−baseline 事件日 delta 全部显著为负**（delta HAC 95% CI 上界均 < 0，无一跨 0）。没有任何阈值出现稳定正净效应（`positive_stable_thresholds = []`）。

---

## 7. Same-bar 歧义 bound（`s0_samebar_bounds.csv`）

碰撞案例极少（−10% 档 7 例，其余 0–4 例）。STOP_FIRST 与 TP_FIRST 的事件日均值差异全部 ≤ 0.0012 pp——**same-bar 顺序对结果影响可忽略**，Primary=STOP_FIRST 的选择稳健。

---

## 8. Gap-stop 与执行延迟（`s0_gap_stops.csv` / `s0_execution_delays.csv`）

- **Gap-stop（open gap 穿越 stop 价）**：随阈值变宽而减少——−10% 档 19,215 例（31.1%），−40% 档 862 例（1.4%）。
- **Pending（触发但不可成交，等待结算）**：各档 4–22 例。
- **执行延迟**（触发→实际成交）：以触发后 `cf_hold` 分布近似，中位 20–25 天、P90 30–40 天（A 股 T+1/涨跌停/停牌语义下 stop 无法即时成交的体现）。

---

## 9. Saved losers / Killed winners（`s0_saved_losers.csv` / `s0_killed_winners.csv`）

| stop_pct | saved_losers old→adj | killed_winners old→adj | net old（PnL） | net adj（PnL） |
|---|---|---|---|---|
| −10% | 6,228 → 6,156 | 14,651 → 14,540 | −1.758e9 | −1.750e9 |
| −20% | 2,716 → 2,642 | 4,652 → 4,616 | −9.825e8 | −9.741e8 |
| −30% | 1,046 → 961 | 1,889 → 1,875 | −5.716e8 | −5.643e8 |
| −40% | 361 → 303 | 714 → 710 | −2.785e8 | −2.730e8 |

- 每档**被杀的赢家（killed winners）数量始终超过被救的输家（saved losers）**，且 `killed_winners` 的 PnL 损失远超 `saved losers` 的 PnL 节省 → **NET_STOP_VALUE 全档为负**。
- adjusted 语义下 saved/killed 数量略降（因消除 460 例误触发），但**方向性结论不变：任何档位的固定止损净效应仍显著为负**。

---

## 10. Deep-MAE 子集（`s0_deep_mae_subset.csv`）

- **baseline MAE < −20%（n=13,050）：** 11 档 adjusted net 全为负（−1.31 ~ −8.45 pp）——对深回撤仓位，除浅档外固定止损反而更差。
- **baseline MAE < −30%（n=6,537）：** −10% 档 adjusted net **+2.35 pp**、−12.5% 档 **+0.89 pp** 为正（极浅止损在极深回撤仓位上略有保护）；−15% 及更宽档仍为负（−0.78 ~ −12.86 pp）。

> **描述性诊断**，不构成选择阈值依据；也不改变整体分类（极深子集仅占全样本 10.6%）。

---

## 11. factor_changed vs factor_unchanged 子集（`s0_factor_changed_subset.csv`）

| group | n | old trig rate（−10%） | adj trig rate（−10%） | old_mean（−10%） | adj_mean（−10%） |
|---|---|---|---|---|---|
| **factor_unchanged** | 54,336 | **40.529%** | **40.529%**（完全一致） | 3.075 | 3.076 |
| **factor_changed** | 7,492 | 70.609% | 65.296%（−5.31pp） | −2.554 | −2.441 |

- **factor_unchanged 子集（87.88%）：old 与 adjusted 触发率逐档完全一致**（invariant I1），证明除坐标语义外无任何引擎行为改变。
- **factor_changed 子集（12.12%）：adjusted 触发率系统性低于 old**（−10% 档 −5.31pp），即 raw 语义确实在除权期间产生了误触发；adjusted 修正后这些误触发消失，子集均值略改善（−2.554 → −2.441），但仍显著为负。

> 这正是"旧 bug 边界清楚"的证据：**触发差异全部集中在 factor_changed；factor_unchanged 完全不受影响**。

---

## 12. 7 项 Invariants（`s0_invariants.json`）— 全部 PASS

| Invariant | 结果 |
|---|---|
| I1 factor_unchanged：old raw trig date == new adj trig date | **PASS** |
| I2 no-stop baseline 完全不变（ret0 逐行相同） | **PASS** |
| I3 old parity exact（见 §3） | **PASS** |
| I4 T+1 保留（无 entry 当日执行） | **PASS** |
| I5 entry/exit costs 不变 | **PASS** |
| I6 2025+ 从未读取（`MAX_READ_I=N2024` + dev-only universe） | **PASS** |
| I7 old Phase A replication exact | **PASS** |

---

## 13. 分类

依据预注册分类（`s0_summary.json`）：

- 无稳定正净效应阈值（`positive_stable_thresholds = []`）→ 非 C；
- old parity 通过 → 非 D；
- **11 档 adjusted 均值全部低于 baseline（`all_adjusted_below_baseline = true`），且 adjusted vs old 差异极小（max 0.021 pp）** → **A — OLD PHASE-A CONCLUSION ROBUST TO SEMANTICS FIX**。

### 最终裁决

> **修正复权语义后，"固定止损无用"的 Phase A 结论仍然成立。**
> 在预注册的 −10…−40% 历史网格下，adjusted-space 固定止损**每一档**的事件日净效应都显著为负（delta HAC CI 全 < 0），无任何档位有稳定正净效应；adjusted 与 old raw 结果差异 < 0.03 pp，语义修复不改变方向性结论。旧 raw 语义的误触发仅影响 factor_changed 子集（12.12%），其边界已被精确界定。

---

## 14. 红线确认

- **是否新增/优化 stop threshold：** NO（11 档网格与 Phase A 完全一致，未扫描）。
- **是否改 ranking / exit / K / layers / market gate：** NO。
- **是否触碰 2025–2026：** NO（I6，全程未读取任何 2025+ 数据）。
- **是否修改历史 CSV / 历史 Registry：** NO（历史 Phase A 结果与旧 Registry 冻结不动）。
- **是否已预注册：** YES（Registry SHA256 `7e8416fd…`，pre-reg commit `b352f77`，结果前 push）。

---

## 15. 交付物清单

**Registry：** `research/execution/registries/STOP_LOSS_SEMANTICS_S0_REGISTRY.csv`（+ `.sha256`）
**代码：** `research/execution/stop_loss_semantics_s0.py`
**结果：** `results/evidence/s0/` — `s0_old_parity.csv`、`s0_parity_2025_boundary.csv`、`s0_adjfactor_semantics_audit.csv`、`s0_threshold_summary.csv`、`s0_samebar_bounds.csv`、`s0_gap_stops.csv`、`s0_execution_delays.csv`、`s0_saved_losers.csv`、`s0_killed_winners.csv`、`s0_deep_mae_subset.csv`、`s0_factor_changed_subset.csv`、`s0_eventday.csv`、`s0_bootstrap.csv`、`s0_invariants.json`、`s0_summary.json`
**图：** `research/execution/figures/s0_threshold_means.png`
