# A-SHARE ALPHA FACTORY — 架构说明

- 独立研究线，与 EE15 前瞻主线、ML-BB 分支完全隔离。
- Phase 0 目标：**Factor Research Infrastructure READY**（可长期、持续、可审计地批量挖掘 A 股因子的基础设施）。
- Phase 0 不做正式大规模因子挖掘；一切结果仅标 SMOKE_ONLY / LEGACY_RESEARCH。

## 0. 隔离纪律（最高优先级）

- EE15（A=exact P* / B=P*×0.985、K=3、Top10、每层 20 万、最多 5 层、ETF 现金管理、公司行为与红利税规则）**冻结不动**。
- 禁止修改 `results/evidence/forward/*`、`forward_state_A/B.json`、`src/forward_engine.py`、`run_forward_daily.py`、`update_forward_tushare.py`、`prepare_forward_data.py`。
- ML-BB Phase 1/2 视为已完成历史研究（Phase 2 评级 C），**不得通过换模型/换阈值/加特征"救"原实验**。
- 新项目全部落在：`research/alpha_factory/`、`src/alpha_factory/`、`tests/alpha_factory/`、`results/evidence/alpha_factory/`。

## 1. 数据流水线（长期蓝图）

```
原始 PIT 市场数据
  ↓
Factor Generator（候选因子生成；受 DSL / 白名单 / 复杂度预算约束）
  ↓
Factor Registry（所有尝试永久登记，append-only）
  ↓
Fast Screening（IC / RankIC / 分位 / 逐年 / bootstrap）
  ↓
Redundancy / Correlation Filter（|rho|>=0.80 预警 + 层次聚类）
  ↓
Walk-Forward OOS（Discovery 2020–2022 / Validation 2023 / Test 2024）
  ↓
Multiple Testing Control（BH-FDR + 尝试计数）
  ↓
Incremental Alpha Test（控制已有 Alpha 后的增量信息）
  ↓
Alpha Library（有效因子库）/ Alpha Graveyard（失败因子墓地）
  ↓
未来：ML Ensemble → Portfolio Test
```

## 2. 两个 Research Universe

### Universe A — BB CONDITIONAL

- 研究问题：**已经出现合法 BB 下轨信号后，什么 PIT 因子能预测未来均值回归质量？**
- 主数据：SIGPATH canonical（`results/evidence/sigpath/signal_path_20d_wide.parquet`，157,469 信号）。
- 主键：`(signal_id)`；时间锚：`signal_date`。
- 输入字段（signal_date 当日及以前 PIT 可得，白名单见 DSL_SPEC §4）：
  - 信号日行情：`signal_day_open/high/low/close/amount/volume/adj_factor`
  - BB 状态：`bb_z / bb_mid / bb_lower / bb_upper / BB_width / distance_to_lower_band`
  - 排名：`turnover_rank`；上市：`list_date`（→ 上市天数）；行业：`sector_pit / industry_snapshot`
  - 回看窗口聚合（由加载器从 `combined_daily.parquet` 在信号日前 250 日窗口内计算，全部 PIT）：
    `ret_1/3/5/10/20/60`、`vol_10/20`、`atr14_pct`、`amount_ratio_5_20`、`drawdown_20/60`、`distance_52w_high`、`gap_pct`、`daily_range_pct`
- 标签：`D1/D5/D10/D20 close_ret`、`D20_MFE / D20_MAE`、`BAD（D20_MAE<=-20%）`、`STRONG（D20_MFE>=+5%）`。
- 横截面纪律：**按 signal_date 聚类 bootstrap**；同一天大量信号不得当作独立样本。

### Universe B — FULL A-SHARE CROSS-SECTION

- 研究问题：**不依赖 BB 信号，全 A 股横截面上哪些 PIT 因子预测未来收益/风险？**
- 主数据接口：`combined_daily.parquet`（ts_code × date，open/high/low/close/vol/amount/adj_factor）+ PIT 状态表。
- 目标 horizon：1D / 5D / 10D / 20D / 60D（fwd_ret_*、MFE、MAE）。
- Phase 0：**只定义 schema 与数据加载接口**（`UniverseB` 加载器 + 小样本 smoke），不正式生成全市场标签、不跑因子。

## 3. 五本 Registry（append-only 治理核心）

| 表 | 文件 | 作用 |
|---|---|---|
| Factor Registry | FACTOR_REGISTRY.parquet/.csv | 每个尝试过的因子永久登记（`AF_000001` 起），禁止删除 |
| Alpha Graveyard | ALPHA_GRAVEYARD.parquet/.csv | 失败因子永久归档，标准失败原因 |
| Alpha Library | ALPHA_LIBRARY.parquet/.csv | 通过完整审核的因子（Phase 0 仅 LEGACY 候选） |
| Experiment Registry | EXPERIMENT_REGISTRY.parquet/.csv | 每次批量研究的完整登记（含全部失败） |
| Multiple Testing Ledger | MULTIPLE_TESTING_LEDGER.parquet | 累计 hypothesis attempts（表达式×horizon×universe×label×variant） |

- 追加即写盘；任何"删除失败因子"都禁止。
- 每次写 Registry 前加载现有文件 → 追加 → 原子写回；保留 `created_date` 等审计字段。

## 4. 防过拟合设施

- **Expression canonicalization**：解析 → 规范化（函数名/参数排序/数值格式/空白统一）→ `expression_hash`（sha256）。交换律算子（interaction/min/max）参数排序；重复表达式识别为 DUPLICATE_REQUEST。
- **复杂度预算**：operator depth ≤ 4、unique inputs ≤ 5、interaction terms ≤ 2；超出 REJECT_COMPLEXITY 并计入尝试次数。
- **Lookback 白名单**：1/2/3/5/10/20/40/60/120/250；禁止任意参数（17/23/47/83 等）。
- **PIT/Leakage Guard**：因子值只能读取 source_date ≤ T 的数据；财务数据未来接入必须用实际公告日；禁止 lead/future/负滞后。
- **Multiple Testing**：BH-FDR；接口预留 Deflated Sharpe / CSCV；禁止仅凭 p<0.05 宣布 Alpha。
- **TOTAL HYPOTHESIS ATTEMPTS** 永远可回答；无法回答尝试次数的 Alpha 结果默认不可信。

## 5. 时间切分（第一版默认）

- Discovery：2020–2022；Validation：2023；Test：2024。
- 2025–2026：禁止用于 Alpha Factory 参数搜索；未来 shadow/blind 另行治理。

## 6. 目录与命名

- 因子 ID：`AF_%06d`（Registry 自动分配）。
- 实验 ID：`AFE_YYYYMMDD_%04d`。
- 输入字段全部小写 snake_case；表达式 DSL 语法见 `DSL_SPEC.md`。

## 7. 运行

- 解释器：生产 python3（pandas 3.0.5 / numpy 2.5 / scipy 1.18 / sklearn 1.9）。
- 一键 smoke：`python src/alpha_factory/smoke.py`。
- 测试：`python -m pytest tests/alpha_factory -q`。
