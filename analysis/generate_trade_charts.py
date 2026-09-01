#!/usr/bin/env python3
"""
生成每笔交易的走势图：进场前20天 ~ 出场后20天
标注：K线、布林带、买卖点、止盈/止损线
输出：单个HTML文件，所有交易图表可滚动查看
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import base64
import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
from analysis.trade_review import TradeReviewAnalyzer


def plot_trade_chart(rt, df_stock, trade_index):
    """
    生成单笔交易的走势图。

    Args:
        rt: round trip字典
        df_stock: 该股票的全部日线数据
        trade_index: 交易编号

    Returns:
        base64编码的PNG图片
    """
    entry_date = rt['entry_date']
    exit_date = rt['exit_date']
    symbol = rt['symbol']

    # 确定时间范围：进场前20天 ~ 出场后20天
    df_stock = df_stock.sort_values('date').reset_index(drop=True)
    entry_idx = df_stock[df_stock['date'] == entry_date].index
    exit_idx = df_stock[df_stock['date'] == exit_date].index

    if len(entry_idx) == 0 or len(exit_idx) == 0:
        return None

    start_idx = max(0, entry_idx[0] - 20)
    end_idx = min(len(df_stock) - 1, exit_idx[0] + 20)

    df_plot = df_stock.iloc[start_idx:end_idx + 1].copy()

    # 计算布林带（全量数据计算，取对应区间）
    df_full = df_stock.copy()
    df_full['middle'] = df_full['close'].rolling(window=20).mean()
    df_full['std'] = df_full['close'].rolling(window=20).std()
    df_full['upper'] = df_full['middle'] + 2 * df_full['std']
    df_full['lower'] = df_full['middle'] - 2 * df_full['std']

    df_plot = df_full.iloc[start_idx:end_idx + 1].copy()

    # 创建图表
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), height_ratios=[3, 1],
                                      gridspec_kw={'hspace': 0.05})

    dates = df_plot['date']
    x = range(len(df_plot))

    # 绘制K线
    for i, row in df_plot.iterrows():
        idx = i - start_idx
        color = 'red' if row['close'] >= row['open'] else 'green'
        # 影线
        ax1.plot([idx, idx], [row['low'], row['high']], color=color, linewidth=0.8)
        # 实体
        body_bottom = min(row['open'], row['close'])
        body_height = abs(row['close'] - row['open'])
        if body_height < 0.01:
            body_height = 0.01
        rect = Rectangle((idx - 0.3, body_bottom), 0.6, body_height,
                          facecolor=color, edgecolor=color, linewidth=0.5)
        ax1.add_patch(rect)

    # 绘制布林带
    ax1.plot(x, df_plot['upper'], color='orange', linewidth=0.8, alpha=0.7, label='BB Upper')
    ax1.plot(x, df_plot['middle'], color='blue', linewidth=0.8, alpha=0.7, label='BB Middle')
    ax1.plot(x, df_plot['lower'], color='orange', linewidth=0.8, alpha=0.7, label='BB Lower')
    ax1.fill_between(x, df_plot['upper'], df_plot['lower'], alpha=0.05, color='orange')

    # 标注进场点
    entry_pos = entry_idx[0] - start_idx
    entry_row = df_stock.iloc[entry_idx[0]]
    ax1.scatter(entry_pos, entry_row['close'] * 0.98, marker='^', color='red', s=150, zorder=5,
                label=f'Entry @ {entry_row["close"]:.2f}')
    ax1.annotate(f'BUY\n{entry_row["close"]:.2f}',
                 xy=(entry_pos, entry_row['low']),
                 xytext=(entry_pos, entry_row['low'] * 0.97),
                 fontsize=8, ha='center', color='red', fontweight='bold')

    # 标注加仓点（如果有）
    if rt.get('buy_trades') and len(rt['buy_trades']) > 1:
        for j, buy in enumerate(rt['buy_trades'][1:], 1):
            buy_date = buy['date']
            buy_idx = df_stock[df_stock['date'] == buy_date].index
            if len(buy_idx) > 0:
                buy_pos = buy_idx[0] - start_idx
                buy_row = df_stock.iloc[buy_idx[0]]
                ax1.scatter(buy_pos, buy_row['close'] * 0.98, marker='^', color='orange', s=120, zorder=5)
                ax1.annotate(f'ADD{j}\n{buy_row["close"]:.2f}',
                             xy=(buy_pos, buy_row['low']),
                             xytext=(buy_pos, buy_row['low'] * 0.97),
                             fontsize=7, ha='center', color='orange', fontweight='bold')

    # 标注出场点
    exit_pos = exit_idx[0] - start_idx
    exit_row = df_stock.iloc[exit_idx[0]]
    exit_color = 'green' if rt['pnl'] > 0 else 'purple'
    ax1.scatter(exit_pos, exit_row['close'] * 1.02, marker='v', color=exit_color, s=150, zorder=5,
                label=f'Exit @ {exit_row["close"]:.2f}')
    ax1.annotate(f'SELL\n{exit_row["close"]:.2f}',
                 xy=(exit_pos, exit_row['high']),
                 xytext=(exit_pos, exit_row['high'] * 1.03),
                 fontsize=8, ha='center', color=exit_color, fontweight='bold')

    # 绘制止盈线和止损线（持仓期间）
    if rt.get('avg_cost'):
        avg_cost = rt['avg_cost']
        tp_price = avg_cost * 1.015
        sl_price = avg_cost * 0.9
        # 只在持仓期间画
        hold_start = entry_pos
        hold_end = exit_pos
        ax1.axhline(y=tp_price, xmin=(hold_start + 0.5) / len(df_plot),
                     xmax=(hold_end + 0.5) / len(df_plot),
                     color='green', linestyle='--', linewidth=0.8, alpha=0.7)
        ax1.axhline(y=sl_price, xmin=(hold_start + 0.5) / len(df_plot),
                     xmax=(hold_end + 0.5) / len(df_plot),
                     color='red', linestyle='--', linewidth=0.8, alpha=0.7)

    # 标注持仓区间背景
    ax1.axvspan(entry_pos - 0.5, exit_pos + 0.5, alpha=0.08, color='yellow')

    # 设置x轴标签
    tick_positions = list(range(0, len(df_plot), max(1, len(df_plot) // 8)))
    tick_labels = [df_plot.iloc[p]['date'].strftime('%m-%d') for p in tick_positions]
    ax1.set_xticks(tick_positions)
    ax1.set_xticklabels(tick_labels, fontsize=8)
    ax1.set_xlim(-1, len(df_plot))

    # 标题
    pnl_color = 'green' if rt['pnl'] > 0 else 'red'
    title = (f"#{trade_index} {symbol} | "
             f"{entry_date.strftime('%Y-%m-%d')} ~ {exit_date.strftime('%Y-%m-%d')} | "
             f"持仓{rt['holding_days']}天 | {rt.get('max_level', 1)}层 | "
             f"盈亏{rt['pnl']:+,.0f}元 ({rt['pnl_pct']:+.2f}%) | {rt.get('exit_reason', '')}")
    ax1.set_title(title, fontsize=10, color=pnl_color, fontweight='bold', pad=10)
    ax1.legend(loc='upper left', fontsize=7)
    ax1.grid(True, alpha=0.3)
    ax1.set_ylabel('Price', fontsize=9)

    # 成交量
    for i, row in df_plot.iterrows():
        idx = i - start_idx
        color = 'red' if row['close'] >= row['open'] else 'green'
        ax2.bar(idx, row['vol'], color=color, alpha=0.6, width=0.6)

    ax2.set_xticks(tick_positions)
    ax2.set_xticklabels(tick_labels, fontsize=8)
    ax2.set_xlim(-1, len(df_plot))
    ax2.set_ylabel('Volume', fontsize=9)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()

    # 转为base64
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    return img_base64


def main():
    trades_path = 'results/trades/trades_20260826_011422.csv'
    trades = pd.read_csv(trades_path).to_dict('records')
    reviewer = TradeReviewAnalyzer(trades)
    round_trips = reviewer._build_round_trips()

    # 为每笔交易关联买入记录
    buy_trades = [t for t in trades if t['action'] == 'BUY']
    for rt in round_trips:
        rt_buys = [t for t in buy_trades
                   if t['symbol'] == rt['symbol']
                   and rt['entry_date'] <= pd.to_datetime(t['date']) <= rt['exit_date']]
        rt['buy_trades'] = rt_buys

    print(f"共 {len(round_trips)} 笔完整交易，开始生成走势图...")

    # 生成HTML
    html_parts = []
    html_parts.append("""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>交易走势图 - 全部交易</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #1a1a2e; color: #eee; margin: 0; padding: 20px; }
h1 { text-align: center; color: #4fc3f7; }
.summary { background: #16213e; padding: 15px; border-radius: 8px; margin-bottom: 20px; display: flex; justify-content: space-around; flex-wrap: wrap; }
.summary-item { text-align: center; }
.summary-value { font-size: 24px; font-weight: bold; }
.summary-label { font-size: 12px; color: #aaa; }
.filter-bar { background: #16213e; padding: 10px; border-radius: 8px; margin-bottom: 20px; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.filter-bar button { background: #0f3460; color: #eee; border: 1px solid #4fc3f7; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 14px; }
.filter-bar button.active { background: #4fc3f7; color: #1a1a2e; }
.trade-card { background: #16213e; border-radius: 8px; margin-bottom: 20px; overflow: hidden; border: 1px solid #0f3460; }
.trade-card.win { border-left: 4px solid #4caf50; }
.trade-card.loss { border-left: 4px solid #f44336; }
.trade-info { padding: 12px 15px; background: #0f3460; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 10px; }
.trade-info span { font-size: 13px; }
.trade-chart { padding: 10px; text-align: center; }
.trade-chart img { max-width: 100%; border-radius: 4px; }
.win-color { color: #4caf50; }
.loss-color { color: #f44336; }
.nav-top { position: fixed; top: 10px; right: 10px; background: #0f3460; padding: 10px; border-radius: 8px; font-size: 12px; z-index: 100; }
</style>
</head>
<body>
<h1>交易走势图 - 全部178笔交易</h1>
<div class="summary">
<div class="summary-item"><div class="summary-value">178</div><div class="summary-label">总交易数</div></div>
<div class="summary-item"><div class="summary-value win-color">160</div><div class="summary-label">止盈</div></div>
<div class="summary-item"><div class="summary-value loss-color">18</div><div class="summary-label">止损</div></div>
<div class="summary-item"><div class="summary-value">89.9%</div><div class="summary-label">胜率</div></div>
<div class="summary-item"><div class="summary-value loss-color">-43.6万</div><div class="summary-label">总盈亏</div></div>
</div>
<div class="filter-bar">
<button onclick="filterTrades('all')" class="active" id="btn-all">全部</button>
<button onclick="filterTrades('win')" id="btn-win">盈利</button>
<button onclick="filterTrades('loss')" id="btn-loss">亏损</button>
<button onclick="filterTrades('stop')" id="btn-stop">止损</button>
<span style="margin-left:auto; color:#aaa; font-size:12px;">每张图包含进场前20天和出场后20天</span>
</div>
<div id="trade-container">
""")

    # 加载股票数据缓存
    stock_cache = {}

    for i, rt in enumerate(round_trips, 1):
        symbol = rt['symbol']

        # 加载股票数据
        if symbol not in stock_cache:
            filepath = os.path.join('data', 'raw', 'daily', f'{symbol}.parquet')
            if os.path.exists(filepath):
                df = pd.read_parquet(filepath)
                df['date'] = pd.to_datetime(df['date'])
                stock_cache[symbol] = df
            else:
                stock_cache[symbol] = None

        df_stock = stock_cache[symbol]
        if df_stock is None:
            continue

        # 生成图表
        img_base64 = plot_trade_chart(rt, df_stock, i)
        if img_base64 is None:
            continue

        # 交易信息
        pnl_class = 'win' if rt['pnl'] > 0 else 'loss'
        pnl_color_class = 'win-color' if rt['pnl'] > 0 else 'loss-color'
        exit_reason = rt.get('exit_reason', '')

        html_parts.append(f"""
<div class="trade-card {pnl_class}" data-type="{pnl_class}" data-reason="{exit_reason}">
<div class="trade-info">
<span>#{i} <b>{symbol}</b></span>
<span>{rt['entry_date'].strftime('%Y-%m-%d')} ~ {rt['exit_date'].strftime('%Y-%m-%d')}</span>
<span>持仓 {rt['holding_days']} 天</span>
<span>{rt.get('max_level', 1)} 层</span>
<span>成本 {rt.get('avg_cost', 0):.2f}</span>
<span class="{pnl_color_class}">盈亏 {rt['pnl']:+,.0f}元 ({rt['pnl_pct']:+.2f}%)</span>
<span>{exit_reason}</span>
</div>
<div class="trade-chart">
<img src="data:image/png;base64,{img_base64}" alt="Trade #{i}">
</div>
</div>
""")

        if i % 20 == 0:
            print(f"  已生成 {i}/{len(round_trips)} 张图表...")

    html_parts.append("""
</div>
<div class="nav-top">
<div id="nav-info">滚动查看</div>
</div>
<script>
function filterTrades(type) {
    document.querySelectorAll('.filter-bar button').forEach(b => b.classList.remove('active'));
    document.getElementById('btn-' + type).classList.add('active');
    document.querySelectorAll('.trade-card').forEach(card => {
        if (type === 'all') {
            card.style.display = '';
        } else if (type === 'win') {
            card.style.display = card.dataset.type === 'win' ? '' : 'none';
        } else if (type === 'loss') {
            card.style.display = card.dataset.type === 'loss' ? '' : 'none';
        } else if (type === 'stop') {
            card.style.display = card.dataset.reason === 'STOP_LOSS' ? '' : 'none';
        }
    });
}
window.addEventListener('scroll', () => {
    const cards = document.querySelectorAll('.trade-card');
    let visible = 0;
    cards.forEach(c => { if (c.getBoundingClientRect().top < window.innerHeight) visible++; });
    document.getElementById('nav-info').textContent = '已查看 ' + visible + '/' + cards.length;
});
</script>
</body>
</html>
""")

    # 保存HTML
    output_path = 'results/charts/全部交易走势图.html'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(html_parts))

    file_size = os.path.getsize(output_path) / 1024 / 1024
    print(f"\n完成！共生成 {len(round_trips)} 张交易走势图")
    print(f"输出文件: {output_path}")
    print(f"文件大小: {file_size:.1f} MB")


if __name__ == '__main__':
    main()
