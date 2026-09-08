# ML-BB Phase 1 Leakage Audit

- 执行时间: 2026-09-09
- seed: 2024

## 1. tests/ml_bb/test_no_future_columns.py 重跑
```
[PASS] feature 列无未来信息，全部在白名单内: ['atr_pct', 'bb_width_pct', 'bb_z', 'distance_to_lower_band', 'entry_role', 'log_amount', 'ret_5d', 'signal_id', 'turnover_rank']
[PASS] 特征来源日期 <= signal_date（merge_asof backward + 缺失率抽查）
[PASS] 标签与特征物理分离，merge 仅通过 signal_id
[PASS] universe 严格 <= 2024-12-31（2025-2026 零读取）

全部 leakage guard 测试通过 ✔

```
exit code: 0
## 2. 100 条正式 signal 抽查
- 特征列白名单: PASS
- 机器断言: 全部样本 signal_date <= entry_date（PASS）
- 抽查样本行数: 100

## 3. 结论
**Leakage Audit: PASS**
本轮特征构建未发现未来信息泄漏；任何后续特征新增必须同步更新白名单与测试。