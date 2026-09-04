# E2 Gate 1B — Ranking Variable Audit

## E1 Frozen Ranking Variable

从 E1 代码 (`research/etf/e1_model1_backtest.py`) 读取：

```python
panel = rep.sort_values(['date', 'amount'], ascending=[True, False]).copy()
sig_rows = g[g['signal'] & (g['amount'] > 0)].head(TOP_N)
```

**E1 ranking variable = amount（日成交额/流动性），降序排列，取 Top 10。**

不是 BB_Z，不是 signal depth，不是其他 score。

## E1.1 Top-N Information Content Audit

E1.1 (`e11_failure_mechanism_audit.py`) 的 Top-N info content 分析：
- 同样使用 amount 排序选取 Top-10
- 比较 selected Top-10 vs non-selected 信号的固定 horizon 前向收益
- 结果：在 1/3/5/10/20 天所有 horizon 上，selected vs non-selected 收益差异 < 0.12%，方向不一致

## 修正后的表述

**正确表述**：amount-based Top-N 排序在 ETF 信号日表现出很弱的前向收益区分度。

**不能泛化为**："Top-N ranking has no information" 或 "BB_Z ranking has no information"。

BB_Z 排序在 E1/E1.1 中**未被测试**。如果未来需要测试 BB_Z ranking 的信息含量，需独立预注册。

## E2 Entry Side

E2 必须保持 E1 冻结的 entry/ranking 逻辑不变：
- Ranking variable = amount（成交额）
- Top-N = 10
- Signal = close < bb_lower (Model1) / index close < bb_lower (Model2)
- Execution = T+1 open

E2 只修改 exit side（upper/STRICT_C → first BB midline touch）。
