"""ML-BB Phase 1 主流水线：训练 + 评价（Registry 冻结参数，见 ML_BB_PHASE1_REGISTRY.md）。

流程：
1. 加载 dataset（feature + label）
2. 时间切分（train 2020-22 / val 2023 / test 2024 + WF1/WF2/WF3）
3. 缺失处理与标准化（只 fit train）
4. 模型族：Ridge(Y1) / Logistic(Y6) / RF / XGB / LGB；参数选择仅在 train+val
5. 选定参数后 WF1/WF2/WF3 重训，输出 OOS 预测
6. 评价：quintile 梯度、Top-K、稳定性、模型 agreement、permutation importance
7. 输出全部 CSV + 图

纪律：2024 不参与参数选择；2025-2026 零读取；不做组合回测。
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, mean_squared_error
from sklearn.inspection import permutation_importance

import xgboost as xgb
import lightgbm as lgb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ML_OUT = os.path.join(ROOT, "results", "evidence", "ml_bb")
RESEARCH = os.path.join(ROOT, "research", "ml_bb")
SEED = 42
np.random.seed(SEED)

# 冻结特征（37 个；bb_width_pctile 因成本除外，见 ML_FEATURE_REGISTRY.csv 注释与 Phase1 报告）
FEATURE_COLS = [
    "bb_z", "distance_to_lower_band",
    "distance_ma5", "distance_ma10", "distance_ma20", "distance_ma60",
    "ret_1d", "ret_3d", "ret_5d", "ret_10d", "ret_20d",
    "drawdown_20", "drawdown_60", "distance_52w_high",
    "atr14_pct", "realized_vol_10", "realized_vol_20", "bb_width",
    "daily_range_pct", "gap_pct",
    "log_amount", "amount_percentile", "volume_ratio_5_20", "amount_ratio_5_20",
    "signal_role", "level_no", "days_since_first_signal", "signal_count_last_20d",
    "csi300_ret_5", "csi300_ret_20", "csi1000_ret_5", "csi1000_ret_20",
    "market_up_ratio", "market_down_ratio", "daily_bb_signal_count",
]

# 冻结超参数组（Registry 第 6 节）
RF_PARAMS = [
    {"n_estimators": 500, "max_depth": 6, "min_samples_leaf": 50, "random_state": SEED, "n_jobs": -1},
    {"n_estimators": 500, "max_depth": 10, "min_samples_leaf": 200, "random_state": SEED, "n_jobs": -1},
    {"n_estimators": 500, "max_depth": None, "min_samples_leaf": 50, "random_state": SEED, "n_jobs": -1},
]
XGB_PARAMS = [
    {"n_estimators": 500, "learning_rate": 0.02, "max_depth": 4, "min_child_weight": 10,
     "subsample": 0.8, "colsample_bytree": 0.8, "random_state": SEED, "n_jobs": -1},
    {"n_estimators": 500, "learning_rate": 0.05, "max_depth": 4, "min_child_weight": 50,
     "subsample": 0.8, "colsample_bytree": 0.8, "random_state": SEED, "n_jobs": -1},
    {"n_estimators": 500, "learning_rate": 0.05, "max_depth": 6, "min_child_weight": 10,
     "subsample": 0.8, "colsample_bytree": 0.8, "random_state": SEED, "n_jobs": -1},
]
LGB_PARAMS = [
    {"n_estimators": 500, "learning_rate": 0.02, "num_leaves": 31, "min_data_in_leaf": 50,
     "feature_fraction": 0.8, "bagging_fraction": 0.8, "random_state": SEED, "verbose": -1},
    {"n_estimators": 500, "learning_rate": 0.05, "num_leaves": 63, "min_data_in_leaf": 50,
     "feature_fraction": 0.8, "bagging_fraction": 0.8, "random_state": SEED, "verbose": -1},
    {"n_estimators": 500, "learning_rate": 0.05, "num_leaves": 63, "min_data_in_leaf": 200,
     "feature_fraction": 0.8, "bagging_fraction": 0.8, "random_state": SEED, "verbose": -1},
]


def load_dataset() -> pd.DataFrame:
    f = pd.read_parquet(os.path.join(ML_OUT, "ml_features_full.parquet"))
    l = pd.read_parquet(os.path.join(ML_OUT, "ml_labels_full.parquet"))
    ds = f.merge(l, on="signal_id", how="inner")
    assert len(ds) == len(f)
    ds["signal_date"] = pd.to_datetime(ds["signal_date"])
    # 剔除 censored（可用未来日 <20 → 标签不可得）
    ds = ds[ds["available_future_days"] >= 20].copy()
    return ds


def make_model(name: str, is_clf: bool, params: dict):
    if name == "ridge":
        return Ridge(alpha=1.0)
    if name == "logit":
        return LogisticRegression(C=1.0, max_iter=1000, class_weight="balanced", random_state=SEED)
    if name == "rf":
        return RandomForestClassifier(**params) if is_clf else RandomForestRegressor(**params)
    if name == "xgb":
        return xgb.XGBClassifier(**params) if is_clf else xgb.XGBRegressor(**params)
    if name == "lgb":
        return lgb.LGBMClassifier(**params) if is_clf else lgb.LGBMRegressor(**params)
    raise ValueError(name)


def select_params(name: str, is_clf: bool, param_sets, Xtr, ytr, Xva, yva, metric):
    """train+val 参数选择；返回最优参数组。"""
    best, best_score = None, -np.inf
    for p in param_sets:
        m = make_model(name, is_clf, p)
        m.fit(Xtr, ytr)
        if is_clf:
            s = roc_auc_score(yva, m.predict_proba(Xva)[:, 1])
        else:
            s = -mean_squared_error(yva, m.predict(Xva)) if metric == "mse" else np.corrcoef(m.predict(Xva), yva)[0, 1]
        if s > best_score:
            best, best_score = p, s
    return best, best_score


def fit_predict(name: str, is_clf: bool, params, Xtr, ytr, Xte):
    m = make_model(name, is_clf, params)
    m.fit(Xtr, ytr)
    if is_clf:
        return m.predict_proba(Xte)[:, 1], m
    return m.predict(Xte), m


def _prep(df, feats):
    """训练集统计填充 + 标准化；返回 (X, scaler)。"""
    imp = df[feats].median()
    X = df[feats].fillna(imp)
    sc = StandardScaler()
    Xs = sc.fit_transform(X)
    return pd.DataFrame(Xs, columns=feats), sc


def main() -> None:
    ds = load_dataset()
    print(f"dataset: {len(ds)} 行 (censored 剔除后); 列 {ds.shape[1]}")

    # 分组
    new_entry = ds[ds["entry_role"] == "NEW_ENTRY"].copy()
    add_on = ds[ds["entry_role"] != "NEW_ENTRY"].copy()
    print(f"NEW_ENTRY: {len(new_entry)} | ADD_ON: {len(add_on)}")

    # 主分析对象：NEW_ENTRY
    for grp_name, grp in [("NEW_ENTRY", new_entry), ("ADD_ON", add_on)]:
        run_group(grp_name, grp)

    print("DONE")


def run_group(grp_name: str, grp: pd.DataFrame) -> None:
    print(f"\n{'='*60}\n分组: {grp_name} (N={len(grp)})\n{'='*60}")

    # 时间切分
    train = grp[(grp["signal_date"] >= "2020-01-01") & (grp["signal_date"] <= "2022-12-31")]
    val = grp[(grp["signal_date"] >= "2023-01-01") & (grp["signal_date"] <= "2023-12-31")]
    test = grp[(grp["signal_date"] >= "2024-01-01") & (grp["signal_date"] <= "2024-12-31")]
    print(f"train {len(train)} | val {len(val)} | test {len(test)}")
    assert test["signal_date"].max() <= pd.Timestamp("2024-12-31")

    # 预处理（只 fit train）
    Xtr_raw = train[FEATURE_COLS].fillna(train[FEATURE_COLS].median())
    sc = StandardScaler().fit(Xtr_raw)
    def _X(df):
        return pd.DataFrame(sc.transform(df[FEATURE_COLS].fillna(train[FEATURE_COLS].median())), columns=FEATURE_COLS)
    Xtr, Xva, Xte = _X(train), _X(val), _X(test)

    # 目标
    Y1 = "close_ret_D20"; Y6 = "Y6_BAD"
    y1_tr, y1_va, y1_te = train[Y1], val[Y1], test[Y1]
    y6_tr, y6_va, y6_te = train[Y6], val[Y6], test[Y6]

    models_reg = [("ridge", None), ("rf", RF_PARAMS), ("xgb", XGB_PARAMS), ("lgb", LGB_PARAMS)]
    models_clf = [("logit", None), ("rf", RF_PARAMS), ("xgb", XGB_PARAMS), ("lgb", LGB_PARAMS)]

    preds = []
    metrics = []

    # ---- 回归 Y1 ----
    print(">> 回归 Y1 (D20_close_return)")
    for name, ps in models_reg:
        if ps is not None:
            p_best, s_best = select_params(name, False, ps, Xtr, y1_tr, Xva, y1_va, "mse")
        else:
            p_best = {}
        p_val, _ = fit_predict(name, False, p_best, Xtr, y1_tr, Xva)
        p_te, _ = fit_predict(name, False, p_best, Xtr, y1_tr, Xte)
        # WF1: train 2020-21 → test 2022
        wf1_tr = grp[(grp["signal_date"] >= "2020-01-01") & (grp["signal_date"] <= "2021-12-31")]
        wf1_te = grp[(grp["signal_date"] >= "2022-01-01") & (grp["signal_date"] <= "2022-12-31")]
        Xw1_tr = _X(wf1_tr); Xw1_te = _X(wf1_te)
        p_w1, _ = fit_predict(name, False, p_best, Xw1_tr, wf1_tr[Y1], Xw1_te)
        # WF2 = val 组（train 2020-22 → test 2023）
        p_w2 = p_val
        # WF3 = test 组（train 2020-23 → test 2024）
        wf3_tr = pd.concat([train, val])
        Xw3_tr = _X(wf3_tr)
        p_w3, _ = fit_predict(name, False, p_best, Xw3_tr, wf3_tr[Y1], Xte)
        p_w3_te = p_te

        corr_va = np.corrcoef(p_val, y1_va)[0, 1]
        corr_te = np.corrcoef(p_te, y1_te)[0, 1]
        metrics.append({"group": grp_name, "task": "Y1_reg", "model": name, "val_ic": corr_va,
                        "test_ic": corr_te, "test_rmse": np.sqrt(mean_squared_error(y1_te, p_te))})
        print(f"  {name:6s} val_ic={corr_va:.4f} test_ic={corr_te:.4f}")

        # 保存 OOS 预测（WF 对应年份）
        preds.append(pd.DataFrame({
            "group": grp_name, "model": name, "task": "Y1", "signal_id": wf1_te["signal_id"].tolist() + val["signal_id"].tolist() + test["signal_id"].tolist(),
            "signal_date": wf1_te["signal_date"].tolist() + val["signal_date"].tolist() + test["signal_date"].tolist(),
            "year": ["2022"]*len(wf1_te) + ["2023"]*len(val) + ["2024"]*len(test),
            "score": np.concatenate([p_w1, p_w2, p_te]),
            "y": wf1_te[Y1].tolist() + val[Y1].tolist() + test[Y1].tolist(),
        }))

    # ---- 分类 Y6 (BAD) ----
    print(">> 分类 Y6_BAD (MAE<=-20%)")
    for name, ps in models_clf:
        if ps is not None:
            p_best, s_best = select_params(name, True, ps, Xtr, y6_tr, Xva, y6_va, "auc")
        else:
            p_best = {}
        p_val, _ = fit_predict(name, True, p_best, Xtr, y6_tr, Xva)
        p_te, _ = fit_predict(name, True, p_best, Xtr, y6_tr, Xte)
        wf1_tr = grp[(grp["signal_date"] >= "2020-01-01") & (grp["signal_date"] <= "2021-12-31")]
        wf1_te = grp[(grp["signal_date"] >= "2022-01-01") & (grp["signal_date"] <= "2022-12-31")]
        Xw1_tr = _X(wf1_tr); Xw1_te = _X(wf1_te)
        p_w1, _ = fit_predict(name, True, p_best, Xw1_tr, wf1_tr[Y6], Xw1_te)
        wf3_tr = pd.concat([train, val])
        Xw3_tr = _X(wf3_tr)
        p_w3, _ = fit_predict(name, True, p_best, Xw3_tr, wf3_tr[Y6], Xte)

        auc_va = roc_auc_score(y6_va, p_val)
        auc_te = roc_auc_score(y6_te, p_te)
        metrics.append({"group": grp_name, "task": "Y6_bad", "model": name, "val_auc": auc_va, "test_auc": auc_te})
        print(f"  {name:6s} val_auc={auc_va:.4f} test_auc={auc_te:.4f}")

        preds.append(pd.DataFrame({
            "group": grp_name, "model": name, "task": "Y6", "signal_id": wf1_te["signal_id"].tolist() + val["signal_id"].tolist() + test["signal_id"].tolist(),
            "signal_date": wf1_te["signal_date"].tolist() + val["signal_date"].tolist() + test["signal_date"].tolist(),
            "year": ["2022"]*len(wf1_te) + ["2023"]*len(val) + ["2024"]*len(test),
            "score": np.concatenate([p_w1, p_val, p_te]),
            "y": wf1_te[Y6].tolist() + val[Y6].tolist() + test[Y6].tolist(),
        }))

    os.makedirs(ML_OUT, exist_ok=True)
    pdf = pd.concat(preds, ignore_index=True)
    pdf.to_csv(os.path.join(ML_OUT, f"walk_forward_predictions_{grp_name}.csv"), index=False)
    mdf = pd.DataFrame(metrics)
    mdf.to_csv(os.path.join(ML_OUT, f"model_metrics_{grp_name}.csv"), index=False)

    # 汇总到合并文件
    pdf.to_csv(os.path.join(ML_OUT, "walk_forward_predictions.csv"), mode="a" if os.path.exists(os.path.join(ML_OUT, "walk_forward_predictions.csv")) else "w",
               header=not os.path.exists(os.path.join(ML_OUT, "walk_forward_predictions.csv")), index=False)
    mdf.to_csv(os.path.join(ML_OUT, "model_metrics.csv"), mode="a" if os.path.exists(os.path.join(ML_OUT, "model_metrics.csv")) else "w",
               header=not os.path.exists(os.path.join(ML_OUT, "model_metrics.csv")), index=False)

    # ---- 特征重要性（Y6 最佳模型 + Y1 最佳模型）----
    best_reg = mdf[mdf["task"] == "Y1_reg"].sort_values("test_ic", ascending=False).iloc[0]["model"]
    best_clf = mdf[mdf["task"] == "Y6_bad"].sort_values("test_auc", ascending=False).iloc[0]["model"]
    imp_rows = []
    for task, model, is_clf, y_tr in [("Y1", best_reg, False, y1_tr), ("Y6", best_clf, True, y6_tr)]:
        params = {"ridge": {}, "logit": {}, "rf": RF_PARAMS[1], "xgb": XGB_PARAMS[1], "lgb": LGB_PARAMS[1]}[model]
        m = make_model(model, is_clf, params)
        m.fit(Xtr, y_tr)
        try:
            r = permutation_importance(m, Xte, y1_te if task == "Y1" else y6_te, n_repeats=5, random_state=SEED, n_jobs=-1)
            imp = pd.DataFrame({"feature": FEATURE_COLS, "importance": r.importances_mean,
                                "task": f"{grp_name}_{task}", "model": model}).sort_values("importance", ascending=False)
            imp_rows.append(imp)
        except Exception as e:
            print(f"  importance 失败 {model}: {e}")
    if imp_rows:
        pd.concat(imp_rows, ignore_index=True).to_csv(os.path.join(ML_OUT, f"feature_importance_{grp_name}.csv"), index=False)

    # ---- 图（quintile by model, 2024 test）----
    plot_group(grp_name, pdf, test)


def plot_group(grp_name: str, pdf: pd.DataFrame, test: pd.DataFrame) -> None:
    os.makedirs(ML_OUT, exist_ok=True)
    try:
        for task in ["Y1", "Y6"]:
            sub = pdf[(pdf["task"] == task) & (pdf["year"] == "2024")]
            fig, ax = plt.subplots(figsize=(9, 5))
            for model in sub["model"].unique():
                m = sub[sub["model"] == model]
                q = pd.qcut(m["score"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
                med = m.groupby(q, observed=True)["y"].median()
                ax.plot(med.index.astype(int), med.values, marker="o", label=model)
            ax.set_title(f"{grp_name} {task} 2024 quintile median")
            ax.set_xlabel("quintile (1=worst)")
            ax.legend()
            plt.tight_layout()
            plt.savefig(os.path.join(ML_OUT, f"quintile_{grp_name}_{task}.png"), dpi=110)
            plt.close()
    except Exception as e:
        print("plot 跳过:", e)


if __name__ == "__main__":
    main()
