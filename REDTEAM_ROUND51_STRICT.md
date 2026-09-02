# REDTEAM_ROUND5_1 — 基础口径封板审计报告

日期：2026-09-02
状态：**Round 5.1 完成**。旧 354.9% 已归档为 INVALID HISTORICAL BACKTEST（含同Bar未来退出信息），本报告不再评价旧基线。

---

## 一、新问题确认表

| 审计发现 | 确认/反驳 | 代码/数据证据 | 影响 |
|---|---|---|---|
| PIT_ST（快照名称污染ST过滤） | **CONFIRMED** | `experiment_fast.py:20-25` 用 `stock_basic.name` 当前快照 + `name.contains('ST')`，无历史状态。已下载 `data/raw/namechange_full.parquet`(8082条/5043只,2010-2026) 重建 PIT 映射。差异：**466,247 股票日 / 683 只**（快照ST但PIT非ST=305,158天即历史摘帽；快照非ST但PIT是ST=161,089天） | 显著，改变收益（见 STRICT_V2） |
| LISTING_60D（切片首日误当上市日） | **CONFIRMED** | `prepare_fast` 用 `listing.setdefault(tc, di)`，di=回测切片首日(2020-01-02)，老股票被误判为上市不足60日。**2020前60交易日：old候选=0 → correct候选=212,080**（下载完整交易日历1990起修复） | 重大，改变收益 |
| ETF_OPEN_RETROACTIVE（15:00信号→09:30 ETF定价） | **CONFIRMED** | `round5_audit.py:110` 单一 `etf_trade_px`（next_open/close_confirm_next 时用 open）覆盖整天所有 ETF 操作 → 收盘后信号却按当日 09:30 open 卖 ETF 筹资，时间倒流 | 重大，STRICT_V1 需作废 |
| ONE_WORD_FUTURE（整日一字板用于09:30判断） | **CONFIRMED** | 引擎用 `one_word = open==high==low==close`（整日结果）判断 T+1 开盘可成交性，但整日一字板收盘后才知道。已改为 `open_fill` 上下界（'limit_conservative' 用开盘价 vs 涨跌停价；'optimistic' 不判成交标 DAILY_DATA_APPROXIMATION） | 中等（Top10 高流动性下两档结果相同） |
| ETF_OPEN_SOURCE（513500 open 数据来源） | **REFUTED（无问题）** | `data/etf_513500.parquet` 为 Tushare `fund_daily` 场内真实行情：open 1614/1614 非空，vol/amount>0 共 1610 行，抽样 2020-06 十天 OHLCV 正常；`unit_nav` 仅末5天有值(1609/1614 NaN) → next_open 用 open 是真实可交易开盘价 | 无 |

---

## 二、STRICT_V2（全部修复后）

引擎：`round51_audit.py`（事件驱动：`ensure_cash_open` 开盘筹资 / `rebalance_close` 收盘再投资；PIT ST；PIT list_date+60交易日；correct 涨跌停；10bp 双腿滑点；历史印花税；ETF market-close 估值；期末清仓同步；100股；T+1；K=3；Top10；BB(20,2)；level_cash=20万；max_levels=5）

| version | total | CAGR | MaxDD | Sharpe | trades | win_rate | 股票PnL |
|---|---|---|---|---|---|---|---|
| STRICT_V2_A（T-1已确定上轨，T日盘中high触发退出） | **+45.12%** | 5.83% | -40.55% | 0.349 | 100 | 68.0% | 184,870 |
| STRICT_V2_A 纯股票(ETF off) | +5.15% | 0.77% | -39.86% | 0.158 | 100 | 70.0% | 51,549 |
| STRICT_V2_B（T日收盘确认 close>=上轨 → T+1 open 卖出） | **+74.43%** | 8.83% | -39.23% | 0.457 | 73 | 63.0% | 150,366 |
| STRICT_V2_B 纯股票(ETF off) | +23.40% | 3.25% | -39.86% | 0.253 | 72 | 62.5% | 234,042 |

注：open_fill 保守/乐观两档结果完全一致（Top10 高流动性股票开盘从未触发一字板约束）。A/B 是两种不同可交易策略，**不得合并**。
STRICT_V1（未修复 PIT ST/listing/ETF 时序）close=62.6%、next_open=84.1% → **均作废**（含 ETF open 倒流 + listing bug）。

### PIT ST 对 STRICT_V2 的影响
- A: pit 45.12% vs snapshot 57.53%（-12.4pp）
- B: pit 74.43% vs snapshot 76.31%（-1.9pp）

### PIT ST 对 Top10/实际交易影响（独立统计）
- 总交易日 1615；Top10 候选池集合差异 **64 天**；Top10 中跌破下轨信号差异 **4 天/4行**；快照 Top10 涉及 539 只 vs PIT 553 只
- STRICT_V2_B 买入 170 笔，其中发生在 PIT/快照 ST 状态差异股票上的 **3 笔**

---

## 三、Alpha 归因

| 口径 | STRICT_V2_A | STRICT_V2_B | ETF buy&hold |
|---|---|---|---|
| 纯股票（无 ETF，资金闲置） | +5.15% | +23.40% | — |
| 组合（股票+ETF永远满仓） | +45.12% | +74.43% | — |
| 全程满仓 ETF 513500（2020-01-02~2026-08-25） | — | — | **+26.59%** |

**关键结论：修复所有已知问题后，股票策略自身收益（A +5.2%、B +23.4%）均未超过"直接满仓持有标普500ETF"（+26.6%）。A 大幅跑输，B 略低于。组合超额收益来自"股票/ETF 动态配置 + 复利交互"，而非股票 Alpha。**

---

## 四、OOS 与分年

### OOS（Train 2020-2023 / Test 2024-2026）

| version | 区间 | total | CAGR | MaxDD | Sharpe | trades | win_rate | 股票PnL |
|---|---|---|---|---|---|---|---|---|
| A 组合 | Train | +34.44% | 7.76% | -27.39% | 0.415 | 65 | 69.2% | 175,468 |
| A 组合 | Test | +15.48% | 5.66% | -28.70% | 0.338 | 37 | 64.9% | **-47,234** |
| A 纯股票 | Train | +12.17% | 2.94% | -27.84% | 0.241 | 65 | 72.3% | 121,724 |
| A 纯股票 | Test | **-11.22%** | -4.45% | -30.01% | -0.025 | 37 | 62.2% | **-112,229** |
| B 组合 | Train | +6.97% | 1.72% | -39.23% | 0.197 | 47 | 63.8% | **-136,050** |
| B 组合 | Test | +65.32% | 21.18% | -24.28% | 0.849 | 28 | 60.7% | 280,881 |
| B 纯股票 | Train | **-5.37%** | -1.39% | -39.86% | 0.075 | 46 | 65.2% | **-53,741** |
| B 纯股票 | Test | +25.39% | 9.03% | -24.30% | 0.465 | 28 | 64.3% | 253,909 |

### 分年（组合口径）

| 年 | A | B |
|---|---|---|
| 2020 | +19.27% | +26.57% |
| 2021 | +21.42% | +6.38% |
| 2022 | -0.40% | -6.55% |
| 2023 | -7.13% | -16.61% |
| 2024 | -0.02% | +30.62% |
| 2025 | +19.85% | +33.90% |
| 2026 YTD | -7.25% | -6.60% |

**OOS 结论：**
- A 模式：股票腿 Test = **-11.2%**（样本外亏损）
- B 模式：股票腿 Train = **-5.4%**（训练期亏损），Test 正收益几乎全部由 2024-2025 贡献
- 两版本股票收益均无跨期稳定性；全样本纯股票均低于 ETF buy&hold

---

## 五、最终评级

### **D — No evidence**

依据（审计员标准，逐条）：
1. 股票策略自身（剥离 ETF）OOS 不稳定：A 的 Test=-11.2%；B 的 Train=-5.4%
2. 全样本纯股票收益（A +5.2%、B +23.4%）**均低于被动 ETF buy&hold（+26.6%）**，无超额
3. 收益高度集中（B 靠 2024-2025；2022/2023/2026 为负）
4. 参数已冻结（Top10/BB(20,2)/K=3/5层×20万），不依赖参数尖峰

**回答核心问题：修复所有已知因果/PIT 问题后，STRICT_V2 不存在可重复的股票 Alpha。** 旧 354.9% 及 Round5 的 STRICT_V1 收益均已被证实来自同Bar未来退出信息、ETF open 倒流、listing bug 与快照 ST 状态的叠加污染；全部修复后，股票腿收益 ≤ 直接持有标普500ETF。

### 第五轮遗留的"77% 未来函数"表述修正（按 Round5.1 第4项）
原"273pp/77% 收益来自未来函数"不精确。V2 同时改变了 trigger 定义（high→close）与 execution timing，应表述为：
> **原结果对同Bar退出定义极度敏感；采用两种严格因果退出（T-1已知上轨盘中触发 / 收盘确认T+1 open）后，组合总收益由约 383% 降至约 45%-74%（尚未计入全部修复）。**

---

## 附：实验脚本与结果文件
- `round51_audit.py` — STRICT_V2 事件驱动引擎（STRICT_V2_A/B、open_fill 上下界、PIT ST、PIT listing）
- `run_strict_v2.py` → `results/round5/strict_v2_matrix.csv`
- `run_strict_v2_oos.py` → `results/round5/strict_v2_oos.csv`
- `run_pit_top10_impact.py` → `results/round5/pit_st_top10_impact.json`
- `build_pit_st.py` → `data/pit_st_daily.parquet`（date/ts_code/is_st_pit/is_st_snapshot）
- `data/raw/trade_cal_full.parquet`（1990-12-19~2026-12-31 完整交易日历）
- `data/raw/namechange_full.parquet`（PIT ST 状态源）
