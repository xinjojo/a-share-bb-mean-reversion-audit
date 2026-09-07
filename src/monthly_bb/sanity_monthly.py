"""MONTHLY-BB-MR Sanity Check
- 随机 20 笔 / 最好 20 / 最差 20 / 指数全部信号 / 除权案例 / 连续跌破案例
- 用原始日线月线公式复算若干案例的月线 open/high/low/close 与 BB lower
- 输出 sanity_monthly_report.csv + 控制台摘要
"""
import os, glob
import numpy as np
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'monthly_bb')
DATA_DIR = os.path.abspath(DATA_DIR)
OUT = os.path.join(os.path.dirname(__file__), '..', '..', 'results', 'evidence', 'monthly_bb')
OUT = os.path.abspath(OUT)

RNG = np.random.default_rng(20260907)


def load_daily_for(ts_code):
    """从分片日线重建单股序列（含 adj）。"""
    files = sorted(glob.glob(os.path.join(DATA_DIR, 'daily', 'daily_*.parquet')))
    parts = []
    for f in files:
        df = pd.read_parquet(f, columns=['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'vol', 'amount'])
        df = df[df['ts_code'] == ts_code]
        if len(df):
            parts.append(df)
    if not parts:
        return None
    d = pd.concat(parts, ignore_index=True)
    d['date'] = pd.to_datetime(d['trade_date'])
    d = d.sort_values('date').reset_index(drop=True)
    adjf = []
    for f in sorted(glob.glob(os.path.join(DATA_DIR, 'adj', 'adj_*.parquet'))):
        a = pd.read_parquet(f, columns=['ts_code', 'trade_date', 'adj_factor'])
        a = a[a['ts_code'] == ts_code]
        if len(a):
            adjf.append(a)
    if adjf:
        ad = pd.concat(adjf, ignore_index=True)
        ad['date'] = pd.to_datetime(ad['trade_date'])
        d = d.merge(ad[['ts_code', 'date', 'adj_factor']], on=['ts_code', 'date'], how='left')
        d['close_adj'] = d['close'] * d['adj_factor']
        d['high_adj'] = d['high'] * d['adj_factor']
        d['low_adj'] = d['low'] * d['adj_factor']
        d['open_adj'] = d['open'] * d['adj_factor']
    return d


def recompute_signal(ts_code, pm, sig):
    """用日线重建该股票该月月线并复算 BB lower，对比信号表。"""
    d = load_daily_for(ts_code)
    if d is None:
        return None
    d['pm'] = d['date'].dt.to_period('M')
    sub = d[d['pm'] == pm]
    if len(sub) == 0:
        return None
    o = sub['open_adj'].iloc[0]
    h = sub['high_adj'].max()
    lo = sub['low_adj'].min()
    c = sub['close_adj'].iloc[-1]
    # 20 月 rolling（含当月）
    m = d.groupby('pm').agg(close_adj=('close_adj', 'last')).reset_index()
    m = m[m['pm'] <= pm].tail(20)
    if len(m) < 20:
        return None
    ma = m['close_adj'].mean()
    sd = m['close_adj'].std(ddof=1)
    lower = ma - 2 * sd
    row = sig[(sig['ts_code'] == ts_code) & (sig['pm'] == pm)]
    if len(row) == 0:
        return None
    r = row.iloc[0]
    return dict(ts_code=ts_code, pm=str(pm), n_days=len(sub),
                recomputed_month_open=round(o, 3), recomputed_high=round(h, 3),
                recomputed_low=round(lo, 3), recomputed_close=round(c, 3),
                recomputed_bb_lower=round(lower, 3), recomputed_bb_z=round((c - ma) / sd, 3),
                table_close_adj=round(r['close_adj'], 3), table_bb_lower=round(r['bb_lower'], 3),
                close_match=abs(c - r['close_adj']) < 1e-6,
                lower_match=abs(lower - r['bb_lower']) < 1e-6,
                signal_match=bool(r['signal'] == 1 and c < lower))


def main():
    sig = pd.read_parquet(os.path.join(DATA_DIR, 'monthly_signals.parquet'))
    sig['pm'] = sig['pm'].astype('period[M]')
    dev = sig[sig['pm'] <= pd.Period('2024-12', freq='M')]

    rows = []
    # 1) 随机 20
    rand = dev.sample(20, random_state=RNG.integers(1, 1 << 30)).copy()
    for _, r in rand.iterrows():
        rec = recompute_signal(r['ts_code'], r['pm'], sig)
        if rec:
            rec['sample_type'] = 'random'
            rows.append(rec)
    # 2) 最好 20 / 最差 20（按 12M close-close）
    s12 = dev[dev['ret_cc_12m'].notna()].copy()
    for label, sub in [('best20', s12.nlargest(20, 'ret_cc_12m')),
                       ('worst20', s12.nsmallest(20, 'ret_cc_12m'))]:
        for _, r in sub.iterrows():
            rec = recompute_signal(r['ts_code'], r['pm'], sig)
            if rec:
                rec['sample_type'] = label
                rows.append(rec)
    # 3) 指数全部信号
    idx_sig = dev[dev['ts_code'].str.match(r'^(000300|000905|000852|399006|000688|000016)')]
    for _, r in idx_sig.iterrows():
        rec = recompute_signal(r['ts_code'], r['pm'], sig)
        if rec:
            rec['sample_type'] = 'index'
            rows.append(rec)
    # 4) 除权案例：信号月发生 adj_factor 突变的（抽样 10 个信号月内 adj 变化 >5%）
    files = sorted(glob.glob(os.path.join(DATA_DIR, 'adj', 'adj_*.parquet')))
    changes = []
    for f in files:
        a = pd.read_parquet(f, columns=['ts_code', 'trade_date', 'adj_factor'])
        a = a.sort_values('trade_date')
        a['prev'] = a['adj_factor'].shift(1)
        a['ratio'] = a['adj_factor'] / a['prev']
        ch = a[(a['ratio'] > 1.05) | (a['ratio'] < 0.95)]
        if len(ch):
            changes.append((a['ts_code'].iloc[0], ch.iloc[0]['trade_date']))
    ca_codes = {c for c, _ in changes}
    ca_sig = dev[dev['ts_code'].isin(ca_codes)].sample(min(10, dev[dev['ts_code'].isin(ca_codes)].shape[0]),
                                                       random_state=7) if len(ca_codes) else dev.head(0)
    for _, r in ca_sig.iterrows():
        rec = recompute_signal(r['ts_code'], r['pm'], sig)
        if rec:
            rec['sample_type'] = 'corp_action'
            rows.append(rec)
    # 5) 连续跌破案例
    cont = dev[dev['NEW_EPISODE'] == 0].sample(min(10, (dev['NEW_EPISODE'] == 0).sum()), random_state=11)
    for _, r in cont.iterrows():
        rec = recompute_signal(r['ts_code'], r['pm'], sig)
        if rec:
            rec['sample_type'] = 'repeat_signal'
            rows.append(rec)

    rep = pd.DataFrame(rows)
    rep.to_csv(os.path.join(OUT, 'sanity_monthly_report.csv'), index=False)
    print(f'sanity cases: {len(rep)}')
    if len(rep):
        print('close_match all:', rep['close_match'].all())
        print('lower_match all:', rep['lower_match'].all())
        print('signal_match all:', rep['signal_match'].all())
        print('mismatch rows:')
        print(rep[~rep[['close_match', 'lower_match', 'signal_match']].all(axis=1)].to_string())
    print('DONE')


if __name__ == '__main__':
    main()
