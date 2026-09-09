"""A-Share Alpha Factory — redundancy / correlation filter.

因子初筛通过后计算 Pearson / Spearman 相关并做层次聚类。
|rho| >= 0.80 冻结预警阈值：标 DUPLICATE candidate（不自动删除，必须记录 duplicate_of）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.cluster import hierarchy
from scipy.stats import pearsonr, spearmanr

REDUNDANCY_THRESHOLD = 0.80


def correlation_matrix(factors: pd.DataFrame, method: str = 'pearson') -> pd.DataFrame:
    """Cross-sectional correlation across factor columns (row-wise pairs)."""
    cols = list(factors.columns)
    n = len(cols)
    out = pd.DataFrame(np.eye(n), index=cols, columns=cols, dtype=float)
    for i in range(n):
        for j in range(i + 1, n):
            a = factors[cols[i]].to_numpy(float)
            b = factors[cols[j]].to_numpy(float)
            m = np.isfinite(a) & np.isfinite(b)
            if m.sum() < 10:
                r = np.nan
            else:
                r = (pearsonr(a[m], b[m])[0] if method == 'pearson'
                     else spearmanr(a[m], b[m])[0])
            out.iloc[i, j] = out.iloc[j, i] = r
    return out


def find_duplicates(corr: pd.DataFrame, threshold: float = REDUNDANCY_THRESHOLD,
                    order: list[str] | None = None) -> list[dict]:
    """Greedy duplicate detection: keep earlier factor (order), mark later ones as
    DUPLICATE candidate of it when |rho| >= threshold."""
    cols = order or list(corr.columns)
    dup = []
    kept = []
    for c in cols:
        hit = None
        for k in kept:
            r = corr.loc[k, c]
            if np.isfinite(r) and abs(r) >= threshold:
                hit = k
                break
        if hit is not None:
            dup.append({'factor_id': c, 'duplicate_of': hit,
                        'rho': float(corr.loc[hit, c])})
        else:
            kept.append(c)
    return dup


def hierarchical_clusters(corr: pd.DataFrame, threshold: float = REDUNDANCY_THRESHOLD,
                          method: str = 'average') -> dict:
    """Hierarchical clustering of factors; returns {cluster_label: [factor_ids]}."""
    cols = list(corr.columns)
    if len(cols) < 2:
        return {}
    dist = np.clip(1 - corr.values, 0.0, None)
    np.fill_diagonal(dist, 0.0)
    dist = np.nan_to_num(dist, nan=1.0)
    Z = hierarchy.linkage(dist[np.triu_indices(len(cols), 1)], method=method)
    t = hierarchy.fcluster(Z, 1.0 - threshold, criterion='distance')
    out = {}
    for c, lab in zip(cols, t):
        out.setdefault(f'CL{lab}', []).append(c)
    return out
