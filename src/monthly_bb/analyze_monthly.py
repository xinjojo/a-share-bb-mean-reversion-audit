"""MONTHLY-BB-MR 统计分析（冻结口径，见 MONTHLY_BB_ALPHA_REGISTRY.md）
- 描述统计 / 三个 benchmark / bootstrap+permutation / cluster by signal_month
- market-relative / size gradient / worst cases / decade
- 输出 CSV -> results/evidence/monthly_bb/
"""
import os, glob
import numpy as np
import pandas as pd
from scipy import stats

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'monthly_bb')
DATA_DIR = os.path.abspath(DATA_DIR)
OUT = os.path.join(os.path.dirname(__file__), '..', '..', 'results', 'evidence', 'monthly_bb')
OUT = os.path.abspath(OUT)
os.makedirs(OUT, exist_ok=True)

HORIZONS = [1, 3, 6, 12]
DEV_END = pd.Timestamp('2024-12-31')
EXPOSED_START = pd.Timestamp('2025-01-01')
TOP_N = [100, 300, 500]
NB = 1000
RNG = np.random.default_rng(20260907)


def load_mcap_map():
    """月末 mcap parquet -> {pm: df}。"""
    out = {}
    for f in glob.glob(os.path.join(DATA_DIR, 'mcap', 'mcap_*.parquet')):
        ds = os.path.basename(f)[5:13]
        pm = pd.Timestamp(ds).to_period('M')
        out[pm] = pd.read_parquet(f)[['ts_code', 'total_mv']]
    return out


def add_universe(sig, mcap_map):
    """PIT 市值分组：signal 当月月末 total_mv 排名 -> Top100/300/500 或 全A。"""
    sig = sig.copy()
    sig['universe'] = 'ALL_A'
    sig['mv_rank'] = np.nan
    sig['total_mv'] = np.nan
    for pm, mdf in mcap_map.items():
        mask = sig['pm'] == pm
        if mask.sum() == 0:
            continue
        mdf = mdf.dropna(subset=['total_mv']).copy()
        mdf['rank'] = mdf['total_mv'].rank(ascending=False, method='first')
        rk = sig.loc[mask, 'ts_code'].map(mdf.set_index('ts_code')['rank'])
        mv = sig.loc[mask, 'ts_code'].map(mdf.set_index('ts_code')['total_mv'])
        sig.loc[mask, 'mv_rank'] = rk
        sig.loc[mask, 'total_mv'] = mv
    def assign(u):
        sig.loc[(sig['mv_rank'] <= u) & (sig['mv_rank'].notna()), 'universe'] = f'TOP{u}'
    for u in TOP_N:
        assign(u)
    sig['universe_clean'] = sig['universe']
    # 无市值数据（早期缺 daily_basic）保持 ALL_A（README 声明）
    return sig


def desc_stats(df, col):
    if df[col].dropna().empty:
        return {}
    x = df[col].dropna()
    qs = np.nanpercentile(x, [5, 10, 25, 50, 75, 90, 95])
    return dict(
        N=len(x), censored=int(df[f'censored_{col.split("_")[1] if "_" in col else ""}m'].sum()) if False else np.nan,
        mean=x.mean(), median=x.median(), std=x.std(), variance=x.var(),
        P5=qs[0], P10=qs[1], P25=qs[2], P50=qs[3], P75=qs[4], P90=qs[5], P95=qs[6],
        positive_rate=(x > 0).mean(),
        ge5=(x >= 0.05).mean(), ge10=(x >= 0.10).mean(), ge20=(x >= 0.20).mean(),
        lt_m10=(x < -0.10).mean(), lt_m20=(x < -0.20).mean(), lt_m30=(x < -0.30).mean(),
        max=x.max(), min=x.min(),
    )


def build_desc(sig, key_cols):
    rows = []
    for (univ, role), g in sig.groupby(['universe_clean', 'episode_role']):
        for h in HORIZONS:
            for tag, col in [(f'CC{h}M', f'ret_cc_{h}m'), (f'EC{h}M', f'ret_ec_{h}m')]:
                d = desc_stats(g, col)
                d.update(universe=univ, role=role, horizon=tag, dev=(g['pm'].max().end_time <= DEV_END))
                rows.append(d)
    return pd.DataFrame(rows)


def benchmark_same_stock_random(sig, m, n_boot=NB):
    """B1：同股票随机月份（匹配年份）。对每个 signal，从同股同年非信号月抽样 horizon 收益。"""
    m = m.copy()
    # m 上重建 signal 标记（signal 月 = sig 表内出现过的 ts_code×pm）
    sigmark = sig[['ts_code', 'pm']].drop_duplicates().copy()
    sigmark['signal'] = 1
    m = m.merge(sigmark, on=['ts_code', 'pm'], how='left')
    m['signal'] = m['signal'].fillna(0)
    for h in HORIZONS:
        g = m.groupby('ts_code')
        m[f'rc_{h}'] = g['close_adj'].shift(-h) / m['close_adj'] - 1.0
    m['year'] = m['pm'].dt.year
    res = []
    for h in HORIZONS:
        col = f'rc_{h}'
        sig_ = sig[sig['pm'] <= DEV_END]
        obs = sig_[f'ret_cc_{h}m'].dropna()
        m_no = m[(m['signal'] == 0) & m[col].notna()].copy()
        matches = []
        for (tc, yr), gs in sig_.groupby(['ts_code', 'year']):
            pool = m_no[(m_no['ts_code'] == tc) & (m_no['year'] == yr)][col].values
            if len(pool) == 0:
                matches.extend([np.nan] * len(gs))
            else:
                matches.extend(RNG.choice(pool, size=len(gs), replace=True))
        null = np.array(matches, dtype=float)
        both = pd.DataFrame({'obs': obs.values, 'null': null}).dropna()
        if len(both) < 30:
            continue
        diff_mean = both['obs'].mean() - both['null'].mean()
        diff_med = both['obs'].median() - both['null'].median()
        boots = []
        for _ in range(n_boot):
            idx = RNG.integers(0, len(both), len(both))
            boots.append(both['obs'].iloc[idx].mean() - both['null'].iloc[idx].mean())
        boots = np.array(boots)
        ci = np.percentile(boots, [2.5, 97.5])
        perm = []
        for _ in range(n_boot):
            flip = RNG.integers(0, 2, len(both))
            d = both['obs'].values - both['null'].values
            perm.append(np.mean(d * (1 - 2 * flip)))
        perm = np.array(perm)
        pval = (np.abs(perm) >= np.abs(diff_mean)).mean()
        pooled = np.concatenate([both['obs'].values, both['null'].values])
        cohens_d = diff_mean / pooled.std(ddof=1) if pooled.std(ddof=1) > 0 else np.nan
        res.append(dict(horizon=f'{h}M', n=len(both), obs_mean=both['obs'].mean(),
                        null_mean=both['null'].mean(), diff_mean=diff_mean,
                        obs_median=both['obs'].median(), null_median=both['null'].median(),
                        diff_median=diff_med, ci_low=ci[0], ci_high=ci[1],
                        perm_p=pval, cohens_d=cohens_d))
    return pd.DataFrame(res)


def benchmark_unconditional(sig, m, n_boot=NB):
    """B2：同股票无条件 forward 收益分布（全部月份均值）。"""
    m = m.copy()
    for h in HORIZONS:
        g = m.groupby('ts_code')
        m[f'rc_{h}'] = g['close_adj'].shift(-h) / m['close_adj'] - 1.0
    res = []
    for h in HORIZONS:
        col = f'rc_{h}'
        obs = sig[sig['pm'] <= DEV_END][f'ret_cc_{h}m'].dropna()
        tcs = sig['ts_code'].unique()
        null_all = m[m['ts_code'].isin(tcs)][col].dropna().values
        boots = []
        for _ in range(n_boot):
            idx = RNG.integers(0, len(obs), len(obs))
            boots.append(obs.iloc[idx].mean())
        ci = np.percentile(boots, [2.5, 97.5])
        res.append(dict(horizon=f'{h}M', n=len(obs), obs_mean=obs.mean(),
                        unconditional_mean=null_all.mean(), unconditional_median=np.median(null_all),
                        ci_low=ci[0], ci_high=ci[1]))
    return pd.DataFrame(res)


def cluster_bootstrap(sig, n_boot=NB):
    """按 signal_month 聚类 bootstrap：以月为抽样单元。"""
    res = []
    for h in HORIZONS:
        col = f'ret_cc_{h}m'
        s = sig[sig['pm'] <= DEV_END][['pm', col]].dropna()
        months = s['pm'].unique()
        means = []
        for _ in range(n_boot):
            msel = RNG.choice(months, size=len(months), replace=True)
            sub = s[s['pm'].isin(msel)]
            means.append(sub[col].mean())
        means = np.array(means)
        res.append(dict(horizon=f'{h}M', n_months=len(months), obs_mean=s[col].mean(),
                        ci_low=np.percentile(means, 2.5), ci_high=np.percentile(means, 97.5),
                        sd_month=np.std(means)))
    return pd.DataFrame(res)


def calendar_month_agg(sig):
    rows = []
    for h in HORIZONS:
        s = sig[sig['pm'] <= DEV_END][['pm', f'ret_cc_{h}m']].dropna()
        agg = s.groupby('pm')[f'ret_cc_{h}m'].mean()
        rows.append(dict(horizon=f'{h}M', n_months=len(agg),
                         month_mean=agg.mean(), month_median=agg.median(),
                         month_positive=(agg > 0).mean()))
    return pd.DataFrame(rows)


def size_gradient(sig):
    rows = []
    for h in HORIZONS:
        col = f'ret_cc_{h}m'
        for u in ['ALL_A', 'TOP500', 'TOP300', 'TOP100']:
            s = sig[(sig['universe_clean'] == u) & (sig['pm'] <= DEV_END)][col].dropna()
            if len(s) < 10:
                continue
            rows.append(dict(horizon=f'{h}M', universe=u, n=len(s), mean=s.mean(),
                             median=s.median(), positive=(s > 0).mean()))
    return pd.DataFrame(rows)


def market_relative(sig):
    rows = []
    for h in HORIZONS:
        col = f'excess_cc_{h}m'
        for u in sig['universe_clean'].unique():
            s = sig[(sig['universe_clean'] == u) & (sig['pm'] <= DEV_END)][col].dropna()
            rows.append(dict(horizon=f'{h}M', universe=u, n=len(s), mean=s.mean(),
                             median=s.median(), positive=(s > 0).mean()))
    return pd.DataFrame(rows)


def worst_cases(sig):
    col12 = 'ret_cc_12m'
    w = sig[(sig['pm'] <= DEV_END) & sig[col12].notna()].copy()
    w = w[w[col12] < -0.20]
    w['worst'] = w[col12]
    return w[['ts_code', 'pm', 'month_end_date', 'ret_cc_12m', 'mae_12m', 'universe_clean']].sort_values('worst')


def decade_table(sig):
    rows = []
    for h in HORIZONS:
        col = f'ret_cc_{h}m'
        for (d0, d1, label) in [(2005, 2009, '2005-2009'), (2010, 2014, '2010-2014'),
                                (2015, 2019, '2015-2019'), (2020, 2024, '2020-2024'),
                                (2025, 2100, '2025+')]:
            s = sig[(sig['pm'].dt.year >= d0) & (sig['pm'].dt.year <= d1)][col].dropna()
            rows.append(dict(horizon=f'{h}M', decade=label, n=len(s), mean=s.mean(),
                             median=s.median(), positive=(s > 0).mean(),
                             mae=sig[(sig['pm'].dt.year >= d0) & (sig['pm'].dt.year <= d1)][f'mae_{h}m'].dropna().mean()))
    return pd.DataFrame(rows)


def index_signal_detail(sig_idx):
    """指数全部信号明细（manual review）。"""
    return sig_idx[['ts_code', 'pm', 'month_end_date', 'close_adj', 'bb_lower', 'bb_z',
                    'ret_cc_1m', 'ret_cc_3m', 'ret_cc_6m', 'ret_cc_12m',
                    'mfe_6m', 'mae_6m', 'mfe_12m', 'mae_12m']]


def main():
    print('== load signals ==')
    sig = pd.read_parquet(os.path.join(DATA_DIR, 'monthly_signals.parquet'))
    m = pd.read_parquet(os.path.join(DATA_DIR, 'monthly_panel.parquet'))
    sig['pm'] = sig['pm'].astype('period[M]')
    sig['episode_role'] = np.where(sig['NEW_EPISODE'] == 1, 'NEW_EPISODE', 'REPEAT_SIGNAL')
    sig['year'] = sig['pm'].dt.year
    print(f'  信号 {len(sig)}（NEW_EPISODE {sig["NEW_EPISODE"].sum()}）')

    print('== add PIT universe ==')
    mcap_map = load_mcap_map()
    sig = add_universe(sig, mcap_map)

    print('== desc stats ==')
    ds = build_desc(sig, None)
    ds.to_csv(os.path.join(OUT, 'monthly_desc_stats.csv'), index=False)

    # 开发期主表（NEW_EPISODE）
    dev = sig[(sig['pm'] <= DEV_END) & (sig['NEW_EPISODE'] == 1)].copy()

    print('== B1 same-stock random month ==')
    b1 = benchmark_same_stock_random(dev, m)
    b1.to_csv(os.path.join(OUT, 'benchmark_same_stock_random.csv'), index=False)

    print('== B2 unconditional ==')
    b2 = benchmark_unconditional(dev, m)
    b2.to_csv(os.path.join(OUT, 'benchmark_unconditional.csv'), index=False)

    print('== cluster bootstrap ==')
    cb = cluster_bootstrap(dev)
    cb.to_csv(os.path.join(OUT, 'cluster_bootstrap.csv'), index=False)

    print('== calendar month agg ==')
    cm = calendar_month_agg(dev)
    cm.to_csv(os.path.join(OUT, 'calendar_month_agg.csv'), index=False)

    print('== size gradient ==')
    sg = size_gradient(dev)
    sg.to_csv(os.path.join(OUT, 'size_gradient.csv'), index=False)

    print('== market relative ==')
    mr = market_relative(dev)
    mr.to_csv(os.path.join(OUT, 'market_relative.csv'), index=False)

    print('== worst cases ==')
    wc = worst_cases(dev)
    wc.to_csv(os.path.join(OUT, 'worst_cases.csv'), index=False)

    print('== decade ==')
    dc = decade_table(sig[sig['NEW_EPISODE'] == 1])
    dc.to_csv(os.path.join(OUT, 'decade_stability.csv'), index=False)

    print('== index detail ==')
    idx_sig = sig[sig['ts_code'].str.match(r'^(000300|000905|000852|399006|000688|000016)') & (sig['NEW_EPISODE'] == 1)]
    idx_sig.to_csv(os.path.join(OUT, 'manual_review_index.csv'), index=False)
    print(f'  指数信号 {len(idx_sig)} 条')

    print('DONE ->', OUT)


if __name__ == '__main__':
    main()
