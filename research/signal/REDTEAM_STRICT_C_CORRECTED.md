# REDTEAM — STRICT_C_CORRECTED（最终版）
## 主版本更名 STRICT_C_EXECUTABLE_TICK；P0 复权修正 + P1 tick + P2 归因文案 + FIX2 跌停/滑点分离
基于 commit `566db88` + 修正 `run_strict_c.py`（commit `8c479f6` 修正 P0/P1/P2；本版新增 FIX2 与命名封板）。

---

## 一、新问题确认表（外部审计 FINAL MINOR 复核）

| 审计发现 | 结论 | 证据 |
|---|---|---|
| P0 复权序列口径错误 | **CONFIRMED（影响温和）** | `x=close_adj[k]=close_raw[k]*adj_factor[k]`；Pstar_raw=Pstar_adj/adj[T]；触发改变仅 5 天(0.15%)；combo −6.49pp |
| P1 optimistic tick 不可成交 | **CONFIRMED** | optimistic 在 `Pstar<high<ceil(Pstar)` 时判触发却按未达到的更高 tick 成交 → **+65.06% 标记 INVALID_DIAGNOSTIC**，不再作为合法边界 |
| P1 主版本命名 | 更名 **STRICT_C_EXECUTABLE_TICK** | `legal_trigger=ceil(Pstar_raw/0.01)*0.01`；open≥trigger→open 成交；elif high≥trigger→trigger 成交；else 不退出。continuous Pstar 仅 NON_EXECUTABLE_REFERENCE |
| FIX2 跌停/滑点未分离 | **CONFIRMED（影响=0）** | 改为 `ref(=open 或 legal_trigger)≤跌停价→不成交`，随后 `cashflow=ref×(1−slip)`；新旧逐笔完全一致：Total diff=0.00pp、StockPnL diff=0、受影响交易=0、退出日改变=0 |
| P2 归因文案 | **CONFIRMED 文案错** | full-sample 股票腿 47.7% > ETF/现金 35.0%；仅 Test 段可说 ETF 支撑 |

> ⚠️ 首版审计曾报"触发改变 5.91%"，系审计脚本 x_old 用"固定19交易日窗口(跳停牌)"与引擎"最近19有效日"窗口不一致所致；已修正为与引擎同一批有效日后重算。

---

## 二、STRICT_C_EXECUTABLE_TICK（主执行语义，参数全部冻结）

| 版本 | Total | CAGR | MaxDD | Sharpe | Trades | 胜率 | 股票PnL |
|---|---|---|---|---|---|---|---|
| **EXECUTABLE_TICK combo（主）** | **+82.66%** | 9.60% | −37.21% | 0.49 | 97 | 67.0% | +477,062 |
| EXECUTABLE_TICK pure 股票 | **+58.20%** | 7.22% | −30.79% | 0.41 | 98 | 68.4% | +581,979 |
| ~~optimistic~~ **INVALID_DIAGNOSTIC** | ~~+65.06%~~ | — | — | — | — | — | — |
| NON_EXECUTABLE_REFERENCE（continuous Pstar） | +70.09% | 8.41% | −39.44% | 0.45 | 97 | 69.1% | +469,325 |
| 旧 STRICT_C（修正前归档） | +89.15% | — | — | — | 93 | — | +618,877 |

冻结：K=3 / Top10 / BB(20,2) / 5层×20万 / slippage=10bp / 历史印花税 / corrected涨跌停 / PIT-ST / 上市60日 / T+1 / 期末结算 / ETF 满仓(NAV 口径)。

**old vs executable**：触发改变 5 天(0.15%)；退出日期改变 5 笔；股票PnL 618,877→550,208（−68,668）；combo −6.49pp。

**FIX2 影响**：affected_exit_count=0，exit_date_changed=0，Total Return diff=0.00pp，Stock PnL diff=0 → 未展开第一代审计重跑（审计员允许：影响为0即无需）。

---

## 三、P0 影响审计（正确 old 口径）

- 评估 stock-days 3253；窗口跨 corporate action 456 天（14.0%）
- Pstar_correct−Pstar_old：mean_abs=0.489 元，median=0，max_abs=83.7 元，mean_pct=−0.30%
- 触发对照：都触发 90 / 旧触修不触 1 / 旧不触修触 4 / 都不触 3158 → **触发改变 5 天(0.15%)**
- 退出日期改变 5 笔（配对 92 笔中 87 笔同日）

---

## 四、归因（P2 修正后口径）

**FULL SAMPLE（2020-2026）**：+82.66% = 股票腿 **+47.7%** + ETF/现金 **+35.0%** → 股票 > ETF。
**TEST 2024-2026**：combo +26.73% vs pure +0.68% → ETF 贡献 ≈**+26.05pp** → 仅 Test 段可说"组合主要由 ETF 支撑"。

---

## 五、OOS 与分年（EXECUTABLE_TICK combo）

| 区间 | combo | pure 股票 |
|---|---|---|
| Train 2020-2023 | +37.79% (sh 0.45) | +29.71% (sh 0.39) |
| Test 2024-2026 | +26.73% (sh 0.46) | **+0.68% (sh 0.15)** |

分年 combo：2020 +25.4 / 2021 +26.7 / 2022 +2.1 / **2023 −15.9** / 2024 +3.4 / 2025 +30.3 / **2026 −0.9**（5正2负）

---

## 六、最终结论与评级

**文案修正后表述**：
- FULL SAMPLE：股票腿有正历史收益（+58.2% 纯股），**不能说"完全无 Alpha"**。
- 但：跨期稳定性弱（Test 后段股票腿≈0，+0.68%）、Sharpe 低（0.41 全期 / 0.15 Test）、年份不稳定（2023、2026 为负）、对退出阈值 tick 级扰动敏感。
- 2024-2026 并非 pristine OOS，仅作 Retrospective Stability Check。

**评级：D — NO EVIDENCE OF ROBUST / REPEATABLE / EXTRAPOLATABLE ALPHA**

严格限定含义："现有历史证据不足以证明该股票 Alpha 跨市场状态稳定、可重复、可外推。" 不得写成"策略完全无效"或"股票腿没有收益"。
