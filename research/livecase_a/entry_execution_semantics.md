# ENTRY EXECUTION SEMANTICS — T+1 入场语义审计

日期：2026-09-06
阶段：LIVECASE-A（MANUAL LOSER CASE RECONCILIATION）
状态：**事实核对完成，无 MISMATCH**

---

## A. 当前冻结引擎的入场定义（以源码为准）

`src/run_strict_c.py`（`run_fast_multi_strict_c`）与 `src/round51/round51_audit.py`（STRICT_V2）：

1. **T 日（signal_date）收盘后判定信号**：
   - `close_adj(T) < BB_LOWER(T)`（MA20 − 2×SD20，ddof=1，含当日）
   - 且当日**不是收盘跌停**（`is_limit_down`，correct 口径 = 收盘价等于跌停价）
2. **买入执行在 T+1 开盘**：`entry_price = open(T+1) × (1 + 10bp 滑点)`
3. 若 T+1 开盘一字涨停（`open >= limit_up_px`）→ 当日不可成交，信号顺延到 T+2（`open_fill='limit_conservative'`）
4. 买入排在当日 amount 降序 Top10 候选池内，K=3 槽位、100 股一手

**全 96 笔冻结交易验证结果**：signal_date 全部 = entry_date 的前一个交易日（`sig_delay = 1`），**无一笔因涨停挡而延迟成交**。这与 Top10 高流动性（大市值高成交额）候选的预期一致。

## B. T+1 是设计还是实现遗留？

**是设计，且有意的保守假设。**

- 信号在 T 日收盘后（15:00 之后）才完整确定，任何"T 日以收盘价买入"的口径都使用了未来信息（在 15:00 收盘前无法知道最终收盘价是否跌破下轨）。
- A 股为 T+1 交收制度，且历史回测无法可靠模拟 T 日 14:57–15:00 集合竞价买入，故冻结口径一律 T+1 open 成交。
- 这与红队审计结论一致：原第一代策略 +354.9% 因 same-bar 未来信息被判定 INVALID（`archive/invalid/RESULTS_LATEST.md`）。

## C. 与预注册文档一致性

- `research/signal/REDTEAM_ROUND51_STRICT.md`（2026-09-02）明确记载 STRICT_V2 引擎语义：**"买入: T收盘信号 -> T+1 open 执行"**。
- STRICT_C（dynamic intraday touch 退出）继承同一入场语义。
- **结论：与 prereg 一致，无 MISMATCH。**

## D. 用户观察的"很多 signal 后是 T+1 entry"——正是设计本身

用户在多笔案例（如亿纬 02-20 信号→02-21 入场、牧原 05-11 信号→05-12 入场）中看到的"信号日和入场日差一天"，就是冻结策略的 T+1 保守口径，不是执行 bug。

## E. 历史可交易性备注（非策略修改）

2020–2024 期间 A 股大部分主板股票支持 15:05–15:30 盘后固定价格交易（收盘定价交易，2020 年起上交所/深交所部分时段开放），但策略从未使用该通道；冻结口径统一为 T+1 open，更保守、更可复现。本阶段不重跑 T 日买入回测。
