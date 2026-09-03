# RESEARCH_MAP.md — 研究链地图

> 本文件建立研究链的**唯一入口导航**：每个阶段 → **一个 canonical 报告**（含其源码与结果数据落点）。
> 旧版本 / 中间版本一律标 `SUPERSEDED` 或 `INVALID`，不以任何方式作为"当前答案"。
> 状态图例：`ACCEPTED`（结案通过）/ `CLOSED`（验证失败或终止）/ `PROVISIONAL`（暂接受）/ `INVALID`（致命错误）。

---

## 研究链总览

```
Original +354.9%  (INVALID: same-bar future info)
   │
   ▼
Lookahead / 红队审计 (REDTEAM rounds 1-5)
   │
   ▼
STRICT_C (ACCEPTED)
   │
   ▼
Independent Trade Replay ──► Signal Layer A (ACCEPTED)
   │
   ▼
Full Market ~89k ──► Trade Path 结构 A (ACCEPTED)
   │
   ▼
Temporal Clustering T1 ──► A STRONG (ACCEPTED)
   │
   ▼
Market State T2 ──► reverse-direction discovery (ACCEPTED AS DISCOVERY)
   │
   ▼
T2-R Reverse Validation ──► A STRONG VALIDATION (ACCEPTED)
   │
   ▼
Market Gate T3 ──► C NO USEFUL PORTFOLIO GATE (CLOSED · FAIL)
   │
   ▼
Cross-sectional Ranking P1/P1.1 ──► A Discovery (ACCEPTED)
   │
   ▼
P2 Ranking Validation ──► B Partial (ATR20_PCT 唯一 full pass) (ACCEPTED)
   │
   ▼
P3 ATR Slot Allocation ──► C NO USEFUL PORTFOLIO RANKING (CLOSED · FAIL)
   │
   ▼
P3.1 Slot Contention ──► C BOTH (ACCEPTED DIAGNOSTIC)
   │
   ▼
P4 Architecture Ablation ──► D TESTED BOTTLENECK (ACCEPTED DIAGNOSTIC)
   │
   ▼
P4.1 Marginal Admission ──► B CAPITAL/PATH DILUTION DOMINANT (DEVELOPMENT DIAGNOSTIC, 待外审)
   │
   ▼
S0 Stop-Loss Semantics ──► A OLD PHASE-A CONCLUSION ROBUST (ACCEPTED)
   │
   ▼
F1 Deep-MAE Recoverability ──► A STRONG RECOVERABILITY PREDICTABILITY (SUPERSEDED FOR INFERENCE BY F1.1, 描述性输出有效)
   │
   ▼
F1.1 Inference Remediation ──► FINAL A (CLOSE A / TOUCH A) (ACCEPTED — NO EXIT POLICY YET)
   │
   ▼
F2 Actionability Value Bound ──► D ACTIONABILITY NEGATIVE (DEVELOPMENT DIAGNOSTIC, 待外审)
   │
   ▼
★ CURRENT: Portfolio Architecture（组合架构瓶颈，研究暂停，等待外部审计）★
```

---

## 逐阶段入口

### 1. 原策略 / 红队审计
- **Canonical:** `[archive/superseded/REDTEAM_ROUND5_STRICT.md](archive/superseded/REDTEAM_ROUND5_STRICT.md)`（最终红队结论）
- **状态:** 原 +354.9% = **INVALID**（`[archive/invalid/RESULTS_LATEST.md](archive/invalid/RESULTS_LATEST.md)`）
- **原因:** same-bar 未来信息 / ETF open 时序 / PIT 状态 / 上市时间
- **结果数据:** `archive/invalid/results/`、`archive/invalid/results_exp/`

### 2. STRICT_C
- **Canonical:** `[research/signal/REDTEAM_ROUND51_STRICT.md](research/signal/REDTEAM_ROUND51_STRICT.md)`
- **源码:** `src/round51/round51_audit.py`、`src/run_strict_c.py`
- **结果数据:** `results/evidence/strict_c/round5/`
- **状态:** **ACCEPTED**（严格因果口径基线）

### 3. Independent Trade Replay（Signal Layer）
- **Canonical:** `[research/signal/INDEPENDENT_TRADE_REPLAY_V2_AUDIT.md](research/signal/INDEPENDENT_TRADE_REPLAY_V2_AUDIT.md)`
- **源码:** `research/signal/independent_trade_replay_v2.py`
- **结果数据:** `results/evidence/independent/`
- **状态:** **ACCEPTED** — Signal Layer **A**（Primary Top10 n=299: mean≈+4.96%, median≈+5.22%, win≈75.9%）
- **被取代:** `archive/superseded/INDEPENDENT_TRADE_REPLAY.md`（V1）

### 4. Full Market Trade Path
- **Canonical:** `[research/trade_path/FULL_MARKET_TRADE_PATH_AUDIT.md](research/trade_path/FULL_MARKET_TRADE_PATH_AUDIT.md)`
- **源码:** `research/trade_path/full_market_trade_path_audit.py`
- **结果数据:** `results/evidence/fullmarket/`（含 `fullmarket_episode_metrics.csv` 89,046 行）
- **状态:** **ACCEPTED** — 全市场 89,046 realized + 124 censored；信号结构 A；MAE 深度与最终交易质量显著相关
- **被取代:** `archive/superseded/TRADE_PATH_QUALITY_AUDIT.md`

### 5. Fixed Stop Phase A
- **Canonical:** `[research/execution/STOP_LOSS_COUNTERFACTUAL_PHASE_A.md](research/execution/STOP_LOSS_COUNTERFACTUAL_PHASE_A.md)`
- **源码:** `research/execution/stop_loss_counterfactual_phase_a.py`
- **结果数据:** `results/evidence/stopA/`
- **状态:** **SUPERSEDED BY S0** — raw first-entry stop 的复权语义问题由 S0 adjusted-space 修复闭环；Phase A 原结论为 `C — NO USEFUL STOP`，S0（ACCEPTED）确认其方向性结论在正确语义下仍成立
- **下游（S0 语义修复）：** `research/execution/STOP_LOSS_SEMANTICS_S0.md`

### 5a. S0 Stop-Loss Semantics Remediation
- **Canonical:** `[research/execution/STOP_LOSS_SEMANTICS_S0.md](research/execution/STOP_LOSS_SEMANTICS_S0.md)`
- **源码:** `research/execution/stop_loss_semantics_s0.py`
- **Registry:** `research/execution/registries/STOP_LOSS_SEMANTICS_S0_REGISTRY.csv`（SHA256 `7e8416fd...`，pre-reg `b352f77`）
- **结果数据:** `results/evidence/s0/`
- **状态:** **A — OLD PHASE-A CONCLUSION ROBUST TO ADJUSTED-SPACE SEMANTICS FIX**（**ACCEPTED**，S0.1 外审通过）— dev n=61,828；factor_changed 12.12%；11 档 adjusted 全低于 baseline；**S0.1 paired delta block-bootstrap 11/11 档 95% CI 上界 <0**（`s0_delta_block_bootstrap.csv`）；I1–I8 全 PASS；2025+ 未读

### 6. Temporal Clustering T1
- **Canonical:** `[research/market_state/TEMPORAL_CLUSTERING_PHASE_T1.md](research/market_state/TEMPORAL_CLUSTERING_PHASE_T1.md)`
- **源码:** `research/market_state/temporal_clustering_phase_t1.py`
- **结果数据:** `results/evidence/temporal/`
- **状态:** **ACCEPTED** — **A — STRONG**（runs z≈−11, lag1 ACF≈0.43；盈利/亏损显著按时间成团；有效独立信息量远小于 89k）

### 7. Market State T2（Discovery）
- **Canonical:** `[research/market_state/MARKET_STATE_PHASE_T2.md](research/market_state/MARKET_STATE_PHASE_T2.md)`
- **源码:** `research/market_state/market_state_phase_t2.py`（+ `STEP_A_PREREGISTER.py` / `STEP_B_VALIDATE.py`）
- **Registry:** `research/market_state/registries/TEMPORAL_STATE_FEATURE_REGISTRY.csv`（SHA256 `b686...c8407`）
- **结果数据:** `results/evidence/t2/`
- **状态:** **ACCEPTED AS DISCOVERY**（reverse-direction；27 predictors 预注册）

### 8. T2-R Reverse Validation
- **Canonical:** `[research/market_state/MARKET_STATE_REVERSE_VALIDATION.md](research/market_state/MARKET_STATE_REVERSE_VALIDATION.md)`
- **源码:** `research/market_state/STEP_A_PREREGISTER.py` / `STEP_B_VALIDATE.py`
- **Registry:** `research/market_state/registries/TEMPORAL_STATE_REVERSE_VALIDATION_REGISTRY.csv`
- **结果数据:** `results/evidence/t2r/`
- **状态:** **ACCEPTED** — **A — STRONG VALIDATION**（F02 ALL_A_EW_RET60 方向 NEGATIVE：Disc IC −0.441 / Val IC −0.417, BH q 0.0105, spread +2.75pp；F18 LIMIT_DOWN_SHARE 方向 POSITIVE：Val IC +0.164, BH q 0.021, spread +2.54pp）

### 9. Market Gate T3
- **Canonical:** `[research/market_state/MARKET_STATE_GATE_T3.md](research/market_state/MARKET_STATE_GATE_T3.md)`
- **源码:** `research/market_state/market_state_gate_t3.py`
- **Registry:** `research/market_state/registries/MARKET_STATE_GATE_REGISTRY.csv`
- **结果数据:** `results/evidence/t3/`
- **状态:** **CLOSED** — **C — NO USEFUL PORTFOLIO GATE**（硬门控失败；G0-G4 冻结，未来 Confirmation 主测 G1）
- **附:** `T3_R05_BASIS_CLARIFICATION.md`（R05 cutpoint 基数澄清）

### 10. Cross-sectional Ranking P1 / P1.1
- **Canonical:** `[research/ranking/CROSS_SECTIONAL_RANKING_P1_CORRECTED.md](research/ranking/CROSS_SECTIONAL_RANKING_P1_CORRECTED.md)`（P1.1 corrected）
- **源码:** `research/ranking/cross_sectional_ranking_p1_corrected.py`（+ `cross_sectional_ranking_p1.py` 被取代）
- **Registry:** `research/ranking/registries/CROSS_SECTIONAL_RANKING_REGISTRY.csv`（SHA256 `fa5beb5a...bab819`）
- **附:** `P1_RELATIVE_RETURN_INVARIANCE_NOTE.md`（REL_RET 同日内 rank-invariant 说明）
- **结果数据:** `results/evidence/p1/`、`results/evidence/p11/`
- **状态:** **ACCEPTED** — Discovery **A**（≥2 非冗余 predictor 通过 gate：RET3/RET20/DIST_MA20/ATR20_PCT/INTRADAY_RANGE）

### 11. P2 Ranking Validation
- **Canonical:** `[research/ranking/CROSS_SECTIONAL_RANKING_P2_VALIDATION.md](research/ranking/CROSS_SECTIONAL_RANKING_P2_VALIDATION.md)`
- **源码:** `research/ranking/STEP_A_RANKING_VALIDATE_PREREGISTER.py` / `STEP_B_RANKING_VALIDATE.py`
- **Registry:** `research/ranking/registries/CROSS_SECTIONAL_RANKING_VALIDATION_REGISTRY.csv`
- **结果数据:** `results/evidence/p2/`
- **状态:** **ACCEPTED** — **B — PARTIAL VALIDATION**（唯一 full pass：V04/F09 ATR20_PCT POS；Val daily CS IC≈+0.134, BH q≈1.6e-8, pairwise 55.23%, K3 lift +1.426pp, bootstrap CI [+0.50,+2.51]）

### 12. P3 ATR Slot Allocation
- **Canonical:** `[research/portfolio/ATR_SLOT_ALLOCATION_P3.md](research/portfolio/ATR_SLOT_ALLOCATION_P3.md)`
- **源码:** `research/portfolio/atr_slot_allocation_p3.py`
- **Registry:** `research/portfolio/registries/ATR_SLOT_ALLOCATION_REGISTRY.csv`
- **附:** `P3_FUTURE_CONFIRMATION_RULE.md`（未来 Confirmation 预注册标准）
- **结果数据:** `results/evidence/p3/`
- **状态:** **CLOSED** — **C — NO USEFUL PORTFOLIO RANKING**（dev 2020–2024 PURE STOCK 10bp：B0 +30.30% / B1 −18.66%；B2 FULL-SIGNAL NON-DEPLOYABLE）
- **附:** `P3_MECHANISM_CORRECTION_NOTE.md`（文档标签勘误，不影响 C 结论）

### 13. P3.1 Slot Contention
- **Canonical:** `[research/portfolio/SLOT_CONTENTION_PATH_AUDIT.md](research/portfolio/SLOT_CONTENTION_PATH_AUDIT.md)`
- **源码:** `research/portfolio/slot_contention_path_audit.py`
- **附:** `SLIPPAGE_PATH_DISCONTINUITY_AUDIT.md`
- **结果数据:** `results/evidence/p31/`
- **状态:** **ACCEPTED DIAGNOSTIC** — **C — BOTH**（ranking-actionable 仅 16/1212=1.32%；K=3 saturation 是主瓶颈；少数选择差异被 path dependence 放大）

### 14. P4 Portfolio Architecture Causal Decomposition
- **Canonical:** `[research/portfolio/PORTFOLIO_ARCHITECTURE_P4.md](research/portfolio/PORTFOLIO_ARCHITECTURE_P4.md)`
- **源码:** `research/portfolio/portfolio_architecture_p4.py`
- **Registry:** `research/portfolio/registries/PORTFOLIO_ARCHITECTURE_P4_REGISTRY.csv`（SHA256 `5f30974c...8ee6545`）
- **结果数据:** `results/evidence/p4/`
- **状态:** **ACCEPTED DIAGNOSTIC（外审通过）** — **D — TESTED ARCHITECTURE BOTTLENECK NOT EXPLAINED BY SIMPLE K/LAYER REMOVAL**（2020–2024 PURE STOCK 10bp 结构消融：A0 +30.30% / A1 K=999 −0.23% / A2 ML=1 −5.84% / A3 −29.27%。**K=3 是实际容量瓶颈（candidate 530 / blocked_K 336），但在当前历史样本与组合规则下同时表现为保护性的 admission constraint / implicit capacity filter**；A2 同批股票纯路径差异即可 ±50 万；A0 parity 精确通过。边界：仅测试极端消融 K 3→999、levels 5→1，未搜索 architecture space）
- **关键发现:** 解除 K 槽位（A1）→ 接入更差信号（新增 58 笔均值 −2,045）+ 资金稀释 → 收益崩盘；移除加仓（A2）→ 同一批股票、entry-level Jaccard 0.96，但 NEVER_RECONVERGED → 收益转负。真正局限在更深层（单笔信号边缘 + 路径依赖 + 深 MAE 长持仓占用），P4 禁止修改 exit。

### 14b. P4.1 Marginal Admission / Capacity Shadow-Price Audit
- **Canonical:** `[research/portfolio/MARGINAL_ADMISSION_P41.md](research/portfolio/MARGINAL_ADMISSION_P41.md)`
- **源码:** `research/portfolio/marginal_admission_p41.py`
- **Registry:** `research/portfolio/registries/MARGINAL_ADMISSION_P41_REGISTRY.csv`（SHA256 `6efc564f...3d6efed`）
- **结果数据:** `results/evidence/p41/`
- **状态:** **DEVELOPMENT DIAGNOSTIC（WAITING EXTERNAL AUDIT，未写入 README CURRENT TRUTH）** — **B — CAPITAL/PATH DILUTION DOMINANT**（A1_ONLY 58 笔独立 quality +3.28%/win 68.8% 仍为正，但实际 PnL −118,610；COMMON 65 笔同 key、same exit 100% 下 A1 少赚 67,116（STRONG CAPITAL/PATH DILUTION EVIDENCE）；A1_ONLY 深 MAE 率 40.6% vs COMMON 18.8%（SUGGESTIVE TAIL-QUALITY DETERIORATION）；A0_ONLY 独立 −1.97%/win40% 覆盖 45.5% → K=3 未证明系统性过滤坏信号；PnL bridge residual=0.00 精确闭合）
- **关键发现:** **H3（资本/路径稀释）主导**；H1（边际信号更差）仅 **suggestive tail-quality deterioration**，aggregate 独立质量未被统计建立为显著更差（事件日 bootstrap CI [−3.59,+1.73] 跨 0）。A1_ONLY 实际亏损集中在少数 deep-MAE 长持仓（4 笔 < −50k 合计 −308,226，其余 54 笔 +189,616）；同一批 COMMON 交易在 A1 中赢家被稀释 > 深亏减少。容量影子成本：每额外 1 笔 ≈ −6,494 元、每额外 slot-day ≈ −148 元。P4 结论保持不变。

### 14c. F1 Deep-MAE Recoverability / Failure-State Taxonomy
- **Canonical:** `[research/risk/FAILURE_STATE_F1.md](research/risk/FAILURE_STATE_F1.md)`
- **源码:** `research/risk/failure_state_f1.py`
- **Registry:** `research/risk/registries/FAILURE_STATE_F1_REGISTRY.csv`（SHA256 `a052309e...eef14`，pre-reg `1de126b`）
- **结果数据:** `results/evidence/f1/`
- **状态:** **DEVELOPMENT DIAGNOSTIC（WAITING EXTERNAL AUDIT，未写入 README CURRENT TRUTH）** — **A — STRONG RECOVERABILITY PREDICTABILITY**（D20 锚点 12,590 笔 / D30 6,130 笔；18 个预注册 primary 中 13 个通过完整 gate：方向 + BH q(m=18)<0.05 + 配对 block-bootstrap(L=21,B=2000) CI 排除 0 + D20/D30 同向）
- **关键发现:** ① 基线——D20 后 recover_to_entry 12.1%、final_profit 36.7%；跌到 −20% 后 ~90% 样本仍会再创新低、一半再跌 ≥7.5pp；② 最强 prospective 信号=浮亏深度×时长（F_DAYS_UNDERWATER −0.353 / F_DAYS_SINCE_FIRST_D10 −0.322 / F_DIST_MA20 −0.317）+ 波动率（F_ATR20_PCT +0.344 / F_INTRADAY_RANGE +0.321 / F_RV20 +0.305），F_CUR_MAE 单点深度不显著（q=0.123）；③ 收敛为约 3 个独立维度（深度×时长/波动/量能），不可表述为 13 个独立发现；④ 市场 overlay：弱市场/压力市场 deep-MAE 恢复率远高于强市场孤立超跌（R01 Q1 15.7% vs Q5 3.6%；R05 Q5 17.8% vs Q1 4.4%），与 T3 systemic-vs-isolated 呼应；⑤ 实现审计：F_DAYS_SINCE_LOW 因 anchor 定义 degenerate（恒 0）、F_NLOW10 方向与预注册相反不 pass。**本轮未设计任何 stop/exit/failure-score。**

### 14d. F1.1 Failure-State Inference Remediation
- **Canonical:** `[research/risk/FAILURE_STATE_F11.md](research/risk/FAILURE_STATE_F11.md)`
- **源码:** `research/risk/failure_state_f11.py`
- **Registry:** `research/risk/registries/FAILURE_STATE_F11_INFERENCE_REGISTRY.csv`（SHA256 `aacb2146...`，pre-reg `2cecd15`）
- **结果数据:** `results/evidence/f11/`
- **状态:** **ACCEPTED（R0.4 外审通过，2026-09-03）** — **FINAL = A — STRONG RECOVERABILITY PREDICTABILITY**（保守取 CLOSE/TOUCH 较低者；README CURRENT TRUTH 已新增一行，注明 **NO EXIT POLICY YET**）
- **关键修复:** ①primary 用全部 anchor dates（D20=752/D30=537，去 MIN_DAY_N=5）；②gate 方向/D20-D30 一致性改用 anchor-day day_corr（F_AMT_RATIO20 在 CLOSE 下 corrected 一致性 True→False，不再误 pass）；③双 outcome 语义 CLOSE/A（9 pass）与 TOUCH/A（11 pass），各 4 family（PRICE_PATH/POSITION/RECOVERY/VOLATILITY）；calendar block-bootstrap CI 全排除 0；MIN5 sensitivity 不改方向；D30 strengthening q=0（仅 537 天，如实报告）；sanity A–J 全 PASS；F1 Registry SHA 不变。**仍未设计任何 stop/exit/failure-score。**

### 14e. F2 Failure-State Actionability / Perfect-Information Value Bound
- **Canonical:** `[research/risk/FAILURE_STATE_F2.md](research/risk/FAILURE_STATE_F2.md)`
- **源码:** `research/risk/failure_state_f2.py`
- **Registry:** `research/risk/registries/FAILURE_STATE_F2_ACTIONABILITY_REGISTRY.csv`（SHA256 `9ed07a57...`，pre-reg `4e088fb`）
- **结果数据:** `results/evidence/f2/`
- **状态:** **INVALID / P0 — CAPITAL-BASIS MISMATCH（SUPERSEDED FOR INFERENCE BY F2.1）**：baseline ret0 分母含 D20 后 future adds，oracle return 分母只含 anchor 已持资本——不同 shares/资本基准，经济比较无效。历史 D 数字仅作记录，不得作 economic value 结论
- **关键数字:** O1/O2/O3 eventday Δ −2.28/−5.19/−4.81pp（HAC & calendar boot CI 全显著负）；TP benefit −4.13pp；FP cost −24.6~−30.3pp；confusion grid 28/28 负；break-even FPR 无解；anchor-close 乐观 −1.69pp 仍负。**未设计 predictor/stop/exit。**
### 14f. F2.1 Matched-Share Actionability / Perfect-Label Fixed-Action Value
- **Canonical:** `[research/risk/FAILURE_STATE_F21.md](research/risk/FAILURE_STATE_F21.md)`
- **源码:** `research/risk/failure_state_f21.py`
- **Registry:** `research/risk/registries/FAILURE_STATE_F21_MATCHED_ACTION_REGISTRY.csv`（SHA256 `12f8311c...`，pre-reg `02c6738`）
- **结果数据:** `results/evidence/f21/`
- **状态:** **B — NARROW POSITIVE ACTIONABILITY**（matched-share O1 core evidence 有效；break-even/precision 由 F2.2 修正；未写入 README CURRENT TRUTH）
- **关键数字:** O1 完美标签 D20+1 清仓 +1.45pp（HAC [0.48,2.42] / boot [0.40,2.61] 显著正）；O2/O3 跨 0；TP −0.46pp、FP −17.9~−25.0pp；natural exit 61,828 replay parity 0 误差；future-add 57.0%。**break-even/precision 见 F2.2（point BE 0.135–0.540、precision 0.762、safe frontier 0.05–0.30）。**未设计 predictor/stop/exit。
### 14g. F2.2 Break-Even / Precision Remediation
- **Canonical:** `[research/risk/FAILURE_STATE_F22.md](research/risk/FAILURE_STATE_F22.md)`
- **源码:** `research/risk/failure_state_f22.py`
- **Registry:** `research/risk/registries/FAILURE_STATE_F22_BREAK_EVEN_REGISTRY.csv`（SHA256 `aff9c429...`，pre-reg `a829298`）
- **结果数据:** `results/evidence/f22/`
- **状态:** **POINT BREAK-EVEN/PRECISION ACCEPTED**（F2.3 完成 sampling 推断后 classification 仍 **B**；未写入 README CURRENT TRUTH）
- **关键数字:** A=+1.4486pp、B=−2.6833pp；point break-even FPR 0.135/0.270/0.405/0.540；break-even precision 0.762（ACCEPTED）。**calendar-safe frontier（F2.3）：0.00/0.05/0.10/0.10；randomization interval 仅 reference。**未设计 predictor/stop/exit/timing。
### 14h. F2.3 Policy-Value Sampling Inference
- **Canonical:** `[research/risk/FAILURE_STATE_F23.md](research/risk/FAILURE_STATE_F23.md)`
- **源码:** `research/risk/failure_state_f23.py`
- **Registry:** `research/risk/registries/FAILURE_STATE_F23_POLICY_VALUE_INFERENCE_REGISTRY.csv`（SHA256 `c0f4d1d2...`，pre-reg `73b9c19`）
- **结果数据:** `results/evidence/f23/`
- **状态:** **DEVELOPMENT DIAGNOSTIC（WAITING EXTERNAL AUDIT，未写入 README CURRENT TRUTH）** — policy-value 历史采样推断完成，classification 仍 B
- **关键数字:** V_d=t·A_d+f·B_d 确定性；O1 parity PASS（HAC [0.48,2.42] / CAL [0.40,2.61]）；**calendar-safe frontier 0.00/0.05/0.10/0.10**（HAC 一致）；.75/.30、1.00/.30 在 sampling 下跨 0；randomization interval 仅 reference。未设计 predictor/stop/exit/timing。
### 15. ★ CURRENT: Portfolio Architecture（组合架构）
- **状态:** 研究**暂停**。当前唯一活跃问题是：有限 K=3 slots + 长持仓 + 多层占位/路径依赖的组合架构如何提升资金效率。
- **P4 进展（2026-09-03，ACCEPTED DIAGNOSTIC，外审通过）:** 结构性消融显示 K=3 是实际容量瓶颈，但在当前历史样本与组合规则下同时表现为保护性的 admission constraint（解除任一约束组合均大幅恶化）；完全移除多层加仓（5→1 层）在测试路径下有害（不断言 5 层最优）。瓶颈在更深层。下一步必须等待外部审计决定；2025–2026 Confirmation 继续 CLOSED。
- **P4.1 进展（2026-09-03，DEVELOPMENT DIAGNOSTIC，待外审）:** 解除 K 的恶化 = **B — CAPITAL/PATH DILUTION DOMINANT**——主因是共享资本/路径稀释（COMMON 同 65 笔、same exit 下 A1 少赚 67k，STRONG H3 证据）；H1 仅为 **suggestive tail-quality deterioration**（深 MAE 率 2.2×、最差几笔独立深亏），aggregate 独立质量未被统计建立为显著更差；A0_ONLY 覆盖 45.5% 显示 K=3 未证明系统性过滤坏信号。A1_ONLY 独立整体仍为正但实际 PnL −118,610。待外审后决定是否更新 README CURRENT TRUTH。

---

## 预注册 Registry 索引

| Registry | 位置 | 冻结 commit |
|---|---|---|
| 104-cell Hypothesis Registry | `[archive/superseded/HYPOTHESIS_REGISTRY.csv](archive/superseded/HYPOTHESIS_REGISTRY.csv)` | `0d5979bf`（原始，历史） |
| T2 Feature Registry | `research/market_state/registries/` | `0d5979bf`（T2 registry commit） |
| T2-R Reverse Validation Registry | `research/market_state/registries/` | T2-R registry commit |
| P1 Ranking Registry | `research/ranking/registries/` | `9c36887` |
| P2 Ranking Validation Registry | `research/ranking/registries/` | `83c3f1e` |
| ATR Slot Allocation Registry | `research/portfolio/registries/` | P3 registry commit |
| Market State Gate Registry | `research/market_state/registries/` | T3 registry commit |
| Portfolio Architecture P4 Registry | `research/portfolio/registries/` | `70588a7`（P4-A） |
| Marginal Admission P4.1 Registry | `research/portfolio/registries/` | `c6c2865`（P4.1-A） |
| S0 Stop-Loss Semantics Registry | `research/execution/registries/` | `b352f77`（S0-A） |
| F1 Failure-State Registry | `research/risk/registries/` | `1de126b`（F1-A） |
| F1.1 Inference Remediation Registry | `research/risk/registries/` | `2cecd15`（F1.1-A） |
| F2 Actionability Value Bound Registry | `research/risk/registries/` | `4e088fb`（F2-A，INVALID/P0） |
| F2.1 Matched-Share Actionability Registry | `research/risk/registries/` | `02c6738`（F2.1-A） |
| F2.2 Break-Even Precision Registry | `research/risk/registries/` | `a829298`（F2.2-A） |
| F2.3 Policy-Value Inference Registry | `research/risk/registries/` | `73b9c19`（F2.3-A） |

---

## 完整性审计

- `[CANONICAL_ARTIFACT_INTEGRITY.csv](CANONICAL_ARTIFACT_INTEGRITY.csv)` — 468 个迁移文件迁移前后 SHA256 全部 **UNCHANGED**
- `[DUPLICATE_FILE_AUDIT.csv](DUPLICATE_FILE_AUDIT.csv)` — 7 组字节级重复（历史命名证据，保留并说明）
- `[BROKEN_LINK_AUDIT.md](BROKEN_LINK_AUDIT.md)` — Markdown 内部链接扫描（目标 0 unresolved）
- 远程 Git 验证：`[REMOTE_VERIFICATION.md](REMOTE_VERIFICATION.md)`（P3.1 commit `a4fed2b` 已 push，remote_contains_commit=YES）
