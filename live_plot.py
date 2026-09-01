"""真实组合回测：净值曲线与关键指标绘图"""
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

sm = pd.read_csv('results/live_summary.csv')
labels = sm['配置'].tolist()

# 选几个代表配置画净值曲线
fig, ax = plt.subplots(figsize=(14, 7))
for lab in labels:
    try:
        eq = pd.read_parquet(f'results/live_{lab}.parquet')
        eq = eq.set_index('date')['equity'] / 1_000_000
        ax.plot(eq.index, eq.values, label=lab, lw=1.5)
    except Exception as e:
        print(lab, 'ERR', e)
ax.set_title('真实单账户组合回测：净值曲线对比（2020-01 ~ 2026-08，初始100万）')
ax.set_ylabel('净值')
ax.legend(loc='upper left', fontsize=8)
ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig('results/live_equity_curves.png', dpi=130)
print('saved live_equity_curves.png')

# 年度收益条形图（对比）
yearly = pd.read_csv('results/live_summary.csv')
print(yearly[['配置', '总收益%', '年化收益%', '最大回撤%', 'Sharpe', '交易次数', '胜率%', '盈亏比', 'ProfitFactor', '资金利用率%(持仓天数占比)']].to_string(index=False))
