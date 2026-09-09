"""A-Share Alpha Factory — label engine.

Feature 与 label 物理分离：label 只能由本模块基于 outcome 列生成，
绝不能出现在 factor feature 列中。Universe A 复用 SIGPATH canonical outcome。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Universe A labels derived from SIGPATH canonical outcome columns
LABEL_COLS_A = {
    'Y1': 'close_ret_D20',        # regression: D20 close return
    'Y2': 'MFE_D20',              # regression: D20 max favorable excursion
    'Y3': 'MAE_D20',              # regression: D20 max adverse excursion
}
# classification thresholds (frozen in registry, not tunable here)
GOOD_THRESHOLD = 0.0
STRONG_THRESHOLD = 0.05
BAD_THRESHOLD = -0.20


def build_labels_a(df: pd.DataFrame) -> pd.DataFrame:
    """Build label columns for Universe A. Input must contain close_ret_D1/D5/D10/D20,
    MFE_D20, MAE_D20 (canonical SIGPATH outcome). Returns only label columns."""
    need = ['close_ret_D1', 'close_ret_D5', 'close_ret_D10', 'close_ret_D20',
            'MFE_D20', 'MAE_D20']
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f'outcome columns missing: {missing}')
    out = pd.DataFrame(index=df.index)
    out['fwd_ret_1'] = df['close_ret_D1']
    out['fwd_ret_5'] = df['close_ret_D5']
    out['fwd_ret_10'] = df['close_ret_D10']
    out['fwd_ret_20'] = df['close_ret_D20']
    out['MFE_20'] = df['MFE_D20']
    out['MAE_20'] = df['MAE_D20']
    out['GOOD'] = (df['close_ret_D20'] > GOOD_THRESHOLD).astype(int)
    out['STRONG'] = (df['MFE_D20'] >= STRONG_THRESHOLD).astype(int)
    out['BAD'] = (df['MAE_D20'] <= BAD_THRESHOLD).astype(int)
    return out


def build_labels_b(panel: pd.DataFrame, horizons=(1, 5, 10, 20, 60)) -> pd.DataFrame:
    """Universe B forward labels on a panel (ts_code × date), close-to-close adjusted.
    Phase 0: interface + smoke only; not used for formal research yet."""
    g = panel.sort_values(['ts_code', 'date']).copy()
    out = pd.DataFrame(index=g.index)
    c = g['close_adj']
    for h in horizons:
        out[f'fwd_ret_{h}'] = g.groupby('ts_code')['close_adj'].transform(
            lambda v: v.shift(-h) / v - 1.0)
    return out


def assert_feature_label_separated(feature_cols, label_cols) -> None:
    overlap = set(feature_cols) & set(label_cols)
    if overlap:
        raise ValueError(f'feature/label column overlap: {sorted(overlap)}')
