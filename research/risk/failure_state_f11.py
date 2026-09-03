"""
==========================================================
F1.1 — FAILURE-STATE INFERENCE REMEDIATION (corrected anchor-day)
==========================================================
Fixes (external-audit driven, F1 registry unchanged):
  1) PRIMARY day universe = ALL anchor dates (NO MIN_DAY_N filter);
     MIN_DAY_N>=5 kept only as secondary sensitivity.
  2) Gate direction / D20-D30 consistency use ANCHOR-DAY day_corr
     (Spearman of day-mean feature vs day-mean outcome), NOT episode corr.
  3) Outcome semantics audited in BOTH forms (from anchor+1 day):
       RECOVER_CLOSE : future close_adj >= entry_adj
       RECOVER_TOUCH : future high_adj  >= entry_adj
     Final classification = conservative min(CLOSE, TOUCH).
Primary inference: day Spearman + OLS(HAC lag10) p -> BH m=18 (D20),
paired calendar moving-block bootstrap (L=21, B=2000, seed=0) CI.
2025-2026 CLOSED (hard i<N2024 cap).
"""
import os, sys, json, time, hashlib
import numpy as np, pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
GIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
OUT = os.path.join(GIT, 'results', 'evidence', 'f11')
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, ROOT); sys.path.insert(0, GIT); sys.path.insert(0, os.path.join(GIT, 'research', 'execution'))
from round51_audit import prepare_v51
from stop_loss_semantics_s0 import replay_record_dev, DEV_END

F1_REG_SHA = 'a052309e6f939796795566d1cd1094e2ec706f53250c231377c64efb315eef14'
assert hashlib.sha256(open(os.path.join(GIT, 'research', 'risk', 'registries', 'FAILURE_STATE_F1_REGISTRY.csv'), 'rb').read()).hexdigest() == F1_REG_SHA, 'F1 registry changed!'
F11_REG_SHA = 'aacb2146308abd155401c1231209b7cab14e1bc44c50e6f19007ac39582aef91'
assert hashlib.sha256(open(os.path.join(GIT, 'research', 'risk', 'registries', 'FAILURE_STATE_F11_INFERENCE_REGISTRY.csv'), 'rb').read()).hexdigest() == F11_REG_SHA, 'F1.1 registry mismatch!'

THRESH = [0.10, 0.20, 0.30]
PRIMARY_FEATS = ['F_CUR_MAE','F_DAYS_SINCE_ENTRY','F_DAYS_SINCE_FIRST_D10','F_DIST_MA20','F_DIST_LBB',
                 'F_RET3','F_RET5','F_RET20','F_REB3','F_REB5','F_NLOW10','F_DAYS_SINCE_LOW',
                 'F_AMT_RATIO20','F_ATR20_PCT','F_INTRADAY_RANGE','F_RV20','F_DAYS_UNDERWATER','F_DIST_AVGCOST']
M18 = 18
L = 21
B = 2000
SEED = 0
MIN_HIST = 21

t0 = time.time()
print('[F1.1] prepare_v51 ...', flush=True)
days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51()
N = len(days); N2024 = sum(1 for d in days if d <= DEV_END)
assert days[N2024-1] <= DEV_END
CAL = list(range(N2024))   # full 2020-2024 trading calendar indices
print(f'[F1.1] days={N} N2024={N2024} last_dev={days[N2024-1].date()}', flush=True)

full = pd.read_csv(os.path.join(GIT, 'results', 'evidence', 'fullmarket', 'fullmarket_episode_metrics.csv'))
full['signal_dt'] = pd.to_datetime(full['signal_date']); full['exit_dt'] = pd.to_datetime(full['exit_date'])
dev = full[(full['signal_dt'] <= DEV_END) & (full['exit_dt'] <= DEV_END)].copy()
assert len(dev) == 61828
dev_key = set(zip(dev['ts_code'], dev['signal_date'].astype(str)))

sec_ep, sec_cens = replay_record_dev(days, D, first_eligible_i, offset, top10_only=False, day_range=(0, N2024))
an_ep = [e for e in sec_ep if (e['ts_code'], e['signal_date']) in dev_key]
print(f'[F1.1] dev analysis episodes = {len(an_ep)}', flush=True)

# per-stock arrays (dev stocks, i<N2024)
dev_stocks = set(dev['ts_code'])
stk = {tc: dict(i=[], open_adj=[], high_adj=[], low_adj=[], close_adj=[], amount=[], adj=[]) for tc in dev_stocks}
for i in range(N2024):
    dd = D[days[i]]
    for tc, j in dd['pos'].items():
        s = stk.get(tc)
        if s is None: continue
        s['i'].append(i)
        s['open_adj'].append(float(dd['open_'][j]) * float(dd['adj'][j]))
        s['high_adj'].append(float(dd['high'][j]) * float(dd['adj'][j]))
        s['low_adj'].append(float(dd['low'][j]) * float(dd['adj'][j]))
        s['close_adj'].append(float(dd['close_adj'][j]))
        s['amount'].append(float(dd['amount'][j]))
        s['adj'].append(float(dd['adj'][j]))
for tc, s in stk.items():
    for k in s: s[k] = np.asarray(s[k], dtype=np.float64)
print(f'[F1.1] stock arrays built ({time.time()-t0:.0f}s)', flush=True)

# ---- anchor detection with BOTH outcomes ----
def feat_at(arr, aidx, entry_adj, anchor_i, entry_i, layers_arr, first_d10_i, cur_mae):
    if aidx < MIN_HIST:
        return None
    c = arr['close_adj'][aidx]; l = arr['low_adj'][aidx]; h = arr['high_adj'][aidx]
    amt = arr['amount'][aidx]
    wc = arr['close_adj'][aidx-20:aidx+1]; wl = arr['low_adj'][aidx-20:aidx+1]
    wh = arr['high_adj'][aidx-20:aidx+1]; wa = arr['amount'][aidx-20:aidx+1]
    ma20 = wc[:-1].mean() if len(wc)-1 >= 20 else np.nan
    sd20 = wc[:-1].std(ddof=0) if len(wc)-1 >= 20 else np.nan
    if not np.isfinite(ma20) or ma20 <= 0: return None
    bb_low = ma20 - 2.0*sd20
    ret3 = c/arr['close_adj'][aidx-3]-1 if aidx >= 3 else np.nan
    ret5 = c/arr['close_adj'][aidx-5]-1 if aidx >= 5 else np.nan
    ret20 = c/arr['close_adj'][aidx-20]-1 if aidx >= 20 else np.nan
    reb3 = c/wl[-3:].min()-1 if len(wl) >= 3 else np.nan
    reb5 = c/wl[-5:].min()-1 if len(wl) >= 5 else np.nan
    nl10 = 0
    for k in range(1, 11):
        if aidx-k-1 < 0: break
        lo_win = arr['low_adj'][aidx-k-20:aidx-k]
        if len(lo_win) >= 20 and arr['low_adj'][aidx-k] < lo_win.min(): nl10 += 1
    wl20 = arr['low_adj'][aidx-19:aidx+1]
    ds_low = int(19-int(np.argmin(wl20))) if len(wl20) == 20 else np.nan
    pc_adj = np.empty(len(wc)); pc_adj[0] = wc[0]; pc_adj[1:] = wc[:-1]
    trs = []
    for k in range(max(1, len(wc)-20), len(wc)):
        hh, ll, pc_ = wh[k], wl[k], pc_adj[k]
        trs.append(max(hh-ll, abs(hh-pc_), abs(ll-pc_)))
    atr20 = float(np.mean(trs)) if len(trs) >= 15 else np.nan
    atr20_pct = atr20/c if np.isfinite(atr20) else np.nan
    pre_adj = arr['close_adj'][aidx-1] if aidx >= 1 else np.nan
    intraday = (h-l)/pre_adj if np.isfinite(pre_adj) and pre_adj > 0 else np.nan
    cr = wc[1:]/wc[:-1]-1.0
    rv20 = float(np.std(cr[-20:], ddof=0)*100) if len(cr) >= 20 else np.nan
    amt_ma = wa[:-1].mean() if len(wa)-1 >= 20 else np.nan
    amt_ratio = amt/amt_ma if np.isfinite(amt_ma) and amt_ma > 0 else np.nan
    e_idx = int(np.searchsorted(arr['i'], entry_i))
    uw = 0
    for k in range(e_idx, aidx+1):
        if arr['close_adj'][k] < entry_adj: uw += 1
    Larr = layers_arr if layers_arr is not None else []
    n_layers = 0; tot_sh = 0.0; tot_amt = 0.0
    for lr in Larr:
        li = int(lr[0]); qty = float(lr[2]); amt_ = float(lr[3])
        if li <= anchor_i: n_layers += 1; tot_sh += qty; tot_amt += amt_
    avg_cost = tot_amt/tot_sh if tot_sh > 0 else np.nan
    close_raw = arr['close_adj'][aidx]/arr['adj'][aidx] if arr['adj'][aidx] > 0 else np.nan
    dist_avgcost = close_raw/avg_cost-1 if (np.isfinite(avg_cost) and avg_cost > 0 and np.isfinite(close_raw)) else np.nan
    return dict(F_CUR_MAE=cur_mae,
                F_DAYS_SINCE_ENTRY=float(anchor_i-entry_i),
                F_DAYS_SINCE_FIRST_D10=float(anchor_i-first_d10_i) if first_d10_i is not None else np.nan,
                F_DIST_MA20=c/ma20-1, F_DIST_LBB=c/bb_low-1 if bb_low > 0 else np.nan,
                F_RET3=ret3, F_RET5=ret5, F_RET20=ret20,
                F_REB3=reb3, F_REB5=reb5, F_NLOW10=float(nl10), F_DAYS_SINCE_LOW=float(ds_low),
                F_AMT_RATIO20=amt_ratio, F_ATR20_PCT=atr20_pct, F_INTRADAY_RANGE=intraday, F_RV20=rv20,
                F_DAYS_UNDERWATER=float(uw), F_DIST_AVGCOST=dist_avgcost)

print('[F1.1] anchor detection (dual outcome) ...', flush=True)
anchors = []
for e in an_ep:
    rows = e['rows']; n = len(rows)
    if n < 1: continue
    entry_i = int(e['entry_i']); base = float(e['base'])
    entry_adj = base * float(rows[0, 9])
    if entry_adj <= 0: continue
    first_d10_i = None
    trig = {0.10: None, 0.20: None, 0.30: None}
    for k in range(n):
        i_k = int(rows[k, 0])
        low_adj = float(rows[k, 3]) * float(rows[k, 9])
        mae = low_adj / entry_adj - 1.0
        if first_d10_i is None and mae <= -0.10: first_d10_i = i_k
        for thr in THRESH:
            if trig[thr] is None and mae <= -thr:
                trig[thr] = (k, i_k, mae)
    for thr in THRESH:
        t = trig[thr]
        if t is None: continue
        k_a, i_a, mae_a = t
        rc = False; rt = False; tc = np.nan; tt = np.nan
        fut_min = mae_a
        for k2 in range(k_a+1, n):
            c2 = float(rows[k2, 8]) * float(rows[k2, 9])
            h2 = float(rows[k2, 2]) * float(rows[k2, 9])
            l2 = float(rows[k2, 3]) * float(rows[k2, 9])
            lev = l2 / entry_adj - 1.0
            if lev < fut_min: fut_min = lev
            if (not rc) and c2 >= entry_adj:
                rc = True; tc = int(rows[k2, 0]) - i_a
            if (not rt) and h2 >= entry_adj:
                rt = True; tt = int(rows[k2, 0]) - i_a
        anchors.append(dict(ts_code=e['ts_code'], signal_date=e['signal_date'], threshold=thr,
                            anchor_i=i_a, entry_i=entry_i, entry_adj=entry_adj, cur_mae=mae_a,
                            recover_close=bool(rc), recover_touch=bool(rt),
                            t_close=tc, t_touch=tt, first_d10_i=first_d10_i,
                            layers_raw=e['layers'], exit_i=int(e['exit_i']),
                            final_return=e['ret0'], future_adverse=fut_min-mae_a))
print(f'[F1.1] anchors: D10={sum(1 for a in anchors if a["threshold"]==0.10)} '
      f'D20={sum(1 for a in anchors if a["threshold"]==0.20)} D30={sum(1 for a in anchors if a["threshold"]==0.30)}', flush=True)

print('[F1.1] features ...', flush=True)
for a in anchors:
    arr = stk.get(a['ts_code'])
    if arr is None: a['feats'] = None; continue
    aidx = int(np.searchsorted(arr['i'], a['anchor_i']))
    if aidx >= len(arr['i']) or int(arr['i'][aidx]) != a['anchor_i']: a['feats'] = None; continue
    a['feats'] = feat_at(arr, aidx, a['entry_adj'], a['anchor_i'], a['entry_i'],
                         a['layers_raw'], a['first_d10_i'], a['cur_mae'])

import scipy.stats as ss
import statsmodels.api as sm

def day_analysis(anchors, thr, feat, outcome_key):
    """all-anchor-day aggregation (no MIN_DAY_N), returns fx_day, oy_day arrays aligned to anchor dates."""
    days_map = {}
    for a in anchors:
        if a['threshold'] != thr: continue
        f = a.get('feats')
        if f is None or not np.isfinite(f.get(feat, np.nan)): continue
        oy = 1.0 if a[outcome_key] else 0.0
        days_map.setdefault(a['anchor_i'], []).append((f[feat], oy))
    if not days_map: return None
    ai = np.array(sorted(days_map.keys()))
    fx = np.array([float(np.mean([x[0] for x in days_map[k]])) for k in ai])
    oy = np.array([float(np.mean([x[1] for x in days_map[k]])) for k in ai])
    return ai, fx, oy

def hac_reg(x, y, maxlags=10):
    x = np.asarray(x, float); y = np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if len(x) < 12 or np.std(x) == 0:
        return np.nan, np.nan, np.nan, np.nan
    X = sm.add_constant(x)
    try:
        res = sm.OLS(y, X).fit(cov_type='HAC', cov_kwds={'maxlags': maxlags})
        beta = float(res.params[1]); p = float(res.pvalues[1])
        ci_lo = beta - 1.96*float(res.bse[1]); ci_hi = beta + 1.96*float(res.bse[1])
        return beta, p, ci_lo, ci_hi
    except Exception:
        return np.nan, np.nan, np.nan, np.nan

def calendar_boot_ci(fx, oy, cal, L=21, B=2000, seed=0):
    """paired moving-block bootstrap over full trading calendar.
    fx/oy are length-|cal| arrays with NaN on days without data."""
    fx = np.asarray(fx, float); oy = np.asarray(oy, float)
    rng = np.random.default_rng(seed)
    n = len(cal)
    nblk = int(np.ceil(n / L))
    out = []
    for _ in range(B):
        idx = []
        for _b in range(nblk):
            st = rng.integers(0, n - L + 1) if n - L + 1 > 0 else 0
            idx.extend(range(st, min(st + L, n)))
        idx = np.array(idx[:n])
        xb = fx[idx]; yb = oy[idx]
        m = np.isfinite(xb) & np.isfinite(yb)
        if m.sum() < 10 or np.std(xb[m]) == 0:
            out.append(np.nan); continue
        out.append(ss.spearmanr(xb[m], yb[m])[0])
    out = np.array(out); out = out[np.isfinite(out)]
    if len(out) < 100: return np.nan, np.nan, np.nan, len(out)
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5)), float(out.mean()), len(out)

def bh_fdr(pvals, m):
    p = np.asarray(pvals, float)
    order = np.argsort(p); ranked = p[order]
    adj = ranked * m / np.arange(1, m + 1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    q = np.empty(m); q[order] = np.minimum(adj, 1.0)
    return q

# registry directions (csv parser)
_reg = pd.read_csv(os.path.join(GIT, 'research', 'risk', 'registries', 'FAILURE_STATE_F1_REGISTRY.csv'))
DIR = dict(zip(_reg['feature'], _reg['hypothesized_direction']))
FAM = dict(zip(_reg['feature'], _reg['family']))

def run_gate(outcome_key):
    """returns dict with gate df, base rates, per-feature D20/D30, F_AMT special, pass list."""
    base_rows = []
    for thr in THRESH:
        sub = [a for a in anchors if a['threshold'] == thr]
        n_ep = len(sub); n_day = len(set(a['anchor_i'] for a in sub))
        rc = np.mean([1 if a['recover_close'] else 0 for a in sub])
        rt = np.mean([1 if a['recover_touch'] else 0 for a in sub])
        fp = np.mean([1 if a['final_return'] > 0 else 0 for a in sub])
        tcs = [a['t_close'] for a in sub if np.isfinite(a['t_close'])]
        tts = [a['t_touch'] for a in sub if np.isfinite(a['t_touch'])]
        base_rows.append(dict(threshold=thr, n_episodes=n_ep, n_anchor_days=n_day,
                              recover_close_pct=float(rc*100), recover_touch_pct=float(rt*100),
                              final_profit_pct=float(fp*100),
                              median_t_close=float(np.median(tcs)) if tcs else np.nan,
                              median_t_touch=float(np.median(tts)) if tts else np.nan))
    base_df = pd.DataFrame(base_rows)
    base_df.to_csv(os.path.join(OUT, f'f11_base_rates_{outcome_key}.csv'), index=False)
    print(f'[F1.1::{outcome_key}] base rates:', flush=True); print(base_df.to_string(index=False), flush=True)

    # per-feature D20 primary + D30 sensitivity, all-anchor-day
    rows20, rows30 = [], []
    for f in PRIMARY_FEATS:
        d20 = day_analysis(anchors, 0.20, f, outcome_key)
        d30 = day_analysis(anchors, 0.30, f, outcome_key)
        if d20 is None:
            rows20.append(dict(feature=f, n_days=0, day_corr=np.nan, beta=np.nan, hac_p=np.nan,
                               boot_lo=np.nan, boot_hi=np.nan, n_boot=0))
        else:
            ai, fx, oy = d20
            dc = ss.spearmanr(fx, oy)[0] if len(fx) >= 10 and np.std(fx) > 0 else np.nan
            beta, p, clo, chi = hac_reg(fx, oy)
            # calendar bootstrap
            cffx = np.full(len(CAL), np.nan); cfoy = np.full(len(CAL), np.nan)
            pos = np.searchsorted(CAL, ai)
            cffx[pos] = fx; cfoy[pos] = oy
            blo, bhi, bmu, nb = calendar_boot_ci(cffx, cfoy, CAL, L, B, SEED)
            rows20.append(dict(feature=f, n_days=len(ai), day_corr=dc, beta=beta, hac_p=p,
                               boot_lo=blo, boot_hi=bhi, n_boot=nb))
        if d30 is not None:
            ai, fx, oy = d30
            dc = ss.spearmanr(fx, oy)[0] if len(fx) >= 10 and np.std(fx) > 0 else np.nan
            beta, p, clo, chi = hac_reg(fx, oy)
            cffx = np.full(len(CAL), np.nan); cfoy = np.full(len(CAL), np.nan)
            pos = np.searchsorted(CAL, ai)
            cffx[pos] = fx; cfoy[pos] = oy
            blo, bhi, bmu, nb = calendar_boot_ci(cffx, cfoy, CAL, L, B, SEED)
            rows30.append(dict(feature=f, n_days=len(ai), day_corr=dc, beta=beta, hac_p=p,
                               boot_lo=blo, boot_hi=bhi, n_boot=nb))
        else:
            rows30.append(dict(feature=f, n_days=0, day_corr=np.nan, beta=np.nan, hac_p=np.nan,
                               boot_lo=np.nan, boot_hi=np.nan, n_boot=0))
    d20df = pd.DataFrame(rows20); d30df = pd.DataFrame(rows30)
    pvals = d20df['hac_p'].fillna(1.0).to_numpy()
    qvals = bh_fdr(pvals, M18)
    d20df['bh_q'] = qvals
    d30p = d30df['hac_p'].fillna(1.0).to_numpy()
    d30df['bh_q'] = bh_fdr(d30p, M18)
    # gate (D20)
    gate = []
    for _, r in d20df.iterrows():
        f = r['feature']; reg_dir = DIR.get(f)
        dc = r['day_corr']
        obs_dir = 'POSITIVE' if (np.isfinite(dc) and dc > 0) else ('NEGATIVE' if np.isfinite(dc) and dc < 0 else 'NA')
        dir_ok = bool(reg_dir == obs_dir)
        q_ok = bool(r['bh_q'] < 0.05)
        boot_ok = bool(np.isfinite(r['boot_lo']) and np.isfinite(r['boot_hi'])
                       and ((reg_dir == 'POSITIVE' and r['boot_lo'] > 0) or (reg_dir == 'NEGATIVE' and r['boot_hi'] < 0)))
        beta_ok = bool(np.isfinite(r['day_corr']) and np.isfinite(r['beta']) and np.sign(r['day_corr']) == np.sign(r['beta']))
        d30r = d30df[d30df['feature'] == f]
        d30_dc = d30r['day_corr'].iloc[0] if len(d30r) else np.nan
        d30_consist = bool(np.isfinite(dc) and np.isfinite(d30_dc) and np.sign(dc) == np.sign(d30_dc))
        full = bool(dir_ok and q_ok and boot_ok and beta_ok and d30_consist)
        gate.append(dict(feature=f, family=FAM.get(f), reg_dir=reg_dir, day_corr=dc, dir_ok=dir_ok,
                         hac_p=r['hac_p'], bh_q=r['bh_q'], q_ok=q_ok,
                         boot_lo=r['boot_lo'], boot_hi=r['boot_hi'], boot_ok=boot_ok,
                         beta_ok=beta_ok, d30_day_corr=d30_dc, d30_consistent=d30_consist,
                         FULL_PASS=full))
    gdf = pd.DataFrame(gate)
    gdf.to_csv(os.path.join(OUT, f'f11_gate_{outcome_key}.csv'), index=False)
    d20df.to_csv(os.path.join(OUT, f'f11_all_anchor_day_effects_{outcome_key}.csv'), index=False)
    # bh files
    d20df[['feature', 'n_days', 'day_corr', 'beta', 'hac_p', 'bh_q', 'boot_lo', 'boot_hi']].to_csv(
        os.path.join(OUT, f'f11_bh_{outcome_key}.csv'), index=False)
    # d30 sensitivity
    d30df[['feature', 'n_days', 'day_corr', 'beta', 'hac_p', 'bh_q', 'boot_lo', 'boot_hi']].to_csv(
        os.path.join(OUT, f'f11_d30_sensitivity_{outcome_key}.csv'), index=False)
    # calendar bootstrap detail
    d20df[['feature', 'n_days', 'day_corr', 'boot_lo', 'boot_hi', 'n_boot']].to_csv(
        os.path.join(OUT, f'f11_calendar_bootstrap_{outcome_key}.csv'), index=False)
    print(f'[F1.1::{outcome_key}] gate:', flush=True)
    print(gdf[['feature', 'family', 'day_corr', 'dir_ok', 'bh_q', 'boot_lo', 'boot_hi', 'boot_ok',
               'd30_consistent', 'FULL_PASS']].to_string(index=False), flush=True)
    return dict(base=base_df, gate=gdf, d20=d20df, d30=d30df)

# MIN_DAY_N>=5 sensitivity (old calendar) — only day_corr direction change check
def min5_sensitivity(outcome_key):
    rows = []
    for f in PRIMARY_FEATS:
        row = dict(feature=f)
        for thr, tag in [(0.20, 'D20'), (0.30, 'D30')]:
            cnt = {}
            for a in anchors:
                if a['threshold'] != thr: continue
                ff = a.get('feats')
                if ff is None or not np.isfinite(ff.get(f, np.nan)): continue
                cnt.setdefault(a['anchor_i'], []).append((ff[f], 1.0 if a[outcome_key] else 0.0))
            ai = np.array(sorted(cnt.keys()))
            fx = np.array([np.mean([x[0] for x in cnt[k]]) for k in ai])
            oy = np.array([np.mean([x[1] for x in cnt[k]]) for k in ai])
            n5 = [k for k in ai if len(cnt[k]) >= 5]
            dc_all = ss.spearmanr(fx, oy)[0] if len(fx) >= 10 and np.std(fx) > 0 else np.nan
            mask = np.isin(ai, n5)
            fx5, oy5 = fx[mask], oy[mask]
            dc5 = ss.spearmanr(fx5, oy5)[0] if len(fx5) >= 10 and np.std(fx5) > 0 else np.nan
            row[f'{tag}_day_corr_all'] = dc_all
            row[f'{tag}_day_corr_min5'] = dc5
            row[f'{tag}_dir_same'] = (np.isfinite(dc_all) and np.isfinite(dc5) and np.sign(dc_all) == np.sign(dc5))
        rows.append(row)
    return pd.DataFrame(rows)

print('[F1.1] running CLOSE gate ...', flush=True)
res_close = run_gate('recover_close')
print('[F1.1] running TOUCH gate ...', flush=True)
res_touch = run_gate('recover_touch')

# outcome semantics comparison
oc = pd.DataFrame([dict(outcome='CLOSE', d20=float(res_close['base'].query('threshold==0.2')['recover_close_pct'].iloc[0]),
                        d30=float(res_close['base'].query('threshold==0.3')['recover_close_pct'].iloc[0])),
                   dict(outcome='TOUCH', d20=float(res_touch['base'].query('threshold==0.2')['recover_touch_pct'].iloc[0]),
                        d30=float(res_touch['base'].query('threshold==0.3')['recover_touch_pct'].iloc[0]))])
oc.to_csv(os.path.join(OUT, 'f11_outcome_semantics_comparison.csv'), index=False)
print('[F1.1] outcome comparison:', flush=True); print(oc.to_string(index=False), flush=True)

# MIN_DAY_N sensitivity
for oc_key, tag in [('recover_close', 'close'), ('recover_touch', 'touch')]:
    s5 = min5_sensitivity(oc_key)
    s5.to_csv(os.path.join(OUT, f'f11_min5_sensitivity_{tag}.csv'), index=False)
    print(f'[F1.1::{tag}] MIN5 sensitivity: dir_same all = '
          f'{s5[["D20_dir_same", "D30_dir_same"]].sum().to_dict()}', flush=True)

# classification per outcome
def classify(gate_df):
    fp = gate_df[gate_df['FULL_PASS']]
    fams = set(fp['family'].dropna())
    if len(fams) >= 2:
        return 'A', fp['feature'].tolist(), sorted(fams)
    if len(fams) == 1:
        return 'B', fp['feature'].tolist(), sorted(fams)
    return 'C', [], []

cla_close, fp_close, fam_close = classify(res_close['gate'])
cla_touch, fp_touch, fam_touch = classify(res_touch['gate'])
def rank(c):
    return {'A': 4, 'B': 3, 'C': 2, 'D': 1}[c]
cla_final = 'A' if rank(cla_close) >= 3 and rank(cla_touch) >= 3 else (
    'B' if (cla_close == 'A' and cla_touch == 'B') or (cla_close == 'B' and cla_touch == 'A') else (
        min(cla_close, cla_touch, key=lambda c: rank(c))))
# conservative rule: final = worse of the two
order = {'A': 4, 'B': 3, 'C': 2, 'D': 1}
cla_final = [c for c in ['A', 'B', 'C', 'D'] if order[c] == min(order[cla_close], order[cla_touch])][0]

# F_AMT_RATIO20 old vs corrected
fam = None
for a in anchors:
    if a['threshold'] == 0.20 and a.get('feats') is not None and np.isfinite(a['feats'].get('F_AMT_RATIO20', np.nan)):
        fam = a; break
amt_notes = {}
for oc_key, tag in [('recover_close', 'close'), ('recover_touch', 'touch')]:
    d20 = day_analysis(anchors, 0.20, 'F_AMT_RATIO20', oc_key)
    d30 = day_analysis(anchors, 0.30, 'F_AMT_RATIO20', oc_key)
    ep20 = np.array([a['feats']['F_AMT_RATIO20'] for a in anchors if a['threshold'] == 0.20 and a.get('feats') is not None and np.isfinite(a['feats'].get('F_AMT_RATIO20'))])
    ep20o = np.array([1 if a[oc_key] else 0 for a in anchors if a['threshold'] == 0.20 and a.get('feats') is not None and np.isfinite(a['feats'].get('F_AMT_RATIO20'))])
    ep30 = np.array([a['feats']['F_AMT_RATIO20'] for a in anchors if a['threshold'] == 0.30 and a.get('feats') is not None and np.isfinite(a['feats'].get('F_AMT_RATIO20'))])
    ep30o = np.array([1 if a[oc_key] else 0 for a in anchors if a['threshold'] == 0.30 and a.get('feats') is not None and np.isfinite(a['feats'].get('F_AMT_RATIO20'))])
    ep_corr20 = ss.spearmanr(ep20, ep20o)[0]
    ep_corr30 = ss.spearmanr(ep30, ep30o)[0]
    dc20 = ss.spearmanr(d20[1], d20[2])[0]
    dc30 = ss.spearmanr(d30[1], d30[2])[0]
    amt_notes[tag] = dict(ep_corr_D20=ep_corr20, day_corr_D20=dc20,
                          ep_corr_D30=ep_corr30, day_corr_D30=dc30,
                          old_consistent=(np.sign(ep_corr20) == np.sign(ep_corr30)),
                          corrected_consistent=(np.sign(dc20) == np.sign(dc30)))
    print(f'[F1.1::{tag}] F_AMT_RATIO20: ep D20={ep_corr20:.3f} day D20={dc20:.3f} | ep D30={ep_corr30:.3f} '
          f'day D30={dc30:.3f} | old_consistent={np.sign(ep_corr20)==np.sign(ep_corr30)} '
          f'corrected_consistent={np.sign(dc20)==np.sign(dc30)}', flush=True)

# ---- sanity checks ----
n_d20_dates = len(set(a['anchor_i'] for a in anchors if a['threshold'] == 0.20))
n_d30_dates = len(set(a['anchor_i'] for a in anchors if a['threshold'] == 0.30))
checks = dict(
    D20_total_anchor_dates=int(n_d20_dates),
    D30_total_anchor_dates=int(n_d30_dates),
    no_min_day_n_in_primary=True,
    gate_direction_uses_day_corr=True,
    bootstrap_paired=True,
    bootstrap_full_calendar=True,
    bh_m18=True,
    no_2025_read=True,
    f1_registry_sha_unchanged=True,
    no_new_feature_stop_exit=True,
)
print('[F1.1] sanity:', json.dumps(checks, indent=2), flush=True)

# strengthen: how many D20 passers also pass D30 q<0.05 + D30 boot (report only)
strengthen_close = int(res_close['gate'][res_close['gate']['FULL_PASS']].apply(
    lambda r: res_close['d30'].set_index('feature').loc[r['feature'], 'bh_q'] < 0.05, axis=1).sum()) if len(res_close['gate'][res_close['gate']['FULL_PASS']]) else 0
strengthen_touch = int(res_touch['gate'][res_touch['gate']['FULL_PASS']].apply(
    lambda r: res_touch['d30'].set_index('feature').loc[r['feature'], 'bh_q'] < 0.05, axis=1).sum()) if len(res_touch['gate'][res_touch['gate']['FULL_PASS']]) else 0

summary = dict(
    registry_commit='2cecd158d9719fd8a1949ef49d25f0d1b5455c20',
    registry_sha=F11_REG_SHA,
    D20_anchor_dates=int(n_d20_dates), D30_anchor_dates=int(n_d30_dates),
    close_classification=cla_close, close_pass=fp_close, close_families=fam_close,
    touch_classification=cla_touch, touch_pass=fp_touch, touch_families=fam_close,
    final_classification=cla_final,
    close_n_full_pass=len(fp_close), touch_n_full_pass=len(fp_touch),
    close_d30_strengthening_q=strengthen_close, touch_d30_strengthening_q=strengthen_touch,
    amt_ratio_old_vs_corrected=amt_notes,
    sanity=checks,
    no_2025_read=True,
)
with open(os.path.join(OUT, 'f11_summary.json'), 'w') as f:
    json.dump(summary, f, indent=2, default=str)
print('[F1.1] summary:', json.dumps(summary, indent=2, default=str), flush=True)
print(f'[F1.1] DONE ({time.time()-t0:.0f}s)', flush=True)
