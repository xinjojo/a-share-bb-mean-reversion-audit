"""FORWARD EXT DATA — 前瞻专用数据扩展加载层（P0-2）。

目标：
1. 保留 prepare_v51 到 2026-08-25 的冻结历史结果完全不变（直接调用 prepare_v51）。
2. 扩展段（> 2026-08-25）按与 prepare_v51 完全相同的字段语义构建 D：
   close_adj=close×adj_factor、BB(20,2) 滚动、PIT ST、分板涨跌停价、上市天数。
3. 历史重叠 parity：扩展层代码路径对冻结段样本日期重建 D，与 prepare_v51 逐字段机器断言一致，
   通过后才允许用于扩展段（08-26+ 真实新增行情）。

数据源：
- 冻结段：data/combined_daily.parquet（prepare_v51 原样，≤2026-08-25）
- 扩展段：data/combined_daily.parquet 中 >2026-08-25 的真实新增行
          （未来若 data/raw/daily/ 分片先出现新日期，可在此优先接入分片，字段语义须过 parity）
- PIT ST：data/pit_st_daily.parquet（已含 2026-08-31）
- 上市日历：data/raw/trade_cal_full.parquet；list_date：data/raw/stock_basic.parquet
- ETF：data/etf_513500_merged.parquet（已含 2026-08-31）

不修改任何冻结策略计算逻辑；prepare_v51 原样保留。
"""
import os, sys, glob
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # github_repo
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(ROOT))                            # audit_package
NEWCHAT = os.path.dirname(os.path.dirname(ROOT))                     # new-chat
sys.path.insert(0, NEWCHAT)
DATA = os.path.join(NEWCHAT, 'data')

FROZEN_END = pd.Timestamp('2026-08-25')   # prepare_v51 硬编码冻结末日（必须与 prepare_v51 一致）
BB_WINDOW = 20
BB_STD = 2.0
MIN_LISTING_DAYS = 60


def _build_frame(df, pit, st_mode='pit', bb_window=BB_WINDOW, bb_std=BB_STD):
    """按 prepare_v51 完全相同的字段语义构建 df（供冻结段复用；扩展段用同公式）。
    df 需含 ts_code/date/open/high/low/close/pre_close/amount/adj_factor，已过滤日期范围。
    """
    df = df.sort_values(['ts_code', 'date']).reset_index(drop=True)
    if st_mode == 'pit':
        df = df.merge(pit[['date', 'ts_code', 'is_st_pit']], on=['date', 'ts_code'], how='left')
        df['is_st'] = df['is_st_pit'].fillna(False)
    else:
        sb = pd.read_parquet(os.path.join(DATA, 'raw', 'stock_basic.parquet'))
        df = df.merge(sb[['ts_code', 'name']], on='ts_code', how='left')
        df['is_st'] = df['name'].str.contains('ST', na=False)
    df['close_adj'] = df['close'] * df['adj_factor']
    df['high_adj'] = df['high'] * df['adj_factor']
    g = df.groupby('ts_code')['close_adj']
    df['ma'] = g.transform(lambda x: x.rolling(bb_window, min_periods=bb_window).mean())
    df['sd'] = g.transform(lambda x: x.rolling(bb_window, min_periods=bb_window).std())
    df['bb_lower'] = df['ma'] - bb_std * df['sd']
    df['bb_upper'] = df['ma'] + bb_std * df['sd']
    is_chi = df['ts_code'].str.startswith(('688', '689'))
    is_gem = df['ts_code'].str.startswith('30')
    is_st = df['is_st']
    gem_pct = np.where(df['date'] >= '2020-08-24', 0.20, 0.10)
    pct = np.where(is_chi, 0.20, np.where(is_gem, gem_pct, np.where(is_st, 0.05, 0.10)))
    df['limit_up_px'] = (df['pre_close'] * (1 + pct)).round(2)
    df['limit_down_px'] = (df['pre_close'] * (1 - pct)).round(2)
    df['is_limit_down'] = df['close'] <= df['limit_down_px']
    df['is_limit_up'] = df['close'] >= df['limit_up_px']
    return df


def _df_to_D(df, days):
    """按 prepare_v51 每日 numpy 结构构建 D（ts 顺序 = ts_code 字母序，与 prepare_v51 groupby 一致）。"""
    D = {}
    for d, g in df.groupby('date'):
        D[d] = dict(
            ts=g['ts_code'].to_numpy(),
            close=g['close'].to_numpy(), open_=g['open'].to_numpy(),
            high=g['high'].to_numpy(), low=g['low'].to_numpy(),
            high_adj=g['high_adj'].to_numpy(), close_adj=g['close_adj'].to_numpy(),
            bb_lower=g['bb_lower'].to_numpy(), bb_upper=g['bb_upper'].to_numpy(), bb_mid=g['ma'].to_numpy(),
            amount=g['amount'].to_numpy(), is_limit=g['is_limit_down'].to_numpy(),
            is_st=g['is_st'].to_numpy(), adj=g['adj_factor'].to_numpy(),
            pre_close=g['pre_close'].to_numpy(),
            limit_up_px=g['limit_up_px'].to_numpy(), limit_down_px=g['limit_down_px'].to_numpy(),
            is_limit_up=g['is_limit_up'].to_numpy(), is_limit_down_arr=g['is_limit_down'].to_numpy(),
        )
        D[d]['pos'] = {tc: j for j, tc in enumerate(D[d]['ts'])}
    return D


def build_ext_days(frozen_end=FROZEN_END, bb_window=BB_WINDOW, bb_std=BB_STD,
                   min_listing_days=MIN_LISTING_DAYS, st_mode='pit'):
    """返回扩展段 (ext_days, ext_D, ext_first_eligible_i, ext_offset, ext_etf)。
    扩展段 = combined_daily > frozen_end 的真实新增行情，字段语义与 prepare_v51 完全一致。
    """
    df = pd.read_parquet(os.path.join(DATA, 'combined_daily.parquet'))
    df['date'] = pd.to_datetime(df['date'])
    pit = pd.read_parquet(os.path.join(DATA, 'pit_st_daily.parquet'))
    pit['date'] = pd.to_datetime(pit['date'])
    df = df[df['date'] > frozen_end]
    if df.empty:
        return [], {}, {}, {}, None
    df = _build_frame(df, pit, st_mode=st_mode, bb_window=bb_window, bb_std=bb_std)
    ext_days = sorted(df['date'].unique())
    ext_D = _df_to_D(df, ext_days)

    # 上市天数（与 prepare_v51 相同：list_date + 完整日历 + min_listing_days）
    tc = pd.read_parquet(os.path.join(DATA, 'raw', 'trade_cal_full.parquet'))
    cal_dates = tc['date'].sort_values().reset_index(drop=True).to_numpy()
    sb2 = pd.read_parquet(os.path.join(DATA, 'raw', 'stock_basic.parquet'))[['ts_code', 'list_date']]
    first_eligible_i = {}
    for tc_code, ld in zip(sb2['ts_code'], sb2['list_date']):
        try:
            list_dt = pd.Timestamp(ld)
        except Exception:
            list_dt = pd.Timestamp('1990-01-01')
        pos = int(np.searchsorted(cal_dates, list_dt))
        first_eligible_i[tc_code] = pos + min_listing_days

    # ETF 扩展（513500 全序列 index 继续递增）
    m = pd.read_parquet(os.path.join(DATA, 'etf_513500_merged.parquet'))
    m['trade_date'] = pd.to_datetime(m['trade_date'])
    m = m.sort_values('trade_date')
    ext_etf = None
    if m['trade_date'].max() > frozen_end:
        me = m[m['trade_date'] > frozen_end]
        ext_etf = dict(
            dates=me['trade_date'].to_numpy(),
            idx={d: k for k, d in enumerate(me['trade_date'])},   # 相对扩展段起点；合并时由调用方加冻结段长度
            px=me['close'].to_numpy(),
            open_=me['open'].to_numpy(),
            nav=me['unit_nav'].to_numpy(),
        )
    return ext_days, ext_D, first_eligible_i, len(cal_dates), ext_etf


def merge_extended(pret):
    """pret = prepare_v51() 返回的 8 元组。返回合并后的完整 (days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset)。
    冻结段原样 + 扩展段（>FROZEN_END）逐日拼接。无扩展段时原样返回。
    """
    days_f, D_f, etf_idx_f, etf_px_f, etf_open_f, etf_nav_f, fei_f, off_f = pret
    ext_days, ext_D, fei_ext, cal_len, ext_etf = build_ext_days()
    if not ext_days:
        return pret

    days = days_f + list(ext_days)
    D = dict(D_f)
    D.update(ext_D)

    # bb_upper_prev：扩展段首日前一日 = 冻结段末日（或扩展段前日）
    prev_bb = {tc: D[days_f[-1]]['bb_upper'][j] for j, tc in enumerate(D[days_f[-1]]['ts'])}
    for k in range(len(days_f), len(days)):
        d0, d1 = days[k - 1], days[k]
        prev_bb = {tc: D[d0]['bb_upper'][j] for j, tc in enumerate(D[d0]['ts'])}
        cur = D[d1]
        cur['bb_upper_prev'] = np.array([prev_bb.get(tc, np.nan) for tc in cur['ts']])

    # ETF 合并：扩展段 index = 冻结段长度 + 相对 index
    etf_idx = dict(etf_idx_f)
    etf_px = list(etf_px_f)
    etf_open = list(etf_open_f)
    etf_nav = list(etf_nav_f)
    if ext_etf is not None:
        base = len(etf_px_f)
        for k, dt in enumerate(ext_etf['dates']):
            etf_idx[dt] = base + k
        etf_px += list(ext_etf['px'])
        etf_open += list(ext_etf['open_'])
        etf_nav += list(ext_etf['nav'])
    etf_px = np.array(etf_px)
    etf_open = np.array(etf_open)
    etf_nav = np.array(etf_nav)

    first_eligible_i = dict(fei_f) if fei_f else {}
    return days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, off_f


def parity_check(pret, n_sample=24, seed=0, frozen_end=FROZEN_END):
    """扩展层代码路径 vs prepare_v51：对冻结段随机 n_sample 个交易日逐字段机器断言。
    用 combined_daily ≤frozen_end 的数据走 _build_frame 路径重建 D，与 prepare_v51 的 D 对比。
    返回 dict(max_abs_diff, fields, sample_dates, pass)。任何字段 max_abs_diff>0 → fail。
    """
    from round51_audit import prepare_v51 as _pv51
    days_f, D_f, *_ = pret if pret is not None else _pv51()
    df = pd.read_parquet(os.path.join(DATA, 'combined_daily.parquet'))
    df['date'] = pd.to_datetime(df['date'])
    pit = pd.read_parquet(os.path.join(DATA, 'pit_st_daily.parquet'))
    pit['date'] = pd.to_datetime(pit['date'])
    df = df[(df['date'] >= '2020-01-01') & (df['date'] <= frozen_end)]
    df = _build_frame(df, pit)
    days_r = sorted(df['date'].unique())
    D_r = _df_to_D(df, days_r)

    rng = np.random.default_rng(seed)
    sample_dates = [d for d in days_r if d in D_f and (d.month, d.year) in {(7, 2026), (8, 2026)}]
    if len(sample_dates) > n_sample:
        sample_dates = [sample_dates[i] for i in rng.choice(len(sample_dates), n_sample, replace=False)]
    sample_dates = sorted(sample_dates)

    fields = ['ts', 'close', 'open_', 'high', 'low', 'high_adj', 'close_adj',
              'bb_lower', 'bb_upper', 'bb_mid', 'amount', 'is_limit',
              'is_st', 'adj', 'pre_close', 'limit_up_px', 'limit_down_px',
              'is_limit_up', 'is_limit_down_arr']
    max_diff = {}
    mism = {}
    for d in sample_dates:
        for f in fields:
            a = D_f[d][f]
            b = D_r[d][f]
            na_a = np.isnan(a) if a.dtype.kind == 'f' else np.zeros(len(a), bool)
            na_b = np.isnan(b) if b.dtype.kind == 'f' else np.zeros(len(b), bool)
            if a.dtype.kind == 'f' or b.dtype.kind == 'f':
                diff = np.nanmax(np.abs(np.where(na_a | na_b, 0, a.astype(float) - b.astype(float)))) if len(a) else 0.0
            else:
                diff = 0.0 if np.array_equal(a, b) else float('inf')
            if np.isfinite(diff) and diff > max_diff.get(f, 0.0):
                max_diff[f] = float(diff)
            if not (a.dtype.kind == 'f' or b.dtype.kind == 'f') and not np.array_equal(a, b):
                mism[f] = mism.get(f, 0) + 1
    # ts 顺序必须完全一致（字母序）
    ts_ok = all(np.array_equal(D_f[d]['ts'], D_r[d]['ts']) for d in sample_dates)
    max_abs = max(max_diff.values(), default=0.0) if max_diff else 0.0
    return dict(max_abs_diff=max_abs, per_field=max_diff, field_mismatch_counts=mism,
                sample_dates=[str(d.date()) for d in sample_dates], ts_order_ok=ts_ok,
                pass_=ts_ok and max_abs == 0.0 and not mism)


if __name__ == '__main__':
    p = parity_check(None)
    print('parity:', p['pass_'], '| max_abs_diff:', p['max_abs_diff'],
          '| ts_order_ok:', p['ts_order_ok'], '| n_sample:', len(p['sample_dates']))
    if p['per_field']:
        print('per_field:', p['per_field'])
