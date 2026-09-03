#!/usr/bin/env python3
"""下载 2018-01-01 ~ 2019-12-31 warmup 历史 (daily + adj_factor + PIT ST 状态)
用于 REGIME DISCOVERY 的 BB/Trend/Liquidity/RV20/Vol-percentile warmup。
token 从环境变量 TUSHARE_TOKEN 读取，不硬编码。
"""
import os, time, sys
import numpy as np, pandas as pd

TOKEN = os.environ.get('TUSHARE_TOKEN')
if not TOKEN:
    sys.exit('TUSHARE_TOKEN env required')
import tushare as ts
ts.set_token(TOKEN)
pro = ts.pro_api()

cal = pd.read_parquet('data/raw/trade_cal_full.parquet')
cal['date'] = pd.to_datetime(cal['date'])
dates = sorted(d for d in cal['date'] if pd.Timestamp('2018-01-01') <= d <= pd.Timestamp('2019-12-31'))
print(f'warmup 交易日数: {len(dates)}  {dates[0].date()} ~ {dates[-1].date()}')

rows = []
# PIT ST 状态: namechange 逐日 active 状态 (start_date <= d 的最近记录)
nc = pd.read_parquet('data/raw/namechange_full.parquet')
nc['start_date'] = pd.to_datetime(nc['start_date'])
nc['is_st'] = nc['name'].str.contains('ST')
st_all = nc[['ts_code', 'start_date', 'is_st']].sort_values('start_date')
for i, d in enumerate(dates):
    ds = d.strftime('%Y%m%d')
    for attempt in range(3):
        try:
            time.sleep(0.15)
            df = pro.daily(trade_date=ds)
            af = pro.adj_factor(trade_date=ds)[['ts_code', 'adj_factor']]
            break
        except Exception as e:
            if attempt == 2: raise
            time.sleep(3)
    df = df.merge(af, on='ts_code', how='left')
    df['date'] = d
    # ST 状态: 该日已生效的最近 namechange
    active = st_all[st_all['start_date'] <= d]
    last_st = active.groupby('ts_code')['is_st'].last()
    df['is_st_pit'] = df['ts_code'].map(last_st).fillna(False).astype(bool)
    rows.append(df)
    if (i+1) % 50 == 0:
        print(f'  {i+1}/{len(dates)} done ({df.shape[0]} rows)')

allw = pd.concat(rows, ignore_index=True)
print('total warmup rows:', len(allw))
res = allw[['ts_code', 'date', 'open', 'high', 'low', 'close', 'pre_close', 'vol', 'amount',
            'adj_factor', 'is_st_pit']]
res.to_parquet('data/warmup_daily_2018_2019.parquet')
print('saved data/warmup_daily_2018_2019.parquet rows=', len(res))
print('date range:', res['date'].min(), '->', res['date'].max())
print('ST rows:', int(res['is_st_pit'].sum()))
