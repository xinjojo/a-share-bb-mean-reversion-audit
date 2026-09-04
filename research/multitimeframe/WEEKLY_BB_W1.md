# PHASE W1 — MULTI-TIMEFRAME BOLLINGER DIAGNOSTIC

**DAILY B20 × REAL-TIME WEEKLY BB STATE** — DEVELOPMENT DIAGNOSTIC（WAITING EXTERNAL AUDIT）

- Phase: W1 (R1.6 开启)
- Registry: `research/multitimeframe/registries/WEEKLY_BB_W1_REGISTRY.csv`
- Registry SHA256: `30df89a59e6014271cccd718b6de010b6258d777f1688c2c8be6067504399f57`
- Prereg commit: `c8da1aa` (W1-A)
- Governance: R1.6 commit `da3581e`（接受 D1.2=C SEMANTICS AMBIGUOUS；D1 HOLD；S3 NOT START；fundamental PAUSED）
- Sample: 2020–2024 Development，frozen S1 B20 signal universe（n=63,785），2025–2026 CLOSED

---

## 1. 冻结口径（Registry 摘要）

- **实时周线（P0，无 lookahead）**：对任意交易日 T，周线状态只用 T 之前已完成自然周 + 当前周截至 T 的数据；禁止用周五最终周收盘判断周一至周四；禁止读 T 之后任何本周数据。
- **周线 bar**：weekly close = 该周最后交易日 close_adj；当前 partial week 用 T 日 close_adj。
- **weekly BB20**：前 19 个 completed weekly closes + 当前 partial close = 20 点；MA20；SD20 ddof=1；k=2；`W_BB_Z_ASOF=(close_adj_T−W_MA20_ASOF)/W_SD20_ASOF`。
- **W_LOW_TOUCH**：本周内逐日 replay（d≤T：low_adj(d) ≤ W_LOWER20_ASOF(d)），任一天成立即=1；**禁止**用"本周 min low < T 日最终 band"的后验算法。
- **Primary**：W_LOW_TOUCH=1 vs 0；signal-day 等权、同日 paired daily delta；HAC maxlags=10；full 2020–2024 trading-calendar moving block bootstrap L=21 B=2000 seed=0。
- **Secondary**：同日 W_CLOSE_Z 排序 LOW30/MID40/HIGH30；between-day 与 within-day 拆分；market confounding；monotonicity。
- 分类 A/B/C/D 全部按 Registry 冻结条件，结果前无任何改动。

## 2. Parity / Coverage

| 项 | 值 |
|---|---|
| B20 signals | 63,785（S1 exact parity ✓）|
| weekly w_z 非空 | 62,892 = **98.60%** |
| 按年覆盖 | 2020: 97.99% / 2021: 97.89% / 2022: 98.31% / 2023: 98.90% / 2024: 99.56% |

warmup（2018–2019）足以支撑 2020 首批信号的 19 周 warmup；缺失 1.4% 主要为新股上市不足 19 周。

## 3. 主结果：W_LOW_TOUCH vs NO_TOUCH

### 3.1 Episode 级（pooled，仅描述）

| 组 | n | mean return | win | PF | MAE | hold med | slot_pnl/1kd |
|---|---|---|---|---|---|---|---|
| TOUCH=1 | 5,547 (8.82%) | **7.44%** | 82.5% | 2.96 | −13.99 | 27d | 726k |
| TOUCH=0 | 57,345 | 4.58% | 75.3% | 1.62 | −12.16 | 24d | 295k |

pooled 层面 touch 看似"更好"，但这是**日期效应**（见 3.4），不是横截面价值。

### 3.2 Primary：signal-day equal-weight paired delta（同日 touch vs no-touch）

| 指标 | 值 |
|---|---|
| paired days | 648（覆盖率 99.08% 的 touch 日）|
| **paired delta（touch − no_touch）** | **−0.686 pp** |
| HAC 95% CI | [−1.421, +0.049] |
| calendar bootstrap 95% CI | [−1.442, +0.039] |

**同一天内，触过周线下轨的股票并不比同日未触轨的 B20 候选更好，点估计反而差 −0.69pp。**

### 3.3 逐年 paired delta（touch − no_touch）

| 年 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|
| day delta | −2.586 | −0.355 | −0.689 | +0.002 | −0.300 |

方向为正的年份：**1/5**（2023 仅 +0.0024pp）。

### 3.4 Between-day vs Within-day

- **BETWEEN-DAY**（日级中位 W_CLOSE_Z 拆分）：低周线日 day-mean return **5.70%** vs 高周线日 **3.13%**，差 **+2.57pp**。低周线状态的日子所有股票整体后续都更强。
- **WITHIN-DAY**（同日横截面）：
  - paired touch − no_touch = **−0.686pp**；
  - 同日 LOW30 − HIGH30 = **−0.555pp**，HAC [−1.084, −0.026]、calendar [−1.084, −0.013]（**两个 CI 全部为负**）。

结论：周线低的"收益"完全来自**普跌日期间效应**（与 S1.1 的 BB 绝对深度结论同构），同日横截面不但没有选择价值，甚至显著反向。

### 3.5 Market confounding

| 组 | 全A当日收益 mean | 全A当日收益 median | RET20 proxy mean |
|---|---|---|---|
| TOUCH | −2.00% | −1.66% | −0.30% |
| NO_TOUCH | −1.47% | −1.30% | −0.06% |

TOUCH 信号系统性集中在大盘暴跌日——直接解释 3.4 的 between-day 效应来源。

### 3.6 W_CLOSE_Z 冻结 bins（pooled，描述）

| bin | n | mean | win | MAE | slot_pnl/1kd |
|---|---|---|---|---|---|
| < −2.0 | 3,731 | 8.06% | 82.8% | −14.46 | 768k |
| [−2.0,−1.5) | 8,590 | 5.71% | 80.0% | −12.70 | 466k |
| [−1.5,−1.0) | 14,295 | 5.11% | 78.9% | −12.16 | 346k |
| [−1.0, 0) | 22,153 | 4.66% | 77.0% | −11.98 | 308k |
| ≥ 0 | 14,123 | 3.45% | 67.1% | −12.22 | 149k |

pooled 单调（越低越好），与 between-day 效应同源；不构成横截面证据。

### 3.7 Monotonicity

- pooled Spearman（W_CLOSE_Z vs return）：**−0.117**（低 z → 高 return，方向存在）
- day-level mean Spearman：**+0.028**（同日内方向反转）

与 3.4 一致：连续关系只存在于"日间"，不存在于"日内的股票选择"。

### 3.8 Tail risk

| 组 | MAE≤−10 | MAE≤−20 | **MAE≤−30** | hold>60 | hold>90 |
|---|---|---|---|---|---|
| TOUCH | 48.5% | 26.0% | **14.0%** | 10.7% | 3.3% |
| NO_TOUCH | 42.5% | 19.8% | **9.8%** | 12.5% | 3.3% |

TOUCH 组 MAE≤−30 明显恶化（+4.1pp），符合"普跌日更深的 falling-knife"特征。

## 4. 分类

**D — HARMFUL**

依据（全部为预注册冻结条件）：
1. Primary paired delta = −0.686pp < 0；
2. 逐年方向为正仅 1/5（2020–2024）；
3. 同日 LOW30−HIGH30 两个 CI 全部为负（横截面显著反向）；
4. MAE≤−30 明显恶化（14.0% vs 9.8%，+4.1pp）。

## 5. 下一步 Gate

- **W1 = D** → **不允许进入 W2**。周线 filter / weekly-trigger 结构研究不启动。
- "日线+周线共振"在 K=3 组合语境下没有横截面增量价值；其 pooled 优势已被证明为普跌日期间效应，不能转化为同日候选选择。
- 本轮未改变 daily B20 entry、未改变 STRICT_C daily exit、未运行任何组合、未打开 2025–2026。

## 6. Invariants

全部通过：B20 n=63,785 exact parity；周线特征只用 signal_date 前信息；无周五/未来周信息用于周一至周四；W_LOW_TOUCH 逐日 replay；entry/exit 未改；无组合运行；无参数扫描；无组合因子；无 fundamental 数据；2025–2026 CLOSED；前序 Registry SHA 未变。
