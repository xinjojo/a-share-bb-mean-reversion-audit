# BACKTEST_INVARIANTS — 回测不可违反规则清单

> 本文件把本项目在五轮红队审计 + Round5.1 基础口径封板中**实际踩过的坑**固化为规则。
> 任何新策略 / 新引擎接入本项目，必须逐条满足；违反即视为回测 INVALID。
> 每条规则附：**本项目踩坑实例** 与 **自动测试对应项**（`tests/test_backtest_invariants.py`，违反直接 FAIL）。

---

## R1. 禁止同Bar未来信息（最高优先级）

**规则**：任何使用 `close[T] / high[T] / low[T] / amount[T]` 产生的信号，不得在这些信息实际可知之前成交。

**本项目踩坑（P0，已验证 INVALID）**：`experiment_fast.py:554` 用 `high_adj[T] >= bb_upper[T]` 盘中判卖，而 `bb_upper[T]` 由含 `close[T]` 的 `rolling(20)` 算出（`prepare_fast:29-32`）。T 日盘中根本无法预知当日收盘才确定的上轨 → 原 +354.9% 中约 77%（383%→109%）收益来自该同Bar泄漏。修复后收益降至 45%-74%（STRICT_V2）。

**口径**：BB(20,2) 的 `ma=rolling(20).mean()`、`sd=rolling(20).std()`，pandas 默认**右对齐**、`min_periods=20`、**`ddof=1`**（样本标准差）。`bb_upper[T]` 仅由 `close_adj[T-19..T]` 构成。

**测试**：`test_bb_no_future`（手动 rolling(20) 与引擎一致）、`test_static_no_future_patterns`（源码无 `shift(-1)/center=True/iloc[i+1]`）。

---

## R2. 明确 signal_time 与 execution_time

**规则**：每笔订单必须保存 `signal_date / signal_time / execution_date / execution_time / execution_price_type`，禁止信号时点与执行时点混用。

**本项目踩坑**：早期 close 信号 + close 成交未声明"收盘后集合竞价"假设；STRICT_V1 用单一 `etf_trade_px` 变量覆盖整天（见 R5）。

**要求**：STRICT_V2 已事件驱动——买入信号在 T 收盘产生（`execution_price_type=T+1 open`），退出 A 为 T 日盘中触及 T-1 已知上轨（`price_type=prev_bb_upper`），退出 B 为 T 收盘确认 → T+1 open 卖出（`price_type=T+1 open`）。新策略必须同样显式区分。

**测试**：`test_no_retroactive_etf`、`test_exit_b_next_open`（买入/卖出价 = 执行日 open，非信号日 close）。

---

## R3. Point-In-Time 数据

**规则**：以下信息必须 PIT 化（当时可知，禁止用当前快照回填历史）：
- ST / \*ST 状态
- 股票名称
- 上市日期 / 退市日期
- 涨跌停制度（主板 10% / 创业板科创板 20% / ST 5% / 北交所 30%）
- 股票池资格

**本项目踩坑（CONFIRMED）**：`prepare_fast:20-25` 用 `stock_basic.name` **当前快照** + `name.contains('ST')`。差异 **466,247 股票日 / 683 只**（摘帽 305,158 天、曾 ST 161,089 天），并污染 ST 过滤 + 涨跌停判定 + TopN 候选池。修复后（`data/pit_st_daily.parquet`，来自 Tushare `namechange`）：STRICT_V2_A 收益 -12.4pp、B -1.9pp。

**测试**：`test_pit_st_used`（`D[d].is_st == pit.is_st_pit`）。

---

## R4. 禁止用回测窗口截断制造伪上市日期

**规则**：上市满 N 日必须来自真实 `list_date` + 完整交易日历（本项目用 1990 起的 `trade_cal_full.parquet`），禁止把"回测切片首日"当作上市日。

**本项目踩坑（CONFIRMED，重大）**：`prepare_fast` 用 `listing.setdefault(tc, di)`（di=切片首日 2020-01-02）→ 2010 年上市的老股票被误判为"上市不足60日"。**2020 前 60 交易日：old 候选=0 → correct 候选=212,080**。

**测试**：`test_listing_from_listdate`（老股票 `first_eligible_i < offset`）。

---

## R5. ETF / 多资产交易不得时间倒流

**规则**：T 日 15:00 收盘后才确认的资金需求，不能按当日 09:30 的 ETF open 价筹资。必须事件驱动：
- `ensure_cash_open()`：open 时点为当日 pending 挂单筹资（open 价）
- `rebalance_close()`：close 时点用剩余现金买 ETF（close 价）

**本项目踩坑（CONFIRMED，重大）**：`round5_audit.py:110` 单一 `etf_trade_px`（`buy_mode==next_open` 或 `exit_bb_mode==close_confirm_next` 时用 open，否则 close）覆盖整天所有 ETF 操作 → 收盘信号却按 09:30 open 卖 ETF。STRICT_V1 的 62.6%/52.3% 因此作废。

**测试**：`test_static_no_single_etf_px_for_whole_day`（无 `etf_trade_px`；`ensure_cash_open`/`rebalance_close` 存在）。

---

## R6. next_open 不得使用当天完整 OHLC 判断是否成交

**规则**：09:30 执行开盘订单时，禁止用当日收盘才能知道的整日信息（如 `open==high==low==close` 一字板）判断是否 fill。

**本项目踩坑（CONFIRMED）**：引擎曾用 `one_word = open==high==low==close`（整日一字板）判断 T+1 开盘成交 → 未来信息。修复：`open_fill` 双档——`limit_conservative` 只用当日开盘价 vs 涨跌停价；`optimistic` 不判成交并标注 `DAILY_DATA_APPROXIMATION`。Top10 高流动性下两档结果一致。

**测试**：`test_static_no_whole_day_oneword`。

---

## R7. 估值与成交价格体系必须明确、不得混用

**规则**：`market price / NAV / adjusted price / raw price` 必须明确区分：
- **信号**：后复权价 `close_adj = close × adj_factor`（保证分红送转连续）
- **成交/现金流**：真实价格（open / close / prev 上轨换算 `bb_upper/adj_factor`）
- **估值**：本项目用 ETF **market close**（`etf_sh × close`）；`unit_nav` 仅末5天有值，不可作全程估值源

**本项目踩坑**：曾混用 NAV 与 market close；STRICT_V1 的 exit 用 `bb_upper[T]`（未换算真实价）。

**测试**：`test_static_adj_only_for_signal`。

---

## R8. Corporate Action（分红/送转/拆股/配股/除权除息）单独处理

**规则**：复权价只用于信号与止盈目标换算；真实 shares / cash 必须按实际成交处理，不得用复权价直接计算交易金额。

**本项目验证**：PIT 复权反事实实验（第二轮实验1）：`adj_close=close×adj_factor` + `BB(20,2)` + 信号，PIT（只用 T 日及之前已发生的除权除息）与当前累计复权对比 **signal_diff=0 / 8054 行** → 该策略对复权因子口径不敏感（信号在除权前后稳定）。但仍必须遵守本条作为通用规则。

**测试**：静态（R7 相关）+ 反事实实验记录在 `REDTEAM_ROUND2_EXPERIMENTS.md`。

---

## R9. T+1 必须 lot-level 验证

**规则**：每批新增 shares 单独记录 `sellable_date`（买入当日不可卖，次日可卖）；同日先买后卖同一标的 = 违规。

**本项目验证**：STRICT_V2 引擎每笔 `hold_days>=1`；`FINAL_SETTLE` 3 笔持仓 40/36/5 自然日均无 T+1 违规。

**测试**：`test_t_plus_1_lot_level`（非 FINAL 每笔 hold_days>=1；actions 无同日同标的先买后卖）。

---

## R10. 资金守恒

**规则**：每天必须满足 `equity == cash + stock_market_value + ETF_market_value`，且：
- `negative_cash_days == 0`
- `overallocated_days == 0`
- `max_balance_error ≈ 0`

**本项目验证**：STRICT_V2 全 1611 日资金守恒误差 = 0.00e+00。

**测试**：`test_cash_conservation`。

---

## R11. 手续费 / 税 / 滑点必须进入真实现金流

**规则**：不能只影响 qty 估算；必须从 cash 中实际扣除（买入 `cash -= amt+fee`，卖出 `cash += amt-fee`）。
费用口径：佣金 0.025%（最低 5 元）、印花税卖出 0.1%→0.05%（2023-08-28 前后）、过户费 0.001%、滑点双边。

**本项目验证**：重建单笔 pnl（Σ买入含费成本 vs 卖出净额）与引擎一致（误差 <1 元）。

**测试**：`test_fees_in_cashflow`。

---

## R12. 期末清仓必须进入最终 equity

**规则**：回测结束时未平仓股票 + ETF 必须清仓（扣费、扣税、扣滑点），并同步到 equity 曲线最后一个点；禁止"清仓发生在曲线最后一点之后但 stats 仍读清仓前 equity"。

**本项目踩坑**：早期版本未同步期末清仓 → 虚增收益。修复后末行 `equity==cash`。

**测试**：`test_final_settle_synced`。

---

## R13. Survivorship Bias 必须显式报告

**规则**：若数据源无法提供历史退市股票，必须在报告中显式标注存在 survivorship bias，不得隐藏。

**本项目状态**：`combined_daily.parquet` 为 Tushare 当前快照，2020 后退市股缺失 15 只（P7），其中进入 Top10 的无法从现有数据验证 → 标 `NEED_EXTERNAL_DATA`，最小补数清单见 Round5 报告。**当前所有结论含 survivorship bias 成分**。

**测试**：人工检查项（README 已显式声明）。

---

## R14. 参数选择与测试集必须隔离

**规则**：禁止用整个历史区间寻找最佳参数后宣称策略有效。必须 Discovery / Validation / Final OOS（或 retrospective holdout）分离；Walk-forward 选择参数时只能用过去数据。

**本项目踩坑**：Round3 曾对 2020-2026 全样本调参 → 因同Bar泄漏得 A 评级，后被推翻。当前冻结：Top10 / BB(20,2) / K=3 / max_levels=5 / level_cash=20万，禁止继续调参。

**测试**：`test_static_params_frozen`。

---

## R15. 多笔交易重叠时禁止默认按 trade 独立

**规则**：K>1 时同一市场急跌窗口可能产生多笔高度相关交易，禁止直接当独立样本做 bootstrap。必须做 block / market-event / cluster bootstrap，并报告有效独立事件数。

**本项目验证**（Round5 P5）：K=3 的 103 笔存在 150 个时间重叠对、最大并发 3、按±10 日聚类后有效独立事件约 60-80 个；三种 bootstrap 的 P(收益>0) 均 100%，但置信区间宽度不同。

**测试**：分析项（记录于 `results/round5/p5_*`）。

---

## 测试运行

```bash
cd <项目根>
python3 tests/test_backtest_invariants.py     # 28 项断言, 全部 PASS 才允许回测结果用于研究结论
```

新策略接入验收流程：
1. 复用同一 `data/`（PIT ST / 完整日历 / 退市股补齐后）
2. 引擎通过本测试全部 28 项
3. 参数选择遵守 R14（冻结或严格 OOS）
4. 结论遵守 R13（显式声明 survivorship bias）
