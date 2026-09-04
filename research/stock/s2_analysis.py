#!/usr/bin/env python3
"""S2 Analysis — Control verification, candidate diagnostics, yearly analysis."""
import sys, os
import numpy as np
import pandas as pd

ETF_WT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/etf_e0_wt'
sys.path.insert(0, os.path.join(ETF_WT, 'research', 'stock'))
from s2_engine import run_fast_multi_strict_c_s2, prepare_v51

OUT = os.path.join(ETF_WT, 'results', 'stock')

print('='*60)
print('S2 ANALYSIS — Control verification + candidate diagnostics')
print('='*60)

# ===== 1. Prepare data =====
print('\n[1] Preparing data...')
days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51(
    limit_down_mode='correct', st_mode='pit')
for _d in days:
    _dd = D[_d]
    _dd['one_word'] = ((_dd['open_'] == _dd['high']) & (_dd['low'] == _dd['close'])
                       & (_dd['open_'] == _dd['close']))

# Find 2020-2024 day range
day_dates = [d.date() for d in days]
start_2020 = 0
end_2024 = next(i for i, d in enumerate(day_dates) if d.year > 2024)
print(f'  2020-2024: days[{start_2020}:{end_2024}] = {day_dates[start_2020]} to {day_dates[end_2024-1]}')

def compute_metrics(eq, tr):
    if len(eq) == 0:
        return {}
    eq = eq.copy()
    eq['date'] = pd.to_datetime(eq['date'])
    eq = eq.set_index('date')
    total_ret = eq['equity'].iloc[-1] / eq['equity'].iloc[0] - 1
    n_years = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (1 + total_ret) ** (1/n_years) - 1 if n_years > 0 else 0
    daily_ret = eq['equity'].pct_change().dropna()
    ann_vol = daily_ret.std() * np.sqrt(252) if len(daily_ret) > 1 else 0
    sharpe = (daily_ret.mean() * 252) / ann_vol if ann_vol > 0 else 0
    cummax = eq['equity'].cummax()
    drawdown = eq['equity'] / cummax - 1
    maxdd = drawdown.min()
    if len(tr) > 0:
        n_trades = len(tr)
        wins = tr[tr['pnl'] > 0]
        losses = tr[tr['pnl'] <= 0]
        win_rate = len(wins) / n_trades
        gross_profit = wins['pnl'].sum() if len(wins) > 0 else 0
        gross_loss = abs(losses['pnl'].sum()) if len(losses) > 0 else 0
        pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        avg_winner = wins['pnl'].mean() if len(wins) > 0 else 0
        avg_loser = losses['pnl'].mean() if len(losses) > 0 else 0
        payoff = abs(avg_winner / avg_loser) if avg_loser != 0 else float('inf')
        avg_hold = tr['hold_days'].mean()
    else:
        n_trades = 0; win_rate = 0; pf = 0; payoff = 0; avg_hold = 0
    return {
        'total_return_pct': round(total_ret * 100, 3),
        'cagr_pct': round(cagr * 100, 3),
        'sharpe': round(sharpe, 4),
        'maxdd_pct': round(maxdd * 100, 3),
        'n_trades': n_trades,
        'win_rate_pct': round(win_rate * 100, 2),
        'profit_factor': round(pf, 4),
        'payoff_ratio': round(payoff, 4),
        'avg_holding_days': round(avg_hold, 1),
    }

# ===== 2. Control 2020-2024 verification =====
print('\n[2] Running Control 2020-2024 (day_range verification)...')
eq_cw, tr_cw = run_fast_multi_strict_c_s2(
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
    K=3, top_n=10, max_levels=5, level_cash=200_000, initial_cash=1_000_000,
    slippage_bp=10, stamp_tax_mode='historical', exit_bb_mode='dynamic_touch',
    open_fill='limit_conservative', selection_mode='amount', seed=42,
    day_range=(start_2020, end_2024))
cw_metrics = compute_metrics(eq_cw, tr_cw)
print(f'  Control 2020-2024: TR={cw_metrics["total_return_pct"]}%, trades={cw_metrics["n_trades"]}, '
      f'WR={cw_metrics["win_rate_pct"]}%, PF={cw_metrics["profit_factor"]}, MaxDD={cw_metrics["maxdd_pct"]}%')
print(f'  Official G0:       TR=+30.30%, trades=76, WR=68.4%, PF=1.304, MaxDD=-30.79%')

recon = pd.DataFrame([{
    'metric': 'total_return_pct', 'control_2020_2024': cw_metrics['total_return_pct'],
    'official_g0': 30.295, 'diff': round(cw_metrics['total_return_pct'] - 30.295, 3),
    'match': 'YES' if abs(cw_metrics['total_return_pct'] - 30.295) < 1.0 else 'NO',
}, {
    'metric': 'n_trades', 'control_2020_2024': cw_metrics['n_trades'],
    'official_g0': 76, 'diff': cw_metrics['n_trades'] - 76,
    'match': 'YES' if abs(cw_metrics['n_trades'] - 76) <= 2 else 'NO',
}, {
    'metric': 'win_rate_pct', 'control_2020_2024': cw_metrics['win_rate_pct'],
    'official_g0': 68.42, 'diff': round(cw_metrics['win_rate_pct'] - 68.42, 2),
    'match': 'YES' if abs(cw_metrics['win_rate_pct'] - 68.42) < 2.0 else 'NO',
}, {
    'metric': 'profit_factor', 'control_2020_2024': cw_metrics['profit_factor'],
    'official_g0': 1.304, 'diff': round(cw_metrics['profit_factor'] - 1.304, 4),
    'match': 'YES' if abs(cw_metrics['profit_factor'] - 1.304) < 0.1 else 'NO',
}, {
    'metric': 'maxdd_pct', 'control_2020_2024': cw_metrics['maxdd_pct'],
    'official_g0': -30.79, 'diff': round(cw_metrics['maxdd_pct'] - (-30.79), 3),
    'match': 'YES' if abs(cw_metrics['maxdd_pct'] - (-30.79)) < 2.0 else 'NO',
}])
print(f'\n  Reconciliation:')
print(recon.to_string(index=False))
recon.to_csv(os.path.join(OUT, 's2_baseline_reconciliation.csv'), index=False)

# ===== 3. Candidate-level diagnostics =====
print('\n[3] Candidate-level diagnostics (amount quantiles + selected vs non-selected)...')

# Build candidate panel from daily data
candidate_rows = []
for i, d in enumerate(days):
    if d.year < 2020 or d.year > 2024:
        continue
    dd = D[d]
    gi = offset + i
    li = gi - np.array([first_eligible_i.get(tc, 0) for tc in dd['ts']])
    valid = (li >= 0) & ~dd['is_st']
    if not valid.any():
        continue
    cand_idx = np.where(valid)[0]
    for j in cand_idx:
        tc = dd['ts'][j]
        bb_lo = dd['bb_lower'][j]
        is_signal = (not np.isnan(bb_lo) and dd['close_adj'][j] < bb_lo and not dd['is_limit'][j])
        if is_signal:
            candidate_rows.append({
                'date': str(d.date()), 'ts_code': tc,
                'amount': dd['amount'][j], 'close_adj': dd['close_adj'][j],
            })

cand_df = pd.DataFrame(candidate_rows)
print(f'  Total BB signals 2020-2024: {len(cand_df)}')
print(f'  Unique signal dates: {cand_df["date"].nunique()}')

# Forward returns for candidates (using stock panel from S1.1)
# Load stock panel for forward returns
STOCK_ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo'
RAWDIR = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/data/raw/etf'
feat_etf = pd.read_parquet(os.path.join(RAWDIR, 'etf_feat_long.parquet'))
feat_etf['date'] = pd.to_datetime(feat_etf['date'])
all_dates = sorted(feat_etf['date'].unique())
cal_by_year = {y: [d for d in all_dates if d.year == y] for y in range(2020, 2025)}
expected = {2020: 243, 2021: 243, 2022: 242, 2023: 242, 2024: 242}

stock_frames = []
for y in range(2020, 2025):
    df = pd.read_parquet(os.path.join(STOCK_ROOT, 'data', 'kline', f'{y}.parquet'))
    df['year'] = y
    stock_frames.append(df)
stock_raw = pd.concat(stock_frames, ignore_index=True)
row_counts = stock_raw.groupby(['ts_code', 'year']).size().unstack(fill_value=0)
full_mask = pd.Series(True, index=row_counts.index)
for y, exp in expected.items():
    full_mask &= (row_counts[y] == exp)
full_stocks = full_mask[full_mask].index.tolist()

stock_full = stock_raw[stock_raw['ts_code'].isin(full_stocks)].copy()
stock_full = stock_full.sort_values(['ts_code', 'year']).reset_index(drop=True)
stock_full['row_in_year'] = stock_full.groupby(['ts_code', 'year']).cumcount()
stock_full['date'] = stock_full.apply(lambda r: cal_by_year[r['year']][int(r['row_in_year'])]
    if int(r['row_in_year']) < len(cal_by_year[r['year']]) else pd.NaT, axis=1)
stock_full = stock_full.dropna(subset=['date']).copy()
stock_full['close_adj'] = stock_full['close'] * stock_full['adj_factor']
stock_full = stock_full.sort_values(['ts_code', 'date']).reset_index(drop=True)
for h in [5, 10, 20, 40]:
    stock_full[f'fwd_{h}d'] = stock_full.groupby('ts_code')['close_adj'].shift(-h) / stock_full['close_adj'] - 1

# Merge candidates with forward returns
cand_df['date'] = pd.to_datetime(cand_df['date'])
cand_fwd = cand_df.merge(
    stock_full[['ts_code', 'date', 'fwd_5d', 'fwd_10d', 'fwd_20d', 'fwd_40d']],
    on=['ts_code', 'date'], how='inner')
print(f'  Candidates with forward returns: {len(cand_fwd)}')

# Amount quantiles (use rank-based to handle duplicates)
def amount_qcut(x):
    if len(x) < 5:
        return pd.Series(['Q_all'] * len(x), index=x.index)
    ranks = x.rank(method='first')
    try:
        return pd.qcut(ranks, 5, labels=['Q1_highest', 'Q2', 'Q3', 'Q4', 'Q5_lowest'])
    except ValueError:
        return pd.Series(['Q_all'] * len(x), index=x.index)

cand_fwd['amount_quantile'] = cand_fwd.groupby('date')['amount'].transform(amount_qcut)
amt_q = cand_fwd.groupby('amount_quantile', observed=True).agg(
    count=('fwd_20d', 'size'),
    mean_5d=('fwd_5d', lambda x: round(x.dropna().mean()*100, 3)),
    mean_10d=('fwd_10d', lambda x: round(x.dropna().mean()*100, 3)),
    mean_20d=('fwd_20d', lambda x: round(x.dropna().mean()*100, 3)),
    mean_40d=('fwd_40d', lambda x: round(x.dropna().mean()*100, 3)),
    median_20d=('fwd_20d', lambda x: round(x.dropna().median()*100, 3)),
    wr_20d=('fwd_20d', lambda x: round((x.dropna()>0).mean()*100, 1)),
).reset_index()
print(f'\n  Amount quantiles (Q1=highest amount, Q5=lowest):')
print(amt_q.to_string(index=False))
amt_q.to_csv(os.path.join(OUT, 's2_amount_quantiles.csv'), index=False)

# Selected Top-N (amount) vs non-selected vs all
cand_fwd['amount_rank'] = cand_fwd.groupby('date')['amount'].rank(ascending=False, method='first')
cand_fwd['selected_amount'] = cand_fwd['amount_rank'] <= 10

sel_stats = []
for label, mask in [('all', cand_fwd['fwd_20d'].notna()),
                     ('amount_top10', cand_fwd['selected_amount']),
                     ('non_selected', ~cand_fwd['selected_amount'])]:
    sub = cand_fwd[mask]
    for h in [5, 10, 20, 40]:
        v = sub[f'fwd_{h}d'].dropna()
        sel_stats.append({'group': label, 'horizon': f'{h}d', 'count': len(v),
                          'mean_pct': round(v.mean()*100, 3), 'median_pct': round(v.median()*100, 3),
                          'wr_pct': round((v>0).mean()*100, 1)})
sel_df = pd.DataFrame(sel_stats)
print(f'\n  Selected vs non-selected (candidate-level):')
print(sel_df.to_string(index=False))
sel_df.to_csv(os.path.join(OUT, 's2_candidate_quality.csv'), index=False)

# ===== 4. Yearly random distribution =====
print('\n[4] Yearly random distribution analysis...')
rand_df = pd.read_csv(os.path.join(OUT, 's2_random_portfolio_distribution.csv'))
# Load control trades for yearly breakdown
tr_ctrl = pd.read_csv(os.path.join(OUT, 's2_control_trades.csv'))
tr_ctrl['entry_date'] = pd.to_datetime(tr_ctrl['entry_date'])
tr_ctrl['exit_date'] = pd.to_datetime(tr_ctrl['exit_date'])
tr_ctrl['entry_year'] = tr_ctrl['entry_date'].dt.year

# Control yearly PnL
ctrl_yearly = tr_ctrl.groupby('entry_year').agg(
    n_trades=('pnl', 'size'),
    total_pnl=('pnl', 'sum'),
    mean_return=('return_pct', 'mean'),
    win_rate=('return_pct', lambda x: round((x>0).mean()*100, 1)),
).reset_index()
print(f'  Control yearly by entry year:')
print(ctrl_yearly.to_string(index=False))

# For random yearly, we need equity curves — but we only saved summaries.
# Use trade logs from first 10 seeds for yearly distribution
yearly_rows = []
for seed in range(42, 52):
    fp = os.path.join(OUT, f's2_random_trades_seed{seed}.csv')
    if os.path.exists(fp):
        tr = pd.read_csv(fp)
        tr['entry_date'] = pd.to_datetime(tr['entry_date'])
        tr['entry_year'] = tr['entry_date'].dt.year
        for y, g in tr.groupby('entry_year'):
            yearly_rows.append({'seed': seed, 'year': y, 'n_trades': len(g),
                               'total_pnl': g['pnl'].sum(), 'mean_return': g['return_pct'].mean(),
                               'win_rate': round((g['return_pct']>0).mean()*100, 1)})
yearly_df = pd.DataFrame(yearly_rows)
if len(yearly_df) > 0:
    yearly_summary = yearly_df.groupby('year').agg(
        n_seeds=('seed', 'nunique'),
        mean_trades=('n_trades', 'mean'),
        p25_pnl=('total_pnl', lambda x: round(x.quantile(0.25), 0)),
        median_pnl=('total_pnl', 'median'),
        p75_pnl=('total_pnl', lambda x: round(x.quantile(0.75), 0)),
        mean_wr=('win_rate', 'mean'),
    ).reset_index()
    print(f'\n  Random yearly PnL distribution (first 10 seeds):')
    print(yearly_summary.to_string(index=False))
    yearly_summary.to_csv(os.path.join(OUT, 's2_yearly_random_distribution.csv'), index=False)

# ===== 5. Path dispersion =====
print('\n[5] Path dispersion (random distribution width)...')
dispersion = pd.DataFrame([{
    'metric': 'total_return_pct',
    'random_std': round(rand_df['total_return_pct'].std(), 2),
    'random_p5': round(rand_df['total_return_pct'].quantile(0.05), 2),
    'random_p25': round(rand_df['total_return_pct'].quantile(0.25), 2),
    'random_median': round(rand_df['total_return_pct'].median(), 2),
    'random_p75': round(rand_df['total_return_pct'].quantile(0.75), 2),
    'random_p95': round(rand_df['total_return_pct'].quantile(0.95), 2),
    'control': 82.662,
}, {
    'metric': 'profit_factor',
    'random_std': round(rand_df['profit_factor'].std(), 4),
    'random_p5': round(rand_df['profit_factor'].quantile(0.05), 4),
    'random_p25': round(rand_df['profit_factor'].quantile(0.25), 4),
    'random_median': round(rand_df['profit_factor'].median(), 4),
    'random_p75': round(rand_df['profit_factor'].quantile(0.75), 4),
    'random_p95': round(rand_df['profit_factor'].quantile(0.95), 4),
    'control': 1.3678,
}, {
    'metric': 'sharpe',
    'random_std': round(rand_df['sharpe'].std(), 4),
    'random_p5': round(rand_df['sharpe'].quantile(0.05), 4),
    'random_p25': round(rand_df['sharpe'].quantile(0.25), 4),
    'random_median': round(rand_df['sharpe'].median(), 4),
    'random_p75': round(rand_df['sharpe'].quantile(0.75), 4),
    'random_p95': round(rand_df['sharpe'].quantile(0.95), 4),
    'control': 0.4994,
}])
print(dispersion.to_string(index=False))
dispersion.to_csv(os.path.join(OUT, 's2_path_dispersion.csv'), index=False)

print('\nS2 analysis complete.')
