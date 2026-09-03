#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
slot_contention_path_audit.py
=============================
PHASE P3.1 — SLOT CONTENTION & PATH-DEPENDENCE MECHANISM AUDIT  (PURE DIAGNOSTIC)

Question: why did the Discovery+Validation-passing ATR20_PCT ranking signal (P2/P3)
have almost no chance to act in the real K=3 portfolio, and why were the few
selection differences amplified by path-dependence into a ~ -490k..-506k divergence?

Red lines (all respected here):
  * 2025-01-01 .. 2026-08-25 CONFIRMATION stays CLOSED (engine runs use day_range=(0,N2024)).
  * No new predictor / composite / threshold / stop / exit / K / layer tuning / ML.
  * P3 Development classification C (NO USEFUL PORTFOLIO RANKING) is NOT modified.
  * Only the mechanism is explained.

Engine instrumentation added in atr_slot_allocation_p3.py is PURELY ADDITIVE
(day_log / exec_log / forced_first are None by default -> bit-identical decisions);
B0 parity vs the frozen _p3_cache/B0_bp10.pkl is asserted here.

Outputs (results/):
  p31_contention_funnel_daily.csv        per signal-day funnel (A..J)
  p31_contention_taxonomy.csv            day taxonomy (NO/SOFT/FULL_BLOCK/HELD/PENDING/EXEC_FAIL)
  p31_actionable_yearly.csv              ranking-actionable days by year
  p31_slot_saturation.csv                K=3 saturation
  p31_slot_occupancy_trades.csv          per-trade slot occupancy + blocked opportunities
  p31_top_slot_blockers.csv              top blockers (hold / blocked / capital)
  p31_capital_constraint.csv             empty-slot-but-no-cash days
  p31_swap_reconciliation.csv            direct swap events + equity divergence
  p31_independent_coverage.csv           independent-episode coverage per swap event
  p31_path_cascade.csv                   B0 vs B1 60-day cascade for the two big divergences
  p31_leave_one_swap.csv                 leave-one-swap attribution (6 forced runs)
  p31_slippage_path_diff.csv             10/20/50bp trade-list diffs (path discontinuity)
plus the two markdown notes.
"""
import os, sys, json
import numpy as np
import pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
sys.path.insert(0, ROOT)
from round51_audit import prepare_v51
sys.path.insert(0, REPO)
from atr_slot_allocation_p3 import build_atr_lookup, run_fast_multi_strict_c_atr, portfolio_metrics

RES = os.path.join(REPO, 'results')
os.makedirs(RES, exist_ok=True)

K = 3
LEVEL_CASH = 200_000
SLIP = 0.001  # 10bp frozen

# ---------------------------------------------------------------------------
# 0. Data prep (once)
# ---------------------------------------------------------------------------
days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51(
    limit_down_mode='correct', st_mode='pit')
N2024 = sum(1 for d in days if d <= pd.Timestamp('2024-12-31'))
dev_dates = [str(d.date()) for d in days[:N2024]]
date_to_idx = {str(days[i].date()): i for i in range(N2024)}
print(f'[prep] n_days={len(days)} dev_days={N2024} last_dev={dev_dates[-1]}', flush=True)

atr_lookup, nan_total = build_atr_lookup(days, D)
print(f'[atr] lookup built nan_cells={nan_total}', flush=True)

# frozen SECONDARY episodes (dev only)
fm = pd.read_csv(os.path.join(RES, 'fullmarket_episode_metrics.csv'))
fm['signal_date'] = pd.to_datetime(fm['signal_date'])
fm['entry_date'] = pd.to_datetime(fm['entry_date'])
fm['exit_date'] = pd.to_datetime(fm['exit_date'])
fm_dev = fm[fm['signal_date'] <= pd.Timestamp('2024-12-31')].copy()
fm_lookup = dict(zip(zip(fm['signal_date'], fm['ts_code']), fm['simple_return_pct']))
fm_mae = dict(zip(zip(fm['signal_date'], fm['ts_code']), fm['MAE_intraday_pct']))
print(f'[episodes] dev n={len(fm_dev)}', flush=True)

# cached P3 payloads
def load(v, bp):
    return pd.read_pickle(os.path.join(RES, '_p3_cache', f'{v}_bp{bp}.pkl'))

B0 = load('B0', 10); B1 = load('B1', 10); B2 = load('B2', 10)
B0_20 = load('B0', 20); B0_50 = load('B0', 50)
B1_20 = load('B1', 20); B1_50 = load('B1', 50)
B2_20 = load('B2', 20); B2_50 = load('B2', 50); B2_100 = load('B2', 100)

# ---------------------------------------------------------------------------
# 1. Instrumented B0 run + parity assert (P0 gate)
# ---------------------------------------------------------------------------
day_log, exec_log, ledger_i, cand_log_i = [], [], [], []
eq_i, tr_i, ac_i = run_fast_multi_strict_c_atr(
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
    K=K, top_n=10, max_levels=5, level_cash=LEVEL_CASH, initial_cash=1_000_000,
    slippage_bp=10, etf_enabled=False, day_range=(0, N2024), record_actions=True,
    entry_rank_mode='amount_top10', atr_lookup=atr_lookup,
    ledger=ledger_i, cand_log=cand_log_i, day_log=day_log, exec_log=exec_log)

cache_tr = B0['tr']; cache_eq = B0['eq']
parity_trades = sorted(zip(tr_i['ts_code'], tr_i['entry_date'])) == sorted(zip(cache_tr['ts_code'], cache_tr['entry_date']))
parity_eq = np.allclose(eq_i['equity'].values, cache_eq['equity'].values, atol=1e-6)
parity_actions = len(ac_i) == len(B0['ac'])
print(f'[parity] trades={parity_trades} equity={parity_eq} actions_len={parity_actions} '
      f'n_trades={len(tr_i)} pnl={tr_i["pnl"].sum():,.0f}', flush=True)
if not (parity_trades and parity_eq and parity_actions):
    print('P0 PARITY FAILURE — STOP', flush=True)
    sys.exit(1)

dayf = pd.DataFrame(day_log)
exf = pd.DataFrame(exec_log)

# funnel merge: per signal-date queue/execution info
queued_by_date = {}
for x in ledger_i:
    if x['state'] == 'QUEUED':
        queued_by_date[x['sig_date']] = queued_by_date.get(x['sig_date'], 0) + 1
exec_ex = exf[exf['outcome'] == 'EXECUTED'].copy()
exec_ex['sig_date'] = exec_ex['sig_date'].astype(str)
# next trading day after each signal date
def next_day(sd):
    i = date_to_idx.get(sd)
    if i is None or i + 1 >= N2024:
        return None
    return str(days[i + 1].date())
exec_ex['next_attempt'] = exec_ex['attempt_date']
# executed on the immediately following trading day
exec_next_map = {}
for _, r in exec_ex.iterrows():
    sd = str(r['sig_date']); nd = next_day(sd)
    if nd is not None and r['attempt_date'] == nd:
        exec_next_map[sd] = exec_next_map.get(sd, 0) + 1
exec_ever_map = exec_ex.groupby('sig_date').size().to_dict()

dayf['queued'] = dayf['date'].map(queued_by_date).fillna(0).astype(int)
dayf['executed_next'] = dayf['date'].map(exec_next_map).fillna(0).astype(int)
dayf['executed_ever'] = dayf['date'].map(exec_ever_map).fillna(0).astype(int)
dayf['year'] = pd.to_datetime(dayf['date']).dt.year

# ---- taxonomy per day ----
def classify(r):
    cand = int(r['top10_oversold'])
    av = int(r['available_slots'])
    q = int(r['queueable_candidates'])
    if cand == 0:
        return 'NO_OVERSOLD_IN_TOP10'
    if r['pending_conflicts'] > 0 and q == 0 and r['held_conflicts'] == 0:
        return 'PENDING_CONFLICT_ONLY'
    if r['held_conflicts'] > 0 and q == 0:
        return 'HELD_CONFLICT_ONLY'
    if av <= 0:
        return 'FULL_BLOCK'
    if q > av:
        return 'SOFT_CONTENTION'
    return 'NO_CONTENTION'
dayf['taxonomy'] = dayf.apply(classify, axis=1)
dayf['ranking_actionable'] = (dayf['available_slots'] >= 1) & (dayf['queueable_candidates'] > dayf['available_slots'])
dayf.to_csv(os.path.join(RES, 'p31_contention_funnel_daily.csv'), index=False)

# ---------------------------------------------------------------------------
# 2. Contention taxonomy
# ---------------------------------------------------------------------------
tax = dayf['taxonomy'].value_counts().to_frame('days').reset_index().rename(columns={'index': 'taxonomy'})
tot = len(dayf)
tax['pct_of_signal_days'] = tax['days'] / tot * 100
# event counts
tax_rows = []
for t, g in dayf.groupby('taxonomy'):
    tax_rows.append(dict(taxonomy=t, days=len(g), candidate_events=int(g['top10_oversold'].sum()),
                         pct_of_signal_days=len(g) / tot * 100))
taxdf = pd.DataFrame(tax_rows).sort_values('days', ascending=False)
taxdf.to_csv(os.path.join(RES, 'p31_contention_taxonomy.csv'), index=False)

# execution failure info (candidate queued but not executed next)
exsum = exf['outcome'].value_counts().to_frame('n').reset_index().rename(columns={'index': 'outcome'})
exsum['pct'] = exsum['n'] / len(exf) * 100
exsum.to_csv(os.path.join(RES, 'p31_exec_outcomes.csv'), index=False)

# ---------------------------------------------------------------------------
# 3. Actionable yearly
# ---------------------------------------------------------------------------
ay = dayf.groupby('year').agg(
    signal_days=('date', 'count'),
    actionable_days=('ranking_actionable', 'sum'),
    top10_oversold_days=('top10_oversold', lambda s: int((s > 0).sum())),
    full_block_days=('taxonomy', lambda s: int((s == 'FULL_BLOCK').sum())),
).reset_index()
ay['actionable_pct_of_signal_days'] = ay['actionable_days'] / ay['signal_days'] * 100
# trading days per year
tday_year = pd.Series(pd.to_datetime(dev_dates)).dt.year.value_counts().sort_index()
ay['trading_days'] = ay['year'].map(tday_year).astype(int)
ay['actionable_pct_of_trading_days'] = ay['actionable_days'] / ay['trading_days'] * 100
ay.to_csv(os.path.join(RES, 'p31_actionable_yearly.csv'), index=False)

# ---------------------------------------------------------------------------
# 4. Non-actionable decomposition (first reason per non-actionable signal day)
# ---------------------------------------------------------------------------
def primary_reason(r):
    if int(r['available_slots']) == 0:
        return 'no_empty_slot'
    if int(r['queueable_candidates']) == 0:
        if int(r['top10_oversold']) == 0:
            return 'no_oversold_in_top10'
        if int(r['held_conflicts']) > 0 and int(r['pending_conflicts']) == 0:
            return 'candidates_all_held'
        if int(r['pending_conflicts']) > 0:
            return 'pending_occupies'
        return 'other'
    return 'insufficient_competition'
nad = dayf[~dayf['ranking_actionable']].copy()
nad['reason'] = nad.apply(primary_reason, axis=1)
reason_sum = nad['reason'].value_counts().to_frame('days').reset_index().rename(columns={'index': 'reason'})
reason_sum['pct_of_non_actionable'] = reason_sum['days'] / max(1, len(nad)) * 100
reason_sum['pct_of_signal_days'] = reason_sum['days'] / tot * 100
reason_sum.to_csv(os.path.join(RES, 'p31_non_actionable_reasons.csv'), index=False)

# ---------------------------------------------------------------------------
# 5. K=3 saturation (B0 equity path + signal days)
# ---------------------------------------------------------------------------
eqb = B0['eq'].copy()
eqb['date'] = pd.to_datetime(eqb['date'])
sat = eqb.groupby('n_pos').size().reset_index(name='days')
sat['pct_of_trading_days'] = sat['days'] / len(eqb) * 100
sig_days = dayf[dayf['top10_oversold'] > 0]
sat2 = sig_days.groupby('available_slots').size().reset_index(name='days')
sat2['pct_of_signal_days'] = sat2['days'] / len(sig_days) * 100
sat2 = sat2.sort_values('available_slots')
sat2.to_csv(os.path.join(RES, 'p31_slot_saturation.csv'), index=False)
kfull_given_signal = float((sig_days['available_slots'] == 0).mean())
one_given_signal = float((sig_days['available_slots'] == 1).mean())
two_given_signal = float((sig_days['available_slots'] >= 2).mean())
with open(os.path.join(RES, 'p31_slot_saturation_stats.json'), 'w') as f:
    json.dump(dict(P_K_full_given_top10_signal=kfull_given_signal,
                   P_1slot_given_top10_signal=one_given_signal,
                   P_2plus_given_top10_signal=two_given_signal,
                   mean_available_slots_given_signal=float(sig_days['available_slots'].mean())), f, indent=2)

# ---------------------------------------------------------------------------
# 6. Capital constraint: empty slot but not enough cash for a new 200k layer
# ---------------------------------------------------------------------------
cap = eqb.copy()
cap['slot_available'] = cap['n_pos'] < K
# a new 200k layer needs >= ~200k cash (plus min commission; use 200_000 as conservative floor)
cap['capital_constrained'] = cap['slot_available'] & (cap['cash'] < LEVEL_CASH)
cap['has_top10_signal'] = cap['date'].dt.strftime('%Y-%m-%d').isin(set(dayf['date']))
cap_const_days = int(cap['capital_constrained'].sum())
cap_sig_days = int((cap['capital_constrained'] & cap['has_top10_signal']).sum())
cap.to_csv(os.path.join(RES, 'p31_capital_constraint.csv'), index=False)
with open(os.path.join(RES, 'p31_capital_constraint_stats.json'), 'w') as f:
    json.dump(dict(capital_constrained_days=cap_const_days,
                   pct_of_trading_days=cap_const_days / len(cap) * 100,
                   cap_constrained_signal_days=cap_sig_days), f, indent=2)

# ---------------------------------------------------------------------------
# 7. Slot occupancy per trade (B0) + blocked future opportunities
# ---------------------------------------------------------------------------
trb = B0['tr'].copy()
trb['entry_date'] = pd.to_datetime(trb['entry_date']); trb['exit_date'] = pd.to_datetime(trb['exit_date'])
trb['sig_date'] = pd.to_datetime(trb['sig_date'])
# capital used = sum of buy amounts for this trade from actions
acb = B0['ac'].copy()
acb['date'] = pd.to_datetime(acb['date'])
buy_amt = acb[acb['action'].isin(['INITIAL_ENTRY', 'ADD_POSITION'])].groupby('ts_code')['amount'].sum()
trb['capital_used'] = trb['ts_code'].map(buy_amt).fillna(0.0)
trb['MAE_intraday'] = trb.apply(lambda r: fm_mae.get((r['sig_date'], r['ts_code']), np.nan), axis=1)
# blocked future opportunities during the trade window: days with available_slots==0 (this trade holding a slot)
# and queueable candidates>0
dayf['date_dt'] = pd.to_datetime(dayf['date'])
blk = []
for _, r in trb.iterrows():
    win = dayf[(dayf['date_dt'] >= r['entry_date']) & (dayf['date_dt'] < r['exit_date'])]
    zero_slot = win[win['available_slots'] == 0]
    blk.append(dict(
        blocked_future_opportunities=int(zero_slot['queueable_candidates'].sum()),
        blocked_days=int(len(zero_slot)),
        top10_oversold_days=int((win['top10_oversold'] > 0).sum()),
    ))
blkdf = pd.DataFrame(blk)
trb = pd.concat([trb.reset_index(drop=True), blkdf], axis=1)
trb['slot_days'] = trb['hold_days']
trb.to_csv(os.path.join(RES, 'p31_slot_occupancy_trades.csv'), index=False)

# ---------------------------------------------------------------------------
# 8. Top slot blockers
# ---------------------------------------------------------------------------
top_hold = trb.nlargest(20, 'hold_days')[['ts_code', 'entry_date', 'hold_days', 'levels_used', 'capital_used', 'return_pct', 'MAE_intraday', 'blocked_future_opportunities']].copy()
top_blk = trb.nlargest(20, 'blocked_future_opportunities')[['ts_code', 'entry_date', 'hold_days', 'levels_used', 'capital_used', 'return_pct', 'MAE_intraday', 'blocked_future_opportunities']].copy()
top_cap = trb.nlargest(20, 'capital_used')[['ts_code', 'entry_date', 'hold_days', 'levels_used', 'capital_used', 'return_pct', 'MAE_intraday', 'blocked_future_opportunities']].copy()
for df in (top_hold, top_blk, top_cap):
    df['entry_date'] = df['entry_date'].dt.strftime('%Y-%m-%d')
top_hold['ranked_by'] = 'hold_days'
top_blk['ranked_by'] = 'blocked_future_opportunities'
top_cap['ranked_by'] = 'capital_used'
pd.concat([top_hold, top_blk, top_cap]).to_csv(os.path.join(RES, 'p31_top_slot_blockers.csv'), index=False)

# ---------------------------------------------------------------------------
# 9. Direct swap reconciliation (B0 vs B1 selection-changed events)
# ---------------------------------------------------------------------------
sw = pd.read_csv(os.path.join(RES, 'p3_selection_changed_events.csv'))
tr1 = B1['tr'].copy(); tr1['entry_date'] = pd.to_datetime(tr1['entry_date']); tr1['exit_date'] = pd.to_datetime(tr1['exit_date']); tr1['sig_date'] = pd.to_datetime(tr1['sig_date'])
eq1 = B1['eq'].copy(); eq1['date'] = pd.to_datetime(eq1['date'])
eq0 = B0['eq'].copy(); eq0['date'] = pd.to_datetime(eq0['date'])
eq0 = eq0.set_index('date'); eq1 = eq1.set_index('date')

def eq_at(eqdf, dt, h):
    """equity h trading days after dt (dev calendar)."""
    try:
        i = dev_dates.index(str(dt.date())) if str(dt.date()) in dev_dates else None
    except ValueError:
        i = None
    if i is None:
        return np.nan
    j = min(i + h, N2024 - 1)
    return float(eqdf.loc[pd.Timestamp(dev_dates[j]), 'equity'])

def port_ret(trdf, sd, tc):
    r = trdf[(trdf['sig_date'] == pd.Timestamp(sd)) & (trdf['ts_code'] == tc)]
    if len(r):
        return float(r['return_pct'].iloc[0]), float(r['pnl'].iloc[0]), str(r['entry_date'].iloc[0].date()), str(r['exit_date'].iloc[0].date()), int(r['levels_used'].iloc[0]), r['exit_type'].iloc[0]
    return (np.nan,) * 6

rows = []
for _, r in sw.iterrows():
    sd = r['signal_date']; b0 = r['baseline_stock']; a0 = r['atr_stock']
    b0p = port_ret(trb, sd, b0); a0p = port_ret(tr1, sd, a0)
    b0i = fm_lookup.get((pd.Timestamp(sd), b0), np.nan); a0i = fm_lookup.get((pd.Timestamp(sd), a0), np.nan)
    b0mae = fm_mae.get((pd.Timestamp(sd), b0), np.nan); a0mae = fm_mae.get((pd.Timestamp(sd), a0), np.nan)
    rows.append(dict(
        signal_date=sd, available_slots=int(r['n_slots']),
        baseline_stock=b0, atr_stock=a0,
        baseline_atr_pct=r['baseline_atr_pct'], atr_stock_atr_pct=r['atr_stock_atr_pct'],
        baseline_ind_ret=b0i, atr_ind_ret=a0i,
        baseline_ind_mae=b0mae, atr_ind_mae=a0mae,
        baseline_port_ret=b0p[0], atr_port_ret=a0p[0],
        baseline_port_pnl=b0p[1], atr_port_pnl=a0p[1],
        baseline_entry=b0p[2], atr_entry=a0p[2],
        baseline_exit=b0p[3], atr_exit=a0p[3],
        baseline_levels=b0p[4], atr_levels=a0p[4],
        baseline_exit_type=b0p[5], atr_exit_type=a0p[5],
        eq_div_7d=eq_at(eq1, pd.Timestamp(sd), 7) - eq_at(eq0, pd.Timestamp(sd), 7),
        eq_div_20d=eq_at(eq1, pd.Timestamp(sd), 20) - eq_at(eq0, pd.Timestamp(sd), 20),
        eq_div_60d=eq_at(eq1, pd.Timestamp(sd), 60) - eq_at(eq0, pd.Timestamp(sd), 60),
    ))
swdf = pd.DataFrame(rows)
swdf.to_csv(os.path.join(RES, 'p31_swap_reconciliation.csv'), index=False)

# ---------------------------------------------------------------------------
# 10. Independent coverage table
# ---------------------------------------------------------------------------
cov_rows = []
for _, r in sw.iterrows():
    sd = pd.Timestamp(r['signal_date'])
    for tag, tc in [('baseline', r['baseline_stock']), ('atr', r['atr_stock'])]:
        in_fm = (pd.Timestamp(sd), tc) in fm_lookup
        cause = ''
        if not in_fm:
            sub = fm[fm['ts_code'] == tc]
            ov = sub[(sub['entry_date'] <= sd) & (sub['exit_date'] >= sd)]
            if len(ov):
                o = ov.iloc[0]
                cause = f"overlap_held_episode(sig={o['signal_date'].date()} entry={o['entry_date'].date()} exit={o['exit_date'].date()} ret={o['simple_return_pct']:.1f})"
            else:
                cause = 'not_in_frozen_population'
        cov_rows.append(dict(signal_date=str(r['signal_date']), side=tag, ts_code=tc,
                             in_frozen_independent=in_fm,
                             independent_ret=fm_lookup.get((sd, tc), np.nan),
                             missing_cause=cause))
covdf = pd.DataFrame(cov_rows)
covdf.to_csv(os.path.join(RES, 'p31_independent_coverage.csv'), index=False)

# ---------------------------------------------------------------------------
# 11. Path cascade (2021-05-24 & 2021-11-16) + reconvergence
# ---------------------------------------------------------------------------
def holdings_on(trdf, dt):
    d = pd.Timestamp(dt)
    return set(trdf[(trdf['entry_date'] <= d) & (trdf['exit_date'] > d)]['ts_code'])

def cascade(sd_str):
    sd = pd.Timestamp(sd_str)
    idx = date_to_idx[sd_str]
    end = dev_dates[min(idx + 60, N2024 - 1)]
    days_in = [dev_dates[i] for i in range(idx, min(idx + 61, N2024))]
    ev0 = B0['ac'].copy(); ev0['date'] = pd.to_datetime(ev0['date'])
    ev1 = B1['ac'].copy(); ev1['date'] = pd.to_datetime(ev1['date'])
    w0 = ev0[(ev0['date'] >= sd) & (ev0['date'] <= pd.Timestamp(end))][['date', 'ts_code', 'action', 'level', 'shares', 'price']]
    w1 = ev1[(ev1['date'] >= sd) & (ev1['date'] <= pd.Timestamp(end))][['date', 'ts_code', 'action', 'level', 'shares', 'price']]
    # find first day holdings differ and reconvergence
    first_diff = None; reconv_day = None
    for i, ds in enumerate(days_in):
        h0 = holdings_on(trb, ds); h1 = holdings_on(tr1, ds)
        if h0 != h1:
            if first_diff is None:
                first_diff = ds
        elif first_diff is not None and reconv_day is None and i > 0:
            reconv_day = ds
    rows = []
    for ds in days_in:
        h0 = holdings_on(trb, ds); h1 = holdings_on(tr1, ds)
        rows.append(dict(date=ds, b0_holdings='|'.join(sorted(h0)), b1_holdings='|'.join(sorted(h1)),
                         b0_eq=eq_at(eq0, pd.Timestamp(ds), 0), b1_eq=eq_at(eq1, pd.Timestamp(ds), 0)))
    rdf = pd.DataFrame(rows)
    rdf.to_csv(os.path.join(RES, f'p31_path_cascade_{sd_str}.csv'), index=False)
    w0[['date', 'ts_code', 'action', 'level', 'shares', 'price']].to_csv(
        os.path.join(RES, f'p31_path_cascade_{sd_str}_events_b0.csv'), index=False)
    w1[['date', 'ts_code', 'action', 'level', 'shares', 'price']].to_csv(
        os.path.join(RES, f'p31_path_cascade_{sd_str}_events_b1.csv'), index=False)
    return dict(signal_date=sd_str, first_holding_diff=first_diff, reconverged_day=reconv_day,
                never_reconverged=(reconv_day is None),
                b0_events_60d=int(len(w0)), b1_events_60d=int(len(w1)),
                b0_trades_entered_60d=int(((trb['entry_date'] >= sd) & (trb['entry_date'] <= pd.Timestamp(end))).sum()),
                b1_trades_entered_60d=int(((tr1['entry_date'] >= sd) & (tr1['entry_date'] <= pd.Timestamp(end))).sum()),
                eq_div_7d=eq_at(eq1, sd, 7) - eq_at(eq0, sd, 7),
                eq_div_20d=eq_at(eq1, sd, 20) - eq_at(eq0, sd, 20),
                eq_div_60d=eq_at(eq1, sd, 60) - eq_at(eq0, sd, 60))

casc = pd.DataFrame([cascade('2021-05-24'), cascade('2021-11-16')])
casc.to_csv(os.path.join(RES, 'p31_path_cascade.csv'), index=False)

# ---------------------------------------------------------------------------
# 12. Leave-one-swap (6 forced-first runs; path endogenous)
# ---------------------------------------------------------------------------
los = []
for _, r in sw.iterrows():
    sd = r['signal_date']
    forced = {sd: [r['atr_stock']]}
    ledg, candl = [], []
    eqf, trf, acf = run_fast_multi_strict_c_atr(
        days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
        K=K, top_n=10, max_levels=5, level_cash=LEVEL_CASH, initial_cash=1_000_000,
        slippage_bp=10, etf_enabled=False, day_range=(0, N2024), record_actions=False,
        entry_rank_mode='amount_top10', atr_lookup=atr_lookup,
        ledger=ledg, cand_log=candl, forced_first=forced)
    # was the swap actually applied? (atr stock queued / baseline stock blocked on that date)
    queued_on = [x['ts_code'] for x in ledg if x['sig_date'] == sd and x['state'] == 'QUEUED']
    blk_on = [x['ts_code'] for x in ledg if x['sig_date'] == sd and x['state'] == 'BLOCKED_K']
    delta_pnl = float(trf['pnl'].sum() - trb['pnl'].sum())
    los.append(dict(signal_date=sd, forced_atr_stock=r['atr_stock'], baseline_stock=r['baseline_stock'],
                    queued_on_date=','.join(queued_on), blocked_k_on_date=','.join(blk_on),
                    counterfactual_pnl=float(trf['pnl'].sum()),
                    baseline_pnl=float(trb['pnl'].sum()),
                    delta_pnl=delta_pnl))
losdf = pd.DataFrame(los)
losdf.to_csv(os.path.join(RES, 'p31_leave_one_swap.csv'), index=False)

# ---------------------------------------------------------------------------
# 13. Slippage path discontinuity (trade-list diffs)
# ---------------------------------------------------------------------------
def tset(p):
    return set(zip(p['tr']['ts_code'], p['tr']['entry_date']))

spr = []
def pair(v, bpl, bph):
    pl, ph = load(v, bpl), load(v, bph)
    kl, kh = tset(pl), tset(ph)
    trl, trh = pl['tr'], ph['tr']
    only_l = kl - kh; only_h = kh - kl
    # pnl change on common trades
    chg = []
    for k in kl & kh:
        rl = trl[(trl['ts_code'] == k[0]) & (trl['entry_date'] == k[1])]['pnl'].iloc[0]
        rh = trh[(trh['ts_code'] == k[0]) & (trh['entry_date'] == k[1])]['pnl'].iloc[0]
        chg.append((abs(rh - rl), k, rl, rh))
    chg = sorted(chg, reverse=True)
    return dict(version=v, bp_low=bpl, bp_high=bph,
                n_low=len(kl), n_high=len(kh),
                only_low=len(only_l), only_high=len(only_h),
                common=len(kl & kh),
                pnl_low=float(trl['pnl'].sum()), pnl_high=float(trh['pnl'].sum()),
                top_chg=[dict(ts=k[0], entry=str(k[1]), pnl_low=round(rl, 1), pnl_high=round(rh, 1)) for _, k, rl, rh in chg[:6]])

spr_rows = [pair('B0', 10, 20), pair('B0', 20, 50), pair('B1', 10, 20), pair('B1', 20, 50), pair('B2', 10, 20), pair('B2', 20, 50), pair('B2', 50, 100)]
sprdf = pd.DataFrame([{k: (json.dumps(v) if isinstance(v, list) else v) for k, v in d.items()} for d in spr_rows])
sprdf.to_csv(os.path.join(RES, 'p31_slippage_path_diff.csv'), index=False)

# ---------------------------------------------------------------------------
# 14. B2 liquidity risk summary (NON-DEPLOYABLE evidence)
# ---------------------------------------------------------------------------
tr2 = B2['tr'].copy(); tr2['sig_date'] = pd.to_datetime(tr2['sig_date'])
sel_amt = []
for _, r in tr2.iterrows():
    j = D[pd.Timestamp(r['sig_date'])]['pos'].get(r['ts_code'])
    if j is not None:
        sel_amt.append(float(D[pd.Timestamp(r['sig_date'])]['amount'][j]))
    else:
        sel_amt.append(np.nan)
tr2['signal_day_amount'] = sel_amt
tr2['layer_amount_ratio_pct'] = tr2['signal_day_amount'] / LEVEL_CASH * 100
liq = tr2['signal_day_amount'].describe(percentiles=[.05, .1, .5, .9, .95, .99]).to_dict()
liq['layer_pct_P50'] = float(tr2['layer_amount_ratio_pct'].median())
liq['layer_pct_P90'] = float(tr2['layer_amount_ratio_pct'].quantile(.90))
liq['layer_pct_P95'] = float(tr2['layer_amount_ratio_pct'].quantile(.95))
liq['layer_pct_P99'] = float(tr2['layer_amount_ratio_pct'].quantile(.99))
pd.DataFrame([liq]).to_csv(os.path.join(RES, 'p31_b2_liquidity_risk.csv'), index=False)

# ---------------------------------------------------------------------------
# 15. Summary JSON for the report
# ---------------------------------------------------------------------------
total_signal_days = int(tot)
actionable = int(dayf['ranking_actionable'].sum())
npos3_days = int((B0['eq']['n_pos'] == 3).sum())
npos3_pct = npos3_days / len(B0['eq']) * 100
summary = dict(
    dev_signal_days=total_signal_days,
    ranking_actionable_days=actionable,
    ranking_actionable_pct_signal=actionable / total_signal_days * 100,
    non_actionable_reasons=reason_sum.to_dict('records'),
    taxonomy=taxdf.to_dict('records'),
    P_Kfull_given_signal=kfull_given_signal,
    n_pos3_days=npos3_days, n_pos3_pct=npos3_pct,
    capital_constrained_days=cap_const_days,
    capital_constrained_signal_days=cap_sig_days,
    swap_events=int(len(swdf)),
    coverage_events=dict(full=0, partial=0, none=0),
    leave_one_swap=losdf.to_dict('records'),
    cascades=casc.to_dict('records'),
    b0_pnl=float(trb['pnl'].sum()), b1_pnl=float(tr1['pnl'].sum()),
)
# coverage per event (both sides present = full, one = partial, none = none)
for _, r in covdf.groupby('signal_date'):
    n = int((~r['in_frozen_independent']).sum())
    if n == 0:
        summary['coverage_events']['full'] += 1
    elif n == 1:
        summary['coverage_events']['partial'] += 1
    else:
        summary['coverage_events']['none'] += 1
with open(os.path.join(RES, 'p31_mechanism_summary.json'), 'w') as f:
    json.dump(summary, f, indent=2, default=str)

print('DONE', flush=True)
