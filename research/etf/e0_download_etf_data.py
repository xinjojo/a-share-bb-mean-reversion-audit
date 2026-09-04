#!/usr/bin/env python3
"""E0 STEP 3: 批量下载 ETF 价格/复权/份额 + 指数价格（后台运行）
对每只候选 ETF:
  fund_daily  全历史（未复权 OHLC + vol/amount），分页防截断
  fund_adj    全历史复权因子
  fund_share  全历史份额（PIT AUM 关键）
对每个匹配到交易所代码(.SH/.SZ)的指数:
  index_daily 全历史
产物: data/raw/etf/fund_daily/{ts_code}.parquet, fund_adj/, fund_share/, index_daily/
      data/raw/etf/download_log.csv
token: 环境变量 TUSHARE_TOKEN 优先，否则 tushare 缓存
"""
import os, sys, time, json
import pandas as pd
import tushare as ts

DATA_ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
RAWDIR = os.path.join(DATA_ROOT, 'data', 'raw', 'etf')
os.makedirs(os.path.join(RAWDIR, 'fund_daily'), exist_ok=True)
os.makedirs(os.path.join(RAWDIR, 'fund_adj'), exist_ok=True)
os.makedirs(os.path.join(RAWDIR, 'fund_share'), exist_ok=True)
os.makedirs(os.path.join(RAWDIR, 'index_daily'), exist_ok=True)

tok = os.environ.get('TUSHARE_TOKEN', '')
if tok:
    ts.set_token(tok)
pro = ts.pro_api()

# 候选 ETF
cand = pd.read_parquet(os.path.join(RAWDIR, 'etf_candidates.parquet'))
codes = sorted(cand['ts_code'].unique().tolist())
print('候选 ETF:', len(codes))

DELAY = 0.13

def call(fn, **kw):
    for attempt in range(3):
        try:
            df = fn(**kw)
            time.sleep(DELAY)
            return df
        except Exception as e:
            time.sleep(2 + attempt * 3)
            if '每分钟' in str(e) or 'freq' in str(e).lower() or '限制' in str(e):
                time.sleep(30)
    return None

def fetch_daily(ts_code):
    """分页拉全历史 fund_daily"""
    parts = []
    start = '20040101'
    end = '20260903'
    while True:
        df = call(pro.fund_daily, ts_code=ts_code, start_date=start, end_date=end)
        if df is None or len(df) == 0:
            break
        parts.append(df)
        if len(df) < 6000:
            break
        # 已到上限，从最早一天往前续拉
        start = str(df['trade_date'].min())
    if not parts:
        return None
    out = pd.concat(parts, ignore_index=True).drop_duplicates(subset=['trade_date'])
    return out.sort_values('trade_date')

def fetch_share(ts_code):
    parts = []
    start, end = '20040101', '20260903'
    while True:
        df = call(pro.fund_share, ts_code=ts_code, start_date=start, end_date=end)
        if df is None or len(df) == 0:
            break
        parts.append(df)
        if len(df) < 6000:
            break
        start = str(df['trade_date'].min())
    if not parts:
        return None
    out = pd.concat(parts, ignore_index=True).drop_duplicates(subset=['trade_date'])
    return out.sort_values('trade_date')

def fetch_adj(ts_code):
    df = call(pro.fund_adj, ts_code=ts_code, start_date='20040101', end_date='20260903')
    if df is None or len(df) == 0:
        return None
    return df.sort_values('trade_date')

log = []
# ---- ETF 数据 ----
for i, c in enumerate(codes):
    d_fd = os.path.join(RAWDIR, 'fund_daily', c.replace('.', '_') + '.parquet')
    d_fa = os.path.join(RAWDIR, 'fund_adj', c.replace('.', '_') + '.parquet')
    d_fs = os.path.join(RAWDIR, 'fund_share', c.replace('.', '_') + '.parquet')
    try:
        if not os.path.exists(d_fd):
            fd = fetch_daily(c)
            if fd is not None:
                fd.to_parquet(d_fd)
                log.append((c, 'fund_daily', len(fd)))
        if not os.path.exists(d_fa):
            fa = fetch_adj(c)
            if fa is not None:
                fa.to_parquet(d_fa)
                log.append((c, 'fund_adj', len(fa)))
        if not os.path.exists(d_fs):
            fs = fetch_share(c)
            if fs is not None:
                fs.to_parquet(d_fs)
                log.append((c, 'fund_share', len(fs)))
    except Exception as e:
        log.append((c, 'ERROR', str(e)[:120]))
    if (i + 1) % 100 == 0:
        print(f'ETF progress {i+1}/{len(codes)}', flush=True)
        pd.DataFrame(log, columns=['ts_code', 'kind', 'info']).to_csv(
            os.path.join(RAWDIR, 'download_log_partial.csv'), index=False)

# ---- 指数数据（映射到交易所代码） ----
map_df = pd.read_parquet(os.path.join(RAWDIR, 'etf_index_map_master.parquet'))
ex_codes = set()
for v in map_df['map_index_code'].astype(str):
    for x in v.replace('[', '').replace(']', '').replace("'", '').split(','):
        x = x.strip()
        if x.endswith('.SH') or x.endswith('.SZ'):
            ex_codes.add(x)
print('交易所指数代码数:', len(ex_codes))
for i, c in enumerate(sorted(ex_codes)):
    d = os.path.join(RAWDIR, 'index_daily', c.replace('.', '_') + '.parquet')
    try:
        if not os.path.exists(d):
            parts = []
            start, end = '20040101', '20260903'
            while True:
                df = call(pro.index_daily, ts_code=c, start_date=start, end_date=end)
                if df is None or len(df) == 0:
                    break
                parts.append(df)
                if len(df) < 6000:
                    break
                start = str(df['trade_date'].min())
            if parts:
                out = pd.concat(parts, ignore_index=True).drop_duplicates(subset=['trade_date'])
                out.sort_values('trade_date').to_parquet(d)
                log.append((c, 'index_daily', len(out)))
    except Exception as e:
        log.append((c, 'INDEX_ERROR', str(e)[:120]))
    if (i + 1) % 100 == 0:
        print(f'INDEX progress {i+1}/{len(ex_codes)}', flush=True)

pd.DataFrame(log, columns=['ts_code', 'kind', 'info']).to_csv(
    os.path.join(RAWDIR, 'download_log.csv'), index=False)
print('DONE ALL. total log rows:', len(log))
