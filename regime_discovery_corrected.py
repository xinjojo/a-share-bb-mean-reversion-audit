#!/usr/bin/env python3
"""REGIME DISCOVERY — PHASE 1 IMPLEMENTATION CORRECTION (v2)
修复外部审计发现：
P0-1 历史 warmup(2018起) + NaN regime->WARMUP
P0-2 正确 BH FDR + statsmodels 交叉验证
P1-1 benchmark uncertainty: HAC regression contrast + bootstrap 内重算 benchmark
P1-2 真实日历 block bootstrap (L=21 固定, 保留 calendar structure)
P1-3 NULL_A(circular shift regime) / NULL_B(within-date, secondary) / NULL_C(regime segment)
P1-4 命名: n_event_days, stock_event_win_rate, daily_raw_positive_rate, daily_excess_positive_rate
Discovery 仅 2020-01-01~2022-12-31; Registry 不修改。
"""
import sys, os, bisect, hashlib, subprocess
import numpy as np, pandas as pd
from scipy import stats as sst

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = f'{ROOT}/audit_package/github_repo'
DISC0, DISC1 = pd.Timestamp('2020-01-01'), pd.Timestamp('2022-12-31')
DIMCOL = {'TREND': 'trend', 'BREADTH': 'breadth', 'VOLATILITY': 'vol', 'LIQUIDITY': 'liq'}
WARMUP = 'WARMUP'

# ---------- Registry 核验 ----------
reg = pd.read_csv(f'{REPO}/HYPOTHESIS_REGISTRY.csv')
fhash = subprocess.check_output(['shasum', '-a', '256', f'{REPO}/HYPOTHESIS_REGISTRY.csv']).decode().split()[0]
frozen_hash = '5c5e451ad4eb3afd5e632b0019a3e02103e58e375e03cc231c5d8ca52b8c5195'
assert fhash == frozen_hash, 'REGISTRY HASH MISMATCH'
assert reg['hypothesis_id'].nunique() == 104
print(f'Registry 冻结核验通过 (SHA256={fhash}, 104行)。')

# ---------- 数据加载: warmup(2018-2019) + combined(2020-2023-02) ----------
print('加载数据 (warmup + combined)...')
dfw = pd.read_parquet(f'{ROOT}/data/warmup_daily_2018_2019.parquet')
dfc = pd.read_parquet(f'{ROOT}/data/combined_daily.parquet',
                      columns=['date', 'ts_code', 'open', 'close', 'amount', 'adj_factor'])
dfc = dfc[dfc['date'] <= pd.Timestamp('2023-02-28')]
st = pd.read_parquet(f'{ROOT}/data/pit_st_daily.parquet', columns=['date', 'ts_code', 'is_st_pit'])
dfc = dfc.merge(st, on=['date', 'ts_code'], how='left')
dfw = dfw[['ts_code', 'date', 'open', 'close', 'amount', 'adj_factor', 'is_st_pit']]
dfc = dfc[['ts_code', 'date', 'open', 'close', 'amount', 'adj_factor', 'is_st_pit']]
df = pd.concat([dfw, dfc], ignore_index=True).sort_values(['ts_code', 'date'])
df['is_st_pit'] = df['is_st_pit'].fillna(False)
sb = pd.read_parquet(f'{ROOT}/data/raw/stock_basic.parquet', columns=['ts_code', 'list_date'])
tc = pd.read_parquet(f'{ROOT}/data/raw/trade_cal_full.parquet')
trade_dates = sorted(pd.to_datetime(tc['date']))
print(f'数据: {df["date"].min().date()} ~ {df["date"].max().date()}, rows={len(df)}')

# ---------- 特征 ----------
print('计算特征...')
df['close_adj'] = df['close'] * df['adj_factor']
df['open_adj'] = df['open'] * df['adj_factor']
df['ret'] = df.groupby('ts_code', sort=False)['close_adj'].pct_change()
g = df.groupby('ts_code', sort=False)
df['ma20'] = g['close_adj'].transform(lambda x: x.rolling(20, min_periods=20).mean())
df['std20'] = g['close_adj'].transform(lambda x: x.rolling(20, min_periods=20).std(ddof=1))
df['bb_z'] = (df['close_adj'] - df['ma20']) / df['std20']

# ---------- PIT universe ----------
sb['ld'] = sb['list_date'].apply(lambda s: pd.Timestamp(str(int(s))) if pd.notna(s) else pd.NaT)
ld2elig = {}
for ld in sb['ld'].dropna().unique():
    pos = bisect.bisect_left(trade_dates, ld)
    ld2elig[ld] = trade_dates[pos + 59] if pos + 59 < len(trade_dates) else pd.Timestamp.max
df['elig_date'] = df['ts_code'].map(sb.set_index('ts_code')['ld'].to_dict()).map(ld2elig)
df['eligible'] = (df['date'] >= df['elig_date']) & (~df['is_st_pit']) & df['close_adj'].notna()

# ---------- 全A等权指数 (2018起, warmup 保证 2020 起 trend/rv 有效) ----------
all_days = pd.DatetimeIndex(sorted(df['date'].unique()))
d_ret = df[df['eligible'] & df['ret'].notna()].groupby('date')['ret'].mean().reindex(all_days)
idx = (1 + d_ret.fillna(0)).cumprod()
mkt_ret = d_ret

# ---------- Regime (每日), NaN -> WARMUP ----------
regime = pd.DataFrame(index=all_days)
idx20 = idx / idx.shift(20) - 1
regime['trend'] = np.where(idx20.isna(), WARMUP,
                           np.select([idx20 > 0.03, idx20 < -0.03], ['UP', 'DOWN'], default='SIDEWAYS'))
uni = df[df['eligible']]
denom = uni.groupby('date').size().reindex(all_days)
nabove = uni[uni['ma20'].notna() & (uni['close_adj'] > uni['ma20'])].groupby('date').size().reindex(all_days)
ratio = (nabove / denom).clip(upper=1.0)
regime['breadth'] = np.where(ratio.isna(), WARMUP,
                             np.select([ratio < 0.30, ratio > 0.70], ['LOW', 'HIGH'], default='MID'))
rv20 = mkt_ret.rolling(20).std() * np.sqrt(245)
rv_vals = rv20.values
n_days = len(rv_vals)
pctile = np.full(n_days, np.nan)
for i in range(n_days):
    if np.isnan(rv_vals[i]):
        continue
    hist = rv_vals[max(0, i - 252):i]
    hist = hist[~np.isnan(hist)]
    if len(hist) < 100:
        continue
    pctile[i] = np.mean(hist < rv_vals[i])
regime['vol'] = np.select(
    [np.isnan(pctile), pctile <= 0.20, pctile > 0.90],
    [WARMUP, 'LOW', 'EXTREME'],
    default=np.where(pctile <= 0.60, 'NORMAL', np.where(pctile <= 0.90, 'HIGH', WARMUP)))
mamt = uni.groupby('date')['amount'].sum().reindex(all_days)
mamt_ma20 = mamt.rolling(20, min_periods=20).mean()
amt_ratio = mamt / mamt_ma20
regime['liq'] = np.where(amt_ratio.isna(), WARMUP,
                         np.select([amt_ratio < 0.80, amt_ratio > 1.20], ['LOW', 'HIGH'], default='NORMAL'))

# ---------- 事件 (Discovery oversold) ----------
print('提取 oversold 事件...')
disc = df[(df['date'] >= DISC0) & (df['date'] <= DISC1)]
ev = disc[disc['eligible'] & disc['bb_z'].notna()].copy()
ev['bin'] = np.select(
    [(ev['bb_z'] > -2.0) & (ev['bb_z'] <= -1.5), (ev['bb_z'] > -2.5) & (ev['bb_z'] <= -2.0),
     (ev['bb_z'] > -3.0) & (ev['bb_z'] <= -2.5), (ev['bb_z'] <= -3.0)],
    ['B1', 'B2', 'B3', 'B4'], default=None)
ev = ev[ev['bin'].notna()].copy()
cal = list(all_days)
next_d = {cal[i]: cal[i + 1] for i in range(len(cal) - 1)}
adv = {h: {cal[i]: cal[i + h] for i in range(len(cal) - h)} for h in (5, 10)}
ev['T1'] = ev['date'].map(next_d)
ev['T5'] = ev['date'].map(adv[5])
ev['T10'] = ev['date'].map(adv[10])
fut_o = df[['ts_code', 'date', 'open_adj']].rename(columns={'date': 'T1', 'open_adj': 'open_adj_T1'})
fut_c5 = df[['ts_code', 'date', 'close_adj']].rename(columns={'date': 'T5', 'close_adj': 'close_adj_T5'})
fut_c10 = df[['ts_code', 'date', 'close_adj']].rename(columns={'date': 'T10', 'close_adj': 'close_adj_T10'})
ev = ev.merge(fut_o, on=['ts_code', 'T1'], how='left')
ev = ev.merge(fut_c5, on=['ts_code', 'T5'], how='left')
ev = ev.merge(fut_c10, on=['ts_code', 'T10'], how='left')
ev['non_tradable_t1'] = ev['open_adj_T1'].isna()
ev['otc5'] = ev['close_adj_T5'] / ev['open_adj_T1'] - 1
ev['otc10'] = ev['close_adj_T10'] / ev['open_adj_T1'] - 1
ev['miss5'] = ev['close_adj_T5'].isna()
ev['miss10'] = ev['close_adj_T10'].isna()
ev = ev.merge(regime[['trend', 'breadth', 'vol', 'liq']], left_on='date', right_index=True, how='left')
print(f'oversold 事件: {len(ev)}; non_tradable_t1={int(ev["non_tradable_t1"].sum())}; '
      f'otc5缺失={int(ev["miss5"].sum())}; otc10缺失={int(ev["miss10"].sum())}')

# ---------- WARMUP 审计 (old vs corrected, 2020) ----------
print('\n===== WARMUP 审计 (2020 年被重新分类天数; 旧版 NaN->SIDEWAYS/NORMAL 错分) =====')
for dim in ['trend', 'breadth', 'vol', 'liq']:
    y2020 = regime.loc[(regime.index >= pd.Timestamp('2020-01-01')) & (regime.index <= pd.Timestamp('2020-12-31')), dim]
    n_wu = int((y2020 == WARMUP).sum())
    print(f'  {dim}: 2020 年 WARMUP 天数 = {n_wu} (旧版将错分为 SIDEWAYS/NORMAL)')
ev_disc_only = ev[(ev['date'] >= DISC0) & (ev['date'] <= DISC1)]
for dim in ['trend', 'breadth', 'vol', 'liq']:
    ev_wu = int((ev_disc_only[dim] == WARMUP).sum())
    print(f'  {dim}: 被 WARMUP 排除的 Primary 事件数 = {ev_wu}')

# ---------- 日级聚合: per (bin, horizon) ----------
print('\n日级聚合 per (bin,horizon)...')
HZCOL = {'5D': 'otc5', '10D': 'otc10'}
day_series = {}   # (bin,hz) -> DataFrame(index=date 完整日历, y=日均值, n=事件数, stock_win=事件胜率)
for b in ['B1', 'B2', 'B3', 'B4']:
    for hz, col in HZCOL.items():
        sub = ev_disc_only[(ev_disc_only['bin'] == b) & ev_disc_only[col].notna()].copy()
        if len(sub) == 0:
            day_series[(b, hz)] = None
            continue
        daily = sub.groupby('date')[col].agg(['mean', 'size'])
        daily = daily.reindex(all_days)
        daily['n'] = daily['size']
        daily['y'] = daily['mean']
        daily['stock_win'] = sub.groupby('date')[col].apply(lambda s: (s > 0).mean()).reindex(all_days)
        day_series[(b, hz)] = daily

# 每 (bin,hz) 的事件日索引(完整日历上的布尔) 与 y 数组、regime 布尔矩阵
print('准备 per-cell 统计...')
N_CAL = len(all_days)
cal_pos = {d: i for i, d in enumerate(all_days)}
regime_bool = {}  # (dim, r) -> np.bool array over calendar
for dim in ['trend', 'breadth', 'vol', 'liq']:
    vals = regime[dim].values
    for r in ['UP', 'SIDEWAYS', 'DOWN', 'LOW', 'MID', 'HIGH', 'NORMAL', 'EXTREME']:
        regime_bool[(dim, r)] = (vals == r)

def nw_se(y, x):
    """Newey-West HAC SE of OLS beta of y ~ const + x, 用 statsmodels 标准实现."""
    import statsmodels.api as sm
    n = len(y)
    K = int(np.floor(4 * (n / 100) ** (2 / 9)))
    K = max(0, min(K, n - 2))
    X = np.column_stack([np.ones(n), x])
    res = sm.OLS(y, X).fit(cov_type='HAC', cov_kwds={'maxlags': K})
    return res.bse[1], res.params[1], K

def block_resample_idx(N, L, B, rng):
    """circular block bootstrap: 返回 B×N idx (预生成共享)."""
    out = np.empty((B, N), dtype=np.int64)
    nblocks = int(np.ceil(N / L))
    for b_ in range(B):
        starts = rng.integers(0, N, size=nblocks)
        idx = np.empty(nblocks * L, dtype=np.int64)
        for j, s in enumerate(starts):
            idx[j * L:(j + 1) * L] = np.arange(s, s + L) % N
        out[b_] = idx[:N]
    return out

# 预生成完整日历 block bootstrap 索引 (L=21, B=2000) 共享
print('预生成 block bootstrap 索引 (L=21, B=2000)...')
rng = np.random.default_rng(2020)
LBLK, BBOOT = 21, 2000
boot_idx = block_resample_idx(N_CAL, LBLK, BBOOT, rng)

# NULL_C: 预生成 per-dimension 的 regime segment block permutation (5000)
print('预生成 NULL_C regime-segment permutations (5000)...')
NPERM = 5000
seg_perm = {}
for dim in ['trend', 'breadth', 'vol', 'liq']:
    rv = regime[dim].values
    # find runs
    bounds = [0]
    for i in range(1, N_CAL):
        if rv[i] != rv[i - 1]:
            bounds.append(i)
    bounds.append(N_CAL)
    runs = [(bounds[j], bounds[j + 1]) for j in range(len(bounds) - 1)]
    seg_perm[dim] = (rv, runs)

def null_c_permuted(dim, b_, rng):
    rv, runs = seg_perm[dim]
    order = rng.permutation(len(runs))
    newrv = np.empty(N_CAL, dtype=object)
    pos = 0
    for oi in order:
        s, e = runs[oi]
        newrv[pos:pos + (e - s)] = rv[s:e]
        pos += e - s
    return newrv

# ---------- 计算 104 cells ----------
print('\n计算 104 Primary cells...')
from statsmodels.stats.multitest import multipletests
rows = []
cell_cache = {}
for _, r in reg.iterrows():
    dim, rbin = r['regime_dimension'], r['regime_bin']
    diml = DIMCOL[dim]
    ob, hz = r['oversold_bin'], r['forward_horizon']
    col = HZCOL[hz]
    ds = day_series[(ob, hz)]
    out = dict(hypothesis_id=r['hypothesis_id'], regime_dimension=dim, regime_bin=rbin,
               oversold_bin=ob, forward_horizon=hz)
    if ds is None:
        out.update(status='INSUFFICIENT_SAMPLE', n_stock_events=0, n_event_days=0)
        rows.append(out); continue
    evmask = ds['y'].notna().values          # 事件日 (完整日历布尔)
    n_all = int(evmask.sum())
    cell = evmask & regime_bool[(diml, rbin)]
    n_r = int(cell.sum())
    n_events_total = int(ev_disc_only[(ev_disc_only['bin'] == ob) & ev_disc_only[col].notna()].shape[0])
    n_events_cell = int(ev_disc_only[(ev_disc_only['bin'] == ob) & ev_disc_only[col].notna()
                                     & (ev_disc_only[diml] == rbin)].shape[0])
    out.update(n_stock_events=n_events_cell, n_event_days=n_r,
               n_non_tradable_t1=int(ev_disc_only[(ev_disc_only['bin'] == ob) & (ev_disc_only[diml] == rbin)]['non_tradable_t1'].sum()))
    if n_r < 150 or n_events_cell == 0:
        out['status'] = 'INSUFFICIENT_SAMPLE'
        rows.append(out); continue
    y_all = ds['y'].values                       # 完整日历
    y_ev = y_all[evmask]
    bm = float(y_ev.mean())                       # unconditional benchmark (原样本)
    y_cell = y_all[cell]
    mean_r = float(y_cell.mean())
    excess_obs = mean_r - bm
    daily_raw_pos = float((y_cell > 0).mean())
    daily_excess_pos = float(((y_cell - bm) > 0).mean())
    # 事件级胜率 (当日事件均值>0 的事件日加权? 直接事件级)
    evrows = ev_disc_only[(ev_disc_only['bin'] == ob) & ev_disc_only[col].notna()
                          & (ev_disc_only[diml] == rbin)]
    stock_win = float((evrows[col] > 0).mean()) if len(evrows) else np.nan
    # HAC regression contrast: y ~ a + b*D  (D=in-cell 于事件日集合上)
    D = cell[evmask].astype(float)
    se_beta, beta, K = nw_se(y_ev, D)
    hac_t = beta / se_beta if se_beta > 0 else np.nan
    raw_p = float(2 * sst.t.sf(abs(hac_t), n_all - 2)) if np.isfinite(hac_t) else np.nan
    # block bootstrap (完整日历, 每次重算 benchmark + conditional + excess)
    exc_boot = np.full(BBOOT, np.nan)
    for b_ in range(BBOOT):
        idx = boot_idx[b_]
        yb = y_all[idx]; rb = regime_bool[(diml, rbin)][idx]
        evb = ~np.isnan(yb)
        if evb.sum() < 2:
            continue
        bmb = yb[evb].mean()
        cellb = evb & rb
        if cellb.sum() < 2:
            continue
        exc_boot[b_] = yb[cellb].mean() - bmb
    exc_boot = exc_boot[~np.isnan(exc_boot)]
    ci_lo, ci_hi = np.percentile(exc_boot, [2.5, 97.5]) if len(exc_boot) else (np.nan, np.nan)
    boot_p = float(np.mean(exc_boot <= 0)) if len(exc_boot) else np.nan
    # NULL_A: circular shift regime labels vs outcome (5000)
    permA = np.empty(NPERM)
    nA = n_all
    for b_ in range(NPERM):
        k = rng.integers(1, nA)
        Ds = np.roll(D, k).astype(bool)
        if Ds.sum() == 0:
            permA[b_] = np.nan; continue
        permA[b_] = y_ev[Ds].mean() - bm
    permA = permA[~np.isnan(permA)]
    nullA_p = float(np.mean(np.abs(permA) >= abs(excess_obs))) if len(permA) else np.nan
    # NULL_C: regime segment block permutation (5000)
    permC = np.empty(NPERM)
    for b_ in range(NPERM):
        newrv = null_c_permuted(diml, b_, rng)
        rb = (newrv == rbin)
        cellc = evmask & rb
        if cellc.sum() < 2:
            permC[b_] = np.nan; continue
        permC[b_] = y_all[cellc].mean() - bm
    permC = permC[~np.isnan(permC)]
    nullC_p = float(np.mean(np.abs(permC) >= abs(excess_obs))) if len(permC) else np.nan
    # NULL_B: within-date stock permutation -> 日截面均值不变 (regime 是 market-wide 标签)
    # 结构恒等检查: 当日股票内置换不改变当日截面均值 y_t, 因此 excess 统计量对股票内选择不敏感。
    # 这是审计员要求的 SECONDARY STRUCTURE CHECK, 非 regime 主 null。
    # 验证: 对当日事件值 shuffle 后日均值不变 => p 结构恒等 = 1.0 (并给出小样本验证)。
    evrows_b = ev_disc_only[(ev_disc_only['bin'] == ob) & ev_disc_only[col].notna()]
    pivot_v = evrows_b.pivot_table(index='date', columns='ts_code', values=col, aggfunc='first')
    inv_check = []
    for b_ in range(20):
        sh = pivot_v.sample(axis=1, frac=1.0, random_state=int(rng.integers(1e9)))
        yd = sh.mean(axis=1)
        yd = yd.reindex(all_days).values
        cellb = evmask & regime_bool[(diml, rbin)]
        if cellb.sum() < 2:
            inv_check.append(np.nan); continue
        inv_check.append(yd[cellb].mean() - bm)
    inv_check = np.array(inv_check)
    nullB_p = float(np.mean(np.abs(inv_check) >= abs(excess_obs))) if len(inv_check) else np.nan
    nullB_note = 'STRUCTURAL_INVARIANT' if np.allclose(inv_check, excess_obs, atol=1e-12) else 'check'

    out.update(status='VALID_SAMPLE',
               mean_raw_return=mean_r, benchmark=bm, mean_regime_excess=excess_obs,
               median_regime_excess=float(np.median(y_cell) - bm),
               stock_event_win_rate=stock_win, daily_raw_positive_rate=daily_raw_pos,
               daily_excess_positive_rate=daily_excess_pos,
               hac_effect=beta, hac_se=se_beta, hac_t=hac_t, raw_p=raw_p,
               ci_lo=ci_lo, ci_hi=ci_hi, boot_p=boot_p,
               nullA_p=nullA_p, nullC_p=nullC_p, nullB_p=nullB_p, nullB_note=nullB_note,
               nw_lag=K)
    rows.append(out)

mat = pd.DataFrame(rows)
# ---------- 正确 BH FDR + statsmodels 交叉验证 ----------
valid = mat[mat['status'] == 'VALID_SAMPLE'].copy()
pvals = valid['raw_p'].dropna().values
ids = valid.loc[valid['raw_p'].notna(), 'hypothesis_id'].values
# own BH
pv = pvals; m = len(pv)
order = np.argsort(pv)
q_sorted = pv[order] * m / np.arange(1, m + 1)
q_sorted = np.minimum.accumulate(q_sorted[::-1])[::-1]
q_sorted = np.clip(q_sorted, 0, 1)
q_own = np.empty(m)
q_own[order] = q_sorted
# statsmodels BH
_, q_sm, _, _ = multipletests(pv, alpha=0.05, method='fdr_bh')
max_diff = float(np.max(np.abs(q_own - q_sm))) if m else np.nan
print(f'BH 交叉验证: m={m}, max_abs(q_own - q_statsmodels) = {max_diff:.3e}')
assert max_diff < 1e-10, 'BH FDR mismatch!'
qmap = dict(zip(ids, q_sm))
mat['bh_q'] = mat['hypothesis_id'].map(qmap)

mat.to_csv(f'{REPO}/results/regime_discovery_matrix_v2.csv', index=False)
print('矩阵已保存: results/regime_discovery_matrix_v2.csv')

# ---------- 汇总 ----------
print('\n===== CORRECTED PHASE 1 汇总 =====')
ns = (mat['status'] == 'VALID_SAMPLE').sum(); ni = (mat['status'] == 'INSUFFICIENT_SAMPLE').sum()
sig = (mat['bh_q'] < 0.05).sum()
pos_ns = ((mat['status'] == 'VALID_SAMPLE') & (mat['mean_regime_excess'] > 0) & ((mat['bh_q'] >= 0.05) | mat['bh_q'].isna())).sum()
neg = ((mat['status'] == 'VALID_SAMPLE') & (mat['mean_regime_excess'] < 0)).sum()
print(f'VALID_SAMPLE={ns}  INSUFFICIENT_SAMPLE={ni}  FDR_SIGNIFICANT={sig}')
print(f'positive_non_significant={pos_ns}  negative={neg}')
print(f'min raw_p={mat["raw_p"].min():.4f}  min bh_q={mat["bh_q"].min():.4f}')
print(f'NULL_A significant(0.05): {int((mat["nullA_p"]<0.05).sum())}  NULL_C significant(0.05): {int((mat["nullC_p"]<0.05).sum())}')
robust = ((mat['bh_q'] < 0.05) & (mat['boot_p'] < 0.05) & (mat['nullA_p'] < 0.05) & (mat['nullC_p'] < 0.05)).sum()
print(f'HAC+FDR+bootstrap+structured permutation 同时支持的 cell 数: {robust}')

print('\n===== BREADTH LOW 全 8 格 (原预注册 <30%) =====')
bl = mat[(mat['regime_dimension'] == 'BREADTH') & (mat['regime_bin'] == 'LOW')]
print(bl[['hypothesis_id', 'oversold_bin', 'forward_horizon', 'n_event_days', 'mean_raw_return',
          'benchmark', 'mean_regime_excess', 'stock_event_win_rate', 'hac_t', 'raw_p', 'bh_q',
          'ci_lo', 'ci_hi', 'boot_p', 'nullA_p', 'nullC_p', 'status']].to_string())
