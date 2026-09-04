# PHASE S1.1 — CONTEMPORANEOUS BB DEPTH RANKING（同日 BB 深度排序诊断）

**阶段**：R1.4 + S1.1 — SAME-DAY SIGNAL SELECTIVITY
**状态**：DEVELOPMENT DIAGNOSTIC / WAITING EXTERNAL AUDIT
**样本**：2020-01-01 .. 2024-12-31（N=1,212 交易日硬截断）；**2025–2026 CLOSED / UNTOUCHED**
**Registry**：`research/signal/registries/SIGNAL_SELECTIVITY_S11_DEPTH_RANK_REGISTRY.csv`（SHA256 `a00c20d3...`，prereg commit `7f0f936`，先于结果）
**结果 commit**：见仓库 git log（本报告 §0）

---

## 0. 治理链

- **R1.4**（`067a443`）：接受 S1（BB threshold = **D — HARMFUL**；RSI = **C**；Sector = **N/A**）；关闭 HIGHER ENTRY K branch；开启 **CONTEMPORANEOUS BB DEPTH RANKING**。
- **S1.1-A**（`7f0f936`）：预注册冻结同日排序诊断（结果前 push）。
- 外部审计状态：**待外审**；未经外审不得写入 README CURRENT TRUTH。

---

## 1. 研究问题与区分

S1 已否定 **THRESHOLD GATING**（"等到 entry k=2.5/3.0 才买"显著有害：B25 vs B20_ONLY −2.12pp、B30 vs B25_ONLY −1.91pp，HAC/calendar CI 全 <0）。

S1 同时留下一个未决迹象：在**原始 B20 首次触发信号**中，signal-date 当天绝对深度更深的 BB_Z bin 有更高独立 expectancy（[-2,-2.5) 4.75% → [-2.5,-3) 5.15% → [-3,-3.5) 5.47%）。

本阶段只回答一个不同的问题——**CONTEMPORANEOUS RANKING**：

> 入场条件完全不变（仍为 close_adj < MA20−2·SD20，不等待更深）。同一个 signal day 出现多个 B20 候选时，signal-date 当天立即可见的 BB_Z 深度能否用于**排序**，把有限 K=3 slots 优先给"更有价值"的信号？

禁止延迟入场；禁止修改 entry/exit；禁止 RSI/MACD/sector/fundamental/news gate；禁止真实 portfolio 执行（TOP3 仅为 counterfactual diagnostic）。

---

## 2. 冻结设计（Registry 摘要）

| 项 | 冻结 |
|---|---|
| 样本 | 2020–2024 Development；B20 S1 frozen independent framework 原样复用 |
| Parity | B20 必须 exact S1 parity：n=63,785；信号集合与 `s1_episodes_B20.csv` 完全一致；entry_date 匹配率 1.0 |
| 特征 | BB_Z_SIGNAL=(close_adj−MA20)/SD20，signal-date close，仅当日可见；禁未来值 |
| 同日排序 | 按 BB_Z 升序（最负优先）；确定性分块 `n_deep=max(1,floor(0.30n+0.5))`、`n_mid=max(0,floor(0.40n+0.5))`、`n_shallow=n−n_deep−n_mid`；ties 按 ts_code 升序 |
| 分组 | DEEP30 / MID40 / SHALLOW30 |
| Collision days | signal_date 候选数 ≥4（冻结，非 ≥3/≥5/≥10） |
| TOP3 | DEPTH_TOP3（BB_Z 最深 3 只）vs AMOUNT_TOP3（frozen amount rank 前 3 只），仅 collision days，COUNTERFACTUAL ONLY |
| FIRST_HIT | days_since_first_cross==0（当前连续 BB_Z<−2 波段首日）；REPEAT_HIT >0；纯诊断 |
| 推断 | signal-day 等权；HAC maxlags=10；full-calendar moving-block bootstrap L=21 B=2000 seed=0 |
| 分类 | A：point>0 + HAC lower>0 + calendar lower>0 + ≥3/5 年正 + collision 正 + tail 无恶化 + 单日集中 ≤50%；B：point 正 + ≥3/5 年 + collision 正但一个 CI 跨 0；C：无稳定排序证据；D：更深同日 rank 稳定更差或 tail 明显恶化。仅 A/B 可进 K=3 depth-ranking portfolio test |

---

## 3. B20 Parity（I1）

引擎重跑（同一 `replay_k(2.0)`、同一 N=1,212 地平线）：

| 项 | 值 |
|---|---|
| B20 n | **63,785**（TP 61,828 / FS 1,957 / censored 102） |
| S1 B20 n | 63,785 |
| (ts_code, signal_date) 信号集合 | **完全一致**（0 / 0 mismatch） |
| entry_date 匹配率 | **1.0** |
| n_diff | 0 |

S1 与 frozen 全历史 CSV 的 287=283+4 分解（最后一日信号 T+1 2025 执行 + 4 笔地平线停牌）为 S1 已声明地平线语义，S1.1 同引擎同地平线重跑得到 exact parity。**PASS**。

---

## 4. 主结果：同日深度排序（DEEP30 vs SHALLOW30）

### 4.1 分组指标（episode-等权，独立归一化）

| 组 | n | mean | win | PF | MAE | hold(med) | mae30 | hold90 | slot(norm PnL/1000d) |
|---|---|---|---|---|---|---|---|---|---|
| DEEP30 | 19,253 | +4.66% | 74.84% | 1.64 | −10.65% | 25d | 8.61% | 3.43% | 1.431 |
| MID40 | 25,505 | +4.93% | 76.40% | 1.76 | −10.59% | 25d | 8.65% | 3.20% | 1.559 |
| SHALLOW30 | 19,027 | +4.93% | 76.55% | 1.71 | −10.87% | 24d | 9.39% | 3.30% | 1.564 |

**同日更深 30% 的候选 mean/win 均不高于同日较浅 30%（DEEP 4.66% < SHALLOW 4.93%），slot efficiency 反而略低（1.431 vs 1.564）。**

### 4.2 Primary inference（signal-day 等权）

**DEEP30 − SHALLOW30**：

- point = **−0.023 pp**（≈0）
- HAC CI [−0.529, +0.483]（跨 0）
- Calendar bootstrap CI [−0.571, +0.499]（跨 0）
- n = 1,001 signal days

### 4.3 三档单调性与 Spearman

- day-等权三档均值：DEEP30 3.58% < SHALLOW30 3.90% < MID40 4.07% —— **非单调，DEEP 最低**
- Spearman（BB_Z, return）：day-level Fisher-z 均值 **+0.003**（n=1,001 天）；pooled **−0.020**
- 同日横截面内：深度与未来收益**无单调关系、相关≈0**

### 4.4 年度稳定性

| 年 | n_days | daily delta (pp) | 方向 |
|---|---|---|---|
| 2020 | 162 | −0.512 | 负 |
| 2021 | 223 | +0.417 | 正 |
| 2022 | 208 | +0.356 | 正 |
| 2023 | 228 | −0.016 | 负 |
| 2024 | 180 | −0.575 | 负 |

**仅 2/5 年为正**（2021、2022），且 2023–2024 连续为负。

### 4.5 Collision days（候选 ≥4，K 竞争场景）

- collision days = **961 / 1,001**（96.0%），collision episodes = 63,499（99.55%）——B20 信号日几乎全部是碰撞日，正是"抢坑"场景。
- collision 内 DEEP30 − SHALLOW30：point **−0.100 pp**，HAC [−0.579, +0.379]，calendar [−0.630, +0.369] —— 方向反而为负，跨 0。

**在"同一天很多候选抢 3 个坑位"的真实稀缺场景里，优先深跌也没有任何正向证据。**

---

## 5. TOP3 Counterfactual Diagnostic（collision days，仅诊断）

| 项 | DEPTH_TOP3 | AMOUNT_TOP3 |
|---|---|---|
| n | 2,883 | 2,883 |
| ep-mean return | +3.71% | +3.62% |
| win | 69.96% | 69.23% |
| slot(norm PnL/1000d) | 1.086 | 1.034 |
| mae30 | 10.06% | 10.82% |
| hold90 | 4.16% | 4.20% |

DEPTH_TOP3 − AMOUNT_TOP3（day-等权）：point **+0.091 pp**，HAC [−0.466, +0.647]，calendar [−0.545, +0.741] —— **跨 0，无显著差异**。当日 3 个最深 vs 当日成交额前 3，独立质量基本相同。

明确标注：**COUNTERFACTUAL SIGNAL-SELECTION DIAGNOSTIC ONLY**——无共享资本、无持仓冲突、无真实 slot occupancy，不是 K=3 portfolio 回测。

---

## 6. Absolute Depth Bins（B20 原始信号日，S1 bin 复现）

| bin | n | mean | median | win | MAE | mae30 | hold90 |
|---|---|---|---|---|---|---|---|
| [-2.0,-2.5) | 49,209 | 4.75% | 5.17% | 75.89% | −10.77% | 8.87% | 3.25% |
| [-2.5,-3.0) | 11,975 | 5.15% | 5.39% | 76.04% | −10.47% | 8.88% | 3.49% |
| [-3.0,-3.5) | 2,340 | 5.47% | 5.79% | 77.56% | −10.39% | 8.55% | 3.25% |
| <-3.5 | 261 | 4.88% | 5.21% | 74.33% | −9.92% | 9.20% | 3.45% |

与 S1 完全一致（同源重跑）。**S1 的"绝对深度迹象"在 episode-等权下复现**（[-2,-2.5) 4.75% → [-3,-3.5) 5.47%）。

**关键机制解释（推断性）**：绝对深度 bin 的差异主要由**日期间效应**驱动——普跌/系统深跌日，当天所有候选的绝对深度都深，且这类日子的信号整体表现更好（与 T3 systemic-vs-isolated、F1 R01/R05 呼应）；而**同日横截面内"更深的那只"并无优势**（§4.2–4.4）。S1 绝对深度迹象 ≠ 同日排序价值。本阶段不重新测试阈值（S1 已 D）。

---

## 7. FIRST_HIT vs REPEAT_HIT（机制诊断，纯描述）

- FIRST_HIT（当日首次跌破 −2σ 即信号）：**62,472（97.94%）**
- REPEAT_HIT（信号日前已连续超卖若干日，多为入场失败重试 / ST / 停牌复牌后重触发）：**1,313（2.06%）**
- episode-等权：REPEAT mean **+8.90%** vs FIRST +4.76%（描述性）
- day-等权 FIRST − REPEAT：

| 范围 | point(pp) | HAC CI | Calendar CI | 方向 |
|---|---|---|---|---|
| all | −0.84 | [−1.98, +0.30] | [−1.90, +0.30] | 跨 0 |
| [-2.5,-3.0) | **−1.47** | [−2.75, −0.20] | [−3.04, −0.38] | **显著负** |
| [-3.0,-3.5) | −0.06 | [−2.60, +2.48] | [−1.47, +1.71] | 跨 0（n=64 天） |

**发现（方向与 S1 假设"快速一步跌深更有价值"相反）**：在 [-2.5,-3.0) bin 内，REPEAT_HIT（阴跌多日后才可执行）的 day-等权结果**显著优于** FIRST_HIT（HAC/calendar CI 上界均 <0）。但 REPEAT 样本很小（1,313，其中 bin 内 486），且其构成混杂入场失败重试/ST/停牌等路径场景，**禁止据此修改 entry**；按 Registry 仅作为描述性诊断记录，需单独预注册方可升级为可行动结论。

---

## 8. 尾部与集中度

- DEEP30 mae30 8.61% < SHALLOW30 9.39%（深组尾部反而略好）；hold90 3.43% vs 3.30%（5pp 内）→ **无 TAIL-RISK TRADEOFF**（`tail_tradeoff_flag=false`）。
- 单日集中度：max|daily delta| / Σ|daily delta| = **0.92%**（远低于 50% 门槛）——不存在单日主导。

---

## 9. 分类

| 判定项 | 值 | 通过 |
|---|---|---|
| point > 0 | −0.023 | NO |
| HAC lower > 0 | −0.529 | NO |
| Calendar lower > 0 | −0.571 | NO |
| ≥3/5 年正 | 2/5 | NO |
| Collision 方向正 | −0.100 | NO |
| Tail 无恶化 | — | YES |
| 单日集中 ≤50% | 0.92% | YES |

**分类 = C — NO STABLE RANKING VALUE**。

→ **不值得进入真实 K=3 depth-ranking portfolio test（NO）**。同日 BB_Z 相对排序无稳定横截面价值；collision 场景方向为负；TOP3 深度 vs TOP3 成交额无显著差异。

---

## 10. Invariants（全部 PASS）

| I | 描述 | 结果 |
|---|---|---|
| I1 | B20 exact S1 parity（63,785；信号集合一致；entry 匹配 1.0） | PASS |
| I2 | 无 entry threshold 改变（仍 k=2.0） | PASS |
| I3 | 无延迟入场 | PASS |
| I4 | exit STRICT_C 未变 | PASS |
| I5 | signal-date BB_Z only | PASS |
| I6 | 仅同日排序 | PASS |
| I7 | 无 RSI/MACD gate | PASS |
| I8 | 无 sector/fundamental/news | PASS |
| I9 | TOP3 诊断不改组合路径 | PASS |
| I10 | 无参数扫描 | PASS |
| I11 | 无组合 | PASS |
| I12 | 无 2025+ 读取（N=1,212 硬截断） | PASS |
| I13 | 前序 Registry SHA 未变 | PASS |

---

## 11. 治理

- **S1.1 = C — NO STABLE RANKING VALUE**（DEVELOPMENT DIAGNOSTIC，待外审）。
- 禁止：重测 entry k=2.5/3、RSI/MACD gate、sector 快照、fundamental/news、组合因子、动态阈值、ML、真实 portfolio 执行。
- 不写入 README CURRENT TRUTH（未外审）。
- 2025–2026：**CLOSED / UNTOUCHED**。
