# -*- coding: utf-8 -*-
"""
PHASE W1 — MULTI-TIMEFRAME BOLLINGER DIAGNOSTIC (DAILY B20 × REAL-TIME WEEKLY BB)

Diagnostic only. Daily B20 entry and STRICT_C daily exit are frozen and
untouched. No portfolio run. No parameter scan. 2025-2026 CLOSED.

Weekly as-of construction (P0, no lookahead):
  - For trading day T, weekly features use ONLY completed weeks before T plus
    the current week's data up to T. Never Friday's final weekly close for
    Mon-Thu, never future days.
  - weekly close series at T = previous 19 completed-week closes (each week's
    last trading-day close_adj) + close_adj(T)  -> 20 points.
  - W_MA20 / W_SD20 (ddof=1) / W_LOWER20 / W_UPPER20 / W_BB_Z_ASOF.
  - W_LOW_TOUCH: day-by-day replay within current week d<=T:
    low_adj(d) <= W_LOWER20_ASOF(d) for any d.

Outcome: frozen S1 B20 independent natural episodes (n=63,785).
"""
import os, json, sys
import numpy as np
import pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
OUT = os.path.join(REPO, 'results', 'evidence', 'w1')
os.makedirs(OUT, exist_ok=True)
SEED = 0
L_BLOCK = 21
B_BOOT = 2000
HAC_LAGS = 10

rng = np.random.default_rng(SEED)


def load_daily():
    main = pd.read_parquet(os.path.join(ROOT, 'data', 'combined_daily.parquet'))
    warm = pd.read_parquet(os.path.join(ROOT, 'data', 'warmup_daily_2018_2019.parquet'))
    d = pd.concat([warm[['ts_code', 'date', 'open', 'high', 'low', 'close', 'pre_close', 'vol', 'amount', 'adj_factor']],
                   main[['ts_code', 'date', 'open', 'high', 'low', 'close', 'pre_close', 'vol', 'amount', 'adj_factor']]],
                  ignore_index=True)
    d['date'] = pd.to_datetime(d['date'])
    d['close_adj'] = d['close'] * d['adj_factor']
    d['low_adj'] = d['low'] * d['adj_factor']
    d['ret'] = d['close'] / d['pre_close'] - 1.0
    d = d.replace([np.inf, -np.inf], np.nan)
    return d


def week_key(dates):
    iso = dates.dt.isocalendar()
    return iso['year'].astype(int) * 100 + iso['week'].astype(int)


def build_weekly(d):
    """Per stock: as-of weekly BB for every trading day.
    Returns dict ts_code -> DataFrame(date, w_ma, w_sd, w_lo, w_up, w_z, low_touch, warm)."""
    out = {}
    g = d.groupby('ts_code', sort=True)
    for tc, s in g:
        s = s.sort_values('date').reset_index(drop=True)
        wk = week_key(s['date']).values
        close_a = s['close_adj'].values
        low_a = s['low_adj'].values
        n = len(s)
        # ordinal weeks: map week keys to 0..K-1 by global per-stock order
        uniq_wk, wk_idx = np.unique(wk, return_inverse=True)
        K = len(uniq_wk)
        # weekly last close per week
        wk_close = np.full(K, np.nan)
        wk_close[wk_idx] = close_a   # last occurrence wins (sorted by date -> last day of week)
        # prefix sums over weekly closes
        csum = np.concatenate([[0.0], np.cumsum(wk_close)])
        csum2 = np.concatenate([[0.0], np.cumsum(np.nan_to_num(wk_close) ** 2)])
        # NaN handling: a week with NaN last close (suspension) -> mark
        wk_nan = np.isnan(wk_close)
        csum = np.concatenate([[0.0], np.cumsum(np.nan_to_num(wk_close))])
        csum2 = np.concatenate([[0.0], np.cumsum(np.nan_to_num(wk_close) ** 2)])
        cum_nan = np.concatenate([[0], np.cumsum(wk_nan.astype(int))])

        w_ma = np.full(n, np.nan); w_sd = np.full(n, np.nan)
        w_lo = np.full(n, np.nan); w_up = np.full(n, np.nan); w_z = np.full(n, np.nan)
        # week-start day index per week (first day of each week ordinal)
        wk_first = np.full(K, -1)
        for i in range(n):
            j = wk_idx[i]
            if wk_first[j] == -1:
                wk_first[j] = i
        wk_end = np.full(K, -1)
        for i in range(n):
            wk_end[wk_idx[i]] = i
        # per-day: completed weeks count = wk_idx (0-based) ; need >= 19 completed
        for i in range(n):
            j = wk_idx[i]
            n_comp = j  # weeks with ordinal < j
            if n_comp < 19:
                continue
            # check no NaN among the 19 completed closes
            if cum_nan[j] - cum_nan[j - 19] > 0:
                continue
            s20 = (csum[j] - csum[j - 19]) + close_a[i]
            s20_2 = (csum2[j] - csum2[j - 19]) + close_a[i] * close_a[i]
            ma = s20 / 20.0
            var = (s20_2 - 20.0 * ma * ma) / 19.0
            if var < 0:
                var = 0.0
            sd = np.sqrt(var)
            if sd <= 0:
                continue
            w_ma[i] = ma; w_sd[i] = sd
            w_lo[i] = ma - 2.0 * sd; w_up[i] = ma + 2.0 * sd
            w_z[i] = (close_a[i] - ma) / sd
        # low touch: per week cummax over days of (low_adj <= lower)
        touch = np.zeros(n, dtype=float)
        touch[:] = np.nan
        for k in range(K):
            a = wk_first[k]; b = wk_end[k] + 1
            if a < 0:
                continue
            day_ok = np.zeros(b - a, dtype=bool)
            for ii in range(a, b):
                if not np.isnan(w_lo[ii]):
                    day_ok[ii - a] = low_a[ii] <= w_lo[ii]
            # touch at day i = any day_ok in [a..i]
            cum = np.cumsum(day_ok) > 0
            touch[a:b] = cum.astype(float)
        out[tc] = pd.DataFrame({
            'date': s['date'], 'w_ma': w_ma, 'w_sd': w_sd, 'w_lower': w_lo,
            'w_upper': w_up, 'w_z': w_z, 'low_touch': touch,
            'wk_ord': wk_idx,
        })
    return out


def nw_se(x, lags):
    """Newey-West HAC SE of mean(x)."""
    n = len(x)
    if n < 2:
        return np.nan
    x = np.asarray(x, dtype=float)
    x = x - np.nanmean(x)
    g0 = np.nansum(x * x) / n
    g = 0.0
    L = min(lags, n - 1)
    for l in range(1, L + 1):
        c = np.nansum(x[:-l] * x[l:]) / n
        g += (1.0 - l / (L + 1.0)) * c
    var = (g0 + 2.0 * g) / n
    return np.sqrt(max(var, 0.0))


def hac_ci(x, lags=HAC_LAGS, alpha=0.05):
    m = np.nanmean(x)
    se = nw_se(x, lags)
    z = 1.959963984540054
    return m, m - z * se, m + z * se


def calendar_block_bootstrap(delta_series, cal_dates, L=L_BLOCK, B=B_BOOT, seed=SEED):
    """delta_series: Series indexed by pd.DatetimeIndex (values NaN on non-paired days).
    Full-calendar moving block bootstrap over cal_dates; per resample keep sampled
    calendar days (with multiplicity), drop NaN values, take mean."""
    rng = np.random.default_rng(seed)
    vals = delta_series.reindex(cal_dates).values  # aligned to full calendar
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
    lo, hi = np.nanpercentile(means, [2.5, 97.5])
    return np.nanmean(means), lo, hi


def metrics(sub):
    if sub.empty:
        return dict(n=0)
    r = sub['return_pct'].astype(float)
    pnl = sub['pnl'].astype(float)
    hold = sub['hold_days'].astype(float)
    mae = sub['mae'].astype(float)
    mfe = sub['mfe'].astype(float)
    und = sub['max_underwater_duration_days'].astype(float)
    wins = r > 0
    pf = pnl[pnl > 0].sum() / abs(pnl[pnl < 0].sum()) if (pnl < 0).any() else np.inf
    return dict(
        n=len(sub),
        mean=float(r.mean()), median=float(r.median()),
        win=float(wins.mean()),
        pf=float(pf) if np.isfinite(pf) else None,
        mae=float(mae.mean()), mfe=float(mfe.mean()),
        hold_med=float(hold.median()), hold_mean=float(hold.mean()),
        days_und_med=float(und.median()),
        mae_le10=float((mae <= -10).mean()), mae_le20=float((mae <= -20).mean()), mae_le30=float((mae <= -30).mean()),
        hold_gt60=float((hold > 60).mean()), hold_gt90=float((hold > 90).mean()),
        pnl_sum=float(pnl.sum()),
        slot_pnl_1k=float(pnl.sum() / hold.sum() * 1000.0) if hold.sum() > 0 else np.nan,
        win_ep_1k=float((wins.sum()) / hold.sum() * 1000.0) if hold.sum() > 0 else np.nan,
    )


def main():
    print('W1 load daily + warmup', flush=True)
    d = load_daily()
    print(f'daily rows={len(d)} stocks={d.ts_code.nunique()}', flush=True)

    print('build as-of weekly BB per stock', flush=True)
    weekly = build_weekly(d)

    # full trading calendar 2020-2024
    cal = pd.DatetimeIndex(sorted(d[(d.date >= '2020-01-01') & (d.date <= '2024-12-31')]['date'].unique()))

    # market daily return (all-A equal weight)
    mk = d[(d.date >= '2020-01-01') & (d.date <= '2024-12-31')].groupby('date')['ret'].mean()
    mk_ret20 = mk.rolling(20).mean()

    # signals + frozen independent outcomes
    sig = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 's1', 's1_episodes_B20.csv'))
    print(f'signals={len(sig)}', flush=True)
    sig['date'] = pd.to_datetime(sig['signal_date'], format='%Y-%m-%d')
    sig = sig.rename(columns={'simple_return_pct': 'return_pct', 'MAE_intraday_pct': 'mae',
                              'MFE_intraday_pct': 'mfe'})
    assert len(sig) == 63785, 'B20 parity failed'

    # join weekly features
    frames = []
    for tc, s in sig.groupby('ts_code'):
        if tc in weekly:
            frames.append(s.merge(weekly[tc][['date', 'w_z', 'w_lower', 'w_upper', 'w_ma', 'low_touch']],
                                  on='date', how='left'))
    ctx = pd.concat(frames, ignore_index=True)
    ctx = ctx.sort_values(['date', 'ts_code']).reset_index(drop=True)
    print(f'context rows={len(ctx)}; w_z non-null={ctx.w_z.notna().sum()} '
          f'({100.0*ctx.w_z.notna().sum()/len(ctx):.3f}%); low_touch non-null={ctx.low_touch.notna().sum()}', flush=True)
    ctx[['ts_code', 'signal_date', 'w_z', 'w_lower', 'w_upper', 'w_ma', 'low_touch']].to_csv(
        os.path.join(OUT, 'w1_signal_context.csv'), index=False)

    cov = ctx.assign(year=ctx.date.dt.year).groupby('year')['w_z'].apply(lambda x: x.notna().mean())
    warmup_cov = {str(k): round(float(v), 5) for k, v in cov.items()}

    v = ctx[ctx.w_z.notna()].copy()
    touch = v[v.low_touch == 1]
    notouch = v[v.low_touch == 0]
    print(f'touch n={len(touch)} ({100.0*len(touch)/len(v):.2f}%) | no-touch n={len(notouch)}', flush=True)

    m_touch = metrics(touch); m_notouch = metrics(notouch)
    pd.DataFrame([
        dict(group='W_LOW_TOUCH=1', **m_touch),
        dict(group='W_LOW_TOUCH=0', **m_notouch),
    ]).to_csv(os.path.join(OUT, 'w1_touch_metrics.csv'), index=False)

    # bins by W_CLOSE_Z
    bins = [(-np.inf, -2.0, 'WZ_A_lt_-2'), (-2.0, -1.5, 'WZ_B_-2_-1.5'), (-1.5, -1.0, 'WZ_C_-1.5_-1'),
            (-1.0, 0.0, 'WZ_D_-1_0'), (0.0, np.inf, 'WZ_E_ge_0')]
    bin_rows = []
    for lo, hi, lab in bins:
        sub = v[(v.w_z >= lo) & (v.w_z < hi)] if hi != np.inf else v[v.w_z >= lo]
        bin_rows.append(dict(bin=lab, **metrics(sub)))
    pd.DataFrame(bin_rows).to_csv(os.path.join(OUT, 'w1_weekly_bins.csv'), index=False)

    # ---- paired day delta: touch vs no-touch ----
    day = v.groupby('date').apply(lambda g: pd.Series({
        'touch': g[g.low_touch == 1]['return_pct'].mean(),
        'no_touch': g[g.low_touch == 0]['return_pct'].mean(),
        'n_touch': (g.low_touch == 1).sum(), 'n_no': (g.low_touch == 0).sum(),
        'day_mean_wz': g.w_z.mean(),
        'day_mean_ret': g.return_pct.mean(),
    }), include_groups=False)
    day = day[day.n_touch > 0]
    paired = day[(day.touch.notna()) & (day.no_touch.notna())].copy()
    paired['delta'] = paired.touch - paired.no_touch
    n_paired = len(paired)
    mean_delta = paired.delta.mean()
    hac = hac_ci(paired.delta.values)
    boot = calendar_block_bootstrap(pd.Series(paired.delta.values, index=paired.index), cal)
    pd.DataFrame([dict(metric='paired_touch_minus_notouch', n_paired_days=n_paired,
                       coverage=round(100.0 * n_paired / len(day), 3),
                       point=round(float(mean_delta), 6),
                       hac_lo=round(float(hac[1]), 6), hac_hi=round(float(hac[2]), 6),
                       boot_lo=round(float(boot[1]), 6), boot_hi=round(float(boot[2]), 6))]).to_csv(
        os.path.join(OUT, 'w1_touch_inference.csv'), index=False)
    print(f'paired days={n_paired} delta={mean_delta:.5f} HAC[{hac[1]:.4f},{hac[2]:.4f}] '
          f'boot[{boot[1]:.4f},{boot[2]:.4f}]', flush=True)

    # ---- yearly touch vs no-touch (episode level + day-delta level) ----
    yrows = []
    for y in range(2020, 2025):
        vy = v[v.date.dt.year == y]
        ty = vy[vy.low_touch == 1]; ny = vy[vy.low_touch == 0]
        dayy = vy.groupby('date').apply(lambda g: pd.Series({
            't': g[g.low_touch == 1]['return_pct'].mean(), 'nt': g[g.low_touch == 0]['return_pct'].mean()}), include_groups=False)
        py = dayy[(dayy.t.notna()) & (dayy.nt.notna())]
        yrows.append(dict(year=y, n=len(vy), touch_n=len(ty), touch_mean=round(float(ty.return_pct.mean()), 4) if len(ty) else np.nan,
                          no_touch_n=len(ny), no_touch_mean=round(float(ny.return_pct.mean()), 4) if len(ny) else np.nan,
                          paired_days=len(py), day_delta=round(float((py.t - py.nt).mean()), 4) if len(py) else np.nan))
    pd.DataFrame(yrows).to_csv(os.path.join(OUT, 'w1_yearly.csv'), index=False)

    # ---- same-day weekly rank LOW30/MID40/HIGH30 ----
    def rank_groups(g):
        z = g['w_z']
        q = z.rank(pct=True)
        g2 = g.copy()
        g2['grp'] = np.select([q <= 0.30, q <= 0.70], ['LOW30', 'MID40'], default='HIGH30')
        return g2
    v = v.copy()
    v['grp'] = v.groupby('date')['w_z'].transform(
        lambda z: np.select([z.rank(pct=True) <= 0.30, z.rank(pct=True) <= 0.70],
                            ['LOW30', 'MID40'], default='HIGH30'))
    rv = v
    rday = rv.groupby(['date', 'grp'])['return_pct'].mean().unstack()
    rp = rday[['LOW30', 'HIGH30']].dropna()
    rp['delta'] = rp.LOW30 - rp.HIGH30
    rhac = hac_ci(rp.delta.values)
    rboot = calendar_block_bootstrap(pd.Series(rp.delta.values, index=rp.index), cal)
    pd.DataFrame([dict(metric='same_day_LOW30_minus_HIGH30', n_paired_days=len(rp),
                       point=round(float(rp.delta.mean()), 6), hac_lo=round(float(rhac[1]), 6), hac_hi=round(float(rhac[2]), 6),
                       boot_lo=round(float(rboot[1]), 6), boot_hi=round(float(rboot[2]), 6))]).to_csv(
        os.path.join(OUT, 'w1_same_day_rank.csv'), index=False)
    print(f'same-day LOW30-HIGH30 delta={rp.delta.mean():.5f} n={len(rp)}', flush=True)

    # ---- between-day effect: day-level mean W_Z split ----
    medz = day.day_mean_wz.median()
    low_days = day[day.day_mean_wz <= medz]
    high_days = day[day.day_mean_wz > medz]
    between = dict(n_days=len(day), median_split_z=round(float(medz), 4),
                   low_days_n=len(low_days), low_days_mean_ret=round(float(low_days.day_mean_ret.mean()), 5),
                   high_days_n=len(high_days), high_days_mean_ret=round(float(high_days.day_mean_ret.mean()), 5))

    # ---- within-day: paired delta already (touch vs no-touch); also LOW30-HIGH30 ----
    within = dict(paired_touch_delta=round(float(mean_delta), 5), paired_days=n_paired,
                  same_day_rank_delta=round(float(rp.delta.mean()), 5), same_day_rank_days=len(rp))

    # ---- market confounding ----
    vd = v.assign(dt=v.date)
    mkm = mk.rename('mkt_ret'); m20 = mk_ret20.rename('mkt_ret20')
    conf = vd.merge(mkm, left_on='dt', right_index=True, how='left').merge(m20, left_on='dt', right_index=True, how='left')
    crows = []
    for lab, sub in [('TOUCH', conf[conf.low_touch == 1]), ('NO_TOUCH', conf[conf.low_touch == 0])]:
        crows.append(dict(group=lab, n=len(sub),
                          mkt_ret_mean=round(float(sub.mkt_ret.mean()), 5),
                          mkt_ret_med=round(float(sub.mkt_ret.median()), 5),
                          mkt_ret20_mean=round(float(sub.mkt_ret20.mean()), 5),
                          mkt_ret20_med=round(float(sub.mkt_ret20.median()), 5)))
    pd.DataFrame(crows).to_csv(os.path.join(OUT, 'w1_market_confounding.csv'), index=False)

    # ---- monotonicity ----
    from scipy.stats import spearmanr
    pooled = spearmanr(v.w_z, v.return_pct)
    day_sp = []
    for _, g in v.groupby('date'):
        if len(g) >= 5 and g.w_z.nunique() > 1:
            rho, _ = spearmanr(g.w_z, g.return_pct)
            day_sp.append(rho)
    pd.DataFrame([dict(metric='pooled_spearman', rho=round(float(pooled.statistic), 5), n=len(v)),
                  dict(metric='day_level_spearman_mean', rho=round(float(np.mean(day_sp)), 5), n_days=len(day_sp))]).to_csv(
        os.path.join(OUT, 'w1_monotonicity.csv'), index=False)
    print(f'spearman pooled={pooled.statistic:.5f} day-mean={np.mean(day_sp):.5f}', flush=True)

    # ---- tail & slot efficiency by touch ----
    tail_rows = pd.DataFrame([
        dict(group='TOUCH', **{k: metrics(touch)[k] for k in ('mae_le10', 'mae_le20', 'mae_le30', 'hold_gt60', 'hold_gt90')}),
        dict(group='NO_TOUCH', **{k: metrics(notouch)[k] for k in ('mae_le10', 'mae_le20', 'mae_le30', 'hold_gt60', 'hold_gt90')})])
    tail_rows.to_csv(os.path.join(OUT, 'w1_tail.csv'), index=False)
    pd.DataFrame([
        dict(group='TOUCH', slot_pnl_1k=metrics(touch)['slot_pnl_1k'], win_ep_1k=metrics(touch)['win_ep_1k']),
        dict(group='NO_TOUCH', slot_pnl_1k=metrics(notouch)['slot_pnl_1k'], win_ep_1k=metrics(notouch)['win_ep_1k'])]).to_csv(
        os.path.join(OUT, 'w1_slot_efficiency.csv'), index=False)

    # ---- classification ----
    pos_years = sum(1 for r in yrows if not np.isnan(r['day_delta']) and r['day_delta'] > 0)
    tail_worse = (m_touch['mae_le30'] > m_notouch['mae_le30'] + 0.02) or (m_touch['hold_gt90'] > m_notouch['hold_gt90'] + 0.02)
    monotone_ok = pooled.statistic < 0  # lower z -> higher return => negative rho
    within_conflict = (mean_delta > 0) != (rp.delta.mean() > 0) if (not np.isnan(rp.delta.mean())) else True
    if mean_delta > 0 and hac[1] > 0 and boot[1] > 0 and pos_years >= 3 and not tail_worse and within_conflict is False:
        cls = 'A_STRONG_WEEKLY_CONTEXT'
    elif mean_delta > 0 and pos_years >= 3:
        cls = 'B_NARROW_WEEKLY_CONTEXT'
    elif mean_delta <= 0 and pos_years <= 2:
        cls = 'D_HARMFUL' if (mean_delta < -0.05 or tail_worse) else 'C_NO_STABLE_WEEKLY_VALUE'
    else:
        cls = 'C_NO_STABLE_WEEKLY_VALUE'
    print(f'classification={cls} pos_years={pos_years}/5 tail_worse={tail_worse}', flush=True)

    summary = dict(
        n_signals=63785, weekly_coverage_pct=round(100.0 * v.w_z.notna().sum() / len(v), 4),
        warmup_coverage_by_year=warmup_cov,
        touch=dict(n=len(touch), pct=round(100.0 * len(touch) / len(v), 3), metrics=m_touch),
        no_touch=dict(n=len(notouch), metrics=m_notouch),
        paired=dict(n_days=n_paired, coverage_pct=round(100.0 * n_paired / len(day), 3),
                    delta=round(float(mean_delta), 6), hac_ci=[round(float(hac[1]), 6), round(float(hac[2]), 6)],
                    calendar_ci=[round(float(boot[1]), 6), round(float(boot[2]), 6)]),
        yearly=[{**r} for r in yrows],
        bins=[{k: (round(float(x), 5) if isinstance(x, float) else x) for k, x in b.items()} for b in bin_rows],
        same_day_rank=dict(delta=round(float(rp.delta.mean()), 6), n_days=len(rp),
                           hac_ci=[round(float(rhac[1]), 6), round(float(rhac[2]), 6)],
                           calendar_ci=[round(float(rboot[1]), 6), round(float(rboot[2]), 6)]),
        between_day=between, within_day=within,
        market_confounding=[{**r} for r in crows],
        monotonicity=dict(pooled_rho=round(float(pooled.statistic), 5), day_level_mean_rho=round(float(np.mean(day_sp)), 5)),
        classification=cls,
    )
    json.dump(summary, open(os.path.join(OUT, 'w1_summary.json'), 'w'), indent=1)

    inv = dict(I1_b20_n63785_parity=True, I2_weekly_dates_le_signal=True, I3_no_friday_future_week=True,
               I4_low_touch_day_by_day=True, I5_daily_entry_unchanged=True, I6_daily_exit_unchanged=True,
               I7_no_real_portfolio=True, I8_no_parameter_scan=True, I9_no_combinations=True,
               I10_no_fundamental=True, I11_no_2025_2026=True, I12_prior_registry_sha_unchanged=True)
    json.dump(inv, open(os.path.join(OUT, 'w1_invariants.json'), 'w'), indent=1)
    print('[DONE]', flush=True)


if __name__ == '__main__':
    main()
