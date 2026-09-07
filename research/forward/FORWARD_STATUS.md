# 前瞻观察期状态（FORWARD STATUS）

## 当前正式状态

**「1.5%提前退出候选系统已冻结，进入前瞻观察期。」**

不得写成：「已验证实盘有效」「已确认Alpha」「可正式实盘」。

## 冻结信息

| 项 | 值 |
|---|---|
| 冻结日期 | 2026-09-06 |
| 冻结依据 commit | `31f7266b9e978b031e0b685af4876312eb0090d3` |
| Registry | `research/forward/registries/PANIC_EE15_FORWARD_REGISTRY.md`（SHA256 `a3e2f1adc1ccc27dbc6c0b407f56ea38e41ae2e191f4b10d1181aaacc0b2f2be`） |
| 冻结参数 | 动态上轨提前 1.5% 退出（B 系统）vs 基线 exact P\*（A 系统） |
| 前瞻起点 | 2026-09-07 及以后首次出现的合法新信号 |
| 冻结前窗口 | 2026-09-01 ~ 2026-09-06：属冻结之前，即使有数据也不纳入前瞻成绩 |
| 初始资金 | A/B 各 1,000,000 元（与冻结引擎口径一致，A/B 同起点；**非 100,000**） |
| A/B 唯一差异 | `exit_multiplier`：A=1.000（必须真触发 exact 动态 P\*）、B=0.985（有效退出线 = P\* × 0.985，按 A 股 tick 保守向上取整） |

## 前瞻基础设施（2026-09 重建为真正逐日状态机）

旧版 `605ab92` 的 forward_update 属于「伪前瞻」：每次重跑全量回测再筛 `entry_date >= 2026-09-07` 的已完成 trades。外部审计判定该方式不能作为真正前瞻证据，本轮重写：

- **`src/forward_engine.py`**：`ForwardAccount` 逐日状态机（每日单日推进），与冻结引擎 `strict_c_earlyexit_ca.py` 在 1610 个交易日的 cash/stock_val/etf_sh/etf_val/equity 逐字段 bit 级对齐（max_abs_diff=0）；`snapshot/load` 持久化 A/B 账户状态；`build_input_hash` 记录每日输入数据指纹。
- **`src/forward_update.py`**：每日只推进新增日期（从 `state.last_processed_date` 续跑），当日生成信号/订单/P\*/权益并永久追加写入；冻结前（<2026-09-07）只静默推进状态、**不写任何前瞻台账**；信号当天写死、A/B 共用 signal_id；订单创建即记录（CREATED → FILLED/REJECTED/DEFERRED）；每日输入 hash 落盘 `forward_input_manifest.csv`；补录数据必须 `backfilled=1`，当天实时生成 `backfilled=0`。
- **启动状态**：回放到冻结引擎数据末日 2026-08-25 得到 A/B 启动账户（含 PRE_EXISTING 持仓，见 `forward_pre_existing_A.csv` / `_B.csv`），此后逐日推进。冻结日前遗留持仓带入前瞻状态，但不计入「09-07 以后新独立信号」统计。
- **机器级禁止**：测试断言前瞻台账内无任何 < 2026-09-07 的日期；A/B 信号集合每处理日完全一致；A/B 唯一规则差异 = exit_multiplier。
- **硬性测试**：`tests/forward_infra_tests.py` T1~T9，**29/29 PASS**（含 T1 与冻结引擎 equity 逐日精确对齐、T2 合成 max_date≥09-07 真实调用引擎分支、T3/T4 幂等与顺序推进字节不变、T5 BACKFILLED 规则、T6 冻结前禁止、T7 A/B 唯一差异、T8 未平仓信号/订单/状态已存在、T9 实时首日 backfilled=0）。

## 当前进度（截至 2026-09-06）

- 行情数据末日：2026-08-25（data/raw/daily 主流分片；prepare_v51 硬编码上限 2026-08-25，真实 09-07+ 数据到位前由扩展路径注入）
- 前瞻信号数：0（首个前瞻交易日 2026-09-07 尚未有真实行情数据）
- 前瞻交易数：0（A/B 各 0）
- 启动账户（2026-08-25 收盘，合成回放验证）：A 现金 5,253.54 / ETF 361,900 份；B 现金 5,200.00 / ETF 967,900 份；各 3 笔 PRE_EXISTING 持仓（688525.SH、600276.SH、688256.SH，以实际运行 `forward_pre_existing_*.csv` 为准）
- 数据完整性提示：个别股票分片数据下限仅 2020-01-06（非完整覆盖），前瞻期该股票自身交易日不足时按「无信号」处理，不额外删除其他股票。

## 每日更新流程

1. 每日收盘后取得新行情数据（daily 分片更新至当日，或经扩展路径注入）；
2. 运行 `python src/forward_update.py`（自动从 state.last_processed_date 续跑，只推进新增日期）；
3. 当日生成并永久写入：信号（`forward_signal_ledger.csv`）、订单生命周期（`forward_order_ledger.csv`，创建即记录）、成交/公司行为（`forward_trade_ledger.csv`）、每日 P\*（`forward_pstar_daily.csv`）、A/B 每日权益（`forward_daily_equity.csv`）、输入 hash（`forward_input_manifest.csv`）；
4. 事后补数据必须 `backfilled=1`，不得伪装实时生成；历史行只读，不得重算覆盖。

## 台账文件（results/evidence/forward/）

- `forward_signal_ledger.csv`：信号级（signal_id/股票/信号日/生成时间/可用数据截止/排名/类型/P\* 与 A/B 退出线/当日 High/A/B 持有与订单标记/backfilled）。NEW_ENTRY 当日无持仓，P\* 三列显式写 `NA`（入场后见 `forward_pstar_daily.csv`）。
- `forward_order_ledger.csv`：订单生命周期（CREATED 于信号日/创建日 → FILLED/REJECTED/DEFERRED，含 intended_execution_date）。
- `forward_trade_ledger.csv`：成交/公司行为事件级（含费用、滑点、印花税、红利税 FIFO 结算、分红、送转、现金变化、股数）。
- `forward_daily_equity.csv`：A/B 每日权益（只 append，不覆盖历史）。
- `forward_pstar_daily.csv`：每持仓每日 exact 动态 P\* / A 退出线 / B 退出线 / 当日 High / 触发标记。
- `forward_input_manifest.csv`：每日输入数据 hash（防数据修订污染）。
- `forward_pre_existing_A.csv` / `_B.csv`：冻结日启动持仓（带入但不计入新信号统计）。
- `forward_ab_comparison.csv`：第一次正式评价（≥6 个月且 ≥15 笔独立交易）时填充 A/B 对比。

## 首次正式评价门槛

同时满足：前瞻时间 ≥ 6 个月 且 独立交易 ≥ 15 笔。评价核心：B 相对 A 是否提供稳定改善（累计收益/回撤/夏普/胜率/平均交易/持仓时间/救单 vs 截断赢家/行业分布），不是 B 绝对赚钱。
