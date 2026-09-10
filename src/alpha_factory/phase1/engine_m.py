"""Alpha Factory Phase 1 — Engine M：ML 自学（Ridge/RF/XGB/LGB，12 规格×2 标签）。

流程（manifest.py 冻结）：
- TRAIN 2020-2022 / VAL 2023（选型）/ TEST 2024（单测）
- 选型：Y_RETURN 按 2023 RankIC；Y_RISK 按 2023 Spearman(pred, MAE)
- walk-forward: 2021/2022/2023 辅助诊断
- label permutation null (200)、5 noise features、family ablation、incremental vs baseline
"""
from __future__ import annotations

import os
import sys
import warnings
from math import erf, sqrt

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

REPO = "/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo"
sys.path.insert(0, os.path.join(REPO, "src"))

from sklearn.impute import SimpleImputer  # noqa: E402
from sklearn.linear_model import Ridge  # noqa: E402
from sklearn.ensemble import RandomForestRegressor  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402
from xgboost import XGBRegressor  # noqa: E402
from lightgbm import LGBMRegressor  # noqa: E402

from alpha_factory.phase1 import manifest  # noqa: E402

DATASET = os.path.join(REPO, "results", "evidence", "alpha_factory", "phase1", "phase1_dataset_full.parquet")
OUT = os.path.join(REPO, "results", "evidence", "alpha_factory", "phase1")
os.makedirs(OUT, exist_ok=True)

SEED = 20260910
N_PERM = 200

FAM_MAP = {"M0_RIDGE": "ridge", "M1_RF": "rf", "M2_XGB": "xgb", "M3_LGB": "lgb"}


def load():
    df = pd.read_parquet(DATASET)
    df = df[~df["censored"]].copy()
    df["year"] = df["signal_date"].dt.year
    feats = [f["feature_name"] for f in manifest.BASE_FEATURES if f["source"] != "UNAVAILABLE"]
    feats = [c for c in feats if c in df.columns]
    return df, feats


def daily_rank_ic(pred, y, dates):
    tmp = pd.DataFrame({"d": dates, "p": pred, "y": y}).dropna()
    ics = []
    for _, g in tmp.groupby("d"):
        if g["p"].nunique() < 5 or g["y"].nunique() < 5:
            continue
        ic = g["p"].corr(g["y"], method="spearman")
        if np.isfinite(ic):
            ics.append(ic)
    return float(np.mean(ics)) if ics else np.nan, len(ics)


def daily_quintiles(pred, y, dates):
    tmp = pd.DataFrame({"d": dates, "p": pred, "y": y}).dropna()
    rows = []
    for _, g in tmp.groupby("d"):
        if g["p"].nunique() < 10:
            continue
        q = pd.qcut(g["p"].rank(method="first"), 5, labels=False)
        g = g.assign(q=q)
        med = g.groupby("q")["y"].median()
        mean = g.groupby("q")["y"].mean()
        if med.shape[0] == 5:
            rows.append({"q5": med.loc[4], "q1": med.loc[0], "q5m": mean.loc[4], "q1m": mean.loc[0]})
    if not rows:
        return {}
    r = pd.DataFrame(rows)
    return {"q5_med": r["q5"].mean(), "q1_med": r["q1"].mean(), "spread_med": (r["q5"] - r["q1"]).mean(),
            "q5_mean": r["q5m"].mean(), "q1_mean": r["q1m"].mean()}


def pval_from_ics(ics):
    arr = np.asarray(ics, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 5:
        return np.nan
    sd = arr.std(ddof=1)
    if sd <= 0:
        return np.nan
    t = arr.mean() / (sd / sqrt(len(arr)))
    return 2 * (1 - 0.5 * (1 + erf(abs(t) / sqrt(2))))


def spearman(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 10:
        return np.nan
    ra = pd.Series(a[m]).rank().values
    rb = pd.Series(b[m]).rank().values
    return float(np.corrcoef(ra, rb)[0, 1])


def make_model(spec):
    family, p = spec["family"], spec["params"]
    if family == "ridge":
        return Ridge(alpha=p["alpha"], random_state=SEED)
    if family == "rf":
        return RandomForestRegressor(n_estimators=p["n_estimators"], max_depth=p["max_depth"],
                                     min_samples_leaf=p["min_samples_leaf"],
                                     max_features=p.get("max_features", 0.6), random_state=SEED, n_jobs=4)
    if family == "xgb":
        return XGBRegressor(n_estimators=p["n_estimators"], max_depth=p["max_depth"],
                            learning_rate=p["learning_rate"], subsample=p.get("subsample", 0.8),
                            colsample_bytree=p.get("colsample_bytree", 0.8),
                            min_child_weight=p.get("min_child_weight", 1),
                            reg_lambda=p.get("reg_lambda", 1.0), random_state=SEED, n_jobs=4, verbosity=0)
    if family == "lgb":
        return LGBMRegressor(n_estimators=p["n_estimators"], max_depth=p["max_depth"],
                             learning_rate=p["learning_rate"], subsample=p.get("subsample", 0.8),
                             colsample_bytree=p.get("colsample_bytree", 0.8),
                             min_child_samples=p.get("min_child_samples", 20),
                             reg_lambda=p.get("reg_lambda", 1.0), random_state=SEED, n_jobs=4, verbose=-1)
    raise ValueError(family)


def fit_predictor(spec, Xtr, ytr, needs_impute):
    """返回 (predict_fn, fitted_model)。imputer+scaler 只 fit train。"""
    imp = scaler = None
    Xtr = pd.DataFrame(Xtr)
    if needs_impute:
        imp = SimpleImputer(strategy="median").fit(Xtr)
        Xtr = pd.DataFrame(imp.transform(Xtr), columns=Xtr.columns, index=Xtr.index)
        scaler = StandardScaler().fit(Xtr)
        Xtr = pd.DataFrame(scaler.transform(Xtr), columns=Xtr.columns, index=Xtr.index)
    model = make_model(spec)
    model.fit(Xtr, ytr)

    def predict(X):
        X = pd.DataFrame(X)
        X = X.replace([np.inf, -np.inf], np.nan)
        if imp is not None:
            X = pd.DataFrame(imp.transform(X), columns=X.columns, index=X.index)
        if scaler is not None:
            X = pd.DataFrame(scaler.transform(X), columns=X.columns, index=X.index)
        return model.predict(X)

    return predict, model


def specs_list():
    out = []
    for key, cfg in manifest.ML_MODELS.items():
        fam = FAM_MAP[key]
        for variant, params in cfg["variants"].items():
            for target in ("Y_RETURN", "Y_RISK"):
                out.append({"family": fam, "variant": variant, "params": params, "target": target})
    return out


def main():
    df, feats = load()
    disc, val, test = df[df.year <= 2022], df[df.year == 2023], df[df.year == 2024]
    Xd = disc[feats].replace([np.inf, -np.inf], np.nan)
    Xv = val[feats].replace([np.inf, -np.inf], np.nan)
    Xt = test[feats].replace([np.inf, -np.inf], np.nan)

    recs = []
    for spec in specs_list():
        target = spec["target"]
        ycol = "close_ret_D20" if target == "Y_RETURN" else "MAE_D20"
        ytr = disc[ycol].values
        needs_imp = spec["family"] in ("ridge", "rf")
        pred_fn, m = fit_predictor(spec, Xd, ytr, needs_imp)
        pred_v, pred_t = pred_fn(Xv), pred_fn(Xt)
        ic_v, _ = daily_rank_ic(pred_v, val[ycol], val["signal_date"])
        ic_t, _ = daily_rank_ic(pred_t, test[ycol], test["signal_date"])
        ic_d, _ = daily_rank_ic(pred_fn(Xd), disc[ycol], disc["signal_date"])
        risk_v = spearman(pred_v, val[ycol].values) if target == "Y_RISK" else np.nan
        risk_t = spearman(pred_t, test[ycol].values) if target == "Y_RISK" else np.nan
        qv = daily_quintiles(pred_v, val[ycol], val["signal_date"])
        qt = daily_quintiles(pred_t, test[ycol], test["signal_date"])
        recs.append({"family": spec["family"], "variant": spec["variant"], "target": target,
                     "disc_ic": ic_d, "val_ic": ic_v, "test_ic": ic_t,
                     "val_q5_q1_med": qv.get("spread_med"), "test_q5_q1_med": qt.get("spread_med"),
                     "risk_val_spearman": risk_v, "risk_test_spearman": risk_t})
        print(f"{spec['family']}/{spec['variant']}/{target}: disc={ic_d:.4f} val={ic_v:.4f} test={ic_t:.4f}", flush=True)

    msum = pd.DataFrame(recs)
    msum.to_csv(os.path.join(OUT, "phase1_ml_model_summary.csv"), index=False)

    sel = {}
    all_specs = specs_list()
    for t in ("Y_RETURN", "Y_RISK"):
        sub = msum[msum.target == t]
        col = "val_ic" if t == "Y_RETURN" else "risk_val_spearman"
        row = sub.loc[sub[col].idxmax()].copy()
        sp = next(x for x in all_specs if x["family"] == row["family"] and x["variant"] == row["variant"] and x["target"] == t)
        row["params"] = sp["params"]
        sel[t] = row
    sel_df = pd.DataFrame(sel).T.reset_index().rename(columns={"index": "target"})
    sel_df.to_csv(os.path.join(OUT, "phase1_ml_selected.csv"), index=False)
    print("\nselected:", sel_df[["target", "family", "variant", "val_ic", "test_ic"]].to_string(index=False), flush=True)

    # ---- yearly stability for selected
    yearly = []
    for t in ("Y_RETURN", "Y_RISK"):
        s = sel[t]
        ycol = "close_ret_D20" if t == "Y_RETURN" else "MAE_D20"
        pred_fn, _ = fit_predictor(s, Xd, disc[ycol].values, s["family"] in ("ridge", "rf"))
        for y in (2021, 2022, 2023, 2024):
            sub = df[df.year == y]
            if len(sub) < 100:
                continue
            pred = pred_fn(sub[feats].replace([np.inf, -np.inf], np.nan))
            ic, _ = daily_rank_ic(pred, sub[ycol], sub["signal_date"])
            yearly.append({"target": t, "year": int(y), "rank_ic": ic,
                           "family": s["family"], "variant": s["variant"]})
    yd = pd.DataFrame(yearly)
    yd.to_csv(os.path.join(OUT, "phase1_ml_yearly.csv"), index=False)
    print("\nyearly:\n", yd.to_string(index=False), flush=True)

    # ---- feature importance (selected tree models)
    imp_rows = []
    for t in ("Y_RETURN", "Y_RISK"):
        s = sel[t]
        if s["family"] in ("rf", "xgb", "lgb"):
            ycol = "close_ret_D20" if t == "Y_RETURN" else "MAE_D20"
            pred_fn, m = fit_predictor(s, Xd, disc[ycol].values, s["family"] == "rf")
            imp = m.feature_importances_
            for f, v in zip(feats, imp):
                imp_rows.append({"target": t, "family": s["family"], "variant": s["variant"],
                                 "feature": f, "importance": float(v)})
    pd.DataFrame(imp_rows).to_csv(os.path.join(OUT, "phase1_ml_feature_importance.csv"), index=False)
    print("\nimportance saved", flush=True)

    # ---- permutation null (selected Y_RETURN model; N_PERM shuffles)
    s = sel["Y_RETURN"]
    needs_imp = s["family"] in ("ridge", "rf")
    null_rows = []
    rng = np.random.default_rng(SEED)
    for k in range(N_PERM):
        yperm = rng.permutation(disc["close_ret_D20"].values)
        pred_fn, _ = fit_predictor(s, Xd, yperm, needs_imp)
        pred = pred_fn(Xv)
        ic, _ = daily_rank_ic(pred, val["close_ret_D20"], val["signal_date"])
        null_rows.append({"perm": k, "val_ic": ic})
    null = pd.DataFrame(null_rows)
    real = float(sel["Y_RETURN"]["val_ic"])
    pct = (null["val_ic"] < real).mean()
    null.to_csv(os.path.join(OUT, "phase1_permutation_null.csv"), index=False)
    print(f"\npermutation null: real val_ic={real:.4f}, pct null below={pct:.1%}, null mean={null['val_ic'].mean():.4f}", flush=True)

    # ---- noise feature audit
    rng = np.random.default_rng(SEED + 1)
    noise = pd.DataFrame(rng.normal(size=(len(df), 5)), columns=[f"noise_{i}" for i in range(5)], index=df.index)
    df_n = pd.concat([df, noise], axis=1)
    Xd_n = df_n[df_n.year <= 2022][feats + [f"noise_{i}" for i in range(5)]].replace([np.inf, -np.inf], np.nan)
    Xv_n = df_n[df_n.year == 2023][feats + [f"noise_{i}" for i in range(5)]].replace([np.inf, -np.inf], np.nan)
    noise_rows = []
    for t in ("Y_RETURN", "Y_RISK"):
        s = sel[t]
        if s["family"] in ("rf", "xgb", "lgb"):
            ycol = "close_ret_D20" if t == "Y_RETURN" else "MAE_D20"
            allf = feats + [f"noise_{i}" for i in range(5)]
            pred_fn, m = fit_predictor(s, Xd_n, disc[ycol].values, s["family"] == "rf")
            imp = m.feature_importances_
            for f, v in zip(allf, imp):
                noise_rows.append({"target": t, "feature": f, "importance": float(v), "is_noise": f.startswith("noise_")})
    pd.DataFrame(noise_rows).to_csv(os.path.join(OUT, "phase1_noise_feature_audit.csv"), index=False)
    print("noise audit saved", flush=True)

    # ---- ablation (family-level, selected models)
    ab = []
    for t in ("Y_RETURN", "Y_RISK"):
        s = sel[t]
        ycol = "close_ret_D20" if t == "Y_RETURN" else "MAE_D20"
        needs_imp = s["family"] in ("ridge", "rf")
        full_ic = float(msum[(msum.target == t) & (msum.family == s["family"]) & (msum.variant == s["variant"])]["test_ic"].iloc[0])
        for fam, cols in manifest.ABLATION_FAMILIES.items():
            drop = [c for c in cols if c in feats]
            keep = [c for c in feats if c not in drop]
            pred_fn, _ = fit_predictor(s, Xd[keep], disc[ycol].values, needs_imp)
            pred = pred_fn(test[keep].replace([np.inf, -np.inf], np.nan))
            ic, _ = daily_rank_ic(pred, test[ycol], test["signal_date"])
            ab.append({"target": t, "removed_family": fam, "test_ic": ic, "test_ic_full": full_ic,
                       "delta": ic - full_ic})
    pd.DataFrame(ab).to_csv(os.path.join(OUT, "phase1_ablation.csv"), index=False)
    print("\nablation:\n", pd.DataFrame(ab).to_string(index=False), flush=True)

    # ---- incremental vs simple baseline linear
    inc = []
    base_feats = [c for c in manifest.INCREMENTAL_BASELINE if c in feats]
    for t in ("Y_RETURN", "Y_RISK"):
        s = sel[t]
        ycol = "close_ret_D20" if t == "Y_RETURN" else "MAE_D20"
        needs_imp = s["family"] in ("ridge", "rf")
        for name, cols in (("baseline_linear", base_feats), ("full_ml", feats)):
            pred_fn, _ = fit_predictor(s, Xd[cols], disc[ycol].values, needs_imp)
            ic_v, _ = daily_rank_ic(pred_fn(val[cols].replace([np.inf, -np.inf], np.nan)), val[ycol], val["signal_date"])
            ic_t, _ = daily_rank_ic(pred_fn(test[cols].replace([np.inf, -np.inf], np.nan)), test[ycol], test["signal_date"])
            inc.append({"target": t, "model": name, "val_ic": ic_v, "test_ic": ic_t})
    pd.DataFrame(inc).to_csv(os.path.join(OUT, "phase1_incremental_ml.csv"), index=False)
    print("\nincremental:\n", pd.DataFrame(inc).to_string(index=False), flush=True)

    print("\nENGINE M DONE", flush=True)


if __name__ == "__main__":
    main()
