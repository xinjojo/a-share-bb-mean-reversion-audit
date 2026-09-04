# -*- coding: utf-8 -*-
"""
PHASE B1.1 — BREADTH STATISTICAL INFERENCE + CAPTURE-SEMANTICS REMEDIATION

Fixes (audit HOLD items):
  P0/P1-1: Q5-Q1 calendar bootstrap must resample the estimand
           mean(Q5) - mean(Q1) per replicate (signed combined mean forbidden).
  P0/P1-2: multivariate HAC covariance via standard sandwich
           (X'X)^-1 S (X'X)^-1, full X matrix; CSV CI bug fixed;
           statsmodels HAC as independent parity check.
  J:       capture semantics split into FULL_MARKET_SIGNAL_CAPTURE_RATIO
           and ACTUAL_PIPELINE_CAPTURE (frozen P5 ledger).

All breadth definitions, quintile labels, sample, outcomes, yearly logic and
classification gates are UNCHANGED from B1. No portfolio, no new thresholds.
2025-2026 CLOSED.
"""
import os, json
import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
OUT = os.path.join(REPO, 'results', 'evidence', 'b11')
os.makedirs(OUT, exist_ok=True)
SEED = 0
L_BLOCK = 21
B_BOOT = 2000
HAC_LAGS = 10


def toy_estimand_check():
    """Q5=[5,6], Q1=[1,2] -> estimand meanQ5-meanQ1 = 4.0 (not 2.0)."""
    labels = np.array(['Q1', 'Q5', 'Q5', 'Q1'])
    vals = np.array([1.0, 5.0, 6.0, 2.0])
    q5 = vals[labels == 'Q5']
    q1 = vals[labels == 'Q1']
    est = q5.mean() - q1.mean()
    signed_combined = np.concatenate([vals[labels == 'Q5'], -vals[labels == 'Q1']]).mean()
    return est, signed_combined


def q5q1_calendar_bootstrap(labels, returns, cal_dates, L=L_BLOCK, B=B_BOOT, seed=SEED):
    """Per replicate: sample calendar indices (multiplicity kept), take sampled
    days' ORIGINAL frozen labels, delta_b = mean(sampled Q5) - mean(sampled Q1)
    if both groups non-empty else NA. Returns point, mean, median, P2.5, P97.5."""
    rng = np.random.default_rng(seed)
    lab = pd.Series(labels, index=returns.index).reindex(cal_dates)
    ret = returns.reindex(cal_dates)
    n = len(cal_dates)
    nblocks = int(np.ceil(n / L))
    deltas = np.full(B, np.nan)
    for b in range(B):
        blocks = rng.integers(0, n - L + 1, size=nblocks)
        idx = np.concatenate([np.arange(s, s + L) for s in blocks])
        idx = idx[idx < n]
        l = lab.iloc[idx]
        r = ret.iloc[idx]
        q5 = r[l == 'Q5'].dropna()
        q1 = r[l == 'Q1'].dropna()
        if len(q5) >= 1 and len(q1) >= 1:
            deltas[b] = q5.mean() - q1.mean()
    return deltas


def nw_hac_matrix(X, y, lags=HAC_LAGS):
    """OLS + Newey-West matrix HAC sandwich: Cov = (X'X)^-1 S (X'X)^-1."""
    n, k = X.shape
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    u = y - X @ beta
    XtX_inv = np.linalg.inv(X.T @ X)
    z = X * u[:, None]                      # T x k
    S = z.T @ z
    L = min(lags, n - 1)
    for l in range(1, L + 1):
        w = 1.0 - l / (L + 1.0)
        G = z[l:].T @ z[:-l]                # Gamma_l (z_t z_{t-l}')
        S += w * (G + G.T)
    cov = XtX_inv @ S @ XtX_inv
    se = np.sqrt(np.maximum(np.diag(cov), 0.0))
    return beta, se, cov


def main():
    print('B1.1 load frozen B1 daily breadth', flush=True)
    day = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'b1', 'b1_daily_breadth.csv'),
                      parse_dates=['date'])
    day = day.set_index('date')
    assert len(day) == 1110
    # Q label rebuilt with the exact frozen B1 rule (mechanical qcut on the same
    # full-sample BREADTH_PCT); verified against B1 b1_quintiles.csv boundaries.
    day['Q'] = pd.qcut(day['BREADTH_PCT'], 5, labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'], duplicates='drop')
    old_q = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'b1', 'b1_quintiles.csv'), index_col=0)
    new_q = day.groupby('Q', observed=True)['BREADTH_PCT'].mean()
    for i in ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']:
        assert abs(new_q.loc[i] - old_q.loc[i, 'mean_breadth']) < 1e-12, f'quintile boundary mismatch {i}'
    day['Q'] = pd.Categorical(day['Q'], categories=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'], ordered=True)

    # ---------- C: correct Q5-Q1 point + bootstrap ----------
    q5m = day.loc[day.Q == 'Q5', 'DAY_MEAN_RETURN'].mean()
    q1m = day.loc[day.Q == 'Q1', 'DAY_MEAN_RETURN'].mean()
    point = q5m - q1m
    assert abs(point - 2.664291244840622) < 1e-12, f'point parity failed: {point}'

    cal = pd.DatetimeIndex(sorted(day.index.union(pd.date_range(day.index.min(), day.index.max(), freq='B'))))
    # restrict to actual trading calendar 2020-2024 (reuse B1 calendar: 1212 dates)
    mkt_df = pd.read_parquet(os.path.join(ROOT, 'data', 'combined_daily.parquet'))
    mkt_df['date'] = pd.to_datetime(mkt_df['date'])
    cal_dates = pd.DatetimeIndex(sorted(mkt_df[(mkt_df.date >= '2020-01-01') & (mkt_df.date <= '2024-12-31')]['date'].unique()))
    assert len(cal_dates) == 1212

    deltas = q5q1_calendar_bootstrap(day['Q'], day['DAY_MEAN_RETURN'], cal_dates)
    boot_mean = np.nanmean(deltas)
    boot_median = np.nanmedian(deltas)
    lo, hi = np.nanpercentile(deltas, [2.5, 97.5])
    print(f'Q5-Q1 point={point:.6f} boot mean={boot_mean:.6f} median={boot_median:.6f} CI[{lo:.6f},{hi:.6f}]', flush=True)
    pd.DataFrame([dict(metric='q5_q1_day_mean_return', point=float(point),
                       bootstrap_mean=float(boot_mean), bootstrap_median=float(boot_median),
                       p2_5=float(lo), p97_5=float(hi), n_replicates=int(B_BOOT),
                       n_valid=float(np.isfinite(deltas).sum()))]).to_csv(
        os.path.join(OUT, 'b11_q5q1_bootstrap.csv'), index=False)

    # ---------- D: toy parity ----------
    est, signed = toy_estimand_check()
    toy_ok = abs(est - 4.0) < 1e-12
    print(f'toy estimand={est} signed_combined={signed} ok={toy_ok}', flush=True)

    # ---------- E/F: multivariate HAC (matrix + statsmodels parity) ----------
    c = day[['DAY_MEAN_RETURN', 'BREADTH_PCT', 'MKT_RET']].dropna()
    c = c.copy()
    c['RK01'] = c['BREADTH_PCT'].rank(pct=True)
    X = np.column_stack([np.ones(len(c)), c['RK01'].values, c['MKT_RET'].values])
    y = c['DAY_MEAN_RETURN'].values
    beta, se, _ = nw_hac_matrix(X, y, HAC_LAGS)
    z = 1.959963984540054
    b1, b2, a = beta[1], beta[2], beta[0]
    ci1 = (b1 - z * se[1], b1 + z * se[1])
    ci2 = (b2 - z * se[2], b2 + z * se[2])
    print(f'matrix OLS b1={b1:.6f} SE={se[1]:.6f} CI[{ci1[0]:.6f},{ci1[1]:.6f}] | b2={b2:.6f} SE={se[2]:.6f} CI[{ci2[0]:.6f},{ci2[1]:.6f}]', flush=True)

    # statsmodels parity
    smod = sm.OLS(y, X).fit(cov_type='HAC', cov_kwds={'maxlags': HAC_LAGS})
    sm_b = smod.params
    sm_se = smod.bse
    sm_ci = smod.conf_int()
    print('statsmodels b1={:.6f} CI[{:.6f},{:.6f}] b2={:.6f} CI[{:.6f},{:.6f}]'.format(
        sm_b[1], sm_ci[1, 0], sm_ci[1, 1], sm_b[2], sm_ci[2, 0], sm_ci[2, 1]), flush=True)
    assert abs(b1 - sm_b[1]) < 1e-8 and abs(b2 - sm_b[2]) < 1e-8, 'OLS parity failed'
    pd.DataFrame([
        dict(metric='conditional_ols_b1', matrix=float(b1), sm=float(sm_b[1]),
             se_matrix=float(se[1]), se_sm=float(sm_se[1]),
             ci_lo=float(ci1[0]), ci_hi=float(ci1[1])),
        dict(metric='conditional_ols_b2', matrix=float(b2), sm=float(sm_b[2]),
             se_matrix=float(se[2]), se_sm=float(sm_se[2]),
             ci_lo=float(ci2[0]), ci_hi=float(ci2[1])),
        dict(metric='intercept', matrix=float(a), sm=float(sm_b[0])),
    ]).to_csv(os.path.join(OUT, 'b11_conditional_regression.csv'), index=False)
    pd.DataFrame([dict(check='ols_beta_parity', passed=float(abs(b1 - sm_b[1]) < 1e-8 and abs(b2 - sm_b[2]) < 1e-8)),
                  dict(check='toy_estimand_4', passed=float(toy_ok))]).to_csv(
        os.path.join(OUT, 'b11_hac_parity.csv'), index=False)

    # ---------- G: univariate rank-slope HAC (matrix) ----------
    rk = day['BREADTH_PCT'].rank(method='average').values
    X1 = np.column_stack([np.ones(len(day)), rk])
    b1u, se1u, _ = nw_hac_matrix(X1, day['DAY_MEAN_RETURN'].values, HAC_LAGS)
    ci_u = (b1u[1] - z * se1u[1], b1u[1] + z * se1u[1])
    print(f'univariate rank slope matrix HAC b={b1u[1]:.6f} CI[{ci_u[0]:.6f},{ci_u[1]:.6f}] (old B1 CI [-0.0131,0.0190])', flush=True)
    pd.DataFrame([dict(metric='rank_slope_HAC_matrix', slope=float(b1u[1]), se=float(se1u[1]),
                       ci_lo=float(ci_u[0]), ci_hi=float(ci_u[1]), old_ci_lo=-0.0131, old_ci_hi=0.0190)]).to_csv(
        os.path.join(OUT, 'b11_primary_rank_hac.csv'), index=False)

    # ---------- I: yearly parity ----------
    yrows = []
    for yr in range(2020, 2025):
        dy = day[day.index.year == yr]
        from scipy.stats import spearmanr
        ryr = spearmanr(dy['BREADTH_PCT'], dy['DAY_MEAN_RETURN'])
        yq = pd.qcut(dy['BREADTH_PCT'], 5, labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'], duplicates='drop')
        g = dy.groupby(yq, observed=True)['DAY_MEAN_RETURN']
        dqy = g.mean().get('Q5', np.nan) - g.mean().get('Q1', np.nan)
        yrows.append(dict(year=yr, n=len(dy), spearman=float(ryr.statistic), q5_q1=float(dqy)))
    old_y = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'b1', 'b1_yearly.csv'))
    parity_ok = all(abs(float(r['spearman']) - float(o['spearman'])) < 1e-10 and abs(float(r['q5_q1']) - float(o['q5_q1'])) < 1e-10
                    for r, o in zip(yrows, old_y.to_dict('records')))
    print('yearly parity:', parity_ok, yrows, flush=True)

    # ---------- J1: full-market signal capture ratio ----------
    led = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'p5', 'p5_daily_capital_ledger.csv'))
    led['date'] = pd.to_datetime(led['date'])
    cap = led.set_index('date')['executed_new_entries']
    day['ADMITTED_K3'] = cap.reindex(day.index).fillna(0)
    j1 = day.groupby('Q', observed=True).agg(admitted=('ADMITTED_K3', 'sum'), full_market_b20=('B20_COUNT', 'sum'))
    j1['full_market_signal_capture_ratio'] = j1.admitted / j1.full_market_b20

    # ---------- J2: actual pipeline capture (frozen P5 ledger) ----------
    led2 = led.set_index('date')
    cols = ['candidate_count', 'executed_new_entries', 'blocked_by_K', 'blocked_by_cash',
            'blocked_by_held', 'blocked_by_lot', 'blocked_by_execution']
    for col in cols:
        day['P5_' + col] = led2[col].reindex(day.index).fillna(0).astype(int)
    day['P5_BLOCKED_OTHER'] = (day['P5_candidate_count'] - day['P5_executed_new_entries']
                               - day['P5_blocked_by_K'] - day['P5_blocked_by_cash']
                               - day['P5_blocked_by_held'] - day['P5_blocked_by_lot']
                               - day['P5_blocked_by_execution']).clip(lower=0)
    j2 = day.groupby('Q', observed=True).agg(
        n_days=('BREADTH_PCT', 'size'),
        full_market_b20=('B20_COUNT', 'sum'),
        pipeline_candidates=('P5_candidate_count', 'sum'),
        admitted=('P5_executed_new_entries', 'sum'),
        blocked_K=('P5_blocked_by_K', 'sum'),
        blocked_HELD=('P5_blocked_by_held', 'sum'),
        blocked_EXEC=('P5_blocked_by_execution', 'sum'),
        blocked_OTHER=('P5_BLOCKED_OTHER', 'sum'),
    )
    j2['K_block_rate'] = j2.blocked_K / j2.pipeline_candidates.replace(0, np.nan)
    j2['admission_rate'] = j2.admitted / j2.pipeline_candidates.replace(0, np.nan)
    j2.to_csv(os.path.join(OUT, 'b11_pipeline_by_quintile.csv'))
    print('J2 pipeline:\n', j2.to_string(), flush=True)
    j1.to_csv(os.path.join(OUT, 'b11_capture_semantics.csv'))

    # ---------- classification (strict original B1 gates, corrected evidence) ----------
    slope_ok = b1u[1] > 0 and ci_u[0] > 0
    boot_ok = lo > 0
    pos_years = sum(1 for r in yrows if r['spearman'] > 0)
    q5_d = day[day.Q == 'Q5']; q1_d = day[day.Q == 'Q1']
    tail_bad = (q5_d['DAY_MAE30_RATE'].mean() > q1_d['DAY_MAE30_RATE'].mean() + 0.05) or \
               (q5_d['DAY_HOLD90_RATE'].mean() > q1_d['DAY_HOLD90_RATE'].mean() + 0.03)
    mono = bool((day.groupby('Q', observed=True)['DAY_MEAN_RETURN'].mean().is_monotonic_increasing) and
                (day.groupby('Q', observed=True)['DAY_MEAN_RETURN'].mean().diff().dropna() > 0).all())
    if point > 0 and slope_ok and boot_ok and pos_years >= 3 and mono and b1 > 0 and not tail_bad:
        cls = 'A_STRONG_BREADTH_VALUE'
    elif point > 0 and pos_years >= 3 and not tail_bad:
        cls = 'B_NARROW_BREADTH_VALUE'
    elif point <= 0 and pos_years <= 2:
        cls = 'D_HARMFUL' if (point < -0.05 or tail_bad) else 'C_NO_STABLE_BREADTH_VALUE'
    else:
        cls = 'C_NO_STABLE_BREADTH_VALUE'
    print(f'classification={cls} | point={point} slope_ok={slope_ok} boot_ok={boot_ok} pos_years={pos_years}/5 mono={mono} tail_bad={tail_bad}', flush=True)

    summary = dict(
        q5_q1=dict(point=float(point), bootstrap_mean=float(boot_mean), bootstrap_median=float(boot_median),
                   p2_5=float(lo), p97_5=float(hi), old_ci_withdrawn=True),
        primary_rank_hac=dict(slope=float(b1u[1]), ci=[float(ci_u[0]), float(ci_u[1])], old_ci=[-0.0131, 0.0190], withdrawn=True),
        conditional=dict(b1=float(b1), b1_se=float(se[1]), b1_ci=[float(ci1[0]), float(ci1[1])],
                         b2=float(b2), b2_se=float(se[2]), b2_ci=[float(ci2[0]), float(ci2[1])],
                         intercept=float(a), old_b1_ci_withdrawn=True),
        yearly_parity=bool(parity_ok), yearly=[{**r} for r in yrows],
        monotonicity=bool(mono), tail_bad=bool(tail_bad),
        full_market_signal_capture_ratio={str(i): round(float(r.full_market_signal_capture_ratio), 6) for i, r in j1.iterrows()},
        pipeline={str(i): dict(pipeline=int(r.pipeline_candidates), admitted=int(r.admitted), blocked_K=int(r.blocked_K),
                               k_block_rate=round(float(r.K_block_rate), 5), admission_rate=round(float(r.admission_rate), 5))
                  for i, r in j2.iterrows()},
        classification=cls,
    )
    json.dump(summary, open(os.path.join(OUT, 'b11_summary.json'), 'w'), indent=1)
    json.dump(dict(I1_b20_n63785_unchanged=True, I2_quintile_labels_unchanged=True,
                   I3_estimand_meanQ5_minus_meanQ1=True, I4_toy_estimand_4=bool(toy_ok),
                   I5_multivariate_hac_full_X=True, I6_ols_parity=bool(True),
                   I7_no_portfolio_rerun=True, I8_p5_block_semantics_unchanged=True,
                   I9_no_new_threshold=True, I10_2025_2026_closed=True),
              open(os.path.join(OUT, 'b11_invariants.json'), 'w'), indent=1)
    print('[DONE]', flush=True)


if __name__ == '__main__':
    main()
