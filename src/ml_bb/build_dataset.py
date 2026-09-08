"""ML-BB dataset builder（Phase 0）：按 signal_id 合并 feature 与 label。

特征与标签在 build_features.py / build_labels.py 中物理分离，
本模块只做 signal_id 内连接——这是唯一合法合并路径。
"""
from __future__ import annotations

import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from src.ml_bb.build_features import build_features, _FEATURES  # noqa: E402
from src.ml_bb.build_labels import build_labels  # noqa: E402

ML_OUT = os.path.join(ROOT, "results", "evidence", "ml_bb")


def build_dataset(sample_signals=None, out_path: str | None = None) -> pd.DataFrame:
    feat = build_features(sample_signals=sample_signals)
    lab = build_labels(sample_signals=sample_signals)
    ds = feat.merge(lab, on="signal_id", how="inner")
    assert len(ds) == len(feat), "merge 后行数不一致（signal_id 必须唯一）"
    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        ds.to_parquet(out_path, index=False)
    return ds


if __name__ == "__main__":
    out = os.path.join(ML_OUT, "ml_smoke_dataset.parquet")
    ds = build_dataset(out_path=out)
    print("dataset:", ds.shape, "->", out)
    print(ds.head(3).to_string(index=False))
