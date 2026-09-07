# MONTHLY_BB_ALPHA_REGISTRY — 月线布林带均值回归 Signal-Level Alpha 审计 Registry

- Registry SHA256: （Commit A 时冻结，见 .sha256）
- 冻结日期：2026-09-07
- 状态：**FROZEN — 结果计算前提交**（Commit A 先于任何正式结果）
- 关联系统：EE15 日线前瞻（冻结，不可修改）——本分支**独立**，禁止污染/优化 EE15

---

## 0. 研究问题（唯一）

月线级别跌破 Bollinger Band 下轨（BB20, 2σ）之后，未来 1/3/6/12 个月的收益分布，
是否显著优于（a）同一股票随机月份、（b）同一股票无条件月份、（c）时间匹配的非信号股票？
即：**月线 BB 下轨信号本身是否存在 signal-level alpha。**

在 signal alpha 未确认前：禁止组合回测、禁止优化卖点、禁止引入任何其他指标、禁止参数寻优、禁止宣称可实盘。

## 1. 数据源与口径（冻结）

- 数据源：Tushare Pro（付费权限）。TOKEN 仅从环境变量 `TUSHARE_TOKEN` 读取，禁止写入任何文件/日志/stdout。
- 接口：
  - `index_daily`：宽基指数日线（点位，无复权）
  - `daily`：全 A 日线（按 trade_date 逐日拉取，天然包含已退市股票历史 → 避免幸存者偏差）
  - `adj_factor`：后复权因子（按 trade_date）
  - `daily_basic`：月度 PIT 市值（仅取每月最后一个交易日 total_mv/circ_mv）
  - `stock_basic`：全量股票列表（含 L/D/P，行业/上市日/退市日）
  - `namechange`：ST/名称变更（PIT 状态）
- 时间范围：日线拉取起点 **2004-01-01**（为月线 BB(20) 提供预热），终点 = 当前最新交易日（2026-09-07）。
- 本地缓存目录：`data/monthly_bb/`（gitignore；大文件不入库，README 记录 hash/行数/schema）。

## 2. 研究时段（冻结）

- 信号评估窗口（开发期）：信号月 **2005-01 ~ 2024-12**（月线 BB(20) 需 ≥20 个月历史，实际首个可用信号 ≈2006 年起视个股历史而定）。
- 已暴露段（仅展示，不用于结论）：**2025-01 ~ 当前**（EE15 前瞻已开始、2025-2026 部分 outcome 已暴露；本分支不读取 EE15 前瞻台账，仅按时间窗划分展示段）。
- 年代分组：2005-2009 / 2010-2014 / 2015-2019 / 2020-2024 / 2025-当前（展示）。

## 3. 研究对象（三组，冻结）

### A. 宽基指数 / ETF 映射
| 指数 | ts_code | 说明 |
|---|---|---|
| 沪深300 | 000300.SH | 优先指数点位，不用 ETF 截断历史 |
| 中证500 | 000905.SH | 同上 |
| 中证1000 | 000852.SH | 同上 |
| 创业板指 | 399006.SZ | 同上 |
| 科创50 | 000688.SH | 2019-07 后发布，此前无数据（censored） |
| 上证50 | 000016.SH | 同上 |

### B. 高流动性 / 大市值 A 股（PIT）
- 每月末按当日 `total_mv`（PIT，非未来信息）排序取 Top100 / Top300 / Top500。
- 资格：非 ST（PIT）、上市 ≥ 12 个月、当月有正常成交（月 amount > 0）。
- 同一信号月内每只股票只属于其当时市值分组。

### C. 全 A 股（最宽基准）
- stock_basic 全量（含退市）；非 ST、上市 ≥ 12 个月、当月有成交。
- 退市股票保留至退市日（避免幸存者偏差）。

## 4. 月线构造（冻结，严格避免未来函数）

- 月末 = 每个自然月最后一个实际交易日。
- 月线 OHLC：open=月首交易日 open；high=月内最高 high；low=月内最低 low；close=月末 close；volume/amount=月内求和。
- **价格序列复权口径：后复权** `close_adj = close × adj_factor`（Tushare adj_factor 为后复权因子，单调不回改 → 无未来函数；前复权会用未来因子回改历史，禁止用于收益与 BB）。
- BB 与收益计算统一使用 `close_adj`；MFE/MAE 用后复权 high/low。
- 指数：指数点位本身连续，无需复权。

## 5. 布林带参数（冻结，唯一一组）

- **BB(20 个月, 2σ)**；`rolling(20, min_periods=20).mean()` ± 2 × `rolling(20).std(ddof=1)`。
- ddof=1（样本标准差），与日线冻结策略口径一致（EE15 引擎 pandas rolling.std 默认 ddof=1，见 BACKTEST_INVARIANTS R1）。
- 禁止第一阶段测试其他 window / σ 组合。

## 6. 信号定义（冻结）

- 主信号：**月内最后交易日 close_adj < 当月 BB20 lower**（当月 lower 仅用截至当月月末可得的 20 个月序列计算）。
- `signal_date` = 信号月最后交易日。
- `entry_date` = 下一月第一个实际交易日；`entry_price` = 该日 open（后复权）。
- 可交易口径：entry open → horizon 收盘（后复权收益）。
- 纯统计口径（不可直接交易）：signal month close → horizon close（后复权收益）。
- 两口径分别输出，不得混用。

## 7. 连续跌破处理（冻结，两种口径均输出）

- A. ALL_SIGNAL_MONTHS：每个月线下轨信号都计。
- B. NEW_EPISODE（主统计）：上月未跌破（close_adj ≥ BB lower 或上月无 BB）→ 本月首次跌破，计 1 个新 episode；连续跌破月仅第 1 个月计。
- 主结论基于 NEW_EPISODE；ALL_SIGNAL_MONTHS 为补充。

## 8. Forward 窗口（冻结）

- 1 / 3 / 6 / 12 个月（月线自然月，非交易日）。
- 未来不足 horizon：保留 signal，horizon 收益置 NaN（censored），**不删除**。
- 每 horizon 输出：close-to-close（统计）与 entry-open→horizon-close（可交易）两套。
- MFE/MAE：截至各 horizon 的 max(后复权 high)/min(后复权 low) 相对基准（signal close 或 entry open）的百分比；first recovery month、first +5%/+10%/-10%/-20%/-30% 首次达到月。

## 9. 描述统计（冻结）

每个 universe × horizon × 口径：
N（含 censored 标注）、mean、median、std、variance、P5/P10/P25/P50/P75/P90/P95、
positive rate、≥+5%/+10%/+20% 比例、<−10%/−20%/−30% 比例、max、min、avg holding。

## 10. 对照基准（冻结，三个）

- B1 同股随机月份：同一股票、匹配年份的随机月份抽样（非信号月）。
- B2 同股无条件：同一股票全部可交易月份的无条件 forward 收益。
- B3 时间匹配：每个 signal month，从同期（±同月）非信号股票中抽样。
- 推断：bootstrap（≥1000 次，signal mean/median vs null）+ permutation p-value（≥1000 次）+ effect size（Cohen's d / 中位数差）。不止 t-test。

## 11. 横截面相关性处理（冻结）

- 月线大跌（2008/2015/2018/2022）常全市场同步：同一 signal month 内 N 只股票 **不视为独立样本**。
- 至少：① 按 signal month 聚合的月均 signal return 分布；② cluster bootstrap by signal_month（≥1000 次）。
- 报告 raw N 与有效独立月份数。

## 12. Market-relative 超额（冻结）

- 对个股：`excess = stock_forward_ret − 沪深300 同期 forward ret`（月线序列对齐）。
- 对指数：与自身长期无条件 forward 分布比较（无市场基准，只有绝对）。
- 结论不得仅凭绝对收益为正。

## 13. 风险 / 结构性衰退（冻结）

- 统计 signal 后 12M 仍 < −20% / < −30% / < −50% 案例 → worst_cases.csv（股票、名称、signal_date、行业、12M、最大 MAE、是否 ST、是否退市、退市日期）。
- 随机抽 ≥20 个 worst cases 人工 sanity。

## 14. 禁止事项（冻结）

- 禁止：K=3 / 20 万层 / 5 层加仓 / ETF 现金管理 / 提前 1.5% / 上轨或中轨卖出 / 止损优化 / 任何组合回测。
- 禁止：参数搜索（BB 窗口/σ、horizon 以外的组合）、引入 RSI/MACD/ADX/Squeeze/成交量等任何过滤。
- 禁止：用 2025+ 展示段选择任何口径；用未来信息（未来市值/未来行业）构造分组。
- 禁止：修改 EE15 任何文件/冻结参数。

## 15. 结论分级（冻结）

- A：月线存在强且稳定 signal alpha（信号相对三个基准与市场相对均显著，且跨年代/分组稳健）。
- B：存在一定 signal alpha，但明显依赖股票类型/年代/市场环境。
- C：只有原始反弹，没有 market-relative alpha。
- D：没有稳定统计优势。
- 平均收益为正不自动构成 A。

## 16. 输出（冻结）

- 全量：`results/evidence/monthly_bb/monthly_signal_wide.parquet` + CSV（过大分片）+ 大文件本地副本 hash。
- 指数：`manual_review_index.csv`（全部信号明细）。
- 统计：descriptive_stats / benchmark / cluster / market_relative / size_gradient / worst_cases / decade / bins。
- 图：8 类（histogram、forward median path、MFE/MAE percentile path、universe 比较、signal vs null、decade、指数 case、BB z vs future return）。
- 报告：`research/monthly_bb/MONTHLY_BB_AUDIT_REPORT.md`。

## 17. Git 提交纪律（冻结）

- Commit A：本 Registry + schema + 全部分析代码，**先于任何正式结果**。
- Commit B：结果 CSV/报告/图。
- 大文件（parquet/csv 分片）不入库，README 记本地路径 + sha256 + 行数 + schema。
- 提交前 secret scan：Tushare token 格式 / token / apikey / api_key / secret / password；git diff、git status、git grep 三查。任何命中立即停止 push 并清除。
