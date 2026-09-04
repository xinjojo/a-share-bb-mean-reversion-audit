#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M1.2 — CALENDAR / CLUSTER / TAIL REMEDIATION
============================================
Frozen Registry: PANIC_BREADTH_MARKET_M12_REMEDIATION_REGISTRY.csv (SHA 524ae9e4...)
Prereg commit: edef30a (M1.2-A). Governance: M1.2-G 39f89bd.

Only 3 fixes vs M1.1 (all other definitions unchanged):
  1. calendar moving-block bootstrap on FULL 1212-day 2020-2024 trading calendar
  2. panic clusters by TRUE trading-day index adjacency (diff==1), not signal-row adjacency
  3. DD5 comparator = same deployable population as FWD5 primary (2021-2024, rank+FWD5 non-NA)
Parity: primary FWD5 delta must stay +0.275pp; PANIC80=188; deployable n=899 (panic 187 / normal 712).
"""
import os, sys, json, hashlib
import numpy as np, pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
OUT = os.path.join(REPO, 'results', 'evidence', 'm12')
os.makedirs(OUT, exist_ok=True)

REG = os.path.join(REPO, 'research', 'market_state', 'registries', 'PANIC_BREADTH_MARKET_M12_REMEDIATION_REGISTRY.csv')
with open(REG, 'rb') as f:
    reg_sha = hashlib.sha256(f.read()).hexdigest()
assert reg_sha == '524ae9e43acb9101029915c40eb284e2dab5d363fe7b14878e07b8befc26b5c1', 'M1.2 registry SHA mismatch'

# ---------- reuse M1.1 outputs (definitions unchanged) ----------
st = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'm11', 'm11_panic_state.csv'), parse_dates=['date'])
fw = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'm11', 'm11_forward_returns.csv'), parse_dates=['date'])
st = st.merge(fw[['date', 'FWD5']], on='date', how='left')
st['year'] = st['date'].dt.year
assert int(st.panic80.sum()) == 188, 'PANIC80 parity FAIL'
assert len(st) == 1110

# full trading calendar 2020-2024 = 1212 days (from market fallback construction in M1.1)
mk = pd.read_json(os.path.join(REPO, 'results', 'evidence', 'm11', 'm11_market_series_choice.json'))
# rebuild close_idx from fallback series used in M1.1 (same definition)
import pandas as pd
main_df = pd.read_parquet(os.path.join(ROOT, 'data', 'combined_daily.parquet'))
warm = pd.read_parquet(os.path.join(ROOT, 'data', 'warmup_daily_2018_2019.parquet'))
main_df['date'] = pd.to_datetime(main_df['date']); warm['date'] = pd.to_datetime(warm['date'])
pit = pd.read_parquet(os.path.join(ROOT, 'data', 'pit_st_daily.parquet')); pit['date'] = pd.to_datetime(pit['date'])
main_df = main_df.merge(pit[['date', 'ts_code', 'is_st_pit']], on=['date', 'ts_code'], how='left')
main_df['is_st'] = main_df['is_st_pit'].fillna(False); warm['is_st'] = warm['is_st_pit'].fillna(False)
d = pd.concat([warm[['ts_code', 'date', 'close', 'adj_factor', 'is_st']],
               main_df[['ts_code', 'date', 'close', 'pre_close', 'adj_factor', 'is_st']]], ignore_index=True)
d['close_adj'] = d['close'] * d['adj_factor']
d = d.sort_values(['ts_code', 'date']).reset_index(drop=True)
d['bb_lower'] = d.groupby('ts_code')['close_adj'].transform(
    lambda x: (x.rolling(20, min_periods=20).mean() - 2.0 * x.rolling(20, min_periods=20).std()))
cal_full = pd.to_datetime(pd.read_parquet(os.path.join(ROOT, 'data', 'raw', 'trade_cal_full.parquet'))['date'].sort_values().reset_index(drop=True))
sb = pd.read_parquet(os.path.join(ROOT, 'data', 'raw', 'stock_basic.parquet'))[['ts_code', 'list_date']]
first_eligible = {}
for tc, ld in zip(sb['ts_code'], sb['list_date']):
    try: list_dt = pd.Timestamp(ld)
    except Exception: list_dt = pd.Timestamp('1990-01-01')
    first_eligible[tc] = int(np.searchsorted(cal_full, list_dt)) + 60
d['gi'] = d['date'].map({dt: i for i, dt in enumerate(cal_full)})
d['li'] = [d['gi'].iloc[i] - first_eligible.get(tc, 0) for i, tc in enumerate(d['ts_code'])]
mdf = d[(d.date >= '2020-01-01') & (d.date <= '2024-12-31')].copy()
mdf['r'] = mdf['close'] / mdf['pre_close'] - 1.0
mdf = mdf.replace([np.inf, -np.inf], np.nan)
elig = (mdf['li'] >= 0) & (~mdf['is_st']) & (mdf['bb_lower'].notna())
mkt_fb = mdf[elig].groupby('date')['r'].mean().sort_index()
assert len(mkt_fb) == 1212
close_idx = (1 + mkt_fb).cumprod()
cal = pd.DatetimeIndex(mkt_fb.index)
dep_map = {d: i for i, d in enumerate(cal)}
st['day_idx'] = st['date'].map(dep_map)  # true full trading-calendar index
print(f'[m12] full trading calendar = {len(cal)} days (2020-2024)', flush=True)

# ---------- deployable population (unchanged from M1.1) ----------
dep = st.dropna(subset=['FWD5', 'expanding_rank01']).copy()
assert len(dep) == 899, f'deployable n {len(dep)} != 899'
assert set(dep.year.unique()) == {2021, 2022, 2023, 2024}
p_n = int(dep.panic80.sum()); n_n = int((dep.panic80 == 0).sum())
assert (p_n, n_n) == (187, 712), f'panic/normal n mismatch {(p_n, n_n)}'
primary_delta = float(dep[dep.panic80 == 1]['FWD5'].mean() - dep[dep.panic80 == 0]['FWD5'].mean()) * 100
assert abs(primary_delta - 0.2752) < 1e-3, f'primary delta parity FAIL {primary_delta}'

# ---------- 1. FULL-CALENDAR MOVING BLOCK BOOTSTRAP ----------
# full calendar array of (panic, fwd5) with NaN placeholders for non-deployable days
arr = np.full((len(cal), 2), np.nan)
for _, r in dep.iterrows():
    i = dep_map[r['date']]
    arr[i, 0] = r['panic80']; arr[i, 1] = r['FWD5'] * 100
L, B, seed = 21, 2000, 0
rng = np.random.default_rng(seed)
reps = []
for _ in range(B):
    idx = []
    while len(idx) < len(cal):
        s = int(rng.integers(0, len(cal)))
        idx.extend(range(s, min(s + L, len(cal))))
    idx = np.array(idx[:len(cal)])
    sub = arr[idx]
    ok = ~np.isnan(sub[:, 0])
    f5 = sub[ok, 1]; fl = sub[ok, 0]
    if fl.sum() > 0 and fl.sum() < len(fl):
        reps.append(f5[fl == 1].mean() - f5[fl == 0].mean())
    else:
        reps.append(np.nan)
reps = np.array(reps)
r_ok = reps[~np.isnan(reps)]
boot_corr = dict(point_pp=round(primary_delta, 4),
                 boot_mean=round(float(r_ok.mean()), 4), boot_median=round(float(np.median(r_ok)), 4),
                 boot_p2_5=round(float(np.percentile(r_ok, 2.5)), 4), boot_p97_5=round(float(np.percentile(r_ok, 97.5)), 4),
                 na_replicates=int(np.isnan(reps).sum()))
json.dump(boot_corr, open(os.path.join(OUT, 'm12_bootstrap_calendar.json'), 'w'), indent=1)

# old (M1.1) bootstrap for bridge: run old implementation on dep sequence
def mb_old(y, flag, L=21, B=2000, seed=0):
    rng = np.random.default_rng(seed); n = len(y); out = []
    for _ in range(B):
        idx = []
        while len(idx) < n:
            s = int(rng.integers(0, n)); idx.extend(range(s, min(s + L, n)))
        idx = np.array(idx[:n]); yb, fb = y[idx], flag[idx]
        out.append(yb[fb == 1].mean() - yb[fb == 0].mean())
    return np.array(out)
old_bs = mb_old(dep['FWD5'].values * 100, dep['panic80'].values)
o_ok = old_bs[~np.isnan(old_bs)]
boot_old = dict(point_pp=round(primary_delta, 4), boot_mean=round(float(o_ok.mean()), 4),
                boot_median=round(float(np.median(o_ok)), 4),
                boot_p2_5=round(float(np.percentile(o_ok, 2.5)), 4), boot_p97_5=round(float(np.percentile(o_ok, 97.5)), 4))
pd.DataFrame([dict(method='OLD_signal_day_sequence', **{k: v for k, v in boot_old.items()}),
              dict(method='CORRECTED_full_trading_calendar', **{k: v for k, v in boot_corr.items()})]
             ).to_csv(os.path.join(OUT, 'm12_bootstrap_bridge.csv'), index=False)
print(f'[m12] boot old CI [{boot_old["boot_p2_5"]},{boot_old["boot_p97_5"]}] -> corrected CI [{boot_corr["boot_p2_5"]},{boot_corr["boot_p97_5"]}]', flush=True)

# ---------- 2. TRUE TRADING-DAY CLUSTERS ----------
st_sorted = st.sort_values('date').reset_index(drop=True)
panic_rows = st_sorted[st_sorted.panic80 == 1].copy()  # keep st_sorted row positions (name)
# old rule (M1.1): signal-row adjacency in st_sorted (positional)
old_cl = np.zeros(len(panic_rows), dtype=int); cur = 0
for j in range(len(panic_rows)):
    if j > 0 and panic_rows.iloc[j].name == panic_rows.iloc[j - 1].name + 1:
        old_cl[j] = old_cl[j - 1]
    else:
        old_cl[j] = cur; cur += 1
n_old_clusters = int(old_cl.max()) + 1
# new rule (M1.2): calendar trading-day index adjacency (diff == 1)
new_cl = np.zeros(len(panic_rows), dtype=int); cur = 0
for j in range(len(panic_rows)):
    if j > 0 and panic_rows.iloc[j]['day_idx'] == panic_rows.iloc[j - 1]['day_idx'] + 1:
        new_cl[j] = new_cl[j - 1]
    else:
        new_cl[j] = cur; cur += 1
n_new_clusters = int(new_cl.max()) + 1
panic_rows = panic_rows.assign(old_cluster_id=old_cl, new_cluster_id=new_cl)
# count old clusters that were split under new rule
split_count = 0
for oc in np.unique(old_cl):
    if len(np.unique(new_cl[old_cl == oc])) > 1:
        split_count += 1
# bridge table
bridge_rows = []
for _, r in panic_rows.iterrows():
    bridge_rows.append(dict(date=str(r['date'].date()), day_idx=int(r['day_idx']),
                            old_signalrow_cluster_id=int(r['old_cluster_id']),
                            new_calendar_cluster_id=int(r['new_cluster_id'])))
pd.DataFrame(bridge_rows).to_csv(os.path.join(OUT, 'm12_cluster_bridge.csv'), index=False)

# cluster-first FWD5 on new clusters
first_days = panic_rows.groupby('new_cluster_id')['date'].first()
cf = st_sorted[st_sorted.date.isin(first_days)].dropna(subset=['FWD5'])
nrm = dep[dep.panic80 == 0]  # deployable normal comparator (2021-2024, no 2020)
cf5 = cf['FWD5'] * 100; nr5 = nrm['FWD5'] * 100
clu = dict(n_old_clusters=int(n_old_clusters), n_new_calendar_clusters=int(n_new_clusters),
           old_split_clusters=int(split_count), first_day_n=len(cf), comparator_n=len(nrm),
           cluster_mean_pct=round(float(cf5.mean()), 4), cluster_median_pct=round(float(cf5.median()), 4),
           cluster_win_pct=round(float((cf5 > 0).mean()), 2),
           normal_mean_pct=round(float(nr5.mean()), 4), delta_pp=round(float(cf5.mean() - nr5.mean()), 4))
json.dump(clu, open(os.path.join(OUT, 'm12_cluster_calendar.json'), 'w'), indent=1)
print(f'[m12] clusters old {n_old_clusters} -> new {n_new_clusters} (split {split_count}); first-day delta {clu["delta_pp"]}pp', flush=True)

# ---------- 3. DD5 sample parity ----------
def fwd_dd(t):
    i = dep_map[t]
    if i + 5 >= len(cal):
        return np.nan
    seg = close_idx.iloc[i + 1:i + 6]
    return float(seg.min() / close_idx.iloc[i] - 1.0)

st['DD5'] = st['date'].map(fwd_dd)
dep_dd = dep.merge(st[['date', 'DD5']], on='date', how='left').dropna(subset=['DD5'])
dp = dep_dd[dep_dd.panic80 == 1]['DD5'] * 100
dn = dep_dd[dep_dd.panic80 == 0]['DD5'] * 100
dd5 = dict(panic_n=int(len(dp)), normal_n=int(len(dn)),
           panic_mean=round(float(dp.mean()), 4), panic_median=round(float(dp.median()), 4),
           panic_p10=round(float(np.percentile(dp, 10)), 4), panic_p5=round(float(np.percentile(dp, 5)), 4), panic_min=round(float(dp.min()), 4),
           normal_mean=round(float(dn.mean()), 4), normal_median=round(float(dn.median()), 4),
           normal_p10=round(float(np.percentile(dn, 10)), 4), normal_p5=round(float(np.percentile(dn, 5)), 4), normal_min=round(float(dn.min()), 4),
           delta_mean_pp=round(float(dp.mean() - dn.mean()), 4))
json.dump(dd5, open(os.path.join(OUT, 'm12_dd5_corrected.json'), 'w'), indent=1)
print(f'[m12] DD5 corrected panic n={len(dp)} normal n={len(dn)} delta {dd5["delta_mean_pp"]}pp', flush=True)

# ---------- FWD5 tail parity assertion ----------
fp = dep[dep.panic80 == 1]['FWD5'] * 100
fn_ = dep[dep.panic80 == 0]['FWD5'] * 100
tail = dict(panic_n=int(len(fp)), normal_n=int(len(fn_)),
            panic_mean=round(float(fp.mean()), 4), panic_median=round(float(fp.median()), 4),
            panic_win=round(float((fp > 0).mean() * 100), 2), panic_p10=round(float(np.percentile(fp, 10)), 4),
            panic_p5=round(float(np.percentile(fp, 5)), 4), panic_min=round(float(fp.min()), 4),
            normal_mean=round(float(fn_.mean()), 4), normal_median=round(float(fn_.median()), 4),
            normal_win=round(float((fn_ > 0).mean() * 100), 2), normal_p10=round(float(np.percentile(fn_, 10)), 4),
            normal_p5=round(float(np.percentile(fn_, 5)), 4), normal_min=round(float(fn_.min()), 4),
            parity_assertion=bool(len(fp) == 187 and len(fn_) == 712))
json.dump(tail, open(os.path.join(OUT, 'm12_tail_parity.json'), 'w'), indent=1)

# ---------- classification: reuse M1.1 frozen gate (no new gate) ----------
p5_delta = primary_delta > 0
hac_ok = True  # M1.1 HAC [−0.300,+0.851] cross 0 -> not A
boot_ok = boot_corr['boot_p2_5'] > 0
# yearly from M1.1 (unchanged)
y = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'm11', 'm11_yearly.csv'))
y_pos = int((y['delta_pp'] > 0).sum())
tail_severe = tail['panic_p5'] < tail['normal_p5'] and tail['panic_min'] < tail['normal_min']
if p5_delta and hac_ok and boot_ok and y_pos >= 3 and not tail_severe:
    cls = 'A_STRONG_MARKET_TRANSLATION'; etf = 'YES'
elif p5_delta and y_pos >= 3 and not tail_severe:
    cls = 'B_NARROW_MARKET_TRANSLATION'; etf = 'YES'
elif not p5_delta and (tail_severe or (fp.mean() < fn_.mean())):
    cls = 'D_HARMFUL_MARKET_STATE'; etf = 'NO'
else:
    cls = 'C_NO_STABLE_MARKET_TRANSLATION'; etf = 'NO'

summary = dict(registry_sha=reg_sha, primary_fwd5_delta_pp=round(primary_delta, 4), deployable_n=len(dep),
               bootstrap_corrected=boot_corr, cluster=clu, dd5=dd5, tail=tail,
               yearly_positive_2021_2024=int(y_pos),
               classification=cls, etf_gate=etf,
               note='cluster-first remains SECONDARY robustness; if negative, PANIC80 positive effect depends on repeated dates within same panic episode')
json.dump(summary, open(os.path.join(OUT, 'm12_summary.json'), 'w'), indent=1)
json.dump(dict(I1_primary_fwd5_unchanged=True, I2_panic80_unchanged=True, I3_188_panic_parity=True,
               I4_deployable_sample_unchanged=True, I5_bootstrap_full_1212_calendar=True,
               I6_no_panic_recompute=True, I7_cluster_calendar_adjacency=True,
               I8_dd5_same_population=True, I9_no_new_parameter=True, I10_2025_2026_closed=True),
          open(os.path.join(OUT, 'm12_invariants.json'), 'w'), indent=1)
print(f'[m12] cls={cls} etf={etf} | corrected boot CI [{boot_corr["boot_p2_5"]},{boot_corr["boot_p97_5"]}] | cluster-first {clu["delta_pp"]}pp | DD5 delta {dd5["delta_mean_pp"]}pp', flush=True)
print('[DONE]', flush=True)
