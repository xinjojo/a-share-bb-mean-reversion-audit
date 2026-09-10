"""Alpha Factory Phase 1 — frozen manifests (Commit A).

本模块定义 Phase 1 冻结的：
- 基础特征池（BASE FEATURES）：公式、来源、PIT 规则、missing policy
- 标签定义（Y_RETURN / Y_RISK）
- 时间切分（Train 2020-2022 / Validate 2023 / Final Test 2024；2025-2026 零参与）
- Symbolic 300 请求来源分解与筛选规则
- ML 模型集合（4 models x 3 variants = 12）与选择规则

Commit A 后禁止增删基础特征、禁止修改任何冻结规则。
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 时间切分（全局唯一）
# ---------------------------------------------------------------------------
TIME_SPLIT = {
    "train_start": "2020-01-01", "train_end": "2022-12-31",
    "val_start": "2023-01-01", "val_end": "2023-12-31",
    "test_start": "2024-01-01", "test_end": "2024-12-31",
    "holdout_note": "2025-2026 严禁参与训练/调参/特征选择/模型选择/公式选择；2024 是唯一 Final OOS，只打开一次。",
}

# walk-forward 辅助诊断（不参与选择）
WALK_FORWARD_SPLITS = [
    ("wf_2021", "2020-01-01", "2020-12-31", "2021-01-01", "2021-12-31"),
    ("wf_2022", "2020-01-01", "2021-12-31", "2022-01-01", "2022-12-31"),
    ("wf_2023", "2020-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
]

# ---------------------------------------------------------------------------
# 基础特征池（Phase 1 冻结；<source> 为实际数据源，<PIT> 说明为什么信号日可知）
# ---------------------------------------------------------------------------
# 说明：
#   [MLBB]  复用 results/evidence/ml_bb/ml_features_full.parquet（ML-BB Phase 1 已审计，37 特征，PIT 规则见 ML_BB_PHASE1_REGISTRY.md）
#   [SIGW]  results/evidence/sigpath/signal_path_20d_wide.parquet 信号日快照
#   [CD]    /Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/data/combined_daily.parquet（<= signal_date 窗口聚合）
#   [IDX]   /Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/data/index_000300/000905/000852.parquet
#   [CALC]  由 [CD] 按主线 BB(20,2) 口径重算全市场状态（PIT：只用当日及以前数据）
#   UNAVAILABLE = 当前无 PIT 可审计数据源，禁止临时引入

BASE_FEATURES: list[dict] = [
    # ---- A. Price / location ----
    {"feature_name": "bb_z", "family": "PRICE_LOCATION", "source": "SIGW", "formula": "(close_adj - bb_mid) / ((bb_upper - bb_mid)/2)，主线冻结口径", "lookback": 20, "PIT": "信号日收盘已知", "missing_policy": "保留 NaN，树模型原生处理/线性模型训练集填充"},
    {"feature_name": "distance_to_lower_band", "family": "PRICE_LOCATION", "source": "SIGW", "formula": "(close_adj - bb_lower)/bb_mid*100，主线冻结口径", "lookback": 20, "PIT": "信号日收盘已知", "missing_policy": "同 bb_z"},
    {"feature_name": "distance_ma5", "family": "PRICE_LOCATION", "source": "MLBB", "formula": "(close_adj / MA5(close_adj) - 1)*100", "lookback": 5, "PIT": "<= 信号日窗口", "missing_policy": "同 bb_z"},
    {"feature_name": "distance_ma10", "family": "PRICE_LOCATION", "source": "MLBB", "formula": "(close_adj / MA10(close_adj) - 1)*100", "lookback": 10, "PIT": "<= 信号日窗口", "missing_policy": "同 bb_z"},
    {"feature_name": "distance_ma20", "family": "PRICE_LOCATION", "source": "MLBB", "formula": "(close_adj / MA20(close_adj) - 1)*100", "lookback": 20, "PIT": "<= 信号日窗口", "missing_policy": "同 bb_z"},
    {"feature_name": "distance_ma60", "family": "PRICE_LOCATION", "source": "MLBB", "formula": "(close_adj / MA60(close_adj) - 1)*100", "lookback": 60, "PIT": "<= 信号日窗口", "missing_policy": "同 bb_z"},
    {"feature_name": "ret_1d", "family": "PRICE_LOCATION", "source": "MLBB", "formula": "close_adj 1 日收益(%)", "lookback": 1, "PIT": "<= 信号日窗口", "missing_policy": "同 bb_z"},
    {"feature_name": "ret_3d", "family": "PRICE_LOCATION", "source": "MLBB", "formula": "close_adj 3 日收益(%)", "lookback": 3, "PIT": "<= 信号日窗口", "missing_policy": "同 bb_z"},
    {"feature_name": "ret_5d", "family": "PRICE_LOCATION", "source": "MLBB", "formula": "close_adj 5 日收益(%)", "lookback": 5, "PIT": "<= 信号日窗口", "missing_policy": "同 bb_z"},
    {"feature_name": "ret_10d", "family": "PRICE_LOCATION", "source": "MLBB", "formula": "close_adj 10 日收益(%)", "lookback": 10, "PIT": "<= 信号日窗口", "missing_policy": "同 bb_z"},
    {"feature_name": "ret_20d", "family": "PRICE_LOCATION", "source": "MLBB", "formula": "close_adj 20 日收益(%)", "lookback": 20, "PIT": "<= 信号日窗口", "missing_policy": "同 bb_z"},
    {"feature_name": "ret_60d", "family": "PRICE_LOCATION", "source": "CD", "formula": "close_adj 60 日收益(%)（Phase 1 新增，<= 信号日窗口）", "lookback": 60, "PIT": "<= 信号日窗口", "missing_policy": "同 bb_z"},
    {"feature_name": "drawdown_20", "family": "PRICE_LOCATION", "source": "MLBB", "formula": "(close_adj / rolling20max - 1)*100", "lookback": 20, "PIT": "<= 信号日窗口", "missing_policy": "同 bb_z"},
    {"feature_name": "drawdown_60", "family": "PRICE_LOCATION", "source": "MLBB", "formula": "(close_adj / rolling60max - 1)*100", "lookback": 60, "PIT": "<= 信号日窗口", "missing_policy": "同 bb_z"},
    {"feature_name": "distance_52w_high", "family": "PRICE_LOCATION", "source": "MLBB", "formula": "(close_adj / rolling250max - 1)*100", "lookback": 250, "PIT": "<= 信号日窗口", "missing_policy": "同 bb_z"},
    # ---- B. Volatility ----
    {"feature_name": "atr14_pct", "family": "VOLATILITY", "source": "MLBB", "formula": "ATR14 / close_adj * 100", "lookback": 14, "PIT": "<= 信号日窗口", "missing_policy": "同 bb_z"},
    {"feature_name": "realized_vol_10", "family": "VOLATILITY", "source": "MLBB", "formula": "close_adj 日收益 10 日滚动 std(%)", "lookback": 10, "PIT": "<= 信号日窗口", "missing_policy": "同 bb_z"},
    {"feature_name": "realized_vol_20", "family": "VOLATILITY", "source": "MLBB", "formula": "close_adj 日收益 20 日滚动 std(%)", "lookback": 20, "PIT": "<= 信号日窗口", "missing_policy": "同 bb_z"},
    {"feature_name": "bb_width", "family": "VOLATILITY", "source": "MLBB", "formula": "(bb_upper - bb_lower)/bb_mid，主线冻结口径", "lookback": 20, "PIT": "信号日收盘已知", "missing_policy": "同 bb_z"},
    {"feature_name": "daily_range_pct", "family": "VOLATILITY", "source": "MLBB", "formula": "(high_adj - low_adj)/close_adj*100", "lookback": 1, "PIT": "信号日收盘已知", "missing_policy": "同 bb_z"},
    {"feature_name": "gap_pct", "family": "GAP", "source": "MLBB", "formula": "(open_adj / prev_close_adj - 1)*100", "lookback": 1, "PIT": "信号日开盘已知", "missing_policy": "同 bb_z"},
    # ---- C. Liquidity ----
    {"feature_name": "log_amount", "family": "LIQUIDITY", "source": "MLBB", "formula": "log(signal_day_amount)", "lookback": 1, "PIT": "信号日收盘已知", "missing_policy": "同 bb_z"},
    {"feature_name": "amount_percentile", "family": "LIQUIDITY", "source": "MLBB", "formula": "信号日成交额在过去 250 日的分位", "lookback": 250, "PIT": "<= 信号日窗口", "missing_policy": "同 bb_z"},
    {"feature_name": "volume_ratio_5_20", "family": "LIQUIDITY", "source": "MLBB", "formula": "vol 5 日均 / 20 日均", "lookback": 20, "PIT": "<= 信号日窗口", "missing_policy": "同 bb_z"},
    {"feature_name": "amount_ratio_5_20", "family": "LIQUIDITY", "source": "MLBB", "formula": "amount 5 日均 / 20 日均", "lookback": 20, "PIT": "<= 信号日窗口", "missing_policy": "同 bb_z"},
    {"feature_name": "turnover_rank", "family": "CROSS_SECTIONAL", "source": "SIGW", "formula": "信号日全市场成交额排名分位（主线冻结）", "lookback": 1, "PIT": "信号日收盘已知", "missing_policy": "同 bb_z"},
    # ---- D. Signal state ----
    {"feature_name": "signal_role", "family": "SIGNAL_STATE", "source": "SIGW/MLBB", "formula": "NEW_ENTRY / ADD_ON_1..4（分类，one-hot 输入）", "lookback": None, "PIT": "信号日已知", "missing_policy": "无缺失"},
    {"feature_name": "level_no", "family": "SIGNAL_STATE", "source": "MLBB", "formula": "加仓层号", "lookback": None, "PIT": "信号日已知", "missing_policy": "无缺失"},
    {"feature_name": "days_since_first_signal", "family": "SIGNAL_STATE", "source": "MLBB", "formula": "距该 episode 首次信号的交易日数", "lookback": None, "PIT": "信号日已知", "missing_policy": "同 bb_z"},
    {"feature_name": "signal_count_last_20d", "family": "SIGNAL_STATE", "source": "MLBB", "formula": "过去 20 日该股 BB 信号次数", "lookback": 20, "PIT": "<= 信号日窗口", "missing_policy": "同 bb_z"},
    # ---- E. Market context ----
    {"feature_name": "daily_bb_signal_count", "family": "MARKET_CONTEXT", "source": "MLBB", "formula": "信号日全市场 BB 下轨信号数", "lookback": 1, "PIT": "信号日收盘已知", "missing_policy": "同 bb_z"},
    {"feature_name": "daily_bb_up_ratio", "family": "MARKET_CONTEXT", "source": "CALC", "formula": "信号日全市场 close_adj>bb_upper 占比（BB20/2 主线口径，Phase 1 新增）", "lookback": 20, "PIT": "只用当日及以前数据重算", "missing_policy": "同 bb_z"},
    {"feature_name": "daily_bb_down_ratio", "family": "MARKET_CONTEXT", "source": "CALC", "formula": "信号日全市场 close_adj<bb_lower 占比（BB20/2 主线口径，Phase 1 新增）", "lookback": 20, "PIT": "只用当日及以前数据重算", "missing_policy": "同 bb_z"},
    {"feature_name": "market_up_ratio", "family": "MARKET_CONTEXT", "source": "MLBB", "formula": "信号日全市场上涨占比（主线口径）", "lookback": 1, "PIT": "信号日收盘已知", "missing_policy": "同 bb_z"},
    {"feature_name": "market_down_ratio", "family": "MARKET_CONTEXT", "source": "MLBB", "formula": "信号日全市场下跌占比（主线口径）", "lookback": 1, "PIT": "信号日收盘已知", "missing_policy": "同 bb_z"},
    # ---- F. Index context ----
    {"feature_name": "csi300_ret_1", "family": "MARKET_CONTEXT", "source": "IDX", "formula": "沪深300 指数 1 日收益(%)", "lookback": 1, "PIT": "<= 信号日收盘", "missing_policy": "同 bb_z"},
    {"feature_name": "csi300_ret_5", "family": "MARKET_CONTEXT", "source": "IDX", "formula": "沪深300 指数 5 日收益(%)", "lookback": 5, "PIT": "<= 信号日收盘", "missing_policy": "同 bb_z"},
    {"feature_name": "csi300_ret_20", "family": "MARKET_CONTEXT", "source": "IDX", "formula": "沪深300 指数 20 日收益(%)", "lookback": 20, "PIT": "<= 信号日收盘", "missing_policy": "同 bb_z"},
    {"feature_name": "csi500_ret_1", "family": "MARKET_CONTEXT", "source": "IDX", "formula": "中证500 指数 1 日收益(%)（Phase 1 新增）", "lookback": 1, "PIT": "<= 信号日收盘", "missing_policy": "同 bb_z"},
    {"feature_name": "csi500_ret_5", "family": "MARKET_CONTEXT", "source": "IDX", "formula": "中证500 指数 5 日收益(%)（Phase 1 新增）", "lookback": 5, "PIT": "<= 信号日收盘", "missing_policy": "同 bb_z"},
    {"feature_name": "csi500_ret_20", "family": "MARKET_CONTEXT", "source": "IDX", "formula": "中证500 指数 20 日收益(%)（Phase 1 新增）", "lookback": 20, "PIT": "<= 信号日收盘", "missing_policy": "同 bb_z"},
    {"feature_name": "csi1000_ret_1", "family": "MARKET_CONTEXT", "source": "IDX", "formula": "中证1000 指数 1 日收益(%)（Phase 1 新增）", "lookback": 1, "PIT": "<= 信号日收盘", "missing_policy": "同 bb_z"},
    {"feature_name": "csi1000_ret_5", "family": "MARKET_CONTEXT", "source": "IDX", "formula": "中证1000 指数 5 日收益(%)", "lookback": 5, "PIT": "<= 信号日收盘", "missing_policy": "同 bb_z"},
    {"feature_name": "csi1000_ret_20", "family": "MARKET_CONTEXT", "source": "IDX", "formula": "中证1000 指数 20 日收益(%)", "lookback": 20, "PIT": "<= 信号日收盘", "missing_policy": "同 bb_z"},
    # ---- G. Industry-relative（UNAVAILABLE）----
    {"feature_name": "stock_ret_5_minus_industry", "family": "INDUSTRY_RELATIVE", "source": "UNAVAILABLE", "formula": "个股 5 日收益 - 同行业均值 5 日收益：无 PIT 行业面板（SIGPATH industry_snapshot 仅信号日快照，非历史 PIT 面板，禁止回算历史行业收益）", "lookback": 5, "PIT": "N/A", "missing_policy": "N/A"},
    {"feature_name": "stock_ret_20_minus_industry", "family": "INDUSTRY_RELATIVE", "source": "UNAVAILABLE", "formula": "个股 20 日收益 - 同行业均值 20 日收益：同上", "lookback": 20, "PIT": "N/A", "missing_policy": "N/A"},
]

NUMERIC_FEATURES: list[str] = [
    f["feature_name"] for f in BASE_FEATURES
    if f["source"] != "UNAVAILABLE" and f["feature_name"] != "signal_role"
]
CATEGORICAL_FEATURES: list[str] = ["signal_role"]

# ---------------------------------------------------------------------------
# 标签（冻结）
# ---------------------------------------------------------------------------
LABELS = {
    "Y_RETURN": {"source": "SIGW", "formula": "close_ret_D20 = close_D20/close_T - 1（%）", "role": "主回归（return）"},
    "Y_RISK": {"source": "SIGW", "formula": "MAE_D20 = 未来 20 日最大不利偏离（%）", "role": "主回归（risk）"},
    "censored": {"source": "SIGW", "formula": "close_ret_D20 缺失（未来窗口不足）即 censored，训练/评估排除", "role": "掩码"},
}

# ---------------------------------------------------------------------------
# Engine M 模型集合（4 x 3 = 12，Commit A 冻结，禁止追加第 13 个）
# ---------------------------------------------------------------------------
ML_MODELS: dict = {
    "M0_RIDGE": {
        "variants": {
            "SMALL": {"alpha": 10.0},
            "MEDIUM": {"alpha": 1.0},
            "REGULARIZED": {"alpha": 100.0},
        },
        "note": "线性正则；输入标准化（scaler 只 fit train）",
    },
    "M1_RF": {
        "variants": {
            "SMALL": {"n_estimators": 200, "max_depth": 4, "min_samples_leaf": 50, "max_features": 0.5},
            "MEDIUM": {"n_estimators": 300, "max_depth": 6, "min_samples_leaf": 25, "max_features": 0.6},
            "REGULARIZED": {"n_estimators": 200, "max_depth": 3, "min_samples_leaf": 100, "max_features": 0.4},
        },
        "note": "RandomForestRegressor；n_jobs=-1",
    },
    "M2_XGB": {
        "variants": {
            "SMALL": {"max_depth": 3, "learning_rate": 0.05, "n_estimators": 200, "min_child_weight": 20, "subsample": 0.8, "colsample_bytree": 0.6, "reg_lambda": 1.0},
            "MEDIUM": {"max_depth": 5, "learning_rate": 0.05, "n_estimators": 300, "min_child_weight": 10, "subsample": 0.8, "colsample_bytree": 0.7, "reg_lambda": 1.0},
            "REGULARIZED": {"max_depth": 3, "learning_rate": 0.03, "n_estimators": 250, "min_child_weight": 50, "subsample": 0.7, "colsample_bytree": 0.5, "reg_lambda": 5.0},
        },
        "note": "XGBRegressor；tree_method=hist",
    },
    "M3_LGB": {
        "variants": {
            "SMALL": {"max_depth": 3, "learning_rate": 0.05, "n_estimators": 200, "min_child_samples": 50, "subsample": 0.8, "colsample_bytree": 0.6, "reg_lambda": 1.0},
            "MEDIUM": {"max_depth": 5, "learning_rate": 0.05, "n_estimators": 300, "min_child_samples": 25, "subsample": 0.8, "colsample_bytree": 0.7, "reg_lambda": 1.0},
            "REGULARIZED": {"max_depth": 3, "learning_rate": 0.03, "n_estimators": 250, "min_child_samples": 100, "subsample": 0.7, "colsample_bytree": 0.5, "reg_lambda": 5.0},
        },
        "note": "LGBMRegressor；verbose=-1",
    },
}

# 选择规则（Commit A 冻结）
SELECTION_RULE = {
    "val_metric_Y_RETURN": "2023 RankIC 最大；并列时看 Q5-Q1 spread 与 2022/2023 方向一致性",
    "val_metric_Y_RISK": "2023 Spearman(pred_risk, MAE) 最大（正相关表示风险可排序）",
    "per_model": "每个模型族（M0..M3）内部先选最优 variant；再跨族比 2023 表现",
    "final": "Y_RETURN 与 Y_RISK 各选 1 个最终模型；用 Train+Val 重训后只开一次 2024",
    "forbidden": "2024 不参与任何选择；2025-2026 零读取",
}

# Negative control（Commit A 冻结）
NEGATIVE_CONTROL = {
    "permutation_n": 200,
    "permutation_seed": 20260910,
    "noise_feature_n": 5,
    "noise_seed": 20260910,
    "eval_metric_for_null": "2023+2024 RankIC 与 Q5-Q1",
}

# Ablation（Commit A 冻结，family-level）
ABLATION_FAMILIES = {
    "PRICE": ["bb_z", "distance_to_lower_band", "distance_ma5", "distance_ma10", "distance_ma20", "distance_ma60",
              "ret_1d", "ret_3d", "ret_5d", "ret_10d", "ret_20d", "ret_60d", "drawdown_20", "drawdown_60", "distance_52w_high"],
    "VOLATILITY": ["atr14_pct", "realized_vol_10", "realized_vol_20", "bb_width", "daily_range_pct", "gap_pct"],
    "LIQUIDITY": ["log_amount", "amount_percentile", "volume_ratio_5_20", "amount_ratio_5_20", "turnover_rank"],
    "MARKET_CONTEXT": ["daily_bb_signal_count", "daily_bb_up_ratio", "daily_bb_down_ratio", "market_up_ratio", "market_down_ratio",
                       "csi300_ret_1", "csi300_ret_5", "csi300_ret_20", "csi500_ret_1", "csi500_ret_5", "csi500_ret_20",
                       "csi1000_ret_1", "csi1000_ret_5", "csi1000_ret_20"],
}

# Incremental baseline（Commit A 冻结）
INCREMENTAL_BASELINE = ["bb_z", "log_amount", "atr14_pct", "daily_bb_signal_count", "ret_5d", "ret_20d"]

# ---------------------------------------------------------------------------
# Engine S（Symbolic 300）
# ---------------------------------------------------------------------------
SYMBOLIC_300 = {
    "human": 30, "template": 180, "random": 60, "llm": 30, "total": 300,
    "random_seed": 20260910,
    "screen": {
        "coverage_min": 0.70,
        "rankic_min": 0.02,
        "q5q1_median_min_pp": 1.0,
        "consistent_years_min": 2,   # 2020-2022 中至少 2 年方向一致
        "fdr_q": 0.10,               # 全 Symbolic family 统一 BH-FDR
    },
}

# Symbolic 输入池（Phase 1 特征中可用的横截面/逐行运算输入）
SYMBOLIC_INPUTS: list[str] = [
    "bb_z", "distance_to_lower_band", "BB_width", "bb_width",
    "ret_1d", "ret_3d", "ret_5d", "ret_10d", "ret_20d", "ret_60d",
    "drawdown_20", "drawdown_60", "distance_52w_high",
    "atr14_pct", "realized_vol_10", "realized_vol_20", "daily_range_pct", "gap_pct",
    "log_amount", "amount_ratio_5_20", "volume_ratio_5_20", "turnover_rank",
    "daily_bb_signal_count", "daily_bb_up_ratio", "daily_bb_down_ratio",
    "market_up_ratio", "market_down_ratio",
    "csi300_ret_1", "csi300_ret_5", "csi300_ret_20",
    "csi500_ret_1", "csi500_ret_5", "csi500_ret_20",
    "csi1000_ret_1", "csi1000_ret_5", "csi1000_ret_20",
    "signal_count_last_20d", "days_since_first_signal",
]

# Signal universe
UNIVERSE_A = {
    "sigpath_wide": "results/evidence/sigpath/signal_path_20d_wide.parquet",
    "note": "157,469 signals，2020-02-06 ~ 2024-12-30；NEW_ENTRY 与 ADD_ON 分组分析",
}
