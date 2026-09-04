#!/usr/bin/env python3
"""E0.1-A (v2): Index-level correlation using DAILY PIT representative selection.

Uses etf_feat_long.parquet (saved by e0_signal_capacity.py) which has daily
per-ETF features including adv60. Does daily B2 selection (highest ADV60 at t-1,
listed >= 60 days), then builds one return series per index by concatenating
the selected representative ETF's daily returns.

This fixes the original bug where 534 ETF-level series were treated as 534 indexes.
"""
import os
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform

DATA_ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
WT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/etf_e0_wt'
OUT = os.path.join(WT, 'results', 'etf')
RAWDIR = os.path.join(DATA_ROOT, 'data', 'raw', 'etf')

print('loading etf_feat_long.parquet...')
feat = pd.read_parquet(os.path.join(RAWDIR, 'etf_feat_long.parquet'))
print(f'feat rows: {len(feat)}, columns: {list(feat.columns)}')

feat['date'] = pd.to_datetime(feat['date'])
feat = feat[feat['date'] <= '2026-09-03'].copy()

# PIT listed filter
feat['listed'] = (feat['list_date'] <= feat['date']) & (feat['delist'].isna() | (feat['delist'] > feat['date']))
avail = feat[feat['listed']].copy()
avail['n_days'] = avail.groupby('etf')['date'].cumcount() + 1
avail = avail[avail['n_days'] >= 60].copy()
print(f'listed & >=60d rows: {len(avail)}')

# Daily B2: per index_key-date, highest adv60
avail = avail.sort_values('adv60', ascending=False)
rep = avail.drop_duplicates(subset=['index_key', 'date']).copy()
print(f'daily PIT reps (index_key x date): {len(rep)}')
print(f'unique indexes: {rep["index_key"].nunique()}, unique ETFs: {rep["etf"].nunique()}')

# Save daily representative selection for E1 use
rep[['date', 'index_key', 'etf', 'close_adj', 'adv60', 'amount']].to_csv(
    os.path.join(OUT, 'e01_daily_pit_representatives.csv'), index=False)
print('saved e01_daily_pit_representatives.csv')

# Build index-level price panel: for each (date, index_key), use rep ETF's close_adj
price_panel = rep.pivot(index='date', columns='index_key', values='close_adj')
price_panel = price_panel.sort_index()
print(f'price panel shape: {price_panel.shape}')
print(f'date range: {price_panel.index.min()} -> {price_panel.index.max()}')

# Returns
ret_df = price_panel.pct_change()
# Drop columns with too few observations
min_obs = 250
valid_cols = ret_df.columns[ret_df.notna().sum() >= min_obs]
print(f'indexes with >= {min_obs} return obs: {len(valid_cols)} / {ret_df.shape[1]}')
ret_valid = ret_df[valid_cols]

# Correlation
corr = ret_valid.corr(min_periods=min_obs)
print(f'correlation matrix: {corr.shape}')

# Pair stats
pairs = []
n_idx = corr.shape[0]
for i in range(n_idx):
    for j in range(i + 1, n_idx):
        r = corr.iloc[i, j]
        if pd.notna(r):
            pairs.append(r)
pairs = np.array(pairs)
print(f'computed pairs: {len(pairs)}')

stats = {
    'n_indexes_with_returns': n_idx,
    'n_indexes_total_in_pit': rep['index_key'].nunique(),
    'n_pairs_computed': len(pairs),
    'pairs_abs_gt_0.95': int((np.abs(pairs) > 0.95).sum()),
    'pairs_gt_0.90': int((pairs > 0.90).sum()),
    'pairs_gt_0.80': int((pairs > 0.80).sum()),
    'pairs_gt_0.50': int((pairs > 0.50).sum()),
    'mean_corr': float(pairs.mean()),
    'median_corr': float(np.median(pairs)),
    'p90_corr': float(np.quantile(pairs, 0.90)),
}

# Clustering
if n_idx >= 3:
    dmat = (1 - corr.fillna(0)) / 2.0
    dmat = dmat.clip(lower=0)
    dist = squareform(dmat, checks=False)
    Z = linkage(dist, method='ward')
    for t in [0.2, 0.3, 0.5]:
        lab = fcluster(Z, t=t, criterion='distance')
        n_cl = len(set(lab))
        print(f'  distance threshold {t}: {n_cl} clusters')
        stats[f'n_clusters_at_dist_{t}'] = n_cl
    lab = fcluster(Z, t=0.3, criterion='distance')
    assign = pd.DataFrame({'index_key': corr.index, 'cluster': lab})
    assign.to_csv(os.path.join(OUT, 'e0_cluster_assignments.csv'), index=False)

clusters_out = pd.DataFrame({'metric': list(stats.keys()), 'value': list(stats.values())})
clusters_out.to_csv(os.path.join(OUT, 'e0_correlation_clusters.csv'), index=False)
ret_valid.to_parquet(os.path.join(OUT, 'e0_index_returns_matrix.parquet'))

print('\n=== Index-Level Correlation (FIXED, daily PIT) ===')
print(clusters_out.to_string(index=False))
print('\nDONE E0.1-A v2')
