#!/usr/bin/env python3
"""E0 STEP 8: History / Liquidity / Duplication Audit
输出:
  results/etf/e0_history_distribution.csv
  results/etf/e0_liquidity_distribution.csv
  results/etf/e0_duplicate_index_report.csv
"""
import os
import numpy as np
import pandas as pd

DATA_ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
WT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/etf_e0_wt'
OUT = os.path.join(WT, 'results', 'etf')
RAWDIR = os.path.join(DATA_ROOT, 'data', 'raw', 'etf')
os.makedirs(OUT, exist_ok=True)

master = pd.read_parquet(os.path.join(RAWDIR, 'master_mapping_full.parquet'))
# 有 daily 数据才算有效 ETF
master['has_daily'] = master['etf_code'].apply(
    lambda c: os.path.exists(os.path.join(RAWDIR, 'fund_daily', c.replace('.', '_') + '.parquet')))

# ============ History distribution ============
hist = master.copy()
hist['start'] = pd.to_datetime(hist['history_start'], errors='coerce')
hist['end'] = pd.to_datetime(hist['history_end'], errors='coerce')
hist['n_years'] = (hist['end'] - hist['start']).dt.days / 365.25
hist_valid = hist[hist['has_daily'] & hist['n_years'].notna()]

def bucket(y):
    if y >= 15: return '>=15y'
    if y >= 10: return '>=10y'
    if y >= 7: return '>=7y'
    if y >= 5: return '>=5y'
    if y >= 3: return '>=3y'
    if y >= 1: return '>=1y'
    return '<1y'

hist_valid['bucket'] = hist_valid['n_years'].apply(bucket)
rows = []
for b in ['>=15y', '>=10y', '>=7y', '>=5y', '>=3y', '>=1y', '<1y']:
    rows.append({'bucket': b, 'etf_count': int((hist_valid['n_years'] >= float(b.replace('y', '').replace('<', '0').replace('>=', '')) if b != '<1y' else (hist_valid['n_years'] < 1)).sum())})
# 简化为累积口径：>=15y, >=10y, ...
def cum_count(threshold):
    return int((hist_valid['n_years'] >= threshold).sum())
hist_out = pd.DataFrame({
    'metric': ['total_etfs_with_data', 'history>=15y', 'history>=10y', 'history>=7y',
               'history>=5y', 'history>=3y', 'history>=1y', 'history<1y',
               'median_years', 'mean_years', 'p25_years', 'p75_years'],
    'value': [len(hist_valid), cum_count(15), cum_count(10), cum_count(7),
              cum_count(5), cum_count(3), cum_count(1),
              int((hist_valid['n_years'] < 1).sum()),
              round(float(hist_valid['n_years'].median()), 2),
              round(float(hist_valid['n_years'].mean()), 2),
              round(float(hist_valid['n_years'].quantile(0.25)), 2),
              round(float(hist_valid['n_years'].quantile(0.75)), 2)]
})
hist_out.to_csv(os.path.join(OUT, 'e0_history_distribution.csv'), index=False)
print('=== History distribution ===')
print(hist_out.to_string(index=False))

# ============ Liquidity distribution ============
liq = master[master['has_daily']].copy()
for c in ['fund_size', 'adv20', 'adv60']:
    liq[c] = pd.to_numeric(liq[c], errors='coerce')

def layered(s, bounds, names):
    """bounds ascending: [lo0, lo1, ..., hi_max]; names correspond to [lo0,lo1), [lo1,lo2), ..., >=last"""
    out = {}
    for i, nm in enumerate(names):
        lo = bounds[i]
        if i < len(names) - 1:
            hi = bounds[i + 1]
            out[nm] = int(((s >= lo) & (s < hi)).sum())
        else:
            out[nm] = int((s >= lo).sum())
    return out

# AUM（元）分层: ascending bounds
aum_rows = layered(liq['fund_size'].dropna(), [0, 1e8, 2e8, 5e8, 1e9],
                   ['AUM<1亿', 'AUM1-2亿', 'AUM2-5亿', 'AUM5-10亿', 'AUM>=10亿'])
aum_rows['AUM_missing'] = int(liq['fund_size'].isna().sum())
# ADV60（元）分层
adv_rows = layered(liq['adv60'].dropna(), [0, 1e7, 2e7, 5e7, 1e8, 5e8],
                   ['ADV60<1000万', 'ADV60>=1000万', 'ADV60>=2000万', 'ADV60>=5000万', 'ADV60>=1亿', 'ADV60>=5亿'])
adv_rows['ADV60_missing'] = int(liq['adv60'].isna().sum())
liq_out = pd.DataFrame({
    'bucket': list(aum_rows.keys()) + list(adv_rows.keys()),
    'count': list(aum_rows.values()) + list(adv_rows.values())
})
liq_out.to_csv(os.path.join(OUT, 'e0_liquidity_distribution.csv'), index=False)
print('\n=== Liquidity distribution ===')
print(liq_out.to_string(index=False))

# ============ Duplicate index report ============
dup = master.copy()
dup['index_key'] = dup.apply(
    lambda r: (r['index_code'] if pd.notna(r['index_code']) and str(r['index_code']) != 'nan'
               else r['bench_idx_name']), axis=1)
dup['fund_size'] = pd.to_numeric(dup['fund_size'], errors='coerce')
dup['adv60'] = pd.to_numeric(dup['adv60'], errors='coerce')

def dup_group(g):
    live = g[g['status'] == 'L']
    n = len(g)
    n_live = len(live)
    # 当前规模最大（live 中）
    cur_largest = live.loc[live['fund_size'].idxmax(), 'etf_code'] if len(live) and live['fund_size'].notna().any() else np.nan
    cur_largest_size = live['fund_size'].max() if len(live) and live['fund_size'].notna().any() else np.nan
    # 历史规模最大（all，含退市）
    his_largest = g.loc[g['fund_size'].idxmax(), 'etf_code'] if g['fund_size'].notna().any() else np.nan
    # 最流动（adv60 最大）
    most_liq = g.loc[g['adv60'].idxmax(), 'etf_code'] if g['adv60'].notna().any() else np.nan
    return pd.Series({
        'n_tracking_etfs': n, 'n_live': n_live,
        'largest_current_etf': cur_largest,
        'largest_current_fund_size': cur_largest_size,
        'largest_historical_etf': his_largest,
        'most_liquid_etf': most_liq,
    })

dup_rep = dup.groupby('index_key').apply(dup_group, include_groups=False).reset_index()
dup_rep = dup_rep.drop_duplicates(subset=['index_key'])
dup_rep.to_csv(os.path.join(OUT, 'e0_duplicate_index_report.csv'), index=False)
print('\n=== Duplicate index report ===')
print('unique index_key:', len(dup_rep))
print(dup_rep['n_tracking_etfs'].describe())
print('多 ETF 跟踪同一指数数量:', (dup_rep['n_tracking_etfs'] > 1).sum())
print('单 ETF 指数:', (dup_rep['n_tracking_etfs'] == 1).sum())
