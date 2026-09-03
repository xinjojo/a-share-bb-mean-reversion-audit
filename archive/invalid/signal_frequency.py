"""
信号频率分析：每日成交额TopN的股票，有多少天收盘<布林下轨（真实组合回测可行性）
"""
import pandas as pd
import numpy as np

df = pd.read_parquet('data/combined_daily.parquet')
sb = pd.read_parquet('data/raw/stock_basic.parquet')
df = df.merge(sb[['ts_code', 'name', 'market']], on='ts_code', how='left')
df['date'] = pd.to_datetime(df['date'])
df = df[(df['date'] >= '2020-01-01') & (df['date'] <= '2026-08-25')]
df = df.sort_values(['ts_code', 'date']).reset_index(drop=True)

# ST标记（当前快照，近似）
df['is_st'] = df['name'].str.contains('ST', na=False)

# 后复权价
df['close_adj'] = df['close'] * df['adj_factor']
df['high_adj'] = df['high'] * df['adj_factor']

# 向量化计算布林带（groupby rolling）
print('计算布林带...', flush=True)
g = df.groupby('ts_code')['close_adj']
df['ma20'] = g.transform(lambda x: x.rolling(20, min_periods=20).mean())
df['std20'] = g.transform(lambda x: x.rolling(20, min_periods=20).std())
df['bb_lower'] = df['ma20'] - 2 * df['std20']
df['bb_upper'] = df['ma20'] + 2 * df['std20']
print('布林带计算完成', flush=True)

# 排除ST后的股票池
df_pool = df[~df['is_st']]
total_days = df['date'].nunique()
print(f'总交易日: {total_days}, 非ST股票数: {df_pool["ts_code"].nunique()}', flush=True)

# 每日成交额TopN
for topn in [1, 3, 5, 10]:
    # 每天取成交额TopN（非ST）
    top_codes = df_pool.sort_values(['date', 'amount'], ascending=[True, False]) \
        .groupby('date')['ts_code'].head(topn)
    top_df = df_pool[df_pool.index.isin(top_codes.index)]
    hit = top_df[top_df['close_adj'] < top_df['bb_lower']]
    hit_days = hit['date'].nunique()
    print(f'Top{topn}: 满足收盘<BB下轨的天数 = {hit_days}/{total_days} ({hit_days/total_days*100:.1f}%), 信号次数={len(hit)}', flush=True)
    if topn == 1:
        # Top1信号明细
        hit1 = hit[['date', 'ts_code', 'name', 'close_adj', 'bb_lower', 'amount']]
        hit1['signal'] = 1
        hit1.to_csv('results/signal_top1_days.csv', index=False)
        print('Top1信号样例:', hit1.head(8).to_string(), flush=True)
        # 每年信号数
        hit1['year'] = hit1['date'].dt.year
        print('Top1每年信号数:', hit1.groupby('year').size().to_dict(), flush=True)

# Top1的股票分布（看是不是总在几只大票）
top1_all = df_pool.sort_values(['date', 'amount'], ascending=[True, False]).groupby('date').head(1)
print('\n成交额Top1的股票分布（出现次数最多前10）:', flush=True)
print(top1_all['name'].value_counts().head(10).to_string(), flush=True)
