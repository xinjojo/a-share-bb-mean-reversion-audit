#!/usr/bin/env python3
"""生成净值曲线图和分析图表。"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


def plot_nav_curve(nav_path: str, output_path: str, title: str = "策略净值曲线"):
    """绘制净值曲线图，包含净值、回撤、仓位。"""
    df = pd.read_csv(nav_path)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)

    fig = plt.figure(figsize=(16, 12))
    gs = GridSpec(3, 1, height_ratios=[3, 1, 1], hspace=0.3)

    # 1. 净值曲线
    ax1 = fig.add_subplot(gs[0])
    ax1.plot(df['date'], df['total_equity'], color='#1f77b4', linewidth=1.5, label='策略净值')
    ax1.axhline(y=1000000, color='gray', linestyle='--', alpha=0.5, label='初始资金')
    ax1.fill_between(df['date'], df['total_equity'], 1000000,
                      where=df['total_equity'] >= 1000000, alpha=0.1, color='green')
    ax1.fill_between(df['date'], df['total_equity'], 1000000,
                      where=df['total_equity'] < 1000000, alpha=0.1, color='red')

    # 标注关键节点
    max_dd_idx = df['drawdown'].idxmin()
    ax1.annotate(f'最大回撤: {df.loc[max_dd_idx, "drawdown"]:.1f}%',
                 xy=(df.loc[max_dd_idx, 'date'], df.loc[max_dd_idx, 'total_equity']),
                 xytext=(20, 30), textcoords='offset points',
                 arrowprops=dict(arrowstyle='->', color='red'),
                 fontsize=10, color='red')

    ax1.set_title(title, fontsize=14, fontweight='bold')
    ax1.set_ylabel('权益 (元)', fontsize=11)
    ax1.legend(loc='upper left', fontsize=10)
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=6))

    # 2. 回撤曲线
    ax2 = fig.add_subplot(gs[1])
    ax2.fill_between(df['date'], df['drawdown'], 0, color='#d62728', alpha=0.4)
    ax2.plot(df['date'], df['drawdown'], color='#d62728', linewidth=0.8)
    ax2.set_ylabel('回撤 (%)', fontsize=11)
    ax2.set_title('回撤曲线', fontsize=12)
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=6))

    # 3. 仓位水平
    ax3 = fig.add_subplot(gs[2])
    colors = ['#2ca02c', '#ff7f0e', '#d62728', '#9467bd', '#8c564b']
    for level in range(1, 6):
        mask = df['position_level'] == level
        ax3.fill_between(df['date'], 0, level, where=mask, alpha=0.6, color=colors[level-1], label=f'第{level}层')
    ax3.set_ylabel('仓位层级', fontsize=11)
    ax3.set_title('仓位层级变化', fontsize=12)
    ax3.set_ylim(0, 5.5)
    ax3.legend(loc='upper left', fontsize=8, ncol=5)
    ax3.grid(True, alpha=0.3)
    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax3.xaxis.set_major_locator(mdates.MonthLocator(interval=6))

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"净值曲线图已保存: {output_path}")


def plot_yearly_returns(nav_path: str, output_path: str):
    """绘制年度收益率柱状图。"""
    df = pd.read_csv(nav_path)
    df['date'] = pd.to_datetime(df['date'])
    df['year'] = df['date'].dt.year

    yearly = []
    for year, group in df.groupby('year'):
        group = group.sort_values('date')
        start_eq = group['total_equity'].iloc[0]
        end_eq = group['total_equity'].iloc[-1]
        ret = (end_eq - start_eq) / start_eq * 100
        yearly.append({'year': int(year), 'return': ret})

    df_yearly = pd.DataFrame(yearly)

    fig, ax = plt.subplots(figsize=(12, 6))
    colors = ['green' if r >= 0 else 'red' for r in df_yearly['return']]
    bars = ax.bar(df_yearly['year'].astype(str), df_yearly['return'], color=colors, alpha=0.7, edgecolor='black')

    for bar, ret in zip(bars, df_yearly['return']):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + (0.5 if height >= 0 else -1.5),
                f'{ret:.1f}%', ha='center', va='bottom' if height >= 0 else 'top', fontsize=11, fontweight='bold')

    ax.axhline(y=0, color='black', linewidth=0.8)
    ax.set_title('年度收益率', fontsize=14, fontweight='bold')
    ax.set_ylabel('收益率 (%)', fontsize=11)
    ax.set_xlabel('年份', fontsize=11)
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"年度收益率图已保存: {output_path}")


def plot_take_profit_space(output_path: str):
    """绘制止盈空间分布图。"""
    # 数据来自分析结果
    thresholds = ['1.5%', '2.0%', '3.0%', '5.0%', '8.0%', '10.0%', '15.0%']
    percentages = [100.0, 95.5, 88.8, 55.6, 29.2, 12.9, 3.4]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    # 左图：达到各涨幅阈值的比例
    bars = ax1.bar(thresholds, percentages, color='#1f77b4', alpha=0.7, edgecolor='black')
    for bar, pct in zip(bars, percentages):
        ax1.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 1,
                 f'{pct:.1f}%', ha='center', va='bottom', fontsize=10, fontweight='bold')
    ax1.set_title('持仓期间达到各涨幅阈值的交易比例', fontsize=12, fontweight='bold')
    ax1.set_ylabel('比例 (%)', fontsize=11)
    ax1.set_ylim(0, 110)
    ax1.grid(True, alpha=0.3, axis='y')
    ax1.axvline(x=0, color='red', linestyle='--', alpha=0.7, label='当前止盈1.5%')
    ax1.legend()

    # 右图：止损参数对比
    stop_levels = ['disabled', '3%', '5%', '7%', '10%', '15%']
    avg_pnl = [0.25, -0.47, -0.14, 0.09, 0.13, 0.17]
    profit_factor = [1.246, 0.632, 0.887, 1.081, 1.116, 1.152]

    x = np.arange(len(stop_levels))
    width = 0.35
    ax2_twin = ax2.twinx()

    bars1 = ax2.bar(x - width/2, avg_pnl, width, label='平均盈亏%', color='#2ca02c', alpha=0.7)
    bars2 = ax2_twin.bar(x + width/2, profit_factor, width, label='盈亏比', color='#ff7f0e', alpha=0.7)

    ax2.set_xticks(x)
    ax2.set_xticklabels(stop_levels)
    ax2.set_ylabel('平均盈亏 (%)', fontsize=11, color='#2ca02c')
    ax2_twin.set_ylabel('盈亏比', fontsize=11, color='#ff7f0e')
    ax2.axhline(y=0, color='black', linewidth=0.8)
    ax2_twin.axhline(y=1, color='gray', linestyle='--', alpha=0.5)
    ax2.set_title('不同止损参数效果对比', fontsize=12, fontweight='bold')

    lines1, labels1 = ax2.get_legend_handles_labels()
    lines2, labels2 = ax2_twin.get_legend_handles_labels()
    ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"止盈空间与止损对比图已保存: {output_path}")


if __name__ == '__main__':
    nav_path = 'results/reports/nav_20260826_011422.csv'
    output_dir = 'results/charts'
    os.makedirs(output_dir, exist_ok=True)

    plot_nav_curve(nav_path, os.path.join(output_dir, 'nav_curve.png'),
                   'A股单股 BB Lower Mean Reversion 策略净值曲线 (2020-2026)')
    plot_yearly_returns(nav_path, os.path.join(output_dir, 'yearly_returns.png'))
    plot_take_profit_space(os.path.join(output_dir, 'take_profit_analysis.png'))
    print('\n所有图表生成完成！')
