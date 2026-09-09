# ALPHA FACTORY — PHASE 0 基础设施验收报告

- 状态：**ALPHA FACTORY PHASE 0 READY**
- 日期：2026-09-09
- 本阶段禁止正式大规模因子挖掘；以下结果全部为 **SMOKE_ONLY**，不作为任何 Alpha 结论。

## 1. 隔离声明

- EE15 前瞻（FORWARD OBSERVATION LIVE）：**零改动**。
  `git status --short results/evidence/forward/` 为空。
- ML-BB Phase 1/2：已评级 B/C 的历史研究，本阶段未触碰其代码与产物。
- 本阶段全部代码/产物独立位于：
  `research/alpha_factory/`、`src/alpha_factory/`、`tests/alpha_factory/`、`results/evidence/alpha_factory/`。

## 2. 架构

- 两份 Universe 定义与五本 append-only 表、时间切分、防过拟合治理：`research/alpha_factory/ARCHITECTURE.md`
- DSL 规格（算子/字段白名单、lookback 白名单、复杂度预算、PIT 规则、canonicalization）：`research/alpha_factory/DSL_SPEC.md`

数据流（与用户指令第 0 节一致）：

```
原始 PIT 市场数据
  → Factor Generator（DSL/白名单/复杂度约束）
  → Factor Registry（append-only，expression_hash 防换皮）
  → Fast Screening（横截面 IC/RankIC/ICIR/cluster bootstrap）
  → Redundancy / Correlation（|rho|≥0.80 → DUPLICATE candidate）
  → Walk-Forward OOS（Discovery 2020-2022 / Validation 2023 / Test 2024）
  → Multiple Testing Control（BH-FDR；预留 DSR/CSCV）
  → Incremental Alpha Test（residual IC / ΔR²）
  → Alpha Library / Alpha Graveyard（失败永久保留）
  → Experiment Registry + Multiple Testing Ledger（总尝试次数永远可回答）
```

## 3. Registry 落盘（本地路径 + SHA256）

parquet 按仓库 `.gitignore`（`*.parquet`）不入库，指纹留档；CSV 镜像入库供人工查看。

| 文件 | 行数 | SHA256 |
|---|---|---|
| research/alpha_factory/FACTOR_REGISTRY.parquet | 34 | 69abd413c7e1699237323e2a2359340f4a270b917b3879d549a3160f84cda378 |
| research/alpha_factory/ALPHA_GRAVEYARD.parquet | 13 | 93825e273b4c9b7052bc12849ad6fcef9b0ca8abf705930f04b13d95cdf31c2d |
| research/alpha_factory/ALPHA_LIBRARY.parquet | 1 | e5717971c6ea4d1e08b29399c0153a72e5efcb806cb4c6a95c71619fbd53c7c8 |
| research/alpha_factory/EXPERIMENT_REGISTRY.parquet | 1 | 8f2cbc58e2b4b5a49dd4f315d3be10fe2d43d59d8e7a2be60c4cb35e1064ed00 |
| research/alpha_factory/MULTIPLE_TESTING_LEDGER.parquet | 42 | c37f0e415ad48b2c33a6797861a0ec8ebc8004a69ecdc199759bf125f54cfd70 |

- Registry 状态分布：FAIL 13 / SCREENING 13 / ARCHIVED 5 / PROPOSED 2 / VALIDATING 1
- Graveyard 13 条（legacy 失败项，永久保留）
- Library 1 条（breadth 候选，VALIDATING 状态，非正式 KEEP）
- Legacy 映射：`research/alpha_factory/LEGACY_IMPORT.csv`（12 项 LEGACY_RESEARCH + 2 项 HOLD）

## 4. Smoke 验证

- Universe A：SIGPATH canonical 157,469 signals / 1,137 signal dates。
- 因子 14 个（SMOKE_ONLY）：ret_5、ret_20、atr14_pct（复用 legacy FAIL 条目，防换皮生效）、
  ret5_div_atr、amount_cs、amount_ratio_5_20、drawdown_20、dist_52w_high、
  market_breadth、breadth_up、bbz_x_amount、drawdown_minus_ret、min_ret5_ret20、gap_sign。
- 标签 3 个（fwd_ret_20 / BAD / STRONG），共 42 个 factor×label 尝试。
- 流水线全部跑通：注册 → 校验 → 计算 → 筛选 → BH-FDR（0 个通过，符合 SMOKE 预期）→
  冗余检测（3 对高相关 DUPLICATE candidate）→ 增量 ΔR²（bb_z 基线之上 ret_5 增加 0.0219，仅演示）→
  leakage 检查（0 泄漏）→ 实验登记 → 报告 → benchmark。
- 输出：`results/evidence/alpha_factory/phase0_smoke/`
  （phase0_smoke_screen.csv / _duplicates.csv / _clusters.csv / _incremental.csv / _leakage.csv / AFE_20260909_0001_report.{json,md}）
- benchmark：`results/evidence/alpha_factory/phase0_benchmark.csv`

## 5. 单元测试

- `tests/alpha_factory/` 共 **55 个测试全部 PASS**（生产解释器 + pytest 9.1.1）：
  DSL parser / canonical hash / 重复检测 / future 算子拒绝 / 负 lag 拒绝 / PIT source-date /
  factor-label 隔离 / IC / RankIC / quantile / cluster bootstrap / BH-FDR / 相关性聚类 /
  Registry append-only / Graveyard append-only / 实验尝试计数。

## 6. 资源评估（M2 Pro 10 核 / 16GB RAM 实测外推）

- 实测：157k signals × 14 因子，计算 0.05s + 筛选 12.7s，单因子约 0.91s。
- 外推（单进程、同数据集）：100 因子 ≈ 1.5 分钟 / 约 126MB RAM；1000 因子 ≈ 15 分钟 / 约 1.26GB RAM。
- 结论：当前机器 **LOCAL ML READY**；每晚可筛数百至上千候选（多进程可线性扩展）。
- 未安装 GPU / 深度学习栈；第一阶段表格模型 CPU 足够。

## 7. 治理要点

- TOTAL HYPOTHESIS ATTEMPTS（全部时间累计）= **42**（=14 因子 × 3 标签；重复表达式按
  expression_hash 去重，不新增尝试）。
- 2025–2026 未用于任何筛选/选择/调参；Discovery/Validation/Test 冻结 2020-2022 / 2023 / 2024。
- Tushare token：本阶段未调用任何外部数据源，无 token 落盘；secret scan 通过。
- 大 parquet 不入库（指纹见上表）；无任何 .env / token / credential 提交。

## 8. 已知限制（如实声明）

- Universe B（全 A 横截面）本阶段仅实现 schema 与小样本 smoke 接口，未正式跑数。
- 财务/分析师/资金流/事件类因子族尚未接入（未来另行治理）。
- ALPHA_LIBRARY 中 breadth 为候选状态，正式入库需后续完整审核。
- 环境变更：生产解释器安装了 pytest 9.1.1（非代码产物）。
