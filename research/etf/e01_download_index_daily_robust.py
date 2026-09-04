#!/usr/bin/env python3
"""E0.1-E: Robust index_daily download (resumable, incremental).

Only downloads indexes that exist in index_basic_exchange.
Saves a progress log after every successful download.
Usage: run repeatedly; skips already-downloaded files.
"""
import os, sys, time, json
import pandas as pd
import tushare as ts
import yaml

DATA_ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
RAWDIR = os.path.join(DATA_ROOT, 'data', 'raw', 'etf')
IDXDIR = os.path.join(RAWDIR, 'index_daily')
os.makedirs(IDXDIR, exist_ok=True)

with open(os.path.join(DATA_ROOT, 'config', 'config.yaml')) as f:
    cfg = yaml.safe_load(f)
ts.set_token(cfg['data_source']['tushare']['token'])
pro = ts.pro_api()

# Get unique index codes from master mapping
master = pd.read_parquet(os.path.join(RAWDIR, 'master_mapping_full.parquet'))
idx_codes = master['index_code'].dropna().unique().tolist()
print(f'unique index_code in master: {len(idx_codes)}')

# Get valid exchange codes from index_basic_exchange
ib = pd.read_parquet(os.path.join(RAWDIR, 'index_basic_exchange.parquet'))
valid_codes = set(ib['ts_code'].tolist())
print(f'valid exchange index codes in index_basic: {len(valid_codes)}')

# Build candidate list: convert .CSI to .SH/.SZ, only keep valid ones
candidates = []
for c in idx_codes:
    if c.endswith('.CSI'):
        num = c.replace('.CSI', '')
        for suffix in ['.SH', '.SZ']:
            code = num + suffix
            if code in valid_codes:
                candidates.append(code)
    elif c in valid_codes:
        candidates.append(c)

candidates = sorted(set(candidates))
print(f'candidates to download (valid only): {len(candidates)}')

# Progress log
log_path = os.path.join(RAWDIR, 'index_daily_download_log.json')
if os.path.exists(log_path):
    with open(log_path) as f:
        log = json.load(f)
else:
    log = {'success': [], 'empty': [], 'failed': [], 'errors': {}}

DELAY = 0.25
success_count = 0
for i, c in enumerate(candidates):
    d = os.path.join(IDXDIR, c.replace('.', '_') + '.parquet')
    if os.path.exists(d):
        if c not in log['success']:
            log['success'].append(c)
        continue
    if c in log['empty'] or c in log['failed']:
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
            log['success'].append(c)
            success_count += 1
        else:
            log['empty'].append(c)
    except Exception as e:
        err = str(e)[:120]
        log['failed'].append(c)
        log['errors'][c] = err
        print(f'  ERROR {c}: {err}')
    if (i + 1) % 20 == 0:
        with open(log_path, 'w') as f:
            json.dump(log, f, indent=2)
        print(f'progress {i+1}/{len(candidates)}, new success={success_count}, '
              f'total success={len(log["success"])}, empty={len(log["empty"])}, failed={len(log["failed"])}', flush=True)

with open(log_path, 'w') as f:
    json.dump(log, f, indent=2)

print(f'\nDONE. success={len(log["success"])}, empty={len(log["empty"])}, failed={len(log["failed"])}')
print(f'files on disk: {len(os.listdir(IDXDIR))}')
