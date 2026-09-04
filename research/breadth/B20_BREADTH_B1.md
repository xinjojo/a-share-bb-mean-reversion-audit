# PHASE B1 — B20 SIGNAL BREADTH / CROWDING DIAGNOSTIC

**DEVELOPMENT DIAGNOSTIC（WAITING EXTERNAL AUDIT）** — date-level only

- Registry: `research/breadth/registries/B20_BREADTH_B1_REGISTRY.csv`
- Registry SHA256: `1ead4b7c8b63134eb7ad84bc905868b2a5915c263b73bbc5926378f9d26c203c`
- Prereg commit: `f9825de` (B1-A)
- Governance: R1.7 commit `0c34f56`（接受 W1=D；关闭 multi-timeframe branch；开启 B1）
- Sample: 2020–2024 Development，frozen S1/S1.1 B20 universe（n=63,785）；2025–2026 CLOSED

---

## 1. 冻结口径（Registry 摘要）

- **B20_COUNT** = 每个 signal_date 的 frozen B20 candidate 数（S1 B20 episodes 按 signal_date 计数）。
- **B20_BREADTH_PCT（PRIMARY）** = B20_COUNT / 当日 PIT 合法可交易 universe size。
- **universe 分母**：list_date+60（full trade calendar 1990+）且非 PIT ST（pit_st_daily）且 bb_lower 非 NaN（BB20 warmup，warmup+main adjusted closes）——与 V2A_FROZEN_STRICT eligibility 同口径。
- **DATE 是 primary observation**；63,785 episodes 不作为独立样本做 primary inference。
- 分位：全部 1,110 个 signal days 按 BREADTH_PCT 机械五等分（qcut），边界非结果后硬编码。
- Q5−Q1：full 2020–2024 trading-calendar moving block bootstrap L=21 B=2000 seed=0（0-signal 日 breadth=0 进时间轴但无 outcome，不填 return=0）。

## 2. Parity / 基本分布

| 项 | 值 |
|---|---|
| B20 parity | 63,785 ✓ exact |
| signal days | **1,110** |
| zero-signal days | 102 / 1,212 交易日（8.4%）|
| B20_COUNT 分布 | min 1；P25 8；median 21；P75 50；max 585 |
| BREADTH_PCT 分布 | min 0.014%；P25 0.13%；median 0.48%；P75 1.53%；max 10.6%（值见 b1_daily_breadth.csv）|

## 3. 分位主表（Q1=最低 20% breadth → Q5=最高 20%）

| Q | n days | mean count | mean breadth | DAY_MEAN_RETURN | DAY_WIN | DAY_MEAN_MAE | MAE30 | hold | HOLD90 | MKT_RET |
|---|---|---|---|---|---|---|---|---|---|---|
| Q1 | 222 | 2.8 | 0.064% | **2.26%** | 65.2% | −13.70 | 12.5% | 33.1d | 4.9% | +0.80% |
| Q2 | 222 | 8.8 | 0.20% | 3.48% | 70.9% | −13.78 | 11.8% | 33.8d | 4.4% | +0.72% |
| Q3 | 222 | 20.8 | 0.48% | 3.73% | 71.4% | −13.78 | 12.0% | 33.2d | 3.6% | +0.19% |
| Q4 | 222 | 46.3 | 1.06% | 4.38% | 73.7% | −13.20 | 11.0% | 32.9d | 3.4% | −0.28% |
| Q5 | 222 | 208.6 | 4.74% | **4.92%** | 77.7% | −11.91 | **9.1%** | 31.5d | **3.1%** | **−1.51%** |

Q1→Q5 的 DAY_MEAN_RETURN **单调递增**（2.26 → 4.92）；win 率同步上升；**tail 不恶化反而改善**（MAE30 12.5%→9.1%，HOLD90 4.9%→3.1%）。

## 4. Primary inference

| 指标 | 值 |
|---|---|
| Spearman(BREADTH_PCT, DAY_MEAN_RETURN) | **+0.160** |
| rank-slope（HAC） | +0.00296；95% CI [−0.0131, +0.0190]（方向正、跨 0）|
| **Q5−Q1 point** | **+2.664 pp** |
| **Q5−Q1 calendar bootstrap 95% CI** | **[+0.335, +2.307]（显著为正）** |

## 5. 逐年稳定性

| 年 | n days | Spearman | Q5−Q1 |
|---|---|---|---|
| 2020 | 198 | +0.135 | +2.35pp |
| 2021 | 241 | +0.270 | +3.41pp |
| 2022 | 227 | +0.140 | +2.37pp |
| 2023 | 238 | +0.112 | +1.36pp |
| 2024 | 206 | +0.177 | +3.37pp |

**5/5 年方向为正**，Q5−Q1 逐年全部为正。

## 6. Market confounding & conditional increment

- 高 breadth 日 = 普跌日：Q5 日全A当日收益 mean −1.51%（Q1 +0.80%）。
- **条件回归**（唯一预注册式）：DAY_MEAN_RETURN = a + b1·rank01(BREADTH_PCT) + b2·MKT_RET：
  - **b1 = +3.283（HAC 95% CI [+3.267, +3.299]，显著为正）**——控制当日市场收益后 breadth 仍保留增量信息，**不是纯粹的 panic-day proxy**；
  - b2 = −0.259（当日越跌、未来 episode 收益越高，均值回归方向）。
- 结论：breadth 包含 strategy-native incremental information，同时与市场普跌日高度相关（两者并存，非互斥）。

## 7. K3 capture（P5/A0 诊断 join）

| Q | admitted | B20 candidates | capture rate |
|---|---|---|---|
| Q1 | 11 | 619 | 1.78% |
| Q2 | 17 | 1,962 | 0.87% |
| Q3 | 11 | 4,611 | 0.24% |
| Q4 | 19 | 10,283 | 0.18% |
| Q5 | 17 | 46,310 | **0.037%** |

**HIGH-QUALITY / LOW-CAPTURE 现象确认**：Q5 日 DAY_MEAN_RETURN 最高（4.92%）且 capture rate 最低（0.037%）——**机会最多的日子恰好是固定 K=3 捕获最差的日子**。这是未来 P7（panic-day capacity architecture）的证据基础；本轮不增加 K。

## 8. 分类

**B — NARROW BREADTH VALUE**

依据：
1. Q5−Q1 point = +2.664pp，calendar bootstrap CI lower > 0 ✓；
2. 逐年 5/5 方向正、Q5−Q1 逐年全正 ✓；
3. Q1→Q5 单调 ✓；
4. 控制 market daily return 后 b1 > 0 且 HAC 显著 ✓；
5. tail 不恶化（反而改善）✓；
6. 但 primary rank-slope HAC CI 跨 0（[−0.0131, +0.0190]）→ 未满足 A 的 (2) 条件 → **B**（NARROW，非 STRONG）。

## 9. Next gate

- B1 = B → **允许 P7（PANIC-DAY CAPACITY ARCHITECTURE）预注册**（dynamic K / basket capture / temporary capacity expansion 等需另行预注册）。
- 本轮未跑真实 portfolio、未动态调整 K、未做阈值优化、未打开 2025–2026。

## 10. Invariants

全部通过：B20 exact 63,785 parity；breadth 只用 signal-date 信息；PIT 合法 universe 分母；breadth 定义未用 outcome；date-level primary inference；无 portfolio rerun；无动态 K；无阈值优化；无新因子；2025–2026 CLOSED；前序 Registry SHA 未变。
