# etf_live_backtest.py 代码调用链（行号级）

> 供审计对照使用。版本：2026-09-01 当前文件。
> 全部行号对应 `etf_live_backtest.py` 实际源码。
> 核心关注：**T 日什么时候知道什么信息 → 什么时候产生信号 → 以什么价格成交 → 什么时候计入持仓 → 什么时候允许卖出**。

---

## 0. 整体架构

```
main (L356-378)
 ├─ prepare_data()      L38-55   数据加载+后复权+布林带计算
 ├─ prepare_etf_data()  L58-64   ETF 行情加载
 └─ run_backtest()      L67-311  主回测循环（逐交易日）
     ├─ calc_fee_buy()  L25-26   买入费用（佣金+过户费）
     ├─ calc_fee_sell() L29-30   卖出费用（佣金+印花税+过户费）
     ├─ calc_fee_etf()  L33-34   ETF 费用（仅佣金）
     ├─ ensure_cash_needed() L98-119  现金不足→卖ETF补足
     ├─ 持仓处理块      L123-191
     │   ├─ 上轨止盈     L129-146
     │   ├─ 时间止损     L147-164（可选）
     │   └─ 加仓         L165-181
     ├─ 空仓扫描买入    L193-223
     ├─ ETF再平衡       L225-263
     └─ 估值入账        L265-271
 └─ calc_stats()        L314-353 绩效统计
```

---

## 1. 数据准备阶段（一次性，L38-64）

### prepare_data() — L38-55
| 行 | 动作 | 说明 |
|---|---|---|
| L39 | `pd.read_parquet('data/combined_daily.parquet')` | 770万行日线：date/ts_code/open/high/low/close/vol/amount/pre_close/adj_factor/is_limit_down/is_red |
| L40 | 读 `stock_basic.parquet` | 5889只（含退市D） |
| L41 | merge name/market | 得到股票名称与板块 |
| L47 | `is_st = name.str.contains('ST')` | **ST/*ST 排除依据**（含"ST"即排除） |
| L48 | `close_adj = close × adj_factor` | **后复权**收盘价（指标用） |
| L49 | `high_adj = high × adj_factor` | 后复权最高价（止盈判断用） |
| L50-53 | `groupby(ts_code).rolling(20).mean()/.std()` | ma20/std20 → `bb_lower=ma20-2σ`、`bb_upper=ma20+2σ` |
| L43-44 | `BT_START`/`BT_END` 环境变量切片 | 默认 2020-01-01 ~ 2026-08-25 |

### prepare_etf_data() — L58-64
| 行 | 动作 | 说明 |
|---|---|---|
| L60 | 读 `etf_513500_merged.parquet` | close(市价) + unit_nav(单位净值) |
| L63 | `unit_nav.ffill()` | 净值缺失用前值近似 |

### 费用函数 — L25-35
| 行 | 公式 |
|---|---|
| L25-26 | 买入费 `max(amount×0.00025, 5) + amount×0.00001`（佣金万2.5最低5元 + 过户费万0.1） |
| L29-30 | 卖出费 `max(amount×0.00025, 5) + amount×0.0005 + amount×0.00001`（+印花税万5） |
| L33-34 | ETF费 `max(amount×0.00025, 5)`（无印花税/过户费） |

---

## 2. 主回测循环 run_backtest() — L67-311

### 2.0 初始化 — L71-87
| 行 | 内容 |
|---|---|
| L71-72 | `days` 交易日排序；`day_index` 日期→索引 |
| L73-74 | `listing_ok`/`list_idx`：每只股票首个交易日索引（**新股≥60交易日过滤依据**，L198 用） |
| L76-83 | cash=100万、pos=None、etf_shares=0、equity_curve/trades/etf_log 列表、round_no=0、last_close={} |
| L85-87 | `daily` = 按日分组的 DataFrame 字典 |

### 2.1 每日循环体 — L89
`for i, d in enumerate(days):`

### 2.2 当日ETF行情 — L92-96
| 行 | 内容 |
|---|---|
| L92-94 | d 在 etf.index 中 → etf_px=close, etf_nav=unit_nav |
| L95-96 | 否则 np.nan（ETF无交易日） |

### 2.3 ensure_cash_needed(need) 闭包 — L98-119
> 任何买入前调用：现金不足时卖出 ETF 补足到目标金额。
| 行 | 逻辑 |
|---|---|
| L101 | 若 cash≥need 或未开ETF或无ETF份额或无行情 → 直接返回 |
| L103-104 | `shortfall = need - cash`；`sell_val = shortfall×1.02`（**2%缓冲覆盖费用**） |
| L105 | `sell_qty = ceil(sell_val/etf_px/100)×100`（100份整数倍） |
| L106 | `min(sell_qty, etf_shares)` 防超卖 |
| L108-119 | 卖出：按市价 close 成交，`fee=calc_fee_etf`，`proceeds=amount-fee`，记 etf_log |

### 2.4 持仓处理块 — L123-191（T日持仓股）
| 行 | 步骤 | 触发条件 | 成交价 | 备注 |
|---|---|---|---|---|
| L128 | `hold_days = i - entry_day_idx` | — | — | **T+1 依据** |
| L129-146 | **上轨止盈** | `hold_days≥1` 且 `high_adj ≥ bb_upper` | `sell_price = bb_upper/adj_factor`（L130，转实际价） | 全部卖出；记 trades `exit_type=TAKE_PROFIT_UB`；cash+=proceeds；pos=None；round_no+=1；`sold_today=True` |
| L147-164 | **时间止损**（可选） | `time_stop_days` 非空且 `hold_days≥N` | `sell_price = close`（L148） | 收盘价清仓；`exit_type=TIME_STOP`；sold_today=True |
| L165-181 | **加仓** | `close_adj<bb_lower` 且 `非is_limit_down` 且 `levels<max_levels(5)` | `buy_price=close`（L170） | `ensure_cash_needed(level_cash)`→`qty=int(min(level_cash,cash)/price/100)×100`；`cost_add=amount+fee`；**重算 avg_cost=(old_shares×avg_cost+cost_add)/new_shares**（L178）；total_cost+=cost_add；levels+=1 |
| L182-186 | 持仓市值 | — | `pos_value=shares×close` | stock_val=持仓市值 |
| L187-189 | 停牌兜底 | 当日无该股行情 | `last_close`（前收） | 用上次收盘估值（**停牌期间估值近似**） |

> **优先级**：先止盈(L129) → 后时间止损(L147) → 后加仓(L165)。同一天只走第一个命中的分支。

### 2.5 空仓扫描买入块 — L193-223（T日空仓）
| 行 | 步骤 | 条件 | 说明 |
|---|---|---|---|
| L194 | `if pos is None and not sold_today` | — | **止盈/止损当日不再买入**（用户确认的规则） |
| L195-198 | 股票池过滤 | `~is_st`（非ST）且 `(i-list_idx)≥60`（上市满60交易日） | 当日全部符合的股票 |
| L200 | `top = pool.nlargest(top_n, 'amount')` | — | **按当日成交额 amount 降序取 Top10** |
| L201-206 | 遍历 top 选候选 | `close_adj<bb_lower` 且 `非is_limit_down` | **取第一只满足的**（按成交额从大到小顺序） |
| L207-222 | 买入 | — | `ensure_cash_needed(level_cash)` → `qty=int(min(level_cash,cash)/price/100)×100`（100股整数倍，不足100跳过）；`buy_price=close`；`cost_add=amount+fee`；pos 初始化（avg_cost=cost_add/qty, levels=1, entry_day_idx=i） |

### 2.6 ETF 目标比例再平衡 — L225-263（空仓时）
| 行 | 逻辑 |
|---|---|
| L227 | `etf_val = etf_shares × unit_nav`（按净值估值） |
| L228-231 | `target_val = (cash+etf_val) × etf_ratio`（默认1.0=100%）；`diff = target_val - etf_val` |
| L232-247 | diff>0 且现金够 → 买入：`max_cash_use=cash-etf_min_cash`，`qty=int(min(diff,max_cash_use)/etf_px/100)×100`；按市价 close 成交；`etf_val+=qty×unit_nav` |
| L248-263 | diff<0 且持有 → 卖出超出部分：按市价 close 成交 |

### 2.7 估值入账 — L265-271
| 行 | 逻辑 |
|---|---|
| L265-267 | `etf_val = etf_shares×unit_nav`（重算）；`equity = cash + stock_val + etf_val` |
| L268-271 | append equity_curve：date/equity/cash/stock_val/etf_val/etf_shares/holding |

### 2.8 期末清仓 — L273-306（最后交易日）
| 行 | 内容 |
|---|---|
| L274-291 | 股票仍持有 → `FINAL_SETTLE`，按最后收盘 close 卖出 |
| L292-306 | ETF 仍持有 → `FINAL_ETF`，按最后市价 close 卖出 |

### 2.9 返回 — L308-311
`eq`(净值曲线)、`tr`(股票交易)、`etf_df`(ETF日志)

---

## 3. 绩效统计 calc_stats() — L314-353
| 行 | 指标 |
|---|---|
| L316 | ret = equity.pct_change() |
| L317-319 | 总收益、年化（252交易日/年） |
| L320-322 | 最大回撤（cummax 基准） |
| L323-324 | 年化波动、Sharpe |
| L325-327 | 股票利用率 / ETF利用率 / 总资金利用率 |
| L328-332 | 交易次数、胜率、平均盈亏、ProfitFactor |
| L333-336 | 分年度收益 |
| L337-353 | 汇总 dict |

---

## 4. main 入口 — L356-378
| 行 | 动作 |
|---|---|
| L356-361 | prepare_data + prepare_etf_data |
| L363-366 | 两个配置：`Top10_5层_ETF现金管理`(etf_enabled=True)、`Top10_5层_无ETF基准`(etf_enabled=False) |
| L368-377 | 循环 run_backtest → calc_stats → 保存 parquet/csv |

---

## 5. T 日信息流时序（审计核心）

```
[T日 盘中]
  持有 → 用 T日 high_adj 判断上轨止盈 (L129)  ← 盘中才知道 High
        → 命中则按 bb_upper/adj_factor 成交 (L130)  [APPROXIMATION: 假设触及即成交]

[T日 收盘后]  ← 此时才知道 close / amount / bb_lower
  持有 → 用 T日 close_adj 判断是否加仓 (L165)
  空仓 → 用 T日 amount 取 Top10 (L200) → 用 T日 close_adj 判断下轨 (L203) → 按 close 买入 (L209)
        → 买入记 entry_day_idx=i，当日不可卖 (T+1, L128/L129)
  空仓 → ETF 再平衡 (L228)

[T日 收盘后] 估值入账 (L265-271)

[T+1日 盘中] 首次可卖 (hold_days≥1)
```

**关键审计点（已自查标注）**：
1. **收盘价成交假设**（L209/L170）：用当日 close 近似"收盘集合竞价买入"，实际收盘后才知道 close → 属于收盘后执行，**无未来函数**（APPROXIMATION）。
2. **上轨止盈盘中触发**（L129-130）：日线无法知盘中触发时刻，假设以 bb_upper 成交 → **APPROXIMATION**，且**未检查当日是否跌停卖不出**（UNSUPPORTED）。
3. **T+1**（L128/L129）：`hold_days≥1` 才允许卖，**当日买入绝无当日卖出** ✓ EXACT。
4. **加仓后加权成本**（L178）：`(old_shares×avg_cost+cost_add)/new_shares`，含费用 ✓ EXACT。
5. **跌停判定**（is_limit_down）：数据列来自构建脚本 `close<=pre_close×0.905` 固定阈值，**未区分板块/ST** → APPROXIMATION（见 AUDIT_GUIDE §5）。
6. **复权因子**：`close_adj=close×adj_factor` 为"截至最新"后复权因子，**含未来分红送转信息** → 需审计（见 AUDIT_GUIDE §4.5）。
7. **止盈当日不再买入**（L194 `not sold_today`）：用户明确规则，防同日循环。
8. **停牌估值**（L187-189）：用 last_close 估值，停牌日不交易 ✓ PARTIAL。
