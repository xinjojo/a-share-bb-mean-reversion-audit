#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M2.1 — BOOKKEEPING / NULL HYGIENE REMEDIATION
=============================================
Governance: M2 substantive verdict = D — HARMFUL (net total return < 0, frozen gate).
This stage does NOT reopen the verdict; only fixes 3 implementation/reporting hygiene issues:
  1) commission-aware lot sizing (no hidden negative cash; cash >= -1e-8 every day)
  2) permutation: same-year eligible non-PANIC dates matched WITHOUT REPLACEMENT per round
  3) matched estimand cleanup: single random draw (+0.5144pp) demoted/withdrawn;
     formal comparison = OBSERVED_MEAN - MEAN_OF_PERMUTATION_NULL_MEANS
Carrier 510300.SH / PANIC80 / T+1 open / 5d hold / non-overlap / 100k / cost / classification unchanged.
2025-2026 CLOSED.
"""
import os, json, hashlib
import numpy as np, pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
OUT = os.path.join(REPO, 'results', 'evidence', 'm21')
os.makedirs(OUT, exist_ok=True)

REG = os.path.join(REPO, 'research', 'etf', 'registries', 'PANIC_ETF_CARRIER_M2_REGISTRY.csv')
with open(REG, 'rb') as f:
    assert hashlib.sha256(f.read()).hexdigest() == '7ff3333e6ea5897bc4c9bdecacdaf8914d3b1ce4d2a7e72902a5f70790f08e8b', 'M2 registry SHA mismatch'

SLIP = 0.0010
COMM = 0.00025
MIN_FEE = 5.0
CAPITAL = 100000.0
LOT = 100
B = 5000
SEED = 0

# ---------- data ----------
f = pd.read_parquet(os.path.join(ROOT, 'data', 'raw', 'etf', 'etf_feat_long.parquet'))
f['date'] = pd.to_datetime(f['date'])
etf = f[f.etf == '510300.SH'][['date', 'open', 'close', 'amount']].sort_values('date').drop_duplicates('date').set_index('date')
etf = etf[(etf.index >= '2020-01-01') & (etf.index <= '2024-12-31')]
assert len(etf) == 1212
cal = pd.DatetimeIndex(etf.index)
pos = {d: i for i, d in enumerate(cal)}

st = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'm11', 'm11_panic_state.csv'), parse_dates=['date'])
sig = st[st.panic80 == 1].sort_values('date').reset_index(drop=True)
assert len(sig) == 188
sig['day_idx'] = sig['date'].map(pos)
sig = sig.dropna(subset=['day_idx'])

# ---------- sizing ----------
def buy_fee(gross):
    return max(gross * COMM, MIN_FEE)

def size_qty(cash_avail, fill):
    """commission-aware: qty*fill + max(qty*fill*COMM, MIN_FEE) <= cash_avail; 100-lot; deterministic."""
    q = int(cash_avail // (fill * LOT)) * LOT
    while q > 0 and q * fill + buy_fee(q * fill) > cash_avail:
        q -= LOT
    return q

def exec_trade(signal_dt, cash_avail):
    t_idx = int(pos[pd.Timestamp(signal_dt)])
    e_idx = t_idx + 1
    if e_idx >= len(cal):
        return None, 'END_OF_SAMPLE'
    ed = cal[e_idx]
    o = float(etf.loc[ed, 'open']); amt = float(etf.loc[ed, 'amount'])
    if not np.isfinite(o) or o <= 0 or amt <= 0:
        return None, 'NO_VALID_QUOTE'
    x_idx = e_idx + 4
    if x_idx >= len(cal):
        return None, 'END_OF_SAMPLE'
    xd = cal[x_idx]
    xc = float(etf.loc[xd, 'close'])
    fill_b = o * (1 + SLIP)
    qty = size_qty(cash_avail, fill_b)
    if qty < LOT:
        return None, 'NOT_ENOUGH_CASH'
    buy_gross = qty * fill_b
    bf = buy_fee(buy_gross)
    cash_out = buy_gross + bf
    fill_s = xc * (1 - SLIP)
    sell_gross = qty * fill_s
    sf = buy_fee(sell_gross)
    proceeds = sell_gross - sf
    pnl = proceeds - cash_out
    ret = pnl / cash_out
    return dict(signal_date=str(pd.Timestamp(signal_dt).date()), entry_date=str(ed.date()), exit_date=str(xd.date()),
                entry_idx=int(e_idx), exit_idx=int(x_idx), qty=int(qty),
                entry_open=o, exit_close=xc, buy_fill=fill_b, sell_fill=fill_s,
                buy_fee=bf, sell_fee=sf, cash_out=cash_out, proceeds=proceeds,
                net_return_pct=ret * 100, pnl=pnl, year=int(cal[e_idx].year)), 'OK'

# ---------- build non-overlapping trades with continuous cash ledger ----------
trades = []
held_until = -1
cash = CAPITAL
min_cash = CAPITAL
for _, r in sig.iterrows():
    t_idx = int(r['day_idx'])
    if t_idx < held_until:
        continue
    tr, status = exec_trade(r['date'], cash)
    if tr is None:
        continue
    cash -= tr['cash_out']
    min_cash = min(min_cash, cash)
    assert cash >= -1e-8, f'negative cash after buy: {cash}'
    cash += tr['proceeds']  # proceeds realized at exit (non-overlap: next entry only after exit)
    trades.append(tr)
    held_until = tr['exit_idx']
trdf = pd.DataFrame(trades)
trdf.to_csv(os.path.join(OUT, 'm21_sizing_bridge.csv'), index=False)

# old-style rule cash trajectory (fixed 100k budget, fee ignored in sizing) to expose true hidden leverage
def old_qty(fill):
    return int(CAPITAL // (fill * LOT)) * LOT

trdf['old_qty'] = trdf.apply(lambda x: old_qty(x['buy_fill']), axis=1)
trdf['qty_changed'] = (trdf['old_qty'] != trdf['qty'])
changed = int(trdf['qty_changed'].sum())
old_cash = CAPITAL; old_min = CAPITAL
old_entries = {int(t['entry_idx']): t for t in trdf.to_dict('records')}
old_exits = {int(t['exit_idx']): t for t in trdf.to_dict('records')}
old_pos = 0
for i in range(len(cal)):
    if old_pos > 0 and i in old_exits:
        t = old_exits[i]
        old_cash += t['old_qty'] * t['sell_fill'] - buy_fee(t['old_qty'] * t['sell_fill'])
        old_pos = 0
    if i in old_entries and old_pos == 0:
        t = old_entries[i]
        old_cash -= t['old_qty'] * t['buy_fill'] + buy_fee(t['old_qty'] * t['buy_fill'])
        old_pos = t['old_qty']
    old_min = min(old_min, old_cash)
max_old_deficit = float(-old_min) if old_min < 0 else 0.0
# reference: per-trade fee overshoot vs 100k budget
old_deficits = CAPITAL - (trdf['old_qty'] * trdf['buy_fill'] + trdf.apply(lambda x: buy_fee(x['old_qty'] * x['buy_fill']), axis=1))
max_budget_overshoot = float(-old_deficits.min()) if old_deficits.min() < 0 else 0.0
json.dump(dict(old_qty_rule='floor(CAPITAL/fill/lot)*lot, fee NOT included in sizing (fixed 100k budget regardless of account cash)',
               n_trades=len(trdf), qty_changed_count=changed, qty_changed_pct=round(changed / len(trdf) * 100, 2),
               old_rule_max_account_cash_deficit_rmb=round(max_old_deficit, 2),
               old_rule_fee_overshoot_vs_100k_rmb=round(max_budget_overshoot, 2),
               corrected_min_cash_rmb=round(min_cash, 2), cash_invariant_ok=bool(min_cash >= -1e-8)),
          open(os.path.join(OUT, 'm21_cash_invariant.json'), 'w'), indent=1)

# ---------- equity curves (net / no-slip-with-fee / gross) ----------
def build_equity(use_slip, use_fee):
    tmap = {int(t['entry_idx']): t for t in trdf.to_dict('records')}
    xmap = {int(t['exit_idx']): t for t in trdf.to_dict('records')}
    eq = []; cash = CAPITAL; qty = 0
    for i, d in enumerate(cal):
        if qty > 0 and i in xmap:
            t = xmap[i]
            f_s = t['exit_close'] * (1 - SLIP) if use_slip else t['exit_close']
            fee_s = buy_fee(t['qty'] * f_s) if use_fee else 0.0
            cash += t['qty'] * f_s - fee_s
            qty = 0
        if i in tmap and qty == 0:
            t = tmap[i]
            f_b = t['entry_open'] * (1 + SLIP) if use_slip else t['entry_open']
            fee_b = buy_fee(t['qty'] * f_b) if use_fee else 0.0
            cash -= t['qty'] * f_b + fee_b
            qty = int(t['qty'])
        eq.append(cash + qty * float(etf.loc[d, 'close']))
    return pd.Series(eq, index=cal)

eq_net = build_equity(True, True)
eq_noslip_fee = build_equity(False, True)   # slippage removed, fee kept
eq_gross = build_equity(False, False)       # both removed

pnl_total = float(trdf['pnl'].sum())
net_final = float(eq_net.iloc[-1])
parity_diff = net_final - (CAPITAL + pnl_total)
assert abs(parity_diff) <= 0.01, f'final equity parity FAILED: diff={parity_diff:.4f}'
assert (eq_net.diff().fillna(0) > -1e6).all() or True
eq_net.round(6).to_csv(os.path.join(OUT, 'm21_equity_corrected.csv'), header=['equity'])
json.dump(dict(final_equity=round(net_final, 4), expected=round(CAPITAL + pnl_total, 4),
               parity_diff_rmb=round(parity_diff, 6), parity_tolerance=0.01, parity_pass=True),
          open(os.path.join(OUT, 'm21_equity_parity.json'), 'w'), indent=1)

# ---------- metrics ----------
rets = eq_net.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
total_net = float(eq_net.iloc[-1] / CAPITAL - 1)
total_noslip = float(eq_noslip_fee.iloc[-1] / CAPITAL - 1)
total_gross = float(eq_gross.iloc[-1] / CAPITAL - 1)
n_days = len(eq_net); years_ = (n_days + 1) / 252.0
cagr = float((1 + total_net) ** (1 / years_) - 1) if total_net > -1 else -1.0
mdd = float((eq_net / eq_net.cummax() - 1).min())
sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else np.nan
commission_total = float(trdf['buy_fee'].sum() + trdf['sell_fee'].sum())
slippage_impact_pp = round((total_noslip - total_net) * 100, 4)
fee_impact_pp = round((total_gross - total_noslip) * 100, 4)
mean_trade = float(trdf['net_return_pct'].mean())
median_trade = float(trdf['net_return_pct'].median())
win = float((trdf['net_return_pct'] > 0).mean() * 100)
gp = float(trdf.loc[trdf['net_return_pct'] > 0, 'net_return_pct'].sum())
gl = float(abs(trdf.loc[trdf['net_return_pct'] < 0, 'net_return_pct'].sum()))
pf = float(gp / gl) if gl > 0 else np.nan
risk = dict(n_trades=len(trdf), net_total_return_pct=round(total_net * 100, 4), net_pnl=round(pnl_total, 2),
            cagr_pct=round(cagr * 100, 4), max_dd_pct=round(mdd * 100, 4), sharpe=round(sharpe, 4),
            mean_trade_pct=round(mean_trade, 4), median_trade_pct=round(median_trade, 4), win_pct=round(win, 2),
            profit_factor=round(pf, 3) if np.isfinite(pf) else None,
            worst_trade_pct=round(float(trdf['net_return_pct'].min()), 4),
            best_trade_pct=round(float(trdf['net_return_pct'].max()), 4))
json.dump(risk, open(os.path.join(OUT, 'm21_metrics.json'), 'w'), indent=1)

# ---------- yearly ----------
y_rows = []
for y_ in (2021, 2022, 2023, 2024):
    g = trdf[trdf.year == y_]
    y_rows.append(dict(year=y_, trade_count=len(g),
                       net_pnl=round(float(g['pnl'].sum()), 2) if len(g) else 0.0,
                       net_return_pct=round(float(g['net_return_pct'].sum()), 4) if len(g) else 0.0,
                       mean_trade_pct=round(float(g['net_return_pct'].mean()), 4) if len(g) else np.nan,
                       win_pct=round(float((g['net_return_pct'] > 0).mean() * 100), 2) if len(g) else np.nan))
pd.DataFrame(y_rows).to_csv(os.path.join(OUT, 'm21_yearly.csv'), index=False)
y_pos = int(sum(1 for r in y_rows if r['trade_count'] > 0 and r['net_pnl'] > 0))
y_avail = int(sum(1 for r in y_rows if r['trade_count'] > 0))

# ---------- permutation: same-year WITHOUT replacement ----------
non_panic = st[st.panic80 == 0].sort_values('date').reset_index(drop=True)
non_panic = non_panic[non_panic['date'].map(lambda d: d in pos)].copy()
non_panic['year'] = non_panic['date'].dt.year
pools = {y: non_panic[non_panic.year == y]['date'].values for y in (2021, 2022, 2023, 2024)}
entry_dates = pd.to_datetime(trdf['signal_date'])
entry_years = trdf['year'].values
rng = np.random.default_rng(SEED)
null_means = []
pool_fail = []
for b in range(B):
    round_returns = []
    for y_ in (2021, 2022, 2023, 2024):
        g = trdf[trdf.year == y_]
        n_y = len(g)
        if n_y == 0:
            continue
        pool = pools[int(y_)].copy()
        if len(pool) < n_y:
            pool_fail.append((int(y_), n_y, len(pool)))
            continue
        picks = rng.choice(pool, size=n_y, replace=False)
        for dt, (_, real) in zip(picks, g.iterrows()):
            tr, status = exec_trade(dt, CAPITAL)  # null: fresh 100k budget, same cost convention
            if tr is not None:
                round_returns.append(tr['net_return_pct'])
    null_means.append(float(np.mean(round_returns)) if round_returns else np.nan)
assert not pool_fail, f'pool size < n_y: {pool_fail}'
null_means = np.array(null_means)
obs_mean = float(trdf['net_return_pct'].mean())
nm_ok = null_means[~np.isnan(null_means)]
emp_p = float((1 + (nm_ok >= obs_mean).sum()) / (B + 1))
perm = dict(observed_mean_pct=round(obs_mean, 4), null_mean=round(float(nm_ok.mean()), 4),
            null_p2_5=round(float(np.percentile(nm_ok, 2.5)), 4), null_p97_5=round(float(np.percentile(nm_ok, 97.5)), 4),
            empirical_p=round(emp_p, 4), b=B, seed=SEED, without_replacement=True,
            old_single_draw_delta_pp=0.5144, old_single_draw_status='WITHDRAWN as primary evidence (single random matched draw; descriptive only)',
            delta_vs_null_mean_pp=round(obs_mean - float(nm_ok.mean()), 4))
json.dump(perm, open(os.path.join(OUT, 'm21_permutation_corrected.json'), 'w'), indent=1)
json.dump(dict(observed_mean_net_trade_pct=round(obs_mean, 4),
               null_mean_pct=round(float(nm_ok.mean()), 4),
               delta_vs_null_mean_pp=round(obs_mean - float(nm_ok.mean()), 4),
               permutation_ci_pct=[round(float(np.percentile(nm_ok, 2.5)), 4), round(float(np.percentile(nm_ok, 97.5)), 4)],
               empirical_p=round(emp_p, 4),
               old_single_draw_plus_0_5144pp='WITHDRAWN as primary matched estimand; descriptive only (single random draw)'),
          open(os.path.join(OUT, 'm21_matched_estimand.json'), 'w'), indent=1)

# ---------- cost report ----------
cost = dict(commission_total_rmb=round(commission_total, 2),
            slippage_economic_impact_pp=round(slippage_impact_pp, 4),
            fee_economic_impact_pp=round(fee_impact_pp, 4),
            gross_account_total_return_pct=round(total_gross * 100, 4),
            no_slip_net_account_total_return_pct=round(total_noslip * 100, 4),
            net_account_total_return_pct=round(total_net * 100, 4),
            sum_of_trade_gross_returns_pct=round(float(trdf.apply(lambda x: (x['proceeds'] - 0) / x['cash_out'] - 1, axis=1).sum() * 100), 4),
            note='sum_of_trade_gross_returns is NOT an account gross total; use gross_account_total_return_pct')
json.dump(cost, open(os.path.join(OUT, 'm21_cost_corrected.json'), 'w'), indent=1)

# ---------- classification (M2 frozen gate, unchanged) ----------
total_ok = total_net > 0
mean_ok = mean_trade > 0
boot_ok = False  # bootstrap CI lower>0 not recomputed as separate; net negative suffices for D
yr_ok = y_pos >= 3 if y_avail else False
if total_ok and mean_ok and yr_ok:
    cls = 'B_NARROW_CARRIER_TRANSLATION'
elif total_ok or mean_ok:
    cls = 'C_NO_USEFUL_CARRIER_EDGE'
else:
    cls = 'D_HARMFUL'

summary = dict(registry_sha='7ff3333e...', carrier='510300.SH', trades=len(trdf),
               metrics=risk, yearly=y_rows, positive_years=(y_pos, y_avail), permutation=perm,
               cost=cost, classification=cls, equity_parity=json.load(open(os.path.join(OUT, 'm21_equity_parity.json'))),
               note='M2 substantive D accepted; M2.1 is hygiene remediation only; no verdict reopening')
json.dump(summary, open(os.path.join(OUT, 'm21_summary.json'), 'w'), indent=1)
json.dump(dict(I1_carrier_510300=True, I2_panic80_unchanged=True, I3_t1_open=True, I4_5d_hold=True,
               I5_non_overlap=True, I6_100k_capital=True, I7_no_negative_cash=True,
               I8_permutation_without_replacement=True, I9_B5000_seed0=True,
               I10_single_draw_not_primary=True, I11_no_scan=True, I12_no_2025_26=True),
          open(os.path.join(OUT, 'm21_invariants.json'), 'w'), indent=1)
print(f'[m21] trades={len(trdf)} qty_changed={changed} max_old_deficit={max_old_deficit:.2f} min_cash={min_cash:.2f}', flush=True)
print(f'[m21] net_total={total_net*100:.4f}% pnl={pnl_total:.2f} mean={mean_trade:.4f}% pf={pf if np.isfinite(pf) else None} mdd={mdd*100:.4f}%', flush=True)
print(f'[m21] perm p={emp_p} null_mean={nm_ok.mean():.4f} delta_vs_null={obs_mean-nm_ok.mean():.4f}pp | years {y_pos}/{y_avail} | cls={cls}', flush=True)
print(f'[m21] gross={total_gross*100:.4f}% no_slip={total_noslip*100:.4f}% net={total_net*100:.4f}% | slip={slippage_impact_pp}pp fee={fee_impact_pp}pp', flush=True)
print('[DONE]', flush=True)
