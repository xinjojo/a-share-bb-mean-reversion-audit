"""多持仓分析：净值曲线对比 + 年度收益对比"""
import os, re, ast
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.rcParams['font.sans-serif'] = ['PingFang SC', 'Heiti TC', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False
ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
os.chdir(ROOT)

key = ['1只_最多5层(基准)', '2只_各最多3层', '3只_各最多2层', '4只_各最多2层', '5只_各1层(满仓)']
colors = ['#e53935', '#8e24aa', '#039be5', '#fb8c00', '#6d4c41']

fig, ax = plt.subplots(figsize=(14, 7))
for lab, c in zip(key, colors):
    eq = pd.read_parquet(f'results/multi_{lab}.parquet')
    eq = eq.set_index('date')['equity'] / 1_000_000
    ax.plot(eq.index, eq.values, label=lab, lw=2.0, color=c)
ax.set_title('多标的 vs 单标的：真实组合净值曲线（2020-01 ~ 2026-08，初始100万）')
ax.set_ylabel('净值')
ax.legend(loc='upper left', fontsize=9)
ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig('results/multi_equity.png', dpi=130)
print('saved multi_equity.png')

# 年度收益对比柱状图
sm = pd.read_csv('results/multi_summary.csv')
fig2, ax2 = plt.subplots(figsize=(14, 6.5))
years = ['2020', '2021', '2022', '2023', '2024', '2025', '2026']
x = np.arange(len(years))
width = 0.17
for i, (lab, c) in enumerate(zip(key, colors)):
    row = sm[sm['配置'] == lab].iloc[0]
    raw = re.sub(r'np\.float64\(([-0-9.]+)\)', r'\1', str(row['年度收益%']))
    yv = ast.literal_eval(raw)
    vals = [float(yv.get(y, 0)) for y in years]
    ax2.bar(x + (i - 2) * width, vals, width, label=lab.split('(')[0], color=c)
ax2.axhline(0, color='black', lw=0.8)
ax2.set_xticks(x)
ax2.set_xticklabels(years)
ax2.set_title('分年度收益对比：多标的在2022熊市吃亏更重')
ax2.set_ylabel('年度收益 %')
ax2.legend(fontsize=8)
ax2.grid(alpha=0.3, axis='y')
plt.tight_layout()
plt.savefig('results/multi_yearly.png', dpi=130)
print('saved multi_yearly.png')
