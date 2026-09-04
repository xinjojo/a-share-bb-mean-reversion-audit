# PHASE E0.1 — Acceptance Gate Report

> 生成日期: 2026-09-04 | Branch: etf-e0 | Commit: (pending)
> 前置: E0 complete (commit 7857545), verdict = CONDITIONAL GO
> 本阶段只处理 consistency / data integrity / interpretation，禁止优化。

---

## E0.1-A — Universe Count Reconciliation

### 问题
E0 报告中存在多个 Universe 计数，尤其 **534 (correlation return series) > 377 (unique indexes)**，需核验。

### 根因
原始相关性分析使用 **ETF-level 序列**（534 只唯一 ETF），而非 index-level 序列。
- B2 PIT 选择中 362 个指数，但 534 只唯一 ETF（115 个指数历史上有多个代表 ETF，最多 7 只）
- 同一指数因代表切换出现为多条序列，导致 pair 数虚高（109,532 → 实际应为 ~49,875）

### 修复
已重写为 **index-level 相关性**：用日频 PIT 代表选择，对每个指数拼接其当日代表 ETF 的日收益率，得到每个指数一条收益序列。

| 指标 | 原始 (ETF-level, BUG) | 修复后 (index-level) |
|------|----------------------|---------------------|
| 收益序列数 | 534 | 340 (≥250 obs) / 362 (total) |
| 计算 pair 数 | 109,532 | 49,875 |
| pairs > 0.80 | 12,237 | 2,973 |
| pairs > 0.90 | 3,060 | 596 |
| pairs > 0.95 | 719 | 136 |
| mean correlation | 0.555 | 0.487 |
| median correlation | 0.572 | 0.502 |
| P90 correlation | 0.811 | 0.751 |
| clusters @ dist 0.3 | 79 | **49** |

### 结论
**不是 universe leakage，是统计层级错误**。修复后 340 个 index-level 收益序列对应 ~49 个独立风险簇（rho>0.8），伪多样化结论仍然成立但数字已修正。

完整对账表: `results/etf/e01_universe_reconciliation.csv`

---

## E0.1-B — Audit the -56.6% Diagnostic

### 实现了什么
重新运行确认 -56.64%（与 E0 报告 -56.6% 一致）。逐项核验：

| 组件 | 实现状态 | 说明 |
|------|---------|------|
| BB(20,2) | ✓ | window=20, sigma=2.0 |
| Signal: close_adj < bb_lower | ✓ | amount>0 过滤 |
| Ranking: amount Top10 | ✓ | PIT 代表面板内按 amount 排序 |
| Execution: T+1 open | ✓ | 信号日 close → 次日 open 成交 |
| Position sizing | ✓ | K=3, max_levels=5, level_cash=200k, initial=1M |
| Exit: STRICT_C dynamic_touch | ✓ | high_adj >= Pstar, Pstar=analytic_Pstar(近19日 close_adj) |
| Slippage | ✓ | 10bp |
| Commission | ✓ | 0.025%, min 5元 |
| Stamp duty | ✓ | 0 (ETF 无卖出印花税) |
| PIT representative | ✓ | B2 ADV60(t-1) |
| Lot rounding | ✓ | 100 份取整 |
| **Tick rounding** | ✗ | **未实现** (价格未 round 到 0.001) |
| **Price limit constraint** | ✗ | **未实现** (涨停买不进/跌停卖不出未处理) |
| **Liquidity filter** | ✗ | **未实现** (未按 ADV60≥2000万 过滤) |
| Suspension | 部分 | 无数据=不可交易，但无显式停牌处理 |
| amount > 0 (execution) | 部分 | 信号时检查，成交时未显式检查 |

### 交易统计
- 总交易: 483 笔 (ENTRY 203, ADD 77, EXIT_PSTAR 201, EXIT_FINAL 2)
- 交易日志: `results/etf/e01_trade_log.csv`

### 结论
**标记为 diagnostic-only portfolio simulation**，不得描述为 E1 baseline performance。
缺失项（tick rounding、price limit、liquidity filter）在 E1 中必须实现。

---

## E0.1-C — Signal vs Position Occupancy

### 每日面板
生成 `results/etf/e01_daily_occupancy.csv`，包含：
date, eligible_count, n_signal, signal_ratio, open_positions, n_entries, n_exits, invested_pct, cash_pct

### 核心问题：68.9% 零信号日 vs 51.8% 满仓日 为何同时成立？

| 指标 | 数值 |
|------|------|
| 零信号日 (n_signal=0) | 3,404 天 (68.9%) |
| 满仓日 (invested≥99%) | 2,560 天 (51.8%) |
| **零信号且满仓日** | **1,406 天** |
| 平均持仓数 | 1.65 (K=3 max) |
| 平均日信号数 | 4.92 |

### 解释
**New signal flow ≠ existing position stock**。STRICT_C 退出机制下，持仓平均持有多日（等待 high_adj >= Pstar），因此：
- 信号日 t 产生信号 → t+1 开仓
- 持仓持续到 Pstar 触发退出（可能数日/数周）
- 在持仓期间，即使无新信号，仓位仍然存在
- 1,406 天零信号但满仓 = 旧仓尚未退出，且无新信号

这是正常的组合动态，不是 bug。

---

## E0.1-D — Signal Burst Audit

### Top 20 信号爆发日
输出 `results/etf/e01_signal_burst_dates.csv`

### Top 10

| 日期 | 信号数 | eligible | 信号比率 | 持仓数 | 新入场 | 退出 | 仓位% |
|------|--------|----------|---------|--------|--------|------|-------|
| 2025-04-07 | 266 | 278 | 95.7% | 2 | 0 | 0 | 99.99% |
| 2026-03-23 | 256 | 312 | 82.1% | 2 | 1 | 0 | 79.6% |
| 2025-01-03 | 242 | 270 | 89.6% | 2 | 0 | 0 | 99.98% |
| 2025-04-08 | 215 | 278 | 77.3% | 2 | 0 | 0 | 99.99% |
| 2023-10-23 | 210 | 240 | 87.5% | 2 | 0 | 0 | 99.98% |
| 2025-01-02 | 199 | 270 | 73.7% | 2 | 0 | 0 | 99.98% |
| 2025-11-21 | 199 | 304 | 65.5% | 2 | 0 | 0 | 90.0% |
| 2022-04-25 | 188 | 214 | 87.9% | 2 | 0 | 0 | 99.99% |
| 2022-04-26 | 185 | 216 | 85.6% | 2 | 0 | 0 | 99.99% |
| 2025-01-06 | 180 | 270 | 66.7% | 2 | 0 | 0 | 99.98% |

### 结论
信号高度集中在**系统性暴跌阶段**：
- 2022-04 (A股疫情后暴跌)
- 2023-10 (A股底部)
- 2025-01 / 2025-04 (微盘股流动性危机)
- 2026-03

信号比率 65-96% 意味着几乎整个 Universe 同时触及 BB 下轨——这是系统性风险释放，不是独立 alpha 信号。Top-N 选择在此时无法提供多样化。

**只诊断，不据此调整 BB 参数。**

---

## E0.1-E — Index Daily Completeness

### 状态
- 请求指数数: 154 (master mapping 中 unique index_code)
- 候选交易所代码: 233 (含 .SH/.SZ 双试)
- 有效代码 (存在于 index_basic_exchange): 待确认
- 已下载: 进行中（健壮可恢复脚本后台运行）
- 失败/空序列: 待下载完成后输出完整列表

### 已知问题
- 前两版下载脚本因 API 限速/进程死亡只完成 8 个文件
- 已改用健壮可恢复脚本 `e01_download_index_daily_robust.py`（增量保存、只下有效代码、可重复运行）
- **禁止 silent drop**：下载完成后将输出完整成功/失败/空序列列表

### 对 E1 的影响
- **Model 1** (ETF price signal + ETF execution): 不需要 index_daily，可立即执行
- **Model 2** (index signal + ETF execution): 需要 index_daily，下载完成后执行
- E1 先启动 Model 1，Model 2 待数据就绪

---

## E0.1-F — Freeze PIT Representative Rule

### 规则
PIT representative ETF = highest ADV60 using information available at **t-1**

### 核验
代码 `e0_signal_capacity.py` line 84:
```python
adv60 = amt.rolling(60, min_periods=20).mean().shift(1)
```
- `.shift(1)` 确保 t 日的 ADV60 使用截至 t-1 的数据
- 不包含 t 当日数据
- 无未来信息泄漏 ✓

### PIT 约束核验
- 已上市: `list_date <= date` ✓
- 未退市: `delist.isna() | (delist > date)` ✓
- 上市满 60 交易日: `n_days >= 60` ✓
- 有历史行情: fund_daily 存在 ✓
- 当日可交易: 有当日数据 ✓
- **流动性要求**: 当前未过滤（E1 加入 ADV60≥2000万）

### 结论
**PASS** — ADV60 t-1 实现正确，无未来泄漏。

---

## E0.1-G — Representative Switch Semantics

### 规则（E1 必须冻结）
如果某指数代表 ETF 从 A → B 变化：
- **已持有 A**: 继续持有并按 A 的价格/规则管理至 exit
- **新 entry**: 使用当日 PIT representative B
- 禁止 daily representative rebalance 导致旧仓被强制切换

### 当前诊断模拟的问题 ⚠️
`e0_signal_capacity.py` 中持仓按 `index_key` 跟踪（line 182），退出时（line 248）使用 `g[g['index_key'] == pos['index_key']]` 获取**当日代表 ETF** 的价格/pstar，而非实际持仓 ETF。

当代表切换时：
- 持仓是 A，但退出价格用 B → **错误**
- Pstar 用 B 的数据计算 → **错误**
- 持仓 dict 虽存储了 `etf` 字段但未使用

### 影响
- 诊断模拟（-56.6%）可能因此有偏差
- 115/362 指数有代表切换，影响范围非平凡

### E1 必须修复
- 持仓按 `(index_key, etf_code)` 唯一标识
- 退出/估值/加仓均使用实际持仓 ETF 的数据
- 新 entry 使用当日代表
- 代表切换不影响已有持仓

### 结论
**PASS WITH KNOWN LIMITATION** — 诊断模拟有代表切换 bug，E1 必须修复。不构成 BLOCK（因为 PIT universe 构建本身正确，bug 在组合模拟层）。

---

## E0.1-H — Liquidity Filter Freeze

### Registry 已冻结值
ADV60 >= 20,000,000 RMB (2000万)

### 当前状态
E0 诊断模拟**未应用**此过滤——所有 PIT 代表均 eligible，无论流动性。

### E1 必须实现
- 在 PIT 代表选择后、信号生成前，过滤 `adv60 >= 20,000,000`
- ADV60 用 t-1 数据（与代表选择一致）
- sensitivity 加测 ADV60 >= 50,000,000 (5000万)

### 流动性过滤后 Universe 预估
- ADV60 >= 2000万: ~509 只 ETF（E0 统计）
- ADV60 >= 5000万: ~437 只 ETF

### 结论
**PASS** — 阈值已冻结，E1 实现即可。

---

## E0.1 VERDICT

### **PASS WITH KNOWN LIMITATIONS**

#### 通过理由
- ✅ PIT 核心逻辑正确（ADV60 t-1 无未来泄漏）
- ✅ ETF-index mapping 完整（1400 候选 → 1137 eligible → 362 PIT indexes）
- ✅ 相关性层级错误已修复（534 ETF-level → 340 index-level）
- ✅ 信号密度/资金利用率/信号爆发诊断完整
- ✅ 无严重 future leakage
- ✅ 未触碰 shared engine，无 regression 风险

#### 已知限制（E1 必须处理，不构成 BLOCK）
1. ⚠️ 代表切换语义 bug（诊断模拟层，E1 修复）
2. ⚠️ index_daily 未完整下载（Model 2 前置，Model 1 不受影响）
3. ⚠️ 诊断模拟缺 tick rounding / price limit / liquidity filter（E1 实现）
4. ⚠️ delist_date / 跟踪指数变更 PIT 数据缺口（标注 limitation）

#### BLOCK 条件（均未触发）
- ✗ 无 materially broken PIT
- ✗ 无 materially broken ETF-index mapping
- ✗ 无 serious future leakage
- ✗ index data 不足以支持 Model 2 → Model 1 可先行
- ✗ 无 shared engine regression

---

## NEXT: E1 BASELINE FALSIFICATION

E0.1 通过，**直接进入 E1**，无需再次等待批准。

E1 执行顺序：
1. E1-0: 读取股票版冻结 baseline（从主仓库代码/Registry/结果）
2. E1 引擎: 复用股票组合引擎 + ETF adapter（lot/tick/price limit/no stamp duty/PIT rep/liquidity filter）
3. E1-1: Model 1（ETF price signal + ETF execution）— 立即执行
4. E1-2: Model 2（index signal + ETF execution）— index_daily 就绪后执行
5. E1 指标: 完整 metrics + yearly returns + common window + cluster exposure
6. E1 对比: Stock vs ETF Model1 vs ETF Model2
7. E1 最终报告 + Registry + commit/push
