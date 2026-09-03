#!/usr/bin/env python3
"""
PHASE P1 — CROSS-SECTIONAL SIGNAL RANKING & SLOT-ALLOCATION DIAGNOSTIC (DISCOVERY ONLY)

Question: within the same signal date, can T-close stock-level characteristics rank the
future quality of BB-oversold signals? (signal selection / ranking, NOT market timing).

Registry preregistered & committed BEFORE this script ran:
  CROSS_SECTIONAL_RANKING_REGISTRY.csv  (17 predictors, 7 families)
  SHA256 = fa5beb5a9a952442be2a359b95347388ff082c06fa36b56cf8f6eee477bab819

Scope & red lines:
  - DISCOVERY ONLY: signal_date 2020-01-01 .. 2022-12-31 (frozen SECONDARY V2A episodes).
  - 2023-2024 Validation CLOSED; 2025-2026 Confirmation CLOSED.
  - NO portfolio backtest, NO K=3 capital path, NO slot reallocation simulation.
  - Outcome = frozen episode final simple_return_pct (realized); predictors <= signal_date.
  - PURE STOCK, no ETF.
"""
import os, sys, time
import numpy as np, pandas as pd
from scipy import stats

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
OUT = os.path.join(REPO, 'results'); os.makedirs(OUT, exist_ok=True)
FIG = os.path.join(REPO, 'figures'); os.makedirs(FIG, exist_ok=True)
sys.path.insert(0, REPO)
from market_state_phase_t2 import load_features, assemble_day_frame
from market_state_gate_t3 import build_feat_state

RNG = np.random.default_rng(20260903)   # fixed seed, frozen
DIS_START, DIS_END = pd.Timestamp('2020-01-01'), pd.Timestamp('2022-12-31')
MIN_SIG = 5
HAC_LAG = 10
BLOCK_L, BLOCK_B = 21, 2000
RANDOM_B = 5000
PAIR_CAP = 5000
G_MIN_IC, G_PAIR, G_K3, G_REVY = 0.03, 53.0, 0.5, 0.03
YEARS = (2020, 2021, 2022)

PREDS = [
    ('F01', 'OVERSOLD_DEPTH',    'BB_Z',              'bb_z',           'UNKNOWN'),
    ('F02', 'OVERSOLD_DEPTH',    'BB_LOWER_DISTANCE', 'bb_ld',          'UNKNOWN'),
    ('F03', 'SHORT_PRICE_SHOCK', 'RET1',              'ret',            'UNKNOWN'),
    ('F04', 'SHORT_PRICE_SHOCK', 'RET3',              'ret3',           'UNKNOWN'),
    ('F05', 'SHORT_PRICE_SHOCK', 'RET5',              'ret5',           'UNKNOWN'),
    ('F06', 'REVERSAL_CONTEXT',  'RET20',             'ret20',          'UNKNOWN'),
    ('F07', 'REVERSAL_CONTEXT',  'DIST_MA20',         'dist_ma20',      'UNKNOWN'),
    ('F08', 'VOLATILITY',        'STOCK_RV20',        'rv20',           'UNKNOWN'),
    ('F09', 'VOLATILITY',        'ATR20_PCT',         'atr20_pct',      'UNKNOWN'),
    ('F10', 'LIQUIDITY',         'AMOUNT',            'log_amt',        'UNKNOWN'),
    ('F11', 'LIQUIDITY',         'AMOUNT_RATIO20',    'amt_ratio20',    'UNKNOWN'),
    ('F12', 'CANDLE',            'CLOSE_LOCATION',    'close_loc',      'POSITIVE'),
    ('F13', 'CANDLE',            'INTRADAY_RANGE',    'intraday_range', 'UNKNOWN'),
    ('F14', 'CANDLE',            'GAP',               'gap',            'UNKNOWN'),
    ('F15', 'MARKET_RELATIVE',   'REL_RET1',          'rel_ret1',       'POSITIVE'),
    ('F16', 'MARKET_RELATIVE',   'REL_RET5',          'rel_ret5',       'POSITIVE'),
    ('F17', 'MARKET_RELATIVE',   'REL_RET20',         'rel_ret20',      'POSITIVE'),
]
FIDS = [p[0] for p in PREDS]
PRED_COLS = [p[3] for p in PREDS]


def nw_mean_t(x, lag):
    x = np.asarray(x, float); x = x[np.isfinite(x)]; n = len(x)
    if n < 2:
        return np.nan, np.nan, np.nan, np.nan
    mu = x.mean(); e = x - mu
    S = (e @ e) / n
    for j in range(1, lag + 1):
        w = 1 - j / (lag + 1)
        S += 2 * w * (e[j:] @ e[:-j]) / n
    se = np.sqrt(max(S, 1e-18) / n); t = mu / se; p = 2 * (1 - stats.norm.cdf(abs(t)))
    return mu, se, t, p


def bh_fdr(pvals):
    p = np.asarray(pvals, float); m = len(p)
    order = np.argsort(p); ps = p[order]
    qs = np.full(m, np.nan); cur = 1.0
    for i in range(m - 1, -1, -1):
        cur = min(cur, ps[i] * m / (i + 1)); qs[i] = cur
    q = np.empty(m); q[order] = np.clip(qs, 0, 1)
    return q


def block_boot_ci(x, L=BLOCK_L, B=BLOCK_B):
    x = np.asarray(x, float); x = x[np.isfinite(x)]; n = len(x)
    if n < 2 * L:
        return np.nan, np.nan
    boot = np.full(B, np.nan); nblk = int(np.ceil(n / L))
    for b in range(B):
        idx = []
        for _ in range(nblk):
            st = RNG.integers(0, n - L + 1) if n - L + 1 > 0 else 0
            idx.extend(range(st, min(st + L, n)))
        idx = np.array(idx[:n]); boot[b] = x[idx].mean()
    return float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))


def spearman(x, y):
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 2:
        return np.nan
    return float(stats.spearmanr(x[m], y[m])[0])


# ---------------------------------------------------------------
# 1. Per-stock predictor frame (PIT at signal_date close)
# ---------------------------------------------------------------
def build_predictor_frame():
    t0 = time.time()
    df = pd.read_parquet(os.path.join(ROOT, 'data', 'combined_daily.parquet'))
    df['date'] = pd.to_datetime(df['date'])
    pit = pd.read_parquet(os.path.join(ROOT, 'data', 'pit_st_daily.parquet'))
    pit['date'] = pd.to_datetime(pit['date'])
    df = df.merge(pit[['date', 'ts_code', 'is_st_pit']], on=['date', 'ts_code'], how='left')
    df['close_adj'] = df['close'] * df['adj_factor']
    df['ret'] = df['close'] / df['pre_close'] - 1.0
    df = df.sort_values(['ts_code', 'date']).reset_index(drop=True)
    g = df.groupby('ts_code', sort=False)
    df['ma20'] = g['close_adj'].rolling(20, min_periods=20).mean().reset_index(level=0, drop=True)
    df['sd20'] = g['close_adj'].rolling(20, min_periods=20).std().reset_index(level=0, drop=True)
    df['bb_lower'] = df['ma20'] - 2.0 * df['sd20']
    df['amt_ma20'] = g['amount'].rolling(20, min_periods=20).mean().reset_index(level=0, drop=True)
    for k in (3, 5, 20):
        df[f'ca_{k}'] = g['close_adj'].shift(k)
    df['ret3'] = df['close_adj'] / df['ca_3'] - 1.0
    df['ret5'] = df['close_adj'] / df['ca_5'] - 1.0
    df['ret20'] = df['close_adj'] / df['ca_20'] - 1.0
    df['rv20'] = g['ret'].rolling(20, min_periods=20).std().reset_index(level=0, drop=True)
    df['tr'] = np.maximum(df['high'] - df['low'],
                          np.maximum((df['high'] - df['pre_close']).abs(), (df['low'] - df['pre_close']).abs()))
    df['atr20_pct'] = g['tr'].rolling(20, min_periods=20).mean().reset_index(level=0, drop=True) / df['close']
    df['close_loc'] = (df['close'] - df['low']) / (df['high'] - df['low'])
    df['intraday_range'] = (df['high'] - df['low']) / df['pre_close']
    df['gap'] = df['open'] / df['pre_close'] - 1.0
    df['log_amt'] = np.log(df['amount'].replace(0, np.nan))
    df['amt_ratio20'] = df['amount'] / df['amt_ma20']
    df['bb_z'] = (df['close_adj'] - df['ma20']) / df['sd20']
    df['bb_ld'] = df['close_adj'] / df['bb_lower'] - 1.0
    df['dist_ma20'] = df['close_adj'] / df['ma20'] - 1.0

    # All-A EW index (identical to T2 assemble_day_frame)
    day_feats, days, offset = load_features()
    ix = assemble_day_frame(day_feats, days)
    lvl = ix['idx_level']
    ew = {k: (lvl / lvl.shift(k) - 1.0).to_dict() for k in (1, 5, 20)}
    dts = df['date'].to_numpy()
    for k in (1, 5, 20):
        col = 'rel_ret' + ('1' if k == 1 else str(k))
        base = 'ret' if k == 1 else ('ret5' if k == 5 else 'ret20')
        arr = np.array([ew[k].get(pd.Timestamp(d), np.nan) for d in dts])
        df[col] = df[base] - arr
    cols = ['ts_code', 'date'] + PRED_COLS
    print(f'[predictors] frame {df[cols].shape} ({time.time()-t0:.0f}s)', flush=True)
    return df[cols]


# ---------------------------------------------------------------
# 2. Main
# ---------------------------------------------------------------
def main():
    t0 = time.time()
    pred = build_predictor_frame().set_index(['ts_code', 'date'])

    fm = pd.read_csv(os.path.join(REPO, 'results', 'fullmarket_episode_metrics.csv'))
    fm['signal_date'] = pd.to_datetime(fm['signal_date'])
    disc = fm[(fm['signal_date'] >= DIS_START) & (fm['signal_date'] <= DIS_END)].copy()
    disc = disc.join(pred, on=['ts_code', 'signal_date'], how='left')
    for c in PRED_COLS:
        print(f'   [nan] {c}: {disc[c].isna().mean()*100:.2f}%')
    fs = build_feat_state()
    disc['r01'] = disc['signal_date'].map(fs['r01'])

    # ---- per-day data ----
    day_eps, day_dates, day_n, day_r01, day_allm = [], [], [], [], []
    for d, dd in disc.groupby('signal_date'):
        day_eps.append(dd); day_dates.append(d); day_n.append(len(dd))
        r01 = dd['r01'].iloc[0]
        day_r01.append(float(r01) if np.isfinite(r01) else np.nan)
        day_allm.append(float(dd['simple_return_pct'].mean()))
    ND = len(day_dates)
    print(f'[days] {ND} signal days, episodes={sum(day_n)} ({time.time()-t0:.0f}s)', flush=True)

    # crowding tertile cutpoints (frozen from n_signals distribution, pre-outcome)
    n_arr = np.array(day_n)
    crowd_cut = np.percentile(n_arr, [33.33, 66.67])
    crowd_lab = np.digitize(n_arr, crowd_cut, right=False)  # 0=LOW,1=MID,2=HIGH
    print(f'[crowding frozen] cut={crowd_cut} -> LOW(<={crowd_cut[0]:.0f}) MID HIGH(>{crowd_cut[1]:.0f})')
    # R01 tertile cutpoints (frozen from Discovery r01 distribution)
    r01_arr = np.array(day_r01)
    m = np.isfinite(r01_arr)
    r01_cut = np.percentile(r01_arr[m], [33.33, 66.67])
    r01_lab = np.full(ND, np.nan)
    r01_lab[m] = np.digitize(r01_arr[m], r01_cut, right=False)
    print(f'[r01 frozen] cut={r01_cut}')

    # accumulators
    ic_series = {f: [] for f in FIDS}
    ic_dates = {f: [] for f in FIDS}
    year_ic = {f: {y: [] for y in YEARS} for f in FIDS}
    qday = {f: {q: [] for q in range(1, 6)} for f in FIDS}
    qep = {f: {q: [] for q in range(1, 6)} for f in FIDS}
    pair_n = {f: 0 for f in FIDS}; pair_ok = {f: 0 for f in FIDS}
    oracle = {f: {k: [] for k in (1, 3, 5, 10)} for f in FIDS}
    bucket_exc = {b: [] for b in ['A_TOP10', 'B_11_50', 'C_51_200', 'D_201_500', 'E_gt500']}
    bucket_n = {b: 0 for b in ['A_TOP10', 'B_11_50', 'C_51_200', 'D_201_500', 'E_gt500']}
    crowd_ic = {f: {0: [], 1: [], 2: []} for f in FIDS}
    r01b_ic = {f: {0: [], 1: [], 2: []} for f in FIDS}

    for i in range(ND):
        dd = day_eps[i]; ret = dd['simple_return_pct'].to_numpy(float); am = day_allm[i]; yr = day_dates[i].year
        for f in FIDS:
            x = dd[PREDS[FIDS.index(f)][3]].to_numpy(float)
            ic = spearman(x, ret)
            if np.isfinite(ic):
                ic_series[f].append(ic); ic_dates[f].append(day_dates[i])
                year_ic[f][yr].append(ic)
                crowd_ic[f][crowd_lab[i]].append(ic)
                if np.isfinite(r01_lab[i]):
                    r01b_ic[f][int(r01_lab[i])].append(ic)
            valid = np.isfinite(x) & np.isfinite(ret)
            if valid.sum() >= MIN_SIG:
                xv = x[valid]; rv = ret[valid]; nv = len(xv)
                ql = np.clip(np.ceil(stats.rankdata(xv) / nv * 5).astype(int), 1, 5)
                for q in range(1, 6):
                    mm = ql == q
                    if mm.sum():
                        qday[f][q].append(rv[mm].mean()); qep[f][q].extend(rv[mm].tolist())
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
                    pair_n[f] += int(ok.sum())
                    pair_ok[f] += int((np.sign(dx[ok]) == np.sign(dr[ok])).sum())
                for k in (1, 3, 5, 10):
                    if nv >= k:
                        oracle[f][k].append(rv[np.argsort(-rv)[:k]].mean())
        for b, (lo, hi) in {'A_TOP10': (0, 10), 'B_11_50': (11, 50), 'C_51_200': (51, 200),
                            'D_201_500': (201, 500), 'E_gt500': (501, 10**9)}.items():
            mm = (dd['turnover_rank'] >= lo) & (dd['turnover_rank'] <= hi)
            if mm.sum():
                bucket_exc[b].append(float(ret[mm.to_numpy()].mean()) - am); bucket_n[b] += int(mm.sum())

    print(f'[pass A] done ({time.time()-t0:.0f}s)', flush=True)

    # mean daily IC -> UNKNOWN direction (registry-frozen for non-UNKNOWN; Discovery-determined for UNKNOWN)
    mean_ic = {f: float(np.mean(ic_series[f])) if ic_series[f] else np.nan for f in FIDS}
    dirn = {}
    for f in FIDS:
        exp = PREDS[FIDS.index(f)][4]
        if exp == 'POSITIVE':
            dirn[f] = 1.0
        elif exp == 'NEGATIVE':
            dirn[f] = -1.0
        else:
            dirn[f] = 1.0 if mean_ic[f] >= 0 else -1.0

    # oriented topK + K3 lift per day
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
            if dirn[f] > 0:
                o = np.argsort(-xv)
            else:
                o = np.argsort(xv)
            for k in (1, 3, 5, 10):
                if len(o) >= k:
                    topk_orient[f][k].append(rv[o[:k]].mean())
            k3_lift_day[f].append(rv[o[:3]].mean() - float(rv.mean()))

    # random K3 baseline (equal-day avg; B resamples)
    usable = [i for i in range(ND) if day_n[i] >= 3]
    rand_k3 = np.full(RANDOM_B, np.nan)
    for b in range(RANDOM_B):
        s = 0.0
        for i in usable:
            r = day_eps[i]['simple_return_pct'].to_numpy(float)
            s += r[RNG.integers(0, len(r), size=3)].mean()
        rand_k3[b] = s / len(usable)
    rand_mu = float(rand_k3.mean()); rand_lo, rand_hi = float(np.percentile(rand_k3, 2.5)), float(np.percentile(rand_k3, 97.5))
    allm_usable = float(np.mean([day_allm[i] for i in usable]))
    allm_mean = float(np.mean(day_allm))
    print(f'[random K3] mean={rand_mu:.4f}pp ({rand_lo:.4f},{rand_hi:.4f}) all-day(n>=3) mean={allm_usable:.4f}pp ({time.time()-t0:.0f}s)', flush=True)

    # ---- master table ----
    rawp = np.array([np.nan if not ic_series[f] else nw_mean_t(ic_series[f], HAC_LAG)[3] for f in FIDS], float)
    qs = bh_fdr(rawp)
    rows = []
    for f in FIDS:
        s = np.array(ic_series[f]); nd = len(s)
        mu, se, t, p = nw_mean_t(s, HAC_LAG) if nd else (np.nan,)*4
        ci_lo, ci_hi = block_boot_ci(s) if nd else (np.nan, np.nan)
        pair_a = (pair_ok[f] / pair_n[f] * 100 if pair_n[f] else np.nan)
        if dirn[f] < 0 and pair_n[f]:
            pair_a = (pair_n[f] - pair_ok[f]) / pair_n[f] * 100   # oriented: predictor ranks winner above loser
        tk3 = np.array(k3_lift_day[f]); k3l = float(tk3.mean()) if len(tk3) else np.nan
        k3c_lo, k3c_hi = block_boot_ci(tk3) if len(tk3) else (np.nan, np.nan)
        k3m = float(np.mean(topk_orient[f][3])) if topk_orient[f][3] else np.nan
        pct = float((rand_k3 < k3m).mean() * 100) if np.isfinite(k3m) else np.nan
        delta = (k3m - rand_mu) if np.isfinite(k3m) else np.nan
        orc3 = float(np.mean(oracle[f][3])) if oracle[f][3] else np.nan
        yic = {y: float(np.mean(year_ic[f][y])) if year_ic[f][y] else np.nan for y in YEARS}
        dsign = np.sign(mu) if np.isfinite(mu) else 0
        yrs = [y for y in YEARS if np.isfinite(yic[y])]
        same = sum(1 for y in yrs if np.sign(yic[y]) == dsign) if dsign != 0 else 0
        rev = any(np.sign(yic[y]) != dsign and abs(yic[y]) >= G_REVY for y in yrs) if dsign != 0 else True
        gate = dict(A=bool(np.isfinite(p) and p < 0.05), B=bool(np.isfinite(mu) and abs(mu) >= G_MIN_IC),
                    C=bool(np.isfinite(pair_a) and pair_a >= G_PAIR), D=bool(np.isfinite(k3l) and k3l >= G_K3),
                    E=bool(np.isfinite(k3c_lo) and k3c_lo > 0), F=bool(same >= 2 and not rev))
        # direction_matches_registry: for non-UNKNOWN, observed IC sign must agree with registry; UNKNOWN is set by Discovery
        exp = PREDS[FIDS.index(f)][4]
        if exp == 'UNKNOWN':
            dir_ok = True
        else:
            obs_sign = np.sign(mu) if np.isfinite(mu) else 0
            dir_ok = (obs_sign == (1 if exp == 'POSITIVE' else -1))
        rows.append(dict(feature_id=f, family=PREDS[FIDS.index(f)][1], name=PREDS[FIDS.index(f)][2],
                         expected_direction=exp,
                         disc_direction='POSITIVE' if dirn[f] > 0 else 'NEGATIVE',
                         direction_matches_registry=bool(dir_ok),
                         n_days=nd, mean_ic=mu, median_ic=float(np.median(s)) if nd else np.nan,
                         pos_frac=float((s > 0).mean()) if nd else np.nan,
                         hac_t=t, raw_p=p, bh_q=float(qs[FIDS.index(f)]),
                         ic_ci_lo=ci_lo, ic_ci_hi=ci_hi,
                         pairwise_acc=pair_a, pairwise_n=pair_n[f],
                         K3_lift_pp=k3l, K3_lift_ci_lo=k3c_lo, K3_lift_ci_hi=k3c_hi,
                         K3_mean_pp=k3m, random_K3_pctile=pct, delta_vs_random_pp=delta,
                         oracle_K3_lift_pp=(orc3 - allm_usable) if np.isfinite(orc3) else np.nan,
                         ic_2020=yic[2020], ic_2021=yic[2021], ic_2022=yic[2022],
                         gateA=gate['A'], gateB=gate['B'], gateC=gate['C'], gateD=gate['D'], gateE=gate['E'], gateF=gate['F'],
                         DISCOVERY_PASS=bool(all(gate.values()) and dir_ok)))
    mdf = pd.DataFrame(rows)
    mdf.to_csv(os.path.join(OUT, 'p1_master_table.csv'), index=False)
    print(mdf[['feature_id', 'name', 'mean_ic', 'bh_q', 'pairwise_acc', 'K3_lift_pp', 'DISCOVERY_PASS']].round(3).to_string())

    # ---- side outputs ----
    # daily IC per predictor
    rows = []
    for f in FIDS:
        for v, d in zip(ic_series[f], ic_dates[f]):
            rows.append(dict(feature_id=f, date=d, daily_cs_ic=v))
    pd.DataFrame(rows).to_csv(os.path.join(OUT, 'p1_feature_daily_ic.csv'), index=False)

    # quintiles equal-day vs episode-weighted
    rows_eq, rows_ep = [], []
    for f in FIDS:
        for q in range(1, 6):
            dm = np.array(qday[f][q]); ep = np.array(qep[f][q])
            rows_eq.append(dict(feature_id=f, quintile=q, n_days=len(dm),
                                mean_return_pct=float(dm.mean()) if len(dm) else np.nan,
                                median_return_pct=float(np.median(dm)) if len(dm) else np.nan,
                                win_rate_pct=float((dm > 0).mean() * 100) if len(dm) else np.nan))
            rows_ep.append(dict(feature_id=f, quintile=q, n_episodes=len(ep),
                                mean_return_pct=float(ep.mean()) if len(ep) else np.nan,
                                median_return_pct=float(np.median(ep)) if len(ep) else np.nan,
                                win_rate_pct=float((ep > 0).mean() * 100) if len(ep) else np.nan))
    pd.DataFrame(rows_eq).to_csv(os.path.join(OUT, 'p1_quintiles_equalday.csv'), index=False)
    pd.DataFrame(rows_ep).to_csv(os.path.join(OUT, 'p1_quintiles_episodeweighted.csv'), index=False)

    # pairwise accuracy per predictor (pooled) + by year
    pd.DataFrame([dict(feature_id=f, n_pairs=pair_n[f],
                       pairwise_accuracy_oriented_pct=(pair_ok[f] / pair_n[f] * 100 if pair_n[f] else np.nan),
                       pairwise_accuracy_pct=(pair_ok[f] / pair_n[f] * 100 if dirn[f] > 0 and pair_n[f] else (pair_n[f] - pair_ok[f]) / pair_n[f] * 100 if pair_n[f] else np.nan))
                  for f in FIDS]).to_csv(
        os.path.join(OUT, 'p1_pairwise_accuracy.csv'), index=False)

    # topk selection per predictor
    rows = []
    for f in FIDS:
        for k in (1, 3, 5, 10):
            arr = topk_orient[f][k]
            rows.append(dict(feature_id=f, K=k, n_days=len(arr),
                             topk_mean_pct=float(np.mean(arr)) if arr else np.nan,
                             lift_vs_all_pp=(float(np.mean(arr)) - allm_usable) if arr else np.nan))
    pd.DataFrame(rows).to_csv(os.path.join(OUT, 'p1_topk_selection.csv'), index=False)

    # random K3 baseline
    pd.DataFrame([dict(b=b, random_k3_mean_pp=rand_k3[b]) for b in range(RANDOM_B)]).to_csv(
        os.path.join(OUT, 'p1_random_k3.csv'), index=False)

    # oracle upper bound (hindsight)
    rows = []
    for f in FIDS:
        for k in (1, 3, 5, 10):
            arr = oracle[f][k]
            rows.append(dict(feature_id=f, K=k, n_days=len(arr),
                             oracle_mean_pct=float(np.mean(arr)) if arr else np.nan,
                             oracle_lift_vs_all_pp=(float(np.mean(arr)) - allm_usable) if arr else np.nan))
    pd.DataFrame(rows).to_csv(os.path.join(OUT, 'p1_oracle_upper_bound.csv'), index=False)

    # turnover rank diagnostic (equal-day excess)
    pd.DataFrame([dict(bucket=b, n_episodes=bucket_n[b],
                       equal_day_excess_pp=float(np.mean(bucket_exc[b])) if bucket_exc[b] else np.nan)
                  for b in ['A_TOP10', 'B_11_50', 'C_51_200', 'D_201_500', 'E_gt500']]).to_csv(
        os.path.join(OUT, 'p1_turnover_rank_diagnostic.csv'), index=False)

    # crowding sensitivity
    rows = []
    for f in FIDS:
        for c, lab in [(0, 'LOW'), (1, 'MID'), (2, 'HIGH')]:
            a = crowd_ic[f][c]
            rows.append(dict(feature_id=f, crowding=lab, n_days=len(a),
                             mean_cs_ic=float(np.mean(a)) if a else np.nan))
    pd.DataFrame(rows).to_csv(os.path.join(OUT, 'p1_crowding_sensitivity.csv'), index=False)

    # market-state (R01) sensitivity
    rows = []
    for f in FIDS:
        for c, lab in [(0, 'LOW'), (1, 'MID'), (2, 'HIGH')]:
            a = r01b_ic[f][c]
            rows.append(dict(feature_id=f, r01_tertile=lab, n_days=len(a),
                             mean_cs_ic=float(np.mean(a)) if a else np.nan))
    pd.DataFrame(rows).to_csv(os.path.join(OUT, 'p1_marketstate_sensitivity.csv'), index=False)

    # yearly
    rows = []
    for f in FIDS:
        for y in YEARS:
            a = year_ic[f][y]
            rows.append(dict(feature_id=f, year=y, n_days=len(a),
                             mean_cs_ic=float(np.mean(a)) if a else np.nan))
    pd.DataFrame(rows).to_csv(os.path.join(OUT, 'p1_yearly.csv'), index=False)

    # redundancy: equal-day average of pairwise cross-sectional rank correlation
    f_cols = {f: PREDS[FIDS.index(f)][3] for f in FIDS}
    corr_sum = {f: {g: 0.0 for g in FIDS} for f in FIDS}
    corr_n = {f: {g: 0 for g in FIDS} for f in FIDS}
    for i in range(ND):
        dd = day_eps[i]
        for a in FIDS:
            xa = dd[f_cols[a]].to_numpy(float)
            for b in FIDS:
                xb = dd[f_cols[b]].to_numpy(float)
                rho = spearman(xa, xb)
                if np.isfinite(rho):
                    corr_sum[a][b] += rho; corr_n[a][b] += 1
    rows = []
    for a in FIDS:
        for b in FIDS:
            if a < b:
                rows.append(dict(pred_a=a, pred_b=b,
                                 avg_cross_sectional_rank_corr=(corr_sum[a][b] / corr_n[a][b] if corr_n[a][b] else np.nan),
                                 n_days=corr_n[a][b],
                                 redundant=bool(corr_n[a][b] and abs(corr_sum[a][b] / corr_n[a][b]) > 0.8)))
    pd.DataFrame(rows).to_csv(os.path.join(OUT, 'p1_redundancy.csv'), index=False)

    # PRIMARY sensitivity (frozen 299, Discovery subset)
    with open(os.path.join(REPO, 'results', 'independent_v2a_episodes.pkl'), 'rb') as fh:
        import pickle
        pp = pickle.load(fh)['episodes']
    ppr = pd.DataFrame(pp)
    ppr['signal_date'] = pd.to_datetime(ppr['signal_date'])
    ppr = ppr[(ppr['signal_date'] >= DIS_START) & (ppr['signal_date'] <= DIS_END)]
    ppr = ppr.join(pred, on=['ts_code', 'signal_date'], how='left')
    rows = []
    for f in FIDS:
        x = ppr[PREDS[FIDS.index(f)][3]].to_numpy(float); y = ppr['return_pct'].to_numpy(float)
        ic = spearman(x, y)
        m = np.isfinite(x) & np.isfinite(y)
        ndays = ppr.loc[m, 'signal_date'].nunique()
        rows.append(dict(feature_id=f, primary_n_episodes=int(m.sum()), primary_signal_days=int(ndays),
                         primary_cs_ic=ic, disc_direction=('POSITIVE' if dirn[f] > 0 else 'NEGATIVE')))
    p1_primary = pd.DataFrame(rows)
    p1_primary.to_csv(os.path.join(OUT, 'p1_primary_sensitivity.csv'), index=False)

    print(f'[all outputs] ({time.time()-t0:.0f}s)', flush=True)
    print(f'DISCOVERY_PASS count: {int(mdf["DISCOVERY_PASS"].sum())}')
    print('PASS details:')
    print(mdf[mdf['DISCOVERY_PASS']][['feature_id', 'name', 'mean_ic', 'bh_q', 'pairwise_acc', 'K3_lift_pp']].round(3).to_string())


if __name__ == '__main__':
    main()
