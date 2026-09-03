"""ETF现金管理 vs 纯股票策略对比图"""
import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.rcParams['font.sans-serif'] = ['PingFang SC', 'Heiti TC', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False
ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
os.chdir(ROOT)

# 净值对比
fig, ax = plt.subplots(figsize=(14, 7))
for lab, c in [('etf_Top10_5层_ETF现金管理', '#e53935'), ('etf_Top10_5层_无ETF基准', '#039be5')]:
    eq = pd.read_parquet(f'results/{lab}.parquet')
    eq['date'] = pd.to_datetime(eq['date'])
    eq = eq.set_index('date')['equity'] / 1_000_000
    ax.plot(eq.index, eq.values, lw=2.2, color=c, label=lab)
ax.axhline(1.0, color='gray', lw=0.8, ls='--')
ax.set_title('闲置资金买标普500ETF(513500)现金管理：总收益+226.75% vs 纯股票+114.83%')
ax.set_ylabel('净值（初始100万）')
ax.legend(fontsize=10)
ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig('results/etf_equity.png', dpi=130)
print('saved etf_equity.png')

# 分年度对比
fig2, ax2 = plt.subplots(figsize=(13, 6))
years = ['2020', '2021', '2022', '2023', '2024', '2025', '2026']
y1 = [20.58, 60.04, -29.01, 48.71, 27.41, 18.61, 8.01]
y2 = [7.43, 42.85, -1.67, 22.58, 7.71, 9.49, -0.9]
x = np.arange(len(years))
ax2.bar(x - 0.2, y1, 0.4, label='ETF现金管理', color='#e53935', alpha=0.85)
ax2.bar(x + 0.2, y2, 0.4, label='纯股票基准', color='#039be5', alpha=0.85)
for i, (a, b) in enumerate(zip(y1, y2)):
    ax2.text(i - 0.2, a + 1, f'{a:.0f}', ha='center', fontsize=9)
    ax2.text(i + 0.2, b + 1, f'{b:.0f}', ha='center', fontsize=9)
ax2.axhline(0, color='black', lw=0.8)
ax2.set_xticks(x); ax2.set_xticklabels(years)
ax2.set_title('分年度收益：2020-21/2023-25 ETF助涨（空仓期吃标普500涨幅），2022年ETF满仓挨打-29%')
ax2.set_ylabel('年度收益 %'); ax2.legend(fontsize=10); ax2.grid(alpha=0.3, axis='y')
plt.tight_layout()
plt.savefig('results/etf_yearly.png', dpi=130)
print('saved etf_yearly.png')

# 溢价率时间序列
fig3, ax3 = plt.subplots(figsize=(14, 4.5))
m = pd.read_parquet('data/etf_513500_merged.parquet')
m['trade_date'] = pd.to_datetime(m['trade_date'])
ax3.plot(m['trade_date'], m['premium'], lw=1, color='#7b1fa2')
ax3.axhline(0, color='gray', lw=0.8)
ax3.fill_between(m['trade_date'], m['premium'], 0, where=m['premium'] > 0, color='#e53935', alpha=0.25)
ax3.fill_between(m['trade_date'], m['premium'], 0, where=m['premium'] < 0, color='#039be5', alpha=0.25)
ax3.set_title('513500 折溢价率（市价/单位净值-1）：均值+1.78%，最高+14.8%，427天溢价>3%')
ax3.set_ylabel('溢价率 %'); ax3.grid(alpha=0.3)
plt.tight_layout()
plt.savefig('results/etf_premium.png', dpi=130)
print('saved etf_premium.png')
