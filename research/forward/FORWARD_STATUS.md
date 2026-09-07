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

旧版 `605ab92` 的 forward_update 属于「伪前瞻」：每次重跑全量回测再筛 `entry_date >= 2026-09-07` 的已完成 trades。外部审计判定该方式不能作为真正前瞻证据，已重写：

- **`src/forward_engine.py`**：`ForwardAccount` 逐日状态机（每日单日推进），与冻结引擎 `strict_c_earlyexit_ca.py` 在 1610 个交易日的 cash/stock_val/etf_sh/etf_val/equity 逐字段 bit 级对齐（max_abs_diff=0）；`snapshot/load` 持久化 A/B 账户状态；`build_input_hash` 记录每日输入数据指纹。
- **`src/forward_update.py`**：每日只推进新增日期（从 `state.last_processed_date` 续跑），当日生成信号/订单/P\*/权益并永久追加写入；冻结前（<2026-09-07）只静默推进状态、**不写任何前瞻台账**；信号当天写死、A/B 共用 signal_id；订单创建即记录（CREATED → FILLED/REJECTED/DEFERRED）；每日输入 hash 落盘 `forward_input_manifest.csv`；补录数据必须 `backfilled=1`，当天实时生成 `backfilled=0`。
- **启动状态**：回放到冻结引擎数据末日 2026-08-25 得到 A/B 启动账户（含 PRE_EXISTING 持仓，见 `forward_pre_existing_A.csv` / `_B.csv`），此后逐日推进。冻结日前遗留持仓带入前瞻状态，但不计入「09-07 以后新独立信号」统计。
- **机器级禁止**：测试断言前瞻台账内无任何 < 2026-09-07 的日期；A/B raw candidate 集合每处理日一致（同源只算一次）；A/B 唯一规则差异 = exit_multiplier。

## P0 修复（2026-09，commit 见 git log）

**P0-1：A/B 信号两层拆分（市场层 vs 账户层）**
- 永久 `sigA == sigB` invariant 已删除（逻辑错误：B 提前退出后 K 槽/现金/ETF 合法分叉，之后 A/B 能接纳的新入场天然不同）。
- **第一层 市场层 raw candidate**（`compute_raw_candidates`）：只依赖市场数据与冻结选股规则（上市合格、非 ST、amount top10、close_adj<bb_lower、非跌停），不含任何账户状态 → **每日只算一次，A/B 同源共用**，机器断言 A/B 集合一致。
- **第二层 账户层 admission**（`admit_new_entries`）：由账户自身状态决定（K 槽满否、是否已持有、是否 pending），允许合法分叉，原因分类：`ADMITTED / K_FULL / ALREADY_HELD / PENDING_EXISTS`。
- **台账**：`forward_signal_ledger.csv` 一条市场信号一行（raw_candidate=1），A/B admission/订单/拒绝原因分别记录（`A_admission_status / B_admission_status / A_order_created / B_order_created / A_reject_reason / B_reject_reason`）。ADD_ON 为持仓侧信号，A/B 各自（signal_id 带 -A/-B 后缀），B 提前退出后无持仓则无 ADD——合法分叉。

**P0-2：生产环境真正读取 09-07+ 行情（数据扩展加载层）**
- 新增 `src/forward_ext_data.py`：冻结段（≤2026-08-25）`prepare_v51` 原样不变；扩展段（>2026-08-25）从 `combined_daily.parquet` 真实新增行按与 prepare_v51 **完全相同的字段语义**重建 D（close_adj=close×adj_factor、BB(20,2)、PIT ST、分板涨跌停价、上市天数、bb_upper_prev、ETF 序列续接）。
- **历史重叠 parity**：对 2026-07~08 随机 24 个交易日，扩展层代码路径重建 vs prepare_v51 原样，19 个字段（含 ts 顺序）**max_abs_diff=0.0，全部机器断言通过**（`tests/forward_ext_parity_test.py` 11/11 PASS）。
- **真实冒烟**：当前数据源真实含有 2026-08-26~08-31（4 个交易日，combined_daily/pit_st/ETF 均真实存在）→ 生产 `main()` 已真实推进 A/B 状态至 2026-08-31（静默，不写前瞻台账）。**尚无 2026-09-07 及以后真实行情 → PRODUCTION NOT STARTED**，状态 = `FROZEN / FORWARD INFRA READY / NOT YET LIVE`。

## 首条真实前瞻记录（2026-09-07，LIVE）

- **Tushare 真实拉取成功**：token 由用户提供（仅命令环境变量，不写文件、不进 git）。探测确认真实最新交易日 = 2026-09-07。
- **增量补齐**：08-26~09-07 共 9 个交易日 daily/adj_factor 全部拉取（08-26 由首轮拉取写入，08-27~09-07 本轮补齐）；stock_basic 5558 只、namechange 10000 条、ETF 513500 fund_daily 至 09-07、Tushare dividend 73 条新事件并入（每股→每10股，不覆盖冻结 50 只）。
- **修订告警**：无（Tushare 08-26~08-31 返回值与本地 combined 一致，未发生数据修订）。
- **9/6 收盘真实遗留持仓（冻结前推进确认）**：A/B 各 3 笔 —— 688525.SH 佰维存储（2 层 1300 股）、600276.SH 恒瑞医药（2 层 8300 股）、688256.SH 寒武纪（1 层 200 股）；A 现金 5,253.54、B 现金 5,200.00；A ETF 361,900 份、B ETF 967,900 份。**9/1~9/6 冻结前推进无退出/加仓/新入场事件**（静默推进，不写前瞻台账）。
- **09-07 实时落盘（backfilled=0）**：2026-09-07 处理 1 个前瞻交易日，当日无新信号（raw candidate 0）、无成交；权益行 A/B 各 1 条（A 总权益 1,869,404.34 / B 3,500,702.80，data_available_through=2026-09-07 == today）；输入 hash 落盘 `60f51dd1...`。
- **状态：FORWARD OBSERVATION LIVE**（首条真实 backfilled=0 记录已产生）。

## Tushare 增量接入（本轮）

**`src/update_forward_tushare.py`**（Tushare 增量更新器）：
- token 只从环境变量 `TUSHARE_TOKEN` 读取，不写入任何文件（与 data/raw/download_dividend.py 同约定）。
- 只拉 2026-08-26 及以后（前瞻增量区）；≤2026-08-25 = 冻结历史，默认不覆盖；Tushare 返回值与本地已有值不同 → 写 `data/forward_incremental/forward_data_revision_alert.csv`（不自动覆盖）。
- 每次运行自动判断本地数据最新日期，只拉缺失交易日；输出到 `data/forward_incremental/`（不动冻结历史数据）。
- 覆盖：A股 daily、adj_factor、stock_basic（上市/退市）、namechange（PIT ST/名称）、trade_cal、ETF 513500 fund_daily+nav、dividend（每股口径自动转每10股并入 corp_map）。

**`src/prepare_forward_data.py`**（前瞻专用数据准备层）：
- 冻结段（≤2026-08-25）`prepare_v51` 原样不变；增量段（>08-25）优先读 Tushare 增量文件，无则回退 combined_daily 真实新增行；字段语义与 prepare_v51 完全一致（close_adj=close×adj、BB(20,2)、PIT ST、分板涨跌停、上市天数、bb_upper_prev、ETF 续接）。
- 历史重叠 parity：24 个 2026-07~08 交易日逐字段 max_abs_diff=0.0（机器断言，通过后才允许使用扩展层）。

**`src/run_forward_daily.py`**（一键每日流程，用户每天只跑这个）：
`python src/run_forward_daily.py`
1. 有 TUSHARE_TOKEN → 自动拉最新增量；无 → 明确警告并本地数据兜底
2. parity 校验 → prepare_forward_data → 逐日推进 A/B state → 写 signal/order/trade/P*/equity/hash
3. 输出人话摘要（最新数据日期 / raw candidate / A/B 持仓现金ETF / 分叉 / BACKFILLED / 修订告警）
4. 无新交易日 → 安全退出，不产生重复行

**本轮真实运行记录**（2026-09-07，用户提供 TUSHARE_TOKEN 后）：
- Tushare 拉取：**执行成功**，真实最新交易日 = 2026-09-07（daily 探测确认，规避未来计划日）
- 增量补齐：08-26~09-07 共 9 个交易日 daily/adj_factor 全齐（含 09-01~09-06 此前缺失段）
- 数据末日：2026-09-07
- parity：PASS（max_abs_diff=0.0, 24 样本日）
- 增量数据源：tushare_incremental；Tushare dividend 73 条并入；修订告警 0 条
- 9/6 收盘真实遗留持仓：3 笔（688525/600276/688256），9/1~9/6 冻结前推进无事件
- 09-07 实时落盘：权益 A/B 各 1 行 + 输入 hash（backfilled=0，data_available_through==today）
- 状态：**FORWARD OBSERVATION LIVE**

## 当前进度（截至 2026-09-07）

- 行情数据末日：**2026-09-07**（Tushare 真实拉取：08-26~09-07 全齐，含 daily/adj_factor/stock_basic/namechange/ETF/dividend）
- 前瞻信号数：0（09-07 首个前瞻交易日无新信号）
- 前瞻交易数：0（A/B 各 0）
- 启动账户（2026-08-25 收盘，真实回放）：A 现金 5,253.54 / ETF 361,900 份；B 现金 5,200.00 / ETF 967,900 份；A/B 各 3 笔 PRE_EXISTING（688525.SH 佰维存储 2 层、600276.SH 恒瑞医药 2 层、688256.SH 寒武纪 1 层，以 `forward_pre_existing_*.csv` 为准）；**冻结前真实推进至 09-06 收盘无事件，9/6 遗留持仓同上**
- 状态：**FORWARD OBSERVATION LIVE**（2026-09-07 首条真实 backfilled=0 权益/输入 hash 记录已落盘）
- 数据完整性提示：个别股票分片数据下限仅 2020-01-06（非完整覆盖），前瞻期该股票自身交易日不足时按「无信号」处理，不额外删除其他股票。

## 硬性测试

- `tests/forward_infra_tests.py` T1~T10，**39/39 PASS**（T1 冻结引擎逐日精确对齐、T2 真实调用引擎分支、T3/T4 幂等与顺序推进字节不变、T5 BACKFILLED、T6 冻结前禁止、T7 A/B 唯一差异、T8 未平仓状态存在、T9 实时首日 backfilled=0、**T10 admission 合法分叉：A K=3 满 → 全 K_FULL 不下单；B 空 1 槽 → 恰好 1 个 ADMITTED 创建 BUY 订单，不 crash**）。
- `tests/forward_ext_parity_test.py` **11/11 PASS**（扩展层 vs prepare_v51 逐字段 0 差异；扩展段真实 4 交易日字段齐全；合并后冻结段原样）。
- `tests/forward_tushare_unit_test.py` **11/11 PASS**（T11a 无 token 处理、T11b dividend 每股→每10股映射且不覆盖冻结、T11c daily+adj 拼接列语义、T11d namechange→PIT ST、T11e 修订告警 CSV）。

## 每日更新流程（一键）

```bash
# 首次/需要自动拉取时设置 token（不写入任何文件）
export TUSHARE_TOKEN=<你的tushare token>
# 每日收盘后运行一次：
python src/run_forward_daily.py
```

脚本自动：Tushare 增量拉取（有 token）→ parity 校验 → 数据准备（冻结段原样+增量段）→ 从 state 续跑推进新增日期 → 写信号/订单/成交/P\*/权益/输入 hash → 输出人话摘要 → 更新状态。无新交易日时安全退出；补录数据必须 `backfilled=1`，历史行只读不得重算覆盖。

## 台账文件（results/evidence/forward/）

- `forward_signal_ledger.csv`：信号级，**一条市场信号一行（P0-1 分层）**。NEW_ENTRY 行 raw_candidate=1，A/B admission/订单/拒绝原因分列（`A_admission_status/B_admission_status/A_order_created/B_order_created/A_reject_reason/B_reject_reason`），P\* 三列显式写 `NA`（入场后见 `forward_pstar_daily.csv`）；ADD_ON 为持仓侧信号（signal_id 带 -A/-B 后缀，A/B 各自，合法分叉）。
- `forward_order_ledger.csv`：订单生命周期（CREATED 于信号日/创建日 → FILLED/REJECTED/DEFERRED，含 intended_execution_date）。
- `forward_trade_ledger.csv`：成交/公司行为事件级（含费用、滑点、印花税、红利税 FIFO 结算、分红、送转、现金变化、股数）。
- `forward_daily_equity.csv`：A/B 每日权益（只 append，不覆盖历史）。
- `forward_pstar_daily.csv`：每持仓每日 exact 动态 P\* / A 退出线 / B 退出线 / 当日 High / 触发标记。
- `forward_input_manifest.csv`：每日输入数据 hash（防数据修订污染）。
- `forward_pre_existing_A.csv` / `_B.csv`：冻结日启动持仓（带入但不计入新信号统计）。
- `forward_ab_comparison.csv`：第一次正式评价（≥6 个月且 ≥15 笔独立交易）时填充 A/B 对比。

## 首次正式评价门槛

同时满足：前瞻时间 ≥ 6 个月 且 独立交易 ≥ 15 笔。评价核心：B 相对 A 是否提供稳定改善（累计收益/回撤/夏普/胜率/平均交易/持仓时间/救单 vs 截断赢家/行业分布），不是 B 绝对赚钱。
