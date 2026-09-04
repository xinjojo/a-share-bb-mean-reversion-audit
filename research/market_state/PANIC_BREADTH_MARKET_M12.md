# PHASE M1.2 — CALENDAR / CLUSTER / TAIL REMEDIATION

**DEVELOPMENT DIAGNOSTIC（WAITING EXTERNAL AUDIT）** — only 3 statistical corrections; all M1.1 definitions unchanged

- Registry: `research/market_state/registries/PANIC_BREADTH_MARKET_M12_REMEDIATION_REGISTRY.csv`
- Registry SHA256: `524ae9e43acb9101029915c40eb284e2dab5d363fe7b14878e07b8befc26b5c1`
- Prereg commit: `edef30a` (M1.2-A)；Governance: M1.2-G `39f89bd`（M1.1 B 标记 PROVISIONAL，ETF gate HOLD）
- Sample: deployable 2021–2024（899 天；panic 187 / normal 712）；2025–2026 CLOSED；无参数扫描

## 0. Parity（unchanged）

- PANIC80 = 188 / 1,110 信号日（P7/M1.1 parity ✓）
- deployable sample = 899 天（2021–2024，expanding_rank + FWD5 非 NA）✓
- **PRIMARY FWD5 delta = +0.2752pp（panic +0.326% vs normal +0.051%）parity ✓**
- FWD5 tail parity：panic n=187 / normal n=712 ✓

## 1. Fix 1 — full trading-calendar bootstrap

- Calendar = full 2020–2024 = **1212 trading days**；非 deployable 日（无 signal / warmup）只占据 calendar 位置参与抽块，不进入均值；每 replicate 沿完整日历抽 L=21 连续交易日块（B=2000, seed=0），仅对 sampled 中 frozen deployable 观测计算 mean(panic FWD5) − mean(normal FWD5)；保留 multiplicity；不重算 PANIC80。
- point 保持 = +0.2752pp ✓（浮点微差内）

| | OLD（signal-day 序列）| CORRECTED（full calendar）|
|---|---|---|
| boot mean | +0.2896 | +0.2760 |
| boot median | +0.2955 | +0.2804 |
| P2.5 / P97.5 | **[−0.2765, +0.7866]** | **[−0.2879, +0.7979]** |

**CI 仍跨 0，不改变结论**（修正后仅略变宽 0.011pp）。

## 2. Fix 2 — true trading-day clusters

- New rule：两个 PANIC 日期仅当完整交易日历索引**严格相差 1** 才同 cluster。
- **Old 96 → New 96 clusters；0 个旧 cluster 被拆分**——本数据上 signal-day 相邻与 trading-day 相邻恰好等价（每个 panic 段内 B20 signal 连续存在，无"周一 panic、周二无 signal、周三 panic"的断档）。
- cluster-first（每段仅首日，n=96）：

| | old（M1.1，normal 混入 2020）| corrected（deployable normal 2021–2024）|
|---|---|---|
| cluster-first mean | −0.226% | **−0.226%** |
| normal comparator | +0.143% | +0.051% |
| delta | −0.369pp | **−0.277pp** |

normal comparator 已与 primary 同口径（deployable 2021–2024，n=712，无 2020）。**cluster-first 仍为负（−0.277pp）**——忠实结论：**PANIC80 的 +0.28pp 日度正效应高度依赖同一 panic episode 内的重复日期**；每个恐慌段只算一次，优势消失并反转。

## 3. Fix 3 — DD5 deployable sample parity

future-5d drawdown 改用与 primary 完全相同的 deployable population（2021–2024，rank+FWD5 非 NA；panic 187 / normal 712；**无 2020 warmup normal**）：

| | old（M1.1，含 2020 normal）| corrected（deployable）|
|---|---|---|
| panic mean / median | −1.715% / −1.340% | −1.715% / −1.340% |
| normal mean / median | −1.416% / −0.952% | **−1.448% / −0.969%** |
| delta | −0.299pp | **−0.267pp** |
| panic P5 / min | −6.53% / −13.46% | −6.53% / −13.46% |
| normal P5 / min | −6.04% / −20.19% | −6.05% / −20.19% |

**panic 后 5 天平均回撤仍略深（0.27pp），但极端尾部（min −13.5% vs −20.2%）不更差**——无严重 tail deterioration。

## 4. FWD5 tail parity（unchanged）

panic mean +0.326% / median +0.539% / win 56.15% / P5 −4.78% / min −12.35%；normal mean +0.051% / win 50.14% / P5 −4.99% / min −20.19%。parity assertion PASS。

## 5. Classification（沿用 M1.1 frozen gate，无新 gate）

**B — NARROW MARKET TRANSLATION**：PANIC FWD5 point>0（+0.275pp）、2021–2024 3/4 年正（2021 +0.746 / 2022 −0.091 / 2023 +0.246 / 2024 +0.261）、tail 无严重恶化；HAC [−0.300, +0.851]、corrected bootstrap [−0.288, +0.798]、continuous slope −0.319、conditional b1 −0.213 均弱/跨 0 —— 按 gate 属 B，A 不满足。

cluster-first 为 SECONDARY robustness，不升级为 mandatory gate；但按指令最终文字忠实反映：**负的 cluster-first 表明 PANIC80 的正效应主要来自同一 panic episode 内的重复日期**。

## 6. ETF gate

**YES — WORTHY OF ONE FROZEN CARRIER TEST**（仅允许未来单独预注册一个 broad-market ETF / basket carrier 测试）。精确表述：**不得写 "ETF signal validated"**——当前证据是窄幅、统计不显著、依赖重复计数的正迹象，不足以直接构建 ETF 策略。

## 7. Invariants

I1–I10 全部 PASS；无 threshold/horizon/benchmark/rank/regression/HAC/bootstrap 参数变化；无 portfolio/ETF run；2025–2026 CLOSED。
