# ML-BB 机器学习架构说明（ML Phase 0）

> 本文件描述 ML-BB 研究分支的数据流与隔离原则。
> ML 分支与 EE15 前瞻系统完全隔离：**不改冻结策略、不触碰 `results/evidence/forward/`、不用 2025–2026 数据调参**。
> ML 不重新定义 BB signal——输入 universe 是已冻结的合法 BB signal（SIGPATH canonical）。

## 0. 一句话定位

ML 的目标是对**已经成立的 BB signal universe** 做排序/选择（哪些 signal 更可能走出好路径），
而不是发明新入场信号。`BB(20,2,ddof=1) close_adj < bb_lower` 的入场定义与冻结引擎完全一致，不可修改。

## 1. 数据流（A → G，Phase 2 才允许 H）

```
A. 原始市场数据
   data/combined_daily.parquet        # 2020-01-02..2026-08-31 全A日线（OHLC/vol/amount/adj_factor）
   data/pit_st_daily.parquet          # PIT ST 标记
   data/raw/trade_cal_full.parquet    # 全交易日历
   data/raw/stock_basic.csv           # list_date/industry（当前快照，NON-PIT）
   data/raw/namechange_full.parquet   # PIT 名称（SIGPATH 已核查）
        │
        ▼
B. 已冻结 SIGPATH signal universe（canonical，SHA256 校验通过）
   results/evidence/sigpath/signal_path_20d_wide.parquet   # 157,469 × 251
   results/evidence/sigpath/signal_path_20d_long.parquet   # 3,149,380 × 22
   · 冻结定义：S1 frozen B20（window=20, k=2.0, ddof=1）；signal=T 收盘 close_adj<bb_lower 且非跌停
   · eligibility：listed>=60d 且 PIT 非 ST 且 BB 有值
   · entry=T+1 open；entry_cost=open×(1+0.001)
   · universe=NEW_ENTRY 63,887 + ADD_ON_1..4 93,582 = 157,469（任何组合/资金约束都不删信号）
        │
        ▼
C. PIT feature builder（src/ml_bb/build_features.py）
   · 只能读取 <= signal_date 的数据（信号日及其之前）
   · 输入：wide 快照列 + combined_daily 历史行情（ret_5d / ATR_pct 等前视窗口特征）
   · 输出：feature 表（signal_id + features），signal_id 为唯一键
        │
        ▼
D. ML dataset（signal_id 为唯一 merge 键）
   features ⋈ labels（results/evidence/ml_bb/）
        │
        ▼
E. time-based walk-forward（Phase 1 设计）
   · 训练/验证按时间切分（e.g. train < validate < test，以 signal_date 计）
   · 禁止随机 K-fold 跨时间泄漏；禁止任何 2025–2026 参与调参
        │
        ▼
F. prediction score（模型输出：signal 级别的条件期望/概率）
        │
        ▼
G. signal ranking evaluation（排序增益评估）
   · 对比 baseline 排序（amount top10 / 随机）的 IC、分组收益、lift
   · 不做 K=3 组合回测（Phase 2 才允许 H）
```

## 2. 物理隔离（特征与标签）

| 组件 | 文件 | 读取范围 | 输出 |
|---|---|---|---|
| Feature builder | `src/ml_bb/build_features.py` | `<= signal_date`（信号日及之前） | feature 表：signal_id + 特征列 |
| Label builder | `src/ml_bb/build_labels.py` | `>= signal_date` 之后（D1–D20 outcome） | label 表：signal_id + 标签列 |
| 合并 | `src/ml_bb/build_dataset.py` | 仅通过 signal_id 内连接 | ML dataset |

- 特征与标签**不得在同一函数内混合计算**。
- 泄漏防护（Phase 0 即建立）：`tests/ml_bb/test_no_future_columns.py` 机器断言 feature 表
  不存在任何未来列（D1–D20 OHLC/ret、MFE、MAE、exit outcome 等），并抽查 >=20 条 signal
  验证特征来源日期 <= signal_date。

## 3. Phase 0 冻结的最小特征集合（smoke）

| 特征 | 口径 | 来源 |
|---|---|---|
| `bb_z` | (close_adj − bb_mid) / (bb_upper − bb_mid) × 2 | wide 快照（信号日 T 收盘） |
| `bb_width_pct` | (bb_upper − bb_lower) / bb_mid | wide 快照 |
| `distance_to_lower_band` | close_adj(T) − bb_lower（<0 表示跌破） | wide 快照 |
| `ret_5d` | signal_date 前 5 个该股实际交易日 close_adj 收益 | combined_daily（<=T） |
| `atr_pct` | 前 20 日 ATR / 当日 close | combined_daily（<=T） |
| `log_amount` | log(signal_day_amount) | wide 快照 |
| `entry_role` | NEW_ENTRY / ADD_ON_1..4 | wide 快照 |

标签（Phase 0 smoke）：`GOOD_D20 = close_ret_D20 > 0`（仅用于流水线冒烟，不构成研究结论）。

## 4. 资源估算（本机：Apple M2 Pro / 10 核 / 16GB RAM / 303GB 可用磁盘）

- 157k signals × 20~50 特征：特征矩阵约 157,469 × 50 × 8B ≈ **63 MB**，内存无压力。
- XGBoost 训练：157k × 50 特征、默认参数、10 核，单轮约 **10–60 秒**；lightgbm 类似。
- 无需分批；无需 GPU。**LOCAL ML READY**。
- 唯一较重步骤：从 combined_daily（7.7M 行）构建 ret_5d/ATR_pct，约 1–3 分钟、内存 <4GB。

## 5. 硬性边界（本轮及后续）

1. **ML 不定义/不修改 BB signal**（冻结定义见第 1 节 B）。
2. **EE15 隔离**：ML 代码/产物只写 `src/ml_bb/`、`research/ml_bb/`、`results/evidence/ml_bb/`、`tests/ml_bb/`；
   禁止写入 `results/evidence/forward/` 任何文件；禁止运行会改变 EE15 state 的代码。
3. **2025–2026 禁止**：SIGPATH universe 止于 2024-12-31；任何训练/验证/调参不得使用 2025–2026。
4. **Phase 0 禁止**：正式训练、超参搜索、Alpha 结论、K=3 组合回测。
5. **secret**：Tushare token 只从环境变量 `TUSHARE_TOKEN` 读取；ML 环境文件不出现真实 token；提交前 secret scan。
6. **环境**：ML 使用独立 `.venv-ml`（Python 3.13.13，依赖见 `requirements-ml-lock.txt`）；不触碰 EE15 运行环境。

## 6. 目录

```
src/ml_bb/                # build_features / build_labels / build_dataset / smoke
research/ml_bb/           # 本文档 + registries/（Phase 1 前冻结 Registry）
results/evidence/ml_bb/   # smoke dataset 等产物（parquet/pkl 不入 git）
tests/ml_bb/              # leakage guard 等测试
```

## 7. 里程碑

- Phase 0（本轮）：环境 + 隔离 + smoke —— 目标状态 `ML PHASE 0 READY`
- Phase 1：Registry 冻结 + feature/label 全量构建 + time-based walk-forward 基线
- Phase 2（届时再议）：K=3 portfolio replay 接入评估
