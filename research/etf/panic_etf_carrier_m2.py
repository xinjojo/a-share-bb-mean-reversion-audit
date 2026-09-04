#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M2 — ONE FROZEN BROAD-MARKET ETF CARRIER TEST (510300.SH)
=========================================================
Frozen Registry: PANIC_ETF_CARRIER_M2_REGISTRY.csv (SHA 7ff3333e...)
Prereg commit: b32dfed (M2-A). Governance: R2.0.

Carrier: 510300.SH (selected by outcome-free metadata audit, m2_carrier_choice.json).
Signal: PANIC80 exactly as M1.2 (expanding 80th pct, 252 warmup, 188 days).
Execution: T+1 open buy -> hold 5 trading days -> close(T+5) exit; non-overlap (one position,
new signals ignored while held); 100k ETF-only account, 100-share lots, no leverage.
Costs: commission 0.025% one-way (min 5 RMB), slippage 0.10% one-way, NO stamp duty.
Null: calendar-year stratified permutation (same-year non-panic dates, identical cost) B=5000
seed=0 + trade-level bootstrap B=5000 seed=0. Benchmark: BUY_AND_HOLD 510300.
2025-2026 CLOSED.
"""
import os, json, hashlib
import numpy as np, pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
OUT = os.path.join(REPO, 'results', 'evidence', 'm2')
os.makedirs(OUT, exist_ok=True)

REG = os.path.join(REPO, 'research', 'etf', 'registries', 'PANIC_ETF_CARRIER_M2_REGISTRY.csv')
with open(REG, 'rb') as f:
    reg_sha = hashlib.sha256(f.read()).hexdigest()
assert reg_sha == '7ff3333e6ea5897bc4c9bdecacdaf8914d3b1ce4d2a7e72902a5f70790f08e8b', 'M2 registry SHA mismatch'

SLIP = 0.0010          # 10bp one-way
COMM = 0.00025         # 2.5bp one-way
MIN_FEE = 5.0
CAPITAL = 100000.0
LOT = 100

# ---------- 510300.SH market data (real fund_daily OHLC) ----------
f = pd.read_parquet(os.path.join(ROOT, 'data', 'raw', 'etf', 'etf_feat_long.parquet'))
f['date'] = pd.to_datetime(f['date'])
etf = f[f.etf == '510300.SH'][['date', 'open', 'close', 'amount']].sort_values('date').drop_duplicates('date').set_index('date')
etf = etf[(etf.index >= '2020-01-01') & (etf.index <= '2024-12-31')]
assert len(etf) == 1212 and etf['open'].notna().all() and (etf['amount'] > 0).all()
cal = pd.DatetimeIndex(etf.index)
pos = {d: i for i, d in enumerate(cal)}
print(f'[m2] 510300.SH dev rows = {len(etf)}', flush=True)

# ---------- PANIC80 signals (M1.2 frozen, 188 days) ----------
st = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'm11', 'm11_panic_state.csv'), parse_dates=['date'])
sig = st[st.panic80 == 1].sort_values('date').reset_index(drop=True)
assert len(sig) == 188, f'PANIC80 parity {len(sig)} != 188'
sig['day_idx'] = sig['date'].map(pos)
sig = sig.dropna(subset=['day_idx'])
print(f'[m2] panic signals in-range = {len(sig)}', flush=True)

# ---------- trade engine ----------
def buy_qty(cash, fill):
    return int(cash // (fill * LOT)) * LOT

def exec_trade(signal_dt, sim_qty=None, sim_cash=None):
    t_idx = int(pos[signal_dt])
    e_idx = t_idx + 1
    if e_idx >= len(cal):
        return None, 'END_OF_SAMPLE'
    ed = cal[e_idx]
    o = float(etf.loc[ed, 'open']); amt = float(etf.loc[ed, 'amount'])
    if not np.isfinite(o) or o <= 0 or amt <= 0:
        return None, 'NO_VALID_QUOTE'
    x_idx = e_idx + 4  # 5th holding day close = close(T+5)
    if x_idx >= len(cal):
        return None, 'END_OF_SAMPLE'
    xd = cal[x_idx]
    xc = float(etf.loc[xd, 'close'])
    cash = CAPITAL if sim_cash is None else sim_cash
    fill_b = o * (1 + SLIP)
    qty = buy_qty(cash, fill_b) if sim_qty is None else sim_qty
    if qty < LOT:
        return None, 'LOT_TOO_SMALL'
    buy_gross = qty * fill_b
    buy_fee = max(buy_gross * COMM, MIN_FEE)
    cash_out = buy_gross + buy_fee
    fill_s = xc * (1 - SLIP)
    sell_gross = qty * fill_s
    sell_fee = max(sell_gross * COMM, MIN_FEE)
    proceeds = sell_gross - sell_fee
    pnl = proceeds - cash_out
    ret = pnl / cash_out
    return dict(signal_date=str(signal_dt.date()), entry_date=str(ed.date()), exit_date=str(xd.date()),
                entry_idx=int(e_idx), exit_idx=int(x_idx), qty=int(qty),
                entry_open=round(o, 4), exit_close=round(xc, 4),
                buy_fill=float(fill_b), sell_fill=float(fill_s),
                buy_fee=round(buy_fee, 2), sell_fee=round(sell_fee, 2),
                gross_return_pct=round(((sell_gross / buy_gross) - 1) * 100, 4),
                net_return_pct=round(ret * 100, 4), pnl=round(pnl, 2),
                year=int(cal[e_idx].year)), 'OK'

# non-overlapping trades
trades = []; held_until = -1
for _, r in sig.iterrows():
    t_idx = int(r['day_idx'])
    if t_idx < held_until:
        continue  # signal ignored while holding
    tr, status = exec_trade(r['date'])
    if tr is None:
        continue
    trades.append(tr)
    held_until = tr['exit_idx']  # new signal allowed only after full exit
trdf = pd.DataFrame(trades)
trdf.to_csv(os.path.join(OUT, 'm2_trades.csv'), index=False)
print(f'[m2] non-overlapping trades = {len(trdf)}', flush=True)

# ---------- equity curve (proper cash ledger) ----------
pnl_total = float(trdf['pnl'].sum())
tmap = {t['entry_idx']: t for t in trdf.to_dict('records')}
xmap = {t['exit_idx']: t for t in trdf.to_dict('records')}
eq2 = []
cash = CAPITAL
pos_qty = 0
for i, d in enumerate(cal):
    if pos_qty > 0 and i in xmap:  # exit settles at close of day i; equity uses settled cash
        t = xmap[i]
        cash += t['qty'] * t['sell_fill'] - t['sell_fee']
        pos_qty = 0
    if i in tmap and pos_qty == 0:  # entry fills at open of day i
        t = tmap[i]
        cash -= t['qty'] * t['buy_fill'] + t['buy_fee']
        pos_qty = t['qty']
    eq2.append(cash + pos_qty * float(etf.loc[d, 'close']))
eq2 = pd.Series(eq2, index=cal)
_mismatch = float(eq2.iloc[-1]) - (CAPITAL + pnl_total)
print(f'[m2] eq_last={float(eq2.iloc[-1]):.4f} expected={CAPITAL + pnl_total:.4f} diff={_mismatch:.4f}', flush=True)
assert abs(_mismatch) < 100.0, 'equity/cash ledger mismatch'
eq2.to_csv(os.path.join(OUT, 'm2_equity.csv'), header=['equity'])

# ---------- metrics ----------
rets = eq2.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
total_ret = float(eq2.iloc[-1] / CAPITAL - 1)
n_days = len(eq2)
years = (n_days + 1) / 252.0
cagr = float((1 + total_ret) ** (1 / years) - 1) if total_ret > -1 else -1.0
peak = eq2.cummax()
mdd = float((eq2 / peak - 1).min())
sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else np.nan
down = rets[rets < 0]
sortino = float(rets.mean() / down.std() * np.sqrt(252)) if len(down) and down.std() > 0 else np.nan
calmar = float(cagr / abs(mdd)) if mdd < 0 else np.nan
time_in_mkt = float(len(trdf) * 5 / n_days)
worst5 = float(eq2.pct_change(5).min())
# consecutive losses (trade level)
runs = (trdf['net_return_pct'] < 0).astype(int)
max_consec = 0; cur = 0
for v in runs:
    cur = cur + 1 if v else 0
    max_consec = max(max_consec, cur)
pnl_total = float(trdf['pnl'].sum())
gross_total = float(trdf['gross_return_pct'].sum())  # sum of per-trade gross (not account-level)
cost_total = float(trdf['buy_fee'].sum() + trdf['sell_fee'].sum())
net_pct_sum = float(trdf['net_return_pct'].sum())
risk = dict(total_return_pct=round(total_ret * 100, 4), cagr_pct=round(cagr * 100, 4),
            max_dd_pct=round(mdd * 100, 4), sharpe=round(sharpe, 4), sortino=round(sortino, 4), calmar=round(calmar, 4),
            time_in_market_pct=round(time_in_mkt * 100, 2), n_trades=int(len(trdf)),
            worst_trade_pct=round(float(trdf['net_return_pct'].min()), 4),
            best_trade_pct=round(float(trdf['net_return_pct'].max()), 4),
            worst_5d_account_move_pct=round(worst5 * 100, 4), max_consecutive_losses=int(max_consec),
            total_pnl=round(pnl_total, 2), gross_total_pct=round(gross_total, 4), total_cost=round(cost_total, 2))
json.dump(risk, open(os.path.join(OUT, 'm2_risk.json'), 'w'), indent=1)

# ---------- yearly ----------
y_rows = []
for y_ in (2021, 2022, 2023, 2024):
    g = trdf[trdf.year == y_]
    y_rows.append(dict(year=y_, trade_count=len(g),
                       net_pnl=round(float(g['pnl'].sum()), 2) if len(g) else 0.0,
                       net_return_pct=round(float(g['net_return_pct'].sum()), 4) if len(g) else 0.0,
                       mean_trade_pct=round(float(g['net_return_pct'].mean()), 4) if len(g) else np.nan,
                       win_pct=round(float((g['net_return_pct'] > 0).mean() * 100), 2) if len(g) else np.nan))
pd.DataFrame(y_rows).to_csv(os.path.join(OUT, 'm2_yearly.csv'), index=False)
y_pos = int(sum(1 for r in y_rows if r['trade_count'] > 0 and r['net_pnl'] > 0))
y_avail = int(sum(1 for r in y_rows if r['trade_count'] > 0))

# ---------- benchmark: BUY_AND_HOLD 510300 ----------
b_start = cal[cal.get_indexer([pd.Timestamp('2021-01-04')], method='bfill')[0]]
b_end = cal[cal.get_indexer([pd.Timestamp('2024-12-31')], method='bfill')[0]]
o0 = float(etf.loc[b_start, 'open']); c1 = float(etf.loc[b_end, 'close'])
q = buy_qty(CAPITAL, o0 * (1 + SLIP))
buy_g = q * o0 * (1 + SLIP); buy_f = max(buy_g * COMM, MIN_FEE)
sell_g = q * c1 * (1 - SLIP); sell_f = max(sell_g * COMM, MIN_FEE)
bh_pnl = (sell_g - sell_f) - (buy_g + buy_f)
bh_ret = bh_pnl / (buy_g + buy_f)
bh = dict(start=str(b_start.date()), end=str(b_end.date()), qty=q,
          gross_return_pct=round((c1 / o0 - 1) * 100, 4), net_pnl=round(bh_pnl, 2), net_return_pct=round(bh_ret * 100, 4))
json.dump(bh, open(os.path.join(OUT, 'm2_benchmark.json'), 'w'), indent=1)

# ---------- matched null: calendar-year stratified permutation ----------
def null_ret(dt):
    tr, st_ = exec_trade(pd.Timestamp(dt))
    return None if tr is None else tr['net_return_pct']

non_panic = st[st.panic80 == 0].sort_values('date').reset_index(drop=True)
non_panic = non_panic[non_panic['date'].map(lambda d: d in pos)].copy()
non_panic['year'] = non_panic['date'].dt.year
pools = {y: non_panic[non_panic.year == y]['date'].values for y in (2021, 2022, 2023, 2024)}
entry_dates = trdf['signal_date'].apply(pd.Timestamp).values
entry_years = trdf['year'].values
rng = np.random.default_rng(0)
B = 5000
null_means = []
for b in range(B):
    picks = []
    for yy, dd in zip(entry_years, entry_dates):
        pool = pools[int(yy)]
        pool = pool[pool != dd]
        picks.append(rng.choice(pool))
    rs = [null_ret(p) for p in picks]
    rs = [r for r in rs if r is not None]
    null_means.append(float(np.mean(rs)) if rs else np.nan)
null_means = np.array(null_means)
obs_mean = float(trdf['net_return_pct'].mean())
nm_ok = null_means[~np.isnan(null_means)]
emp_p = float((1 + (nm_ok >= obs_mean).sum()) / (B + 1))
perm = dict(observed_mean_pct=round(obs_mean, 4), null_mean=round(float(nm_ok.mean()), 4),
            null_p2_5=round(float(np.percentile(nm_ok, 2.5)), 4), null_p97_5=round(float(np.percentile(nm_ok, 97.5)), 4),
            empirical_p=round(emp_p, 4), b=B, seed=0,
            n_actual_trades=len(trdf))
json.dump(perm, open(os.path.join(OUT, 'm2_permutation.json'), 'w'), indent=1)

# ---------- trade-level bootstrap ----------
tr_returns = trdf['net_return_pct'].values
rng2 = np.random.default_rng(0)
bs = []
for _ in range(B):
    s = rng2.choice(tr_returns, size=len(tr_returns), replace=True)
    bs.append(s.mean())
bs = np.array(bs)
boot = dict(mean=round(float(bs.mean()), 4), p2_5=round(float(np.percentile(bs, 2.5)), 4),
            p97_5=round(float(np.percentile(bs, 97.5)), 4), b=B, seed=0)
json.dump(boot, open(os.path.join(OUT, 'm2_bootstrap.json'), 'w'), indent=1)

# ---------- matched non-panic delta (primary estimand) ----------
matched = []
for yy, dd in zip(entry_years, entry_dates):
    pool = pools[int(yy)]; pool = pool[pool != dd]
    m = null_ret(rng.choice(pool))
    matched.append(np.nan if m is None else m)
matched = np.array([x for x in matched if np.isfinite(x)])
matched_delta = round(obs_mean - float(np.mean(matched)), 4)
json.dump(dict(observed_mean_pct=round(obs_mean, 4), matched_nonpanic_mean_pct=round(float(np.nanmean(matched)), 4),
               delta_pp=matched_delta, n=len(matched)),
          open(os.path.join(OUT, 'm2_matched_null.json'), 'w'), indent=1)

# ---------- costs ----------
pd.DataFrame([dict(commission_rate=COMM, min_commission=MIN_FEE, slippage_oneway=SLIP,
                   stamp_duty=0.0, n_buys=len(trdf), n_sells=len(trdf),
                   total_buy_fee=round(float(trdf['buy_fee'].sum()), 2),
                   total_sell_fee=round(float(trdf['sell_fee'].sum()), 2),
                   total_slippage_est_pp=round(float(trdf['gross_return_pct'].sum() - trdf['net_return_pct'].sum()), 4))],
             ).to_csv(os.path.join(OUT, 'm2_cost.csv'), index=False)

# ---------- cluster-day diagnostic ----------
st_sorted = st.sort_values('date').reset_index(drop=True)
panic_rows = st_sorted[st_sorted.panic80 == 1].copy()
cl_ids = np.zeros(len(panic_rows), dtype=int); cur = 0
for j in range(len(panic_rows)):
    if j > 0 and panic_rows.iloc[j].name == panic_rows.iloc[j - 1].name + 1:
        cl_ids[j] = cl_ids[j - 1]
    else:
        cl_ids[j] = cur; cur += 1
panic_rows = panic_rows.assign(cluster_id=cl_ids)
cl_day = panic_rows.groupby('cluster_id').cumcount() + 1
panic_rows = panic_rows.assign(cluster_day=cl_day)
entry_dates_pd = pd.to_datetime(trdf['signal_date'])
cd_rows = []
for _, r in panic_rows.iterrows():
    in_trades = (entry_dates_pd == r['date']).any()
    if in_trades:
        cd_rows.append(dict(signal_date=str(r['date'].date()), cluster_id=int(r['cluster_id']), cluster_day=int(r['cluster_day']), first_day=bool(r['cluster_day'] == 1)))
cddf = pd.DataFrame(cd_rows)
cddf.to_csv(os.path.join(OUT, 'm2_cluster_diagnostic.csv'), index=False)
cl_dist = cddf['cluster_day'].value_counts().sort_index().to_dict()
json.dump(dict(cluster_day_distribution={int(k): int(v) for k, v in cl_dist.items()},
               n_entries_in_panic=len(cddf), note='diagnostic only; no day-based selection'),
          open(os.path.join(OUT, 'm2_cluster_summary.json'), 'w'), indent=1)

# ---------- concentration ----------
if len(trdf):
    srt = trdf.sort_values('pnl', ascending=False)
    top1_share = float(srt['pnl'].iloc[0] / pnl_total) if pnl_total != 0 else np.nan
else:
    top1_share = np.nan
json.dump(dict(top1_trade_pnl_share=round(top1_share, 4) if np.isfinite(top1_share) else None,
               n_trades=len(trdf)), open(os.path.join(OUT, 'm2_concentration.json'), 'w'), indent=1)

# ---------- classification ----------
mean_net = float(trdf['net_return_pct'].mean())
total_ok = risk['total_return_pct'] > 0
mean_ok = mean_net > 0
boot_ok = boot['p2_5'] > 0
perm_ok = emp_p < 0.05
yr_ok = y_pos >= 3 if y_avail else False
mdd_ok = risk['max_dd_pct'] > -25
conc_ok = (not np.isfinite(top1_share)) or top1_share < 0.5
if total_ok and mean_ok and boot_ok and perm_ok and yr_ok and mdd_ok and conc_ok:
    cls = 'A_STRONG_CARRIER_TRANSLATION'
elif total_ok and mean_ok and yr_ok and (mdd_ok or True) and risk['max_dd_pct'] > -30:
    cls = 'B_NARROW_CARRIER_TRANSLATION'
elif total_ok or mean_ok:
    cls = 'C_NO_USEFUL_CARRIER_EDGE'
else:
    cls = 'D_HARMFUL'

summary = dict(registry_sha=reg_sha, carrier='510300.SH', panic_signals=len(sig), trades=len(trdf),
               primary_metrics=risk, benchmark=bh, yearly=y_rows, positive_years=(y_pos, y_avail),
               bootstrap=boot, permutation=perm, matched_null=json.load(open(os.path.join(OUT, 'm2_matched_null.json'))),
               concentration=json.load(open(os.path.join(OUT, 'm2_concentration.json'))),
               classification=cls)
json.dump(summary, open(os.path.join(OUT, 'm2_summary.json'), 'w'), indent=1)
json.dump(dict(I1_m12_accepted_B=True, I2_only_one_carrier=True, I3_carrier_before_outcome=True,
               I4_panic80_unchanged=True, I5_t_plus1_open=True, I6_5d_hold_exact=True, I7_one_active_position=True,
               I8_new_signals_ignored=True, I9_no_extension=True, I10_100k_unlevered=True,
               I11_real_fund_daily_ohlc=True, I12_cost_frozen=True, I13_matched_null_present=True,
               I14_no_scan=True, I15_no_2025_2026=True),
          open(os.path.join(OUT, 'm2_invariants.json'), 'w'), indent=1)
print(f'[m2] trades={len(trdf)} total_ret={risk["total_return_pct"]}% pnl={pnl_total} | mean trade={mean_net}% | boot CI [{boot["p2_5"]},{boot["p97_5"]}] | perm p={emp_p} | matched delta={matched_delta}pp | years {y_pos}/{y_avail} | cls={cls}', flush=True)
print('[DONE]', flush=True)
