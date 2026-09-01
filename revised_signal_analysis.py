"""分析：全市场跌破布林下轨的信号特征（用户提出的'先超跌后成交额'方案）"""
import pandas as pd
import numpy as np
import time

t0 = time.time()
df = pd.read_parquet('data/combined_daily.parquet')
sb = pd.read_parquet('data/raw/stock_basic.parquet')
df = df.merge(sb[['ts_code', 'name']], on='ts_code', how='left')
df['date'] = pd.to_datetime(df['date'])
df = df[(df['date'] >= '2020-01-01') & (df['date'] <= '2026-08-25')]
df = df.sort_values(['ts_code', 'date']).reset_index(drop=True)
df['is_st'] = df['name'].str.contains('ST', na=False)
df['close_adj'] = df['close'] * df['adj_factor']
g = df.groupby('ts_code')['close_adj']
df['ma20'] = g.transform(lambda x: x.rolling(20, min_periods=20).mean())
df['std20'] = g.transform(lambda x: x.rolling(20, min_periods=20).std())
df['bb_lower'] = df['ma20'] - 2 * df['std20']
df['cond_super'] = (~np.isnan(df['bb_lower'])) & (df['close_adj'] < df['bb_lower']) & (~df['is_limit_down'])
print(f'布林带计算完成 {time.time()-t0:.0f}s')

pool = df[~df['is_st']]
super_df = pool[pool['cond_super']]

# 每天超跌股数量统计
daily_cnt = super_df.groupby('date').size()
print('\n=== 每天跌破布林下轨的股票数量 ===')
print(f'平均: {daily_cnt.mean():.0f} 只/天, 中位数: {daily_cnt.median():.0f}, 最大: {daily_cnt.max()}, 最小: {daily_cnt.min()}')
print(f'完全无超跌股的天数: {(daily_cnt == 0).sum()} 天 / {len(daily_cnt)} 天')

# 每天从超跌股里选成交额最大的
sel = super_df.sort_values(['date', 'amount'], ascending=[True, False]).groupby('date').head(1)
print(f'\n=== 每天成交额最大的超跌股（可交易天数 {len(sel)} 天）===')
print('每年可交易天数:')
sel['year'] = sel['date'].dt.year
print(sel.groupby('year').size().to_dict())
print('\n成交额最大超跌股top15（出现次数）:')
print(sel['name'].value_counts().head(15).to_string())
print(f'\n选中股票平均成交额(千元): {sel["amount"].mean()/1e4:.0f} 万')
print(f'选中股票成交额中位数(千元): {sel["amount"].median()/1e4:.0f} 万')

# 成交额排名分布：被选中的超跌股，在全市场成交额里排第几
print('\n=== 被选中的超跌股在全市场成交额中的排名分布 ===')
df_sorted = pool.sort_values(['date', 'amount'], ascending=[True, False]).copy()
df_sorted['rank_all'] = df_sorted.groupby('date').cumcount() + 1
sel2 = df_sorted[df_sorted['ts_code'].isin(set(sel['ts_code'].unique()))]
# 更精确：按 date+ts_code 合并
sel_m = sel[['date', 'ts_code']].merge(df_sorted[['date', 'ts_code', 'rank_all']], on=['date', 'ts_code'])
print(sel_m['rank_all'].describe().round(1).to_string())
print('排名<=10 占比:', (sel_m['rank_all'] <= 10).mean() * 100, '%')
print('排名<=30 占比:', (sel_m['rank_all'] <= 30).mean() * 100, '%')
print('排名<=100 占比:', (sel_m['rank_all'] <= 100).mean() * 100, '%')

# 计算量评估
print(f'\n=== 计算量 ===')
print(f'每天跌破下轨股票数（需从中nlargest选1）: 平均 {daily_cnt.mean():.0f} 只')
print(f'总计算: 布林带一次性预计算 {time.time()-t0:.0f}s, 每天筛选为向量化布尔+nlargest, 1611天 x 5000行')
print(f'方案A（全市场先超跌后选额）计算量: 完全可接受，不需要讨巧')
