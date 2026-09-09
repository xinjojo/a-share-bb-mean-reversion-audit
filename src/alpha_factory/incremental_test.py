"""A-Share Alpha Factory — incremental alpha test.

回答：控制已有 Alpha 后，新因子还有没有额外信息？
Phase 0：接口 + smoke（residual IC / partial correlation / incremental R²）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def residual_ic(new_factor: pd.Series, label: pd.Series,
                existing_factors: pd.DataFrame, date: pd.Series,
                n_boot: int = 200, seed: int = 2026) -> dict:
    """IC of new factor on label residuals after regressing label on existing factors
    (per-date cross-sectional)."""
    d = pd.DataFrame({'date': date.values, 'f': new_factor.values, 'y': label.values})
    for c in existing_factors.columns:
        d[c] = existing_factors[c].values
    d = d.dropna()
    if len(d) < 50:
        return {'residual_ic': np.nan, 'partial_corr': np.nan, 'n': len(d)}
    ics = []
    rng = np.random.default_rng(seed)
    for _ in range(n_boot):
        idx = rng.integers(0, len(d), size=len(d))
        sub = d.iloc[idx]
        if len(sub) < 30:
            continue
        ics.append(_ic_once(sub))
    return {
        'residual_ic': float(np.mean([x[0] for x in ics])) if ics else np.nan,
        'partial_corr': float(np.mean([x[1] for x in ics])) if ics else np.nan,
        'n': len(d),
    }


def _ic_once(d: pd.DataFrame):
    xcols = [c for c in d.columns if c not in ('date', 'f', 'y')]
    if xcols:
        X = np.column_stack([d[c].to_numpy(float) for c in xcols])
        X = np.column_stack([np.ones(len(d)), X])
        beta, *_ = np.linalg.lstsq(X, d['y'].to_numpy(float), rcond=None)
        resid = d['y'].to_numpy(float) - X @ beta
    else:
        resid = d['y'].to_numpy(float)
    m = np.isfinite(d['f'].to_numpy(float)) & np.isfinite(resid)
    if m.sum() < 10:
        return (np.nan, np.nan)
    ic = stats.pearsonr(d['f'].to_numpy(float)[m], resid[m])[0]
    # partial correlation of f with y given existing
    xcols2 = [c for c in d.columns if c not in ('date', 'f', 'y')]
    if xcols2:
        X = np.column_stack([np.ones(len(d)), np.column_stack(
            [d[c].to_numpy(float) for c in xcols2])])
        bf, *_ = np.linalg.lstsq(X, d['f'].to_numpy(float), rcond=None)
        rf = d['f'].to_numpy(float) - X @ bf
        by, *_ = np.linalg.lstsq(X, d['y'].to_numpy(float), rcond=None)
        ry = d['y'].to_numpy(float) - X @ by
        m2 = np.isfinite(rf) & np.isfinite(ry)
        pc = stats.pearsonr(rf[m2], ry[m2])[0] if m2.sum() > 10 else np.nan
    else:
        pc = ic
    return (ic, pc)


def incremental_r2(y: pd.Series, base: pd.DataFrame, new: pd.Series) -> dict:
    """R² gain from adding new factor to linear baseline."""
    m = np.isfinite(y.to_numpy(float))
    yy = y.to_numpy(float)[m]
    bcols = [c for c in base.columns if np.isfinite(base[c].to_numpy(float)[m]).sum() > 50]
    if not bcols:
        return {'base_r2': np.nan, 'new_r2': np.nan, 'delta_r2': np.nan}
    Xb = np.column_stack([np.ones(m.sum()),
                          np.column_stack([base[c].to_numpy(float)[m] for c in bcols])])
    beta, *_ = np.linalg.lstsq(Xb, yy, rcond=None)
    r2b = 1 - np.sum((yy - Xb @ beta) ** 2) / np.sum((yy - yy.mean()) ** 2)
    Xn = np.column_stack([Xb, new.to_numpy(float)[m]])
    betan, *_ = np.linalg.lstsq(Xn, yy, rcond=None)
    r2n = 1 - np.sum((yy - Xn @ betan) ** 2) / np.sum((yy - yy.mean()) ** 2)
    return {'base_r2': float(r2b), 'new_r2': float(r2n), 'delta_r2': float(r2n - r2b)}
