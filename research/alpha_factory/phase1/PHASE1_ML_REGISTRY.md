# Alpha Factory Phase 1 — ML Registry（Commit A 冻结）

- 冻结时间：2026-09-10（Commit A）
- 治理基线：`1a7db3f`（Phase 0.1 GOVERNANCE PASS）
- 状态：**本文件在正式训练前冻结，禁止在看过 Validation/Test 结果后修改**

---

## 1. 研究问题（Universe A）

对 SIGPATH canonical 157,469 个合法 BB 下轨信号，仅使用 signal_date 当日及以前可知的信息，
预测两个标签：

| 标签 | 定义 | 来源 | 任务 |
|---|---|---|---|
| Y_RETURN | D20 close return（%） | SIGPATH `close_ret_D20` | 主回归 |
| Y_RISK | D20 MAE（%） | SIGPATH `MAE_D20` | 风险回归 |

censored（close_ret_D20 缺失）样本：训练与评估一律排除；不填充。

分组：NEW_ENTRY 与 ADD_ON 独立分析，主结论以 NEW_ENTRY 为准。

## 2. 输入

- `PHASE1_BASE_FEATURE_MANIFEST.csv`（46 行：44 可用 + 2 UNAVAILABLE），SHA256 见 `PHASE1_MANIFEST_SHA256.json`
- 行业相对特征（stock_ret_5/20_minus_industry）：**UNAVAILABLE**（无 PIT 行业面板）
- signal_role 为分类特征，one-hot 编码；scaler/imputer 只 fit train

## 3. 时间切分（全局冻结）

| 用途 | 区间 |
|---|---|
| TRAIN / DISCOVERY | 2020-01-01 ~ 2022-12-31 |
| VALIDATION | 2023-01-01 ~ 2023-12-31 |
| FINAL TEST | 2024-01-01 ~ 2024-12-31（只打开一次） |
| 禁区 | 2025-2026 零读取；2024 不参与任何选择 |

辅助 walk-forward（诊断用，不参与选择）：
- WF1：Train 2020 → Test 2021
- WF2：Train 2020-21 → Test 2022
- WF3：Train 2020-22 → Test 2023

## 4. 模型集合（4 × 3 = 12，禁止第 13 个）

| 模型 | variants | 参数（预冻结） |
|---|---|---|
| M0 Ridge | SMALL / MEDIUM / REGULARIZED | alpha=10 / 1 / 100；输入标准化 |
| M1 RandomForest | SMALL / MEDIUM / REGULARIZED | 见 manifest.ML_MODELS（depth 3/6/3, leaf 50/25/100） |
| M2 XGBoost | SMALL / MEDIUM / REGULARIZED | 见 manifest.ML_MODELS（depth 3/5/3, lr 0.05/0.05/0.03） |
| M3 LightGBM | SMALL / MEDIUM / REGULARIZED | 见 manifest.ML_MODELS（depth 3/5/3, samples 50/25/100） |

禁止：NN / Transformer / LSTM / 强化学习 / AutoML / 遗传 / 贝叶斯无限调参。

## 5. 选择规则（Commit A 冻结）

- Y_RETURN：2023 RankIC 最大；并列看 Q5-Q1 spread 与 2022/2023 方向一致性
- Y_RISK：2023 Spearman(pred, MAE) 最大
- 流程：每族先选最优 variant → 跨族比 2023 → 每标签选 1 个最终模型 → Train+Val 重训 → 2024 单次预测
- 严禁：看完 2023/2024 后新增模型、改参数、改特征、改公式

## 6. Negative control（冻结）

- Label permutation null：≥200 次（seed 20260910），保持 feature/模型/时间结构，观察真实模型 2023/2024 表现处于 null 分布的百分位
- Noise features：5 个确定性随机噪声列（seed 20260910）；若噪声进入长期 Top importance → OVERFIT_WARNING

## 7. Interpretability（冻结）

- Permutation importance（树模型 + 线性系数符号）
- SHAP（若可用；否则 tree gain + ALE/PDP 替代并说明）
- 交互重要性（SHAP interaction / gain）；提取稳定规则 → `phase1_ml_discovered_relationships.csv`（DISCOVERED_RELATIONSHIP，非 Alpha）
- ML→Symbolic 蒸馏：新 factor_id、source=ML_DISTILLED、禁止用 2024 调公式

## 8. Ablation（冻结，family-level，逐组一次）

去掉 PRICE / VOLATILITY / LIQUIDITY / MARKET_CONTEXT 各一次，报告 2023/2024 RankIC 变化。
禁止逐个特征反复删到 2024 最好。

## 9. Incremental test（冻结）

Baseline Linear：bb_z + log_amount + atr14_pct + daily_bb_signal_count + ret_5d + ret_20d。
Full ML vs Baseline：2023/2024 RankIC 增量、Q5-Q1 增量。无增量 → NO_INCREMENTAL_ML_ALPHA。

## 10. 成功/评级标准

| 级 | 标准 |
|---|---|
| A | 2023+2024 均明显优于简单 baseline；permutation null 显著；≥3/4 年份方向一致；发现 ≥1 个可靠 Symbolic 或 Model Alpha |
| B | 存在稳定增量预测信息，但优势弱或仅部分年份 |
| C | Train/Val 有信息，2024 明显衰减 |
| D | 与随机/简单 baseline 无区别 |

## 11. Multiple testing 记账

- 每个 model × variant × target = 1 条 attempt（12 规格 × 2 标签 = 24 基础 attempts）
- walk-forward 附加训练次数、permutation 200 次、ablation 4 次、noise audit 均计入 `MULTIPLE_TESTING_LEDGER`
- Symbolic 300 请求：全家族统一 BH-FDR q=0.10；重复/非法请求计 REQUEST_ATTEMPTS

## 12. Library 规则

- Symbolic 因子走完整 gate（PIT/FDR/Val/Test/Stability/Redundancy/Incremental）才可 KEEP
- ML 模型只进 `ML_ALPHA_CANDIDATES`（status=ML_VALIDATING），组合经济测试通过才升级
- MODEL ALPHA 不要求压成公式；大模型文件本地保存，Git 只存 hash + metadata
