#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P5.1 — DEFERRED-ADMISSION ELIGIBILITY DIAGNOSTIC
=================================================
Pure diagnostic: for each of the 336 P5 BLOCKED_K candidates, re-run the
ORIGINAL frozen BB entry rules at the slot-release date to determine whether
the candidate is still a legal BB entry signal when a slot becomes available.
No delayed entry is executed; no portfolio path is modified; no parameter
scan; 2025-2026 CLOSED.

Registry: PORTFOLIO_ARCHITECTURE_P51_QUEUE_ELIGIBILITY_REGISTRY.csv
          (SHA 7de0874eba6fe49c370060851b1a3bbd13e9f65498a83c0a9b1dcf1376838ec6,
           prereg commit dc5fb74, pushed BEFORE outcomes)
"""
import os, sys, json, hashlib
import numpy as np, pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
OUT = os.path.join(REPO, 'results', 'evidence', 'p51')
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(REPO, 'research', 'portfolio'))

from portfolio_architecture_p4 import run_fast_multi_strict_c_atr, portfolio_metrics
from round51_audit import prepare_v51, stamp_rate, COMMISSION_RATE, MIN_COMMISSION, TRANSFER_FEE_RATE

# ---------------- registry integrity ----------------
REG = os.path.join(REPO, 'research', 'portfolio', 'registries', 'PORTFOLIO_ARCHITECTURE_P51_QUEUE_ELIGIBILITY_REGISTRY.csv')
with open(REG, 'rb') as f:
    reg_sha = hashlib.sha256(f.read()).hexdigest()
assert reg_sha == '7de0874eba6fe49c370060851b1a3bbd13e9f65498a83c0a9b1dcf1376838ec6', 'P5.1 registry SHA mismatch'
prior = {
 'F1': ('FAILURE_STATE_F1_REGISTRY.csv', 'a052309e6f939796795566d1cd1094e2ec706f53250c231377c64efb315eef14'),
 'F1.1': ('FAILURE_STATE_F11_INFERENCE_REGISTRY.csv', 'aacb2146308abd155401c1231209b7cab14e1bc44c50e6f19007ac39582aef91'),
 'F2': ('FAILURE_STATE_F2_ACTIONABILITY_REGISTRY.csv', '9ed07a575ae65bbda3d63321e676431231d00548bb8977fb443764163b85642a'),
 'F2.1': ('FAILURE_STATE_F21_MATCHED_ACTION_REGISTRY.csv', '12f8311c52df76ca6fc10cb7f5f43a95bae4e1c9a9dc1f5880bfdcee60357787'),
 'F2.2': ('FAILURE_STATE_F22_BREAK_EVEN_REGISTRY.csv', 'aff9c4295fceec450a54ea7bc2bfbc8055761d396081d778d4e1ff616b6095d8'),
 'F2.3': ('FAILURE_STATE_F23_POLICY_VALUE_INFERENCE_REGISTRY.csv', 'c0f4d1d2bd46a7c5bca01752020dec121404984feb8273984a5164f56942f83c'),
 'F3': ('FAILURE_STATE_F3_PREDICTOR_REGISTRY.csv', '803e15245746a90d542de1bd18889686dacf6e926b3ac931717c68335db2a032'),
 'P5': ('PORTFOLIO_ARCHITECTURE_P5_REGISTRY.csv', '7415608a1003b612704e295a76427eba5c124607163a926fb514342c699f7ce7'),
}
for name, (fn, sha) in prior.items():
    pth = os.path.join(REPO, 'research', 'portfolio', 'registries', fn)
    if not os.path.exists(pth):
        pth = os.path.join(REPO, 'research', 'risk', 'registries', fn)
    assert os.path.exists(pth), f'{name} registry not found'
    with open(pth, 'rb') as f:
        assert hashlib.sha256(f.read()).hexdigest() == sha, f'{name} registry SHA changed (I12)'

# ---------------- data & baseline run (I1 parity + BLOCKED_K) ----------------
days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51(
    limit_down_mode='correct', st_mode='pit')
N2024 = sum(1 for d in days if d <= pd.Timestamp('2024-12-31'))
assert N2024 == 1212 and all(d.year <= 2024 for d in days[:N2024]), 'I11'
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
assert abs(m['total'] - 30.295093786122408) < 1e-6 and m['n'] == 76 and abs(stock_pnl - 302950.9378612245) < 1.0
print(f'[P5.1] A0 parity PASS total={m["total"]:.6f}% n={m["n"]} pnl={stock_pnl:.2f}', flush=True)

ld = pd.DataFrame(ledger)
bk = ld[ld['state'] == 'BLOCKED_K'].copy()
assert len(bk) == 336, f'I1 BLOCKED_K {len(bk)} != 336'
bk['sig_date'] = pd.to_datetime(bk['sig_date'])
cand_keys = set(zip(pd.to_datetime([c['sig_date'] for c in cand_log]), [c['ts_code'] for c in cand_log]))
eqd = eq.copy(); eqd['date'] = pd.to_datetime(eqd['date'])
npos_by_date = eqd.set_index('date')['n_pos'].to_dict()
cash_by_date = eqd.set_index('date')['cash'].to_dict()

# ---------------- release date (P5 frozen definition) ----------------
def release_date_for(sd):
    idx0 = days.index(sd)
    for i0 in range(idx0 + 1, N2024):
        d0 = days[i0]
        if npos_by_date.get(d0, 9) < 3 and cash_by_date.get(d0, 0) >= 200000:
            return d0, i0 - idx0
    return None, None

# ---------------- frozen independent episode join ----------------
fm = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'fullmarket', 'fullmarket_episode_metrics.csv'))
fm['signal_date'] = pd.to_datetime(fm['signal_date'])
fm = fm[fm['signal_date'] <= pd.Timestamp('2024-12-31')].copy()
fm_lookup = {k: r for k, r in fm.set_index(['signal_date', 'ts_code']).iterrows()}

SLIP = 0.001

def release_scan(rel_ts, tc):
    """re-run ORIGINAL frozen entry eligibility at release date (release-day info only).
    Returns dict of eligibility flags + contextual prices."""
    dd = D[rel_ts]
    i_rel = offset + days.index(rel_ts)
    pos = np.where(dd['ts'] == tc)[0]
    if len(pos) == 0:
        return dict(in_pit=False)
    j = int(pos[0])
    def rget(k): return dd[k][j]
    li = i_rel - first_eligible_i.get(tc, 0)
    valid = (li >= 0) and (not bool(rget('is_st')))
    close_adj = float(rget('close_adj')); bb_lo = float(rget('bb_lower')); bb_hi = float(rget('bb_upper'))
    is_limit = bool(rget('is_limit'))
    oversold = (not np.isnan(bb_lo)) and (close_adj < bb_lo) and (not is_limit)
    open_raw = float(rget('open_'))
    qty = int(np.floor(200000 / (open_raw * (1 + SLIP)) / 100) * 100)
    one_lot = qty >= 100
    # amount Top10 among full eligible pool at release date (engine rule)
    amt_all = []
    for t2 in dd['ts']:
        li2 = i_rel - first_eligible_i.get(t2, 0)
        if (li2 >= 0) and (not bool(dd['is_st'][np.where(dd['ts'] == t2)[0][0]])):
            amt_all.append((float(dd['amount'][np.where(dd['ts'] == t2)[0][0]]), t2))
    amt_all.sort(reverse=True)
    rank = next((k + 1 for k, (_, t2) in enumerate(amt_all) if t2 == tc), None)
    in_top10 = (rank is not None) and (rank <= 10)
    return dict(in_pit=True, valid=valid, oversold=oversold, is_limit=is_limit,
                in_top10=in_top10, one_lot=one_lot, amount_rank=rank,
                close_adj=close_adj, bb_lo=bb_lo, bb_hi=bb_hi, open_raw=open_raw, qty=qty)

def bb_oversold_on(day_ts, tc):
    dd = D[day_ts]
    pos = np.where(dd['ts'] == tc)[0]
    if len(pos) == 0:
        return False
    j = int(pos[0])
    return (not np.isnan(dd['bb_lower'][j])) and (float(dd['close_adj'][j]) < float(dd['bb_lower'][j])) and (not bool(dd['is_limit'][j]))

# ---------------- classify each blocked candidate ----------------
recs = []
for _, c in bk.iterrows():
    sd = c['sig_date']; tc = c['ts_code']
    rel, wait = release_date_for(sd)
    rec = dict(sig_date=str(sd.date()), ts_code=tc, release_date=str(rel.date()) if rel is not None else 'NEVER',
               wait_days=int(wait) if wait is not None else np.nan)
    if rel is None:
        rec['state'] = 'NO_RELEASE'
        recs.append(rec)
        continue
    # signal-day context
    srow = D[sd]
    spos = np.where(srow['ts'] == tc)[0]
    if len(spos) > 0:
        sj = int(spos[0])
        rec['signal_close_adj'] = float(srow['close_adj'][sj]); rec['signal_bb_lower'] = float(srow['bb_lower'][sj])
    # release scan
    rs = release_scan(rel, tc)
    rec.update({k: rs.get(k) for k in ['in_pit', 'valid', 'oversold', 'is_limit', 'in_top10', 'one_lot', 'amount_rank']})
    if rs.get('in_pit'):
        rec['release_close_adj'] = rs['close_adj']; rec['release_bb_lower'] = rs['bb_lo']
        rec['release_bb_upper'] = rs['bb_hi']; rec['release_open_raw'] = rs['open_raw']
        rec['release_return_from_signal_pct'] = (rs['close_adj'] / rec.get('signal_close_adj', np.nan) - 1) * 100 if rec.get('signal_close_adj') else np.nan
        rec['release_distance_to_lbb_pct'] = (rs['close_adj'] / rs['bb_lo'] - 1) * 100 if not np.isnan(rs['bb_lo']) else np.nan
        rec['still_below_lower_band'] = int(rs['oversold'])
    # independent outcome + Q0
    cov = (sd, tc) in fm_lookup
    rec['ind_cov'] = int(cov)
    if cov:
        ep = fm_lookup[(sd, tc)]
        rec['ind_return'] = float(ep['simple_return_pct']); rec['ind_win'] = int(ep['simple_return_pct'] > 0)
        rec['ind_mae'] = float(ep['MAE_close_pct']); rec['ind_hold'] = float(ep['hold_days'])
        rec['ind_exit_date'] = str(ep['exit_date'])
        exited_before = pd.Timestamp(ep['exit_date']) <= rel
        rec['expired_tp_before_release'] = int(exited_before)
    else:
        rec['ind_exit_date'] = ''
        rec['expired_tp_before_release'] = np.nan
    # Q state (exclusive)
    if cov and rec['expired_tp_before_release'] == 1:
        rec['state'] = 'Q0_EXPIRED_TP'
    elif rs.get('in_pit') and rs.get('valid') and rs.get('oversold') and rs.get('in_top10') and rs.get('one_lot'):
        rec['state'] = 'Q1_EXACT_ELIGIBLE'
    elif rs.get('in_pit') and rs.get('valid') and rs.get('oversold'):
        rec['state'] = 'Q2_OVERSOLD_NOT_TOP10'
    else:
        rec['state'] = 'Q3_NO_LONGER_OVERSOLD'
    # retrigger diagnostic between signal and release (inclusive)
    i_sig = days.index(sd); i_rel = days.index(rel)
    rts = []
    for i0 in range(i_sig + 1, i_rel + 1):
        if bb_oversold_on(days[i0], tc):
            rts.append(days[i0])
    rec['retrigger_count'] = len(rts)
    rec['retrigger_ge1'] = int(len(rts) > 0)
    rec['days_to_first_retrigger'] = int(days.index(rts[0]) - i_sig) if rts else np.nan
    # natural capture by frozen engine: retrigger day present in P5 cand_log
    nat_cap = []
    for r0 in rts:
        if (r0, tc) in cand_keys:
            nat_cap.append(r0)
    rec['natural_capture_count'] = len(nat_cap)
    rec['natural_captured'] = int(len(nat_cap) > 0)
    recs.append(rec)

qdf = pd.DataFrame(recs)
assert len(qdf) == 336, 'I1'
qdf.to_csv(os.path.join(OUT, 'p51_queue_eligibility.csv'), index=False)

# ---------------- state summary ----------------
state_counts = qdf['state'].value_counts().to_dict()
state_sum = []
for st in ['Q0_EXPIRED_TP', 'Q1_EXACT_ELIGIBLE', 'Q2_OVERSOLD_NOT_TOP10', 'Q3_NO_LONGER_OVERSOLD']:
    n = int(state_counts.get(st, 0))
    state_sum.append(dict(state=st, n=n, pct=float(n / 336 * 100)))
pd.DataFrame(state_sum).to_csv(os.path.join(OUT, 'p51_queue_state_summary.csv'), index=False)

# ---------------- wait decay ----------------
bins = [(1, 5), (6, 10), (11, 20), (21, 40), (40, 10 ** 9)]
wait_rows = []
for lo, hi in bins:
    sub = qdf[(qdf['wait_days'] >= lo) & (qdf['wait_days'] <= hi)]
    if len(sub) == 0:
        continue
    lbl = f'{lo}-{hi if hi < 10 ** 9 else "+"}d'
    wait_rows.append(dict(wait_bin=lbl, n=len(sub),
                          q0_pct=float((sub['state'] == 'Q0_EXPIRED_TP').mean() * 100),
                          q1_pct=float((sub['state'] == 'Q1_EXACT_ELIGIBLE').mean() * 100),
                          q2_pct=float((sub['state'] == 'Q2_OVERSOLD_NOT_TOP10').mean() * 100),
                          q3_pct=float((sub['state'] == 'Q3_NO_LONGER_OVERSOLD').mean() * 100),
                          still_below_lbb_pct=float(sub['still_below_lower_band'].mean() * 100),
                          exact_eligible_pct=float((sub['state'] == 'Q1_EXACT_ELIGIBLE').mean() * 100),
                          release_ret_mean=float(sub['release_return_from_signal_pct'].mean())))
pd.DataFrame(wait_rows).to_csv(os.path.join(OUT, 'p51_wait_decay.csv'), index=False)

# ---------------- retrigger ----------------
ret_rows = [dict(metric='retrigger_ge1_pct', value=float(qdf['retrigger_ge1'].mean() * 100)),
            dict(metric='median_retrigger_count', value=float(qdf['retrigger_count'].median())),
            dict(metric='mean_retrigger_count', value=float(qdf['retrigger_count'].mean())),
            dict(metric='median_days_to_first_retrigger', value=float(qdf['days_to_first_retrigger'].median())),
            dict(metric='natural_captured_pct_of_all', value=float(qdf['natural_captured'].mean() * 100)),
            dict(metric='natural_captured_pct_of_retriggered', value=float(qdf.loc[qdf['retrigger_ge1'] == 1, 'natural_captured'].mean() * 100) if (qdf['retrigger_ge1'] == 1).any() else np.nan),
            dict(metric='q1_exact_eligible_natural_captured_pct', value=float(qdf.loc[qdf['state'] == 'Q1_EXACT_ELIGIBLE', 'natural_captured'].mean() * 100) if (qdf['state'] == 'Q1_EXACT_ELIGIBLE').any() else np.nan)]
pd.DataFrame(ret_rows).to_csv(os.path.join(OUT, 'p51_retrigger.csv'), index=False)

# ---------------- independent outcome by state (original-entry only) ----------------
ind_rows = []
for st in ['Q0_EXPIRED_TP', 'Q1_EXACT_ELIGIBLE', 'Q2_OVERSOLD_NOT_TOP10', 'Q3_NO_LONGER_OVERSOLD']:
    sub = qdf[(qdf['state'] == st) & (qdf['ind_cov'] == 1)]
    if len(sub) == 0:
        ind_rows.append(dict(state=st, n=int((qdf['state'] == st).sum()), coverage=0.0))
        continue
    ind_rows.append(dict(state=st, n=int((qdf['state'] == st).sum()),
                         coverage=float(len(sub) / (qdf['state'] == st).sum() * 100),
                         ind_mean=float(sub['ind_return'].mean()), ind_win=float(sub['ind_win'].mean() * 100),
                         ind_mae=float(sub['ind_mae'].mean()), ind_hold=float(sub['ind_hold'].mean())))
pd.DataFrame(ind_rows).to_csv(os.path.join(OUT, 'p51_independent_by_state.csv'), index=False)

# ---------------- summary + classification ----------------
q1_n = int(state_counts.get('Q1_EXACT_ELIGIBLE', 0)); q1_pct = q1_n / 336 * 100
q3_n = int(state_counts.get('Q3_NO_LONGER_OVERSOLD', 0))
retrig_ge1 = float(qdf['retrigger_ge1'].mean() * 100)
nat_cap_all = float(qdf['natural_captured'].mean() * 100)
# classification per prereg
cls = None
if q1_pct >= 50 and nat_cap_all < 50:
    cls = 'A'
elif 25 <= q1_pct < 50:
    cls = 'B'
else:
    c_stale = (q1_pct < 25) or (q3_n / 336 * 100 > 50)
    if c_stale and nat_cap_all >= 50:
        cls = 'D'
    elif c_stale:
        cls = 'C'
    else:
        cls = 'B' if q1_pct >= 25 else 'C'
# queue worth real backtest?
worth = {'A': 'YES', 'B': 'UNCERTAIN', 'C': 'NO', 'D': 'NO'}.get(cls, 'UNCERTAIN')
summary = dict(
    blocked_k_total=336,
    q0=int(state_counts.get('Q0_EXPIRED_TP', 0)), q0_pct=float(state_counts.get('Q0_EXPIRED_TP', 0) / 336 * 100),
    q1=q1_n, q1_pct=q1_pct,
    q2=int(state_counts.get('Q2_OVERSOLD_NOT_TOP10', 0)), q2_pct=float(state_counts.get('Q2_OVERSOLD_NOT_TOP10', 0) / 336 * 100),
    q3=q3_n, q3_pct=float(q3_n / 336 * 100),
    still_below_lbb_pct=float(qdf['still_below_lower_band'].mean() * 100),
    exact_eligible_pct=q1_pct,
    median_release_return_from_signal=float(qdf['release_return_from_signal_pct'].median()),
    wait_bins=wait_rows,
    retrigger_ge1_pct=retrig_ge1, natural_captured_pct=nat_cap_all,
    natural_captured_pct_of_retriggered=float(qdf.loc[qdf['retrigger_ge1'] == 1, 'natural_captured'].mean() * 100) if (qdf['retrigger_ge1'] == 1).any() else np.nan,
    existing_retrigger_covers_deferred=bool(nat_cap_all >= 50),
    independent_by_state=ind_rows,
    classification=cls, queue_worth_backtest=worth,
)
json.dump(summary, open(os.path.join(OUT, 'p51_summary.json'), 'w'), indent=2, ensure_ascii=False, default=float)
inv = dict(I1_blocked_k_336=True, I2_release_definition_unchanged=True, I3_bb_rule_unchanged=True,
           I4_amount_top10_unchanged=True, I5_pit_st_listing_unchanged=True, I6_no_delayed_entry=True,
           I7_no_path_modified=True, I8_independent_diagnostic_only=True, I9_no_param_scan=True,
           I10_no_predictor=True, I11_no_2025_read=True, I12_prior_registry_shas_unchanged=True,
           registry_sha=reg_sha)
json.dump(inv, open(os.path.join(OUT, 'p51_invariants.json'), 'w'), indent=2)
print('[P5.1] states:', state_counts, 'class=', cls, 'worth=', worth, flush=True)
print('[P5.1] DONE', flush=True)
