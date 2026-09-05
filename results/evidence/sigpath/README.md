# SIGPATH — A股 BB Mean Reversion 全量 Signal Forward Path Audit

## 1. 目的
数据事实层: 把 2020–2024 全部满足冻结 BB 入场定义的信号 (含加仓层) 逐条展开,
观察每条 signal 未来 D1..D20 (该股票实际交易日) 的自然价格路径。
**不输出任何策略结论** (策略解释由人工审阅完成)。

## 2. 数据来源
- 日线: `data/combined_daily.parquet` (2020-01-01..2026-08-25; 本任务仅使用 signal_date<=2024-12-31 且路径<=2024-12-31)
- 复权: `close_adj = close * adj_factor` (与 frozen baseline 一致)
- ST PIT: `data/pit_st_daily.parquet`; 上市日历: `data/raw/trade_cal_full.parquet`; 股票基础: `data/raw/stock_basic.csv` (list_date/industry 为当前快照, 非 PIT)
- stock_name: `data/raw/namechange_full.parquet` 中 signal_date 落入有效区间时为 PIT 名称; 若无有效区间则 fallback stock_basic 当前名; 均无 -> 'UNKNOWN'
- PIT sector: `results/evidence/d1/d1_signal_context.csv` (signal-date 级, 申万 L1; 仅首层/有 context 者非 NA)

## 3. 冻结定义 (S1 frozen B20, commit 1368584; SIGPATH lineage 见第 9 节)
- BB: window=20, k=2.0, ddof=1 (pandas rolling std, min_periods=20); bb_lower = MA20 - 2*SD20
- signal (T 收盘): `close_adj < bb_lower` 且当日非跌停 (is_limit=0)
- eligibility: listed>=60d (list_date + 全交易日历) 且非 ST (PIT) 且 BB20 有值且当日有行情
- entry: T+1 open; `entry_cost = open * (1 + 0.001)` (10bp 滑点); 100 股 lot; 200,000/层;
  T+1 涨停/停牌 -> CANCEL (与 frozen replay 一致, 不入 universe)
- universe: **全部成功入场信号层** = NEW_ENTRY 63,887 (63,785 realized + 102 censored end-period no-quote) + ADD_ON_1..4 93,582 (levels 语义, MAX_LEVELS=5) = **157,469 层**
- 不做任何组合约束 (TopN / K / cash / 已持仓他股 均不删除信号)

## 4. 字段口径
- `entry_cost`: 每股执行价 (open*(1+SLIP), 含滑点, 不含佣金; 佣金= max(amt*0.025%, 5元) + 过户费, 见 round51_audit)
- ret (open_ret/high_ret/low_ret/close_ret): `price / entry_cost - 1` (可为负, 不截断)
- MFE_Dn = max(high_ret D1..Dn); MAE_Dn = min(low_ret D1..Dn)
- D1 = entry_date (该股票实际交易日); 停牌日不计入 horizon
- `BB_width = bb_upper - bb_lower` (adj 空间, 信号日 T 收盘); `distance_to_lower_band = close_adj(T) - bb_lower` (<0 表示已跌破)
- `data_quality_flag`: JUMP (路径内相邻 close 跳变>=30%, 常见于除权/复权跳变); SHORT_HISTORY (期末 available_future_days<20)
- `entry_role`: NEW_ENTRY / ADD_ON_1..4; `position_episode_id`: 本审计 replay 中 NEW_ENTRY 入场顺序 1..63785
- `signal_day_volume`: parquet vol 原单位; `signal_day_amount`: parquet amount 原单位

## 5. 数据范围与总量
- signal_date: 2020-02-06 .. 2024-12-30
- entry_date: 2020-02-07 .. 2024-12-31
- 股票数: 5166; episode 数: 63887
- 信号层: 总计 157,469 (NEW_ENTRY 63,887 + ADD_ON 93,582)
  (ADD_ON_1 42,105 / _2 25,652 / _3 15,828 / _4 9,997)
- long 行: 3,149,380 (最多 20 行/信号, 期末截断留 NaN)
- 缺失 horizon 格: 43,031; SHORT_HISTORY 信号: 3,135

## 6. PIT / Survivorship 风险
- eligibility 为 PIT (listed>=60d + PIT ST); 未按当前快照过滤退市股 (退市股在期间内仍在 universe)
- stock_name 在 namechange_full 有效区间覆盖时为 PIT 名称; 无有效区间的 fallback stock_basic 当前名和 UNKNOWN 仅用于人工定位, 不构成 PIT 特征
- industry_snapshot / list_date 为**当前 stock_basic 快照**, NON-PIT, manual-reference-only
- sector_pit 仅覆盖 d1 context 可 join 者 (首层为主); add-on 层多为 NA
- 未来路径止于 2024-12-31 (2025–2026 CLOSED 不变), 期末信号 available_future_days<20

## 7. 文件清单
- RAW: `signal_path_20d_long.parquet` / `signal_path_20d_long.csv.part_001..N`
- RAW: `signal_path_20d_wide.parquet` / `signal_path_20d_wide.csv.part_001..N`
- MANUAL: `manual_review_index.csv` (signal_id/stock/date/entry_cost/role/MFE/MAE/close_ret D5/D10/D20)
- STATS: `signal_path_descriptive_statistics.csv` (D1..D20 x 5 vars x mean/median/std/var/min/max/range/IQR/P1..P99)
- STATS: `signal_path_distribution_bins.csv` (17+2 桶 x horizon x count/pct)
- STATS: `mfe_hit_rate_matrix.csv` / `mae_hit_rate_matrix.csv` (horizon x threshold)
- CHECK: `sanity_check.txt` (随机20 + 5大涨 + 5大跌 + 5先跌后涨 + 5先涨后跌, 全 20 日 OHLC)
- CHARTS: `charts/fig1..fig11.png` (hist x3, percentile path x3, heatmap x3, hit-rate heatmap x2)
- META: `sigpath_summary.json` / `sigpath_invariants.json` / `sigpath_layers_raw.csv` / `sigpath_episodes_parity.csv`
- META: `raw_data_manifest.json` / `raw_partition_manifest.csv` / `cross_table_parity.json` / `missing_horizon_by_available_days.csv` / `date_boundary_audit.json`
- META: `wide_long_value_parity.json` / `path_math_invariants.json` / `manual_index_parity.json` / `pit_name_audit.json`
- 本文件 `README.md`

## 8. 描述性摘要 (事实, 非结论)
close_ret (百分比):
- D1:  mean -0.22  median -0.04  std 2.99
- D5:  mean +0.52  median +0.21  std 6.76
- D10: mean +0.68  median +0.13  std 10.17
- D20: mean +1.49  median +0.25  std 13.39
完整分位数/离散度见 descriptive_statistics.csv。

## 9. SIGPATH-C 追溯性与 raw-data policy
- SIGPATH-A: `94bd041d21a695557df3d9596f26385b4fc8f1bf`
- SIGPATH-A2: `8bb98867988bf2b8d3d0304974391ec9276a72ba`
- SIGPATH-A3: `ea369277546d73957f6b5fd94700a03f21788173`
- SIGPATH-B canonical result commit: `974fa2aef6fd9284ce50163d0d68a4fb13d3697e`
- 大 raw 表未进入 GitHub；canonical copy 位于本地 `results/evidence/sigpath/`。
- Git 中保存 manifest hashes、生成代码、统计、sanity、manual index、charts、metadata。
- 任何 downstream study 必须先验证 `signal_path_20d_wide.parquet` 与 `signal_path_20d_long.parquet` 的 SHA256 与 `raw_data_manifest.json` 一致。
- SIGPATH-C PIT name audit: namechange_full 有效区间覆盖 127,165 rows, name mismatch 0; 4,044 rows 早于该股首个 namechange_full 区间, raw stock_name 不能证明为 PIT, 只能按 fallback/manual-reference-only 处理。
- SIGPATH-C 仅做 bookkeeping cleanup；未修改 raw parquet/CSV 数据，未重新计算策略。

## 10. 交互式 HTML 报告（本地交付，不入 Git）
- `results/evidence/sigpath/sigpath_interactive_report.html`（约 45MB，单文件自包含，双击即开，无外部依赖）
- 内容：SIGPATH 全部统计（描述统计/18 桶分布/MFE-MAE hit-rate/数据指纹/parity/date-boundary/sanity）+ 11 张图 + SIGPATH-D 描述审计（核心统计/分桶/role 对比/percentile path/first-hit/扩展表 + 17 张图）+ manual_review_index 157,469 条全量浏览（搜索/排序/分页）。
- 生成：`python research/sigpath/build_interactive_html.py`（只读既有产物，不重新计算任何统计）。
- 因含全量明细索引体积较大，未进入 GitHub；canonical 本地副本即上路径。
