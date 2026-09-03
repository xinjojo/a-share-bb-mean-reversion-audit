#!/usr/bin/env python3
"""生成带买卖点标注和布林带的交互式K线图。"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def load_stock_data(ts_code: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """加载股票日线数据。"""
    filepath = os.path.join('data', 'raw', 'daily', f'{ts_code}.parquet')
    df = pd.read_parquet(filepath)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)

    if start_date:
        df = df[df['date'] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df['date'] <= pd.to_datetime(end_date)]

    return df


def calculate_bollinger(df: pd.DataFrame, period: int = 20, std_mult: float = 2.0) -> pd.DataFrame:
    """计算布林带。"""
    df = df.copy()
    df['middle'] = df['close'].rolling(window=period).mean()
    df['std'] = df['close'].rolling(window=period).std()
    df['upper'] = df['middle'] + std_mult * df['std']
    df['lower'] = df['middle'] - std_mult * df['std']
    return df


def load_trades(ts_code: str) -> pd.DataFrame:
    """加载策略交易记录。"""
    trades_path = 'results/trades/trades_20260826_011422.csv'
    trades = pd.read_csv(trades_path)
    trades['date'] = pd.to_datetime(trades['date'])
    stock_trades = trades[trades['symbol'] == ts_code].sort_values('date').reset_index(drop=True)
    return stock_trades


def plot_candlestick(ts_code: str, stock_name: str, output_path: str):
    """生成带买卖点和布林带的K线图。"""
    # 加载数据
    df = load_stock_data(ts_code, start_date='2020-01-01', end_date='2026-08-25')
    df = calculate_bollinger(df, period=20, std_mult=2.0)
    trades = load_trades(ts_code)

    print(f"股票: {stock_name} ({ts_code})")
    print(f"K线数据: {len(df)} 天")
    print(f"交易记录: {len(trades)} 笔")

    # 创建子图：K线 + 成交量
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_width=[0.2, 0.8],
        subplot_titles=(f'{stock_name} ({ts_code}) K线图 + 布林带(20,2) + 策略买卖点', '成交量')
    )

    # K线图
    fig.add_trace(go.Candlestick(
        x=df['date'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        name='K线',
        increasing_line_color='#ff4d4f',
        decreasing_line_color='#52c41a',
        increasing_fillcolor='#ff4d4f',
        decreasing_fillcolor='#52c41a',
    ), row=1, col=1)

    # 布林带
    fig.add_trace(go.Scatter(
        x=df['date'], y=df['upper'],
        name='上轨', line=dict(color='orange', width=1),
        opacity=0.6
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df['date'], y=df['middle'],
        name='中轨(MA20)', line=dict(color='blue', width=1),
        opacity=0.6
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df['date'], y=df['lower'],
        name='下轨', line=dict(color='orange', width=1),
        opacity=0.6,
        fill='tonexty',
        fillcolor='rgba(255, 165, 0, 0.1)'
    ), row=1, col=1)

    # 标注买卖点
    buy_trades = trades[trades['action'] == 'BUY']
    sell_trades = trades[trades['action'] == 'SELL']

    # 买入点
    if not buy_trades.empty:
        fig.add_trace(go.Scatter(
            x=buy_trades['date'],
            y=buy_trades['price'],
            mode='markers+text',
            name='买入',
            marker=dict(symbol='triangle-up', size=12, color='red'),
            text=[f"买{row['position_level']}层" for _, row in buy_trades.iterrows()],
            textposition='top center',
            textfont=dict(size=9, color='red'),
        ), row=1, col=1)

    # 卖出点
    if not sell_trades.empty:
        fig.add_trace(go.Scatter(
            x=sell_trades['date'],
            y=sell_trades['price'],
            mode='markers+text',
            name='卖出',
            marker=dict(symbol='triangle-down', size=12, color='green'),
            text=[f"卖({row['reason']})" for _, row in sell_trades.iterrows()],
            textposition='bottom center',
            textfont=dict(size=9, color='green'),
        ), row=1, col=1)

    # 成交量
    colors = ['#ff4d4f' if row['close'] >= row['open'] else '#52c41a' for _, row in df.iterrows()]
    fig.add_trace(go.Bar(
        x=df['date'],
        y=df['vol'],
        name='成交量',
        marker_color=colors,
        opacity=0.7
    ), row=2, col=1)

    # 布局
    fig.update_layout(
        title=dict(
            text=f'{stock_name} ({ts_code}) 策略交易复盘 — 2020~2026',
            font=dict(size=16)
        ),
        xaxis_rangeslider_visible=False,
        xaxis2_rangeslider_visible=False,
        height=900,
        hovermode='x unified',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        template='plotly_white'
    )

    fig.update_xaxes(type='category', nticks=20)
    fig.update_yaxes(title_text='价格 (元)', row=1, col=1)
    fig.update_yaxes(title_text='成交量', row=2, col=1)

    # 保存
    fig.write_html(output_path, include_plotlyjs='cdn')
    print(f"K线图已保存: {output_path}")

    # 打印交易复盘
    print(f"\n{'='*70}")
    print(f"策略交易复盘 ({stock_name})")
    print(f"{'='*70}")

    # 构建完整交易对
    round_trips = []
    current_buys = []
    for _, trade in trades.iterrows():
        if trade['action'] == 'BUY':
            current_buys.append(trade)
        elif trade['action'] == 'SELL':
            if current_buys:
                total_cost = sum(b['amount'] + b['commission'] + b['transfer_fee'] for b in current_buys)
                total_shares = sum(b['shares'] for b in current_buys)
                avg_cost = total_cost / total_shares if total_shares > 0 else 0
                sell_amount = trade['amount'] - trade['commission'] - trade['stamp_tax'] - trade['transfer_fee']
                pnl = sell_amount - total_cost
                pnl_pct = pnl / total_cost * 100 if total_cost > 0 else 0

                round_trips.append({
                    'entry': current_buys[0]['date'],
                    'exit': trade['date'],
                    'levels': len(current_buys),
                    'avg_cost': avg_cost,
                    'sell_price': trade['price'],
                    'pnl': pnl,
                    'pnl_pct': pnl_pct,
                    'reason': trade['reason'],
                })
                current_buys = []

    for i, rt in enumerate(round_trips, 1):
        print(f"\n第{i}轮交易:")
        print(f"  买入: {rt['entry'].date()} (共{rt['levels']}层加仓)")
        print(f"  卖出: {rt['exit'].date()} ({rt['reason']})")
        print(f"  平均成本: {rt['avg_cost']:.3f}")
        print(f"  卖出价格: {rt['sell_price']:.3f}")
        print(f"  盈亏: {rt['pnl']:+,.0f} 元 ({rt['pnl_pct']:+.2f}%)")

    total_pnl = sum(rt['pnl'] for rt in round_trips)
    print(f"\n{'='*70}")
    print(f"合计: {len(round_trips)}轮交易, 总盈亏: {total_pnl:+,.0f} 元")
    print(f"{'='*70}")


if __name__ == '__main__':
    plot_candlestick('601318.SH', '中国平安', 'results/charts/中国平安_K线图_策略复盘.html')
