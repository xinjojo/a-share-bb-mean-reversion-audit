"""池宽×排序维度扫描分析图"""
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

sm = pd.read_csv('results/pool_summary.csv')
sm['池宽'] = sm['配置'].str.extract(r'Top(\d+)')[0].astype(int)
sm['维度'] = sm['配置'].str.extract(r'(amount|vol)_')[0]

# 图1：池宽 vs 总收益（成交额 vs 成交量）
fig, ax = plt.subplots(figsize=(12, 6.5))
for dim, c, mk in [('amount', '#e53935', 'o-'), ('vol', '#039be5', 's--')]:
    sub = sm[sm['维度'] == dim].sort_values('池宽')
    ax.plot(sub['池宽'], sub['总收益%'], mk, color=c, lw=2, label='成交额 TopN' if dim == 'amount' else '成交量 TopN')
    for _, r in sub.iterrows():
        ax.annotate(f"{r['总收益%']:.0f}%", (r['池宽'], r['总收益%']), textcoords="offset points",
                    xytext=(0, 8), ha='center', fontsize=9, color=c)
ax.axhline(0, color='black', lw=0.8)
ax.set_xlabel('候选池宽度 TopN')
ax.set_ylabel('总收益 %（2020-01 ~ 2026-08）')
ax.set_title('候选池宽度 × 排序维度：成交额Top10为全场最优，成交量维度普遍差且不稳定')
ax.legend(fontsize=10)
ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig('results/pool_width_vs_return.png', dpi=130)
print('saved pool_width_vs_return.png')

# 图2：净值曲线代表性对比
fig2, ax2 = plt.subplots(figsize=(14, 7))
for lab, c in [('amount_Top10_5层', '#e53935'), ('amount_Top20_5层', '#ff9800'),
               ('vol_Top10_5层', '#039be5'), ('vol_Top30_5层', '#8e24aa')]:
    eq = pd.read_parquet(f'results/pool_{lab}.parquet')
    eq = eq.set_index('date')['equity'] / 1_000_000
    ax2.plot(eq.index, eq.values, label=lab, lw=2, color=c)
ax2.set_title('净值曲线对比：成交额Top10/20（红/橙）远好于成交量Top10/30（蓝/紫）')
ax2.set_ylabel('净值')
ax2.legend(loc='upper left', fontsize=9)
ax2.grid(alpha=0.3)
plt.tight_layout()
plt.savefig('results/pool_equity.png', dpi=130)
print('saved pool_equity.png')

print(sm[['配置', '总收益%', '最大回撤%', 'Sharpe', '胜率%', '盈亏比', 'ProfitFactor']].to_string(index=False))
