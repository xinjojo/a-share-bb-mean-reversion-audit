"""ML-BB label builder（Phase 0）。

物理隔离原则（ML_ARCHITECTURE.md 第 2 节）：
- 本模块只读取信号日之后的 outcome（D1-D20 自然价格路径），输出标签。
- 与 build_features.py 完全分离，合并仅通过 signal_id。

标签（Phase 0 smoke）：
- GOOD_D20 = close_ret_D20 > 0（D20 收盘相对 entry_cost 收益为正）
  —— 仅用于流水线冒烟，不构成研究结论。
"""
from __future__ import annotations

import os
import sys
from typing import Optional

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

SIGPATH_WIDE = os.path.join(ROOT, "results", "evidence", "sigpath", "signal_path_20d_wide.parquet")


def build_labels(
    wide_path: str = SIGPATH_WIDE,
    sample_signals: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """构建标签表（signal_id + GOOD_D20 等）。"""
    cols = ["signal_id", "close_ret_D20", "available_future_days"]
    wide = pd.read_parquet(wide_path, columns=cols)
    if sample_signals is not None:
        wide = wide[wide["signal_id"].isin(set(sample_signals))].copy()

    lab = pd.DataFrame({"signal_id": wide["signal_id"]})
    lab["close_ret_D20"] = wide["close_ret_D20"].astype(float)
    lab["available_future_days"] = wide["available_future_days"].astype(int)
    # 标签：D20 完整路径（available_future_days>=20）且收益为正 → GOOD
    lab["GOOD_D20"] = np.where(
        (lab["available_future_days"] >= 20) & (lab["close_ret_D20"] > 0), 1, 0
    )
    # 未满 20 日的 censored 信号单独标记（Phase 1 再决定处理方式）
    lab["censored"] = (lab["available_future_days"] < 20).astype(int)
    return lab


if __name__ == "__main__":
    l = build_labels()
    print("label 表:", l.shape, "| GOOD_D20 正样本:", int(l["GOOD_D20"].sum()), "/", len(l))
