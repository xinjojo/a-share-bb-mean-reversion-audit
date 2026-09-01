# A股 BB 均值回归策略 — 完整交易系统（按步骤全流程）

> 版本：最终冻结版（Round4 审计后，2026-09-01 起参数冻结）
> 引擎：`experiment_fast.py`（与 `etf_live_backtest.py` 主引擎逐位一致，仅 numpy 加速）
> 数据：Tushare，2020-01-02 ~ 2026-08-31，7,731,551 行 / 5,725 只
> 精度标注：**EXACT**=完全按真实规则 / **APPROXIMATION**=日线近似 / **UNSUPPORTED**=无法模拟

---

## 第 0 步 · 系统总览

```
数据下载(Tushare) → 本地Parquet仓库 → 预处理(复权/BB/涨跌停) → 每日交易循环
    → 信号(Top10+BB下轨) → 执行(收盘价) → 持仓管理(加仓/止盈/T+1) → ETF现金管理
    → 交易明细/权益曲线 → 绩效统计 → 审计/盲测
```

---

## 第 1 步 · 数据层

### 1.1 数据源与文件
| 文件 | 内容 | 来源 |
|---|---|---|
| `data/combined_daily.parquet` | 全A日线：date/ts_code/open/high/low/close/pre_close/vol/amount/adj_factor | Tushare `daily` + `adj_factor` |
| `data/raw/stock_basic.parquet` | 股票基础信息：name/list_date/delist_date/list_status | Tushare `stock_basic` |
| `data/etf_513500_merged.parquet` | 标普500ETF：close + unit_nav + premium | Tushare |

**amount 单位 = 千元**（Tushare 标准，排序时只比相对大小，不影响 TopN 选择）。

### 1.2 预处理（`prepare_fast`）
| 步骤 | 操作 | 精度 |
|---|---|---|
| 1.2.1 | 合并 name → `is_st = name含"ST"`（含\*ST） | **EXACT** |
| 1.2.2 | **复权**：`close_adj = close × adj_factor`，`high_adj = high × adj_factor`（adj_factor 为 Tushare 累计复权因子，PIT 已审计 signal_diff=0） | **EXACT** |
| 1.2.3 | **布林带**（按股票分组、rolling、仅用当日及之前数据）：`ma = rolling(close_adj, 20).mean()`；`sd = rolling(close_adj, 20).std()`；`bb_lower = ma − 2×sd`；`bb_upper = ma + 2×sd`（前19日 NaN，不产生信号） | **EXACT** |
| 1.2.4 | **涨跌停判定**（correct口径）：主板10%、创业板/科创板20%（创业板2020-08-24前10%）、ST 5%；`is_limit_down = close ≤ round(pre_close×(1−pct), 2)` | **EXACT** |
| 1.2.5 | **一字板标记**：`open==high==low==close` | **EXACT** |
| 1.2.6 | **上市天数索引**：`listing[ts_code] = 首次出现在数据的日索引` | **EXACT** |

---

## 第 2 步 · 每日交易循环（核心，逐日执行）

对每个交易日 `d`（i = 日索引，0 起）：

### 2.1 开盘执行（仅 next_open 模式）
> 当前最终版用 **close 模式**，此分支不触发。审计中测试过 next_open（T日收盘信号→T+1开盘成交，+233.0% 略高，已记录在案）。

### 2.2 持仓处理（当前持有一只股票时）
取当日该股数据，`hold_days = i − entry_day_idx`。

**① 止盈判断**（第1优先级）：
```
hold_days ≥ 1 且 high_adj ≥ bb_upper 且 当日非跌停
→ 全仓卖出
→ 成交价 sell_price = (bb_upper / adj_factor) × (1 − 滑点)
```
| 要素 | 说明 | 精度 |
|---|---|---|
| T+1 | `hold_days ≥ 1`（当日买入不可卖） | **EXACT** |
| 触发 | 盘中最高复权价触及布林上轨 | **EXACT**（用high） |
| 成交价 | 以 `bb_upper` 折算的实际价成交 | **APPROXIMATION**（日线不知盘中真实成交，实际可能高于上轨或在更高/更低位成交；这是日线级别的止盈成交近似） |

**② 时间止损**（当前**禁用**，`time_stop_days=None`）：保留接口，可配置 N 日未止盈则收盘卖出。

**③ 加仓判断**（未止盈、未止损时）：
```
close_adj < bb_lower 且 当日非跌停 且 当前层数 < 5
且 非一字涨停（成交约束开时）
→ 再加一层 20万
```
| 要素 | 说明 | 精度 |
|---|---|---|
| 层数 | 第1次=20%，第5次=100%（共5层） | **EXACT** |
| 成交价 | close × (1+滑点) | **APPROXIMATION**（收盘价成交） |
| 加仓后成本 | `avg_cost = (旧shares×旧avg_cost + 新增金额+手续费) / 新shares` | **EXACT**（含费加权） |

**④ 停牌处理**：持仓股当日无行（停牌）→ 不交易，`stock_val = shares × 最近收盘价`（用 last_close）。 | **EXACT**

### 2.3 空仓买入（当前无持仓且今日未卖出时）
```
① 候选池：上市≥60交易日 且 非ST
② 按当日 amount 从大到小排序，取前 top_n=10
③ 在Top10中找第一个：close_adj < bb_lower 且 非跌停（且非一字涨停若开约束）
④ 找到 → 买入首层 20万（收盘价 close × (1+滑点)，100股整数倍）
⑤ 没找到 → 当日空仓，进入ETF管理
```
| 要素 | 说明 | 精度 |
|---|---|---|
| 成交额Top10 | 当日真实 amount（非市值/成交量/换手） | **EXACT** |
| 排序时点 | T日收盘后确定，T日收盘价成交——收盘后交易窗口近似 | **APPROXIMATION** |
| 最小单位 | 100股整数倍；若20万买不足100股则不成交 | **EXACT** |
| 跌停过滤 | 收盘跌停不买 | **EXACT** |
| 资金不足 | 现金不足时买入 `min(level_cash, cash)`，不足100股则放弃 | **EXACT** |

### 2.4 ETF 现金管理（空仓期）
```
目标 = 总资产 × 100%（etf_ratio=1.0）
持仓不足 → 买入513500（按 close 市价，unit_nav 估值权益）
持仓超出 → 卖出513500
买入股票需现金 → ensure_cash 自动卖ETF凑钱
```
| 要素 | 说明 | 精度 |
|---|---|---|
| 估值 | 权益按 unit_nav（单位净值）计 | **EXACT**（审计已用 accum_nav 校正基准） |
| 成交 | 按 close 市价，含佣金 | **APPROXIMATION**（按收盘价成交） |

### 2.5 权益记录
`equity = cash + 股票市值(shares×close) + ETF市值(shares×unit_nav)` → 每日写入 equity_curve。

---

## 第 3 步 · 费用模型（全参数化）

| 费用 | 规则 | 参数 | 精度 |
|---|---|---|---|
| 佣金 | `max(成交额×0.00025, 5元)`（**最低佣金5元**） | COMMISSION_RATE=0.00025, MIN=5 | **EXACT** |
| 印花税 | 仅卖出：`成交额×0.0005`（2023-08-28后）/ `×0.001`（前，历史模式） | STAMP_TAX | **EXACT** |
| 过户费 | `成交额×0.00001`（买卖均收） | TRANSFER_FEE | **EXACT** |
| 滑点 | 买入×(1+slip)、卖出×(1−slip)，默认0bp | slippage_bp | **EXACT**（可配） |
| ETF费用 | 仅佣金 `max(×0.00025, 5)` | — | **EXACT** |

---

## 第 4 步 · 关键交易规则汇总

| 规则 | 实现 | 精度 |
|---|---|---|
| T+1 | `hold_days≥1` 才可卖；当天买入+加仓份额统一持仓，卖出时全部可卖（每批不单独计T+1，但整体持仓自首日+1起可卖） | **EXACT** |
| 单持仓 | 同时最多1只；清仓后才重新扫描Top10 | **EXACT** |
| 加仓上限 | 最多5层（第5层=100%），第5层后禁止再加 | **EXACT** |
| 止盈 | 高≥布林上轨→全出；止盈后当日收盘若再出信号→重新买回第1层 | **EXACT**（同日止盈+重买支持） |
| 止损 | 当前无硬止损（参数化接口保留：fixed_percent/ATR/close_below_MA/time_stop） | — |
| 涨跌停 | 跌停不买；止盈日跌停不卖（约束开）；审计验证本策略路径0次触发 | **EXACT** |
| ST | 默认排除，参数化可开 | **EXACT** |
| 新股 | 上市满60交易日 | **EXACT** |
| 复权 | 信号用 adj_close（前复权口径一致）；成交用实际价=adj价/adj_factor | **EXACT**（PIT已验证） |

---

## 第 5 步 · 输出

### 5.1 权益曲线（equity_curve）
每日：date / equity / cash / stock_val / etf_val / etf_shares / holding

### 5.2 交易明细（trades）
每笔：round / ts_code / name / entry_date / exit_date / exit_type(TAKE_PROFIT_UB|TIME_STOP|FINAL_SETTLE) / levels_used / shares / pnl / return_pct / hold_days

### 5.3 绩效统计（stats）
累计收益 / 年化 / 最大回撤 / Sharpe / 交易数 / 胜率

---

## 第 6 步 · 基准与审计对照

| 指标 | 值（asof 2026-08-31） |
|---|---|
| 组合累计（含ETF现金管理） | **+226.48%** |
| 股票核心（剥离ETF） | **+114.83%** |
| 交易笔数 | 39 |
| 胜率 | 82.1% |
| 最大回撤（组合） | -37.63% |
| Sharpe（组合） | 1.16 |
| 盲测状态 | 2026-09-01 起未知数据，每月自动记录 |

---

## 精度声明（必须明确）

- **EXACT**：成交额Top10排序、BB信号、T+1、100股最小单位、费用（含最低佣金）、上市天数、ST过滤、跌停过滤、加权成本含费、单持仓约束、ETF unit_nav估值。
- **APPROXIMATION**：①收盘价成交（T日信号→T日收盘成交，模拟收盘后交易窗口，审计对比 next_open 后确认此假设偏保守）；②止盈以布林上轨折算价成交（日线无法知盘中真实成交）；③ETF按收盘价成交；④一字板/极端跳空的成交可行性按收盘价近似（本策略39笔路径上从未遇到）。
- **UNSUPPORTED**：盘中分时价格、真实集合竞价、逐笔成交、盘中精确触发时刻（若未来接入1分钟数据可升级）。

> 所有无法精确模拟之处均已在此明示，不隐藏任何假设。
