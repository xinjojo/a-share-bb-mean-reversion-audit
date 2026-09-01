#!/usr/bin/env python3
"""增量下载2025-01-01至2026-08-26的A股日线和复权因子数据。"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import pandas as pd
import tushare as ts
from config.loader import load_config
from datetime import datetime

def main():
    config = load_config()
    token = config['data_source']['tushare']['token']
    ts.set_token(token)
    pro = ts.pro_api()

    start_date = '20250101'
    end_date = '20260826'

    # 获取交易日历
    print('获取交易日历...')
    trade_cal = pro.trade_cal(exchange='SSE', start_date=start_date, end_date=end_date)
    trade_dates = trade_cal[trade_cal['is_open'] == 1]['cal_date'].tolist()
    print(f'需要下载 {len(trade_dates)} 个交易日的数据')

    # 按交易日下载日线数据
    print('\n开始下载日线数据...')
    all_daily = []
    for i, trade_date in enumerate(trade_dates):
        try:
            df = pro.daily(trade_date=trade_date)
            if df is not None and len(df) > 0:
                all_daily.append(df)
            if (i + 1) % 50 == 0:
                print(f'  已下载 {i+1}/{len(trade_dates)} 天，累计 {sum(len(d) for d in all_daily)} 条')
            time.sleep(0.15)  # 避免频率限制
        except Exception as e:
            print(f'  下载 {trade_date} 失败: {e}，重试...')
            time.sleep(2)
            try:
                df = pro.daily(trade_date=trade_date)
                if df is not None and len(df) > 0:
                    all_daily.append(df)
            except Exception as e2:
                print(f'  重试失败: {e2}')

    if all_daily:
        daily_df = pd.concat(all_daily, ignore_index=True)
        print(f'\n日线数据总计: {len(daily_df)} 条')
        min_date = daily_df['trade_date'].min()
        max_date = daily_df['trade_date'].max()
        n_stocks = daily_df['ts_code'].nunique()
        print(f'日期范围: {min_date} ~ {max_date}')
        print(f'股票数: {n_stocks}')

        # 按股票保存，追加到现有文件
        daily_df['date'] = pd.to_datetime(daily_df['trade_date'])
        daily_df = daily_df.drop(columns=['trade_date'])

        saved = 0
        for ts_code, group in daily_df.groupby('ts_code'):
            filepath = f'data/raw/daily/{ts_code}.parquet'
            if os.path.exists(filepath):
                existing = pd.read_parquet(filepath)
                combined = pd.concat([existing, group]).drop_duplicates('date').sort_values('date')
            else:
                combined = group.sort_values('date')
            combined.to_parquet(filepath, index=False)
            saved += 1

        print(f'已保存 {saved} 只股票的日线数据')

    # 下载复权因子
    print('\n开始下载复权因子...')
    all_adj = []
    for i, trade_date in enumerate(trade_dates):
        try:
            df = pro.adj_factor(trade_date=trade_date)
            if df is not None and len(df) > 0:
                all_adj.append(df)
            if (i + 1) % 50 == 0:
                print(f'  已下载 {i+1}/{len(trade_dates)} 天')
            time.sleep(0.15)
        except Exception as e:
            print(f'  下载复权因子 {trade_date} 失败: {e}')
            time.sleep(2)
            try:
                df = pro.adj_factor(trade_date=trade_date)
                if df is not None and len(df) > 0:
                    all_adj.append(df)
            except Exception as e2:
                print(f'  重试失败: {e2}')

    if all_adj:
        adj_df = pd.concat(all_adj, ignore_index=True)
        print(f'\n复权因子总计: {len(adj_df)} 条')
        adj_df['date'] = pd.to_datetime(adj_df['trade_date'])
        adj_df = adj_df.drop(columns=['trade_date'])

        saved = 0
        for ts_code, group in adj_df.groupby('ts_code'):
            filepath = f'data/raw/adj_factor/{ts_code}.parquet'
            if os.path.exists(filepath):
                existing = pd.read_parquet(filepath)
                combined = pd.concat([existing, group]).drop_duplicates('date').sort_values('date')
            else:
                combined = group.sort_values('date')
            combined.to_parquet(filepath, index=False)
            saved += 1

        print(f'已保存 {saved} 只股票的复权因子')

    # 更新交易日历
    print('\n更新交易日历...')
    full_cal = pro.trade_cal(exchange='SSE', start_date='20200101', end_date=end_date)
    full_cal['date'] = pd.to_datetime(full_cal['cal_date'])
    full_cal = full_cal.drop(columns=['cal_date'])
    full_cal.to_parquet('data/raw/trade_cal.parquet', index=False)
    print(f'交易日历已更新: {len(full_cal)} 天')

    print('\n增量下载完成！')

if __name__ == '__main__':
    main()
