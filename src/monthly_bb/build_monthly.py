"""MONTHLY-BB-MR 月线构建 + 信号 + forward 收益/MFE/MAE
严格避免未来函数：
- 价格统一后复权 close_adj = close * adj_factor（因子单调不回改）
- BB(20, 2σ, ddof=1) 只用截至当月月末的序列
- entry = 下月第一个交易日 open
- 输出：data/monthly_bb/monthly_panel.parquet（月线全量）
       data/monthly_bb/monthly_signals.parquet（信号全量）
"""
import os, glob
import numpy as np
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'monthly_bb')
DATA_DIR = os.path.abspath(DATA_DIR)

BB_WINDOW = 20
BB_STD = 2.0
DDOF = 1
MIN_LIST_MONTHS = 12          # 上市至少 12 个月
HORIZONS = [1, 3, 6, 12]
DEV_END = pd.Timestamp('2024-12-31')       # 开发期信号月上限
EXPOSED_START = pd.Timestamp('2025-01-01')  # 已暴露段（仅展示）


def load_all_daily():
    """从 data/monthly_bb/daily/*.parquet 拼接全 A 日线（按 trade_date 分片），只保留必要列。"""
    files = sorted(glob.glob(os.path.join(DATA_DIR, 'daily', 'daily_*.parquet')))
    cols = ['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'vol', 'amount']
    parts = []
    for f in files:
        parts.append(pd.read_parquet(f, columns=cols))
    df = pd.concat(parts, ignore_index=True)
    df['date'] = pd.to_datetime(df['trade_date'])
    df = df.sort_values(['ts_code', 'date']).reset_index(drop=True)
    return df


def load_all_adj():
    files = sorted(glob.glob(os.path.join(DATA_DIR, 'adj', 'adj_*.parquet')))
    parts = [pd.read_parquet(f, columns=['ts_code', 'trade_date', 'adj_factor']) for f in files]
    df = pd.concat(parts, ignore_index=True)
    df['date'] = pd.to_datetime(df['trade_date'])
    return df[['ts_code', 'date', 'adj_factor']]


def build_monthly_panel(daily, adj):
    """日线 -> 月线（后复权）。"""
    d = daily.merge(adj, on=['ts_code', 'date'], how='left')
    d['close_adj'] = d['close'] * d['adj_factor']
    d['open_adj'] = d['open'] * d['adj_factor']
    d['high_adj'] = d['high'] * d['adj_factor']
    d['low_adj'] = d['low'] * d['adj_factor']
    d['pm'] = d['date'].dt.to_period('M')
    g = d.groupby(['ts_code', 'pm'])
    m = g.agg(
        open_adj=('open_adj', 'first'),
        high_adj=('high_adj', 'max'),
        low_adj=('low_adj', 'min'),
        close_adj=('close_adj', 'last'),
        volume=('vol', 'sum'),
        amount=('amount', 'sum'),
        n_days=('date', 'count'),
        last_date=('date', 'max'),
    ).reset_index()
    m['month_end'] = m['pm'].dt.to_timestamp('M').dt.to_period('M')
    m['month_end_date'] = m['last_date']
    return m.sort_values(['ts_code', 'pm']).reset_index(drop=True)


def add_bb(m):
    """BB(20,2,ddof=1) 于月线 close_adj。"""
    m = m.sort_values(['ts_code', 'pm']).copy()
    g = m.groupby('ts_code', group_keys=False)
    m['bb_mid'] = g['close_adj'].transform(lambda x: x.rolling(BB_WINDOW, min_periods=BB_WINDOW).mean())
    m['bb_sd'] = g['close_adj'].transform(lambda x: x.rolling(BB_WINDOW, min_periods=BB_WINDOW).std(ddof=DDOF))
    m['bb_lower'] = m['bb_mid'] - BB_STD * m['bb_sd']
    m['bb_upper'] = m['bb_mid'] + BB_STD * m['bb_sd']
    m['bb_width'] = (m['bb_upper'] - m['bb_lower']) / m['bb_mid']
    m['bb_z'] = (m['close_adj'] - m['bb_mid']) / m['bb_sd']
    return m


def eligibility(m, basic):
    """PIT 资格：上市 ≥12 个月、当月有成交、非 ST（PIT 需在信号计算时应用）。
    这里附加上市月份数与成交标记；ST 由 namechange 在 signal 阶段处理。"""
    m = m.copy()
    m['list_date_ts'] = m['ts_code'].map(basic.set_index('ts_code')['list_date'])
    m['list_month'] = (m['pm'].dt.to_timestamp('M').dt.to_period('M')
                       .astype(str).astype(str)
                       )
    # 上市月数
    ld = pd.to_datetime(m['list_date_ts'], format='%Y%m%d', errors='coerce')
    m['months_since_list'] = ((m['month_end_date'].dt.to_period('M') -
                               ld.dt.to_period('M')).apply(lambda x: x.n if pd.notna(x) else np.nan))
    m['eligible'] = (m['months_since_list'] >= MIN_LIST_MONTHS) & (m['n_days'] >= 1) & (m['amount'] > 0)
    return m


def build_signal_table(m, namechange):
    """信号：月末 close_adj < 当月 bb_lower；NEW_EPISODE / ALL_SIGNAL_MONTHS。
    关键：signal / prev_signal / NEW_EPISODE 在【完整月序列】上计算（ST/eligible 只决定该月是否入表，
    不参与 shift，避免跨月错位）。"""
    m = m.sort_values(['ts_code', 'pm']).copy()
    # 完整序列信号标记（含不 eligible / ST 月，用于连续跌破判定）
    g = m.groupby('ts_code', group_keys=False)
    m['signal_full'] = (m['close_adj'] < m['bb_lower']).astype(int)
    m['prev_signal_full'] = g['signal_full'].shift(1).fillna(0)
    m['NEW_EPISODE_full'] = ((m['signal_full'] == 1) & (m['prev_signal_full'] == 0)).astype(int)
    m['next_open_adj'] = g['open_adj'].shift(-1)
    m['next_pm'] = g['pm'].shift(-1)
    m['next_month_end_date'] = g['month_end_date'].shift(-1)

    # PIT ST：namechange start_date <= 当月月末 < end_date(或空) → ST
    st = namechange.copy()
    st['start_ts'] = pd.to_datetime(st['start_date'], format='%Y%m%d', errors='coerce')
    st['end_ts'] = pd.to_datetime(st['end_date'], format='%Y%m%d', errors='coerce')
    st['is_st'] = st['name'].str.contains('ST', na=False)

    m2 = m.copy()
    m2['month_end_ts'] = m2['month_end_date']
    st_on = st[st['is_st']].copy()
    st_on = st_on.sort_values(['ts_code', 'start_ts'])
    m2 = m2.sort_values(['ts_code', 'month_end_ts'])
    m2['st_flag'] = 0
    st_codes = set(st_on['ts_code'])
    mask = m2['ts_code'].isin(st_codes)
    if mask.sum():
        sub = m2[mask].copy()
        merged = pd.merge_asof(sub.sort_values('month_end_ts'),
                               st_on[['ts_code', 'start_ts', 'end_ts']].sort_values('start_ts'),
                               left_on='month_end_ts', right_on='start_ts', by='ts_code', direction='backward')
        merged['st_flag'] = ((merged['start_ts'] <= merged['month_end_ts']) &
                             ((merged['end_ts'].isna()) | (merged['month_end_ts'] < merged['end_ts']))).astype(int)
        m2.loc[mask, 'st_flag'] = merged['st_flag'].values

    m2['signal'] = m2['signal_full']
    m2['prev_signal'] = m2['prev_signal_full']
    m2['NEW_EPISODE'] = m2['NEW_EPISODE_full']
    m2 = m2[(m2['eligible']) & (m2['st_flag'] == 0)].copy()
    sig = m2[m2['signal'] == 1].copy()
    return sig


def add_forward(sig, m, horizons=HORIZONS):
    """对每个 signal：后续 horizon 月收益（close→close 与 entry→close）与 MFE/MAE。"""
    cols = []
    m_idx = m.set_index(['ts_code', 'pm'])
    # 需要 close_adj / high_adj / low_adj / open_adj 未来值 → 用 shift(-h) 于按 pm 排序的序列
    m_sorted = m.sort_values(['ts_code', 'pm']).copy()
    for h in horizons:
        g = m_sorted.groupby('ts_code')
        m_sorted[f'f_close_{h}'] = g['close_adj'].shift(-h)
        m_sorted[f'f_open_{h}'] = g['open_adj'].shift(-h)
        # MFE/MAE：未来 h 个月内 max high / min low（含信号月之后）
        roll = g['high_adj'].transform(lambda x: x.shift(-1).rolling(h, min_periods=1).max())
        roll_low = g['low_adj'].transform(lambda x: x.shift(-1).rolling(h, min_periods=1).min())
        m_sorted[f'f_maxhigh_{h}'] = roll
        m_sorted[f'f_minlow_{h}'] = roll_low

    sig = sig.merge(m_sorted[['ts_code', 'pm'] + [c for c in m_sorted.columns if c.startswith('f_')]],
                    on=['ts_code', 'pm'], how='left')
    base_close = sig['close_adj']
    base_entry = sig['next_open_adj']
    for h in horizons:
        sig[f'ret_cc_{h}m'] = sig[f'f_close_{h}'] / base_close - 1.0
        sig[f'ret_ec_{h}m'] = sig[f'f_close_{h}'] / base_entry - 1.0
        sig[f'mfe_{h}m'] = sig[f'f_maxhigh_{h}'] / base_close - 1.0
        sig[f'mae_{h}m'] = sig[f'f_minlow_{h}'] / base_close - 1.0
        # entry 基准 MFE/MAE
        sig[f'mfe_ent_{h}m'] = sig[f'f_maxhigh_{h}'] / base_entry - 1.0
        sig[f'mae_ent_{h}m'] = sig[f'f_minlow_{h}'] / base_entry - 1.0
        # censored：未来不足 h 月
        sig[f'censored_{h}m'] = sig[f'f_close_{h}'].isna().astype(int)
    return sig


def add_market_relative(sig, idx_m):
    """沪深300 同期（按 pm 对齐）收益，计算 excess。只用 000300 一根序列。"""
    idx = idx_m[idx_m['ts_code'] == '000300'][['pm', 'close_adj']].rename(columns={'close_adj': 'idx_close'})
    idx = idx.drop_duplicates('pm').sort_values('pm')
    for h in HORIZONS:
        idx[f'idx_fclose_{h}'] = idx['idx_close'].shift(-h)
    sig = sig.merge(idx, on='pm', how='left')
    for h in HORIZONS:
        sig[f'idx_ret_{h}m'] = sig[f'idx_fclose_{h}'] / sig['idx_close'] - 1.0
        sig[f'excess_cc_{h}m'] = sig[f'ret_cc_{h}m'] - sig[f'idx_ret_{h}m']
    return sig


def build_index_signals():
    """6 只宽基指数月线 BB(20,2) + 信号 + forward/MFE/MAE（独立表，指数不复权）。"""
    out = []
    for code in ['000300', '000905', '000852', '399006', '000688', '000016']:
        f = os.path.join(DATA_DIR, f'idx_{code}.parquet')
        if not os.path.exists(f):
            continue
        ix = pd.read_parquet(f)
        ix['date'] = pd.to_datetime(ix['trade_date'])
        ix = ix.sort_values('date').reset_index(drop=True)
        ix['pm'] = ix['date'].dt.to_period('M')
        g = ix.groupby('pm')
        im = g.agg(open=('open', 'first'), high=('high', 'max'), low=('low', 'min'),
                   close=('close', 'last'), month_end_date=('date', 'max'),
                   n_days=('date', 'count')).reset_index()
        im['ts_code'] = code
        im = im.sort_values('pm')
        im['bb_mid'] = im['close'].rolling(BB_WINDOW, min_periods=BB_WINDOW).mean()
        im['bb_sd'] = im['close'].rolling(BB_WINDOW, min_periods=BB_WINDOW).std(ddof=DDOF)
        im['bb_lower'] = im['bb_mid'] - BB_STD * im['bb_sd']
        im['bb_upper'] = im['bb_mid'] + BB_STD * im['bb_sd']
        im['bb_z'] = (im['close'] - im['bb_mid']) / im['bb_sd']
        im['signal'] = (im['close'] < im['bb_lower']).astype(int)
        im['prev_signal'] = im['signal'].shift(1).fillna(0)
        im['NEW_EPISODE'] = ((im['signal'] == 1) & (im['prev_signal'] == 0)).astype(int)
        im['next_open'] = im['open'].shift(-1)
        for h in HORIZONS:
            im[f'f_close_{h}'] = im['close'].shift(-h)
            im[f'f_maxhigh_{h}'] = im['high'].shift(-1).rolling(h, min_periods=1).max()
            im[f'f_minlow_{h}'] = im['low'].shift(-1).rolling(h, min_periods=1).min()
            im[f'ret_cc_{h}m'] = im[f'f_close_{h}'] / im['close'] - 1.0
            im[f'ret_ec_{h}m'] = im[f'f_close_{h}'] / im['next_open'] - 1.0
            im[f'mfe_{h}m'] = im[f'f_maxhigh_{h}'] / im['close'] - 1.0
            im[f'mae_{h}m'] = im[f'f_minlow_{h}'] / im['close'] - 1.0
            im[f'censored_{h}m'] = im[f'f_close_{h}'].isna().astype(int)
        out.append(im)
    idx_sig = pd.concat(out, ignore_index=True)
    idx_sig = idx_sig[idx_sig['signal'] == 1].reset_index(drop=True)
    idx_sig.to_parquet(os.path.join(DATA_DIR, 'index_signals.parquet'), index=False)
    print(f'  指数信号: {len(idx_sig)} 条')
    return idx_sig


def main():
    print('== load daily/adj ==')
    daily = load_all_daily()
    adj = load_all_adj()
    print(f'  daily {len(daily)} 行, adj {len(adj)} 行')
    print('== build monthly panel ==')
    m = build_monthly_panel(daily, adj)
    m = add_bb(m)
    basic = pd.read_parquet(os.path.join(DATA_DIR, 'stock_basic_all.parquet'))
    m = eligibility(m, basic)
    m.to_parquet(os.path.join(DATA_DIR, 'monthly_panel.parquet'), index=False)
    print(f'  月线 panel: {len(m)} 行, {m["ts_code"].nunique()} 只')
    print('== build signals ==')
    nc = pd.concat([
        pd.read_parquet(os.path.join(DATA_DIR, 'namechange_2004_2009.parquet')) if
        os.path.exists(os.path.join(DATA_DIR, 'namechange_2004_2009.parquet')) else pd.DataFrame(),
        pd.read_parquet(os.path.join(DATA_DIR, 'namechange_full.parquet')) if
        os.path.exists(os.path.join(DATA_DIR, 'namechange_full.parquet')) else pd.DataFrame(),
    ], ignore_index=True)
    sig = build_signal_table(m, nc)
    print(f'  信号(ALL): {len(sig)}, NEW_EPISODE: {sig["NEW_EPISODE"].sum()}')
    print('== add forward ==')
    sig = add_forward(sig, m)
    # 指数月线（用于 market-relative）
    idx_parts = []
    for code in ['000300', '000905', '000852', '399006', '000688', '000016']:
        f = os.path.join(DATA_DIR, f'idx_{code}.parquet')
        if os.path.exists(f):
            ix = pd.read_parquet(f)
            ix['pm'] = pd.to_datetime(ix['trade_date']).dt.to_period('M')
            g = ix.groupby('pm')
            im = g.agg(open=('open', 'first'), high=('high', 'max'), low=('low', 'min'),
                       close_adj=('close', 'last'), month_end_date=('trade_date', 'max')).reset_index()
            idx_parts.append(im.assign(ts_code=code))
    idx_m = pd.concat(idx_parts, ignore_index=True)
    sig = add_market_relative(sig, idx_m)
    sig.to_parquet(os.path.join(DATA_DIR, 'monthly_signals.parquet'), index=False)
    print(f'  信号表: {len(sig)} 行 -> {DATA_DIR}/monthly_signals.parquet')
    print('== index signals ==')
    build_index_signals()
    print('DONE')


if __name__ == '__main__':
    main()
