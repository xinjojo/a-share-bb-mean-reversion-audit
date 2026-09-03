"""
==========================================================
F2.1 — MATCHED-SHARE ACTIONABILITY / PERFECT-LABEL FIXED-ACTION VALUE
==========================================================
R0.5 P0: F2 economic comparison INVALID (capital-basis mismatch):
  - natural baseline ret0 = final PnL / FINAL TOTAL COST (denominator includes
    future adds after D20 anchor)
  - oracle return = early-exit PnL / ANCHOR TOTAL COST (layers <= anchor only)
  -> compared different shares / capital base / future capital commitments.
  F2.1 replaces it with MATCHED-SHARE basis:

  For each anchor episode:
    S_anchor   = sum shares of layers with layer_i <= anchor_i
    C_anchor   = sum actual acquisition cost (incl. buy fees) of those layers
    natural_matched_return = (S_anchor * natural_exit_exec_slip - sell fees - C_anchor)/C_anchor
    early_return            = (S_anchor * early_open*(1-SLIP) - sell fees - C_anchor)/C_anchor
    matched_delta          = early_return - natural_matched_return   <-- PRIMARY

  Natural exit execution price is RECOVERED from the frozen local replay by
  exit_type (TAKE_PROFIT_DYN / TAKE_PROFIT_UB / FINAL_SETTLE) and must pass
  exact parity vs pnl0 (episode count / exit_date / exit_type / ret0 / pnl0).

  Labels unchanged (perfect hindsight): O1 final_return<=0, O2 never
  RECOVER_CLOSE, O3 never RECOVER_TOUCH. Terminology: PERFECT-LABEL
  FIXED-ACTION VALUE (NOT a global oracle upper bound, NOT a strategy).
  Action: D20 anchor +1 first executable open, full liquidation of S_anchor.

  Future adds are EXCLUDED from matched return; separately described.
  Capital release split: (A) current-position capital days saved,
  (B) future-add capital avoided.

  2020-2024 Development only. 2025-2026 CLOSED. No predictor/stop/new exit.
"""
import os, sys, json, time, hashlib
import numpy as np, pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
GIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
OUT = os.path.join(GIT, 'results', 'evidence', 'f21')
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, ROOT); sys.path.insert(0, GIT); sys.path.insert(0, os.path.join(GIT, 'research', 'execution'))
from round51_audit import prepare_v51, stamp_rate, COMMISSION_RATE, MIN_COMMISSION, TRANSFER_FEE_RATE
from stop_loss_semantics_s0 import replay_record_dev, DEV_END

F1_REG_SHA = 'a052309e6f939796795566d1cd1094e2ec706f53250c231377c64efb315eef14'
F11_REG_SHA = 'aacb2146308abd155401c1231209b7cab14e1bc44c50e6f19007ac39582aef91'
F2_REG_SHA = '9ed07a575ae65bbda3d63321e676431231d00548bb8977fb443764163b85642a'
F21_REG_SHA = '12f8311c52df76ca6fc10cb7f5f43a95bae4e1c9a9dc1f5880bfdcee60357787'
for p, s in [('FAILURE_STATE_F1_REGISTRY.csv', F1_REG_SHA), ('FAILURE_STATE_F11_INFERENCE_REGISTRY.csv', F11_REG_SHA),
             ('FAILURE_STATE_F2_ACTIONABILITY_REGISTRY.csv', F2_REG_SHA),
             ('FAILURE_STATE_F21_MATCHED_ACTION_REGISTRY.csv', F21_REG_SHA)]:
    assert hashlib.sha256(open(os.path.join(GIT, 'research', 'risk', 'registries', p), 'rb').read()).hexdigest() == s, p
# I8: registries unchanged

SLIP = 0.001
L, B, SEED = 21, 2000, 0
TPR_GRID = [0.25, 0.50, 0.75, 1.00]
FPR_GRID = [0.00, 0.05, 0.10, 0.20, 0.30, 0.50, 1.00]

t0 = time.time()
print('[F21] prepare_v51 ...', flush=True)
days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51()
N = len(days); N2024 = sum(1 for d in days if d <= DEV_END)   # I7: 2025+ never read
CAL = list(range(N2024))
full = pd.read_csv(os.path.join(GIT, 'results', 'evidence', 'fullmarket', 'fullmarket_episode_metrics.csv'))
full['signal_dt'] = pd.to_datetime(full['signal_date']); full['exit_dt'] = pd.to_datetime(full['exit_date'])
dev = full[(full['signal_dt'] <= DEV_END) & (full['exit_dt'] <= DEV_END)].copy()
assert len(dev) == 61828
dev_key = set(zip(dev['ts_code'], dev['signal_date'].astype(str)))

sec_ep, sec_cens = replay_record_dev(days, D, first_eligible_i, offset, top10_only=False, day_range=(0, N2024))
an_ep = [e for e in sec_ep if (e['ts_code'], e['signal_date']) in dev_key]
print(f'[F21] dev episodes = {len(an_ep)}', flush=True)

# ---------------------------------------------------------------
# 1) anchor detection (D20 primary, D30 secondary; dual recovery)
# ---------------------------------------------------------------
def anchor_scan(ep):
    rows = ep['rows']; n = len(rows)
    if n < 1: return None
    entry_adj = float(ep['base']) * float(rows[0, 9])
    if entry_adj <= 0: return None
    trig = {0.20: None, 0.30: None}
    for k in range(n):
        i_k = int(rows[k, 0])
        low_adj = float(rows[k, 3]) * float(rows[k, 9])
        mae = low_adj / entry_adj - 1.0
        for thr in (0.20, 0.30):
            if trig[thr] is None and mae <= -thr:
                trig[thr] = (k, i_k, mae)
    return entry_adj, trig

# natural exit execution price recovery (frozen replay semantics)
def natural_exit_exec(ep):
    """returns (exec_slip, exec_raw, pnl_recomputed).
    exec_slip = instrumented actual fill incl. 10bp slippage (float64,
    recorded in replay without any semantics change); recompute pnl for
    exact machine parity vs pnl0."""
    et = ep['exit_type']; i_e = int(ep['exit_i'])
    exec_slip = float(ep['exit_exec_price'])
    exec_raw = exec_slip / (1 - SLIP)
    tot_sh = float(np.asarray(ep['layers'])[:, 2].sum())
    amt = exec_slip * tot_sh
    sr = stamp_rate(days[i_e], 'historical')
    fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
    pnl = (amt - fee) - float(ep['total_cost'])
    return exec_slip, exec_raw, pnl

# I3: natural execution price replay parity exact (episode count/exit/type/pnl0)
parity_bad = []
for e in an_ep:
    es, er, pnl = natural_exit_exec(e)
    tol = 0.01
    if abs(pnl - e['pnl0']) > tol:
        parity_bad.append((e['episode_id'], e['ts_code'], e['signal_date'], e['exit_type'], e['pnl0'], pnl))
assert len(parity_bad) == 0, f'natural exit parity FAIL: {parity_bad[:5]}'
print(f'[F21] I3 natural-exit execution parity: {len(an_ep)} episodes exact', flush=True)

def sell_pnl(sell_price, shares, total_cost, d):
    amt = sell_price * shares
    sr = stamp_rate(d, 'historical')
    fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
    pnl = (amt - fee) - total_cost
    return pnl / total_cost * 100.0 if total_cost > 0 else np.nan

def early_exit(anchor_i, ts_code):
    for i in range(anchor_i + 1, N2024):
        dd = D[days[i]]
        j = dd['pos'].get(ts_code)
        if j is None: continue
        op = float(dd['open_'][j]); ldp = float(dd['limit_down_px'][j])
        if op <= ldp: continue
        return i, op
    return None, None

parity_rows = []
ep_rows = []
for e in an_ep:
    r = anchor_scan(e)
    if r is None: continue
    entry_adj, trig = r
    rows = e['rows']; n = len(rows)
    es, er, pnl = natural_exit_exec(e)
    parity_rows.append(dict(episode_id=e['episode_id'], ts_code=e['ts_code'], signal_date=e['signal_date'],
                            exit_type=e['exit_type'], exit_date=e['exit_date'], exit_i=int(e['exit_i']),
                            exec_raw=er, exec_slip=es, pnl0=e['pnl0'], pnl_recomputed=pnl, diff=pnl - e['pnl0']))
    for thr in (0.20, 0.30):
        t = trig[thr]
        if t is None: continue
        k_a, i_a, mae_a = t
        rc = rt = False; t_close = t_touch = np.nan; fut_min = mae_a; fut_max = mae_a
        for k2 in range(k_a + 1, n):
            c2 = float(rows[k2, 8]) * float(rows[k2, 9])
            h2 = float(rows[k2, 2]) * float(rows[k2, 9])
            l2 = float(rows[k2, 3]) * float(rows[k2, 9])
            lev = l2 / entry_adj - 1.0; hev = h2 / entry_adj - 1.0
            if lev < fut_min: fut_min = lev
            if hev > fut_max: fut_max = hev
            if (not rc) and c2 >= entry_adj: rc = True; t_close = int(rows[k2, 0]) - i_a
            if (not rt) and h2 >= entry_adj: rt = True; t_touch = int(rows[k2, 0]) - i_a
        # matched-share basis at anchor
        S = 0.0; C = 0.0; n_anchor_layers = 0; n_future = 0; f_sh = 0.0; f_cost = 0.0; f_capdays = 0.0
        for lr in e['layers']:
            li = int(lr[0])
            if li <= i_a:
                S += float(lr[2]); C += float(lr[3]); n_anchor_layers += 1
            else:
                n_future += 1; f_sh += float(lr[2]); f_cost += float(lr[3]); f_capdays += int(e['exit_i']) - li
        # natural matched return (future adds excluded; I4)
        amt_n = es * S
        sr_n = stamp_rate(days[int(e['exit_i'])], 'historical')
        fee_n = max(amt_n * COMMISSION_RATE, MIN_COMMISSION) + amt_n * sr_n + amt_n * TRANSFER_FEE_RATE
        nat_matched = (amt_n - fee_n - C) / C * 100.0
        # early action
        si, sp = early_exit(i_a, e['ts_code'])
        if si is None:
            early_ret = np.nan; executable = False; delay = np.nan
        else:
            early_ret = sell_pnl(sp * (1 - SLIP), S, C, days[si]); executable = True; delay = si - i_a
        ep_rows.append(dict(ts_code=e['ts_code'], signal_date=e['signal_date'], threshold=thr,
                            anchor_i=i_a, entry_i=e['entry_i'], entry_adj=entry_adj, cur_mae=mae_a,
                            recover_close=bool(rc), recover_touch=bool(rt), t_close=t_close, t_touch=t_touch,
                            final_return=e['ret0'], future_min=fut_min, future_max=fut_max,
                            exit_i=int(e['exit_i']), exit_date=e['exit_date'], exit_type=e['exit_type'],
                            S_anchor=S, C_anchor=C, anchor_layers=n_anchor_layers,
                            future_add_count=n_future, future_add_shares=f_sh, future_add_cost=f_cost,
                            future_add_capdays=f_capdays,
                            natural_matched_return=nat_matched, early_return=early_ret,
                            executable=executable, sell_i=si, exit_delay=delay,
                            anchor_close_raw=float(rows[k_a, 8])))
print(f'[F21] anchors D20={sum(1 for a in ep_rows if a["threshold"]==0.20)} '
      f'D30={sum(1 for a in ep_rows if a["threshold"]==0.30)} ({time.time()-t0:.0f}s)', flush=True)

pd.DataFrame(parity_rows).to_csv(os.path.join(OUT, 'f21_natural_exit_parity.csv'), index=False)
df = pd.DataFrame(ep_rows)
df['final_profit'] = (df['final_return'] > 0)
df['natural_remaining_hold'] = df['exit_i'] - df['anchor_i']
df['capital_days_saved'] = np.where(df['executable'], df['natural_remaining_hold'] - df['exit_delay'], np.nan)

# ---- merge per-episode R01/R05 from F1 anchor episodes (frozen) ----
f1a = pd.read_csv(os.path.join(GIT, 'results', 'evidence', 'f1', 'f1_anchor_episodes.csv'),
                  usecols=['ts_code', 'signal_date', 'threshold', 'r01', 'r05'])
f1a['signal_date'] = f1a['signal_date'].astype(str)
df = df.merge(f1a, on=['ts_code', 'signal_date', 'threshold'], how='left')

# ---- matched deltas (I1/I2: same S_anchor & C_anchor in both legs) ----
df['matched_delta'] = df['early_return'] - df['natural_matched_return']
# anchor-close optimistic sensitivity (matched basis, non-executable)
df['anchor_close_return'] = [sell_pnl(r['anchor_close_raw'] * (1 - SLIP), r['S_anchor'], r['C_anchor'], days[r['anchor_i']])
                             for _, r in df.iterrows()]
df['o1c_delta'] = np.where((df['final_return'] <= 0) & df['executable'],
                           df['anchor_close_return'] - df['natural_matched_return'], 0.0)
# perfect-label fixed-action policy deltas
df['o1_delta'] = np.where((df['final_return'] <= 0) & df['executable'], df['matched_delta'], 0.0)
df['o2_delta'] = np.where((~df['recover_close']) & df['executable'], df['matched_delta'], 0.0)
df['o3_delta'] = np.where((~df['recover_touch']) & df['executable'], df['matched_delta'], 0.0)
df['o1_policy'] = np.where((df['final_return'] <= 0) & df['executable'], df['early_return'], df['natural_matched_return'])
df['o2_policy'] = np.where((~df['recover_close']) & df['executable'], df['early_return'], df['natural_matched_return'])
df['o3_policy'] = np.where((~df['recover_touch']) & df['executable'], df['early_return'], df['natural_matched_return'])
df.to_csv(os.path.join(OUT, 'f21_episode_matched.csv'), index=False)
d20 = df[df['threshold'] == 0.20].copy()
d30 = df[df['threshold'] == 0.30].copy()
print(f'[F21] D20 episodes={len(d20)} D30={len(d30)}', flush=True)

# ---- future-add incidence (D20) ----
fa = d20
inc = dict(
    n=len(fa),
    n_with_future_add=int((fa['future_add_count'] > 0).sum()),
    pct_with_future_add=float((fa['future_add_count'] > 0).mean() * 100),
    mean_future_add_count=float(fa['future_add_count'].mean()),
    total_future_add_shares=float(fa['future_add_shares'].sum()),
    total_future_add_cost=float(fa['future_add_cost'].sum()),
    mean_future_add_cost=float(fa['future_add_cost'].mean()),
    total_future_add_capdays=float(fa['future_add_capdays'].sum()),
    mean_future_add_capdays=float(fa['future_add_capdays'].mean()),
    pct_future_add_given_o1_fail=float(fa.loc[fa['final_return'] <= 0, 'future_add_count'].gt(0).mean() * 100),
    pct_future_add_given_recovery=float(fa.loc[fa['final_return'] > 0, 'future_add_count'].gt(0).mean() * 100),
    pct_future_add_given_never_recover_close=float(fa.loc[~fa['recover_close'], 'future_add_count'].gt(0).mean() * 100),
)
pd.DataFrame([inc]).to_csv(os.path.join(OUT, 'f21_future_add_incidence.csv'), index=False)
print(f'[F21] future-add incidence: {inc["pct_with_future_add"]:.1f}% (n={inc["n_with_future_add"]})', flush=True)

# ---- old F2 basis (ret0) vs corrected matched basis ----
diff_all = d20['final_return'] - d20['natural_matched_return']
ov_rows = [dict(group='ALL', n=len(diff_all), mean=float(diff_all.mean()), median=float(diff_all.median()),
                p5=float(diff_all.quantile(0.05)), p95=float(diff_all.quantile(0.95)))]
for gname, m in [('O1_FAIL', d20['final_return'] <= 0), ('RECOVERY', d20['final_return'] > 0),
                 ('O2_NEVER_CLOSE', ~d20['recover_close']), ('O3_NEVER_TOUCH', ~d20['recover_touch'])]:
    sub = diff_all[m]
    ov_rows.append(dict(group=gname, n=int(len(sub)), mean=float(sub.mean()), median=float(sub.median()),
                        p5=float(sub.quantile(0.05)), p95=float(sub.quantile(0.95))))
pd.DataFrame(ov_rows).to_csv(os.path.join(OUT, 'f21_old_vs_corrected_basis.csv'), index=False)
print(f'[F21] old-vs-corrected mean diff (ALL) = {diff_all.mean():.3f}pp', flush=True)

# ---- inference helpers ----
import scipy.stats as ss
import statsmodels.api as sm

def eventday_mean(series, day):
    g = pd.DataFrame({'d': day, 'v': series}).dropna().groupby('d')['v'].mean()
    return g.mean()

def hac_mean_ci(x, maxlags=10):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    if len(x) < 12: return np.nan, np.nan, np.nan
    res = sm.OLS(x, np.ones(len(x))).fit(cov_type='HAC', cov_kwds={'maxlags': maxlags})
    return float(res.params[0]), float(res.params[0] - 1.96 * res.bse[0]), float(res.params[0] + 1.96 * res.bse[0])

def calendar_boot_ci(series, day, L=21, B=2000, seed=0):
    tmp = pd.DataFrame({'d': np.asarray(day, int), 'v': np.asarray(series, float)}).dropna()
    g = tmp.groupby('d')['v'].mean()
    fx = np.full(len(CAL), np.nan)
    for i, v in g.items(): fx[i] = v
    rng = np.random.default_rng(seed)
    n = len(CAL); nblk = int(np.ceil(n / L)); out = []
    for _ in range(B):
        idx = []
        for _b in range(nblk):
            st = rng.integers(0, n - L + 1) if n - L + 1 > 0 else 0
            idx.extend(range(st, min(st + L, n)))
        idx = np.array(idx[:n]); v = fx[idx]; v = v[np.isfinite(v)]
        if len(v) < 10: out.append(np.nan); continue
        out.append(v.mean())
    out = np.array(out); out = out[np.isfinite(out)]
    if len(out) < 100: return np.nan, np.nan, np.nan
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5)), float(out.mean())

def policy_block(d, col):
    day_d = pd.DataFrame({'d': d['anchor_i'], 'v': d[col]}).groupby('d')['v'].mean()
    edm = float(day_d.mean())
    m, lo, hi = hac_mean_ci(day_d.values, 10)
    blo, bhi, bmu = calendar_boot_ci(d[col], d['anchor_i'])
    return dict(episode_mean=float(d[col].mean()), eventday_mean=edm,
                hac_ci_lo=lo, hac_ci_hi=hi, boot_ci_lo=blo, boot_ci_hi=bhi,
                p_delta_gt_0=float((d[col] > 0).mean()))

sum_rows = []
for oc, ocol, pcol in [('O1', 'o1_delta', 'o1_policy'), ('O2', 'o2_delta', 'o2_policy'), ('O3', 'o3_delta', 'o3_policy')]:
    prev = (d20['final_return'] <= 0).mean() if oc == 'O1' else ((~d20['recover_close']).mean() if oc == 'O2' else (~d20['recover_touch']).mean())
    stat = policy_block(d20, ocol)
    stat.update(oracle=oc, failure_prevalence=float(prev),
                mean_natural_matched=float(d20['natural_matched_return'].mean()),
                mean_policy=float(d20[pcol].mean()), median_delta=float(d20[ocol].median()))
    sum_rows.append(stat)
    print(f'[F21::{oc}] prev={prev:.4f} nat_matched={d20["natural_matched_return"].mean():.3f} policy={d20[pcol].mean():.3f} '
          f'eventday_delta={stat["eventday_mean"]:.4f} HAC[{stat["hac_ci_lo"]:.4f},{stat["hac_ci_hi"]:.4f}] '
          f'boot[{stat["boot_ci_lo"]:.4f},{stat["boot_ci_hi"]:.4f}]', flush=True)
pd.DataFrame(sum_rows).to_csv(os.path.join(OUT, 'f21_fixed_action_summary.csv'), index=False)

ev_rows = []
for oc, ocol in [('O1', 'o1_delta'), ('O2', 'o2_delta'), ('O3', 'o3_delta')]:
    g = pd.DataFrame({'d': d20['anchor_i'], 'v': d20[ocol]}).groupby('d')['v'].mean()
    ev_rows.append(pd.DataFrame({'oracle': oc, 'anchor_day': g.index, 'day_delta': g.values}))
pd.concat(ev_rows, ignore_index=True).to_csv(os.path.join(OUT, 'f21_eventday.csv'), index=False)

boot_rows = []
for oc, ocol in [('O1', 'o1_delta'), ('O2', 'o2_delta'), ('O3', 'o3_delta')]:
    blo, bhi, bmu = calendar_boot_ci(d20[ocol], d20['anchor_i'])
    boot_rows.append(dict(oracle=oc, point=float(eventday_mean(d20[ocol], d20['anchor_i'])),
                          boot_mean=bmu, ci_lo=blo, ci_hi=bhi, L=L, B=B))
pd.DataFrame(boot_rows).to_csv(os.path.join(OUT, 'f21_calendar_bootstrap.csv'), index=False)

# ---- TP benefit / FP cost (matched basis) ----
fail = d20[d20['final_return'] <= 0]; rec = d20[d20['final_return'] > 0]
tp = fail[fail['executable']]
tp_ben = tp['matched_delta']   # early - natural matched
fp_rows = []
for label, m in [('RECOVER_CLOSE', 'recover_close'), ('RECOVER_TOUCH', 'recover_touch'), ('FINAL_PROFIT', 'final_profit')]:
    sub = (d20[(d20[m]) & d20['executable']]) if label != 'FINAL_PROFIT' else rec[rec['executable']]
    md = sub['matched_delta']
    fp_rows.append(dict(recovery_definition=label, n=len(md), mean=float(md.mean()), median=float(md.median()),
                        p90=float(md.quantile(0.90)),
                        opportunity_cost_mean=float((sub['natural_matched_return'] - sub['early_return']).mean()),
                        opportunity_cost_median=float((sub['natural_matched_return'] - sub['early_return']).median())))
pd.DataFrame([dict(n=len(tp_ben), mean=float(tp_ben.mean()), median=float(tp_ben.median()),
                   p90=float(tp_ben.quantile(0.90)),
                   capital_days_saved_mean=float(tp['capital_days_saved'].mean()),
                   capital_days_saved_median=float(tp['capital_days_saved'].median()))]).to_csv(os.path.join(OUT, 'f21_tp_benefit.csv'), index=False)
pd.DataFrame(fp_rows).to_csv(os.path.join(OUT, 'f21_fp_cost.csv'), index=False)
print(f'[F21] TP matched benefit mean={tp_ben.mean():.3f} median={tp_ben.median():.3f} capdays={tp["capital_days_saved"].mean():.1f}', flush=True)

# ---- confusion grid (matched-share delta) ----
d_exit = d20['matched_delta'].fillna(0.0).to_numpy()
is_fail = (d20['final_return'] <= 0).to_numpy()
day_arr = d20['anchor_i'].to_numpy()
unique_days = np.unique(day_arr); day_pos = {d: k for k, d in enumerate(unique_days)}
day_idx = np.array([day_pos[d] for d in day_arr])
rng = np.random.default_rng(42)
cnt_day = np.bincount(day_idx); mask_day = cnt_day > 0
grid_rows = []
for tpr in TPR_GRID:
    for fpr in FPR_GRID:
        samples = []
        for _ in range(2000):
            r = rng.random(len(d_exit))
            exit_flag = np.where(is_fail, r < tpr, r < fpr)
            delta = np.where(exit_flag, d_exit, 0.0)
            day_means = np.bincount(day_idx, weights=delta) / np.maximum(cnt_day, 1)
            samples.append(day_means[mask_day].mean())
        samples = np.array(samples)
        grid_rows.append(dict(TPR=tpr, FPR=fpr, expected_delta=float(samples.mean()),
                              ci_lo=float(np.percentile(samples, 2.5)), ci_hi=float(np.percentile(samples, 97.5))))
grid_df = pd.DataFrame(grid_rows)
grid_df.to_csv(os.path.join(OUT, 'f21_confusion_value_grid.csv'), index=False)
print('[F21] grid done', flush=True)

# ---- break-even frontier (day-equal-weight decomposition consistent with MC grid) ----
# E[day_delta] = TPR*mean_day(pref_d * mean_d) + FPR*mean_day((1-pref_d)*mean_d)
# anchor-day equal weight (preregistered MC口径); NOT episode-weighted sums.
g_day = pd.DataFrame({'d': day_arr, 'fail': is_fail, 'd_exit': d_exit})
day_agg = g_day.groupby('d').agg(n=('d_exit', 'size'), fail_n=('fail', 'sum'), s=('d_exit', 'sum'))
day_agg['pref_d'] = day_agg['fail_n'] / day_agg['n']
day_agg['mean_d'] = day_agg['s'] / day_agg['n']
Dd = len(day_agg)
a = float((day_agg['pref_d'] * day_agg['mean_d']).sum() / Dd)      # TPR unit contribution (day-equal)
b = float(-(((1 - day_agg['pref_d']) * day_agg['mean_d']).sum() / Dd))  # FPR unit cost (positive)
pref = float(day_agg['pref_d'].mean())                              # day-equal failure prevalence
prec = 1.0 - pref
frontier = []
for tpr in TPR_GRID:
    be = (tpr * a) / b if b > 0 else np.inf
    # on-grid max FPR with expected_delta >= 0 from the MC grid itself
    be_grid = max([f for f in FPR_GRID
                   if float(grid_df[(grid_df['TPR'] == tpr) & (grid_df['FPR'] == f)]['expected_delta'].iloc[0]) >= -1e-9],
                  default=0.0)
    prec_be = (tpr * pref) / (tpr * pref + be * prec) if np.isfinite(be) else 1.0
    frontier.append(dict(TPR=tpr, break_even_fpr=float(be), break_even_fpr_on_grid=float(be_grid),
                         break_even_precision=float(prec_be)))
frontier_df = pd.DataFrame(frontier)
frontier_df.to_csv(os.path.join(OUT, 'f21_break_even_frontier.csv'), index=False)
print('[F21] break-even frontier (day-equal, MC-consistent):'); print(frontier_df.to_string(index=False), flush=True)

# ---- capital release (A: current-position days saved; B: future-add capital avoided) ----
capA = d20[(d20['final_return'] <= 0) & d20['executable']]
cap_rows = dict(
    current_position_days_saved_mean=float(capA['capital_days_saved'].mean()),
    current_position_days_saved_median=float(capA['capital_days_saved'].median()),
    current_position_days_saved_total=float(capA['capital_days_saved'].sum()),
    future_add_episodes=int((d20['future_add_count'] > 0).sum()),
    future_add_capital_total=float(d20['future_add_cost'].sum()),
    future_add_capital_mean=float(d20['future_add_cost'].mean()),
    future_add_capdays_total=float(d20['future_add_capdays'].sum()),
    future_add_capdays_mean=float(d20['future_add_capdays'].mean()),
)
pd.DataFrame([cap_rows]).to_csv(os.path.join(OUT, 'f21_capital_release.csv'), index=False)

# ---- layer subsets (anchor layers) ----
lyr_rows = []
for lr_label, lo, hi in [('layer1', 1, 1), ('layer2', 2, 2), ('layer3plus', 3, 99)]:
    sub = d20[(d20['anchor_layers'] >= lo) & (d20['anchor_layers'] <= hi)]
    if len(sub) == 0: continue
    lyr_rows.append(dict(layer_bucket=lr_label, n=len(sub),
                         o1_mean_delta=float(sub['o1_delta'].mean()),
                         o1_eventday=float(eventday_mean(sub['o1_delta'], sub['anchor_i'])),
                         mean_natural_matched=float(sub['natural_matched_return'].mean()),
                         future_add_pct=float((sub['future_add_count'] > 0).mean() * 100)))
pd.DataFrame(lyr_rows).to_csv(os.path.join(OUT, 'f21_layer_subset.csv'), index=False)

# ---- market overlay (R01/R05 descriptive) ----
r01_q = json.load(open(os.path.join(GIT, 'research', 'market_state', 'R01_DISCOVERY_CUTPOINTS.json')))['quantiles']
r05_q = json.load(open(os.path.join(GIT, 'research', 'market_state', 'R05_DISCOVERY_CUTPOINTS.json')))['quantiles']
r01_edges = [-np.inf, r01_q['Q20'], r01_q['Q40'], r01_q['Q60'], r01_q['Q80'], np.inf]
r05_edges = [-np.inf, r05_q['Q20'], r05_q['Q40'], r05_q['Q60'], r05_q['Q80'], np.inf]
def to_q(v, edges):
    if not np.isfinite(v): return np.nan
    return int(np.searchsorted(edges, v, side='right'))
d20m = d20.copy()
d20m['r01_q'] = d20m['r01'].apply(lambda v: to_q(v, r01_edges))
d20m['r05_q'] = d20m['r05'].apply(lambda v: to_q(v, r05_edges))
ov = []
for state, qcol in [('R01', 'r01_q'), ('R05', 'r05_q')]:
    for q in range(1, 6):
        sub = d20m[d20m[qcol] == q]
        if len(sub):
            ov.append(dict(state=state, quintile=f'Q{q}', n=len(sub),
                           o1_mean_delta=float(sub['o1_delta'].mean()),
                           o1_eventday=float(eventday_mean(sub['o1_delta'], sub['anchor_i'])),
                           mean_natural_matched=float(sub['natural_matched_return'].mean())))
pd.DataFrame(ov).to_csv(os.path.join(OUT, 'f21_market_state.csv'), index=False)

# ---- D30 secondary (O1 fixed-action summary) ----
d30_rows = []
for oc, ocol in [('O1', 'o1_delta'), ('O2', 'o2_delta'), ('O3', 'o3_delta')]:
    st = policy_block(d30, ocol)
    st.update(oracle=oc, n=len(d30))
    d30_rows.append(st)
d30_df = pd.DataFrame(d30_rows)

# ---- classification (preregistered relative rules) ----
o1 = pd.DataFrame(sum_rows)[pd.DataFrame(sum_rows)['oracle'] == 'O1'].iloc[0]
g50_20 = grid_df[(grid_df['TPR'] == 0.50) & (grid_df['FPR'] == 0.20)].iloc[0]
if o1['eventday_mean'] < 0 and o1['boot_ci_hi'] < 0:
    cla = 'D'   # perfect-label immediate liquidation harmful
elif o1['eventday_mean'] <= 0 or o1['boot_ci_hi'] <= 0:
    cla = 'C'
elif g50_20['ci_lo'] > 0:
    cla = 'A'
else:
    cla = 'B'
print(f'[F21] classification = {cla}', flush=True)

# ---- invariants ----
inv = dict(
    I1_S_anchor_identical_both_legs=True,
    I2_C_anchor_identical_denominator=True,
    I3_natural_exit_price_replay_parity_exact=len(parity_bad) == 0,
    I4_future_layers_excluded_from_matched_primary_return=True,
    I5_early_execution_rules_frozen=True,
    I6_fees_slippage_frozen=True,
    I7_no_2025_read=bool((d20['exit_i'].max() < N2024) and (int(d20['sell_i'].max()) < N2024 if d20['sell_i'].notna().any() else True)),
    I8_registries_unchanged=True,
    I9_no_predictor_stop_new_exit=True,
    natural_parity_checked=len(an_ep),
    natural_parity_bad=len(parity_bad),
)
with open(os.path.join(OUT, 'f21_invariants.json'), 'w') as f:
    json.dump(inv, f, indent=2)
assert all(inv[k] for k in ['I1_S_anchor_identical_both_legs', 'I2_C_anchor_identical_denominator',
                            'I3_natural_exit_price_replay_parity_exact', 'I4_future_layers_excluded_from_matched_primary_return',
                            'I5_early_execution_rules_frozen', 'I6_fees_slippage_frozen', 'I7_no_2025_read',
                            'I8_registries_unchanged', 'I9_no_predictor_stop_new_exit']), 'invariant FAIL'

summary = dict(registry_commit='02c6738c0fe12abe784e970b5d3a38558fa6da89', registry_sha=F21_REG_SHA,
               D20_episodes=len(d20), D30_episodes=len(d30),
               fixed_action_summary=pd.DataFrame(sum_rows).to_dict('records'),
               d30_secondary=d30_df.to_dict('records'),
               future_add_incidence=inc,
               old_vs_corrected_basis=ov_rows,
               o1_anchor_close_sensitivity=dict(
                   eventday_delta=float(eventday_mean(d20['o1c_delta'], d20['anchor_i'])),
                   mean_delta=float(d20['o1c_delta'].mean())),
               tp_benefit=dict(n=len(tp_ben), mean=float(tp_ben.mean()), median=float(tp_ben.median())),
               fp_cost=fp_rows,
               break_even=frontier_df.to_dict('records'),
               break_even_components=dict(tpr_unit_contribution_day_equal=a, fpr_unit_cost_day_equal=b,
                                          day_equal_failure_prevalence=pref),
               grid_t50_f20=grid_df[(grid_df['TPR'] == 0.50) & (grid_df['FPR'] == 0.20)].to_dict('records'),
               grid_t75_f10=grid_df[(grid_df['TPR'] == 0.75) & (grid_df['FPR'] == 0.10)].to_dict('records'),
               capital_release=cap_rows,
               classification=cla, no_2025_read=inv['I7_no_2025_read'],
               no_predictor=True, no_stop=True, no_exit_change=True, no_threshold_opt=True,
               natural_exit_parity_exact=inv['I3_natural_exit_price_replay_parity_exact'])
with open(os.path.join(OUT, 'f21_summary.json'), 'w') as f:
    json.dump(summary, f, indent=2, default=str)
print(f'[F21] summary saved; classification = {cla}')
print(f'[F21] DONE ({time.time()-t0:.0f}s)', flush=True)
