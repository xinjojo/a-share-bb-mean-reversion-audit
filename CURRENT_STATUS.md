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
| 14i | F2.2 Break-Even / Precision Remediation | **POINT BREAK-EVEN / PRECISION ACCEPTED（冻结）**：A=+1.4485803535pp、B=−2.6832617657pp（day-等权 752 days）；point break-even FPR 0.13496/0.26993/0.40489/0.53986；break-even precision **0.76190**；analytic-MC parity 0.0071pp、grid 复现 0 误差；contradiction test PASS。 | **ACCEPTED**（统一结论 B — NARROW POSITIVE ACTIONABILITY；未写入 README CURRENT TRUTH 之外） | `[research/risk/FAILURE_STATE_F22.md](research/risk/FAILURE_STATE_F22.md)` |
| 14k | F3 Failure-State Predictor Feasibility | **C — PREDICTIVE BUT ECONOMICALLY INSUFFICIENT**：OOF AUC 0.720 / PR-AUC 0.786（M1，2021–2024 严格样本外）；fold AUC 0.587–0.788；**STABLE_SAFE 0/6、STABLE_POINT 0/6**——2021–2023 全部 model-target EV 为负；2024 年 M0 T50/T75、M1 T50/T75/T90 为正但无组合达标；O1 prevalence 63.3% 下 test FPR 0.12–0.64 远超 F2.3 calendar-safe（≤0.05–0.10）；T50 经济门槛需 FPR≤0.27 而实际 0.12–0.64；系数 3/4 方向稳定（DAYS_UNDERWATER+ / RET20− / INTRADAY_RANGE− / REB5 不稳定）；D30 transfer AUC 0.584–0.807（FPR 同高）。M0/M1 均为冻结线性 logistic（L2 C=1.0），无调参。 | **ACCEPTED DIAGNOSTIC**（C — PREDICTIVE BUT ECONOMICALLY INSUFFICIENT；README 加一句 + NO DEPLOYABLE EXIT PREDICTOR） | `[research/risk/FAILURE_STATE_F3.md](research/risk/FAILURE_STATE_F3.md)` |
| 14j | F2.3 Policy-Value Sampling Inference | **确定性 V_d(t,f)=t·A_d+f·B_d；point 与 tA+fB 机器精度一致（<1e-12）；Perfect-label O1 parity PASS（point +1.4485803535 / HAC [0.4767,2.4205] / CAL [0.4027,2.6072]）；纳入历史采样不确定性后 calendar-safe frontier 收窄为 0.00 / 0.05 / 0.10 / 0.10（HAC-safe 一致）；TPR=.75/FPR=.30 由 randomization 显著正变为 sampling 跨 0（CAL [−0.599,+1.227]）；旧 randomization interval 降级 reference（0.05/0.10/0.30/0.30，系统性偏宽）；A gate fail（.5/.2 CAL lower −0.399<0），O1 显著正 → FINAL 仍 B**。 | **ACCEPTED**（F2.3 正式通过外审；冻结 O1 +1.4485803535pp / HAC [+0.4767,+2.4205] / CAL [+0.4027,+2.6072]；calendar-safe 0.00/0.05/0.10/0.10；FINAL **B — NARROW POSITIVE ACTIONABILITY**；README 仅加一行，注明 NO DEPLOYABLE PREDICTOR YET） | `[research/risk/FAILURE_STATE_F23.md](research/risk/FAILURE_STATE_F23.md)` |
| 14m | S1 Signal Selectivity Audit（BB depth / RSI14 / Sector） | **BB threshold = D — HARMFUL**（B25 vs B20_ONLY day-delta **−2.12pp**、B30 vs B25_ONLY **−1.91pp**，HAC/calendar CI 全部 <0；仅 2024 年方向为正 1/5 年；MAE≤−30 与 hold>90d 略恶化——语义：**"等到 entry k=2.5/3.0 才买"显著有害**，非"更深的同日 BB_Z 有害"）；**RSI14 = C — NO STABLE INCREMENT**（R30 ep-mean +7.70%/win 80.96%/PF 2.68 但 matched-depth 4 bin 全跨 0、R30−B20 day-delta −0.02pp；2023 崩塌 2.68%；MAE 更深 −12.07%；slot eff 2.21 未过 day-等权 gate）；**Sector = N/A — PIT DATA NOT READY**（无 PIT 行业归属，禁当前快照回填）；MACD diagnostic 无明显关系（4.78 vs 4.85）；Fundamental/News readiness NOT_READY | **ACCEPTED**（R1.4 主审确认；未经外审不写 README CURRENT TRUTH） | `[research/signal/SIGNAL_SELECTIVITY_S1.md](research/signal/SIGNAL_SELECTIVITY_S1.md)` |
| 14n | S1.1 Contemporaneous BB Depth Ranking（同日排序诊断） | **C — NO STABLE RANKING VALUE**（DEEP30−SHALLOW30 day-delta **−0.023pp**、HAC [−0.53,+0.48] / calendar [−0.57,+0.50] 全跨 0；仅 2/5 年为正（2021/2022）、2023–2024 连续为负；collision days（候选≥4，961 天、占 99.55%）方向 −0.10pp 反而为负；三档 day-等权非单调（DEEP 3.58 < SHALLOW 3.90 < MID 4.07）；Spearman day-level +0.003 / pooled −0.020；DEPTH_TOP3 vs AMOUNT_TOP3 day-delta +0.09pp 跨 0、slot eff 1.086 vs 1.034 无显著差异——同日横截面内"更深更值得占坑"无证据；S1 绝对深度 bin 迹象为**日期间效应**（普跌日整体更好）而非同日排序价值；FIRST_HIT 97.94% / REPEAT 2.06%，[-2.5,-3.0) 内 FIRST−REPEAT −1.47pp（CI 上界<0，方向与"快速一步跌深"假设相反）仅作 **exploratory lead，NOT REGISTERED FOR DEVELOPMENT**；tail 无恶化（DEEP mae30 8.61% < SHALLOW 9.39%）；单日集中度 0.92%） | **ACCEPTED**（R1.5 主审确认；未经外审不写 README CURRENT TRUTH） | `[research/signal/SIGNAL_SELECTIVITY_S11.md](research/signal/SIGNAL_SELECTIVITY_S11.md)` |
| 14o | D1 PIT Context Data Foundation（Sector + Fundamental 数据层） | **SECTOR = B — PARTIAL**（申万 2021 L1 + index_member in/out 重建历史归属，31 行业/7,740 条 membership；**信号级 coverage 94.555%**（2020 96.4 / 2021 93.0 / 2022 91.6 / 2023 92.8 / 2024 100.0）；缺失 3,473 信号中 98.7% 为**申万首次纳入滞后于信号日**（真实 PIT 特性，非数据污染）；3,214 只行业变更股可重建；spot check 300 行 bad_interval=0、25 变更边界 chg_fail=0；`stock_basic.industry` current snapshot 从未回填）；**FUNDAMENTAL = A — READY**（fina_indicator/income/cashflow/express/forecast，全部 5,147 只覆盖；**financial PIT coverage 100%**、TTM 98.80%、forecast 94.73%、express 37.16%；revision as-of selector PASS（57,680 个 ts_code×period 有多版本）；100 例 PIT spotcheck 0 fail；financial age 中位 58 天；LOSS_FLAG 18.2%/NEG_OCF 20.4%/PROFIT_DECLINE 50.3%）；**NEWS = NOT_READY**；红队 7 项全 CLEAN；I1–I13 PASS | **HOLD / VISIBILITY-DATE AMBIGUITY**（D1.1 PASS 后，D1.2 审计确认 f_ann_date 字段混合语义（小 delta=真实披露日 8/11 匹配巨潮；大 delta=库更新时间 0/30 匹配）；单一 RULE_A/RULE_B 均不可靠 → **D1.2-C SEMANTICS AMBIGUOUS**；D1 不 ACCEPT；income/cashflow PIT 进 S3 需更可靠公告日源或治理登记混合规则） | `[research/context/PIT_CONTEXT_D1.md](research/context/PIT_CONTEXT_D1.md)` |
| 14q | D1.2 Effective Financial Visibility-Date Audit | **D1.2-C — SEMANTICS AMBIGUOUS（外审 ACCEPTED）**：Tushare 官方定义 ann_date=公告日期、f_ann_date=实际公告日期；实证发现 **f_ann_date 字段混合两种语义**——小 delta（1–30d）= 真实实际披露日（巨潮 11 例 8/11 精确匹配，晚间公告模式），大 delta（>180d）= **库更新时间戳**（同一股票全报告期同日，如 600973.SH 全期=20260314；巨潮 30 例 0/30 匹配）；income f_ann>ann 3,143 行（1.64%）、cashflow 2,036 行（1.08%），delta median 295/182 天；D1.1 选中组件中 ann≤T 且 f_ann>T = **3,466 个 / 2,262 信号（3.55%）**，其中 **91.5% 为大 delta 假警报**，真泄漏候选仅 14（≤0.02%）–249（≤0.39%）个组件；RULE_B 重建错误修正 381 信号（0.60%）；RULE_B TTM future_visible=0；fina AMBIGUOUS→NA 与 sector B 不受影响 | **ACCEPTED AS C — SEMANTICS AMBIGUOUS**；D1 overall 维持 **HOLD**；**S3 FUNDAMENTAL DISTRESS NOT START**（禁止事后发明 small-delta/large-delta 混合 visibility 规则；需权威公告日源或治理登记混合规则） | `[research/context/PIT_CONTEXT_D12.md](research/context/PIT_CONTEXT_D12.md)` |
| 14p | D1.1 PIT Financial Version-Selector Remediation | **PASS**（STRICT_SELECTOR 完整实现 Registry：ann_date<=T→max ann→max update_flag→max f_ann_date→row-hash；**版本标识层面 OLD vs STRICT 0/63,785 差异**，但同公告日多版本行的数值选择在 **revenue_ttm 8,064（12.64%）/ netprofit_ttm 8,348（13.09%）/ ocf_ttm 7,793（12.22%）** 上被 f_ann_date tie-break 修正（income 重复行数值实质差异，cashflow 仅浮点噪声）；fina_indicator 同日不同值 **2,020 组→AMBIGUOUS→NA**，命中 **1,179 个信号事件（1.85%）**，废止 D1 的 keep='last' 任意取值；扩展抽查 **1,179 事件全查 0 fail**；TTM 红队全量 249,636 组件行 **future_component_count=0**；coverage 不变（financial 100%/TTM 98.80%）；sector B 不受影响；D1.1 PASS=True，fundamental=A） | **DEVELOPMENT DIAGNOSTIC / WAITING EXTERNAL AUDIT**（D1 解除 HOLD 需外部审计确认 D1.1） | `[research/context/PIT_CONTEXT_D11.md](research/context/PIT_CONTEXT_D11.md)` |
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

**F2.3 进展（2026-09-04，DEVELOPMENT DIAGNOSTIC，待外审）：** 确定性 V_d=t·A_d+f·B_d（752 days），point 与解析式机器精度一致；O1 perfect-label parity PASS（HAC [0.48,2.42] / CAL [0.40,2.61]）；**calendar-safe frontier 0.00/0.05/0.10/0.10**（HAC 一致）；.75/.30 与 1.00/.30 由 randomization 显著正变为 sampling 跨 0；randomization interval 降级 reference（0.05/0.10/0.30/0.30）。A gate fail → FINAL **B**。未设计 predictor/stop/exit/timing。

**P5 诊断（2026-09-04，DEVELOPMENT DIAGNOSTIC / WAITING EXTERNAL AUDIT）：** PORTFOLIO CAPITAL ARCHITECTURE 纯诊断完成（prereg `PORTFOLIO_ARCHITECTURE_P5_REGISTRY.csv`、commit `e007979`；A0 parity 5 项全 PASS）。候选 530 = ADMITTED 76 + BLOCKED_K 336 (63.4%) + BLOCKED_HELD 116 (21.9%) + 其他 2；**cash 从不阻塞（NO_CASH=0）**；K 满交易日 55.1%。Top10% 持仓占 capital-days 37.8%；layer2+ 占投入资本 50.9%（matched-share 平均正）；blocked_K 独立 mean +5.08% vs admitted +3.53%（coverage 36.6%，bootstrap CI 跨 0，无统计结论）；虚拟队列 336 全部可释放、median 11 天、16.3% 释放前已自然 TP。Q7 登记 NEXT lever = **D QUEUE/DEFERRED ADMISSION**（仅登记不执行）。分类按外部审计修正为 **C — BOTTLENECK EXISTS BUT ECONOMIC RELEVANCE UNCLEAR**（R1.1）：K 是明确机械容量瓶颈（63.4% 候选、55.1% 交易日 K 满），但 independent coverage 仅 36.6%、blocked_K vs admitted bootstrap CI [-14.08,+4.79]pp 跨 0，无法证明被挡机会有可实现经济增益；同时保留 R0.2 措辞（K=3 同时是保护性 admission constraint）。禁止写“放开 K 会增加收益”“blocked_K 是更好信号”“queue 已证明值得部署”。未经外审不得写入 README CURRENT TRUTH。

**P6（2026-09-04，ACCEPTED / D — HARMFUL，R1.3 主审确认）：** ADD-BUDGET SEPARATION 测试（prereg `PORTFOLIO_ARCHITECTURE_P6_ADD_BUDGET_REGISTRY.csv`、commit `407335e`；A0 parity 5 项全 PASS）。**预算隔离全面有害**：A1(600/400) +11.04% / A2(800/200) +10.27% / A3(400/600) −7.76% vs A0 共享池 +30.30%（Sharpe 0.209/0.202/0.061 vs 0.347）。A1 vs A0：return −19.25pp、MaxDD 恶化 1.59pp、仅 1/5 年 PnL 更好。机制：**NO_NEW_BUDGET=0（新仓池从不缺钱，预算隔离几乎无新信号，A1_ONLY=1）；NO_ADD_BUDGET=85 次加仓被拒（adds 82→65）**，COMMON 74 个相同信号 PnL 合计 −163,660（约 A0 总 PnL 54%），切掉了 P5 已证明为正的 layer2/3 matched-share 贡献。核心结论：**共享现金池的时间弹性本身是 A0 的组成部分；瓶颈是 K 不是钱（P5 blocked_cash=0 再证）**。分类 **D — HARMFUL**。20/40/60% 仅探针、无正价值证据。**ADD-BUDGET SEPARATION branch CLOSED**：共享现金池保留、不做 NEW/ADD pool separation、不扫描 reserve ratio；K=3 仍是机械瓶颈兼 protective admission constraint；queue 已关闭；failure predictor 已关闭。2025–2026 CLOSED。

**R1.3（2026-09-04）：** 正式接受 P6=D（HARMFUL），关闭 ADD-BUDGET SEPARATION branch，开启 **SIGNAL SELECTIVITY RESEARCH（S1）**：在 K=3 稀缺槽位前提下，审计 BB depth（k=2.0/2.5/3.0，只改 entry 不改 exit）、Wilder RSI14（R30/R25）、sector strength（PIT gate，不合格则 NOT RUN）是否能在入场前提高 signal quality。只做 entry selectivity，exit STRICT_C k=2 冻结；signal-level first，不修改真实 K=3 portfolio；2025–2026 CLOSED。

**R1.5+D1+D1.1（2026-09-04）：** 正式接受 **S1.1 = C — NO STABLE RANKING VALUE**（外部审计 PASS）。同日 BB_Z 相对排序无稳定横截面价值；collision 场景方向为负；TOP3 深度 vs 成交额无差异；**不进入 K=3 portfolio test**。关闭 **CONTEMPORANEOUS BB DEPTH RANKING branch**；REPEAT_HIT exploratory finding **NOT REGISTERED FOR DEVELOPMENT**。开启并完成 **PIT CONTEXT DATA FOUNDATION（D1）**：只建立 2020–2024 每个 B20 signal date 可审计的 PIT SECTOR 与 PIT FUNDAMENTAL 数据层（ann_date <= signal_date 硬规则、revision as-of selector、TTM 只用已披露季度）；**DATA FOUNDATION ONLY**——禁止交易策略测试、禁止读取 outcome 后挑财务指标、禁止打开 2025–2026。SECTOR 达 A/B 才允许 S2（sector strength）；FUNDAMENTAL 达 A/B 才允许 S3（fundamental distress）；若两者都 A/B 优先 S3（技术性错杀 vs 永久性基本面重估假设，本阶段不测试）。**D1.1（2026-09-04）**：外部审计指出 D1 revision tie-break 与 Registry 潜在不一致 → D1 **HOLD**；D1.1 完整实现 STRICT_SELECTOR（ann_date≤T→max ann→max update_flag→max f_ann_date→row-hash）并给 fina_indicator 同日重复建立 **AMBIGUOUS→NA** 规则；结果：版本标识 OLD vs STRICT **0 差异**，但同公告日多版本行的数值在 ~12% 信号上被修正（revenue_ttm 8,064 / netprofit_ttm 8,348 / ocf_ttm 7,793 changed），fina **1,179 事件（1.85%）置 NA**；1,179 全查 0 fail；TTM 全量 future_component_count=0；coverage 不变；**D1.1 PASS=True**（sector B / fundamental A）。S3 的启动条件 = 外部审计确认 D1.1。**D1.2（2026-09-04）**：外审再发现 Registry 更根本的 visibility 问题（ann_date=公告日期 vs f_ann_date=实际公告日期）；审计结论：**f_ann_date 字段混合两种语义**——小 delta（1–30d）是真实实际披露日（巨潮 11 例中 8/11 精确匹配，晚间公告场景），大 delta（>180d）是**库更新时间戳**（同一股票全报告期同一天；巨潮 30 例 0/30 匹配）；信号级 FUTURE_ACTUAL 组件 3,466 个中 **91.5% 为大 delta 假警报**，真泄漏候选仅 **14 个 cur 组件（≤0.02%）至 249 个（≤0.39%）**；RULE_B 会对 381 信号（0.60%）造成错误修正；**D1.2 分类 = C SEMANTICS AMBIGUOUS**（外审 ACCEPTED），D1 维持 HOLD 不 ACCEPT；S3 仍禁止（需更可靠公告日源或治理登记混合规则，禁止事后发明混合规则）。**R1.6（2026-09-04）**：接受 D1.2=C，fundamental branch PAUSED；开启 **W1 MULTI-TIMEFRAME BOLLINGER DIAGNOSTIC**（日线 B20 × real-time weekly BB state；纯诊断，不改 entry/exit，2025–2026 CLOSED）。

**R1.2（2026-09-04）：** 正式接受 P5.1 = **C — QUEUE MOSTLY STALE**（P5.1 PASS/ACCEPTED）。**QUEUE / DEFERRED ADMISSION branch CLOSED**。禁止继续：queue cutoff / wait-day scan / delayed-entry optimization / queue ranking。NEXT 研究：ADD-BUDGET SEPARATION（P6）。2025–2026 CLOSED。

**P5.1 诊断（2026-09-04，DEVELOPMENT DIAGNOSTIC / WAITING EXTERNAL AUDIT）：** DEFERRED-ADMISSION ELIGIBILITY DIAGNOSTIC（prereg `PORTFOLIO_ARCHITECTURE_P51_QUEUE_ELIGIBILITY_REGISTRY.csv`、commit `dc5fb74`）。对 P5 的 336 个 BLOCKED_K 在 release 日重新扫描原始入场条件：Q1 EXACT_ELIGIBLE 仅 **9（2.68%）**、Q2 8（2.38%）、Q3 NO_LONGER_OVERSOLD 299（88.99%）、Q0 EXPIRED_TP 20（5.95%）。**P5 的“83.7% still active”= 未达止盈价，不是还能买**；release 日仍 below LBB 仅 5.06%，median release 距 LBB +5.5%，资格随等待快速衰减（1-5d 7.4% → 40+d 0%）；65.2% 等待期重新超卖、37.5% 已被原 engine 自然重新捕获（占重触发者 57.5%，未达冗余主导）。分类 **C — QUEUE MOSTLY STALE**；显式 queue 不值得进入真实回测（NO）。Q7 的 NEXT lever=D 登记撤销。2025–2026 CLOSED。未经外审不得写入 README CURRENT TRUTH。

**R1.0 开放（2026-09-04）：** 正式从 failure-state predictor 分支转回 **PORTFOLIO ARCHITECTURE 研究主线**。冻结：F1.1 A（failure state 前瞻可识别）、F2.1/F2.2/F2.3 B（perfect-label fixed action 窄幅正价值）、F3 C（真实简单 predictor 经济不足）；failure-state predictor branch **PAUSED / CLOSED FOR DEVELOPMENT**（禁止调 C、增删特征、换模型族、interaction、threshold/market/layer gate、D20/D30 scan）。2025–2026 保持 CLOSED/UNTOUCHED。下一诊断：P5 CAPITAL ARCHITECTURE——不预测单股输赢、不改 BB 入场与自然退出、不做参数优化，只回答资金如何被占用/阻塞/释放。

**R0.9 关闭（2026-09-04）：** 外部审计正式接受 **F3 = C — PREDICTIVE BUT ECONOMICALLY INSUFFICIENT**。核心含义：failure state 非随机不可识别（OOF M1 AUC≈0.720），但预注册简单 predictor 无法稳定达到 F2.3 经济门槛（STABLE_SAFE/STABLE_POINT 均 0/6）；2024 年 M0 T50/T75、M1 T50/T75/T90 的 point EV 为正但单年不足以支持，禁止继续调参。**failure-state predictor branch 正式 PAUSED / CLOSED FOR DEVELOPMENT**（禁止调 C、增删特征、换模型族、interaction、threshold/market/layer gate、D20/D30 threshold scan）。2025–2026 保持 CLOSED/UNTOUCHED（F3 未达 A，不满足打开 Confirmation 条件）。NEXT（仅登记不执行）：PORTFOLIO ARCHITECTURE——不预测单股输赢、不改 BB 入场与自然退出，仅通过组合资金架构提高 signal capture 与 capital efficiency 且不破坏保护性 admission constraint，WAITING NEW PREREGISTRATION。

**R0.8 关闭（2026-09-04）：** 外部审计正式接受 F2.1（matched-share actionability）、F2.2（point break-even 数学）、F2.3（policy-value 历史采样推断），统一结论 **B — NARROW POSITIVE ACTIONABILITY**。冻结：O1 perfect-label D20+1 fixed action day-equal value **+1.4485803535pp**（HAC [+0.4767,+2.4205]、CAL [+0.4027,+2.6072]）；point break-even FPR 0.13496/0.26993/0.40489/0.53986；break-even precision 0.76190；calendar-safe FPR 0/0.05/0.10/0.10。README CURRENT TRUTH 仅增一行（NO DEPLOYABLE PREDICTOR YET）。下一阶段 F3 用这些冻结常数作 economic target。

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
