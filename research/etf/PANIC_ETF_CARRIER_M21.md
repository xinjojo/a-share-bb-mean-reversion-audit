# PANIC_ETF_CARRIER_M21.md — Bookkeeping / Null Hygiene Remediation

> 治理状态：M2 substantive verdict = **D — HARMFUL**（frozen gate：net total return < 0 直接触发 D），**不因本阶段重新开放**。
> M2.1 仅做 3 项 implementation/reporting hygiene 修复：①commission-aware lot sizing（消除隐性负现金）；②permutation 同年无放回；③matched estimand 清理（单次随机 draw 不再作为 primary）。
> 本阶段禁止：重新选 ETF、改 signal、改 hold、改 cost、改 threshold、改 classification、寻找盈利版本。
> 2025–2026 CLOSED。Registry: `research/etf/registries/PANIC_ETF_CARRIER_M2_REGISTRY.csv`（SHA `7ff3333e…`，冻结不变）。

---

## 1. Issue 1 — Commission-Aware Lot Sizing

**旧规则**（M2）：`qty = floor(CAPITAL / fill / lot) * lot`，之后才扣 buy commission —— 每笔按固定 100k 预算，**完全无视账户当前现金**；费用超支（每笔约 25 元）加上 2023 年连续亏损后账户现金跌破 100k 仍按 100k 买入，产生**万元级隐性杠杆**。

**修复**（M2.1）：`available_cash = 账户当前现金`（entry 日结算后）；`qty` 递减至满足

```
qty * buy_fill + max(qty * buy_fill * COMM, MIN_FEE) <= available_cash
```

且为 100 份 lot；每日机器断言 `cash >= -1e-8`。

**bridge 结果**：

| 项 | 值 |
|---|---|
| 交易笔数 | 78（与 M2 相同，无新开/丢单） |
| qty 发生变化的 trades | **76 / 78（97.4%）** |
| 旧规则账户现金最大赤字 | **−13,206.41 元**（2023 亏损期隐性杠杆；非"极小"fee 量级） |
| 旧规则预算超支（fee 量级，参考） | 24.90 元 |
| 修正后最小现金 | **+2.42 元**（从不负） |
| cash invariant | PASS（`cash >= -1e-8` 全程成立） |

> 注：旧 M2 净收益 −5.309% 中含隐性杠杆成分；修正为真实无杠杆账户后净收益为 −7.2514%（见 §5）。

## 2. Issue 2 — Permutation Without Replacement

Registry 冻结：每轮置换内，同年 eligible non-PANIC 日期**无放回**匹配。旧实现每笔独立 `rng.choice(pool)` 可能同轮重复抽取。

**修复**：对每个 calendar year（2021–2024），每轮一次性 `rng.choice(pool, size=n_y, replace=False)`，与该年实际 trades 一一配对；`pool < n_y` → STOP（invariant failure，未发生）。B=5000、seed=0 不变。

| 项 | M2（旧，有放回） | M2.1（无放回） |
|---|---|---|
| observed mean trade | −0.0683% | −0.0683% |
| null mean | −0.392% | **−0.3941%** |
| empirical p | 0.159 | **0.1452** |
| null CI（P2.5/P97.5） | [−0.972, +0.308] | [见 m21_permutation_corrected.json] |

修正后 p=0.145，仍不显著；结论方向不变。

## 3. Issue 3 — Matched Estimand Cleanup

旧报告把一次随机 matched sample 的差值 **+0.5144pp** 作为 primary matched delta —— **正式撤回（WITHDRAWN as primary evidence；descriptive only）**。

正式 matched comparison（同年分层置换 null）：

```
OBSERVED_MEAN_NET_TRADE − MEAN_OF_PERMUTATION_NULL_MEANS
= (−0.0683%) − (−0.3941%) = +0.3257pp
```

并同时报告 observed mean / null mean / permutation CI / empirical p（见 `m21_matched_estimand.json`）。稳定口径下 panic 后 5 日相对普通日仍略好，但绝对均值负、统计不显著，不构成经济优势。

## 4. Equity Ledger & Cash Invariant

- 佣金感知 sizing 后重建净 equity 曲线（`m21_equity_corrected.csv`，全精度内部计算、CSV 显示时 round）。
- **final equity = 100,000 + Σ(realized trade pnl)**：parity diff = **0.00 元**（tolerance ≤ 0.01）✓。
- 每日 `cash >= -1e-8` 机器断言 PASS。

## 5. Cost Report（正确口径）

| 指标 | 值 |
|---|---|
| **GROSS_ACCOUNT_TOTAL_RETURN**（同 trades，commission/slippage=0 的真实 gross equity 曲线） | **+12.0474%** |
| NO_SLIP_WITH_FEE 账户总收益 | +8.1876% |
| **NET_ACCOUNT_TOTAL_RETURN** | **−7.2514%** |
| 佣金总额 | ≈3,860 元（fee economic impact ≈3.86pp） |
| 滑点经济影响 | ≈15.44pp |
| SUM_OF_TRADE_GROSS_RETURNS（改名，非账户毛收益） | −1.43%（仅信息性，不再称 account gross total） |

> 关键解释：毛账户收益为正（+12.05%）——panic 后 5 日买入持有本身有正毛收益；但 10bp 单边滑点 × 双边 × 78 笔 ≈ 15.4pp + 佣金 ≈3.9pp，合计 ≈19.3pp 成本**全部吃光毛收益**。净收益为负的直接原因不是信号方向，而是高频小持仓下的成本拖累。

## 6. Corrected Metrics（commission-aware 复利账户）

| 指标 | M2（旧） | M2.1（修正） |
|---|---|---|
| net total return | −5.309% | **−7.2514%** |
| net PnL | −5,309 | **−7,251.41** |
| mean trade | −0.0683% | −0.0683%（不变：per-trade ret 与 qty 无关，非 min-fee 区） |
| median trade | −0.1633% | −0.1633% |
| win | 48.72% | 48.72% |
| profit factor | 0.93 | **0.930** |
| MaxDD | −23.25% | **−24.1339%** |
| CAGR | −1.13% | −1.48% |
| Sharpe | −0.059 | −0.064 |

逐年（M2.1）：2021 **+8.78%**（win 65%）/ 2022 **−3.47%** / 2023 **−17.35%**（win 47.4%）/ 2024 **+6.72%**；**正年份 2/4**。

## 7. Classification

沿用 M2 frozen gate（无新 gate）：net total return **−7.2514% < 0** → **D — HARMFUL**。

- 修正后结果比旧 M2 更差（−5.31% → −7.25%），差异机制明确：旧实现每笔固定 100k 预算、无视账户现金（2023 亏损期隐性杠杆峰值 −13,206 元）；修正为真实无杠杆复利账户后拖累显现。**非异常 bookkeeping 错误**（mean trade/PF/win 不变，仅账户语义修正）。
- **ETF branch CLOSED（YES）**；**blind test NO**；**参数扫描 NO**；**2025–2026 未读**。

## 8. Hard Invariants（全部 PASS）

I1 carrier=510300.SH ✓ ｜ I2 PANIC80 不变 ✓ ｜ I3 T+1 open ✓ ｜ I4 5d hold ✓ ｜ I5 non-overlap ✓ ｜ I6 100k capital ✓ ｜ I7 无负现金 ✓ ｜ I8 permutation 同年无放回 ✓ ｜ I9 B=5000 seed=0 ✓ ｜ I10 单次随机 matched delta 不作为 primary ✓ ｜ I11 无参数扫描 ✓ ｜ I12 2025–2026 CLOSED ✓

## 9. Outputs

`results/evidence/m21/`：m21_sizing_bridge.csv、m21_cash_invariant.json、m21_equity_corrected.csv、m21_equity_parity.json、m21_permutation_corrected.json、m21_matched_estimand.json、m21_metrics.json、m21_yearly.csv、m21_cost_corrected.json、m21_summary.json、m21_invariants.json
