"""Universe B — feature builder (Phase 0). 只使用 <= T 数据；窗口不足 → NaN。
输出 results/evidence/alpha_factory/universe_b/features/year=YYYY/*.parquet
"""
import os
import numpy as np
import pandas as pd

REPO = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo'
DATA = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/data'
PANEL = os.path.join(REPO, 'results/evidence/alpha_factory/universe_b', 'panel')
OUT = os.path.join(REPO, 'results/evidence/alpha_factory/universe_b', 'features')

IDX_MAP = {'csi300': '000300', 'csi500': '000905', 'csi1000': '000852'}


def load_panel():
    files = []
    for root, _, fs in os.walk(PANEL):
        for f in fs:
            if f.endswith('.parquet'):
                files.append(os.path.join(root, f))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def load_index_returns():
    out = {}
    for name, code in IDX_MAP.items():
        i = pd.read_parquet(os.path.join(REPO, 'data/monthly_bb', f'idx_{code}.parquet'))
        i['date'] = pd.to_datetime(i['trade_date'], format='%Y%m%d', errors='coerce')
        i = i.dropna(subset=['date']).sort_values('date').set_index('date')
        c = i['close'].astype(float)
        r = pd.DataFrame({
            f'{name}_ret_1': c.pct_change(1),
            f'{name}_ret_5': c.pct_change(5),
            f'{name}_ret_20': c.pct_change(20),
            f'{name}_ret_60': c.pct_change(60),
        })
        out[name] = r
    idx = pd.concat(out.values(), axis=1).reset_index()
    idx = idx[(idx['date'] >= pd.Timestamp('2019-01-01')) & (idx['date'] <= pd.Timestamp('2024-12-31'))]
    return idx


def load_industry():
    sm = pd.read_parquet(os.path.join(DATA, 'raw/d1_cache/sector_membership.parquet'))
    sm['in'] = pd.to_datetime(sm['in_date'], format='%Y%m%d', errors='coerce')
    sm['out'] = pd.to_datetime(sm['out_date'], format='%Y%m%d', errors='coerce')
    sm = sm[sm['industry_name'].notna()]
    return sm[['con_code', 'industry_code', 'industry_name', 'in', 'out']]


def compute_time_series_features(p):
    """按股票 groupby 计算时序特征（rolling/移位，只用 <=T）。"""
    g = p.sort_values('date').groupby('ts_code', sort=False)
    close = p['close_adj']
    ret1 = close.groupby(p['ts_code']).pct_change(1)
    feats = pd.DataFrame(index=p.index)
    for h in [1, 2, 3, 5, 10, 20, 40, 60, 120, 250]:
        feats[f'ret_{h}'] = close.groupby(p['ts_code']).pct_change(h)
    # drawdown / 52w high
    def roll_min_max(s, w, kind):
        return s.groupby(p['ts_code']).transform(lambda x: x.rolling(w, min_periods=5).agg(kind))
    for h in [20, 60, 120]:
        rollmin = roll_min_max(close, h, 'min')
        rollmax = roll_min_max(close, h, 'max')
        feats[f'drawdown_{h}'] = rollmin / rollmax - 1.0
    hi52 = roll_min_max(close, 250, 'max')
    feats['distance_52w_high'] = close / hi52 - 1.0
    # volatility
    tr = pd.concat([
        p['high_adj'] - p['low_adj'],
        (p['high_adj'] - p['close'].shift(1) * p['adj_factor']).abs(),
        (p['low_adj'] - p['close'].shift(1) * p['adj_factor']).abs(),
    ], axis=1).max(axis=1)
    atr = tr.groupby(p['ts_code']).transform(lambda x: x.rolling(14, min_periods=5).mean())
    feats['atr14_pct'] = atr / close
    for h in [5, 10, 20, 60]:
        feats[f'vol_{h}'] = ret1.groupby(p['ts_code']).transform(
            lambda x: x.rolling(h, min_periods=5).std())
    feats['range_pct'] = (p['high'] - p['low']) / p['pre_close']
    feats['gap_pct'] = p['open'] / p['pre_close'] - 1.0
    # liquidity
    amt = p['amount']
    feats['log_amount'] = np.log1p(amt)
    feats['amount_ma5'] = amt.groupby(p['ts_code']).transform(lambda x: x.rolling(5, min_periods=2).mean())
    feats['amount_ma20'] = amt.groupby(p['ts_code']).transform(lambda x: x.rolling(20, min_periods=5).mean())
    feats['amount_ma60'] = amt.groupby(p['ts_code']).transform(lambda x: x.rolling(60, min_periods=10).mean())
    feats['amount_ratio_5_20'] = feats['amount_ma5'] / feats['amount_ma20'] - 1.0
    feats['amount_ratio_20_60'] = feats['amount_ma20'] / feats['amount_ma60'] - 1.0
    feats['amount_ma5_pct'] = amt / feats['amount_ma5'] - 1.0
    feats['amount_ma20_pct'] = amt / feats['amount_ma20'] - 1.0
    # trend (MA distance & slope)
    for h in [5, 10, 20, 60, 120, 250]:
        ma = close.groupby(p['ts_code']).transform(lambda x: x.rolling(h, min_periods=h // 2).mean())
        feats[f'distance_ma{h}'] = close / ma - 1.0
        if h in (5, 20, 60):
            ma5 = ma.groupby(p['ts_code']).shift(5) if h == 5 else None
            ma_prev = ma.groupby(p['ts_code']).transform(lambda x: x.shift(5))
            feats[f'ma{h}_slope_pct'] = ma / ma_prev - 1.0
    # BB(20, 2)
    mid = close.groupby(p['ts_code']).transform(lambda x: x.rolling(20, min_periods=10).mean())
    sd = close.groupby(p['ts_code']).transform(lambda x: x.rolling(20, min_periods=10).std(ddof=0))
    feats['bb_z'] = (close - mid) / sd
    feats['bb_width'] = sd / mid
    feats['percent_b'] = (close - (mid - 2 * sd)) / (4 * sd)
    return feats


def cross_section_rank(feats, p):
    """每日横截面 rank（[0,1]）。"""
    date = p['date']
    for col in ['ret_5', 'ret_20', 'atr14_pct', 'bb_z', 'drawdown_20', 'range_pct', 'vol_20']:
        feats[f'{col}_cs_rank'] = feats[col].groupby(date).rank(pct=True)
    feats['amount_cs_rank'] = feats['log_amount'].groupby(date).rank(pct=True)
    feats['bb_width_cs_rank'] = feats['bb_width'].groupby(date).rank(pct=True)
    feats['amount_percentile'] = feats['amount_cs_rank']
    # amount_rank 单独保留（原始 rank / N）
    feats['amount_rank'] = feats['log_amount'].groupby(date).rank() / \
        feats['log_amount'].groupby(date).transform('count')
    return feats


def market_context(p, feats):
    """每日共享的市场特征。"""
    work = p.copy()
    for c in ['ret_1', 'ret_5', 'ret_20', 'ret_60', 'distance_52w_high', 'bb_z']:
        work[c] = feats[c].values
    d = work.groupby('date').agg(
        market_up_ratio=('ret_1', lambda s: (s > 0).mean()),
        market_down_ratio=('ret_1', lambda s: (s < 0).mean()),
        new_high_ratio=('distance_52w_high', lambda s: (s > -1e-9).mean()),
        new_low_ratio=('distance_52w_high', lambda s: (s <= -1 + 1e-9).mean()),
        limit_up_count=('is_limit_up', 'sum'),
        limit_down_count=('is_limit_down', 'sum'),
        bb_signal_breadth=('bb_z', lambda s: (s < -2).mean()),
    )
    # market_vol_20 = 每日市场平均 ret_1 的 20 日滚动 std
    mret = work.groupby('date')['ret_1'].mean().to_frame('mret')
    mret['market_vol_20'] = mret['mret'].rolling(20, min_periods=5).std()
    d = d.join(mret[['market_vol_20']])
    idx = load_index_returns().set_index('date')
    d = d.join(idx)
    return d


def industry_features(p, feats):
    """申万 L1 PIT 行业相对特征。"""
    sm = load_industry()
    sm = sm.rename(columns={'con_code': 'ts_code'})
    # 每日股票-行业归属：按 in/out 窗口 merge_asof
    p2 = p[['date', 'ts_code']].copy()
    for c in ['ret_1', 'ret_5', 'ret_20', 'ret_60']:
        p2[c] = feats[c].values
    # 展开行业窗口为 long：行业成员按 (ts_code, in, out)；merge_asof 需同名列
    mem = sm[['ts_code', 'industry_name', 'in', 'out']].dropna(subset=['in'])
    mem = mem.rename(columns={'in': 'date'})
    p2s = p2.sort_values('date')
    asof_in = pd.merge_asof(p2s,
                            mem.sort_values('date'),
                            on='date', by='ts_code', direction='backward',
                            suffixes=('', '_in'))
    # 失效行业（out < T）置 NaN，不删行
    bad = asof_in['industry_name'].notna() & asof_in['out'].notna() & (asof_in['out'] < asof_in['date'])
    ind_cols = ['industry_name', 'out']
    asof_in.loc[bad, ind_cols] = np.nan
    ind = asof_in.groupby(['industry_name', 'date']).agg(
        industry_ret_1=('ret_1', 'mean'),
        industry_breadth=('ret_1', lambda s: (s > 0).mean()),
    )
    # industry ret_h：用行业内 ret_h 均值
    ind5 = asof_in.groupby(['industry_name', 'date'])['ret_5'].mean().rename('industry_ret_5')
    ind20 = asof_in.groupby(['industry_name', 'date'])['ret_20'].mean().rename('industry_ret_20')
    ind60 = asof_in.groupby(['industry_name', 'date'])['ret_60'].mean().rename('industry_ret_60')
    ind = ind.join(ind5).join(ind20).join(ind60).reset_index()
    merged = asof_in.merge(ind, on=['industry_name', 'date'], how='left')
    # 恢复 p2 原行序（merge_asof 要求按 date 排序）
    merged.index = p2s.index
    merged = merged.sort_index()
    feats['industry_ret_5'] = merged['industry_ret_5']
    feats['industry_ret_20'] = merged['industry_ret_20']
    feats['industry_ret_60'] = merged['industry_ret_60']
    feats['industry_breadth'] = merged['industry_breadth']
    feats['ret_5_minus_industry'] = feats['ret_5'] - feats['industry_ret_5']
    feats['ret_20_minus_industry'] = feats['ret_20'] - feats['industry_ret_20']
    feats['ret_60_minus_industry'] = feats['ret_60'] - feats['industry_ret_60']
    return feats


def build():
    p = load_panel()
    p = p[p['is_suspended'] == False].copy()  # 停牌行不参与特征
    feats = compute_time_series_features(p)
    feats = cross_section_rank(feats, p)
    mc = market_context(p, feats)
    # 市场上下文按 date 合并回（每日共享值广播到当日所有股票）
    mc_rows = mc.reset_index().rename(columns={'index': 'date'})
    mj = pd.merge(p[['date']], mc_rows, on='date', how='left')
    for c in mc.columns:
        feats[c] = mj[c].values
    feats = industry_features(p, feats)
    # 状态变量
    for c in ['is_st_pit', 'is_limit_up', 'is_limit_down', 'listing_days']:
        feats[c] = p[c].values
    feats['is_suspended'] = False
    out = pd.concat([p[['date', 'ts_code']], feats], axis=1)
    out['year'] = out['date'].dt.year
    os.makedirs(OUT, exist_ok=True)
    for y, g in out.groupby('year'):
        yd = os.path.join(OUT, f'year={y}')
        os.makedirs(yd, exist_ok=True)
        g.drop(columns=['year']).to_parquet(os.path.join(yd, 'part.parquet'), index=False)
    return out


if __name__ == '__main__':
    o = build()
    print('feature rows:', len(o), 'cols:', o.shape[1])
