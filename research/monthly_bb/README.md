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

## 大文件本地记录（2026-09-07 Commit B）
| 文件（本地 data/monthly_bb/） | sha256 | 行数/规模 | 说明 |
|---|---|---|---|
| monthly_panel.parquet | 2b31a83222bb6607dea1ce6366cbfee46d6c2923137cfc698d4faa257a5db613 | 829,535 行 × 77.6MB | 全 A 月线（后复权）+ BB |
| monthly_signals.parquet | 82eefb796bd3e905d46a769b21412404aca1caf14f2f62066dd51cbce62ffc9b | 14,708 行 × 8.0MB | 全部信号 + forward/MFE/MAE/超额 |
| index_signals.parquet | e528d9197dca8b422d208062d97564748b41fda0ea68f457a781d230c9cb0289 | 35 行 | 指数信号 |
| daily/*.parquet（5586 片） | 见 wide_manifest（分片未逐片列） | 5586 交易日 × 16,327,635 日线行 | 全 A 日线（2004-01-02~2026-09-07） |
| adj/*.parquet（5586 片） | 同上 | 17,119,651 行 | 复权因子 |
| mcap/*.parquet（276 片） | 同上 | 276 个月末 | PIT 市值 daily_basic |

Git 中保存：生成代码、全部小型结果 CSV、图、wide 表（含 sha256 manifest `results/evidence/monthly_bb/wide_manifest.json`）、报告。任何 downstream 研究须先核对 parquet sha256 与上表一致。

## 关键口径（详见 Registry）
- BB(20, 2σ, ddof=1)，与日线冻结策略一致。
- 后复权 `close_adj = close × adj_factor`（无未来函数）。
- 信号：月末 close_adj < BB lower；entry = 下月第一个交易日 open。
- 主统计：NEW_EPISODE（首次跌破）；补充 ALL_SIGNAL_MONTHS。
- 基准：同股随机月 / 同股无条件 / 时间匹配抽样；bootstrap+permutation ≥1000；cluster by signal_month。
- 超额：个股收益 − 沪深300 同期。
- 开发期信号月 2005-01~2024-12；2025+ 已暴露段仅展示。
