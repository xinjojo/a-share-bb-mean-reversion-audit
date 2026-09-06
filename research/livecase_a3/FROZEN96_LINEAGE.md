# FROZEN96 PROVENANCE / REPRODUCIBILITY FORENSIC AUDIT — LIVECASE-A3

阶段：LIVECASE-A3（A股 BB Mean Reversion 审计 2026）
目标：解释 frozen96（`results/evidence/strict_c/round5/strict_c_trades.csv`，96 笔）如何生成，以及为什么当前 replay 是 97 笔。
方法：git 谱系追查 + 历史引擎重建 + 逐字节复现 + 动作级对账。全程未修改任何 frozen 产物，未跑新策略研究。

---

## 1. 结论先行

1. **frozen96 的生成引擎 = 566db88 版本的 `run_strict_c.py`**（2026-09-02 20:42 提交，STRICT_C 语义复原审计）。
2. **frozen96 的输入数据 = 当前这份 `data/combined_daily.parquet`（同一份）**，证据：
   - 行情文件 mtime 2026-09-01 23:15 **早于** frozen96 生成提交 566db88（2026-09-02 20:42）→ 生成时读的就是当前文件；
   - 用 566db88 引擎 + 当前数据重建，得到 **96 笔、总收益 +89.148731%、股票 PnL 545,730.26**，与 frozen blob **逐字节一致**（SHA256 相同）→ 任何"不同数据"假说被直接排除。
3. **"data drift / 数据版本漂移"正式不成立**。此前文档中的该表述全部撤回。
4. **frozen96(96) 与当前 replay(97) 的差异全部来自代码版本演进**：8c479f6（STRICT_C_CORRECTED）的 **P0 复权口径修正**（+tick/FIX2）。5 笔退出日期变化与 8c479f6 内嵌的 `p0_audit.csv` 记录的 **5 个触发改变日一一对应**（CODE_VERSION_PROVEN）。
5. 牧原 2020-06-18、茅台 2023-12-29 的"提前触发"在 **566 旧口径下不触发**（P* 分别为 151.44 / 1751.89，均高于当日最高 73.18 / 1749.58）；触发是 **8c479f6 P0 修正的直接结果**（修正后 P* 72.62 / 1737.93）。**不是数据变了**。

---

## 2. frozen96 谱系（artifact → 源文件 → 生成脚本 → 引擎 commit）

| 项 | 值 |
|---|---|
| 目标文件 | `results/evidence/strict_c/round5/strict_c_trades.csv` |
| 迁移前路径 | `results/round5/strict_c_trades.csv`（b343256 由 `git mv` 迁入，blob 不变、0 行 diff） |
| **首次出现 commit** | **`566db88d84022b02b7f8d19990a5bccd9b9fa011`**（2026-09-02 20:42:58 +0800） |
| git blob SHA1 | `d98549cbac7c83dea7991002c0f14a0c044721dc` |
| 内容 SHA256 | `76f401fd67710d7cb15ba20db9107b719b40aa0176ce0d27c1f8198ab91bde55` |
| 数据行 | 96（+1 表头行 = 97 行文件） |
| 日期范围 | 2020-03-02 ~ 2026-08-25 |
| 生成脚本 | 566db88 版 `run_strict_c.py`（459 行）+ `run_strict_c_math.py`（131 行） |
| 引擎 commit | 566db88（与首次出现 commit 相同） |
| 上游输入 | `data/combined_daily.parquet`（mtime 2026-09-01 23:15；**不在 git 内**） |
| 之后是否重算 | 否——blob 自 566db88 起未变；457241a 的 named_ranked 文件为展示副本，无重算逻辑 |
| 重建复现 | 566db88 引擎 + 当前数据 → 96 笔，与 frozen **逐字节一致**（SHA256 匹配） |

### 重建命令（可复核）

```bash
# 1. 检出 566db88 到独立 worktree
git worktree add /tmp/lc3_566 566db88d84022b02b7f8d19990a5bccd9b9fa011
# 2. 把当前数据软链进 worktree（脚本 ROOT 硬编码为数据根）
ln -sfn /Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/data /tmp/lc3_566/round51/data
ln -sfn /Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/data /tmp/lc3_566/data
# 3. 复跑 STRICT_C（mode=c）
cd /tmp/lc3_566 && python3 run_strict_c.py c
# 4. 与 frozen blob 逐字节比较
cmp <(git show 566db88:results/round5/strict_c_trades.csv) results/round5/strict_c_trades.csv && echo IDENTICAL
```

复跑结果：trades=96、total_return=+89.148731%、stock_pnl=545,730.26，`cmp` 判 IDENTICAL。

---

## 3. 历史引擎语义（566db88）vs 当前引擎（8c479f6+）

| 组件 | 566db88（frozen96 引擎） | 8c479f6+（当前） | 差异 |
|---|---|---|---|
| P* 输入序列 | `x = 最近19日 close_raw × adj[T]`（19 天全部乘 **T 当日** 复权因子） | `x = 各日 close_adj[k] = close_raw × adj_factor[k]`（各日自身因子） | **P0（根因）** |
| P* 输出口径 | P*_adj 直接判定 `high_adj ≥ P*_adj` | P*_raw = P*_adj / adj[T]；可执行价 = ceil(P*_raw/0.01)×0.01；判定 `high_adj ≥ threshold×adj[T]` | **P1（tick conservative）** |
| 跌停卖出顺序 | slip_first（先滑点再判跌停） | ref_first：先判 ref ≤ limit_down 不可卖，再乘滑点 | **FIX2** |
| 入场 | T 收盘 close_adj < bb_lower + 非一字 → T+1 open×(1+10bp) | 相同 | 无 |
| ADD_ON | ≤5 层、单层 20 万、距上次 ≥1 交易日、现金检查 | 相同 | 无 |
| K / TopN | K=3、金额 Top10 | 相同 | 无 |
| 退出方式 | STRICT_C 动态盘中 touch（动态上轨随价格移动） | 相同（数学实现） | 无 |
| 费用 | 佣金 0.025%（min5）+过户费，印花税 historical，滑点 10bp | 相同 | 无 |
| FINAL_SETTLE / ETF | 末日 close 清仓；事件驱动 ETF 腿（etf_enabled=True） | 相同 | 无 |

组件级 diff 另存 `results/evidence/livecase_a3/historical_vs_current_engine_diff.csv`（见下方生成记录），可逐项核对。

---

## 4. Replay matrix

| 引擎 | 数据 | 交易数 | 结果 |
|---|---|---|---|
| 566db88（历史） | 当前数据 | 96 | **与 frozen96 逐字节一致** |
| 8c479f6（P0/P1 修正） | 当前数据 | 97 | strict_c_corr_trades.csv；5 笔退出+3 笔入场±1+4 笔层数差异 |
| 当前 HEAD（迁移后） | 当前数据 | 97 | 与 8c479f6 产物 97/97 零差异（exit/levels/return 全同） |
| V2A_FROZEN_STRICT（d65ea83） | 当前数据 | 299 独立事件 | 299/299 parity（事件层） |

**第 97 笔 = 复权修正引入，不是数据变化。** current replay 与 8c479f6 修正版 97/97 完全一致、0 差异。

### 为什么 299 能 exact parity、frozen96 不能？

- V2A 是**独立事件层**回放（K=巨大、现金无限、无组合路径）：每笔交易的 P* 判定、入场判定逐笔独立，不受资金/K/持仓影响 → 修正前后只需保证事件语义一致即可 299/299。
- frozen96 是**组合层**（K=3、共享 100 万现金、Top10、加仓竞争、ETF 资金池）：P* 口径一改 → 某日多一笔退出 → 现金释放时点改变 → 后续入场/加仓/层数连锁变化。所以"299 parity"证明的是**修正版引擎事件语义可精确复现**，**不覆盖** 566 版组合产物，两者并不矛盾。

---

## 5. First divergence（核心取证）

逐日动作级对比（566 引擎 ac566 vs 当前引擎 ac_cur）：

- **第一个分叉日：2020-06-18**，类型 **EXIT**。
- 当日动作：frozen = `{000063.SZ 卖, 002415.SZ 卖}`；current = 多一条 `002714.SZ TAKE_PROFIT_DYN lv1`。
- 前一个交易日（2020-05-26）双流动作完全一致。
- 根因：002714 在 2020-06 除权（复权因子 7.5891→12.9598 区间）。566 旧代码把 19 日历史 raw close 全部乘 **当日** adj → P*_raw=151.44，06-18 最高 73.18 不触发；8c479f6 改为各日自身因子 → P*_raw=72.62，73.18 ≥ 72.62 **触发**。
- 现金/ETF 层面在 06-17 已存在微小差异（etf_sh 213,100 vs 214,200，约 1,100 份、千元级），由共享现金池浮点/阈值敏感传播，金额小、不构成股票动作层的 primary divergence。

### 5 笔 exit mismatch（frozen exit → replay exit，全部 CODE_VERSION_PROVEN）

| ts_code | entry | frozen exit | replay exit | p0 触发改变日 | 566 P*_old → corrected |
|---|---|---|---|---|---|
| 002714.SZ | 2020-05-12 | 2020-07-06 | **2020-06-18** | 2020-06-18 | 151.44 → 72.62（触发） |
| 600519.SH | 2023-10-16 | 2024-02-06 | **2023-12-29** | 2023-12-29 | 1751.89 → 1737.93（触发） |
| 600519.SH | 2025-06-16 | 2025-07-11 | 2025-07-10 | 2025-07-10 | 1442.15 → 1427.51（触发） |
| 601899.SH | 2022-09-27 | 2022-10-27 | 2022-10-28 | 2022-10-27 | 8.362（old 触发 → corrected 不触发，顺延） |
| 002415.SZ | 2022-05-09 | 2022-06-08 | 2022-06-06 | 2022-06-06 | 35.459 → 34.768（触发） |

### 4 笔 levels mismatch（frozen → current，全部 PORTFOLIO_PATH_PROPAGATION）

| ts_code | entry | frozen | current | 机制 |
|---|---|---|---|---|
| 601919.SH | 2024-07-15 | 3 层（08-09、09-06 add） | 2 层（09-06 缺） | 茅台61 12-29 早退改变现金时点 |
| 600519.SH | 2022-10-13 | 3 层（10-20、10-28 add） | 2 层（10-28 缺） | 601899 退迟一日 → 10-28 现金被 000858 新入占用 |
| 601012.SH | 2024-01-30 | 2 层（02-01 add） | 1 层（02-01 缺） | 002230 01-04 用茅台61 早退现金入场 |
| 300418.SZ | 2023-06-27 | 2 层（06-29 add） | 1 层（06-29 缺） | current 06-29 现金仅 465.96，无 ETF 可卖；566 现金 5,006+ETF 93,900 |

### 3 笔 entry 差异

- frozen-only：`000858.SZ|2022-10-28`（current 10-28 现金未到：601899 延迟到 10-28 卖出）
- current-only：`300750.SZ|2022-10-31`（frozen 10-28 买五粮液占资金，current 未买 → 10-31 补位宁德）
- current-only：`002230.SZ|2024-01-04`（茅台61 12-29 早退放水）

全部为 first divergence 之后的路径传播，无独立根因。

---

## 6. 数据身份

- 行情数据不在 git 内（`git ls-files | grep combined_daily` 为 0 条）。
- `combined_daily.parquet` mtime = 2026-09-01 23:15，frozen96 生成提交 = 2026-09-02 20:42 → **9/1 早于 9/2**，mtime 不能证明"用了另一版数据"，反而与"用同一份数据"一致。
- 决定性证据：566db88 引擎 + 当前数据 → 逐字节复现 frozen96。数据身份 = **PROVEN：同一份数据**。
- 结论：**不存在 data drift**；"旧数据下 P* 更高 / 未触发"的旧表述是**错误的归因**，正确归因是 **8c479f6 代码版本修正（P0 复权口径）**。

---

## 7. mtime 文案纠正

所有此前写"差异属数据版本漂移""旧数据下实时阈值更高"的文档段落，一律改为：

> current-data replay differs from frozen artifact; **input identity: SAME data PROVEN (566 engine rebuild byte-identical)**; differences caused by 8c479f6 code fix (P0 adj-factor semantics), NOT data.

已修正文件：
- `research/livecase_a3/LIVECASE_A3_REPORT.md`（本阶段新写，全部采用正确表述）
- `results/evidence/livecase_a3/data_identity.json`（记录纠正）
- LIVECASE-A / A2 旧报告以"勘误章节"方式追加（见下），不静默覆盖原文。

---

## 8. 旧结果状态（仅治理判断，未重跑策略）

| 旧结果 | 状态 | 说明 |
|---|---|---|
| +82.66% combo（8c479f6 corrected 口径） | **UNCHANGED** | 当前引擎与 8c479f6 产物 97/97 零差异 |
| +58.20% pure stock | **UNCHANGED** | 同上（同一产出链） |
| P4 A0 +30.2951% | **UNCHANGED** | P4 阶段产物，独立链条，本阶段未触碰 |
| frozen96 ranked list | **UNCHANGED（566 语义）** | 作为 566 引擎产物可精确复现；但 P* 口径已被 8c479f6 修正取代（仅 P* 正确性，非全盘推翻） |

---

## 9. 最终判定

- **P* 数学**：正确（A2 已三方验证：analytic/numerical/brute-force 一致）。
- **历史代码谱系**：证明（frozen96 = 566db88 引擎）。
- **历史数据身份**：**证明 = 当前数据（同一份）**。
- **组合回放**：frozen96 逐字节可复现（566 引擎 + 当前数据）。
- **牧原 2020-06-18**：566 口径不触发，8c479f6 口径触发 → 代码版本原因。
- **茅台 2023-12-29**：566 口径不触发（P*=1751.89 > high 1749.58），8c479f6 口径触发（1737.93）→ 代码版本原因。
- **frozen96 canonical 状态**：**A — exact reproducible（给定 566 引擎语义）**。作为"566 语义历史产物"完全成立；作为"当前正确 P* 口径的组合表现"则被 8c479f6 修正版（97 笔）取代。

commit: 见 `LIVECASE_A3_REPORT.md` 末尾。
