"""A-Share Alpha Factory — fast screening engine.

横截面 IC 纪律：按日计算横截面 IC（Pearson / Spearman），对每日 IC 时间序列做统计。
BB universe 支持按 signal_date 聚类 bootstrap，避免同日大量信号冒充独立样本。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scipy import stats


def daily_cross_sectional_ic(factor: pd.Series, label: pd.Series,
                             date: pd.Series) -> pd.DataFrame:
    """Per-date cross-sectional IC (Pearson & Spearman) and coverage.
    Returns DataFrame indexed by date with columns n, ic, rank_ic."""
    d = pd.DataFrame({'date': date.values, 'f': factor.values, 'y': label.values})
    d = d.dropna(subset=['f', 'y'])
    rows = []
    for dt, g in d.groupby('date'):
        if len(g) < 5:
            continue
        if g['f'].nunique() <= 1 or g['y'].nunique() <= 1:
            rows.append({'date': dt, 'n': len(g), 'ic': np.nan, 'rank_ic': np.nan})
            continue
        ic = stats.pearsonr(g['f'], g['y'])[0]
        ric = stats.spearmanr(g['f'], g['y'])[0]
        rows.append({'date': dt, 'n': len(g), 'ic': ic, 'rank_ic': ric})
    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=['date', 'n', 'ic', 'rank_ic'])
    return out.set_index('date')


def summarize_daily_ic(daily: pd.DataFrame) -> dict:
    """Statistics over the daily IC time series (NOT over raw observations)."""
    ic = daily['ic'].dropna()
    ric = daily['rank_ic'].dropna()
    return {
        'n_days': int(daily['n'].sum()),
        'n_dates': int(len(daily)),
        'ic_mean': float(ic.mean()) if len(ic) else np.nan,
        'ic_std': float(ic.std(ddof=1)) if len(ic) > 1 else np.nan,
        'icir': float(ic.mean() / ic.std(ddof=1)) if len(ic) > 1 else np.nan,
        'ic_positive_ratio': float((ic > 0).mean()) if len(ic) else np.nan,
        'rank_ic_mean': float(ric.mean()) if len(ric) else np.nan,
        'rank_ic_std': float(ric.std(ddof=1)) if len(ric) > 1 else np.nan,
        'rank_icir': float(ric.mean() / ric.std(ddof=1)) if len(ric) > 1 else np.nan,
        'coverage': float(daily['n'].sum()) if len(daily) else 0.0,
    }


def cluster_bootstrap_ci(daily: pd.DataFrame, n_boot: int = 200, seed: int = 2026,
                         alpha: float = 0.05) -> tuple:
    """Cluster bootstrap by date over daily IC series. Returns (lo, hi) for IC mean."""
    rng = np.random.default_rng(seed)
    ic = daily['ic'].dropna()
    dates = daily.index[daily['ic'].notna()]
    if len(dates) < 10:
        return (np.nan, np.nan)
    means = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(dates), size=len(dates))
        sample = ic.loc[dates[idx]]
        means.append(sample.mean())
    lo, hi = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return (float(lo), float(hi))


def quantile_table(factor: pd.Series, label: pd.Series, date: pd.Series,
                   q: int = 5, horizon_label: str = 'fwd_ret') -> pd.DataFrame:
    """Quantile buckets Q1..Q5 (Q1 = lowest factor) with forward stats."""
    d = pd.DataFrame({'date': date.values, 'f': factor.values, 'y': label.values})
    d = d.dropna(subset=['f', 'y'])
    d['q'] = pd.qcut(d['f'].rank(method='first'), q, labels=[f'Q{i}' for i in range(1, q + 1)])
    rows = []
    for qq, g in d.groupby('q', observed=True):
        rows.append({
            'quantile': qq,
            'n': len(g),
            'mean': float(g['y'].mean()),
            'median': float(g['y'].median()),
            'win_rate': float((g['y'] > 0).mean()),
            'std': float(g['y'].std(ddof=1)) if len(g) > 1 else np.nan,
        })
    out = pd.DataFrame(rows)
    if len(out) == q:
        q5, q1 = out.iloc[-1], out.iloc[0]
        out.attrs['q5_q1_mean'] = q5['mean'] - q1['mean']
        out.attrs['q5_q1_median'] = q5['median'] - q1['median']
        out.attrs['monotonic'] = bool(
            all(out.iloc[i]['median'] <= out.iloc[i + 1]['median']
                for i in range(q - 1)) or
            all(out.iloc[i]['median'] >= out.iloc[i + 1]['median']
                for i in range(q - 1)))
    return out


def yearly_ic(factor: pd.Series, label: pd.Series, date: pd.Series,
              year_col: pd.Series | None = None) -> pd.DataFrame:
    """Yearly IC/RankIC (per-year daily-IC mean)."""
    d = pd.DataFrame({'date': date.values, 'f': factor.values, 'y': label.values,
                      'year': (year_col if year_col is not None else pd.to_datetime(date)).values})
    if isinstance(d['year'].iloc[0], (pd.Timestamp, np.datetime64)):
        d['year'] = pd.to_datetime(d['year']).dt.year
    rows = []
    for yr, g in d.groupby('year'):
        daily = daily_cross_sectional_ic(g['f'], g['y'], g['date'])
        s = summarize_daily_ic(daily)
        rows.append({'year': yr, 'ic_mean': s['ic_mean'], 'rank_ic_mean': s['rank_ic_mean'],
                     'n_days': s['n_dates']})
    return pd.DataFrame(rows)


def turnover(factor: pd.Series, date: pd.Series, quantile_frac: float = 0.2) -> float:
    """Average cross-sectional rank-order turnover between consecutive dates
    within the top quantile_frac bucket."""
    d = pd.DataFrame({'date': date.values, 'f': factor.values}).dropna()
    d = d.sort_values('date')
    d['r'] = d.groupby('date')['f'].rank(pct=True)
    tos = []
    for (d1, g1), (d2, g2) in zip(d.groupby('date'), list(d.groupby('date'))[1:]):
        s1 = set(g1[g1['r'] >= 1 - quantile_frac].index)
        s2 = set(g2[g2['r'] >= 1 - quantile_frac].index)
        if s1 and s2:
            tos.append(1 - len(s1 & s2) / max(len(s1 | s2), 1))
    return float(np.mean(tos)) if tos else np.nan


def screen(factor: pd.Series, label: pd.Series, date: pd.Series, *,
           year_col: pd.Series | None = None, q: int = 5,
           n_boot: int = 200, seed: int = 2026,
           horizon_label: str = 'fwd_ret') -> dict:
    """Full screen of one factor against one label. Returns a results dict."""
    daily = daily_cross_sectional_ic(factor, label, date)
    s = summarize_daily_ic(daily)
    lo, hi = cluster_bootstrap_ci(daily, n_boot=n_boot, seed=seed)
    qt = quantile_table(factor, label, date, q=q, horizon_label=horizon_label)
    q5q1 = qt.attrs.get('q5_q1_mean', np.nan)
    q5q1_med = qt.attrs.get('q5_q1_median', np.nan)
    mon = qt.attrs.get('monotonic', False)
    to = turnover(factor, date)
    yic = yearly_ic(factor, label, date, year_col)
    result = {
        'horizon_label': horizon_label,
        **s,
        'q5_q1_mean': q5q1,
        'q5_q1_median': q5q1_med,
        'monotonic': mon,
        'turnover': to,
        'bootstrap_lo': lo,
        'bootstrap_hi': hi,
        'quantile_table': qt,
        'yearly': yic,
    }
    return result


def screen_row(result: dict, factor_id: str, horizon: str) -> pd.Series:
    """Flatten a screen result dict into a single CSV-friendly row."""
    y = result.get('yearly')
    yearly_direction = None
    if y is not None and len(y):
        signs = [1 if v > 0 else (-1 if v < 0 else 0) for v in y['ic_mean']]
        yearly_direction = '+'.join(str(s) for s in signs)
    return pd.Series({
        'factor_id': factor_id, 'horizon': horizon,
        'n_days': result.get('n_dates'), 'coverage': result.get('coverage'),
        'ic_mean': result.get('ic_mean'), 'rank_ic_mean': result.get('rank_ic_mean'),
        'icir': result.get('icir'), 'rank_icir': result.get('rank_icir'),
        'ic_positive_ratio': result.get('ic_positive_ratio'),
        'q5_q1_mean': result.get('q5_q1_mean'), 'q5_q1_median': result.get('q5_q1_median'),
        'monotonic': result.get('monotonic'), 'turnover': result.get('turnover'),
        'bootstrap_lo': result.get('bootstrap_lo'), 'bootstrap_hi': result.get('bootstrap_hi'),
        'yearly_direction': yearly_direction,
    })
