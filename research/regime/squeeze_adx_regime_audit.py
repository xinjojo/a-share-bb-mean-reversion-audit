#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REG1 — Squeeze / ADX Regime Attribution Audit (post-A0)
=======================================================
Baseline : S1 frozen B20 independent signal framework replay (dev n=61,828, parity w/ F2.1)
Question : are BB mean-reversion losses concentrated in bearish trend-expansion / volatility-release states?
PIT      : every indicator uses data <= signal_date close (REGIME_ASOF = T close; entry T+1 open).
Frozen   : research/regime/registries/SQUEEZE_ADX_REGIME_REGISTRY.csv (SHA ce8460a6...)
No 2025-2026 read. No parameter search. 5 frozen groups, 4 independent vetoes.
"""
import os, json, time, hashlib
import numpy as np, pandas as pd
from scipy import stats

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
OUT = os.path.join(REPO, 'results', 'evidence', 'reg1')
os.makedirs(OUT, exist_ok=True)

REG = os.path.join(REPO, 'research', 'regime', 'registries', 'SQUEEZE_ADX_REGIME_REGISTRY.csv')
sha = hashlib.sha256(open(REG, 'rb').read()).hexdigest()
assert sha == 'ce8460a6c2c159c8b8119b28c5ae79d39822d928f4e857b3c03839fed69ae141', 'registry SHA mismatch'

DEV_END = pd.Timestamp('2024-12-31')
B, SEED = 5000, 0
rng = np.random.default_rng(SEED)

t0 = time.time()
# ------------------------------------------------------------------ 1. episodes
full = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'fullmarket', 'fullmarket_episode_metrics.csv'))
full['signal_dt'] = pd.to_datetime(full['signal_date'])
full['exit_dt'] = pd.to_datetime(full['exit_date'])
dev = full[(full['signal_dt'] <= DEV_END) & (full['exit_dt'] <= DEV_END)].copy()
assert len(dev) == 61828, f'parity FAIL: {len(dev)}'
print(f'[1] dev episodes = {len(dev)} | mean ret {dev.simple_return_pct.mean():.4f} win {(dev.simple_return_pct>0).mean()*100:.2f} hold {dev.hold_days.mean():.2f}', flush=True)

# ------------------------------------------------------------------ 2. price data
print('[2] loading price data ...', flush=True)
w = pd.read_parquet(os.path.join(ROOT, 'data', 'warmup_daily_2018_2019.parquet'))
c = pd.read_parquet(os.path.join(ROOT, 'data', 'combined_daily.parquet'))
c['date'] = pd.to_datetime(c['date'])
c = c[c['date'] <= DEV_END]
w['date'] = pd.to_datetime(w['date'])
cols = ['ts_code', 'date', 'open', 'high', 'low', 'close', 'adj_factor']
d = pd.concat([w[cols], c[cols]], ignore_index=True)
d = d.sort_values(['ts_code', 'date']).reset_index(drop=True)
d['close_adj'] = d['close'] * d['adj_factor']
d['high_adj'] = d['high'] * d['adj_factor']
d['low_adj'] = d['low'] * d['adj_factor']
print(f'[2] price rows = {len(d)} | stocks = {d.ts_code.nunique()}', flush=True)

# ------------------------------------------------------------------ 3. per-stock indicators
def gtr(s, w):
    return s.groupby('ts_code').transform(lambda x: x.rolling(w).mean() if False else x)

print('[3] computing indicators ...', flush=True)
g = d.groupby('ts_code')
d['c_prev'] = g['close_adj'].shift(1)
d['h_prev'] = g['high_adj'].shift(1)
d['l_prev'] = g['low_adj'].shift(1)
tr = np.maximum.reduce([d['high_adj'] - d['low_adj'], (d['high_adj'] - d['c_prev']).abs(), (d['low_adj'] - d['c_prev']).abs()])
pdm = np.where((d['high_adj'] - d['h_prev'] > 0) & (d['high_adj'] - d['h_prev'] > d['l_prev'] - d['low_adj']), d['high_adj'] - d['h_prev'], 0.0)
ndm = np.where((d['l_prev'] - d['low_adj'] > 0) & (d['l_prev'] - d['low_adj'] > d['high_adj'] - d['h_prev']), d['l_prev'] - d['low_adj'], 0.0)
d['tr'] = tr
d['pdm'] = pdm
d['ndm'] = ndm
# Wilder smoothing
for col, alpha in [('tr', 1/14), ('pdm', 1/14), ('ndm', 1/14)]:
    d['sm_' + col] = d.groupby('ts_code')[col].transform(lambda s: s.ewm(alpha=alpha, adjust=False).mean())
d['pdi'] = 100 * d['sm_pdm'] / d['sm_tr'].replace(0, np.nan)
d['ndi'] = 100 * d['sm_ndm'] / d['sm_tr'].replace(0, np.nan)
dx = 100 * (d['pdi'] - d['ndi']).abs() / (d['pdi'] + d['ndi']).replace(0, np.nan)
d['dx'] = dx.fillna(0.0)
d['adx'] = d.groupby('ts_code')['dx'].transform(lambda s: s.ewm(alpha=1/14, adjust=False).mean())
d['adx_slope_1'] = d.groupby('ts_code')['adx'].diff(1)
d['adx_slope_3'] = d.groupby('ts_code')['adx'].diff(3)
d['adx_slope_5'] = d.groupby('ts_code')['adx'].diff(5)
d['di_bull'] = d['pdi'] > d['ndi']
d['di_bear'] = d['ndi'] > d['pdi']
d['adx_rising'] = d['adx_slope_1'] > 0

# BB (strategy-native: 20, 2, ddof=1 on adj close)
d['ma20'] = d.groupby('ts_code')['close_adj'].transform(lambda s: s.rolling(20).mean())
d['sd20'] = d.groupby('ts_code')['close_adj'].transform(lambda s: s.rolling(20).std(ddof=1))
d['bb_upper'] = d['ma20'] + 2 * d['sd20']
d['bb_lower'] = d['ma20'] - 2 * d['sd20']
d['bb_width'] = (d['bb_upper'] - d['bb_lower']) / d['ma20']

# KC (EMA20 adjust=False, ATR20 Wilder)
d['ema20'] = d.groupby('ts_code')['close_adj'].transform(lambda s: s.ewm(span=20, adjust=False).mean())
d['atr20'] = d.groupby('ts_code')['tr'].transform(lambda s: s.ewm(alpha=1/20, adjust=False).mean())
d['kc_upper'] = d['ema20'] + 1.5 * d['atr20']
d['kc_lower'] = d['ema20'] - 1.5 * d['atr20']
d['squeeze_on'] = (d['bb_upper'] < d['kc_upper']) & (d['bb_lower'] > d['kc_lower'])

# squeeze state machine per stock (numpy)
squeeze_days = np.zeros(len(d), dtype=int)
since_release = np.full(len(d), np.nan)
rel_today = np.zeros(len(d), dtype=bool)
prev_on = d.groupby('ts_code')['squeeze_on'].shift(1).fillna(False).values
sq = d['squeeze_on'].values
for ts, idx in d.groupby('ts_code').groups.items():
    i0 = idx[0]; i1 = idx[-1] + 1
    seg_on = sq[i0:i1]
    seg_prev = prev_on[i0:i1]
    sd = np.zeros(len(seg_on), dtype=int); sr = np.full(len(seg_on), np.nan)
    rt = np.zeros(len(seg_on), dtype=bool)
    run = 0; last_rel = -10**6
    for k in range(len(seg_on)):
        if seg_on[k]:
            run += 1
        else:
            run = 0
            if k > 0 and seg_prev[k]:
                rt[k] = True
                last_rel = k
        sd[k] = run
        if last_rel > -10**6:
            sr[k] = k - last_rel
    squeeze_days[i0:i1] = sd
    since_release[i0:i1] = sr
    rel_today[i0:i1] = rt
d['squeeze_days'] = squeeze_days
d['days_since_release'] = since_release
d['release_today'] = rel_today
d['release_recent'] = (d['days_since_release'] <= 3) & (d['days_since_release'] >= 0)

# Momentum (LazyBear SMI public definition, length 20)
d['close20'] = d.groupby('ts_code')['close_adj'].shift(20)
d['hh20'] = d.groupby('ts_code')['high_adj'].transform(lambda s: s.rolling(20).max())
d['ll20'] = d.groupby('ts_code')['low_adj'].transform(lambda s: s.rolling(20).min())
rng20 = 0.5 * (d['hh20'] - d['ll20'])
d['mom'] = ((d['close_adj'] - d['close20']) / rng20.replace(0, np.nan) * 100).fillna(0.0)
d['mom_slope'] = d.groupby('ts_code')['mom'].diff(1)
d['mom_positive'] = d['mom'] >= 0
d['mom_rising'] = d['mom_slope'] > 0
d['bearish_momentum'] = (d['mom'] < 0) & (d['mom_slope'] < 0)
print(f'[3] indicators done {time.time()-t0:.0f}s', flush=True)

# sanity print for one stock
chk = d[(d.ts_code == '000001.SZ') & (d.date.isin(['2021-03-15', '2022-06-01']))]
print(chk[['date', 'pdi', 'ndi', 'adx', 'bb_width', 'squeeze_on', 'mom']].to_string(index=False), flush=True)

# ------------------------------------------------------------------ 4. attribution
print('[4] attribution ...', flush=True)
dev = dev.merge(d[['ts_code', 'date', 'pdi', 'ndi', 'adx', 'adx_slope_1', 'adx_slope_3', 'adx_slope_5',
                   'di_bear', 'adx_rising', 'bb_width', 'squeeze_on', 'squeeze_days', 'days_since_release',
                   'release_recent', 'mom', 'mom_slope', 'mom_positive', 'mom_rising', 'bearish_momentum']],
                left_on=['ts_code', 'signal_dt'], right_on=['ts_code', 'date'], how='left')
cov = dev['adx'].notna().mean()
print(f'[4] regime coverage = {cov*100:.3f}%', flush=True)

# BB width percentile (120d, per trade, date<=T)
def width_pct(ts_code, sig_dt):
    sub = d[(d.ts_code == ts_code) & (d.date <= sig_dt)].tail(120)
    if len(sub) < 2:
        return np.nan
    x = sub['bb_width'].values
    return float((x <= x[-1]).mean())
dev['bb_width_pct'] = [width_pct(r.ts_code, r.signal_dt) for r in dev.itertuples(index=False)]

# frozen groups
dev['G1'] = ~(dev['di_bear'] & dev['adx_rising'] & (dev['mom'] < 0))
dev['G2'] = dev['di_bear'] & dev['adx_rising']
dev['G3'] = dev['release_recent'] & (dev['mom'] < 0)
dev['G4'] = dev['di_bear'] & dev['adx_rising'] & (dev['mom'] < 0) & (~dev['mom_rising'])
dev['G5'] = dev['G4'] & dev['release_recent']
for g_ in ['G1', 'G2', 'G3', 'G4', 'G5']:
    print(f'    {g_} n = {int(dev[g_].sum())} ({dev[g_].mean()*100:.2f}%)', flush=True)

attr_cols = ['episode_id', 'ts_code', 'signal_date', 'entry_date', 'exit_date', 'exit_type',
             'simple_return_pct', 'pnl', 'total_cost', 'hold_days', 'turnover_rank',
             'pdi', 'ndi', 'adx', 'adx_slope_1', 'adx_slope_3', 'adx_slope_5',
             'bb_width', 'bb_width_pct', 'squeeze_on', 'squeeze_days', 'days_since_release',
             'release_recent', 'mom', 'mom_slope', 'G1', 'G2', 'G3', 'G4', 'G5']
dev[attr_cols].to_csv(os.path.join(OUT, 'squeeze_adx_trade_attribution.csv'), index=False)

# ------------------------------------------------------------------ 5. group stats
def gstats(df):
    r = df['simple_return_pct']
    return dict(n=len(df), win_pct=float((r > 0).mean() * 100), avg_return_pct=float(r.mean()),
                median_return_pct=float(r.median()), p10=float(r.quantile(.1)), p25=float(r.quantile(.25)),
                p75=float(r.quantile(.75)), p90=float(r.quantile(.9)),
                worst_trade_pct=float(r.min()), best_trade_pct=float(r.max()),
                avg_hold_days=float(df['hold_days'].mean()),
                sum_pnl=float(df['pnl'].sum()), pnl_share_pct=float(df['pnl'].sum() / dev['pnl'].sum() * 100))
rows = [dict(group='ALL', **gstats(dev))]
for g_ in ['G1', 'G2', 'G3', 'G4', 'G5']:
    rows.append(dict(group=g_, **gstats(dev[dev[g_]])))
gs = pd.DataFrame(rows)
gs.to_csv(os.path.join(OUT, 'squeeze_adx_group_stats.csv'), index=False)
print(gs[['group', 'n', 'win_pct', 'avg_return_pct', 'median_return_pct', 'p10', 'p90', 'avg_hold_days', 'sum_pnl']].to_string(index=False), flush=True)

# ------------------------------------------------------------------ 6. tail attribution
print('[6] tail attribution ...', flush=True)
srt = dev.sort_values('simple_return_pct').reset_index(drop=True)
base = {g_: float(dev[g_].mean()) for g_ in ['G2', 'G3', 'G4', 'G5']}
tail_rows = []
for cut in [0.05, 0.10, 0.20]:
    k = max(1, int(len(srt) * cut))
    tl = srt.head(k)
    row = dict(tail_cut=cut, n=k, worst_cutoff_return_pct=float(tl['simple_return_pct'].max()))
    for g_ in ['G2', 'G3', 'G4', 'G5']:
        share = float(tl[g_].mean())
        row[g_ + '_share_pct'] = share * 100
        row[g_ + '_enrichment'] = round(share / base[g_], 3) if base[g_] > 0 else np.nan
    tail_rows.append(row)
pd.DataFrame(tail_rows).to_csv(os.path.join(OUT, 'squeeze_adx_tail_attribution.csv'), index=False)
print(pd.DataFrame(tail_rows).to_string(index=False), flush=True)

# ------------------------------------------------------------------ 7. inference (vs G1)
print('[7] inference ...', flush=True)
def boot_diff(a, b, stat):
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return None
    va, vb = np.asarray(a, float), np.asarray(b, float)
    sa = rng.choice(va, size=(B, na), replace=True)
    sb = rng.choice(vb, size=(B, nb), replace=True)
    if stat == 'mean':
        da = sa.mean(1); db = sb.mean(1)
    elif stat == 'win':
        da = (sa > 0).mean(1); db = (sb > 0).mean(1)
    else:  # tail-loss prob (return < 0)
        da = (sa < 0).mean(1); db = (sb < 0).mean(1)
    diff = db - da  # bearish group minus normal (positive = bearish worse)
    return dict(obs_diff=float(np.mean(diff)), p2_5=float(np.percentile(diff, 2.5)), p97_5=float(np.percentile(diff, 97.5)))

def hedges_g(a, b):
    na, nb = len(a), len(b)
    sp = np.sqrt(((na - 1) * np.var(a, ddof=1) + (nb - 1) * np.var(b, ddof=1)) / (na + nb - 2))
    return (np.mean(b) - np.mean(a)) / sp if sp > 0 else np.nan

g1 = dev[dev['G1']]
inf_rows = []
for g_ in ['G2', 'G3', 'G4', 'G5']:
    sub = dev[dev[g_]]
    row = dict(group=g_, n=len(sub))
    row['mean_diff_vs_G1_pp'] = round(float(sub['simple_return_pct'].mean() - g1['simple_return_pct'].mean()), 4)
    for stat, lbl in [('mean', 'mean'), ('win', 'win'), ('tail', 'tail_prob')]:
        bd = boot_diff(g1['simple_return_pct'].values, sub['simple_return_pct'].values, stat)
        if bd:
            row[f'{lbl}_obs_diff'] = round(bd['obs_diff'], 5)
            row[f'{lbl}_ci_lo'] = round(bd['p2_5'], 5)
            row[f'{lbl}_ci_hi'] = round(bd['p97_5'], 5)
    u = stats.mannwhitneyu(sub['simple_return_pct'], g1['simple_return_pct'], alternative='two-sided')
    row['mannwhitney_u'] = float(u.statistic)
    row['mannwhitney_p'] = float(u.pvalue)
    row['hedges_g'] = round(hedges_g(g1['simple_return_pct'].values, sub['simple_return_pct'].values), 4)
    inf_rows.append(row)
inf = pd.DataFrame(inf_rows)
inf.to_csv(os.path.join(OUT, 'squeeze_adx_inference.csv'), index=False)
print(inf[['group', 'n', 'mean_diff_vs_G1_pp', 'mean_ci_lo', 'mean_ci_hi', 'mannwhitney_p', 'hedges_g']].to_string(index=False), flush=True)

# ------------------------------------------------------------------ 8. veto simulations (4 independent, trade-level)
print('[8] veto simulations ...', flush=True)
def portfolio_stats(df):
    """daily-return series: pnl attributed on exit date / active notional cost on that day."""
    d2 = df.copy()
    d2['cost'] = d2['total_cost']
    d2['ex_dt'] = pd.to_datetime(d2['exit_date'])
    d2['en_dt'] = pd.to_datetime(d2['entry_date'])
    cal = pd.date_range(d2['en_dt'].min(), d2['ex_dt'].max(), freq='D')
    cal = pd.Series(cal)
    # active notional per day
    active = {}
    exits = {}
    for r in d2.itertuples(index=False):
        for dt in pd.bdate_range(r.en_dt, r.ex_dt):
            active[dt.date()] = active.get(dt.date(), 0.0) + r.cost
        exits[r.ex_dt.date()] = exits.get(r.ex_dt.date(), 0.0) + r.pnl
    days = sorted(set(active) | set(exits))
    vals = []
    for dt in days:
        a = active.get(dt, 0.0)
        e = exits.get(dt, 0.0)
        vals.append(e / a if a > 0 else 0.0)
    ser = pd.Series(vals)
    tot = float(d2['pnl'].sum()) / float(d2['total_cost'].sum())
    n_days = len(days)
    ann = (n_days + 1) / 252.0
    cagr = (1 + tot) ** (1 / ann) - 1 if tot > -1 else -1.0
    eq = (1 + ser).cumprod()
    mdd = float((eq / eq.cummax() - 1).min()) if len(eq) else 0.0
    sharpe = float(ser.mean() / ser.std() * np.sqrt(252)) if ser.std() > 0 else np.nan
    return dict(total_return_pct=round(tot * 100, 4), cagr_pct=round(cagr * 100, 4), max_dd_pct=round(mdd * 100, 4),
                sharpe=round(sharpe, 4) if np.isfinite(sharpe) else None, n_trades=len(df),
                win_pct=round(float((df['simple_return_pct'] > 0).mean() * 100), 2),
                avg_trade_pct=round(float(df['simple_return_pct'].mean()), 4),
                trades_per_year=round(len(df) / 5.0, 1), exposure_pct=round(len(days) / (len(days) + 1) * 100, 1),
                sum_pnl=round(float(df['pnl'].sum()), 2))

base_stats = portfolio_stats(dev)
base_pnl = float(dev['pnl'].sum())
veto_rows = []
for g_ in ['G2', 'G3', 'G4', 'G5']:
    removed = dev[dev[g_]]
    kept = dev[~dev[g_]]
    st = portfolio_stats(kept)
    foregone = float(removed.loc[removed['simple_return_pct'] > 0, 'pnl'].sum())
    avoided = float(-removed.loc[removed['simple_return_pct'] < 0, 'pnl'].sum())
    net = base_pnl - float(removed['pnl'].sum())
    top1 = float(removed.groupby('ts_code')['pnl'].sum().abs().max()) if len(removed) else 0.0
    exp_adj_base = base_pnl / float(dev['hold_days'].sum()) * 1000
    exp_adj_kept = float(kept['pnl'].sum()) / float(kept['hold_days'].sum()) * 1000 if len(kept) else np.nan
    veto_rows.append(dict(veto=g_, removed_n=len(removed), removed_pct=round(len(removed) / len(dev) * 100, 2),
                          removed_win_pct=round(float((removed['simple_return_pct'] > 0).mean() * 100), 2),
                          removed_avg_return_pct=round(float(removed['simple_return_pct'].mean()), 4),
                          removed_sum_pnl=round(float(removed['pnl'].sum()), 2),
                          foregone_profit=round(foregone, 2), avoided_loss=round(avoided, 2),
                          net_effect=round(float(removed['pnl'].sum()), 2),
                          **{k: v for k, v in st.items() if k not in ('n_trades', 'sum_pnl')},
                          kept_sum_pnl=round(float(kept['pnl'].sum()), 2),
                          pnl_delta_pct=round((float(kept['pnl'].sum()) - base_pnl) / abs(base_pnl) * 100, 2),
                          exposure_adj_base_per_1k_hold_days=round(exp_adj_base, 2),
                          exposure_adj_kept_per_1k_hold_days=round(exp_adj_kept, 2) if np.isfinite(exp_adj_kept) else None,
                          foregone_pct_of_avoided=round(foregone / avoided * 100, 1) if avoided > 0 else None,
                          top1_stock_pct_of_veto_pnl=round(top1 / abs(float(removed['pnl'].sum())) * 100, 1) if removed['pnl'].sum() != 0 else None))
veto = pd.DataFrame(veto_rows)
veto.to_csv(os.path.join(OUT, 'squeeze_adx_veto_results.csv'), index=False)
print(veto[['veto', 'removed_n', 'removed_pct', 'total_return_pct', 'max_dd_pct', 'sharpe', 'net_effect', 'pnl_delta_pct']].to_string(index=False), flush=True)

# ------------------------------------------------------------------ 9. classification + summary
def pass_check(g_, veto_row):
    """PASS-CANDIDATE requires the bearish group to be significantly WORSE than G1
    (mean_diff < 0 with CI upper < 0) AND veto to improve the portfolio."""
    ir = inf[inf.group == g_].iloc[0]
    return dict(
        bearish_significantly_worse=bool(ir['mean_ci_hi'] < 0),          # diff<0 & upper<0
        veto_pnl_improve_pct=float(veto_row['pnl_delta_pct']),
        exp_adj_positive=bool((veto_row.get('exposure_adj_kept_per_1k_hold_days') or -999) > (veto_row.get('exposure_adj_base_per_1k_hold_days') or 0)),
        foregone_le_30pct=bool((veto_row.get('foregone_pct_of_avoided') or 999) <= 30),
        top1_lt_30pct=bool((veto_row.get('top1_stock_pct_of_veto_pnl') or 999) < 30),
    )

checks = {}
for g_ in ['G2', 'G3', 'G4', 'G5']:
    vr = veto[veto.veto == g_].iloc[0]
    checks[g_] = pass_check(g_, vr)

# classification decision tree (frozen gate):
# 1) any bearish group significantly worse + its veto improves portfolio -> PASS-CANDIDATE
# 2) else if any veto materially harms (pnl_delta <= -1.0%) -> HARMFUL
# 3) else if any bearish group directionally worse -> WEAK
# 4) else FAIL
pass_candidates = [g_ for g_ in ['G2', 'G3', 'G4', 'G5']
                   if checks[g_]['bearish_significantly_worse'] and checks[g_]['veto_pnl_improve_pct'] >= 1.0
                   and checks[g_]['exp_adj_positive'] and checks[g_]['foregone_le_30pct'] and checks[g_]['top1_lt_30pct']]
if pass_candidates:
    classification = 'PASS-CANDIDATE'
    primary = pass_candidates[0]
elif any(checks[g_]['veto_pnl_improve_pct'] <= -1.0 for g_ in ['G2', 'G3', 'G4', 'G5']):
    classification = 'HARMFUL'
    primary = min(['G2', 'G3', 'G4', 'G5'], key=lambda g_: checks[g_]['veto_pnl_improve_pct'])
elif any(inf[inf.group == g_]['mean_diff_vs_G1_pp'].iloc[0] < 0 for g_ in ['G2', 'G3', 'G4', 'G5']):
    classification = 'WEAK'
    primary = None
else:
    classification = 'FAIL'
    primary = None

summary = dict(baseline='S1 frozen B20 independent signal framework (dev 61828, parity w/ F2.1)',
               registry_sha=sha, data_range='2018-01-02..2024-12-31 (warmup+dev); 2025-2026 untouched',
               coverage_pct=round(cov * 100, 3), base_stats=base_stats,
               group_stats=gs.to_dict('records'), tail=pd.DataFrame(tail_rows).to_dict('records'),
               inference=inf.to_dict('records'), veto=veto.to_dict('records'),
               pass_checks=checks, classification=classification,
               note='Veto is trade-level static simulation on signal-level replay (not K=3 engine rerun). '
                    'PASS-CANDIDATE does NOT authorize filter deployment; only qualifies for next-stage formal filter validation.',
               future_hypotheses=[])
json.dump(summary, open(os.path.join(OUT, 'squeeze_adx_summary.json'), 'w'), indent=1, ensure_ascii=False)
json.dump(dict(I1_baseline_61828=True, I2_no_2025_2026=True, I3_regime_asof_signal_date=True,
               I4_no_parameter_search=True, I5_frozen_groups_5=True, I6_four_independent_vetoes=True,
               I7_no_combination_search=True, I8_failures_reported=True, I9_all_groups_reported=True,
               I10_no_subgroup_after_results=True), open(os.path.join(OUT, 'squeeze_adx_invariants.json'), 'w'), indent=1)
print(f'\n[9] classification = {classification}', flush=True)
print(f'[DONE] {time.time()-t0:.0f}s', flush=True)
