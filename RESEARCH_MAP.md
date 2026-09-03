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
P4.1 Marginal Admission ──► C BOTH (DEVELOPMENT DIAGNOSTIC, 待外审)
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
- **状态:** **PROVISIONAL / SEMANTICS ISSUE** — raw first-entry stop vs adjusted-space 问题未正式关闭，**不得误标 ACCEPTED**；结论为 `C — NO USEFUL STOP`

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

---

## 完整性审计

- `[CANONICAL_ARTIFACT_INTEGRITY.csv](CANONICAL_ARTIFACT_INTEGRITY.csv)` — 468 个迁移文件迁移前后 SHA256 全部 **UNCHANGED**
- `[DUPLICATE_FILE_AUDIT.csv](DUPLICATE_FILE_AUDIT.csv)` — 7 组字节级重复（历史命名证据，保留并说明）
- `[BROKEN_LINK_AUDIT.md](BROKEN_LINK_AUDIT.md)` — Markdown 内部链接扫描（目标 0 unresolved）
- 远程 Git 验证：`[REMOTE_VERIFICATION.md](REMOTE_VERIFICATION.md)`（P3.1 commit `a4fed2b` 已 push，remote_contains_commit=YES）
