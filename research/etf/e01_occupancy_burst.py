#!/usr/bin/env python3
"""E0.1-B/C/D: Audit -56.6% diagnostic, signal-vs-position occupancy, signal burst.

Re-runs the same portfolio simulation as e0_signal_capacity.py but with full
trade logging (entry/exit/position), then generates:
  - e01_daily_occupancy.csv (daily panel: signals, positions, entries, exits, invested%)
  - e01_signal_burst_dates.csv (Top 20 signal-burst dates)
  - e01_trade_log.csv (every entry/exit for audit)

Also documents exactly what the -56.6% diagnostic implements vs. what E1 baseline requires.
"""
import os
import numpy as np
import pandas as pd

DATA_ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
WT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/etf_e0_wt'
OUT = os.path.join(WT, 'results', 'etf')
RAWDIR = os.path.join(DATA_ROOT, 'data', 'raw', 'etf')

import sys
sys.path.insert(0, DATA_ROOT)
from run_strict_c_math import analytic_Pstar

BB_WINDOW, BB_STD = 20, 2.0
K, MAX_LEVELS, LEVEL_CASH, INITIAL = 3, 5, 200_000, 1_000_000
SLIP = 10 / 10000.0
COMM = 0.00025
MIN_COMM = 5.0

print('loading etf_feat_long.parquet...')
feat = pd.read_parquet(os.path.join(RAWDIR, 'etf_feat_long.parquet'))
feat['date'] = pd.to_datetime(feat['date'])
feat = feat[feat['date'] <= '2026-09-03'].copy()
feat['listed'] = (feat['list_date'] <= feat['date']) & (feat['delist'].isna() | (feat['delist'] > feat['date']))
avail = feat[feat['listed']].copy()
avail['n_days'] = avail.groupby('etf')['date'].cumcount() + 1
avail = avail[avail['n_days'] >= 60].copy()
avail = avail.sort_values('adv60', ascending=False)
rep = avail.drop_duplicates(subset=['index_key', 'date']).copy()
rep['signal'] = (rep['close_adj'] < rep['bb_lower']) & (rep['amount'].fillna(0) > 0) & rep['bb_lower'].notna()
print(f'PIT reps: {len(rep)}, unique indexes: {rep["index_key"].nunique()}')

# Daily signal stats
daily_sig = rep.groupby('date').agg(
    eligible_count=('etf', 'count'),
    n_signal=('signal', 'sum'),
    n_amount_pos=('amount', lambda x: (x.fillna(0) > 0).sum()),
).reset_index()
daily_sig['signal_ratio'] = daily_sig['n_signal'] / daily_sig['eligible_count']

# Portfolio simulation with trade logging
panel = rep.sort_values(['date', 'amount'], ascending=[True, False]).copy()
days = sorted(panel['date'].unique())
D = {d: g for d, g in panel.groupby('date')}

positions = []
cash = INITIAL
trade_log = []
daily_positions = []

def commission(amt):
    return max(amt * COMM, MIN_COMM)

def find_pos(idx):
    return next((p for p in positions if p['index_key'] == idx), None)

pending_buy = []
pending_add = {}

for i, d in enumerate(days):
    g = D[d]
    n_entries = 0
    n_exits = 0

    # Open: execute pending buys
    if pending_buy:
        for pb in list(pending_buy):
            if len(positions) >= K:
                continue
            row = g[g['index_key'] == pb]
            if len(row) == 0:
                pending_buy = [x for x in pending_buy if x != pb]
                continue
            r = row.iloc[0]
            opx = r['open']
            if pd.isna(opx) or opx <= 0:
                pending_buy = [x for x in pending_buy if x != pb]
                continue
            price = opx * (1 + SLIP)
            qty = int(min(LEVEL_CASH, cash) / price / 100) * 100
            if qty < 100:
                pending_buy = [x for x in pending_buy if x != pb]
                continue
            amt = price * qty
            fee = commission(amt)
            if amt + fee > cash:
                pending_buy = [x for x in pending_buy if x != pb]
                continue
            cash -= amt + fee
            positions.append({'index_key': pb, 'etf': r['etf'], 'shares': qty,
                              'avg_cost': (amt + fee) / qty, 'levels': 1,
                              'total_cost': amt + fee, 'entry_day': d, 'last_add': d})
            trade_log.append({'date': d, 'action': 'ENTRY', 'index_key': pb, 'etf': r['etf'],
                              'shares': qty, 'price': price, 'amount': amt, 'fee': fee,
                              'cash_after': cash, 'level': 1})
            n_entries += 1
            pending_buy = [x for x in pending_buy if x != pb]

    # Open: execute pending adds
    if pending_add:
        for idx in list(pending_add.keys()):
            pos = find_pos(idx)
            if pos is None or pos['levels'] >= MAX_LEVELS:
                pending_add.pop(idx, None)
                continue
            row = g[g['index_key'] == idx]
            if len(row) == 0:
                pending_add.pop(idx, None)
                continue
            r = row.iloc[0]
            opx = r['open']
            if pd.isna(opx) or opx <= 0:
                pending_add.pop(idx, None)
                continue
            price = opx * (1 + SLIP)
            qty = int(min(LEVEL_CASH, cash) / price / 100) * 100
            if qty >= 100:
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
                    trade_log.append({'date': d, 'action': 'ADD', 'index_key': idx, 'etf': r['etf'],
                                      'shares': qty, 'price': price, 'amount': amt, 'fee': fee,
                                      'cash_after': cash, 'level': pos['levels']})
                    n_entries += 1
            pending_add.pop(idx, None)

    # Intraday: dynamic touch exit
    for pos in list(positions):
        row = g[g['index_key'] == pos['index_key']]
        if len(row) == 0:
            continue
        r = row.iloc[0]
        if pd.notna(r['pstar']) and pd.notna(r['high_adj']) and r['high_adj'] >= r['pstar']:
            px = (r['pstar'] / r['adj']) * (1 - SLIP)
            amt = px * pos['shares']
            fee = commission(amt)
            cash += amt - fee
            pnl = (px - pos['avg_cost']) * pos['shares'] - fee
            trade_log.append({'date': d, 'action': 'EXIT_PSTAR', 'index_key': pos['index_key'],
                              'etf': pos['etf'], 'shares': pos['shares'], 'price': px,
                              'amount': amt, 'fee': fee, 'cash_after': cash,
                              'pnl': pnl, 'holding_days': (d - pos['entry_day']).days,
                              'level': pos['levels']})
            positions.remove(pos)
            n_exits += 1

    # Close: new signals -> pending buy/add
    for _, r in g.iterrows():
        held = {p['index_key'] for p in positions}
        if r['index_key'] in held:
            pos = find_pos(r['index_key'])
            if (pos and pos['levels'] < MAX_LEVELS and pd.notna(r['bb_lower'])
                    and r['close_adj'] < r['bb_lower'] and r['amount'] > 0
                    and (d - pos['last_add']).days >= 1):
                pending_add[r['index_key']] = True
        elif r['signal'] and len(positions) + len(pending_buy) < K:
            if r['index_key'] not in pending_buy:
                pending_buy.append(r['index_key'])

    # Valuation
    stock_val = 0.0
    for pos in positions:
        row = g[g['index_key'] == pos['index_key']]
        px = row.iloc[0]['close'] if len(row) else pos['avg_cost']
        stock_val += pos['shares'] * px
    equity = cash + stock_val
    invested_pct = (equity - cash) / equity if equity > 0 else 0
    daily_positions.append({'date': d, 'open_positions': len(positions),
                            'cash': cash, 'equity': equity,
                            'invested_pct': invested_pct,
                            'n_entries': n_entries, 'n_exits': n_exits})

# Final liquidation
last_d = days[-1]
g = D[last_d]
for pos in list(positions):
    row = g[g['index_key'] == pos['index_key']]
    px = row.iloc[0]['close'] * (1 - SLIP) if len(row) else pos['avg_cost']
    amt = px * pos['shares']
    fee = commission(amt)
    cash += amt - fee
    pnl = (px - pos['avg_cost']) * pos['shares'] - fee
    trade_log.append({'date': last_d, 'action': 'EXIT_FINAL', 'index_key': pos['index_key'],
                      'etf': pos['etf'], 'shares': pos['shares'], 'price': px,
                      'amount': amt, 'fee': fee, 'cash_after': cash, 'pnl': pnl,
                      'holding_days': (last_d - pos['entry_day']).days, 'level': pos['levels']})

# Save trade log
tl = pd.DataFrame(trade_log)
tl.to_csv(os.path.join(OUT, 'e01_trade_log.csv'), index=False)
print(f'\ntrade log: {len(tl)} trades')
print(f'  ENTRY: {(tl["action"]=="ENTRY").sum()}, ADD: {(tl["action"]=="ADD").sum()}')
print(f'  EXIT_PSTAR: {(tl["action"]=="EXIT_PSTAR").sum()}, EXIT_FINAL: {(tl["action"]=="EXIT_FINAL").sum()}')

# Daily occupancy panel
dp = pd.DataFrame(daily_positions)
occ = dp.merge(daily_sig, on='date', how='left')
occ['cash_pct'] = 1 - occ['invested_pct']
occ.to_csv(os.path.join(OUT, 'e01_daily_occupancy.csv'), index=False)
print(f'\ndaily occupancy: {len(occ)} days')
print(f'  mean open positions: {occ["open_positions"].mean():.2f}')
print(f'  mean n_signal: {occ["n_signal"].mean():.2f}')
print(f'  zero-signal days: {(occ["n_signal"]==0).sum()} ({(occ["n_signal"]==0).mean()*100:.1f}%)')
print(f'  fully-invested days (>=99%): {(occ["invested_pct"]>=0.99).sum()} ({(occ["invested_pct"]>=0.99).mean()*100:.1f}%)')
print(f'  zero-signal AND fully-invested: {((occ["n_signal"]==0)&(occ["invested_pct"]>=0.99)).sum()} days')

# Signal burst top 20
burst = occ.nlargest(20, 'n_signal')[['date', 'n_signal', 'eligible_count', 'signal_ratio',
                                          'open_positions', 'n_entries', 'n_exits', 'invested_pct']].copy()
burst['date'] = burst['date'].dt.strftime('%Y-%m-%d')
burst.to_csv(os.path.join(OUT, 'e01_signal_burst_dates.csv'), index=False)
print(f'\n=== Top 10 Signal Burst Dates ===')
print(burst.head(10).to_string(index=False))

print(f'\nfinal equity: {cash:.2f}, total return: {(cash/INITIAL-1)*100:.2f}%')
print('DONE E0.1-B/C/D')
