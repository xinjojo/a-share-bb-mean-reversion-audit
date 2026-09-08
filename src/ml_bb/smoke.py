"""ML-BB Phase 0 smoke test：最小流水线验证。

- 从 canonical SIGPATH 按时间顺序抽 3000 条 signal（<=2024-12-31，天然满足 2025-2026 零读取）。
- 只构造 3~5 个安全特征（bb_z / bb_width_pct / ret_5d / log_amount / entry_role）。
- LogisticRegression 训练（GOOD_D20 = close_ret_D20 > 0）。

⚠️ 这是工程 smoke test：
- 只验证 数据读取 → 特征构建 → 标签构建 → merge → 训练 全链路可跑通；
- 不报告模型表现为研究结论；不调参。
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from src.ml_bb.build_dataset import build_dataset  # noqa: E402

ML_OUT = os.path.join(ROOT, "results", "evidence", "ml_bb")

SIGPATH_WIDE = os.path.join(ROOT, "results", "evidence", "sigpath", "signal_path_20d_wide.parquet")


def pick_smoke_signals(n: int = 3000, seed: int = 42) -> pd.Series:
    """按时间顺序（signal_date）均匀抽取 n 条信号，保证不触碰 2025-2026。"""
    ids = pd.read_parquet(SIGPATH_WIDE, columns=["signal_id", "signal_date", "entry_date"])
    ids = ids.sort_values("signal_date").reset_index(drop=True)
    assert ids["signal_date"].max() <= "2024-12-31", "universe 不应包含 2025-2026"
    idx = np.linspace(0, len(ids) - 1, n, dtype=int)
    return ids["signal_id"].iloc[idx].reset_index(drop=True)


def main() -> None:
    seed = 42
    rng = np.random.default_rng(seed=seed)
    sigs = pick_smoke_signals(3000)
    ds = build_dataset(sample_signals=sigs)

    # 只用安全特征（entry_role 做简单序数编码：NEW_ENTRY=0, ADD_ON_1..4=1..4）
    role_map = {f"ADD_ON_{i}": i for i in range(1, 5)}
    role_map["NEW_ENTRY"] = 0
    ds["entry_role_ord"] = ds["entry_role"].map(role_map)

    feat_cols = ["bb_z", "bb_width_pct", "ret_5d", "log_amount", "entry_role_ord"]
    X = ds[feat_cols].astype(float)
    y = ds["GOOD_D20"].astype(int)

    # 丢弃缺失特征行（smoke 允许；Phase 1 才做正式缺失策略）
    mask = X.notna().all(axis=1)
    X, y = X[mask], y[mask]

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.3, random_state=seed, stratify=y)

    clf = LogisticRegression(max_iter=1000, random_state=seed)
    clf.fit(X_tr, y_tr)
    acc = accuracy_score(y_te, clf.predict(X_te))

    print("=" * 60)
    print("ML-BB Phase 0 smoke 完成（仅验证流水线，非研究结论）")
    print("-" * 60)
    print(f"抽取信号数        : {len(sigs)}")
    print(f"dataset 行数      : {len(ds)}（缺失特征剔除后 {len(X)}）")
    print(f"特征列            : {feat_cols}")
    print(f"标签 GOOD_D20 正类: {int(y.sum())} / {len(y)}（{y.mean()*100:.1f}%）")
    print(f"train/test        : {len(X_tr)} / {len(X_te)}")
    print(f"LogReg test acc   : {acc:.4f}（仅供 smoke 断言，不代表 alpha）")
    print("=" * 60)
    assert 0.3 < acc < 1.0, "acc 超出 smoke 合理范围，检查流水线"

    # 落盘 smoke dataset
    out = os.path.join(ML_OUT, "ml_smoke_dataset.parquet")
    ds.to_parquet(out, index=False)
    print(f"smoke dataset 已落盘: {out}（{os.path.getsize(out)/1e6:.1f} MB）")


if __name__ == "__main__":
    main()
