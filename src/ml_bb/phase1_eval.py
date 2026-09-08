"""ML-BB Phase 1 评价：quintile / Top-K / 稳定性 / 模型 agreement / bootstrap（Registry 冻结口径）。

输入：walk_forward_predictions.csv（由 phase1_pipeline.py 生成）
输出：ranking_quintile_stats.csv / topk_comparison.csv / yearly_stability.csv / model_agreement.csv
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

ML_OUT = os.path.join(ROOT, "results", "evidence", "ml_bb")
SEED = 2024
rng = np.random.default_rng(SEED)


def cluster_bootstrap_ci(df, score_col, y_col, date_col, stat_fn, n=1000, alpha=0.05):
    """按 signal_date 聚类 bootstrap。返回 (lo, hi)。"""
    dates = df[date_col].unique()
    lo_hi = []
    for _ in range(n):
        d_sample = rng.choice(dates, size=len(dates), replace=True)
        sdf = pd.concat([df[df[date_col] == d] for d in d_sample])
        lo_hi.append(stat_fn(sdf))
    lo_hi = np.array(lo_hi)
    return np.percentile(lo_hi, 100 * alpha / 2), np.percentile(lo_hi, 100 * (1 - alpha / 2))


def _bucket_stats(df):
    y = df["y"]
    return pd.Series({
        "N": len(df), "D20_mean": y.mean(), "D20_median": y.median(),
        "positive_rate": (y > 0).mean() * 100,
    })


def main() -> None:
    pdf = pd.read_csv(os.path.join(ML_OUT, "walk_forward_predictions.csv"), parse_dates=["signal_date"])

    # ---- 1. quintile stats（Y1, 每年每模型）----
    qrows = []
    for (grp, model, year), g in pdf[pdf["task"] == "Y1"].groupby(["group", "model", "year"]):
        g = g.copy()
        g["q"] = pd.qcut(g["score"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
        for q, gg in g.groupby("q", observed=True):
            qrows.append({"group": grp, "model": model, "year": year, "quintile": int(q),
                          **_bucket_stats(gg).to_dict()})
    qdf = pd.DataFrame(qrows)
    qdf.to_csv(os.path.join(ML_OUT, "ranking_quintile_stats.csv"), index=False)
    print("quintile stats 已输出:", qdf.shape)

    # ---- 2. yearly stability（Y1 Q5-Q1 spread）----
    stab = []
    for (grp, model, year), g in pdf[pdf["task"] == "Y1"].groupby(["group", "model", "year"]):
        g = g.copy()
        g["q"] = pd.qcut(g["score"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
        q5 = g[g["q"] == 5]["y"]; q1 = g[g["q"] == 1]
        overall = g["y"].median()
        stab.append({"group": grp, "model": model, "year": year,
                     "Q5_median": q5.median(), "Q1_median": q1.median(),
                     "Q5_Q1_spread": q5.median() - q1.median(),
                     "overall_median": overall,
                     "Q5_vs_overall": q5.median() - overall,
                     "Q5_positive_rate": (q5 > 0).mean() * 100,
                     "Q1_positive_rate": (q1 > 0).mean() * 100})
    sdf = pd.DataFrame(stab)
    sdf.to_csv(os.path.join(ML_OUT, "yearly_stability.csv"), index=False)
    print("yearly stability 已输出:", sdf.shape)

    # ---- 3. Top-K comparison（2024 NEW_ENTRY, 按 signal_date 分组）----
    y1_2024 = pdf[(pdf["task"] == "Y1") & (pdf["year"] == "2024") & (pdf["group"] == "NEW_ENTRY")]
    # baselines 用已落盘特征（避免重跑全量特征构建）
    feat = pd.read_parquet(os.path.join(ML_OUT, "ml_features_full.parquet"),
                           columns=["signal_id", "atr14_pct"])
    meta = pd.read_parquet(os.path.join(ROOT, "results/evidence/sigpath/signal_path_20d_wide.parquet"),
                           columns=["signal_id", "signal_day_amount", "bb_z"])
    meta = meta.merge(feat, on="signal_id", how="left")
    topk = []
    for model, g in y1_2024.groupby("model"):
        g = g.copy()
        g = g.merge(meta, on="signal_id", how="left")
        for k, col, asc in [("model", "score", False), ("amount", "signal_day_amount", False),
                            ("bb_z", "bb_z", False), ("atr", "atr14_pct", False),
                            ("random", "score", False)]:
            gg = g.copy()
            if col == "score" and k == "model":
                pass
            elif k == "random":
                gg["r"] = rng.random(len(gg))
                col = "r"
            gg = gg.sort_values(col, ascending=asc)
            for top in [1, 3, 5]:
                # 按 signal_date 组内选 top-K
                sel = gg.groupby("signal_date").head(top)
                if len(sel) == 0:
                    continue
                ci = cluster_bootstrap_ci(sel, col, "y", "signal_date", lambda s: s["y"].mean())
                topk.append({"model": k, "top_k": top, "N": len(sel),
                             "D20_mean": sel["y"].mean(), "D20_median": sel["y"].median(),
                             "ci_lo": ci[0], "ci_hi": ci[1], "bad_rate": (sel["y"] <= -20).mean() * 100})
    tdf = pd.DataFrame(topk)
    tdf.to_csv(os.path.join(ML_OUT, "topk_comparison.csv"), index=False)
    print("topk comparison 已输出:", tdf.shape)

    # ---- 4. Model agreement（Y1 2024 Top20% overlap）----
    agree = []
    y1_2024p = y1_2024.pivot_table(index="signal_id", columns="model", values="score")
    models = [m for m in y1_2024p.columns if y1_2024p[m].notna().sum() > 0]
    for i, ma in enumerate(models):
        for mb in models[i + 1:]:
            a = set(y1_2024p[y1_2024p[ma] >= y1_2024p[ma].quantile(0.8)].index)
            b = set(y1_2024p[y1_2024p[mb] >= y1_2024p[mb].quantile(0.8)].index)
            inter = len(a & b); union = len(a | b)
            agree.append({"model_a": ma, "model_b": mb, "top20_overlap": inter,
                          "union": union, "jaccard": inter / union if union else np.nan})
    adf = pd.DataFrame(agree)
    adf.to_csv(os.path.join(ML_OUT, "model_agreement.csv"), index=False)
    print("model agreement 已输出:", adf.shape)

    # ---- 5. BAD (Y6) quintile bad-rate 梯度（2024）----
    y6_2024 = pdf[(pdf["task"] == "Y6") & (pdf["year"] == "2024")]
    bq = []
    for (grp, model), g in y6_2024.groupby(["group", "model"]):
        g = g.copy()
        g["q"] = pd.qcut(g["score"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
        for q, gg in g.groupby("q", observed=True):
            bq.append({"group": grp, "model": model, "year": "2024", "quintile": int(q),
                       "N": len(gg), "BAD_rate": gg["y"].mean() * 100})
    bdf = pd.DataFrame(bq)
    bdf.to_csv(os.path.join(ML_OUT, "ranking_quintile_bad.csv"), index=False)
    print("BAD quintile 已输出:", bdf.shape)


if __name__ == "__main__":
    main()
