"""FORWARD DATA PREP — 前瞻专用数据准备层（用户点名文件）。

职责：
1. 冻结段（≤2026-08-25）：prepare_v51 原样，历史冻结结果完全不变。
2. 增量段（>2026-08-25）：优先读 Tushare 增量（data/forward_incremental/，由 update_forward_tushare.py 生成）；
   若尚无 Tushare 增量文件，回退本地 combined_daily 真实新增行（同字段语义）。
3. 生成与冻结引擎完全一致的 days / D / ETF 数据结构（字段语义与 prepare_v51 相同，技术指标只用当时及以前数据）。
4. 供 src/run_forward_daily.py 一键流程使用。

禁止修改冻结策略计算逻辑；prepare_v51 原样保留。
"""
import os, sys, glob
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(ROOT))
NEWCHAT = os.path.dirname(os.path.dirname(ROOT))
sys.path.insert(0, NEWCHAT)
DATA = os.path.join(NEWCHAT, 'data')
INC = os.path.join(DATA, 'forward_incremental')

from forward_ext_data import (_build_frame, _df_to_D, FROZEN_END, BB_WINDOW, BB_STD,
                              MIN_LISTING_DAYS, build_ext_days, merge_extended, parity_check)


def _pit_st_from_namechange():
    """用 Tushare namechange 增量构建 PIT ST 标记（date, ts_code, is_st_pit）。
    名称含 'ST'（含 *ST）→ is_st。区间 = start_date ~ end_date（end NaN = 至今）。"""
    f = os.path.join(INC, 'namechange_forward.parquet')
    if not os.path.exists(f):
        return None
    nc = pd.read_parquet(f)
    nc['start_date'] = pd.to_datetime(nc['start_date'])
    nc['end_date'] = pd.to_datetime(nc['end_date'])
    nc['is_st'] = nc['name'].str.contains('ST', na=False)
    rows = []
    for _, r in nc.iterrows():
        if not r['is_st']:
            continue
        end = r['end_date'] if pd.notna(r['end_date']) else pd.Timestamp('2026-12-31')
        rows.append(dict(ts_code=r['ts_code'], start=r['start_date'], end=end))
    if not rows:
        return None
    seg = pd.DataFrame(rows)
    # 展开为逐日（2026-08-26 起增量区）
    dates = pd.date_range(FROZEN_END + pd.Timedelta(days=1), '2026-12-31', freq='D')
    out = []
    for d in dates:
        hit = seg[(seg['start'] <= d) & (d <= seg['end'])]
        for _, r in hit.iterrows():
            out.append(dict(date=d, ts_code=r['ts_code'], is_st_pit=True))
    if not out:
        return None
    return pd.DataFrame(out)


def _tushare_ext_df():
    """读 Tushare 增量 daily + adj_factor，拼成与 combined 相同列语义的长表（ts_code/date/OHLC/pre_close/amount/adj_factor）。"""
    files = sorted(glob.glob(os.path.join(INC, 'daily_*.parquet')))
    if not files:
        return None
    frames = []
    for f in files:
        df = pd.read_parquet(f)
        if df.empty:
            continue
        df['date'] = pd.to_datetime(df['trade_date'])
        adf = os.path.join(INC, 'adj_' + os.path.basename(f)[6:])
        if os.path.exists(adf):
            adj = pd.read_parquet(adf)[['ts_code', 'trade_date', 'adj_factor']]
            adj['date'] = pd.to_datetime(adj['trade_date'])
            df = df.merge(adj[['ts_code', 'date', 'adj_factor']], on=['ts_code', 'date'], how='left')
        else:
            df['adj_factor'] = np.nan
        frames.append(df[['ts_code', 'date', 'open', 'high', 'low', 'close', 'pre_close',
                          'change', 'pct_chg', 'vol', 'amount', 'adj_factor']])
    out = pd.concat(frames, ignore_index=True)
    out = out.dropna(subset=['adj_factor'])
    return out


def _tushare_ext_etf():
    """读 Tushare ETF 513500 fund_daily 增量；与本地 merged 序列续接。"""
    f = os.path.join(INC, 'etf_513500_forward.parquet')
    if not os.path.exists(f):
        return None
    e = pd.read_parquet(f)
    e['trade_date'] = pd.to_datetime(e['trade_date'])
    e = e.sort_values('trade_date')
    me = pd.read_parquet(os.path.join(DATA, 'etf_513500_merged.parquet'))
    me['trade_date'] = pd.to_datetime(me['trade_date'])
    me = me.sort_values('trade_date')
    # 续接：本地 merged 已有部分不重复
    e = e[e['trade_date'] > me['trade_date'].max()]
    if e.empty:
        return None
    # 与本地 merged 相同的列
    nav = e['unit_nav'] if 'unit_nav' in e.columns else np.nan
    return dict(dates=e['trade_date'].to_numpy(),
                idx={d: k for k, d in enumerate(e['trade_date'])},
                px=e['close'].to_numpy(),
                open_=e['open'].to_numpy(),
                nav=np.asarray(nav, dtype=float))


def build_ext_from_tushare():
    """从 Tushare 增量构建扩展段（签名与 forward_ext_data.build_ext_days 一致）。
    无 Tushare 增量文件时返回 None（调用方回退 combined）。
    """
    df = _tushare_ext_df()
    if df is None or df.empty:
        return None
    pit = _pit_st_from_namechange()
    if pit is not None:
        df = _build_frame(df, pit, st_mode='pit')
    else:
        df = _build_frame(df, pd.DataFrame(columns=['date', 'ts_code', 'is_st_pit']), st_mode='pit')
    df = df[df['date'] > FROZEN_END]
    if df.empty:
        return None
    ext_days = sorted(df['date'].unique())
    ext_D = _df_to_D(df, ext_days)
    # 上市日历 / list_date（优先 Tushare stock_basic 增量）
    tc = pd.read_parquet(os.path.join(DATA, 'raw', 'trade_cal_full.parquet'))
    cal_dates = tc['date'].sort_values().reset_index(drop=True).to_numpy()
    sb_path = os.path.join(INC, 'stock_basic_forward.parquet')
    if os.path.exists(sb_path):
        sb2 = pd.read_parquet(sb_path)[['ts_code', 'list_date']]
    else:
        sb2 = pd.read_parquet(os.path.join(DATA, 'raw', 'stock_basic.parquet'))[['ts_code', 'list_date']]
    first_eligible_i = {}
    for tc_code, ld in zip(sb2['ts_code'], sb2['list_date']):
        try:
            list_dt = pd.Timestamp(ld)
        except Exception:
            list_dt = pd.Timestamp('1990-01-01')
        pos = int(np.searchsorted(cal_dates, list_dt))
        first_eligible_i[tc_code] = pos + MIN_LISTING_DAYS
    ext_etf = _tushare_ext_etf()
    return ext_days, ext_D, first_eligible_i, len(cal_dates), ext_etf


def prepare_forward_data(prefer_tushare=True):
    """返回完整 (days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset)。
    冻结段 = prepare_v51 原样（≤2026-08-25）；
    增量段 = Tushare 增量（若存在）否则 combined 兜底。
    返回 (data_tuple, source_label, ext_days)。
    """
    from round51_audit import prepare_v51
    pret = prepare_v51(limit_down_mode='correct', st_mode='pit')
    ext = None
    src = 'combined_fallback'
    if prefer_tushare:
        ext = build_ext_from_tushare()
        if ext is not None and len(ext[0]):
            src = 'tushare_incremental'
    if ext is None:
        ext = build_ext_days()
        src = 'combined_fallback'
    if not ext[0]:
        return pret, src, []
    # 复用 forward_ext_data 的合并逻辑（D 引用不变，冻结段原样）
    days_f, D_f, etf_idx_f, etf_px_f, etf_open_f, etf_nav_f, fei_f, off_f = pret
    ext_days, ext_D, fei_ext, cal_len, ext_etf = ext
    days = days_f + list(ext_days)
    D = dict(D_f)
    D.update(ext_D)
    prev_bb = {tc: D[days_f[-1]]['bb_upper'][j] for j, tc in enumerate(D[days_f[-1]]['ts'])}
    for k in range(len(days_f), len(days)):
        d0, d1 = days[k - 1], days[k]
        prev_bb = {tc: D[d0]['bb_upper'][j] for j, tc in enumerate(D[d0]['ts'])}
        cur = D[d1]
        cur['bb_upper_prev'] = np.array([prev_bb.get(tc, np.nan) for tc in cur['ts']])
    etf_idx = dict(etf_idx_f)
    etf_px, etf_open, etf_nav = list(etf_px_f), list(etf_open_f), list(etf_nav_f)
    if ext_etf is not None:
        base = len(etf_px_f)
        for k, dt in enumerate(ext_etf['dates']):
            etf_idx[dt] = base + k
        etf_px += list(ext_etf['px'])
        etf_open += list(ext_etf['open_'])
        etf_nav += list(ext_etf['nav'])
    etf_px, etf_open, etf_nav = np.array(etf_px), np.array(etf_open), np.array(etf_nav)
    first_eligible_i = dict(fei_f) if fei_f else {}
    return (days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, off_f), src, list(ext_days)


if __name__ == '__main__':
    p = parity_check(None)
    print('parity:', p['pass_'], '| max_abs_diff:', p['max_abs_diff'],
          '| ts_order_ok:', p['ts_order_ok'], '| n_sample:', len(p['sample_dates']))
    data, src, ext_days = prepare_forward_data()
    days = data[0]
    print('prepare_forward_data source:', src)
    print('days:', len(days), '| 末日:', days[-1].date())
    if ext_days:
        print('扩展段:', ext_days[0].date(), '..', ext_days[-1].date())
