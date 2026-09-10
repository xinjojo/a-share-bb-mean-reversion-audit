# ALPHA FACTORY PHASE 1 REPORT — DUAL-ENGINE ALPHA DISCOVERY

- Experiment: AFE_20260910_0004（Phase 1 正式结果；记账见 MULTIPLE_TESTING_LEDGER）
- Governance baseline: Commit 1a7db3f（Phase 0.1 GOVERNANCE PASS）
- Phase 1 Commit A（Registry/manifest/schema 冻结）: 19b188a
- Universe: A（BB-CONDITIONAL，SIGPATH canonical 157,469 signals，剔除 censored 3,136）
- Labels: Y_RETURN = D20 close return（回归）；Y_RISK = D20 MAE（风险回归）
- 时间隔离: Train 2020–2022 / Validation 2023（选型）/ Final Test 2024（只开一次）。2025–2026 零读取。

---

## 1. 结论摘要

- **收益预测（Y_RETURN）**：训练期（disc_ic 0.02~0.37）信息看似很强，但 2023 validation 全部≈0（最好 +0.004），2024 OOS 全部为负（-0.039 ~ +0.035，24 规格中 22 个为负）。Label permutation null（200 次）显示真实模型 2023 val RankIC=0.0040 落在 null 分布的 **48.5% 百分位**——与乱标签模型无差异。**结论：在本特征集与冻结模型规格下，机器学习没有学到可外推的 D20 收益排序信息。**
- **风险预测（Y_RISK）**：每日横截面 Spearman（按 signal_date 聚合）在 2023 val 0.22~0.26、2024 test 0.22~0.28，选型模型（ridge/REGULARIZED）逐年 2021=0.268 / 2022=0.209 / 2023=0.220 / 2024=0.233 稳定为正——**模型能稳定预测"D20 潜在亏损幅度"的横截面排序（坏单避让信号），但这是风险度量，不是收益 Alpha。**
- 但注意：全体样本 raw Spearman（跨日混合）在 2024 明显衰减（ridge 0.004、树模型为负）——模型预测的是**当日相对风险**而非绝对风险水平；且 incremental 检验显示 full_ml 并不优于简单线性 baseline（Y_RISK baseline val 0.233 vs full 0.220）。
- **Symbolic Engine**：300 条全部合法求值，discovery pass 113，全家族 BH-FDR（q=0.10）后 110 条。FDR 通过组的 val_ic 中位数 0.0185、test_ic 中位数 0.0199，但方向不单调、top 因子 OOS 衰减明显（例：diff(distance_to_lower_band, log_amount) 2023 val=0.1146 → 2024 test=-0.0164）。
- **多模型一致性**：收益维度四个模型族一致失败（2024 全负）；风险维度一致为正——模型间一致，但收益结论是否定的。
- **无过拟合迹象的正面证据**：5 个随机噪声特征的重要性长期≈0（max importance 0.00012），模型没有把噪声当信号。
- **Phase 1 评级：C** — 训练/Validation 存在信息，2024 OOS 明显衰减（收益完全失败；风险维度仅横截面排序稳定但无增量、绝对水平不可靠）。不足以支持进入 Universe B 全 A 股机器学习或任何组合使用。

---

## 2. Engine M 详细结果

### 2.1 模型规格（Commit A 冻结，4 家族 × 3 variants × 2 labels = 24）

| family | variants | 备注 |
|---|---|---|
| M0 ridge | alpha 10 / 1 / 100 | 线性基线，需 impute+scale |
| M1 RF | depth 4/6/3, leaf 50/25/100, mf 0.5/0.6/0.4 | 需 impute |
| M2 XGB | depth 3/5/3, lr 0.05/0.05/0.03, mcw 20/10/50 | 原生缺失 |
| M3 LGB | 同 XGB 档 | 原生缺失 |

### 2.2 选型（按 2023 validation，2024 未参与）

- Y_RETURN 选定：**rf/SMALL**（val RankIC=0.0040，test=-0.0259）
- Y_RISK 选定：**ridge/REGULARIZED**（val 每日 Spearman=0.2198，test=0.2327；raw Spearman val=0.337、test=0.0045）

### 2.3 24 规格全表（phase1_ml_model_summary.csv）

Y_RETURN 2024 test RankIC：ridge -0.009/-0.013/-0.012；rf -0.026/-0.027/+0.035；xgb -0.039/-0.031/-0.029；lgb -0.016/-0.016/-0.038。**22/24 为负。**

Y_RISK 2024 test 每日 RankIC：ridge 0.232/0.232/0.233；rf 0.265/0.246/0.259；xgb 0.257/0.216/0.264；lgb 0.267/0.227/0.276。**24/24 为正。**

### 2.4 Walk-forward 逐年（选定模型，phase1_ml_yearly.csv）

| target | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|
| Y_RETURN (rf/SMALL) | 0.154 | 0.109 | 0.004 | -0.026 |
| Y_RISK (ridge/REGULARIZED) | 0.268 | 0.209 | 0.220 | 0.233 |

Y_RISK 逐年稳定；Y_RETURN 2023 起崩塌。

### 2.5 Label permutation null（200 次）

真实 Y_RETURN val RankIC = 0.0040；null 分布 mean=0.0057, sd=0.0318；真实值位于 **48.5%** 百分位 → **与乱标签无差异，收益预测不可信**。

### 2.6 Noise feature audit

5 个随机噪声列加入后，tree 模型 importance 最大 = 0.00012（全部落在 46 个真实特征之后）→ 未依赖噪声。

### 2.7 Ablation（选定模型，family-level，phase1_ablation.csv）

- Y_RETURN（rf/SMALL）：移除 MARKET_CONTEXT 使 test_ic 变化 -0.0147（信息主要来自市场背景特征），但全模型本身就是负 IC，无实际意义。
- Y_RISK（ridge/REGULARIZED）：移除 VOLATILITY 后 test_ic -0.0184、移除 MARKET_CONTEXT 后 -0.0232 → 风险预测信息主要来自波动率与市场环境。

### 2.8 Incremental ML（phase1_incremental_ml.csv）

| target | baseline_linear val/test | full_ml val/test |
|---|---|---|
| Y_RETURN | 0.054 / -0.017 | 0.004 / -0.026 |
| Y_RISK | 0.233 / 0.263 | 0.220 / 0.233 |

**full_ml 未超过简单线性 baseline → NO_INCREMENTAL_ML_ALPHA。**

### 2.9 发现的关系（phase1_ml_distilled_factors.csv，描述性，非 Alpha）

23 条 top/bottom 桶特征差异规则，5 个蒸馏候选（AFD_001~005）已注册为 PROPOSED（source=ML_DISTILLED），不做任何结论。

---

## 3. Engine S 详细结果

- 300 条（30 HUMAN + 180 TEMPLATE + 60 RANDOM + 30 LLM），全部 DSL 合法求值，expression_hash 唯一（Symbolic Manifest SHA256 已冻结）。
- discovery（coverage≥70% 且 |RankIC|≥0.02 或 |Q5-Q1|≥1pp 且 2020/2021/2022 至少 2 年同向）pass：113。
- 全家族 BH-FDR（q=0.10）：**110 条 pass**（不是按 family 各自 FDR，是统一控制）。
- FDR-pass 组：val_ic 中位数 0.0185（均值 0.0054，正值率 58%）；test_ic 中位数 0.0199（均值 0.0113，正值率 60%）。
- 但 top 因子 OOS 方向衰减（示例）：
  - diff(distance_to_lower_band, log_amount)：disc≈0.06 → val 0.1146 → **test -0.0164**
  - ratio(days_since_first_signal, signal_count_last_20d)：disc≈0.056 → val≈-0.003 → test≈-0.012
- 结论：Symbolic 引擎能发现 discovery 期有信号的公式，但**没有发现通过 2023+2024 双重 OOS 且方向稳定的强因子**。110 个 FDR-pass 因子大多 val/test |IC|≈0.02~0.05，经济意义弱、无强单调。
- Generator 对比（300 请求分布）：LLM vs Random 无明显差异（无 generator 维度优势结论）。

---

## 4. Engine S vs Engine M vs Baselines（phase1_engine_comparison.csv）

- BASELINE（bb_z / amount / atr14_pct / ret_5d / breadth）：在 symbolic_all 中已有各自 RankIC。
- SYMBOLIC best-by-val（FDR-pass）：val 0.1146 → test -0.0164（OOS 失败）。
- ML（rf/SMALL, Y_RETURN）：val 0.0040 → test -0.0259（OOS 失败）。
- ML_INCR：full_ml 未超 baseline_linear。

---

## 5. 治理与多重检验

- 记账：AFE_20260910_0004 追加 29 条 ML attempts（24 基础规格 + walk-forward + permutation null×200 + noise + ablation + incremental），全部 status=TESTED。
- 蒸馏候选 5 个注册 PROPOSED（ML_DISTILLED）。
- TOTAL_REQUEST_ATTEMPTS / UNIQUE_EXPRESSIONS / COMPUTED_HYPOTHESES 以 Registry summary 为准（见 MULTIPLE_TESTING_LEDGER）。
- Registry integrity audit：Phase 0.1 工具再跑，PASS（见 REGISTRY_INTEGRITY_REPORT.md 更新）。
- 泄漏：特征全部 signal_date 当时可见；D1-D20/未来字段未入特征列（Phase 0.1 test_no_future_columns 通过）。

---

## 6. 禁止事项与状态

- 未触碰 EE15（results/evidence/forward/ git diff = 0；state hash A=5f6af667…、B=be058fa0… 未变）。
- 未使用 2025–2026 任何数据训练/选型/调参。
- 2024 只打开一次，未"救"结果。
- 未做组合回测（Phase 1 边界）。
- 发现项全部为候选（ML_ALPHA_CANDIDATES 语义：无新因子进入正式 Alpha Library；AFD_001~005 为 PROPOSED，不进 Library）。

## 7. 评级

**C** — 训练/Validation 有信息，2024 OOS 明显衰减；收益预测与乱标签无异；风险预测横截面排序稳定但无增量且绝对水平不可靠。不进入 Universe B；不进入任何组合/前瞻使用。

## 8. 遗留 / 下一步建议（不由本轮执行）

1. 若继续：Y_RISK（坏单避让）方向可考虑在 Phase 2 作为"BAD veto"输入做影子组合验证（需先解决 raw-spearman 跨日衰减与 incremental 无增益两个问题）。
2. Universe B 全 A 股 ML 发现：暂不建议启动，先解决 Phase 1 收益维度失效根因（特征集无市场 level 信息？标签噪声？BB 条件信号本身无收益可预测性？）。
3. 特征层面：daily_bb_signal_count / 指数收益等市场环境特征对 Y_RISK 有信息；未来可考虑加入行业相对、横截面 rank 特征。
