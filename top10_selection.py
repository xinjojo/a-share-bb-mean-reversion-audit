"""Top10池选股逻辑分析：实际选中排名分布"""
import pandas as pd
import numpy as np

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
df['cond'] = (~np.isnan(df['bb_lower'])) & (df['close_adj'] < df['bb_lower']) & (~df['is_limit_down'])

rows = []
for d, g in df.groupby('date'):
    pool = g[~g['is_st']]
    if len(pool) == 0:
        continue
    top10 = pool.nlargest(10, 'amount')
    sel = None
    for i, (_, r) in enumerate(top10.iterrows()):
        if r['cond']:
            sel = i + 1
            break
    if sel is not None:
        rows.append({'date': d, 'selected_rank': sel,
                     'top1_name': top10.iloc[0]['name'],
                     'sel_name': top10.iloc[sel - 1]['name']})
res = pd.DataFrame(rows)
print('=== Top10池中实际被选中的成交额排名分布 ===')
vc = res['selected_rank'].value_counts().sort_index()
for k in range(1, 11):
    print(f'选中第{k}名: {vc.get(k, 0)} 天  ({vc.get(k,0)/len(res)*100:.1f}%)')
print()
print(f'选中第1名(成交额最大)占比: {(res["selected_rank"]==1).mean()*100:.1f}%')
print(f'选中第1~3名占比: {(res["selected_rank"]<=3).mean()*100:.1f}%')
print(f'总选中天数: {len(res)}')
print()
print('=== 举例：Top1没跌破下轨，但从后面选中的日子 ===')
ex = res[res['selected_rank'] > 1].head(8)
print(ex[['date', 'top1_name', 'selected_rank', 'sel_name']].to_string(index=False))
