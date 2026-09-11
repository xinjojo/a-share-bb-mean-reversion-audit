# UNIVERSE B — FULL A-SHARE ML DATA FOUNDATION (PHASE 0) REGISTRY

> 冻结时间：2026-09-11（Commit A 之后任何改动需显式变更登记）
> 上游状态：Alpha Factory Phase 0.1 GOVERNANCE PASS；Phase 1 BB-CONDITIONAL = C（收尾）
> 生产隔离：EE15 FORWARD OBSERVATION LIVE 零改动（git diff=0，state hash A=5f6af667 / B=be058fa0）

## 1. 目标与范围

一行 = 股票 × 交易日。研究窗口 **2020-01-01 ~ 2024-12-31**（标签需要用到 2025 年初的价格，
但**任何训练/选参/模型选择禁止使用 2025-2026 数据**——标签 horizon 内引用的 2025 年价格仅用于
构建 2024 年样本的 label，且 purge/embargo 保证这些样本不会进入 2024 之前的训练集；2025-2026
本身零参与特征计算以外的任何研究活动）。

本阶段 = DATA FOUNDATION ONLY。禁止：正式调模型/比较模型/调 LightGBM/看 2024 选参数/
批量挖新公式/组合回测/修改 EE15。

## 2. Universe 定义（PIT）

- 候选池：`data/raw/stock_basic.parquet`（5,889 只，含 list_date / delist_date / list_status）。
- 每日 T 的合法股票：
  - `list_date <= T`（已上市）
  - `delist_date` 为 NaN 或 `delist_date > T`（未退市）
  - 当日存在行情行（`data/raw/daily/{ts_code}.parquet` 或 `data/combined_daily.parquet` 补充）→ 非停牌
  - **上市不足 60 个交易日**（按交易日历计数 < 60）→ 从 Universe 剔除（新股效应），但保留在原始宽表中供审计
- **退市股票必须保留**：2020-2024 退市 179 只中，raw/daily 覆盖 176 只；缺失 3 只北交所
  （832317.BJ / 833874.BJ / 833994.BJ）如实披露于 UNIVERSE_SURVIVORSHIP_AUDIT.md。
- ST：PIT 状态来自 `data/raw/namechange_full.parquet`（is_st_pit），与主引擎 round51 口径一致。
- 停牌：无当日行 = 停牌（主引擎口径）；`is_suspended = True` 时该行不进入特征计算（其 OHLC 为缺失）。
- 涨跌停：按板块阈值近似（主板 10%、创业板/科创板 20%、北交所 30%、ST 5%）：
  `is_limit_up = close >= pre_close * (1 + thr - 1e-9)`，`is_limit_down` 同理（与主引擎
  limit_down_mode 近似一致，ST/板块阈值按 PIT ST 与代码前缀判定）。
- 禁止用 2026 当前 stock_basic 反填历史股票池；delist_date 仅用于界定"该日是否仍在市场"。

## 3. 时间切分（未来 ML 使用，本阶段只建接口）

- Train/Discovery：2020-01-01 ~ 2022-12-31
- Validation：2023-01-01 ~ 2023-12-31
- Final Test：2024-01-01 ~ 2024-12-31
- **purge/embargo**：训练样本的 label 窗口（最大 60 交易日）不得跨越 OOS 起点。
  `split_purged(df, train_end, embargo_days=60)`：train 内样本要求
  `signal_date + label_horizon <= train_end`。Validation/Test 同理向前剔除。
- 2024 仅构建标签，禁止任何模型选择。

## 4. 标签定义（与 Feature 物理隔离）

- 价格口径：`close_adj = close * adj_factor`（后复权，公司行为后连续）。
- STATISTICAL（T close → T+h close，close_adj）：
  `fwd_ret_1/5/10/20/60`、`MAE_5/20`（未来窗口最低点相对 T close 的最大跌幅）、`MFE_5/20`（最大涨幅）。
- CROSS-SECTIONAL（每日横截面，仅当日合法股票）：
  `fwd20_rank01`（fwd_ret_20 的当日 rank → [0,1]，1=最好）、`TOP20_FWD20`、`BOTTOM20_FWD20`。
- EXECUTABLE（T+1 open 入场）：`exec_fwd_ret_20`（T+1 open_adj → T+1+20 close_adj）、
  `exec_entry_possible`（T+1 非停牌且非一字涨停可买）、`exec_exit_possible`（T+h 非停牌可卖）。
- 每个样本记录 `label_end_date`（= signal_date + horizon），供 purge/embargo 使用。
- 标签源日期严格 > T；特征源日期严格 <= T（leakage guard 机器验证，500 条随机 stock-day）。

## 5. Feature 池（77 个已冻结 + 4 个 UNAVAILABLE，见 FEATURE_REGISTRY）

- 价格/位置、波动、流动性、趋势、BB(20,2)、横截面 rank、市场上下文、行业相对（申万 L1 PIT）、
  状态变量。全部只使用 <= T 数据；窗口不足 → NaN（missing_policy=NAN，树模型原生处理）。
- **市值特征 UNAVAILABLE**：本地仅 `daily_basic_20241231.csv` 单日快照，无 PIT 历史市值 →
  `log_market_cap/market_cap_percentile/size_bucket/turnover_*` 冻结为 PIT_UNAVAILABLE，
  不得用 2026 快照或未来市值填充。
- 行业：`data/raw/d1_cache/sector_membership.parquet`（申万 L1，PIT in_date/out_date）。

## 6. 数据源与存储

- 日线主源：`data/raw/daily/*.parquet`（5777 只）+ `data/raw/adj_factor/*.parquet`；
  退市补全：与 `data/combined_daily.parquet` 交叉核对后补入缺失退市股。
- 输出：`results/evidence/alpha_factory/universe_b/features/year=YYYY/` 与
  `labels/year=YYYY/`（parquet 分区）；Git 只提交 schema/manifest/hash/audit/benchmark/摘要。
- 复权审计：≥50 个跨除权除息窗口人工/机器 parity（close_adj 连续性）。

## 7. 性能

- M2 Pro / 10 核 / 16GB RAM。目标：全量 5 年 ~6.5M 行 × 80 列 float64 ≈ 4GB 以内可构建；
  benchmark 实测 1 月/1 年/5 年读取与特征计算时间，决定 Phase 1 引擎（Pandas vs Polars vs DuckDB）。

## 8. 冻结声明

本 Registry 与 FEATURE_REGISTRY / LABEL_REGISTRY 在正式结果计算前由 Commit A 冻结。
Commit A 之后：禁止增删特征、修改标签定义、修改 purge 规则（除非显式变更登记 + 新 commit）。
