"""新旧选股逻辑对比图"""
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

# 净值曲线对比
fig, ax = plt.subplots(figsize=(14, 7))
pairs = [
    ('results/live_Top10_5层.parquet', '旧逻辑：Top10池找超跌 (+97.4%)', '#e53935'),
    ('results/live_先超跌后成交额_5层.parquet', '新逻辑：全市场超跌选额最大 (+28.4%)', '#039be5'),
]
for path, lab, c in pairs:
    eq = pd.read_parquet(path)
    eq = eq.set_index('date')['equity'] / 1_000_000
    ax.plot(eq.index, eq.values, label=lab, lw=2.2, color=c)
ax.set_title('选股逻辑反转对比：先超跌后成交额 vs 成交额Top10池找超跌')
ax.set_ylabel('净值（初始100万）')
ax.legend(loc='upper left', fontsize=10)
ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig('results/revised_vs_old_equity.png', dpi=130)
print('saved revised_vs_old_equity.png')

# 分年度对比
fig2, ax2 = plt.subplots(figsize=(13, 6))
years = ['2020', '2021', '2022', '2023', '2024', '2025', '2026']
x = np.arange(len(years))
data = [
    ('results/live_summary.csv', 'Top10_5层', '#e53935'),
    ('results/revised_summary.csv', '先超跌后成交额_5层', '#039be5'),
]
for fname, cfg, c in data:
    sm = pd.read_csv(fname)
    row = sm[sm['配置'] == cfg].iloc[0]
    raw = re.sub(r'np\.float64\(([-0-9.]+)\)', r'\1', str(row['年度收益%']))
    yv = ast.literal_eval(raw)
    vals = [float(yv.get(y, 0)) for y in years]
    ax2.bar(x + (0 if cfg.startswith('Top') else 0.4), vals, 0.4,
            label=cfg, color=c, alpha=0.85)
ax2.axhline(0, color='black', lw=0.8)
ax2.set_xticks(x + 0.2)
ax2.set_xticklabels(years)
ax2.set_title('分年度收益：新逻辑2025年因退市股巨亏-28.6%，且2020-21牛市反而亏')
ax2.set_ylabel('年度收益 %')
ax2.legend(fontsize=10)
ax2.grid(alpha=0.3, axis='y')
plt.tight_layout()
plt.savefig('results/revised_vs_old_yearly.png', dpi=130)
print('saved revised_vs_old_yearly.png')
