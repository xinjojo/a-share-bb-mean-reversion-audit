"""REGIME DISCOVERY — PHASE 1 (2020-01-01 ~ 2022-12-31)
严格按冻结 REGIME_RESEARCH_PLAN v3 + HYPOTHESIS_REGISTRY(104 PRIMARY) 实现。

只做 Discovery；不打开 Validation/Confirmation；不修改 Registry。
"""
import sys, os, bisect, hashlib
import numpy as np, pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = f'{ROOT}/audit_package/github_repo'
DISC0, DISC1 = '2020-01-01', '2022-12-31'

# ---------- Registry 核验 ----------
reg = pd.read_csv(f'{REPO}/HYPOTHESIS_REGISTRY.csv')
h = hashlib.sha256(pd.util.hash_pandas_object(reg, index=True).values.tobytes()).hexdigest()
frozen_hash = '5c5e451ad4eb3afd5e632b0019a3e02103e58e375e03cc231c5d8ca52b8c5195'
import subprocess
fhash = subprocess.check_output(['shasum','-a','256',f'{REPO}/HYPOTHESIS_REGISTRY.csv']).decode().split()[0]
print(f'Registry rows={len(reg)}  sha256={fhash}')
assert fhash == frozen_hash, 'REGISTRY HASH MISMATCH!'
assert reg['hypothesis_id'].nunique() == 104
print('Registry 冻结核验通过 (SHA256 一致, 104行)。')

# ---------- 1. 数据加载 (Discovery + 缓冲至 2023-02-28 供未来收益) ----------
print('加载数据...')
df = pd.read_parquet(f'{ROOT}/data/combined_daily.parquet',
                     columns=['date','ts_code','open','close','amount','adj_factor'])
df = df[(df['date']>='2020-01-02')&(df['date']<='2023-02-28')].copy()
st = pd.read_parquet(f'{ROOT}/data/pit_st_daily.parquet', columns=['date','ts_code','is_st_pit'])
sb = pd.read_parquet(f'{ROOT}/data/raw/stock_basic.parquet', columns=['ts_code','list_date'])
tc = pd.read_parquet(f'{ROOT}/data/raw/trade_cal_full.parquet')
trade_dates = sorted(pd.to_datetime(tc['date']))
df = df.merge(st, on=['date','ts_code'], how='left')
df['is_st_pit'] = df['is_st_pit'].fillna(False)

# ---------- 2. 特征 (按 ts_code rolling) ----------
print('计算特征...')
df['close_adj'] = df['close']*df['adj_factor']
df['open_adj'] = df['open']*df['adj_factor']
df['ret'] = df.groupby('ts_code', sort=False)['close_adj'].pct_change()
g = df.groupby('ts_code', sort=False)
df['ma20'] = g['close_adj'].transform(lambda x: x.rolling(20, min_periods=20).mean())
df['std20'] = g['close_adj'].transform(lambda x: x.rolling(20, min_periods=20).std(ddof=1))
df['bb_z'] = (df['close_adj']-df['ma20'])/df['std20']

# ---------- 3. PIT universe: 上市满60交易日 + 非ST + 有效行情 ----------
sb['ld'] = sb['list_date'].apply(lambda s: pd.Timestamp(str(int(s))) if pd.notna(s) else pd.NaT)
ld2elig = {}
for ld in sb['ld'].dropna().unique():
    pos = bisect.bisect_left(trade_dates, ld)
    ld2elig[ld] = trade_dates[pos+59] if pos+59 < len(trade_dates) else pd.Timestamp.max
df['elig_date'] = df['ts_code'].map(sb.set_index('ts_code')['ld'].to_dict()).map(ld2elig)
df['listed_60d'] = df['date'] >= df['elig_date']
df['eligible'] = df['listed_60d'] & (~df['is_st_pit']) & df['close_adj'].notna()
# 有效行情(含停牌说明): 数据行本身即为有行情日; 停牌日无行。不额外用 delist_date(避免PIT泄漏)。

# ---------- 4. 全A等权指数 (日收益 = PIT eligible 股票当日收益等权均值) ----------
all_days = pd.DatetimeIndex(sorted(df['date'].unique()))
print(f'交易日数(加载): {len(all_days)}')
d_ret = df[df['eligible'] & df['ret'].notna()].groupby('date')['ret'].mean().reindex(all_days)
idx = (1+d_ret.fillna(0)).cumprod()
mkt_ret = d_ret

# ---------- 5. Regime 标签 (每日) ----------
# TREND
idx20 = (idx / idx.shift(20) - 1)
regime = pd.DataFrame(index=all_days)
regime['trend'] = np.select([idx20>0.03, idx20<-0.03], ['UP','DOWN'], default='SIDEWAYS')
# BREADTH
uni = df[df['eligible']].copy()
denom = uni.groupby('date').size().reindex(all_days)
nabove = uni[uni['ma20'].notna() & (uni['close_adj']>uni['ma20'])].groupby('date').size().reindex(all_days)
ratio = (nabove/denom).clip(upper=1.0)
regime['breadth'] = np.select([ratio<0.30, ratio>0.70], ['LOW','HIGH'], default='MID')
# VOLATILITY (PIT percentile, 仅用T前历史)
rv20 = mkt_ret.rolling(20).std()*np.sqrt(245)
rv_vals = rv20.values; n_days = len(rv_vals)
pctile = np.full(n_days, np.nan)
for i in range(n_days):
    if np.isnan(rv_vals[i]):
        continue
    hist = rv_vals[max(0,i-252):i]
    hist = hist[~np.isnan(hist)]
    if len(hist) < 100:
        continue
    pctile[i] = np.mean(hist < rv_vals[i])
regime['vol_pctile'] = pctile
regime['vol'] = np.select([pctile<=0.20, pctile>0.90], ['LOW','EXTREME'],
                          default=np.where(pctile<=0.60, 'NORMAL', np.where(pctile<=0.90,'HIGH','WARMUP')))
regime.loc[np.isnan(pctile), 'vol'] = 'WARMUP'
# LIQUIDITY
mamt = df[df['eligible']].groupby('date')['amount'].sum().reindex(all_days)
mamt_ma20 = mamt.rolling(20, min_periods=20).mean()
amt_ratio = mamt/mamt_ma20
regime['liq'] = np.select([amt_ratio<0.80, amt_ratio>1.20], ['LOW','HIGH'], default='NORMAL')

# ---------- 6. 事件: Discovery 区间 oversold (BB_zscore 互斥 bins) ----------
print('提取 oversold 事件...')
disc = df[(df['date']>=DISC0)&(df['date']<=DISC1)]
ev = disc[disc['eligible'] & disc['bb_z'].notna()].copy()
ev['bin'] = np.select(
    [(ev['bb_z']>-2.0)&(ev['bb_z']<=-1.5), (ev['bb_z']>-2.5)&(ev['bb_z']<=-2.0),
     (ev['bb_z']>-3.0)&(ev['bb_z']<=-2.5), (ev['bb_z']<=-3.0)],
    ['B1','B2','B3','B4'], default=None)
ev = ev[ev['bin'].notna()].copy()
print(f'oversold 事件总数(Discovery): {len(ev)}')

# 未来收益: T+1 open -> T+5/T+10 close (causal_otc), 严格按交易日历推进
cal = list(all_days)
next_d = {cal[i]: cal[i+1] for i in range(len(cal)-1)}
adv = {h: {cal[i]: cal[i+h] for i in range(len(cal)-h)} for h in (5,10)}
ev['T1'] = ev['date'].map(next_d)
ev['T5'] = ev['date'].map(adv[5])
ev['T10'] = ev['date'].map(adv[10])
fut_o = df[['ts_code','date','open_adj']].rename(columns={'date':'T1','open_adj':'open_adj_T1'})
fut_c5 = df[['ts_code','date','close_adj']].rename(columns={'date':'T5','close_adj':'close_adj_T5'})
fut_c10 = df[['ts_code','date','close_adj']].rename(columns={'date':'T10','close_adj':'close_adj_T10'})
ev = ev.merge(fut_o, on=['ts_code','T1'], how='left')
ev = ev.merge(fut_c5, on=['ts_code','T5'], how='left')
ev = ev.merge(fut_c10, on=['ts_code','T10'], how='left')
ev['non_tradable_t1'] = ev['open_adj_T1'].isna()
ev['otc5'] = ev['close_adj_T5']/ev['open_adj_T1'] - 1
ev['otc10'] = ev['close_adj_T10']/ev['open_adj_T1'] - 1
ev['miss5'] = ev['close_adj_T5'].isna()
ev['miss10'] = ev['close_adj_T10'].isna()
# regime 标签
ev = ev.merge(regime[['trend','breadth','vol','liq']], left_on='date', right_index=True, how='left')
print(f'non_tradable_t1 事件数: {int(ev["non_tradable_t1"].sum())} (单独标记,不删除,不纳入return统计)')
print(f'otc5 缺失: {int(ev["miss5"].sum())}, otc10 缺失: {int(ev["miss10"].sum())} (缺失则不纳入,数量单独报告)')

# ---------- 7. benchmark: same_oversold_unconditional (日级截面均值再平均, 仅Discovery) ----------
bench = {}
for b in ['B1','B2','B3','B4']:
    for hz, col in [('5D','otc5'),('10D','otc10')]:
        sub = ev[(ev['bin']==b) & ev[col].notna()]
        if len(sub):
            bench[(b,hz)] = sub.groupby('date')[col].mean().mean()
        else:
            bench[(b,hz)] = np.nan

# ---------- 8. 104 Primary cells ----------
print('计算 104 Primary cells...')
rows = []
DIMCOL = {'TREND':'trend','BREADTH':'breadth','VOLATILITY':'vol','LIQUIDITY':'liq'}
for _, r in reg.iterrows():
    dim, rbin = r['regime_dimension'], r['regime_bin']
    ob, hz = r['oversold_bin'], r['forward_horizon']
    col = 'otc5' if hz=='5D' else 'otc10'
    sel = ev[(ev['bin']==ob) & (ev[DIMCOL[dim]]==rbin) & ev[col].notna()]
    n_ev = len(sel); n_days = sel['date'].nunique()
    out = dict(hypothesis_id=r['hypothesis_id'], regime_dimension=dim, regime_bin=rbin,
               oversold_bin=ob, forward_horizon=hz,
               n_stock_events=n_ev, n_independent_days=n_days,
               n_non_tradable_t1=int(ev[(ev['bin']==ob)&(ev[DIMCOL[dim]]==rbin)]['non_tradable_t1'].sum()),
               status='INSUFFICIENT_SAMPLE')
    if n_days < 150 or n_ev == 0:
        rows.append(out); continue
    day = sel.groupby('date')[col].mean()
    bm = bench[(ob,hz)]
    exc = day - bm
    out.update(dict(
        status='VALID_SAMPLE',
        mean_raw_return=float(day.mean()),
        benchmark=float(bm),
        mean_regime_excess=float(exc.mean()),
        median_regime_excess=float(exc.median()),
        win_rate=float((sel[col]>0).mean()),
        std_daily=float(day.std()),
        n_days_used=int(len(day))))
    # HAC (Newey-West) t on daily excess
    x = exc.values; n = len(x)
    mu = x.mean()
    if n > 1 and np.std(x) > 0:
        k = int(np.floor(4*(n/100)**(2/9)))
        k = max(0, min(k, n-2))
        gam = np.correlate(x-mu, x-mu, mode='full')[n-1:]
        gam = gam/ n
        s = gam[0] + 2*sum((1-np.arange(1,k+1)/(k+1))*gam[1:k+1]) if k>0 else gam[0]
        se = np.sqrt(s/n)
        hac_t = mu/se if se>0 else np.nan
    else:
        hac_t = np.nan
    out['hac_t'] = float(hac_t) if not np.isnan(hac_t) else np.nan
    # block bootstrap CI (circular block, L=21, 2000; 每block独立随机起点)
    rng = np.random.default_rng(2020)
    L = 21; B = 2000
    means = np.empty(B)
    if n >= L:
        wrap = np.concatenate([x, x, x])
        for b_ in range(B):
            idx = []
            while len(idx) < n:
                s = rng.integers(0, n)
                idx.extend(range(s, s + L))
            idx = np.array(idx[:n])
            means[b_] = wrap[idx].mean()
        out['ci_lo'] = float(np.percentile(means, 2.5)); out['ci_hi'] = float(np.percentile(means, 97.5))
        out['boot_p_pos'] = float(np.mean(means <= 0))
    else:
        out['ci_lo'] = out['ci_hi'] = out['boot_p_pos'] = np.nan
    rows.append(out)

mat = pd.DataFrame(rows)
# raw p 与 FDR (BH, 全部VALID_SAMPLE)
valid = mat[mat['status']=='VALID_SAMPLE'].copy()
from scipy import stats as sst
def raw_p(t, n):
    if not np.isfinite(t) or n < 2: return np.nan
    return float(2*sst.t.sf(abs(t), n-1))
valid['raw_p'] = [raw_p(t, n) for t, n in zip(valid['hac_t'], valid['n_days_used'])]
pv = valid['raw_p'].dropna().values; m = len(pv)
order = np.argsort(pv); ranked = np.empty(m)
for i, j in enumerate(order): ranked[j] = pv[j]*m/(i+1)
q = np.minimum.accumulate(ranked[::-1])[::-1]
valid['fdr_q'] = q
valid.loc[valid['raw_p'].isna(), 'fdr_q'] = np.nan
mat = mat.merge(valid[['hypothesis_id','raw_p','fdr_q']], on='hypothesis_id', how='left')
mat.to_csv(f'{REPO}/results/regime_discovery_matrix.csv', index=False)

# ---------- 9. 汇总 ----------
print('\n===== REGIME DISCOVERY Phase 1 汇总 =====')
ns = (mat['status']=='VALID_SAMPLE').sum(); ni = (mat['status']=='INSUFFICIENT_SAMPLE').sum()
sig = (mat['fdr_q']<0.05).sum()
pos_ns = ((mat['status']=='VALID_SAMPLE') & (mat['mean_regime_excess']>0) & ((mat['fdr_q']>=0.05)|mat['fdr_q'].isna())).sum()
neg = ((mat['status']=='VALID_SAMPLE') & (mat['mean_regime_excess']<0)).sum()
print(f'VALID_SAMPLE: {ns}   INSUFFICIENT_SAMPLE: {ni}')
print(f'FDR_SIGNIFICANT(q<0.05): {sig}')
print(f'方向为正但不显著: {pos_ns}')
print(f'方向为负: {neg}')
print(f'非正非负(恰为0): {((mat["status"]=="VALID_SAMPLE")&(mat["mean_regime_excess"]==0)).sum()}')
print('\n各维度 VALID 分布:'); print(mat[mat['status']=='VALID_SAMPLE'].groupby('regime_dimension').size())
print('\nFDR显著格:'); print(mat[mat['fdr_q']<0.05][['hypothesis_id','regime_dimension','regime_bin','oversold_bin','forward_horizon','n_independent_days','mean_regime_excess','win_rate','hac_t','raw_p','fdr_q']].to_string())
print('\n矩阵已保存: results/regime_discovery_matrix.csv')
