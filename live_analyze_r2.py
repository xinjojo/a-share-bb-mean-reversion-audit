"""真实组合回测第二轮：关键配置净值曲线 + 年度收益图 + 完整汇总"""
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

# 关键代表性配置
key = ['Top1_5层', 'Top3_5层', 'Top5_5层', 'Top10_5层', 'Top10_5层_时间止损40',
       'Top10_4层', 'Top15_5层', 'Top20_5层']
colors = ['#9e9e9e', '#ff9800', '#4caf50', '#e53935', '#8e24aa', '#039be5', '#6d4c41', '#546e7a']

fig, ax = plt.subplots(figsize=(14, 7.5))
for lab, c in zip(key, colors):
    try:
        eq = pd.read_parquet(f'results/live_{lab}.parquet')
        eq = eq.set_index('date')['equity'] / 1_000_000
        ax.plot(eq.index, eq.values, label=lab, lw=2 if 'Top10_5层"' == lab else 1.5, color=c)
    except Exception as e:
        print(lab, 'ERR', e)
ax.set_title('真实单账户组合回测：净值曲线（2020-01 ~ 2026-08，初始100万，每笔实收费用）')
ax.set_ylabel('净值（元/100万）')
ax.legend(loc='upper left', fontsize=9)
ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig('results/live_equity_key.png', dpi=130)
print('saved live_equity_key.png')

# Top10_5层 年度收益
sm = pd.read_csv('results/live_summary.csv')
sm_r2 = pd.read_csv('results/live_summary_r2.csv')
allc = pd.concat([sm, sm_r2], ignore_index=True)
best = allc[allc['配置'] == 'Top10_5层'].iloc[0]
import ast
import re
raw = best['年度收益%']
raw2 = re.sub(r'np\.float64\(([-0-9.]+)\)', r'\1', raw)
yearly = ast.literal_eval(raw2)
years = list(yearly.keys())
vals = [float(yearly[y]) for y in years]
fig2, ax2 = plt.subplots(figsize=(11, 5.5))
bars = ax2.bar(years, vals, color=['#e53935' if v >= 0 else '#1e88e5' for v in vals])
for b, v in zip(bars, vals):
    ax2.text(b.get_x() + b.get_width()/2, b.get_height() + (0.5 if v >= 0 else -1.5),
             f'{v:+.1f}%', ha='center', fontsize=10)
ax2.axhline(0, color='black', lw=0.8)
ax2.set_title('Top10_5层（最优组合）：分年度收益')
ax2.set_ylabel('年度收益率 %')
ax2.grid(alpha=0.3, axis='y')
plt.tight_layout()
plt.savefig('results/live_yearly_best.png', dpi=130)
print('saved live_yearly_best.png')

# 完整汇总表（两轮合并，排序）
cols = ['配置', '总收益%', '年化收益%', '最大回撤%', '年化波动%', 'Sharpe', '交易次数',
        '胜率%', '平均盈利%', '平均亏损%', '盈亏比', 'ProfitFactor', '资金利用率%(持仓天数占比)']
allc = allc[cols].copy()
allc['总收益%'] = allc['总收益%'].astype(float).round(2)
allc['年化收益%'] = allc['年化收益%'].astype(float).round(2)
allc['最大回撤%'] = allc['最大回撤%'].astype(float).round(2)
allc['年化波动%'] = allc['年化波动%'].astype(float).round(2)
allc['Sharpe'] = allc['Sharpe'].astype(float).round(2)
allc['交易次数'] = allc['交易次数'].astype(int)
allc['胜率%'] = allc['胜率%'].astype(float).round(1)
allc['平均盈利%'] = allc['平均盈利%'].astype(float).round(2)
allc['平均亏损%'] = allc['平均亏损%'].astype(float).round(2)
allc['盈亏比'] = allc['盈亏比'].astype(float).round(2)
allc['ProfitFactor'] = allc['ProfitFactor'].astype(float).round(2)
allc['资金利用率%(持仓天数占比)'] = allc['资金利用率%(持仓天数占比)'].astype(float).round(1)
allc = allc.sort_values('总收益%', ascending=False).reset_index(drop=True)
allc.to_csv('results/live_all_combined.csv', index=False)
print('\n===== 全部23个配置总表（按总收益排序） =====')
print(allc.to_string(index=False))
