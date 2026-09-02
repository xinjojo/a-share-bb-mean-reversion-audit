# REDTEAM — STRICT_C_CORRECTED
## P0 复权口径修正 + P1 tick 双边界 + P2 归因文案修正
Commit: `566db88` 基础上修正 `run_strict_c.py`，本报告为 CORRECTED 重跑结果。

---

## 一、新问题确认表

| 外部审计发现 | 确认/反驳 | 证据 |
|---|---|---|
| P0 复权序列口径错误（raw_hist 存 close_raw×adj[T]） | **CONFIRMED** | `run_strict_c.py` 修正前 `x = np.array(list(hist)[-19:]) * adjT`（hist 存 close_raw），改为各日 `close_adj[k]=close_raw[k]*adj_factor[k]` 后 `x = np.array(list(hist)[-19:])` |
| P0 实际影响 | **CONFIRMED 但影响小** | 评估 3253 stock-days，窗口跨 corporate action 456 天(14.0%)；触发改变仅 5 天(0.15%)；combo −6.49pp |
| P1 tick=0.01 未处理 | **CONFIRMED** | 新增 conservative(ceil, 主)/optimistic 双边界；tick 级扰动对收益敏感（65.1%~82.7%） |
| P2 归因文案（full-sample 称 ETF 为大头） | **CONFIRMED 文案错误** | full-sample 股票腿 47.7% > ETF/现金 35.0%；仅 Test 段可说 ETF 支撑 |

> 首轮审计曾出现"触发改变 5.91%"的夸大数字，系审计脚本 x_old 用"固定19交易日窗口(跳停牌)"与引擎"最近19有效日"窗口不一致所致；已修正为与引擎同一批有效日后重算。

---

## 二、STRICT_C_CORRECTED（复权修正 + tick conservative 主结果）

| 版本 | Total | CAGR | MaxDD | Sharpe | Trades | WinRate | StockPnL |
|---|---|---|---|---|---|---|---|
| CORRECTED combo (conservative) | **+82.66%** | 9.60% | −37.21% | 0.49 | 97 | 67.0% | +477,062 |
| CORRECTED combo (optimistic) | +65.06% | 7.92% | −34.06% | 0.43 | 97 | 68.0% | +522,941 |
| CORRECTED combo (tick=none 对照) | +70.09% | 8.41% | −39.44% | 0.45 | 97 | 69.1% | +469,325 |
| CORRECTED pure (conservative) | **+58.20%** | 7.22% | −30.79% | 0.41 | 98 | 68.4% | +581,979 |
| old STRICT_C（修正前，归档） | +89.15% | — | — | — | 93 | — | +618,877 |

参数完全冻结：K=3 / Top10 / BB(20,2) / 5层×20万 / slippage=10bp / 历史印花税 / corrected涨跌停 / PIT-ST / 上市60日 / T+1 / 期末结算 / ETF 满仓(NAV 口径)。

**old vs corrected 差异（复权修正影响）**：
- 触发改变：仅 5 个评估日（0.15%）
- 退出日期改变：5 笔（配对 92 笔，87 笔同日退出；退出日差 mean −11.8 交易日，median −2）
- 股票已实现 PnL：618,877 → 550,208（−68,668）
- combo 收益：+89.15% → +82.66%（**−6.49pp**）

结论：P0 复权修正真实存在但影响温和，未推翻旧 STRICT_C 量级。

---

## 三、P0 影响审计（正确口径）

- 评估 stock-days：3253
- 窗口内 adj_factor 变化：456 天（14.02%）
- Pstar_correct − Pstar_old：mean_abs=0.489 元，**median=0**，max_abs=83.69 元，mean_pct=−0.30%
  （多数评估日两口径完全一致；差异集中于跨除权除息窗口）
- 触发对照（旧 vs 修正）：都触发 90 / 旧触修不触 1 / 旧不触修触 4 / 都不触 3158；触发改变 5 (0.15%)

---

## 四、P1 tick 敏感性（保守/乐观边界）

| 口径 | 触发阈值 | 成交价 | Total |
|---|---|---|---|
| conservative（主） | ceil(P\*_raw/0.01)×0.01 | open≥阈值→open；否则阈值 | +82.66% |
| optimistic | P\*_raw（理论临界） | open≥P\*→open；否则 ceil(P\*) | +65.06% |
| none（连续对照） | P\*_raw | P\*_raw | +70.09% |

→ 退出阈值在 tick 级（0.01 元）扰动下，组合收益波动约 ±9pp（65~83%）。策略对退出触发阈值敏感，主结果采用 conservative（自洽合法）。

---

## 五、归因（P2 修正后口径）

**FULL SAMPLE（2020-2026）**：
- 组合 +82.66% = 股票腿已实现 PnL **+47.7%** + ETF/现金 **+35.0%**
- 股票腿 > ETF 贡献 → **不能说"full-sample 大头来自 ETF"**

**TEST 2024-2026**：
- combo +26.73% / pure 股票 +0.68% → ETF 贡献 ≈ **+26.05pp**
- **仅 Test 阶段可说"组合收益主要由 ETF 支撑"**（股票腿样本外≈0）

---

## 六、OOS 与分年（corrected combo, conservative）

| 区间 | combo | pure 股票 |
|---|---|---|
| Train 2020-2023 | +37.79% (sh 0.45) | +29.71% (sh 0.39) |
| Test 2024-2026 | +26.73% (sh 0.46) | **+0.68% (sh 0.15)** |

分年（combo）：2020 +25.4% / 2021 +26.7% / 2022 +2.1% / **2023 −15.9%** / 2024 +3.4% / 2025 +30.3% / **2026 −0.9%**（5 正 2 负）

---

## 七、结论与评级

修正后 STRICT_C 表现：
- full sample 纯股有一定收益（+58.2%，CAGR 7.2%，Sharpe 0.41）
- **但 Test 段股票腿≈0（+0.68%，Sharpe 0.15）**
- 年份不稳定（2023、2026 为负）
- 对 tick 级退出阈值敏感（65~83%）

符合外部审计预设的 **D / NO EVIDENCE 候选** 标准。非 NEW MATERIAL FINDING（修正前后量级一致，仅 −6.5pp）。

评级交外部审计最终确认。
