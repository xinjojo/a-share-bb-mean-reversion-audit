"""ML-BB Phase 1 正式标签（Registry 冻结，见 ML_LABEL_REGISTRY.csv）。

只读 signal_date 之后的 outcome（wide 的 D1-D20 列），输出 Y1-Y6。
censored（available_future_days<20）单独标记，不进训练/评价。
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

SIGPATH_WIDE = os.path.join(ROOT, "results", "evidence", "sigpath", "signal_path_20d_wide.parquet")
ML_OUT = os.path.join(ROOT, "results", "evidence", "ml_bb")


def build_labels_full() -> pd.DataFrame:
    cols = ["signal_id", "ts_code", "entry_role", "close_ret_D20", "MFE_D20", "MAE_D20", "available_future_days"]
    w = pd.read_parquet(SIGPATH_WIDE, columns=cols)
    lab = pd.DataFrame({"signal_id": w["signal_id"], "ts_code": w["ts_code"], "entry_role": w["entry_role"]})
    lab["Y1"] = w["close_ret_D20"].astype(float)
    lab["Y2"] = w["MFE_D20"].astype(float)
    lab["Y3"] = w["MAE_D20"].astype(float)
    lab["Y4_GOOD"] = (w["close_ret_D20"] > 0).astype(int)
    lab["Y5_STRONG_RECOVERY"] = (w["MFE_D20"] >= 5.0).astype(int)
    lab["Y6_BAD"] = (w["MAE_D20"] <= -20.0).astype(int)
    lab["available_future_days"] = w["available_future_days"].astype(int)
    lab["censored"] = (w["available_future_days"] < 20).astype(int)
    return lab


if __name__ == "__main__":
    lab = build_labels_full()
    os.makedirs(ML_OUT, exist_ok=True)
    out = os.path.join(ML_OUT, "ml_labels_full.parquet")
    lab.to_parquet(out, index=False)
    print("labels:", lab.shape)
    print("censored:", int(lab["censored"].sum()))
    for c in ["Y4_GOOD", "Y5_STRONG_RECOVERY", "Y6_BAD"]:
        print(f"{c} positive rate: {lab[c].mean():.4f} (N={int(lab[c].sum())})")
    print("已落盘:", out)
