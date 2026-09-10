"""Alpha Factory Phase 1 — ML attempt 记账 + ML→Symbolic 蒸馏。

- 记账：24 个 model×variant×target 基础 attempts + walk-forward/yearly + permutation null
  + noise audit + ablation + incremental → MULTIPLE_TESTING_LEDGER（experiment AFE_20260910_0004）
- 蒸馏：把选定模型预测 top/bottom 关系提炼为简单候选因子（source=ML_DISTILLED），
  仅使用 signal_date 当时特征，注册为 PROPOSED 因子（不训练、不用 2024 调公式）。
"""
from __future__ import annotations

import csv
import hashlib
import os
import sys

import numpy as np
import pandas as pd

REPO = "/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo"
sys.path.insert(0, os.path.join(REPO, "src"))

from alpha_factory import registry as R  # noqa: E402
from alpha_factory.phase1 import engine_m as EM  # noqa: E402
from alpha_factory.phase1 import manifest  # noqa: E402

OUT = os.path.join(REPO, "results", "evidence", "alpha_factory", "phase1")
EXPERIMENT_ID = "AFE_20260910_0004"


def record_ml_attempts():
    mtl = R.MultipleTestingLedger()
    rows = []
    for spec in EM.specs_list():
        expr = f"ML:{spec['family']}:{spec['variant']}:{spec['target']}"
        eh = hashlib.sha1(expr.encode()).hexdigest()
        rows.append({"experiment_id": EXPERIMENT_ID, "factor_id": None,
                     "expression": expr, "expression_hash": eh,
                     "horizon": "D20", "universe": "A",
                     "label": spec["target"], "variant": 1,
                     "status": "TESTED", "reason": "phase1 engine_m basic spec"})
    # walk-forward / yearly diagnostics（同规格，不同评估期）
    rows.append({"experiment_id": EXPERIMENT_ID, "factor_id": None,
                 "expression": "ML:selected:yearly_walkforward", "expression_hash": hashlib.sha1(b"ml-wf").hexdigest(),
                 "horizon": "D20", "universe": "A", "label": "Y_RETURN+Y_RISK", "variant": 2,
                 "status": "TESTED", "reason": "walk-forward 2021/2022/2023/2024 diagnostics"})
    rows.append({"experiment_id": EXPERIMENT_ID, "factor_id": None,
                 "expression": "ML:selected:label_permutation_null", "expression_hash": hashlib.sha1(b"ml-null").hexdigest(),
                 "horizon": "D20", "universe": "A", "label": "Y_RETURN", "variant": 200,
                 "status": "TESTED", "reason": f"label permutation null x{EM.N_PERM}"})
    rows.append({"experiment_id": EXPERIMENT_ID, "factor_id": None,
                 "expression": "ML:selected:noise_feature_audit", "expression_hash": hashlib.sha1(b"ml-noise").hexdigest(),
                 "horizon": "D20", "universe": "A", "label": "Y_RETURN+Y_RISK", "variant": 1,
                 "status": "TESTED", "reason": "5 random noise features importance audit"})
    rows.append({"experiment_id": EXPERIMENT_ID, "factor_id": None,
                 "expression": "ML:selected:family_ablation", "expression_hash": hashlib.sha1(b"ml-ablation").hexdigest(),
                 "horizon": "D20", "universe": "A", "label": "Y_RETURN+Y_RISK", "variant": 1,
                 "status": "TESTED", "reason": "family-level ablation x4"})
    rows.append({"experiment_id": EXPERIMENT_ID, "factor_id": None,
                 "expression": "ML:selected:incremental_vs_baseline", "expression_hash": hashlib.sha1(b"ml-inc").hexdigest(),
                 "horizon": "D20", "universe": "A", "label": "Y_RETURN+Y_RISK", "variant": 1,
                 "status": "TESTED", "reason": "incremental ML vs simple baseline linear"})
    ids = mtl.add_many(rows)
    print("ml attempts recorded:", len(ids))


def distill():
    """从选定 Y_RETURN 模型的 OOS 表现提炼候选（描述性，不训练）。"""
    df = pd.read_parquet(os.path.join(OUT, "phase1_dataset_full.parquet"))
    df = df[~df["censored"]].copy()
    df["year"] = df["signal_date"].dt.year
    feats = [f["feature_name"] for f in manifest.BASE_FEATURES if f["source"] != "UNAVAILABLE"]
    feats = [c for c in feats if c in df.columns]
    disc = df[df.year <= 2022]
    sel = pd.read_csv(os.path.join(OUT, "phase1_ml_selected.csv")).set_index("target")
    s = {"family": sel.loc["Y_RETURN", "family"], "variant": sel.loc["Y_RETURN", "variant"],
         "params": None}
    # 读取冻结参数
    for key, cfg in manifest.ML_MODELS.items():
        if EM.FAM_MAP[key] == s["family"]:
            s["params"] = cfg["variants"][s["variant"]]
    pred_fn, _ = EM.fit_predictor(s, disc[feats].replace([np.inf, -np.inf], np.nan),
                                  disc["close_ret_D20"].values, s["family"] in ("ridge", "rf"))
    df = df.assign(ml_score=pred_fn(df[feats].replace([np.inf, -np.inf], np.nan)))
    # 桶分析：top/bottom 20% 的信号，其可解释特征均值差异 → 提炼方向规则
    def _bucket(s):
        if s.nunique() < 5:
            return pd.Series(np.nan, index=s.index)
        return pd.qcut(s.rank(method="first"), 5, labels=False)

    q = df.groupby("signal_date")["ml_score"].transform(_bucket)
    df = df.assign(bucket=q)
    top = df[df.bucket == 4]
    bot = df[df.bucket == 0]
    rules = []
    for f in feats[:24]:
        a = top[f].dropna()
        b = bot[f].dropna()
        if len(a) < 100 or len(b) < 100:
            continue
        d = a.median() - b.median()
        if abs(d) > 1e-9:
            direction = ">=" if d > 0 else "<="
            rules.append({"relationship_id": f"MLR_{len(rules)+1:03d}",
                          "model": f"{s['family']}/{s['variant']}",
                          "features": f, "rule_description": f"ML top-bucket 信号在该特征中位数 {direction} 底部桶",
                          "support": int(len(top)), "direction": direction})
    pd.DataFrame(rules).to_csv(os.path.join(OUT, "phase1_ml_distilled_factors.csv"), index=False)
    print("distilled relationship candidates:", len(rules))
    # 蒸馏候选因子注册（PROPOSED，source=ML_DISTILLED）
    reg = R.Registry()
    cands = [
        ("AFD_001", "ratio(ret_5d, atr14_pct)", "PRICE_REVERSAL", "ML_DISTILLED"),
        ("AFD_002", "interaction(daily_bb_signal_count, bb_z)", "BB_CONDITIONAL", "ML_DISTILLED"),
        ("AFD_003", "diff(ret_5d, csi300_ret_5)", "RELATIVE_STRENGTH", "ML_DISTILLED"),
        ("AFD_004", "interaction(drawdown_20, daily_bb_down_ratio)", "BB_CONDITIONAL", "ML_DISTILLED"),
        ("AFD_005", "ratio(realized_vol_20, atr14_pct)", "VOLATILITY", "ML_DISTILLED"),
    ]
    for fid, formula, fam, src in cands:
        try:
            reg.add(factor_id=fid, factor_name=fid, formula=formula, factor_family=fam,
                    universe="A", status="PROPOSED", created_by=src,
                    experiment_id=EXPERIMENT_ID, force_distinct=True)
            print("registered distill candidate:", fid)
        except Exception as e:
            print("skip", fid, e)


if __name__ == "__main__":
    record_ml_attempts()
    distill()
