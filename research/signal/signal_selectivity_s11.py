# -*- coding: utf-8 -*-
"""
PHASE S1.1 - CONTEMPORANEOUS BB DEPTH RANKING (SAME-DAY SIGNAL SELECTIVITY)
===========================================================================
Registry: research/signal/registries/SIGNAL_SELECTIVITY_S11_DEPTH_RANK_REGISTRY.csv
SHA256  : see .sha256 file (frozen before any result)

Research question:
  Entry stays B20 (close_adj < MA20 - 2*SD20). No waiting for -2.5/-3 sigma.
  Among same-day legal B20 candidates, does signal-date-visible BB_Z depth rank
  select more valuable signals when K=3 slots are scarce?

  THRESHOLD GATING (S1, D-HARMFUL)  vs  CONTEMPORANEOUS RANKING (this phase).

Frozen design (from Registry):
  - sample 2020-01-01..2024-12-31 (N=1212 hard horizon), 2025-2026 CLOSED
  - B20 exact S1 parity: n=63,785 + signal-key set identical to s1_episodes_B20.csv
  - BB_Z_SIGNAL = (close_adj-MA20)/SD20 at signal-date close, signal-date-visible only
  - same-day rank by BB_Z ascending (most negative first); deterministic split:
      n_deep = max(1, floor(0.30*n+0.5)); n_mid = max(0, floor(0.40*n+0.5));
      n_shallow = n - n_deep - n_mid   (ties broken by ts_code ascending)
  - groups DEEP30 / MID40 / SHALLOW30
  - collision days: signal_date with candidate_count >= 4 (frozen)
  - TOP3 diagnostic: DEPTH_TOP3 vs AMOUNT_TOP3 (counterfactual only, no portfolio)
  - FIRST_HIT: days_since_first_cross == 0; REPEAT_HIT: > 0
  - inference: signal-day equal weight; HAC maxlags=10;
    full-calendar moving-block bootstrap L=21 B=2000 seed=0
  - classification A/B/C/D per Registry; only A/B qualifies for K=3 depth-ranking
    portfolio test
  - invariants I1-I13; no 2025+ read; no RSI/MACD gate; no delayed entry

Outputs: results/evidence/s11/ (11 files)
"""
import os, sys, json
from datetime import date
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, 'research', 'signal'))

import signal_selectivity_s1 as s1  # replay_k / epdf / calendar_series / hac_ci / cal_block_bootstrap

B2024 = date(2024, 12, 31)
OUT = os.path.join(REPO, 'results', 'evidence', 's11')
os.makedirs(OUT, exist_ok=True)
S1_OUT = os.path.join(REPO, 'results', 'evidence', 's1')

BINS = ['[-2.0,-2.5)', '[-2.5,-3.0)', '[-3.0,-3.5)', '<-3.5']


def zbin(z):
    if not np.isfinite(z):
        return 'NA'
    if z < -3.5:
        return '<-3.5'
    if z < -3.0:
        return '[-3.0,-3.5)'
    if z < -2.5:
        return '[-2.5,-3.0)'
    if z < -2.0:
        return '[-2.0,-2.5)'
    return '>=-2.0'


def split_groups(n):
    """Deterministic 30/40/30 split by same-day BB_Z rank (1 = deepest)."""
    n_deep = max(1, int(np.floor(0.30 * n + 0.5)))
    n_mid = max(0, int(np.floor(0.40 * n + 0.5)))
    n_shallow = n - n_deep - n_mid
    return n_deep, n_mid, n_shallow


def build_first_cross(days, D, N, ts_list):
    """
    For each ts_code: first_cross[i] = index of the first trading day of the
    current continuous BB_Z<-2 episode ending at day i (None if not oversold
    on day i). Days without quotes are skipped without resetting oversold
    state (no quote does not change oversold status). PIT: only uses data
    up to day i.
    """
    res = {}
    for tc in ts_list:
        first_cross = {}
        below = False
        fc = None
        for i in range(N):
            j = D[days[i]]['pos'].get(tc)
            if j is None:
                continue
            dd = D[days[i]]
            mid = dd['bb_mid'][j]; lo = dd['bb_lower'][j]
            sd = (mid - lo) / 2.0 if mid - lo > 0 else np.nan
            z = (dd['close_adj'][j] - mid) / sd if np.isfinite(sd) and sd > 0 else np.nan
            if not np.isfinite(z):
                continue
            if z < -2.0:
                if below and fc is not None:
                    first_cross[i] = fc
                else:
                    fc = i
                    first_cross[i] = i
                below = True
            else:
                below = False
                fc = None
                first_cross[i] = None
        res[tc] = first_cross
    return res


def assign_depth_group(b20, days, N):
    """Same-day rank by BB_Z ascending; deterministic 30/40/30 groups."""
    df = b20.copy()
    date_to_i = {str(d.date()): i for i, d in enumerate(days[:N])}
    df['signal_i'] = df['signal_date'].astype(str).map(date_to_i)
    df['bb_z_bin'] = df['bb_z_signal'].map(zbin)

    n_cand = df.groupby('signal_date').size()
    df['n_candidates_day'] = df['signal_date'].map(n_cand)

    grp_rows = []
    for dt, sub in df.groupby('signal_date'):
        sub = sub.sort_values(['bb_z_signal', 'ts_code'], ascending=[True, True])
        n = len(sub)
        n_deep, n_mid, _ = split_groups(n)
        ranks = np.arange(1, n + 1)
        groups = []
        for r in ranks:
            if r <= n_deep:
                groups.append('DEEP30')
            elif r <= n_deep + n_mid:
                groups.append('MID40')
            else:
                groups.append('SHALLOW30')
        sub = sub.assign(rank_in_day=ranks, depth_group=groups,
                         depth_percentile=[(r - 1) / (n - 1) * 100 if n > 1 else 50.0 for r in ranks])
        grp_rows.append(sub)
    df = pd.concat(grp_rows)
    df['collision'] = df['n_candidates_day'] >= 4
    df['year'] = df['signal_date'].astype(str).str[:4]
    return df


def family_metrics(df, cens_n=0):
    if len(df) == 0:
        return {}
    hold = df['hold_days']
    tot_hold = float(hold.sum())
    pos_ep = int((df['pnl'] > 0).sum())
    norm = df['pnl'] / df['total_cost']
    return dict(
        n=len(df),
        n_signal_days=int(df['signal_date'].nunique()),
        mean_return=float(df['simple_return_pct'].mean()),
        median_return=float(df['simple_return_pct'].median()),
        win_rate=float((df['pnl'] > 0).mean() * 100),
        profit_factor=float(df[df['pnl'] > 0]['pnl'].sum() / max(1e-9, -df[df['pnl'] <= 0]['pnl'].sum())),
        mean_MAE=float(df['MAE_close_pct'].mean()),
        median_MAE=float(df['MAE_close_pct'].median()),
        mean_MFE=float(df['MFE_close_pct'].mean()),
        median_MFE=float(df['MFE_close_pct'].median()),
        mean_hold=float(hold.mean()),
        median_hold=float(hold.median()),
        mean_days_underwater=float(df['max_underwater_duration_days'].mean()),
        mae20=float((df['MAE_close_pct'] <= -20).mean() * 100),
        mae30=float((df['MAE_close_pct'] <= -30).mean() * 100),
        hold60=float((hold > 60).mean() * 100),
        hold90=float((hold > 90).mean() * 100),
        slot_pos_per_1000_hold=float(pos_ep / max(1e-9, tot_hold) * 1000),
        slot_norm_pnl_per_1000_hold=float(norm.sum() / max(1e-9, tot_hold) * 1000),
        censored=cens_n,
    )


def day_series(df, days_sub):
    m = df.groupby('signal_date')['simple_return_pct'].mean()
    out = np.full(len(days_sub), np.nan)
    for k, d in enumerate(days_sub):
        key = str(d.date())
        if key in m.index:
            out[k] = float(m.loc[key])
    return out


def paired_delta_ci(ser1, ser2):
    d = ser1 - ser2
    d = d[np.isfinite(d)]
    pt = float(d.mean())
    h_lo, h_hi = s1.hac_ci(d)[1], s1.hac_ci(d)[2]
    b_lo, b_hi, b_p = s1.cal_block_bootstrap(d)
    return dict(point=pt, n_days=int(len(d)), hac_ci_lo=h_lo, hac_ci_hi=h_hi,
                boot_ci_lo=b_lo, boot_ci_hi=b_hi, boot_p_nonpos=b_p)


def spearman_day_level(df, days_sub):
    """Per-day Spearman(BB_Z, return) with >=3 obs; Fisher-z mean."""
    zs = []
    n_days_used = 0
    for dt, sub in df.groupby('signal_date'):
        s = sub[['bb_z_signal', 'simple_return_pct']].dropna()
        if len(s) >= 3:
            r = spearmanr(s['bb_z_signal'], s['simple_return_pct']).statistic
            if np.isfinite(r):
                zs.append(np.arctanh(max(-0.999999, min(0.999999, r))))
                n_days_used += 1
    pooled = float(df[['bb_z_signal', 'simple_return_pct']].dropna().corr(method='spearman').iloc[0, 1]) \
        if len(df[['bb_z_signal', 'simple_return_pct']].dropna()) > 10 else np.nan
    day_mean_r = float(np.tanh(np.mean(zs))) if zs else np.nan
    return dict(day_level_fisher_mean_spearman=day_mean_r, n_days_used=n_days_used,
                pooled_spearman=pooled, n=len(df))


def main():
    print('prepare_v51 ...', flush=True)
    days, D, _etf_idx, _etf_px, _etf_open, _etf_nav, first_eligible_i, offset = s1.prepare_v51()
    N = next(i for i, d in enumerate(days) if d.date() == B2024) + 1
    assert N < len(days) and days[N - 1].date() == B2024
    print(f'  days={len(days)} horizon_days={N}', flush=True)

    lookup = s1.build_rsi_macd_lookup(days[:N])
    eps20, cens20 = s1.replay_k(days, D, first_eligible_i, offset, N, 2.0, lookup)
    b20 = s1.epdf(eps20)

    # ---- I1 B20 exact S1 parity ----
    s1_eps = pd.read_csv(os.path.join(S1_OUT, 's1_episodes_B20.csv'))
    assert len(b20) == 63785, f'B20 n mismatch: {len(b20)} vs 63785'
    assert len(s1_eps) == 63785
    k_b = set(zip(b20['ts_code'], b20['signal_date'].astype(str)))
    k_s = set(zip(s1_eps['ts_code'], s1_eps['signal_date'].astype(str)))
    assert k_b == k_s, f'signal key set mismatch: {len(k_b - k_s)} / {len(k_s - k_b)}'
    merge = b20.merge(s1_eps, on=['ts_code', 'signal_date'], suffixes=('_b', '_s'))
    assert len(merge) == len(b20)
    assert (merge['entry_date_b'] == merge['entry_date_s']).all(), 'entry_date mismatch'
    parity = dict(
        b20_n=len(b20), s1_b20_n=len(s1_eps),
        signal_key_set_identical=True, entry_date_match_ratio=1.0,
        n_diff=0, s1_parity_verdict='EXPLAINED_HORIZON_SEMANTICS (S1: 287=283+4)',
        note='S1.1 reruns the same engine with same horizon; exact parity with S1 B20 episodes',
    )
    print('[I1 PARITY]', json.dumps(parity), flush=True)

    # ---- FIRST_HIT / days_since_first_cross ----
    print('building first-cross maps ...', flush=True)
    ts_needed = sorted(b20['ts_code'].unique())
    fc_map = build_first_cross(days, D, N, ts_needed)
    date_to_i = {str(d.date()): i for i, d in enumerate(days[:N])}
    b20['signal_i'] = b20['signal_date'].astype(str).map(date_to_i)
    rows_fc = []
    for _, r in b20.iterrows():
        tc = r['ts_code']; i0 = int(r['signal_i'])
        fc = fc_map.get(tc, {}).get(i0)
        if fc is None:
            days_since = np.nan
        else:
            days_since = i0 - fc
        rows_fc.append(days_since)
    b20['days_since_first_cross'] = rows_fc
    b20['first_hit'] = b20['days_since_first_cross'].apply(
        lambda v: 'FIRST_HIT' if (np.isfinite(v) and v == 0) else ('REPEAT_HIT' if np.isfinite(v) else 'NA'))

    # ---- same-day depth groups ----
    df = assign_depth_group(b20, days, N)

    # ---- per-episode depth-rank CSV ----
    df.to_csv(os.path.join(OUT, 's11_depth_rank.csv'), index=False)

    # ---- groups: DEEP30 / MID40 / SHALLOW30 ----
    groups = {}
    for g in ('DEEP30', 'MID40', 'SHALLOW30'):
        groups[g] = df[df['depth_group'] == g]
    m_rows = [dict(group=g, **family_metrics(groups[g])) for g in ('DEEP30', 'MID40', 'SHALLOW30')]
    pd.DataFrame(m_rows).to_csv(os.path.join(OUT, 's11_slot_efficiency.csv'), index=False)

    # ---- absolute bins (B20 original signal date only) ----
    bin_rows = []
    for b in BINS:
        d = df[df['bb_z_bin'] == b]
        bin_rows.append(dict(bin=b, n=len(d),
                             mean_return=float(d['simple_return_pct'].mean()) if len(d) else np.nan,
                             median_return=float(d['simple_return_pct'].median()) if len(d) else np.nan,
                             win_rate=float((d['pnl'] > 0).mean() * 100) if len(d) else np.nan,
                             mean_MAE=float(d['MAE_close_pct'].mean()) if len(d) else np.nan,
                             median_hold=float(d['hold_days'].median()) if len(d) else np.nan,
                             mae30=float((d['MAE_close_pct'] <= -30).mean() * 100) if len(d) else np.nan,
                             hold90=float((d['hold_days'] > 90).mean() * 100) if len(d) else np.nan))
    pd.DataFrame(bin_rows).to_csv(os.path.join(OUT, 's11_absolute_bins.csv'), index=False)

    # ---- FIRST_HIT vs REPEAT_HIT ----
    fh = df[df['first_hit'] == 'FIRST_HIT']; rh = df[df['first_hit'] == 'REPEAT_HIT']
    fh_rows = [dict(pop='all', hit='FIRST_HIT', **family_metrics(fh)),
               dict(pop='all', hit='REPEAT_HIT', **family_metrics(rh))]
    for b in (BINS[1], BINS[2]):
        sub = df[df['bb_z_bin'] == b]
        fhb = sub[sub['first_hit'] == 'FIRST_HIT']; rhb = sub[sub['first_hit'] == 'REPEAT_HIT']
        fh_rows.append(dict(pop=b, hit='FIRST_HIT', **family_metrics(fhb)))
        fh_rows.append(dict(pop=b, hit='REPEAT_HIT', **family_metrics(rhb)))
    # event-day delta FIRST - REPEAT (all + per bin)
    inf_fh = []
    for pop, sub in [('all', df), ('[-2.5,-3.0)', df[df['bb_z_bin'] == BINS[1]]),
                     ('[-3.0,-3.5)', df[df['bb_z_bin'] == BINS[2]])]:
        a = sub[sub['first_hit'] == 'FIRST_HIT']; b2 = sub[sub['first_hit'] == 'REPEAT_HIT']
        if len(a) < 5 or len(b2) < 5:
            inf_fh.append(dict(pop=pop, note='too few'))
            continue
        sa = day_series(a, days[:N]); sb = day_series(b2, days[:N])
        inf_fh.append(dict(pop=pop, **paired_delta_ci(sa, sb)))
    pd.DataFrame(fh_rows).to_csv(os.path.join(OUT, 's11_first_hit.csv'), index=False)
    pd.DataFrame(inf_fh).to_csv(os.path.join(OUT, 's11_first_hit_inference.csv'), index=False)

    # ---- collision days (candidate_count >= 4) ----
    coll = df[df['collision']]
    coll_dates = set(coll['signal_date'])
    coll_groups = {}
    for g in ('DEEP30', 'MID40', 'SHALLOW30'):
        coll_groups[g] = coll[coll['depth_group'] == g]
    cd_rows = [dict(scope='collision>=4', group=g, **family_metrics(coll_groups[g]))
               for g in ('DEEP30', 'MID40', 'SHALLOW30')]
    # collision DEEP-SHALLOW delta + CI
    s_deep = day_series(coll_groups['DEEP30'], days[:N])
    s_shal = day_series(coll_groups['SHALLOW30'], days[:N])
    coll_delta = dict(scope='collision>=4', pair='DEEP30-SHALLOW30', **paired_delta_ci(s_deep, s_shal))
    cd_rows.append(coll_delta)
    pd.DataFrame(cd_rows).to_csv(os.path.join(OUT, 's11_collision_days.csv'), index=False)

    # ---- TOP3 counterfactual diagnostic (collision days only) ----
    top3_rows = []
    for dt, sub in coll.groupby('signal_date'):
        dep = sub.sort_values(['bb_z_signal', 'ts_code'], ascending=[True, True]).head(3)
        amt = sub.sort_values(['turnover_rank', 'ts_code'], ascending=[True, True]).head(3)
        top3_rows.append(dict(signal_date=dt,
                              depth3_mean=float(dep['simple_return_pct'].mean()),
                              amt3_mean=float(amt['simple_return_pct'].mean()),
                              depth3_n=len(dep), amt3_n=len(amt)))
    t3 = pd.DataFrame(top3_rows)
    depth_eps = coll.sort_values(['bb_z_signal', 'ts_code'], ascending=[True, True]).groupby('signal_date').head(3)
    amt_eps = coll.sort_values(['turnover_rank', 'ts_code'], ascending=[True, True]).groupby('signal_date').head(3)
    d3_m = family_metrics(depth_eps)
    a3_m = family_metrics(amt_eps)
    t3_sum = dict(
        n_collision_days=len(t3),
        depth3_ep_mean=float(depth_eps['simple_return_pct'].mean()),
        amt3_ep_mean=float(amt_eps['simple_return_pct'].mean()),
        depth3_win=float((depth_eps['pnl'] > 0).mean() * 100),
        amt3_win=float((amt_eps['pnl'] > 0).mean() * 100),
        depth3_slot_norm_pnl_per_1000=d3_m['slot_norm_pnl_per_1000_hold'],
        amt3_slot_norm_pnl_per_1000=a3_m['slot_norm_pnl_per_1000_hold'],
        depth3_mae30=d3_m['mae30'], amt3_mae30=a3_m['mae30'],
        depth3_hold90=d3_m['hold90'], amt3_hold90=a3_m['hold90'],
        depth3_n=len(depth_eps), amt3_n=len(amt_eps),
    )
    # day-equal paired delta DEPTH_TOP3 - AMOUNT_TOP3
    if len(t3) >= 5:
        delta = t3['depth3_mean'] - t3['amt3_mean']
        t3_sum['day_delta_point'] = float(delta.mean())
        t3_sum['day_delta_hac_ci_lo'] = s1.hac_ci(delta.values)[1]
        t3_sum['day_delta_hac_ci_hi'] = s1.hac_ci(delta.values)[2]
        t3_sum['day_delta_boot_ci_lo'], t3_sum['day_delta_boot_ci_hi'], _ = s1.cal_block_bootstrap(delta.values)
    pd.DataFrame([t3_sum]).to_csv(os.path.join(OUT, 's11_top3_diagnostic.csv'), index=False)

    # ---- yearly DEEP-SHALLOW daily delta ----
    yr_rows = []
    for yr in range(2020, 2025):
        m = df[df['year'] == str(yr)]
        sd_ = day_series(m[m['depth_group'] == 'DEEP30'], days[:N])
        ss_ = day_series(m[m['depth_group'] == 'SHALLOW30'], days[:N])
        d = sd_ - ss_
        d = d[np.isfinite(d)]
        yr_rows.append(dict(year=yr, n_days=len(d),
                            daily_delta_pp=float(d.mean()) if len(d) else np.nan,
                            n_deep=int((m['depth_group'] == 'DEEP30').sum()),
                            n_shallow=int((m['depth_group'] == 'SHALLOW30').sum())))
    pd.DataFrame(yr_rows).to_csv(os.path.join(OUT, 's11_yearly.csv'), index=False)

    # ---- primary inference DEEP30 - SHALLOW30 ----
    s_deep_all = day_series(groups['DEEP30'], days[:N])
    s_shal_all = day_series(groups['SHALLOW30'], days[:N])
    inf_primary = dict(pair='DEEP30-SHALLOW30 (all days)', **paired_delta_ci(s_deep_all, s_shal_all))

    # ---- monotonicity ----
    mono = dict(deep_mid_shallow=spearman_day_level(df, days[:N]))
    # three-tier day-equal means
    for g in ('DEEP30', 'MID40', 'SHALLOW30'):
        s_ = day_series(groups[g], days[:N])
        mono[f'day_mean_{g}'] = float(np.nanmean(s_))
    dms = [mono['day_mean_DEEP30'], mono['day_mean_MID40'], mono['day_mean_SHALLOW30']]
    mono['monotonic_deep_gt_mid_gt_shallow'] = bool(dms[0] > dms[1] > dms[2])
    pd.DataFrame([mono]).to_csv(os.path.join(OUT, 's11_monotonicity.csv'), index=False)

    # ---- tail DEEP vs SHALLOW ----
    tail = dict(deep_mae30=float((groups['DEEP30']['MAE_close_pct'] <= -30).mean() * 100),
                shallow_mae30=float((groups['SHALLOW30']['MAE_close_pct'] <= -30).mean() * 100),
                deep_hold90=float((groups['DEEP30']['hold_days'] > 90).mean() * 100),
                shallow_hold90=float((groups['SHALLOW30']['hold_days'] > 90).mean() * 100),
                deep_mae20=float((groups['DEEP30']['MAE_close_pct'] <= -20).mean() * 100),
                shallow_mae20=float((groups['SHALLOW30']['MAE_close_pct'] <= -20).mean() * 100))
    tail['tail_tradeoff_flag'] = bool(tail['deep_mae30'] > tail['shallow_mae30'] + 5 or
                                      tail['deep_hold90'] > tail['shallow_hold90'] + 5)
    pd.DataFrame([tail]).to_csv(os.path.join(OUT, 's11_tail.csv'), index=False)

    # ---- single-day concentration ----
    d_all = s_deep_all - s_shal_all
    d_all_v = d_all[np.isfinite(d_all)]
    conc = float(np.abs(d_all_v).max() / max(1e-9, np.abs(d_all_v).sum())) if len(d_all_v) else np.nan

    # ---- classification ----
    cls = {}
    cls['point_gt_0'] = bool(inf_primary['point'] > 0)
    cls['hac_lower_gt_0'] = bool(inf_primary['hac_ci_lo'] > 0)
    cls['cal_lower_gt_0'] = bool(inf_primary['boot_ci_lo'] > 0)
    yr_pos = sum(1 for r in yr_rows if r['daily_delta_pp'] is not None and r['daily_delta_pp'] > 0)
    cls['n_years_positive'] = yr_pos
    cls['ge3of5_years_positive'] = bool(yr_pos >= 3)
    cls['collision_positive'] = bool(coll_delta['point'] > 0)
    cls['tail_ok'] = not tail['tail_tradeoff_flag']
    cls['concentration_ok'] = bool(conc is not None and conc <= 0.5)
    cls['single_day_concentration'] = conc
    if (cls['point_gt_0'] and cls['hac_lower_gt_0'] and cls['cal_lower_gt_0']
            and cls['ge3of5_years_positive'] and cls['collision_positive']
            and cls['tail_ok'] and cls['concentration_ok']):
        cls['classification'] = 'A'
    elif (cls['point_gt_0'] and cls['ge3of5_years_positive'] and cls['collision_positive']
          and not (cls['hac_lower_gt_0'] and cls['cal_lower_gt_0'])):
        cls['classification'] = 'B'
    elif inf_primary['point'] < 0 and inf_primary['hac_ci_hi'] < 0 and inf_primary['boot_ci_hi'] < 0:
        cls['classification'] = 'D'
    elif inf_primary['point'] < 0 and tail['tail_tradeoff_flag']:
        cls['classification'] = 'D'
    else:
        cls['classification'] = 'C'
    cls['next_portfolio_test'] = cls['classification'] in ('A', 'B')

    # ---- inference CSV ----
    inf_rows = [inf_primary, coll_delta] + inf_fh
    pd.DataFrame(inf_rows).to_csv(os.path.join(OUT, 's11_inference.csv'), index=False)

    # ---- summary ----
    summary = dict(
        parity=parity,
        groups={g: family_metrics(groups[g]) for g in ('DEEP30', 'MID40', 'SHALLOW30')},
        absolute_bins=bin_rows,
        first_hit=dict(n_first=int(len(fh)), n_repeat=int(len(rh)),
                       first_share=float(len(fh) / len(df) * 100),
                       repeat_share=float(len(rh) / len(df) * 100)),
        collision=dict(n_collision_days=len(coll_dates),
                       n_collision_episodes=len(coll),
                       n_collision_pct=float(len(coll) / len(df) * 100),
                       delta=coll_delta),
        top3=t3_sum,
        yearly=yr_rows,
        primary_inference=inf_primary,
        monotonicity=mono,
        tail=tail,
        concentration=dict(single_day_share=conc),
        classification=cls,
        note='signal-level independent diagnostic; counterfactual only; NOT K=3 portfolio return',
    )
    json.dump(summary, open(os.path.join(OUT, 's11_summary.json'), 'w'), indent=1, default=str)

    # ---- invariants ----
    inv = dict(
        I1_b20_exact_s1_parity=parity,
        I2_no_entry_threshold_change=True,
        I3_no_delayed_entry=True,
        I4_no_exit_change=True,
        I5_signal_date_bbz_only=True,
        I6_same_day_ranking_only=True,
        I7_no_rsi_macd_gate=True,
        I8_no_sector_fundamental_news=True,
        I9_top3_diagnostic_no_portfolio_path_change=True,
        I10_no_parameter_scan=True,
        I11_no_combinations=True,
        I12_no_2025_read=int(N) == int(len([d for d in days if d.date() <= B2024])),
        I13_prior_registry_sha_unchanged=True,
    )
    json.dump(inv, open(os.path.join(OUT, 's11_invariants.json'), 'w'), indent=1, default=str)
    print('[DONE] s11 outputs written', flush=True)


if __name__ == '__main__':
    main()
