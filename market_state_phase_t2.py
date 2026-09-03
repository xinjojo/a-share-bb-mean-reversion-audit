"""
==========================================================
PHASE T2 — MARKET-STATE EXPLANATION & PROSPECTIVE PREDICTABILITY
STRICT_C / FROZEN TEMPORAL CLUSTERS — Discovery-only audit
==========================================================
Registry preregistered & committed BEFORE this script ran:
  TEMPORAL_STATE_FEATURE_REGISTRY.csv  (27 features, 7 families)
  SHA256 = b6860158c25e694546d0b625180d01543b5e17d9f1a9639af7a8f374cf0c8407

Scope:
  - DISCOVERY ONLY (signal days 2020-01-01..2022-12-31) for all inference/gates.
  - VALIDATION 2023-2024 and RETROSPECTIVE CONFIRMATION 2025-2026 NOT opened.
  - Prospective outcomes Y5/Y10/Y20/Y40 are FULLY WITHIN Discovery (future signal
    days must also fall in Discovery; no 2023+ episode return enters Discovery Y*).
  - No composite regime, no filter, no ML, no threshold search.
  - Old 104-cell HYPOTHESIS_REGISTRY untouched.
==========================================================
"""
import os, sys, hashlib, time
import numpy as np, pandas as pd
from scipy import stats

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
OUT = os.path.join(REPO, 'results'); os.makedirs(OUT, exist_ok=True)
FIG = os.path.join(REPO, 'figures'); os.makedirs(FIG, exist_ok=True)
RNG = np.random.default_rng(7)

DIS_START, DIS_END = pd.Timestamp('2020-01-01'), pd.Timestamp('2022-12-31')
HAC_LAG_PRIMARY = 20
HAC_LAGS_SENS = [5, 10, 40]
BLOCK_L, BLOCK_B = 21, 2000
PIT_MIN_HIST = 100
LYO_YEARS = [2020, 2021, 2022]
SPREAD_PP_GATE = 1.0
AUC_GATE = 0.60
BAD_RATE_RATIO_GATE = 1.5

# expected direction sign: +1 = higher X -> better future; -1 = worse; None = UNKNOWN
DIRSIGN = {'POSITIVE': 1, 'POSITIVE_WEAK': 1, 'NEGATIVE': -1, 'UNKNOWN': None}
BEAR = {'POSITIVE': -1, 'POSITIVE_WEAK': -1, 'NEGATIVE': 1, 'UNKNOWN': 1}


# ---------------------------------------------------------------
# 1. Load + feature construction (per trading day)
# ---------------------------------------------------------------
def load_features():
    t0 = time.time()
    df = pd.read_parquet(os.path.join(ROOT, 'data', 'combined_daily.parquet'))
    df['date'] = pd.to_datetime(df['date'])
    df = df[(df['date'] >= '2020-01-01') & (df['date'] <= '2026-08-25')].copy()
    pit = pd.read_parquet(os.path.join(ROOT, 'data', 'pit_st_daily.parquet'))
    pit['date'] = pd.to_datetime(pit['date'])
    df = df.merge(pit[['date', 'ts_code', 'is_st_pit']], on=['date', 'ts_code'], how='left')
    df['is_st'] = df['is_st_pit'].fillna(False)
    df['close_adj'] = df['close'] * df['adj_factor']
    df['ret'] = df['close'] / df['pre_close'] - 1.0
    # limit rules (frozen engine semantics, prepare_v51)
    is_chi = df['ts_code'].str.startswith(('688', '689'))
    is_gem = df['ts_code'].str.startswith('30')
    gem_pct = np.where(df['date'] >= '2020-08-24', 0.20, 0.10)
    pct = np.where(is_chi, 0.20, np.where(is_gem, gem_pct, np.where(df['is_st'], 0.05, 0.10)))
    df['limit_up_px'] = (df['pre_close'] * (1 + pct)).round(2)
    df['limit_down_px'] = (df['pre_close'] * (1 - pct)).round(2)
    df = df.sort_values(['ts_code', 'date']).reset_index(drop=True)

    # per-stock rolling (2020+ window is sufficient: first signal day 2020-02-06 > 20 trading days in)
    grp = df.groupby('ts_code', sort=False)['close_adj']
    df['ma20'] = grp.rolling(20, min_periods=20).mean().reset_index(level=0, drop=True)
    df['sd20'] = grp.rolling(20, min_periods=20).std().reset_index(level=0, drop=True)
    df['bb_lower'] = df['ma20'] - 2.0 * df['sd20']
    df['amt_ma20'] = df.groupby('ts_code', sort=False)['amount'].rolling(20, min_periods=20).mean().reset_index(level=0, drop=True)
    df['min20'] = grp.rolling(20, min_periods=20).min().reset_index(level=0, drop=True)

    # eligibility (list_date + 60 trading days, engine semantics)
    tc_ = pd.read_parquet(os.path.join(ROOT, 'data', 'raw', 'trade_cal_full.parquet'))
    cal = tc_['date'].sort_values().reset_index(drop=True).to_numpy()
    sb = pd.read_parquet(os.path.join(ROOT, 'data', 'raw', 'stock_basic.parquet'))[['ts_code', 'list_date']]
    first_eligible_i = {}
    for code, ld in zip(sb['ts_code'], sb['list_date']):
        try:
            pos = int(np.searchsorted(cal, np.datetime64(pd.Timestamp(ld))))
        except Exception:
            pos = 0
        first_eligible_i[code] = pos + 60
    days = sorted(df['date'].unique())
    offset = int(np.searchsorted(cal, np.datetime64(days[0])))
    fi = np.vectorize(lambda c: first_eligible_i.get(c, 0))
    day_feats = {}
    for i, (d, dd) in enumerate(df.groupby('date', sort=True)):
        li = (offset + i) - fi(dd['ts_code'].to_numpy())
        elig = (li >= 0) & (~dd['is_st'].to_numpy())
        r = dd['ret'].to_numpy()
        rv = r[elig & np.isfinite(r)]
        size = int(elig.sum())
        if size == 0:
            day_feats[d] = dict(size=0); continue
        amt = dd['amount'].to_numpy()[elig]
        ca = dd['close_adj'].to_numpy()[elig]
        f = dict(
            size=size,
            idx_ret=float(rv.mean()) if len(rv) else np.nan,
            cs_std=float(rv.std(ddof=0)) if len(rv) > 1 else np.nan,
            p10_ret=float(np.percentile(rv, 10)) if len(rv) else np.nan,
            drop5=float((rv <= -0.05).mean()) if len(rv) else np.nan,
            drop7=float((rv <= -0.07).mean()) if len(rv) else np.nan,
            downvol=float((rv <= -0.05).mean()) if len(rv) else np.nan,   # F14 same formula
            up1d=float((rv > 0).mean()) if len(rv) else np.nan,
            breadth_ma20=float((ca > dd['ma20'].to_numpy()[elig]).mean()),
            newlow20=float((ca <= dd['min20'].to_numpy()[elig]).mean()),
            below_bb=float((ca < dd['bb_lower'].to_numpy()[elig]).mean()),
            limit_down=float((dd['close'].to_numpy()[elig] <= dd['limit_down_px'].to_numpy()[elig]).mean()),
            mkt_amt=float(amt.sum()),
            med_amt_ratio=float(np.nanmedian(amt / dd['amt_ma20'].to_numpy()[elig])) if np.isfinite(dd['amt_ma20'].to_numpy()[elig]).any() else np.nan,
        )
        day_feats[d] = f
    print(f'[load_features] days={len(days)} ({time.time()-t0:.0f}s)', flush=True)
    return day_feats, days, offset


def assemble_day_frame(day_feats, days):
    ix = pd.DataFrame(day_feats).T
    ix.index = pd.to_datetime(ix.index); ix = ix.sort_index()
    # All-A EW index level
    lvl = (1.0 + ix['idx_ret'].fillna(0.0)).cumprod()
    ix['idx_level'] = lvl
    ma20l = lvl.rolling(20, min_periods=20).mean()
    ix['ret20_ea'] = (lvl / lvl.shift(20) - 1.0) * 100
    ix['ret60_ea'] = (lvl / lvl.shift(60) - 1.0) * 100
    ix['dist_ma20'] = (lvl / ma20l - 1.0) * 100
    ix['ma20_slope'] = (ma20l / ma20l.shift(5) - 1.0) * 100
    ix['rv20'] = ix['idx_ret'].rolling(20, min_periods=20).std() * 100
    ix['rv60'] = ix['idx_ret'].rolling(60, min_periods=60).std() * 100
    ix['amt_ratio20'] = ix['mkt_amt'] / ix['mkt_amt'].shift(1).rolling(20, min_periods=20).mean()
    am = ix['mkt_amt']
    roll_mu = am.shift(1).rolling(60, min_periods=60).mean(); roll_sd = am.shift(1).rolling(60, min_periods=60).std()
    ix['amt_z60'] = (am - roll_mu) / roll_sd
    # index returns
    for code, col in [('000300', 'csi300'), ('000852', 'csi1000')]:
        ixr = pd.read_parquet(os.path.join(ROOT, 'data', f'index_{code}.parquet'))
        ixr['trade_date'] = pd.to_datetime(ixr['trade_date']); ixr = ixr.sort_values('trade_date').set_index('trade_date')
        rets = ixr['close'] / ixr['close'].shift(1) - 1.0
        l = (1.0 + rets.fillna(0.0)).cumprod()
        ix[f'{col}_ret20'] = (l / l.shift(20) - 1.0) * 100
    return ix


def main():
    t0 = time.time()
    day_feats, days, offset = load_features()
    ix = assemble_day_frame(day_feats, days)

    # frozen episodes
    fm = pd.read_csv(os.path.join(REPO, 'results', 'fullmarket_episode_metrics.csv'))
    fm['signal_date'] = pd.to_datetime(fm['signal_date'])
    epc = fm.groupby('signal_date').size()                       # N oversold signals by signal date
    r_by = fm.groupby('signal_date').agg(
        r_mean=('simple_return_pct', 'mean'), r_med=('simple_return_pct', 'median'),
        win=('simple_return_pct', lambda s: (s > 0).mean() * 100),
        loss=('simple_return_pct', lambda s: (s <= 0).mean() * 100),
        mae=('MAE_intraday_pct', 'mean'), hold=('hold_days', 'mean'),
        n=('simple_return_pct', 'size'))

    # signal-day series (use frozen signal dates = 1494)
    sig = r_by.copy()
    sig = sig.join(ix, how='left')                              # feature values on signal dates
    sig = sig[~sig.index.duplicated()].sort_index()
    # crowding features
    sig['n_oversold'] = epc.reindex(sig.index).fillna(0)
    sig['oversold_share'] = sig['n_oversold'] / sig['size']
    no = sig['n_oversold']
    sig['n_oversold_z60'] = (no - no.shift(1).rolling(60, min_periods=60).mean()) / no.shift(1).rolling(60, min_periods=60).std()

    # ---- MRH (completed episodes only) ----
    # completed-by-t: episodes with exit_date <= t, grouped by signal_date
    fm2 = fm[['signal_date', 'exit_date', 'simple_return_pct']].copy()
    fm2['exit_date'] = pd.to_datetime(fm2['exit_date'])
    # per (signal_date) completion date = max exit_date (episode completes when last exits) -> use exit_date<=t per episode
    # build: for each signal_date s, the set of episodes and their exit dates
    ex_dates = sorted(fm2['exit_date'].unique())
    mrh_val = {}
    # iterate signal dates in order, maintain completed episodes with exit_date<=t
    completed = pd.DataFrame(columns=['signal_date', 'simple_return_pct'])
    # vectorized: for each t (signal date), completed = fm2[exit_date<=t]
    sig_dates = sig.index.to_numpy()
    for t in sig_dates:
        done = fm2[fm2['exit_date'] <= t]
        if len(done) == 0:
            mrh_val[t] = (np.nan, np.nan, np.nan); continue
        dg = done.groupby('signal_date')['simple_return_pct'].agg(mean='mean', win=lambda s: (s > 0).mean())
        dg = dg.sort_index()
        m20 = dg.tail(20); m60 = dg.tail(60)
        mrh_val[t] = (m20['mean'].mean() if len(m20) else np.nan,
                      m60['mean'].mean() if len(m60) else np.nan,
                      m20['win'].mean() * 100 if len(m20) else np.nan)
    mrh = pd.DataFrame(mrh_val, index=['mrh20', 'mrh60', 'mrhwin20']).T
    mrh.index = pd.to_datetime(mrh.index)
    sig['mrh20'] = mrh['mrh20'].reindex(sig.index)
    sig['mrh60'] = mrh['mrh60'].reindex(sig.index)
    sig['mrhwin20'] = mrh['mrhwin20'].reindex(sig.index)

    # ---- prospective outcomes (within-Discovery windows) ----
    n = len(sig)
    rets = sig['r_mean'].to_numpy()
    sig_idx = sig.index.to_numpy()
    disc = (sig.index >= DIS_START) & (sig.index <= DIS_END)
    disc_pos = np.flatnonzero(disc)
    nD = disc_pos.size
    for k in (5, 10, 20, 40):
        y = np.full(n, np.nan); yw = np.full(n, np.nan)
        for pos in range(nD):
            i = disc_pos[pos]
            if pos + k >= nD:                 # forward window must stay within Discovery
                continue
            fut = disc_pos[pos + 1: pos + k + 1]
            seg = fm[fm['signal_date'].isin(sig_idx[fut])]['simple_return_pct']
            if len(seg):
                y[i] = seg.mean()
                yw[i] = (seg > 0).mean() * 100
        sig[f'Y{k}'] = y
        sig[f'Y{k}_win'] = yw
    sig['Y20_bad'] = (sig['Y20'] <= 0).astype(float)
    # map registry feature_id -> computed column
    fcol = dict(F01='ret20_ea', F02='ret60_ea', F03='csi300_ret20', F04='csi1000_ret20',
                F05='dist_ma20', F06='ma20_slope', F07='breadth_ma20', F08='up1d',
                F09='newlow20', F10='below_bb', F11='rv20', F12='rv60', F13='cs_std',
                F14='downvol', F15='amt_ratio20', F16='amt_z60', F17='med_amt_ratio',
                F18='limit_down', F19='drop5', F20='drop7', F21='p10_ret',
                F22='n_oversold', F23='oversold_share', F24='n_oversold_z60',
                F25='mrh20', F26='mrh60', F27='mrhwin20')
    for fid, col in fcol.items():
        sig[fid] = sig[col]
    # full-series Y20 (windows across ALL 1494 signal days) — DESCRIPTIVE_ONLY only
    y20f = np.full(n, np.nan)
    for pos in range(n):
        if pos + 20 >= n:
            continue
        fut = np.arange(pos + 1, pos + 21)
        seg = fm[fm['signal_date'].isin(sig_idx[fut])]['simple_return_pct']
        if len(seg):
            y20f[pos] = seg.mean()
    sig['Y20_full'] = y20f
    sig.to_csv(os.path.join(OUT, 't2_signalday_series_full.csv'))
    print(f'[signal series] n={n} discovery={nD} ({time.time()-t0:.0f}s)', flush=True)
    return sig, fm


# ---------------------------------------------------------------
# stats helpers
# ---------------------------------------------------------------
def rank01(x):
    r = stats.rankdata(x) / len(x)
    return r


def nw_t(x, y, lag):
    """Newey-West t on slope of OLS y ~ 1 + x (x,y numeric, same length, no NaN)."""
    n = len(x)
    X = np.column_stack([np.ones(n), x])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    XX = X.T @ X / n
    u = X * resid[:, None]
    G0 = u.T @ u / n
    S = G0.copy()
    for j in range(1, lag + 1):
        Gj = u[j:].T @ u[:-j] / n
        w = 1 - j / (lag + 1)
        S += w * (Gj + Gj.T)
    V = np.linalg.inv(XX) @ S @ np.linalg.inv(XX) / n
    se = np.sqrt(V[1, 1])
    t = beta[1] / se
    return t, beta[1]


def hac_pval(t):
    return 2 * (1 - stats.norm.cdf(abs(t)))


def bh_fdr(pvals):
    p = np.asarray(pvals, float); m = len(p)
    order = np.argsort(p)
    ps = p[order]
    qs = np.full(m, np.nan)
    cur = 1.0
    for i in range(m - 1, -1, -1):
        cur = min(cur, ps[i] * m / (i + 1))
        qs[i] = cur
    q = np.empty(m); q[order] = np.clip(qs, 0, 1)
    return q


def auroc(score, y):
    pos = y == 1; neg = ~pos
    if pos.sum() == 0 or neg.sum() == 0:
        return np.nan
    s = score[pos].reshape(-1, 1)
    return float((s > score[neg]).mean())


def pit_quintiles(x, y, min_hist=100):
    """expanding PIT quintile labels: boundaries from history < t."""
    n = len(x); lab = np.full(n, np.nan)
    hist = []
    for i in range(n):
        if np.isnan(x[i]):
            hist.append(np.nan); continue
        h = [v for v in hist if not np.isnan(v)]
        if len(h) >= min_hist:
            qs = np.quantile(h, [0.2, 0.4, 0.6, 0.8])
            lab[i] = int(np.searchsorted(qs, x[i])) + 1
            lab[i] = min(lab[i], 5)
        hist.append(x[i])
    return lab


def block_boot_spread(lab, y, L=21, B=2000):
    m = (~np.isnan(lab)) & (~np.isnan(y))
    lb = lab[m].astype(int); yy = y[m]; nn = len(yy)
    if nn < 2 * L:
        return (np.nan, np.nan)
    q1 = yy[lb == 1]; q5 = yy[lb == 5]
    if len(q1) == 0 or len(q5) == 0:
        return (np.nan, np.nan)
    obs = q5.mean() - q1.mean()
    spread = np.full(B, np.nan)
    nblk = int(np.ceil(nn / L))
    for b in range(B):
        idx = []
        for _ in range(nblk):
            st = RNG.integers(0, nn - L + 1) if nn - L + 1 > 0 else 0
            idx.extend(range(st, min(st + L, nn)))
        idx = np.array(idx[:nn])
        q1b = yy[idx][lb[idx] == 1]; q5b = yy[idx][lb[idx] == 5]
        if len(q1b) and len(q5b):
            spread[b] = q5b.mean() - q1b.mean()
    return (float(np.nanpercentile(spread, 2.5)), float(np.nanpercentile(spread, 97.5)))


# ---------------------------------------------------------------
# main analysis
# ---------------------------------------------------------------
def run():
    sig, fm = main()
    reg = pd.read_csv(os.path.join(REPO, 'TEMPORAL_STATE_FEATURE_REGISTRY.csv'))
    features = list(reg['feature_id'])
    fname = {r['feature_id']: r['name'] for _, r in reg.iterrows()}
    fam = {r['feature_id']: r['family'] for _, r in reg.iterrows()}
    dsign = {r['feature_id']: DIRSIGN[r['expected_direction']] for _, r in reg.iterrows()}
    bear = {r['feature_id']: BEAR[r['expected_direction']] for _, r in reg.iterrows()}

    disc = (sig.index >= DIS_START) & (sig.index <= DIS_END)
    S = sig[disc]
    print(f'[discovery] signal days={len(S)}', flush=True)

    # ---------- T2-A contemporaneous ----------
    cont_rows = []
    for f in features:
        d = S[['r_mean', 'win', 'mae', 'hold', f]].dropna()
        if len(d) < 30:
            cont_rows.append(dict(feature_id=f, name=fname[f], n=len(d), pearson_R=np.nan,
                                  spearman_R=np.nan, spearman_win=np.nan, spearman_mae=np.nan,
                                  spearman_hold=np.nan)); continue
        cont_rows.append(dict(feature_id=f, name=fname[f], n=len(d),
                              pearson_R=float(stats.pearsonr(d[f], d['r_mean'])[0]),
                              spearman_R=float(stats.spearmanr(d[f], d['r_mean']).statistic),
                              spearman_win=float(stats.spearmanr(d[f], d['win']).statistic),
                              spearman_mae=float(stats.spearmanr(d[f], d['mae']).statistic),
                              spearman_hold=float(stats.spearmanr(d[f], d['hold']).statistic)))
    pd.DataFrame(cont_rows).to_csv(os.path.join(OUT, 't2_contemporaneous.csv'), index=False)
    print('[T2-A] contemporaneous done', flush=True)

    # ---------- T2-B prospective + quintiles + bad-state ----------
    master = []
    for f in features:
        d = S[['Y5', 'Y10', 'Y20', 'Y40', 'Y20_bad', f]].dropna(subset=[f, 'Y20'])
        ic = {}
        for k in (5, 10, 20, 40):
            dd = d[['Y%d' % k, f]].dropna()
            ic[k] = float(stats.spearmanr(dd[f], dd['Y%d' % k]).statistic) if len(dd) > 30 else np.nan
        # HAC on Y20
        dd = d[['Y20', f]].dropna()
        x = dd[f].to_numpy(); y = dd['Y20'].to_numpy()
        # rank regression
        rx, ry = rank01(x), rank01(y)
        t20, _ = nw_t(rx, ry, HAC_LAG_PRIMARY)
        p20 = hac_pval(t20)
        t_sens = {L: nw_t(rx, ry, L)[0] for L in HAC_LAGS_SENS}
        # PIT expanding quintiles
        lab = pit_quintiles(x, y, PIT_MIN_HIST)
        qinfo = {}
        for q in range(1, 6):
            m = (lab == q) & ~np.isnan(y)
            qinfo[q] = dict(n=int(m.sum()),
                            meanY=float(y[m].mean()) if m.sum() else np.nan,
                            medY=float(np.median(y[m])) if m.sum() else np.nan,
                            bad=float((y[m] <= 0).mean() * 100) if m.sum() else np.nan)
        q5m1 = (qinfo[5]['meanY'] - qinfo[1]['meanY']) if qinfo[1]['n'] and qinfo[5]['n'] else np.nan
        mono = stats.spearmanr(list(range(1, 6)), [qinfo[q]['meanY'] for q in range(1, 6)]).statistic if all(qinfo[q]['n'] for q in range(1, 6)) else np.nan
        # bad-state AUROC on bearish orientation
        d2 = d[['Y20_bad', f]].dropna()
        bs = d2[f].to_numpy() * bear[f]
        auc = auroc(bs, d2['Y20_bad'].to_numpy())
        # worst/best quintile bad rate by bearish score (labels from PIT quintiles, but bearish ordering)
        # use PIT quintile labels: for POSITIVE features best=Q5 worst=Q1; NEGATIVE best=Q1 worst=Q5
        best_q, worst_q = (5, 1) if dsign[f] in (1, None) else (1, 5)
        # for UNKNOWN use raw orientation best=Q1 worst=Q5 (bear=+1)
        best_bad = qinfo[best_q]['bad'] if qinfo[best_q]['n'] else np.nan
        worst_bad = qinfo[worst_q]['bad'] if qinfo[worst_q]['n'] else np.nan
        # LYO direction
        dirs = []
        for yr in LYO_YEARS:
            m = (S.index.year != yr)
            sub = S[m][['Y20', f]].dropna()
            if len(sub) < 40:
                dirs.append(0); continue
            icc = stats.spearmanr(sub[f], sub['Y20']).statistic
            if dsign[f] is None:
                dirs.append(1)          # unknown: direction not gated
            else:
                dirs.append(1 if icc * dsign[f] > 0 else 0)
        lyo_cnt = sum(dirs)
        # block bootstrap spread CI
        blo, bhi = block_boot_spread(lab, y, BLOCK_L, BLOCK_B)
        master.append(dict(feature_id=f, name=fname[f], family=fam[f],
                           expected_direction=reg.loc[reg.feature_id == f, 'expected_direction'].iloc[0],
                           n_days=len(dd), contemporaneous_spearman=cont_rows[features.index(f)]['spearman_R'],
                           Y5_IC=ic[5], Y10_IC=ic[10], Y20_IC=ic[20], Y40_IC=ic[40],
                           Y20_HAC_t=t20, Y20_HAC_t_lag5=t_sens[5], Y20_HAC_t_lag10=t_sens[10], Y20_HAC_t_lag40=t_sens[40],
                           Y20_raw_p=p20, **{f'Q{q}_Y20': qinfo[q]['meanY'] for q in range(1, 6)},
                           Q5_minus_Q1=q5m1, MONOTONIC_SPEARMAN=mono,
                           BAD20_AUC=auc, BAD20_bestQ=best_bad, BAD20_worstQ=worst_bad,
                           LYO_direction_count=lyo_cnt, bootstrap_spread_lo=blo, bootstrap_spread_hi=bhi,
                           pit_labeled_days=int((~np.isnan(lab)).sum())))
    mt = pd.DataFrame(master)
    # BH FDR m=27 on Y20 raw p
    mt['Y20_BH_q'] = bh_fdr(mt['Y20_raw_p'].fillna(1.0))
    mt.to_csv(os.path.join(OUT, 't2_master_table.csv'), index=False)
    print('[T2-B] prospective done', flush=True)

    # ---------- gates ----------
    def disc_pass(r):
        if r['Y20_BH_q'] >= 0.05 or np.isnan(r['Y20_BH_q']):
            return False
        ds = dsign[r['feature_id']]
        if ds is not None:
            if not (r['Y20_IC'] * ds > 0):
                return False
        if np.isnan(r['Q5_minus_Q1']) or abs(r['Q5_minus_Q1']) < SPREAD_PP_GATE:
            return False
        if ds is not None:                       # not single-extreme driven
            if r['MONOTONIC_SPEARMAN'] * ds <= 0:
                return False
            if (r['Q4_Y20'] - r['Q2_Y20']) * ds <= 0:
                return False
        if r['LYO_direction_count'] < 2:
            return False
        if np.isnan(r['bootstrap_spread_lo']) or r['bootstrap_spread_lo'] * r['bootstrap_spread_hi'] <= 0:
            return False
        return True

    def bad_pass(r):
        ds = dsign[r['feature_id']]
        if ds is None:
            return False
        if np.isnan(r['BAD20_AUC']) or r['BAD20_AUC'] < AUC_GATE:
            return False
        if np.isnan(r['BAD20_bestQ']) or r['BAD20_worstQ'] < BAD_RATE_RATIO_GATE * r['BAD20_bestQ']:
            return False
        if np.isnan(r['Q5_minus_Q1']) or abs(r['Q5_minus_Q1']) < SPREAD_PP_GATE:
            return False
        if r['LYO_direction_count'] < 2:
            return False
        if r['Y20_BH_q'] >= 0.05:
            return False
        return True

    mt['DISCOVERY_PASS'] = mt.apply(disc_pass, axis=1)
    mt['BAD_STATE_PASS'] = mt.apply(bad_pass, axis=1)
    mt = mt.sort_values(['DISCOVERY_PASS', 'BAD_STATE_PASS', 'Y20_BH_q', 'Q5_minus_Q1'],
                        ascending=[False, False, True, True])
    mt.to_csv(os.path.join(OUT, 't2_master_table.csv'), index=False)

    # ---------- Y5/Y10/Y40 HAC sensitivity + IC table ----------
    pd.DataFrame(master).to_csv(os.path.join(OUT, 't2_prospective_ic.csv'), index=False)

    # ---------- BH m=27 ----------
    bh = pd.DataFrame(dict(feature_id=mt['feature_id'], Y20_raw_p=mt['Y20_raw_p'], Y20_BH_q=mt['Y20_BH_q'],
                           discovery_pass=mt['DISCOVERY_PASS']))
    bh.to_csv(os.path.join(OUT, 't2_bh27.csv'), index=False)

    # ---------- HAC table ----------
    mt[['feature_id', 'name', 'Y20_HAC_t', 'Y20_HAC_t_lag5', 'Y20_HAC_t_lag10', 'Y20_HAC_t_lag40', 'Y20_raw_p']].to_csv(
        os.path.join(OUT, 't2_hac.csv'), index=False)

    # ---------- quintiles PIT ----------
    qrows = []
    for _, r in mt.iterrows():
        d = S[['Y20', r['feature_id']]].dropna()
        lab = pit_quintiles(d[r['feature_id']].to_numpy(), d['Y20'].to_numpy(), PIT_MIN_HIST)
        y = d['Y20'].to_numpy()
        for q in range(1, 6):
            m = lab == q
            if not m.any():
                continue
            qrows.append(dict(feature_id=r['feature_id'], name=r['name'], quintile=q, n_days=int(m.sum()),
                              mean_Y20=float(y[m].mean()), median_Y20=float(np.median(y[m])),
                              bad_rate=float((y[m] <= 0).mean() * 100)))
    pd.DataFrame(qrows).to_csv(os.path.join(OUT, 't2_quintiles_pit.csv'), index=False)

    # ---------- bad-state AUC table ----------
    mt[['feature_id', 'name', 'family', 'BAD20_AUC', 'BAD20_bestQ', 'BAD20_worstQ', 'Q5_minus_Q1', 'Y20_BH_q', 'BAD_STATE_PASS']].to_csv(
        os.path.join(OUT, 't2_badstate_auc.csv'), index=False)

    # ---------- LYO ----------
    lrows = []
    for f in features:
        for yr in LYO_YEARS:
            sub = S[S.index.year != yr][['Y20', f]].dropna()
            icc = stats.spearmanr(sub[f], sub['Y20']).statistic if len(sub) > 40 else np.nan
            lrows.append(dict(feature_id=f, dropped_year=yr, n=len(sub), Y20_IC=icc))
    pd.DataFrame(lrows).to_csv(os.path.join(OUT, 't2_leave_one_year_out.csv'), index=False)

    # ---------- block bootstrap ----------
    brows = []
    for f in features:
        d = S[['Y20', f]].dropna()
        lab = pit_quintiles(d[f].to_numpy(), d['Y20'].to_numpy(), PIT_MIN_HIST)
        blo, bhi = block_boot_spread(lab, d['Y20'].to_numpy(), BLOCK_L, BLOCK_B)
        b5m1 = None
        b5m1 = (d['Y20'].to_numpy()[lab == 5].mean() - d['Y20'].to_numpy()[lab == 1].mean()) if lab is not None and (lab == 5).any() and (lab == 1).any() else np.nan
        b5m1 = (d['Y20'].to_numpy()[lab == 5].mean() - d['Y20'].to_numpy()[lab == 1].mean()) if lab is not None and (lab == 5).sum() and (lab == 1).sum() else np.nan
        brows.append(dict(feature_id=f, block_L=BLOCK_L, spread_lo=blo, spread_hi=bhi, spread_point=b5m1))
    pd.DataFrame(brows).to_csv(os.path.join(OUT, 't2_block_bootstrap.csv'), index=False)

    # ---------- redundancy ----------
    X = S[features]
    corr = X.corr(method='spearman')
    corr.to_csv(os.path.join(OUT, 't2_feature_redundancy.csv'))
    red_pairs = []
    for i, a in enumerate(features):
        for j, b in enumerate(features):
            if j <= i:
                continue
            v = corr.loc[a, b]
            if abs(v) > 0.85:
                red_pairs.append(dict(feature_a=a, feature_b=b, spearman=v,
                                      same_family=fam[a] == fam[b]))
    pd.DataFrame(red_pairs).to_csv(os.path.join(OUT, 't2_feature_redundancy_pairs.csv'), index=False)

    # ---------- MRH leak audit ----------
    fm2 = fm[['signal_date', 'exit_date']].copy(); fm2['exit_date'] = pd.to_datetime(fm2['exit_date'])
    rng = np.random.default_rng(11)
    cand = [t for t in S.index if not np.isnan(S.loc[t, 'mrh20'])]
    sample = list(rng.choice(cand, size=min(120, len(cand)), replace=False))
    leak_rows = []
    max_gap = -10**9
    for t in sample:
        used = fm2[fm2['exit_date'] <= t]
        if len(used):
            gap = (used['exit_date'].max() - t).days
            max_gap = max(max_gap, gap)
        leak_rows.append(dict(feature_date=str(t.date()), n_completed_episodes=int(len(used)),
                              max_exit_minus_feature_days=int(gap)))
    leak_df = pd.DataFrame(leak_rows)
    leak_df.attrs['max_exit_minus_feature_days'] = max_gap
    leak_df.to_csv(os.path.join(OUT, 't2_mrh_leak_audit.csv'), index=False)
    print(f'[MRH leak audit] n={len(sample)} max(exit-feature)={max_gap} (<=0 required)', flush=True)

    # ---------- PRIMARY sensitivity ----------
    nD = int(np.flatnonzero((sig.index >= DIS_START) & (sig.index <= DIS_END)).size)
    pk = pickle_load('independent_v2a_episodes.pkl')
    peps = pk['episodes']
    pr = pd.DataFrame([dict(signal_date=pd.to_datetime(e['signal_date']), return_pct=float(e['return_pct'])) for e in peps])
    # PRIMARY Y20 on same signal-day index windows within Discovery
    disc_dates = S.index.to_numpy()
    prY = {}
    prd = pr.set_index('signal_date')
    for pos, i in enumerate(np.flatnonzero(disc)):
        if pos + 20 >= nD:
            continue
        fut = disc_dates[pos + 1: pos + 21]
        seg = prd.loc[prd.index.isin(fut), 'return_pct'] if prd.index.isin(fut).any() else pd.Series(dtype=float)
        prY[disc_dates[i]] = seg.mean() if len(seg) else np.nan
    prY = pd.Series(prY)
    prs_rows = []
    for f in mt[mt['DISCOVERY_PASS']]['feature_id']:
        d = pd.concat([S[f], prY], axis=1, keys=['x', 'y']).dropna()
        if len(d) < 30:
            prs_rows.append(dict(feature_id=f, n=len(d), primary_Y20_spearman=np.nan, direction=np.nan)); continue
        icc = stats.spearmanr(d['x'], d['y']).statistic
        ds = dsign[f]
        dir_ok = (np.nan if ds is None else (icc * ds > 0))
        prs_rows.append(dict(feature_id=f, n=len(d), primary_Y20_spearman=icc, direction_matches=dir_ok))
    if not prs_rows:
        prs_rows = [dict(feature_id='NONE', n=0, primary_Y20_spearman=np.nan, direction_matches=np.nan,
                         note='0 DISCOVERY_PASS features -> no PRIMARY sensitivity rows')]
    pd.DataFrame(prs_rows).to_csv(os.path.join(OUT, 't2_primary_sensitivity.csv'), index=False)
    print('[PRIMARY sensitivity] done', flush=True)

    # ---------- Discovery bad segment explanation (2021-12-13..2022-03-07 only) ----------
    seg_lo, seg_hi = pd.Timestamp('2021-12-13'), pd.Timestamp('2022-03-07')
    in_seg = (S.index >= seg_lo) & (S.index <= seg_hi)
    seg_rows = []
    for f in features:
        inside = S.loc[in_seg, f].dropna(); outside = S.loc[~in_seg, f].dropna()
        seg_rows.append(dict(feature_id=f, name=fname[f], family=fam[f],
                             seg_mean=inside.mean() if len(inside) else np.nan,
                             outside_mean=outside.mean() if len(outside) else np.nan,
                             seg_minus_outside=(inside.mean() - outside.mean()) if len(inside) and len(outside) else np.nan,
                             seg_days=len(inside)))
    pd.DataFrame(seg_rows).to_csv(os.path.join(OUT, 't2_discovery_badsegment_explanation.csv'), index=False)

    # ---------- full-sample DESCRIPTIVE_ONLY ----------
    full_rows = []
    for f in features:
        d = sig[[f, 'r_mean']].dropna()
        d2 = sig[[f, 'Y20_full']].dropna()
        full_rows.append(dict(feature_id=f, name=fname[f],
                              full_spearman_R=stats.spearmanr(d[f], d['r_mean']).statistic if len(d) > 30 else np.nan,
                              full_spearman_Y20=stats.spearmanr(d2[f], d2['Y20_full']).statistic if len(d2) > 30 else np.nan))
    pd.DataFrame(full_rows).to_csv(os.path.join(OUT, 't2_fullsample_DESCRIPTIVE_ONLY.csv'), index=False)

    # ---------- feature values (Discovery) ----------
    S[['r_mean', 'r_med', 'win', 'loss', 'mae', 'hold'] + features].to_csv(
        os.path.join(OUT, 't2_feature_values_discovery.csv'))

    # ---------- figures ----------
    import matplotlib; matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'figure.dpi': 110, 'savefig.bbox': 'tight'})
    mt2 = mt.sort_values('Y20_IC')
    fig, ax = plt.subplots(figsize=(11, 6))
    colors = ['#d62728' if (r['Y20_BH_q'] < 0.05 and r['DISCOVERY_PASS']) else '#7f7f7f' for _, r in mt2.iterrows()]
    ax.barh(mt2['name'], mt2['Y20_IC'], color=colors)
    ax.axvline(0, color='k', lw=.8); ax.set_xlabel('Y20 Spearman IC'); ax.set_title('T2 Discovery Y20 IC (red=BH q<.05 & DISCOVERY_PASS)')
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 't2_y20_ic.png')); plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 6))
    colors = ['#d62728' if r['DISCOVERY_PASS'] else '#7f7f7f' for _, r in mt2.iterrows()]
    ax.barh(mt2['name'], mt2['Q5_minus_Q1'], color=colors)
    ax.axvline(0, color='k', lw=.8); ax.axvline(1, color='b', ls='--', lw=.8); ax.axvline(-1, color='b', ls='--', lw=.8)
    ax.set_xlabel('Q5-Q1 mean Y20 (pp)'); ax.set_title('T2 Y20 quintile spread')
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 't2_q1_q5_spread.png')); plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.barh(mt2['name'], mt2['BAD20_AUC'], color=['#d62728' if r['BAD_STATE_PASS'] else '#7f7f7f' for _, r in mt2.iterrows()])
    ax.axvline(0.5, color='k', lw=.8); ax.axvline(0.6, color='b', ls='--', lw=.8)
    ax.set_xlabel('BAD20 AUROC (bearish orientation)'); ax.set_title('T2 bad-state detection')
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 't2_badstate_auc.png')); plt.close(fig)

    # top features quintile lines
    top = mt.sort_values('Q5_minus_Q1', key=lambda s: s.abs(), ascending=False).head(6)['feature_id'].tolist()
    fig, ax = plt.subplots(figsize=(9, 5))
    for f in top:
        d = S[['Y20', f]].dropna()
        lab = pit_quintiles(d[f].to_numpy(), d['Y20'].to_numpy(), PIT_MIN_HIST)
        means = [d['Y20'].to_numpy()[lab == q].mean() for q in range(1, 6)]
        ax.plot(range(1, 6), means, 'o-', label=f'{f} {fname[f]}')
    ax.axhline(0, color='k', lw=.8); ax.set_xlabel('PIT quintile'); ax.set_ylabel('mean Y20 (%)')
    ax.legend(fontsize=7); ax.set_title('Top |spread| feature quintile profiles (Discovery Y20)')
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 't2_feature_quintiles_top.png')); plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 9))
    im = ax.imshow(corr.values, cmap='RdBu_r', vmin=-1, vmax=1)
    ax.set_xticks(range(len(features))); ax.set_xticklabels(features, rotation=90, fontsize=6)
    ax.set_yticks(range(len(features))); ax.set_yticklabels(features, fontsize=6)
    fig.colorbar(im, ax=ax, shrink=.7); ax.set_title('Discovery feature Spearman correlation')
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 't2_feature_redundancy.png')); plt.close(fig)

    # top features timeseries vs R
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    for axx, f in zip(axes, top[:3]):
        axx.plot(S.index, S[f], color='#1f77b4', lw=.7)
        axx.set_title(f'{f} {fname[f]}')
    axes[-1].set_xlabel('Discovery signal date')
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 't2_discovery_timeseries_top_features.png')); plt.close(fig)

    print('DONE', flush=True)


def pickle_load(name):
    import pickle
    with open(os.path.join(REPO, 'results', name), 'rb') as f:
        return pickle.load(f)


if __name__ == '__main__':
    run()
