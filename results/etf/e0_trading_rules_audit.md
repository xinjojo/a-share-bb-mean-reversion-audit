# E0 ETF Trading Rules Audit（微观结构审计）

> 生成日期: 2026-09-04 | 数据来源: Tushare fund_basic / fund_daily / fund_adj / fund_share
> 范围: 1400 只候选 ETF（境内 A 股股票 ETF），其中 1345 只有 fund_daily 数据，1137 只 eligible 且有数据

---

## 1. T+1 交易制度

- **结论**: 境内 A 股股票 ETF 二级市场买入实行 **T+1**（当日买入，次一交易日可卖出）。
- **核验**: 全部 1400 只候选 ETF 均为交易所上市股票型 ETF（`fund_type='股票型'`，`market='E'` 交易所），适用股票 ETF T+1 规则。
- **注意**: 债券 ETF、货币 ETF、黄金 ETF、跨境 ETF、商品期货 ETF 部分实行 T+0，**已在 Universe 筛选阶段排除**，不得将 T+0 规则误套到股票 ETF。
- **Backtest 影响**: 信号日 t close 产生信号，t+1 open 成交，与股票版 baseline 一致。

## 2. 申报单位（Lot Size）

- **结论**: 股票 ETF 竞价买入申报单位为 **100 份或其整数倍**；卖出不足 100 份的零股部分按交易所规则一次性卖出。
- **核验**: `e0_price_limit_rule.csv` 中全部 1400 只 `lot_size=100`。
- **关键区别**: **100 股（股票）≠ 100 份（ETF）**。ETF 份额单位为"份"，非"股"。position sizing 必须按 ETF 份额取整到 100 的整数倍，不得 fractional shares。
- **Backtest 影响**: 买入数量 `qty = int(cash / price / 100) * 100`，已在 signal_capacity 脚本中实现。

## 3. 最小价格变动（Tick Size）

- **结论**: 基金二级市场申报价格最小变动单位为 **0.001 元**（A股股票为 0.01 元）。
- **核验**: 数据驱动检查——遍历 1345 只有 fund_daily 的 ETF，检查 close 价格是否符合 0.001 分辨率（`close * 1000` 为整数），**0 只不符合**。
- **Backtest 影响**: fill/target/stop/limit 价格必须 round 到 0.001 的整数倍。当前 signal_capacity 脚本使用原始 open/close/pstar 价格未做 tick round，**E1 必须加入 tick 约束**。

## 4. 涨跌幅限制（Price Limit）

- **结论**: 禁止写死"所有 ETF 10%"。逐只核验结果：

| 规则 | ETF 数量 | 说明 |
|------|---------|------|
| 10PCT | 1145 | 主板/中小板成份为主的 ETF |
| 20PCT_STAR | 163 | 科创板（688/689）成份为主，20% |
| 20PCT_GEM_20200824 | 92 | 创业板（30 开头），2020-08-24 起 20% |

- **PIT 规则**: 创业板涨跌幅 2020-08-24 之前为 10%，之后为 20%。`price_limit_pit` 字段已标注。科创板 2019-07-22 上市起即 20%。
- **历史变化**: 2020-08-24 创业板注册制改革是唯一已知的股票 ETF 涨跌幅规则历史变化。**不得将 2026 年规则倒灌到 2015 年**。
- **Backtest 影响**: E1 回测中，买入日 open 若触及涨停则无法成交（需跳过），卖出日若触及跌停则无法卖出（需持有）。E0 signal_capacity 脚本未实现涨跌停成交约束，**E1 必须加入**。

## 5. 交易制度历史版本

- **集合竞价/连续竞价/收盘集合竞价**: 上交所 2018-08-20 起引入收盘集合竞价；深交所此前已有。本策略只用 close signal → 下一交易日 open 成交，不受盘中交易阶段变化影响。
- **盘后固定价格交易**: 科创板/创业板盘后定价交易（15:05-15:30）不影响本策略（使用 open/close 常规时段）。
- **被忽略规则说明**: 本策略不涉及盘中实时下单，仅用日频 open/close/high，因此盘中交易制度细节（集合竞价撮合规则、临停机制等）对 backtest path 无实质影响。

## 6. 交易成本（Transaction Cost）

- **印花税**: ETF 二级市场交易**无卖出印花税**（股票卖出有 0.05% 印花税，2023-08-28 起）。**不得将股票印花税套用到 ETF**。
- **佣金**: 券商佣金通常 0.025%（万 2.5），最低 5 元。baseline 采用 `commission_rate=0.00025, min_commission=5.0`。
- **经手费/证管费/过户费**: 已包含在佣金中或极低（ETF 无过户费）。baseline 不单独计列。
- **滑点**: baseline 10bp，sensitivity 档位 5bp/10bp/20bp（与主仓库 10bp 框架对齐）。
- **成本模型文件**: `e0_cost_model.json`
- **Backtest 影响**: ETF 无印花税使得交易成本显著低于股票（股票卖出印花税 0.05% 是主要成本项），高频策略在 ETF 上成本 drag 更小。

## 7. 分红/复权/NAV/折溢价

- **复权口径**: `fund_adj` 提供复权因子，`close_adj = close × adj_factor`。已核验 1345 只 ETF 中 `fund_adj_flag=True`（adj_factor 不全为 1）的占比——分红/拆分导致复权因子变化是正常现象。
- **Price Return vs Total Return**: `fund_daily.close` 为 raw close（price return），`close_adj` 为前复权（含分红再投资，近似 total return）。**长期收益比较必须用复权价格**，不得用 raw close。
- **NAV/IOPV/折溢价**: `fund_daily` 不含 NAV/IOPV 字段。Tushare `fund_nav` 接口可获取 NAV 但未在本次下载范围内。正式二级市场回测用 market traded price（close/open），不用 NAV 替代成交价。
- **异常折溢价**: 未发现 amount==0 或 vol==0 的交易日（数据驱动检查 0 条），说明流动性枯竭导致的极端折溢价在候选 Universe 中不显著。但 E1 应监控买入日 open 相对 pre_close 的异常跳空（>5%）。

## 8. 停牌/无成交/流动性

- **停牌**: Tushare `fund_daily` 中停牌日通常无记录（非 amount=0 的空行）。回测中若某日某 ETF 无数据，则视为不可交易。
- **零成交**: 数据驱动检查——1345 只 ETF 的全部交易日中，`amount==0` 共 **0 日**，`vol==0` 共 **0 日**。说明候选 ETF 均有持续成交。
- **流动性分布**: 见 `e0_liquidity_distribution.csv`。ADV60 >= 5000 万的有 437 只，>= 1 亿的有 232 只，>= 5 亿的有 74 只。
- **Backtest 影响**: `amount == 0` 不得假设无摩擦成交。E0 中未发现此情况，但 E1 应在回测引擎中加入 `amount > 0` 过滤。

## 9. 清盘风险（Delisting / Survivorship）

- **已清盘 ETF**: `fund_basic` 中 `status='D'`（delisted）共 676 只（全部基金类型，含非股票）。候选 1400 只股票 ETF 中含已清盘者。
- **delist_date**: `fund_basic.due_date` 字段在多数 ETF 中为空（开放式 ETF 无固定到期日），清盘日期需从基金公告获取。Tushare `fund_basic` 不直接提供清盘日期，**这是 PIT Universe 的数据缺口**。
- **Survivorship 处理**: Universe B（PIT）使用 `list_date <= t` 且 `(delist_date 为空或 delist_date > t)` 过滤。由于 delist_date 大量缺失，实际 PIT Universe 可能包含已清盘 ETF（其 fund_daily 数据截止到清盘前最后交易日，回测中自然不可交易）。
- **更换跟踪指数**: 部分 ETF 历史上变更过跟踪指数，`fund_basic.benchmark` 为当前值，历史变更需从基金公告获取。**E0 未做历史跟踪指数变更的 PIT 重建**，这是已知 limitation。
- **Backtest 影响**: 清盘 ETF 在最后交易日后无数据，回测引擎自然跳过（无数据=不可交易）。但清盘前的流动性枯竭（amount 骤降）可能导致实际无法卖出，E0 中未发现 amount=0 但清盘前最后几日可能有低流动性。

---

## 审计结论

| 项目 | 状态 | E1 必须处理 |
|------|------|------------|
| T+1 | 确认 | 已实现（t+1 open） |
| Lot=100 份 | 确认 | 已实现（qty 取整） |
| Tick=0.001 | 确认 | **需加入 tick round** |
| 涨跌幅逐只 | 确认（10%/20%） | **需加入涨跌停成交约束** |
| 无印花税 | 确认 | 已实现（stamp_duty=0） |
| 复权口径 | 确认（close_adj） | 已实现 |
| 流动性 | 无零成交 | 需加入 amount>0 过滤 |
| 清盘 PIT | 部分（delist_date 缺失） | 需标注 limitation |
| 跟踪指数变更 PIT | 未做 | **已知 limitation，E1 需评估影响** |
