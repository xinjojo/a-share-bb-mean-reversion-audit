# ML-BB Phase 1 Registry — Signal Ranking Audit

> 冻结时间：2026-09-09（在查看任何正式模型结果之前冻结）
> 依赖：ML Phase 0（commit `8c5ec1d`，状态 ML PHASE 0 READY）
> EE15 隔离：本轮不改 EE15 任何生产文件/state/ledger/冻结参数；ML 产物只写入 `src/ml_bb/`、`research/ml_bb/`、`results/evidence/ml_bb/`、`tests/ml_bb/`。

## 0. 本轮唯一研究问题

对已经出现的合法 BB Mean Reversion signal（冻结定义），
仅使用 signal_date 当时可见的信息，机器学习能否稳定地区分未来更好/更差的信号。
目标用途：未来 K=3 有限槽位 admission ranking。**本轮不做完整组合回测。**

## 1. Signal Universe（冻结）

- 主 universe：SIGPATH canonical **157,469 条**（`results/evidence/sigpath/signal_path_20d_wide.parquet`，SHA256 已校验）。
- 强制分拆两组，禁止混合训练后直接下统一结论：
  - **NEW_ENTRY**（63,887）：主 ranking 结论对象（未来 K=3 admission 对应首次新入场）。
  - **ADD_ON_1..4**（93,582）：独立辅助模型/子组分析。
- censored（`available_future_days<20`，3,136 条）：从训练/评价剔除（标签不可得），单独披露计数，不进模型。
- 2025–2026：**零读取**（universe 止于 2024-12-31，机器断言）。
- signal_date 范围：2020-02-06 ~ 2024-12-30。

## 2. Feature List（冻结，全部 signal_date 当时可知）

### A. Price / location
| feature | 口径 | 来源 |
|---|---|---|
| bb_z | (close_adj − bb_mid) / ((bb_upper−bb_mid)/2) | wide 快照 |
| distance_to_lower_band | close_adj(T) − bb_lower（<0 跌破） | wide 快照 |
| distance_ma5 / ma10 / ma20 / ma60 | close_adj(T) / MA_n − 1（pct） | combined_daily ≤T |
| ret_1d / 3d / 5d / 10d / 20d | close_adj 前 1/3/5/10/20 交易日收益（pct） | combined_daily ≤T |
| drawdown_20 / 60 | 前 20/60 交易日最大回撤（pct，负值） | combined_daily ≤T |
| distance_52w_high | close_adj(T) / 前 250 交易日最高 close_adj − 1 | combined_daily ≤T |

### B. Volatility
| feature | 口径 | 来源 |
|---|---|---|
| atr14_pct | ATR(14) / close_adj（pct） | combined_daily ≤T |
| realized_vol_10 / 20 | 前 10/20 日 close_adj 日收益 std（pct） | combined_daily ≤T |
| bb_width | bb_upper − bb_lower（adj 空间） | wide 快照 |
| bb_width_pctile | 该股 bb_width 历史（≤T，前 250 日）百分位 | combined_daily ≤T |
| daily_range_pct | (high−low)/close ×100（T 日） | combined_daily ≤T |
| gap_pct | (open − prev_close)/prev_close ×100（T 日） | combined_daily ≤T |

### C. Liquidity / volume
| feature | 口径 | 来源 |
|---|---|---|
| log_amount | log(signal_day_amount) | wide 快照 |
| amount_percentile | T 日全市场 amount 横截面百分位（0-100） | combined_daily ≤T |
| volume_ratio_5_20 | 前 5 日 / 前 20 日日均 vol | combined_daily ≤T |
| amount_ratio_5_20 | 前 5 日 / 前 20 日日均 amount | combined_daily ≤T |

### D. Signal state
| feature | 口径 | 来源 |
|---|---|---|
| signal_role | NEW_ENTRY=0, ADD_ON_1..4=1..4 | wide 快照 |
| level_no | 层序号（同 signal_role） | wide 快照 |
| days_since_first_signal | signal_date − 该 episode 首次 signal_date（自然日） | wide 快照（episode 内最早 signal_date） |
| signal_count_last_20d | 该股 ≤T 前 20 个交易日内出现信号次数 | wide 快照 |
| current_mae_to_date | ADD_ON 时点距入场已实现 MAE（≤T 已知；NEW_ENTRY 为 NaN） | wide/长表 ≤T（Phase 1 仅 ADD_ON 子组用） |
| distance_from_first_entry | 相对首次入场 close_adj 收益（pct；NEW_ENTRY=NaN） | 同上，ADD_ON 子组用 |

### E. Market context
| feature | 口径 | 来源 |
|---|---|---|
| csi300_ret_5 / 20 | 沪深300 前 5/20 交易日收益（pct） | data/index_000300.parquet ≤T |
| csi1000_ret_5 / 20 | 中证1000 前 5/20 交易日收益（pct） | data/index_000852.parquet ≤T |
| market_up_ratio | T 日全市场上涨股票占比（0-1） | combined_daily ≤T |
| market_down_ratio | T 日全市场下跌股票占比（0-1） | combined_daily ≤T |
| daily_bb_signal_count | T 日全市场 BB 信号数（log 后入模） | wide 快照按日计数 |

**禁止**：future return / future MFE / future MAE / 未来 ST / 未来行业 / 未来复权信息。
机器保证：所有特征来源日期 ≤ signal_date（tests/ml_bb/test_no_future_columns.py + Phase 1 100 条抽查）。

## 3. Label List（冻结）

| label | 定义 | 类型 |
|---|---|---|
| Y1 | close_ret_D20（D20 close / entry_cost − 1，pct） | regression |
| Y2 | MFE_D20（D1..D20 最大 high_ret，pct） | regression |
| Y3 | MAE_D20（D1..D20 最小 low_ret，pct） | regression |
| Y4_GOOD | close_ret_D20 > 0 | binary |
| Y5_STRONG_RECOVERY | MFE_D20 ≥ +5% | binary |
| Y6_BAD | MAE_D20 ≤ −20% | binary |

阈值 +5% / −20% 冻结，**不得看到结果后修改**。

## 4. 时间切分（冻结，严禁 random split）

| 角色 | 区间（signal_date） |
|---|---|
| Train | 2020-01-01 ~ 2022-12-31 |
| Validation | 2023-01-01 ~ 2023-12-31 |
| Final OOS Test | 2024-01-01 ~ 2024-12-31 |

Expanding walk-forward（模型选择/稳定性展示）：
- WF1: Train 2020–2021 → Test 2022
- WF2: Train 2020–2022 → Test 2023（= 主 Val）
- WF3: Train 2020–2023 → Test 2024（= 主 OOS）

2025–2026 零读取：机器断言 max model-selection data ≤ 2024-12-31。

## 5. 模型集合（冻结）

1. Linear Regression（Ridge, alpha 冻结）— Y1 回归
2. Logistic Regression（Ridge, class_weight balanced）— Y6_BAD 分类
3. Random Forest（冻结参数集见下）
4. XGBoost
5. LightGBM

禁止：LSTM / Transformer / PyTorch / TensorFlow / 强化学习 / AutoML。

## 6. 超参数集合（冻结，预注册 3~5 组合/模型）

树模型每模型 3 组：
- RF: {n_estimators:500, max_depth:[6,10,None], min_samples_leaf:[50,200]}
- XGB: {n_estimators:500, learning_rate:[0.02,0.05], max_depth:[4,6], min_child_weight:[10,50], subsample:0.8, colsample_bytree:0.8}
- LGB: {n_estimators:500, learning_rate:[0.02,0.05], num_leaves:[31,63], min_data_in_leaf:[50,200], feature_fraction:0.8, bagging_fraction:0.8}

选择仅在 Train+Validation 完成；2024 不参与任何参数选择。

## 7. Ranking Metrics（冻结）

- 每 OOS 年份按预测 score 分 quintile（Q1 最差 20% … Q5 最好 20%），输出每桶：N / D20 mean / D20 median / positive rate / MFE median / MAE median / BAD rate。
- **核心判定：Q1→Q5 是否形成稳定单调梯度**（D20 median、BAD rate）。
- 置信区间：**cluster bootstrap by signal_date**（同一天多信号不作独立样本），≥1000 次。

## 8. Top-K Evaluation（冻结）

按 signal_date 分组（当日 ≥2 个 NEW_ENTRY 信号的日期），比较：
Model Top1 / Top3 / Top5 vs Random / amount 排序 / BB_z 排序 / ATR 排序 / 冻结原 admission 顺序（signal_i 序）。
指标：D20 mean / median / BAD rate / MFE / MAE；bootstrap 置信区间按 signal_date。

## 9. Baselines（冻结）

B0 全部不排序 / B1 Random / B2 amount / B3 BB_z / B4 ATR / B5 简单 Linear（无特征工程超参）。
ML 必须明显优于这些才判有实际价值。

## 10. Stability & Agreement（冻结）

- 至少报告 2022 / 2023 / 2024 每年：Q5−Q1 D20 median spread、Q5−Q1 BAD rate spread、Top3 vs baseline、模型排名。
- 模型 agreement：Linear/RF/XGB/LGB 的 Top20% 信号集合 overlap（Jaccard / 共享数）。
- 若某模型 2022 好、2023 坏、2024 好 → 明确写“不稳定”。

## 11. Feature Importance（冻结）

最佳树模型输出 permutation importance（+ SHAP summary 若稳定可用，非硬要求）。
必须回答模型真实依赖哪些特征，重点关注：market breadth / BB depth / ATR / market context / signal role / liquidity。

## 12. Leakage Audit（冻结流程）

全量 dataset 完成后：
1. 重跑 `tests/ml_bb/test_no_future_columns.py`（4/4 须 PASS）。
2. 新增随机 ≥100 正式 signal 抽查：feature source date ≤ signal_date。
3. 输出 `research/ml_bb/ML_LEAKAGE_AUDIT_PHASE1.md`。
任何 leakage → 本轮结果作废重跑。

## 13. 成功标准（Phase 1 评级）

- **A**：2024 OOS 有明显 ranking gradient；2022/2023/2024 至少 2 年同方向；Q5 明显优于 overall/random；Q1 BAD rate 明显更高或 Q5 更低；≥2 模型支持；Top-K 优于 amount/BB_z/ATR。
- **B**：有一定 OOS 排序能力，但年份/模型稳定性一般。
- **C**：仅弱统计关系，不足以改善 K=3 admission。
- **D**：无 OOS 价值 / 明显过拟合。

## 14. Random Seeds（冻结）

- 数据抽样：42；训练：42；bootstrap：2024；train/val/test 分裂由时间决定（无随机）。
- 模型随机种子：RF/XGB/LGB 均 42；`random_state`/`seed` 全部固定。

## 15. 输出文件（冻结清单）

`ml_signal_dataset_full.parquet` / `feature_registry.csv` / `label_registry.csv` / `walk_forward_predictions.csv` / `model_metrics.csv` / `ranking_quintile_stats.csv` / `topk_comparison.csv` / `yearly_stability.csv` / `model_agreement.csv` / `feature_importance.csv` / `ML_LEAKAGE_AUDIT_PHASE1.md` / `ML_PHASE1_REPORT.md` + 图（score-vs-realized、quintile D20 median、quintile BAD rate、yearly spread、Top3 baseline、feature importance、model agreement）。

## 16. Git 纪律

Commit A = 本 Registry + feature/label registry + code skeleton（看结果前）。
Commit B = 正式结果 + 报告 + 图 + 摘要。
大模型文件不入 git（记录 hash/参数/库版本）。
EE15 forward 文件保持 0 change（git status 验证）。
