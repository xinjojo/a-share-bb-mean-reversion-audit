"""
==========================================================
TEMPORAL CLUSTERING DIAGNOSTIC — PHASE T1
STRICT_C FULL-MARKET SECONDARY (+ PRIMARY benchmark)
==========================================================
Pure time-clustering audit of the FROZEN V2A_FROZEN_STRICT episodes.
Question: do winning/losing trades cluster in time (state persistence)?
NO regime explanation, NO market variables, NO filters, NO strategy change.

Samples (frozen, read only):
  SECONDARY: results/fullmarket_episode_metrics.csv  (89,046 realized)
  PRIMARY  : results/independent_v2a_episodes.pkl    (299 realized)

Primary series: signal-date cross-sectional mean final return (R_mean(t)).
OUTCOME DIAGNOSTIC only - not a tradeable predictor.

Methods:
  - Wald-Wolfowitz runs test + 10,000-day-permutation null (permute signal DAYS,
    preserving each day's cross-section) on: runs, max +/- run, sum sq run lengths,
    mean abs diff, lag1/lag5 ACF, 20D/60D rolling-mean variance, longest rolling<0 run.
  - ACF (lag 1..120) on R_mean / sign / win-rate vs permutation null.
  - Conditional persistence probabilities vs permutation null.
  - Multi-scale block variance-ratio (5..120 days) vs permutation.
  - Calendar aggregation (monthly heatmap, quarterly, semiannual) - description only.
  - Change-point detection: A) PELT mean-shift, BIC penalty 2*var*log(N) [pre-fixed];
    B) CUSUM binary segmentation with permutation-calibrated threshold [pre-fixed].
    Segments are called PERFORMANCE SEGMENTS (not regime).
  - Cluster duration (positive/negative segments), calendar + signal days.
  - Effective sample size: ACF (first-zero-crossing + Geyer monotone) + block bootstrap.
  - Quality drawdowns: Q20/Q60 < 0 intervals.
  - Cross-sectional synchronization (day quality buckets).
  - PRIMARY vs SECONDARY daily-outcome correlation.
  - Leave-one-year-out stability of the clustering statistics.

No Validation opened. Registry untouched.
==========================================================
"""
import os, sys, pickle, time
import numpy as np, pandas as pd
from collections import Counter

REPO = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(REPO, 'results'); os.makedirs(OUT, exist_ok=True)
FIG = os.path.join(REPO, 'figures'); os.makedirs(FIG, exist_ok=True)
RNG = np.random.default_rng(42)


def load_episodes():
    fm = pd.read_csv(os.path.join(OUT, 'fullmarket_episode_metrics.csv'))
    fm['signal_date'] = pd.to_datetime(fm['signal_date'])
    d = pickle.load(open(os.path.join(OUT, 'independent_v2a_episodes.pkl'), 'rb'))
    fep = d['episodes']
    p = pd.DataFrame([dict(ts_code=e['ts_code'], signal_date=pd.to_datetime(e['signal_date']),
                           return_pct=float(e['return_pct']), hold_days=int(e['hold_days']))
                      for e in fep])
    return fm, p


def daily_series(df, retcol):
    g = df.groupby('signal_date')
    r = pd.DataFrame({
        'mean_return': g[retcol].mean(),
        'median_return': g[retcol].median(),
        'win_rate': (g[retcol].apply(lambda s: (s > 0).mean() * 100)),
        'loss_rate': (g[retcol].apply(lambda s: (s <= 0).mean() * 100)),
        'n_episodes': g[retcol].size(),
    })
    if 'MAE_intraday_pct' in df.columns:
        r['mean_mae'] = g['MAE_intraday_pct'].mean()
        r['mean_hold'] = g['hold_days'].mean()
    r = r.reset_index()
    return r


# ------------------------------------------------------------
# runs & permutation statistics
# ------------------------------------------------------------
def run_lengths(s):
    s = s.astype(np.int8)
    d = np.diff(np.concatenate(([0], s, [0])))
    starts = np.flatnonzero(d == 1); ends = np.flatnonzero(d == -1)
    return ends - starts


def all_stats(x):
    n = len(x)
    s = x > 0
    rp = run_lengths(s); rn = run_lengths(~s)
    n_runs = len(rp) + len(rn)
    max_pos = int(rp.max()) if len(rp) else 0
    max_neg = int(rn.max()) if len(rn) else 0
    sum_sq = int((rp.astype(np.int64) ** 2).sum() + (rn.astype(np.int64) ** 2).sum())
    md = float(np.mean(np.abs(np.diff(x))))
    a1 = float(np.corrcoef(x[:-1], x[1:])[0, 1]) if n > 2 else np.nan
    a5 = float(np.corrcoef(x[:-5], x[5:])[0, 1]) if n > 6 else np.nan

    def roll_var(w):
        S = np.concatenate([[0], np.cumsum(x)])
        ws = (S[w:] - S[:-w]) / w
        return float(ws.var())
    rv20 = roll_var(20); rv60 = roll_var(60)

    # longest rolling-20 mean < 0 interval
    S = np.concatenate([[0], np.cumsum(x)])
    r20 = (S[20:] - S[:-20]) / 20
    rl = run_lengths(r20 < 0)
    max_roll_neg = int(rl.max()) if len(rl) else 0
    return dict(n_runs=n_runs, max_pos=max_pos, max_neg=max_neg, sum_sq=sum_sq,
                mean_abs_diff=md, lag1_acf=a1, lag5_acf=a5, rv20=rv20, rv60=rv60,
                max_roll_neg=max_roll_neg)


def wald_wolfowitz(s):
    s = np.asarray(s, dtype=bool)
    n1 = int(s.sum()); n2 = int((~s).sum()); n = n1 + n2
    r = len(run_lengths(s)) + len(run_lengths(~s))
    if n1 == 0 or n2 == 0:
        return dict(n1=n1, n2=n2, runs=r, z=np.nan, p=np.nan)
    E = 1 + 2 * n1 * n2 / n
    V = 2 * n1 * n2 * (2 * n1 * n2 - n) / (n * n * (n - 1))
    z = (r - E) / np.sqrt(V)
    from scipy.stats import norm
    p = 2 * (1 - norm.cdf(abs(z)))
    return dict(n1=n1, n2=n2, runs=r, z=float(z), p=float(p))


# ------------------------------------------------------------
# ACF
# ------------------------------------------------------------
def acf(x, maxlag):
    n = len(x); xc = x - x.mean()
    v = (xc * xc).sum() / n
    out = []
    for k in range(1, maxlag + 1):
        a = (xc[:-k] * xc[k:]).sum() / (n - k) / v
        out.append(a)
    return np.array(out)


# ------------------------------------------------------------
# effective sample size
# ------------------------------------------------------------
def neff_estimates(x, maxlag=250):
    n = len(x)
    rho = acf(x, maxlag)
    # rule 1: first zero crossing
    neg = np.flatnonzero(rho <= 0)
    k1 = neg[0] if len(neg) else maxlag          # rho_1..rho_{k1-1} used
    r1 = rho[:k1]
    neff1 = n / (1 + 2 * r1.sum())
    # rule 2: Geyer initial monotone (positive) sequence
    m = np.array(rho)
    for k in range(1, len(m)):
        if m[k] > m[k - 1]:
            m[k] = m[k - 1]
    m[m < 0] = 0
    stop = np.flatnonzero(m <= 0)
    k2 = stop[0] if len(stop) else maxlag
    neff2 = n / (1 + 2 * m[:k2].sum())
    # block bootstrap sensitivity
    boot_neff = {}
    for L in (10, 21, 40, 60):
        B = 2000; nblk = int(np.ceil(n / L)); means = np.empty(B)
        for b in range(B):
            idx = []
            for _ in range(nblk):
                st = RNG.integers(0, n - L + 1) if n - L + 1 > 0 else 0
                idx.extend(range(st, min(st + L, n)))
            means[b] = x[np.array(idx[:n])].mean()
        var_iid = x.var() / n
        var_boot = means.var()
        boot_neff[L] = n * var_iid / var_boot
    return dict(k_first_zc=int(k1), neff_zc=float(neff1), k_geyer=int(k2),
                neff_geyer=float(neff2), boot=boot_neff)


# ------------------------------------------------------------
# PELT (mean shift) with BIC-style penalty (pre-fixed)
# ------------------------------------------------------------
def pelt_mean(x, beta):
    n = len(x)
    S = np.concatenate([[0], np.cumsum(x)]).astype(float)
    S2 = np.concatenate([[0], np.cumsum(x * x)]).astype(float)
    F = np.full(n + 1, np.inf); F[0] = 0.0
    cp = np.full(n + 1, -1, dtype=int)
    R = [0]
    for t in range(1, n + 1):
        best = np.inf; best_s = -1
        for s in R:
            if s >= t:
                continue
            m = t - s
            cost = (S2[t] - S2[s]) - (S[t] - S[s]) ** 2 / m
            pen = 0.0 if s == 0 else beta
            v = F[s] + cost + pen
            if v < best:
                best = v; best_s = s
        F[t] = best; cp[t] = best_s
        newR = [s for s in R if s < t and F[s] + (S2[t] - S2[s]) - (S[t] - S[s]) ** 2 / (t - s) <= F[t]]
        newR.append(t)
        R = newR
    ch = []
    k = cp[n]
    while k > 0:
        ch.append(k); k = cp[k]
    return sorted(ch)


# ------------------------------------------------------------
# CUSUM binary segmentation with permutation-calibrated threshold
# ------------------------------------------------------------
def cusum_stat(x):
    n = len(x)
    x = np.asarray(x, float)
    pref = np.concatenate([[0], np.cumsum(x)])
    tot = pref[n]
    k = np.arange(1, n)
    left = pref[k] / k
    right = (tot - pref[k]) / (n - k)
    T = np.sqrt(k * (n - k) / n) * np.abs(left - right)
    i = int(np.argmax(T))
    return float(T[i]), i, T


def cusum_threshold(x, B=1000, alpha=0.05):
    n = len(x); maxT = np.empty(B)
    for b in range(B):
        y = RNG.permutation(x)
        T, _, _ = cusum_stat(y)
        maxT[b] = T
    return float(np.percentile(maxT, 100 * (1 - alpha)))


def cusum_seg(x, thr, seg, out):
    T, i, _ = cusum_stat(x)
    if T > thr and len(x) >= 4:
        out.append(seg[0] + i + 1)   # change point at global index seg[0]+i+1
        cusum_seg(x[:i + 1], thr, (seg[0], seg[0] + i), out)
        cusum_seg(x[i + 1:], thr, (seg[0] + i + 1, seg[1]), out)


# ------------------------------------------------------------
# main
# ------------------------------------------------------------
def main():
    t0 = time.time()
    fm, p = load_episodes()
    sec = daily_series(fm, 'simple_return_pct')
    prim = daily_series(p, 'return_pct')
    # save daily series (both, stacked)
    sec_ = sec.copy(); sec_['sample'] = 'SECONDARY'
    prim_ = prim.copy(); prim_['sample'] = 'PRIMARY'
    for c in ('mean_mae', 'mean_hold'):
        if c not in prim_.columns:
            prim_[c] = np.nan
    cols = ['sample', 'signal_date'] + [c for c in sec.columns if c != 'signal_date']
    daily = pd.concat([sec_[cols], prim_[cols]], ignore_index=True)
    daily.to_csv(os.path.join(OUT, 'temporal_daily_series.csv'), index=False)
    n_days = len(sec)
    print(f'[LOAD] SECONDARY days={n_days} PRIMARY days={len(prim)} ({time.time()-t0:.0f}s)', flush=True)

    R = sec['mean_return'].to_numpy()
    sign = R > 0
    npos = int(sign.sum()); nneg = int((~sign).sum())

    # ---- runs (Wald-Wolfowitz + empirical) ----
    ww = wald_wolfowitz(sign)
    obs = all_stats(R)
    B = 10_000
    stats_keys = list(obs.keys())
    perms = {k: np.empty(B) for k in stats_keys}
    for b in range(B):
        y = RNG.permutation(R)
        st = all_stats(y)
        for k in stats_keys:
            perms[k][b] = st[k]
    pvals = {}
    for k in stats_keys:
        pv = perms[k]
        if k in ('n_runs', 'mean_abs_diff'):
            pvals[k] = (1 + (pv <= obs[k]).sum()) / (B + 1)   # clustering -> fewer runs / smaller diff
        else:
            pvals[k] = (1 + (pv >= obs[k]).sum()) / (B + 1)   # clustering -> larger
    runs_row = dict(n_signal_days=n_days, n_positive=npos, n_negative=nneg,
                    n_runs=obs['n_runs'], ww_z=ww['z'], ww_p=ww['p'],
                    perm_p_runs=pvals['n_runs'], max_pos_run=obs['max_pos'],
                    max_neg_run=obs['max_neg'], perm_p_maxpos=pvals['max_pos'],
                    perm_p_maxneg=pvals['max_neg'], sum_sq_runs=obs['sum_sq'],
                    perm_p_sumsq=pvals['sum_sq'], mean_abs_diff=obs['mean_abs_diff'],
                    perm_p_mad=pvals['mean_abs_diff'], lag1_acf=obs['lag1_acf'],
                    perm_p_lag1=pvals['lag1_acf'], lag5_acf=obs['lag5_acf'],
                    perm_p_lag5=pvals['lag5_acf'], rv20=obs['rv20'], perm_p_rv20=pvals['rv20'],
                    rv60=obs['rv60'], perm_p_rv60=pvals['rv60'], max_roll_neg_run=obs['max_roll_neg'],
                    perm_p_maxrollneg=pvals['max_roll_neg'])
    pd.DataFrame([runs_row]).to_csv(os.path.join(OUT, 'temporal_runs.csv'), index=False)
    print(f'[RUNS] days={n_days} pos={npos} neg={nneg} runs={obs["n_runs"]} ww_z={ww["z"]:.2f} ww_p={ww["p"]:.4g} '
          f'perm_p_runs={pvals["n_runs"]:.4g} maxpos={obs["max_pos"]} maxneg={obs["max_neg"]} '
          f'lag1={obs["lag1_acf"]:.3f} perm_p_lag1={pvals["lag1_acf"]:.4g}', flush=True)

    # ---- permutation null summary ----
    null_rows = []
    for k in stats_keys:
        pv = perms[k]
        null_rows.append(dict(statistic=k, observed=obs[k], null_mean=float(pv.mean()),
                              null_p50=float(np.percentile(pv, 50)), null_p5=float(np.percentile(pv, 5)),
                              null_p95=float(np.percentile(pv, 95)), null_p1=float(np.percentile(pv, 1)),
                              null_p99=float(np.percentile(pv, 99)),
                              empirical_percentile=float((pv <= obs[k]).mean() * 100),
                              empirical_p=pvals[k]))
    pd.DataFrame(null_rows).to_csv(os.path.join(OUT, 'temporal_permutation_null.csv'), index=False)

    # ---- ACF ----
    lags = [1, 2, 3, 5, 10, 20, 40, 60, 120]
    acf_rows = []
    for name, ser in [('R_mean', R), ('sign', sign.astype(float)), ('win_rate', sec['win_rate'].to_numpy())]:
        for L in lags:
            if len(ser) > L + 2:
                a = float(np.corrcoef(ser[:-L], ser[L:])[0, 1])
            else:
                a = np.nan
            acf_rows.append(dict(series=name, lag=L, acf=a))
    # permutation null ACF for R_mean
    null_acf = {L: [] for L in lags}
    for b in range(2000):
        y = RNG.permutation(R)
        for L in lags:
            if len(y) > L + 2:
                null_acf[L].append(np.corrcoef(y[:-L], y[L:])[0, 1])
    for L in lags:
        nv = np.array(null_acf[L])
        acf_rows.append(dict(series='R_mean_perm', lag=L, acf=np.nan,
                             perm_ci_lo=float(np.percentile(nv, 2.5)),
                             perm_ci_hi=float(np.percentile(nv, 97.5))))
    adf = pd.DataFrame(acf_rows)
    # attach permutation CI to R_mean rows
    for i, row in adf.iterrows():
        if row['series'] == 'R_mean':
            pr = adf[(adf['series'] == 'R_mean_perm') & (adf['lag'] == row['lag'])].iloc[0]
            adf.at[i, 'perm_ci_lo'] = pr['perm_ci_lo']; adf.at[i, 'perm_ci_hi'] = pr['perm_ci_hi']
    adf = adf[adf['series'] != 'R_mean_perm']
    adf.to_csv(os.path.join(OUT, 'temporal_acf.csv'), index=False)
    print('[ACF]', flush=True)
    for L in lags:
        r_ = adf[(adf['series'] == 'R_mean') & (adf['lag'] == L)].iloc[0]
        print(f'   lag{L:>3}: acf={r_["acf"]:.3f}  permCI=[{r_["perm_ci_lo"]:.3f},{r_["perm_ci_hi"]:.3f}]', flush=True)

    # ---- persistence ----
    def cond_series(cond_mask, target_mask):
        return float(target_mask[cond_mask].mean() * 100) if cond_mask.any() else np.nan
    R20 = pd.Series(R).rolling(20).mean().to_numpy()
    fwd5 = np.array([R[t + 1:t + 6].mean() if t + 6 <= len(R) else np.nan for t in range(len(R))])
    fwd20 = np.array([R[t + 1:t + 21].mean() if t + 21 <= len(R) else np.nan for t in range(len(R))])
    m20pos = np.nan_to_num(R20 > 0, nan=False); m20neg = np.nan_to_num(R20 < 0, nan=False)
    f5pos = np.nan_to_num(fwd5 > 0, nan=False); f20neg = np.nan_to_num(fwd20 < 0, nan=False)
    unp_pos = (sign.sum()) / len(R) * 100
    p_pos_given_pos = cond_series(sign, np.roll(sign, -1)) if len(sign) > 1 else np.nan
    p_neg_given_neg = cond_series(~sign, np.roll(~sign, -1))
    p_f5pos_given_m20pos = cond_series(m20pos, f5pos)
    p_f20neg_given_m20neg = cond_series(m20neg, f20neg)
    # permutation null for persistence
    PB = 5000
    npg = np.empty(PB); ngg = np.empty(PB); pf5 = np.empty(PB); pf20 = np.empty(PB)
    for b in range(PB):
        y = RNG.permutation(R)
        sy = y > 0
        r20y = pd.Series(y).rolling(20).mean().to_numpy()
        f5y = np.array([y[t + 1:t + 6].mean() if t + 6 <= len(y) else np.nan for t in range(len(y))])
        f20y = np.array([y[t + 1:t + 21].mean() if t + 21 <= len(y) else np.nan for t in range(len(y))])
        m20py = np.nan_to_num(r20y > 0, nan=False); m20ny = np.nan_to_num(r20y < 0, nan=False)
        f5py = np.nan_to_num(f5y > 0, nan=False); f20ny = np.nan_to_num(f20y < 0, nan=False)
        npg[b] = cond_series(sy, np.roll(sy, -1)) if len(sy) > 1 else np.nan
        ngg[b] = cond_series(~sy, np.roll(~sy, -1))
        pf5[b] = cond_series(m20py, f5py)
        pf20[b] = cond_series(m20ny, f20ny)
    pers_row = dict(unconditional_positive_pct=unp_pos,
                    p_pos_next_given_pos=p_pos_given_pos, perm_null=float(np.nanmean(npg)),
                    perm_p_greater=(1 + (npg >= p_pos_given_pos).sum()) / (PB + 1),
                    p_neg_next_given_neg=p_neg_given_neg, perm_null_neg=float(np.nanmean(ngg)),
                    perm_p_neg_greater=(1 + (ngg >= p_neg_given_neg).sum()) / (PB + 1),
                    p_fwd5pos_given_m20pos=p_f5pos_given_m20pos, perm_null_f5=float(np.nanmean(pf5)),
                    perm_p_f5=(1 + (pf5 >= p_f5pos_given_m20pos).sum()) / (PB + 1),
                    p_fwd20neg_given_m20neg=p_f20neg_given_m20neg, perm_null_f20=float(np.nanmean(pf20)),
                    perm_p_f20=(1 + (pf20 >= p_f20neg_given_m20neg).sum()) / (PB + 1))
    pd.DataFrame([pers_row]).to_csv(os.path.join(OUT, 'temporal_persistence.csv'), index=False)
    print(f'[PERSIST] P(+|+prev)={p_pos_given_pos:.1f}% (null {np.nanmean(npg):.1f}%) ; '
          f'P(5d>0|M20>0)={p_f5pos_given_m20pos:.1f}% (null {np.nanmean(pf5):.1f}%)', flush=True)

    # ---- block variance ratio ----
    block_rows = []
    PB = 5000
    for L in (5, 10, 20, 40, 60, 120):
        nb = len(R) // L
        xb = R[:nb * L].reshape(nb, L)
        bmean = xb.mean(axis=1); bmed = np.median(xb, axis=1)
        bwin = (xb > 0).mean(axis=1) * 100
        obs_var_m = bmean.var(); obs_var_med = bmed.var(); obs_var_win = bwin.var()
        nullm = np.empty(PB); nullmed = np.empty(PB); nullwin = np.empty(PB)
        for b in range(PB):
            y = RNG.permutation(R)[:nb * L].reshape(nb, L)
            bm = y.mean(axis=1); bmed_ = np.median(y, axis=1); bw = (y > 0).mean(axis=1) * 100
            nullm[b] = bm.var(); nullmed[b] = bmed_.var(); nullwin[b] = bw.var()
        block_rows.append(dict(block_len=L, n_blocks=nb,
                               block_mean_var=obs_var_m, perm_null_mean_var=float(nullm.mean()),
                               var_ratio_mean=obs_var_m / float(nullm.mean()),
                               perm_p_mean=(1 + (nullm >= obs_var_m).sum()) / (PB + 1),
                               positive_blocks_pct=(bmean > 0).mean() * 100,
                               negative_blocks_pct=(bmean <= 0).mean() * 100,
                               block_median_var=obs_var_med, var_ratio_median=obs_var_med / float(nullmed.mean()),
                               block_winrate_var=obs_var_win, var_ratio_winrate=obs_var_win / float(nullwin.mean())))
    bdf = pd.DataFrame(block_rows)
    bdf.to_csv(os.path.join(OUT, 'temporal_block_analysis.csv'), index=False)
    print('[BLOCK]', flush=True)
    for _, r in bdf.iterrows():
        print(f'   L={r["block_len"]:>3}: var_ratio={r["var_ratio_mean"]:.2f} perm_p={r["perm_p_mean"]:.4g} '
              f'posblocks={r["positive_blocks_pct"]:.0f}%', flush=True)

    # ---- calendar ----
    dts = pd.to_datetime(sec['signal_date'])
    R_ = pd.Series(R, index=dts)
    mono = pd.DataFrame({'mean_return': R_, 'win_rate': pd.Series(sec['win_rate'].to_numpy(), index=dts)})
    m = mono.groupby([mono.index.year, mono.index.month]).agg(mean_return=('mean_return', 'mean'),
                                                              n_days=('mean_return', 'size'))
    m.index.names = ['year', 'month']; m = m.reset_index()
    m.to_csv(os.path.join(OUT, 'temporal_monthly.csv'), index=False)
    q = mono.groupby([mono.index.year, mono.index.quarter]).agg(mean_return=('mean_return', 'mean'),
                                                                median_return=('mean_return', 'median'),
                                                                n_days=('mean_return', 'size'))
    q.index.names = ['year', 'quarter']; q = q.reset_index()
    q.to_csv(os.path.join(OUT, 'temporal_quarterly.csv'), index=False)
    print('[CALENDAR] monthly/quarterly saved', flush=True)

    # ---- change points ----
    var_R = R.var(ddof=1)
    beta = 2 * var_R * np.log(n_days)          # BIC-style, pre-fixed
    cp_pelt = pelt_mean(R, beta)
    thr = cusum_threshold(R, B=1000, alpha=0.05)
    cp_cusum = []
    cusum_seg(R, thr, (0, len(R)), cp_cusum)
    cp_cusum = sorted(set(cp_cusum))
    seg_rows = []
    bounds = [0] + cp_pelt + [len(R)]
    for i in range(len(bounds) - 1):
        a, b = bounds[i], bounds[i + 1]
        seg = sec.iloc[a:b]
        ep = fm[(fm['signal_date'] >= seg['signal_date'].iloc[0]) & (fm['signal_date'] <= seg['signal_date'].iloc[-1])]
        seg_rows.append(dict(method='PELT', seg_idx=i, start_i=a, end_i=b - 1,
                             start_date=str(sec['signal_date'].iloc[a].date()),
                             end_date=str(sec['signal_date'].iloc[b - 1].date()),
                             n_signal_days=b - a, n_episodes=len(ep),
                             mean_daily_R=float(R[a:b].mean()), median_daily_R=float(np.median(R[a:b])),
                             win_day_pct=float((R[a:b] > 0).mean() * 100),
                             episode_mean_ret=float(ep['simple_return_pct'].mean()),
                             episode_win_pct=float((ep['simple_return_pct'] > 0).mean() * 100),
                             calendar_days=int((pd.to_datetime(sec['signal_date'].iloc[b - 1]) - pd.to_datetime(sec['signal_date'].iloc[a])).days)))
    cp_rows = [dict(method='PELT', change_index=int(k), change_date=str(sec['signal_date'].iloc[k].date())) for k in cp_pelt]
    cp_rows += [dict(method='CUSUM', change_index=int(k), change_date=str(sec['signal_date'].iloc[k].date())) for k in cp_cusum]
    cpdf = pd.DataFrame(cp_rows); cpdf.to_csv(os.path.join(OUT, 'temporal_change_points.csv'), index=False)
    sdf = pd.DataFrame(seg_rows); sdf.to_csv(os.path.join(OUT, 'temporal_segments.csv'), index=False)
    print(f'[CHANGEPOINT] PELT n={len(cp_pelt)} CUSUM n={len(cp_cusum)} beta={beta:.2f} thr={thr:.2f}', flush=True)
    print('  PELT dates:', [str(sec["signal_date"].iloc[k].date()) for k in cp_pelt], flush=True)

    # cluster duration from segments (positive/negative performance segments)
    pos_seg = sdf[sdf['mean_daily_R'] > 0]; neg_seg = sdf[sdf['mean_daily_R'] <= 0]
    seg_dur = pd.DataFrame([
        dict(seg_type='positive', n=len(pos_seg), cal_days_p50=float(pos_seg['calendar_days'].median()) if len(pos_seg) else np.nan,
             cal_days_p75=float(pos_seg['calendar_days'].quantile(.75)) if len(pos_seg) else np.nan,
             cal_days_p90=float(pos_seg['calendar_days'].quantile(.90)) if len(pos_seg) else np.nan,
             cal_days_max=float(pos_seg['calendar_days'].max()) if len(pos_seg) else np.nan,
             sig_days_p50=float(pos_seg['n_signal_days'].median()) if len(pos_seg) else np.nan,
             sig_days_max=float(pos_seg['n_signal_days'].max()) if len(pos_seg) else np.nan,
             mean_neg_seg=None),
        dict(seg_type='negative', n=len(neg_seg), cal_days_p50=float(neg_seg['calendar_days'].median()) if len(neg_seg) else np.nan,
             cal_days_p75=float(neg_seg['calendar_days'].quantile(.75)) if len(neg_seg) else np.nan,
             cal_days_p90=float(neg_seg['calendar_days'].quantile(.90)) if len(neg_seg) else np.nan,
             cal_days_max=float(neg_seg['calendar_days'].max()) if len(neg_seg) else np.nan,
             sig_days_p50=float(neg_seg['n_signal_days'].median()) if len(neg_seg) else np.nan,
             sig_days_max=float(neg_seg['n_signal_days'].max()) if len(neg_seg) else np.nan,
             mean_neg_seg=None)
    ])
    seg_dur.to_csv(os.path.join(OUT, 'temporal_segments_duration.csv'), index=False)

    # ---- effective sample size ----
    ne = neff_estimates(R)
    ne_row = dict(n_episodes=len(fm), n_signal_days=n_days, neff_first_zc=ne['neff_zc'],
                  k_first_zc=ne['k_first_zc'], neff_geyer=ne['neff_geyer'], k_geyer=ne['k_geyer'])
    for L, v in ne['boot'].items():
        ne_row[f'neff_block_{L}'] = v
    pd.DataFrame([ne_row]).to_csv(os.path.join(OUT, 'temporal_effective_sample_size.csv'), index=False)
    print(f'[NEFF] zc={ne["neff_zc"]:.0f} geyer={ne["neff_geyer"]:.0f} '
          f'block10={ne["boot"][10]:.0f} block21={ne["boot"][21]:.0f} block40={ne["boot"][40]:.0f} block60={ne["boot"][60]:.0f}', flush=True)

    # ---- quality drawdowns (Q20 / Q60 < 0) ----
    qd_rows = []
    for w in (20, 60):
        rw = pd.Series(R).rolling(w).mean().to_numpy()
        negm = np.nan_to_num(rw < 0, nan=False)
        rl = run_lengths(negm)
        # find intervals
        d = np.diff(np.concatenate(([0], negm.astype(np.int8), [0])))
        starts = np.flatnonzero(d == 1); ends = np.flatnonzero(d == -1)
        for s_, e_ in zip(starts, ends):
            qd_rows.append(dict(window=w, start_sigday=int(s_), end_sigday=int(e_ - 1),
                                start_date=str(sec['signal_date'].iloc[s_].date()),
                                end_date=str(sec['signal_date'].iloc[max(0, e_ - 1)].date()),
                                n_signal_days=int(e_ - s_),
                                calendar_days=int((pd.to_datetime(sec['signal_date'].iloc[e_ - 1]) - pd.to_datetime(sec['signal_date'].iloc[s_])).days),
                                mean_Q=float(rw[s_:e_].mean()), min_Q=float(rw[s_:e_].min())))
    qdf = pd.DataFrame(qd_rows)
    qdf.to_csv(os.path.join(OUT, 'temporal_quality_drawdowns.csv'), index=False)
    print('[QDRAWDOWN] Q20<0 intervals:', len(qdf[qdf.window == 20]), ' Q60<0 intervals:', len(qdf[qdf.window == 60]), flush=True)
    if len(qdf[qdf.window == 60]):
        m60 = qdf[qdf.window == 60]
        print('   longest Q60<0:', m60.loc[m60['n_signal_days'].idxmax(), ['start_date', 'end_date', 'n_signal_days']].to_dict(), flush=True)

    # ---- cross-sectional synchronization ----
    sec2 = fm.copy()
    sec2['day_ret'] = sec2['simple_return_pct']
    dg = sec2.groupby('signal_date')['day_ret'].agg(win_rate=lambda s: (s > 0).mean() * 100,
                                                    disp=lambda s: s.std(),
                                                    p10=lambda s: s.quantile(.10),
                                                    p50=lambda s: s.quantile(.50),
                                                    p90=lambda s: s.quantile(.90))
    dg = dg.reset_index()
    dg['R_mean'] = sec['mean_return'].to_numpy()
    qs = dg['R_mean'].quantile([.10, .25, .75, .90]).to_dict()
    def bucket(x):
        if x <= qs[.10]: return 'Bottom10'
        if x <= qs[.25]: return '10-25'
        if x <= qs[.75]: return '25-75'
        if x <= qs[.90]: return '75-90'
        return 'Top10'
    dg['bucket'] = dg['R_mean'].apply(bucket)
    cs_rows = []
    for bk, g in dg.groupby('bucket', sort=False):
        ep = sec2.merge(g[['signal_date']], on='signal_date')
        cs_rows.append(dict(bucket=bk, n_days=len(g), n_episodes=len(ep),
                            daily_win_rate=g['win_rate'].mean(), daily_disp=g['disp'].mean(),
                            daily_p10=g['p10'].mean(), daily_p50=g['p50'].mean(), daily_p90=g['p90'].mean(),
                            episode_mae=ep['MAE_intraday_pct'].mean(), episode_hold=ep['hold_days'].mean(),
                            episode_win=ep['day_ret'].gt(0).mean() * 100))
    csdf = pd.DataFrame(cs_rows)
    csdf.to_csv(os.path.join(OUT, 'temporal_crosssection_quality.csv'), index=False)
    print('[CROSSSECTION] buckets:', csdf[['bucket', 'n_days', 'daily_win_rate', 'episode_win']].round(1).to_string(index=False), flush=True)

    # ---- PRIMARY vs SECONDARY ----
    ps = prim.set_index('signal_date')[['mean_return', 'median_return', 'win_rate']].rename(
        columns={'mean_return': 'prim_mean', 'median_return': 'prim_median', 'win_rate': 'prim_win'})
    ss = sec.set_index('signal_date')[['mean_return', 'median_return', 'win_rate', 'n_episodes']].rename(
        columns={'mean_return': 'sec_mean', 'median_return': 'sec_median', 'win_rate': 'sec_win'})
    both = ps.join(ss, how='inner')
    pc = float(both['prim_mean'].corr(both['sec_mean']))
    sp = float(both['prim_mean'].corr(both['sec_mean'], method='spearman'))
    # PRIMARY on SECONDARY bottom-10% days
    thr10 = sec['mean_return'].quantile(.10)
    bad_days = sec[sec['mean_return'] <= thr10]['signal_date']
    prim_bad = prim[prim['signal_date'].isin(bad_days)]['mean_return'].mean()
    prim_other = prim[~prim['signal_date'].isin(bad_days)]['mean_return'].mean()
    psr = dict(n_overlap=len(both), pearson=pc, spearman=sp,
               prim_mean_all=prim['mean_return'].mean(), prim_mean_on_sec_bottom10=prim_bad,
               prim_mean_on_sec_other=prim_other, sec_bottom10_threshold=thr10)
    pd.DataFrame([psr]).to_csv(os.path.join(OUT, 'temporal_primary_secondary.csv'), index=False)
    print(f'[PRI-SEC] overlap={len(both)} pearson={pc:.3f} spearman={sp:.3f} '
          f'prim_on_sec_bottom10={prim_bad:.2f} vs other={prim_other:.2f}', flush=True)

    # ---- leave-one-year-out ----
    lyo_rows = []
    yrs = sorted(sec['signal_date'].dt.year.unique())
    for y in yrs:
        mask = sec['signal_date'].dt.year != y
        Rr = sec.loc[mask, 'mean_return'].to_numpy()
        sr_ = Rr > 0
        ww_ = wald_wolfowitz(sr_)
        a1 = float(np.corrcoef(Rr[:-1], Rr[1:])[0, 1]) if len(Rr) > 3 else np.nan
        L = 20; nb = len(Rr) // L
        obs_v = Rr[:nb * L].reshape(nb, L).mean(axis=1).var()
        PB = 1000; nv = np.empty(PB)
        for b in range(PB):
            yy = RNG.permutation(Rr)[:nb * L].reshape(nb, L)
            nv[b] = yy.mean(axis=1).var()
        vr = obs_v / float(nv.mean()); pv = (1 + (nv >= obs_v).sum()) / (PB + 1)
        var_Rr = Rr.var(ddof=1)
        beta_y = 2 * var_Rr * np.log(len(Rr))
        ncp = len(pelt_mean(Rr, beta_y))
        rp_ = run_lengths(sr_); rn_ = run_lengths(~sr_)
        lyo_rows.append(dict(dropped_year=int(y), n_days=len(Rr), n_runs=ww_['runs'],
                             ww_z=ww_['z'], lag1_acf=a1, block20_var_ratio=vr,
                             block20_perm_p=pv, pelt_changepoints=ncp,
                             max_pos_run=int(rp_.max()) if len(rp_) else 0,
                             max_neg_run=int(rn_.max()) if len(rn_) else 0))
    lyo = pd.DataFrame(lyo_rows)
    lyo.to_csv(os.path.join(OUT, 'temporal_leave_one_year_out.csv'), index=False)
    print('[LYO]', flush=True)
    print(lyo.round(3).to_string(index=False), flush=True)

    # ------------------------------------------------------------
    # figures
    # ------------------------------------------------------------
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    plt.rcParams.update({'figure.dpi': 110, 'savefig.bbox': 'tight'})
    dts_all = pd.to_datetime(sec['signal_date'])
    Rs = pd.Series(R, index=dts_all)

    # 1) daily series + rolling
    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.plot(dts_all, R, color='#999', lw=.6, label='daily mean return')
    for w, c in [(20, '#1f77b4'), (60, '#d62728'), (120, '#2ca02c')]:
        ax.plot(dts_all, Rs.rolling(w).mean(), color=c, lw=1.4, label=f'{w}-day rolling')
    ax.axhline(0, color='k', lw=.8)
    ax.set_ylabel('signal-day mean final return %'); ax.legend(ncol=4, fontsize=9)
    ax.set_title('SECONDARY daily signal return series (no regime coloring)')
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 'daily_signal_return_series.png')); plt.close(fig)

    # 2) ACF
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))
    for ax, (name, ser) in zip(axes, [('R_mean', R), ('sign', sign.astype(float)),
                                      ('win_rate', sec['win_rate'].to_numpy())]):
        av = [np.corrcoef(ser[:-L], ser[L:])[0, 1] for L in lags]
        ax.axhline(0, color='k', lw=.8)
        ax.plot(lags, av, 'o-')
        pm = adf[(adf['series'] == 'R_mean')]
        if name == 'R_mean':
            lo = pm['perm_ci_lo'].to_numpy(); hi = pm['perm_ci_hi'].to_numpy()
            ax.fill_between(lags, lo, hi, alpha=.15, color='C1', label='perm 95% CI')
        ax.set_xlabel('lag'); ax.set_ylabel('ACF'); ax.set_title(name); ax.grid(alpha=.3)
        if name == 'R_mean':
            ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 'temporal_acf.png')); plt.close(fig)

    # 3) runs: null distributions with observed
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))
    for ax, (k, lab) in zip(axes, [('n_runs', 'number of runs'), ('max_pos', 'max positive run'),
                                   ('max_neg', 'max negative run')]):
        pv = perms[k]
        ax.hist(pv, bins=60, alpha=.7, color='#7f7f7f')
        ax.axvline(obs[k], color='#d62728', lw=2, label=f'observed={obs[k]}')
        ax.set_xlabel(lab); ax.set_ylabel('perm count'); ax.legend(fontsize=8); ax.grid(alpha=.3)
    fig.suptitle('Permutation null (10,000) vs observed', y=1.02)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 'temporal_runs.png')); plt.close(fig)

    # 4) block variance ratio
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.axhline(1, color='k', lw=.8, label='null ratio=1')
    ax.plot(bdf['block_len'], bdf['var_ratio_mean'], 'o-', label='mean var ratio')
    ax.plot(bdf['block_len'], bdf['var_ratio_winrate'], 's--', label='win-rate var ratio')
    ax.set_xscale('log'); ax.set_xticks(bdf['block_len']); ax.set_xticklabels(bdf['block_len'])
    ax.set_xlabel('block length (signal days)'); ax.set_ylabel('var ratio observed/perm')
    ax.legend(); ax.grid(alpha=.3); ax.set_title('Block-mean dispersion vs permutation')
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 'temporal_block_variance.png')); plt.close(fig)

    # 5) monthly heatmap
    piv = m.pivot(index='year', columns='month', values='mean_return').reindex(
        columns=range(1, 13), index=range(2020, 2027))
    fig, ax = plt.subplots(figsize=(11, 4.2))
    im = ax.imshow(piv.values, aspect='auto', cmap='RdBu_r', vmin=-8, vmax=8)
    ax.set_xticks(range(12)); ax.set_xticklabels(range(1, 13))
    ax.set_yticks(range(len(piv))); ax.set_yticklabels(piv.index)
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            v = piv.values[i, j]
            if not np.isnan(v):
                ax.text(j, i, f'{v:.1f}', ha='center', va='center', fontsize=7)
    ax.set_title('Monthly mean signal-day return (%)'); fig.colorbar(im, ax=ax)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 'monthly_strategy_quality_heatmap.png')); plt.close(fig)

    # 6) quarterly
    fig, ax = plt.subplots(figsize=(11, 3.6))
    qlab = [f"{int(r['year'])}Q{int(r['quarter'])}" for _, r in q.iterrows()]
    cols = ['#2ca02c' if v > 0 else '#d62728' for v in q['mean_return']]
    ax.bar(range(len(q)), q['mean_return'], color=cols)
    ax.axhline(0, color='k', lw=.8)
    ax.set_xticks(range(len(q))); ax.set_xticklabels(qlab, rotation=90, fontsize=7)
    ax.set_ylabel('mean signal-day return %'); ax.set_title('Quarterly strategy quality')
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 'quarterly_strategy_return.png')); plt.close(fig)

    # 7) change points
    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.plot(dts_all, R, color='#999', lw=.6)
    for _, r in sdf.iterrows():
        a = pd.to_datetime(r['start_date']); b = pd.to_datetime(r['end_date'])
        ax.hlines(r['mean_daily_R'], a, b, color='#1f77b4', lw=2.2)
    for _, r in cpdf[cpdf['method'] == 'PELT'].iterrows():
        ax.axvline(pd.to_datetime(r['change_date']), color='#d62728', lw=1.2, ls='--')
    ax.axhline(0, color='k', lw=.8)
    ax.set_ylabel('signal-day mean return %'); ax.set_title('PELT performance segments (BIC penalty)')
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 'temporal_change_points.png')); plt.close(fig)

    # 8) quality drawdowns
    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.plot(dts_all, Rs.rolling(20).mean(), color='#1f77b4', lw=1.1, label='Q20')
    ax.plot(dts_all, Rs.rolling(60).mean(), color='#d62728', lw=1.1, label='Q60')
    for _, r in qdf[qdf['window'] == 20].iterrows():
        a = pd.to_datetime(r['start_date']); b = pd.to_datetime(r['end_date'])
        ax.axvspan(a, b, color='#d62728', alpha=.15)
    ax.axhline(0, color='k', lw=.8)
    ax.set_ylabel('rolling mean return %'); ax.legend(); ax.set_title('Q20/Q60 quality drawdowns (Q<0 shaded)')
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 'temporal_quality_drawdowns.png')); plt.close(fig)

    # 9) primary-secondary
    fig, ax = plt.subplots(figsize=(12, 4.2))
    ax.plot(dts_all, R, color='#999', lw=.6, label='SECONDARY')
    ax.plot(pd.to_datetime(prim['signal_date']), prim['mean_return'], color='#1f77b4', lw=1.0, label='PRIMARY (Top10)')
    ax.axhline(0, color='k', lw=.8)
    ax.legend(); ax.set_ylabel('signal-day mean return %'); ax.set_title('PRIMARY vs SECONDARY daily outcomes')
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 'primary_secondary_temporal_compare.png')); plt.close(fig)

    print(f'DONE in {time.time()-t0:.0f}s', flush=True)


if __name__ == '__main__':
    main()
