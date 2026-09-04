#!/usr/bin/env python3
"""E1.1 ETF Failure Mechanism Audit — comprehensive analysis.

All thresholds frozen in PHASE_E1_1_REGISTRY.csv BEFORE this script runs.
No strategy optimization. All counterfactuals marked POST-HOC DIAGNOSTIC ONLY.
"""
import os, sys
import numpy as np
import pandas as pd
from collections import defaultdict

DATA_ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
WT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/etf_e0_wt'
OUT = os.path.join(WT, 'results', 'etf')
RAWDIR = os.path.join(DATA_ROOT, 'data', 'raw', 'etf')

# ===== LOAD DATA =====
print('loading data...')
feat = pd.read_parquet(os.path.join(RAWDIR, 'etf_feat_long.parquet'))
feat['date'] = pd.to_datetime(feat['date'])
# Compute BB mid and upper for path analysis
feat = feat.sort_values(['etf', 'date'])
feat['bb_mid'] = feat.groupby('etf')['close_adj'].transform(lambda x: x.rolling(20, min_periods=20).mean())
feat['bb_upper'] = 2 * feat['bb_mid'] - feat['bb_lower']

clusters = pd.read_csv(os.path.join(OUT, 'e0_cluster_assignments.csv'))
cluster_map = dict(zip(clusters['index_key'], clusters['cluster']))

master = pd.read_parquet(os.path.join(RAWDIR, 'master_mapping_full.parquet'))
# Compute index_key same way as E0 scripts
master['index_key'] = master.apply(
    lambda r: (r['index_code'] if pd.notna(r['index_code']) and str(r['index_code']) != 'nan'
               else r['bench_idx_name']), axis=1)
# Build index_key -> name/category mapping
idx_name = dict(zip(master['index_key'], master['index_name']))
idx_category = dict(zip(master['index_key'], master.get('index_category', pd.Series(['Other']*len(master)))))

# Load CSI300 for regime
idx_dir = os.path.join(RAWDIR, 'index_daily')
csi300_path = os.path.join(idx_dir, '000300_SH.parquet')
if os.path.exists(csi300_path):
    csi300 = pd.read_parquet(csi300_path)
    csi300['trade_date'] = pd.to_datetime(csi300['trade_date'])
    csi300 = csi300.sort_values('trade_date')
    csi300['cummax'] = csi300['close'].cummax()
    csi300['drawdown'] = csi300['close'] / csi300['cummax'] - 1
    csi300['ret_20d'] = csi300['close'].pct_change(20)
    csi300['ret_60d'] = csi300['close'].pct_change(60)
    csi300['vol_20d'] = csi300['close'].pct_change().rolling(20).std() * np.sqrt(252)
    csi300_map = csi300.set_index('trade_date')[['drawdown', 'ret_20d', 'ret_60d', 'vol_20d', 'close']].to_dict('index')
else:
    csi300_map = {}

def get_regime(dd):
    if pd.isna(dd): return 'unknown'
    if dd > -0.05: return 'uptrend'
    if dd > -0.15: return 'sideways'
    if dd > -0.25: return 'downtrend'
    return 'stress'

# ===== BUILD COMPLETE TRADES =====
def build_trades(trade_log_path, model_name):
    tl = pd.read_csv(trade_log_path, parse_dates=['date'])
    tl = tl.sort_values('date').reset_index(drop=True)

    # Match ENTRY+ADD with EXIT by (index_key, etf)
    open_positions = {}  # (index_key, etf) -> {entry_date, entry_price, total_shares, total_cost, adds}
    trades = []
    trade_id = 0

    for _, row in tl.iterrows():
        key = (row['index_key'], row['etf'])
        if row['action'] == 'ENTRY':
            open_positions[key] = {
                'entry_date': row['date'],
                'entry_price': row['price'],
                'total_shares': row['shares'],
                'total_cost': row['amount'] + row['fee'],
                'adds': [{'date': row['date'], 'shares': row['shares'], 'price': row['price']}],
                'max_level': row['level']
            }
        elif row['action'] == 'ADD':
            if key in open_positions:
                pos = open_positions[key]
                pos['total_shares'] += row['shares']
                pos['total_cost'] += row['amount'] + row['fee']
                pos['adds'].append({'date': row['date'], 'shares': row['shares'], 'price': row['price']})
                pos['max_level'] = max(pos['max_level'], row['level'])
        elif row['action'] in ('EXIT_PSTAR', 'EXIT_FINAL'):
            if key in open_positions:
                pos = open_positions.pop(key)
                avg_cost = pos['total_cost'] / pos['total_shares']
                exit_price = row['price']
                trade_return = (exit_price - avg_cost) / avg_cost
                trades.append({
                    'trade_id': trade_id,
                    'model': model_name,
                    'index_key': row['index_key'],
                    'index_name': idx_name.get(row['index_key'], row['index_key']),
                    'etf': row['etf'],
                    'entry_date': pos['entry_date'],
                    'entry_price': pos['entry_price'],
                    'avg_cost': avg_cost,
                    'exit_date': row['date'],
                    'exit_price': exit_price,
                    'exit_action': row['action'],
                    'shares': pos['total_shares'],
                    'holding_days': (row['date'] - pos['entry_date']).days,
                    'trade_return': trade_return,
                    'pnl': row.get('pnl', (exit_price - avg_cost) * pos['total_shares']),
                    'n_adds': len(pos['adds']) - 1,
                    'max_level': pos['max_level'],
                    'cluster': cluster_map.get(row['index_key'], -1),
                })
                trade_id += 1

    return pd.DataFrame(trades)

print('building Model 1 trades...')
trades_m1 = build_trades(os.path.join(OUT, 'e1_model1_trade_log.csv'), 'Model1')
print(f'  {len(trades_m1)} complete trades')
print('building Model 2 trades...')
trades_m2 = build_trades(os.path.join(OUT, 'e1_model2_trade_log.csv'), 'Model2')
print(f'  {len(trades_m2)} complete trades')

# ===== MAE/MFE + BB PATH + FAILURE CLASSIFICATION =====
def compute_trade_paths(trades_df):
    """For each trade, get price path during holding and compute MAE/MFE/BB hits."""
    results = []
    feat_etf = {etf: g.sort_values('date') for etf, g in feat.groupby('etf')}

    for _, t in trades_df.iterrows():
        etf_data = feat_etf.get(t['etf'])
        if etf_data is None:
            results.append({**t.to_dict(), 'MAE_pct': np.nan, 'MFE_pct': np.nan,
                           'hit_mid': False, 'hit_upper': False, 'failure_class': 'E_OTHER'})
            continue

        mask = (etf_data['date'] >= t['entry_date']) & (etf_data['date'] <= t['exit_date'])
        path = etf_data[mask].copy()
        if len(path) == 0:
            results.append({**t.to_dict(), 'MAE_pct': np.nan, 'MFE_pct': np.nan,
                           'hit_mid': False, 'hit_upper': False, 'failure_class': 'E_OTHER'})
            continue

        # Use avg_cost as reference for MAE/MFE (actual breakeven)
        ref_price = t['avg_cost']
        path['ret_from_entry'] = path['close_adj'] / ref_price - 1

        mae = path['ret_from_entry'].min()
        mfe = path['ret_from_entry'].max()
        mae_day = path.loc[path['ret_from_entry'].idxmin(), 'date']
        mfe_day = path.loc[path['ret_from_entry'].idxmax(), 'date']

        # BB hits
        hit_mid = (path['close_adj'] >= path['bb_mid']).any() if path['bb_mid'].notna().any() else False
        hit_upper = (path['close_adj'] >= path['bb_upper']).any() if path['bb_upper'].notna().any() else False
        days_to_mid = np.nan
        if hit_mid:
            mid_days = path[path['close_adj'] >= path['bb_mid']]
            if len(mid_days) > 0:
                days_to_mid = (mid_days.iloc[0]['date'] - t['entry_date']).days
        days_to_upper = np.nan
        if hit_upper:
            up_days = path[path['close_adj'] >= path['bb_upper']]
            if len(up_days) > 0:
                days_to_upper = (up_days.iloc[0]['date'] - t['entry_date']).days

        # MFE at mid hit (hypothesis-generating diagnostic)
        mfe_at_mid = np.nan
        if hit_mid and days_to_mid is not np.nan:
            mid_date = mid_days.iloc[0]['date']
            mfe_at_mid = path[path['date'] <= mid_date]['ret_from_entry'].max()

        # Failure classification (frozen thresholds)
        first5 = path.head(5)
        first10 = path.head(10)
        mae_5d = first5['ret_from_entry'].min() if len(first5) > 0 else 0
        mae_10d = first10['ret_from_entry'].min() if len(first10) > 0 else 0

        failure_class = 'E_OTHER'
        if t['trade_return'] <= 0:  # only classify losers
            if mae_10d < -0.15:
                failure_class = 'D_CRASH_CONTINUATION'
            elif mfe >= 0.05 or hit_mid:
                failure_class = 'B_REBOUND_RELAPSE'
            elif mae_5d < -0.05 and mfe < 0.02:
                failure_class = 'A_IMMEDIATE_FAILURE'
            elif t['holding_days'] > 60 and mfe < 0.05:
                failure_class = 'C_SLOW_BLEED'

        # Signal context (from daily panel)
        results.append({
            **t.to_dict(),
            'MAE_pct': round(mae * 100, 2),
            'MAE_day': str(mae_day.date()) if pd.notna(mae_day) else '',
            'MFE_pct': round(mfe * 100, 2),
            'MFE_day': str(mfe_day.date()) if pd.notna(mfe_day) else '',
            'hit_mid': hit_mid,
            'hit_upper': hit_upper,
            'days_to_mid': days_to_mid,
            'days_to_upper': days_to_upper,
            'mfe_at_mid_pct': round(mfe_at_mid * 100, 2) if pd.notna(mfe_at_mid) else np.nan,
            'hit_mid_then_failed': hit_mid and t['trade_return'] <= 0,
            'hit_mid_then_upper': hit_mid and hit_upper,
            'never_hit_mid': not hit_mid,
            'failure_class': failure_class,
            'mae_5d_pct': round(mae_5d * 100, 2),
            'mae_10d_pct': round(mae_10d * 100, 2),
        })

    return pd.DataFrame(results)

print('computing Model 1 trade paths (MAE/MFE/BB)...')
trades_m1_full = compute_trade_paths(trades_m1)
print('computing Model 2 trade paths (MAE/MFE/BB)...')
trades_m2_full = compute_trade_paths(trades_m2)

# Save MAE/MFE files
trades_m1_full.to_csv(os.path.join(OUT, 'e11_mae_mfe_model1.csv'), index=False)
trades_m2_full.to_csv(os.path.join(OUT, 'e11_mae_mfe_model2.csv'), index=False)
print(f'saved MAE/MFE: Model1={len(trades_m1_full)}, Model2={len(trades_m2_full)}')

# ===== A. TRADE DISTRIBUTION =====
def trade_distribution(df, model_name):
    rets = df['trade_return'].dropna()
    pnls = df['pnl'].dropna()
    return {
        'model': model_name,
        'trade_count': len(df),
        'mean_return_pct': round(rets.mean() * 100, 2),
        'median_return_pct': round(rets.median() * 100, 2),
        'win_rate_pct': round((rets > 0).mean() * 100, 2),
        'loss_rate_pct': round((rets <= 0).mean() * 100, 2),
        'P1_pct': round(rets.quantile(0.01) * 100, 2),
        'P5_pct': round(rets.quantile(0.05) * 100, 2),
        'P10_pct': round(rets.quantile(0.10) * 100, 2),
        'P25_pct': round(rets.quantile(0.25) * 100, 2),
        'P50_pct': round(rets.quantile(0.50) * 100, 2),
        'P75_pct': round(rets.quantile(0.75) * 100, 2),
        'P90_pct': round(rets.quantile(0.90) * 100, 2),
        'P95_pct': round(rets.quantile(0.95) * 100, 2),
        'P99_pct': round(rets.quantile(0.99) * 100, 2),
        'best_trade_pct': round(rets.max() * 100, 2),
        'worst_trade_pct': round(rets.min() * 100, 2),
        'gross_profit': round(pnls[pnls > 0].sum(), 2),
        'gross_loss': round(pnls[pnls <= 0].sum(), 2),
        'profit_factor': round(pnls[pnls > 0].sum() / abs(pnls[pnls <= 0].sum()), 4) if (pnls <= 0).any() else float('inf'),
    }

dist_m1 = trade_distribution(trades_m1_full, 'Model1')
dist_m2 = trade_distribution(trades_m2_full, 'Model2')
pd.DataFrame([dist_m1, dist_m2]).to_csv(os.path.join(OUT, 'e11_trade_distribution_model1.csv'), index=False)
# Also save combined
pd.DataFrame([dist_m1, dist_m2]).to_csv(os.path.join(OUT, 'e11_trade_distribution_model2.csv'), index=False)
print('saved trade distribution')

# ===== TAIL CONTRIBUTION =====
def tail_contribution(df, model_name):
    pnls = df['pnl'].dropna().sort_values()
    total_gross = pnls.sum()
    total_gross_loss = pnls[pnls <= 0].sum()
    rows = []
    for n in [1, 3, 5, 10]:
        worst_n = pnls.head(n)
        rows.append({
            'model': model_name, 'level': f'worst_{n}',
            'n_trades': min(n, len(pnls)),
            'sum_pnl': round(worst_n.sum(), 2),
            'pct_of_gross_loss': round(worst_n.sum() / abs(total_gross_loss) * 100, 2) if total_gross_loss != 0 else 0,
            'pct_of_total_gross': round(worst_n.sum() / abs(total_gross) * 100, 2) if total_gross != 0 else 0,
        })
    for pct_label, pct_val in [('worst_1pct', 0.01), ('worst_5pct', 0.05), ('worst_10pct', 0.10)]:
        n = max(1, int(len(pnls) * pct_val))
        worst_n = pnls.head(n)
        rows.append({
            'model': model_name, 'level': pct_label,
            'n_trades': n,
            'sum_pnl': round(worst_n.sum(), 2),
            'pct_of_gross_loss': round(worst_n.sum() / abs(total_gross_loss) * 100, 2) if total_gross_loss != 0 else 0,
            'pct_of_total_gross': round(worst_n.sum() / abs(total_gross) * 100, 2) if total_gross != 0 else 0,
        })
    return rows

tail_rows = tail_contribution(trades_m1_full, 'Model1') + tail_contribution(trades_m2_full, 'Model2')
pd.DataFrame(tail_rows).to_csv(os.path.join(OUT, 'e11_tail_contribution.csv'), index=False)
print('saved tail contribution')

# ===== COUNTERFACTUAL TAIL REMOVAL (POST-HOC DIAGNOSTIC ONLY) =====
def tail_removal_diagnostic(df, model_name):
    pnls = df['pnl'].dropna().sort_values()
    rets = df['trade_return'].dropna()
    rows = [{'model': model_name, 'exclusion': 'all_trades', 'n_remaining': len(pnls),
             'sum_pnl': round(pnls.sum(), 2), 'mean_return_pct': round(rets.mean()*100, 2),
             'profit_factor': round(pnls[pnls>0].sum()/abs(pnls[pnls<=0].sum()),4) if (pnls<=0).any() else float('inf'),
             'diagnostic_note': 'POST-HOC DIAGNOSTIC ONLY - NOT A TRADABLE STRATEGY'}]
    for n in [1, 3, 5, 10]:
        remaining = pnls.iloc[n:]
        remaining_rets = rets.sort_values().iloc[n:]
        rows.append({'model': model_name, 'exclusion': f'exclude_worst_{n}', 'n_remaining': len(remaining),
                     'sum_pnl': round(remaining.sum(), 2), 'mean_return_pct': round(remaining_rets.mean()*100, 2),
                     'profit_factor': round(remaining[remaining>0].sum()/abs(remaining[remaining<=0].sum()),4) if (remaining<=0).any() else float('inf'),
                     'diagnostic_note': 'POST-HOC DIAGNOSTIC ONLY - NOT A TRADABLE STRATEGY'})
    for pct_label, pct_val in [('5pct', 0.05), ('10pct', 0.10)]:
        n = max(1, int(len(pnls) * pct_val))
        remaining = pnls.iloc[n:]
        remaining_rets = rets.sort_values().iloc[n:]
        rows.append({'model': model_name, 'exclusion': f'exclude_worst_{pct_label}', 'n_remaining': len(remaining),
                     'sum_pnl': round(remaining.sum(), 2), 'mean_return_pct': round(remaining_rets.mean()*100, 2),
                     'profit_factor': round(remaining[remaining>0].sum()/abs(remaining[remaining<=0].sum()),4) if (remaining<=0).any() else float('inf'),
                     'diagnostic_note': 'POST-HOC DIAGNOSTIC ONLY - NOT A TRADABLE STRATEGY'})
    return rows

removal_rows = tail_removal_diagnostic(trades_m1_full, 'Model1') + tail_removal_diagnostic(trades_m2_full, 'Model2')
pd.DataFrame(removal_rows).to_csv(os.path.join(OUT, 'e11_tail_removal_diagnostic.csv'), index=False)
print('saved tail removal diagnostic')

# ===== BB PATH STATS =====
def bb_path_stats(df, model_name):
    total = len(df)
    winners = df[df['trade_return'] > 0]
    losers = df[df['trade_return'] <= 0]
    return {
        'model': model_name,
        'total_trades': total,
        'pct_hit_mid': round(df['hit_mid'].mean() * 100, 1),
        'pct_hit_upper': round(df['hit_upper'].mean() * 100, 1),
        'pct_winners_hit_mid': round(winners['hit_mid'].mean() * 100, 1) if len(winners) else 0,
        'pct_losers_hit_mid': round(losers['hit_mid'].mean() * 100, 1) if len(losers) else 0,
        'pct_winners_hit_upper': round(winners['hit_upper'].mean() * 100, 1) if len(winners) else 0,
        'pct_losers_hit_upper': round(losers['hit_upper'].mean() * 100, 1) if len(losers) else 0,
        'median_days_to_mid': round(df[df['hit_mid']]['days_to_mid'].median(), 1) if df['hit_mid'].any() else np.nan,
        'median_days_to_upper': round(df[df['hit_upper']]['days_to_upper'].median(), 1) if df['hit_upper'].any() else np.nan,
        'pct_hit_mid_never_upper': round((df['hit_mid'] & ~df['hit_upper']).mean() * 100, 1),
        'pct_hit_mid_then_failed': round(df['hit_mid_then_failed'].mean() * 100, 1),
        'pct_never_hit_mid': round(df['never_hit_mid'].mean() * 100, 1),
        'mean_mfe_at_mid_pct': round(df[df['hit_mid']]['mfe_at_mid_pct'].mean(), 2) if df['hit_mid'].any() else np.nan,
    }

bb_m1 = bb_path_stats(trades_m1_full, 'Model1')
bb_m2 = bb_path_stats(trades_m2_full, 'Model2')
pd.DataFrame([bb_m1, bb_m2]).to_csv(os.path.join(OUT, 'e11_bb_path_stats.csv'), index=False)
print('saved BB path stats')

# ===== WORST 20 TRADES AUTOPSY =====
def worst_trades_autopsy(df, model_name, daily_panel_path):
    dp = pd.read_csv(daily_panel_path, parse_dates=['date'])
    dp_map = dp.set_index('date')[['eligible_count', 'n_index_signal' if 'n_index_signal' in dp.columns else 'n_signal']].to_dict('index') if len(dp) else {}

    worst = df.nsmallest(20, 'trade_return').copy()
    worst['rank'] = range(1, len(worst) + 1)

    rows = []
    for _, t in worst.iterrows():
        entry_date = t['entry_date']
        # Signal context
        sig_ctx = dp_map.get(entry_date, {})
        eligible = sig_ctx.get('eligible_count', np.nan)
        n_sig = sig_ctx.get('n_index_signal', sig_ctx.get('n_signal', np.nan))
        sig_ratio = n_sig / eligible if (eligible and not pd.isna(eligible) and eligible > 0) else np.nan

        # CSI300 context
        csi = csi300_map.get(entry_date, {})
        csi_dd = csi.get('drawdown', np.nan)
        csi_ret20 = csi.get('ret_20d', np.nan)
        csi_ret60 = csi.get('ret_60d', np.nan)
        csi_vol = csi.get('vol_20d', np.nan)
        regime = get_regime(csi_dd)

        # Pre-entry index return (from ETF price as proxy)
        etf_data = feat[(feat['etf'] == t['etf']) & (feat['date'] <= entry_date)].tail(60)
        ret_20d_pre = np.nan
        ret_60d_pre = np.nan
        if len(etf_data) >= 21:
            ret_20d_pre = etf_data['close_adj'].iloc[-1] / etf_data['close_adj'].iloc[-21] - 1
        if len(etf_data) >= 61:
            ret_60d_pre = etf_data['close_adj'].iloc[-1] / etf_data['close_adj'].iloc[-61] - 1

        # BB z-score at entry
        entry_row = feat[(feat['etf'] == t['etf']) & (feat['date'] == entry_date)]
        bb_z = np.nan
        dist_to_ma20 = np.nan
        if len(entry_row) > 0:
            r = entry_row.iloc[0]
            if pd.notna(r['bb_mid']) and pd.notna(r['bb_lower']):
                bb_std = (r['bb_mid'] - r['bb_lower']) / 2
                if bb_std > 0:
                    bb_z = (r['close_adj'] - r['bb_mid']) / bb_std
                dist_to_ma20 = r['close_adj'] / r['bb_mid'] - 1

        rows.append({
            'rank': t['rank'], 'model': model_name,
            'index_name': t['index_name'], 'index_key': t['index_key'],
            'etf': t['etf'], 'entry_date': str(entry_date.date()),
            'exit_date': str(t['exit_date'].date()), 'holding_days': t['holding_days'],
            'trade_return_pct': round(t['trade_return'] * 100, 2),
            'pnl': round(t['pnl'], 2),
            'MAE_pct': t['MAE_pct'], 'MFE_pct': t['MFE_pct'],
            'hit_mid': t['hit_mid'], 'hit_upper': t['hit_upper'],
            'failure_class': t['failure_class'],
            'signal_count_same_day': n_sig, 'eligible_universe_count': eligible,
            'signal_ratio_pct': round(sig_ratio * 100, 1) if not pd.isna(sig_ratio) else np.nan,
            'csi300_drawdown_pct': round(csi_dd * 100, 2) if not pd.isna(csi_dd) else np.nan,
            'csi300_ret_20d_pct': round(csi_ret20 * 100, 2) if not pd.isna(csi_ret20) else np.nan,
            'csi300_ret_60d_pct': round(csi_ret60 * 100, 2) if not pd.isna(csi_ret60) else np.nan,
            'csi300_vol_20d': round(csi_vol, 4) if not pd.isna(csi_vol) else np.nan,
            'regime': regime,
            'risk_cluster': t['cluster'],
            'pre_entry_ret_20d_pct': round(ret_20d_pre * 100, 2) if not pd.isna(ret_20d_pre) else np.nan,
            'pre_entry_ret_60d_pct': round(ret_60d_pre * 100, 2) if not pd.isna(ret_60d_pre) else np.nan,
            'bb_z_at_entry': round(bb_z, 2) if not pd.isna(bb_z) else np.nan,
            'dist_to_MA20_pct': round(dist_to_ma20 * 100, 2) if not pd.isna(dist_to_ma20) else np.nan,
        })
    return pd.DataFrame(rows)

print('building worst 20 autopsy...')
worst_m1 = worst_trades_autopsy(trades_m1_full, 'Model1', os.path.join(OUT, 'e1_model1_daily_panel.csv'))
worst_m2 = worst_trades_autopsy(trades_m2_full, 'Model2', os.path.join(OUT, 'e1_model2_daily_panel.csv'))
pd.concat([worst_m1, worst_m2]).to_csv(os.path.join(OUT, 'e11_worst20_trades.csv'), index=False)
print(f'saved worst20: M1={len(worst_m1)}, M2={len(worst_m2)}')

# ===== WORST 10 PATH SNAPSHOTS =====
def worst10_paths(df, model_name):
    worst = df.nsmallest(10, 'trade_return')
    rows = []
    for rank, (_, t) in enumerate(worst.iterrows(), 1):
        etf_data = feat[feat['etf'] == t['etf']].sort_values('date')
        path = etf_data[(etf_data['date'] >= t['entry_date']) & (etf_data['date'] <= t['exit_date'])].copy()
        if len(path) == 0:
            continue
        path = path.reset_index(drop=True)
        ref = t['avg_cost']
        for day_offset in [0, 1, 3, 5, 10, 20, 40]:
            if day_offset < len(path):
                p = path.iloc[day_offset]
                ret = p['close_adj'] / ref - 1
                dd = path.iloc[:day_offset+1]['close_adj'].min() / ref - 1
                rows.append({
                    'rank': rank, 'model': model_name, 'index_name': t['index_name'],
                    'etf': t['etf'], 'entry_date': str(t['entry_date'].date()),
                    'day_offset': day_offset, 'date': str(p['date'].date()),
                    'price_return_pct': round(ret * 100, 2),
                    'drawdown_pct': round(dd * 100, 2),
                    'bb_mid': round(p['bb_mid'], 4) if pd.notna(p['bb_mid']) else np.nan,
                    'bb_upper': round(p['bb_upper'], 4) if pd.notna(p['bb_upper']) else np.nan,
                })
        # Exit
        rows.append({
            'rank': rank, 'model': model_name, 'index_name': t['index_name'],
            'etf': t['etf'], 'entry_date': str(t['entry_date'].date()),
            'day_offset': len(path) - 1, 'date': str(t['exit_date'].date()),
            'price_return_pct': round(t['trade_return'] * 100, 2),
            'drawdown_pct': round(t['MAE_pct'], 2),
            'bb_mid': np.nan, 'bb_upper': np.nan,
        })
    return pd.DataFrame(rows)

print('building worst 10 path snapshots...')
paths_m1 = worst10_paths(trades_m1_full, 'Model1')
paths_m2 = worst10_paths(trades_m2_full, 'Model2')
pd.concat([paths_m1, paths_m2]).to_csv(os.path.join(OUT, 'e11_worst10_paths.csv'), index=False)
print('saved worst10 paths')

# ===== FAILURE CLASSIFICATION =====
def failure_class_summary(df, model_name):
    losers = df[df['trade_return'] <= 0]
    summary = losers['failure_class'].value_counts().reset_index()
    summary.columns = ['failure_class', 'count']
    summary['model'] = model_name
    summary['pct_of_losers'] = round(summary['count'] / len(losers) * 100, 1)
    # Add mean return per class
    class_returns = losers.groupby('failure_class')['trade_return'].mean().reset_index()
    summary = summary.merge(class_returns, on='failure_class')
    summary['mean_return_pct'] = round(summary['trade_return'] * 100, 2)
    summary = summary.drop(columns=['trade_return'])
    return summary

fc_m1 = failure_class_summary(trades_m1_full, 'Model1')
fc_m2 = failure_class_summary(trades_m2_full, 'Model2')
pd.concat([fc_m1, fc_m2]).to_csv(os.path.join(OUT, 'e11_failure_classification.csv'), index=False)
print('saved failure classification')

# ===== HOLDING PERIOD ANALYSIS =====
def holding_period_analysis(df, model_name):
    winners = df[df['trade_return'] > 0]
    losers = df[df['trade_return'] <= 0]
    corr = df['holding_days'].corr(df['trade_return'])
    longest10 = df.nlargest(10, 'holding_days')[['index_name', 'holding_days', 'trade_return', 'hit_upper', 'failure_class']]
    return {
        'model': model_name,
        'all_mean_holding': round(df['holding_days'].mean(), 1),
        'all_median_holding': round(df['holding_days'].median(), 1),
        'all_P75_holding': round(df['holding_days'].quantile(0.75), 1),
        'all_P90_holding': round(df['holding_days'].quantile(0.90), 1),
        'all_max_holding': round(df['holding_days'].max(), 1),
        'winners_mean_holding': round(winners['holding_days'].mean(), 1) if len(winners) else 0,
        'winners_median_holding': round(winners['holding_days'].median(), 1) if len(winners) else 0,
        'losers_mean_holding': round(losers['holding_days'].mean(), 1) if len(losers) else 0,
        'losers_median_holding': round(losers['holding_days'].median(), 1) if len(losers) else 0,
        'corr_holding_return': round(corr, 4),
        'longest10_mean_return_pct': round(longest10['trade_return'].mean() * 100, 2),
        'longest10_pct_negative': round((longest10['trade_return'] <= 0).mean() * 100, 1),
        'longest10_hit_upper_pct': round(longest10['hit_upper'].mean() * 100, 1),
    }

hp_m1 = holding_period_analysis(trades_m1_full, 'Model1')
hp_m2 = holding_period_analysis(trades_m2_full, 'Model2')
pd.DataFrame([hp_m1, hp_m2]).to_csv(os.path.join(OUT, 'e11_holding_period_analysis.csv'), index=False)
print('saved holding period analysis')

# ===== SIGNAL BREADTH ANALYSIS =====
def signal_breadth_analysis(trades_df, daily_panel_path, model_name):
    dp = pd.read_csv(daily_panel_path, parse_dates=['date'])
    sig_col = 'n_index_signal' if 'n_index_signal' in dp.columns else 'n_signal'
    dp['signal_ratio'] = dp[sig_col] / dp['eligible_count']

    def get_breadth_bin(ratio):
        if pd.isna(ratio) or ratio < 0.05: return '0-5%'
        if ratio < 0.10: return '5-10%'
        if ratio < 0.25: return '10-25%'
        if ratio < 0.50: return '25-50%'
        return '50%+'

    # Merge signal ratio into trades
    ratio_map = dp.set_index('date')['signal_ratio'].to_dict()
    trades_df = trades_df.copy()
    trades_df['signal_ratio'] = trades_df['entry_date'].map(ratio_map)
    trades_df['breadth_bin'] = trades_df['signal_ratio'].apply(get_breadth_bin)

    rows = []
    for b in ['0-5%', '5-10%', '10-25%', '25-50%', '50%+']:
        sub = trades_df[trades_df['breadth_bin'] == b]
        if len(sub) == 0:
            rows.append({'model': model_name, 'breadth_bin': b, 'trade_count': 0})
            continue
        pnls = sub['pnl'].dropna()
        gp = pnls[pnls > 0].sum()
        gl = abs(pnls[pnls <= 0].sum())
        rows.append({
            'model': model_name, 'breadth_bin': b, 'trade_count': len(sub),
            'mean_return_pct': round(sub['trade_return'].mean() * 100, 2),
            'median_return_pct': round(sub['trade_return'].median() * 100, 2),
            'win_rate_pct': round((sub['trade_return'] > 0).mean() * 100, 1),
            'profit_factor': round(gp / gl, 4) if gl > 0 else float('inf'),
            'mean_MAE_pct': round(sub['MAE_pct'].mean(), 2),
            'mean_MFE_pct': round(sub['MFE_pct'].mean(), 2),
        })

    # Low vs high breadth
    low = trades_df[trades_df['signal_ratio'] < 0.10]
    high = trades_df[trades_df['signal_ratio'] >= 0.25]
    for label, sub in [('low_breadth(<10%)', low), ('high_breadth(>=25%)', high)]:
        if len(sub) > 0:
            pnls = sub['pnl'].dropna()
            gp = pnls[pnls > 0].sum()
            gl = abs(pnls[pnls <= 0].sum())
            rows.append({
                'model': model_name, 'breadth_bin': label, 'trade_count': len(sub),
                'mean_return_pct': round(sub['trade_return'].mean() * 100, 2),
                'median_return_pct': round(sub['trade_return'].median() * 100, 2),
                'win_rate_pct': round((sub['trade_return'] > 0).mean() * 100, 1),
                'profit_factor': round(gp / gl, 4) if gl > 0 else float('inf'),
            })
    return pd.DataFrame(rows)

print('building signal breadth analysis...')
sb_m1 = signal_breadth_analysis(trades_m1_full, os.path.join(OUT, 'e1_model1_daily_panel.csv'), 'Model1')
sb_m2 = signal_breadth_analysis(trades_m2_full, os.path.join(OUT, 'e1_model2_daily_panel.csv'), 'Model2')
pd.concat([sb_m1, sb_m2]).to_csv(os.path.join(OUT, 'e11_signal_breadth_analysis.csv'), index=False)
print('saved signal breadth analysis')

# ===== CLUSTER CROWDING =====
def cluster_crowding_analysis(trades_df, model_name):
    # For each trade, count same-day signals in same cluster
    # Use daily panel signal data
    dp_path = os.path.join(OUT, f'e1_{"model1" if model_name=="Model1" else "model2"}_daily_panel.csv')
    dp = pd.read_csv(dp_path, parse_dates=['date'])

    # Group trades by entry date and cluster
    trades_df = trades_df.copy()
    date_cluster = trades_df.groupby(['entry_date', 'cluster']).size().reset_index(name='same_cluster_entries')
    date_total = trades_df.groupby('entry_date').size().reset_index(name='same_day_entries')
    trades_df = trades_df.merge(date_cluster, on=['entry_date', 'cluster'], how='left')
    trades_df = trades_df.merge(date_total, on='entry_date', how='left')
    trades_df['cluster_share'] = trades_df['same_cluster_entries'] / trades_df['same_day_entries']

    rows = []
    for conc_label, mask in [('low(<33%)', trades_df['cluster_share'] < 0.33),
                               ('medium(33-66%)', (trades_df['cluster_share'] >= 0.33) & (trades_df['cluster_share'] <= 0.66)),
                               ('high(>66%)', trades_df['cluster_share'] > 0.66)]:
        sub = trades_df[mask]
        if len(sub) > 0:
            pnls = sub['pnl'].dropna()
            gp = pnls[pnls > 0].sum()
            gl = abs(pnls[pnls <= 0].sum())
            rows.append({
                'model': model_name, 'cluster_concentration': conc_label,
                'trade_count': len(sub),
                'mean_return_pct': round(sub['trade_return'].mean() * 100, 2),
                'win_rate_pct': round((sub['trade_return'] > 0).mean() * 100, 1),
                'profit_factor': round(gp / gl, 4) if gl > 0 else float('inf'),
            })
    return pd.DataFrame(rows)

print('building cluster crowding analysis...')
cc_m1 = cluster_crowding_analysis(trades_m1_full, 'Model1')
cc_m2 = cluster_crowding_analysis(trades_m2_full, 'Model2')
pd.concat([cc_m1, cc_m2]).to_csv(os.path.join(OUT, 'e11_cluster_crowding_analysis.csv'), index=False)
print('saved cluster crowding analysis')

# ===== TOP-N INFORMATION CONTENT =====
def topn_information_content(model_name):
    """Compare selected Top-N vs non-selected signals on fixed forward horizons."""
    # Use daily panel to find signal days, then compare selected vs non-selected
    dp_path = os.path.join(OUT, f'e1_{"model1" if model_name=="Model1" else "model2"}_daily_panel.csv')
    dp = pd.read_csv(dp_path, parse_dates=['date'])
    sig_col = 'n_index_signal' if 'n_index_signal' in dp.columns else 'n_signal'

    # For each signal day, get all signals from feature data
    # This is expensive, so sample up to 100 signal days
    signal_days = dp[dp[sig_col] > 0]['date'].tolist()
    if len(signal_days) > 100:
        np.random.seed(42)
        signal_days = list(np.random.choice(signal_days, 100, replace=False))

    rows = []
    for d in signal_days:
        # Get all ETFs with BB signal on this day
        day_feat = feat[(feat['date'] == d) & (feat['close_adj'] < feat['bb_lower']) & feat['bb_lower'].notna()]
        if len(day_feat) == 0:
            continue
        day_feat = day_feat.sort_values('amount', ascending=False)
        selected = day_feat.head(10)
        non_selected = day_feat.iloc[10:]

        for horizon in [1, 3, 5, 10, 20]:
            for label, group in [('selected_Top10', selected), ('non_selected', non_selected)]:
                if len(group) == 0:
                    continue
                fwd_rets = []
                for _, r in group.iterrows():
                    etf_future = feat[(feat['etf'] == r['etf']) & (feat['date'] > d)].head(horizon)
                    if len(etf_future) >= horizon:
                        fwd_ret = etf_future.iloc[-1]['close_adj'] / r['close_adj'] - 1
                        fwd_rets.append(fwd_ret)
                if fwd_rets:
                    rows.append({
                        'model': model_name, 'signal_date': str(d.date()),
                        'horizon_days': horizon, 'group': label,
                        'n_signals': len(group),
                        'mean_fwd_return_pct': round(np.mean(fwd_rets) * 100, 3),
                        'median_fwd_return_pct': round(np.median(fwd_rets) * 100, 3),
                    })
    return pd.DataFrame(rows)

print('building Top-N information content (this may take a minute)...')
topn_m1 = topn_information_content('Model1')
topn_m2 = topn_information_content('Model2')
pd.concat([topn_m1, topn_m2]).to_csv(os.path.join(OUT, 'e11_topn_information_content.csv'), index=False)
print(f'saved Top-N info content: M1={len(topn_m1)}, M2={len(topn_m2)}')

# ===== MODEL 1 VS MODEL 2 COMPARISON =====
def model_comparison(m1, m2):
    # Entry date overlap
    m1_entries = set(zip(m1['entry_date'], m1['etf']))
    m2_entries = set(zip(m2['entry_date'], m2['etf']))
    overlap = m1_entries & m2_entries

    # Worst trade overlap
    m1_worst5 = set(m1.nsmallest(5, 'trade_return')['etf'])
    m2_worst5 = set(m2.nsmallest(5, 'trade_return')['etf'])

    rows = [
        {'metric': 'total_trades', 'model1': len(m1), 'model2': len(m2)},
        {'metric': 'win_rate_pct', 'model1': round((m1['trade_return']>0).mean()*100,1), 'model2': round((m2['trade_return']>0).mean()*100,1)},
        {'metric': 'mean_return_pct', 'model1': round(m1['trade_return'].mean()*100,2), 'model2': round(m2['trade_return'].mean()*100,2)},
        {'metric': 'median_return_pct', 'model1': round(m1['trade_return'].median()*100,2), 'model2': round(m2['trade_return'].median()*100,2)},
        {'metric': 'profit_factor', 'model1': round(m1[m1['pnl']>0]['pnl'].sum()/abs(m1[m1['pnl']<=0]['pnl'].sum()),4), 'model2': round(m2[m2['pnl']>0]['pnl'].sum()/abs(m2[m2['pnl']<=0]['pnl'].sum()),4)},
        {'metric': 'mean_MAE_pct', 'model1': round(m1['MAE_pct'].mean(),2), 'model2': round(m2['MAE_pct'].mean(),2)},
        {'metric': 'mean_MFE_pct', 'model1': round(m1['MFE_pct'].mean(),2), 'model2': round(m2['MFE_pct'].mean(),2)},
        {'metric': 'pct_hit_mid', 'model1': round(m1['hit_mid'].mean()*100,1), 'model2': round(m2['hit_mid'].mean()*100,1)},
        {'metric': 'pct_hit_upper', 'model1': round(m1['hit_upper'].mean()*100,1), 'model2': round(m2['hit_upper'].mean()*100,1)},
        {'metric': 'mean_holding_days', 'model1': round(m1['holding_days'].mean(),1), 'model2': round(m2['holding_days'].mean(),1)},
        {'metric': 'entry_overlap_count', 'model1': len(overlap), 'model2': len(overlap)},
        {'metric': 'worst5_etf_overlap', 'model1': len(m1_worst5 & m2_worst5), 'model2': len(m1_worst5 & m2_worst5)},
        {'metric': 'pct_hit_mid_then_failed', 'model1': round(m1['hit_mid_then_failed'].mean()*100,1), 'model2': round(m2['hit_mid_then_failed'].mean()*100,1)},
    ]
    return pd.DataFrame(rows)

comp = model_comparison(trades_m1_full, trades_m2_full)
comp.to_csv(os.path.join(OUT, 'e11_model1_vs_model2.csv'), index=False)
print('saved Model1 vs Model2 comparison')

# ===== PROFIT FACTOR DECOMPOSITION =====
def pf_decomposition(df, model_name):
    winners = df[df['trade_return'] > 0]
    losers = df[df['trade_return'] <= 0]
    gp = winners['pnl'].sum()
    gl = abs(losers['pnl'].sum())
    avg_win = winners['pnl'].mean() if len(winners) else 0
    avg_loss = abs(losers['pnl'].mean()) if len(losers) else 0
    payoff_ratio = avg_win / avg_loss if avg_loss > 0 else float('inf')
    breakeven_winrate = 1 / (1 + payoff_ratio) * 100 if payoff_ratio != float('inf') else 0
    actual_winrate = len(winners) / len(df) * 100
    expectancy = actual_winrate/100 * avg_win - (1-actual_winrate/100) * avg_loss
    return {
        'model': model_name,
        'gross_profit': round(gp, 2),
        'gross_loss': round(gl, 2),
        'profit_factor': round(gp / gl, 4) if gl > 0 else float('inf'),
        'winner_count': len(winners),
        'loser_count': len(losers),
        'avg_winner_pnl': round(avg_win, 2),
        'avg_loser_pnl': round(avg_loss, 2),
        'median_winner_pnl': round(winners['pnl'].median(), 2) if len(winners) else 0,
        'median_loser_pnl': round(losers['pnl'].median(), 2) if len(losers) else 0,
        'payoff_ratio': round(payoff_ratio, 4),
        'breakeven_win_rate_pct': round(breakeven_winrate, 2),
        'actual_win_rate_pct': round(actual_winrate, 2),
        'expectancy_per_trade': round(expectancy, 2),
        'failure_due_to': 'payoff_ratio' if payoff_ratio < 1 else ('win_rate' if actual_winrate < breakeven_winrate else 'both'),
    }

pf_m1 = pf_decomposition(trades_m1_full, 'Model1')
pf_m2 = pf_decomposition(trades_m2_full, 'Model2')
pd.DataFrame([pf_m1, pf_m2]).to_csv(os.path.join(OUT, 'e11_profit_factor_decomposition.csv'), index=False)
print('saved PF decomposition')

# ===== STOCK VS ETF DISPERSION (limitation note) =====
dispersion_note = pd.DataFrame([{
    'item': 'stock_vs_etf_cross_sectional_dispersion',
    'status': 'LIMITATION - stock signal daily detail not readily available in ETF worktree',
    'note': 'Main repo stock pipeline not rebuilt per E1.1 rules. ETF signal dispersion available from E0/E1 daily panels.',
    'etf_signal_ratio_mean': '',  # will fill below
}])
# Compute ETF signal dispersion from daily panels
dp1 = pd.read_csv(os.path.join(OUT, 'e1_model1_daily_panel.csv'))
sig_col1 = 'n_index_signal' if 'n_index_signal' in dp1.columns else 'n_signal'
dp1['ratio'] = dp1[sig_col1] / dp1['eligible_count']
print(f'ETF signal ratio: mean={dp1["ratio"].mean():.4f}, median={dp1["ratio"].median():.4f}, max={dp1["ratio"].max():.4f}')
print(f'ETF zero-signal days: {(dp1[sig_col1]==0).mean()*100:.1f}%')
print(f'ETF median signals/day: {dp1[sig_col1].median():.1f}, P90: {dp1[sig_col1].quantile(0.9):.1f}')

dispersion_note.to_csv(os.path.join(OUT, 'e11_stock_vs_etf_dispersion.csv'), index=False)
print('saved stock vs ETF dispersion (limitation note)')

print('\n===== E1.1 ANALYSIS COMPLETE =====')
print(f'Output files in {OUT}')
