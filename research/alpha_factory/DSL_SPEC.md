# A-SHARE ALPHA FACTORY — Factor DSL 规格

## 1. 设计原则

- 禁止 LLM / 任意代码直接执行 Python 表达式。
- 所有因子表达式必须先过：DSL parser → operator 白名单 → lookback 白名单 → PIT validator → complexity validator，才能进入计算。
- 目标：可审计、可复算、可 canonical 化、可防换皮。

## 2. 语法

```
<expr>   := <input> | <op>(<args>)
<args>   := 逗号分隔的 <expr> 或 <int>（lookback 参数）
<input>  := 白名单输入字段名（见 §4）
```

示例：
```
ret_5
ratio(ret_5, atr14_pct)
ts_zscore(close, 20)
interaction(bb_z, log_amount)
delta(close, 5)
rolling_rank(amount, 20)
```

## 3. Operator 白名单

| operator | 语义 | 参数 |
|---|---|---|
| `lag(x,n)` | 滞后 n 期（n>0，禁止负/零） | expr, int |
| `delta(x,n)` | x - lag(x,n) | expr, int |
| `return(x,n)` | x/lag(x,n) - 1 | expr, int |
| `rolling_mean(x,n)` | 滚动均值 | expr, int |
| `rolling_std(x,n)` | 滚动标准差 | expr, int |
| `rolling_min(x,n)` | 滚动最小 | expr, int |
| `rolling_max(x,n)` | 滚动最大 | expr, int |
| `rolling_rank(x,n)` | 滚动百分位排名 | expr, int |
| `ts_zscore(x,n)` | (x - mean)/std 滚动 | expr, int |
| `cs_rank(x)` | 当日横截面排名 | expr |
| `cs_zscore(x)` | 当日横截面 z | expr |
| `ratio(x,y)` | x / y | expr, expr |
| `diff(x,y)` | x - y | expr, expr |
| `corr(x,y,n)` | 滚动相关系数 | expr, expr, int |
| `min(x,y)` | 逐元素最小（交换律） | expr, expr |
| `max(x,y)` | 逐元素最大（交换律） | expr, expr |
| `abs(x)` | 绝对值 | expr |
| `sign(x)` | 符号 | expr |
| `interaction(x,y)` | x * y（交换律） | expr, expr |

**禁止**：`lead`、`future`、负 lag、任何未来窗口。

## 4. 输入字段白名单

### Universe A（BB CONDITIONAL，信号日 PIT）

行情/基本面：
`signal_day_open` `signal_day_high` `signal_day_low` `signal_day_close` `signal_day_amount` `signal_day_volume` `signal_day_adj_factor`

BB 状态：
`bb_z` `bb_mid` `bb_lower` `bb_upper` `BB_width` `distance_to_lower_band`

排名/上市/行业：
`turnover_rank` `listing_age_days` `sector_pit`（分类变量，不直接参与数值算子）

回看窗口聚合（加载器保证 ≤ signal_date）：
`ret_1` `ret_3` `ret_5` `ret_10` `ret_20` `ret_60`
`vol_10` `vol_20` `atr14_pct` `amount_ratio_5_20`
`drawdown_20` `drawdown_60` `distance_52w_high`
`gap_pct` `daily_range_pct`

### Universe B（FULL A-SHARE，接口定义）

`open` `high` `low` `close` `volume` `amount` `adj_factor`
（未来：`market_cap` `float_market_cap` `industry` `index_return` `breadth` 等，接入前必须过 PIT 审核）

## 5. Lookback 白名单

```
1 2 3 5 10 20 40 60 120 250
```
- 所有算子整数参数必须在白名单内。
- 禁止 generator 随机产生 17/23/47/83 等任意参数（降低搜索自由度）。

## 6. Complexity Budget（第一版冻结）

- operator depth ≤ 4（嵌套层数）
- unique inputs ≤ 5（不同输入字段数）
- interaction terms ≤ 2（interaction/ratio/diff/corr 中二元算子总数，不含输入字段本身）

超限 → `REJECT_COMPLEXITY`，并计入实验尝试次数。

## 7. Canonicalization 与 expression_hash

1. 表达式解析为 AST。
2. 规范化：
   - 函数名统一小写；
   - 交换律算子（interaction/min/max）参数按 canonical 串排序；
   - 整数参数规范化为十进制；
   - 去空白、统一括号。
3. `expression_hash = sha256(canonical_string).hexdigest()[:16]`。
4. 例：`ratio(ret_5, atr_20)` 与 `ret_5 / atr_20`（若支持除法语法）→ 同一 hash；`interaction(a,b)` 与 `interaction(b,a)` → 同一 hash。

## 8. PIT / Leakage Guard

- 任何 factor value at date T 只能读取 `source_date <= T`。
- 未来接入财务数据必须使用**实际公告日**，禁止用报告期末日。
- 测试：`test_no_future_operator.py` / `test_negative_lag_forbidden.py` / `test_feature_source_date.py` / `test_label_feature_separation.py` / `test_registry_expression_reproducible.py`。

## 9. Factor Family（标准分类）

`PRICE_REVERSAL` `MOMENTUM` `VOLATILITY` `LIQUIDITY` `VOLUME_PRICE` `GAP` `RANGE` `TREND` `RELATIVE_STRENGTH` `MARKET_CONTEXT` `BREADTH` `INDUSTRY_RELATIVE` `CROSS_SECTIONAL` `BB_CONDITIONAL` `INTERACTION`

未来可加：`FUNDAMENTAL` `ANALYST` `FLOW` `EVENT`（Phase 0 不接未来数据源）。
