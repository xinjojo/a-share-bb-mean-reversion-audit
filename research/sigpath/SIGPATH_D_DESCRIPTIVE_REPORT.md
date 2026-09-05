# SIGPATH-D — Full Descriptive Statistical Audit

本报告只描述 2020-2024 已冻结 SIGPATH forward-path 数据的样本分布。报告未修改 raw parquet, 未重新生成 raw, 未重跑策略, 未做参数优化, 未读取 2025-2026 outcome。

## 1. 数据范围
- total signals: 157,469
- role counts: {'ADD_ON_1': 42105, 'ADD_ON_2': 25652, 'ADD_ON_3': 15828, 'ADD_ON_4': 9997, 'NEW_ENTRY': 63887}
- raw wide SHA256: `5fcb3384b3d8260954fcf53905da0f5c2fae4efbe3a6f7e3cfeb1c2d7274fdc0`
- raw long SHA256: `a359cebc0307f19c043c979c5f687ef36f00be8d8703ba20a32d52acdfcd854e`
- 结果目录: `results/evidence/sigpath_d/`

## 2. 总体收益分布
- D1 close mean/median: -0.22% / -0.04%
- D5 close mean/median: +0.52% / +0.21%
- D10 close mean/median: +0.68% / +0.13%
- D20 close mean/median/P10/P90: +1.49% / +0.25% / -12.02% / +15.99%
- D20 positive pct: 51.00%
- 完整 skew/kurtosis 和分位数见 `core_horizon_statistics.csv`。

## 3. D1-D20 路径
- `percentile_path_close.csv`, `percentile_path_mfe.csv`, `percentile_path_mae.csv` 给出 D1-D20 mean/P5/P10/P25/P50/P75/P90/P95。
- 图 05/06/07 分别为 close_ret, MFE, MAE 的独立 percentile path。

## 4. MFE / MAE
- D10 MFE median: +4.84%
- D10 MAE median: -4.72%
- By D10, MFE >= +5% pct: 48.83%
- By D10, MAE <= -5% pct: 47.58%
- extended hit-rate matrices 见 `mfe_hit_rate_extended.csv` 与 `mae_hit_rate_extended.csv`。

## 5. 首次触及时间
- MFE +5% D10 cumulative pct: 48.83%
- MAE -5% D10 cumulative pct: 47.58%
- 完整首次触及统计见 `first_hit_time_mfe.csv` 与 `first_hit_time_mae.csv`。

## 6. 先跌后涨
- 样本中先触及 -10% 后后续交易日触及 0% 的比例: 10.15%。
- 样本中先触及 -10% 后后续交易日触及 +5% 的比例: 6.31%。
- 这些是固定模板的路径顺序描述, 不是操作规则。

## 7. 先涨后跌
- 样本中先触及 +10% 后后续交易日触及 0% 的比例: 9.45%。
- 完整路径顺序表见 `up_then_down_path_stats.csv`。

## 8. 早期浮亏与 D20
- `mae_d3_to_d20_outcome_table.csv`, `mae_d5_to_d20_outcome_table.csv`, `mae_d10_to_d20_outcome_table.csv` 给出早期 MAE 分桶后的 D20 描述统计。
- 描述上, MAE_D10 最深桶 `<=-30%` 的 D20 median 为 -11.32%。

## 9. 早期浮盈与 D20
- `early_mfe_to_d20_outcome.csv` 给出 MFE_D3/D5/D10 固定分桶后的 D20 描述统计。

## 10. NEW_ENTRY / ADD_ON 分层
- NEW_ENTRY D20 median: -0.35%; ADD_ON_4 D20 median: +1.77%。
- 描述上, NEW_ENTRY 与 ADD_ON_4 的 D10 MFE median 分别为 +4.62% / +5.83%。
- 这里只描述分层路径差异, 不推导配置。

## 11. 年度稳定性
- 描述上 D20 median 最高年份: 2022 (+1.00%); 最低年份: 2020 (-0.88%)。
- NEW_ENTRY 年度表单独见 `new_entry_year_statistics.csv`。

## 12. BB_z 描述性分桶
- 固定 BB_z 桶的 D20 median 序列: 描述上递增。
- 该表只作 descriptive stratification。

## 13. turnover rank 描述性分桶
- 固定 turnover_rank 桶的 D20 median 序列: 没有单调描述趋势。
- 该表只描述 turnover_rank 分桶中的样本分布。

## 14. 多层 episode
- 1 层 episode count: 21782; NEW_ENTRY D20 median: +6.33%。
- 5 层 episode count: 9997; NEW_ENTRY D20 median: -5.99%; last ADD_ON D20 median: +1.77%。
- 这里只有 episode 内路径描述, 不推导配置。

## 15. 极端样本
- `manual_casebook.csv` 已生成, rows=450。包含 D20 worst/best, D10 MAE/MFE, 路径顺序模板, 5 层 episode, 以及接近总体中位数的普通样本。

## 16. 数据限制
- stock_name 在 namechange_full 有效区间覆盖时可作为 PIT 名称; 不能覆盖的 fallback/UNKNOWN 只用于人工定位。
- industry_snapshot / list_date 是 NON-PIT manual-reference-only 字段。
- 本报告没有输出买卖建议、参数选择或组合模拟。
