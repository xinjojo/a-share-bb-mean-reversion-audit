#!/usr/bin/env python3
"""E0.1-A: Reconcile universe counts + fix correlation to INDEX-LEVEL.

Root cause of 534 > 377:
  Original correlation used ETF-level series (534 unique ETFs from B2 PIT selection).
  115/362 indexes have multiple representative ETFs over time (up to 7), so the same
  index appears as multiple series. This inflates pair count and distorts cluster count.

Fix: Build INDEX-LEVEL return series by concatenating PIT representative ETF returns.
  For each date t and index_key, use the daily return of the B2-selected representative ETF.
  This gives one return series per index (~362), making correlation/cluster meaningful
  for "effective independent risk assets".

Outputs:
  results/etf/e01_universe_reconciliation.csv
  results/etf/e0_correlation_clusters.csv (overwritten, index-level)
  results/etf/e0_index_returns_matrix.parquet (overwritten, index-level)
  results/etf/e0_cluster_assignments.csv (overwritten, index-level)
  results/etf/e01_etf_level_correlation_stats.csv (supplementary, for comparison)
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

# ============ A. Universe count reconciliation ============
master = pd.read_parquet(os.path.join(RAWDIR, 'master_mapping_full.parquet'))
master['index_key'] = master.apply(
    lambda r: (r['index_code'] if pd.notna(r['index_code']) and str(r['index_code']) != 'nan'
               else r['bench_idx_name']), axis=1)

det = pd.read_csv(os.path.join(OUT, 'e0_pit_universe_selection_detail.csv'))
b2 = det[det['rule'] == 'B2_ADV60'].copy()

recon = pd.DataFrame([
    {'metric': 'candidate_etfs_total', 'value': len(master),
     'definition': 'fund_basic filtered to stock-type exchange-traded ETFs (1400)'},
    {'metric': 'eligible_with_daily', 'value': int(master['eligible'].sum() & master['has_daily'].sum()),
     'definition': 'eligible=True AND has_daily=True (1137)'},
    {'metric': 'unique_index_keys_all_candidates', 'value': master['index_key'].nunique(),
     'definition': 'distinct index_key across all 1400 candidates (377)'},
    {'metric': 'universe_A_current_reps', 'value': 328,
     'definition': 'current largest-AUM ETF per index (live only)'},
    {'metric': 'universe_B_pit_indexes', 'value': b2['index_key'].nunique(),
     'definition': 'distinct index_keys in B2 PIT selection (362)'},
    {'metric': 'universe_B_pit_unique_etfs', 'value': b2['etf_code'].nunique(),
     'definition': 'distinct ETFs ever selected as B2 representative (534) — NOT independent indexes'},
    {'metric': 'indexes_with_multi_rep_over_time', 'value': int((b2.groupby('index_key')['etf_code'].nunique() > 1).sum()),
     'definition': 'indexes whose B2 representative changed at least once over history (115)'},
    {'metric': 'max_rep_etfs_per_index', 'value': int(b2.groupby('index_key')['etf_code'].nunique().max()),
     'definition': 'max number of distinct representative ETFs for a single index (7)'},
    {'metric': 'correlation_series_original_etf_level', 'value': 534,
     'definition': 'BUG: original correlation used ETF-level series, inflating count'},
    {'metric': 'correlation_series_fixed_index_level', 'value': b2['index_key'].nunique(),
     'definition': 'FIX: index-level concatenated PIT representative returns (one series per index)'},
])
recon.to_csv(os.path.join(OUT, 'e01_universe_reconciliation.csv'), index=False)
print('=== Universe Count Reconciliation ===')
print(recon[['metric', 'value']].to_string(index=False))

# ============ Build INDEX-LEVEL return matrix ============
print('\n=== Building index-level return matrix ===')

# Get all ETFs needed
all_etfs = b2['etf_code'].unique()
print(f'loading {len(all_etfs)} ETF daily series...')

# Load each ETF's close_adj
etf_returns = {}
for tc in all_etfs:
    p = os.path.join(RAWDIR, 'fund_daily', tc.replace('.', '_') + '.parquet')
    if not os.path.exists(p):
        continue
    fd = pd.read_parquet(p)
    if len(fd) == 0:
        continue
    fd['trade_date'] = pd.to_datetime(fd['trade_date'])
    fd = fd.sort_values('trade_date')
    close = pd.to_numeric(fd['close'], errors='coerce')
    # adj factor
    adj = pd.Series(1.0, index=fd.index)
    ap = os.path.join(RAWDIR, 'fund_adj', tc.replace('.', '_') + '.parquet')
    if os.path.exists(ap):
        fa = pd.read_parquet(ap)
        if len(fa):
            fa['trade_date'] = pd.to_datetime(fa['trade_date'])
            fa = fa.sort_values('trade_date').drop_duplicates('trade_date').set_index('trade_date')['adj_factor']
            adj = fd['trade_date'].map(fa).fillna(1.0).to_numpy()
    close_adj = close.to_numpy() * np.asarray(adj)
    s = pd.Series(close_adj, index=fd['trade_date'], name=tc)
    ret = s.pct_change()
    etf_returns[tc] = ret

print(f'loaded {len(etf_returns)} ETF return series')

# Build index-level: for each (date, index_key), use selected ETF's return
b2['date'] = pd.to_datetime(b2['date'])
idx_rets = {}
for idx_key, grp in b2.groupby('index_key'):
    # for each date, get the selected ETF
    series_parts = []
    for _, row in grp.iterrows():
        d = row['date']
        tc = row['etf_code']
        if tc in etf_returns and d in etf_returns[tc].index:
            series_parts.append((d, etf_returns[tc].loc[d]))
    if series_parts:
        s = pd.Series(dict(series_parts)).sort_index()
        # remove duplicates (keep first)
        s = s[~s.index.duplicated(keep='first')]
        idx_rets[idx_key] = s

print(f'index-level return series: {len(idx_rets)}')

# Build DataFrame
ret_df = pd.DataFrame(idx_rets).sort_index()
print(f'return matrix shape: {ret_df.shape}')
ret_df.to_parquet(os.path.join(OUT, 'e0_index_returns_matrix.parquet'))

# ============ Index-level correlation ============
corr = ret_df.corr(min_periods=250)
print(f'correlation matrix: {corr.shape}')

# pair stats
pairs = []
n_idx = corr.shape[0]
for i in range(n_idx):
    for j in range(i + 1, n_idx):
        r = corr.iloc[i, j]
        if pd.notna(r):
            pairs.append(r)
pairs = np.array(pairs)

stats = {
    'n_indexes_with_returns': n_idx,
    'n_pairs_computed': len(pairs),
    'pairs_abs_gt_0.95': int((np.abs(pairs) > 0.95).sum()),
    'pairs_gt_0.90': int((pairs > 0.90).sum()),
    'pairs_gt_0.80': int((pairs > 0.80).sum()),
    'pairs_gt_0.50': int((pairs > 0.50).sum()),
    'mean_corr': float(pairs.mean()),
    'median_corr': float(np.median(pairs)),
    'p90_corr': float(np.quantile(pairs, 0.90)),
}

# clustering
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
print('\n=== Index-Level Correlation Stats (FIXED) ===')
print(clusters_out.to_string(index=False))

# ============ ETF-level correlation stats (supplementary) ============
# Also compute ETF-level for comparison, but clearly label as supplementary
etf_ret_df = pd.DataFrame(etf_returns).sort_index()
etf_corr = etf_ret_df.corr(min_periods=250)
etf_pairs = []
for i in range(etf_corr.shape[0]):
    for j in range(i + 1, etf_corr.shape[0]):
        r = etf_corr.iloc[i, j]
        if pd.notna(r):
            etf_pairs.append(r)
etf_pairs = np.array(etf_pairs)

etf_stats = pd.DataFrame([
    {'level': 'ETF-level (original, supplementary)', 'n_series': etf_corr.shape[0],
     'n_pairs': len(etf_pairs), 'pairs_gt_0.80': int((etf_pairs > 0.80).sum()),
     'mean_corr': float(etf_pairs.mean()), 'median_corr': float(np.median(etf_pairs))},
    {'level': 'Index-level (fixed, primary)', 'n_series': n_idx,
     'n_pairs': len(pairs), 'pairs_gt_0.80': int((pairs > 0.80).sum()),
     'mean_corr': float(pairs.mean()), 'median_corr': float(np.median(pairs))},
])
etf_stats.to_csv(os.path.join(OUT, 'e01_etf_level_correlation_stats.csv'), index=False)
print('\n=== ETF-level vs Index-level comparison ===')
print(etf_stats.to_string(index=False))

print('\nDONE E0.1-A')
