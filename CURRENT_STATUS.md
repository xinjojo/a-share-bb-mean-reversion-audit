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
| 6 | Fixed Stop Phase A | **PROVISIONAL / SEMANTICS ISSUE**（raw first-entry stop vs adjusted-space 问题未正式关闭，**不得误标 ACCEPTED**） | PROVISIONAL | `[research/execution/STOP_LOSS_COUNTERFACTUAL_PHASE_A.md](research/execution/STOP_LOSS_COUNTERFACTUAL_PHASE_A.md)` |
| 7 | Temporal Clustering T1 | **A — STRONG TEMPORAL CLUSTERING**（runs z≈−11, lag1 ACF≈0.43, 盈利/亏损显著按时间成团） | ACCEPTED | `[research/market_state/TEMPORAL_CLUSTERING_PHASE_T1.md](research/market_state/TEMPORAL_CLUSTERING_PHASE_T1.md)` |
| 8 | Market State T2（Discovery） | reverse-direction discovery | ACCEPTED AS DISCOVERY | `[research/market_state/MARKET_STATE_PHASE_T2.md](research/market_state/MARKET_STATE_PHASE_T2.md)` |
| 9 | T2-R Reverse Validation | **A — STRONG VALIDATION**（F02 ALL_A_EW_RET60 方向 NEGATIVE：Disc IC −0.441 / Val IC −0.417, BH q 0.0105, spread +2.75pp；F18 LIMIT_DOWN_SHARE 方向 POSITIVE：Val IC +0.164, BH q 0.021, spread +2.54pp） | ACCEPTED | `[research/market_state/MARKET_STATE_REVERSE_VALIDATION.md](research/market_state/MARKET_STATE_REVERSE_VALIDATION.md)` |
| 10 | Market Gate T3 | **C — NO USEFUL PORTFOLIO GATE**（删信号改变组合路径后更差） | CLOSED | `[research/market_state/MARKET_STATE_GATE_T3.md](research/market_state/MARKET_STATE_GATE_T3.md)` |
| 11 | P1 / P1.1 Ranking（Discovery） | **A — STRONG CROSS-SECTIONAL RANKING**（≥2 非冗余 predictor：RET3/RET20/DIST_MA20/ATR20_PCT/INTRADAY_RANGE 通过完整 gate） | ACCEPTED | `[research/ranking/CROSS_SECTIONAL_RANKING_P1_CORRECTED.md](research/ranking/CROSS_SECTIONAL_RANKING_P1_CORRECTED.md)` |
| 12 | P2 Ranking Validation | **B — PARTIAL VALIDATION**（唯一 full pass：V04/F09 ATR20_PCT，POS；Val daily CS IC≈+0.134, BH q≈1.6e-8, pairwise 55.23%, K3 lift +1.426pp） | ACCEPTED | `[research/ranking/CROSS_SECTIONAL_RANKING_P2_VALIDATION.md](research/ranking/CROSS_SECTIONAL_RANKING_P2_VALIDATION.md)` |
| 13 | P3 ATR Slot Allocation | **C — NO USEFUL PORTFOLIO RANKING**（dev 2020–2024 PURE STOCK 10bp：B0 +30.30% / B1 −18.66%；B2 NON-DEPLOYABLE） | CLOSED | `[research/portfolio/ATR_SLOT_ALLOCATION_P3.md](research/portfolio/ATR_SLOT_ALLOCATION_P3.md)` |
| 14 | P3.1 Slot Contention | **C — BOTH**（ranking-actionable 仅 16/1212=1.32%；K=3 saturation 是主瓶颈；少数选择差异被 path dependence 放大） | ACCEPTED DIAGNOSTIC | `[research/portfolio/SLOT_CONTENTION_PATH_AUDIT.md](research/portfolio/SLOT_CONTENTION_PATH_AUDIT.md)` |
| 14b | P4 Portfolio Architecture Causal Decomposition | **D — TESTED ARCHITECTURE BOTTLENECK NOT EXPLAINED BY SIMPLE K/LAYER REMOVAL**（结构消融 2020–2024 PURE STOCK 10bp：A0 +30.30% / A1 K=999 −0.23% / A2 ML=1 −5.84% / A3 −29.27%。**K=3 是实际容量瓶颈（candidate 530 / blocked_K 336），但在当前历史样本与组合规则下同时表现为保护性的 admission constraint / implicit capacity filter**；解除任一约束均大幅恶化；A2 同批股票纯路径差异即可 ±50 万；A0 parity 精确通过。边界：P4 仅测试极端消融 K 3→999、levels 5→1，未搜索 architecture space，不构成"K/layer 结构不重要"的全局断言） | ACCEPTED DIAGNOSTIC（外审通过） | `[research/portfolio/PORTFOLIO_ARCHITECTURE_P4.md](research/portfolio/PORTFOLIO_ARCHITECTURE_P4.md)` |
| 14c | P4.1 Marginal Admission / Capacity Shadow-Price Audit | **C — BOTH**（A1_ONLY 58 笔独立 quality +3.28%/win 68.8% 仍为正，但实际 PnL −118,610；COMMON 65 笔同 key 在 A1 少赚 67,116（赢家稀释>深亏减少）；A1_ONLY 深 MAE 率 40.6% vs COMMON 18.8%，最差几笔独立 return −18%~−22%、MAE −37%~−55% 本就被坏信号标记；PnL bridge residual=0.00 精确闭合；容量影子成本每额外 1 笔 ≈ −6,494 元。**H1 边际信号更差 + H3 资本/路径稀释 = both**；P4 结论保持不变） | DEVELOPMENT DIAGNOSTIC（WAITING EXTERNAL AUDIT，未写入 README CURRENT TRUTH） | `[research/portfolio/MARGINAL_ADMISSION_P41.md](research/portfolio/MARGINAL_ADMISSION_P41.md)` |
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

**P4.1 进展（2026-09-03，DEVELOPMENT DIAGNOSTIC，待外审）：** 解除 K 的恶化 = **C — BOTH**：
（1）**H1 部分成立**——A1_ONLY 边际信号深 MAE 率 40.6%（2.2× COMMON），最差几笔
（002714/300750/000625）独立 return −18%~−22%、MAE −37%~−55%，本来就被坏信号标记；
（2）**H3 部分成立**——A1_ONLY 覆盖样本独立整体仍 +3.28%/win 68.8%，但实际 PnL −118,610，
COMMON 同 65 笔在 A1 少赚 67,116（赢家被共享资金稀释 > 深亏减少）。PnL bridge residual=0.00
精确闭合。容量影子成本：每额外 1 笔 ≈ −6,494 元、每额外 slot-day ≈ −148 元。

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

---

## 五、关键冻结参数（引擎口径，不可改）

- `prepare_v51(limit_down_mode='correct', st_mode='pit')`：offset=7100, days[0]=2020-01-02, 共 1611 交易日, N2024=1212（2024-12-31 开发期边界）
- 组合：initial_capital=1,000,000 RMB, K=3, layer=200,000 RMB, max_levels=5, slippage_bp=10, T+1, 100股 lot, PIT ST, listing≥60 trading days, dynamic P\*, etf_enabled=False（PURE STOCK）
- 独立样本：`results/evidence/fullmarket/fullmarket_episode_metrics.csv`（89,046 行）

---

## 六、数据可用性

审计仓库 `data/` 仅含**原始 kline 分片**（`data/kline/2020..2026.parquet` 等，供审计核实）。**派生数据**（`combined_daily.parquet` / `pit_st_daily.parquet` / `raw/stock_basic.parquet` / `raw/trade_cal_full.parquet` / `etf_513500_merged.parquet`）**不在仓库内**（体积大不入库）。复现/运行 `tests/` 需在主工作区数据齐全环境下进行。详见 `[data_docs/KLINE_DATA.md](data_docs/KLINE_DATA.md)`。
