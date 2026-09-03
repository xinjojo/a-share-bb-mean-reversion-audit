# FAILURE-STATE TAXONOMY / DEEP-MAE RECOVERABILITY — PHASE F1

**状态：DEVELOPMENT DIAGNOSTIC — WAITING EXTERNAL AUDIT**
**Registry commit：`1de126b3cc6e85a0548113c397c5cb1f6bfd7130`（F1-A）**
**Registry SHA256：`a052309e6f939796795566d1cd1094e2ec706f53250c231377c64efb315eef14`**
**开发样本：2020-01-01 ~ 2024-12-31（2025-2026 Confirmation 全程 CLOSED）**

---

## 0. 一句话结论（classification：**A — STRONG RECOVERABILITY PREDICTABILITY**）

当一笔 BB 交易首次达到 adjusted-space 深度浮亏（D20 / D30）时，**锚点当日收盘可得的信息可以前瞻性地、显著地区分"仍会均值回归"与"已进入失败状态"**：18 个预注册 primary feature 中有 13 个通过完整 gate（方向、BH q<0.05、配对 block-bootstrap CI 排除 0、D20/D30 方向一致），覆盖 ≥2 个非冗余 family。最强的 prospective 信号是"浮亏的深度×时长"（days underwater / days since first D10 / dist MA20）与"波动率"（ATR20_PCT / intraday range / RV20）。

**但本轮不构成任何止损/卖出规则。** 只证明"失败/可恢复是前瞻可识别的"，不设计交易动作。

---

## 1. 研究问题

已冻结事实：
- deep-MAE / 长持仓是 BB 组合主要尾部风险来源（P4 / P4.1）；
- simple fixed-percentage stops (-10%…-40%) 已正式证明整体有害（S0 / S0.1，11/11 paired CI<0）。

因此问题不是"止损放多少"，而是：

> 在首次达到 adjusted-space MAE ≤ -10% / -20% / -30%（D10 / D20 / D30 anchor）的时刻，
> 仅用锚点当日及以前可得的信息，能否前瞻地区分 RECOVERED vs FAILED？

## 2. 方法（严格预注册，frozen）

- **样本**：frozen SECONDARY V2A 独立 episodes，`signal_date` 与 `exit_date` 均 ≤ 2024-12-31（61,828 笔，与 frozen fullmarket dev 完全一致，re-record mismatch=0）。
- **Anchor**：持有期内首次 adjusted low ≤ entry_adj×(1-thr)（D10/D20/D30）。这是**固定观察锚点，不是止损**。
- **Outcome**：
  - `RECOVER_TO_ENTRY`：锚点后最终 close_adj ≥ entry_adj（自然退出前）；
  - `FINAL_PROFIT`：episode 最终 return > 0；
  - 时间：`time_to_breakeven`、`future_adverse`（锚点后再创新低幅度）。
- **信息集（锚点收盘可得）**：18 个 primary feature（6 个 family）+ 3 个 secondary（R01/R05/layer），全部冻结于 Registry，公式与 Registry 一致，**禁止根据结果翻转方向**。
- **统计推断**：episode-level Spearman/point-biserial 作为效应；anchor-day 聚合（同日 episodes 先聚合）做 day-level Spearman + HAC（lag=10）回归 p + 配对 block bootstrap（L=21, B=2000, seed=0）CI；BH-FDR **m=18**。
- **红线**：无新 stop、无 exit 修改、无阈值扫描、无 ML/composite；2025-2026 数据未读取（硬编码 `i<N2024`，锚点与 outcome 全部 ≤2024-12-31）。

## 3. 样本规模

| 锚点 | episodes | anchor days |
|---|---|---|
| D10 (≤-10%) | 26,914 | 958 |
| D20 (≤-20%) | 12,590 | 752 |
| D30 (≤-30%) | 6,130 | 537 |

（与 frozen fullmarket dev 的 27,312 / 13,050 / 6,537 数量级一致；微小差异来自 entry 基准 = `entry_raw × entry_adj_factor` 的 re-record 口径。）

## 4. 基础恢复率（f1_base_rates.csv）

| 锚点 | recover_to_entry | final_profit | median 回本天数 | median 最终 return |
|---|---|---|---|---|
| D10 | 31.1% | 54.0% | 9 天 | +0.76% |
| D20 | 12.1% | 36.7% | 11 天 | -3.75% |
| D30 | 7.8% | 30.6% | 14 天 | -8.01% |

**跌得越深，可恢复比例越低、最终亏损越确定** —— 这是本 taxonomn 的基线事实。

## 5. 锚点后再创新低（f1_future_adverse_excursion.csv）—— 最重要的风险量化

| 锚点 | n | p50 | p75 | p90 | p95 | mean |
|---|---|---|---|---|---|---|
| D20 | 12,590 | -7.51pp | -2.13pp | 0.00 | 0.00 | -10.34pp |
| D30 | 6,130 | -6.16pp | -1.71pp | 0.00 | 0.00 | -8.28pp |

解读：**跌到 -20% 后，约 90% 的样本还会再创新低；其中一半再跌 ≥7.5pp（典型触底约 -27.5%）**。这从机理上解释了为何固定止损"看似有用实则有害"（过早切断正在恢复的均值回归路径），也量化了 deep-MAE 后续的真实尾部。

## 6. 恢复时间（f1_recovery_timing.csv）

| 锚点 | 回本样本 | 从未回本 | 回本样本中位天数 | p90 |
|---|---|---|---|---|
| D20 | 1,523 | 11,067 | 11 天 | 26 天 |
| D30 | 480 | 5,650 | 14 天 | 26 天 |

## 7. 单变量预测能力（D20 primary，f1_anchor_day_inference.csv / f1_predictability_gate.csv）

BH m=18。通过完整 gate（方向 + q<0.05 + 配对 block-bootstrap CI 排除 0 + D20/D30 同向）的 13 个 feature：

| feature | family | 方向 | episode corr | day corr | HAC p | BH q | boot CI |
|---|---|---|---|---|---|---|---|
| F_DAYS_UNDERWATER | POSITION | NEG | -0.353 | -0.343 | 0.017 | 0.028 | [-0.539, -0.220] |
| F_ATR20_PCT | VOLATILITY | POS | +0.344 | +0.369 | 0.010 | 0.028 | [0.256, 0.544] |
| F_DAYS_SINCE_FIRST_D10 | PRICE_PATH | NEG | -0.322 | -0.358 | 0.014 | 0.028 | [-0.563, -0.221] |
| F_DAYS_SINCE_ENTRY | PRICE_PATH | NEG | -0.319 | -0.321 | 0.022 | 0.031 | [-0.518, -0.191] |
| F_INTRADAY_RANGE | VOLATILITY | POS | +0.321 | +0.313 | 0.023 | 0.031 | [0.231, 0.469] |
| F_DIST_MA20 | PRICE_PATH | NEG | -0.317 | -0.347 | 0.005 | 0.028 | [-0.546, -0.217] |
| F_RET5 | PRICE_PATH | NEG | -0.305 | -0.277 | 0.011 | 0.028 | [-0.465, -0.147] |
| F_RET20 | PRICE_PATH | NEG | -0.298 | -0.355 | 0.009 | 0.028 | [-0.538, -0.228] |
| F_RV20 | VOLATILITY | POS | +0.305 | +0.327 | 0.011 | 0.028 | [0.201, 0.512] |
| F_RET3 | PRICE_PATH | NEG | -0.246 | -0.254 | 0.017 | 0.028 | [-0.415, -0.116] |
| F_REB3 / F_REB5 | RECOVERY | POS | +0.138 | +0.192 | 0.007 | 0.028 | [0.106, 0.317] |
| F_AMT_RATIO20 | LIQUIDITY | NEG | -0.064 | -0.165 | 0.013 | 0.028 | [-0.236, -0.039] |

未通过：
- F_CUR_MAE（q=0.123）：**MAE 深度本身不显著** —— 预测力来自"下跌的深度×时长×形态"，而非单一的当前浮亏幅度；
- F_DIST_LBB（q=0.182）、F_DIST_AVGCOST（q=0.229，且 D30 反向）；
- F_NLOW10：观测方向（+0.129）与预注册 NEGATIVE 相反 → dir fail（未翻转、不 pass）；
- F_DAYS_SINCE_LOW：**degenerate（恒 0，实现审计发现，见 §10）**。

## 8. 家族冗余与独立维度（诚实收敛）

通过 family：PRICE_PATH（7 个）、VOLATILITY（3 个）、RECOVERY（2 个）、POSITION（1 个）、LIQUIDITY（1 个）。

预注册 gate（≥2 非冗余 family 通过）→ **A** 成立。但必须明确：
- PRICE_PATH 内 7 个高度相关（"下跌时长×深度"是一个维度）；F_REB3 与 F_REB5 数值完全相同（冗余）；VOLATILITY 内 3 个高相关（f1_redundancy 见 f1_quintiles/fe 内部一致性）。
- 因此**真正稳健的独立维度约为 3 个**：① 浮亏深度×时长（PRICE_PATH/POSITION）；② 波动率（VOLATILITY）；③ 量能/放量（LIQUIDITY）。RECOVERY 反弹力度为一个弱独立增量。
- **不可把 13 个显著 feature 表述为 13 个独立发现。**

## 9. 市场状态 overlay（secondary，描述性，f1_market_state.csv）

| R01 quintile（ret60_ea） | D20 recover_to_entry | D30 recover_to_entry |
|---|---|---|
| Q1 最弱市场 | **15.73%** | **9.20%** |
| Q2 | 2.26% | 0.00% |
| Q3 | 3.22% | 0.00% |
| Q4 | 4.25% | 0.61% |
| Q5 最强市场 | 3.63% | 0.00% |

| R05 quintile（limit-down share） | D20 | D30 |
|---|---|---|
| Q1 无压力 | 4.39% | 6.65% |
| Q5 压力最大 | **17.79%** | **10.10%** |

解读：**弱市场 / 有系统性压力中的 deep-MAE 恢复率远高于强市场中的"孤立超跌"**。这与 T3"systemic vs isolated oversold"主题在 recovery 维度上形成独立呼应（R01 q1 vs q5 恢复率差 ~4 倍）。

## 10. 实现审计发现（不改 Registry，不影响结论）

1. **F_DAYS_SINCE_LOW degenerate**：由于 anchor 定义为"首次达到 threshold 的最低点"，20-obs 窗口内最低点必然是 anchor 日本身 → 该 feature 恒为 0、无变异、corr=NaN。属特征构造与 anchor 定义的自然冲突，非选择偏差。Registry 保持 frozen（其 BH q=1.0，不影响 m=18 门控与结论）。
2. **F_NLOW10 方向与预注册相反**：观测为 POSITIVE（10 日内新低越多 → 恢复率略高）。按要求未翻转方向，dir fail 不 pass。
3. Registry CSV 公式含逗号，解析改用 csv 语义（`pandas.read_csv`），方向列读取正确。

## 11. layer 与恢复（描述性，f1_layer_recovery.csv）

| D20 layer count | recover_to_entry | final_profit |
|---|---|---|
| 1 | 24.4% | 49.2% |
| 3 | 13.9% | 46.5% |
| 5 | 3.3% | 12.7% |

加仓越多恢复率越低 —— 含强路径依赖（加仓多=跌得久仍持有），**仅描述，不改 layers**（P4 已证明"完全去加仓"同样有害）。

## 12. 结论与边界

- 分类：**A — STRONG RECOVERABILITY PREDICTABILITY**（预注册 gate：≥2 非冗余 family 通过完整 gate；实际 4-5 family 通过，收敛到 ~3 独立维度）。
- **禁止措辞**：不得据此设计"止损/卖出/failure score"；本阶段只判断 failure/recoverability 是否前瞻可识别。
- **未决问题**（供后续外部审计决定）：即使可前瞻识别，由于 S0 已证明简单固定止损有害、P4 已证明架构约束主导组合结果，这些 prospective 信息如何转化为**不损害均值回归路径**的行动仍是开放问题——不在本轮范围。

## 13. 交付物

```
research/risk/failure_state_f1.py
research/risk/FAILURE_STATE_F1.md
research/risk/registries/FAILURE_STATE_F1_REGISTRY.csv  (+ .sha256, commit 1de126b)
results/evidence/f1/f1_base_rates.csv
results/evidence/f1/f1_anchor_episodes.csv      (45,634 行 anchor 明细)
results/evidence/f1/f1_feature_effects.csv      (D10/D20/D30 × 21 features)
results/evidence/f1/f1_quintiles.csv
results/evidence/f1/f1_anchor_day_inference.csv (D20 day-level + HAC + BH)
results/evidence/f1/f1_bootstrap.csv            (boot CI 列含于 inference/gate)
results/evidence/f1/f1_winner_loser_effects.csv
results/evidence/f1/f1_future_adverse_excursion.csv
results/evidence/f1/f1_recovery_timing.csv
results/evidence/f1/f1_layer_recovery.csv
results/evidence/f1/f1_market_state.csv
results/evidence/f1/f1_predictability_gate.csv
results/evidence/f1/f1_summary.json
```

## 14. 红线复核

- 未创建/修改任何 stop、exit、threshold、ranking、gate、ML；
- 未读取任何 2025-2026 数据（锚点、outcome、feature、market series 均 ≤2024-12-31）；
- 未修改历史 Registry / CSV / commit；
- 未进入 T3/P4 后续研究。
