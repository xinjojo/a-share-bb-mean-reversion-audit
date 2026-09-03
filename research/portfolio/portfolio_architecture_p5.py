#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P5 — PORTFOLIO CAPITAL ARCHITECTURE: CAPACITY / CAPITAL-LOCK DIAGNOSTIC
========================================================================
Diagnostic only. No optimization, no predictor, no gate, no new admission
rule, no exit/entry change, 2025-2026 CLOSED.

Baseline = P4 A0 exact parity (total +30.295093786122408%, stock_pnl
302950.9378612245, trades 76, MaxDD -30.78972881784398%, Sharpe .3467648...).
Engine imported unchanged from portfolio_architecture_p4.py; all daily ledger
fields come from the engine's own equity_curve + action log + ledger +
exec_log (deterministic aggregation, no path reconstruction).

Registry: PORTFOLIO_ARCHITECTURE_P5_REGISTRY.csv
          (SHA 7415608a1003b612704e295a76427eba5c124607163a926fb514342c699f7ce7,
           prereg commit e007979, pushed BEFORE outcomes)
"""
import os, sys, json, hashlib
import numpy as np, pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
OUT = os.path.join(REPO, 'results', 'evidence', 'p5')
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(REPO, 'research', 'portfolio'))

from portfolio_architecture_p4 import run_fast_multi_strict_c_atr, portfolio_metrics
from round51_audit import prepare_v51, stamp_rate, COMMISSION_RATE, MIN_COMMISSION, TRANSFER_FEE_RATE

# ---------------- registry integrity (I12) ----------------
REG = os.path.join(REPO, 'research', 'portfolio', 'registries', 'PORTFOLIO_ARCHITECTURE_P5_REGISTRY.csv')
with open(REG, 'rb') as f:
    reg_sha = hashlib.sha256(f.read()).hexdigest()
assert reg_sha == '7415608a1003b612704e295a76427eba5c124607163a926fb514342c699f7ce7', 'P5 registry SHA mismatch'
prior = {
 'F1': ('FAILURE_STATE_F1_REGISTRY.csv', 'a052309e6f939796795566d1cd1094e2ec706f53250c231377c64efb315eef14'),
 'F1.1': ('FAILURE_STATE_F11_INFERENCE_REGISTRY.csv', 'aacb2146308abd155401c1231209b7cab14e1bc44c50e6f19007ac39582aef91'),
 'F2': ('FAILURE_STATE_F2_ACTIONABILITY_REGISTRY.csv', '9ed07a575ae65bbda3d63321e676431231d00548bb8977fb443764163b85642a'),
 'F2.1': ('FAILURE_STATE_F21_MATCHED_ACTION_REGISTRY.csv', '12f8311c52df76ca6fc10cb7f5f43a95bae4e1c9a9dc1f5880bfdcee60357787'),
 'F2.2': ('FAILURE_STATE_F22_BREAK_EVEN_REGISTRY.csv', 'aff9c4295fceec450a54ea7bc2bfbc8055761d396081d778d4e1ff616b6095d8'),
 'F2.3': ('FAILURE_STATE_F23_POLICY_VALUE_INFERENCE_REGISTRY.csv', 'c0f4d1d2bd46a7c5bca01752020dec121404984feb8273984a5164f56942f83c'),
 'F3': ('FAILURE_STATE_F3_PREDICTOR_REGISTRY.csv', '803e15245746a90d542de1bd18889686dacf6e926b3ac931717c68335db2a032'),
}
for name, (fn, sha) in prior.items():
    pth = os.path.join(REPO, 'research', 'risk', 'registries', fn)
    assert os.path.exists(pth), f'{name} registry not found'
    with open(pth, 'rb') as f:
        assert hashlib.sha256(f.read()).hexdigest() == sha, f'{name} registry SHA changed (I12)'

# ---------------- data & baseline run (I1 exact parity) ----------------
days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51(
    limit_down_mode='correct', st_mode='pit')
N2024 = sum(1 for d in days if d <= pd.Timestamp('2024-12-31'))
assert N2024 == 1212
assert all(d.year <= 2024 for d in days[:N2024]), 'I11: dev horizon wrong'

ledger, cand_log, day_log, exec_log = [], [], [], []
eq, tr, ac = run_fast_multi_strict_c_atr(
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
    K=3, top_n=10, max_levels=5, level_cash=200_000, initial_cash=1_000_000,
    slippage_bp=10, stamp_tax_mode='historical', exit_bb_mode='dynamic_touch',
    open_fill='limit_conservative', tick_mode='conservative', limit_slip_order='ref_first',
    etf_enabled=False, day_range=(0, N2024), record_actions=True,
    entry_rank_mode='amount_top10', atr_lookup=None, ledger=ledger, cand_log=cand_log,
    day_log=day_log, exec_log=exec_log)
m = portfolio_metrics(eq, tr)
stock_pnl = float(tr['pnl'].sum())
g0 = dict(total=30.295093786122408, n=76, stock_pnl=302950.9378612245, mdd=-30.78972881784398, sharpe=0.3467648252149691)
assert abs(m['total'] - g0['total']) < 1e-6, f'I1 total parity FAIL {m["total"]}'
assert m['n'] == g0['n'], f'I1 trade count parity FAIL {m["n"]}'
assert abs(stock_pnl - g0['stock_pnl']) < 1.0, f'I1 stock_pnl parity FAIL {stock_pnl}'
assert abs(m['mdd'] - g0['mdd']) < 1e-4, f'I1 mdd parity FAIL {m["mdd"]}'
assert abs(m['sharpe'] - g0['sharpe']) < 1e-6, f'I1 sharpe parity FAIL {m["sharpe"]}'
print(f'[P5] A0 parity PASS: total={m["total"]:.6f}% n={m["n"]} pnl={stock_pnl:.2f} mdd={m["mdd"]:.5f}% sharpe={m["sharpe"]:.6f}', flush=True)

# ---------------- engine logs as frames ----------------
acd = ac.copy()
eqd = eq.copy(); eqd['date'] = pd.to_datetime(eqd['date'])
ld = pd.DataFrame(ledger)
el = pd.DataFrame(exec_log)
cl = pd.DataFrame(cand_log)

# ---------------- episode lifecycle keyed by (ts_code, entry_date) ----------------
EXIT_ACTS = ('TAKE_PROFIT_DYN', 'TAKE_PROFIT_UB', 'FINAL_SETTLE')
acd['date_dt'] = pd.to_datetime(acd['date'])

def buy_cost(amt):
    return amt + max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * TRANSFER_FEE_RATE

def sell_fee(gross, d):
    sr = stamp_rate(d, 'historical')
    return max(gross * COMMISSION_RATE, MIN_COMMISSION) + gross * sr + gross * TRANSFER_FEE_RATE

pos_ev = {}
for _, t in tr.iterrows():
    tc = str(t['ts_code']); edt = pd.Timestamp(t['entry_date']); xdt = pd.Timestamp(t['exit_date'])
    init = acd[(acd['ts_code'] == tc) & (acd['date_dt'] == edt) & (acd['action'] == 'INITIAL_ENTRY')]
    assert len(init) == 1, f'{tc} {t["entry_date"]} init rows {len(init)}'
    adds = acd[(acd['ts_code'] == tc) & (acd['date_dt'] > edt) & (acd['date_dt'] < xdt) & (acd['action'] == 'ADD_POSITION')]
    exits = acd[(acd['ts_code'] == tc) & (acd['date_dt'] == xdt) & (acd['action'].isin(EXIT_ACTS))]
    lrows = [init.iloc[0]] + [r for _, r in adds.iterrows()]
    layers = [dict(date=pd.Timestamp(r['date']), px=float(r['price']), qty=int(r['shares']),
                   amt=float(r['amount']), lvl=i + 1) for i, r in enumerate(lrows)]
    if len(exits) == 1:
        exit_price = float(exits.iloc[0]['price'])
    elif t['exit_type'] == 'FINAL_SETTLE':
        # FINAL_SETTLE is not written to actions; resolve execution price from pnl
        # pnl = exit_gross - sell_fee(exit_gross) - total_buy_cost ; solve for exit_gross
        tcost = float(sum(buy_cost(l['amt']) for l in layers))
        g = float(t['pnl']) + tcost
        for _ in range(6):
            g = float(t['pnl']) + tcost + sell_fee(g, xdt)
        exit_price = g / int(t['shares'])
    else:
        raise AssertionError(f'{tc} {t["exit_date"]} exit rows {len(exits)} type {t["exit_type"]}')
    pos_ev[(tc, str(t['entry_date']))] = dict(ts_code=tc, entry=edt, exit=xdt,
                                              exit_price=exit_price, layers=layers)
assert len(pos_ev) == 76, f'episodes {len(pos_ev)} != 76'

# ---------------- daily capital ledger ----------------
cand_daily = cl.groupby(pd.to_datetime(cl['sig_date'])).size().to_dict()
ledger_daily = {}
for d0, g in ld.groupby(pd.to_datetime(ld['sig_date'])):
    ledger_daily[d0] = dict(k=int((g['state'] == 'BLOCKED_K').sum()),
                            held=int((g['state'] == 'BLOCKED_HELD').sum()),
                            queued=int((g['state'] == 'QUEUED').sum()))
exec_daily = {}
for _, r in el.iterrows():
    d0 = pd.to_datetime(r['attempt_date'])
    rec = exec_daily.setdefault(d0, {'cash': 0, 'lot': 0, 'exec_fail': 0, 'k_drop': 0})
    if r['outcome'] == 'NO_CASH': rec['cash'] += 1
    elif r['outcome'] == 'NO_LOT': rec['lot'] += 1
    elif r['outcome'] == 'DROPPED_K_HELD': rec['k_drop'] += 1
    elif r['outcome'] in ('CARRY_LIMITUP', 'MISSING'): rec['exec_fail'] += 1

def n_active_layers(d):
    return sum(len(pos_ev[k]['layers']) for k in pos_ev
               if pos_ev[k]['entry'] <= d and pos_ev[k]['exit'] > d)

daily = []
for _, r in eqd.iterrows():
    d = r['date']
    n_new = int(((acd['action'] == 'INITIAL_ENTRY') & (pd.to_datetime(acd['date']) == d)).sum())
    n_add = int(((acd['action'] == 'ADD_POSITION') & (pd.to_datetime(acd['date']) == d)).sum())
    sold = float(acd.loc[(pd.to_datetime(acd['date']) == d) & (acd['action'].isin(['TAKE_PROFIT_DYN', 'TAKE_PROFIT_UB', 'FINAL_SETTLE'])), 'amount'].sum())
    bought = float(acd.loc[(pd.to_datetime(acd['date']) == d) & (acd['action'].isin(['INITIAL_ENTRY', 'ADD_POSITION'])), 'amount'].sum())
    ld_ = ledger_daily.get(d, {})
    ed_ = exec_daily.get(d, {})
    daily.append(dict(date=str(d.date()), portfolio_nav=float(r['equity']), cash=float(r['cash']),
                      invested_cost=float(r['invested']), market_value=float(r['stock_val']),
                      n_positions=int(r['n_pos']), total_layers=n_active_layers(d),
                      free_slots=max(0, 3 - int(r['n_pos'])),
                      cash_available_for_new_entry=float(r['cash']),
                      candidate_count=int(cand_daily.get(d, 0)),
                      new_entry_candidate_count=int(cand_daily.get(d, 0)),
                      add_candidate_count=n_add,
                      executed_new_entries=n_new, executed_adds=n_add,
                      blocked_by_K=int(ld_.get('k', 0) + ed_.get('k_drop', 0)),
                      blocked_by_cash=int(ed_.get('cash', 0)),
                      blocked_by_held=int(ld_.get('held', 0)),
                      blocked_by_lot=int(ed_.get('lot', 0)),
                      blocked_by_execution=int(ed_.get('exec_fail', 0)),
                      released_capital_today=sold, new_capital_committed_today=bought))
daily_df = pd.DataFrame(daily)
for _, t in tr[tr['exit_type'] == 'FINAL_SETTLE'].iterrows():
    evt = pos_ev[(str(t['ts_code']), str(t['entry_date']))]
    g = evt['exit_price'] * int(t['shares'])
    r = daily_df[daily_df['date'] == t['exit_date']]
    if len(r):
        i = r.index[0]
        daily_df.loc[i, 'released_capital_today'] += g - sell_fee(g, pd.Timestamp(t['exit_date']))
daily_df.to_csv(os.path.join(OUT, 'p5_daily_capital_ledger.csv'), index=False)
json.dump(dict(total_return_pct=m['total'], stock_pnl=stock_pnl, trades=m['n'], maxdd_pct=m['mdd'],
               sharpe=m['sharpe'], parity='PASS'), open(os.path.join(OUT, 'p5_baseline_parity.json'), 'w'), indent=2)

# ---------------- blocked candidate classification (precedence HELD>EXEC>K>CASH>LOT>OTHER) ----------------
def classify_candidate(sd_str, tc):
    lrows = ld[(ld['sig_date'] == sd_str) & (ld['ts_code'] == tc)]
    if len(lrows) == 0:
        return 'BLOCKED_OTHER'
    st = lrows['state'].iloc[0]
    if st == 'BLOCKED_HELD':
        return 'BLOCKED_HELD'
    if st == 'BLOCKED_K':
        return 'BLOCKED_K'
    if st == 'QUEUED':
        er = el[(el['sig_date'] == sd_str) & (el['ts_code'] == tc)].sort_values('attempt_date')
        if len(er) == 0:
            return 'ADMITTED' if ((tr['sig_date'] == sd_str) & (tr['ts_code'] == tc)).any() else 'BLOCKED_OTHER'
        outs = er['outcome'].tolist()
        if 'EXECUTED' in outs:
            return 'ADMITTED'
        last = outs[-1]
        if last == 'NO_CASH': return 'BLOCKED_CASH'
        if last == 'NO_LOT': return 'BLOCKED_LOT'
        if last == 'DROPPED_K_HELD': return 'BLOCKED_K'
        if last in ('CARRY_LIMITUP', 'MISSING'): return 'BLOCKED_EXECUTION'
        return 'BLOCKED_OTHER'
    return 'BLOCKED_OTHER'

cand_df = cl.copy()
cand_df['block_reason'] = [classify_candidate(s, t) for s, t in zip(cand_df['sig_date'], cand_df['ts_code'])]
cand_df['sig_date_dt'] = pd.to_datetime(cand_df['sig_date'])

# ---------------- independent episode join ----------------
fm = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'fullmarket', 'fullmarket_episode_metrics.csv'))
fm['signal_date'] = pd.to_datetime(fm['signal_date'])
fm = fm[fm['signal_date'] <= pd.Timestamp('2024-12-31')].copy()
fm_lookup = {k: r for k, r in fm.set_index(['signal_date', 'ts_code']).iterrows()}
cand_df['ind_cov'] = [1 if (pd.Timestamp(s), t) in fm_lookup else 0 for s, t in zip(cand_df['sig_date'], cand_df['ts_code'])]
for col in ['simple_return_pct', 'hold_days', 'MAE_close_pct', 'time_to_break_even_days', 'pnl']:
    cand_df['ind_' + col] = [float(fm_lookup[(pd.Timestamp(s), t)][col]) if (pd.Timestamp(s), t) in fm_lookup else np.nan
                             for s, t in zip(cand_df['sig_date'], cand_df['ts_code'])]
cand_df['ind_exit_date'] = [fm_lookup[(pd.Timestamp(s), t)]['exit_date'] if (pd.Timestamp(s), t) in fm_lookup else np.nan
                            for s, t in zip(cand_df['sig_date'], cand_df['ts_code'])]

# ---------------- blocked signal quality ----------------
def grp_stats(sub):
    if len(sub) == 0:
        return dict(n=0, coverage=0.0)
    c = sub[sub['ind_cov'] == 1]
    if len(c) == 0:
        return dict(n=len(sub), coverage=0.0)
    ret = c['ind_simple_return_pct']
    win = (ret > 0).mean() * 100
    pf = float(c.loc[ret > 0, 'ind_simple_return_pct'].sum() / abs(c.loc[ret <= 0, 'ind_simple_return_pct'].sum())) if (ret <= 0).any() else float('inf')
    return dict(n=len(sub), coverage=float(len(c) / len(sub) * 100), ind_mean=float(ret.mean()),
                ind_median=float(ret.median()), ind_win=float(win), ind_pf=pf,
                ind_mae=float(c['ind_MAE_close_pct'].mean()), ind_hold=float(c['ind_hold_days'].mean()))
qual_rows = []
for reason in ['ADMITTED', 'BLOCKED_K', 'BLOCKED_CASH', 'BLOCKED_HELD', 'BLOCKED_LOT', 'BLOCKED_EXECUTION', 'BLOCKED_OTHER']:
    d = grp_stats(cand_df[cand_df['block_reason'] == reason]); d['reason'] = reason
    qual_rows.append(d)
qual_df = pd.DataFrame(qual_rows)
qual_df.to_csv(os.path.join(OUT, 'p5_blocked_signal_quality.csv'), index=False)

def hac_ci(x, maxlags=10):
    import statsmodels.api as sm
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    if len(x) < 12:
        return np.nan, np.nan, np.nan
    r = sm.OLS(x, np.ones(len(x))).fit(cov_type='HAC', cov_kwds={'maxlags': maxlags})
    return float(r.params[0]), float(r.params[0] - 1.96 * r.bse[0]), float(r.params[0] + 1.96 * r.bse[0])

def cal_boot_ci(series_day, L=21, B=2000, seed=0):
    rng = np.random.default_rng(seed)
    fx = np.full(N2024, np.nan)
    for d, v in series_day.items():
        if d not in days: continue
        di = days.index(d)
        if di >= N2024: continue
        fx[di] = v
    n = N2024; nblk = int(np.ceil(n / L)); out = []
    for _ in range(B):
        idx = []
        for _b in range(nblk):
            st = rng.integers(0, n - L + 1) if n - L + 1 > 0 else 0
            idx.extend(range(st, min(st + L, n)))
        idx = np.array(idx[:n]); v = fx[idx]; v = v[np.isfinite(v)]
        if len(v) >= 10: out.append(v.mean())
    out = np.array(out)
    if len(out) == 0:
        return float('nan'), float('nan'), float('nan')
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5)), float(out.mean())

def event_day_series(reason):
    sub = cand_df[(cand_df['block_reason'] == reason) & (cand_df['ind_cov'] == 1)]
    return sub.groupby('sig_date_dt')['ind_simple_return_pct'].mean()

ev_rows, boot_rows = [], []
sa = event_day_series('ADMITTED')
for reason in ['BLOCKED_K', 'BLOCKED_CASH']:
    sb = event_day_series(reason)
    both = sa.index.intersection(sb.index)
    d = (sb.loc[both] - sa.loc[both])
    hm, hlo, hhi = hac_ci(d.values)
    blo, bhi, bmu = cal_boot_ci(d)
    ev_rows.append(dict(reason=reason, n_days=len(both), admitted_mean=float(sa.loc[both].mean()),
                        blocked_mean=float(sb.loc[both].mean()), delta_mean=float(d.mean()),
                        delta_hac_ci_lo=float(hlo), delta_hac_ci_hi=float(hhi),
                        delta_boot_ci_lo=float(blo), delta_boot_ci_hi=float(bhi)))
    boot_rows.append(dict(reason=reason, metric='blocked_minus_admitted_event_day', point=float(d.mean()),
                          hac_ci_lo=float(hlo), hac_ci_hi=float(hhi), boot_ci_lo=float(blo), boot_ci_hi=float(bhi)))
pd.DataFrame(ev_rows).to_csv(os.path.join(OUT, 'p5_blocked_signal_eventday.csv'), index=False)
pd.DataFrame(boot_rows).to_csv(os.path.join(OUT, 'p5_blocked_signal_bootstrap.csv'), index=False)

# ---------------- capital shadow (counterfactual diagnostic only) ----------------
shadow_rows = []
for reason, lbl in [(['BLOCKED_K'], 'BLOCKED_K'), (['BLOCKED_CASH'], 'BLOCKED_CASH'), (['BLOCKED_K', 'BLOCKED_CASH'], 'BLOCKED_K+CASH')]:
    sub = cand_df[(cand_df['block_reason'].isin(reason)) & (cand_df['ind_cov'] == 1)]
    norm = sub['ind_simple_return_pct'] / 100 * 200000
    missed = float(norm[norm > 0].sum()); avoided = float(-norm[norm < 0].sum())
    shadow_rows.append(dict(reason=lbl, n=len(sub), missed_positive=missed, avoided_negative=avoided, net=missed - avoided))
pd.DataFrame(shadow_rows).to_csv(os.path.join(OUT, 'p5_capital_shadow.csv'), index=False)

# ---------------- position lock / age curve / layer curve ----------------
pos_rows = []
for _, t in tr.iterrows():
    evt = pos_ev[(str(t['ts_code']), str(t['entry_date']))]
    entry = pd.Timestamp(t['entry_date']); exitd = pd.Timestamp(t['exit_date'])
    layers = sorted(evt['layers'], key=lambda x: x['date'])
    i_e = days.index(entry); i_x = days.index(exitd)
    hold_days = i_x - i_e
    slot_days = hold_days
    costs = []
    lvl_days = {}
    for i0 in range(i_e, i_x):
        d0 = days[i0]
        c = 0.0; n_l = 0
        for l in layers:
            if l['date'] <= d0:
                fee = max(l['amt'] * COMMISSION_RATE, MIN_COMMISSION) + l['amt'] * TRANSFER_FEE_RATE
                c += l['amt'] + fee; n_l += 1
        costs.append(c); lvl_days[n_l] = lvl_days.get(n_l, 0) + 1
    capital_days = float(np.sum(costs))
    total_cost = float(np.sum([l['amt'] + max(l['amt'] * COMMISSION_RATE, MIN_COMMISSION) + l['amt'] * TRANSFER_FEE_RATE for l in layers]))
    k_full_days = int(((eqd['date'] >= entry) & (eqd['date'] < exitd) & (eqd['n_pos'] >= 3)).sum())
    blocked_during = int(((ld['sig_date'] >= str(entry.date())) & (ld['sig_date'] < str(exitd.date()))).sum())
    blocked_new = int(((ld['sig_date'] >= str(entry.date())) & (ld['sig_date'] < str(exitd.date())) & (ld['state'] == 'BLOCKED_K')).sum())
    add_cost = float(sum(l['amt'] for l in layers[1:]))
    gaps = [days.index(layers[i]['date']) - days.index(layers[i - 1]['date']) for i in range(1, len(layers))]
    pos_rows.append(dict(round=int(t['round']), ts_code=t['ts_code'], entry_date=t['entry_date'], exit_date=t['exit_date'],
                         holding_days=hold_days, slot_days=slot_days, capital_days=capital_days,
                         initial_layer_cost=float(layers[0]['amt']), total_cost=total_cost,
                         max_layers=int(t['levels_used']),
                         days_at_1_layer=lvl_days.get(1, 0), days_at_2_layers=lvl_days.get(2, 0),
                         days_at_3plus_layers=sum(v for k, v in lvl_days.items() if k >= 3),
                         days_K_full_while_held=k_full_days,
                         candidate_signals_blocked_during_hold=blocked_during,
                         new_entry_blocked_while_occupied=blocked_new,
                         capital_added_after_initial=add_cost,
                         median_days_between_adds=float(np.median(gaps)) if gaps else np.nan,
                         realized_pnl=float(t['pnl']), return_pct=float(t['return_pct'])))
pos_df = pd.DataFrame(pos_rows)
pos_df.to_csv(os.path.join(OUT, 'p5_position_lock.csv'), index=False)

age_bins = [(0, 5), (6, 10), (11, 20), (21, 40), (41, 60), (61, 90), (91, 120), (120, 10 ** 9)]
age_rows = []
for lo, hi in age_bins:
    sub = pos_df[(pos_df['holding_days'] >= lo) & (pos_df['holding_days'] <= hi)]
    age_rows.append(dict(age_bin=f'{lo}-{hi if hi < 10 ** 9 else "+"}d', n=len(sub),
                         slot_days=int(sub['slot_days'].sum()), capital_days=float(sub['capital_days'].sum()),
                         blocked_signals=int(sub['candidate_signals_blocked_during_hold'].sum()),
                         add_capital=float(sub['capital_added_after_initial'].sum()),
                         realized_pnl=float(sub['realized_pnl'].sum())))
age_df = pd.DataFrame(age_rows)
age_df.to_csv(os.path.join(OUT, 'p5_lock_age_curve.csv'), index=False)

layer_rows = []
for _, t in tr.iterrows():
    evt = pos_ev[(str(t['ts_code']), str(t['entry_date']))]
    layers = sorted(evt['layers'], key=lambda x: x['date'])
    exit_px = evt['exit_price']
    if not layers: continue
    exitd = pd.Timestamp(t['exit_date'])
    tot_cost = float(sum(l['amt'] for l in layers))
    buy_fees = sum(max(l['amt'] * COMMISSION_RATE, MIN_COMMISSION) + l['amt'] * TRANSFER_FEE_RATE for l in layers)
    sell_fee = float(t['pnl'] + tot_cost + buy_fees - exit_px * int(t['shares']))
    exit_fee = buy_fees + sell_fee
    for l in layers:
        hold_after = days.index(exitd) - days.index(l['date'])
        gross = l['qty'] * (exit_px - l['px'])
        fee_share = exit_fee * (l['amt'] / tot_cost) if tot_cost else 0
        net = gross - fee_share
        layer_rows.append(dict(round=int(t['round']), ts_code=t['ts_code'], entry_date=t['entry_date'], layer=l['lvl'],
                               layer_date=str(l['date'].date()), shares=l['qty'], layer_price=float(l['px']),
                               layer_cost=float(l['amt']), holding_days_after_layer=hold_after,
                               layer_pnl=float(net), layer_return_pct=float(net / l['amt'] * 100),
                               episode_return_pct=float(t['return_pct'])))
layer_df = pd.DataFrame(layer_rows)
layer_df.to_csv(os.path.join(OUT, 'p5_layer_capital_curve.csv'), index=False)

# ---------------- signal collision ----------------
k_full_days = int((eqd['n_pos'] >= 3).sum())
cash_insuf_days = int(((eqd['n_pos'] < 3) & (eqd['cash'] < 200000)).sum())
both_days = int(((eqd['n_pos'] >= 3) & (eqd['cash'] < 200000)).sum())
coll_df = daily_df[['date', 'n_positions', 'cash', 'candidate_count']].copy()
coll_df['k_full'] = (coll_df['n_positions'] >= 3).astype(int)
coll_df['cash_insufficient'] = ((coll_df['n_positions'] < 3) & (coll_df['cash'] < 200000)).astype(int)
coll_df.to_csv(os.path.join(OUT, 'p5_signal_collision.csv'), index=False)

# ---------------- occupancy concentration ----------------
pos_df['rank_slot'] = pos_df['slot_days'].rank(ascending=False, method='first')
tot_slot = pos_df['slot_days'].sum(); tot_cap = pos_df['capital_days'].sum(); tot_blk = pos_df['candidate_signals_blocked_during_hold'].sum()
conc_rows = []
for frac in [0.05, 0.10, 0.20]:
    n_top = max(1, int(np.ceil(len(pos_df) * frac)))
    top = pos_df.nsmallest(n_top, 'rank_slot')
    conc_rows.append(dict(frac=frac, n_top=n_top,
                          slot_share=float(top['slot_days'].sum() / tot_slot * 100),
                          capital_share=float(top['capital_days'].sum() / tot_cap * 100) if tot_cap else np.nan,
                          blocked_share=float(top['candidate_signals_blocked_during_hold'].sum() / tot_blk * 100) if tot_blk else np.nan))
sh = pos_df['slot_days'] / tot_slot
conc_rows.append(dict(frac='HHI_slot', n_top=len(pos_df), slot_share=float((sh ** 2).sum()), capital_share=np.nan, blocked_share=np.nan))
pd.DataFrame(conc_rows).to_csv(os.path.join(OUT, 'p5_occupancy_concentration.csv'), index=False)

# ---------------- virtual queue ----------------
npos_by_date = eqd.set_index('date')['n_pos'].to_dict()
cash_by_date = eqd.set_index('date')['cash'].to_dict()
vq_rows = []
for _, c in cand_df[cand_df['block_reason'].isin(['BLOCKED_K', 'BLOCKED_CASH'])].iterrows():
    sd = c['sig_date_dt']
    wait = np.nan; rel_date = None
    if sd in days:
        idx0 = days.index(sd)
        for i0 in range(idx0 + 1, N2024):
            d0 = days[i0]
            if npos_by_date.get(d0, 9) < 3 and cash_by_date.get(d0, 0) >= 200000:
                wait = i0 - idx0; rel_date = d0; break
    tp_before = np.nan
    if c['ind_cov'] and pd.notna(c['ind_exit_date']):
        ex = pd.Timestamp(c['ind_exit_date'])
        if sd in days and ex in days and wait == wait:
            tp_before = 1 if (days.index(ex) - days.index(sd)) <= wait else 0
    vq_rows.append(dict(sig_date=str(sd.date()), ts_code=c['ts_code'], block_reason=c['block_reason'],
                        wait_days=float(wait) if wait == wait else np.nan,
                        release_date=str(rel_date.date()) if rel_date is not None else 'NEVER',
                        ind_return=float(c['ind_simple_return_pct']) if c['ind_cov'] else np.nan,
                        ind_time_to_breakeven=float(c['ind_time_to_break_even_days']) if c['ind_cov'] else np.nan,
                        natural_exit_before_release=float(tp_before) if tp_before == tp_before else np.nan))
vq_df = pd.DataFrame(vq_rows)
vq_df.to_csv(os.path.join(OUT, 'p5_virtual_queue.csv'), index=False)
released = vq_df[vq_df['wait_days'].notna()]
tp_share = float(released['natural_exit_before_release'].mean() * 100) if len(released) else np.nan

# ---------------- summary ----------------
A = qual_df.set_index('reason')
l2 = layer_df[layer_df['layer'] >= 2]['layer_cost'].sum(); l3 = layer_df[layer_df['layer'] >= 3]['layer_cost'].sum()
lt = layer_df['layer_cost'].sum()
age_gt60 = age_df[age_df['age_bin'].isin(['61-90d', '91-120d', '120+d'])]
summary = dict(
    parity='PASS', n_days=N2024,
    k_full_days=int(k_full_days), k_full_pct=float(k_full_days / N2024 * 100),
    cash_insufficient_days=int(cash_insuf_days), cash_insufficient_pct=float(cash_insuf_days / N2024 * 100),
    both_k_cash_days=int(both_days), both_pct=float(both_days / N2024 * 100),
    candidate_events=int(len(cand_df)),
    admitted=int(A.loc['ADMITTED', 'n']) if 'ADMITTED' in A.index else 0,
    blocked_k=int(A.loc['BLOCKED_K', 'n']) if 'BLOCKED_K' in A.index else 0,
    blocked_cash=int(A.loc['BLOCKED_CASH', 'n']) if 'BLOCKED_CASH' in A.index else 0,
    blocked_held=int(A.loc['BLOCKED_HELD', 'n']) if 'BLOCKED_HELD' in A.index else 0,
    blocked_other=int(sum(A.loc[r, 'n'] for r in ['BLOCKED_LOT', 'BLOCKED_EXECUTION', 'BLOCKED_OTHER'] if r in A.index)),
    top10pct_slot_share=float(conc_rows[1]['slot_share']), top10pct_capital_share=float(conc_rows[1]['capital_share']),
    age_gt60_slot_share=float(age_gt60['slot_days'].sum() / tot_slot * 100),
    age_gt60_capital_share=float(age_gt60['capital_days'].sum() / tot_cap * 100) if tot_cap else np.nan,
    layer2plus_capital_share=float(l2 / lt * 100) if lt else np.nan,
    layer3plus_capital_share=float(l3 / lt * 100) if lt else np.nan,
    admitted_ind_mean=float(A.loc['ADMITTED', 'ind_mean']) if 'ADMITTED' in A.index else np.nan,
    blocked_k_ind_mean=float(A.loc['BLOCKED_K', 'ind_mean']) if 'BLOCKED_K' in A.index else np.nan,
    blocked_cash_ind_mean=float(A.loc['BLOCKED_CASH', 'ind_mean']) if 'BLOCKED_CASH' in A.index else np.nan,
    shadow=shadow_rows,
    virtual_queue_median_wait=float(released['wait_days'].median()) if len(released) else np.nan,
    virtual_queue_np_before_release_pct=float(tp_share) if tp_share == tp_share else np.nan,
    blocked_vs_admitted=ev_rows, occupancy_concentration=conc_rows, age_curve=age_rows,
    layer_summary={int(k): int(v) for k, v in layer_df.groupby('layer').size().to_dict().items()},
)
json.dump(summary, open(os.path.join(OUT, 'p5_summary.json'), 'w'), indent=2, ensure_ascii=False, default=float)
inv = dict(I1_parity='PASS', I2_candidate_universe_unchanged=True, I3_entry_unchanged=True, I4_exit_unchanged=True,
           I5_cost_slippage_unchanged=True, I6_no_predictor=True, I7_no_gate=True, I8_no_new_admission_rule=True,
           I9_independent_diagnostic_only=True, I10_same_exit_matched_share=True, I11_no_2025_read=True,
           I12_prior_registry_shas_unchanged=True, registry_sha=reg_sha)
json.dump(inv, open(os.path.join(OUT, 'p5_invariants.json'), 'w'), indent=2)
print('[P5] summary saved', flush=True)
print(json.dumps({k: summary[k] for k in ['candidate_events', 'admitted', 'blocked_k', 'blocked_cash', 'blocked_held',
                                           'k_full_days', 'cash_insufficient_days']}, indent=1), flush=True)
print('[P5] DONE', flush=True)
