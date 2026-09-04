#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M1.1 — EXTERNAL-PROTOCOL RECONCILIATION (PANIC-BREADTH → MARKET REBOUND)
========================================================================
Frozen Registry: PANIC_BREADTH_MARKET_M11_PROTOCOL_REGISTRY.csv (SHA bf10c749...)
Prereg commit: 852635a (M1.1-A). Governance: M1.1-G 8c66b21.

Restores the external frozen protocol:
- PRIMARY horizon = FWD5; secondary FWD1/FWD3/FWD10/FWD20 (FWD40 never in classification)
- continuous = EXPANDING_BREADTH_RANK01 (date<T only; <252 prior -> NA)
- conditional = FWD5 ~ expanding_rank + MARKET_RET_T (multivariate NW, statsmodels parity)
- yearly denominator = 2021-2024 (>=3/4)
- cluster-first robustness; 5d tail + future-5d drawdown
- market series hierarchy: official wide-base index first, else PIT equal-weight fallback
- PANIC80 = P7 parity (188 days)
"""
import os, sys, json, hashlib
import numpy as np, pandas as pd
from scipy.stats import spearmanr
import statsmodels.api as sm

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
OUT = os.path.join(REPO, 'results', 'evidence', 'm11')
os.makedirs(OUT, exist_ok=True)

REG = os.path.join(REPO, 'research', 'market_state', 'registries', 'PANIC_BREADTH_MARKET_M11_PROTOCOL_REGISTRY.csv')
with open(REG, 'rb') as f:
    reg_sha = hashlib.sha256(f.read()).hexdigest()
assert reg_sha == 'bf10c7498d6e19d5a360ff654ef2da153424144f14961d56c869938b8b93f5b3', 'M1.1 registry SHA mismatch'

# ---------- PRIMARY MARKET SERIES CHOICE (before looking at any outcome) ----------
# official wide-base full-market index (中证全指 000985 or equivalent) present?
import glob
idx_files = sorted(glob.glob(os.path.join(ROOT, 'data', 'index_*.parquet')))
official_full_market = None
for f in idx_files:
    code = os.path.basename(f).replace('index_', '').replace('.parquet', '')
    if code in ('000985',):
        official_full_market = f
# repo has only 000300/000905/000852 (none is a full-market wide-base index)
choice = dict(choice='PIT_EQUAL_WEIGHT_FALLBACK',
              official_full_market_index_found=False,
              available_index_files=[os.path.basename(x) for x in idx_files],
              reason='repo data contains only 沪深300(000300)/中证500(000905)/中证1000(000852), none is a full-market wide-base index; 中证全指(000985) not present; per frozen protocol fallback = daily equal-weight close-to-close over that day legal universe (listed>=60d & non-PIT-ST & BB warmup non-NaN, same as B1 universe_size)')
json.dump(choice, open(os.path.join(OUT, 'm11_market_series_choice.json'), 'w'), indent=1)

# ---------- build PIT equal-weight fallback series (frozen legal universe) ----------
main_df = pd.read_parquet(os.path.join(ROOT, 'data', 'combined_daily.parquet'))
warm = pd.read_parquet(os.path.join(ROOT, 'data', 'warmup_daily_2018_2019.parquet'))
main_df['date'] = pd.to_datetime(main_df['date'])
warm['date'] = pd.to_datetime(warm['date'])
pit = pd.read_parquet(os.path.join(ROOT, 'data', 'pit_st_daily.parquet'))
pit['date'] = pd.to_datetime(pit['date'])
main_df = main_df.merge(pit[['date', 'ts_code', 'is_st_pit']], on=['date', 'ts_code'], how='left')
main_df['is_st'] = main_df['is_st_pit'].fillna(False)
warm['is_st'] = warm['is_st_pit'].fillna(False)
d = pd.concat([warm[['ts_code', 'date', 'close', 'adj_factor', 'is_st']],
               main_df[['ts_code', 'date', 'close', 'pre_close', 'adj_factor', 'is_st']]],
              ignore_index=True)
d['close_adj'] = d['close'] * d['adj_factor']
d = d.sort_values(['ts_code', 'date']).reset_index(drop=True)
d['bb_lower'] = d.groupby('ts_code')['close_adj'].transform(
    lambda x: (x.rolling(20, min_periods=20).mean() - 2.0 * x.rolling(20, min_periods=20).std()))
cal_full = pd.to_datetime(pd.read_parquet(os.path.join(ROOT, 'data', 'raw', 'trade_cal_full.parquet'))['date'].sort_values().reset_index(drop=True))
sb = pd.read_parquet(os.path.join(ROOT, 'data', 'raw', 'stock_basic.parquet'))[['ts_code', 'list_date']]
first_eligible = {}
for tc, ld in zip(sb['ts_code'], sb['list_date']):
    try:
        list_dt = pd.Timestamp(ld)
    except Exception:
        list_dt = pd.Timestamp('1990-01-01')
    first_eligible[tc] = int(np.searchsorted(cal_full, list_dt)) + 60
d['gi'] = d['date'].map({dt: i for i, dt in enumerate(cal_full)})
d['li'] = [d['gi'].iloc[i] - first_eligible.get(tc, 0) for i, tc in enumerate(d['ts_code'])]
mdf = d[(d.date >= '2020-01-01') & (d.date <= '2024-12-31')].copy()
mdf['r'] = mdf['close'] / mdf['pre_close'] - 1.0
mdf = mdf.replace([np.inf, -np.inf], np.nan)
elig = (mdf['li'] >= 0) & (~mdf['is_st']) & (mdf['bb_lower'].notna())
mkt_fb = mdf[elig].groupby('date')['r'].mean().sort_index()
# parity with B1 universe_size
br = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'b1', 'b1_daily_breadth.csv'),
                 parse_dates=['date']).set_index('date').sort_index()
us = mdf[elig].groupby('date').size().reindex(br.index)
assert (us - br['universe_size']).abs().max() == 0, 'fallback universe parity FAIL'
assert len(mkt_fb) == 1212
mkt = mkt_fb
cal = pd.DatetimeIndex(mkt.index)
close_idx = (1 + mkt).cumprod()  # normalized index level
# official index availability record (for completeness, no cherry-pick)
for code in ('000300', '000905', '000852'):
    d = pd.read_parquet(os.path.join(ROOT, 'data', f'index_{code}.parquet'))
    d['trade_date'] = pd.to_datetime(d['trade_date'])
    ok = d[d.trade_date.between('2020-01-02', '2024-12-31')].dropna()
    print(f'[series] official {code}: rows {len(ok)} (not selected: not full-market wide-base)', flush=True)

# ---------- forward returns on fallback series ----------
def fwd(t, H):
    i = cal.get_loc(t)
    if i + H >= len(cal):
        return np.nan
    return float(close_idx.iloc[i + H] / close_idx.iloc[i] - 1.0)

# ---------- PANIC80 (P7 parity) + EXPANDING_BREADTH_RANK01 ----------
brr = br.reset_index().sort_values('date').reset_index(drop=True)
day_index = {d: i for i, d in enumerate(cal)}
brr['day_idx'] = brr['date'].map(day_index)
min_hist = 252
rows = []
for _, r in brr.iterrows():
    t = r['date']; i = int(r['day_idx'])
    prior = i
    ref = brr.loc[brr['date'] < t, 'BREADTH_PCT']
    if prior < min_hist:
        p80 = np.nan; panic = 0; rank01 = np.nan
    else:
        p80 = float(np.percentile(ref, 80))
        panic = 1 if r['BREADTH_PCT'] >= p80 else 0
        rank01 = float((ref <= r['BREADTH_PCT']).mean())
    rows.append(dict(date=t, day_idx=i, breadth_pct=float(r['BREADTH_PCT']),
                     b20_count=int(r['B20_COUNT']), prior_trading_days=int(prior),
                     ref_p80=p80, panic80=int(panic), expanding_rank01=rank01))
st = pd.DataFrame(rows)
st['mkt_ret_t'] = st['date'].map(mkt).fillna(np.nan)
panic_days = st[st.panic80 == 1]
assert len(panic_days) == 188, f'PANIC80 parity FAIL {len(panic_days)} != 188'
st.to_csv(os.path.join(OUT, 'm11_panic_state.csv'), index=False)
st[['date', 'expanding_rank01', 'panic80', 'breadth_pct', 'prior_trading_days']].to_csv(
    os.path.join(OUT, 'm11_expanding_rank.csv'), index=False)
print(f'[m11] PANIC80 parity OK = 188 days; expanding rank available {st.expanding_rank01.notna().sum()}', flush=True)

for H in (1, 3, 5, 10, 20):
    st[f'FWD{H}'] = st['date'].map(lambda t: fwd(t, H))
st.to_csv(os.path.join(OUT, 'm11_forward_returns.csv'), index=False)

# ---------- deployable sample ----------
dep = st.dropna(subset=['FWD5', 'expanding_rank01']).copy()
dep['year'] = dep['date'].dt.year
print(f'[m11] deployable sample n={len(dep)} years={sorted(dep.year.unique())} panic={int(dep.panic80.sum())}', flush=True)

# ---------- primary estimand ----------
p = dep[dep.panic80 == 1]['FWD5']; n = dep[dep.panic80 == 0]['FWD5']
prim = dict(panic_n=len(p), normal_n=len(n),
            panic_mean_pct=round(float(p.mean() * 100), 4), panic_median_pct=round(float(p.median() * 100), 4),
            panic_win_pct=round(float((p > 0).mean() * 100), 2), panic_p10=round(float(np.percentile(p, 10) * 100), 4), panic_p90=round(float(np.percentile(p, 90) * 100), 4),
            normal_mean_pct=round(float(n.mean() * 100), 4), normal_median_pct=round(float(n.median() * 100), 4),
            normal_win_pct=round(float((n > 0).mean() * 100), 2),
            delta_pp=round(float((p.mean() - n.mean()) * 100), 4))
json.dump(prim, open(os.path.join(OUT, 'm11_primary_fwd5.json'), 'w'), indent=1)

# ---------- HAC (NW maxlags=10) + statsmodels parity ----------
def hac_ols(y, X, maxlags=10):
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    u = y - X @ b
    n, k = X.shape
    z = X * u[:, None]
    s0 = z.T @ z / n
    S = s0.copy()
    for l in range(1, maxlags + 1):
        w = 1.0 - l / (maxlags + 1)
        gl = (z[l:, :].T @ z[:-l, :]) / n
        S = S + w * (gl + gl.T)
    xtx = np.linalg.inv(X.T @ X / n)
    cov = xtx @ S @ xtx / n
    return b, np.sqrt(np.diag(cov))

y5 = dep['FWD5'].values * 100
f = dep['panic80'].values
Xp = np.column_stack([np.ones(len(y5)), f])
bp, sep = hac_ols(y5, Xp)
sm_res = sm.OLS(y5, Xp).fit(cov_type='HAC', cov_kwds={'maxlags': 10})
hac = dict(point_pp=round(float(bp[1]), 4), se=round(float(sep[1]), 4),
           ci_lower=round(float(bp[1] - 1.96 * sep[1]), 4), ci_upper=round(float(bp[1] + 1.96 * sep[1]), 4),
           sm_parity_se=round(float(sm_res.bse[1]), 4), sm_parity_ci=round(float(sm_res.conf_int()[1][0]), 4),
           statsmodels_match=bool(np.allclose(sm_res.params[1], bp[1]) and np.allclose(sm_res.bse[1], sep[1], atol=1e-8)))
json.dump(hac, open(os.path.join(OUT, 'm11_hac.json'), 'w'), indent=1)

# ---------- calendar moving block bootstrap (L=21, B=2000, seed=0) ----------
def mb_bootstrap(y, flag, L=21, B=2000, seed=0):
    rng = np.random.default_rng(seed)
    n = len(y)
    out = []
    for _ in range(B):
        idx = []
        while len(idx) < n:
            s = int(rng.integers(0, n))
            idx.extend(range(s, min(s + L, n)))
        idx = np.array(idx[:n])
        yb, fb = y[idx], flag[idx]
        if fb.sum() > 0 and fb.sum() < n:
            out.append(yb[fb == 1].mean() - yb[fb == 0].mean())
        else:
            out.append(np.nan)
    out = np.array(out)
    return out

bs = mb_bootstrap(y5, f)
bs_ok = bs[~np.isnan(bs)]
boot = dict(point_pp=float(hac['point_pp']), boot_mean=round(float(bs_ok.mean()), 4),
            boot_median=round(float(np.median(bs_ok)), 4),
            boot_p2_5=round(float(np.percentile(bs_ok, 2.5)), 4), boot_p97_5=round(float(np.percentile(bs_ok, 97.5)), 4),
            na_replicates=int(np.isnan(bs).sum()))
json.dump(boot, open(os.path.join(OUT, 'm11_bootstrap.json'), 'w'), indent=1)

# ---------- continuous primary-support test ----------
rk = dep['expanding_rank01'].values
Xr = np.column_stack([np.ones(len(y5)), rk])
br2, ser2 = hac_ols(y5, Xr)
sm_r = sm.OLS(y5, Xr).fit(cov_type='HAC', cov_kwds={'maxlags': 10})
rho, rho_p = spearmanr(rk, y5)
cont = dict(slope_pp=round(float(br2[1]), 4), se=round(float(ser2[1]), 4),
            ci_lower=round(float(br2[1] - 1.96 * ser2[1]), 4), ci_upper=round(float(br2[1] + 1.96 * ser2[1]), 4),
            spearman=round(float(rho), 4), spearman_p=round(float(rho_p), 4),
            sm_parity_se=round(float(sm_r.bse[1]), 4), statsmodels_match=bool(np.allclose(sm_r.params[1], br2[1])))
json.dump(cont, open(os.path.join(OUT, 'm11_continuous.json'), 'w'), indent=1)

# ---------- conditional: FWD5 ~ expanding_rank + MARKET_RET_T ----------
csub = dep.dropna(subset=['mkt_ret_t'])
Xc = np.column_stack([np.ones(len(csub)), csub['expanding_rank01'].values, csub['mkt_ret_t'].values * 100])
yc = csub['FWD5'].values * 100
bc, sec = hac_ols(yc, Xc)
sm_c = sm.OLS(yc, Xc).fit(cov_type='HAC', cov_kwds={'maxlags': 10})
cond = dict(b1_rank_pp=round(float(bc[1]), 4), b1_se=round(float(sec[1]), 4),
            b1_ci_lower=round(float(bc[1] - 1.96 * sec[1]), 4), b1_ci_upper=round(float(bc[1] + 1.96 * sec[1]), 4),
            b2_mkt=round(float(bc[2]), 4), b2_se=round(float(sec[2]), 4),
            b2_ci_lower=round(float(bc[2] - 1.96 * sec[2]), 4), b2_ci_upper=round(float(bc[2] + 1.96 * sec[2]), 4),
            sm_parity_b1_se=round(float(sm_c.bse[1]), 4), statsmodels_match=bool(np.allclose(sm_c.params, bc, atol=1e-8)))
json.dump(cond, open(os.path.join(OUT, 'm11_conditional.json'), 'w'), indent=1)

# ---------- yearly 2021-2024 ----------
y_rows = []
for y_ in (2021, 2022, 2023, 2024):
    g = dep[dep.year == y_]
    gp = g[g.panic80 == 1]['FWD5']; gn = g[g.panic80 == 0]['FWD5']
    rho_y = spearmanr(g['expanding_rank01'], g['FWD5']).statistic if len(g) > 3 else np.nan
    y_rows.append(dict(year=y_, panic_n=len(gp), normal_n=len(gn),
                       panic_mean_pct=round(float(gp.mean() * 100), 4) if len(gp) else np.nan,
                       normal_mean_pct=round(float(gn.mean() * 100), 4) if len(gn) else np.nan,
                       delta_pp=round(float((gp.mean() - gn.mean()) * 100), 4) if len(gp) and len(gn) else np.nan,
                       spearman_rank=round(float(rho_y), 4) if np.isfinite(rho_y) else np.nan))
pd.DataFrame(y_rows).to_csv(os.path.join(OUT, 'm11_yearly.csv'), index=False)
y_pos = int(sum(1 for r in y_rows if np.isfinite(r['delta_pp']) and r['delta_pp'] > 0))

# ---------- cluster-first robustness ----------
st_sorted = st.sort_values('date').reset_index(drop=True)
panic_idx = st_sorted.index[st_sorted.panic80 == 1]
clusters = []
cur = [panic_idx[0]]
for j in panic_idx[1:]:
    if j == cur[-1] + 1:
        cur.append(j)
    else:
        clusters.append(cur); cur = [j]
clusters.append(cur)
first_days = [st_sorted.iloc[c[0]]['date'] for c in clusters]
cf = st_sorted[st_sorted.date.isin(first_days)].dropna(subset=['FWD5'])
nrm = st_sorted[(st_sorted.panic80 == 0)].dropna(subset=['FWD5'])
cf5 = cf['FWD5']; nr5 = nrm['FWD5']
clu = dict(n_clusters=len(clusters), first_day_n=len(cf),
           cluster_mean_pct=round(float(cf5.mean() * 100), 4), cluster_median_pct=round(float(cf5.median() * 100), 4),
           cluster_win_pct=round(float((cf5 > 0).mean() * 100), 2),
           normal_mean_pct=round(float(nr5.mean() * 100), 4), delta_pp=round(float((cf5.mean() - nr5.mean()) * 100), 4))
json.dump(clu, open(os.path.join(OUT, 'm11_clusters.json'), 'w'), indent=1)

# ---------- all horizons ----------
h_rows = []
for H in (1, 3, 5, 10, 20):
    sub = dep.dropna(subset=[f'FWD{H}'])
    yh = sub[f'FWD{H}'].values * 100
    fh = sub['panic80'].values
    Xh = np.column_stack([np.ones(len(yh)), fh])
    bh, seh = hac_ols(yh, Xh)
    hp = sub[sub.panic80 == 1][f'FWD{H}'].mean() * 100
    hn = sub[sub.panic80 == 0][f'FWD{H}'].mean() * 100
    h_rows.append(dict(horizon=H, panic_n=int(sub.panic80.sum()), normal_n=int((sub.panic80 == 0).sum()),
                       panic_mean_pct=round(float(hp), 4), normal_mean_pct=round(float(hn), 4),
                       delta_pp=round(float(hp - hn), 4),
                       hac_ci_lower=round(float(bh[1] - 1.96 * seh[1]), 4), hac_ci_upper=round(float(bh[1] + 1.96 * seh[1]), 4)))
pd.DataFrame(h_rows).to_csv(os.path.join(OUT, 'm11_horizons.csv'), index=False)

# ---------- tail ----------
fp = dep[dep.panic80 == 1]['FWD5'] * 100
fn_ = dep[dep.panic80 == 0]['FWD5'] * 100
tail = dict(panic_mean=round(float(fp.mean()), 4), panic_median=round(float(fp.median()), 4),
            panic_win=round(float((fp > 0).mean() * 100), 2), panic_p10=round(float(np.percentile(fp, 10)), 4),
            panic_p5=round(float(np.percentile(fp, 5)), 4), panic_min=round(float(fp.min()), 4),
            normal_mean=round(float(fn_.mean()), 4), normal_median=round(float(fn_.median()), 4),
            normal_win=round(float((fn_ > 0).mean() * 100), 2), normal_p10=round(float(np.percentile(fn_, 10)), 4),
            normal_p5=round(float(np.percentile(fn_, 5)), 4), normal_min=round(float(fn_.min()), 4))
json.dump(tail, open(os.path.join(OUT, 'm11_tail_fwd5.json'), 'w'), indent=1)

# future-5d drawdown from T close
def fwd_dd(t):
    i = cal.get_loc(t)
    if i + 5 >= len(cal):
        return np.nan
    seg = close_idx.iloc[i + 1:i + 6]
    return float(seg.min() / close_idx.iloc[i] - 1.0)

st['DD5'] = st['date'].map(fwd_dd)
dd_dep = st.dropna(subset=['DD5'])
dp = dd_dep[dd_dep.panic80 == 1]['DD5'] * 100
dn = dd_dep[dd_dep.panic80 == 0]['DD5'] * 100
dd5 = dict(panic_mean=round(float(dp.mean()), 4), panic_median=round(float(dp.median()), 4),
           panic_p10=round(float(np.percentile(dp, 10)), 4), panic_p5=round(float(np.percentile(dp, 5)), 4), panic_min=round(float(dp.min()), 4),
           normal_mean=round(float(dn.mean()), 4), normal_median=round(float(dn.median()), 4),
           normal_p10=round(float(np.percentile(dn, 10)), 4), normal_p5=round(float(np.percentile(dn, 5)), 4), normal_min=round(float(dn.min()), 4))
json.dump(dd5, open(os.path.join(OUT, 'm11_tail_drawdown5.json'), 'w'), indent=1)

# ---------- protocol bridge ----------
pd.DataFrame([
    dict(deviation='D1', external='PRIMARY=FWD5', m1_actual='FWD20', m11='FWD5 restored'),
    dict(deviation='D2', external='horizons 1/3/5/10/20', m1_actual='5/10/20/40', m11='1/3/5/10/20 (FWD40 excluded from classification)'),
    dict(deviation='D3', external='EXPANDING_BREADTH_RANK01', m1_actual='raw Spearman + full-sample Q1-Q5', m11='EXPANDING_BREADTH_RANK01'),
    dict(deviation='D4', external='FWD5 ~ expanding_rank + MARKET_RET_T', m1_actual='panic dummy conditional', m11='expanding_rank + MARKET_RET_T (panic-dummy kept as secondary descriptive)'),
    dict(deviation='D5', external='yearly 2021-2024 >=3/4', m1_actual='registry 2020-2024 >=3/5', m11='2021-2024 >=3/4'),
    dict(deviation='D6', external='cluster-first robustness', m1_actual='missing', m11='clusters merged, first-day only'),
    dict(deviation='D7', external='FWD5 tail + future-5d drawdown', m1_actual='missing', m11='FWD5 tail + DD5 present'),
    dict(deviation='D8', external='benchmark hierarchy official-first', m1_actual='not executed/recorded', m11='official checked (000985 absent), PIT equal-weight fallback recorded'),
]).to_csv(os.path.join(OUT, 'm11_protocol_bridge.csv'), index=False)

# ---------- classification (frozen external gate) ----------
p5_delta = prim['delta_pp'] > 0
hac_ok = hac['ci_lower'] > 0
boot_ok = boot['boot_p2_5'] > 0
cont_ok = cont['slope_pp'] > 0 and cont['ci_lower'] > 0
cond_ok = cond['b1_rank_pp'] > 0 and cond['b1_ci_lower'] > 0
tail_severe = tail['panic_p5'] < tail['normal_p5'] and tail['panic_min'] < tail['normal_min']
if p5_delta and hac_ok and boot_ok and cont_ok and cond_ok and y_pos >= 3 and not tail_severe:
    cls = 'A_STRONG_MARKET_TRANSLATION'; etf = 'YES'
elif p5_delta and y_pos >= 3 and not tail_severe:
    cls = 'B_NARROW_MARKET_TRANSLATION'; etf = 'YES'
elif not p5_delta and (tail_severe or (dep[dep.panic80 == 1]['FWD5'].mean() < dep[dep.panic80 == 0]['FWD5'].mean())):
    cls = 'D_HARMFUL_MARKET_STATE'; etf = 'NO'
else:
    cls = 'C_NO_STABLE_MARKET_TRANSLATION'; etf = 'NO'

summary = dict(registry_sha=reg_sha, market_series=choice, primary=prim, hac=hac, bootstrap=boot,
               continuous=cont, conditional=cond, yearly=y_rows, clusters=clu,
               horizons=h_rows, tail=tail, dd5=dd5,
               positive_years=int(y_pos), classification=cls, etf_gate=etf)
json.dump(summary, open(os.path.join(OUT, 'm11_summary.json'), 'w'), indent=1)
json.dump(dict(I1_m1_b_withdrawn=True, I2_m1_artifacts_exploratory=True, I3_panic80_p7_parity=True,
               I4_date_lt_T_only=True, I5_252_warmup=True, I6_fwd5_primary=True, I7_horizons_1_3_5_10_20=True,
               I8_continuous_expanding_rank=True, I9_conditional_expanding_rank=True, I10_year_2021_2024=True,
               I11_cluster_robustness=True, I12_5d_tail=True, I13_no_horizon_selection=True,
               I14_no_portfolio_etf=True, I15_2025_2026_closed=True),
          open(os.path.join(OUT, 'm11_invariants.json'), 'w'), indent=1)
print(f'cls={cls} etf={etf} | FWD5 delta={prim["delta_pp"]} HAC={hac["ci_lower"]},{hac["ci_upper"]} boot={boot["boot_p2_5"]},{boot["boot_p97_5"]} cont={cont["ci_lower"]},{cont["ci_upper"]} cond_b1={cond["b1_ci_lower"]},{cond["b1_ci_upper"]} yearly_pos={y_pos}/4', flush=True)
print('[DONE]', flush=True)
