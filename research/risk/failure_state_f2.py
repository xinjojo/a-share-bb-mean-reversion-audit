"""
==========================================================
F2 — FAILURE-STATE ACTIONABILITY / PERFECT-INFORMATION VALUE BOUND
==========================================================
Question: even if failure state is prospectively identifiable (F1/F1.1 = A),
how large is the ECONOMIC VALUE of acting early on truly-failing deep-MAE
episodes? This is an ORACLE / VALUE-OF-INFORMATION UPPER BOUND — NOT a
tradable strategy, NOT a predictor.

Oracles (hindsight, upper-bound diagnostic only):
  O0 = natural frozen BB exit (baseline)
  O1 = PERFECT FINAL-LOSER : exit at anchor+1 first executable open IF final
       natural return <= 0, else natural
  O2 = PERFECT NON-RECOVERY-CLOSE : exit if never RECOVER_CLOSE, else natural
  O3 = PERFECT NON-RECOVERY-TOUCH  : exit if never RECOVER_TOUCH, else natural

Execution (primary): anchor+1 first executable open = first day after anchor
with T+1 satisfied, stock present (not suspended) and open > limit_down_px;
fill at real open * (1-SLIP); same sell fee logic as frozen engine.
Sensitivity: anchor-close (optimistic, non-executable reference).

Confusion-value curve (no predictor): per (TPR,FPR) grid, randomly exit that
fraction of true-failure / true-recovery episodes; expected delta return via
MC (B=2000, anchor-day clustered) + break-even FPR frontier + precision.

2020-2024 Development only. 2025-2026 CLOSED. No predictor/stop/exit change.
"""
import os, sys, json, time, hashlib
import numpy as np, pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
GIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
OUT = os.path.join(GIT, 'results', 'evidence', 'f2')
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, ROOT); sys.path.insert(0, GIT); sys.path.insert(0, os.path.join(GIT, 'research', 'execution'))
from round51_audit import prepare_v51, stamp_rate, COMMISSION_RATE, MIN_COMMISSION, TRANSFER_FEE_RATE
from stop_loss_semantics_s0 import replay_record_dev, DEV_END

F1_REG_SHA = 'a052309e6f939796795566d1cd1094e2ec706f53250c231377c64efb315eef14'
F11_REG_SHA = 'aacb2146308abd155401c1231209b7cab14e1bc44c50e6f19007ac39582aef91'
F2_REG_SHA = '9ed07a575ae65bbda3d63321e676431231d00548bb8977fb443764163b85642a'
for p, s in [('FAILURE_STATE_F1_REGISTRY.csv', F1_REG_SHA), ('FAILURE_STATE_F11_INFERENCE_REGISTRY.csv', F11_REG_SHA),
             ('FAILURE_STATE_F2_ACTIONABILITY_REGISTRY.csv', F2_REG_SHA)]:
    assert hashlib.sha256(open(os.path.join(GIT, 'research', 'risk', 'registries', p), 'rb').read()).hexdigest() == s, p

SLIP = 0.001
L, B, SEED = 21, 2000, 0
TPR_GRID = [0.25, 0.50, 0.75, 1.00]
FPR_GRID = [0.00, 0.05, 0.10, 0.20, 0.30, 0.50, 1.00]

t0 = time.time()
print('[F2] prepare_v51 ...', flush=True)
days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51()
N = len(days); N2024 = sum(1 for d in days if d <= DEV_END)
CAL = list(range(N2024))
full = pd.read_csv(os.path.join(GIT, 'results', 'evidence', 'fullmarket', 'fullmarket_episode_metrics.csv'))
full['signal_dt'] = pd.to_datetime(full['signal_date']); full['exit_dt'] = pd.to_datetime(full['exit_date'])
dev = full[(full['signal_dt'] <= DEV_END) & (full['exit_dt'] <= DEV_END)].copy()
assert len(dev) == 61828
dev_key = set(zip(dev['ts_code'], dev['signal_date'].astype(str)))

sec_ep, sec_cens = replay_record_dev(days, D, first_eligible_i, offset, top10_only=False, day_range=(0, N2024))
an_ep = [e for e in sec_ep if (e['ts_code'], e['signal_date']) in dev_key]
print(f'[F2] dev episodes = {len(an_ep)}', flush=True)

# ---- anchor detection (D20 primary, D30 secondary; dual recovery) ----
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

ep_meta = []
for e in an_ep:
    r = anchor_scan(e)
    if r is None: continue
    entry_adj, trig = r
    rows = e['rows']; n = len(rows)
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
        # shares / total_cost at anchor
        tot_sh = 0.0; tot_amt = 0.0
        for lr in e['layers']:
            if int(lr[0]) <= i_a: tot_sh += float(lr[2]); tot_amt += float(lr[3])
        ep_meta.append(dict(ts_code=e['ts_code'], signal_date=e['signal_date'], threshold=thr,
                            anchor_i=i_a, entry_i=e['entry_i'], entry_adj=entry_adj, cur_mae=mae_a,
                            recover_close=bool(rc), recover_touch=bool(rt),
                            t_close=t_close, t_touch=t_touch,
                            final_return=e['ret0'], future_min=fut_min, future_max=fut_max,
                            exit_i=int(e['exit_i']), exit_date=e['exit_date'],
                            shares=tot_sh, total_cost=tot_amt,
                            anchor_close_raw=float(rows[k_a, 8])))
print(f'[F2] anchors D20={sum(1 for a in ep_meta if a["threshold"]==0.20)} '
      f'D30={sum(1 for a in ep_meta if a["threshold"]==0.30)} ({time.time()-t0:.0f}s)', flush=True)

# ---- oracle execution: anchor+1 first executable open ----
def oracle_exit_price(anchor_i, ts_code):
    """returns (sell_i, sell_price_raw) or (None, None) if never executable."""
    for i in range(anchor_i + 1, N2024):
        dd = D[days[i]]
        j = dd['pos'].get(ts_code)
        if j is None: continue
        op = float(dd['open_'][j]); ldp = float(dd['limit_down_px'][j])
        if op <= ldp: continue
        return i, op
    return None, None

def sell_pnl(sell_price, shares, total_cost, d):
    amt = sell_price * shares
    sr = stamp_rate(d, 'historical')
    fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
    pnl = (amt - fee) - total_cost
    return pnl / total_cost * 100.0 if total_cost > 0 else np.nan

print('[F2] oracle execution scan ...', flush=True)
oracle_rows = []
for a in ep_meta:
    si, sp = oracle_exit_price(a['anchor_i'], a['ts_code'])
    a['sell_i'] = si; a['sell_price'] = sp
    if si is None:
        a['oracle_exit_return'] = np.nan; a['exit_delay'] = np.nan; a['executable'] = False
    else:
        a['oracle_exit_return'] = sell_pnl(sp * (1 - SLIP), a['shares'], a['total_cost'], days[si])
        a['exit_delay'] = si - a['anchor_i']; a['executable'] = True
print(f'[F2] oracle exit scan done ({time.time()-t0:.0f}s)', flush=True)

df = pd.DataFrame(ep_meta)
df['natural_remaining_hold'] = df['exit_i'] - df['anchor_i']
df['capital_days_saved'] = np.where(df['executable'], df['natural_remaining_hold'] - df['exit_delay'], np.nan)
df['final_profit'] = (df['final_return'] > 0)

# ---- merge per-episode R01/R05/layer_count from F1 anchor episodes (frozen) ----
f1a = pd.read_csv(os.path.join(GIT, 'results', 'evidence', 'f1', 'f1_anchor_episodes.csv'),
                  usecols=['ts_code', 'signal_date', 'threshold', 'r01', 'r05', 'layer_count'])
f1a['signal_date'] = f1a['signal_date'].astype(str)
df = df.merge(f1a, on=['ts_code', 'signal_date', 'threshold'], how='left')
df['r01'] = df['r01'].fillna(np.nan); df['r05'] = df['r05'].fillna(np.nan)

# ---- anchor-close optimistic sensitivity (non-executable reference) ----
df['anchor_close_return'] = [sell_pnl(r['anchor_close_raw'] * (1 - SLIP), r['shares'], r['total_cost'], days[r['anchor_i']])
                             for _, r in df.iterrows()]
df['o1c_delta'] = np.where(df['final_return'] <= 0, df['anchor_close_return'] - df['final_return'], 0.0)

# oracle deltas
df['o1_delta'] = np.where((df['final_return'] <= 0) & df['executable'], df['oracle_exit_return'] - df['final_return'], 0.0)
df['o2_delta'] = np.where((~df['recover_close']) & df['executable'], df['oracle_exit_return'] - df['final_return'], 0.0)
df['o3_delta'] = np.where((~df['recover_touch']) & df['executable'], df['oracle_exit_return'] - df['final_return'], 0.0)
df['o1_oracle_return'] = np.where((df['final_return'] <= 0) & df['executable'], df['oracle_exit_return'], df['final_return'])
df['o2_oracle_return'] = np.where((~df['recover_close']) & df['executable'], df['oracle_exit_return'], df['final_return'])
df['o3_oracle_return'] = np.where((~df['recover_touch']) & df['executable'], df['oracle_exit_return'], df['final_return'])
df.to_csv(os.path.join(OUT, 'f2_oracle_episode.csv'), index=False)
d20 = df[df['threshold'] == 0.20].copy()
d30 = df[df['threshold'] == 0.30].copy()
print(f'[F2] D20 episodes={len(d20)} D30={len(d30)} ({time.time()-t0:.0f}s)', flush=True)

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
    for i, v in g.items():
        fx[i] = v
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

def oracle_block(d, col):
    """event-day aggregated mean delta + day-level HAC CI + calendar bootstrap CI."""
    day_d = pd.DataFrame({'d': d['anchor_i'], 'v': d[col]}).groupby('d')['v'].mean()
    edm = float(day_d.mean())
    m, lo, hi = hac_mean_ci(day_d.values, 10)
    blo, bhi, bmu = calendar_boot_ci(d[col], d['anchor_i'])
    return dict(episode_mean=float(d[col].mean()), eventday_mean=edm,
                hac_ci_lo=lo, hac_ci_hi=hi, boot_ci_lo=blo, boot_ci_hi=bhi,
                p_delta_gt_0=float((d[col] > 0).mean()))

# ---- oracle summary ----
oracle_sum = []
for oc, ocol, rcol in [('O1', 'o1_delta', 'o1_oracle_return'), ('O2', 'o2_delta', 'o2_oracle_return'),
                       ('O3', 'o3_delta', 'o3_oracle_return')]:
    dd = d20
    prev = (dd['final_return'] <= 0).mean() if oc == 'O1' else ((~dd['recover_close']).mean() if oc == 'O2' else (~dd['recover_touch']).mean())
    stat = oracle_block(dd, ocol)
    stat.update(oracle=oc, failure_prevalence=float(prev),
                mean_baseline=float(dd['final_return'].mean()),
                mean_oracle=float(dd[rcol].mean()),
                median_delta=float(dd[ocol].median()))
    oracle_sum.append(stat)
    print(f'[F2::{oc}] prev={prev:.4f} mean_base={dd["final_return"].mean():.3f} mean_oracle={dd[rcol].mean():.3f} '
          f'eventday_delta={stat["eventday_mean"]:.4f} HAC[{stat["hac_ci_lo"]:.4f},{stat["hac_ci_hi"]:.4f}] '
          f'boot[{stat["boot_ci_lo"]:.4f},{stat["boot_ci_hi"]:.4f}]', flush=True)
oracle_df = pd.DataFrame(oracle_sum)
oracle_df.to_csv(os.path.join(OUT, 'f2_oracle_summary.csv'), index=False)

# event-day detail + calendar bootstrap files
ev_rows = []
for oc, ocol in [('O1', 'o1_delta'), ('O2', 'o2_delta'), ('O3', 'o3_delta')]:
    g = pd.DataFrame({'d': d20['anchor_i'], 'v': d20[ocol]}).groupby('d')['v'].mean()
    ev_rows.append(pd.DataFrame({'oracle': oc, 'anchor_day': g.index, 'day_delta': g.values}))
ev = pd.concat(ev_rows, ignore_index=True)
ev.to_csv(os.path.join(OUT, 'f2_eventday.csv'), index=False)

boot_rows = []
for oc, ocol in [('O1', 'o1_delta'), ('O2', 'o2_delta'), ('O3', 'o3_delta')]:
    blo, bhi, bmu = calendar_boot_ci(d20[ocol], d20['anchor_i'])
    boot_rows.append(dict(oracle=oc, point=float(eventday_mean(d20[ocol], d20['anchor_i'])),
                          boot_mean=bmu, ci_lo=blo, ci_hi=bhi, L=L, B=B))
pd.DataFrame(boot_rows).to_csv(os.path.join(OUT, 'f2_calendar_bootstrap.csv'), index=False)

# ---- true-positive benefit / false-positive cost (O1) ----
fail = d20[d20['final_return'] <= 0]; rec = d20[d20['final_return'] > 0]
tp = fail[fail['executable']]
tp_benefit = tp['oracle_exit_return'] - tp['final_return']   # d_exit; positive = avoided loss, negative = oracle hurts
fp_cost_by_def = {}
for label, m in [('RECOVER_CLOSE', 'recover_close'), ('RECOVER_TOUCH', 'recover_touch'), ('FINAL_PROFIT', 'final_profit')]:
    if label == 'FINAL_PROFIT':
        sub = rec
        cost = sub['oracle_exit_return'] - sub['final_return']
    else:
        sub = d20[(d20[m]) & d20['executable']]   # would have recovered but wrongly exited
        cost = sub['oracle_exit_return'] - sub['final_return']
    fp_cost_by_def[label] = dict(n=len(cost), mean=float(cost.mean()), median=float(cost.median()),
                                 p90=float(cost.quantile(0.90)))
tp_df = pd.DataFrame([dict(n=len(tp_benefit), mean=float(tp_benefit.mean()), median=float(tp_benefit.median()),
                           p90=float(tp_benefit.quantile(0.90)),
                           capital_days_saved_mean=float(tp['capital_days_saved'].mean()),
                           capital_days_saved_median=float(tp['capital_days_saved'].median()))])
tp_df.to_csv(os.path.join(OUT, 'f2_tp_benefit.csv'), index=False)
fp_df = pd.DataFrame(fp_cost_by_def).T.reset_index().rename(columns={'index': 'recovery_definition'})
fp_df.to_csv(os.path.join(OUT, 'f2_fp_cost.csv'), index=False)
print(f'[F2] TP benefit mean={tp_benefit.mean():.3f} median={tp_benefit.median():.3f} '
      f'capdays={tp["capital_days_saved"].mean():.1f}', flush=True)
for k, v in fp_cost_by_def.items():
    print(f'[F2] FP cost ({k}) mean={v["mean"]:.3f} median={v["median"]:.3f} p90={v["p90"]:.3f}', flush=True)

# ---- confusion-value grid (MC, anchor-day clustered) ----
# per-episode delta if exited
d_exit = (d20['oracle_exit_return'] - d20['final_return']).fillna(0.0).to_numpy()
is_fail = (d20['final_return'] <= 0).to_numpy()
day_arr = d20['anchor_i'].to_numpy()
unique_days = np.unique(day_arr)
day_pos = {d: k for k, d in enumerate(unique_days)}
day_idx = np.array([day_pos[d] for d in day_arr])
rng = np.random.default_rng(42)
grid_rows = []
for tpr in TPR_GRID:
    for fpr in FPR_GRID:
        # expected delta via MC B=2000 (anchor-day clustered: each iteration day-mean then mean)
        samples = []
        cnt_day = np.bincount(day_idx)
        mask_day = cnt_day > 0
        for _ in range(2000):
            r = rng.random(len(d_exit))
            exit_flag = np.where(is_fail, r < tpr, r < fpr)
            delta = np.where(exit_flag, d_exit, 0.0)
            day_means = np.bincount(day_idx, weights=delta) / np.maximum(cnt_day, 1)
            samples.append(day_means[mask_day].mean())
        samples = np.array(samples)
        grid_rows.append(dict(TPR=tpr, FPR=fpr,
                              expected_delta=float(samples.mean()),
                              ci_lo=float(np.percentile(samples, 2.5)),
                              ci_hi=float(np.percentile(samples, 97.5))))
grid_df = pd.DataFrame(grid_rows)
grid_df.to_csv(os.path.join(OUT, 'f2_confusion_value_grid.csv'), index=False)
print('[F2] confusion grid done', flush=True)

# ---- break-even frontier (analytic on event-day weighted sums) ----
g_day = pd.DataFrame({'d': day_arr, 'fail': is_fail, 'd_exit': d_exit})
gg = g_day.groupby('d').agg(n=('d_exit', 'size'), fail_n=('fail', 'sum'), s=('d_exit', 'sum'))
w = gg['n'] / gg['n'].sum()
S_F = float((gg['s'] * w).sum() * (gg['fail_n'] / gg['n']).mean())  # placeholder, computed properly below
# proper: event-day weighted expected delta decomposition
# E[delta] = TPR * E[delta|fail] * P(fail) - FPR * E[-delta|rec] * P(rec), all day-weighted
day_fail = gg['fail_n'] / gg['n']
day_mean_d = gg['s'] / gg['n']
pref = float((day_fail * w).sum())            # day-weighted P(fail)
prec = 1.0 - pref
# E[delta|fail] and E[delta|rec] day-weighted
fails = g_day[g_day['fail'] == 1]; recs = g_day[g_day['fail'] == 0]
def dayw_mean(df_):
    gg_ = df_.groupby('d')['d_exit'].mean()
    w_ = df_.groupby('d')['d_exit'].size()
    w_ = w_ / w_.sum()
    return float((gg_ * w_).sum())
mdf = dayw_mean(fails); mdr = dayw_mean(recs)
# E[delta] = TPR*P(fail)*mdf + FPR*P(rec)*mdr  (mdr<0)
benefit_term = pref * mdf      # per unit TPR
cost_term = -prec * mdr        # per unit FPR (positive magnitude)
frontier = []
for tpr in TPR_GRID:
    be = (tpr * benefit_term) / cost_term if cost_term > 0 else np.inf
    be_grid = max([f for f in FPR_GRID if tpr * benefit_term - f * cost_term >= -1e-12], default=0.0)
    prec_be = (tpr * pref) / (tpr * pref + be * prec) if np.isfinite(be) else 1.0
    frontier.append(dict(TPR=tpr, break_even_fpr=float(be), break_even_fpr_on_grid=float(be_grid),
                         break_even_precision=float(prec_be)))
frontier_df = pd.DataFrame(frontier)
frontier_df.to_csv(os.path.join(OUT, 'f2_break_even_frontier.csv'), index=False)
print('[F2] break-even frontier:', flush=True); print(frontier_df.to_string(index=False), flush=True)

# precision/recall framing table
pr_rows = []
for tpr in TPR_GRID:
    for fpr in FPR_GRID:
        denom = tpr * pref + fpr * prec
        prec_ = (tpr * pref) / denom if denom > 0 else 1.0
        pr_rows.append(dict(TPR=tpr, FPR=fpr, precision=float(prec_), recall=tpr))
pd.DataFrame(pr_rows).to_csv(os.path.join(OUT, 'f2_precision_recall.csv'), index=False)

# capital days
cap = d20[(d20['final_return'] <= 0) & d20['executable']]
pd.DataFrame([dict(n=len(cap), mean=float(cap['capital_days_saved'].mean()),
                   median=float(cap['capital_days_saved'].median()),
                   total=float(cap['capital_days_saved'].sum()),
                   p90=float(cap['capital_days_saved'].quantile(0.90)))]) \
    .to_csv(os.path.join(OUT, 'f2_capital_days.csv'), index=False)

# ---- layer subset (descriptive, using frozen layer_count from F1) ----
lyr_rows = []
for lr_label, lo, hi in [('layer1', 0, 1), ('layer2', 2, 2), ('layer3plus', 3, 99)]:
    sub = d20[(d20['layer_count'] >= lo) & (d20['layer_count'] <= hi)]
    if len(sub) == 0: continue
    lyr_rows.append(dict(layer_bucket=lr_label, n=len(sub),
                         o1_mean_delta=float(sub['o1_delta'].mean()),
                         o1_eventday=float(eventday_mean(sub['o1_delta'], sub['anchor_i'])),
                         mean_baseline=float(sub['final_return'].mean())))
pd.DataFrame(lyr_rows).to_csv(os.path.join(OUT, 'f2_layer_subset.csv'), index=False)

# ---- market state overlay (frozen R01/R05 cutpoints, descriptive) ----
r01_q = json.load(open(os.path.join(GIT, 'research', 'market_state', 'R01_DISCOVERY_CUTPOINTS.json')))['quantiles']
r05_q = json.load(open(os.path.join(GIT, 'research', 'market_state', 'R05_DISCOVERY_CUTPOINTS.json')))['quantiles']
r01_edges = [-np.inf, r01_q['Q20'], r01_q['Q40'], r01_q['Q60'], r01_q['Q80'], np.inf]
r05_edges = [-np.inf, r05_q['Q20'], r05_q['Q40'], r05_q['Q60'], r05_q['Q80'], np.inf]

def to_q(v, edges):
    if not np.isfinite(v): return np.nan
    return int(np.searchsorted(edges, v, side='right'))  # 1..5

d20m = d20.copy()
d20m['r01_q'] = d20m['r01'].apply(lambda v: to_q(v, r01_edges))
d20m['r05_q'] = d20m['r05'].apply(lambda v: to_q(v, r05_edges))
ov = []
for state, qcol in [('R01', 'r01_q'), ('R05', 'r05_q')]:
    for q in range(1, 6):
        sub = d20m[d20m[qcol] == q]
        if len(sub):
            ov.append(dict(state=state, quintile=f'Q{q}', n=len(sub),
                           o1_delta=float(sub['o1_delta'].mean()),
                           o1_eventday=float(eventday_mean(sub['o1_delta'], sub['anchor_i'])),
                           baseline=float(sub['final_return'].mean())))
pd.DataFrame(ov).to_csv(os.path.join(OUT, 'f2_market_state.csv'), index=False)

# ---- classification (preregistered relative rules) ----
o1 = oracle_df[oracle_df['oracle'] == 'O1'].iloc[0]
g50_20 = grid_df[(grid_df['TPR'] == 0.50) & (grid_df['FPR'] == 0.20)].iloc[0]
if o1['eventday_mean'] < 0 and o1['boot_ci_hi'] < 0:
    cla = 'D'   # ACTIONABILITY NEGATIVE: even the perfect oracle reduces expectancy
elif o1['eventday_mean'] <= 0 or o1['boot_ci_hi'] <= 0:
    cla = 'C'
elif g50_20['ci_lo'] > 0:
    cla = 'A'
else:
    cla = 'B'
print(f'[F2] classification = {cla}', flush=True)

summary = dict(registry_commit='4e088fbf93adbe5c3340971d659fcc9843fb212e', registry_sha=F2_REG_SHA,
               D20_episodes=len(d20), D30_episodes=len(d30),
               oracle_summary=oracle_df.to_dict('records'),
               o1_anchor_close_sensitivity=dict(
                   eventday_delta=float(eventday_mean(d20['o1c_delta'], d20['anchor_i'])),
                   mean_delta=float(d20['o1c_delta'].mean())),
               tp_benefit=tp_df.to_dict('records'), fp_cost=fp_df.to_dict('records'),
               break_even=frontier_df.to_dict('records'),
               grid_t50_f20=grid_df[(grid_df['TPR'] == 0.50) & (grid_df['FPR'] == 0.20)].to_dict('records'),
               grid_t75_f10=grid_df[(grid_df['TPR'] == 0.75) & (grid_df['FPR'] == 0.10)].to_dict('records'),
               classification=cla, no_2025_read=True,
               no_predictor=True, no_stop=True, no_exit_change=True, no_threshold_opt=True)
with open(os.path.join(OUT, 'f2_summary.json'), 'w') as f:
    json.dump(summary, f, indent=2, default=str)
print('[F2] summary saved; classification =', cla)
print(f'[F2] DONE ({time.time()-t0:.0f}s)', flush=True)
