#!/usr/bin/env python3
"""E1 Model 1: ETF PRICE SIGNAL + ETF EXECUTION (Baseline Falsification)

Reuses the E0 diagnostic portfolio simulation with E1-required fixes:
  1. Representative switch fix: positions tracked by (index_key, etf_code),
     exit/valuation uses ACTUAL held ETF data (not current rep)
  2. Tick rounding: all fill prices round to 0.001 RMB
  3. Price limit constraint: PIT 10%/20% rules, limit-up open = can't buy
  4. Liquidity filter: ADV60(t-1) >= 20,000,000 RMB (frozen in Registry)
  5. amount > 0 for execution
  6. Full trade logging + equity curve + yearly returns

Frozen parameters (identical to stock A0 baseline, apples-to-apples):
  BB(20,2), amount Top10, T+1 open, K=3, max_levels=5, level_cash=200k,
  initial=1M, slippage=10bp, commission=0.025% min 5, NO stamp duty (ETF),
  STRICT_C dynamic_touch exit (Pstar=analytic_Pstar(近19日 close_adj))

Outputs:
  results/etf/e1_model1_trade_log.csv
  results/etf/e1_model1_equity_curve.csv
  results/etf/e1_model1_yearly_returns.csv
  results/etf/e1_model1_summary.csv
  results/etf/e1_model1_daily_panel.csv
"""
import os, sys
import numpy as np
import pandas as pd

DATA_ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
WT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/etf_e0_wt'
OUT = os.path.join(WT, 'results', 'etf')
RAWDIR = os.path.join(DATA_ROOT, 'data', 'raw', 'etf')

sys.path.insert(0, DATA_ROOT)
from run_strict_c_math import analytic_Pstar

# ===== FROZEN PARAMETERS =====
BB_WINDOW, BB_STD = 20, 2.0
K, MAX_LEVELS, LEVEL_CASH, INITIAL = 3, 5, 200_000, 1_000_000
SLIP = 10 / 10000.0
COMM = 0.00025
MIN_COMM = 5.0
TOP_N = 10
LIQUIDITY_FILTER_ADV60 = 20_000  # in 千元 (fund_daily.amount unit = 千元), = 2000万元, frozen in Registry
TICK = 0.001
LOT = 100

def round_tick(px):
    """Round price to tick size (0.001)."""
    return round(px / TICK) * TICK

def commission(amt):
    return max(amt * COMM, MIN_COMM)

print('loading etf_feat_long.parquet...')
feat = pd.read_parquet(os.path.join(RAWDIR, 'etf_feat_long.parquet'))
feat['date'] = pd.to_datetime(feat['date'])
feat = feat[feat['date'] <= '2026-09-03'].copy()
print(f'feat rows: {len(feat)}')

# PIT listed filter + min 60 days
feat['listed'] = (feat['list_date'] <= feat['date']) & (feat['delist'].isna() | (feat['delist'] > feat['date']))
avail = feat[feat['listed']].copy()
avail['n_days'] = avail.groupby('etf')['date'].cumcount() + 1
avail = avail[avail['n_days'] >= 60].copy()

# Liquidity filter: ADV60(t-1) >= 20M
avail = avail[avail['adv60'] >= LIQUIDITY_FILTER_ADV60].copy()
print(f'after liquidity filter (ADV60>={LIQUIDITY_FILTER_ADV60:,} 千元 = {LIQUIDITY_FILTER_ADV60*1000:,.0f} 元): {len(avail)} rows')

# Daily PIT B2 representative: per index_key-date, highest adv60
avail = avail.sort_values('adv60', ascending=False)
rep = avail.drop_duplicates(subset=['index_key', 'date']).copy()
print(f'daily PIT reps: {len(rep)}, unique indexes: {rep["index_key"].nunique()}, unique ETFs: {rep["etf"].nunique()}')

# Signal: close_adj < bb_lower, amount > 0
rep['signal'] = (rep['close_adj'] < rep['bb_lower']) & (rep['amount'].fillna(0) > 0) & rep['bb_lower'].notna()

# Pre-compute limit prices for each ETF-day (for price limit constraint)
# price_limit_pit: '10PCT' or '20PCT_STAR' or '20PCT_GEM_20200824'
def limit_pct(rule):
    if pd.isna(rule) or rule == '10PCT':
        return 0.10
    return 0.20

rep['limit_pct'] = rep['price_limit_pit'].apply(limit_pct).astype(float)
# pre_close per ETF
rep = rep.sort_values(['etf', 'date'])
rep['pre_close'] = rep.groupby('etf')['close'].shift(1).astype(float)
rep['limit_up'] = rep['pre_close'] * (1 + rep['limit_pct'])
rep['limit_down'] = rep['pre_close'] * (1 - rep['limit_pct'])
# is limit-up at open (can't buy): open >= limit_up (allow 0.1% rounding tolerance)
rep['is_limit_up_open'] = rep['open'] >= rep['limit_up'] * 0.999
rep['is_limit_down_day'] = rep['high'] <= rep['limit_down'] * 1.001  # whole day at limit down

# Build day-indexed panel for fast lookup
panel = rep.sort_values(['date', 'amount'], ascending=[True, False]).copy()
days = sorted(panel['date'].unique())
D = {d: g for d, g in panel.groupby('date')}
print(f'trading days: {len(days)}, range: {days[0].date()} -> {days[-1].date()}')

# ===== PORTFOLIO SIMULATION =====
# FIX: positions tracked by (index_key, etf_code) tuple, not just index_key
positions = []  # each: {index_key, etf, shares, avg_cost, levels, total_cost, entry_day, last_add}
cash = INITIAL
trade_log = []
equity_curve = []
daily_panel = []

pending_buy = []  # list of (index_key, etf_code) — FIX: include etf
pending_add = {}  # (index_key, etf_code) -> True

def find_pos(index_key, etf):
    """FIX: find position by both index_key AND etf_code."""
    return next((p for p in positions if p['index_key'] == index_key and p['etf'] == etf), None)

for i, d in enumerate(days):
    g = D[d]
    n_entries = 0
    n_exits = 0

    # ---- OPEN: execute pending buys ----
    if pending_buy:
        for pb in list(pending_buy):
            idx_key, etf_code = pb
            if len(positions) >= K:
                pending_buy = [x for x in pending_buy if x != pb]
                continue
            # FIX: look up by actual ETF, not just index_key
            row = g[g['etf'] == etf_code]
            if len(row) == 0:
                # ETF not in today's panel (suspended/delisted) — carry
                continue
            r = row.iloc[0]
            opx = r['open']
            if pd.isna(opx) or opx <= 0 or r['amount'] <= 0:
                pending_buy = [x for x in pending_buy if x != pb]
                continue
            # Price limit: if limit-up at open, can't buy — carry to next day
            if r['is_limit_up_open']:
                continue  # keep in pending_buy, try again next day
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
                              'cash_after': cash, 'level': 1})
            n_entries += 1
            pending_buy = [x for x in pending_buy if x != pb]

    # ---- OPEN: execute pending adds ----
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
                continue  # carry
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
                                      'cash_after': cash, 'level': pos['levels']})
                    n_entries += 1
            pending_add.pop(key, None)

    # ---- INTRADAY: STRICT_C dynamic_touch exit (FIX: use actual held ETF) ----
    for pos in list(positions):
        row = g[g['etf'] == pos['etf']]  # FIX: actual ETF, not current rep
        if len(row) == 0:
            continue  # ETF not trading today, can't exit
        r = row.iloc[0]
        # If whole day at limit-down, can't exit intraday
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
                              'level': pos['levels']})
            positions.remove(pos)
            n_exits += 1

    # ---- CLOSE: new signals -> pending buy/add ----
    # Top-N by amount within signals
    sig_rows = g[g['signal'] & (g['amount'] > 0)].head(TOP_N)
    for _, r in sig_rows.iterrows():
        idx_key = r['index_key']
        etf_code = r['etf']
        held = {(p['index_key'], p['etf']) for p in positions}
        if (idx_key, etf_code) in held:
            pos = find_pos(idx_key, etf_code)
            if (pos and pos['levels'] < MAX_LEVELS and pd.notna(r['bb_lower'])
                    and r['close_adj'] < r['bb_lower'] and r['amount'] > 0
                    and (d - pos['last_add']).days >= 1):
                pending_add[(idx_key, etf_code)] = True
        elif len(positions) + len(pending_buy) < K:
            if (idx_key, etf_code) not in pending_buy:
                pending_buy.append((idx_key, etf_code))

    # ---- Valuation (FIX: use actual held ETF prices) ----
    stock_val = 0.0
    for pos in positions:
        row = g[g['etf'] == pos['etf']]
        px = row.iloc[0]['close'] if len(row) else pos['avg_cost']
        stock_val += pos['shares'] * px
    equity = cash + stock_val
    invested_pct = (equity - cash) / equity if equity > 0 else 0
    equity_curve.append({'date': d, 'equity': equity, 'cash': cash,
                         'invested': equity - cash, 'invested_pct': invested_pct})
    # daily signal stats
    day_sig = g[g['signal']]
    daily_panel.append({'date': d, 'eligible_count': len(g),
                        'n_signal': len(day_sig), 'open_positions': len(positions),
                        'n_entries': n_entries, 'n_exits': n_exits,
                        'invested_pct': invested_pct})

# ---- Final liquidation ----
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
                      'holding_days': (last_d - pos['entry_day']).days, 'level': pos['levels']})

# ===== SAVE OUTPUTS =====
tl = pd.DataFrame(trade_log)
tl.to_csv(os.path.join(OUT, 'e1_model1_trade_log.csv'), index=False)

eq = pd.DataFrame(equity_curve)
eq.to_csv(os.path.join(OUT, 'e1_model1_equity_curve.csv'), index=False)

dp = pd.DataFrame(daily_panel)
dp.to_csv(os.path.join(OUT, 'e1_model1_daily_panel.csv'), index=False)

# ===== METRICS =====
print(f'\n===== E1 Model 1 Summary =====')
print(f'Period: {days[0].date()} -> {days[-1].date()} ({len(days)} days)')
print(f'Trades: {len(tl)} (ENTRY {(tl["action"]=="ENTRY").sum()}, ADD {(tl["action"]=="ADD").sum()}, '
      f'EXIT_PSTAR {(tl["action"]=="EXIT_PSTAR").sum()}, EXIT_FINAL {(tl["action"]=="EXIT_FINAL").sum()})')

final_equity = cash
total_return = (final_equity / INITIAL - 1) * 100
n_years = (days[-1] - days[0]).days / 365.25
cagr = ((final_equity / INITIAL) ** (1 / n_years) - 1) * 100 if n_years > 0 else 0

# Daily returns for vol/Sharpe/MaxDD
eq['daily_ret'] = eq['equity'].pct_change()
ann_vol = eq['daily_ret'].std() * np.sqrt(252) * 100
sharpe = (eq['daily_ret'].mean() * 252) / (eq['daily_ret'].std() * np.sqrt(252)) if eq['daily_ret'].std() > 0 else 0
# MaxDD
cummax = eq['equity'].cummax()
drawdown = (eq['equity'] / cummax - 1) * 100
maxdd = drawdown.min()

# Trade stats (completed trades only)
completed = tl[tl['action'].isin(['EXIT_PSTAR', 'EXIT_FINAL'])]
win_rate = (completed['pnl'] > 0).mean() * 100 if len(completed) > 0 else 0
avg_trade = completed['pnl'].mean() if len(completed) > 0 else 0
median_trade = completed['pnl'].median() if len(completed) > 0 else 0
avg_holding = completed['holding_days'].mean() if len(completed) > 0 else 0
# Profit factor
gross_profit = completed[completed['pnl'] > 0]['pnl'].sum()
gross_loss = abs(completed[completed['pnl'] < 0]['pnl'].sum())
pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')

# Exposure / cash
avg_exposure = eq['invested_pct'].mean() * 100
median_exposure = eq['invested_pct'].median() * 100
fully_invested = (eq['invested_pct'] >= 0.99).mean() * 100
lt50_invested = (eq['invested_pct'] < 0.5).mean() * 100
avg_cash = (1 - eq['invested_pct']).mean() * 100

# Cost drag
total_fees = tl['fee'].sum()
cost_drag = total_fees / INITIAL * 100

# Turnover (approx: total bought / initial / years)
total_bought = tl[tl['action'].isin(['ENTRY', 'ADD'])]['amount'].sum()
turnover = total_bought / INITIAL / n_years if n_years > 0 else 0

summary = pd.DataFrame([
    {'metric': 'period_start', 'value': str(days[0].date())},
    {'metric': 'period_end', 'value': str(days[-1].date())},
    {'metric': 'n_trading_days', 'value': len(days)},
    {'metric': 'n_years', 'value': round(n_years, 2)},
    {'metric': 'initial_cash', 'value': INITIAL},
    {'metric': 'final_equity', 'value': round(final_equity, 2)},
    {'metric': 'total_return_pct', 'value': round(total_return, 2)},
    {'metric': 'CAGR_pct', 'value': round(cagr, 2)},
    {'metric': 'annualized_vol_pct', 'value': round(ann_vol, 2)},
    {'metric': 'Sharpe', 'value': round(sharpe, 4)},
    {'metric': 'MaxDD_pct', 'value': round(maxdd, 2)},
    {'metric': 'Calmar', 'value': round(cagr / abs(maxdd), 4) if maxdd != 0 else 0},
    {'metric': 'total_trades', 'value': len(tl)},
    {'metric': 'completed_trades', 'value': len(completed)},
    {'metric': 'win_rate_pct', 'value': round(win_rate, 2)},
    {'metric': 'avg_trade_pnl', 'value': round(avg_trade, 2)},
    {'metric': 'median_trade_pnl', 'value': round(median_trade, 2)},
    {'metric': 'profit_factor', 'value': round(pf, 4)},
    {'metric': 'avg_holding_days', 'value': round(avg_holding, 1)},
    {'metric': 'avg_exposure_pct', 'value': round(avg_exposure, 2)},
    {'metric': 'median_exposure_pct', 'value': round(median_exposure, 2)},
    {'metric': 'avg_cash_pct', 'value': round(avg_cash, 2)},
    {'metric': 'fully_invested_days_pct', 'value': round(fully_invested, 2)},
    {'metric': 'lt50_invested_days_pct', 'value': round(lt50_invested, 2)},
    {'metric': 'total_fees', 'value': round(total_fees, 2)},
    {'metric': 'cost_drag_pct', 'value': round(cost_drag, 2)},
    {'metric': 'annual_turnover', 'value': round(turnover, 2)},
    {'metric': 'signals_per_day', 'value': round(dp['n_signal'].mean(), 2)},
    {'metric': 'entries_per_day', 'value': round(dp['n_entries'].mean(), 4)},
    {'metric': 'avg_open_positions', 'value': round(dp['open_positions'].mean(), 2)},
])
summary.to_csv(os.path.join(OUT, 'e1_model1_summary.csv'), index=False)
print(summary.to_string(index=False))

# Yearly returns
eq['year'] = eq['date'].dt.year
yearly = eq.groupby('year').agg(
    start_equity=('equity', 'first'),
    end_equity=('equity', 'last'),
).reset_index()
yearly['return_pct'] = (yearly['end_equity'] / yearly['start_equity'] - 1) * 100
yearly.to_csv(os.path.join(OUT, 'e1_model1_yearly_returns.csv'), index=False)
print(f'\n=== Yearly Returns ===')
print(yearly[['year', 'return_pct']].to_string(index=False))

print(f'\nDONE E1 Model 1. final_equity={final_equity:.2f}, total_return={total_return:.2f}%')
