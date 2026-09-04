#!/usr/bin/env python3
"""E0 STEP 0: 下载并缓存 Tushare 基础数据（fund_basic / index_basic / trade_cal ETF 口径）
产物（原始缓存，不入 git）:
  DATA_ROOT/data/raw/etf/fund_basic.parquet   全量（L/D/P 全部 status）
  DATA_ROOT/data/raw/etf/index_basic.parquet  全量（CSI + 其他 market，尽量全）
  DATA_ROOT/data/raw/etf/retrieval_meta.json  拉取时间与参数记录
token 从环境变量 TUSHARE_TOKEN / tushare 缓存读取，不写入任何文件。
"""
import os, sys, json, time
import pandas as pd
import tushare as ts

DATA_ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
OUT = os.path.join(DATA_ROOT, 'data', 'raw', 'etf')
os.makedirs(OUT, exist_ok=True)

tok = os.environ.get('TUSHARE_TOKEN', '')
if tok:
    ts.set_token(tok)
pro = ts.pro_api()

meta = {'retrieval_date': time.strftime('%Y-%m-%d %H:%M:%S'), 'tushare_version': ts.__version__, 'steps': {}}

def save(df, name):
    path = os.path.join(OUT, name)
    df.to_parquet(path)
    print(f'saved {name}: {len(df)} rows', flush=True)

# 1. fund_basic 全量（market=E 交易所上市基金，含 L/D）
fb = pro.fund_basic(market='E')
fb['retrieval_date'] = meta['retrieval_date']
save(fb, 'fund_basic.parquet')
meta['steps']['fund_basic'] = {'rows': len(fb), 'status': fb['status'].value_counts().to_dict()}

# 2. index_basic 全量（CSI + OTHER；SW 是申万非指数，跳过）
ib_parts = []
for m in ['CSI', 'OTHER']:
    try:
        d = pro.index_basic(market=m)
        if d is not None and len(d):
            d['_mkt'] = m
            ib_parts.append(d)
            print(f'index_basic market={m}: {len(d)}', flush=True)
    except Exception as e:
        print(f'index_basic market={m} ERROR: {e}', flush=True)
if ib_parts:
    ib = pd.concat(ib_parts, ignore_index=True).drop_duplicates(subset=['ts_code'])
    ib['retrieval_date'] = meta['retrieval_date']
    save(ib, 'index_basic.parquet')
    meta['steps']['index_basic'] = {'rows': len(ib), 'markets': ib['_mkt'].value_counts().to_dict()}

with open(os.path.join(OUT, 'retrieval_meta.json'), 'w') as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)
print('DONE')
