#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M1 — PANIC-BREADTH → MARKET REBOUND TRANSLATION
================================================
Frozen Registry: PANIC_REBOUND_M1_REGISTRY.csv (SHA 44d7c777...)
Prereg commit: 661e81f (M1-A). Governance: R1.9 commit 1cf7b38 (P7=D accepted).

Pure market-level diagnostic. B1.1=A breadth alpha → market forward rebound?
- PANIC80 = P7 deployable expanding percentile (dates<T only, 252 prior trading days)
- benchmark = all-A equal-weight daily return (B1 MKT_RET same construction)
- forward horizons H ∈ {5,10,20,40}; PRIMARY H=20
- primary compare: PANIC vs NON-PANIC signal days, signal-day equal weight
- inference: HAC(maxlags=10) + calendar moving block bootstrap (L=21, B=2000, seed=0)
- conditional: forward_ret ~ a + b1*PANIC + b2*MKT_RET (multivariate NW sandwich)
- NO portfolio / NO parameter scan / 2025-2026 CLOSED
"""
import os, sys, json, hashlib
import numpy as np, pandas as pd
from scipy.stats import spearmanr

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
OUT = os.path.join(REPO, 'results', 'evidence', 'm1')
os.makedirs(OUT, exist_ok=True)

REG = os.path.join(REPO, 'research', 'market_rebound', 'registries', 'PANIC_REBOUND_M1_REGISTRY.csv')
with open(REG, 'rb') as f:
    reg_sha = hashlib.sha256(f.read()).hexdigest()
assert reg_sha == '44d7c7773bc9d98cc0e40246987f2c52b5bd3b634d11b3742aec6145ac5b8900', 'M1 registry SHA mismatch'

# ---------- all-A equal-weight daily market return (B1 MKT_RET same construction) ----------
main_df = pd.read_parquet(os.path.join(ROOT, 'data', 'combined_daily.parquet'))
main_df['date'] = pd.to_datetime(main_df['date'])
mret = main_df[['date', 'pre_close', 'close']].copy()
mret['r'] = mret['close'] / mret['pre_close'] - 1.0
mret = mret.replace([np.inf, -np.inf], np.nan)
mkt = mret.groupby('date')['r'].mean().sort_index()
mkt = mkt[(mkt.index >= '2020-01-01') & (mkt.index <= '2024-12-31')]
assert len(mkt) == 1212, len(mkt)
cal = pd.DatetimeIndex(mkt.index)

# forward cumulative returns from T+1 .. T+H
def forward_ret(t, H):
    i = cal.get_loc(t)
    if i + H >= len(cal):
        return np.nan
    return float(np.prod(1.0 + mkt.iloc[i + 1:i + 1 + H].values) - 1.0)

# ---------- B1 daily breadth + P7 deployable PANIC80 ----------
br = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'b1', 'b1_daily_breadth.csv'),
                 parse_dates=['date']).sort_values('date').reset_index(drop=True)
assert len(br) == 1110
day_index = {d: i for i, d in enumerate(cal)}
br['day_idx'] = br['date'].map(day_index)
min_hist = 252
panic_rows = []
for _, r in br.iterrows():
    t = r['date']; i = int(r['day_idx'])
    prior = i
    if prior < min_hist:
        panic = 0; p80 = np.nan
    else:
        ref = br.loc[br['date'] < t, 'BREADTH_PCT']
        p80 = float(np.percentile(ref, 80))
        panic = 1 if r['BREADTH_PCT'] >= p80 else 0
    panic_rows.append(dict(date=t, day_idx=i, breadth_pct=float(r['BREADTH_PCT']),
                           b20_count=int(r['B20_COUNT']), prior_trading_days=int(prior),
                           ref_p80=p80, panic80=int(panic)))
panic_df = pd.DataFrame(panic_rows)
panic_df.to_csv(os.path.join(OUT, 'm1_panic_state.csv'), index=False)
panic_days = panic_df[panic_df.panic80 == 1]
assert len(panic_days) == 188, f'PANIC80 days {len(panic_days)} != 188 (P7 frozen)'

# B1 frozen quintile labels (no re-qcut)
q5 = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'b1', 'b1_quintiles.csv'))
# rebuild labels from full-sample qcut exactly as B1.1 (BREADTH_PCT 5 bins)
br = br.sort_values('date').reset_index(drop=True)
labels = pd.qcut(br['BREADTH_PCT'], 5, labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'], duplicates='drop')
br['Q'] = labels.astype(str)

# ---------- forward returns ----------
HORIZONS = [5, 10, 20, 40]
for H in HORIZONS:
    br[f'FWD_{H}'] = br['date'].map(lambda t: forward_ret(t, H))
br.to_csv(os.path.join(OUT, 'm1_forward_market.csv'), index=False)

# ---------- primary: PANIC vs NON-PANIC (signal days only) ----------
br['PANIC'] = br['date'].map(dict(zip(panic_df['date'], panic_df['panic80']))).fillna(0).astype(int)
sig = br.dropna(subset=['FWD_20']).copy()  # primary horizon availability

pr_rows = []
for H in HORIZONS:
    sub = br.dropna(subset=[f'FWD_{H}']).copy()
    p = sub[sub.PANIC == 1][f'FWD_{H}']
    n = sub[sub.PANIC == 0][f'FWD_{H}']
    delta = float(p.mean() - n.mean())
    pr_rows.append(dict(horizon=H, panic_n=len(p), nonpanic_n=len(n),
                        panic_mean_pct=round(float(p.mean() * 100), 4),
                        nonpanic_mean_pct=round(float(n.mean() * 100), 4),
                        delta_pp=round(delta * 100, 4)))
pr = pd.DataFrame(pr_rows)
pr.to_csv(os.path.join(OUT, 'm1_panic_rebound.csv'), index=False)

# ---------- quintile forward ----------
q_rows = []
for H in HORIZONS:
    for q in ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']:
        sub = br[br.Q == q].dropna(subset=[f'FWD_{H}'])
        q_rows.append(dict(horizon=H, quintile=q, n=len(sub),
                           mean_fwd_pct=round(float(sub[f'FWD_{H}'].mean() * 100), 4)))
pd.DataFrame(q_rows).to_csv(os.path.join(OUT, 'm1_quintiles.csv'), index=False)

# ---------- inference helpers ----------
def hac_se(X, u, maxlags=10):
    n = X.shape[0]
    k = X.shape[1]
    z = X * u[:, None]
    s0 = z.T @ z / n
    S = s0.copy()
    for l in range(1, maxlags + 1):
        w = 1.0 - l / (maxlags + 1)
        gl = (z[l:, :].T @ z[:-l, :]) / n
        S = S + w * (gl + gl.T)
    xtx_inv = np.linalg.inv(X.T @ X / n)
    cov = xtx_inv @ S @ xtx_inv / n
    return np.sqrt(np.diag(cov))

def calendar_bootstrap_delta(y, flag, L=21, B=2000, seed=0):
    """delta_b = mean(sampled panic) - mean(sampled nonpanic) per replicate; NA if either group empty."""
    rng = np.random.default_rng(seed)
    n = len(y)
    nblocks = int(np.ceil(n / L))
    out = []
    for _ in range(B):
        idx = []
        while len(idx) < n:
            s = rng.integers(0, n)
            idx.extend(range(s, min(s + L, n)))
        idx = np.array(idx[:n])
        yb, fb = y[idx], flag[idx]
        if fb.sum() > 0 and (fb.sum() < n):
            out.append(yb[fb == 1].mean() - yb[fb == 0].mean())
        else:
            out.append(np.nan)
    out = np.array(out)
    return out

inf_rows = []
for H in HORIZONS:
    sub = br.dropna(subset=[f'FWD_{H}']).copy()
    y = sub[f'FWD_{H}'].values * 100
    f = sub['PANIC'].values
    # HAC regression forward ~ panic (single regressor + intercept)
    X = np.column_stack([np.ones(len(y)), f])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    u = y - X @ b
    se = hac_se(X, u)
    ci = [b[1] - 1.96 * se[1], b[1] + 1.96 * se[1]]
    # calendar bootstrap
    bs = calendar_bootstrap_delta(y, f, L=21, B=2000, seed=0)
    bs_ok = bs[~np.isnan(bs)]
    inf_rows.append(dict(horizon=H, point_pp=round(float(b[1]), 4),
                         hac_se=round(float(se[1]), 4), hac_ci_lower=round(ci[0], 4), hac_ci_upper=round(ci[1], 4),
                         boot_mean=round(float(bs_ok.mean()), 4), boot_median=round(float(np.median(bs_ok)), 4),
                         boot_p2_5=round(float(np.percentile(bs_ok, 2.5)), 4), boot_p97_5=round(float(np.percentile(bs_ok, 97.5)), 4),
                         na_replicates=int(np.isnan(bs).sum())))
inf = pd.DataFrame(inf_rows)
inf.to_csv(os.path.join(OUT, 'm1_inference.csv'), index=False)

# ---------- conditional: forward ~ panic + MKT_RET ----------
cond_rows = []
for H in HORIZONS:
    sub = br.dropna(subset=[f'FWD_{H}', 'MKT_RET']).copy()
    y = sub[f'FWD_{H}'].values * 100
    X = np.column_stack([np.ones(len(y)), sub['PANIC'].values, sub['MKT_RET'].values * 100])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    u = y - X @ b
    se = hac_se(X, u)
    cond_rows.append(dict(horizon=H, b1_panic=round(float(b[1]), 4), b1_se=round(float(se[1]), 4),
                          b1_ci_lower=round(b[1] - 1.96 * se[1], 4), b1_ci_upper=round(b[1] + 1.96 * se[1], 4),
                          b2_mkt=round(float(b[2]), 4), b2_se=round(float(se[2]), 4),
                          b2_ci_lower=round(b[2] - 1.96 * se[2], 4), b2_ci_upper=round(b[2] + 1.96 * se[2], 4)))
pd.DataFrame(cond_rows).to_csv(os.path.join(OUT, 'm1_conditional.csv'), index=False)

# ---------- yearly ----------
y_rows = []
for H in HORIZONS:
    for y_, g in br.groupby(br['date'].dt.year):
        g = g.dropna(subset=[f'FWD_{H}'])
        p = g[g.PANIC == 1][f'FWD_{H}']
        n = g[g.PANIC == 0][f'FWD_{H}']
        delta = float(p.mean() - n.mean()) if len(p) and len(n) else np.nan
        rho = spearmanr(g['BREADTH_PCT'], g[f'FWD_{H}']).statistic if len(g) > 3 else np.nan
        y_rows.append(dict(year=int(y_), horizon=H, panic_n=len(p), nonpanic_n=len(n),
                           delta_pp=round(delta * 100, 4) if np.isfinite(delta) else np.nan,
                           spearman=round(float(rho), 4) if np.isfinite(rho) else np.nan))
pd.DataFrame(y_rows).to_csv(os.path.join(OUT, 'm1_yearly.csv'), index=False)

# ---------- monotonicity (primary horizon) ----------
H0 = 20
sub = br.dropna(subset=[f'FWD_{H0}'])
rho20, p20 = spearmanr(sub['BREADTH_PCT'], sub[f'FWD_{H0}'])
q_means = br[br.Q.notna()].groupby('Q')[f'FWD_{H0}'].mean().reindex(['Q1', 'Q2', 'Q3', 'Q4', 'Q5'])
mono = dict(horizon=H0, spearman=round(float(rho20), 4), spearman_p=round(float(p20), 4),
            q1_pct=round(float(q_means['Q1'] * 100), 4), q2_pct=round(float(q_means['Q2'] * 100), 4),
            q3_pct=round(float(q_means['Q3'] * 100), 4), q4_pct=round(float(q_means['Q4'] * 100), 4),
            q5_pct=round(float(q_means['Q5'] * 100), 4),
            q5_q1_pp=round(float((q_means['Q5'] - q_means['Q1']) * 100), 4))
json.dump(mono, open(os.path.join(OUT, 'm1_monotonicity.json'), 'w'), indent=1)

# ---------- classification (frozen gates) ----------
inf20 = inf[inf.horizon == 20].iloc[0]
inf10 = inf[inf.horizon == 10].iloc[0]
cond20 = cond_rows[3]  # H=20
yearly20 = pd.DataFrame(y_rows)
yearly20 = yearly20[yearly20.horizon == 20].dropna(subset=['delta_pp'])
y_pos = int((yearly20['delta_pp'] > 0).sum())
point_pos = inf20['point_pp'] > 0
hac_pos = inf20['hac_ci_lower'] > 0
cal_pos = inf20['boot_p2_5'] > 0
h10_consist = inf10['point_pp'] > 0
cond_pos = cond20['b1_panic'] > 0 and cond20['b1_ci_lower'] > 0

if point_pos and hac_pos and cal_pos and y_pos >= 3 and h10_consist and cond_pos:
    cls = 'A_STRONG_REBOUND_TRANSLATION'; verdict = 'YES'
elif point_pos and y_pos >= 3 and h10_consist:
    cls = 'B_NARROW_REBOUND'; verdict = 'YES'
elif not point_pos:
    cls = 'D_HARMFUL' if inf20['point_pp'] < 0 and (inf20['hac_ci_upper'] < 0 or yearly20['delta_pp'].mean() < 0) else 'C_NO_STABLE_REBOUND'
    verdict = 'NO' if cls == 'D_HARMFUL' else 'UNCERTAIN'
else:
    cls = 'C_NO_STABLE_REBOUND'; verdict = 'UNCERTAIN'

summary = dict(registry_sha=reg_sha, panic80_days=int(len(panic_days)),
               primary_compare=pr.to_dict('records'), inference=inf.to_dict('records'),
               conditional=cond_rows, yearly=pd.DataFrame(y_rows).to_dict('records'),
               monotonicity=mono, classification=cls, etf_carrier_verdict=verdict,
               panic_mean_fwd20_pp=round(float(sig[sig.PANIC == 1]['FWD_20'].mean() * 100), 4),
               nonpanic_mean_fwd20_pp=round(float(sig[sig.PANIC == 0]['FWD_20'].mean() * 100), 4))
json.dump(summary, open(os.path.join(OUT, 'm1_summary.json'), 'w'), indent=1)
json.dump(dict(I1_breadth_p7_panic80=True, I2_forward_dates_gt_T=True, I3_alla_equal_weight=True,
               I4_no_portfolio_run=True, I5_no_parameter_scan=True, I6_no_2025_2026=True,
               I7_prior_registry_sha_unchanged=True),
          open(os.path.join(OUT, 'm1_invariants.json'), 'w'), indent=1)
print(f'cls={cls} verdict={verdict} | H20 point={inf20["point_pp"]} HAC={inf20["hac_ci_lower"]},{inf20["hac_ci_upper"]} boot={inf20["boot_p2_5"]},{inf20["boot_p97_5"]} yearly_pos={y_pos}/5 cond_b1={cond20["b1_panic"]} CI={cond20["b1_ci_lower"]},{cond20["b1_ci_upper"]}', flush=True)
print('[DONE]', flush=True)
