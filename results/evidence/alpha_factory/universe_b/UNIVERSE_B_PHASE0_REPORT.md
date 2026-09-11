# UNIVERSE B — FULL A-SHARE ML DATA FOUNDATION (Phase 0)

状态：**UNIVERSE B DATA FOUNDATION READY**
前置：Alpha Factory Phase 0.1 GOVERNANCE PASS（1a7db3f）；Phase 1 BB-CONDITIONAL = C（ab2f55d，Symbolic 300 无 KEEP）
EE15：FORWARD OBSERVATION LIVE，本阶段零改动（results/evidence/forward/ git diff=0）

---

## 1. 数据规模（真实实测）

| part | rows | 说明 |
|---|---|---|
| panel | 5,558,740 | 股票×交易日（含 18,127 停牌行），2020-01-02 ~ 2024-12-31 |
| features | 5,540,613 | 非停牌行 × 84 列（77 PIT 特征 + 5 状态 + date/ts_code） |
| labels | 5,540,613 | 16 标签列（统计 7 + 横截面 3 + 可执行 3 + 元 1 + date/ts_code） |

按 year 分区（panel/features/labels 各 5 个 year=YYYY 分区），parquet 本地保存，不入 git。

## 2. Universe 定义（PIT）

- 股票池：raw/daily 与 combined_daily 实有行情（5,249 只在窗口内有行），上市日期=list_date、退市日期=delist_date，缺失退市日视为窗口内持续存在。
- 2020-2024 退市 179 只，panel 覆盖 176 只（98.3%）；缺 3 只北交所（832317.BJ / 833874.BJ / 833994.BJ）本地无行情文件，属数据源客观缺口，非主动剔除（详见 UNIVERSE_SURVIVORSHIP_AUDIT.md）。
- ST：pit_st_daily + namechange PIT（date/ts_code 级 is_st_pit），非当前快照回填。
- 停牌：按每只股票 list→min(delist,2024) 交易日历展开，缺行情行=停牌（is_suspended）。
- 涨跌停：combined 无 is_limit_up，按板块阈值近似（ST→5%；300/301/688/689→20%；8/4/92 开头→30%；否则 10%），is_limit_down 以 combined 为准（原列 22,186 NaN 已按同规则补全）。Registry 已标注口径。

## 3. 特征（77 PIT + 5 状态 + 5 UNAVAILABLE 市值族）

- PRICE：ret_1/2/3/5/10/20/40/60/120/250、drawdown_20/60/120、distance_52w_high
- VOLATILITY：atr14_pct、vol_5/10/20/60、range_pct、gap_pct
- LIQUIDITY：log_amount、amount_rank、amount_percentile、amount_ratio_5_20、amount_ratio_20_60
- TREND：distance_ma5/10/20/60/120/250、ma_slope_5_20/20_60
- BB：bb_z、bb_width（BB20/2，样本标准差口径与日线主线可比）
- CROSS_SECTIONAL：ret_5/20/60、atr14_pct、log_amount、bb_z 的 cs_rank 版本
- MARKET_CONTEXT（每日共享）：market_up/down_ratio、new_high/low_ratio、limit_up/down_count、bb_signal_breadth、market_vol_20、CSI300/500/1000 ret_1/5/20/60（12）
- INDUSTRY_RELATIVE（申万 L1 PIT，窗口 merge_asof）：industry_ret_1/5/20/60、industry_breadth、ret_h_minus_industry（3）
- STATE：is_st_pit、is_limit_up、is_limit_down、listing_days（is_suspended 恒 False 于特征行）
- UNAVAILABLE：log_market_cap、market_cap_percentile、size_bucket、turnover、turnover_rank（daily_basic 仅有 2024-12-31 单日快照，无 PIT 历史 → 明确不生成，不引入未经审计新数据源）

全部特征 source_date <= T。详见 UNIVERSE_B_FEATURE_REGISTRY.csv（82 行）。

## 4. 标签（16 列）

- STATISTICAL：fwd_ret_1/5/10/20/60（close_adj 未来 h 日收益）；MFE_5/20、MAE_5/20（未来窗口最高/最低 adj 相对当前 close）
- CROSS_SECTIONAL：fwd20_rank01（当日合法股票 fwd_ret_20 百分位）、TOP20_FWD20、BOTTOM20_FWD20
- EXECUTABLE：exec_fwd_ret_20（T+1 open 入场 → T+21 open 后 close）、exec_entry_possible（T+1 非停牌且非一字涨停）、exec_exit_possible
- META：label_end_date（T 起第 60 个交易日 → purge/embargo 键）

## 5. 审计（全部 PASS）

- Survivorship：176/179 退市股保留；缺失 3 只北交所数据源缺口。
- 复权 parity：27,864 个 adj_factor 变动事件；非除权日 close_adj 异常跳变（>5%）行数 = 0；adj_factor 缺 000587.SZ / 600385.SH（1.0 兜底，ADJ_FACTOR_GAP.csv）。
- Leakage：随机 500 stock-day；feature 列无任何 fwd_/MAE/MFE/exec_/TOP/BOTTOM/label_end 前缀混入（leak_cols=[]）；label 列白名单全部通过（bad_lab=[]）→ PASS。
- Scale：见 SCALE_SUMMARY.md（2020 4,116 只 → 2024 5,125 只；ST 行 41,786→29,828；涨跌停占比 0.4%~1.3%）。

## 6. 性能 benchmark（M2 Pro / 10 核 / 16GB）

| 读取 | 时间 | 峰值 RSS |
|---|---|---|
| panel 1 年（942k×20） | 0.06s | ~0.4GB |
| panel 全（5.56M×20） | 0.22s | ~1.9GB |
| features 全（5.54M×86） | 3.8s | ~5.8GB |
| labels 全（5.54M×18） | 0.6s | ~5.8GB |

结论：Pandas（pyarrow 并行读）完全足够 Phase 1（<30s、峰值<8GB）。Polars/DuckDB 列为可选优化，非必需。第一阶段优先简单可靠。

## 7. SMOKE ML（SMOKE_ONLY，非研究结论）

- LightGBM（n_estimators=50, depth=4, lr=0.1, seed=42）目标 fwd20_rank01
- train：2,826,740 行（2020-2022，purged label_end<=2022-12-31）；val：2023 前 20,000 行；features 84
- 管道完整跑通（读 → merge → purge → fit → predict）。
- **不报告任何 IC/收益/Alpha；不得据此评估模型质量。**

## 8. 2025-2026 隔离

本数据集只覆盖 2020-01-01 ~ 2024-12-31。2025-2026 未参与任何训练/选参/特征选择/模型选择。

## 9. 文件清单

- Registry：research/alpha_factory/universe_b/{UNIVERSE_B_REGISTRY.md, UNIVERSE_B_FEATURE_REGISTRY.csv, UNIVERSE_B_LABEL_REGISTRY.csv}
- 代码：src/alpha_factory/universe_b/{build_universe, build_features, build_labels, audit, benchmark, smoke}.py
- 证据：results/evidence/alpha_factory/universe_b/{panel,features,labels}/、UNIVERSE_SURVIVORSHIP_AUDIT.md、ADJUSTMENT_PARITY_AUDIT.md、UNIVERSE_B_LEAKAGE_AUDIT.md、SCALE_SUMMARY.md、BENCHMARK.csv/.md、SMOKE_ML.md、DATA_MANIFEST.csv/.md、ADJ_FACTOR_GAP.csv
- 测试：tests/alpha_factory/test_universe_b.py（8 项，全量 95 passed）

## 10. 治理

- 上一阶段 Symbolic 300 全部可追溯（AFS_000001~300 → StatusHistory → Graveyard，PHASE1_SYMBOLIC_TRACE.csv），0 KEEP 为治理设计允许（failure_stage/failure_reason 完整）。
- Registry integrity：P0=0 / P1=8（已文档化豁免）。
- EE15 forward 文件 git diff=0；state hash 未变。

状态结论：**UNIVERSE B DATA FOUNDATION READY**
