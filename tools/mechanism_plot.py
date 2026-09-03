"""机制示意图：为什么'触及上轨卖出'仍亏损（欧菲光 2020-09-01 ~ 2020-10-28）"""
import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

plt.rcParams['font.sans-serif'] = ['PingFang SC', 'Heiti TC', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
os.chdir(ROOT)

df = pd.read_parquet('data/combined_daily.parquet')
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values(['ts_code', 'date'])
of = df[(df['ts_code'] == '002456.SZ') & (df['date'] >= '2020-08-01') & (df['date'] <= '2020-11-20')].copy()
of = of.reset_index(drop=True)
of['close_adj'] = of['close'] * of['adj_factor']
of['high_adj'] = of['high'] * of['adj_factor']
of['low_adj'] = of['low'] * of['adj_factor']
of['ma20'] = of['close_adj'].rolling(20).mean()
of['std20'] = of['close_adj'].rolling(20).std()
of['bb_lower_adj'] = of['ma20'] - 2 * of['std20']
of['bb_upper_adj'] = of['ma20'] + 2 * of['std20']
# 转回实际价格
of['ma20_act'] = of['ma20'] / of['adj_factor']
of['bb_lower_act'] = of['bb_lower_adj'] / of['adj_factor']
of['bb_upper_act'] = of['bb_upper_adj'] / of['adj_factor']

# 平均成本16.52（实际价），卖出价16.04
avg_cost = 16.52
entry_d = pd.Timestamp('2020-09-01')
exit_d = pd.Timestamp('2020-10-28')

fig, ax = plt.subplots(figsize=(13, 6.5))
x = np.arange(len(of))
for i, r in of.iterrows():
    color = '#e53935' if r['close'] >= r['open'] else '#1e88e5'
    ax.plot([i, i], [r['low'], r['high']], color=color, lw=0.8, zorder=2)
    ax.add_patch(Rectangle((i-0.3, min(r['open'], r['close'])), 0.6,
                           abs(r['close']-r['open']) if r['close'] != r['open'] else 0.05,
                           facecolor=color, edgecolor=color, zorder=3))
ax.plot(x, of['ma20_act'], color='#fdd835', lw=1.6, label='MA20（布林中轨，随价格下移）')
ax.plot(x, of['bb_upper_act'], color='#8e24aa', lw=1.6, ls='--', label='布林上轨（也在下移）')
ax.plot(x, of['bb_lower_act'], color='#00897b', lw=1.6, ls='--', label='布林下轨（买入触发线）')
ax.axhline(avg_cost, color='#e53935', lw=2, ls='-', label=f'平均成本 {avg_cost:.2f} 元')
ax.axhline(16.04, color='#fb8c00', lw=1.6, ls=':', label='上轨卖出价 16.04 元（低于成本）')

# 标注买入点和卖出点
ei = of.index[of['date'] == entry_d][0]
xi = of.index[of['date'] == exit_d][0]
ax.scatter([ei], [of.loc[ei, 'close']], marker='^', color='#00897b', s=140, zorder=5)
ax.scatter([xi], [of.loc[xi, 'close']], marker='v', color='#fb8c00', s=140, zorder=5)
ax.annotate('9/1 收盘<下轨买入\n第1层', (ei, of.loc[ei, 'close']), xytext=(ei-6, avg_cost+2.2),
            fontsize=10, arrowprops=dict(arrowstyle='->', color='#00897b'))
ax.annotate('10/28 反弹触及上轨卖出\n但上轨<成本，-2.95%', (xi, of.loc[xi, 'close']), xytext=(xi+2, avg_cost+1.6),
            fontsize=10, arrowprops=dict(arrowstyle='->', color='#fb8c00'))

# 阴影区：成本线与卖出价之间的亏损
ax.fill_between(x, 16.04, avg_cost, where=(x >= ei), alpha=0.12, color='#e53935')
ax.text(len(of)-1, (avg_cost+16.04)/2, ' 亏损区：\n上轨 < 平均成本', ha='right', va='center',
        fontsize=10, color='#e53935')

ax.set_xticks(range(0, len(of), 5))
ax.set_xticklabels([of.loc[i, 'date'].strftime('%m-%d') for i in range(0, len(of), 5)], rotation=45, fontsize=9)
ax.set_title('欧菲光(002456) 2020-09-01 买入→2020-10-28 止盈卖出：为什么"触及上轨"还是亏 -2.95%？')
ax.set_ylabel('实际价格（元）')
ax.legend(loc='lower left', fontsize=9)
ax.grid(alpha=0.2)
plt.tight_layout()
plt.savefig('results/mechanism_loss.png', dpi=130)
print('saved mechanism_loss.png')
print('欧菲光期间最低点:', of['low'].min(), '最高点:', of['high'].max())
