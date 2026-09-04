# PHASE M1 — PANIC-BREADTH → MARKET REBOUND TRANSLATION

**DEVELOPMENT DIAGNOSTIC（WAITING EXTERNAL AUDIT）** — pure market-level diagnostic

- Registry: `research/market_rebound/registries/PANIC_REBOUND_M1_REGISTRY.csv`
- Registry SHA256: `44d7c7773bc9d98cc0e40246987f2c52b5bd3b634d11b3742aec6145ac5b8900`
- Prereg commit: `661e81f` (M1-A)；Governance: R1.9 commit `1cf7b38`（接受 P7=D/M4，关闭 panic capacity expansion branch）
- Sample: 2020–2024 Development；2025–2026 CLOSED；无 portfolio run；无参数扫描

> **规格补全说明**：原指令于 D 节（PANIC80 处）截断。本阶段规格按可见意图与既有研究纪律补全并写入 Registry：benchmark=全A等权日收益（B1 MKT_RET 同口径）、horizons={5,10,20,40} 主 H=20、inference=HAC(maxlags=10)+calendar bootstrap(L=21,B=2000,seed=0)、conditional=forward ~ panic_dummy + MKT_RET、分类沿用 A/B/C/D + YES/NO/UNCERTAIN 翻译。**待外部审计确认**。

---

## 1. Breadth state

完全沿用 P7 deployable PANIC80：expanding breadth percentile（date<T only）、252 前交易日门槛、T 不进自身参考分布。**PANIC80 = 188 / 1,110 signal days（16.9%）**（与 P7 一致，2020 全年 0 panic）。

## 2. 全A等权 forward rebound（primary，signal-day equal weight）

| Horizon | PANIC 日 n | mean | NON-PANIC n | mean | **delta** |
|---|---|---|---|---|---|
| 5d | 187 | +0.431% | 919 | +0.308% | **+0.123pp** |
| 10d | 185 | +1.040% | 916 | +0.565% | **+0.475pp** |
| **20d（PRIMARY）** | 184 | +1.713% | 908 | +1.283% | **+0.430pp** |
| 40d | 181 | +3.699% | 894 | +2.966% | **+0.733pp** |

4 个 horizon 方向全正且大致随 horizon 增大（0.12→0.47→0.43→0.73pp）——**panic 日后市场整体反弹幅度略高，但幅度温和**。

## 3. Inference（H=20 primary）

| | point | SE | 95% CI |
|---|---|---|---|
| HAC（maxlags=10）| +0.430pp | 0.660 | **[−0.862, +1.723]**（跨 0）|
| Calendar bootstrap（L=21, B=2000）| mean +0.422 / median +0.436 | — | **[−0.891, +1.678]**（跨 0）|

H=10/40 同样跨 0（H=10 [−0.531, +1.480]；H=40 [−1.714, +3.179]）。**所有 horizon 的 panic 优势均统计不显著**。

## 4. Conditional（forward ~ panic + T日 MKT_RET，multivariate NW HAC）

| Horizon | b1_panic | b1 CI | b2_mkt | 说明 |
|---|---|---|---|---|
| 5 | +0.267 | [−0.375, +0.909] | +0.084 | |
| 10 | +0.396 | [−0.775, +1.568] | −0.046 | |
| 20 | **+0.368** | **[−1.206, +1.941]** | −0.037 | 控制当日市场收益后 panic 系数缩水不大（0.430→0.368），**panic 效应不完全等同于"大跌后反弹"代理**，但 CI 很宽 |
| 40 | +0.521 | [−2.306, +3.347] | −0.126 | |

## 5. 连续 breadth（H=20）——非单调

- Spearman(BREADTH_PCT, FWD20) = **−0.0097**（≈0，p=0.75）
- Quintile（B1 冻结 labels）：Q1 1.853% / Q2 1.147% / Q3 0.848% / Q4 1.407% / **Q5 1.534%**；**Q5−Q1 = −0.319pp**（负）

**关键对比**：B1 中 Q5 日期的个股 episode 平均收益最高（4.92%），但 Q5 日期的**市场** 20 日 forward 收益并不高（1.53% < Q1 的 1.85%）。B1 的 breadth alpha 主要不是"市场整体反弹"驱动，而是该日个股/横截面的选择效应。这对"breadth → 市场 ETF 转译"是弱化信号：**个股 alpha 与市场 rebound 不是一回事**。

## 6. Yearly（H=20）

2021 +1.808pp / 2022 +1.246pp / 2023 +0.422pp / **2024 −0.501pp**（2020 无 panic）→ **3/5 年为正**，但 2024 反转。

## 7. 分类

**B — NARROW REBOUND**：point 全 horizon 为正 + ≥3/5 年正（3/5）+ H=10 方向一致；但 HAC 与 calendar CI 全部跨 0，conditional 增量 CI 跨 0，连续广度非单调。

Verdict（冻结翻译规则）：**YES（WORTHY OF FUTURE PREREG）**——但必须精确表述：

- panic 日 vs 非 panic 日存在**窄幅正迹象**（+0.43pp @ H20），值得未来单独预注册一个 broad-market ETF / basket carrier 测试；
- **当前证据不足以直接构建 ETF 策略**：CI 全部跨 0、2024 年为负、连续广度无单调关系；
- B1.1 的个股 breadth alpha ≠ 市场 forward rebound（Q5 个股高收益但市场 forward 不高的对比是明确反证）；
- 未来 carrier 预注册必须同样使用 expanding PANIC80（禁 full-sample qcut）。

## 8. Invariants

I1–I7 全部 PASS；无 portfolio run；无参数扫描；2025–2026 CLOSED。
