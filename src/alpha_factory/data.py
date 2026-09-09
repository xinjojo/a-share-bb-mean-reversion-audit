"""A-Share Alpha Factory — data loaders for Universe A (BB conditional) and B (full cross-section).

Universe A: SIGPATH canonical + PIT lookback aggregates from combined_daily (<= signal_date).
Universe B: combined_daily panel interface (Phase 0: schema + small smoke only).
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

PROJECT_ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
SIGPATH_WIDE = os.path.join(PROJECT_ROOT, 'audit_package', 'github_repo',
                            'results', 'evidence', 'sigpath', 'signal_path_20d_wide.parquet')
COMBINED_DAILY = os.path.join(PROJECT_ROOT, 'data', 'combined_daily.parquet')

# lookback aggregate spec: name -> (function on per-stock df, params)
WINDOW = {'ret_1': 1, 'ret_3': 3, 'ret_5': 5, 'ret_10': 10, 'ret_20': 20, 'ret_60': 60}
LOOKBACKS = [1, 3, 5, 10, 20, 60, 250]

_SIG_REQUIRED = [
    'signal_id', 'ts_code', 'stock_name', 'list_date', 'sector_pit',
    'signal_date', 'signal_day_open', 'signal_day_high', 'signal_day_low',
    'signal_day_close', 'signal_day_amount', 'signal_day_volume',
    'signal_day_adj_factor', 'bb_z', 'bb_mid', 'bb_lower', 'bb_upper',
    'BB_width', 'distance_to_lower_band', 'turnover_rank',
    'close_ret_D1', 'close_ret_D5', 'close_ret_D10', 'close_ret_D20',
    'MFE_D20', 'MAE_D20',
]


def _per_stock_features(grp: pd.DataFrame) -> pd.DataFrame:
    """Compute PIT lookback aggregates on a per-stock daily frame (sorted by date).
    grp columns: date, close_adj, close_raw, high, low, pre_close, amount, vol.
    Returns one row per date with aggregate fields."""
    g = grp.sort_values('date').copy()
    out = pd.DataFrame(index=g.index)
    out['date'] = g['date']
    c = g['close_adj']
    for n in LOOKBACKS:
        out[f'ret_{n}'] = c / c.shift(n) - 1.0
    r = c.pct_change()
    out['vol_10'] = r.rolling(10).std()
    out['vol_20'] = r.rolling(20).std()
    # ATR14 (% of close)
    pc = g['pre_close'].replace(0, np.nan)
    tr = pd.concat([(g['high'] - g['low']),
                    (g['high'] - pc).abs(),
                    (g['low'] - pc).abs()], axis=1).max(axis=1)
    out['atr14_pct'] = tr.rolling(14).mean() / g['close_raw']
    am5 = g['amount'].rolling(5).mean()
    am20 = g['amount'].rolling(20).mean()
    out['amount_ratio_5_20'] = am5 / am20
    out['drawdown_20'] = c / c.rolling(20).max() - 1.0
    out['drawdown_60'] = c / c.rolling(60).max() - 1.0
    out['distance_52w_high'] = c / c.rolling(250).max() - 1.0
    out['gap_pct'] = g['open'] / pc - 1.0
    out['daily_range_pct'] = (g['high'] - g['low']) / pc
    return out


def load_universe_a(sig_path: str = SIGPATH_WIDE, daily_path: str = COMBINED_DAILY,
                    max_signals: int | None = None, with_labels: bool = True) -> pd.DataFrame:
    """Build Universe A wide table: one row per BB signal with PIT fields + lookback aggregates."""
    sig = pd.read_parquet(sig_path, columns=_SIG_REQUIRED)
    if max_signals is not None:
        sig = sig.head(max_signals).copy()
    sig['signal_date'] = pd.to_datetime(sig['signal_date'])
    sig['list_date'] = pd.to_datetime(sig['list_date'])
    sig['listing_age_days'] = (sig['signal_date'] - sig['list_date']).dt.days

    daily = pd.read_parquet(daily_path,
                            columns=['date', 'ts_code', 'open', 'high', 'low',
                                     'close', 'vol', 'amount', 'pre_close', 'adj_factor'])
    daily = daily.rename(columns={'vol': 'volume'})
    daily['date'] = pd.to_datetime(daily['date'])
    daily['close_adj'] = daily['close'] * daily['adj_factor']
    daily['close_raw'] = daily['close']

    # keep only stocks present in signals
    codes = sig['ts_code'].unique()
    daily = daily[daily['ts_code'].isin(codes)]

    parts = []
    for code, g in daily.groupby('ts_code'):
        f = _per_stock_features(g)
        f['ts_code'] = code
        parts.append(f)
    feats = pd.concat(parts, ignore_index=True)
    # merge aggregates onto signals by (ts_code, signal_date)
    feats = feats.rename(columns={'date': 'signal_date'})
    sig = sig.merge(feats, on=['ts_code', 'signal_date'], how='left')

    # breadth fields (cross-sectional, PIT at signal_date)
    cnt = sig.groupby('signal_date').size().rename('daily_bb_signal_count')
    sig = sig.merge(cnt.reset_index(), on='signal_date', how='left')
    upr = sig.assign(_up=(sig['signal_day_close'] > sig['signal_day_open']).astype(int)) \
        .groupby('signal_date')['_up'].mean().rename('daily_bb_up_ratio')
    sig = sig.merge(upr.reset_index(), on='signal_date', how='left')

    if not with_labels:
        drop = ['close_ret_D1', 'close_ret_D5', 'close_ret_D10', 'close_ret_D20',
                'MFE_D20', 'MAE_D20']
        sig = sig.drop(columns=[c for c in drop if c in sig.columns])
    return sig.reset_index(drop=True)


class UniverseB:
    """Full A-share cross-section interface (Phase 0: schema only + small smoke)."""

    PANEL_COLUMNS = ['ts_code', 'date', 'open', 'high', 'low', 'close',
                     'volume', 'amount', 'adj_factor', 'close_adj']

    def __init__(self, daily_path: str = COMBINED_DAILY):
        self.daily_path = daily_path
        self.df = None

    def load_smoke(self, n_stocks: int = 50, n_days: int = 120,
                   end_date: str = '2024-12-31', seed: int = 7) -> pd.DataFrame:
        """Small panel for pipeline smoke only — NOT a formal research dataset."""
        rng = np.random.default_rng(seed)
        daily = pd.read_parquet(self.daily_path,
                                columns=['date', 'ts_code', 'open', 'high', 'low',
                                         'close', 'vol', 'amount', 'adj_factor'])
        daily = daily.rename(columns={'vol': 'volume'})
        daily['date'] = pd.to_datetime(daily['date'])
        end = pd.Timestamp(end_date)
        d = daily[daily['date'] <= end]
        codes = np.array(sorted(d['ts_code'].unique()))
        sel = rng.choice(codes, size=min(n_stocks, len(codes)), replace=False)
        d = d[d['ts_code'].isin(sel)]
        d = d[d['date'] >= end - pd.Timedelta(days=int(n_days * 2.2))]
        d = d.sort_values(['ts_code', 'date'])
        d['close_adj'] = d['close'] * d['adj_factor']
        self.df = d.reset_index(drop=True)
        return self.df
