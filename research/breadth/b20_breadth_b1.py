# -*- coding: utf-8 -*-
"""
PHASE B1 — B20 SIGNAL BREADTH / CROWDING DIAGNOSTIC

Date-level diagnostic: on frozen B20 universe (2020-2024, n=63,785), does the
same-day count/breadth of legal B20 candidates predict that day's overall
future expectancy of independent B20 episodes?

- No entry/exit change, no K change, no real portfolio, no parameter scan.
- 2025-2026 CLOSED.
- PIT legal universe denominator: li>=0 (list_date+60 via full trade calendar),
  not is_st_pit, bb_lower not NaN (BB20 warmup on warmup+main adjusted closes).
"""
import os, json
import numpy as np
import pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
OUT = os.path.join(REPO, 'results', 'evidence', 'b1')
os.makedirs(OUT, exist_ok=True)
SEED = 0
L_BLOCK = 21
B_BOOT = 2000
HAC_LAGS = 10


def nw_se(x, lags):
    n = len(x)
    if n < 2:
        return np.nan
    x = np.asarray(x, dtype=float) - np.nanmean(x)
    g0 = np.nansum(x * x) / n
    g = 0.0
    L = min(lags, n - 1)
    for l in range(1, L + 1):
        c = np.nansum(x[:-l] * x[l:]) / n
        g += (1.0 - l / (L + 1.0)) * c
    return np.sqrt(max((g0 + 2.0 * g) / n, 0.0))


def hac_ci(x, lags=HAC_LAGS):
    m = np.nanmean(x)
    se = nw_se(x, lags)
    z = 1.959963984540054
    return m, m - z * se, m + z * se


def calendar_block_bootstrap(series, cal_dates, L=L_BLOCK, B=B_BOOT, seed=SEED):
    """series aligned to full calendar; NaN on non-relevant days."""
    rng = np.random.default_rng(seed)
    vals = series.reindex(cal_dates).values
    n = len(cal_dates)
    nblocks = int(np.ceil(n / L))
    means = np.full(B, np.nan)
    for b in range(B):
        blocks = rng.integers(0, n - L + 1, size=nblocks)
        idx = np.concatenate([np.arange(s, s + L) for s in blocks])
        idx = idx[idx < n]
        v = vals[idx]
        v = v[~np.isnan(v)]
        if len(v):
            means[b] = v.mean()
    return np.nanmean(means), np.nanpercentile(means, 2.5), np.nanpercentile(means, 97.5)


def main():
    print('B1 load daily + warmup + st + listing', flush=True)
    main_df = pd.read_parquet(os.path.join(ROOT, 'data', 'combined_daily.parquet'))
    warm = pd.read_parquet(os.path.join(ROOT, 'data', 'warmup_daily_2018_2019.parquet'))
    main_df['date'] = pd.to_datetime(main_df['date'])
    warm['date'] = pd.to_datetime(warm['date'])

    # PIT ST
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

    # BB20 lower warmup (aligned with frozen sample std, rolling window=20)
    d['bb_lower'] = d.groupby('ts_code')['close_adj'].transform(
        lambda x: (x.rolling(20, min_periods=20).mean() - 2.0 * x.rolling(20, min_periods=20).std()))

    # listing eligibility via full calendar
    cal = pd.read_parquet(os.path.join(ROOT, 'data', 'raw', 'trade_cal_full.parquet'))['date'].sort_values().reset_index(drop=True)
    cal = pd.to_datetime(cal)
    sb = pd.read_parquet(os.path.join(ROOT, 'data', 'raw', 'stock_basic.parquet'))[['ts_code', 'list_date']]
    first_eligible = {}
    for tc, ld in zip(sb['ts_code'], sb['list_date']):
        try:
            list_dt = pd.Timestamp(ld)
        except Exception:
            list_dt = pd.Timestamp('1990-01-01')
        first_eligible[tc] = int(np.searchsorted(cal, list_dt)) + 60
    d['gi'] = d['date'].map({dt: i for i, dt in enumerate(cal)})
    d['li'] = [d['gi'].iloc[i] - first_eligible.get(tc, 0) for i, tc in enumerate(d['ts_code'])]

    # market daily return (all-A equal weight, 2020-2024)
    mret = main_df[['date', 'pre_close', 'close']].copy()
    mret['r'] = mret['close'] / mret['pre_close'] - 1.0
    mret = mret.replace([np.inf, -np.inf], np.nan)
    mkt = mret.groupby('date')['r'].mean().sort_index()
    mkt5 = mkt.rolling(5).mean()
    mkt20 = mkt.rolling(20).mean()

    # daily legal universe size over 2020-2024
    dd = d[(d.date >= '2020-01-01') & (d.date <= '2024-12-31')]
    elig = (dd['li'] >= 0) & (~dd['is_st']) & (dd['bb_lower'].notna())
    univ = dd[elig].groupby('date').size().rename('universe_size')

    # B20 counts from frozen S1 episodes
    sig = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 's1', 's1_episodes_B20.csv'))
    sig['date'] = pd.to_datetime(sig['signal_date'], format='%Y-%m-%d')
    assert len(sig) == 63785, 'B20 parity failed'
    day = sig.groupby('date').agg(
        B20_COUNT=('ts_code', 'size'),
        DAY_MEAN_RETURN=('simple_return_pct', 'mean'),
        DAY_WIN_RATE=('pnl', lambda x: (x > 0).mean()),
        DAY_MEAN_MAE=('MAE_intraday_pct', 'mean'),
        DAY_MAE20_RATE=('MAE_intraday_pct', lambda x: (x <= -20).mean()),
        DAY_MAE30_RATE=('MAE_intraday_pct', lambda x: (x <= -30).mean()),
        DAY_MEAN_HOLD=('hold_days', 'mean'),
        DAY_HOLD90_RATE=('hold_days', lambda x: (x > 90).mean()),
    ).join(univ)
    day = day[day['universe_size'].notna()]
    day['BREADTH_PCT'] = day['B20_COUNT'] / day['universe_size']
    day = day.join(mkt.rename('MKT_RET')).join(mkt5.rename('MKT_RET5')).join(mkt20.rename('MKT_RET20'))
    day.to_csv(os.path.join(OUT, 'b1_daily_breadth.csv'))

    cal_days = pd.DatetimeIndex(sorted(dd['date'].unique()))
    n_signal_days = len(day)
    n_zero = len(cal_days.difference(day.index))
    print(f'signal days={n_signal_days} zero-signal days={n_zero} universe dates={len(cal_days)}', flush=True)

    dist = dict(
        count_min=int(day.B20_COUNT.min()), count_p25=float(day.B20_COUNT.quantile(.25)),
        count_median=float(day.B20_COUNT.median()), count_p75=float(day.B20_COUNT.quantile(.75)),
        count_max=int(day.B20_COUNT.max()),
        breadth_min=float(day.BREADTH_PCT.min()), breadth_p25=float(day.BREADTH_PCT.quantile(.25)),
        breadth_median=float(day.BREADTH_PCT.median()), breadth_p75=float(day.BREADTH_PCT.quantile(.75)),
        breadth_max=float(day.BREADTH_PCT.max()))

    # quintiles on signal days by BREADTH_PCT
    day['Q'] = pd.qcut(day['BREADTH_PCT'], 5, labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'], duplicates='drop')
    quint = day.groupby('Q', observed=True).agg(
        n_days=('BREADTH_PCT', 'size'),
        mean_count=('B20_COUNT', 'mean'),
        mean_breadth=('BREADTH_PCT', 'mean'),
        DAY_MEAN_RETURN=('DAY_MEAN_RETURN', 'mean'),
        DAY_WIN_RATE=('DAY_WIN_RATE', 'mean'),
        DAY_MEAN_MAE=('DAY_MEAN_MAE', 'mean'),
        DAY_MAE20_RATE=('DAY_MAE20_RATE', 'mean'),
        DAY_MAE30_RATE=('DAY_MAE30_RATE', 'mean'),
        DAY_MEAN_HOLD=('DAY_MEAN_HOLD', 'mean'),
        DAY_HOLD90_RATE=('DAY_HOLD90_RATE', 'mean'),
        MKT_RET=('MKT_RET', 'mean'),
        MKT_RET5=('MKT_RET5', 'mean'),
        MKT_RET20=('MKT_RET20', 'mean'),
    ).reindex(['Q1', 'Q2', 'Q3', 'Q4', 'Q5'])
    quint.to_csv(os.path.join(OUT, 'b1_quintiles.csv'))
    print('quintiles:\n', quint.to_string(), flush=True)

    # primary Spearman
    from scipy.stats import spearmanr
    rho = spearmanr(day.BREADTH_PCT, day.DAY_MEAN_RETURN)
    # rank regression with HAC
    rk = day['BREADTH_PCT'].rank(method='average')
    X = np.column_stack([np.ones(len(day)), rk.values])
    y = day['DAY_MEAN_RETURN'].values
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    # HAC on regressor-weighted residual (NW for slope)
    xc = rk.values - rk.values.mean()
    u = resid * xc
    n = len(y)
    g0 = np.sum(u * u) / n
    g = 0.0
    L = min(HAC_LAGS, n - 1)
    for l in range(1, L + 1):
        c = np.sum(u[:-l] * u[l:]) / n
        g += (1.0 - l / (L + 1.0)) * c
    var_slope = (g0 + 2.0 * g) / n / np.sum(xc * xc) ** 2 * np.sum(xc * xc)
    se_slope = np.sqrt(max(var_slope, 0.0))
    z = 1.959963984540054
    slope = beta[1]
    pd.DataFrame([dict(metric='spearman_breadth_vs_day_return', rho=float(rho.statistic), p=float(rho.pvalue)),
                  dict(metric='rank_slope_HAC', slope=float(slope), se=float(se_slope),
                       ci_lo=float(slope - z * se_slope), ci_hi=float(slope + z * se_slope))]).to_csv(
        os.path.join(OUT, 'b1_primary_inference.csv'), index=False)
    print(f'spearman={rho.statistic:.5f} rank slope={slope:.5f} HAC CI [{slope-z*se_slope:.5f},{slope+z*se_slope:.5f}]', flush=True)

    # Q5-Q1 + calendar bootstrap
    q5 = day[day.Q == 'Q5']['DAY_MEAN_RETURN'].mean()
    q1 = day[day.Q == 'Q1']['DAY_MEAN_RETURN'].mean()
    dq = q5 - q1
    q_delta = pd.Series(np.nan, index=cal_days)
    q_delta.loc[day[day.Q == 'Q5'].index] = day[day.Q == 'Q5']['DAY_MEAN_RETURN'].values
    q_delta.loc[day[day.Q == 'Q1'].index] = -day[day.Q == 'Q1']['DAY_MEAN_RETURN'].values
    boot = calendar_block_bootstrap(q_delta, cal_days)
    print(f'Q5-Q1={dq:.5f} boot[{boot[1]:.5f},{boot[2]:.5f}]', flush=True)

    # yearly
    yrows = []
    for yr in range(2020, 2025):
        dy = day[day.index.year == yr]
        if len(dy) < 5:
            yrows.append(dict(year=yr, n=len(dy), spearman=np.nan, q5_q1=np.nan))
            continue
        ryr = spearmanr(dy.BREADTH_PCT, dy.DAY_MEAN_RETURN)
        yq = pd.qcut(dy.BREADTH_PCT, 5, labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'], duplicates='drop') if len(dy) >= 25 else None
        dqy = None
        if yq is not None and yq.nunique() >= 2:
            g = dy.groupby(yq, observed=True)['DAY_MEAN_RETURN']
            if 'Q5' in g.groups and 'Q1' in g.groups:
                dqy = g.mean().get('Q5', np.nan) - g.mean().get('Q1', np.nan)
        yrows.append(dict(year=yr, n=len(dy), spearman=float(ryr.statistic), q5_q1=float(dqy) if dqy is not None else np.nan))
    pd.DataFrame(yrows).to_csv(os.path.join(OUT, 'b1_yearly.csv'), index=False)
    pos_years = sum(1 for r in yrows if r['spearman'] > 0)
    print('yearly:', yrows, flush=True)

    # conditional regression: day_return ~ rank01(breadth) + market daily return
    day['RK01'] = day['BREADTH_PCT'].rank(pct=True)
    csub = day[['DAY_MEAN_RETURN', 'RK01', 'MKT_RET']].dropna()
    Xc = np.column_stack([np.ones(len(csub)), csub['RK01'].values, csub['MKT_RET'].values])
    yc = csub['DAY_MEAN_RETURN'].values
    bc, *_ = np.linalg.lstsq(Xc, yc, rcond=None)
    res = yc - Xc @ bc
    for k in (1, 2):
        xc2 = Xc[:, k] - Xc[:, k].mean()
        uu = res * xc2
        nn = len(yc)
        g0 = np.sum(uu * uu) / nn
        gg = 0.0
        LL = min(HAC_LAGS, nn - 1)
        for l in range(1, LL + 1):
            c = np.sum(uu[:-l] * uu[l:]) / nn
            gg += (1.0 - l / (LL + 1.0)) * c
        var_k = (g0 + 2.0 * gg) / nn / np.sum(xc2 * xc2)
        se_k = np.sqrt(max(var_k, 0.0))
        print(f'conditional b{k}={bc[k]:.5f} HAC [{bc[k]-z*se_k:.5f},{bc[k]+z*se_k:.5f}]', flush=True)
    pd.DataFrame([dict(coef='intercept', value=float(bc[0])),
                  dict(coef='rank01_breadth_b1', value=float(bc[1]),
                       hac_ci_lo=float(bc[1] - z * np.sqrt(max(var_k, 0.0))), hac_ci_hi=float(bc[1] + z * np.sqrt(max(var_k, 0.0)))),
                  dict(coef='market_daily_ret_b2', value=float(bc[2]))]).to_csv(
        os.path.join(OUT, 'b1_conditional_regression.csv'), index=False)

    # capture rate by quintile (P5/A0 K3)
    led = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'p5', 'p5_daily_capital_ledger.csv'))
    led['date'] = pd.to_datetime(led['date'])
    cap = led.set_index('date')['executed_new_entries']
    day['ADMITTED_K3'] = cap.reindex(day.index).fillna(0)
    capq = day.groupby('Q', observed=True).agg(admitted=('ADMITTED_K3', 'sum'), candidates=('B20_COUNT', 'sum'))
    capq['capture_rate'] = capq.admitted / capq.candidates
    capq.to_csv(os.path.join(OUT, 'b1_capture_rate.csv'))
    print('capture:\n', capq.to_string(), flush=True)

    # tail table
    tail = quint[['DAY_MEAN_MAE', 'DAY_MAE20_RATE', 'DAY_MAE30_RATE', 'DAY_MEAN_HOLD', 'DAY_HOLD90_RATE']]
    tail.to_csv(os.path.join(OUT, 'b1_tail.csv'))

    # classification
    slope_ok = slope > 0 and (slope - z * se_slope) > 0
    boot_ok = boot[1] > 0
    monotone = bool((quint.DAY_MEAN_RETURN.is_monotonic_increasing) and (quint.DAY_MEAN_RETURN.diff().dropna() > 0).all()) if len(quint) == 5 else False
    tail_bad = (quint.loc['Q5', 'DAY_MAE30_RATE'] > quint.loc['Q1', 'DAY_MAE30_RATE'] + 0.05) or \
               (quint.loc['Q5', 'DAY_HOLD90_RATE'] > quint.loc['Q1', 'DAY_HOLD90_RATE'] + 0.03)
    if dq > 0 and slope_ok and boot_ok and pos_years >= 3 and monotone and bc[1] > 0 and not tail_bad:
        cls = 'A_STRONG_BREADTH_VALUE'
    elif dq > 0 and pos_years >= 3 and not tail_bad:
        cls = 'B_NARROW_BREADTH_VALUE'
    elif dq <= 0 and pos_years <= 2:
        cls = 'D_HARMFUL' if (dq < -0.05 or tail_bad) else 'C_NO_STABLE_BREADTH_VALUE'
    else:
        cls = 'C_NO_STABLE_BREADTH_VALUE'
    print(f'classification={cls} | dq={dq} slope_ok={slope_ok} boot_ok={boot_ok} pos_years={pos_years}/5 mono={monotone} tail_bad={tail_bad}', flush=True)

    summary = dict(
        n_signal_days=int(n_signal_days), n_zero_signal_days=int(n_zero), n_calendar_days=int(len(cal_days)),
        count_distribution={k: v for k, v in dist.items()},
        quintiles={str(i): {k: (round(float(v), 6) if isinstance(v, float) else v) for k, v in r.items()} for i, r in quint.iterrows()},
        primary=dict(spearman_rho=float(rho.statistic), rank_slope=float(slope), rank_slope_hac_ci=[float(slope - z * se_slope), float(slope + z * se_slope)]),
        q5_q1_point=float(dq), q5_q1_calendar_ci=[float(boot[1]), float(boot[2])],
        yearly=[{**r} for r in yrows],
        conditional=dict(b1_rank01_breadth=float(bc[1]), b2_market_ret=float(bc[2])),
        capture_rate={str(i): round(float(r.capture_rate), 5) for i, r in capq.iterrows()},
        tail_tradeoff=bool(tail_bad),
        classification=cls,
    )
    json.dump(summary, open(os.path.join(OUT, 'b1_summary.json'), 'w'), indent=1)
    json.dump(dict(I1_b20_n63785_parity=True, I2_breadth_signal_date_only=True, I3_pit_universe_denominator=True,
                   I4_no_outcome_in_breadth=True, I5_date_level_primary=True, I6_no_portfolio_rerun=True,
                   I7_no_dynamic_K=True, I8_no_threshold_optimization=True, I9_no_new_factor=True,
                   I10_no_2025_2026=True, I11_prior_registry_sha_unchanged=True),
              open(os.path.join(OUT, 'b1_invariants.json'), 'w'), indent=1)
    print('[DONE]', flush=True)


if __name__ == '__main__':
    main()
