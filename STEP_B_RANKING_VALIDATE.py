#!/usr/bin/env python3
"""
STEP_B_RANKING_VALIDATE.py

Phase P2 — Cross-Sectional Ranking Validation (untouched 2023-2024).

Reads frozen SECONDARY episodes + predictors, validates V01-V05 against the
pre-registered CROSS_SECTIONAL_RANKING_VALIDATION_REGISTRY (commit 83c3f1e,
SHA d5859930...). F05 RET5 is MARGINAL ONLY (not in BH m=5, not in A/B/C).

Registry gate (frozen):
  A direction-frozen mean daily CS IC
  B BH q(m=5) < 0.05
  C |mean daily IC| >= 0.03
  D oriented pairwise >= 53.0% (ties excluded, PAIR_CAP 5000)
  E equal-day K3 lift >= +0.50 pp
  F signal-day block bootstrap (L=21, B=5000) K3-lift 95% CI lower > 0
  G 2023 & 2024 same direction, or one same + other |annual IC| < 0.02;
    opposite year |IC| >= 0.02 forbids STRONG PASS
"""
import os, sys, time, pickle
import numpy as np, pandas as pd
from scipy import stats

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
OUT = os.path.join(REPO, 'results'); os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, REPO)
from cross_sectional_ranking_p1 import (build_predictor_frame, nw_mean_t, bh_fdr, spearman,
                                        PREDS, FIDS, PRED_COLS)
from cross_sectional_ranking_p1_corrected import block_boot_mean_ci_full

RNG = np.random.default_rng(20260903)
VAL_START, VAL_END = pd.Timestamp('2023-01-01'), pd.Timestamp('2024-12-31')
MIN_SIG = 5
HAC_LAGS = (5, 10, 20)
BLOCK_L, BLOCK_B = 21, 5000
RANDOM_B = 5000
PAIR_CAP = 5000
G_MIN_IC, G_PAIR, G_K3 = 0.03, 53.0, 0.50
NEAR_ZERO = 0.02

FEATS = [  # (vid, fid, col, direction, window_k)
    ('V01', 'F04', 'ret3', 'NEGATIVE', 3),
    ('V02', 'F06', 'ret20', 'NEGATIVE', 20),
    ('V03', 'F07', 'dist_ma20', 'NEGATIVE', 20),
    ('V04', 'F09', 'atr20_pct', 'POSITIVE', 20),
    ('V05', 'F13', 'intraday_range', 'POSITIVE', 1),
]
MARGINAL = ('F05', 'ret5', 'NEGATIVE')

# Discovery reference (P1.1 corrected) for effect replication
DISC_REF = {f: {} for f in ['F04', 'F06', 'F07', 'F09', 'F13', 'F05']}
_d = pd.read_csv(os.path.join(OUT, 'p11_master_table.csv')).set_index('feature_id')
for f in DISC_REF:
    DISC_REF[f]['ic'] = float(_d.loc[f, 'mean_ic'])
    DISC_REF[f]['k3'] = float(_d.loc[f, 'K3_lift_pp'])


def load_val_data():
    pred = build_predictor_frame().set_index(['ts_code', 'date'])
    fm = pd.read_csv(os.path.join(REPO, 'results', 'fullmarket_episode_metrics.csv'))
    fm['signal_date'] = pd.to_datetime(fm['signal_date'])
    val = fm[(fm['signal_date'] >= VAL_START) & (fm['signal_date'] <= VAL_END)].copy()
    val = val.join(pred, on=['ts_code', 'signal_date'], how='left')
    return pred, val


def window_gap_flags(val, col, k):
    """Per-episode: did the last k observed stock bars of `col` span > k market days?"""
    df = pd.read_parquet(os.path.join(ROOT, 'data', 'combined_daily.parquet'), columns=['ts_code', 'date'])
    mdates = np.array(sorted(df['date'].unique()))
    m_idx = {d: i for i, d in enumerate(mdates)}
    stock_dates = {c: np.sort(np.asarray(d, dtype='datetime64[ns]')) for c, d in df.groupby('ts_code')['date']}
    codes = val['ts_code'].to_numpy(); sig = val['signal_date'].to_numpy(dtype='datetime64[ns]')
    gap = np.zeros(len(val), dtype=bool)
    for i in range(len(val)):
        arr = stock_dates.get(codes[i])
        if arr is None:
            continue
        pos = np.searchsorted(arr, sig[i], side='left')
        if pos >= k and pos < len(arr) and arr[pos] == sig[i]:
            obs_k = arr[pos - k]
            span = m_idx.get(sig[i], np.searchsorted(mdates, sig[i], side='right')) - \
                   m_idx.get(obs_k, np.searchsorted(mdates, obs_k, side='right'))
            gap[i] = span > k
    return gap


def per_day_metrics(val, col, direction):
    """Per signal day: IC, pairwise, K3 lift, quintile episode-mean metrics. All equal-day."""
    day_ic, day_ic_d, day_k3, day_pair, day_pair_n, day_pair_t = [], [], [], [], [], []
    quint = {q: {'ret': [], 'wr': [], 'mae': [], 'mfe': [], 'hold': []} for q in range(1, 6)}
    for d, dd in val.groupby('signal_date'):
        x = dd[col].to_numpy(float); r = dd['simple_return_pct'].to_numpy(float)
        v = np.isfinite(x) & np.isfinite(r)
        if v.sum() >= MIN_SIG:
            icv = spearman(x, r)
            if np.isfinite(icv):
                day_ic.append(icv); day_ic_d.append(d)
        if v.sum() >= 3:
            xv = x[v]; rv = r[v]; nv = len(xv)
            # pairwise (oriented later, ties excluded)
            n_pairs = nv * (nv - 1) // 2
            if n_pairs:
                if n_pairs > PAIR_CAP:
                    ap = np.array([(a, b) for a in range(nv) for b in range(a + 1, nv)])
                    sel = RNG.choice(len(ap), size=PAIR_CAP, replace=False); pairs = ap[sel]
                else:
                    pairs = np.array([(a, b) for a in range(nv) for b in range(a + 1, nv)])
                dx = xv[pairs[:, 0]] - xv[pairs[:, 1]]; dr = rv[pairs[:, 0]] - rv[pairs[:, 1]]
                ok = (dx != 0) & (dr != 0)
                day_pair.append(int(ok.sum())); day_pair_n.append(int((np.sign(dx[ok]) == np.sign(dr[ok])).sum()))
                day_pair_t.append(int(len(pairs) - ok.sum()))
            # oriented K3
            o = np.argsort(-xv) if direction == 'POSITIVE' else np.argsort(xv)
            day_k3.append(rv[o[:3]].mean() - float(rv.mean()))
            # quintiles (episode-level metrics within day)
            ql = np.clip(np.ceil(stats.rankdata(xv) / nv * 5).astype(int), 1, 5)
            em = dd[['MAE_intraday_pct', 'MFE_intraday_pct', 'hold_days']].to_numpy(float)
            for q in range(1, 6):
                mm = ql == q
                if mm.sum():
                    quint[q]['ret'].append(rv[mm].mean())
                    quint[q]['wr'].append((rv[mm] > 0).mean() * 100)
                    quint[q]['mae'].append(np.nanmean(em[mm, 0]))
                    quint[q]['mfe'].append(np.nanmean(em[mm, 1]))
                    quint[q]['hold'].append(np.nanmean(em[mm, 2]))
    return day_ic, day_ic_d, day_k3, day_pair, day_pair_n, day_pair_t, quint


def main():
    t0 = time.time()
    pred, val = load_val_data()
    n_ep = len(val); n_day = val['signal_date'].nunique()
    print(f'[val] episodes={n_ep}, signal days={n_day} ({time.time()-t0:.0f}s)', flush=True)

    rows = []
    daily_ic_rows = []
    for vid, fid, col, direction, wk in FEATS:
        ic_ser, ic_d, k3_ser, pn, pok, pt, quint = per_day_metrics(val, col, direction)
        s = np.array(ic_ser); k3 = np.array(k3_ser)
        # HAC
        mu = t = rawp = np.nan
        if len(s):
            mu, se, t, rawp = nw_mean_t(s, 10)
        # BH over m=5 (compute per-feature raw p for m=5 family; q computed globally after loop)
        # oriented pairwise
        p_tot = sum(pn); p_ok = sum(pok); p_tie = sum(pt)
        raw_agree = p_ok / p_tot * 100 if p_tot else np.nan
        pair_acc = raw_agree if direction == 'POSITIVE' else (100 - raw_agree)
        # K3 lift
        k3_mu = float(k3.mean()) if len(k3) else np.nan
        k3_pe, k3_bm, k3_lo, k3_hi = block_boot_mean_ci_full(k3, BLOCK_L, BLOCK_B) if len(k3) else (np.nan,) * 4
        # per-feature exact usable-day random K3 (no replacement)
        usable_arrays = []  # (day_mean_ret, rv array) for days with >=3 valid signals
        for d, dd in val.groupby('signal_date'):
            x = dd[col].to_numpy(float); r = dd['simple_return_pct'].to_numpy(float)
            v = np.isfinite(x) & np.isfinite(r)
            if v.sum() >= 3:
                usable_arrays.append((float(r[v].mean()), r[v]))
        n_use = len(usable_arrays)
        rand = np.full(RANDOM_B, np.nan)
        for b in range(RANDOM_B):
            sm = 0.0
            for am, rv in usable_arrays:
                sm += rv[RNG.choice(len(rv), size=3, replace=False)].mean()
            rand[b] = sm / n_use
        rand_mu = float(rand.mean()); rand_lo, rand_hi = float(np.percentile(rand, 2.5)), float(np.percentile(rand, 97.5))
        # ranked K3 mean (equal-day) on same usable-day set
        k3m = np.nan
        if usable_arrays:
            rk = []
            for d, dd in val.groupby('signal_date'):
                x = dd[col].to_numpy(float); r = dd['simple_return_pct'].to_numpy(float)
                v = np.isfinite(x) & np.isfinite(r)
                if v.sum() >= 3:
                    xv = x[v]; rv = r[v]
                    o = np.argsort(-xv) if direction == 'POSITIVE' else np.argsort(xv)
                    rk.append(rv[o[:3]].mean())
            k3m = float(np.mean(rk))
        pctile = float((rand < k3m).mean() * 100) if np.isfinite(k3m) else np.nan
        # oracle
        orc = {k: np.nan for k in (1, 3, 5)}
        if usable_arrays:
            for k in (1, 3, 5):
                sm = []
                for _, rv in usable_arrays:
                    if len(rv) >= k:
                        sm.append(rv[np.argsort(-rv)[:k]].mean())
                orc[k] = float(np.mean(sm)) if sm else np.nan
        # yearly IC
        yic = {}
        for yr in (2023, 2024):
            yy = [ic for ic, d in zip(ic_ser, ic_d) if d.year == yr]
            yic[yr] = float(np.mean(yy)) if yy else np.nan
        # quintile summary
        qrow = []
        for q in range(1, 6):
            qrow.append(dict(vid=vid, quintile=q,
                             n_days=len(quint[q]['ret']),
                             mean_return_pp=float(np.mean(quint[q]['ret'])) if quint[q]['ret'] else np.nan,
                             positive_day_fraction=float(np.mean([a > 0 for a in quint[q]['ret']])) if quint[q]['ret'] else np.nan,
                             episode_win_rate_pct=float(np.mean(quint[q]['wr'])) if quint[q]['wr'] else np.nan,
                             MAE_intraday_pct=float(np.mean(quint[q]['mae'])) if quint[q]['mae'] else np.nan,
                             MFE_intraday_pct=float(np.mean(quint[q]['mfe'])) if quint[q]['mfe'] else np.nan,
                             hold_days=float(np.mean(quint[q]['hold'])) if quint[q]['hold'] else np.nan))
        qdf = pd.DataFrame(qrow)
        qdf.to_csv(os.path.join(OUT, 'p2_quintiles.csv'), mode='a', header=not os.path.exists(os.path.join(OUT, 'p2_quintiles.csv')), index=False)
        # gap audit
        g = window_gap_flags(val, col, wk)
        gap_n = int(g.sum())
        sub = val[~g].copy()
        s_ic, s_d, s_k3, *_ = per_day_metrics(sub, col, direction)
        ss = np.array(s_ic); sk = np.array(s_k3)
        s_mu = nw_mean_t(ss, 10)[0] if len(ss) else np.nan
        s_k3m = float(sk.mean()) if len(sk) else np.nan
        # effect replication
        d_ic, d_k3 = DISC_REF[fid]['ic'], DISC_REF[fid]['k3']
        ratio_ic = (mu / d_ic) if (np.isfinite(mu) and np.isfinite(d_ic) and abs(d_ic) > 1e-9) else np.nan
        ratio_k3 = (k3_mu / d_k3) if (np.isfinite(k3_mu) and np.isfinite(d_k3) and abs(d_k3) > 1e-9) else np.nan
        if np.isfinite(ratio_ic):
            repl = 'REPLICATED' if ratio_ic >= 0.5 else 'ATTENUATED' if ratio_ic > 0 else 'FAILED'
        else:
            repl = 'FAILED'
        rows.append(dict(validation_id=vid, feature_id=fid, name=PREDS[FIDS.index(fid)][2], direction=direction,
                         n_days=len(s), n_episodes=n_ep, mean_ic=mu, median_ic=float(np.median(s)) if len(s) else np.nan,
                         pos_frac=float((s > 0).mean()) if len(s) else np.nan,
                         hac_t=t, raw_p=rawp, n_pairs=p_tot, ties=p_tie, pairwise_acc=pair_acc,
                         K3_lift_pp=k3_mu, K3_boot_mean=k3_bm, K3_ci_lo=k3_lo, K3_ci_hi=k3_hi,
                         K3_ranked_mean_pp=k3m, usable_days=n_use, random_K3_mean=rand_mu,
                         random_K3_lo=rand_lo, random_K3_hi=rand_hi, random_pctile=pctile,
                         oracle_K3=orc[3], ic_2023=yic[2023], ic_2024=yic[2024],
                         disc_ic=d_ic, disc_k3=d_k3, ratio_ic=ratio_ic, ratio_k3=ratio_k3, replication=repl,
                         gap_n=gap_n, gap_pct=gap_n / n_ep * 100, sens_ic=s_mu, sens_k3=s_k3m))
        for ic, d in zip(ic_ser, ic_d):
            daily_ic_rows.append(dict(validation_id=vid, signal_date=d, ic=ic))
    mdf = pd.DataFrame(rows)
    # BH m=5 (only V01-V05)
    rawps = mdf['raw_p'].to_numpy(float)
    qs = bh_fdr(rawps)
    mdf['bh_q'] = qs
    # gates
    def evaluate(r):
        A = (np.sign(r['mean_ic']) == (1 if r['direction'] == 'POSITIVE' else -1)) if np.isfinite(r['mean_ic']) else False
        B = bool(np.isfinite(r['bh_q']) and r['bh_q'] < 0.05)
        C = bool(np.isfinite(r['mean_ic']) and abs(r['mean_ic']) >= G_MIN_IC)
        D = bool(np.isfinite(r['pairwise_acc']) and r['pairwise_acc'] >= G_PAIR)
        E = bool(np.isfinite(r['K3_lift_pp']) and r['K3_lift_pp'] >= G_K3)
        F = bool(np.isfinite(r['K3_ci_lo']) and r['K3_ci_lo'] > 0)
        i23, i24 = r['ic_2023'], r['ic_2024']
        sgn = 1 if r['direction'] == 'POSITIVE' else -1
        y23 = np.sign(i23) == sgn; y24 = np.sign(i24) == sgn
        nz23 = abs(i23) < NEAR_ZERO; nz24 = abs(i24) < NEAR_ZERO
        opp23 = (np.sign(i23) != sgn) and (abs(i23) >= NEAR_ZERO)
        opp24 = (np.sign(i24) != sgn) and (abs(i24) >= NEAR_ZERO)
        G = bool((y23 and y24) or (y23 and nz24) or (y24 and nz23)) and not (opp23 or opp24)
        return A, B, C, D, E, F, G
    gatecols = []
    for _, r in mdf.iterrows():
        A, B, C, D, E, F, G = evaluate(r)
        gatecols.append(dict(gateA_direction=A, gateB_bhq=B, gateC_effectsize=C, gateD_pairwise=D,
                             gateE_k3=E, gateF_boot=F, gateG_yearly=G,
                             STRONG_PASS=bool(A and B and C and D and E and F and G),
                             PASS=(A and B and C and D and E and F and G)))
    mdf = pd.concat([mdf, pd.DataFrame(gatecols)], axis=1)
    mdf.to_csv(os.path.join(OUT, 'p2_master_table.csv'), index=False)
    pd.DataFrame(daily_ic_rows).to_csv(os.path.join(OUT, 'p2_daily_ic.csv'), index=False)
    print(mdf[['validation_id', 'feature_id', 'direction', 'n_days', 'mean_ic', 'bh_q', 'pairwise_acc',
               'K3_lift_pp', 'K3_ci_lo', 'K3_ci_hi', 'ic_2023', 'ic_2024', 'STRONG_PASS', 'PASS']].round(4).to_string())

    # HAC sensitivity
    hac_rows = []
    for vid, fid, col, direction, wk in FEATS:
        ic_ser, *_ = per_day_metrics(val, col, direction)
        s = np.array(ic_ser)
        for lag in HAC_LAGS:
            mu, se, t, p = nw_mean_t(s, lag)
            hac_rows.append(dict(validation_id=vid, feature_id=fid, lag=lag, mean_ic=mu, hac_t=t, raw_p=p))
    pd.DataFrame(hac_rows).to_csv(os.path.join(OUT, 'p2_hac.csv'), index=False)
    pd.DataFrame([dict(feature_id=r['feature_id'], validation_id=r['validation_id'], raw_p=r['raw_p'], bh_q=r['bh_q'], bh_family=5)
                  for _, r in mdf.iterrows()]).to_csv(os.path.join(OUT, 'p2_bh5.csv'), index=False)

    # pairwise / k3 / random / oracle / effect / yearly detail files
    mdf.to_csv(os.path.join(OUT, 'p2_pairwise.csv'), index=False, columns=['validation_id', 'feature_id', 'n_pairs', 'ties', 'pairwise_acc'])
    mdf.to_csv(os.path.join(OUT, 'p2_k3_lift.csv'), index=False, columns=['validation_id', 'feature_id', 'K3_lift_pp', 'K3_ranked_mean_pp', 'usable_days'])
    mdf.to_csv(os.path.join(OUT, 'p2_k3_bootstrap.csv'), index=False, columns=['validation_id', 'feature_id', 'K3_lift_pp', 'K3_boot_mean', 'K3_ci_lo', 'K3_ci_hi'])
    mdf.to_csv(os.path.join(OUT, 'p2_random_k3_per_feature.csv'), index=False, columns=['validation_id', 'feature_id', 'usable_days', 'random_K3_mean', 'random_K3_lo', 'random_K3_hi', 'K3_ranked_mean_pp', 'random_pctile'])
    mdf.to_csv(os.path.join(OUT, 'p2_oracle.csv'), index=False, columns=['validation_id', 'feature_id', 'usable_days', 'oracle_K3'])
    mdf.to_csv(os.path.join(OUT, 'p2_effect_replication.csv'), index=False, columns=['validation_id', 'feature_id', 'disc_ic', 'mean_ic', 'ratio_ic', 'disc_k3', 'K3_lift_pp', 'ratio_k3', 'replication'])
    mdf.to_csv(os.path.join(OUT, 'p2_yearly.csv'), index=False, columns=['validation_id', 'feature_id', 'ic_2023', 'ic_2024'])
    mdf.to_csv(os.path.join(OUT, 'p2_suspension_sensitivity.csv'), index=False, columns=['validation_id', 'feature_id', 'gap_n', 'gap_pct', 'sens_ic', 'sens_k3'])

    # redundancy (same-day rank corr among V01-V05)
    red = []
    for a in FEATS:
        for b in FEATS:
            sm = 0.0; n = 0
            for d, dd in val.groupby('signal_date'):
                xa = dd[a[2]].to_numpy(float); xb = dd[b[2]].to_numpy(float)
                rho = spearman(xa, xb)
                if np.isfinite(rho):
                    sm += rho; n += 1
            red.append(dict(pred_a=a[0], pred_b=b[0], avg_same_day_rank_corr=sm / n if n else np.nan, n_days=n))
    pd.DataFrame(red).to_csv(os.path.join(OUT, 'p2_redundancy.csv'), index=False)

    # PRIMARY pooled direction sensitivity (PASS features only) + F05 marginal + Top10
    with open(os.path.join(REPO, 'results', 'independent_v2a_episodes.pkl'), 'rb') as fh:
        pp = pickle.load(fh)['episodes']
    ppr = pd.DataFrame(pp)
    ppr['signal_date'] = pd.to_datetime(ppr['signal_date'])
    pval = ppr[(ppr['signal_date'] >= VAL_START) & (ppr['signal_date'] <= VAL_END)].copy().join(pred, on=['ts_code', 'signal_date'], how='left')
    prow = []
    pass_feats = mdf[mdf['PASS']]['feature_id'].tolist()
    for fid in pass_feats:
        col = PREDS[FIDS.index(fid)][3]; direction = mdf[mdf['feature_id'] == fid]['direction'].iloc[0]
        x = pval[col].to_numpy(float); y = pval['return_pct'].to_numpy(float)
        m = np.isfinite(x) & np.isfinite(y)
        ic = spearman(x, y)
        prow.append(dict(feature_id=fid, n_episodes=int(m.sum()), n_signal_days=int(pval.loc[m, 'signal_date'].nunique()),
                         pooled_spearman=ic, direction=direction,
                         direction_match=bool(np.sign(ic) == (1 if direction == 'POSITIVE' else -1)) if np.isfinite(ic) else False))
    pd.DataFrame(prow).to_csv(os.path.join(OUT, 'p2_primary_sensitivity.csv'), index=False)

    # F05 marginal (excluded from BH5 / classification)
    fid, col, direction = MARGINAL
    ic_ser, ic_d, k3_ser, pn, pok, pt, quint = per_day_metrics(val, col, direction)
    s = np.array(ic_ser); k3 = np.array(k3_ser)
    mu, se, t, rawp = nw_mean_t(s, 10) if len(s) else (np.nan,) * 4
    pair_acc = sum(pok) / sum(pn) * 100 if sum(pn) else np.nan  # direction NEGATIVE -> 100-raw
    pair_acc = 100 - pair_acc if direction == 'NEGATIVE' else pair_acc
    k3_mu = float(k3.mean()) if len(k3) else np.nan
    k3_pe, k3_bm, k3_lo, k3_hi = block_boot_mean_ci_full(k3, BLOCK_L, BLOCK_B) if len(k3) else (np.nan,) * 4
    pd.DataFrame([dict(feature_id=fid, status='MARGINAL_DISCOVERY_SENSITIVITY', direction=direction, n_days=len(s),
                       mean_ic=mu, hac_t=t, raw_p=rawp, pairwise_acc=pair_acc, K3_lift_pp=k3_mu,
                       K3_ci_lo=k3_lo, K3_ci_hi=k3_hi,
                       note='NOT in BH m=5; NOT in classification; cannot rescue failures; '
                            'cannot be added to main model later based on validation')]).to_csv(
        os.path.join(OUT, 'p2_f05_marginal.csv'), index=False)

    # Top10 turnover descriptive (2023-2024)
    val['turnover_rank'] = val['turnover_rank'].astype(float)
    bucket = {}
    for b, (lo, hi) in {'A_TOP10': (0, 10), 'B_11_50': (11, 50), 'C_51_200': (51, 200),
                        'D_201_500': (201, 500), 'E_gt500': (501, 10**9)}.items():
        mm = (val['turnover_rank'] >= lo) & (val['turnover_rank'] <= hi)
        exc = []
        for d, dd in val[mm].groupby('signal_date'):
            exc.append(float(dd['simple_return_pct'].mean()) - float(val[val['signal_date'] == d]['simple_return_pct'].mean()))
        bucket[b] = dict(n=int(mm.sum()), equal_day_excess_pp=float(np.mean(exc)) if exc else np.nan)
    pd.DataFrame([dict(bucket=b, **v) for b, v in bucket.items()]).to_csv(
        os.path.join(OUT, 'p2_turnover_top10_descriptive.csv'), index=False)

    print(f'[done] ({time.time()-t0:.0f}s)', flush=True)


if __name__ == '__main__':
    main()
