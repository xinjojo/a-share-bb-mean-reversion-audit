#!/usr/bin/env python3
"""E4 BB_Z Ranking Hypothesis Test — parameterized backtest + ranking diagnostic.

Runs 4 portfolio configs (M1/M2 × Amount/BB_Z), all with Midline exit + LowBreadth filter.
Also runs pure cross-sectional ranking diagnostic: IC, quantile monotonicity, selected vs non-selected.

Only ranking variable changes. Everything else frozen from E3.
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

# ===== FROZEN PARAMETERS (identical to E3) =====
BB_WINDOW, BB_STD = 20, 2.0
K, MAX_LEVELS, LEVEL_CASH, INITIAL = 3, 5, 200_000, 1_000_000
SLIP = 10 / 10000.0
COMM = 0.00025
MIN_COMM = 5.0
TOP_N = 10
LIQUIDITY_FILTER_ADV60 = 20_000  # 千元
TICK = 0.001
LOT = 100
BREADTH_THRESHOLD = 0.10

def round_tick(px):
    return round(px / TICK) * TICK

def commission(amt):
    return max(amt * COMM, MIN_COMM)

# ===== LOAD DATA =====
print('loading data...')
feat = pd.read_parquet(os.path.join(RAWDIR, 'etf_feat_long.parquet'))
feat['date'] = pd.to_datetime(feat['date'])
feat = feat[feat['date'] <= '2026-09-03'].copy()
feat = feat.sort_values(['etf', 'date'])
feat['bb_mid'] = feat.groupby('etf')['close_adj'].transform(
    lambda x: x.rolling(BB_WINDOW, min_periods=BB_WINDOW).mean())
# NOTE: bb_z computed LATER on rep only, to keep feat/rep construction identical to E3

master = pd.read_parquet(os.path.join(RAWDIR, 'master_mapping_full.parquet'))
master['index_key'] = master.apply(
    lambda r: (r['index_code'] if pd.notna(r['index_code']) and str(r['index_code']) != 'nan'
               else r['bench_idx_name']), axis=1)
idx_to_key = dict(zip(master['index_code'], master['index_key']))

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

# Load index data with BB_Z
index_data = {}
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
    bb_z = (close - ma) / sd
    sig = (close < bb_lower) & bb_lower.notna()
    index_signals[idx_code] = pd.DataFrame({'date': df['trade_date'], 'index_signal': sig.values})
    index_data[idx_code] = pd.DataFrame({'date': df['trade_date'], 'index_close': close.values,
                                           'index_bb_z': bb_z.values})

# Build PIT representative panel
print('building PIT representative panel...')
feat['listed'] = (feat['list_date'] <= feat['date']) & (feat['delist'].isna() | (feat['delist'] > feat['date']))
avail = feat[feat['listed']].copy()
avail['n_days'] = avail.groupby('etf')['date'].cumcount() + 1
avail = avail[avail['n_days'] >= 60].copy()
avail = avail[avail['adv60'] >= LIQUIDITY_FILTER_ADV60].copy()
avail = avail.sort_values('adv60', ascending=False)
rep = avail.drop_duplicates(subset=['index_key', 'date']).copy()

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

# BB_Z computed on rep only (after all E3-identical rep construction)
# BB_Z = (close - MA20) / rolling_std; std = (bb_mid - bb_lower) / 2
rep['bb_std'] = (rep['bb_mid'] - rep['bb_lower']) / BB_STD
rep['bb_z'] = (rep['close_adj'] - rep['bb_mid']) / rep['bb_std']
rep.loc[rep['bb_std'] == 0, 'bb_z'] = np.nan

print(f'PIT reps: {len(rep)}, unique indexes: {rep["index_key"].nunique()}')


def build_panel(signal_source):
    """Build daily panel with signals and BB_Z for given signal source."""
    panel = rep.copy()
    if signal_source == 'etf':
        panel['signal'] = (panel['close_adj'] < panel['bb_lower']) & panel['bb_lower'].notna()
        panel['ranking_bb_z'] = panel['bb_z']
    else:
        # Index signal + index BB_Z
        sig_rows = []
        bbz_rows = []
        for idx_code, sig_df in index_signals.items():
            idx_key = idx_to_key.get(idx_code)
            if idx_key is None:
                continue
            sig_days = sig_df[sig_df['index_signal']]['date']
            for d in sig_days:
                sig_rows.append({'date': d, 'index_key': idx_key})
        for idx_code, idf in index_data.items():
            idx_key = idx_to_key.get(idx_code)
            if idx_key is None:
                continue
            for _, row in idf.iterrows():
                bbz_rows.append({'date': row['date'], 'index_key': idx_key, 'index_bb_z': row['index_bb_z']})
        sig_df_all = pd.DataFrame(sig_rows)
        bbz_df_all = pd.DataFrame(bbz_rows)
        panel['signal'] = False
        if len(sig_df_all) > 0:
            sig_keys = set(zip(sig_df_all['date'], sig_df_all['index_key']))
            panel['signal'] = panel.apply(lambda r: (r['date'], r['index_key']) in sig_keys, axis=1)
        if len(bbz_df_all) > 0:
            panel = panel.merge(bbz_df_all, on=['date', 'index_key'], how='left')
            panel['ranking_bb_z'] = panel['index_bb_z']
        else:
            panel['ranking_bb_z'] = np.nan
    return panel


def rank_candidates(g, ranking_var):
    """Rank candidates by specified variable. Returns sorted dataframe.
    For amount ranking: use existing panel order (already sorted by amount desc) to match E3 exactly.
    For BB_Z ranking: ascending BB_Z, tie-breaker: larger amount, then lexicographic code.
    """
    if ranking_var == 'amount':
        return g  # panel already sorted by date then amount desc; preserve E3 tie-breaking
    elif ranking_var == 'bb_z':
        g = g.copy()
        g = g.sort_values(['ranking_bb_z', 'amount', 'etf'], ascending=[True, False, True], kind='mergesort')
        return g
    return g


# ===== PART 1: RANKING DIAGNOSTIC (IC, quantiles, selected vs non-selected) =====
print('\n===== PART 1: RANKING DIAGNOSTIC =====')

for signal_source in ['etf', 'index']:
    model_name = 'M1' if signal_source == 'etf' else 'M2'
    print(f'\n--- {model_name} ({signal_source} signal) ---')
    panel = build_panel(signal_source)
    panel = panel.sort_values(['date', 'amount'], ascending=[True, False]).copy()
    days = sorted(panel['date'].unique())
    D = {d: g for d, g in panel.groupby('date')}

    # Collect all low-breadth signal-day candidates with forward returns
    all_candidates = []
    for d in days:
        g = D[d]
        n_eligible = len(g)
        n_signals = g['signal'].sum()
        if n_eligible == 0:
            continue
        ratio = n_signals / n_eligible
        if ratio >= BREADTH_THRESHOLD:
            continue  # only low-breadth days
        sig_cands = g[g['signal'] & (g['amount'] > 0)].copy()
        if len(sig_cands) == 0:
            continue
        # Compute forward returns for each candidate
        for _, cand in sig_cands.iterrows():
            etf = cand['etf']
            etf_hist = feat[(feat['etf'] == etf) & (feat['date'] >= d)].head(21)
            if len(etf_hist) < 2:
                continue
            entry_close = etf_hist.iloc[0]['close_adj']
            fwd = {}
            for h in [1, 3, 5, 10, 20]:
                if len(etf_hist) > h:
                    fwd[f'ret_{h}d'] = etf_hist.iloc[h]['close_adj'] / entry_close - 1
                else:
                    fwd[f'ret_{h}d'] = np.nan
            all_candidates.append({
                'date': d, 'etf': etf, 'index_key': cand['index_key'],
                'amount': cand['amount'], 'bb_z': cand['ranking_bb_z'],
                'n_eligible': n_eligible, 'n_signals': n_signals, 'signal_ratio': ratio,
                **fwd
            })

    cand_df = pd.DataFrame(all_candidates)
    print(f'  total low-breadth signal candidates: {len(cand_df)}')
    if len(cand_df) == 0:
        continue

    # Amount rank and BB_Z rank within each day
    cand_df['amount_rank'] = cand_df.groupby('date')['amount'].rank(ascending=False, method='min')
    cand_df['bbz_rank'] = cand_df.groupby('date')['bb_z'].rank(ascending=True, method='min')

    # === IC (Spearman) ===
    print('  --- Spearman IC ---')
    ic_rows = []
    for h in [1, 3, 5, 10, 20]:
        col = f'ret_{h}d'
        valid = cand_df[cand_df[col].notna() & cand_df['bb_z'].notna()]
        if len(valid) < 10:
            continue
        # Pooled
        rho_amount = valid[['amount_rank', col]].corr(method='spearman').iloc[0, 1]
        rho_bbz = valid[['bbz_rank', col]].corr(method='spearman').iloc[0, 1]
        # Date-level IC mean
        daily_ic_amount = []
        daily_ic_bbz = []
        for d, group in valid.groupby('date'):
            if len(group) >= 3:
                r_a = group[['amount_rank', col]].corr(method='spearman').iloc[0, 1]
                r_b = group[['bbz_rank', col]].corr(method='spearman').iloc[0, 1]
                if not np.isnan(r_a):
                    daily_ic_amount.append(r_a)
                if not np.isnan(r_b):
                    daily_ic_bbz.append(r_b)
        ic_rows.append({
            'horizon': f'{h}d', 'n': len(valid),
            'ic_amount_pooled': round(rho_amount, 4),
            'ic_bbz_pooled': round(rho_bbz, 4),
            'ic_amount_daily_mean': round(np.mean(daily_ic_amount), 4) if daily_ic_amount else np.nan,
            'ic_bbz_daily_mean': round(np.mean(daily_ic_bbz), 4) if daily_ic_bbz else np.nan,
            'ic_amount_hit_rate': round(np.mean(np.array(daily_ic_amount) > 0) * 100, 1) if daily_ic_amount else np.nan,
            'ic_bbz_hit_rate': round(np.mean(np.array(daily_ic_bbz) > 0) * 100, 1) if daily_ic_bbz else np.nan,
        })
    ic_df = pd.DataFrame(ic_rows)
    print(ic_df.to_string(index=False))
    ic_df.to_csv(os.path.join(OUT, f'e4_ranking_ic_{model_name.lower()}.csv'), index=False)

    # === Quantile monotonicity (by BB_Z) ===
    print('  --- BB_Z Quantile Monotonicity ---')
    q_rows = []
    for h in [1, 3, 5, 10, 20]:
        col = f'ret_{h}d'
        valid = cand_df[cand_df[col].notna() & cand_df['bb_z'].notna()].copy()
        if len(valid) < 50:
            continue
        # Assign quantiles within each day (only days with >=5 candidates)
        valid['bbz_quantile'] = valid.groupby('date')['bb_z'].transform(
            lambda x: pd.qcut(x, 5, labels=False, duplicates='drop') if len(x) >= 5 else np.nan)
        for q in range(5):
            qg = valid[valid['bbz_quantile'] == q]
            if len(qg) == 0:
                continue
            q_rows.append({
                'horizon': f'{h}d', 'quantile': f'Q{q+1}',
                'q_label': 'deepest' if q == 0 else ('least' if q == 4 else ''),
                'count': len(qg),
                'mean_ret_pct': round(qg[col].mean() * 100, 3),
                'median_ret_pct': round(qg[col].median() * 100, 3),
                'win_rate_pct': round((qg[col] > 0).mean() * 100, 1),
            })
    q_df = pd.DataFrame(q_rows)
    if len(q_df) > 0:
        print(q_df[q_df['horizon'] == '20d'].to_string(index=False))
    q_df.to_csv(os.path.join(OUT, f'e4_bbz_quantiles_{model_name.lower()}.csv'), index=False)

    # === Selected vs Non-selected ===
    print('  --- Selected Top-N vs Non-selected ---')
    sn_rows = []
    for ranking in ['amount', 'bb_z']:
        rank_col = 'amount_rank' if ranking == 'amount' else 'bbz_rank'
        for h in [1, 3, 5, 10, 20]:
            col = f'ret_{h}d'
            valid = cand_df[cand_df[col].notna()].copy()
            selected = valid[valid[rank_col] <= TOP_N]
            nonselected = valid[valid[rank_col] > TOP_N]
            if len(selected) == 0 or len(nonselected) == 0:
                continue
            sn_rows.append({
                'ranking': ranking, 'horizon': f'{h}d',
                'selected_count': len(selected),
                'selected_mean_pct': round(selected[col].mean() * 100, 3),
                'selected_median_pct': round(selected[col].median() * 100, 3),
                'selected_win_pct': round((selected[col] > 0).mean() * 100, 1),
                'nonselected_count': len(nonselected),
                'nonselected_mean_pct': round(nonselected[col].mean() * 100, 3),
                'nonselected_median_pct': round(nonselected[col].median() * 100, 3),
                'nonselected_win_pct': round((nonselected[col] > 0).mean() * 100, 1),
                'diff_mean_pct': round((selected[col].mean() - nonselected[col].mean()) * 100, 3),
            })
    sn_df = pd.DataFrame(sn_rows)
    if len(sn_df) > 0:
        print(sn_df[sn_df['horizon'] == '20d'].to_string(index=False))
    sn_df.to_csv(os.path.join(OUT, f'e4_selected_vs_nonselected_{model_name.lower()}.csv'), index=False)


# ===== PART 2: PORTFOLIO BACKTEST =====
print('\n===== PART 2: PORTFOLIO BACKTEST =====')

def run_backtest(signal_source, ranking_var, label):
    print(f'\n=== Running {label} (signal={signal_source}, ranking={ranking_var}) ===')
    panel = build_panel(signal_source)
    panel = panel.sort_values(['date', 'amount'], ascending=[True, False]).copy()
    days = sorted(panel['date'].unique())
    D = {d: g for d, g in panel.groupby('date')}

    daily_stats = {}
    for d in days:
        g = D[d]
        n_eligible = len(g)
        n_signals = g['signal'].sum()
        ratio = n_signals / n_eligible if n_eligible > 0 else 0
        daily_stats[d] = {'n_eligible': n_eligible, 'n_signals': n_signals, 'signal_ratio': ratio}

    positions = []
    cash = INITIAL
    trade_log = []
    equity_curve = []
    pending_buy = []
    pending_add = {}

    def find_pos(index_key, etf):
        return next((p for p in positions if p['index_key'] == index_key and p['etf'] == etf), None)

    for i, d in enumerate(days):
        g = D[d]
        stats = daily_stats[d]
        n_entries, n_exits = 0, 0
        breadth_blocked = stats['signal_ratio'] >= BREADTH_THRESHOLD

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
                                  'cash_after': cash, 'level': 1, 'ranking': ranking_var})
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
                                          'cash_after': cash, 'level': pos['levels'], 'ranking': ranking_var})
                        n_entries += 1
                pending_add.pop(key, None)

        # Intraday exit: Midline touch
        for pos in list(positions):
            row = g[g['etf'] == pos['etf']]
            if len(row) == 0:
                continue
            r = row.iloc[0]
            if r['is_limit_down_day']:
                continue
            if r['amount'] <= 0:
                continue
            if pd.notna(r['bb_mid']) and pd.notna(r['high_adj']) and r['high_adj'] >= r['bb_mid']:
                px = round_tick((r['bb_mid'] / r['adj']) * (1 - SLIP))
                amt = px * pos['shares']
                fee = commission(amt)
                cash += amt - fee
                pnl = (px - pos['avg_cost']) * pos['shares'] - fee
                trade_log.append({'date': d, 'action': 'EXIT_MIDLINE', 'index_key': pos['index_key'],
                                  'etf': pos['etf'], 'shares': pos['shares'], 'price': px,
                                  'amount': amt, 'fee': fee, 'cash_after': cash,
                                  'pnl': pnl, 'holding_days': (d - pos['entry_day']).days,
                                  'level': pos['levels'], 'ranking': ranking_var})
                positions.remove(pos)
                n_exits += 1

        # Close: new signals -> pending buy/add (with ranking)
        sig_rows_today = g[g['signal'] & (g['amount'] > 0)].copy()
        sig_rows_today = rank_candidates(sig_rows_today, ranking_var)
        sig_rows_today = sig_rows_today.head(TOP_N)

        if breadth_blocked:
            # High breadth: block NEW entries, but ADDs to existing positions still allowed
            for _, r in sig_rows_today.iterrows():
                idx_key = r['index_key']
                etf_code = r['etf']
                held = {(p['index_key'], p['etf']) for p in positions}
                if (idx_key, etf_code) in held:
                    pos = find_pos(idx_key, etf_code)
                    if (pos and pos['levels'] < MAX_LEVELS
                            and r['amount'] > 0 and (d - pos['last_add']).days >= 1):
                        pending_add[(idx_key, etf_code)] = True
        else:
            # Low breadth: normal entry + add
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
                          'level': pos['levels'], 'ranking': ranking_var})

    # Save
    tl = pd.DataFrame(trade_log)
    eq = pd.DataFrame(equity_curve)
    suffix = label.lower().replace(' ', '_').replace('+', '').replace('-', '')
    tl.to_csv(os.path.join(OUT, f'e4_trade_log_{suffix}.csv'), index=False)
    eq.to_csv(os.path.join(OUT, f'e4_equity_{suffix}.csv'), index=False)

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
    total_fees = tl['fee'].sum()
    turnover = len(completed) / n_years if n_years > 0 else 0

    summary = {
        'config': label, 'signal_source': signal_source, 'ranking': ranking_var,
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
        'annual_turnover': round(turnover, 2),
        'total_fees': round(total_fees, 2),
        'avg_exposure_pct': round(eq['invested_pct'].mean() * 100, 2),
        'median_exposure_pct': round(eq['invested_pct'].median() * 100, 2),
        'fully_invested_days_pct': round((eq['invested_pct'] >= 0.99).mean() * 100, 2),
        'lt25_invested_days_pct': round((eq['invested_pct'] < 0.25).mean() * 100, 2),
        'lt50_invested_days_pct': round((eq['invested_pct'] < 0.50).mean() * 100, 2),
    }

    print(f'  Total Return: {total_return:.2f}%, CAGR: {cagr:.2f}%, Sharpe: {sharpe:.4f}, MaxDD: {maxdd:.2f}%')
    print(f'  Trades: {len(completed)}, Win Rate: {win_rate:.1f}%, PF: {pf:.4f}, Payoff: {payoff:.4f}')
    print(f'  Avg Holding: {avg_holding:.1f}d, Avg Exposure: {eq["invested_pct"].mean()*100:.1f}%')

    return summary, tl, eq


# Run all 4 configs
results = []
for signal_source, model in [('etf', 'M1'), ('index', 'M2')]:
    for ranking_var, rlabel in [('amount', 'Amount'), ('bb_z', 'BB_Z')]:
        label = f'{model} {rlabel}'
        s, _, _ = run_backtest(signal_source, ranking_var, label)
        results.append(s)

summary_df = pd.DataFrame(results)
summary_df.to_csv(os.path.join(OUT, 'e4_all_configs_summary.csv'), index=False)
for _, row in summary_df.iterrows():
    suffix = row['config'].lower().replace(' ', '_').replace('+', '').replace('-', '')
    pd.DataFrame([row]).to_csv(os.path.join(OUT, f'e4_{suffix}_summary.csv'), index=False)

print('\n===== E4 ALL CONFIGS SUMMARY =====')
print(summary_df[['config', 'total_return_pct', 'CAGR_pct', 'Sharpe', 'MaxDD_pct',
                   'completed_trades', 'win_rate_pct', 'profit_factor', 'payoff_ratio',
                   'avg_holding_days', 'avg_exposure_pct']].to_string(index=False))

# Control reproduction check
print('\n===== CONTROL REPRODUCTION CHECK (vs E3) =====')
e3_m1 = -17.14
e3_m2 = -3.47
m1_ctrl = summary_df[summary_df['config'] == 'M1 Amount'].iloc[0]
m2_ctrl = summary_df[summary_df['config'] == 'M2 Amount'].iloc[0]
print(f'M1 Amount: E3={e3_m1}% vs E4={m1_ctrl["total_return_pct"]}% (diff={abs(m1_ctrl["total_return_pct"]-e3_m1):.2f}pp)')
print(f'M2 Amount: E3={e3_m2}% vs E4={m2_ctrl["total_return_pct"]}% (diff={abs(m2_ctrl["total_return_pct"]-e3_m2):.2f}pp)')

# Common window
print('\n===== COMMON WINDOW (2020-2024) =====')
cw_rows = []
for _, row in summary_df.iterrows():
    suffix = row['config'].lower().replace(' ', '_').replace('+', '').replace('-', '')
    eq = pd.read_csv(os.path.join(OUT, f'e4_equity_{suffix}.csv'), parse_dates=['date'])
    cw = eq[(eq['date'] >= '2020-01-01') & (eq['date'] <= '2024-12-31')].copy().reset_index(drop=True)
    if len(cw) < 2:
        continue
    initial = cw['equity'].iloc[0]
    final = cw['equity'].iloc[-1]
    total_ret = (final/initial - 1) * 100
    n_years = (cw['date'].iloc[-1] - cw['date'].iloc[0]).days / 365.25
    cagr = ((final/initial)**(1/n_years) - 1) * 100 if n_years > 0 else 0
    cw['daily_ret'] = cw['equity'].pct_change()
    sharpe = (cw['daily_ret'].mean()*252) / (cw['daily_ret'].std()*np.sqrt(252)) if cw['daily_ret'].std() > 0 else 0
    cummax = cw['equity'].cummax()
    maxdd = ((cw['equity']/cummax - 1)*100).min()
    cw_rows.append({'config': row['config'], 'total_return_pct': round(total_ret,2),
                     'CAGR_pct': round(cagr,2), 'Sharpe': round(sharpe,4), 'MaxDD_pct': round(maxdd,2)})
    print(f'{row["config"]:12s}: TR={total_ret:>7.2f}% CAGR={cagr:>6.2f}% Sharpe={sharpe:>7.4f} MaxDD={maxdd:>7.2f}%')
pd.DataFrame(cw_rows).to_csv(os.path.join(OUT, 'e4_common_window_comparison.csv'), index=False)

# Full window
fw_rows = []
for _, row in summary_df.iterrows():
    fw_rows.append({'config': row['config'], 'total_return_pct': row['total_return_pct'],
                     'CAGR_pct': row['CAGR_pct'], 'Sharpe': row['Sharpe'], 'MaxDD_pct': row['MaxDD_pct']})
pd.DataFrame(fw_rows).to_csv(os.path.join(OUT, 'e4_full_window_comparison.csv'), index=False)

print('\nDONE E4.')
