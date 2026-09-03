# A股 BB 均值回归策略 · 研究级审计仓库

> 成交额TopN + 布林带(20,2)下轨超跌信号 + 5层分批建仓 + 动态 P\* 止盈
> 样本区间：2020-01-02 ~ 2026-08-25 · 全市场 A 股
> 本仓库是一份**逐年推进的、可审计的研究档案**，不含任何真实 Token / 密钥 / 个人账号信息。
> 当前唯一权威入口：`README.md`（现状）→ `[CURRENT_STATUS.md](CURRENT_STATUS.md)`（结论冻结表）→ `[RESEARCH_MAP.md](RESEARCH_MAP.md)`（研究链地图）。

---

## 一、这个项目研究什么？

围绕一个具体假设展开的研究级审计：

> **"A 股中跌破布林带下轨（20,2）的超跌股票，其后存在可利用的均值回归收益吗？"**

研究不满足于"回测能赚多少"，而是逐层拆解以下问题：

1. 原回测结果是否可信（lookahead / PIT / 执行语义）？
2. 信号本身（在严格因果口径下）是否有正期望？
3. 信号质量的**时间结构**如何（是否成团、可预测）？
4. 市场状态能否提前识别好坏时期？
5. 有限的资金（K=3 / 200k 层 / 5 层）该把稀缺 slot 分配给哪些股票？
6. 为什么横截面有效的排序信号在真实组合里无法兑现？

**当前答案一句话：** 信号层存在稳健的正 edge；时间聚类与市场状态都有统计意义；但**硬门控（Hard Gate）与单因子选股（Ranking）在有限资金组合里均无法改善实盘结果**——真正的瓶颈是组合架构（有限 K=3 slots + 长持仓 + 多层占位 + 路径依赖），而非缺乏信号级 alpha。

---

## 二、原 +354.9% 为什么无效？

原回测结果因**确定性致命方法错误**被判定 INVALID，不得作为任何策略有效性的证据：

| 缺陷 | 说明 | 影响 |
|---|---|---|
| 同Bar未来信息 | 当日盘中交易使用了**当日收盘后才能确定的**布林上轨止盈价 | 系统性高估收益 |
| ETF 执行时序错误 | ETF 现金管理腿存在 open 时间倒流 / 单一全天价 | 组合收益失真 |
| PIT 状态 / 上市时间 | 股票 ST 状态与上市日使用事后快照 | 幸存者偏差 |
| 乐观 tick 语义 | 非可执行 tick 成交假设 | 高估可成交性 |

> ⚠️ 这些 INVALID 结果的原始文件仍在 `[archive/invalid/](archive/invalid/)`（**保留证据**），但**严禁作为策略表现证据引用**。详见该目录 README。

---

## 三、现在仍成立的证据是什么？（当前真相）

以下是**已经冻结并结案**的结论，全部有 canonical 报告可查。详见 `[CURRENT_STATUS.md](CURRENT_STATUS.md)` 完整冻结表与 `[RESEARCH_MAP.md](RESEARCH_MAP.md)` 各阶段入口。

| 问题 | Canonical 证据 | 判定 | 状态 |
|---|---|---|---|
| STRICT_C 严格因果口径回测 | `[research/signal/REDTEAM_ROUND51_STRICT.md](research/signal/REDTEAM_ROUND51_STRICT.md)` | STRICT_C 基线成立 | ACCEPTED |
| 独立交易重放（Primary Top10, n=299） | `[research/signal/INDEPENDENT_TRADE_REPLAY_V2_AUDIT.md](research/signal/INDEPENDENT_TRADE_REPLAY_V2_AUDIT.md)` | mean≈+4.96%, median≈+5.22%, win≈75.9% · **Signal Layer A** | ACCEPTED |
| 全市场 89,046 笔独立交易 | `[research/trade_path/FULL_MARKET_TRADE_PATH_AUDIT.md](research/trade_path/FULL_MARKET_TRADE_PATH_AUDIT.md)` | 信号结构 **A** 成立 | ACCEPTED |
| 时间聚类 | `[research/market_state/TEMPORAL_CLUSTERING_PHASE_T1.md](research/market_state/TEMPORAL_CLUSTERING_PHASE_T1.md)` | **A — STRONG**（runs z≈−11, lag1 ACF≈0.43） | ACCEPTED |
| 市场状态前瞻解释 | `[research/market_state/MARKET_STATE_PHASE_T2.md](research/market_state/MARKET_STATE_PHASE_T2.md)`（Discovery）<br>`[research/market_state/MARKET_STATE_REVERSE_VALIDATION.md](research/market_state/MARKET_STATE_REVERSE_VALIDATION.md)`（T2-R） | **A — STRONG VALIDATION**（F02 ALL_A_EW_RET60 反向、F18 LIMIT_DOWN_SHARE） | ACCEPTED |
| 个股横截面排序 | `[research/ranking/CROSS_SECTIONAL_RANKING_P1_CORRECTED.md](research/ranking/CROSS_SECTIONAL_RANKING_P1_CORRECTED.md)`（Discovery）<br>`[research/ranking/CROSS_SECTIONAL_RANKING_P2_VALIDATION.md](research/ranking/CROSS_SECTIONAL_RANKING_P2_VALIDATION.md)`（Validation） | Discovery **A**；Validation **B — PARTIAL**（唯一 full pass：ATR20_PCT） | ACCEPTED |
| Deep-MAE failure/recovery state | `[research/risk/FAILURE_STATE_F11.md](research/risk/FAILURE_STATE_F11.md)`（F1.1 corrected anchor-day inference） | **PROSPECTIVELY IDENTIFIABLE (A, F1.1)** —— **NO EXIT POLICY YET** | ACCEPTED |
| Failure-state actionability | `[research/risk/FAILURE_STATE_F23.md](research/risk/FAILURE_STATE_F23.md)`（F2.3 matched-share fixed-action diagnostic） | **POSITIVE BUT NARROW (B)** —— **NO DEPLOYABLE PREDICTOR YET** | ACCEPTED |
| 2025–2026 Confirmation | — | **全程 UNTOUCHED / CLOSED** | CLOSED |

---

## 四、什么尝试已经失败？

研究链中所有**明确失败的尝试**同样被完整保留，是当前结论的一部分：

| 尝试 | 结论 | 状态 |
|---|---|---|
| Fixed Price Stop（Phase A） | PROVISIONAL：raw-space 证据对固定止损不利（系统性错杀最终赢家），但 **adjusted-price-space 止损语义仍未解决**，未正式关闭 | PROVISIONAL · SEMANTICS ISSUE（不可正式写为 CLOSED） |
| Market-State Hard Gate（T3） | `C — NO USEFUL PORTFOLIO GATE`（删信号改变组合路径后更差） | CLOSED |
| ATR20_PCT Slot Allocation（P3） | `C — NO USEFUL PORTFOLIO RANKING`（B0 +30.30% vs B1 −18.66%） | CLOSED |
| 原 +354.9% / 乐观 tick / 参数扫描 | `INVALID` | 见 `[archive/invalid/](archive/invalid/)` |

> 关键教训：**独立交易层面有效的信号，不代表放进真实有限资金组合后有效**。原因在 P3.1 中定位：`C — BOTH`（ranking-actionable 仅 16/1212=1.32%，K=3 饱和是主瓶颈，少数选择差异被路径依赖放大）。

---

## 五、当前研究问题

```
原策略 +354.9% ──► 无效（lookahead / PIT）
      │
      ▼
STRICT_C ──► 独立重放 A ──► 全市场 89k A ──► 时间聚类 A ──► 市场状态 A（已验证）
      │                                                    │
      ▼                                                    ▼
   信号层 edge 为正                            硬门控 T3 = C（失败）
      │
      ▼
   横截面排序 Discovery A / Validation B（ATR20_PCT 唯一 full pass）
      │
      ▼
   P3 ATR Slot Allocation = C（真实组合失败）
      │
      ▼
   P3.1 Slot Contention = C — BOTH
      │
      ▼
   ★ CURRENT：瓶颈是组合架构（有限 K=3 slots + 长持仓 + 多层占位/路径依赖），
     而非缺乏 signal-level edge。★
```

**当前活跃问题：** 在有限 K=3 slots / 200k 层 / 5 层、长持仓 + 多层加仓 + 路径依赖的组合架构下，如何提升资金利用效率与整体组合质量？——**本轮只整理仓库，不研究该问题。下一研究阶段必须等待外部审计决定。**

---

## 六、CURRENT EVIDENCE TABLE

| Question | Canonical Evidence | Verdict | Status |
|---|---|---|---|
| 原 +354.9% 是否可信？ | `[RESULTS_LATEST.md](archive/invalid/RESULTS_LATEST.md)`（见 [archive/invalid/](archive/invalid/)） | INVALID（same-bar 未来信息等） | INVALID |
| BB 超跌信号本身有无 edge？ | `[research/signal/INDEPENDENT_TRADE_REPLAY_V2_AUDIT.md](research/signal/INDEPENDENT_TRADE_REPLAY_V2_AUDIT.md)` | 有（Signal Layer A） | ACCEPTED |
| 89k 全市场交易说明什么？ | `[research/trade_path/FULL_MARKET_TRADE_PATH_AUDIT.md](research/trade_path/FULL_MARKET_TRADE_PATH_AUDIT.md)` | 结构 A，MAE 深度与质量显著相关 | ACCEPTED |
| 市场状态有无预测力？ | `[research/market_state/MARKET_STATE_REVERSE_VALIDATION.md](research/market_state/MARKET_STATE_REVERSE_VALIDATION.md)` | 有（A — STRONG VALIDATION） | ACCEPTED |
| 市场门控为何失败？ | `[research/market_state/MARKET_STATE_GATE_T3.md](research/market_state/MARKET_STATE_GATE_T3.md)` | C — NO USEFUL PORTFOLIO GATE | CLOSED |
| 横截面排序有无验证？ | `[research/ranking/CROSS_SECTIONAL_RANKING_P2_VALIDATION.md](research/ranking/CROSS_SECTIONAL_RANKING_P2_VALIDATION.md)` | B — PARTIAL（ATR20_PCT 唯一 full pass） | ACCEPTED |
| ATR 为何未改善真实组合？ | `[research/portfolio/ATR_SLOT_ALLOCATION_P3.md](research/portfolio/ATR_SLOT_ALLOCATION_P3.md)` + `[research/portfolio/SLOT_CONTENTION_PATH_AUDIT.md](research/portfolio/SLOT_CONTENTION_PATH_AUDIT.md)` | C（组合路径依赖主导） | CLOSED |
| 固定价格止损是否有效？ | `[research/execution/STOP_LOSS_SEMANTICS_S0.md](research/execution/STOP_LOSS_SEMANTICS_S0.md)`（adjusted-space 复权语义修复 + 配对推断） | Fixed price stop: **ACCEPTED NEGATIVE RESULT**（11 档均有害） | ACCEPTED |
| 2025–2026 是否被打开？ | — | 否（UNTOUCHED） | CLOSED |

---

## 七、仓库导航

```
README.md            ← 你在这里：项目现状（第一屏）
[CURRENT_STATUS.md](CURRENT_STATUS.md)    ← 所有研究结论的冻结总表（含 INVALID/SUPERSEDED 分类）
[RESEARCH_MAP.md](RESEARCH_MAP.md)      ← 研究链地图（每个阶段 → 唯一 canonical 报告）
[REPO_INVENTORY.csv](REPO_INVENTORY.csv)   ← 全仓库 621 个文件的分类清单（status / canonical / 落点）
[MIGRATION_MAP.csv](MIGRATION_MAP.csv)    ← 468 个文件的迁移映射（旧路径 → 新路径）
CANONICAL_ARTIFACT_INTEGRITY.csv ← 迁移前后 canonical 文件 SHA256 校验（ALL UNCHANGED）
DUPLICATE_FILE_AUDIT.csv         ← 字节级重复文件审计
BROKEN_LINK_AUDIT.md             ← Markdown 内部链接完整性（目标 0 unresolved）
REMOTE_VERIFICATION.md           ← 远程 Git 验证记录

research/            ← 各研究阶段源码 + 报告（signal / execution / trade_path /
                        market_state / ranking / portfolio）
src/                 ← 当前有效、可复用的共享引擎（含 STRICT_C frozen engine）
results/evidence/    ← 各阶段原始结果数据（按 phase 归档，不删除）
[results/current/](results/current/)     ← 当前结论真正需要的 summary 文件（≤15 个）
[archive/invalid/](archive/invalid/)     ← 已确认致命方法错误的产物（保留证据，禁止引用）
archive/superseded/  ← 被更严格版本替代的产物（保留证据）
data/                ← 原始数据说明（派生数据不在仓库内，见 data_docs/）
```

---

## 八、审计入口

新审计员按以下顺序阅读，10 分钟内应能回答 README 第一节的五个问题：

1. `README.md`（本文件）
2. `[CURRENT_STATUS.md](CURRENT_STATUS.md)`
3. `[RESEARCH_MAP.md](RESEARCH_MAP.md)`
4. 需要深入时：各阶段 canonical 报告 + `results/evidence/<phase>/` 数据
5. 验证工具：`tests/test_backtest_invariants.py`（需在数据齐全环境下运行，见 `data_docs/`）

> ⚠️ 派生数据（`combined_daily.parquet` / `pit_st_daily.parquet` 等）不在本仓库内（体积大不入库）。复现/运行测试需在主工作区数据齐全环境下进行，仓库 `data/` 仅含原始 kline 分片供核实。
