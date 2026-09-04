#!/usr/bin/env python3
"""E5 Stock vs ETF Cross-Sectional Dispersion Mechanism Audit.

Compares stock-level vs ETF-level BB mean reversion cross-sectional structure.
Core question H4: Does stock have a larger, more informative cross-sectional
idiosyncratic opportunity set than ETF/index?

RESEARCH STATUS: MECHANISM AUDIT / ADAPTIVE HISTORICAL RESEARCH
NOT strategy optimization.
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
print('E5 STOCK vs ETF CROSS-SECTIONAL DISPERSION AUDIT')
print('='*60)

# ===== 1. LOAD ETF DATA (reuse E4 data) =====
print('\n[1/5] Loading ETF data...')
feat_etf = pd.read_parquet(os.path.join(RAWDIR, 'etf_feat_long.parquet'))
feat_etf['date'] = pd.to_datetime(feat_etf['date'])
feat_etf = feat_etf[(feat_etf['date'] >= COMMON_START) & (feat_etf['date'] <= COMMON_END)].copy()
feat_etf = feat_etf.sort_values(['etf', 'date'])
feat_etf['bb_mid'] = feat_etf.groupby('etf')['close_adj'].transform(
    lambda x: x.rolling(BB_WINDOW, min_periods=BB_WINDOW).mean())
feat_etf['bb_std'] = (feat_etf['bb_mid'] - feat_etf['bb_lower']) / BB_STD
feat_etf['bb_z'] = (feat_etf['close_adj'] - feat_etf['bb_mid']) / feat_etf['bb_std']
feat_etf.loc[feat_etf['bb_std'] == 0, 'bb_z'] = np.nan

# ETF PIT eligible universe (same as E1-E4: listed, >=60 days, ADV60>=20M)
feat_etf['listed'] = (feat_etf['list_date'] <= feat_etf['date']) & (feat_etf['delist'].isna() | (feat_etf['delist'] > feat_etf['date']))
feat_etf['n_days'] = feat_etf.groupby('etf')['date'].cumcount() + 1
etf_eligible = feat_etf[(feat_etf['listed']) & (feat_etf['n_days'] >= 60) & (feat_etf['adv60'] >= 20000)].copy()
etf_eligible['signal'] = (etf_eligible['close_adj'] < etf_eligible['bb_lower']) & etf_eligible['bb_lower'].notna()

# Forward returns for ETF
etf_eligible = etf_eligible.sort_values(['etf', 'date'])
for h in [1, 3, 5, 10, 20]:
    etf_eligible[f'fwd_{h}d'] = etf_eligible.groupby('etf')['close_adj'].shift(-h) / etf_eligible['close_adj'] - 1

print(f'  ETF eligible rows: {len(etf_eligible)}, unique ETFs: {etf_eligible["etf"].nunique()}')
print(f'  ETF signal rows: {etf_eligible["signal"].sum()}')
etf_trading_days = sorted(etf_eligible['date'].unique())
print(f'  ETF trading days: {len(etf_trading_days)}')

# ===== 2. LOAD STOCK DATA =====
print('\n[2/5] Loading stock data...')
stock_frames = []
for y in range(2020, 2025):
    df = pd.read_parquet(os.path.join(STOCK_ROOT, 'data', 'kline', f'{y}.parquet'))
    df['year'] = y
    stock_frames.append(df)
stock_raw = pd.concat(stock_frames, ignore_index=True)
print(f'  Stock raw rows: {len(stock_raw)}, unique stocks: {stock_raw["ts_code"].nunique()}')

# Assign dates: each stock has N rows per year in chronological order.
# Use ETF trading days as canonical calendar.
stock_raw = stock_raw.sort_values(['ts_code', 'year']).reset_index(drop=True)
# For each stock-year, assign row index -> trading day of that year
stock_raw['row_in_year'] = stock_raw.groupby(['ts_code', 'year']).cumcount()

# Get trading days per year from ETF data
etf_dates_by_year = {}
for y in range(2020, 2025):
    year_dates = sorted(etf_eligible[etf_eligible['date'].dt.year == y]['date'].unique())
    etf_dates_by_year[y] = year_dates
    print(f'  Year {y}: {len(year_dates)} ETF trading days, stock rows/stock: {stock_raw[stock_raw["year"]==y].groupby("ts_code").size().median()}')

def assign_date(row):
    y = row['year']
    idx = int(row['row_in_year'])
    dates = etf_dates_by_year.get(y, [])
    if idx < len(dates):
        return dates[idx]
    return pd.NaT

stock_raw['date'] = stock_raw.apply(assign_date, axis=1)
stock_raw = stock_raw.dropna(subset=['date']).copy()
stock_raw['close_adj'] = stock_raw['close'] * stock_raw['adj_factor']
stock_raw = stock_raw.sort_values(['ts_code', 'date']).reset_index(drop=True)

# Compute BB features for stocks
stock_raw['ma20'] = stock_raw.groupby('ts_code')['close_adj'].transform(
    lambda x: x.rolling(BB_WINDOW, min_periods=BB_WINDOW).mean())
stock_raw['sd20'] = stock_raw.groupby('ts_code')['close_adj'].transform(
    lambda x: x.rolling(BB_WINDOW, min_periods=BB_WINDOW).std())
stock_raw['bb_lower'] = stock_raw['ma20'] - BB_STD * stock_raw['sd20']
stock_raw['bb_z'] = (stock_raw['close_adj'] - stock_raw['ma20']) / stock_raw['sd20']
stock_raw.loc[stock_raw['sd20'] == 0, 'bb_z'] = np.nan
stock_raw['signal'] = (stock_raw['close_adj'] < stock_raw['bb_lower']) & stock_raw['bb_lower'].notna()

# Stock listing filter: min 60 days (use n_days as proxy)
stock_raw['n_days'] = stock_raw.groupby('ts_code')['date'].cumcount() + 1
stock_eligible = stock_raw[stock_raw['n_days'] >= BB_WINDOW].copy()  # need at least BB window

# Forward returns for stocks
for h in [1, 3, 5, 10, 20]:
    stock_eligible[f'fwd_{h}d'] = stock_eligible.groupby('ts_code')['close_adj'].shift(-h) / stock_eligible['close_adj'] - 1

print(f'  Stock eligible rows: {len(stock_eligible)}, unique stocks: {stock_eligible["ts_code"].nunique()}')
print(f'  Stock signal rows: {stock_eligible["signal"].sum()}')

# ===== 3. CROSS-SECTIONAL DISPERSION =====
print('\n[3/5] Computing cross-sectional dispersion...')

def compute_dispersion(df, group_col, date_col, val_col, label):
    """Compute daily cross-sectional dispersion stats."""
    rows = []
    for d, g in df.groupby(date_col):
        vals = g[val_col].dropna()
        if len(vals) < 5:
            continue
        rows.append({
            'date': d,
            'asset_class': label,
            'count': len(vals),
            'mean': vals.mean(),
            'median': vals.median(),
            'std': vals.std(),
            'iqr': vals.quantile(0.75) - vals.quantile(0.25),
            'mad': (vals - vals.median()).abs().median(),
            'p10': vals.quantile(0.10),
            'p90': vals.quantile(0.90),
            'p10_p90_spread': vals.quantile(0.90) - vals.quantile(0.10),
            'min': vals.min(),
            'max': vals.max(),
        })
    return pd.DataFrame(rows)

# Eligible universe BB_Z dispersion
stock_disp_elig = compute_dispersion(stock_eligible, 'ts_code', 'date', 'bb_z', 'stock')
etf_disp_elig = compute_dispersion(etf_eligible, 'etf', 'date', 'bb_z', 'etf')

# Signal candidate BB_Z dispersion
stock_signals = stock_eligible[stock_eligible['signal']].copy()
etf_signals = etf_eligible[etf_eligible['signal']].copy()
stock_disp_sig = compute_dispersion(stock_signals, 'ts_code', 'date', 'bb_z', 'stock')
etf_disp_sig = compute_dispersion(etf_signals, 'etf', 'date', 'bb_z', 'etf')

daily_disp = pd.concat([stock_disp_elig.assign(scope='eligible'),
                         etf_disp_elig.assign(scope='eligible'),
                         stock_disp_sig.assign(scope='signal'),
                         etf_disp_sig.assign(scope='signal')], ignore_index=True)
daily_disp.to_csv(os.path.join(OUT, 'e5_dispersion_daily.csv'), index=False)

# Summary
disp_summary = daily_disp.groupby(['asset_class', 'scope']).agg(
    mean_std=('std', 'mean'),
    median_std=('std', 'median'),
    mean_iqr=('iqr', 'mean'),
    median_iqr=('iqr', 'median'),
    mean_mad=('mad', 'mean'),
    median_mad=('mad', 'median'),
    mean_p10p90=('p10_p90_spread', 'mean'),
    median_p10p90=('p10_p90_spread', 'median'),
    mean_count=('count', 'mean'),
    n_days=('date', 'count'),
).round(4).reset_index()
print('\n=== BB_Z CROSS-SECTIONAL DISPERSION SUMMARY ===')
print(disp_summary.to_string(index=False))
disp_summary.to_csv(os.path.join(OUT, 'e5_dispersion_summary.csv'), index=False)

# ===== 4. FORWARD RETURN DISPERSION =====
print('\n[4/5] Computing forward return dispersion and IC...')
fwd_disp_rows = []
ic_rows = []
for h in [1, 3, 5, 10, 20]:
    col = f'fwd_{h}d'
    # Stock signal candidates
    for label, sig_df in [('stock', stock_signals), ('etf', etf_signals)]:
        valid = sig_df[sig_df[col].notna() & sig_df['bb_z'].notna()]
        # Daily forward return dispersion
        for d, g in valid.groupby('date'):
            rets = g[col].dropna()
            if len(rets) < 5:
                continue
            fwd_disp_rows.append({
                'horizon': f'{h}d', 'asset_class': label, 'date': d,
                'count': len(rets), 'std': rets.std(),
                'iqr': rets.quantile(0.75) - rets.quantile(0.25),
                'mad': (rets - rets.median()).abs().median(),
                'p10_p90': rets.quantile(0.90) - rets.quantile(0.10),
            })
        # Common BB_Z IC (Spearman): deeper oversold (more negative bb_z) -> better return
        # rank bb_z ascending (most negative = rank 1), so positive IC = deeper oversold predicts better return
        if len(valid) > 10:
            valid = valid.copy()
            valid['bbz_rank'] = valid.groupby('date')['bb_z'].rank(ascending=True, method='min')
            # Pooled IC
            pooled_ic = valid[['bbz_rank', col]].corr(method='spearman').iloc[0, 1]
            # Daily IC
            daily_ics = []
            for d, g in valid.groupby('date'):
                if len(g) >= 5:
                    ic = g[['bbz_rank', col]].corr(method='spearman').iloc[0, 1]
                    if not np.isnan(ic):
                        daily_ics.append(ic)
            # Amount native ranking IC
            valid['amt_rank'] = valid.groupby('date')['amount'].rank(ascending=False, method='min')
            pooled_ic_amt = valid[['amt_rank', col]].corr(method='spearman').iloc[0, 1]
            daily_ics_amt = []
            for d, g in valid.groupby('date'):
                if len(g) >= 5:
                    ic = g[['amt_rank', col]].corr(method='spearman').iloc[0, 1]
                    if not np.isnan(ic):
                        daily_ics_amt.append(ic)

            ic_rows.append({
                'horizon': f'{h}d', 'asset_class': label,
                'n': len(valid),
                'bbz_pooled_ic': round(pooled_ic, 4),
                'bbz_daily_mean': round(np.mean(daily_ics), 4) if daily_ics else np.nan,
                'bbz_daily_median': round(np.median(daily_ics), 4) if daily_ics else np.nan,
                'bbz_hit_rate': round(np.mean(np.array(daily_ics) > 0) * 100, 1) if daily_ics else np.nan,
                'n_valid_days': len(daily_ics),
                'amount_pooled_ic': round(pooled_ic_amt, 4),
                'amount_daily_mean': round(np.mean(daily_ics_amt), 4) if daily_ics_amt else np.nan,
                'amount_hit_rate': round(np.mean(np.array(daily_ics_amt) > 0) * 100, 1) if daily_ics_amt else np.nan,
            })

fwd_disp_df = pd.DataFrame(fwd_disp_rows)
fwd_disp_summary = fwd_disp_df.groupby(['horizon', 'asset_class']).agg(
    mean_std=('std', 'mean'), median_std=('std', 'median'),
    mean_iqr=('iqr', 'mean'), mean_mad=('mad', 'mean'),
    mean_p10p90=('p10_p90', 'mean'), n_days=('date', 'count'),
).round(4).reset_index()
print('\n=== FORWARD RETURN DISPERSION (signal candidates) ===')
print(fwd_disp_summary.to_string(index=False))
fwd_disp_df.to_csv(os.path.join(OUT, 'e5_forward_return_dispersion.csv'), index=False)

ic_df = pd.DataFrame(ic_rows)
print('\n=== COMMON BB_Z IC + NATIVE AMOUNT IC ===')
print(ic_df.to_string(index=False))
ic_df.to_csv(os.path.join(OUT, 'e5_common_bbz_ic.csv'), index=False)

# ===== 5. SIGNAL EXPECTANCY, TOP-N SEPARATION, BREADTH =====
print('\n[5/5] Signal expectancy, Top-N separation, breadth...')

# Raw signal expectancy (all signal candidates, no portfolio)
exp_rows = []
for h in [1, 3, 5, 10, 20]:
    col = f'fwd_{h}d'
    for label, sig_df in [('stock', stock_signals), ('etf', etf_signals)]:
        valid = sig_df[sig_df[col].notna()]
        if len(valid) == 0:
            continue
        exp_rows.append({
            'horizon': f'{h}d', 'asset_class': label,
            'n': len(valid),
            'mean_ret_pct': round(valid[col].mean() * 100, 3),
            'median_ret_pct': round(valid[col].median() * 100, 3),
            'win_rate_pct': round((valid[col] > 0).mean() * 100, 1),
            'std_pct': round(valid[col].std() * 100, 3),
        })
exp_df = pd.DataFrame(exp_rows)
print('\n=== RAW SIGNAL EXPECTANCY (all signal candidates) ===')
print(exp_df.to_string(index=False))
exp_df.to_csv(os.path.join(OUT, 'e5_signal_expectancy_stock_vs_etf.csv'), index=False)

# Top-N separation (native amount ranking)
topn_rows = []
for h in [1, 3, 5, 10, 20]:
    col = f'fwd_{h}d'
    for label, sig_df, id_col in [('stock', stock_signals, 'ts_code'), ('etf', etf_signals, 'etf')]:
        valid = sig_df[sig_df[col].notna()].copy()
        if len(valid) == 0:
            continue
        valid['amt_rank'] = valid.groupby('date')['amount'].rank(ascending=False, method='min')
        selected = valid[valid['amt_rank'] <= TOP_N]
        nonselected = valid[valid['amt_rank'] > TOP_N]
        if len(selected) == 0 or len(nonselected) == 0:
            continue
        topn_rows.append({
            'horizon': f'{h}d', 'asset_class': label,
            'selected_n': len(selected),
            'selected_mean_pct': round(selected[col].mean() * 100, 3),
            'selected_median_pct': round(selected[col].median() * 100, 3),
            'selected_win_pct': round((selected[col] > 0).mean() * 100, 1),
            'nonselected_n': len(nonselected),
            'nonselected_mean_pct': round(nonselected[col].mean() * 100, 3),
            'nonselected_median_pct': round(nonselected[col].median() * 100, 3),
            'nonselected_win_pct': round((nonselected[col] > 0).mean() * 100, 1),
            'diff_mean_pct': round((selected[col].mean() - nonselected[col].mean()) * 100, 3),
        })
topn_df = pd.DataFrame(topn_rows)
print('\n=== TOP-N (amount) SELECTED vs NON-SELECTED ===')
print(topn_df.to_string(index=False))
topn_df.to_csv(os.path.join(OUT, 'e5_topn_separation.csv'), index=False)

# Signal breadth comparison
breadth_rows = []
for label, elig_df, sig_df in [('stock', stock_eligible, stock_signals), ('etf', etf_eligible, etf_signals)]:
    daily_sig = sig_df.groupby('date').size()
    daily_elig = elig_df.groupby('date').size()
    ratio = (daily_sig / daily_elig).dropna()
    breadth_rows.append({
        'asset_class': label,
        'n_days': len(ratio),
        'zero_signal_days_pct': round((ratio == 0).mean() * 100, 1),
        'median_signal_ratio_pct': round(ratio.median() * 100, 2),
        'p75_pct': round(ratio.quantile(0.75) * 100, 2),
        'p90_pct': round(ratio.quantile(0.90) * 100, 2),
        'p95_pct': round(ratio.quantile(0.95) * 100, 2),
        'max_pct': round(ratio.max() * 100, 2),
        'days_ge5_pct': round((ratio >= 0.05).mean() * 100, 1),
        'days_ge10_pct': round((ratio >= 0.10).mean() * 100, 1),
        'days_ge25_pct': round((ratio >= 0.25).mean() * 100, 1),
        'days_ge50_pct': round((ratio >= 0.50).mean() * 100, 1),
    })
breadth_df = pd.DataFrame(breadth_rows)
print('\n=== SIGNAL BREADTH COMPARISON ===')
print(breadth_df.to_string(index=False))
breadth_df.to_csv(os.path.join(OUT, 'e5_signal_breadth_comparison.csv'), index=False)

# BB_Z quantile monotonicity
quant_rows = []
for h in [5, 10, 20]:
    col = f'fwd_{h}d'
    for label, sig_df in [('stock', stock_signals), ('etf', etf_signals)]:
        valid = sig_df[sig_df[col].notna() & sig_df['bb_z'].notna()].copy()
        if len(valid) < 50:
            continue
        valid['bbz_q'] = valid.groupby('date')['bb_z'].transform(
            lambda x: pd.qcut(x, 5, labels=False, duplicates='drop') if len(x) >= 5 else np.nan)
        for q in range(5):
            qg = valid[valid['bbz_q'] == q]
            if len(qg) == 0:
                continue
            quant_rows.append({
                'horizon': f'{h}d', 'asset_class': label,
                'quantile': f'Q{q+1}', 'q_label': 'deepest' if q == 0 else ('shallowest' if q == 4 else ''),
                'count': len(qg),
                'mean_ret_pct': round(qg[col].mean() * 100, 3),
                'median_ret_pct': round(qg[col].median() * 100, 3),
                'win_rate_pct': round((qg[col] > 0).mean() * 100, 1),
            })
quant_df = pd.DataFrame(quant_rows)
print('\n=== BB_Z QUANTILE MONOTONICITY (20d) ===')
print(quant_df[quant_df['horizon'] == '20d'].to_string(index=False))
quant_df.to_csv(os.path.join(OUT, 'e5_bbz_quantiles.csv'), index=False)

# Matched dates: both have >=5 signal candidates
stock_sig_dates = set(stock_signals.groupby('date').size()[lambda x: x >= 5].index)
etf_sig_dates = set(etf_signals.groupby('date').size()[lambda x: x >= 5].index)
matched_dates = sorted(stock_sig_dates & etf_sig_dates)
print(f'\n=== MATCHED DATES: {len(matched_dates)} days (both >=5 signals) ===')
pd.DataFrame({'date': matched_dates}).to_csv(os.path.join(OUT, 'e5_matched_dates.csv'), index=False)

# Matched date summary: BB_Z dispersion on matched dates
matched_rows = []
for d in matched_dates:
    s_bbz = stock_signals[stock_signals['date'] == d]['bb_z'].dropna()
    e_bbz = etf_signals[etf_signals['date'] == d]['bb_z'].dropna()
    if len(s_bbz) >= 5 and len(e_bbz) >= 5:
        matched_rows.append({
            'date': d,
            'stock_n': len(s_bbz), 'stock_bbz_std': s_bbz.std(), 'stock_bbz_iqr': s_bbz.quantile(0.75) - s_bbz.quantile(0.25),
            'etf_n': len(e_bbz), 'etf_bbz_std': e_bbz.std(), 'etf_bbz_iqr': e_bbz.quantile(0.75) - e_bbz.quantile(0.25),
        })
matched_df = pd.DataFrame(matched_rows)
if len(matched_df) > 0:
    print(f'  Stock BB_Z std (matched): mean={matched_df["stock_bbz_std"].mean():.4f}, median={matched_df["stock_bbz_std"].median():.4f}')
    print(f'  ETF BB_Z std (matched): mean={matched_df["etf_bbz_std"].mean():.4f}, median={matched_df["etf_bbz_std"].median():.4f}')
    print(f'  Stock/ETF BB_Z std ratio: {matched_df["stock_bbz_std"].mean() / matched_df["etf_bbz_std"].mean():.2f}x')
matched_df.to_csv(os.path.join(OUT, 'e5_matched_date_summary.csv'), index=False)

# Random Top-N control (stock only, 20d horizon)
print('\n=== RANDOM TOP-N CONTROL (stock, 20d) ===')
rng = np.random.RandomState(RANDOM_SEED)
rand_rows = []
for label, sig_df, id_col in [('stock', stock_signals, 'ts_code'), ('etf', etf_signals, 'etf')]:
    valid = sig_df[sig_df['fwd_20d'].notna()].copy()
    if len(valid) == 0:
        continue
    valid['amt_rank'] = valid.groupby('date')['amount'].rank(ascending=False, method='min')
    actual_selected = valid[valid['amt_rank'] <= TOP_N]
    actual_mean = actual_selected['fwd_20d'].mean()

    random_means = []
    for d, g in valid.groupby('date'):
        if len(g) < TOP_N:
            continue
        for _ in range(RANDOM_REPS):
            sample = g.sample(n=TOP_N, random_state=rng)
            random_means.append(sample['fwd_20d'].mean())
    if random_means:
        rand_arr = np.array(random_means)
        pctile = (rand_arr < actual_mean).mean() * 100
        rand_rows.append({
            'asset_class': label,
            'actual_mean_pct': round(actual_mean * 100, 3),
            'random_mean_pct': round(rand_arr.mean() * 100, 3),
            'random_p5_pct': round(np.percentile(rand_arr, 5) * 100, 3),
            'random_p50_pct': round(np.percentile(rand_arr, 50) * 100, 3),
            'random_p95_pct': round(np.percentile(rand_arr, 95) * 100, 3),
            'actual_percentile': round(pctile, 1),
            'n_days': len(valid.groupby('date')),
        })
        print(f'  {label}: actual={actual_mean*100:.3f}%, random mean={rand_arr.mean()*100:.3f}%, actual percentile={pctile:.1f}%')
rand_df = pd.DataFrame(rand_rows)
rand_df.to_csv(os.path.join(OUT, 'e5_random_topn_control.csv'), index=False)

# Stock data audit
audit = pd.DataFrame([{
    'stock_source': f'{STOCK_ROOT}/data/kline/*.parquet',
    'stock_commit': '43e9e4a (master HEAD)',
    'stock_common_window': f'{COMMON_START} to {COMMON_END}',
    'stock_unique_stocks': int(stock_eligible['ts_code'].nunique()),
    'stock_eligible_rows': len(stock_eligible),
    'stock_signal_rows': int(stock_signals.shape[0]),
    'etf_unique': int(etf_eligible['etf'].nunique()),
    'etf_eligible_rows': len(etf_eligible),
    'etf_signal_rows': int(etf_signals.shape[0]),
    'matched_dates': len(matched_dates),
    'date_assignment': 'ETF trading calendar mapped to stock row-in-year index',
    'limitation': 'No stock_basic/list_date/ST PIT data; using n_days>=20 as eligibility proxy; no ADV60 filter for stocks',
}])
audit.to_csv(os.path.join(OUT, 'e5_stock_data_audit.csv'), index=False)

print('\n' + '='*60)
print('E5 ANALYSIS COMPLETE')
print('='*60)
