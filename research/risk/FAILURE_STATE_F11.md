# FAILURE-STATE INFERENCE REMEDIATION — PHASE F1.1

**状态：DEVELOPMENT / EXTERNAL AUDIT REMEDIATION — WAITING EXTERNAL AUDIT**
**F1.1-A Registry commit：`2cecd158d9719fd8a1949ef49d25f0d1b5455c20`**
**F1.1 Registry SHA256：`aacb2146308abd155401c1231209b7cab14e1bc44c50e6f19007ac39582aef91`**
**F1 Registry（冻结，未修改）：SHA256 `a052309e6f939796795566d1cd1094e2ec706f53250c231377c64efb315eef14`**
**开发样本：2020-01-01 ~ 2024-12-31（2025–2026 Confirmation 全程 CLOSED）**

---

## 0. 结论（修正统计口径后）

**FINAL classification：A — STRONG RECOVERABILITY PREDICTABILITY**（取 CLOSE 与 TOUCH 两种 recovery 语义的保守评级，二者均为 A）。

修复外部审计的三个问题后，核心发现保持稳健：**深度浮亏（D20/D30）后的失败/恢复状态，在锚点当日收盘可得的信息下具有前瞻可识别性**。CLOSE 语义下 9 个、TOUCH 语义下 11 个预注册 primary feature 通过完整修正 gate（≥2 非冗余 family，二者均为 4 个 family）。

## 1. 修复的三个问题

| Issue | 原实现 | F1.1 修正 |
|---|---|---|
| 1. 未注册的 MIN_DAY_N 过滤 | `MIN_DAY_N=5`：D20 用 355/752、D30 用 155/537 天 | **Primary day universe = 全部 anchor dates**（D20=752、D30=537），仅要求当日该 feature ≥1 个非缺失 episode；`n>=5` 降为 secondary sensitivity |
| 2. gate 用 episode-level 符号 | `dir_ok` 与 D20/D30 一致性用 episode corr | **全部改用 anchor-day day_corr**（Spearman(日均值 feature, 日均值 outcome)）；episode corr 仅作 secondary descriptive |
| 3. recover outcome 歧义 | 仅实现 future close_adj≥entry_adj | **双语义审计**：RECOVER_CLOSE（close_adj≥entry_adj）与 RECOVER_TOUCH（high_adj≥entry_adj），均从 anchor+1 日起、均 ≤2024-12-31；最终评级取更保守者 |

## 2. 修正后的 primary inference（D20）

- **聚合**：每个 anchor date 一个权重；`fx_day`=当日该 feature 均值、`oy_day`=当日 recovery 均值。
- **效应**：anchor-day Spearman + OLS(`oy ~ const + fx`)，Newey-West HAC maxlags=10。
- **BH**：m=18，p 来自 all-anchor-day HAC 回归；F_DAYS_SINCE_LOW（degenerate）p=1 保留在 m=18。
- **Bootstrap**：完整 2020–2024 交易日历（1,212 交易日）moving-block，L=21、B=2000、seed=0；每次重采样**配对** fx/oy、删除任一 NaN 日期后计算 Spearman；21 anchor-event-day blocks 仅作 sensitivity。
- **Gate**（D20）：方向=day_corr sign 与注册一致；BH q<0.05；calendar bootstrap CI 在注册方向排除 0；beta sign 与 day_corr 一致；D30 anchor-day day_corr 与 D20 同向。

## 3. Base rates — 双 outcome 语义（f11_base_rates.csv）

| 锚点 | episodes | anchor days | RECOVER_CLOSE | RECOVER_TOUCH | FINAL_PROFIT | median t_close | median t_touch |
|---|---|---|---|---|---|---|---|
| D10 | 26,914 | 958 | 31.1% | 41.7% | 54.0% | 9 天 | 9 天 |
| D20 | 12,590 | 752 | **12.1%** | **16.5%** | 36.7% | 11 天 | 11 天 |
| D30 | 6,130 | 537 | **7.8%** | **10.9%** | 30.6% | 14 天 | 13.5 天 |

（原 F1 的 12.1% / 7.8% 为 **RECOVER_CLOSE** 语义；TOUCH 语义下恢复率略高。）

## 4. CLOSE gate（f11_gate_close.csv）— classification A，9 个 FULL_PASS

| feature | family | day_corr | BH q | calendar boot CI |
|---|---|---|---|---|
| F_DAYS_SINCE_FIRST_D10 | PRICE_PATH | −0.175 | 0.000137 | [−0.264, −0.085] |
| F_DAYS_UNDERWATER | POSITION | −0.160 | 0.000137 | [−0.244, −0.075] |
| F_DAYS_SINCE_ENTRY | PRICE_PATH | −0.147 | 0.000175 | [−0.230, −0.063] |
| F_INTRADAY_RANGE | VOLATILITY | +0.269 | 0.0013 | [0.192, 0.344] |
| F_REB3 / F_REB5 | RECOVERY | +0.164 | 0.0013 | [0.091, 0.239] |
| F_ATR20_PCT | VOLATILITY | +0.171 | 0.0076 | [0.088, 0.252] |
| F_RV20 | VOLATILITY | +0.136 | 0.0129 | [0.044, 0.221] |
| F_RET20 | PRICE_PATH | −0.157 | 0.0381 | [−0.243, −0.071] |

pass families = {PRICE_PATH, POSITION, RECOVERY, VOLATILITY}（4 个）。

## 5. TOUCH gate（f11_gate_touch.csv）— classification A，11 个 FULL_PASS

多出 F_DIST_MA20（−0.206, q=0.0005）与 F_RET5（−0.184, q=0.010）；其余同 CLOSE。pass families 同 4 个。

## 6. 保守最终评级

CLOSE=A、TOUCH=A → **FINAL = A**。

## 7. F_AMT_RATIO20 — primary-unit bug 修复验证

| 语义 | D20 episode corr | D20 day corr | D30 episode corr | D30 day corr | 旧 gate 一致性 | 修正后一致性 |
|---|---|---|---|---|---|---|
| CLOSE | −0.064 | −0.053 | −0.029 | +0.005 | True（错误） | **False** |
| TOUCH | −0.073 | −0.073 | −0.015 | −0.002 | True | True（但 bootstrap CI 跨 0，boot_ok=False，仍不 pass） |

修正后 F_AMT_RATIO20 在 CLOSE gate 因 D30 day_corr 反向（+0.005）不再通过 d30_consistent；在 TOUCH gate 因 bootstrap CI 跨 0 不通过。**证明旧 primary-unit bug 已修复，且该 feature 不再被误判为 pass。**

## 8. 原 13 个 passer 在修正口径下的保留

原 F1（episode-level gate）13 个 passer → 修正后 CLOSE 9 个、TOUCH 11 个。掉出的主要为：F_DIST_MA20（CLOSE 下 q=0.087）、F_RET3/F_RET5（CLOSE 下 q=0.28/0.16）、F_AMT_RATIO20（方向/CI 不达标）。核心 family 结构（PRICE_PATH×POSITION + VOLATILITY + RECOVERY）在两个语义下均保留。

## 9. MIN_DAY_N≥5 sensitivity（f11_min5_sensitivity.csv，secondary）

D20 方向一致性 17/18（仅 degenerate F_DAYS_SINCE_LOW 为 False）、D30 方向一致性 17/18（CLOSE）/16/18（TOUCH）。`n>=5` 过滤会使 day_corr 数值变大（如 F_ATR20_PCT 0.171→0.369），但**不改变任何 direction**，不改变结论。

## 10. D30 strengthening（f11_d30_sensitivity_*.csv，报告性，非硬门槛）

D30 anchor-day day_corr 与 D20 方向一致性在 gate 中全部通过；但 D30 全部 anchor-day HAC p 无一 <0.05（D30 仅 537 天、day-level 更稀疏），故 strengthening q 计数为 0。按预注册规则不作为 primary 门槛，如实报告。

## 11. Sanity checks（全部 PASS）

A. D20 total anchor dates = 752（等于 base population，无 episode-count 过滤）；B. D30 = 537；C. primary 无 MIN_DAY_N；D. gate 方向用 day_corr；E. bootstrap 配对 fx/oy；F. bootstrap 用完整交易日历 21 日 block；G. BH m=18；H. 2025+ 未读（锚点/outcome/特征全部 ≤2024-12-31）；I. F1 冻结 Registry SHA 不变（`a052309e...`）；J. 未新增 feature/stop/exit。

## 12. 禁止事项重申

无新 feature、无 stop、无 exit 修改、无 threshold 搜索、无 ML/composite；F1 Registry 保持 frozen；2025–2026 全程 CLOSED。

## 13. 交付物

```
research/risk/registries/FAILURE_STATE_F11_INFERENCE_REGISTRY.csv (+ .sha256, commit 2cecd15)
research/risk/failure_state_f11.py
research/risk/FAILURE_STATE_F11.md
results/evidence/f11/f11_base_rates.csv
results/evidence/f11/f11_all_anchor_day_effects_close.csv / _touch.csv
results/evidence/f11/f11_bh_close.csv / f11_bh_touch.csv
results/evidence/f11/f11_calendar_bootstrap_close.csv / _touch.csv
results/evidence/f11/f11_d30_sensitivity_close.csv / _touch.csv
results/evidence/f11/f11_gate_close.csv / f11_gate_touch.csv
results/evidence/f11/f11_min5_sensitivity.csv
results/evidence/f11/f11_outcome_semantics_comparison.csv
results/evidence/f11/f11_summary.json
```
