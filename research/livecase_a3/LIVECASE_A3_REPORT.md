# LIVECASE-A3 REPORT — FROZEN96 PROVENANCE / REPRODUCIBILITY FORENSIC AUDIT

项目：A股 BB Mean Reversion 审计（2026）
阶段：LIVECASE-A3（承接 LIVECASE-A2 commit `2daf3aa`）
日期：2026-09-06
commit：见 git log（本阶段 commit message: `LIVECASE-A3: frozen96 provenance and replay reproducibility forensic audit`）

---

## 0. 背景

- frozen portfolio = 96 笔（`results/evidence/strict_c/round5/strict_c_trades.csv`）
- current replay = 97 笔
- 此前 LIVECASE-A2 确认：P* 数学实现正确；13 个用户点名日期中 11 个当前数据下未触发、2 个提前触发（牧原 2020-06-18、茅台 2023-12-29）；但历史输入不可复算（HISTORICAL_INPUT_UNAVAILABLE）。
- 本阶段目标：证明 frozen96 怎么生成的、为什么今天无法 exact replay（或证明它可以 exact replay），**禁止无证据声称 data drift**。

---

## 1. 核心发现（一句话版）

**frozen96 就是 566db88 引擎 + 当前这份数据在 2026-09-02 生成的产物，逐字节可复现；96 vs 97 的差异全部来自 8c479f6 的 P0 复权口径修正（+P1 tick +FIX2），不是数据版本变化。**

---

## 2. 证据链

### E1 谱系
- `git log --follow -- results/round5/strict_c_trades.csv`：首次出现 = `566db88`（2026-09-02 20:42）。
- `git ls-tree 566db88 results/round5/strict_c_trades.csv` → blob `d98549cbac7c83dea7991002c0f14a0c044721dc`，与 evidence 路径 blob 相同；b343256 为 `git mv` 迁移，零改动。
- 内容 SHA256 = `76f401fd67710d7cb15ba20db9107b719b40aa0176ce0d27c1f8198ab91bde55`。

### E2 逐字节复现
- 检出 566db88 到独立 worktree，软链当前数据，`run_strict_c.py c` 复跑 → **96 笔，total +89.148731%，stock_pnl 545,730.26**。
- 复跑产物与 frozen blob `cmp` → **IDENTICAL**。

### E3 数据身份
- `combined_daily.parquet` mtime 2026-09-01 23:15 < frozen commit 2026-09-02 20:42 → 生成时读的就是当前文件。
- 逐字节复现成立 → 排除任何"不同数据"假说。**data drift 不成立，HISTORICAL_INPUT_UNAVAILABLE 结论被推翻**：历史输入 = 当前数据，AVAILABLE。

### E4 差异根因 = 代码版本
- 8c479f6 内嵌 `p0_audit.csv`（3253 行逐日 P*_old vs P*_correct）记录 **5 个触发改变日**，与 5 笔 exit mismatch **一一对应**：
  - 002714.SZ 2020-06-18（151.44→72.62，触发）
  - 002415.SZ 2022-06-06（35.459→34.768，触发）
  - 601899.SH 2022-10-27（8.362，old 触发→corrected 不触发，顺延一日）
  - 600519.SH 2023-12-29（1751.89→1737.93，触发）
  - 600519.SH 2025-07-10（1442.15→1427.51，触发）
- 当前 replay（97）与 8c479f6 产物（97）**97/97 零差异** → 当前引擎 = 8c479f6 修正口径。

### E5 first divergence
- 逐日动作级对比：**2020-06-18**，类型 EXIT（current 多 `002714.SZ TAKE_PROFIT_DYN lv1`）；前一交易日双流一致。
- 牧原 2020-06 除权（因子 7.5891→12.9598 区间）：566 旧口径 P*_raw=151.44（19 日 raw×当日 adj，错误），06-18 high 73.18 不触发；修正口径 72.62，触发。
- 现金/ETF 层在 06-17 已存在千元级微小差异（etf_sh 213,100 vs 214,200），由共享现金池浮点/阈值敏感传播；股票动作层 primary divergence 仍是 06-18。

---

## 3. 差异清单

### 3.1 5 笔 exit mismatch（全部 CODE_VERSION_PROVEN）

| ts_code | entry | frozen exit | replay exit | p0 改变日 | 566 P*_old → corrected |
|---|---|---|---|---|---|
| 002714.SZ | 2020-05-12 | 2020-07-06 | **2020-06-18** | 2020-06-18 | 151.44 → 72.62 |
| 600519.SH | 2023-10-16 | 2024-02-06 | **2023-12-29** | 2023-12-29 | 1751.89 → 1737.93 |
| 600519.SH | 2025-06-16 | 2025-07-11 | 2025-07-10 | 2025-07-10 | 1442.15 → 1427.51 |
| 601899.SH | 2022-09-27 | 2022-10-27 | 2022-10-28 | 2022-10-27 | 8.362（反向） |
| 002415.SZ | 2022-05-09 | 2022-06-08 | 2022-06-06 | 2022-06-06 | 35.459 → 34.768 |

### 3.2 4 笔 levels mismatch（全部 PORTFOLIO_PATH_PROPAGATION）

| ts_code | entry | frozen | current | 缺失的 add | 机制 |
|---|---|---|---|---|---|
| 601919.SH | 2024-07-15 | 3 | 2 | 2024-09-06 | 茅台61 12-29 早退 → 现金时点变化 |
| 600519.SH | 2022-10-13 | 3 | 2 | 2022-10-28 | 601899 退迟一日 → 10-28 现金给 000858 新入 |
| 601012.SH | 2024-01-30 | 2 | 1 | 2024-02-01 | 002230 01-04 用茅台61 早退现金入场 |
| 300418.SZ | 2023-06-27 | 2 | 1 | 2023-06-29 | current 06-29 现金 465.96 无 ETF；566 现金 5,006+ETF 93,900 |

### 3.3 3 笔 entry 差异（全部 PATH_PROPAGATION）
- frozen-only：000858.SZ|2022-10-28（601899 延迟到 10-28 卖 → 现金未到）
- current-only：300750.SZ|2022-10-31（frozen 10-28 买五粮液占资金 → current 未买 → 10-31 补位宁德）
- current-only：002230.SZ|2024-01-04（茅台61 12-29 早退放水）

### 3.4 第 97 笔
= current replay 相对 frozen96 的净增 1 笔（current-only 2 笔 − frozen-only 1 笔 = +1）。它不是"新发现的数据"或"新信号"，是 P0 修正改变退出时点 → 现金 → 入场路径传播的产物。

---

## 4. 关键问题逐项回答

| 问题 | 答案 |
|---|---|
| 牧原 2020-06-18，历史引擎 + 当前数据是否触发 | **566 引擎：否**（P*=151.44 > high 73.18）；8c479f6 修正引擎：**是**（72.62）。触发=代码版本 |
| 茅台 2023-12-29，历史引擎 + 当前数据是否触发 | **566 引擎：否**（P*=1751.89 > high 1749.58，gap −2.31）；修正引擎：**是**（1737.93，gap +11.65）。触发=代码版本 |
| data drift 是否 PROVEN | **否（且被推翻）**。数据同一份，逐字节复现 |
| 历史数据 snapshot/hash 是否存在 | 不需要——复现成功已证明身份 |
| 9/1 vs 9/2 文案 | 已纠正：9/1 早于 9/2，mtime 支持"同一份数据"，不支持"另一版数据" |
| 299 parity（d65ea83） | 事件层语义 parity，不覆盖 K3 组合路径；与 frozen96 可复现不矛盾 |
| frozen96 是否 exactly reproducible | **是**（566 引擎 + 当前数据，逐字节） |
| frozen96 是否还能当 canonical | 作为 566 语义历史产物：**是（A）**；作为当前正确 P* 口径：被 8c479f6 修正版（97 笔）取代 |
| +82.66 / +58.20 / +30.2951 | UNCHANGED（前两者当前引擎与 8c479f6 零差异；P4 链条未触碰） |
| 是否需要重新生成 canonical portfolio artifact | **不需要重新生成 frozen96**（它作为 566 语义产物可复现）；项目当前 canonical = 8c479f6 修正引擎输出（97 笔），已存在（strict_c_corr_trades.csv） |

---

## 5. 文档勘误（不静默覆盖历史，追加勘误）

### 5.1 LIVECASE-A 报告（b86868c）
- 原句："差异属数据版本漂移（旧数据下 06-18 实时阈值更高未触发）" → **勘误**：旧数据假说无证据；566 旧代码口径下 P*_raw=151.44 确实不触发，但那是 **566 引擎 P0 修正前的数学口径**，与 8c479f6 修正无关；数据始终同一份。根因 = 代码版本。

### 5.2 LIVECASE-A2 报告（2daf3aa）
- 原结论：HISTORICAL_INPUT_UNAVAILABLE（旧数据不可复算）→ **勘误**：A3 证明历史输入 = 当前数据（逐字节复现），HISTORICAL_INPUT **AVAILABLE**。A2 的"当前数据下 11 未触发 / 2 触发"事实不变；2 个提前触发在 566 引擎下不触发（代码版本原因），不是数据原因。
- 原"6 案例 7 日期视觉假象"：A2 已撤回；A3 进一步证明 13 个点名日期中 2 个是**真实代码版本触发的提前退出**（牧原 06-18、茅台 12-29），其余 11 个当前数据下确实未触发（566 与修正引擎均未触发——除茅台 12-29 与牧原 06-18 外的日期）。

---

## 6. 判定

| 项 | 判定 |
|---|---|
| P* 数学 | 正确（A2 三方验证） |
| 历史代码谱系 | **PROVEN**（frozen96 = 566db88） |
| 历史数据身份 | **PROVEN = 当前数据（同一份）** |
| 组合回放 | frozen96 逐字节可复现 |
| 牧原 06-18 | 566 口径不触发；修正口径触发 → CODE_VERSION |
| 茅台 12-29 | 566 口径不触发；修正口径触发 → CODE_VERSION |
| frozen96 canonical | **A — exact reproducibility restored**（566 语义）；当前 canonical = 修正引擎 97 笔 |

**最终分类：A。**

---

## 7. 产物清单

- `results/evidence/livecase_a3/frozen96_artifact_lineage.csv`
- `results/evidence/livecase_a3/replay_matrix.csv`
- `results/evidence/livecase_a3/current_only_vs_frozen_only.csv`
- `results/evidence/livecase_a3/exit_mismatch_forensics.csv`
- `results/evidence/livecase_a3/levels_mismatch_forensics.csv`
- `results/evidence/livecase_a3/first_divergence_state_before.csv`
- `results/evidence/livecase_a3/first_divergence_event_compare.csv`
- `results/evidence/livecase_a3/first_divergence_state_after.csv`
- `results/evidence/livecase_a3/data_identity.json`
- `results/evidence/livecase_a3/livecase_a3_summary.json`
- `results/evidence/livecase_a3/livecase_a3_invariants.json`
- `research/livecase_a3/FROZEN96_LINEAGE.md`
- `research/livecase_a3/historical_engine_semantics.md`
- `research/livecase_a3/LIVECASE_A3_REPORT.md`（本文档）

**下一步：STOP。**
