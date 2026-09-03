"""
层数对比分析：读取 levels_cmp_*.parquet，计算完整对比指标并输出图表
口径说明：
- 简单平均收益 = 所有回合 return_pct 的等权算术平均
- 资金加权收益 = Σpnl / Σcost（按每笔投入成本加权，即"按总本金算"的口径）
- 资金占用率 = Σ(cost×hold_days) / (日历天数×100万)
- 月度累计资金加权曲线 = 按 exit 月份累计 Σpnl / 全周期Σcost
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIGS = [1, 2, 3, 4, 5]

for f in ['PingFang SC', 'Hiragino Sans GB', 'Heiti SC', 'Arial Unicode MS']:
    try:
        font_manager.findfont(f, fallback_to_default=False)
        plt.rcParams['font.family'] = f
        break
    except Exception:
        continue
plt.rcParams['axes.unicode_minus'] = False

# 日历天数：2020-01-01 ~ 2026-08-25
CAL_DAYS = (pd.Timestamp('2026-08-25') - pd.Timestamp('2020-01-01')).days


def main():
    data = {}
    for c in CONFIGS:
        d = pd.read_parquet(os.path.join(PROJECT_ROOT, 'results', f'levels_cmp_{c}layer.parquet'))
        d['exit_date'] = pd.to_datetime(d['exit_date'])
        d['exit_month'] = d['exit_date'].dt.to_period('M')
        d['exit_year'] = d['exit_date'].dt.year
        data[c] = d

    # ============ 1. 主对比表 ============
    print('===== 层数对比主表 =====')
    rows = []
    for c in CONFIGS:
        d = data[c]
        wins = d[d['pnl'] > 0]
        loss = d[d['pnl'] <= 0]
        pf = wins['pnl'].sum() / abs(loss['pnl'].sum()) if loss['pnl'].sum() != 0 else np.inf
        cost_days = (d['cost'] * d['hold_days']).sum()
        rows.append({
            '最大层数': c,
            '回合数': len(d),
            '简单平均收益%': round(d['return_pct'].mean(), 2),
            '资金加权收益%': round(d['pnl'].sum() / d['cost'].sum() * 100, 2),
            '胜率%': round((d['pnl'] > 0).mean() * 100, 1),
            '平均盈利%': round(wins['return_pct'].mean(), 2) if len(wins) else 0,
            '平均亏损%': round(loss['return_pct'].mean(), 2) if len(loss) else 0,
            '盈亏比': round(wins['return_pct'].mean() / abs(loss['return_pct'].mean()), 2) if len(loss) else 0,
            'ProfitFactor': round(pf, 2),
            '平均每笔投入(万)': round(d['cost'].mean() / 1e4, 1),
            '平均持仓天': round(d['hold_days'].mean(), 1),
            '资金占用率%': round(cost_days / (CAL_DAYS * 1_000_000) * 100, 1),
        })
    df_main = pd.DataFrame(rows)
    print(df_main.to_string(index=False))
    df_main.to_csv(os.path.join(PROJECT_ROOT, 'results', 'levels_cmp_main.csv'), index=False)

    # ============ 2. 年度资金加权收益 ============
    print('\n===== 年度资金加权收益%（Σ当年pnl/Σ当年cost） =====')
    rows_year = []
    for c in CONFIGS:
        d = data[c]
        g = d.groupby('exit_year').apply(
            lambda x: pd.Series({
                '回合数': len(x),
                '资金加权收益%': round(x['pnl'].sum() / x['cost'].sum() * 100, 2),
                '胜率%': round((x['pnl'] > 0).mean() * 100, 1),
            }), include_groups=False).reset_index()
        g['最大层数'] = c
        rows_year.append(g)
    df_year = pd.concat(rows_year, ignore_index=True)
    pivot = df_year.pivot(index='exit_year', columns='最大层数', values='资金加权收益%')
    print(pivot.to_string())
    df_year.to_csv(os.path.join(PROJECT_ROOT, 'results', 'levels_cmp_yearly.csv'), index=False)

    # ============ 3. 月度累计资金加权收益曲线（用于画图/回撤） ============
    print('\n===== 月度累计资金加权收益%（曲线数据） =====')
    monthly = {}
    for c in CONFIGS:
        d = data[c]
        total_cost = d['cost'].sum()
        m = d.groupby('exit_month').apply(
            lambda x: pd.Series({'pnl': x['pnl'].sum(), 'cost': x['cost'].sum()}),
            include_groups=False).reset_index()
        m = m.sort_values('exit_month')
        m['cum_pnl'] = m['pnl'].cumsum()
        m['cum_weighted_pct'] = m['cum_pnl'] / total_cost * 100
        monthly[c] = m
        # 最大回撤（基于月度累计资金加权收益曲线，相对峰值回落）
        peak = m['cum_weighted_pct'].cummax()
        dd = (m['cum_weighted_pct'] - peak).min()
        print(f'  N={c}: 终值资金加权={m["cum_weighted_pct"].iloc[-1]:+.2f}%, 曲线最大回撤={dd:+.2f}pp')

    # ============ 4. 层数实际分布 ============
    print('\n===== 实际使用层数分布（N=5配置） =====')
    dist = data[5].groupby('levels_used').size()
    print((dist / dist.sum() * 100).round(1).to_string())

    # ============ 5. 验证：N=5资金加权 vs 历史口径（应≈2.87%） ============
    d5 = data[5]
    print(f'\n校验 N=5 资金加权收益: {d5["pnl"].sum()/d5["cost"].sum()*100:+.2f}% (历史明细口径 +2.87%)')

    # ============ 6. 画图 ============
    fig, axes = plt.subplots(2, 2, figsize=(16, 11))
    fig.suptitle('加仓层数对比：信号越买越亏？——全市场 95,615 笔/配置（2020-01 ~ 2026-08）', fontsize=14, fontweight='bold')

    # 图1: 简单平均 vs 资金加权
    ax = axes[0, 0]
    x = np.arange(len(CONFIGS))
    simple = df_main['简单平均收益%'].values
    weighted = df_main['资金加权收益%'].values
    w = 0.35
    b1 = ax.bar(x - w / 2, simple, w, label='简单平均(等权)', color='#4C9A6E')
    b2 = ax.bar(x + w / 2, weighted, w, label='资金加权(按投入)', color='#C0392B')
    for i, v in enumerate(simple):
        ax.text(i - w / 2, v + 0.2, f'{v:.1f}', ha='center', fontsize=9)
    for i, v in enumerate(weighted):
        ax.text(i + w / 2, v + 0.2, f'{v:.1f}', ha='center', fontsize=9)
    ax.set_xticks(x); ax.set_xticklabels([f'{c}层' for c in CONFIGS])
    ax.set_ylabel('收益率(%)'); ax.set_title('不同层数配置的平均收益（两种口径）')
    ax.legend(); ax.axhline(0, color='gray', linewidth=0.8)

    # 图2: 月度累计资金加权收益曲线
    ax = axes[0, 1]
    colors = ['#4C9A6E', '#7FB3D5', '#C9A227', '#D97B29', '#C0392B']
    for c, col in zip(CONFIGS, colors):
        m = monthly[c]
        ax.plot(m['exit_month'].astype(str), m['cum_weighted_pct'], label=f'{c}层', color=col, linewidth=1.8)
    ax.set_xlabel('退出月份'); ax.set_ylabel('累计资金加权收益(%)')
    ax.set_title('按退出月份的累计资金加权收益曲线')
    ax.legend(); ax.grid(alpha=0.3)
    ax.tick_params(axis='x', labelrotation=90, labelsize=7)

    # 图3: 年度资金加权收益
    ax = axes[1, 0]
    years = sorted(pivot.index)
    x2 = np.arange(len(years))
    width = 0.15
    for j, c in enumerate(CONFIGS):
        vals = [pivot.loc[y, c] if c in pivot.columns and y in pivot.index else np.nan for y in years]
        ax.bar(x2 + (j - 2) * width, vals, width, label=f'{c}层')
    ax.set_xticks(x2); ax.set_xticklabels(years)
    ax.set_ylabel('年度资金加权收益(%)'); ax.set_title('分年度资金加权收益')
    ax.legend(ncol=5, fontsize=8); ax.axhline(0, color='gray', linewidth=0.8)

    # 图4: N=5配置 层数实际分布
    ax = axes[1, 1]
    d = data[5]
    dist5 = d.groupby('levels_used')['return_pct'].agg(['mean', 'count'])
    dist5['pct'] = dist5['count'] / dist5['count'].sum() * 100
    bars = ax.bar(dist5.index.astype(str), dist5['pct'], color='#7FB3D5')
    ax2 = ax.twinx()
    ax2.plot(dist5.index.astype(str), dist5['mean'], 'o-', color='#C0392B', linewidth=2, label='平均收益')
    for i, (idx, row) in enumerate(dist5.iterrows()):
        ax.text(i, row['pct'] + 0.5, f"{row['pct']:.1f}%\n({row['mean']:+.1f}%)", ha='center', fontsize=8)
    ax.set_xlabel('实际使用层数'); ax.set_ylabel('回合占比(%)')
    ax2.set_ylabel('该层数平均收益(%)'); ax.set_title('N=5配置：实际使用层数分布与对应收益')
    ax.set_ylim(0, dist5['pct'].max() * 1.35)

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(os.path.join(PROJECT_ROOT, 'results', 'levels_comparison.png'), dpi=130, bbox_inches='tight')
    print('\n图表已保存: results/levels_comparison.png')


if __name__ == '__main__':
    main()
