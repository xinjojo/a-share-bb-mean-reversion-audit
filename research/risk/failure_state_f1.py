"""
==========================================================
FAILURE-STATE TAXONOMY / DEEP-MAE RECOVERABILITY — F1
==========================================================
Question: at the moment an episode first reaches D20/D30 (adjusted-space MAE),
can we prospectively separate RECOVERED (mean-reversion) from FAILED paths,
using only information available at anchor close?

Discipline (frozen):
  - dev-only episodes: signal_date<=2024-12-31 AND exit_date<=2024-12-31 (61,828 SECONDARY)
  - 2025-2026 CONFIRMATION CLOSED: never read any 2025+ price / outcome (I6-style; only i<N2024)
  - Anchors D10/D20/D30 = first holding day with adjusted low <= entry_adj*(1-thr)  [observation anchors, NOT stops]
  - Outcomes: RECOVER_TO_ENTRY (any later close_adj>=entry_adj) / FINAL_PROFIT (final return>0)
  - Features: 18 primary (frozen Registry, BH m=18) + 3 secondary (R01/R05/layer, descriptive)
  - NO optimization, NO new stop, NO exit change, NO ML, NO composite
  - Primary inference: episode-level Spearman/point-biserial + anchor-day clustered HAC/block bootstrap
==========================================================
"""
import os, sys, json, time, hashlib
import numpy as np, pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
GIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
OUT = os.path.join(GIT, 'results', 'evidence', 'f1')
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, ROOT); sys.path.insert(0, GIT); sys.path.insert(0, os.path.join(GIT, 'research', 'execution'))
from round51_audit import prepare_v51
from stop_loss_semantics_s0 import replay_record_dev, DEV_END

REGISTRY_SHA = 'a052309e6f939796795566d1cd1094e2ec706f53250c231377c64efb315eef14'
# verify registry sha
_reg_sha = hashlib.sha256(open(os.path.join(GIT, 'research', 'risk', 'registries', 'FAILURE_STATE_F1_REGISTRY.csv'), 'rb').read()).hexdigest()
assert _reg_sha == REGISTRY_SHA, f'F1 registry SHA mismatch: {_reg_sha}'

THRESH = [0.10, 0.20, 0.30]   # D10 / D20 / D30
PRIMARY_FEATS = ['F_CUR_MAE','F_DAYS_SINCE_ENTRY','F_DAYS_SINCE_FIRST_D10','F_DIST_MA20','F_DIST_LBB',
                 'F_RET3','F_RET5','F_RET20','F_REB3','F_REB5','F_NLOW10','F_DAYS_SINCE_LOW',
                 'F_AMT_RATIO20','F_ATR20_PCT','F_INTRADAY_RANGE','F_RV20','F_DAYS_UNDERWATER','F_DIST_AVGCOST']
SECONDARY_FEATS = ['F_R01_RET60','F_R05_LDS','F_LAYER_COUNT']
M18 = 18
L = 21
B = 2000
SEED = 0
MIN_DAY_N = 5          # min episodes per anchor day for day-level correlation
MIN_HIST = 21          # min observed bars before anchor for MA20/ATR20/RET20

t0 = time.time()
print('[F1] prepare_v51 ...', flush=True)
days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51()
N = len(days)
N2024 = sum(1 for d in days if d <= DEV_END)
assert days[N2024 - 1] <= DEV_END and (N2024 == N or days[N2024] > DEV_END)
MAX_READ_I = N2024   # I6: hard stop at dev boundary
print(f'[F1] days={N} {days[0].date()}..{days[-1].date()} N2024={N2024} last_dev={days[N2024-1].date()}', flush=True)

# ---------------- dev universe ----------------
full = pd.read_csv(os.path.join(GIT, 'results', 'evidence', 'fullmarket', 'fullmarket_episode_metrics.csv'))
full['signal_dt'] = pd.to_datetime(full['signal_date']); full['exit_dt'] = pd.to_datetime(full['exit_date'])
dev = full[(full['signal_dt'] <= DEV_END) & (full['exit_dt'] <= DEV_END)].copy()
assert len(dev) == 61828, f'expected 61828 dev episodes, got {len(dev)}'
dev_key = set(zip(dev['ts_code'], dev['signal_date'].astype(str)))
print(f'[F1] dev episodes = {len(dev)}', flush=True)

# ---------------- re-record dev episodes (rows with adj) ----------------
sec_ep, sec_cens = replay_record_dev(days, D, first_eligible_i, offset, top10_only=False, day_range=(0, N2024))
an_ep = [e for e in sec_ep if (e['ts_code'], e['signal_date']) in dev_key]
print(f'[F1] re-recorded dev analysis episodes = {len(an_ep)}', flush=True)
dev_map = {k: row for k, row in zip(zip(dev['ts_code'], dev['signal_date'].astype(str)), dev.to_dict('records'))}
# verify
mism = 0
for e in an_ep:
    row = dev_map[(e['ts_code'], e['signal_date'])]
    if e['exit_date'] != str(pd.Timestamp(row['exit_date']).date()) or abs(e['ret0'] - float(row['simple_return_pct'])) > 0.01:
        mism += 1
assert mism == 0, 'F1 dev re-record mismatch'
print(f'[F1] re-record verify OK (n={len(an_ep)})', flush=True)

# ---------------- per-stock arrays (only dev stocks, i < N2024) ----------------
dev_stocks = set(dev['ts_code'])
print(f'[F1] dev stocks = {len(dev_stocks)}; building stock arrays ...', flush=True)
stk = {}
for tc in dev_stocks:
    stk[tc] = dict(i=[], open_adj=[], high_adj=[], low_adj=[], close_adj=[], amount=[], adj=[])
for i in range(N2024):
    dd = D[days[i]]
    for tc, j in dd['pos'].items():
        s = stk.get(tc)
        if s is None:
            continue
        s['i'].append(i)
        s['open_adj'].append(float(dd['open_'][j]) * float(dd['adj'][j]))
        s['high_adj'].append(float(dd['high'][j]) * float(dd['adj'][j]))
        s['low_adj'].append(float(dd['low'][j]) * float(dd['adj'][j]))
        s['close_adj'].append(float(dd['close_adj'][j]))
        s['amount'].append(float(dd['amount'][j]))
        s['adj'].append(float(dd['adj'][j]))
for tc, s in stk.items():
    for k in s:
        s[k] = np.asarray(s[k], dtype=np.float64)
    s['i_lookup'] = np.searchsorted(s['i'], s['i'])  # identity (arrays are sorted by i)
print(f'[F1] stock arrays built ({time.time()-t0:.0f}s)', flush=True)

# ---------------- daily market series (R01 ret60_ea, R05 limit_down) ----------------
print('[F1] computing daily market series ...', flush=True)
prev_close = {}
mkt_rows = []
for i in range(N2024):
    dd = D[days[i]]
    ts = dd['ts']; pos = dd['pos']; ca = dd['close_adj']; st = dd['is_st']; cl = dd['close']; ldpx = dd['limit_down_px']
    rr = np.full(len(ts), np.nan)
    for j, tc in enumerate(ts):
        pc = prev_close.get(tc)
        if pc is not None and pc > 0:
            rr[j] = ca[j] / pc - 1.0
    elig = (~st) & np.isfinite(rr)
    idx_ret = float(rr[elig].mean()) if elig.sum() else np.nan
    ldn = float((cl[elig] <= ldpx[elig]).mean()) if elig.sum() else np.nan
    mkt_rows.append(dict(i=i, d=str(days[i].date()), idx_ret=idx_ret, limit_down=ldn))
    for tc, j in pos.items():
        prev_close[tc] = float(ca[j])
mkt = pd.DataFrame(mkt_rows)
mkt['lvl'] = (1.0 + mkt['idx_ret'].fillna(0.0)).cumprod()
mkt['ret60_ea'] = (mkt['lvl'] / mkt['lvl'].shift(60) - 1.0) * 100
mkt['limit_down'] = mkt['limit_down']
mkt_by_i = {int(r['i']): (r['ret60_ea'], r['limit_down']) for _, r in mkt.iterrows()}
print(f'[F1] market series done ({time.time()-t0:.0f}s); n days={len(mkt)}', flush=True)

# frozen R01/R05 cutpoints
r01_q = json.load(open(os.path.join(GIT, 'research', 'market_state', 'R01_DISCOVERY_CUTPOINTS.json')))['quantiles']
r05_q = json.load(open(os.path.join(GIT, 'research', 'market_state', 'R05_DISCOVERY_CUTPOINTS.json')))['quantiles']
R01_EDGES = [r01_q['Q20'], r01_q['Q40'], r01_q['Q60'], r01_q['Q80']]
R05_EDGES = [r05_q['Q20'], r05_q['Q40'], r05_q['Q60'], r05_q['Q80']]

# ---------------- anchor detection + outcomes + features ----------------
def feat_at(arr, aidx, entry_adj, anchor_i, entry_i, entry_raw, layers_arr, first_d10_i, threshold, cur_mae):
    """compute anchor-time features; returns dict or None if insufficient history."""
    if aidx < MIN_HIST:
        return None
    iarr = arr['i']
    c = arr['close_adj'][aidx]; l = arr['low_adj'][aidx]; h = arr['high_adj'][aidx]
    amt = arr['amount'][aidx]
    wc = arr['close_adj'][aidx - 20:aidx + 1]       # 21 obs incl anchor
    wl = arr['low_adj'][aidx - 20:aidx + 1]
    wh = arr['high_adj'][aidx - 20:aidx + 1]
    wa = arr['amount'][aidx - 20:aidx + 1]
    ma20 = wc[:-1].mean() if len(wc) - 1 >= 20 else np.nan
    sd20 = wc[:-1].std(ddof=0) if len(wc) - 1 >= 20 else np.nan
    if not np.isfinite(ma20) or ma20 <= 0:
        return None
    bb_low = ma20 - 2.0 * sd20
    ret3 = c / arr['close_adj'][aidx - 3] - 1 if aidx >= 3 else np.nan
    ret5 = c / arr['close_adj'][aidx - 5] - 1 if aidx >= 5 else np.nan
    ret20 = c / arr['close_adj'][aidx - 20] - 1 if aidx >= 20 else np.nan
    reb3 = c / wl[-3:].min() - 1 if len(wl) >= 3 else np.nan
    reb5 = c / wl[-5:].min() - 1 if len(wl) >= 5 else np.nan
    # NLOW10: count of prior 10 obs (excluding anchor) with low < min(low of 20 obs before that day)
    nl10 = 0
    for k in range(1, 11):
        if aidx - k - 1 < 0:
            break
        lo_win = arr['low_adj'][aidx - k - 20:aidx - k]
        if len(lo_win) >= 20 and arr['low_adj'][aidx - k] < lo_win.min():
            nl10 += 1
    # DAYS_SINCE_LOW over prior 20 obs window incl anchor
    wl20 = arr['low_adj'][aidx - 19:aidx + 1]
    ds_low = int(19 - int(np.argmin(wl20))) if len(wl20) == 20 else np.nan   # days since the min (0=today)
    # ATR20
    pc_adj = np.empty(len(wc))
    pc_adj[0] = wc[0]
    pc_adj[1:] = wc[:-1]
    # compute TR over last 20 obs
    trs = []
    for k in range(max(1, len(wc) - 20), len(wc)):
        hh = wh[k]; ll = wl[k]; pc_ = pc_adj[k]
        trs.append(max(hh - ll, abs(hh - pc_), abs(ll - pc_)))
    atr20 = float(np.mean(trs)) if len(trs) >= 15 else np.nan
    atr20_pct = atr20 / c if np.isfinite(atr20) else np.nan
    # intraday range
    pre_adj = arr['close_adj'][aidx - 1] if aidx >= 1 else np.nan
    intraday = (h - l) / pre_adj if np.isfinite(pre_adj) and pre_adj > 0 else np.nan
    # RV20 (close_adj daily ret, 20 obs excl anchor)
    cr = wc[1:] / wc[:-1] - 1.0
    rv20 = float(np.std(cr[-20:], ddof=0) * 100) if len(cr) >= 20 else np.nan
    # amount ratio
    amt_ma = wa[:-1].mean() if len(wa) - 1 >= 20 else np.nan
    amt_ratio = amt / amt_ma if np.isfinite(amt_ma) and amt_ma > 0 else np.nan
    # days underwater (entry..anchor, close_adj < entry_adj): use stock arrays from entry_i to anchor_i
    e_idx = int(np.searchsorted(iarr, entry_i))
    uw = 0
    for k in range(e_idx, aidx + 1):
        if arr['close_adj'][k] < entry_adj:
            uw += 1
    # layer count at anchor + avg cost
    L = layers_arr if layers_arr is not None else []
    n_layers = 0; tot_sh = 0.0; tot_amt = 0.0
    for lr in L:
        li = int(lr[0]); qty = float(lr[2]); amt_ = float(lr[3])
        if li <= anchor_i:
            n_layers += 1; tot_sh += qty; tot_amt += amt_
    avg_cost = tot_amt / tot_sh if tot_sh > 0 else np.nan
    close_raw = arr['close_adj'][aidx] / arr['adj'][aidx] if arr['adj'][aidx] > 0 else np.nan
    dist_avgcost = close_raw / avg_cost - 1 if (np.isfinite(avg_cost) and avg_cost > 0 and np.isfinite(close_raw)) else np.nan
    feats = dict(
        F_CUR_MAE=cur_mae,
        F_DAYS_SINCE_ENTRY=float(anchor_i - entry_i),
        F_DAYS_SINCE_FIRST_D10=float(anchor_i - first_d10_i) if first_d10_i is not None else np.nan,
        F_DIST_MA20=c / ma20 - 1,
        F_DIST_LBB=c / bb_low - 1 if bb_low > 0 else np.nan,
        F_RET3=ret3, F_RET5=ret5, F_RET20=ret20,
        F_REB3=reb3, F_REB5=reb5,
        F_NLOW10=float(nl10), F_DAYS_SINCE_LOW=float(ds_low),
        F_AMT_RATIO20=amt_ratio,
        F_ATR20_PCT=atr20_pct, F_INTRADAY_RANGE=intraday, F_RV20=rv20,
        F_DAYS_UNDERWATER=float(uw), F_DIST_AVGCOST=dist_avgcost,
        F_LAYER_COUNT=float(n_layers),
    )
    return feats

print('[F1] detecting anchors + computing features ...', flush=True)
anchors = []   # one record per (episode, threshold) anchor
for e in an_ep:
    rows = e['rows']; n = len(rows)
    if n < 1:
        continue
    entry_i = int(e['entry_i']); base = float(e['base'])
    entry_adj = base * float(rows[0, 9])
    if entry_adj <= 0:
        continue
    # scan rows: adjusted low/close vs entry
    first_d10_i = None
    trig = {0.10: None, 0.20: None, 0.30: None}
    for k in range(n):
        i_k = int(rows[k, 0])
        low_adj = float(rows[k, 3]) * float(rows[k, 9])
        close_adj = float(rows[k, 8]) * float(rows[k, 9])
        mae = low_adj / entry_adj - 1.0
        if first_d10_i is None and mae <= -0.10:
            first_d10_i = i_k
        for thr in THRESH:
            if trig[thr] is None and mae <= -thr:
                trig[thr] = (k, i_k, low_adj, close_adj, mae)
    for thr in THRESH:
        t = trig[thr]
        if t is None:
            continue
        k_a, i_a, low_a, close_a, mae_a = t
        # outcomes after anchor (rows k_a+1 .. n-1)
        rec_entry = False; breakeven_i = None
        fut_min_level = mae_a
        for k2 in range(k_a + 1, n):
            c2 = float(rows[k2, 8]) * float(rows[k2, 9])
            l2 = float(rows[k2, 3]) * float(rows[k2, 9])
            lev = l2 / entry_adj - 1.0
            if lev < fut_min_level:
                fut_min_level = lev
            if (not rec_entry) and c2 >= entry_adj:
                rec_entry = True; breakeven_i = int(rows[k2, 0])
        final_profit = e['ret0'] > 0
        time_breakeven = (breakeven_i - i_a) if breakeven_i is not None else np.nan
        anchors.append(dict(ts_code=e['ts_code'], signal_date=e['signal_date'], entry_date=e['entry_date'],
                            threshold=thr, anchor_i=i_a, entry_i=entry_i, entry_adj=entry_adj,
                            cur_mae=mae_a, recover_to_entry=bool(rec_entry), final_profit=bool(final_profit),
                            time_to_breakeven=time_breakeven, final_return=e['ret0'],
                            future_adverse=fut_min_level - mae_a,   # additional pp below anchor level
                            layers_raw=e['layers'], first_d10_i=first_d10_i,
                            exit_i=int(e['exit_i']), hold_days=int(e['exit_i'] - entry_i)))

print(f'[F1] anchors detected: D10={sum(1 for a in anchors if a["threshold"]==0.10)} '
      f'D20={sum(1 for a in anchors if a["threshold"]==0.20)} '
      f'D30={sum(1 for a in anchors if a["threshold"]==0.30)}  ({time.time()-t0:.0f}s)', flush=True)

# attach features + market overlay
print('[F1] computing anchor-time features ...', flush=True)
n_feat_ok = 0
for a in anchors:
    arr = stk.get(a['ts_code'])
    if arr is None:
        a['feats'] = None; continue
    aidx = int(np.searchsorted(arr['i'], a['anchor_i']))
    if aidx >= len(arr['i']) or int(arr['i'][aidx]) != a['anchor_i']:
        a['feats'] = None; continue
    feats = feat_at(arr, aidx, entry_adj=a['entry_adj'], anchor_i=a['anchor_i'],
                    entry_i=a['entry_i'], entry_raw=None, layers_arr=a['layers_raw'],
                    first_d10_i=a['first_d10_i'], threshold=a['threshold'], cur_mae=a['cur_mae'])
    a['feats'] = feats
    if feats is not None:
        n_feat_ok += 1
    mi = mkt_by_i.get(a['anchor_i'])
    a['r01'] = mi[0] if mi else np.nan
    a['r05'] = mi[1] if mi else np.nan
    # layer count from feats
    a['layer_count'] = feats['F_LAYER_COUNT'] if feats else np.nan
print(f'[F1] features computed ok on {n_feat_ok} anchors', flush=True)

# ================= statistical analysis =================
import scipy.stats as ss
import statsmodels.api as sm

def spearman(x, y):
    x = np.asarray(x, float); y = np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 10:
        return np.nan
    return ss.spearmanr(x[m], y[m])[0]

def hac_pval(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    if len(x) < 10:
        return np.nan, np.nan
    res = sm.OLS(x, np.ones((len(x), 1))).fit(cov_type='HAC', cov_kwds={'maxlags': 10})
    return float(res.pvalues[0]), float(res.bse[0])

def block_boot_ci(x, L=21, B=2000, seed=0):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    n = len(x)
    rng = np.random.default_rng(seed)
    nblk = int(np.ceil(n / L)); bl = []
    for _ in range(B):
        idx = []
        for _b in range(nblk):
            s = rng.integers(0, n - L + 1) if n - L + 1 > 0 else 0
            idx.extend(range(s, min(s + L, n)))
        idx = np.array(idx[:n])
        bl.append(x[idx].mean())
    bl = np.array(bl)
    return float(np.percentile(bl, 2.5)), float(np.percentile(bl, 97.5)), float(np.mean(bl))

def bh_fdr(pvals, m):
    p = np.asarray(pvals, float)
    order = np.argsort(p); ranked = p[order]
    adj = ranked * m / np.arange(1, m + 1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    q = np.empty(m); q[order] = np.minimum(adj, 1.0)
    return q

# ---- build per-anchor dataframe ----
recs = []
for a in anchors:
    if a.get('feats') is None:
        continue
    r = dict(ts_code=a['ts_code'], signal_date=a['signal_date'], threshold=a['threshold'],
             anchor_i=a['anchor_i'], anchor_date=days[a['anchor_i']].date(),
             recover_to_entry=int(a['recover_to_entry']), final_profit=int(a['final_profit']),
             time_to_breakeven=a['time_to_breakeven'], final_return=a['final_return'],
             future_adverse=a['future_adverse'], cur_mae=a['cur_mae'],
             r01=a['r01'], r05=a['r05'], layer_count=a.get('layer_count', np.nan))
    r.update(a['feats'])
    r['F_R01_RET60'] = r['r01']
    r['F_R05_LDS'] = r['r05']
    recs.append(r)
adf = pd.DataFrame(recs)
adf.to_csv(os.path.join(OUT, 'f1_anchor_episodes.csv'), index=False)
print(f'[F1] anchor dataframe: {len(adf)} rows ({time.time()-t0:.0f}s)', flush=True)

# ---- 1) base rates ----
base_rows = []
for thr in THRESH:
    sub = adf[adf['threshold'] == thr]
    n_days = sub['anchor_date'].nunique()
    base_rows.append(dict(threshold=thr, n_episodes=len(sub), n_anchor_days=n_days,
                          recover_to_entry_pct=float(sub['recover_to_entry'].mean() * 100),
                          final_profit_pct=float(sub['final_profit'].mean() * 100),
                          median_time_breakeven=float(sub['time_to_breakeven'].median()) if sub['time_to_breakeven'].notna().any() else np.nan,
                          median_final_return=float(sub['final_return'].median()),
                          median_adverse_after=float(sub['future_adverse'].median()) if sub['future_adverse'].notna().any() else np.nan))
base_df = pd.DataFrame(base_rows)
base_df.to_csv(os.path.join(OUT, 'f1_base_rates.csv'), index=False)
print('[F1] base rates:', base_df.to_string(index=False), flush=True)

# ---- 2) per-feature effects (D20 & D30 primary; D10 secondary) ----
fe_rows = []
for thr in [0.20, 0.30, 0.10]:
    sub = adf[adf['threshold'] == thr]
    for f in PRIMARY_FEATS + SECONDARY_FEATS:
        s = sub[[f, 'recover_to_entry', 'anchor_date']].dropna()
        if len(s) < 100:
            continue
        corr = spearman(s[f], s['recover_to_entry'])
        day = s.groupby('anchor_date').agg(n=('anchor_date', 'size'), fx=(f, 'mean'), oy=('recover_to_entry', 'mean')).reset_index()
        day = day[day['n'] >= MIN_DAY_N]
        day_corr = spearman(day['fx'], day['oy']) if len(day) >= 20 else np.nan
        p = np.nan; beta = np.nan
        if len(day) >= 20:
            X = sm.add_constant(day['fx'].to_numpy(float))
            try:
                res = sm.OLS(day['oy'].to_numpy(float), X).fit(cov_type='HAC', cov_kwds={'maxlags': 10})
                beta = float(res.params[1]); p = float(res.pvalues[1])
            except Exception:
                pass
        fe_rows.append(dict(threshold=thr, feature=f, n_episodes=len(s), n_anchor_days=len(day),
                            corr=corr, day_corr=day_corr, hac_p=p, beta=beta))
fe_df = pd.DataFrame(fe_rows)
fe_df.to_csv(os.path.join(OUT, 'f1_feature_effects.csv'), index=False)
print('[F1] feature effects computed', flush=True)

# ---- BH on D20 primary (m=18) ----
d20 = fe_df[(fe_df['threshold'] == 0.20) & (fe_df['feature'].isin(PRIMARY_FEATS))].copy()
d30 = fe_df[(fe_df['threshold'] == 0.30) & (fe_df['feature'].isin(PRIMARY_FEATS))].copy()
p20 = d20.set_index('feature')['hac_p'].reindex(PRIMARY_FEATS)
q20 = bh_fdr(p20.fillna(1.0).to_numpy(), M18)
d20['bh_q'] = q20
# bootstrap CI on day_corr for each primary feature (D20)
bci = {}
for f in PRIMARY_FEATS:
    s = adf[(adf['threshold'] == 0.20)][[f, 'recover_to_entry', 'anchor_date']].dropna()
    day = s.groupby('anchor_date').agg(n=('anchor_date', 'size'), fx=(f, 'mean'), oy=('recover_to_entry', 'mean')).reset_index()
    day = day[day['n'] >= MIN_DAY_N]
    if len(day) < 20:
        bci[f] = (np.nan, np.nan)
        continue
    lo, hi, mu = block_boot_ci(day['fx'].to_numpy(float), L, B, SEED)
    # bootstrap the Spearman between bootstrapped day fx and original day oy
    bcorrs = []
    rng = np.random.default_rng(SEED)
    fx = day['fx'].to_numpy(float); oy = day['oy'].to_numpy(float)
    for _ in range(2000):
        n = len(fx)
        idx = []
        nblk = int(np.ceil(n / L))
        for _b in range(nblk):
            st = rng.integers(0, n - L + 1) if n - L + 1 > 0 else 0
            idx.extend(range(st, min(st + L, n)))
        idx = np.array(idx[:n])
        bcorrs.append(ss.spearmanr(fx[idx], oy[idx])[0])   # PAIRED resample
    bcorrs = np.array(bcorrs)
    bci[f] = (float(np.percentile(bcorrs, 2.5)), float(np.percentile(bcorrs, 97.5)))
d20['boot_ci_lo'] = [bci[f][0] for f in PRIMARY_FEATS]
d20['boot_ci_hi'] = [bci[f][1] for f in PRIMARY_FEATS]
d20.to_csv(os.path.join(OUT, 'f1_anchor_day_inference.csv'), index=False)
print('[F1] D20 BH inference:', flush=True)
print(d20[['feature', 'corr', 'day_corr', 'hac_p', 'bh_q', 'boot_ci_lo', 'boot_ci_hi']].to_string(index=False), flush=True)

# ---- 3) quintiles by feature (recovery rate) ----
q_rows = []
for thr in [0.20, 0.30]:
    sub = adf[adf['threshold'] == thr]
    for f in PRIMARY_FEATS:
        s = sub[[f, 'recover_to_entry', 'anchor_date']].dropna()
        if len(s) < 500:
            continue
        try:
            q = pd.qcut(s[f], 5, labels=False, duplicates='drop')
        except Exception:
            continue
        for qi in sorted(set(q)):
            m = q == qi
            q_rows.append(dict(threshold=thr, feature=f, quintile=qi, n=int(m.sum()),
                               recover_rate=float(s.loc[m, 'recover_to_entry'].mean() * 100)))
q_df = pd.DataFrame(q_rows)
q_df.to_csv(os.path.join(OUT, 'f1_quintiles.csv'), index=False)
print('[F1] quintiles done', flush=True)

# ---- 4) winner vs loser standardized effects (D20/D30) ----
wl_rows = []
for thr in [0.20, 0.30]:
    sub = adf[adf['threshold'] == thr]
    win = sub[sub['recover_to_entry'] == 1]
    los = sub[sub['recover_to_entry'] == 0]
    for f in PRIMARY_FEATS:
        w = win[f].dropna(); l = los[f].dropna()
        if len(w) < 30 or len(l) < 30:
            continue
        pooled = np.concatenate([w, l])
        sd = pooled.std(ddof=0)
        d = (w.mean() - l.mean()) / sd if sd > 0 else np.nan
        wl_rows.append(dict(threshold=thr, feature=f, n_win=len(w), n_los=len(l),
                            win_mean=float(w.mean()), los_mean=float(l.mean()),
                            cohen_d=float(d) if np.isfinite(d) else np.nan))
wl_df = pd.DataFrame(wl_rows)
wl_df.to_csv(os.path.join(OUT, 'f1_winner_loser_effects.csv'), index=False)
print('[F1] winner-loser effects done', flush=True)

# ---- 5) future adverse excursion ----
ex_rows = []
for thr in THRESH:
    sub = adf[adf['threshold'] == thr]
    s = sub['future_adverse'].dropna()
    if len(s) == 0:
        continue
    ex_rows.append(dict(threshold=thr, n=len(s), p50=float(s.quantile(.5)), p75=float(s.quantile(.75)),
                        p90=float(s.quantile(.9)), p95=float(s.quantile(.95)),
                        mean=float(s.mean())))
ex_df = pd.DataFrame(ex_rows)
ex_df.to_csv(os.path.join(OUT, 'f1_future_adverse_excursion.csv'), index=False)
print('[F1] future adverse:', ex_df.to_string(index=False), flush=True)

# ---- 6) recovery timing ----
rt_rows = []
for thr in THRESH:
    sub = adf[adf['threshold'] == thr]
    s = sub['time_to_breakeven'].dropna()
    never = int((sub['time_to_breakeven'].isna()).sum())
    if len(s) == 0:
        continue
    rt_rows.append(dict(threshold=thr, n_recovered=len(s), n_never=int(never),
                        p25=float(s.quantile(.25)), p50=float(s.quantile(.5)),
                        p75=float(s.quantile(.75)), p90=float(s.quantile(.9))))
rt_df = pd.DataFrame(rt_rows)
rt_df.to_csv(os.path.join(OUT, 'f1_recovery_timing.csv'), index=False)
print('[F1] recovery timing:', rt_df.to_string(index=False), flush=True)

# ---- 7) layer recovery (descriptive) ----
lr_rows = []
for thr in [0.20, 0.30]:
    sub = adf[adf['threshold'] == thr]
    for lc in [1, 2, 3, 4, 5]:
        m = sub['layer_count'] == lc
        if m.sum() >= 30:
            lr_rows.append(dict(threshold=thr, layer_count=lc, n=int(m.sum()),
                                recover_rate=float(sub.loc[m, 'recover_to_entry'].mean() * 100),
                                final_profit_rate=float(sub.loc[m, 'final_profit'].mean() * 100)))
lr_df = pd.DataFrame(lr_rows)
lr_df.to_csv(os.path.join(OUT, 'f1_layer_recovery.csv'), index=False)
print('[F1] layer recovery:', lr_df.to_string(index=False), flush=True)

# ---- 8) market state (R01 / R05) ----
ms_rows = []
for thr in [0.20, 0.30]:
    sub = adf[adf['threshold'] == thr]
    for f, edges in [('r01', R01_EDGES), ('r05', R05_EDGES)]:
        s = sub[[f, 'recover_to_entry']].dropna()
        if len(s) == 0:
            continue
        q = np.searchsorted(edges, s[f], side='right')  # 0..4
        for qi in range(5):
            m = q == qi
            if m.sum() >= 30:
                ms_rows.append(dict(threshold=thr, feature=f, quintile=qi + 1, n=int(m.sum()),
                                    recover_rate=float(s.loc[m, 'recover_to_entry'].mean() * 100)))
ms_df = pd.DataFrame(ms_rows)
ms_df.to_csv(os.path.join(OUT, 'f1_market_state.csv'), index=False)
print('[F1] market state overlay:', flush=True)
print(ms_df.to_string(index=False), flush=True)

# ---- 9) predictability gate (D20 primary, BH m=18) ----
_reg = pd.read_csv(os.path.join(GIT, 'research', 'risk', 'registries', 'FAILURE_STATE_F1_REGISTRY.csv'))
_dir_of = dict(zip(_reg['feature'], _reg['hypothesized_direction']))
pass_rows = []
for _, r in d20.iterrows():
    f = r['feature']
    reg_dir = _dir_of.get(f)
    obs_dir = 'POSITIVE' if r['corr'] > 0 else 'NEGATIVE'
    dir_ok = (reg_dir == obs_dir)
    q_ok = r['bh_q'] < 0.05
    boot_ok = np.isfinite(r['boot_ci_lo']) and r['boot_ci_lo'] > 0 if reg_dir == 'POSITIVE' else (
        np.isfinite(r['boot_ci_hi']) and r['boot_ci_hi'] < 0)
    # D20 vs D30 direction consistency
    d30r = d30[d30['feature'] == f]
    d30_sign = np.sign(d30r['corr'].iloc[0]) if len(d30r) else np.nan
    d20_sign = np.sign(r['corr'])
    consist = bool(np.isfinite(d30_sign) and (d20_sign == d30_sign))
    full_pass = bool(dir_ok and q_ok and boot_ok and consist and np.isfinite(r['corr']))
    pass_rows.append(dict(feature=f, reg_dir=reg_dir, obs_corr=r['corr'], dir_ok=dir_ok,
                          bh_q=r['bh_q'], q_ok=q_ok, boot_ci_lo=r['boot_ci_lo'], boot_ci_hi=r['boot_ci_hi'],
                          boot_ok=boot_ok, d20_d30_consistent=consist, FULL_PASS=full_pass))
pass_df = pd.DataFrame(pass_rows)
pass_df.to_csv(os.path.join(OUT, 'f1_predictability_gate.csv'), index=False)
print('[F1] predictability gate:', flush=True)
print(pass_df[['feature', 'reg_dir', 'obs_corr', 'dir_ok', 'bh_q', 'q_ok', 'boot_ci_lo', 'boot_ci_hi', 'boot_ok', 'd20_d30_consistent', 'FULL_PASS']].to_string(index=False), flush=True)

n_pass = int(pass_df['FULL_PASS'].sum())
pass_feats = pass_df[pass_df['FULL_PASS']]['feature'].tolist()
# family-level non-redundancy: count distinct families among passers
fam_of = {}
for reg in open(os.path.join(GIT, 'research', 'risk', 'registries', 'FAILURE_STATE_F1_REGISTRY.csv')):
    parts = reg.strip().split(',')
    if parts[0] in PRIMARY_FEATS:
        fam_of[parts[0]] = parts[1]
pass_fams = set(fam_of.get(f, '?') for f in pass_feats)

if n_pass >= 2 and len(pass_fams) >= 2:
    cls = 'A'
elif n_pass >= 1:
    cls = 'B'
elif n_pass == 0:
    # descriptive structure check: any |corr|>0.05 on D20 and D30 both?
    strong_descr = fe_df[(fe_df['threshold'].isin([0.20, 0.30])) & (fe_df['feature'].isin(PRIMARY_FEATS))].copy()
    d20m = strong_descr[strong_descr['threshold'] == 0.20].set_index('feature')['corr']
    d30m = strong_descr[strong_descr['threshold'] == 0.30].set_index('feature')['corr']
    stable = [f for f in PRIMARY_FEATS if np.isfinite(d20m.get(f, np.nan)) and np.isfinite(d30m.get(f, np.nan))
              and abs(d20m.get(f, 0)) > 0.05 and np.sign(d20m.get(f, 0)) == np.sign(d30m.get(f, 0))]
    cls = 'C' if len(stable) >= 2 else 'D'
else:
    cls = 'C'

summary = dict(
    n_dev_episodes=len(an_ep),
    n_anchors_D10=int((adf['threshold'] == 0.10).sum()),
    n_anchors_D20=int((adf['threshold'] == 0.20).sum()),
    n_anchors_D30=int((adf['threshold'] == 0.30).sum()),
    n_features_ok=n_feat_ok,
    primary_BH_m=M18,
    n_full_pass=int(n_pass),
    pass_features=pass_feats,
    pass_families=sorted(pass_fams),
    classification=cls,
    no_2025_read=True,
)
with open(os.path.join(OUT, 'f1_summary.json'), 'w') as f:
    json.dump(summary, f, indent=2, default=str)
print('[F1] summary:', json.dumps(summary, indent=2, default=str), flush=True)
print(f'[F1] DONE  ({time.time()-t0:.0f}s)', flush=True)
