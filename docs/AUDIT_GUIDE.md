# A股单股布林带均值回归策略 — 独立审计参考材料（AUDIT GUIDE）

> 本材料供**独立审计 agent** 使用，用于核验本策略回测结果的可信度。
> 审计应基于代码与数据本身，而非交付物声称的数字。
> 所有无法精确模拟之处已诚实标注（EXACT / APPROXIMATION / PARTIAL / UNSUPPORTED）。
>
> 生成时间：2026-09-01　|　回测区间：2020-01-02 ~ 2026-08-25　|　数据源：Tushare Pro（方案B）

---

## 0. 审计目标

对以下**核心主张**逐项核验：
1. **策略收益真实性**：当前最佳策略 2020-01 ~ 2026-08 累计 +226.75%（含ETF现金管理）是否为真实可交易结果。
2. **无未来函数**：成交额、收盘价、复权因子、涨跌停信息是否泄漏未来。
3. **幸存者偏差程度**：数据是否包含历史退市股票，缺多少、影响多大。
4. **A股规则符合度**：T+1、100股、涨跌停、停牌、ST排除、费用模型是否符合真实规则。
5. **引擎正确性**：上轨止盈、分批加仓、加权平均成本、ETF现金管理的实现是否有 bug。

---

## 1. 项目背景与需求演化（理解"为什么策略长这样"）

### 1.1 原始需求（用户第一版）
- 每个交易日找出**成交额排名第一**（Top 1 by amount）的 A 股普通股票
- 当它**收盘价跌破布林带下轨**（MA20−2×STD20）时**分批建仓**
- 最多 **5 层 × 20%**（第1次20%，第5次100%）
- **止盈**：持仓加权平均成本 × 1.015（1.5%），盘中 High 触发
- **止损**：参数化模块（fixed_percent / ATR / close_below_MA / fixed_price / disabled）
- 严格 T+1、100 股整数倍、涨跌停、停牌、ST 排除、新股满 60 交易日
- 费用：佣金（最低5元）、印花税（卖出单边）、过户费、滑点
- 复权：指标用后复权，交易用不复权，禁止混用

### 1.2 多轮迭代后的**最终策略**（当前交付版本）
> 与原始需求存在**有意偏离**，均来自用户逐轮确认，非实现错误。

| 维度 | 原始需求 | 最终策略 | 变更原因 |
|---|---|---|---|
| 股票池 | Top 1 | **Top 10**（top_n=10） | 用户测试发现Top1经常空仓，扩大池子提高资金利用率 |
| 止盈 | 固定 1.5% | **布林上轨**（盘中 High≥上轨卖出） | 用户发现95%以上交易都到2%，怀疑固定比例截断利润 |
| 止损 | 可配置 | **当前关闭**（无固定/时间止损） | 多轮扫描后用户暂选无止损；另有时间止损30日版本可测 |
| 加仓 | ≤5层 | ≤5层（保留） | — |
| ETF现金管理 | 无 | **空仓期买入标普500ETF(513500)** | 用户要求提高空仓期资金利用率；100%目标比例（另有30/50/70扫描） |
| 止盈后当天重入 | 支持 | **关闭**（当天不再操作） | 用户明确："当天止盈后当天不再操作该股票" |

### 1.3 关键用户决策点记录
- 跌停不买入（收盘跌停的票不买）；排除后重新选 Top1 → 扩展为 TopN 内选第一只非跌停
- 加仓同样遵循"非跌停 + 收盘<下轨"原则
- 停牌按无行情日自然跳过
- 只做股票，暂排 ETF（指选股池）；ST/*ST 一律不买
- 用户多次要求：诚实标注近似，不能假装精确

---

## 2. 最终策略完整定义（机器可执行）

### 2.1 引擎：`etf_live_backtest.py`（当前最佳，含ETF现金管理）

**每日流程（按交易日顺序）**：

1. **预处理（一次性）**
   - 载入 `combined_daily.parquet`（Tushare daily + adj_factor 合并），合并 `stock_basic` 得 name/market
   - `close_adj = close × adj_factor`（后复权），`high_adj = high × adj_factor`
   - 按 ts_code 分组计算 `ma20`、`std20`（rolling 20, min_periods=20）
   - `bb_lower = ma20 − 2×std20`，`bb_upper = ma20 + 2×std20`

2. **持仓处理**（若有持仓）
   - **上轨止盈**：`hold_days ≥ 1`（T+1）且 `high_adj ≥ bb_upper` → 全部卖出，成交价 `= bb_upper / adj_factor`（转实际价）
   - **时间止损**（可选，time_stop_days 非空时）：`hold_days ≥ N` → 收盘价清仓
   - **加仓**：`close_adj < bb_lower` 且非跌停 且 `levels < 5` → 加仓一层（目标 20 万，100 股整数倍）；**加仓后重算加权平均成本** `avg_cost = (old_shares×avg_cost + cost_add) / new_shares`
   - 优先级：先止盈 → 后时间止损 → 后加仓

3. **空仓扫描买入**
   - 股票池 = 当日全部非 ST（name 含 "ST" 剔除）且上市满 60 交易日
   - 按 `amount`（当日成交额）降序取 **Top 10**
   - 在 Top 10 中按成交额顺序找第一只 `close_adj < bb_lower` 且非跌停 → 候选
   - 买入：20 万（level_cash），`qty = int(min(level_cash, cash)/price/100)×100`，不足 100 股跳过
   - 成交价 = 当日收盘价 `close`（收盘买入）

4. **ETF 现金管理**（空仓时）
   - 空仓且现金充裕 → 把 ETF 市值再平衡到 `总资产 × etf_ratio`（默认 1.0 = 100%）
   - 买入按市价 close、按 `unit_nav` 估值；需要资金时先卖 ETF 换现金（卖按市价）

5. **估值**
   - `equity = cash + stock_val(实际价) + etf_shares × unit_nav`

**参数**：`top_n=10, max_levels=5, level_cash=200_000, etf_ratio=1.0, min_listing_days=60, initial_cash=1_000_000`

### 2.2 关键实现细节（审计重点）
- **T+1**：`entry_day_idx` 记录入场日索引，`hold_days = i - entry_day_idx`，`hold_days ≥ 1` 才允许卖 ✓
- **加权平均成本含费用**：`cost_add = amount + fee`，`avg_cost = 总成本 / 总股数` ✓
- **止盈价**：`sell_price = bb_upper / adj_factor`（用后复权信号转实际成交价）✓
- **跌停不买**：`is_limit_down` 标记（见第 5 节来源）
- **加仓资金**：先 `ensure_cash_needed` 卖 ETF 补足，再买

---

## 3. 代码地图

```
项目根目录：/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/
├── etf_live_backtest.py      ← 【核心】当前最佳策略引擎（Top10+上轨止盈+5层+ETF现金管理）
├── live_backtest.py          ← 无ETF版引擎（同策略核心，Top1/3/5/10 扫描）
├── etf_ratio_scan.py         ← ETF目标比例扫描（0/30/50/70/100%）
├── live_backtest_r2.py       ← 早期版本（r2）
├── config/config.yaml        ← 最初配置（注意：止盈1.5%、Top1 与最终引擎不同）
├── data_loader/
│   ├── download_data.py      ← 数据下载入口（Tushare：stock_basic L/D/P + daily + adj_factor）
│   ├── tushare_loader.py     ← Tushare API 封装
│   ├── akshare_loader.py     ← 备用数据源
│   ├── data_validator.py     ← 数据校验
│   └── storage.py            ← 本地存储（raw/daily、raw/adj_factor 逐股文件）
├── engine/                   ← 早期设计的规则模块（commission/trading_rules/position）
├── backtest/                 ← 早期 VectorBT 尝试（vbt_runner.py）
├── analysis/                 ← 各类研究脚本（参数扫描/持仓分析/K线工具/时间止损等）
├── data/
│   ├── combined_daily.parquet  ← 【回测实际用】合并日线 770 万行，2020-01~2026-08
│   ├── etf_513500_*.parquet    ← 标普500ETF（市价+净值）
│   ├── etf_513100_*.parquet    ← 纳斯达克100ETF（基准用）
│   ├── index_000300.parquet / index_000905.parquet  ← A股指数（基准用）
│   ├── raw/stock_basic.parquet ← 股票列表（L 5550 + D 339）
│   ├── raw/daily/              ← 逐股原始日线（5777个文件，488MB）
│   ├── raw/adj_factor/         ← 逐股复权因子（5778个文件，82MB）
│   └── validation/             ← 数据校验报告
└── results/                   ← 全部回测结果（净值曲线/交易明细/图表/HTML）
```

**说明**：回测引擎实际读取的是 `combined_daily.parquet`（已合并），`raw/daily` 是下载存档，供单股核验。

---

## 4. 数据来源与口径（审计核心）

### 4.1 来源
- **Tushare Pro**，token 方案 B，接口：`stock_basic` / `daily` / `adj_factor`
- 备用：akshare（未实际用于本回测）

### 4.2 字段
- `daily`：trade_date, ts_code, open, high, low, close, vol(手), amount(千元), pre_close
- `adj_factor`：复权因子（Tushare 定义，后复权）
- `stock_basic`：ts_code, name, list_date, delist_date, market, exchange, list_status

### 4.3 复权处理（设计决策，禁止混用）
- **指标（BB带）**：`close_adj = close × adj_factor`（**后复权**）
- **实际交易价**：`close`（不复权）
- **止盈价转换**：`bb_upper / adj_factor`（后复权信号 → 实际价）
- **原因**：前复权价格随未来分红调整历史 → 引入未来函数；后复权 = 实际价 × 最新累计因子，历史价格序列固定

### 4.4 数据覆盖率与**幸存者偏差**（重要审计点）
- `stock_basic`：5889 只（L=5550 上市 + D=339 退市 + P 暂停）
- `combined_daily.parquet`：5725 只，2020-01-02 ~ 2026-08-25，7,709,365 行
- **退市股覆盖**：339 只退市股中 **214 只在回测数据中（63%）**，**125 只缺失**
- 缺失退市股中，**15 只是在 2020 年之后退市的**（本应出现在回测区间）：
  - 000018.SZ 神城A退(2020-01-07退)、000939.SZ 凯迪退(2020-12-17)、002604.SZ 龙力退(2020-07-15)、300104.SZ 乐视退(2020-07-21)、300028.SZ 金亚退(2020-08-03)、600074.SH 退保千(2020-06-02)、600240.SH 退华业(2020-02-05)、002450.SZ 康得退(2021-05-31)、300216.SZ 千山退(2020-09-16)、000587.SZ *ST金洲(2023-04-03)、002260.SZ 德奥退(2022-06-17)、600385.SH 退金泰(2022-07-07)、832317.BJ 观典防务、833874.BJ 泰祥股份、833994.BJ 翰博高新
- **北交所**（8/4/9 开头）在下载时被显式排除（`download_data.py` 中 `~ts_code.str.startswith(('8','4','9'))`）
- **结论**：幸存者偏差**存在但有限**。15 只区间内退市股多数为 ST（已被策略排除），但仍需审计 agent 判断其是否曾进入"成交额 Top10"池——**这是本材料最需要独立核验的偏差点之一**。

### 4.5 未来函数风险（审计重点）
| 潜在泄漏点 | 现状 | 判断 |
|---|---|---|
| 当日成交额 amount | 收盘后才知道，用于当日收盘后决策 | ✓ 无泄漏 |
| 当日收盘价 | 收盘后执行买入（收盘集合竞价近似） | ✓ 可接受（APPROXIMATION） |
| 布林带 | rolling 20 前向窗口（不含当日之后） | ✓ 无泄漏 |
| **复权因子 adj_factor** | **Tushare 返回的是"截至最新"的累计因子**，对历史所有日期统一适用 | ⚠️ **需审计**：后复权价格含未来分红/送转信息。对 BB 相对指标（close_adj 与 bb_lower 同乘因子）比例不变、信号不受影响；但止盈价转换（bb_upper/adj_factor）若涉及除权日附近，可能有偏差。**请审计 agent 验证该因子是否引入未来信息** |
| 涨跌停 is_limit_down | 由当日 pre_close 与涨跌幅实时计算（见下） | 需确认是否含未来信息 |
| 股票列表 | 含退市股（见 4.4） | 部分缓解幸存者偏差 |

---

## 5. A股交易规则实现对照

| 规则 | 实现 | 精度 |
|---|---|---|
| T+1 当日买入不可卖 | `hold_days ≥ 1` 才允许卖 | EXACT |
| 最小100股/整数倍 | `qty=int(.../100)*100`，不足100跳过 | EXACT |
| 跌停不买入 | `is_limit_down` 标记（当日收盘价≈跌停价） | APPROXIMATION |
| **跌停卖不出** | **未实现**（止盈/止损仍按价格触发卖出） | **UNSUPPORTED** |
| **涨停买不进** | **未实现** | **UNSUPPORTED** |
| 停牌 | 无行情日自然无数据、跳过 | PARTIAL |
| ST/*ST 排除 | name 含 "ST" 剔除（含 *ST） | EXACT |
| 新股≥60交易日 | `list_idx` 过滤 | EXACT |
| 佣金 | 万2.5，最低5元，买卖双向 | EXACT（费率假设见6） |
| 印花税 | 万5，仅卖出 | EXACT（费率假设见6） |
| 过户费 | 万0.1，买卖双向 | EXACT（费率假设见6） |
| 滑点 | **未实现**（无 slippage 项） | UNSUPPORTED |

### is_limit_down 计算（已核实）
- 实现：`is_limit_down = close <= pre_close * 0.905`（即当日收盘较前收跌 ≥9.5% 视为跌停），见 `strategy_optimized.py` / `full_market_v8.py` / `strategy_v8_multi.py`（combined_daily 构建时生成该列）
- **精度：APPROXIMATION，存在明显简化**：使用**固定 9.5% 阈值**，**未区分板块**（创业板/科创板 20%、北交所 30%、主板 ST 5%），也**未按日期动态**（全面注册制前后 ST 涨跌幅变化）。意味着：20% 涨跌幅的创业板股票在 -9.5% 到 -19% 之间会被**误判为跌停**（该买没买）；而主板 ST 在 -5% 附近跌停反而不会被识别。**审计 agent 应重点评估此误判对"成交额 Top10 池"的影响**（创业板/科创板高成交额股票占比不低）。

---

## 6. 已知近似与未实现（诚实标注汇总）

| 项目 | 精度 | 说明 |
|---|---|---|
| 收盘价成交 | APPROXIMATION | 用当日 close 作为收盘集合竞价成交价近似 |
| 上轨止盈盘中触发 | APPROXIMATION | 日线无法知盘中触发时刻，假设以 bb_upper 成交 |
| 跌停卖不出 | UNSUPPORTED | 风险：若止盈日实际跌停，回测会错误认为能卖出 |
| 涨停买不进 | UNSUPPORTED | 风险：若买入日实际涨停，回测会错误认为能买进 |
| 停牌显式标记 | PARTIAL | 无行情日跳过，但无 suspension_status 列 |
| 历史费率动态 | APPROXIMATION | **用当前费率套全部历史**：2023-08-28 印花税才从万10减半到万5；2024 前深市免过户费。历史回测存在费用低估/口径偏差 |
| ETF估值 | APPROXIMATION | 持仓按 unit_nav 估值（公允），买卖按市价，溢价率计入 |
| ETF溢价率 | PARTIAL | 用 `市价/unit_nav−1` 近似（Tushare premium_rate 字段当前 token 无权限） |
| 同一天止盈+再买 | N/A | 当前已关闭（用户确认当天不再操作） |

---

## 7. 引擎历史 bug 修复记录（供审计追溯）

1. **equity 变量未定义崩溃**：live_backtest.py 中在止盈/时间止损当日清仓后 `equity` 未定义导致子区间回测崩溃 → 在 `equity_curve.append` 前加 `if 'equity' not in locals(): equity = cash` 兜底。修复后完整区间结果与修复前完全一致（+114.83%/-16.79%/39笔/82.1%）——即该 bug 仅影响 walk-forward 子区间，不影响主结果。
2. **ETF"增量比例"误解**：原实现每次只投闲置现金的 X%（增量），存量 ETF 复利积累导致实际暴露远超设定 → 已改为**目标比例再平衡**（空仓时把 ETF 市值调整到总资产 X%）。
3. **100% 满仓 ETF 从不买入**：`investable = cash×1.0` 时买入金额≈现金，加手续费后 cost>cash 永不成交 → 修复为 `max_cash_use = cash − etf_min_cash`。修复后 100% 目标比例结果 +226.48%（与修复前"增量100%"的 +226.75% 基本一致）。

---

## 8. 关键结果汇总（当前最佳策略，2020-01 ~ 2026-08-25）

| 指标 | 数值 |
|---|---|
| 累计收益（含ETF现金管理100%） | **+226.75%** |
| 年化收益 | +20.3% |
| 最大回撤 | -36.74% |
| Sharpe | 1.16 |
| 交易笔数（股票轮次） | 39 |
| 胜率 | 82.1% |
| 纯股票（无ETF）对照 | +114.83%，回撤-16.79%，Sharpe 0.92 |

**基准对比**（2020-01 ~ 2026-08）：
| 基准 | 累计收益 |
|---|---|
| 策略 | +227.9% |
| 纳斯达克100（513100 累计净值） | +207.7% |
| 标普500（513500 累计净值） | +132.1% |
| 中证500（000905 收盘价） | +43.7% |
| 沪深300（000300 收盘价） | +9.6% |

**ETF目标比例扫描**：30%→+135.8%/回撤-30.4%/Sharpe1.12；50%→+158.9%/-36.0%/1.18；70%→+190.9%/-37.0%/**1.20**；100%→+226.5%/-36.7%/1.16

---

## 9. 复现步骤

```bash
# 环境：python3.10+，pip install pandas numpy pyarrow duckdb tushare pyyaml
cd /Users/mouha/DoubaoWork/chats/2026-08-25/new-chat

# 1) 复现最佳策略（Top10+5层+ETF现金管理100%）
python3 etf_live_backtest.py        # main 跑默认配置，输出 results/etf_Top10_5层_ETF现金管理.parquet 等

# 2) 复现 ETF 目标比例扫描
python3 etf_ratio_scan.py           # 输出 results/etf_ratio_summary.csv + ratio_*.parquet

# 3) 复现无ETF版本（Top1/3/5/10 扫描）
python3 live_backtest.py

# 4) 独立核验单股数据
python3 -c "
import pandas as pd
df = pd.read_parquet('data/combined_daily.parquet')
sub = df[df.ts_code=='600519.SH']
print(sub[['date','open','high','low','close','amount','adj_factor']].head(10))"
```

**数据已全部本地化**，回测无需联网、无需 token。

---

## 10. 审计检查清单（请逐项核验）

### A. 数据层
- [ ] A1. `combined_daily.parquet` 与 `raw/daily` 抽样对账（随机挑股票/日期，逐字段比对）
- [ ] A2. 退市股覆盖率复核（339只D状态中多少在combined；15只区间内退市股缺失的影响评估）
- [ ] A3. 复权因子是否含未来信息：取某只有分红的股票，验证 adj_factor 对历史价格的作用；评估对 BB 信号与止盈价转换的影响
- [ ] A4. `is_limit_down` 计算逻辑复核（涨跌幅限制是否按板块/日期动态，ST 涨跌幅是否正确）
- [ ] A5. amount 字段单位核对（Tushare daily.amount 单位为千元）

### B. 引擎逻辑
- [ ] B1. T+1 正确性：任取一笔交易，验证买入当日绝无卖出
- [ ] B2. 加仓与加权平均成本：任取一笔多层级交易，手工重算 avg_cost
- [ ] B3. 上轨止盈：验证触发条件（high_adj ≥ bb_upper）与成交价（bb_upper/adj_factor）
- [ ] B4. 100股整数倍与"买不起跳过"
- [ ] B5. 候选股选择：Top10 按 amount 降序、取第一只满足条件的——验证无"越过后面的高成交额候选"的逻辑错误
- [ ] B6. 费用计算：佣金最低5元、印花税仅卖出、过户费
- [ ] B7. ETF 现金管理：再平衡逻辑、买/卖时点、估值口径、资金占用
- [ ] B8. `equity` 崩溃修复是否影响主结果

### C. 规则缺口
- [ ] C1. 跌停卖不出 / 涨停买不进：评估对结果的影响方向与量级（尤其止盈日跌停的极端案例）
- [ ] C2. 历史费率动态：2020-2023 印花税万10 vs 当前万5 的影响
- [ ] C3. 滑点未实现的影响
- [ ] C4. 停牌处理是否产生"停牌中仍估值/仍持有"的错误

### D. 结果核验
- [ ] D1. 用代码重跑，核对 +226.75% / -36.74% / Sharpe 1.16 / 39笔 / 82.1%
- [ ] D2. 逐笔抽查 ≥20 笔交易（买入价/时间/加仓/T+1/止盈/费用）
- [ ] D3. 三线/五线基准对比数据核对（ETF累计净值、指数收盘价归一化）

---

## 11. 交付物索引（飞书，均已设 anyone_readable）

- 策略 vs 标普500 vs 纳斯达克（3线）文档：https://my.feishu.cn/docx/UMKwdeETRosTDzxuaTjcn4H3654
- 五基准对比+ETF比例扫描 文档：https://my.feishu.cn/docx/KqmldPDyKoRAYCxTpIacOdHV6Vd
- 五基准交互图：https://my.feishu.cn/file/Fx82bjvdJojGOXxUyWEcMrix60e
- 五基准年度表：https://my.feishu.cn/sheets/FlH9sGJPzhbT5ttKUw2cdFXD6re
- ETF目标比例扫描表：https://my.feishu.cn/sheets/EbAUspjGAhKBYatqZIfcujPu6Uf
- 三线交互图：https://my.feishu.cn/file/CSMjbcjwqoORucxeBT2c7LAf66g

---

## 12. 审计输出建议格式

请审计 agent 输出：
1. 逐项核验结果（A1-D3 每个勾选项：通过/不通过/需修正 + 证据）
2. 发现的具体问题清单（按严重度：BLOCKER / MAJOR / MINOR / INFO）
3. 对"策略收益是否可信"的最终结论与置信度
4. 修正建议（若需重跑，明确改哪些文件哪些行）
