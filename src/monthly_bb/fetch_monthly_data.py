"""MONTHLY-BB-MR 数据拉取器（Tushare Pro）
- token 只从环境变量 TUSHARE_TOKEN 读取；禁止写入文件/日志/打印
- 指数：index_daily 按 ts_code 全历史
- 全 A：daily + adj_factor 按 trade_date 逐日拉（天然含退市股历史 → 避免幸存者偏差）
- PIT 市值：daily_basic 仅取每月最后一个交易日 total_mv/circ_mv
- namechange：按 start_date 段补拉（本地 namechange_full 覆盖 2010+，补 2004-2009）
- 输出：data/monthly_bb/（gitignore）
"""
import os, sys, time, json
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'monthly_bb')
DATA_DIR = os.path.abspath(DATA_DIR)
os.makedirs(DATA_DIR, exist_ok=True)

START_DATE = '20040101'          # 为月线 BB(20) 预热
INDEX_CODES = ['000300.SH', '000905.SH', '000852.SH', '399006.SZ', '000688.SH', '000016.SH']


def get_pro():
    tok = os.environ.get('TUSHARE_TOKEN')
    if not tok:
        sys.exit('[ERR] TUSHARE_TOKEN 环境变量未设置（禁止写入任何文件）')
    import tushare as ts
    ts.set_token(tok)
    return ts.pro_api()


def _call(pro, fn, **kw):
    for attempt in range(4):
        try:
            df = fn(**kw)
            return df
        except Exception as exc:
            msg = str(exc)
            if '每分钟' in msg or 'limit' in msg.lower() or '访问' in msg:
                time.sleep(2.0 + attempt * 2.0)
                continue
            if attempt == 3:
                print(f'  [WARN] {kw} -> {msg}')
                return None
            time.sleep(0.5)
    return None


def fetch_indices(pro):
    out = {}
    for code in INDEX_CODES:
        df = _call(pro, pro.index_daily, ts_code=code,
                   start_date=START_DATE, end_date='20261231')
        if df is not None and len(df):
            df = df[['ts_code', 'trade_date', 'open', 'high', 'low', 'close',
                     'vol', 'amount']].sort_values('trade_date').reset_index(drop=True)
            df.to_parquet(os.path.join(DATA_DIR, f'idx_{code[:6]}.parquet'), index=False)
            out[code] = len(df)
            print(f'  [OK] index {code}: {len(df)} 行')
        time.sleep(0.25)
    return out


def fetch_daily_by_trade_date(pro, cal_days):
    """按 trade_date 拉 daily + adj_factor（全市场，含退市股历史）。"""
    n_ok = 0
    for i, d in enumerate(cal_days):
        ds = d.strftime('%Y%m%d')
        f1 = os.path.join(DATA_DIR, 'daily', f'daily_{ds}.parquet')
        f2 = os.path.join(DATA_DIR, 'adj', f'adj_{ds}.parquet')
        if os.path.exists(f1) and os.path.exists(f2):
            continue
        df = _call(pro, pro.daily, trade_date=ds)
        ad = _call(pro, pro.adj_factor, trade_date=ds)
        if df is None or ad is None:
            print(f'  [WARN] {ds} 拉取失败，跳过')
            continue
        os.makedirs(os.path.dirname(f1), exist_ok=True)
        df.to_parquet(f1, index=False)
        ad.to_parquet(f2, index=False)
        n_ok += 1
        if (i + 1) % 200 == 0:
            print(f'  ... daily {i + 1}/{len(cal_days)} (ok={n_ok})')
    print(f'  daily/adj 拉取完成: 新增 {n_ok} 天')
    return n_ok


def fetch_monthly_market_cap(pro, month_ends):
    """仅取每月最后一个交易日 daily_basic（PIT 市值）。"""
    n_ok = 0
    for i, d in enumerate(month_ends):
        ds = d.strftime('%Y%m%d')
        f = os.path.join(DATA_DIR, 'mcap', f'mcap_{ds}.parquet')
        if os.path.exists(f):
            continue
        df = _call(pro, pro.daily_basic, trade_date=ds,
                   fields='ts_code,trade_date,total_mv,circ_mv,close,pe_ttm,pb')
        if df is None:
            continue
        os.makedirs(os.path.dirname(f), exist_ok=True)
        df.to_parquet(f, index=False)
        n_ok += 1
        if (i + 1) % 50 == 0:
            print(f'  ... mcap {i + 1}/{len(month_ends)}')
        time.sleep(0.25)
    print(f'  daily_basic(月末) 拉取完成: 新增 {n_ok} 月')
    return n_ok


def fetch_namechange_early(pro):
    """补拉 2004-2009 namechange（本地 namechange_full 自 2010 起）。"""
    f = os.path.join(DATA_DIR, 'namechange_2004_2009.parquet')
    if os.path.exists(f):
        return 0
    df = _call(pro, pro.namechange, start_date='20040101', end_date='20091231')
    if df is not None and len(df):
        df.to_parquet(f, index=False)
        print(f'  namechange 2004-2009: {len(df)} 条')
        return len(df)
    return 0


def fetch_stock_basic(pro):
    df = _call(pro, pro.stock_basic, exchange='', list_status='L',
               fields='ts_code,symbol,name,area,industry,market,exchange,list_date,delist_date,list_status')
    df2 = _call(pro, pro.stock_basic, exchange='', list_status='D',
               fields='ts_code,symbol,name,area,industry,market,exchange,list_date,delist_date,list_status')
    df3 = _call(pro, pro.stock_basic, exchange='', list_status='P',
               fields='ts_code,symbol,name,area,industry,market,exchange,list_date,delist_date,list_status')
    all_ = pd.concat([df, df2, df3], ignore_index=True).drop_duplicates('ts_code')
    all_.to_parquet(os.path.join(DATA_DIR, 'stock_basic_all.parquet'), index=False)
    print(f'  stock_basic 全量: {len(all_)} 只（L/D/P）')
    return len(all_)


def fetch_trade_cal(pro):
    df = _call(pro, pro.trade_cal, exchange='SSE', start_date=START_DATE, end_date='20261231',
               fields='cal_date,is_open')
    if df is None:
        sys.exit('[ERR] trade_cal 拉取失败')
    days = pd.to_datetime(df.loc[df['is_open'] == 1, 'cal_date']).tolist()
    return sorted(days)


def month_ends_from_days(days):
    """每月最后一个交易日。"""
    s = pd.Series(pd.to_datetime(days))
    ends = s.groupby(s.dt.to_period('M')).max().tolist()
    return ends


def main():
    pro = get_pro()
    print('== fetch: indices ==')
    fetch_indices(pro)
    print('== fetch: stock_basic / namechange ==')
    fetch_stock_basic(pro)
    fetch_namechange_early(pro)
    print('== fetch: trade_cal ==')
    days = fetch_trade_cal(pro)
    print(f'  交易日 {len(days)} 天: {days[0].date()} ~ {days[-1].date()}')
    print('== fetch: daily + adj (逐日) ==')
    fetch_daily_by_trade_date(pro, days)
    print('== fetch: 月末 daily_basic (PIT 市值) ==')
    fetch_monthly_market_cap(pro, month_ends_from_days(days))
    print('DONE')


if __name__ == '__main__':
    main()
