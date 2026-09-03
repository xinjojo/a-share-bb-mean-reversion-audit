"""INDEPENDENT TRADE REPLAY — 统计分析
读取 4 个重放 pkl, 生成:
  independent_trade_episodes.csv / _yearly / _eventday / _concentration / _exit_semantics / _layers / _cross_section
PRIMARY 用 TRADE_EPISODE 为主; ENTRY_LAYER 单独输出.
"""
import os, sys, pickle, bisect
import numpy as np, pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
sys.path.insert(0, ROOT)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
CACHE = os.path.join(OUT, 'independent_replay_per.pkl')

with open(CACHE, 'rb') as f:
    C = pickle.load(f)
days, per, top10_by_date = C['days'], C['per'], C['top10_by_date']

# ---------------- 数据 meta ----------------
df = pd.read_parquet(os.path.join(ROOT, 'data', 'combined_daily.parquet'))
df['date'] = pd.to_datetime(df['date'])
df = df[(df['date'] >= '2020-01-01') & (df['date'] <= '2026-08-25')]
# 当日 amount 百分位
amt = df[['date', 'ts_code', 'amount']].copy()
amt['amount_pct'] = amt.groupby('date')['amount'].rank(pct=True)
amt_map = amt.set_index(['date', 'ts_code'])['amount_pct']
del df
sb = pd.read_parquet(os.path.join(ROOT, 'data', 'raw', 'stock_basic.parquet'))
meta = sb.set_index('ts_code')[['name', 'industry', 'delist_date']].copy()
meta['delist_date'] = pd.to_datetime(meta['delist_date'], errors='coerce')
meta['delisted'] = meta['delist_date'].notna() & (meta['delist_date'] < '2026-08-25')


def per_lookup(tc, dt, field):
    r = per.get(tc)
    if r is None:
        return np.nan
    dts = r['dates']
    pos = bisect.bisect_left(dts, dt)
    if pos >= len(dts) or dts[pos] != dt:
        return np.nan
    return r[field][pos]


def build_epdf(tag, primary):
    with open(os.path.join(OUT, f'independent_ep_{tag}.pkl'), 'rb') as f:
        eps = pickle.load(f)
    rows = []
    for k, e in enumerate(eps):
        sd = pd.Timestamp(e['signal_date'])
        tc = e['ts_code']
        z = np.nan
        m_ = per_lookup(tc, sd, 'bb_mid'); u_ = per_lookup(tc, sd, 'bb_upper'); c_ = per_lookup(tc, sd, 'close_adj')
        if not (np.isnan(m_) or np.isnan(u_) or u_ == m_):
            z = (c_ - m_) * 2.0 / (u_ - m_)
        if np.isnan(z):
            bin_ = 'NA'
        elif z <= -3.0:
            bin_ = 'B4'
        elif z <= -2.5:
            bin_ = 'B3'
        elif z <= -2.0:
            bin_ = 'B2'
        elif z <= -1.5:
            bin_ = 'B1'
        else:
            bin_ = 'ABOVE'
        a_ = per_lookup(tc, sd, 'amount')
        aq = amt_map.get((sd, tc), np.nan) if not pd.isna(a_) else np.nan
        mta = meta.loc[tc] if tc in meta.index else None
        rows.append(dict(
            episode_id=k, ts_code=tc,
            name=mta['name'] if mta is not None else None,
            industry=mta['industry'] if mta is not None else None,
            delisted=bool(mta['delisted']) if mta is not None else False,
            signal_date=e['signal_date'], entry_date=e['entry_date'], exit_date=e['exit_date'],
            exit_type=e['exit_type'], levels_used=e['levels_used'], hold_days=e['hold_days'],
            total_cost=e['total_cost'], proceeds=e['proceeds'], pnl=e['pnl'],
            return_pct=e['return_pct'], signal_z=z, oversold_bin=bin_,
            signal_amount=a_, amount_pct=aq,
            signal_year=pd.Timestamp(e['signal_date']).year))
    d = pd.DataFrame(rows)
    d['amount_quintile'] = pd.cut(d['amount_pct'], [0, .2, .4, .6, .8, 1.0],
                                   labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'], include_lowest=True)
    return d


def headline(d, label=''):
    n = len(d)
    if n == 0:
        return dict(label=label, n=0)
    r = d['return_pct']
    pnl = d['pnl']
    pos = pnl[pnl > 0].sum(); neg = pnl[pnl < 0].sum()
    pf = pos / abs(neg) if neg != 0 else np.inf
    return dict(label=label, n=n,
                mean=r.mean(), median=r.median(), win_rate=(pnl > 0).mean() * 100,
                p10=r.quantile(.10), p25=r.quantile(.25), p75=r.quantile(.75), p90=r.quantile(.90),
                mean_hold=d['hold_days'].mean(), median_hold=d['hold_days'].median(),
                mean_pnl=pnl.mean(), profit_factor=pf,
                expected_ret=r.mean())


def yearly(d):
    out = []
    for y, g in d.groupby('signal_year'):
        h = headline(g)
        out.append(dict(year=y, **h))
    return pd.DataFrame(out)


def timesplit(d):
    a = d[d['signal_year'] <= 2023]
    b = d[d['signal_year'] >= 2024]
    return pd.DataFrame([headline(a, '2020-2023'), headline(b, '2024-2026')])


def eventday(d, label=''):
    s = d[d['signal_date'].notna()].copy()
    s['sd'] = pd.to_datetime(s['signal_date'])
    daily = s.groupby('sd')['return_pct'].mean()
    n_days = len(daily)
    mean_ = daily.mean()
    med_ = daily.median()
    pos_rate = (daily > 0).mean() * 100
    # HAC (event-day series)
    import statsmodels.api as sm
    y = daily.to_numpy()
    K = int(np.floor(4 * (n_days / 100) ** (2 / 9)))
    K = max(0, min(K, n_days - 2))
    X = np.ones((n_days, 1))
    res = sm.OLS(y, X).fit(cov_type='HAC', cov_kwds={'maxlags': K})
    t = res.tvalues[0]
    se = res.bse[0]
    p = 2 * (1 - __import__('scipy').stats.t.cdf(abs(t), n_days - 1))
    ci_lo = mean_ - 1.96 * se
    ci_hi = mean_ + 1.96 * se
    return dict(label=label, n_event_days=n_days, mean_daily=mean_, median_daily=med_,
                pos_day_rate=pos_rate, hac_t=t, hac_p=p, hac_ci_lo=ci_lo, hac_ci_hi=ci_hi)


def concentration(d):
    pnl = d['pnl'].sort_values()
    total = pnl.sum()
    n = len(d)
    top1 = int(np.ceil(n * 0.01)); top5 = int(np.ceil(n * 0.05))
    top_pnl = d['pnl'].nlargest(top1).sum()
    top5_pnl = d['pnl'].nlargest(top5).sum()
    worst_pnl = d['pnl'].nsmallest(top1).sum()
    best1_excl = d['pnl'].nlargest(top1).index
    best5_excl = d['pnl'].nlargest(top5).index
    keep1 = d.drop(index=best1_excl)
    keep5 = d.drop(index=best5_excl)
    stk_pnl = d.groupby('ts_code')['pnl'].sum().sort_values()
    top10_stk = stk_pnl.tail(10).index
    keep_stk = d[~d['ts_code'].isin(top10_stk)]
    ind_pnl = d.groupby('industry')['pnl'].sum().sort_values()
    top_ind = ind_pnl.tail(1).index[0] if len(ind_pnl) else None
    keep_ind = d[d['industry'] != top_ind]
    return dict(label='PRIMARY_DYN',
                n=n, total_pnl=total, top1pct_pnl=top_pnl, top1pct_share=top_pnl / total,
                top5pct_pnl=top5_pnl, top5pct_share=top5_pnl / total, worst1pct_pnl=worst_pnl,
                best1_excl_mean=keep1['return_pct'].mean(), best1_excl_median=keep1['return_pct'].median(),
                best5_excl_mean=keep5['return_pct'].mean(), best5_excl_median=keep5['return_pct'].median(),
                excl_top10stk_mean=keep_stk['return_pct'].mean(), excl_top10stk_median=keep_stk['return_pct'].median(),
                top_industry=top_ind, excl_top_ind_mean=keep_ind['return_pct'].mean(),
                excl_top_ind_median=keep_ind['return_pct'].median())


def cross_section(d):
    rows = []
    # amount quintile
    for q, g in d.groupby('amount_quintile', observed=True):
        h = headline(g)
        rows.append(dict(dim='amount_quintile', group=str(q), **h))
    # oversold bin
    for b, g in d.groupby('oversold_bin'):
        h = headline(g)
        rows.append(dict(dim='oversold_bin', group=str(b), **h))
    # industry (top15 by count)
    for ind, g in d.groupby('industry'):
        rows.append(dict(dim='industry', group=str(ind), **headline(g)))
    return pd.DataFrame(rows)


# ============================================================
# 主
# ============================================================
pdyn = build_epdf('PRIMARY_DYN', True)
print('PRIMARY_DYN episodes:', len(pdyn), ' delisted:', pdyn['delisted'].sum())

# 1) episodes.csv
pdyn.sort_values(['signal_date', 'ts_code']).to_csv(os.path.join(OUT, 'independent_trade_episodes.csv'), index=False)

# 2) yearly.csv
y = yearly(pdyn)
y.to_csv(os.path.join(OUT, 'independent_trade_yearly.csv'), index=False)
print('\n=== PRIMARY_DYN YEARLY ==='); print(y.round(3).to_string(index=False))

# 3) timesplit
ts = timesplit(pdyn)
print('\n=== TIMESPLIT ==='); print(ts.round(3).to_string(index=False))
ts.to_csv(os.path.join(OUT, 'independent_trade_timesplit.csv'), index=False)

# 4) eventday
ed = pd.DataFrame([eventday(pdyn, 'PRIMARY_DYN')])
print('\n=== EVENTDAY (HAC) ==='); print(ed.round(4).to_string(index=False))
ed.to_csv(os.path.join(OUT, 'independent_trade_eventday.csv'), index=False)

# 5) concentration
cn = pd.DataFrame([concentration(pdyn)])
print('\n=== CONCENTRATION ==='); print(cn.round(4).to_string(index=False))
cn.to_csv(os.path.join(OUT, 'independent_trade_concentration.csv'), index=False)

# 6) cross_section
cs = cross_section(pdyn)
cs.to_csv(os.path.join(OUT, 'independent_trade_cross_section.csv'), index=False)
top_cs = cs[cs['dim'] == 'amount_quintile'][['group', 'n', 'mean', 'median', 'win_rate']]
print('\n=== CROSS_SECTION amount_quintile ==='); print(top_cs.round(3).to_string(index=False))
bin_cs = cs[cs['dim'] == 'oversold_bin'][['group', 'n', 'mean', 'median', 'win_rate']]
print('\n=== CROSS_SECTION oversold_bin ==='); print(bin_cs.round(3).to_string(index=False))

# 7) exit_semantics
sem = []
for tag, lab in [('PRIMARY_DYN', 'STRICT_C_dynamic_touch'),
                 ('PRIMARY_PREV', 'STRICT_A_prev_bb_upper'),
                 ('PRIMARY_CONFIRM', 'STRICT_B_close_confirm_next')]:
    d = build_epdf(tag, True)
    h = headline(d)
    sem.append(dict(exit_mode=lab, **h))
semdf = pd.DataFrame(sem)
print('\n=== EXIT SEMANTICS ==='); print(semdf.round(3).to_string(index=False))
semdf.to_csv(os.path.join(OUT, 'independent_trade_exit_semantics.csv'), index=False)

# 8) layers (ENTRY_LAYER) — PRIMARY_DYN
with open(os.path.join(OUT, 'independent_ep_PRIMARY_DYN.pkl'), 'rb') as f:
    eps = pickle.load(f)
lrows = []
for k, e in enumerate(eps):
    for lr in e['layers']:
        lrows.append(dict(episode_id=k, level=lr['level'], layer_pnl=lr['layer_pnl'],
                          layer_return_pct=lr['layer_return_pct']))
layers = pd.DataFrame(lrows)
lh = headline(layers.rename(columns={'return_pct': 'layer_return_pct'}) ) if False else None
ly = layers.groupby('level')['layer_pnl'].agg(['count', 'mean', lambda s: (s > 0).mean() * 100])
ly.columns = ['n', 'mean_pnl', 'win_rate']
print('\n=== ENTRY_LAYER (PRIMARY_DYN) ==='); print(ly.round(2).to_string())
layers.to_csv(os.path.join(OUT, 'independent_trade_layers.csv'), index=False)

# 9) SECONDARY 核心统计
ps = build_epdf('SECONDARY_DYN', False)
ps.sort_values(['signal_date', 'ts_code']).to_csv(os.path.join(OUT, 'independent_trade_episodes_secondary.csv'), index=False)
hs = headline(ps, 'SECONDARY_DYN')
print('\n=== SECONDARY_DYN HEADLINE ==='); print(hs)
ys = yearly(ps)
ys.to_csv(os.path.join(OUT, 'independent_trade_yearly_secondary.csv'), index=False)
print('\n=== SECONDARY YEARLY ==='); print(ys.round(3).to_string(index=False))
eds = pd.DataFrame([eventday(ps, 'SECONDARY_DYN')])
eds.to_csv(os.path.join(OUT, 'independent_trade_eventday_secondary.csv'), index=False)
print('\n=== SECONDARY EVENTDAY ==='); print(eds.round(4).to_string(index=False))
print('\nALL STATS DONE')
