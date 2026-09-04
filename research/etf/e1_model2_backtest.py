#!/usr/bin/env python3
"""E1 Model 2: INDEX SIGNAL + PIT ETF EXECUTION (Baseline Falsification)

Signal source: CSI index close → BB(20,2) → index-level oversold signal
Execution: PIT representative ETF (B2 ADV60 t-1) at next-day open
Exit: STRICT_C dynamic_touch on the actual held ETF (same as Model 1)

Key difference from Model 1: signal uses INDEX price (longer history),
execution uses ETF. Actual strategy returns only start when a tradable
representative ETF exists.

All other parameters identical to Model 1 / stock A0 baseline (apples-to-apples).

Outputs:
  results/etf/e1_model2_trade_log.csv
  results/etf/e1_model2_equity_curve.csv
  results/etf/e1_model2_yearly_returns.csv
  results/etf/e1_model2_summary.csv
  results/etf/e1_model2_daily_panel.csv
"""
import os, sys
import numpy as np
import pandas as pd

DATA_ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
WT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/etf_e0_wt'
OUT = os.path.join(WT, 'results', 'etf')
RAWDIR = os.path.join(DATA_ROOT, 'data', 'raw', 'etf')
IDXDIR = os.path.join(RAWDIR, 'index_daily')

sys.path.insert(0, DATA_ROOT)
from run_strict_c_math import analytic_Pstar

# ===== FROZEN PARAMETERS (identical to Model 1 / stock A0) =====
BB_WINDOW, BB_STD = 20, 2.0
K, MAX_LEVELS, LEVEL_CASH, INITIAL = 3, 5, 200_000, 1_000_000
SLIP = 10 / 10000.0
COMM = 0.00025
MIN_COMM = 5.0
TOP_N = 10
LIQUIDITY_FILTER_ADV60 = 20_000  # 千元 = 2000万元
TICK = 0.001
LOT = 100

def round_tick(px):
    return round(px / TICK) * TICK

def commission(amt):
    return max(amt * COMM, MIN_COMM)

# ===== STEP 1: Load index daily data and compute BB signals =====
print('loading index daily data...')
master = pd.read_parquet(os.path.join(RAWDIR, 'master_mapping_full.parquet'))

# Build index_code -> exchange code mapping for loading index_daily
idx_codes = master['index_code'].dropna().unique()
ib = pd.read_parquet(os.path.join(RAWDIR, 'index_basic_exchange.parquet'))
valid_codes = set(ib['ts_code'].tolist())

index_data = {}  # exchange_code -> DataFrame
index_to_exchange = {}  # index_code (.CSI) -> exchange_code (.SH/.SZ)
for c in idx_codes:
    if c.endswith('.CSI'):
        num = c.replace('.CSI', '')
        for s in ['.SH', '.SZ']:
            ex = num + s
            if ex in valid_codes and os.path.exists(os.path.join(IDXDIR, ex.replace('.', '_') + '.parquet')):
                index_to_exchange[c] = ex
                break
    elif os.path.exists(os.path.join(IDXDIR, c.replace('.', '_') + '.parquet')):
        index_to_exchange[c] = c

print(f'indexes with daily data: {len(index_to_exchange)}')

# Compute BB on each index
index_signals = {}  # index_code -> DataFrame with date, close, bb_lower, signal
for idx_code, ex_code in index_to_exchange.items():
    p = os.path.join(IDXDIR, ex_code.replace('.', '_') + '.parquet')
    df = pd.read_parquet(p)
    if len(df) < BB_WINDOW + 1:
        continue
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.sort_values('trade_date').reset_index(drop=True)
    close = pd.to_numeric(df['close'], errors='coerce')
    ma = close.rolling(BB_WINDOW, min_periods=BB_WINDOW).mean()
    sd = close.rolling(BB_WINDOW, min_periods=BB_WINDOW).std()
    bb_lower = ma - BB_STD * sd
    sig = (close < bb_lower) & bb_lower.notna()
    index_signals[idx_code] = pd.DataFrame({
        'date': df['trade_date'], 'index_close': close.values,
        'index_bb_lower': bb_lower.values, 'index_signal': sig.values
    })

print(f'indexes with BB signals: {len(index_signals)}')

# ===== STEP 2: Load ETF PIT representative panel (for execution) =====
print('loading ETF feature data for execution...')
feat = pd.read_parquet(os.path.join(RAWDIR, 'etf_feat_long.parquet'))
feat['date'] = pd.to_datetime(feat['date'])
feat = feat[feat['date'] <= '2026-09-03'].copy()
feat['listed'] = (feat['list_date'] <= feat['date']) & (feat['delist'].isna() | (feat['delist'] > feat['date']))
avail = feat[feat['listed']].copy()
avail['n_days'] = avail.groupby('etf')['date'].cumcount() + 1
avail = avail[avail['n_days'] >= 60].copy()
avail = avail[avail['adv60'] >= LIQUIDITY_FILTER_ADV60].copy()
avail = avail.sort_values('adv60', ascending=False)
rep = avail.drop_duplicates(subset=['index_key', 'date']).copy()
print(f'PIT reps: {len(rep)}, unique indexes: {rep["index_key"].nunique()}')

# Build index_code -> index_key mapping from master
master['index_key'] = master.apply(
    lambda r: (r['index_code'] if pd.notna(r['index_code']) and str(r['index_code']) != 'nan'
               else r['bench_idx_name']), axis=1)
idx_to_key = dict(zip(master['index_code'], master['index_key']))

# ===== STEP 3: Merge index signals with ETF execution panel =====
print('merging index signals with ETF execution panel...')
# For each day, collect index signals, map to index_key, get PIT representative ETF
sig_rows = []
for idx_code, sig_df in index_signals.items():
    idx_key = idx_to_key.get(idx_code)
    if idx_key is None:
        continue
    sig_days = sig_df[sig_df['index_signal']].copy()
    sig_days['index_code'] = idx_code
    sig_days['index_key'] = idx_key
    sig_rows.append(sig_days[['date', 'index_code', 'index_key', 'index_close', 'index_bb_lower']])

all_index_signals = pd.concat(sig_rows, ignore_index=True) if sig_rows else pd.DataFrame()
print(f'index signal days: {len(all_index_signals)}, unique indexes: {all_index_signals["index_key"].nunique() if len(all_index_signals) else 0}')

# Build execution panel: for each day, all PIT reps, with index_signal flag
rep['index_signal'] = False
# Mark signals by matching (date, index_key)
sig_keys = set(zip(all_index_signals['date'], all_index_signals['index_key'])) if len(all_index_signals) else set()
rep['index_signal'] = rep.apply(lambda r: (r['date'], r['index_key']) in sig_keys, axis=1)
print(f'rep rows with index signal: {rep["index_signal"].sum()}')

# Price limit (same as Model 1)
def limit_pct(rule):
    if pd.isna(rule) or rule == '10PCT':
        return 0.10
    return 0.20
rep['limit_pct'] = rep['price_limit_pit'].apply(limit_pct).astype(float)
rep = rep.sort_values(['etf', 'date'])
rep['pre_close'] = rep.groupby('etf')['close'].shift(1).astype(float)
rep['limit_up'] = rep['pre_close'] * (1 + rep['limit_pct'])
rep['limit_down'] = rep['pre_close'] * (1 - rep['limit_pct'])
rep['is_limit_up_open'] = rep['open'] >= rep['limit_up'] * 0.999
rep['is_limit_down_day'] = rep['high'] <= rep['limit_down'] * 1.001

# Build day-indexed panel, ranked by amount for Top-N
panel = rep.sort_values(['date', 'amount'], ascending=[True, False]).copy()
days = sorted(panel['date'].unique())
D = {d: g for d, g in panel.groupby('date')}
print(f'trading days: {len(days)}, range: {days[0].date()} -> {days[-1].date()}')

# ===== STEP 4: Portfolio simulation (same engine as Model 1) =====
positions = []
cash = INITIAL
trade_log = []
equity_curve = []
daily_panel = []
pending_buy = []
pending_add = {}

def find_pos(index_key, etf):
    return next((p for p in positions if p['index_key'] == index_key and p['etf'] == etf), None)

for i, d in enumerate(days):
    g = D[d]
    n_entries, n_exits = 0, 0

    # Open: pending buys
    if pending_buy:
        for pb in list(pending_buy):
            idx_key, etf_code = pb
            if len(positions) >= K:
                pending_buy = [x for x in pending_buy if x != pb]
                continue
            row = g[g['etf'] == etf_code]
            if len(row) == 0:
                continue
            r = row.iloc[0]
            opx = r['open']
            if pd.isna(opx) or opx <= 0 or r['amount'] <= 0:
                pending_buy = [x for x in pending_buy if x != pb]
                continue
            if r['is_limit_up_open']:
                continue
            price = round_tick(opx * (1 + SLIP))
            qty = int(min(LEVEL_CASH, cash) / price / LOT) * LOT
            if qty < LOT:
                pending_buy = [x for x in pending_buy if x != pb]
                continue
            amt = price * qty
            fee = commission(amt)
            if amt + fee > cash:
                pending_buy = [x for x in pending_buy if x != pb]
                continue
            cash -= amt + fee
            positions.append({'index_key': idx_key, 'etf': etf_code, 'shares': qty,
                              'avg_cost': (amt + fee) / qty, 'levels': 1,
                              'total_cost': amt + fee, 'entry_day': d, 'last_add': d})
            trade_log.append({'date': d, 'action': 'ENTRY', 'index_key': idx_key, 'etf': etf_code,
                              'shares': qty, 'price': price, 'amount': amt, 'fee': fee,
                              'cash_after': cash, 'level': 1, 'signal_source': 'INDEX'})
            n_entries += 1
            pending_buy = [x for x in pending_buy if x != pb]

    # Open: pending adds
    if pending_add:
        for key in list(pending_add.keys()):
            idx_key, etf_code = key
            pos = find_pos(idx_key, etf_code)
            if pos is None or pos['levels'] >= MAX_LEVELS:
                pending_add.pop(key, None)
                continue
            row = g[g['etf'] == etf_code]
            if len(row) == 0:
                pending_add.pop(key, None)
                continue
            r = row.iloc[0]
            opx = r['open']
            if pd.isna(opx) or opx <= 0 or r['amount'] <= 0:
                pending_add.pop(key, None)
                continue
            if r['is_limit_up_open']:
                continue
            price = round_tick(opx * (1 + SLIP))
            qty = int(min(LEVEL_CASH, cash) / price / LOT) * LOT
            if qty >= LOT:
                amt = price * qty
                fee = commission(amt)
                if amt + fee <= cash:
                    cash -= amt + fee
                    old = pos['shares'] * pos['avg_cost']
                    pos['shares'] += qty
                    pos['avg_cost'] = (old + amt + fee) / pos['shares']
                    pos['total_cost'] += amt + fee
                    pos['levels'] += 1
                    pos['last_add'] = d
                    trade_log.append({'date': d, 'action': 'ADD', 'index_key': idx_key, 'etf': etf_code,
                                      'shares': qty, 'price': price, 'amount': amt, 'fee': fee,
                                      'cash_after': cash, 'level': pos['levels'], 'signal_source': 'INDEX'})
                    n_entries += 1
            pending_add.pop(key, None)

    # Intraday: STRICT_C exit (on actual held ETF)
    for pos in list(positions):
        row = g[g['etf'] == pos['etf']]
        if len(row) == 0:
            continue
        r = row.iloc[0]
        if r['is_limit_down_day']:
            continue
        if pd.notna(r['pstar']) and pd.notna(r['high_adj']) and r['high_adj'] >= r['pstar']:
            px = round_tick((r['pstar'] / r['adj']) * (1 - SLIP))
            amt = px * pos['shares']
            fee = commission(amt)
            cash += amt - fee
            pnl = (px - pos['avg_cost']) * pos['shares'] - fee
            trade_log.append({'date': d, 'action': 'EXIT_PSTAR', 'index_key': pos['index_key'],
                              'etf': pos['etf'], 'shares': pos['shares'], 'price': px,
                              'amount': amt, 'fee': fee, 'cash_after': cash,
                              'pnl': pnl, 'holding_days': (d - pos['entry_day']).days,
                              'level': pos['levels'], 'signal_source': 'INDEX'})
            positions.remove(pos)
            n_exits += 1

    # Close: new INDEX signals -> pending buy/add
    sig_rows_today = g[g['index_signal'] & (g['amount'] > 0)].head(TOP_N)
    for _, r in sig_rows_today.iterrows():
        idx_key = r['index_key']
        etf_code = r['etf']
        held = {(p['index_key'], p['etf']) for p in positions}
        if (idx_key, etf_code) in held:
            pos = find_pos(idx_key, etf_code)
            if (pos and pos['levels'] < MAX_LEVELS
                    and r['amount'] > 0 and (d - pos['last_add']).days >= 1):
                # For Model 2, add condition: index still in BB lower? Use index_signal flag
                pending_add[(idx_key, etf_code)] = True
        elif len(positions) + len(pending_buy) < K:
            if (idx_key, etf_code) not in pending_buy:
                pending_buy.append((idx_key, etf_code))

    # Valuation
    stock_val = 0.0
    for pos in positions:
        row = g[g['etf'] == pos['etf']]
        px = row.iloc[0]['close'] if len(row) else pos['avg_cost']
        stock_val += pos['shares'] * px
    equity = cash + stock_val
    invested_pct = (equity - cash) / equity if equity > 0 else 0
    equity_curve.append({'date': d, 'equity': equity, 'cash': cash,
                         'invested': equity - cash, 'invested_pct': invested_pct})
    day_sig = g[g['index_signal']]
    daily_panel.append({'date': d, 'eligible_count': len(g),
                        'n_index_signal': len(day_sig), 'open_positions': len(positions),
                        'n_entries': n_entries, 'n_exits': n_exits,
                        'invested_pct': invested_pct})

# Final liquidation
last_d = days[-1]
g = D[last_d]
for pos in list(positions):
    row = g[g['etf'] == pos['etf']]
    px = round_tick(row.iloc[0]['close'] * (1 - SLIP)) if len(row) else pos['avg_cost']
    amt = px * pos['shares']
    fee = commission(amt)
    cash += amt - fee
    pnl = (px - pos['avg_cost']) * pos['shares'] - fee
    trade_log.append({'date': last_d, 'action': 'EXIT_FINAL', 'index_key': pos['index_key'],
                      'etf': pos['etf'], 'shares': pos['shares'], 'price': px,
                      'amount': amt, 'fee': fee, 'cash_after': cash, 'pnl': pnl,
                      'holding_days': (last_d - pos['entry_day']).days,
                      'level': pos['levels'], 'signal_source': 'INDEX'})

# ===== SAVE + METRICS =====
tl = pd.DataFrame(trade_log)
tl.to_csv(os.path.join(OUT, 'e1_model2_trade_log.csv'), index=False)
eq = pd.DataFrame(equity_curve)
eq.to_csv(os.path.join(OUT, 'e1_model2_equity_curve.csv'), index=False)
dp = pd.DataFrame(daily_panel)
dp.to_csv(os.path.join(OUT, 'e1_model2_daily_panel.csv'), index=False)

print(f'\n===== E1 Model 2 Summary =====')
print(f'Period: {days[0].date()} -> {days[-1].date()} ({len(days)} days)')
print(f'Trades: {len(tl)} (ENTRY {(tl["action"]=="ENTRY").sum()}, ADD {(tl["action"]=="ADD").sum()}, '
      f'EXIT_PSTAR {(tl["action"]=="EXIT_PSTAR").sum()}, EXIT_FINAL {(tl["action"]=="EXIT_FINAL").sum()})')

final_equity = cash
total_return = (final_equity / INITIAL - 1) * 100
n_years = (days[-1] - days[0]).days / 365.25
cagr = ((final_equity / INITIAL) ** (1 / n_years) - 1) * 100 if n_years > 0 else 0
eq['daily_ret'] = eq['equity'].pct_change()
ann_vol = eq['daily_ret'].std() * np.sqrt(252) * 100
sharpe = (eq['daily_ret'].mean() * 252) / (eq['daily_ret'].std() * np.sqrt(252)) if eq['daily_ret'].std() > 0 else 0
cummax = eq['equity'].cummax()
maxdd = ((eq['equity'] / cummax - 1) * 100).min()

completed = tl[tl['action'].isin(['EXIT_PSTAR', 'EXIT_FINAL'])]
win_rate = (completed['pnl'] > 0).mean() * 100 if len(completed) > 0 else 0
avg_trade = completed['pnl'].mean() if len(completed) > 0 else 0
median_trade = completed['pnl'].median() if len(completed) > 0 else 0
avg_holding = completed['holding_days'].mean() if len(completed) > 0 else 0
gross_profit = completed[completed['pnl'] > 0]['pnl'].sum()
gross_loss = abs(completed[completed['pnl'] < 0]['pnl'].sum())
pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')

summary = pd.DataFrame([
    {'metric': 'period_start', 'value': str(days[0].date())},
    {'metric': 'period_end', 'value': str(days[-1].date())},
    {'metric': 'n_trading_days', 'value': len(days)},
    {'metric': 'n_years', 'value': round(n_years, 2)},
    {'metric': 'signal_source', 'value': 'INDEX_CLOSE_BB20_2'},
    {'metric': 'execution', 'value': 'PIT_REPRESENTATIVE_ETF'},
    {'metric': 'initial_cash', 'value': INITIAL},
    {'metric': 'final_equity', 'value': round(final_equity, 2)},
    {'metric': 'total_return_pct', 'value': round(total_return, 2)},
    {'metric': 'CAGR_pct', 'value': round(cagr, 2)},
    {'metric': 'annualized_vol_pct', 'value': round(ann_vol, 2)},
    {'metric': 'Sharpe', 'value': round(sharpe, 4)},
    {'metric': 'MaxDD_pct', 'value': round(maxdd, 2)},
    {'metric': 'total_trades', 'value': len(tl)},
    {'metric': 'completed_trades', 'value': len(completed)},
    {'metric': 'win_rate_pct', 'value': round(win_rate, 2)},
    {'metric': 'avg_trade_pnl', 'value': round(avg_trade, 2)},
    {'metric': 'median_trade_pnl', 'value': round(median_trade, 2)},
    {'metric': 'profit_factor', 'value': round(pf, 4)},
    {'metric': 'avg_holding_days', 'value': round(avg_holding, 1)},
    {'metric': 'avg_exposure_pct', 'value': round(eq['invested_pct'].mean() * 100, 2)},
    {'metric': 'signals_per_day', 'value': round(dp['n_index_signal'].mean(), 2)},
    {'metric': 'avg_open_positions', 'value': round(dp['open_positions'].mean(), 2)},
])
summary.to_csv(os.path.join(OUT, 'e1_model2_summary.csv'), index=False)
print(summary.to_string(index=False))

# Yearly returns
eq['year'] = eq['date'].dt.year
yearly = eq.groupby('year').agg(start_equity=('equity', 'first'), end_equity=('equity', 'last')).reset_index()
yearly['return_pct'] = (yearly['end_equity'] / yearly['start_equity'] - 1) * 100
yearly.to_csv(os.path.join(OUT, 'e1_model2_yearly_returns.csv'), index=False)
print(f'\n=== Yearly Returns ===')
print(yearly[['year', 'return_pct']].to_string(index=False))

print(f'\nDONE E1 Model 2. final_equity={final_equity:.2f}, total_return={total_return:.2f}%')
