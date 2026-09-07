# MONTHLY-BB-MR — 月线布林带均值回归 Signal-Level Alpha 审计

**独立研究分支。绝对禁止修改 / 污染 / 重新优化 EE15 日线前瞻系统（冻结）。**

## 状态
- Registry：`registries/MONTHLY_BB_ALPHA_REGISTRY.md`（**结果计算前冻结并提交**）
- 阶段：第一阶段 = 仅验证月线 BB(20,2σ) 下轨信号的 signal-level alpha。
- 结论分级：A（强稳定）/ B（依赖条件）/ C（仅原始反弹无超额）/ D（无优势）。

## 目录布局
- `src/monthly_bb/`：拉取 / 构建 / 分析 / 图表 / sanity 代码
- `research/monthly_bb/`：Registry、报告
- `results/evidence/monthly_bb/`：小型结果 CSV、图（Git 入库）
- `data/monthly_bb/`：大文件本地缓存（**gitignore**）：daily 分片、adj 分片、月末市值、月线 panel、信号全量 parquet

## 大文件本地记录（Commit B 时更新 hash / 行数 / schema）
| 文件（本地 data/monthly_bb/） | sha256 | 行数 | 说明 |
|---|---|---|---|
| monthly_panel.parquet | （Commit B 填） | （Commit B 填） | 全 A 月线（后复权）+ BB |
| monthly_signals.parquet | （Commit B 填） | （Commit B 填） | 全部信号 + forward/MFE/MAE |
| daily/*.parquet | （Commit B 填） | （Commit B 填） | 全 A 日线按交易日分片 |

## 关键口径（详见 Registry）
- BB(20, 2σ, ddof=1)，与日线冻结策略一致。
- 后复权 `close_adj = close × adj_factor`（无未来函数）。
- 信号：月末 close_adj < BB lower；entry = 下月第一个交易日 open。
- 主统计：NEW_EPISODE（首次跌破）；补充 ALL_SIGNAL_MONTHS。
- 基准：同股随机月 / 同股无条件 / 时间匹配抽样；bootstrap+permutation ≥1000；cluster by signal_month。
- 超额：个股收益 − 沪深300 同期。
- 开发期信号月 2005-01~2024-12；2025+ 已暴露段仅展示。
