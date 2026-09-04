#!/usr/bin/env python3
"""E0 STEP 9: Correlation / Cluster Diagnostic
用 PIT 代表 ETF（ADV60 规则）的日收益率计算指数间相关矩阵
输出:
  results/etf/e0_correlation_clusters.csv
  results/etf/e0_index_returns_matrix.parquet
  results/etf/e0_cluster_assignments.csv
"""
import os
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform

DATA_ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
WT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/etf_e0_wt'
OUT = os.path.join(WT, 'results', 'etf')
os.makedirs(OUT, exist_ok=True)

# 用 signal-capacity 已产出的 PIT 代表面板（若存在），否则用 master
rep_path = os.path.join(OUT, 'e0_signal_daily_detail.csv')
if os.path.exists(rep_path):
    daily = pd.read_csv(rep_path, parse_dates=['date'])
    # 重建代表面板：从 e0_pit_universe_selection_detail.csv
    det = pd.read_csv(os.path.join(OUT, 'e0_pit_universe_selection_detail.csv'), parse_dates=['date'])
    rep = det[det['rule'] == 'B2_ADV60'][['date', 'index_key', 'etf_code']].copy()
else:
    # 备用：直接构造（master 最新代表）
    master = pd.read_parquet(os.path.join(RAWDIR := '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/data/raw/etf', 'master_mapping_full.parquet'))
    elig = master[(master['eligible'] == True) & (master['status'] == 'L')]
    elig['index_key'] = elig.apply(lambda r: r['index_code'] if pd.notna(r['index_code']) else r['bench_idx_name'], axis=1)
    rep = elig[['index_key', 'etf_code']].copy()
    rep['date'] = pd.Timestamp('2026-09-03')

# 读每只代表 ETF 的 close_adj，构建价格面板
etfs = sorted(rep['etf_code'].unique())
px = {}
for tc in etfs:
    p = os.path.join('/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/data/raw/etf/fund_daily', tc.replace('.', '_') + '.parquet')
    if not os.path.exists(p):
        continue
    fd = pd.read_parquet(p)
    if len(fd) == 0:
        continue
    ap = os.path.join('/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/data/raw/etf/fund_adj', tc.replace('.', '_') + '.parquet')
    adj = 1.0
    if os.path.exists(ap):
        fa = pd.read_parquet(ap)
        if len(fa):
            fa = fa.sort_values('trade_date').drop_duplicates('trade_date').set_index('trade_date')['adj_factor']
            adj = fd['trade_date'].map(fa).fillna(1.0).to_numpy()
    fd = fd.assign(close_adj=pd.to_numeric(fd['close'], errors='coerce').to_numpy() * np.asarray(adj))
    s = fd.set_index('trade_date')['close_adj']
    px[tc] = s

pxdf = pd.DataFrame(px).sort_index()
print('price panel:', pxdf.shape)
ret = pxdf.pct_change()
# 对齐到共同历史（>= 若干年共同样本）
common = ret.dropna(how='all')
corr = ret.corr(min_periods=250)
print('corr matrix:', corr.shape)

# 统计 pair 数量
vals = []
n_idx = corr.shape[0]
pairs = []
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
clusters_out = pd.DataFrame({'metric': list(stats.keys()), 'value': list(stats.values())})
clusters_out.to_csv(os.path.join(OUT, 'e0_correlation_clusters.csv'), index=False)
print('\n=== Correlation stats ===')
print(clusters_out.to_string(index=False))
corr.to_parquet(os.path.join(OUT, 'e0_index_returns_matrix.parquet'))

# Hierarchical clustering: 1-corr 距离，ward
if n_idx >= 3:
    try:
        dmat = (1 - corr.fillna(0)) / 2.0
        dmat = dmat.clip(lower=0)
        dist = squareform(dmat, checks=False)
        Z = linkage(dist, method='ward')
        # 在 rho>0.8 附近切分：距离阈值 = 1-0.8=0.2 → 切割后 cluster 内相关通常 >0.8
        for t in [0.2, 0.3, 0.5]:
            lab = fcluster(Z, t=t, criterion='distance')
            n_cl = len(set(lab))
            print(f'  distance threshold {t}: {n_cl} clusters (独立风险簇估计)')
        lab = fcluster(Z, t=0.3, criterion='distance')
        assign = pd.DataFrame({'index_key': corr.index, 'cluster': lab})
        assign.to_csv(os.path.join(OUT, 'e0_cluster_assignments.csv'), index=False)
        clusters_out.loc[len(clusters_out)] = ['n_clusters_at_dist_0.3', len(set(lab))]
        clusters_out.to_csv(os.path.join(OUT, 'e0_correlation_clusters.csv'), index=False)
    except Exception as e:
        print('cluster failed:', e)
