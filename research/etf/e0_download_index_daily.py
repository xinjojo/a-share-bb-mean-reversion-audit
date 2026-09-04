#!/usr/bin/env python3
"""E0 STEP 3b: 下载指数日线（修复版）
从 master mapping 提取唯一 index_code，转为交易所代码(.SH/.SZ)，下载 index_daily。
CSI 纯指数无交易所代码的跳过并记录。
"""
import os, sys, time
import pandas as pd
import tushare as ts

DATA_ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
RAWDIR = os.path.join(DATA_ROOT, 'data', 'raw', 'etf')
IDXDIR = os.path.join(RAWDIR, 'index_daily')
os.makedirs(IDXDIR, exist_ok=True)

# token from config
import yaml
with open(os.path.join(DATA_ROOT, 'config', 'config.yaml')) as f:
    cfg = yaml.safe_load(f)
tok = cfg['data_source']['tushare']['token']
ts.set_token(tok)
pro = ts.pro_api()

master = pd.read_parquet(os.path.join(RAWDIR, 'etf_index_map_master.parquet'))
idx_codes = master['index_code'].dropna().unique().tolist()
print(f'unique index_code in master: {len(idx_codes)}')

# Convert .CSI to exchange codes: try .SH then .SZ
ex_candidates = set()
for c in idx_codes:
    if c.endswith('.CSI'):
        num = c.replace('.CSI', '')
        ex_candidates.add(num + '.SH')
        ex_candidates.add(num + '.SZ')
    elif c.endswith('.SH') or c.endswith('.SZ'):
        ex_candidates.add(c)

print(f'exchange code candidates: {len(ex_candidates)}')

DELAY = 0.15
log = []
success = 0
for i, c in enumerate(sorted(ex_candidates)):
    d = os.path.join(IDXDIR, c.replace('.', '_') + '.parquet')
    if os.path.exists(d):
        continue
    try:
        parts = []
        start, end = '20040101', '20260903'
        while True:
            df = pro.index_daily(ts_code=c, start_date=start, end_date=end)
            time.sleep(DELAY)
            if df is None or len(df) == 0:
                break
            parts.append(df)
            if len(df) < 6000:
                break
            start = str(df['trade_date'].min())
        if parts:
            out = pd.concat(parts, ignore_index=True).drop_duplicates(subset=['trade_date'])
            out = out.sort_values('trade_date')
            out.to_parquet(d)
            success += 1
            log.append((c, 'OK', len(out)))
        else:
            log.append((c, 'NO_DATA', 0))
    except Exception as e:
        log.append((c, 'ERROR', str(e)[:80]))
    if (i + 1) % 50 == 0:
        print(f'progress {i+1}/{len(ex_candidates)}, success={success}', flush=True)
        pd.DataFrame(log, columns=['ts_code', 'status', 'info']).to_csv(
            os.path.join(RAWDIR, 'index_daily_log.csv'), index=False)

pd.DataFrame(log, columns=['ts_code', 'status', 'info']).to_csv(
    os.path.join(RAWDIR, 'index_daily_log.csv'), index=False)
print(f'DONE. success={success}/{len(ex_candidates)}')
