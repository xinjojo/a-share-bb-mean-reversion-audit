# Alpha Factory — Phase 0 → 0.1 Registry Migration Report

- 迁移时间: 2026-09-10T12:23:40
- 迁移脚本: src/alpha_factory/migrate_phase0.py

## 1. 原 Factor Registry 多少行？
- 迁移前 FACTOR_REGISTRY = 35 行；迁移后 = 35 行。
- 迁移前 status 分布: {'SCREENING': 13, 'FAIL': 8, 'INVALID': 8, 'ARCHIVED': 4, 'VALIDATING': 1, 'PROPOSED': 1}

## 2. 哪些属于误重复 legacy import？
- (factor_name, universe) 重复的误导入行共 8 行：
  - AF_000027（rsi_filter）
  - AF_000028（macd_filter）
  - AF_000029（squeeze_adx_filter）
  - AF_000030（regime_filter）
  - AF_000031（bad_classifier）
  - AF_000032（addon_ranking）
  - AF_000033（early_exit_1.5pct）
  - AF_000034（monthly_bb）

## 3. 哪些 canonical 保留？
- AF_000001~AF_000013（首轮 legacy 导入，含信号定义/失败项/HOLD）
- AF_000014~AF_000026（Phase 0 smoke 因子）
- 补录：AF_000035 weekly_bb（Phase 0 旧 importer 曾因表达式同形被误判为 bb_z 重复而跳过，本次按 LEGACY 语义恢复 canonical 记录）

## 4. Graveyard 重复多少？
- 迁移前 ALPHA_GRAVEYARD = 8 行；其中重复 legacy 埋葬 0 行（[]）；迁移后 = 8 行。  canonical 墓地记录不变，重复行在 GOVERNANCE_EVENTS 留痕。

## 5. breadth 为什么不应在 Library？
- AF_000004 market_breadth 当前 status = VALIDATING（≠ KEEP），且未通过 multiple_testing / incremental_alpha / OOS / leakage 全门禁；ALPHA_LIBRARY 只允许 fully approved factors。已移至 ALPHA_CANDIDATES （Phase 1 特征重要性候选）。

## 6. attempt 42 的旧定义是什么？
- 旧代码 count_attempts = len(MULTIPLE_TESTING_LEDGER) = 42，全部 status=TESTED（14 个 smoke 表达式 × 3 标签），无 attempt_id、无重复/拒绝分类。
- 旧 MT CSV 只有 3 行而 parquet 42 行：旧 _save 直接写、CSV 为陈旧镜像 （Phase 0 一致性缺陷；parquet 为真实数据，未丢失）。

## 7. 新定义下各项计数（迁移完成时点）
- TOTAL_REQUEST_ATTEMPTS = 42
- TOTAL_UNIQUE_EXPRESSIONS = 14
- TOTAL_COMPUTED_HYPOTHESES = 42
- TOTAL_DUPLICATE_REQUESTS = 0
- TOTAL_REJECTED_COMPLEXITY = 0
- TOTAL_REJECTED_LEAKAGE = 0
- TOTAL_REJECTED_LOOKBACK = 0
- TOTAL_REJECTED_INPUT = 0
- TOTAL_REJECTED_SYNTAX = 0

## 8. 有没有丢失无法恢复的历史？
- 可恢复：旧 42 条 attempt 全部在 parquet canonical 中；CSV 3 行只是陈旧 镜像，重建后 = 42。
- 不可恢复：weekly_bb 在 Phase 0 从未被正确登记（旧 importer 表达式同形 误判跳过），该“当时未登记”的事实无法倒填——已补 canonical 记录并标 RESTORED_LEGACY_ITEM，原错误不假装未发生。
- 其余 legacy 项与 smoke attempt 均可从现有 parquet 完整恢复；不存在 UNKNOWN_LEGACY_ATTEMPT_COUNT 缺口。

## 8b. Phase 0 setdefault 遗留空字段回填
- Graveyard date_killed 回填 0 行（迁移日期）；Experiment timestamp 回填 1 行；MT ledger attempt date 回填 42 行；Registry canonical_expression 回填 34 行（dsl 规范化）。
全部回填在 GOVERNANCE_REPAIR_LOG.csv 留痕，不覆盖任何既有值。

## 治理事件摘要
- EXPRESSION_HASH_AMBIGUITY: 1
- FORCED_STATUS_TRANSITION: 8
- GRAVEYARD_DUPLICATE_REMOVED: 6
- REMOVED_FROM_LIBRARY_NOT_APPROVED: 1
