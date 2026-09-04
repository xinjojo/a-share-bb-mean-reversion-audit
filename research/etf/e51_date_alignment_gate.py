#!/usr/bin/env python3
"""E5.1 Stock Date Alignment Gate + Core E5 Reproduction.

Fixes E5 date assignment:
- E5 used row-in-year index -> first N trading days (wrong for IPO stocks)
- E5.1 uses full-data stocks only + ETF trading calendar (authoritative)
- Partial-year stocks excluded from primary analysis

Also audits:
- pre_close continuity
- known price anchors
- PIT universe / breadth
- forward return semantics
- random Top-N methodology
"""
import os, sys
import numpy as np
import pandas as pd

STOCK_ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo'
ETF_WT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/etf_e0_wt'
OUT = os.path.join(ETF_WT, 'results', 'etf')
RAWDIR = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/data/raw/etf'

BB_WINDOW, BB_STD = 20, 2.0
COMMON_START = '2020-01-01'
COMMON_END = '2024-12-31'
TOP_N = 10
RANDOM_SEED = 42
RANDOM_REPS = 1000

print('='*60)
print('E5.1 STOCK DATE ALIGNMENT GATE')
print('='*60)

# ===== 1. AUTHORITATIVE TRADING CALENDAR FROM ETF DATA =====
print('\n[1] Building authoritative trading calendar from ETF data...')
feat_etf = pd.read_parquet(os.path.join(RAWDIR, 'etf_feat_long.parquet'))
feat_etf['date'] = pd.to_datetime(feat_etf['date'])
all_trading_dates = sorted(feat_etf['date'].unique())
cal_by_year = {}
for y in range(2020, 2025):
    dates = [d for d in all_trading_dates if d.year == y]
    cal_by_year[y] = dates
    print(f'  {y}: {len(dates)} trading days')

# ===== 2. LOAD STOCK DATA AND IDENTIFY FULL-DATA STOCKS =====
print('\n[2] Loading stock kline data, identifying full-data stocks...')
stock_frames = []
for y in range(2020, 2025):
    df = pd.read_parquet(os.path.join(STOCK_ROOT, 'data', 'kline', f'{y}.parquet'))
    df['year'] = y
    stock_frames.append(df)
stock_raw = pd.concat(stock_frames, ignore_index=True)

# Count rows per stock per year
row_counts = stock_raw.groupby(['ts_code', 'year']).size().unstack(fill_value=0)
expected = {2020: 243, 2021: 243, 2022: 242, 2023: 242, 2024: 242}
full_data_mask = pd.Series(True, index=row_counts.index)
for y, exp in expected.items():
    full_data_mask &= (row_counts[y] == exp)
full_stocks = full_data_mask[full_data_mask].index.tolist()
partial_stocks = full_data_mask[~full_data_mask].index.tolist()
print(f'  Full-data stocks: {len(full_stocks)} / {len(row_counts)}')
print(f'  Partial-data stocks (excluded): {len(partial_stocks)}')

# Audit partial stocks
partial_audit = []
for tc in partial_stocks[:50]:
    rc = row_counts.loc[tc]
    partial_audit.append({'ts_code': tc, **{f'y{y}': int(rc[y]) for y in range(2020,2025)}})
pd.DataFrame(partial_audit).to_csv(os.path.join(OUT, 'e51_partial_stocks_audit.csv'), index=False)

# ===== 3. ASSIGN DATES TO FULL-DATA STOCKS =====
print('\n[3] Assigning dates to full-data stocks...')
stock_full = stock_raw[stock_raw['ts_code'].isin(full_stocks)].copy()
stock_full = stock_full.sort_values(['ts_code', 'year']).reset_index(drop=True)
stock_full['row_in_year'] = stock_full.groupby(['ts_code', 'year']).cumcount()

def assign_date_full(row):
    y = row['year']
    idx = int(row['row_in_year'])
    dates = cal_by_year.get(y, [])
    if idx < len(dates):
        return dates[idx]
    return pd.NaT

stock_full['date'] = stock_full.apply(assign_date_full, axis=1)
stock_full = stock_full.dropna(subset=['date']).copy()
stock_full['close_adj'] = stock_full['close'] * stock_full['adj_factor']
stock_full = stock_full.sort_values(['ts_code', 'date']).reset_index(drop=True)
print(f'  Full-data panel rows: {len(stock_full)}')
print(f'  Unique stocks: {stock_full["ts_code"].nunique()}')
print(f'  Date range: {stock_full["date"].min()} to {stock_full["date"].max()}')

# ===== 4. DATE ALIGNMENT AUDIT =====
print('\n[4] Date alignment audit...')
# 4a. pre_close continuity
pre_close_mm = 0
pre_close_total = 0
for tc, g in stock_full.groupby('ts_code'):
    g = g.sort_values('date').reset_index(drop=True)
    if len(g) > 1:
        mm = (g['pre_close'].iloc[1:].values != g['close'].iloc[:-1].values).sum()
        pre_close_mm += mm
        pre_close_total += len(g) - 1
print(f'  pre_close mismatch: {pre_close_mm} / {pre_close_total} ({pre_close_mm/pre_close_total*100:.3f}%)')

# 4b. Known price anchors
anchors = [
    ('000001.SZ', '2020-01-02', 16.87),  # Ping An Bank first trading day 2020
    ('000001.SZ', '2020-12-31', None),     # last day 2020 (just check exists)
    ('600000.SH', '2020-01-02', None),     # SPD Bank
    ('300750.SZ', '2020-01-02', None),     # CATL
]
anchor_results = []
for tc, dt_str, expected_close in anchors:
    dt = pd.Timestamp(dt_str)
    row = stock_full[(stock_full['ts_code'] == tc) & (stock_full['date'] == dt)]
    if len(row) > 0:
        actual_close = row.iloc[0]['close']
        match = 'OK' if expected_close is None or abs(actual_close - expected_close) < 0.01 else f'MISMATCH (expected {expected_close})'
        anchor_results.append({'ts_code': tc, 'date': dt_str, 'actual_close': actual_close, 'status': match})
    else:
        anchor_results.append({'ts_code': tc, 'date': dt_str, 'actual_close': None, 'status': 'NOT FOUND'})
anchor_df = pd.DataFrame(anchor_results)
print('  Price anchors:')
for _, r in anchor_df.iterrows():
    print(f'    {r["ts_code"]} {r["date"]}: close={r["actual_close"]} [{r["status"]}]')
anchor_df.to_csv(os.path.join(OUT, 'e51_price_anchors.csv'), index=False)

# 4c. Rows per day distribution
daily_counts = stock_full.groupby('date').size()
print(f'  Stocks per day: mean={daily_counts.mean():.0f}, median={daily_counts.median():.0f}, min={daily_counts.min()}, max={daily_counts.max()}')

# ===== 5. COMPUTE BB FEATURES ON CORRECTED PANEL =====
print('\n[5] Computing BB features on corrected panel...')
stock_full['ma20'] = stock_full.groupby('ts_code')['close_adj'].transform(
    lambda x: x.rolling(BB_WINDOW, min_periods=BB_WINDOW).mean())
stock_full['sd20'] = stock_full.groupby('ts_code')['close_adj'].transform(
    lambda x: x.rolling(BB_WINDOW, min_periods=BB_WINDOW).std())
stock_full['bb_lower'] = stock_full['ma20'] - BB_STD * stock_full['sd20']
stock_full['bb_upper'] = stock_full['ma20'] + BB_STD * stock_full['sd20']
stock_full['bb_z'] = (stock_full['close_adj'] - stock_full['ma20']) / stock_full['sd20']
stock_full.loc[stock_full['sd20'] == 0, 'bb_z'] = np.nan
stock_full['signal'] = (stock_full['close_adj'] < stock_full['bb_lower']) & stock_full['bb_lower'].notna()
stock_full['n_days'] = stock_full.groupby('ts_code')['date'].cumcount() + 1
stock_eligible = stock_full[stock_full['n_days'] >= BB_WINDOW].copy()

# Forward returns (market trading day horizon, consistent with ETF)
for h in [1, 3, 5, 10, 20]:
    stock_eligible[f'fwd_{h}d'] = stock_eligible.groupby('ts_code')['close_adj'].shift(-h) / stock_eligible['close_adj'] - 1

stock_signals = stock_eligible[stock_eligible['signal']].copy()
print(f'  Eligible rows: {len(stock_eligible)}, signal rows: {len(stock_signals)}')

# ===== 6. ETF REFERENCE (same as E5) =====
print('\n[6] Building ETF reference panel...')
feat_etf_cw = feat_etf[(feat_etf['date'] >= COMMON_START) & (feat_etf['date'] <= COMMON_END)].copy()
feat_etf_cw = feat_etf_cw.sort_values(['etf', 'date'])
feat_etf_cw['bb_mid'] = feat_etf_cw.groupby('etf')['close_adj'].transform(
    lambda x: x.rolling(BB_WINDOW, min_periods=BB_WINDOW).mean())
feat_etf_cw['bb_std'] = (feat_etf_cw['bb_mid'] - feat_etf_cw['bb_lower']) / BB_STD
feat_etf_cw['bb_z'] = (feat_etf_cw['close_adj'] - feat_etf_cw['bb_mid']) / feat_etf_cw['bb_std']
feat_etf_cw.loc[feat_etf_cw['bb_std'] == 0, 'bb_z'] = np.nan
feat_etf_cw['listed'] = (feat_etf_cw['list_date'] <= feat_etf_cw['date']) & (feat_etf_cw['delist'].isna() | (feat_etf_cw['delist'] > feat_etf_cw['date']))
feat_etf_cw['n_days'] = feat_etf_cw.groupby('etf')['date'].cumcount() + 1
etf_eligible = feat_etf_cw[(feat_etf_cw['listed']) & (feat_etf_cw['n_days'] >= 60) & (feat_etf_cw['adv60'] >= 20000)].copy()
etf_eligible['signal'] = (etf_eligible['close_adj'] < etf_eligible['bb_lower']) & etf_eligible['bb_lower'].notna()
for h in [1, 3, 5, 10, 20]:
    etf_eligible[f'fwd_{h}d'] = etf_eligible.groupby('etf')['close_adj'].shift(-h) / etf_eligible['close_adj'] - 1
etf_signals = etf_eligible[etf_eligible['signal']].copy()
print(f'  ETF eligible: {len(etf_eligible)}, signals: {len(etf_signals)}')

# ===== 7. CORE E5 METRICS REPRODUCTION (CORRECTED) =====
print('\n[7] Reproducing core E5 metrics on corrected panel...')

def bbz_dispersion(df, date_col, val_col, label):
    rows = []
    for d, g in df.groupby(date_col):
        vals = g[val_col].dropna()
        if len(vals) >= 5:
            rows.append({'date': d, 'std': vals.std(), 'iqr': vals.quantile(0.75)-vals.quantile(0.25),
                         'mad': (vals-vals.median()).abs().median(), 'count': len(vals)})
    return pd.DataFrame(rows)

# 7a. BB_Z signal candidate dispersion
stock_sig_disp = bbz_dispersion(stock_signals, 'date', 'bb_z', 'stock')
etf_sig_disp = bbz_dispersion(etf_signals, 'date', 'bb_z', 'etf')

# 7b. 20d forward return dispersion
def fwd_dispersion(df, date_col, col, label):
    rows = []
    for d, g in df.groupby(date_col):
        vals = g[col].dropna()
        if len(vals) >= 5:
            rows.append({'date': d, 'std': vals.std(), 'count': len(vals)})
    return pd.DataFrame(rows)

stock_fwd20_disp = fwd_dispersion(stock_signals, 'date', 'fwd_20d', 'stock')
etf_fwd20_disp = fwd_dispersion(etf_signals, 'date', 'fwd_20d', 'etf')

# 7c. Signal 20d expectancy
stock_sig_20d = stock_signals['fwd_20d'].dropna()
etf_sig_20d = etf_signals['fwd_20d'].dropna()

# 7d. Signal breadth (PIT: signal_count / eligible_count each day)
stock_daily_elig = stock_eligible.groupby('date').size()
stock_daily_sig = stock_signals.groupby('date').size()
stock_breadth = (stock_daily_sig / stock_daily_elig).dropna()
etf_daily_elig = etf_eligible.groupby('date').size()
etf_daily_sig = etf_signals.groupby('date').size()
etf_breadth = (etf_daily_sig / etf_daily_elig).dropna()

# 7e. BB_Z IC (daily mean, 20d)
def compute_daily_ic(df, date_col, rank_col, ret_col):
    ics = []
    for d, g in df.groupby(date_col):
        valid = g[[rank_col, ret_col]].dropna()
        if len(valid) >= 5:
            ic = valid[[rank_col, ret_col]].corr(method='spearman').iloc[0,1]
            if not np.isnan(ic):
                ics.append(ic)
    return np.array(ics)

stock_signals['bbz_rank'] = stock_signals.groupby('date')['bb_z'].rank(ascending=True)
etf_signals['bbz_rank'] = etf_signals.groupby('date')['bb_z'].rank(ascending=True)
stock_bbz_ic = compute_daily_ic(stock_signals, 'date', 'bbz_rank', 'fwd_20d')
etf_bbz_ic = compute_daily_ic(etf_signals, 'date', 'bbz_rank', 'fwd_20d')

# 7f. Amount Top-N vs random (20d, per-day percentile then aggregate)
def amount_vs_random_corrected(df, date_col, amount_col, ret_col, n=TOP_N, reps=RANDOM_REPS, seed=RANDOM_SEED):
    rng = np.random.RandomState(seed)
    daily_percentiles = []
    pooled_actual = []
    pooled_random_expected = []
    for d, g in df.groupby(date_col):
        valid = g[[amount_col, ret_col]].dropna()
        if len(valid) < n:
            continue
        actual = valid.nlargest(n, amount_col)[ret_col].mean()
        pooled_actual.append(actual)
        random_means = []
        for _ in range(reps):
            sample = valid.sample(n=n, random_state=rng)
            random_means.append(sample[ret_col].mean())
        pooled_random_expected.append(np.mean(random_means))
        pctile = (np.array(random_means) < actual).mean() * 100
        daily_percentiles.append(pctile)
    return {
        'mean_daily_percentile': np.mean(daily_percentiles),
        'median_daily_percentile': np.median(daily_percentiles),
        'pct_days_above_random_median': np.mean(np.array(daily_percentiles) >= 50) * 100,
        'pooled_actual_mean': np.mean(pooled_actual),
        'pooled_random_expected_mean': np.mean(pooled_random_expected),
        'diff': np.mean(pooled_actual) - np.mean(pooled_random_expected),
        'n_days': len(daily_percentiles),
    }

stock_rand = amount_vs_random_corrected(stock_signals, 'date', 'amount', 'fwd_20d')
etf_rand = amount_vs_random_corrected(etf_signals, 'date', 'amount', 'fwd_20d')

# ===== 8. OLD vs NEW COMPARISON =====
print('\n[8] OLD (E5) vs NEW (E5.1 corrected) comparison...')
old_vals = {
    'stock_bbz_signal_std': 0.2631,
    'etf_bbz_signal_std': 0.1713,
    'stock_fwd20_std': 0.1226,
    'etf_fwd20_std': 0.0451,
    'stock_signal_20d_mean': 2.503,
    'stock_signal_20d_median': 1.033,
    'etf_signal_20d_mean': 1.618,
    'etf_signal_20d_median': 0.280,
    'stock_median_breadth_pct': 1.71,
    'etf_median_breadth_pct': 6.05,
    'stock_amount_actual_20d_pct': -0.105,
    'stock_random_20d_pct': 0.127,
    'etf_amount_actual_20d_pct': 0.588,
    'etf_random_20d_pct': 1.168,
    'stock_bbz_daily_ic_20d': -0.0015,
    'etf_bbz_daily_ic_20d': -0.0157,
}

new_vals = {
    'stock_bbz_signal_std': round(stock_sig_disp['std'].mean(), 4),
    'etf_bbz_signal_std': round(etf_sig_disp['std'].mean(), 4),
    'stock_fwd20_std': round(stock_fwd20_disp['std'].mean(), 4),
    'etf_fwd20_std': round(etf_fwd20_disp['std'].mean(), 4),
    'stock_signal_20d_mean': round(stock_sig_20d.mean() * 100, 3),
    'stock_signal_20d_median': round(stock_sig_20d.median() * 100, 3),
    'etf_signal_20d_mean': round(etf_sig_20d.mean() * 100, 3),
    'etf_signal_20d_median': round(etf_sig_20d.median() * 100, 3),
    'stock_median_breadth_pct': round(stock_breadth.median() * 100, 2),
    'etf_median_breadth_pct': round(etf_breadth.median() * 100, 2),
    'stock_amount_actual_20d_pct': round(stock_rand['pooled_actual_mean'] * 100, 3),
    'stock_random_20d_pct': round(stock_rand['pooled_random_expected_mean'] * 100, 3),
    'etf_amount_actual_20d_pct': round(etf_rand['pooled_actual_mean'] * 100, 3),
    'etf_random_20d_pct': round(etf_rand['pooled_random_expected_mean'] * 100, 3),
    'stock_bbz_daily_ic_20d': round(stock_bbz_ic.mean(), 4),
    'etf_bbz_daily_ic_20d': round(etf_bbz_ic.mean(), 4),
}

repro_rows = []
for k in old_vals:
    old = old_vals[k]
    new = new_vals.get(k, np.nan)
    diff = new - old if not np.isnan(new) else np.nan
    repro_rows.append({'metric': k, 'old_e5': old, 'new_e51': new, 'diff': diff})
repro_df = pd.DataFrame(repro_rows)
print(repro_df.to_string(index=False))
repro_df.to_csv(os.path.join(OUT, 'e51_core_e5_reproduction.csv'), index=False)

# Random Top-N detailed audit
rand_audit = pd.DataFrame([
    {'asset': 'stock', **stock_rand},
    {'asset': 'etf', **etf_rand},
])
print('\n=== Random Top-N corrected audit ===')
print(rand_audit.to_string(index=False))
rand_audit.to_csv(os.path.join(OUT, 'e51_random_topn_audit.csv'), index=False)

# ===== 9. VERDICT =====
print('\n' + '='*60)
print('E5.1 VERDICT ASSESSMENT')
print('='*60)
# Check if core conclusions are unchanged
checks = []
checks.append(('Stock BB_Z dispersion > ETF', new_vals['stock_bbz_signal_std'] > new_vals['etf_bbz_signal_std']))
checks.append(('Stock fwd20 dispersion > ETF', new_vals['stock_fwd20_std'] > new_vals['etf_fwd20_std']))
checks.append(('Stock signal 20d mean > ETF', new_vals['stock_signal_20d_mean'] > new_vals['etf_signal_20d_mean']))
checks.append(('Stock signal 20d median > ETF', new_vals['stock_signal_20d_median'] > new_vals['etf_signal_20d_median']))
checks.append(('ETF median breadth > stock', new_vals['etf_median_breadth_pct'] > new_vals['stock_median_breadth_pct']))
checks.append(('Stock amount Top-N < random', new_vals['stock_amount_actual_20d_pct'] < new_vals['stock_random_20d_pct']))
checks.append(('ETF amount Top-N < random', new_vals['etf_amount_actual_20d_pct'] < new_vals['etf_random_20d_pct']))

all_pass = all(v for _, v in checks)
for name, result in checks:
    print(f'  {"PASS" if result else "FAIL"}: {name}')

print(f'\n  All core conclusions unchanged: {all_pass}')
print(f'  pre_close mismatch: {pre_close_mm/pre_close_total*100:.3f}%')
print(f'  Full-data stocks: {len(full_stocks)} / {len(row_counts)} ({len(full_stocks)/len(row_counts)*100:.1f}%)')
print(f'  Price anchor 000001.SZ 2020-01-02: {anchor_df.iloc[0]["status"]}')

if all_pass and pre_close_mm/pre_close_total < 0.01:
    verdict = 'PASS WITH CORRECTION'
    print(f'\n  E5.1 VERDICT: {verdict}')
    print('  Date mapping corrected (full-data stocks only, ETF calendar).')
    print('  All core E5 conclusions unchanged. Safe to proceed to S1.')
else:
    verdict = 'MATERIAL REVISION'
    print(f'\n  E5.1 VERDICT: {verdict}')
    print('  Some conclusions changed. H4 verdict needs update before S1.')

# Save verdict
pd.DataFrame([{'verdict': verdict, 'all_core_unchanged': all_pass,
                'pre_close_mismatch_pct': round(pre_close_mm/pre_close_total*100, 3),
                'full_data_stocks': len(full_stocks), 'total_stocks': len(row_counts)}]).to_csv(
    os.path.join(OUT, 'e51_verdict.csv'), index=False)

print('\nE5.1 complete.')
