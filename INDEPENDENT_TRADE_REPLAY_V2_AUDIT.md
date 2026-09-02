# INDEPENDENT TRADE REPLAY V2 — REPLAY SEMANTICS AUDIT

> 范围：仅 REPLAY SEMANTICS AUDIT。不调参 / 不新策略 / 不开 Validation / 不改 Registry（SHA256 冻结 `5c5e451a...`）。
> 目的：核实 V1 独立重放与冻结 STRICT_C_EXECUTABLE_TICK 引擎的 execution/censoring 语义差异，量化对 PRIMARY（Top10 超跌）独立交易 edge 的影响。

---

## 1. 实现：V2A_FROZEN_STRICT

`independent_trade_replay_v2.py::replay_v2a` — 完全复制冻结 `run_fast_multi_strict_c`（run_strict_c.py）语义：
- **全局市场交易日历**（1611 日，2020-01-02 ~ 2026-08-25）逐日迭代，非 per-stock。
- **P1**：pending_buy / pending_add / pending_sell 在 T+1 市场日 `D[d]['pos']` 无该股（停牌/缺失）→ **CANCEL**（与冻结引擎一致）。
- **P2**：入场时 `init_raw_hist` 回看前 **19 个市场交易日**、含数据者加入（与冻结 `init_raw_hist` 一致）；持有期间每个有数据日 CLOSE 追加 close_adj。
- T+1 / 100股 / tick ceil / ref_first 跌停可达 / 10bp 滑点 / 历史印花税 / 动态 P\*（analytic_Pstar, 各日自身 adj_factor）——逐行对齐冻结引擎。
- **P3**：期末 FINAL_SETTLE 仅对末日（2026-08-25）有行情股结算；其余持仓 → **censored** 单独记录。
- K 无限 / ETF off / 现金无限 → 独立交易、无组合阻塞。

`V2B_RESUME_ALLOWED` = V1 per-stock resume 语义（标 ALTERNATIVE_EXECUTION_DIAGNOSTIC）。

## 2. P4 — Exact frozen-engine parity（最关键）

用冻结 `run_fast_multi_strict_c(K=10^6, etf_enabled=False, initial_cash=10^9)` 与 V2A 逐笔对账：

| 指标 | 值 |
|---|---|
| 冻结引擎 trades | 299（TAKE_PROFIT_DYN 290 + FINAL_SETTLE 9） |
| 匹配（ts_code+entry_date） | **299 / 299** |
| 完全一致（exit_date + exit_type + return 2dp） | **299 / 299** |
| 仅冻结 / 仅 V2A | 0 / 0 |

**结论：V2A 与冻结引擎逐笔完全一致**（含信号→T+1 入场、停牌取消、9 笔期末结算）。V2A 是冻结语义的精确复现。

## 3. P1 — Pending 语义影响（V1 vs V2A）

V1（resume）与 V2A（frozen）按 `(ts_code, signal_date)` 匹配：

| 项 | 数量 |
|---|---|
| MATCHED（两版同一笔） | 298 |
| **V1_ONLY（V2A 因停牌取消 pending）** | **1** |
| V2A_ONLY | 1 |
| matched 中 entry_date 不同 | 0 |
| matched 中 exit_date / return 不同 | 0 / 0 |

唯一差异：**600150.SH（中国船舶）2024-09**。V1 在 2024-09-02 信号→停牌→2024-09-19 复牌开盘买入（+18.45%）；V2A/冻结引擎取消该 pending，之后 2024-09-19 重新触发信号、2024-09-20 买入（+4.47%）。**净笔数不变（299→299）**。V1 vs V2A 全部 298 笔匹配交易的退出日与收益**完全相同**。

**pending suspension affected count = 1**（6.7 年 299 笔中仅 1 笔，Top10 大盘股停牌在 T+1 窗口极罕见）。

## 4. P2 — dynamic P\* history 语义影响

- 入场时前 19 市场日内有效数据日 < 19 的（冻结 init_raw_hist 短于 19 / 与 V1 的 OBSERVATION_19 口径不同）：**仅 1 笔**（600150.SH 2024-09-20 复牌后入场，仅 9 个前序数据日）。
- 该笔无 V1 对应（属 V2A_ONLY），不影响匹配交易的退出/收益。
- matched 298 笔中 **P* 历史语义影响导致的 exit/return 差异 = 0**。

**raw_hist semantics affected count = 1**，对 headline 无实质影响。

## 5. P3 — Censoring / FINAL_SETTLE 分类

| 分类 | 定义 | 数量 |
|---|---|---|
| A_GLOBAL_END_SETTLE | 末日（2026-08-25）有行情，期末 close 结算 | **9**（均 2026-08-25 结算） |
| B_EARLY_DATA_END | 数据早于末日、非退市、距末日>5 市场日 | 0 |
| C_KNOWN_DELISTED | 退市信息确认（delist<2026-08-25） | 0 |
| D_UNKNOWN_TRUNCATION | 非退市、距末日≤5 市场日截断 | 0 |
| **censored 合计** | | **0** |

PRIMARY Top10 尾仓（9 笔）全部在末日仍有行情、为**真实可执行的期末结算（A）**，无 B/C/D censored。因此 OPTIMISTIC 与 PESSIMISTIC 边界在此股票池下**完全一致**（无 censored 需要 recovery 假设）。

## 6. P5 — PRIMARY 六口径 headline

| version | n | mean% | median% | win% | PF | HAC t | HAC CI | 2020-23% | 2024-26% |
|---|---|---|---|---|---|---|---|---|---|
| V1_CURRENT | 299 | 5.002 | 5.232 | 75.92 | 1.60 | 6.42 | [3.39,6.36] | 4.406 | 6.120 |
| **V2A_FROZEN_STRICT** | 299 | **4.955** | **5.219** | 75.92 | 1.59 | 6.43 | [3.35,6.29] | 4.406 | 5.986 |
| V2B_RESUME_ALLOWED | 299 | 5.002 | 5.232 | 75.92 | 1.60 | 6.42 | [3.39,6.36] | 4.406 | 6.120 |
| **REALIZED_EXIT_ONLY** | 290 | **5.258** | **5.308** | 77.59 | 1.66 | 7.20 | [3.74,6.53] | 4.406 | 7.008 |
| OPTIMISTIC_BOUND | 299 | 4.955 | 5.219 | 75.92 | 1.59 | 6.43 | [3.35,6.29] | 4.406 | 5.986 |
| PESSIMISTIC_BOUND | 299 | 4.955 | 5.219 | 75.92 | 1.59 | 6.43 | [3.35,6.29] | 4.406 | 5.986 |

> REALIZED_EXIT_ONLY = 仅 290 笔 TAKE_PROFIT_DYN 自然止盈（剔除 9 笔期末结算）。OPTIMISTIC = PESSIMISTIC = V2A 全量（censored=0 所致，二者无差异）。

**Event-day block bootstrap**（L=21, B=2000, 保持事件日时间结构）：
- V2A_FROZEN：n_event_days=249，CI **[3.33, 6.47]**，P(mean≤0)=0.000%
- REALIZED_TP：n_event_days=241，CI **[3.69, 6.63]**，P(mean≤0)=0.000%

## 7. 判定 gate（事实，不自动选级）

外部审计判定规则要求 `V2A_FROZEN_STRICT + REALIZED_EXIT_ONLY` 同时满足四项。逐项核查：

| gate | V2A_FROZEN_STRICT | REALIZED_EXIT_ONLY |
|---|---|---|
| clearly positive mean | +4.955% | +5.258% |
| clearly positive median | +5.219% | +5.308% |
| event-day CI > 0 | [3.35, 6.29] ✓ | [3.74, 6.53] ✓ |
| recent period not collapsed | 2024-26 +5.986% | 2024-26 +7.008% |

**四项全部满足**（且 V2A 与冻结引擎 parity 299/299 完全一致，V1 与 V2A 仅 1 笔停牌差异）。按本轮指令，**不自动选择 A/B/C/D**，交由外部审计最终裁定。

## 8. 关键结论

1. **V1 与冻结 STRICT_C 语义差异极小**：仅 1 笔（600150.SH 停牌窗口）因 pending 取消语义不同而换了一笔交易，298/299 笔逐笔一致；V1 headline（+5.002%）→ V2A 严格口径（+4.955%），差异 −0.05pp。
2. **censoring 对 PRIMARY 无影响**（censored=0，9 笔尾仓全为 A_GLOBAL_END_SETTLE 真实结算），OPT=PESS。
3. **P* 历史语义（OBSERVATION_19 vs 前19市场日）仅 1 笔入场受影响**，未改变任何匹配交易退出。
4. **严格因果口径下独立交易 edge 稳健**：mean +4.96~5.26%、median +5.22~5.31%、win 75.9~77.6%、PF 1.59~1.66、event-day HAC t 6.4~7.2、2024-26 无衰减。
5. 不影响第一代组合级 D 评级；Registry 未改；Validation 未开。

## 9. 交付文件

| 文件 | 内容 |
|---|---|
| `independent_trade_replay_v2.py` | V2A 重放 + P3 分类 + P5 六口径 + P4 parity（可 `--build/--run/--parity` 复现） |
| `results/independent_v2_primary_summary.csv` | 六口径 headline 表 |
| `results/independent_v2_semantics_diff.csv` | V1 vs V2A 逐笔语义差异（300 行，含 P1/P2 flag） |
| `results/independent_v2_censored_episodes.csv` | censored 明细（PRIMARY 为 0 行，仅表头） |
| `results/independent_v2_parity_check.csv` | V2A vs 冻结引擎逐笔对账（299/299 MATCH） |
| `results/independent_v2a_episodes.csv` | V2A 全量 episodes |
| `results/independent_v2_parity_frozen_trades.csv` | 冻结引擎（K=huge, etf off）trades |

V1 产物（`independent_trade_replay.py` 及 14 个 CSV）完整保留，未覆盖。
