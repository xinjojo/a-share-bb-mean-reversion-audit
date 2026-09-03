#!/usr/bin/env python3
"""审计交叉验证: 对 5 个随机 VALID cells 用第二套独立实现重算
- event dates / conditional mean / unconditional benchmark / excess / HAC t / raw p
- 聚合路径: dict 累加 (非 pandas reindex), HAC: statsmodels OLS + HAC
- 与 regime_discovery_matrix_v2.csv 对比
"""
import sys, os, bisect
import numpy as np, pandas as pd
import statsmodels.api as sm

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = f'{ROOT}/audit_package/github_repo'
DISC0, DISC1 = pd.Timestamp('2020-01-01'), pd.Timestamp('2022-12-31')

# ---- 数据 (与主脚本相同) ----
dfw = pd.read_parquet(f'{ROOT}/data/warmup_daily_2018_2019.parquet')
dfc = pd.read_parquet(f'{ROOT}/data/combined_daily.parquet', columns=['date','ts_code','open','close','amount','adj_factor'])
dfc = dfc[dfc['date'] <= pd.Timestamp('2023-02-28')]
st = pd.read_parquet(f'{ROOT}/data/pit_st_daily.parquet', columns=['date','ts_code','is_st_pit'])
dfc = dfc.merge(st, on=['date','ts_code'], how='left')
dfw = dfw[['ts_code','date','open','close','amount','adj_factor','is_st_pit']]
dfc = dfc[['ts_code','date','open','close','amount','adj_factor','is_st_pit']]
df = pd.concat([dfw, dfc], ignore_index=True).sort_values(['ts_code','date'])
df['is_st_pit'] = df['is_st_pit'].fillna(False)
sb = pd.read_parquet(f'{ROOT}/data/raw/stock_basic.parquet', columns=['ts_code','list_date'])
tc = pd.read_parquet(f'{ROOT}/data/raw/trade_cal_full.parquet')
trade_dates = sorted(pd.to_datetime(tc['date']))

df['close_adj'] = df['close']*df['adj_factor']
df['open_adj'] = df['open']*df['adj_factor']
df['ret'] = df.groupby('ts_code', sort=False)['close_adj'].pct_change()
g = df.groupby('ts_code', sort=False)
df['ma20'] = g['close_adj'].transform(lambda x: x.rolling(20, min_periods=20).mean())
df['std20'] = g['close_adj'].transform(lambda x: x.rolling(20, min_periods=20).std(ddof=1))
df['bb_z'] = (df['close_adj']-df['ma20'])/df['std20']

sb['ld'] = sb['list_date'].apply(lambda s: pd.Timestamp(str(int(s))) if pd.notna(s) else pd.NaT)
ld2elig = {}
for ld in sb['ld'].dropna().unique():
    pos = bisect.bisect_left(trade_dates, ld)
    ld2elig[ld] = trade_dates[pos+59] if pos+59 < len(trade_dates) else pd.Timestamp.max
df['elig_date'] = df['ts_code'].map(sb.set_index('ts_code')['ld'].to_dict()).map(ld2elig)
df['eligible'] = (df['date']>=df['elig_date']) & (~df['is_st_pit']) & df['close_adj'].notna()

all_days = pd.DatetimeIndex(sorted(df['date'].unique()))
uni = df[df['eligible']]
d_ret = uni[uni['ret'].notna()].groupby('date')['ret'].mean().reindex(all_days)
idx = (1+d_ret.fillna(0)).cumprod()
mkt_ret = d_ret

# regime (完整 4 维, 与预注册公式一致)
regime = pd.DataFrame(index=all_days)
idx20 = idx/idx.shift(20)-1
regime['trend'] = np.where(idx20.isna(),'WARMUP',np.select([idx20>0.03,idx20<-0.03],['UP','DOWN'],default='SIDEWAYS'))
denom = uni.groupby('date').size().reindex(all_days)
nabove = uni[uni['ma20'].notna()&(uni['close_adj']>uni['ma20'])].groupby('date').size().reindex(all_days)
ratio = (nabove/denom).clip(upper=1.0)
regime['breadth'] = np.where(ratio.isna(),'WARMUP',np.select([ratio<0.30,ratio>0.70],['LOW','HIGH'],default='MID'))
rv20 = mkt_ret.rolling(20).std()*np.sqrt(245)
rvv = rv20.values; nD = len(rvv)
pctile = np.full(nD, np.nan)
for i in range(nD):
    if np.isnan(rvv[i]): continue
    hist = rvv[max(0,i-252):i]; hist = hist[~np.isnan(hist)]
    if len(hist) < 100: continue
    pctile[i] = np.mean(hist < rvv[i])
regime['vol'] = np.select([np.isnan(pctile), pctile<=0.20, pctile>0.90],
                          ['WARMUP','LOW','EXTREME'],
                          default=np.where(pctile<=0.60,'NORMAL',np.where(pctile<=0.90,'HIGH','WARMUP')))
mamt = uni.groupby('date')['amount'].sum().reindex(all_days)
mamt_ma20 = mamt.rolling(20, min_periods=20).mean()
amt_ratio = mamt/mamt_ma20
regime['liq'] = np.where(amt_ratio.isna(),'WARMUP',np.select([amt_ratio<0.80,amt_ratio>1.20],['LOW','HIGH'],default='NORMAL'))

# 事件
disc = df[(df['date']>=DISC0)&(df['date']<=DISC1)]
ev = disc[disc['eligible']&disc['bb_z'].notna()].copy()
ev['bin'] = np.select([(ev['bb_z']>-2.0)&(ev['bb_z']<=-1.5),(ev['bb_z']>-2.5)&(ev['bb_z']<=-2.0),
                       (ev['bb_z']>-3.0)&(ev['bb_z']<=-2.5),(ev['bb_z']<=-3.0)],['B1','B2','B3','B4'],default=None)
ev = ev[ev['bin'].notna()].copy()
cal = list(all_days)
nxt = {cal[i]:cal[i+1] for i in range(len(cal)-1)}
adv = {h:{cal[i]:cal[i+h] for i in range(len(cal)-h)} for h in (5,10)}
ev['T1']=ev['date'].map(nxt); ev['T5']=ev['date'].map(adv[5]); ev['T10']=ev['date'].map(adv[10])
fo = df[['ts_code','date','open_adj']].rename(columns={'date':'T1','open_adj':'o1'})
fc5 = df[['ts_code','date','close_adj']].rename(columns={'date':'T5','close_adj':'c5'})
fc10 = df[['ts_code','date','close_adj']].rename(columns={'date':'T10','close_adj':'c10'})
ev = ev.merge(fo,on=['ts_code','T1'],how='left').merge(fc5,on=['ts_code','T5'],how='left').merge(fc10,on=['ts_code','T10'],how='left')
ev['otc5']=ev['c5']/ev['o1']-1; ev['otc10']=ev['c10']/ev['o1']-1
for _k, _v in [('trend',regime['trend']),('breadth',regime['breadth']),('vol',regime['vol']),('liq',regime['liq'])]:
    ev['rg_'+_k] = ev['date'].map(_v.astype(str)).values.astype(object)
DIML = {'TREND':'trend','BREADTH':'breadth','VOLATILITY':'vol','LIQUIDITY':'liq'}

# ---- 独立聚合: dict 累加 ----
def indep_cell(bin_, hz, rbin, diml, seed):
    col = 'otc5' if hz=='5D' else 'otc10'
    sub = ev[(ev['bin']==bin_)&ev[col].notna()]
    # regime 匹配 (独立: 按维度选列, 不含 WARMUP)
    rg_map = ev[['date','rg_'+diml]].drop_duplicates().set_index('date')['rg_'+diml].to_dict()
    sub = sub[sub['date'].map(lambda d: rg_map.get(d)==rbin)]
    if len(sub)==0: return None
    # 事件日集合 (独立: 用 set)
    ev_days = sorted(set(sub['date']))
    # 每事件日截面均值 (dict 累加)
    sums, cnts = {}, {}
    for d, v in zip(sub['date'], sub[col]):
        sums[d] = sums.get(d,0.0)+v; cnts[d] = cnts.get(d,0)+1
    y_cell = {d: sums[d]/cnts[d] for d in ev_days}
    n_r = len(ev_days)
    # unconditional benchmark: 全部事件日 (bin+horizon, 不区 regime)
    sub_all = ev[(ev['bin']==bin_)&ev[col].notna()]
    sums_a, cnts_a = {}, {}
    for d, v in zip(sub_all['date'], sub_all[col]):
        sums_a[d] = sums_a.get(d,0.0)+v; cnts_a[d] = cnts_a.get(d,0)+1
    y_all = {d: sums_a[d]/cnts_a[d] for d in sorted(set(sub_all['date']))}
    bm = np.mean(list(y_all.values()))
    yv = np.array([y_cell[d] for d in ev_days])
    cond = yv.mean()
    exc = cond - bm
    # HAC (statsmodels)
    D = np.array([1.0 if d in y_cell else 0.0 for d in sorted(y_all.keys())])
    Y = np.array([y_all[d] for d in sorted(y_all.keys())])
    n_all = len(Y)
    K = int(np.floor(4*(n_all/100)**(2/9))); K=max(0,min(K,n_all-2))
    X = np.column_stack([np.ones(n_all),D])
    res = sm.OLS(Y,X).fit(cov_type='HAC',cov_kwds={'maxlags':K})
    beta, se = res.params[1], res.bse[1]
    t = beta/se
    from scipy import stats as sst
    p = float(2*sst.t.sf(abs(t), n_all-2))
    return dict(n_event_days=n_r, cond_mean=cond, benchmark=bm, excess=exc,
                hac_t=t, raw_p=p, hac_se=se, n_stock_events=len(sub))

# ---- 随机 5 个 VALID cells ----
mat = pd.read_csv(f'{REPO}/results/regime_discovery_matrix_v2.csv')
valid = mat[mat['status']=='VALID_SAMPLE']
rng = np.random.default_rng(42)
pick = valid.sample(n=5, random_state=42)
print('=== 独立交叉验证 (seed=42) ===')
print(f'{"id":6} {"dim":10} {"bin":5} {"ob":3} {"hz":4} | {"事件日":>5} {"cond":>8} {"bench":>8} {"excess":>8} | 矩阵excess   | {"t":>7}  矩阵t    | {"raw_p":>8} 矩阵p')
ok = True
for _, r in pick.iterrows():
    dim = r['regime_dimension']; diml = DIML[dim]
    rbin, ob, hz = r['regime_bin'], r['oversold_bin'], r['forward_horizon']
    res = indep_cell(ob, hz, rbin, diml, None)
    if res is None:
        print(f'{r["hypothesis_id"]}: MISSING'); continue
    m = dict(cond_mean=r['mean_raw_return'], benchmark=r['benchmark'], excess=r['mean_regime_excess'],
             hac_t=r['hac_t'], raw_p=r['raw_p'], n_event_days=r['n_event_days'])
    de = abs(res['excess']-m['excess']); dt = abs(res['hac_t']-m['hac_t'])
    ok = ok and de < 5e-4 and dt < 0.05
    print(f'{r["hypothesis_id"]:6} {dim:10} {rbin:5} {ob:3} {hz:4} | {res["n_event_days"]:>5} {res["cond_mean"]:>8.4f} {res["benchmark"]:>8.4f} {res["excess"]:>8.4f} | {m["excess"]:>8.4f}   | {res["hac_t"]:>7.2f} {m["hac_t"]:>7.2f}  | {res["raw_p"]:>8.4f} {m["raw_p"]:>8.4f}')
print()
print('CROSS-CHECK RESULT:', 'PASS' if ok else 'FAIL')
