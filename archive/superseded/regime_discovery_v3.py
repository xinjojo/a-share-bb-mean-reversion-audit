#!/usr/bin/env python3
"""REGIME DISCOVERY — PHASE 1 INFERENCE CORRECTION (v3)
外部审计 NOT PASS YET (3 P1 + 1 prereg consistency). 本版仅修 Discovery inference 实现:
P1-1 NULL_A 在完整 INFERENCE_CALENDAR (2020-01-01~2022-12-31) 上 circular shift regime label series,
      不再压缩 event calendar (只 roll 事件日 D).
P1-2 bootstrap / NULL_C / NULL_A / event mask 全部基于 INFERENCE_CALENDAR (严格 2020-2022),
      不含 2018-2019 warmup / 2023 日历结构. FEATURE_CALENDAR 仍 2018+ 计算 PIT 特征,
      OUTCOME_LOOKAHEAD 允许读取 late-2022 的 T+5/T+10 future price.
P1-3 PRIMARY bootstrap inference = 95% percentile/block-bootstrap CI (boot_ci_lo/boot_ci_hi)
      + positive/negative_boot_support; boot_p 改名 boot_prob_nonpositive (descriptive directional only).
P1-4 见 REGIME_PHASE1_METHODOLOGY_CLARIFICATION.md: PRIMARY=daily cross-sectional aggregate + HAC,
      SECONDARY(stock-event panel cluster) 仅记录, 不替换 Primary.
HAC lag: 自动 K 未在首次 Discovery run 前预注册 -> 标 POST-HOC; 补固定 lag sensitivity (5D:4,5 / 10D:9,10 + auto), 只作 sensitivity.
FDR: 主 m=60 (仅 VALID/testable); 参考 m=104 (44 insufficient 视为 p=1) 仅 robustness reference.
Registry SHA256 不变; 不打开 Validation; 不改阈值/bins/benchmark/horizons.
"""
import sys, os, bisect, hashlib, subprocess
import numpy as np, pandas as pd
from scipy import stats as sst

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = f'{ROOT}/audit_package/github_repo'
DISC0, DISC1 = pd.Timestamp('2020-01-01'), pd.Timestamp('2022-12-31')
DIMCOL = {'TREND': 'trend', 'BREADTH': 'breadth', 'VOLATILITY': 'vol', 'LIQUIDITY': 'liq'}
WARMUP = 'WARMUP'
OUTDIR = f'{REPO}/results'

# ---------- Registry 核验 ----------
reg = pd.read_csv(f'{REPO}/HYPOTHESIS_REGISTRY.csv')
fhash = subprocess.check_output(['shasum', '-a', '256', f'{REPO}/HYPOTHESIS_REGISTRY.csv']).decode().split()[0]
frozen_hash = '5c5e451ad4eb3afd5e632b0019a3e02103e58e375e03cc231c5d8ca52b8c5195'
assert fhash == frozen_hash, 'REGISTRY HASH MISMATCH'
assert reg['hypothesis_id'].nunique() == 104
assert (reg['benchmark'] == 'same_oversold_unconditional').all()
print(f'Registry 冻结核验通过 (SHA256={fhash}, 104行, benchmark 唯一 same_oversold_unconditional)。')

# ---------- 数据加载: FEATURE_CALENDAR = 2018起 (warmup + combined) ----------
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
print(f'FEATURE_CALENDAR: {df["date"].min().date()} ~ {df["date"].max().date()}, rows={len(df)}')

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

# ---------- 全A等权指数 (2018起) ----------
all_days = pd.DatetimeIndex(sorted(df['date'].unique()))
d_ret = df[df['eligible'] & df['ret'].notna()].groupby('date')['ret'].mean().reindex(all_days)
idx = (1 + d_ret.fillna(0)).cumprod()
mkt_ret = d_ret

# ---------- Regime (每日, FEATURE_CALENDAR), NaN -> WARMUP ----------
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

# ---------- INFERENCE_CALENDAR: 严格 2020-01-01 ~ 2022-12-31 ----------
INF = all_days[(all_days >= DISC0) & (all_days <= DISC1)]
N_INF = len(INF)
print(f'INFERENCE_CALENDAR: {INF[0].date()} ~ {INF[-1].date()}, n_days={N_INF}')

# ---------- 事件 (Discovery oversold), outcome lookup 允许读入 2023-01 (OUTCOME_LOOKAHEAD) ----------
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

# ---------- 日级聚合 per (bin, horizon), reindex 到 INFERENCE_CALENDAR ----------
print('日级聚合 per (bin,horizon) [INFERENCE_CALENDAR]...')
HZCOL = {'5D': 'otc5', '10D': 'otc10'}
day_series = {}
for b in ['B1', 'B2', 'B3', 'B4']:
    for hz, col in HZCOL.items():
        sub = ev[(ev['bin'] == b) & ev[col].notna()].copy()
        if len(sub) == 0:
            day_series[(b, hz)] = None
            continue
        daily = sub.groupby('date')[col].agg(['mean', 'size'])
        daily = daily.reindex(INF)
        daily['n'] = daily['size']
        daily['y'] = daily['mean']
        daily['stock_win'] = sub.groupby('date')[col].apply(lambda s: (s > 0).mean()).reindex(INF)
        day_series[(b, hz)] = daily

# regime 布尔矩阵 over INFERENCE_CALENDAR
print('准备 per-cell 统计...')
regime_inf = {dim: regime.loc[INF, dim].values for dim in ['trend', 'breadth', 'vol', 'liq']}
regime_bool = {}
for dim in ['trend', 'breadth', 'vol', 'liq']:
    vals = regime_inf[dim]
    for r in ['UP', 'SIDEWAYS', 'DOWN', 'LOW', 'MID', 'HIGH', 'NORMAL', 'EXTREME']:
        regime_bool[(dim, r)] = (vals == r)

def nw_se(y, x, K=None):
    """Newey-West HAC SE of OLS beta of y ~ const + x. K=None -> automatic."""
    import statsmodels.api as sm
    n = len(y)
    if K is None:
        K = int(np.floor(4 * (n / 100) ** (2 / 9)))
        K = max(0, min(K, n - 2))
    X = np.column_stack([np.ones(n), x])
    res = sm.OLS(y, X).fit(cov_type='HAC', cov_kwds={'maxlags': K})
    return res.bse[1], res.params[1], K

def block_resample_idx(N, L, B, rng):
    out = np.empty((B, N), dtype=np.int64)
    nblocks = int(np.ceil(N / L))
    for b_ in range(B):
        starts = rng.integers(0, N, size=nblocks)
        idx = np.empty(nblocks * L, dtype=np.int64)
        for j, s in enumerate(starts):
            idx[j * L:(j + 1) * L] = np.arange(s, s + L) % N
        out[b_] = idx[:N]
    return out

# 预生成: bootstrap 索引 (INFERENCE_CALENDAR, L=21, B=2000)
print('预生成 block bootstrap 索引 (INFERENCE_CALENDAR, L=21, B=2000)...')
rng = np.random.default_rng(2020)
LBLK, BBOOT = 21, 2000
boot_idx = block_resample_idx(N_INF, LBLK, BBOOT, rng)

# 预生成: NULL_A 每 dim 5000 个 circular shift k (INFERENCE_CALENDAR 上 roll regime label)
print('预生成 NULL_A circular shifts (5000)...')
NPERM = 5000
nullA_shift = {}   # dim -> (k 数组)
for dim in ['trend', 'breadth', 'vol', 'liq']:
    ks = rng.integers(1, N_INF, size=NPERM)
    nullA_shift[dim] = ks

# 预生成: NULL_C 每 dim 5000 个 segment permutation (INFERENCE_CALENDAR 上 regime runs)
print('预生成 NULL_C regime-segment permutations (5000)...')
seg_perm_order = {}
seg_runs = {}
for dim in ['trend', 'breadth', 'vol', 'liq']:
    rv = regime_inf[dim]
    bounds = [0]
    for i in range(1, N_INF):
        if rv[i] != rv[i - 1]:
            bounds.append(i)
    bounds.append(N_INF)
    runs = [(bounds[j], bounds[j + 1]) for j in range(len(bounds) - 1)]
    seg_runs[dim] = runs
    orders = np.array([rng.permutation(len(runs)) for _ in range(NPERM)])
    seg_perm_order[dim] = orders

def null_c_permuted(dim, b_, rv):
    runs = seg_runs[dim]
    order = seg_perm_order[dim][b_]
    newrv = np.empty(N_INF, dtype=object)
    pos = 0
    for oi in order:
        s, e = runs[oi]
        newrv[pos:pos + (e - s)] = rv[s:e]
        pos += e - s
    return newrv

# ---------- 计算 104 cells ----------
print('\n计算 104 Primary cells [INFERENCE_CALENDAR]...')
from statsmodels.stats.multitest import multipletests
rows = []
lag_sens = []
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
    evmask = ds['y'].notna().values          # 事件日 (INFERENCE_CALENDAR 布尔)
    n_all = int(evmask.sum())
    cell = evmask & regime_bool[(diml, rbin)]
    n_r = int(cell.sum())
    n_events_total = int(ev[(ev['bin'] == ob) & ev[col].notna()].shape[0])
    n_events_cell = int(ev[(ev['bin'] == ob) & ev[col].notna() & (ev[diml] == rbin)].shape[0])
    out.update(n_stock_events=n_events_cell, n_event_days=n_r,
               n_non_tradable_t1=int(ev[(ev['bin'] == ob) & (ev[diml] == rbin)]['non_tradable_t1'].sum()))
    if n_r < 150 or n_events_cell == 0:
        out['status'] = 'INSUFFICIENT_SAMPLE'
        rows.append(out); continue
    y_all = ds['y'].values                       # INFERENCE_CALENDAR
    y_ev = y_all[evmask]
    bm = float(y_ev.mean())                       # same-oversold unconditional (原样本, 不依赖 regime)
    y_cell = y_all[cell]
    mean_r = float(y_cell.mean())
    excess_obs = mean_r - bm
    daily_raw_pos = float((y_cell > 0).mean())
    daily_excess_pos = float(((y_cell - bm) > 0).mean())
    evrows = ev[(ev['bin'] == ob) & ev[col].notna() & (ev[diml] == rbin)]
    stock_win = float((evrows[col] > 0).mean()) if len(evrows) else np.nan
    # HAC regression contrast (自动 K, POST-HOC; 固定 lag sensitivity 另行输出)
    D = cell[evmask].astype(float)
    se_beta, beta, K_auto = nw_se(y_ev, D)
    hac_t = beta / se_beta if se_beta > 0 else np.nan
    raw_p = float(2 * sst.t.sf(abs(hac_t), n_all - 2)) if np.isfinite(hac_t) else np.nan
    # fixed-lag sensitivity (仅 Discovery): 5D lag 4,5 / 10D lag 9,10
    for lag in ([4, 5] if hz == '5D' else [9, 10]):
        if lag <= n_all - 2:
            try:
                se_l, beta_l, _ = nw_se(y_ev, D, K=lag)
                t_l = beta_l / se_l if se_l > 0 else np.nan
                p_l = float(2 * sst.t.sf(abs(t_l), n_all - 2)) if np.isfinite(t_l) else np.nan
            except Exception:
                p_l = np.nan
        else:
            p_l = np.nan
        lag_sens.append(dict(hypothesis_id=r['hypothesis_id'], forward_horizon=hz,
                             lag_auto=K_auto, raw_p_auto=raw_p, lag_fixed=lag, raw_p_fixed=p_l))
    # block bootstrap (INFERENCE_CALENDAR, L=21, B=2000, 每次重算 benchmark+conditional+excess)
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
    boot_prob_nonpos = float(np.mean(exc_boot <= 0)) if len(exc_boot) else np.nan
    pos_boot = bool(ci_lo > 0) if np.isfinite(ci_lo) else False
    neg_boot = bool(ci_hi < 0) if np.isfinite(ci_hi) else False
    # NULL_A: 在 INFERENCE_CALENDAR 上 circular shift regime label series (事件序列固定)
    rv_inf = regime_inf[diml]
    permA = np.empty(NPERM)
    ks = nullA_shift[diml]
    for b_ in range(NPERM):
        rv_shifted = np.roll(rv_inf, int(ks[b_]))
        cells = evmask & (rv_shifted == rbin)
        if cells.sum() < 2:
            permA[b_] = np.nan; continue
        permA[b_] = y_all[cells].mean() - bm
    permA = permA[~np.isnan(permA)]
    nullA_p = float(np.mean(np.abs(permA) >= abs(excess_obs))) if len(permA) else np.nan
    # NULL_C: INFERENCE_CALENDAR 上 regime segment block permutation (5000)
    permC = np.empty(NPERM)
    for b_ in range(NPERM):
        newrv = null_c_permuted(diml, b_, rv_inf)
        cellc = evmask & (newrv == rbin)
        if cellc.sum() < 2:
            permC[b_] = np.nan; continue
        permC[b_] = y_all[cellc].mean() - bm
    permC = permC[~np.isnan(permC)]
    nullC_p = float(np.mean(np.abs(permC) >= abs(excess_obs))) if len(permC) else np.nan
    # NULL_B: within-date stock permutation -> 日截面均值不变 (secondary structure check)
    evrows_b = ev[(ev['bin'] == ob) & ev[col].notna()]
    pivot_v = evrows_b.pivot_table(index='date', columns='ts_code', values=col, aggfunc='first')
    inv_check = []
    for b_ in range(20):
        sh = pivot_v.sample(axis=1, frac=1.0, random_state=int(rng.integers(1e9)))
        yd = sh.mean(axis=1)
        yd = yd.reindex(INF).values
        cellb2 = evmask & regime_bool[(diml, rbin)]
        if cellb2.sum() < 2:
            inv_check.append(np.nan); continue
        inv_check.append(yd[cellb2].mean() - bm)
    inv_check = np.array(inv_check)
    nullB_p = float(np.mean(np.abs(inv_check) >= abs(excess_obs))) if len(inv_check) else np.nan
    nullB_note = 'STRUCTURAL_INVARIANT' if np.allclose(inv_check, excess_obs, atol=1e-12) else 'check'

    out.update(status='VALID_SAMPLE',
               mean_raw_return=mean_r, benchmark=bm, mean_regime_excess=excess_obs,
               median_regime_excess=float(np.median(y_cell) - bm),
               stock_event_win_rate=stock_win, daily_raw_positive_rate=daily_raw_pos,
               daily_excess_positive_rate=daily_excess_pos,
               hac_effect=beta, hac_se=se_beta, hac_t=hac_t, raw_p=raw_p,
               boot_ci_lo=ci_lo, boot_ci_hi=ci_hi, boot_p=boot_prob_nonpos,
               positive_boot_support=pos_boot, negative_boot_support=neg_boot,
               nullA_p=nullA_p, nullC_p=nullC_p, nullB_p=nullB_p, nullB_note=nullB_note,
               nw_lag=K_auto)
    rows.append(out)

mat = pd.DataFrame(rows)

# ---------- 主 BH FDR: m=60 (仅 VALID/testable) + statsmodels 交叉验证 ----------
print('\n主 BH FDR (m=60, 仅 VALID/testable)...')
valid = mat[mat['status'] == 'VALID_SAMPLE'].copy()
pvals = valid['raw_p'].dropna().values
ids = valid.loc[valid['raw_p'].notna(), 'hypothesis_id'].values
m = len(pvals)
pv = pvals
order = np.argsort(pv)
q_sorted = pv[order] * m / np.arange(1, m + 1)
q_sorted = np.minimum.accumulate(q_sorted[::-1])[::-1]
q_sorted = np.clip(q_sorted, 0, 1)
q_own = np.empty(m); q_own[order] = q_sorted
_, q_sm, _, _ = multipletests(pv, alpha=0.05, method='fdr_bh')
max_diff = float(np.max(np.abs(q_own - q_sm))) if m else np.nan
print(f'BH 交叉验证 (m={m}): max_abs(q_own - q_statsmodels) = {max_diff:.3e}')
assert max_diff < 1e-10, 'BH FDR mismatch!'
qmap = dict(zip(ids, q_sm))
mat['bh_q'] = mat['hypothesis_id'].map(qmap)

# ---------- 保守参考 FDR: m=104 (44 insufficient 视为 p=1) ----------
print('参考 BH FDR (m=104, insufficient p=1)...')
allp = []
for _, r in mat.iterrows():
    if r['status'] == 'VALID_SAMPLE' and pd.notna(r['raw_p']):
        allp.append((r['hypothesis_id'], r['raw_p']))
    else:
        allp.append((r['hypothesis_id'], 1.0))
allp = pd.DataFrame(allp, columns=['hypothesis_id', 'p'])
p_all = allp['p'].values
_, q_all, _, _ = multipletests(p_all, alpha=0.05, method='fdr_bh')
bh104 = pd.DataFrame({'hypothesis_id': allp['hypothesis_id'], 'status': mat['status'].values,
                      'raw_p': allp['p'].values, 'bh_q_104': q_all})

# ---------- 保存 ----------
mat.to_csv(f'{OUTDIR}/regime_discovery_matrix_v3.csv', index=False)
pd.DataFrame(lag_sens).to_csv(f'{OUTDIR}/regime_v3_hac_lag_sensitivity.csv', index=False)
bh104.to_csv(f'{OUTDIR}/regime_v3_bh104_reference.csv', index=False)
print('已保存: regime_discovery_matrix_v3.csv / regime_v3_hac_lag_sensitivity.csv / regime_v3_bh104_reference.csv')

# ---------- v2 -> v3 diff ----------
try:
    v2 = pd.read_csv(f'{OUTDIR}/regime_discovery_matrix_v2.csv')
    keys = ['hypothesis_id']
    diff_cols = ['mean_regime_excess', 'hac_t', 'raw_p', 'bh_q', 'boot_p', 'nullA_p', 'nullC_p', 'status']
    d = v2[keys + diff_cols].merge(mat[keys + diff_cols], on='hypothesis_id', suffixes=('_v2', '_v3'))
    # 添加 v3 bootstrap CI / support
    d = d.merge(mat[['hypothesis_id', 'boot_ci_lo', 'boot_ci_hi', 'positive_boot_support', 'negative_boot_support', 'nw_lag']], on='hypothesis_id')
    d['excess_delta'] = d['mean_regime_excess_v3'] - d['mean_regime_excess_v2']
    d['rawp_delta'] = d['raw_p_v3'] - d['raw_p_v2']
    d['nullA_delta'] = d['nullA_p_v3'] - d['nullA_p_v2']
    d['nullC_delta'] = d['nullC_p_v3'] - d['nullC_p_v2']
    d['bootp_delta'] = d['boot_p_v3'] - d['boot_p_v2']
    d['status_changed'] = d['status_v2'] != d['status_v3']
    d['bhq_changed_significance'] = (d['bh_q_v2'] < 0.05) != (d['bh_q_v3'] < 0.05)
    d.to_csv(f'{OUTDIR}/regime_v2_v3_diff.csv', index=False)
    print('已保存: regime_v2_v3_diff.csv')
except Exception as e:
    print('v2->v3 diff 生成失败:', e)

# ---------- 汇总 ----------
print('\n===== CORRECTED PHASE 1 (v3) 汇总 =====')
ns = (mat['status'] == 'VALID_SAMPLE').sum(); ni = (mat['status'] == 'INSUFFICIENT_SAMPLE').sum()
sig = (mat['bh_q'] < 0.05).sum()
pos_ns = ((mat['status'] == 'VALID_SAMPLE') & (mat['mean_regime_excess'] > 0) & ((mat['bh_q'] >= 0.05) | mat['bh_q'].isna())).sum()
neg = ((mat['status'] == 'VALID_SAMPLE') & (mat['mean_regime_excess'] < 0)).sum()
print(f'VALID_SAMPLE={ns}  INSUFFICIENT_SAMPLE={ni}  FDR_SIGNIFICANT(m60)={sig}')
print(f'positive_non_significant={pos_ns}  negative={neg}')
print(f'min raw_p={mat["raw_p"].min():.4f}  min bh_q(m60)={mat["bh_q"].min():.4f}')
print(f'positive_boot_support: {(mat["positive_boot_support"]==True).sum()}  negative_boot_support: {(mat["negative_boot_support"]==True).sum()}')
print(f'NULL_A significant(0.05): {int((mat["nullA_p"]<0.05).sum())}  NULL_C significant(0.05): {int((mat["nullC_p"]<0.05).sum())}')
robust = ((mat['bh_q'] < 0.05) & (mat['negative_boot_support'] == True) & (mat['nullA_p'] < 0.05) & (mat['nullC_p'] < 0.05)).sum()
print(f'FDR+neg_boot+NULL_A+NULL_C 同时支持: {robust}')
robust_pos = ((mat['bh_q'] < 0.05) & (mat['positive_boot_support'] == True) & (mat['nullA_p'] < 0.05) & (mat['nullC_p'] < 0.05)).sum()
print(f'FDR+pos_boot+NULL_A+NULL_C 同时支持: {robust_pos}')
print(f'BH(m104) FDR_SIGNIFICANT: {int((bh104["bh_q_104"]<0.05).sum())}')

print('\n===== BREADTH LOW 全 8 格 (原预注册 <30%) =====')
bl = mat[(mat['regime_dimension'] == 'BREADTH') & (mat['regime_bin'] == 'LOW')]
print(bl[['hypothesis_id', 'oversold_bin', 'forward_horizon', 'n_event_days', 'mean_raw_return',
          'benchmark', 'mean_regime_excess', 'stock_event_win_rate', 'hac_t', 'raw_p', 'bh_q',
          'boot_ci_lo', 'boot_ci_hi', 'boot_p', 'positive_boot_support', 'negative_boot_support',
          'nullA_p', 'nullC_p', 'status']].to_string())
