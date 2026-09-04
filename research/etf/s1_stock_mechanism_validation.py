#!/usr/bin/env python3
"""S1 Stock Signal Mechanism Validation.

Explains what the frozen stock BB Mean Reversion baseline actually earns.
Candidate mechanisms: raw signal, amount ranking, STRICT_C exit, K=3 pyramid,
breadth, dispersion.

NO OPTIMIZATION. Only mechanism diagnostics.
"""
import os, sys
import numpy as np
import pandas as pd

STOCK_ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo'
ETF_WT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/etf_e0_wt'
OUT_STOCK = os.path.join(ETF_WT, 'results', 'stock')
OUT_ETF = os.path.join(ETF_WT, 'results', 'etf')
RAWDIR = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/data/raw/etf'

os.makedirs(OUT_STOCK, exist_ok=True)

BB_WINDOW, BB_STD = 20, 2.0
COMMON_START = '2020-01-01'
COMMON_END = '2024-12-31'
TOP_N = 10
RANDOM_SEED = 42
RANDOM_REPS = 1000

print('='*60)
print('S1 STOCK SIGNAL MECHANISM VALIDATION')
print('='*60)

# ===== 1. LOAD CORRECTED STOCK PANEL =====
print('\n[1] Loading corrected stock panel (E5.1 full-data stocks)...')
feat_etf = pd.read_parquet(os.path.join(RAWDIR, 'etf_feat_long.parquet'))
feat_etf['date'] = pd.to_datetime(feat_etf['date'])
all_trading_dates = sorted(feat_etf['date'].unique())
cal_by_year = {y: [d for d in all_trading_dates if d.year == y] for y in range(2020, 2025)}
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
stock_full['high_adj'] = stock_full['high'] * stock_full['adj_factor']
stock_full = stock_full.sort_values(['ts_code', 'date']).reset_index(drop=True)

# BB features
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

# Forward returns 1-60d
for h in [1,2,3,5,10,20,40,60]:
    stock_eligible[f'fwd_{h}d'] = stock_eligible.groupby('ts_code')['close_adj'].shift(-h) / stock_eligible['close_adj'] - 1

stock_signals = stock_eligible[stock_eligible['signal']].copy()
print(f'  Full-data stocks: {len(full_stocks)}')
print(f'  Eligible rows: {len(stock_eligible)}, signal rows: {len(stock_signals)}')

# ===== 2. LOAD STOCK TRADE LOG (2020-2024) =====
print('\n[2] Loading stock baseline trade log (STRICT_C, 2020-2024)...')
trades = pd.read_csv(os.path.join(STOCK_ROOT, 'results/evidence/strict_c/round5/strict_c_trades.csv'))
trades['entry_date'] = pd.to_datetime(trades['entry_date'])
trades['exit_date'] = pd.to_datetime(trades['exit_date'])
trades_cw = trades[(trades['entry_date'] >= COMMON_START) & (trades['entry_date'] <= COMMON_END)].copy()
print(f'  Total trades: {len(trades)}, 2020-2024: {len(trades_cw)}')
print(f'  Win rate: {(trades_cw["return_pct"]>0).mean()*100:.1f}%')
print(f'  Total PnL: {trades_cw["pnl"].sum():.0f}')
print(f'  Mean return: {trades_cw["return_pct"].mean():.2f}%')
print(f'  Median return: {trades_cw["return_pct"].median():.2f}%')
trades_cw.to_csv(os.path.join(OUT_STOCK, 's1_stock_trades_2020_2024.csv'), index=False)

# ===== 3. RAW SIGNAL EXPECTANCY =====
print('\n[3] Raw signal expectancy (all BB oversold signals, no ranking/portfolio)...')
exp_rows = []
for h in [1,2,3,5,10,20,40,60]:
    col = f'fwd_{h}d'
    valid = stock_signals[col].dropna()
    exp_rows.append({
        'horizon': f'{h}d', 'count': len(valid),
        'mean_pct': round(valid.mean()*100, 3),
        'median_pct': round(valid.median()*100, 3),
        'win_rate_pct': round((valid>0).mean()*100, 1),
        'p10_pct': round(valid.quantile(0.1)*100, 3),
        'p25_pct': round(valid.quantile(0.25)*100, 3),
        'p75_pct': round(valid.quantile(0.75)*100, 3),
        'p90_pct': round(valid.quantile(0.9)*100, 3),
        'std_pct': round(valid.std()*100, 3),
    })
exp_df = pd.DataFrame(exp_rows)
print(exp_df.to_string(index=False))
exp_df.to_csv(os.path.join(OUT_STOCK, 's1_raw_signal_expectancy.csv'), index=False)

# Signal decay curve (cumulative mean)
decay_rows = []
for h in [1,2,3,5,10,20,40,60]:
    col = f'fwd_{h}d'
    valid = stock_signals[col].dropna()
    decay_rows.append({'horizon': h, 'mean_cum_ret_pct': round(valid.mean()*100, 3),
                       'median_cum_ret_pct': round(valid.median()*100, 3)})
decay_df = pd.DataFrame(decay_rows)
decay_df.to_csv(os.path.join(OUT_STOCK, 's1_signal_decay.csv'), index=False)
print(f'\n  Signal decay: 1d={decay_df.iloc[0]["mean_cum_ret_pct"]}%, 5d={decay_df.iloc[3]["mean_cum_ret_pct"]}%, 20d={decay_df.iloc[5]["mean_cum_ret_pct"]}%, 60d={decay_df.iloc[7]["mean_cum_ret_pct"]}%')

# ===== 4. AMOUNT RANKING CONTRIBUTION =====
print('\n[4] Amount ranking contribution (Top-N vs all vs non-selected vs random)...')
# Per-day Top-N (amount) vs all signals vs non-selected
rank_rows = []
for h in [5,10,20,40]:
    col = f'fwd_{h}d'
    all_sig = stock_signals[col].dropna()
    # Top-N amount
    topn_returns = []
    nonselected_returns = []
    for d, g in stock_signals.groupby('date'):
        valid = g[[col, 'amount']].dropna()
        if len(valid) >= TOP_N:
            topn = valid.nlargest(TOP_N, 'amount')[col]
            nonsel = valid.nsmallest(max(0, len(valid)-TOP_N), 'amount')[col]
            topn_returns.extend(topn.tolist())
            nonselected_returns.extend(nonsel.tolist())
    topn_arr = np.array(topn_returns)
    nonsel_arr = np.array(nonselected_returns)
    rank_rows.append({
        'horizon': f'{h}d',
        'all_signals_mean_pct': round(all_sig.mean()*100, 3),
        'all_signals_n': len(all_sig),
        'topn_amount_mean_pct': round(topn_arr.mean()*100, 3),
        'topn_amount_n': len(topn_arr),
        'nonselected_mean_pct': round(nonsel_arr.mean()*100, 3),
        'topn_minus_all_pct': round((topn_arr.mean() - all_sig.mean())*100, 3),
        'topn_minus_nonselected_pct': round((topn_arr.mean() - nonsel_arr.mean())*100, 3),
    })
rank_df = pd.DataFrame(rank_rows)
print(rank_df.to_string(index=False))
rank_df.to_csv(os.path.join(OUT_STOCK, 's1_amount_vs_random.csv'), index=False)

# Random Top-N per-day percentile
rng = np.random.RandomState(RANDOM_SEED)
rand_daily_pct = []
rand_pooled_actual = []
rand_pooled_random = []
for d, g in stock_signals.groupby('date'):
    valid = g[['amount', 'fwd_20d']].dropna()
    if len(valid) < TOP_N:
        continue
    actual = valid.nlargest(TOP_N, 'amount')['fwd_20d'].mean()
    rand_pooled_actual.append(actual)
    rmeans = [valid.sample(n=TOP_N, random_state=rng)['fwd_20d'].mean() for _ in range(RANDOM_REPS)]
    rand_pooled_random.append(np.mean(rmeans))
    rand_daily_pct.append((np.array(rmeans) < actual).mean() * 100)
rand_result = {
    'mean_daily_percentile': round(np.mean(rand_daily_pct), 1),
    'median_daily_percentile': round(np.median(rand_daily_pct), 1),
    'pct_days_above_random_median': round(np.mean(np.array(rand_daily_pct) >= 50)*100, 1),
    'pooled_actual_mean_pct': round(np.mean(rand_pooled_actual)*100, 3),
    'pooled_random_expected_pct': round(np.mean(rand_pooled_random)*100, 3),
    'diff_pct': round((np.mean(rand_pooled_actual)-np.mean(rand_pooled_random))*100, 3),
    'n_days': len(rand_daily_pct),
}
print(f'\n  Random Top-N (20d): daily percentile mean={rand_result["mean_daily_percentile"]}%, '
      f'%days>random median={rand_result["pct_days_above_random_median"]}%')
print(f'  Pooled: actual={rand_result["pooled_actual_mean_pct"]}%, random={rand_result["pooled_random_expected_pct"]}%')
pd.DataFrame([rand_result]).to_csv(os.path.join(OUT_STOCK, 's1_random_topn_summary.csv'), index=False)

# ===== 5. EXIT CAPTURE (MAE/MFE for actual trades) =====
print('\n[5] Exit capture: MAE/MFE, BB mid/upper hit for actual trades...')
# Build price lookup
price_lookup = stock_full.set_index(['ts_code', 'date'])
mae_mfe_rows = []
for _, t in trades_cw.iterrows():
    tc = t['ts_code']
    ed = t['entry_date']
    xd = t['exit_date']
    try:
        entry_price = price_lookup.loc[(tc, ed), 'close_adj']
    except KeyError:
        continue
    # Get price path between entry and exit
    mask = (stock_full['ts_code'] == tc) & (stock_full['date'] >= ed) & (stock_full['date'] <= xd)
    path = stock_full[mask].sort_values('date')
    if len(path) < 2:
        continue
    # MAE/MFE from entry close
    rets = path['close_adj'].values / entry_price - 1
    mae = rets.min()
    mfe = rets.max()
    mae_day = int(np.argmin(rets))
    mfe_day = int(np.argmax(rets))
    # BB mid/upper hit (using high_adj to check intraday touch)
    hit_mid = (path['high_adj'] >= path['ma20']).any() if 'ma20' in path.columns else False
    hit_upper = (path['high_adj'] >= path['bb_upper']).any() if 'bb_upper' in path.columns else False
    days_to_mid = int(np.argmax(path['high_adj'].values >= path['ma20'].values)) if hit_mid else -1
    days_to_upper = int(np.argmax(path['high_adj'].values >= path['bb_upper'].values)) if hit_upper else -1

    mae_mfe_rows.append({
        'ts_code': tc, 'entry_date': str(ed.date()), 'exit_date': str(xd.date()),
        'hold_days': t['hold_days'], 'return_pct': t['return_pct'],
        'mae_pct': round(mae*100, 2), 'mfe_pct': round(mfe*100, 2),
        'mae_day': mae_day, 'mfe_day': mfe_day,
        'hit_mid': hit_mid, 'hit_upper': hit_upper,
        'days_to_mid': days_to_mid, 'days_to_upper': days_to_upper,
        'levels_used': t['levels_used'],
    })

mae_mfe_df = pd.DataFrame(mae_mfe_rows)
print(f'  Trades with MAE/MFE: {len(mae_mfe_df)}')
if len(mae_mfe_df) > 0:
    winners = mae_mfe_df[mae_mfe_df['return_pct'] > 0]
    losers = mae_mfe_df[mae_mfe_df['return_pct'] <= 0]
    print(f'  Winners: {len(winners)}, Losers: {len(losers)}')
    print(f'  All: median MAE={mae_mfe_df["mae_pct"].median():.1f}%, median MFE={mae_mfe_df["mfe_pct"].median():.1f}%')
    print(f'  Winners: median MAE={winners["mae_pct"].median():.1f}%, median MFE={winners["mfe_pct"].median():.1f}%')
    print(f'  Losers: median MAE={losers["mae_pct"].median():.1f}%, median MFE={losers["mfe_pct"].median():.1f}%')
    print(f'  Hit mid: {mae_mfe_df["hit_mid"].mean()*100:.1f}%, Hit upper: {mae_mfe_df["hit_upper"].mean()*100:.1f}%')
    print(f'  MFE>0 but lost: {(losers["mfe_pct"]>0).mean()*100:.1f}% of losers')
    if len(winners) > 0:
        print(f'  Winner median hold: {winners["hold_days"].median():.0f}d, Loser median hold: {losers["hold_days"].median():.0f}d')
mae_mfe_df.to_csv(os.path.join(OUT_STOCK, 's1_exit_capture.csv'), index=False)

# ===== 6. PATH CLASSIFICATION =====
print('\n[6] Path classification (preregistered simple rules)...')
def classify_path(row):
    if row['mae_pct'] < -15 and row['mfe_day'] <= 3:
        return 'CRASH_CONTINUATION'
    if row['mfe_pct'] > 2 and row['return_pct'] <= 0 and row['mfe_day'] < row['hold_days'] * 0.5:
        return 'REBOUND_THEN_RELAPSE'
    if row['hold_days'] > 60 and row['mae_pct'] > -10 and row['mfe_pct'] < 5:
        return 'SLOW_BLEED'
    if row['mfe_pct'] < 1 and row['mae_day'] <= 5:
        return 'IMMEDIATE_FAILURE'
    if row['return_pct'] > 0 and row['hit_upper']:
        return 'CLEAN_MEAN_REVERSION'
    return 'OTHER'

if len(mae_mfe_df) > 0:
    mae_mfe_df['path_class'] = mae_mfe_df.apply(classify_path, axis=1)
    path_counts = mae_mfe_df['path_class'].value_counts()
    print(path_counts.to_string())
    path_summary = mae_mfe_df.groupby('path_class').agg(
        count=('return_pct', 'size'),
        mean_return=('return_pct', 'mean'),
        median_return=('return_pct', 'median'),
        win_rate=('return_pct', lambda x: (x>0).mean()*100),
        mean_hold=('hold_days', 'mean'),
    ).round(2).reset_index()
    path_summary.to_csv(os.path.join(OUT_STOCK, 's1_path_classification.csv'), index=False)

# ===== 7. PROFIT FACTOR DECOMPOSITION =====
print('\n[7] Profit factor decomposition...')
winners_t = trades_cw[trades_cw['return_pct'] > 0]
losers_t = trades_cw[trades_cw['return_pct'] <= 0]
gross_profit = winners_t['pnl'].sum()
gross_loss = abs(losers_t['pnl'].sum())
pf = gross_profit / gross_loss if gross_loss > 0 else np.inf
avg_winner = winners_t['pnl'].mean()
avg_loser = abs(losers_t['pnl'].mean())
payoff = avg_winner / avg_loser if avg_loser > 0 else np.inf
wr = len(winners_t) / len(trades_cw)
breakeven_wr = 1 / (1 + payoff) if payoff > 0 else np.nan
pf_decomp = {
    'total_trades': len(trades_cw),
    'winner_count': len(winners_t),
    'loser_count': len(losers_t),
    'win_rate_pct': round(wr*100, 1),
    'gross_profit': round(gross_profit, 0),
    'gross_loss': round(gross_loss, 0),
    'profit_factor': round(pf, 3),
    'avg_winner_pnl': round(avg_winner, 0),
    'avg_loser_pnl': round(avg_loser, 0),
    'payoff_ratio': round(payoff, 3),
    'breakeven_win_rate_pct': round(breakeven_wr*100, 1),
    'mean_return_pct': round(trades_cw['return_pct'].mean(), 2),
    'median_return_pct': round(trades_cw['return_pct'].median(), 2),
    'expectancy_per_trade': round(trades_cw['pnl'].mean(), 0),
}
print(f'  WR={pf_decomp["win_rate_pct"]}%, PF={pf_decomp["profit_factor"]}, payoff={pf_decomp["payoff_ratio"]}')
print(f'  Breakeven WR={pf_decomp["breakeven_win_rate_pct"]}%, actual WR={pf_decomp["win_rate_pct"]}%')
print(f'  Avg winner={pf_decomp["avg_winner_pnl"]:.0f}, avg loser={pf_decomp["avg_loser_pnl"]:.0f}')
pd.DataFrame([pf_decomp]).to_csv(os.path.join(OUT_STOCK, 's1_profit_factor_decomposition.csv'), index=False)

# ===== 8. K=3 LOT ATTRIBUTION (levels_used proxy) =====
print('\n[8] K=3 lot attribution (by levels_used)...')
lot_attr = trades_cw.groupby('levels_used').agg(
    count=('pnl', 'size'),
    total_pnl=('pnl', 'sum'),
    mean_pnl=('pnl', 'mean'),
    mean_return_pct=('return_pct', 'mean'),
    win_rate=('return_pct', lambda x: (x>0).mean()*100),
    mean_hold_days=('hold_days', 'mean'),
).round(2).reset_index()
print(lot_attr.to_string(index=False))
lot_attr.to_csv(os.path.join(OUT_STOCK, 's1_add_lot_attribution.csv'), index=False)

# ===== 9. BREADTH CONDITIONING =====
print('\n[9] Breadth conditioning (raw signal 20d by signal_ratio bins)...')
stock_daily_elig = stock_eligible.groupby('date').size()
stock_daily_sig = stock_signals.groupby('date').size()
stock_breadth = (stock_daily_sig / stock_daily_elig).rename('signal_ratio')
stock_signals_wb = stock_signals.merge(stock_breadth, left_on='date', right_index=True)

bins = [0, 0.05, 0.10, 0.25, 1.0]
labels = ['0-5%', '5-10%', '10-25%', '25%+']
stock_signals_wb['breadth_bin'] = pd.cut(stock_signals_wb['signal_ratio'], bins=bins, labels=labels)
breadth_analysis = stock_signals_wb.groupby('breadth_bin', observed=True).agg(
    count=('fwd_20d', 'size'),
    mean_20d_pct=('fwd_20d', lambda x: round(x.dropna().mean()*100, 3)),
    median_20d_pct=('fwd_20d', lambda x: round(x.dropna().median()*100, 3)),
    win_rate=('fwd_20d', lambda x: round((x.dropna()>0).mean()*100, 1)),
    fwd20_std=('fwd_20d', lambda x: round(x.dropna().std()*100, 3)),
).reset_index()
print(breadth_analysis.to_string(index=False))
breadth_analysis.to_csv(os.path.join(OUT_STOCK, 's1_breadth_analysis.csv'), index=False)

# ===== 10. DISPERSION CONDITIONING =====
print('\n[10] Dispersion conditioning (signal-day BB_Z std terciles)...')
daily_bbz_std = stock_signals.groupby('date')['bb_z'].std().rename('bbz_std')
stock_signals_wd = stock_signals.merge(daily_bbz_std, left_on='date', right_index=True)
# Terciles
terciles = pd.qcut(stock_signals_wd['bbz_std'], 3, labels=['LOW', 'MID', 'HIGH'])
stock_signals_wd['dispersion_tercile'] = terciles
disp_analysis = stock_signals_wd.groupby('dispersion_tercile', observed=True).agg(
    count=('fwd_20d', 'size'),
    mean_20d_pct=('fwd_20d', lambda x: round(x.dropna().mean()*100, 3)),
    median_20d_pct=('fwd_20d', lambda x: round(x.dropna().median()*100, 3)),
    win_rate=('fwd_20d', lambda x: round((x.dropna()>0).mean()*100, 1)),
).reset_index()
print(disp_analysis.to_string(index=False))
disp_analysis.to_csv(os.path.join(OUT_STOCK, 's1_dispersion_analysis.csv'), index=False)

# ===== 11. STOCK vs ETF MECHANISM TABLE =====
print('\n[11] Stock vs ETF mechanism comparison table...')
# ETF reference values (from E3/E4/E5 frozen results)
etf_ref = {
    'raw_signal_20d_mean_pct': 1.618,
    'raw_signal_20d_median_pct': 0.280,
    'raw_signal_20d_win_rate': 51.5,
    'signal_20d_std_pct': 8.928,
    'median_breadth_pct': 6.05,
    'bbz_signal_std': 0.171,
    'fwd20_dispersion_std': 0.045,
    'amount_topn_20d_pct': 0.695,
    'amount_random_20d_pct': 1.163,
    'amount_daily_percentile': 42.8,
    'pf_m2_lowbreadth': 0.937,
    'win_rate_m2_lowbreadth': 68.1,
    'payoff_m2': 0.39,
    'mid_hit_rate': 100.0,
    'upper_hit_rate': 60.0,
    'mfe_positive_but_lost': 95.0,
    'winner_median_hold': 37,
    'loser_median_hold': 341,
}

stock_mech = {
    'raw_signal_20d_mean_pct': round(stock_signals['fwd_20d'].dropna().mean()*100, 3),
    'raw_signal_20d_median_pct': round(stock_signals['fwd_20d'].dropna().median()*100, 3),
    'raw_signal_20d_win_rate': round((stock_signals['fwd_20d'].dropna()>0).mean()*100, 1),
    'signal_20d_std_pct': round(stock_signals['fwd_20d'].dropna().std()*100, 3),
    'median_breadth_pct': round(stock_breadth.median()*100, 2),
    'bbz_signal_std': round(daily_bbz_std.mean(), 4),
    'fwd20_dispersion_std': round(stock_signals.groupby('date')['fwd_20d'].std().mean(), 4),
    'amount_topn_20d_pct': rand_result['pooled_actual_mean_pct'],
    'amount_random_20d_pct': rand_result['pooled_random_expected_pct'],
    'amount_daily_percentile': rand_result['mean_daily_percentile'],
    'pf_baseline': pf_decomp['profit_factor'],
    'win_rate_baseline': pf_decomp['win_rate_pct'],
    'payoff_ratio': pf_decomp['payoff_ratio'],
}
if len(mae_mfe_df) > 0:
    stock_mech['mid_hit_rate'] = round(mae_mfe_df['hit_mid'].mean()*100, 1)
    stock_mech['upper_hit_rate'] = round(mae_mfe_df['hit_upper'].mean()*100, 1)
    stock_mech['mfe_positive_but_lost'] = round((mae_mfe_df[mae_mfe_df['return_pct']<=0]['mfe_pct']>0).mean()*100, 1) if len(mae_mfe_df[mae_mfe_df['return_pct']<=0])>0 else np.nan
    w = mae_mfe_df[mae_mfe_df['return_pct']>0]
    l = mae_mfe_df[mae_mfe_df['return_pct']<=0]
    stock_mech['winner_median_hold'] = float(w['hold_days'].median()) if len(w)>0 else np.nan
    stock_mech['loser_median_hold'] = float(l['hold_days'].median()) if len(l)>0 else np.nan

mech_table = pd.DataFrame([
    {'mechanism': k, 'stock': v, 'etf': etf_ref.get(k, 'N/A')}
    for k, v in stock_mech.items()
])
print(mech_table.to_string(index=False))
mech_table.to_csv(os.path.join(OUT_STOCK, 's1_stock_vs_etf_mechanism_table.csv'), index=False)

# ===== 12. VERDICT =====
print('\n' + '='*60)
print('S1 MECHANISM VERDICT ASSESSMENT')
print('='*60)

# Assess each mechanism
raw_signal_positive = stock_signals['fwd_20d'].dropna().mean() > 0
amount_harmful = rand_result['mean_daily_percentile'] < 50
exit_captures = stock_mech.get('upper_hit_rate', 0) > 50 if not np.isnan(stock_mech.get('upper_hit_rate', 0)) else False
pyramid_contributes = lot_attr[lot_attr['levels_used']>=2]['mean_return_pct'].mean() > lot_attr[lot_attr['levels_used']==1]['mean_return_pct'].mean() if len(lot_attr)>1 else False

print(f'  Raw signal 20d mean: {stock_mech["raw_signal_20d_mean_pct"]}% (positive={raw_signal_positive})')
print(f'  Amount ranking daily percentile: {rand_result["mean_daily_percentile"]}% (harmful={amount_harmful})')
print(f'  Upper band hit rate: {stock_mech.get("upper_hit_rate", "N/A")}%')
print(f'  PF={pf_decomp["profit_factor"]}, WR={pf_decomp["win_rate_pct"]}%, payoff={pf_decomp["payoff_ratio"]}')
print(f'  Breakeven WR={pf_decomp["breakeven_win_rate_pct"]}% (actual exceeds by {pf_decomp["win_rate_pct"]-pf_decomp["breakeven_win_rate_pct"]:.1f}pp)')

# Primary mechanism determination
mechanisms = []
if raw_signal_positive:
    mechanisms.append(('SIGNAL-DOMINATED EDGE', 3))
if exit_captures:
    mechanisms.append(('EXIT-CAPTURE DOMINATED EDGE', 2))
if amount_harmful:
    mechanisms.append(('SELECTION NOT CONTRIBUTING (amount harmful)', -1))
if pyramid_contributes:
    mechanisms.append(('PYRAMID-CONTRIBUTION MATERIAL', 1))

primary = 'MULTI-COMPONENT EDGE' if len([m for m,s in mechanisms if s>0]) >= 2 else (mechanisms[0][0] if mechanisms else 'EDGE MECHANISM INCONCLUSIVE')

print(f'\n  PRIMARY MECHANISM: {primary}')
print(f'  Mechanisms: {[m[0] for m in mechanisms]}')

pd.DataFrame([{'primary_mechanism': primary,
                'raw_signal_positive': raw_signal_positive,
                'amount_ranking_harmful': amount_harmful,
                'exit_upper_hit_rate': stock_mech.get('upper_hit_rate', np.nan),
                'pf': pf_decomp['profit_factor'],
                'win_rate': pf_decomp['win_rate_pct'],
                'payoff_ratio': pf_decomp['payoff_ratio'],
                'breakeven_wr': pf_decomp['breakeven_win_rate_pct'],
                'expectancy_per_trade': pf_decomp['expectancy_per_trade']}]).to_csv(
    os.path.join(OUT_STOCK, 's1_verdict.csv'), index=False)

print('\nS1 complete.')
