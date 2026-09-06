# 历史引擎语义重建 — LIVECASE-A3（566db88）

本文档从 566db88 检出版本的 `run_strict_c.py` / `run_strict_c_math.py` / `round51/round51_audit.py` 实际代码重建，**不是凭当前引擎猜测**。

## 1. 数据层

- 行情源：`data/combined_daily.parquet`（2020 前 ~ 2026-08-25 全历史 A 股日线，raw OHLC + 复权因子）。
- 数据字典 `D[date]`：`close`=raw close、`close_adj`=raw×当日 adj_factor、`adj`（复权因子字段名）、`bb_upper/bb_lower`（前复权口径 0.01 级）、`limit_down_px`、`is_limit`、`pos[ts_code]`=行情行号；`days` 为 pandas.Timestamp 列表。
- 股票池过滤：`prepare_v51(limit_down_mode='correct', st_mode='pit')`——PIT 口径剔除 ST、上市不足 60 天（round51 语义），BB 需要 20 日 warmup。

## 2. 入场语义

- signal：T 收盘 `close_adj < bb_lower` 且非一字跌停 → 进入 pending。
- 成交：T+1 日 `open × (1 + slippage_bp/10000)`，slippage_bp=10。
- 排名：候选按当日 `amount` 降序取 Top10。
- K=3：同时最多持有 3 只股票（新入场额度上限）。
- 加仓 ADD_ON：T 收盘再次满足 `close_adj < bb_lower`；单层预算 20 万；距上次同股动作 ≥1 交易日；层数上限 5；需要现金足够。
- 现金：初始 1,000,000；佣金 0.025%（最低 5 元）+ 过户费 0.001%；印花税按 historical 规则；滑点 10bp；100 股整数手。
- ETF 腿：`etf_enabled=True`，事件驱动，与股票共享现金池。

## 3. 退出语义（STRICT_C 动态盘中 touch）

- 动态上轨：`Upper(P) = mean(x1..x19, P) + 2 × sample_sd(x1..x19, P)`，ddof=1。
- 解析根：`5339·P² − 562·S·P + (99·S² − 1600·T) = 0`，取大根；S=Σxᵢ、T=Σxᵢ²。
- **566 版（P0 修正前）**：`xᵢ = 最近19日 close_raw × adj[T]` —— 19 个历史 raw close **全部乘 T 当日复权因子**（这是后来被 8c479f6 判定为错误并修正的口径）。
- 触发：`high_adj ≥ P*_adj`（adjusted 口径直接比较）。
- 成交：T+1 卖出（持有时自 entry 次日起）；跌停顺延；FINAL_SETTLE 末日 close 清仓。
- 无 tick 双边界（566 版）；`slip_first`（先乘滑点，再判跌停）——FIX2 后来改为 `ref_first`。

## 4. 与当前引擎（8c479f6+）的组件级 diff

见 `results/evidence/livecase_a3/historical_vs_current_engine_diff.csv`。核心三点：

1. **P0**：P* 输入序列口径（raw19×adj[T] → 各日 close_adj[k]）；这是 5 笔退出日变更 + 组合路径全部下游差异的唯一根因。
2. **P1**：可执行价 tick 修正（P*_raw 向下取整到 0.01 + 双边界保守判定）。
3. **FIX2**：跌停判定顺序（ref_first）。

## 5. 复现验证

- 566db88 引擎 + 当前数据 → 96 笔，与 frozen blob 逐字节一致（SHA256 `76f401fd...`）。
- 8c479f6 引擎 + 当前数据 → 97 笔（strict_c_corr_trades.csv）；当前 HEAD 引擎复跑 → 97/97 与其零差异。
- 因此：frozen96 与 current97 的差异 = 代码版本（P0/P1/FIX2），不是数据。
