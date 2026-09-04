#!/usr/bin/env python3
"""E2 Midline Exit Hypothesis Test — parameterized backtest engine.

Runs 4 configurations:
  M1 Control   (ETF signal + STRICT_C exit)  — must reproduce frozen E1
  M1 Midline   (ETF signal + first BB midline touch exit)
  M2 Control   (Index signal + STRICT_C exit) — must reproduce frozen E1
  M2 Midline   (Index signal + first BB midline touch exit)

Only exit threshold differs: Control uses pstar (STRICT_C), Treatment uses bb_mid.
All execution semantics (bar-based touch, fill at threshold, slippage, tick rounding,
price-limit, suspension, T+1) are IDENTICAL between Control and Treatment.
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

# ===== FROZEN PARAMETERS (identical to E1) =====
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

# ===== LOAD DATA (once) =====
print('loading data...')
feat = pd.read_parquet(os.path.join(RAWDIR, 'etf_feat_long.parquet'))
feat['date'] = pd.to_datetime(feat['date'])
feat = feat[feat['date'] <= '2026-09-03'].copy()
feat = feat.sort_values(['etf', 'date'])
# Compute bb_mid (MA20) for midline exit — PIT rolling, no future data
feat['bb_mid'] = feat.groupby('etf')['close_adj'].transform(
    lambda x: x.rolling(BB_WINDOW, min_periods=BB_WINDOW).mean())

master = pd.read_parquet(os.path.join(RAWDIR, 'master_mapping_full.parquet'))
master['index_key'] = master.apply(
    lambda r: (r['index_code'] if pd.notna(r['index_code']) and str(r['index_code']) != 'nan'
               else r['bench_idx_name']), axis=1)
idx_to_key = dict(zip(master['index_code'], master['index_key']))

# Index daily for Model 2
ib = pd.read_parquet(os.path.join(RAWDIR, 'index_basic_exchange.parquet'))
valid_codes = set(ib['ts_code'].tolist())
index_to_exchange = {}
for c in master['index_code'].dropna().unique():
    if c.endswith('.CSI'):
        num = c.replace('.CSI', '')
        for s in ['.SH', '.SZ']:
            ex = num + s
            if ex in valid_codes and os.path.exists(os.path.join(IDXDIR, ex.replace('.', '_') + '.parquet')):
                index_to_exchange[c] = ex
                break
    elif os.path.exists(os.path.join(IDXDIR, c.replace('.', '_') + '.parquet')):
        index_to_exchange[c] = c

# Compute index BB signals
index_signals = {}
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
        'date': df['trade_date'], 'index_signal': sig.values})

# Build PIT representative panel (same for all configs)
print('building PIT representative panel...')
feat['listed'] = (feat['list_date'] <= feat['date']) & (feat['delist'].isna() | (feat['delist'] > feat['date']))
avail = feat[feat['listed']].copy()
avail['n_days'] = avail.groupby('etf')['date'].cumcount() + 1
avail = avail[avail['n_days'] >= 60].copy()
avail = avail[avail['adv60'] >= LIQUIDITY_FILTER_ADV60].copy()
avail = avail.sort_values('adv60', ascending=False)
rep = avail.drop_duplicates(subset=['index_key', 'date']).copy()

# Price limit
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

print(f'PIT reps: {len(rep)}, unique indexes: {rep["index_key"].nunique()}')


def run_backtest(exit_type, signal_source, label):
    """
    exit_type: 'strict_c' or 'midline'
    signal_source: 'etf' (Model1) or 'index' (Model2)
    label: output label
    """
    print(f'\n=== Running {label} (exit={exit_type}, signal={signal_source}) ===')

    # Build panel with signal flag
    panel = rep.copy()
    if signal_source == 'etf':
        panel['signal'] = (panel['close_adj'] < panel['bb_lower']) & panel['bb_lower'].notna()
    else:
        # Index signal: map index signals to index_key
        sig_rows = []
        for idx_code, sig_df in index_signals.items():
            idx_key = idx_to_key.get(idx_code)
            if idx_key is None:
                continue
            sig_days = sig_df[sig_df['index_signal']]['date']
            for d in sig_days:
                sig_rows.append({'date': d, 'index_key': idx_key})
        sig_df_all = pd.DataFrame(sig_rows)
        panel['signal'] = False
        if len(sig_df_all) > 0:
            sig_keys = set(zip(sig_df_all['date'], sig_df_all['index_key']))
            panel['signal'] = panel.apply(lambda r: (r['date'], r['index_key']) in sig_keys, axis=1)

    panel = panel.sort_values(['date', 'amount'], ascending=[True, False]).copy()
    days = sorted(panel['date'].unique())
    D = {d: g for d, g in panel.groupby('date')}
    print(f'  trading days: {len(days)}, signals: {panel["signal"].sum()}')

    # Portfolio simulation
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
                                  'cash_after': cash, 'level': 1})
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
                                          'cash_after': cash, 'level': pos['levels']})
                        n_entries += 1
                pending_add.pop(key, None)

        # Intraday exit — THE ONLY DIFFERENCE BETWEEN CONTROL AND TREATMENT
        for pos in list(positions):
            row = g[g['etf'] == pos['etf']]
            if len(row) == 0:
                continue
            r = row.iloc[0]
            if r['is_limit_down_day']:
                continue
            if r['amount'] <= 0:
                continue

            if exit_type == 'strict_c':
                # Control: STRICT_C pstar touch (identical to E1)
                if pd.notna(r['pstar']) and pd.notna(r['high_adj']) and r['high_adj'] >= r['pstar']:
                    threshold_adj = r['pstar']
                else:
                    continue
            else:  # midline
                # Treatment: first BB midline touch — SAME bar-based semantics
                if pd.notna(r['bb_mid']) and pd.notna(r['high_adj']) and r['high_adj'] >= r['bb_mid']:
                    threshold_adj = r['bb_mid']
                else:
                    continue

            # Fill at threshold price (identical execution generosity)
            px = round_tick((threshold_adj / r['adj']) * (1 - SLIP))
            amt = px * pos['shares']
            fee = commission(amt)
            cash += amt - fee
            pnl = (px - pos['avg_cost']) * pos['shares'] - fee
            exit_action = 'EXIT_PSTAR' if exit_type == 'strict_c' else 'EXIT_MIDLINE'
            trade_log.append({'date': d, 'action': exit_action, 'index_key': pos['index_key'],
                              'etf': pos['etf'], 'shares': pos['shares'], 'price': px,
                              'amount': amt, 'fee': fee, 'cash_after': cash,
                              'pnl': pnl, 'holding_days': (d - pos['entry_day']).days,
                              'level': pos['levels']})
            positions.remove(pos)
            n_exits += 1

        # Close: new signals -> pending buy/add
        sig_rows_today = g[g['signal'] & (g['amount'] > 0)].head(TOP_N)
        for _, r in sig_rows_today.iterrows():
            idx_key = r['index_key']
            etf_code = r['etf']
            held = {(p['index_key'], p['etf']) for p in positions}
            if (idx_key, etf_code) in held:
                pos = find_pos(idx_key, etf_code)
                if (pos and pos['levels'] < MAX_LEVELS
                        and r['amount'] > 0 and (d - pos['last_add']).days >= 1):
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
        day_sig = g[g['signal']]
        daily_panel.append({'date': d, 'eligible_count': len(g),
                            'n_signal': len(day_sig), 'open_positions': len(positions),
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
                          'level': pos['levels']})

    # Save
    tl = pd.DataFrame(trade_log)
    eq = pd.DataFrame(equity_curve)
    dp = pd.DataFrame(daily_panel)

    suffix = label.lower().replace(' ', '_')
    tl.to_csv(os.path.join(OUT, f'e2_trade_log_{suffix}.csv'), index=False)
    eq.to_csv(os.path.join(OUT, f'e2_equity_{suffix}.csv'), index=False)
    dp.to_csv(os.path.join(OUT, f'e2_daily_panel_{suffix}.csv'), index=False)

    # Metrics
    final_equity = cash
    total_return = (final_equity / INITIAL - 1) * 100
    n_years = (days[-1] - days[0]).days / 365.25
    cagr = ((final_equity / INITIAL) ** (1 / n_years) - 1) * 100 if n_years > 0 else 0
    eq['daily_ret'] = eq['equity'].pct_change()
    ann_vol = eq['daily_ret'].std() * np.sqrt(252) * 100
    sharpe = (eq['daily_ret'].mean() * 252) / (eq['daily_ret'].std() * np.sqrt(252)) if eq['daily_ret'].std() > 0 else 0
    downside = eq[eq['daily_ret'] < 0]['daily_ret']
    sortino = (eq['daily_ret'].mean() * 252) / (downside.std() * np.sqrt(252)) if len(downside) > 0 and downside.std() > 0 else 0
    cummax = eq['equity'].cummax()
    maxdd = ((eq['equity'] / cummax - 1) * 100).min()
    calmar = cagr / abs(maxdd) if maxdd != 0 else 0

    completed = tl[tl['action'].str.startswith('EXIT')]
    win_rate = (completed['pnl'] > 0).mean() * 100 if len(completed) > 0 else 0
    avg_trade = completed['pnl'].mean() if len(completed) > 0 else 0
    median_trade = completed['pnl'].median() if len(completed) > 0 else 0
    winners = completed[completed['pnl'] > 0]
    losers = completed[completed['pnl'] <= 0]
    gp = winners['pnl'].sum()
    gl = abs(losers['pnl'].sum())
    pf = gp / gl if gl > 0 else float('inf')
    avg_winner = winners['pnl'].mean() if len(winners) else 0
    avg_loser = abs(losers['pnl'].mean()) if len(losers) else 0
    payoff = avg_winner / avg_loser if avg_loser > 0 else float('inf')
    avg_holding = completed['holding_days'].mean() if len(completed) > 0 else 0
    median_holding = completed['holding_days'].median() if len(completed) > 0 else 0
    p90_holding = completed['holding_days'].quantile(0.90) if len(completed) > 0 else 0
    total_fees = tl['fee'].sum()
    turnover = len(completed) / n_years if n_years > 0 else 0

    summary = {
        'config': label, 'exit_type': exit_type, 'signal_source': signal_source,
        'period_start': str(days[0].date()), 'period_end': str(days[-1].date()),
        'n_trading_days': len(days), 'n_years': round(n_years, 2),
        'final_equity': round(final_equity, 2),
        'total_return_pct': round(total_return, 2),
        'CAGR_pct': round(cagr, 2),
        'annualized_vol_pct': round(ann_vol, 2),
        'Sharpe': round(sharpe, 4),
        'Sortino': round(sortino, 4),
        'MaxDD_pct': round(maxdd, 2),
        'Calmar': round(calmar, 4),
        'total_trades': len(tl),
        'completed_trades': len(completed),
        'win_rate_pct': round(win_rate, 2),
        'avg_trade_pnl': round(avg_trade, 2),
        'median_trade_pnl': round(median_trade, 2),
        'profit_factor': round(pf, 4),
        'avg_winner_pnl': round(avg_winner, 2),
        'avg_loser_pnl': round(avg_loser, 2),
        'payoff_ratio': round(payoff, 4),
        'avg_holding_days': round(avg_holding, 1),
        'median_holding_days': round(median_holding, 1),
        'p90_holding_days': round(p90_holding, 1),
        'annual_turnover': round(turnover, 2),
        'total_fees': round(total_fees, 2),
        'avg_exposure_pct': round(eq['invested_pct'].mean() * 100, 2),
        'avg_cash_pct': round((1 - eq['invested_pct']).mean() * 100, 2),
        'fully_invested_days_pct': round((eq['invested_pct'] >= 0.99).mean() * 100, 2),
    }

    print(f'  Total Return: {total_return:.2f}%, CAGR: {cagr:.2f}%, Sharpe: {sharpe:.4f}, MaxDD: {maxdd:.2f}%')
    print(f'  Trades: {len(completed)}, Win Rate: {win_rate:.1f}%, PF: {pf:.4f}, Payoff: {payoff:.4f}')
    print(f'  Avg Holding: {avg_holding:.1f}d, Avg Exposure: {eq["invested_pct"].mean()*100:.1f}%')

    return summary, tl, eq, dp


# ===== RUN ALL 4 CONFIGS =====
results = []

# M1 Control (must reproduce E1)
s, _, _, _ = run_backtest('strict_c', 'etf', 'M1 Control')
results.append(s)

# M1 Midline
s, _, _, _ = run_backtest('midline', 'etf', 'M1 Midline')
results.append(s)

# M2 Control
s, _, _, _ = run_backtest('strict_c', 'index', 'M2 Control')
results.append(s)

# M2 Midline
s, _, _, _ = run_backtest('midline', 'index', 'M2 Midline')
results.append(s)

# Save combined summary
summary_df = pd.DataFrame(results)
summary_df.to_csv(os.path.join(OUT, 'e2_all_configs_summary.csv'), index=False)

# Also save individual summaries
for _, row in summary_df.iterrows():
    suffix = row['config'].lower().replace(' ', '_')
    pd.DataFrame([row]).to_csv(os.path.join(OUT, f'e2_{suffix}_summary.csv'), index=False)

print('\n===== E2 ALL CONFIGS SUMMARY =====')
print(summary_df[['config', 'total_return_pct', 'CAGR_pct', 'Sharpe', 'MaxDD_pct',
                   'completed_trades', 'win_rate_pct', 'profit_factor', 'payoff_ratio',
                   'avg_holding_days', 'avg_exposure_pct']].to_string(index=False))

# Control reproduction check
print('\n===== CONTROL REPRODUCTION CHECK =====')
e1_m1 = pd.read_csv(os.path.join(OUT, 'e1_model1_summary.csv'))
e1_m2 = pd.read_csv(os.path.join(OUT, 'e1_model2_summary.csv'))
m1_ctrl = summary_df[summary_df['config'] == 'M1 Control'].iloc[0]
m2_ctrl = summary_df[summary_df['config'] == 'M2 Control'].iloc[0]
print(f'M1 Control: E1 total_return={e1_m1[e1_m1["metric"]=="total_return_pct"]["value"].values[0]} vs E2={m1_ctrl["total_return_pct"]}')
print(f'M1 Control: E1 trades={e1_m1[e1_m1["metric"]=="total_trades"]["value"].values[0]} vs E2={m1_ctrl["total_trades"]}')
print(f'M2 Control: E1 total_return={e1_m2[e1_m2["metric"]=="total_return_pct"]["value"].values[0]} vs E2={m2_ctrl["total_return_pct"]}')
print(f'M2 Control: E1 trades={e1_m2[e1_m2["metric"]=="total_trades"]["value"].values[0]} vs E2={m2_ctrl["total_trades"]}')

print('\nDONE E2.')
