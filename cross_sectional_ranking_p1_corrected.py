#!/usr/bin/env python3
"""
PHASE P1.1 — CROSS-SECTIONAL RANKING IMPLEMENTATION CORRECTION (Discovery re-run)

P1 Discovery (2020-2022) showed strong cross-sectional ranking evidence. External audit
flagged P1-level implementation/interpretation issues. This round ONLY fixes the
implementation and re-runs Discovery. Registry is NOT modified.

Corrections applied (vs cross_sectional_ranking_p1.py):
  1. Gate A now uses BH q (m=17) per Registry, not raw p.
  2. Random K3 baseline draws WITHOUT replacement (3 distinct stocks per day).
  3. K3-lift block bootstrap outputs point estimate, bootstrap mean (centering sanity), CI.
  4. Pairwise accuracy: explicit ties-excluded count; orientation from Discovery IC sign
     (UNKNOWN) or frozen Registry direction (POSITIVE/NEGATIVE).
  5. REL_RET family rank-invariance formally verified (see P1_RELATIVE_RETURN_INVARIANCE_NOTE.md).
  6. PRIMARY sensitivity renamed PRIMARY_POOLED_DIRECTION_SENSITIVITY (pooled Spearman).
  7. Suspension/observation-window gap audit + exclusion sensitivity.
  8. Passer 5x5 same-day rank correlation + economic grouping.
  9. Quintile metrics split: positive_day_fraction vs equal_day_mean_episode_win_rate.
 10. Oracle & random K3 on the SAME usable-day set (>=3 signals), without replacement.
 11. Turnover Top10 diagnostic conclusion limited to "no superior within-day quality".
 12. Registry gate A-F unchanged otherwise.

CLOSED: 2023-2024 Ranking Validation, 2025-2026 Confirmation.
"""
import os, sys, time
import numpy as np, pandas as pd
from scipy import stats

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
OUT = os.path.join(REPO, 'results'); os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, REPO)
from cross_sectional_ranking_p1 import (build_predictor_frame, nw_mean_t, bh_fdr, spearman,
                                        PREDS, FIDS, PRED_COLS, DIS_START, DIS_END)

RNG = np.random.default_rng(20260903)
MIN_SIG = 5
HAC_LAG = 10
BLOCK_L, BLOCK_B = 21, 2000
RANDOM_B = 5000
PAIR_CAP = 5000
G_MIN_IC, G_PAIR, G_K3, G_REVY = 0.03, 53.0, 0.5, 0.03
YEARS = (2020, 2021, 2022)


def block_boot_mean_ci_full(x, L=BLOCK_L, B=BLOCK_B):
    """Full-length moving-block resample of a calendar-ordered series.
    Returns (point_est, bootstrap_mean, ci_lo, ci_hi)."""
    x = np.asarray(x, float); x = x[np.isfinite(x)]; n = len(x)
    if n < 2 * L:
        return np.nan, np.nan, np.nan, np.nan
    boot = np.full(B, np.nan); nblk = int(np.ceil(n / L))
    for b in range(B):
        idx = []
        for _ in range(nblk):
            st = RNG.integers(0, n - L + 1) if n - L + 1 > 0 else 0
            idx.extend(range(st, min(st + L, n)))
        idx = np.array(idx[:n]); boot[b] = x[idx].mean()
    return float(x.mean()), float(boot.mean()), float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))


def build_gap_flags(episodes):
    """For each episode, count market trading days spanned by the last 20 observed stock bars.
       gap = span > 20 (no-gap expectation = exactly 20 market intervals)."""
    df = pd.read_parquet(os.path.join(ROOT, 'data', 'combined_daily.parquet'), columns=['ts_code', 'date'])
    mdates = np.array(sorted(df['date'].unique()))
    stock_dates = {c: np.sort(np.asarray(d, dtype='datetime64[ns]')) for c, d in df.groupby('ts_code')['date']}
    codes = episodes['ts_code'].to_numpy()
    sig = episodes['signal_date'].to_numpy(dtype='datetime64[ns]')
    span = np.full(len(episodes), np.nan)
    m_idx = {d: i for i, d in enumerate(mdates)}
    for i in range(len(episodes)):
        arr = stock_dates.get(codes[i])
        if arr is None:
            continue
        pos = np.searchsorted(arr, sig[i], side='left')
        if pos >= 20 and pos < len(arr) and arr[pos] == sig[i]:
            obs20 = arr[pos - 20]
            span[i] = m_idx.get(sig[i], np.searchsorted(mdates, sig[i], side='right')) - \
                      m_idx.get(obs20, np.searchsorted(mdates, obs20, side='right'))
    return span


def main():
    t0 = time.time()
    pred = build_predictor_frame().set_index(['ts_code', 'date'])
    fm = pd.read_csv(os.path.join(REPO, 'results', 'fullmarket_episode_metrics.csv'))
    fm['signal_date'] = pd.to_datetime(fm['signal_date'])
    disc = fm[(fm['signal_date'] >= DIS_START) & (fm['signal_date'] <= DIS_END)].copy()
    disc = disc.join(pred, on=['ts_code', 'signal_date'], how='left')
    from market_state_gate_t3 import build_feat_state
    disc['r01'] = disc['signal_date'].map(build_feat_state()['r01'])

    # suspension gap audit (point 7)
    disc['gap_span'] = build_gap_flags(disc)
    disc['gap_20'] = disc['gap_span'] > 20
    n_gap = int(disc['gap_20'].sum()); n_tot = len(disc)
    print(f'[gap] episodes={n_tot}, gap(span>20)={n_gap} ({n_gap/n_tot*100:.2f}%) ({time.time()-t0:.0f}s)', flush=True)
    gap_audit_rows = [dict(metric='all_episodes', n_episodes=n_tot, n_gap=n_gap, gap_pct=round(n_gap/n_tot*100, 3))]
    for f in ['F04', 'F05', 'F06', 'F07', 'F09', 'F13']:
        sub = disc[disc[PREDS[FIDS.index(f)][3]].notna()]
        ng = int(sub['gap_20'].sum()); nn = len(sub)
        gap_audit_rows.append(dict(metric=f, n_episodes=nn, n_gap=ng, gap_pct=round(ng/nn*100, 3) if nn else np.nan))
    pd.DataFrame(gap_audit_rows).to_csv(os.path.join(OUT, 'p11_suspension_gap_audit.csv'), index=False)

    # ---- per-day data ----
    day_eps, day_dates, day_n, day_r01, day_allm = [], [], [], [], []
    for d, dd in disc.groupby('signal_date'):
        day_eps.append(dd); day_dates.append(d); day_n.append(len(dd))
        r01 = dd['r01'].iloc[0]
        day_r01.append(float(r01) if np.isfinite(r01) else np.nan)
        day_allm.append(float(dd['simple_return_pct'].mean()))
    ND = len(day_dates)
    print(f'[days] {ND} signal days, episodes={sum(day_n)}', flush=True)

    # pass A
    ic_series = {f: [] for f in FIDS}; ic_dates = {f: [] for f in FIDS}
    year_ic = {f: {y: [] for y in YEARS} for f in FIDS}
    qday = {f: {q: {'m': [], 'wr': []} for q in range(1, 6)} for f in FIDS}
    qep = {f: {q: [] for q in range(1, 6)} for f in FIDS}
    pair_n = {f: 0 for f in FIDS}; pair_ok = {f: 0 for f in FIDS}; pair_ties = {f: 0 for f in FIDS}
    oracle = {k: [] for k in (1, 3, 5, 10)}
    bucket_exc = {b: [] for b in ['A_TOP10', 'B_11_50', 'C_51_200', 'D_201_500', 'E_gt500']}
    bucket_n = {b: 0 for b in ['A_TOP10', 'B_11_50', 'C_51_200', 'D_201_500', 'E_gt500']}
    crowd_ic = {f: {0: [], 1: [], 2: []} for f in FIDS}
    r01b_ic = {f: {0: [], 1: [], 2: []} for f in FIDS}
    n_arr = np.array(day_n)
    crowd_cut = np.percentile(n_arr, [33.33, 66.67]); crowd_lab = np.digitize(n_arr, crowd_cut, right=False)
    r01_arr = np.array(day_r01); m = np.isfinite(r01_arr)
    r01_cut = np.percentile(r01_arr[m], [33.33, 66.67]); r01_lab = np.full(ND, np.nan); r01_lab[m] = np.digitize(r01_arr[m], r01_cut, right=False)

    for i in range(ND):
        dd = day_eps[i]; ret = dd['simple_return_pct'].to_numpy(float); am = day_allm[i]; yr = day_dates[i].year
        for f in FIDS:
            x = dd[PREDS[FIDS.index(f)][3]].to_numpy(float)
            valid = np.isfinite(x) & np.isfinite(ret)
            if valid.sum() >= MIN_SIG:
                ic = spearman(x, ret)
                if np.isfinite(ic):
                    ic_series[f].append(ic); ic_dates[f].append(day_dates[i]); year_ic[f][yr].append(ic)
                    crowd_ic[f][crowd_lab[i]].append(ic)
                    if np.isfinite(r01_lab[i]):
                        r01b_ic[f][int(r01_lab[i])].append(ic)
                xv = x[valid]; rv = ret[valid]; nv = len(xv)
                ql = np.clip(np.ceil(stats.rankdata(xv) / nv * 5).astype(int), 1, 5)
                for q in range(1, 6):
                    mm = ql == q
                    if mm.sum():
                        qday[f][q]['m'].append(rv[mm].mean())
                        qday[f][q]['wr'].append((rv[mm] > 0).mean() * 100)
                        qep[f][q].extend(rv[mm].tolist())
                n_pairs = nv * (nv - 1) // 2
                if n_pairs:
                    if n_pairs > PAIR_CAP:
                        all_pairs = np.array([(a, b) for a in range(nv) for b in range(a + 1, nv)])
                        sel = RNG.choice(len(all_pairs), size=PAIR_CAP, replace=False)
                        pairs = all_pairs[sel]
                    else:
                        pairs = np.array([(a, b) for a in range(nv) for b in range(a + 1, nv)])
                    dx = xv[pairs[:, 0]] - xv[pairs[:, 1]]; dr = rv[pairs[:, 0]] - rv[pairs[:, 1]]
                    ok = (dx != 0) & (dr != 0)
                    pair_ties[f] += int(len(pairs) - ok.sum())
                    pair_n[f] += int(ok.sum())
                    pair_ok[f] += int((np.sign(dx[ok]) == np.sign(dr[ok])).sum())
        if day_n[i] >= 3:
            r = ret
            for k in (1, 3, 5, 10):
                if len(r) >= k:
                    oracle[k].append(r[np.argsort(-r)[:k]].mean())
        for b, (lo, hi) in {'A_TOP10': (0, 10), 'B_11_50': (11, 50), 'C_51_200': (51, 200),
                            'D_201_500': (201, 500), 'E_gt500': (501, 10**9)}.items():
            mm = (dd['turnover_rank'] >= lo) & (dd['turnover_rank'] <= hi)
            if mm.sum():
                bucket_exc[b].append(float(ret[mm.to_numpy()].mean()) - am); bucket_n[b] += int(mm.sum())
    print(f'[pass A] ({time.time()-t0:.0f}s)', flush=True)

    mean_ic = {f: float(np.mean(ic_series[f])) if ic_series[f] else np.nan for f in FIDS}
    dirn = {}
    for f in FIDS:
        exp = PREDS[FIDS.index(f)][4]
        dirn[f] = 1.0 if exp == 'POSITIVE' else (-1.0 if exp == 'NEGATIVE' else (1.0 if mean_ic[f] >= 0 else -1.0))

    # pass B: oriented topK + K3 lift
    topk_orient = {f: {k: [] for k in (1, 3, 5, 10)} for f in FIDS}
    k3_lift_day = {f: [] for f in FIDS}
    for i in range(ND):
        dd = day_eps[i]; ret = dd['simple_return_pct'].to_numpy(float)
        for f in FIDS:
            x = dd[PREDS[FIDS.index(f)][3]].to_numpy(float)
            valid = np.isfinite(x) & np.isfinite(ret)
            if valid.sum() < 3:
                continue
            xv = x[valid]; rv = ret[valid]
            o = np.argsort(-xv) if dirn[f] > 0 else np.argsort(xv)
            for k in (1, 3, 5, 10):
                if len(o) >= k:
                    topk_orient[f][k].append(rv[o[:k]].mean())
            k3_lift_day[f].append(rv[o[:3]].mean() - float(rv.mean()))

    # random K3 WITHOUT replacement, same usable-day set (point 2/10)
    usable = [i for i in range(ND) if day_n[i] >= 3]
    rand_k3 = np.full(RANDOM_B, np.nan)
    for b in range(RANDOM_B):
        s = 0.0
        for i in usable:
            r = day_eps[i]['simple_return_pct'].to_numpy(float)
            s += r[RNG.choice(len(r), size=3, replace=False)].mean()
        rand_k3[b] = s / len(usable)
    rand_mu = float(rand_k3.mean()); rand_lo, rand_hi = float(np.percentile(rand_k3, 2.5)), float(np.percentile(rand_k3, 97.5))
    allm_usable = float(np.mean([day_allm[i] for i in usable]))
    print(f'[random K3 (no-replace)] mean={rand_mu:.4f}pp ({rand_lo:.4f},{rand_hi:.4f}) usable-day all mean={allm_usable:.4f}pp', flush=True)
    orc_mu = {k: float(np.mean(oracle[k])) for k in (1, 3, 5, 10)}
    print(f'[oracle] K1={orc_mu[1]:.3f} K3={orc_mu[3]:.3f} K5={orc_mu[5]:.3f} K10={orc_mu[10]:.3f} lift K3={orc_mu[3]-allm_usable:.3f}pp', flush=True)

    # master table with corrected gates
    rawp = np.array([np.nan if not ic_series[f] else nw_mean_t(ic_series[f], HAC_LAG)[3] for f in FIDS], float)
    qs = bh_fdr(rawp)
    rows = []
    for f in FIDS:
        s = np.array(ic_series[f]); nd = len(s)
        mu, se, t, p = nw_mean_t(s, HAC_LAG) if nd else (np.nan,)*4
        # block bootstrap with centering sanity
        pe, bmean, clo, chi = block_boot_mean_ci_full(s) if nd else (np.nan,)*4
        raw_agree = pair_ok[f] / pair_n[f] * 100 if pair_n[f] else np.nan
        pair_a = raw_agree if dirn[f] > 0 else (100 - raw_agree)
        tk3 = np.array(k3_lift_day[f]); k3l = float(tk3.mean()) if len(tk3) else np.nan
        k3_pe, k3_bm, k3c_lo, k3c_hi = block_boot_mean_ci_full(tk3) if len(tk3) else (np.nan,)*4
        k3m = float(np.mean(topk_orient[f][3])) if topk_orient[f][3] else np.nan
        pct = float((rand_k3 < k3m).mean() * 100) if np.isfinite(k3m) else np.nan
        delta = (k3m - rand_mu) if np.isfinite(k3m) else np.nan
        yic = {y: float(np.mean(year_ic[f][y])) if year_ic[f][y] else np.nan for y in YEARS}
        dsign = np.sign(mu) if np.isfinite(mu) else 0
        yrs = [y for y in YEARS if np.isfinite(yic[y])]
        same = sum(1 for y in yrs if np.sign(yic[y]) == dsign) if dsign != 0 else 0
        rev = any(np.sign(yic[y]) != dsign and abs(yic[y]) >= G_REVY for y in yrs) if dsign != 0 else True
        exp = PREDS[FIDS.index(f)][4]
        dir_ok = True if exp == 'UNKNOWN' else (np.sign(mu) == (1 if exp == 'POSITIVE' else -1) if np.isfinite(mu) else False)
        bh_q = float(qs[FIDS.index(f)])
        gate = dict(A=bool(np.isfinite(bh_q) and bh_q < 0.05), B=bool(np.isfinite(mu) and abs(mu) >= G_MIN_IC),
                    C=bool(np.isfinite(pair_a) and pair_a >= G_PAIR), D=bool(np.isfinite(k3l) and k3l >= G_K3),
                    E=bool(np.isfinite(k3c_lo) and k3c_lo > 0), F=bool(same >= 2 and not rev))
        rows.append(dict(feature_id=f, family=PREDS[FIDS.index(f)][1], name=PREDS[FIDS.index(f)][2],
                         expected_direction=exp, disc_direction='POSITIVE' if dirn[f] > 0 else 'NEGATIVE',
                         direction_matches_registry=bool(dir_ok),
                         n_days=nd, mean_ic=mu, median_ic=float(np.median(s)) if nd else np.nan,
                         pos_frac=float((s > 0).mean()) if nd else np.nan,
                         hac_t=t, raw_p=p, bh_q=bh_q,
                         ic_boot_point=pe, ic_boot_mean=bmean, ic_ci_lo=clo, ic_ci_hi=chi,
                         pairwise_n=pair_n[f], pairwise_ties=pair_ties[f], pairwise_acc=pair_a,
                         K3_lift_pp=k3l, K3_lift_boot_point=k3_pe, K3_lift_boot_mean=k3_bm,
                         K3_lift_ci_lo=k3c_lo, K3_lift_ci_hi=k3c_hi,
                         K3_mean_pp=k3m, random_K3_pctile=pct, delta_vs_random_pp=delta,
                         ic_2020=yic[2020], ic_2021=yic[2021], ic_2022=yic[2022],
                         gateA_bh_q=gate['A'], gateB=gate['B'], gateC=gate['C'], gateD=gate['D'], gateE=gate['E'], gateF=gate['F'],
                         DISCOVERY_PASS=bool(all(gate.values()) and dir_ok)))
    mdf = pd.DataFrame(rows)
    mdf.to_csv(os.path.join(OUT, 'p11_master_table.csv'), index=False)
    print(mdf[['feature_id', 'name', 'mean_ic', 'bh_q', 'pairwise_acc', 'K3_lift_pp', 'DISCOVERY_PASS']].round(3).to_string())

    # old-new pass diff (point 1)
    old_pass = ['F04', 'F06', 'F07', 'F09', 'F13']
    new_pass = mdf[mdf['DISCOVERY_PASS']]['feature_id'].tolist()
    pd.DataFrame([dict(feature_id=f, OLD_PASS=f in old_pass, NEW_PASS=f in new_pass,
                       changed=(f in old_pass) != (f in new_pass)) for f in FIDS]).to_csv(
        os.path.join(OUT, 'p11_old_new_pass_diff.csv'), index=False)
    print(f'OLD_PASS={old_pass} NEW_PASS={new_pass}')

    # corrected random K3 CSV + baseline comparison (point 2)
    pd.DataFrame([dict(b=b, random_k3_mean_pp=rand_k3[b]) for b in range(RANDOM_B)]).to_csv(
        os.path.join(OUT, 'p11_random_k3_corrected.csv'), index=False)
    pd.DataFrame([dict(stat='random_K3_mean', value=rand_mu), dict(stat='random_K3_lo', value=rand_lo),
                  dict(stat='random_K3_hi', value=rand_hi), dict(stat='usable_day_all_mean', value=allm_usable),
                  dict(stat='oracle_K3_mean', value=orc_mu[3]), dict(stat='oracle_K3_lift_pp', value=orc_mu[3]-allm_usable)]).to_csv(
        os.path.join(OUT, 'p11_random_baseline_comparison.csv'), index=False)

    # pairwise csv (point 4)
    pd.DataFrame([dict(feature_id=f, n_pairs=pair_n[f], ties_excluded=pair_ties[f],
                       oriented_accuracy_pct=(pair_ok[f]/pair_n[f]*100 if dirn[f] > 0 and pair_n[f] else (pair_n[f]-pair_ok[f])/pair_n[f]*100 if pair_n[f] else np.nan),
                       disc_direction='POSITIVE' if dirn[f] > 0 else 'NEGATIVE') for f in FIDS]).to_csv(
        os.path.join(OUT, 'p11_pairwise.csv'), index=False)

    # k3 bootstrap csv (point 3)
    pd.DataFrame([dict(feature_id=f, K3_lift_point=rows[i]['K3_lift_pp'], K3_lift_boot_mean=rows[i]['K3_lift_boot_mean'],
                       K3_lift_ci_lo=rows[i]['K3_lift_ci_lo'], K3_lift_ci_hi=rows[i]['K3_lift_ci_hi'],
                       centering_diff=rows[i]['K3_lift_boot_mean']-rows[i]['K3_lift_pp'])
                  for i, f in enumerate(FIDS)]).to_csv(os.path.join(OUT, 'p11_k3_bootstrap.csv'), index=False)

    # passer redundancy 5x5 (point 8)
    passers = new_pass if new_pass else ['F04', 'F06', 'F07', 'F09', 'F13']
    corr_sum = {a: {b: 0.0 for b in passers} for a in passers}
    corr_n = {a: {b: 0 for b in passers} for a in passers}
    for i in range(ND):
        dd = day_eps[i]
        for a in passers:
            xa = dd[PREDS[FIDS.index(a)][3]].to_numpy(float)
            for b in passers:
                rho = spearman(xa, dd[PREDS[FIDS.index(b)][3]].to_numpy(float))
                if np.isfinite(rho):
                    corr_sum[a][b] += rho; corr_n[a][b] += 1
    red_rows = []
    for a in passers:
        for b in passers:
            red_rows.append(dict(pred_a=a, pred_b=b,
                                 avg_same_day_rank_corr=(corr_sum[a][b]/corr_n[a][b] if corr_n[a][b] else np.nan),
                                 n_days=corr_n[a][b]))
    pd.DataFrame(red_rows).to_csv(os.path.join(OUT, 'p11_passer_redundancy.csv'), index=False)

    # quintile metrics (point 9)
    q_rows = []
    for f in FIDS:
        for q in range(1, 6):
            dm = np.array(qday[f][q]['m']); dw = np.array(qday[f][q]['wr']); ep = np.array(qep[f][q])
            q_rows.append(dict(feature_id=f, quintile=q, n_days=len(dm), n_episodes=len(ep),
                               equal_day_mean_return_pct=float(dm.mean()) if len(dm) else np.nan,
                               positive_day_fraction=float((dm > 0).mean()) if len(dm) else np.nan,
                               equal_day_mean_episode_win_rate_pct=float(dw.mean()) if len(dw) else np.nan,
                               episode_weighted_mean_return_pct=float(ep.mean()) if len(ep) else np.nan,
                               episode_weighted_win_rate_pct=float((ep > 0).mean() * 100) if len(ep) else np.nan))
    pd.DataFrame(q_rows).to_csv(os.path.join(OUT, 'p11_quintile_metrics.csv'), index=False)

    # oracle csv (point 10)
    pd.DataFrame([dict(K=k, oracle_mean_pct=orc_mu[k], oracle_lift_vs_usable_all_pp=orc_mu[k]-allm_usable,
                       random_K3_mean_pct=rand_mu, usable_day_all_mean_pct=allm_usable) for k in (1, 3, 5, 10)]).to_csv(
        os.path.join(OUT, 'p11_oracle.csv'), index=False)

    # turnover diagnostic (point 11)
    pd.DataFrame([dict(bucket=b, n_episodes=bucket_n[b],
                       equal_day_excess_pp=float(np.mean(bucket_exc[b])) if bucket_exc[b] else np.nan)
                  for b in ['A_TOP10', 'B_11_50', 'C_51_200', 'D_201_500', 'E_gt500']]).to_csv(
        os.path.join(OUT, 'p11_turnover_rank_diagnostic.csv'), index=False)

    # PRIMARY pooled direction sensitivity (point 6)
    with open(os.path.join(REPO, 'results', 'independent_v2a_episodes.pkl'), 'rb') as fh:
        import pickle
        pp = pickle.load(fh)['episodes']
    ppr = pd.DataFrame(pp)
    ppr['signal_date'] = pd.to_datetime(ppr['signal_date'])
    ppr = ppr[(ppr['signal_date'] >= DIS_START) & (ppr['signal_date'] <= DIS_END)]
    ppr = ppr.join(pred, on=['ts_code', 'signal_date'], how='left')
    prow = []
    for f in FIDS:
        x = ppr[PREDS[FIDS.index(f)][3]].to_numpy(float); y = ppr['return_pct'].to_numpy(float)
        ic = spearman(x, y)
        msk = np.isfinite(x) & np.isfinite(y)
        prow.append(dict(feature_id=f, n_episodes=int(msk.sum()), n_signal_days=int(ppr.loc[msk, 'signal_date'].nunique()),
                         pooled_spearman=ic, disc_direction=('POSITIVE' if dirn[f] > 0 else 'NEGATIVE'),
                         direction_match=bool(np.sign(ic) == np.sign(dirn[f]) if np.isfinite(ic) else False)))
    pd.DataFrame(prow).to_csv(os.path.join(OUT, 'p11_primary_direction_sensitivity.csv'), index=False)

    # suspension sensitivity (point 7): recompute for passers on non-gap subset
    sens = []
    for f in passers:
        sub = disc[(disc[PREDS[FIDS.index(f)][3]].notna()) & (~disc['gap_20'])].copy()
        # daily IC over non-gap subset
        ics = []
        for d, dd in sub.groupby('signal_date'):
            x = dd[PREDS[FIDS.index(f)][3]].to_numpy(float); r = dd['simple_return_pct'].to_numpy(float)
            v = np.isfinite(x) & np.isfinite(r)
            if v.sum() >= MIN_SIG:
                icv = spearman(x, r)
                if np.isfinite(icv):
                    ics.append(icv)
        s = np.array(ics)
        mu = nw_mean_t(s, HAC_LAG)[0] if len(s) else np.nan
        # pairwise oriented on subset
        pk = 0; pn = 0
        for d, dd in sub.groupby('signal_date'):
            x = dd[PREDS[FIDS.index(f)][3]].to_numpy(float); r = dd['simple_return_pct'].to_numpy(float)
            v = np.isfinite(x) & np.isfinite(r)
            if v.sum() >= 2:
                xv = x[v]; rv = r[v]; nv = len(xv)
                n_pairs = nv*(nv-1)//2
                if n_pairs:
                    if n_pairs > PAIR_CAP:
                        ap = np.array([(a,b) for a in range(nv) for b in range(a+1,nv)])
                        sel = RNG.choice(len(ap), size=PAIR_CAP, replace=False); pairs = ap[sel]
                    else:
                        pairs = np.array([(a,b) for a in range(nv) for b in range(a+1,nv)])
                    dx = xv[pairs[:,0]]-xv[pairs[:,1]]; dr = rv[pairs[:,0]]-rv[pairs[:,1]]
                    ok = (dx!=0)&(dr!=0)
                    pn += int(ok.sum()); pk += int((np.sign(dx[ok])==np.sign(dr[ok])).sum())
        pacc = (pk/pn*100 if dirn[f]>0 and pn else (pn-pk)/pn*100 if pn else np.nan)
        k3l = []
        for d, dd in sub.groupby('signal_date'):
            x = dd[PREDS[FIDS.index(f)][3]].to_numpy(float); r = dd['simple_return_pct'].to_numpy(float)
            v = np.isfinite(x)&np.isfinite(r)
            if v.sum() >= 3:
                xv=x[v]; rv=r[v]
                o = np.argsort(-xv) if dirn[f]>0 else np.argsort(xv)
                k3l.append(rv[o[:3]].mean()-float(rv.mean()))
        sens.append(dict(feature_id=f, n_episodes_after=len(sub), n_days_after=len(s),
                         mean_ic_after=mu, pairwise_acc_after=pacc, K3_lift_after=float(np.mean(k3l)) if k3l else np.nan))
    pd.DataFrame(sens).to_csv(os.path.join(OUT, 'p11_suspension_sensitivity.csv'), index=False)

    print(f'[done] ({time.time()-t0:.0f}s)', flush=True)


if __name__ == '__main__':
    main()
