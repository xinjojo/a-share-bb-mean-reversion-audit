# CURRENT_STATUS.md — 当前研究真相（冻结结论总表）

> 本文档是**当前状态**的单一权威来源。研究结论按以下分类冻结：
> `ACCEPTED`（已审计通过）/ `CLOSED`（已验证失败或终止）/ `PROVISIONAL`（暂接受，有未关闭问题）/ `INVALID`（致命方法错误）/ `SUPERSEDED`（被更严格版本替代）/ `UNTOUCHED`（未触碰）。
> 每个阶段只对应**一个 canonical 报告**（见 `[RESEARCH_MAP.md](RESEARCH_MAP.md)`）。

---

## 一、冻结结论总表

| # | 阶段 | 结论 | 状态 | Canonical 报告 |
|---|---|---|---|---|
| 1 | 原始 +354.9% | INVALID（same-bar 未来信息 / ETF 时序 / PIT / 上市时间） | INVALID | `archive/invalid/RESULTS_LATEST.md` |
| 2 | STRICT_C 严格因果口径 | STRICT_C 基线成立 | ACCEPTED | `[research/signal/REDTEAM_ROUND51_STRICT.md](research/signal/REDTEAM_ROUND51_STRICT.md)` |
| 3 | 独立交易重放（Primary Top10, n=299） | mean≈+4.96% / median≈+5.22% / win≈75.9% · **Signal Layer A** | ACCEPTED | `[research/signal/INDEPENDENT_TRADE_REPLAY_V2_AUDIT.md](research/signal/INDEPENDENT_TRADE_REPLAY_V2_AUDIT.md)` |
| 4 | 全市场 SECONDARY 89,046 realized + 124 censored（1,494 signal days） | 信号结构 **A**（MAE/MFE/尾部结构泛化，Top10 未提高单笔质量） | ACCEPTED | `[research/trade_path/FULL_MARKET_TRADE_PATH_AUDIT.md](research/trade_path/FULL_MARKET_TRADE_PATH_AUDIT.md)` |
| 5 | Trade Path（描述性风险结构） | 接受：MAE 深度与最终交易质量显著相关 | ACCEPTED | `[research/trade_path/FULL_MARKET_TRADE_PATH_AUDIT.md](research/trade_path/FULL_MARKET_TRADE_PATH_AUDIT.md)` |
| 6 | Fixed Stop Phase A | **SUPERSEDED BY S0**（raw first-entry stop 的复权语义问题由 S0 adjusted-space 修复闭环；S0 已补全配对推断并外审通过，见 14d 行） | SUPERSEDED BY S0 | `[research/execution/STOP_LOSS_COUNTERFACTUAL_PHASE_A.md](research/execution/STOP_LOSS_COUNTERFACTUAL_PHASE_A.md)` |
| 7 | Temporal Clustering T1 | **A — STRONG TEMPORAL CLUSTERING**（runs z≈−11, lag1 ACF≈0.43, 盈利/亏损显著按时间成团） | ACCEPTED | `[research/market_state/TEMPORAL_CLUSTERING_PHASE_T1.md](research/market_state/TEMPORAL_CLUSTERING_PHASE_T1.md)` |
| 8 | Market State T2（Discovery） | reverse-direction discovery | ACCEPTED AS DISCOVERY | `[research/market_state/MARKET_STATE_PHASE_T2.md](research/market_state/MARKET_STATE_PHASE_T2.md)` |
| 9 | T2-R Reverse Validation | **A — STRONG VALIDATION**（F02 ALL_A_EW_RET60 方向 NEGATIVE：Disc IC −0.441 / Val IC −0.417, BH q 0.0105, spread +2.75pp；F18 LIMIT_DOWN_SHARE 方向 POSITIVE：Val IC +0.164, BH q 0.021, spread +2.54pp） | ACCEPTED | `[research/market_state/MARKET_STATE_REVERSE_VALIDATION.md](research/market_state/MARKET_STATE_REVERSE_VALIDATION.md)` |
| 10 | Market Gate T3 | **C — NO USEFUL PORTFOLIO GATE**（删信号改变组合路径后更差） | CLOSED | `[research/market_state/MARKET_STATE_GATE_T3.md](research/market_state/MARKET_STATE_GATE_T3.md)` |
| 11 | P1 / P1.1 Ranking（Discovery） | **A — STRONG CROSS-SECTIONAL RANKING**（≥2 非冗余 predictor：RET3/RET20/DIST_MA20/ATR20_PCT/INTRADAY_RANGE 通过完整 gate） | ACCEPTED | `[research/ranking/CROSS_SECTIONAL_RANKING_P1_CORRECTED.md](research/ranking/CROSS_SECTIONAL_RANKING_P1_CORRECTED.md)` |
| 12 | P2 Ranking Validation | **B — PARTIAL VALIDATION**（唯一 full pass：V04/F09 ATR20_PCT，POS；Val daily CS IC≈+0.134, BH q≈1.6e-8, pairwise 55.23%, K3 lift +1.426pp） | ACCEPTED | `[research/ranking/CROSS_SECTIONAL_RANKING_P2_VALIDATION.md](research/ranking/CROSS_SECTIONAL_RANKING_P2_VALIDATION.md)` |
| 13 | P3 ATR Slot Allocation | **C — NO USEFUL PORTFOLIO RANKING**（dev 2020–2024 PURE STOCK 10bp：B0 +30.30% / B1 −18.66%；B2 NON-DEPLOYABLE） | CLOSED | `[research/portfolio/ATR_SLOT_ALLOCATION_P3.md](research/portfolio/ATR_SLOT_ALLOCATION_P3.md)` |
| 14 | P3.1 Slot Contention | **C — BOTH**（ranking-actionable 仅 16/1212=1.32%；K=3 saturation 是主瓶颈；少数选择差异被 path dependence 放大） | ACCEPTED DIAGNOSTIC | `[research/portfolio/SLOT_CONTENTION_PATH_AUDIT.md](research/portfolio/SLOT_CONTENTION_PATH_AUDIT.md)` |
| 14b | P4 Portfolio Architecture Causal Decomposition | **D — TESTED ARCHITECTURE BOTTLENECK NOT EXPLAINED BY SIMPLE K/LAYER REMOVAL**（结构消融 2020–2024 PURE STOCK 10bp：A0 +30.30% / A1 K=999 −0.23% / A2 ML=1 −5.84% / A3 −29.27%。**K=3 是实际容量瓶颈（candidate 530 / blocked_K 336），但在当前历史样本与组合规则下同时表现为保护性的 admission constraint / implicit capacity filter**；解除任一约束均大幅恶化；A2 同批股票纯路径差异即可 ±50 万；A0 parity 精确通过。边界：P4 仅测试极端消融 K 3→999、levels 5→1，未搜索 architecture space，不构成"K/layer 结构不重要"的全局断言） | ACCEPTED DIAGNOSTIC（外审通过） | `[research/portfolio/PORTFOLIO_ARCHITECTURE_P4.md](research/portfolio/PORTFOLIO_ARCHITECTURE_P4.md)` |
| 14c | P4.1 Marginal Admission / Capacity Shadow-Price Audit | **B — CAPITAL/PATH DILUTION DOMINANT**（A1_ONLY 58 笔独立 quality +3.28%/win 68.8% 仍为正，但实际 PnL −118,610；**COMMON 65 笔同 key、same exit 100% 下 A1 少赚 67,116（STRONG CAPITAL/PATH DILUTION EVIDENCE）**；A1_ONLY 深 MAE 率 40.6% vs COMMON 18.8%（**SUGGESTIVE TAIL-QUALITY DETERIORATION**，非 population-level 信号质量恶化——事件日 bootstrap CI [−3.59,+1.73] 跨 0，aggregate independent quality 不显著更差）；A0_ONLY 独立质量 −1.97%/win 40% 且覆盖仅 45.5% → K=3 未被证明系统性过滤坏信号；PnL bridge residual=0.00；容量影子成本每额外 1 笔 ≈ −6,494 元） | DEVELOPMENT DIAGNOSTIC（WAITING EXTERNAL AUDIT，未写入 README CURRENT TRUTH） | `[research/portfolio/MARGINAL_ADMISSION_P41.md](research/portfolio/MARGINAL_ADMISSION_P41.md)` |
| 14d | S0 Stop-Loss Semantics Remediation（复权语义修复） | **A — OLD PHASE-A CONCLUSION ROBUST TO ADJUSTED-SPACE SEMANTICS FIX**（dev n=61,828；factor_changed 7,492=12.12%，old-only 误触发 460、new-only 0；**11 档 adjusted-space 固定止损均值全部低于 baseline**（d_adj_base −2.69~−0.85pp）；**S0.1 补全配对推断：paired delta block-bootstrap（L=21,B=2000）11/11 档 95% CI 上界全 <0、p(delta≥0)=0.000**；adjusted vs old 差异 <0.03pp；I1–I8 invariants 全 PASS（I7=dev-comparable old parity exact、I8=2025 边界污染隔离）；旧 raw parity true_mismatch=0（唯一差异 002789 为 canonical 依赖 2025-01-24 价格的已知边界，已披露）） | **ACCEPTED**（S0.1 外审通过） | `[research/execution/STOP_LOSS_SEMANTICS_S0.md](research/execution/STOP_LOSS_SEMANTICS_S0.md)` |
| 14e | F1 Deep-MAE Recoverability / Failure-State Taxonomy | **A — STRONG RECOVERABILITY PREDICTABILITY**（DEVELOPMENT DIAGNOSTIC；D20 锚点 12,590 笔、D30 6,130 笔；**18 个预注册 primary 中 13 个通过完整 gate**：方向一致 + BH q(m=18)<0.05 + 配对 block-bootstrap(L=21,B=2000) CI 排除 0 + D20/D30 同向，覆盖 PRICE_PATH/POSITION/VOLATILITY/RECOVERY/LIQUIDITY 5 family（收敛为约 3 个独立维度：浮亏深度×时长、波动率、量能）；F_CUR_MAE 本身不显著(q=0.123)；R01 Q1 弱市场 D20 恢复率 15.7% vs Q5 3.6%、R05 Q5 压力市场 17.8% vs Q1 4.4%（与 T3 systemic-vs-isolated 呼应）；跌到 −20% 后 ~90% 样本仍会再创新低、一半再跌 ≥7.5pp；实现审计：F_DAYS_SINCE_LOW 因 anchor 定义 degenerate 恒 0（已披露）、F_NLOW10 方向与预注册相反不 pass）。**本阶段仅证明失败/可恢复前瞻可识别，未设计任何 stop/exit** | **SUPERSEDED FOR INFERENCE BY F1.1**（描述性输出继续有效） | `[research/risk/FAILURE_STATE_F1.md](research/risk/FAILURE_STATE_F1.md)` |
| 14f | F1.1 Failure-State Inference Remediation | **FINAL = A — STRONG RECOVERABILITY PREDICTABILITY**（保守取 CLOSE/TOUCH 两语义较低者；修复三问题：①primary 用全部 anchor dates（D20=752/D30=537，去掉未注册 MIN_DAY_N=5，降为 sensitivity）；②gate 方向/D20-D30 一致性改用 anchor-day day_corr（F_AMT_RATIO20 由此 CLOSE 下 d30_consistent 由 True 改 False，不再误 pass）；③双 recovery 语义 CLOSE/A（9 pass）与 TOUCH/A（11 pass），各 4 family（PRICE_PATH/POSITION/RECOVERY/VOLATILITY）≥2 非冗余；calendar block-bootstrap(L21,B2000,seed0) CI 全排除 0；MIN5 sensitivity 不改方向；D30 strengthening q 计数 0（仅 537 天更稀疏，如实报告，不作为门槛）；sanity A–J 全 PASS） | **ACCEPTED**（R0.4 外审通过；描述性输出在 F1，推断以 F1.1 为准） | `[research/risk/FAILURE_STATE_F11.md](research/risk/FAILURE_STATE_F11.md)` |
| 14g | F2 Failure-State Actionability / Perfect-Information Value Bound | **INVALID / P0 — CAPITAL-BASIS MISMATCH（SUPERSEDED FOR INFERENCE BY F2.1）**：natural baseline ret0 分母含 D20 后 future adds 全部资本，oracle return 分母只含 anchor 已持资本（不同 shares / 不同资本基准 / 不同未来资本承诺），经济比较无效。原 D 数字仅作历史记录（O1 Δ −2.28pp 等），**不得**作为 action economic value 结论 | INVALID（历史结果保留，不删） | `[research/risk/FAILURE_STATE_F2.md](research/risk/FAILURE_STATE_F2.md)` |
| 14h | F2.1 Matched-Share Actionability / Perfect-Label Fixed-Action Value | **B — NARROW POSITIVE ACTIONABILITY**（matched-share O1 core evidence 有效，F2.2 修正 break-even 后确认）：61,828 natural exit replay parity 0 误差；D20 n=12,590/752 days；O1 完美最终-loser 标签 D20+1 清仓 eventday **+1.45pp**（HAC [0.48,2.42] / boot [0.40,2.61] 显著正）；O2 −0.34pp、O3 −0.09pp（跨 0）；TP −0.46pp、FP −17.9~−25.0pp；future-add 57.0%。 | DEVELOPMENT DIAGNOSTIC（待 F2.2 外审；未写入 README CURRENT TRUTH） | `[research/risk/FAILURE_STATE_F21.md](research/risk/FAILURE_STATE_F21.md)` |
| 14i | F2.2 Break-Even / Precision Remediation | **POINT BREAK-EVEN / PRECISION ACCEPTED**：A=+1.4486pp、B=−2.6833pp（day-等权 752 days）；point break-even FPR 0.135/0.270/0.405/0.540；break-even precision **0.762**（旧 0.96 撤销）；analytic-MC parity 0.0071pp、grid 复现 0 误差；contradiction test PASS。**但 POLICY-VALUE CI / SAFE FRONTIER WAITING F2.3**：现 CI 仅反映 classifier randomization，未含历史 anchor-day 采样不确定性；f21 randomization interval 不得再作 primary safe frontier。F2.1/F2.2 classification = **PROVISIONAL B**。 | DEVELOPMENT DIAGNOSTIC（point 数学 ACCEPTED；policy-value sampling CI 待 F2.3，未写入 README CURRENT TRUTH） | `[research/risk/FAILURE_STATE_F22.md](research/risk/FAILURE_STATE_F22.md)` |
| 15 | 2025–2026 Confirmation | **UNTOUCHED / CLOSED**（全程未读取任何 2025–2026 的 episode outcome / portfolio / feature） | CLOSED | — |

---

## 二、CURRENT ACTIVE QUESTION

> **The primary bottleneck now appears to be portfolio architecture:**
> finite K=3 slots + long holding periods + multi-layer occupancy / path dependence,
> **not** lack of signal-level edge.

（中文：当前主要瓶颈似乎是组合架构——有限 K=3 slots + 长持仓 + 多层占位/路径依赖，而非缺乏信号级 edge。）

**P4 进展（2026-09-03，ACCEPTED DIAGNOSTIC，外审通过）：** 结构性消融显示，K=3 是实际
容量瓶颈（binding capacity constraint），但在当前历史样本与组合规则下同时表现为保护性的
admission constraint / implicit capacity filter——解除任一约束均使组合大幅恶化
（A1 −0.23% / A2 −5.84% / A3 −29.27% vs A0 +30.30%）。完全移除多层加仓（5→1 层）在测试
路径下有害（不断言 5 层最优、不断言全市场必要）。真正局限在更深层：单笔信号边缘 +
极端路径依赖 + 少数深 MAE 长持仓的占用结构（P4 禁止修改 exit，未给对策建议）。

**P4.1 进展（2026-09-03，DEVELOPMENT DIAGNOSTIC，待外审）：** 解除 K 的恶化 = **B — CAPITAL/PATH
DILUTION DOMINANT**，secondary finding 为 **suggestive tail-quality deterioration**（非 aggregate
独立质量恶化）：
（1）**STRONG H3 证据**——COMMON 65 笔同 key、same exit 100% 下，A1 少赚 67,116（同一批交易仅
因资本可用性/数量/加仓路径不同即明显 PnL 退化）；A1_ONLY 独立整体仍 +3.28%/win 68.8%，但实际
PnL −118,610。
（2）**A1_ONLY 深 MAE 率 40.6% vs COMMON 18.8%、最差几笔独立 return −18%~−22%** → 仅定性为
**SUGGESTIVE TAIL-QUALITY DETERIORATION**；事件日 bootstrap CI [−3.59,+1.73] 跨 0，
**aggregate independent quality 未被统计建立为更差**。
（3）**A0_ONLY counterevidence**——独立 −1.97%/win 40%（覆盖 45.5%），K=3 未被证明系统性过滤坏信号；
更准确：K=3 改变内生共享资金路径，历史上实现的 K=3 路径恰好产生更优组合结果。
PnL bridge residual=0.00 精确闭合。容量影子成本：每额外 1 笔 ≈ −6,494 元、每额外 slot-day ≈ −148 元。

**S0 / S0.1 结论（2026-09-03，ACCEPTED）：** 复权语义修复后，Phase A"固定止损无用"结论**保持稳健（A）**，并已补全配对推断：
（1）**old raw parity**——20/22 组合机器精度 exact，唯一差异 002789.SZ/2024-02-02 为 canonical 依赖 2025-01-24 价格的已知边界（true_mismatch=0，已披露；I7=dev-comparable exact、I8=边界污染已隔离）。
（2）**factor_changed 7,492（12.12%）**，old-only 误触发 460、new-only 0；factor_unchanged 子集触发率逐档完全一致（I1 边界清楚）。
（3）**11 档 adjusted 均值全部低于 baseline**（d_adj_base −2.69~−0.85pp）。
（4）**S0.1 主推断：paired delta block-bootstrap（同事件日 adj−baseline，L=21, B=2000）11/11 档 95% CI 上界全部 <0、p(delta≥0)=0.000**；B 类 delta HAC 与 C 类 paired bootstrap 一致，`paired_delta_11_upper_ci_neg=true`。
（5）I1–I8 全 PASS；2025+ 全程未读（I6）。
结论（范围限定）：**在冻结的 −10%…−40% 网格下，简单固定价格止损对独立 BB episode 期望稳健有害**。这**不等于**所有止损方法都无用。
Fixed Stop Phase A → **SUPERSEDED BY S0**；S0 → **ACCEPTED**。

**F1 进展（2026-09-03，DEVELOPMENT DIAGNOSTIC，待外审）：** 深度浮亏锚点（D20/D30）的
可恢复性前瞻识别——**A — STRONG RECOVERABILITY PREDICTABILITY**：
（1）**基线**：D20 后 recover_to_entry 仅 12.1%、final_profit 36.7%、中位回本 11 天；D30 后
recover 7.8%、final_profit 30.6%。跌到 −20% 后 ~90% 样本还会再创新低，其中一半再跌 ≥7.5pp
（典型触底约 −27.5%）。
（2）**13/18 primary 通过完整 gate**（方向 + BH q<0.05 + 配对 block-bootstrap CI 排除 0 +
D20/D30 同向）：最强为 F_DAYS_UNDERWATER（corr −0.353）、F_ATR20_PCT（+0.344）、
F_DAYS_SINCE_FIRST_D10（−0.322）、F_DIST_MA20（−0.317）；F_CUR_MAE 单点深度不显著。
收敛为约 3 个独立维度（浮亏深度×时长 / 波动率 / 量能）——不可表述为 13 个独立发现。
（3）**市场状态 overlay（secondary）**：弱市场/压力市场中的 deep-MAE 恢复率远高于强市场
孤立超跌（R01 Q1 15.7% vs Q5 3.6%；R05 Q5 17.8% vs Q1 4.4%）——与 T3 systemic-vs-isolated
主题在 recovery 维度独立呼应。
（4）实现审计：F_DAYS_SINCE_LOW 因 anchor 定义 degenerate（恒 0）、F_NLOW10 方向与预注册
相反不 pass；均不改变 Registry，不影响门控。
**本轮未设计任何 stop/exit/failure-score；禁止据此构造交易规则。**

**F1.1 进展（2026-09-03，已通过外部审计，R0.4 收口）：** 修复 F1 外部审计三项问题后，最终评级 **A**，现正式 **ACCEPTED**（推断以 F1.1 为准，F1 描述性输出继续有效；README CURRENT TRUTH 已新增一行 "Deep-MAE failure/recovery state: PROSPECTIVELY IDENTIFIABLE (A, F1.1)" 并注明 **NO EXIT POLICY YET**）：
（1）**primary 口径修正**——去掉未注册的 MIN_DAY_N=5 过滤，primary 用全部 anchor dates（D20=752、D30=537，仅要求当日 feature 非缺失），`n>=5` 降为 sensitivity（方向 17/18 一致，不改结论）。
（2）**primary-unit 修正**——gate 方向与 D20/D30 一致性改用 anchor-day day_corr 而非 episode corr；F_AMT_RATIO20 在 CLOSE 下 corrected 一致性由 True→False（D20 day −0.053 / D30 day +0.005），不再误 pass，验证旧 bug 已修。
（3）**双 outcome 语义**——RECOVER_CLOSE（D20 12.1%/D30 7.8%）与 RECOVER_TOUCH（D20 16.5%/D30 10.9%）各自跑完整 gate；CLOSE 9 pass / TOUCH 11 pass，各 4 family（PRICE_PATH/POSITION/RECOVERY/VOLATILITY）；**FINAL=min(CLOSE,TOUCH)=A**。
（4）calendar block-bootstrap（L21/B2000/seed0，完整 1,212 交易日，配对）CI 全部排除 0；D30 strengthening q 计数 0（D30 仅 537 天更稀疏，按预注册不作硬门槛，如实报告）；sanity A–J 全 PASS；F1 Registry SHA 不变。
**结论不变：深度浮亏后的失败/恢复在锚点当日具有前瞻可识别性；仍未设计任何 stop/exit/failure-score。**

**F2 进展（2026-09-03，INVALID / P0 — CAPITAL-BASIS MISMATCH，SUPERSEDED FOR INFERENCE BY F2.1）：** 外部审计冻结 P0：F2 的 O1/O2/O3 delta、TP benefit、FP cost、break-even frontier 全部存在 **capital-basis mismatch**——natural baseline ret0（final PnL / FINAL TOTAL COST，分母含 D20 后 future adds）与 oracle return（early-exit PnL / ANCHOR TOTAL COST，仅 layers ≤ anchor）比较了不同 shares、不同资本基准、不同未来资本承诺，**不得解释为 action economic value**。原 **D — ACTIONABILITY NEGATIVE** 结论作废（历史文件保留，顶部加 INVALID 标注；不写入 README CURRENT TRUTH）。正确经济比较在 F2.1（matched-share basis）进行。


**F2.1 进展（2026-09-03，DEVELOPMENT DIAGNOSTIC，待外审）：** 修复 F2 P0（capital-basis mismatch）后，matched-share 基准下结论**反转**：O1 完美最终-loser 标签 D20+1 首个可执行 open 全仓清仓 **+1.45pp（显著正）**，O2/O3 接近 0（跨 0）；TP 正确退出 mean −0.46pp（近中性）、FP 误杀恢复者 −17.9~−25.0pp；grid TPR=.5/FPR=.2 跨 0 → **B — NARROW POSITIVE ACTIONABILITY**（完美标签有正价值但 break-even 精度 ≥96%、TPR=.5 时 break-even FPR 仅 8%）。61,828 自然退出执行价 replay parity 0 误差；future-add 发生率 57.0%（F2 分母污染平均 4.77pp）。未设计任何 predictor/stop/exit。

**R0.6 修正（2026-09-04）：** 外部审计确认 matched-share O1 core evidence 有效，但 **break-even/precision 模块无效**（day_agg 分解错误：mean_d 混合 failure/recovery delta；A/B 单位贡献必须按 per-day `A_d=Σfail_delta/n_d`、`B_d=Σrec_delta/n_d` 分解）。旧 "precision~=96%"、旧 "TPR=.5 break-even FPR=8%" 全部废止，由 F2.2 重算。

**F2.2 进展（2026-09-04，DEVELOPMENT DIAGNOSTIC，待外审）：** 修正分解后 A=+1.4486pp、B=−2.6833pp（752 days 等权），analytic-MC parity 0.0071pp、grid 复现 0 误差；**point break-even FPR 0.135/0.270/0.405/0.540**、**break-even precision 0.762**、**CI-safe frontier 0.05/0.10/0.30/0.30**；TPR=.75/FPR=.30 CI 显著正；contradiction assert PASS。旧 "96% precision / 8% FPR" 撤销。classification 仍 **B**。未设计 predictor/stop/exit/timing。

**R0.7 修正（2026-09-04）：** 外部审计接受 F2.2 point 数学（A/B、point break-even、precision 冻结），但指出 f21 confusion grid 的 CI 只反映 **classifier randomization uncertainty**（在固定历史样本上随机 TP/FP flag），未对 **historical anchor-day sampling uncertainty** 做 block resampling——因此 safe frontier 与 TPR=.5/FPR=.2 CI 不能作为 A/B final inference。F2.1/F2.2 分类降为 **PROVISIONAL B**，policy-value sampling inference 由 F2.3 完成（full-calendar block bootstrap L21 B2000 seed0 + HAC，确定性 V_d(t,f)=t·A_d+f·B_d）。

**下一步仍须等待外部审计决定**，方可决定是否打开 2025–2026 Confirmation 或进入新的
研究阶段。

---

## 三、INVALID vs SUPERSEDED 严格分离

**INVALID（存在已确认致命方法错误，禁止作为策略表现证据）：**
- 原 +354.9%（same-bar 未来信息）
- 乐观 tick / non-executable 成交假设
- exp2 limit-mismatch 等原系统产物
- 原始参数扫描 / 时间止损 / topN 扫描等（原系统证据）

**SUPERSEDED（方法未必错误，但被更严格版本替代）：**
- Replay V1 → V2（`archive/superseded/`）
- P1 → P1.1 corrected
- TRADE_PATH_QUALITY_AUDIT → FULL_MARKET_TRADE_PATH_AUDIT
- 旧 104-cell Regime Registry 系列（`archive/superseded/`）
- Fixed Stop Phase A → **S0**（adjusted-space 复权语义修复；S0 已外审通过，ACCEPTED）

---

## 四、已注册的预注册 Registry（冻结，不可修改）

| Registry | Commit | SHA256 |
|---|---|---|
| 104-cell Hypothesis Registry | `0d5979bfa3e3a3ccfe261681daebd2a738ea70de`（T2 registry commit 前已有） | `5c5e451ad4eb3afd5e632b0019a3e02103e58e375e03cc231c5d8ca52b8c5195` |
| T2 Feature Registry | 见 `research/market_state/registries/TEMPORAL_STATE_FEATURE_REGISTRY.sha256` | `b6860158c25e694546d0b625180d01543b5e17d9f1a9639af7a8f374cf0c8407` |
| P1 Ranking Registry | `9c36887` | `fa5beb5a9a952442be2a359b95347388ff082c06fa36b56cf8f6eee477bab819` |
| P2 Ranking Validation Registry | `83c3f1e`（TASK 记录） | 见 `research/ranking/registries/CROSS_SECTIONAL_RANKING_VALIDATION_REGISTRY.sha256` |
| ATR Slot Allocation Registry | 见 `research/portfolio/registries/ATR_SLOT_ALLOCATION_REGISTRY.sha256` | — |
| Market State Gate Registry | 见 `research/market_state/registries/MARKET_STATE_GATE_REGISTRY.sha256` | — |
| S0 Stop-Loss Semantics Registry | `b352f77`（S0-A，结果前 push） | `7e8416fd4fc3a3f67da41d020747ffda34aaf8b1e230ddf574c131ab30f36273` |
| F1 Failure-State Registry | `1de126b`（F1-A，结果前 push） | `a052309e6f939796795566d1cd1094e2ec706f53250c231377c64efb315eef14` |
| F1.1 Inference Remediation Registry | `2cecd15`（F1.1-A，结果前 push） | `aacb2146308abd155401c1231209b7cab14e1bc44c50e6f19007ac39582aef91` |
| F2 Actionability Value Bound Registry | `4e088fb`（F2-A，结果前 push） | `9ed07a575ae65bbda3d63321e676431231d00548bb8977fb443764163b85642a` |
| F2.1 Matched-Share Actionability Registry | `02c6738`（F2.1-A，结果前 push） | `12f8311c52df76ca6fc10cb7f5f43a95bae4e1c9a9dc1f5880bfdcee60357787` |

---

## 五、关键冻结参数（引擎口径，不可改）

- `prepare_v51(limit_down_mode='correct', st_mode='pit')`：offset=7100, days[0]=2020-01-02, 共 1611 交易日, N2024=1212（2024-12-31 开发期边界）
- 组合：initial_capital=1,000,000 RMB, K=3, layer=200,000 RMB, max_levels=5, slippage_bp=10, T+1, 100股 lot, PIT ST, listing≥60 trading days, dynamic P\*, etf_enabled=False（PURE STOCK）
- 独立样本：`results/evidence/fullmarket/fullmarket_episode_metrics.csv`（89,046 行）

---

## 六、数据可用性

审计仓库 `data/` 仅含**原始 kline 分片**（`data/kline/2020..2026.parquet` 等，供审计核实）。**派生数据**（`combined_daily.parquet` / `pit_st_daily.parquet` / `raw/stock_basic.parquet` / `raw/trade_cal_full.parquet` / `etf_513500_merged.parquet`）**不在仓库内**（体积大不入库）。复现/运行 `tests/` 需在主工作区数据齐全环境下进行。详见 `[data_docs/KLINE_DATA.md](data_docs/KLINE_DATA.md)`。
