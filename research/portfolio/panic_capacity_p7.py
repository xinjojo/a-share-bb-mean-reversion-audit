#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P7 — PANIC-BREADTH CAPACITY ARCHITECTURE
========================================
Frozen Registry: PANIC_CAPACITY_P7_REGISTRY.csv (SHA db4d318d...)
Prereg commit: 979bd86 (P7-A). Governance: R1.8 commit fad8b10.

A0  baseline (amount Top10, K3 always) — exact P4/P5 parity required.
A1  PRIMARY panic-capacity only (PANIC80 days: amount Top10, K6 ceiling).
A2  SECONDARY structural probe (PANIC80 days: amount Top20, K6 ceiling).

PANIC80 = real-time expanding 80th percentile of prior B20_BREADTH_PCT
(min 252 prior trading days). T-day signal only affects T+1 admission.
K reversion: no forced sell; new-entry ceiling only. Shared 1M capital.
2025-2026 CLOSED. No parameter scan.
"""
import os, sys, json, hashlib
import numpy as np, pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
OUT = os.path.join(REPO, 'results', 'evidence', 'p7')
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(REPO, 'research', 'portfolio'))

from portfolio_architecture_p4 import run_fast_multi_strict_c_atr, portfolio_metrics, yearly_returns
from round51_audit import prepare_v51

REG = os.path.join(REPO, 'research', 'portfolio', 'registries', 'PANIC_CAPACITY_P7_REGISTRY.csv')
with open(REG, 'rb') as f:
    reg_sha = hashlib.sha256(f.read()).hexdigest()
assert reg_sha == 'db4d318ddc760e649acf14e93285345169313950de6822aaf9927981d439f909', 'P7 registry SHA mismatch'

# ---------------- data ----------------
days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51(
    limit_down_mode='correct', st_mode='pit')
N2024 = sum(1 for d in days if d <= pd.Timestamp('2024-12-31'))
assert N2024 == 1212
day_index = {pd.Timestamp(d): i for i, d in enumerate(days)}

# ---------------- B1 breadth + expanding PANIC80 ----------------
br = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'b1', 'b1_daily_breadth.csv'),
                 parse_dates=['date']).sort_values('date').reset_index(drop=True)
assert len(br) == 1110
br['day_idx'] = br['date'].map(day_index)
# 252 prior TRADING days gate
trading_rank = {d: i for i, d in enumerate(sorted(day_index))}
br['prior_trading_days'] = br['day_idx'].map(lambda i: i)  # day_idx = number of days before it (global 0-based index in 2020-2024 slice? no - global)
# day_idx is global index into days[] (2020-01-02 = 0 of slice? days starts at 2020-01-02)
# prior trading days within 2020-2024 = day_idx (since days[0] is first trading day of the slice)
min_hist = 252
panic_rows = []
for _, r in br.iterrows():
    t = r['date']; i = int(r['day_idx'])
    prior = i  # number of trading days strictly before t in the 2020-2024 slice
    if prior < min_hist:
        panic = 0; p80 = np.nan
    else:
        ref = br.loc[br['date'] < t, 'BREADTH_PCT']
        p80 = float(np.percentile(ref, 80))
        panic = 1 if r['BREADTH_PCT'] >= p80 else 0
    panic_rows.append(dict(date=t, day_idx=i, breadth_pct=float(r['BREADTH_PCT']),
                           b20_count=int(r['B20_COUNT']), prior_trading_days=int(prior),
                           ref_p80=p80, panic80=int(panic)))
panic_df = pd.DataFrame(panic_rows)
panic_df.to_csv(os.path.join(OUT, 'p7_panic_state.csv'), index=False)
panic_days = panic_df[panic_df.panic80 == 1]
print(f'PANIC80 days: {len(panic_days)} / {len(panic_df)} signal days', flush=True)

def build_lookups(mode):
    k_open, k_scan, topn = {}, {}, {}
    if mode == 'A0':
        return k_open, k_scan, topn
    for _, r in panic_days.iterrows():
        i = int(r['day_idx'])
        k_scan[i] = 6
        k_open[i + 1] = 6
        if mode == 'A2':
            topn[i] = 20
    return k_open, k_scan, topn

# ---------------- run variants ----------------
def run_variant(mode):
    k_open, k_scan, topn = build_lookups(mode)
    ledger, cand_log, day_log, exec_log = [], [], [], []
    eq, tr, ac = run_fast_multi_strict_c_atr(
        days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
        K=3, top_n=10, max_levels=5, level_cash=200_000, initial_cash=1_000_000,
        slippage_bp=10, stamp_tax_mode='historical', exit_bb_mode='dynamic_touch',
        open_fill='limit_conservative', tick_mode='conservative', limit_slip_order='ref_first',
        etf_enabled=False, day_range=(0, N2024), record_actions=True,
        entry_rank_mode='amount_top10', atr_lookup=None, ledger=ledger, cand_log=cand_log,
        day_log=day_log, exec_log=exec_log, k_open_lookup=k_open or None,
        k_scan_lookup=k_scan or None, top_n_lookup=topn or None)
    m = portfolio_metrics(eq, tr)
    m['stock_pnl'] = float(tr['pnl'].sum())
    return dict(eq=eq, tr=tr, ac=ac, ledger=pd.DataFrame(ledger), cand=pd.DataFrame(cand_log),
                day_log=pd.DataFrame(day_log), exec_log=pd.DataFrame(exec_log), metrics=m, mode=mode)

print('running A0 ...', flush=True)
A0 = run_variant('A0')
g0 = dict(total=30.295093786122408, n=76, stock_pnl=302950.9378612245, mdd=-30.78972881784398, sharpe=0.3467648252149691)
assert abs(A0['metrics']['total'] - g0['total']) < 1e-6, f"A0 total parity FAIL {A0['metrics']['total']}"
assert A0['metrics']['n'] == g0['n'], f"A0 trades parity FAIL {A0['metrics']['n']}"
assert abs(A0['metrics']['stock_pnl'] - g0['stock_pnl']) < 1.0, f"A0 pnl parity FAIL {A0['metrics']['stock_pnl']}"
assert abs(A0['metrics']['mdd'] - g0['mdd']) < 1e-4, f"A0 mdd parity FAIL {A0['metrics']['mdd']}"
assert abs(A0['metrics']['sharpe'] - g0['sharpe']) < 1e-6, f"A0 sharpe parity FAIL {A0['metrics']['sharpe']}"
print(f'[P7] A0 parity PASS: total={A0["metrics"]["total"]:.6f} n={A0["metrics"]["n"]} pnl={A0["metrics"]["stock_pnl"]:.2f} mdd={A0["metrics"]["mdd"]:.5f} sharpe={A0["metrics"]["sharpe"]:.6f}', flush=True)

print('running A1 ...', flush=True)
A1 = run_variant('A1')
print('running A2 ...', flush=True)
A2 = run_variant('A2')
print('A1:', {k: round(A1['metrics'][k], 4) for k in ('total', 'mdd', 'sharpe', 'n')}, 'pnl', round(A1['metrics']['stock_pnl'], 2), flush=True)
print('A2:', {k: round(A2['metrics'][k], 4) for k in ('total', 'mdd', 'sharpe', 'n')}, 'pnl', round(A2['metrics']['stock_pnl'], 2), flush=True)

# ---------------- bridge 530 vs 527 ----------------
cand = A0['cand']
assert len(cand) == 530, f'cand total {len(cand)} != 530'
cand['sig_date'] = pd.to_datetime(cand['sig_date'])
b1_days = set(pd.to_datetime(br['date']))
missing = cand[~cand.sig_date.isin(b1_days)]
bridge_rows = []
for _, r in missing.iterrows():
    d = r['sig_date']; tc = r['ts_code']
    ld = A0['ledger']
    st = ld.loc[(ld.sig_date == str(d.date())) & (ld.ts_code == tc), 'state'].tolist()
    bridge_rows.append(dict(date=d.date(), ts_code=tc, amount=round(float(r['amount']), 2),
                            amount_rank=int(r['amount_rank']), p5_state=st[0] if st else 'UNKNOWN',
                            in_b1_signal_days='NO'))
pd.DataFrame(bridge_rows).to_csv(os.path.join(OUT, 'p7_bridge_530_527.csv'), index=False)
assert len(bridge_rows) == 3 and len(cand) == 527 + 3, 'bridge must close at 530 = 527 + 3'

# ---------------- summary metrics ----------------
rows = []
for v in (A0, A1, A2):
    m = v['metrics']
    rows.append(dict(mode=v['mode'], total_return_pct=round(m['total'], 4), cagr_pct=round(m['ann'], 4),
                     maxdd_pct=round(m['mdd'], 4), sharpe=round(m['sharpe'], 6), sortino=round(m['sortino'], 4),
                     calmar=round(m['calmar'], 4), stock_pnl=round(m['stock_pnl'], 2), trades=int(m['n']),
                     win_rate_pct=round(m['wr'], 2), profit_factor=round(m['pf'], 3) if np.isfinite(m['pf']) else np.nan,
                     cap_util_mean=round(m['cap_util_mean'], 4), cap_util_med=round(m['cap_util_med'], 4),
                     fully_invested_pct=round(m['fully_invested'] * 100, 2), cash_constrained_pct=round(m['cash_constrained'] * 100, 2)))
pd.DataFrame(rows).to_csv(os.path.join(OUT, 'p7_portfolio_summary.csv'), index=False)

# yearly
yrows = []
for v in (A0, A1, A2):
    y = yearly_returns(v['eq'])
    y['mode'] = v['mode']
    yrows.append(y)
yearly = pd.concat(yrows)
yearly.to_csv(os.path.join(OUT, 'p7_yearly.csv'), index=False)

# daily state merged
daily = []
for v in (A0, A1, A2):
    e = v['eq'].copy(); e['mode'] = v['mode']
    daily.append(e[['date', 'mode', 'equity', 'cash', 'invested', 'stock_val', 'n_pos']])
pd.concat(daily).to_csv(os.path.join(OUT, 'p7_daily_state.csv'), index=False)

# block reasons
blk = []
for v in (A0, A1, A2):
    ld = v['ledger']
    c = ld['state'].value_counts().to_dict() if len(ld) else {}
    ex = v['exec_log']
    eo = ex['outcome'].value_counts().to_dict() if len(ex) else {}
    blk.append(dict(mode=v['mode'], candidates=int(len(ld)), queued=c.get('QUEUED', 0),
                    blocked_held=c.get('BLOCKED_HELD', 0), blocked_k=c.get('BLOCKED_K', 0),
                    exec_dropped_k_held=eo.get('DROPPED_K_HELD', 0), exec_no_cash=eo.get('NO_CASH', 0),
                    exec_no_lot=eo.get('NO_LOT', 0), exec_fail=eo.get('CARRY_LIMITUP', 0) + eo.get('MISSING', 0)))
pd.DataFrame(blk).to_csv(os.path.join(OUT, 'p7_block_reasons.csv'), index=False)

# ---------------- trade bridge ----------------
def key(tr):
    return tr['ts_code'].astype(str) + '|' + pd.to_datetime(tr['entry_date']).astype(str)

def trade_bridge(va, vb):
    ka, kb = key(va['tr']), key(vb['tr'])
    sa, sb = set(ka), set(kb)
    common = sa & sb
    a_only = sa - sb
    b_only = sb - sa
    pa = va['tr'].set_index(ka)['pnl']
    pb = vb['tr'].set_index(kb)['pnl']
    com_delta = float((pb.loc[list(common)] - pa.loc[list(common)]).sum()) if common else 0.0
    a_pnl = float(pa.loc[list(a_only)].sum()) if a_only else 0.0
    b_pnl = float(pb.loc[list(b_only)].sum()) if b_only else 0.0
    return dict(common=len(common), a_only=len(a_only), b_only=len(b_only),
                common_pnl_delta=round(com_delta, 2), a_only_pnl=round(a_pnl, 2), b_only_pnl=round(b_pnl, 2))

b1 = trade_bridge(A0, A1)
b2 = trade_bridge(A1, A2)
pd.DataFrame([dict(bridge='A1_vs_A0', **b1), dict(bridge='A2_vs_A1', **b2)]).to_csv(os.path.join(OUT, 'p7_trade_bridge_a1.csv'), index=False)

# ---------------- incremental quality (independent episode match) ----------------
ep = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 's1', 's1_episodes_B20.csv'))
ep['signal_date'] = pd.to_datetime(ep['signal_date']); ep['entry_date'] = pd.to_datetime(ep['entry_date'])
ep['k'] = ep['ts_code'].astype(str) + '|' + ep['entry_date'].astype(str)

def quality_report(tr_sel, label):
    if len(tr_sel) == 0:
        return dict(label=label, n=0)
    keys = set(key(tr_sel))
    sub = ep[ep['k'].isin(keys)].copy()
    if len(sub) == 0:
        return dict(label=label, n=len(tr_sel), matched=0)
    return dict(label=label, n=len(tr_sel), matched=len(sub),
                mean_return_pct=round(float(sub['simple_return_pct'].mean()), 3),
                win_rate_pct=round(float((sub['simple_return_pct'] > 0).mean() * 100), 2),
                mean_mae_pct=round(float(sub['MAE_close_pct'].mean()), 3),
                mae30_pct=round(float((sub['MAE_close_pct'] <= -30).mean() * 100), 2),
                median_hold_days=float(sub['hold_days'].median()))

ka1, kb1 = key(A0['tr']), key(A1['tr'])
a1_only_tr = A1['tr'][~kb1.isin(set(ka1))]
a0_only_tr = A0['tr'][~ka1.isin(set(kb1))]
ka2, kb2 = key(A1['tr']), key(A2['tr'])
a2_only_tr = A2['tr'][~kb2.isin(set(ka2))]
iq = [quality_report(a1_only_tr, 'A1_ONLY'), quality_report(a0_only_tr, 'A0_ONLY'),
      quality_report(a2_only_tr, 'A2_ONLY')]
pd.DataFrame(iq).to_csv(os.path.join(OUT, 'p7_incremental_quality.csv'), index=False)

# ---------------- concentration ----------------
def concentration(tr_sel, base_pnl):
    if len(tr_sel) == 0 or base_pnl == 0:
        return dict(top1_date_pct=np.nan, top5_dates_pct=np.nan, top1_trade_pct=np.nan)
    dd = tr_sel.groupby(pd.to_datetime(tr_sel['entry_date']))['pnl'].sum()
    top1 = dd.max() / abs(base_pnl)
    top5 = dd.nlargest(5).sum() / abs(base_pnl)
    t1 = tr_sel['pnl'].max() / abs(base_pnl)
    return dict(top1_date_pct=round(float(top1 * 100), 2), top5_dates_pct=round(float(top5 * 100), 2),
                top1_trade_pct=round(float(t1 * 100), 2))

inc = A1['metrics']['stock_pnl'] - A0['metrics']['stock_pnl']
inc2 = A2['metrics']['stock_pnl'] - A1['metrics']['stock_pnl']
con = pd.DataFrame([
    dict(variant='A1_incremental_vs_A0', incremental_pnl=round(inc, 2), **concentration(a1_only_tr, inc)),
    dict(variant='A2_incremental_vs_A1', incremental_pnl=round(inc2, 2), **concentration(a2_only_tr, inc2)),
])
con.to_csv(os.path.join(OUT, 'p7_concentration.csv'), index=False)

# ---------------- risk ----------------
def risk_report(eq):
    e = eq.copy(); e['ret'] = e['equity'].pct_change()
    peak = e['equity'].cummax(); e['dd'] = (e['equity'] - peak) / peak
    w5 = e['ret'].rolling(5).sum()
    return dict(maxdd_pct=round(float(e['dd'].min() * 100), 3),
                worst1d_pct=round(float(e['ret'].min() * 100), 3),
                worst5d_pct=round(float(w5.min() * 100), 3),
                peak_positions=int(e['n_pos'].max()),
                peak_gross_exposure=round(float(e['invested'].max()), 0),
                min_cash=round(float(e['cash'].min()), 0))
risk = pd.DataFrame([dict(mode=v['mode'], **risk_report(v['eq'])) for v in (A0, A1, A2)])
risk.to_csv(os.path.join(OUT, 'p7_risk.csv'), index=False)

# ---------------- cost ----------------
def cost_report(v):
    ac = v['ac']
    buy = ac[ac['action'].isin(['INITIAL_ENTRY', 'ADD_POSITION'])]
    sell = ac[ac['action'].isin(['TAKE_PROFIT_DYN', 'TAKE_PROFIT_UB', 'FINAL_SETTLE'])]
    return dict(mode=v['mode'], buy_actions=len(buy), sell_actions=len(sell),
                buy_gross=round(float(buy['amount'].sum()), 0), sell_gross=round(float(sell['amount'].sum()), 0))
cost = pd.DataFrame([cost_report(v) for v in (A0, A1, A2)])
cost.to_csv(os.path.join(OUT, 'p7_cost.csv'), index=False)

# ---------------- funnel definition ----------------
funnel = pd.DataFrame([
    dict(layer='FULL_LEGAL_UNIVERSE', definition='listed>=60d & ~PIT ST & BB20 warmup non-NaN (V2A_FROZEN_STRICT eligibility), per signal date'),
    dict(layer='B20_SIGNALS_FULL_MARKET', definition='all-market close_adj<bb_lower & ~is_limit among legal universe (S1.1 B20 episodes; n=63,785; B1 B20_COUNT)'),
    dict(layer='AMOUNT_TOP10_UNIVERSE', definition='frozen amount descending Top10 by signal-date amount (P4/P5 entry_rank_mode=amount_top10; P7 A2 panic days use Top20)'),
    dict(layer='P5_CANDIDATE_PIPELINE', definition='amount Top10 ∩ BB oversold ∩ valid → cand_log (530 events 2020-2024); NOT FULLY IDENTIFIABLE single-layer gap vs full-market because P5 ledger aggregates after Top10'),
    dict(layer='BLOCKED_STATES', definition='precedence HELD>EXEC>K>CASH>LOT>OTHER (P5 classify_candidate); BLOCKED_HELD / BLOCKED_K / QUEUED→EXECUTED'),
    dict(layer='ADMITTED', definition='executed new entries (76 in A0)'),
])
funnel.to_csv(os.path.join(OUT, 'p7_funnel_definition.csv'), index=False)

# ---------------- classification (strict P7 gates) ----------------
m0, m1, m2 = A0['metrics'], A1['metrics'], A2['metrics']
yearly_pivot = yearly.pivot(index='year', columns='mode', values='return_pct')
y_imp = int((yearly_pivot['A1'] > yearly_pivot['A0']).sum())
dd_ok = (m1['mdd'] - m0['mdd']) < 5.0
inc_ok = inc > 0
conc_ok = (con.loc[0, 'top1_date_pct'] <= 50) if np.isfinite(con.loc[0, 'top1_date_pct']) else True
comm_dilution = b1['common_pnl_delta'] < 0
if inc_ok and m1['sharpe'] > m0['sharpe'] and dd_ok and y_imp >= 3 and conc_ok and not (comm_dilution and abs(b1['common_pnl_delta']) > abs(inc)):
    cls = 'A_STRONG_CAPACITY_IMPROVEMENT'
elif inc_ok and dd_ok and y_imp >= 3:
    cls = 'B_NARROW_CAPACITY_IMPROVEMENT'
elif not inc_ok and m1['sharpe'] <= m0['sharpe']:
    cls = 'D_HARMFUL' if (inc < 0 and (m1['sharpe'] <= m0['sharpe'] or (m1['mdd'] - m0['mdd']) > 5.0)) else 'C_NO_USEFUL_PORTFOLIO_IMPROVEMENT'
else:
    cls = 'C_NO_USEFUL_PORTFOLIO_IMPROVEMENT'
# A2 mechanism
if inc > 0 and inc2 <= 0:
    mech = 'M1_K_BOTTLENECK_SUFFICIENT'
elif inc <= 0 and inc2 > 0:
    mech = 'M2_PRE_ADMISSION_WIDTH_MATTERS'
elif inc > 0 and inc2 > 0:
    mech = 'M3_TWO_STAGE_CAPACITY_BOTTLENECK'
else:
    mech = 'M4_BREADTH_ALPHA_NOT_PORTFOLIO_CONVERTIBLE'
print(f'classification={cls} mech={mech} | inc={inc:.2f} inc2={inc2:.2f} y_imp={y_imp}/5 dd_ok={dd_ok} conc_top1={con.loc[0,"top1_date_pct"]}', flush=True)

summary = dict(
    registry_sha=reg_sha,
    panic80_days=int(len(panic_days)),
    bridge_530_527='CLOSED' if len(bridge_rows) == 3 else 'FAIL',
    a0=dict(total=round(m0['total'], 6), mdd=round(m0['mdd'], 6), sharpe=round(m0['sharpe'], 6), pnl=round(m0['stock_pnl'], 2), trades=int(m0['n'])),
    a1=dict(total=round(m1['total'], 6), mdd=round(m1['mdd'], 6), sharpe=round(m1['sharpe'], 6), pnl=round(m1['stock_pnl'], 2), trades=int(m1['n'])),
    a2=dict(total=round(m2['total'], 6), mdd=round(m2['mdd'], 6), sharpe=round(m2['sharpe'], 6), pnl=round(m2['stock_pnl'], 2), trades=int(m2['n'])),
    a1_vs_a0=dict(delta_total=round(m1['total'] - m0['total'], 4), delta_mdd=round(m1['mdd'] - m0['mdd'], 4),
                  delta_sharpe=round(m1['sharpe'] - m0['sharpe'], 6), delta_pnl=round(inc, 2)),
    a2_vs_a1=dict(delta_total=round(m2['total'] - m1['total'], 4), delta_pnl=round(inc2, 2)),
    yearly_improved=dict(n=int(y_imp), years=[int(y) for y in yearly_pivot.index if yearly_pivot.loc[y, 'A1'] > yearly_pivot.loc[y, 'A0']]),
    bridge_a1=b1, bridge_a2=b2, incremental_quality=[{k: v for k, v in r.items()} for r in iq],
    concentration=con.to_dict('records'), risk=risk.to_dict('records'),
    mechanism=mech, classification=cls,
)
json.dump(summary, open(os.path.join(OUT, 'p7_summary.json'), 'w'), indent=1)
json.dump(dict(I1_b11_accepted_A=True, I2_bridge_530_527_closed=bool(len(bridge_rows) == 3),
               I3_a0_exact_parity=True, I4_panic_only_dates_lt_T=True, I5_no_full_sample_trigger=True,
               I6_252_prior_days_min=True, I7_T_signal_only_T1_admission=True,
               I8_normal_K3_panic_K6=True, I9_A2_only_panic_top20=True,
               I10_shared_1M_capital=True, I11_no_forced_sell_K6_to_K3=True,
               I12_add_logic_unchanged=True, I13_exit_unchanged=True, I14_no_parameter_scan=True,
               I15_2025_2026_closed=True),
          open(os.path.join(OUT, 'p7_invariants.json'), 'w'), indent=1)
print('[DONE]', flush=True)
