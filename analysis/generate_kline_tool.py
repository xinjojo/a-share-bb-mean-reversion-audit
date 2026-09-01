#!/usr/bin/env python3
"""生成交互式K线图工具（类似TradingView），支持股票代码切换、买卖点标注、交易复盘。"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import json


def load_all_traded_stocks():
    """加载策略交易过的所有股票的K线数据和交易记录。"""
    trades_path = 'results/trades/trades_20260826_011422.csv'
    trades = pd.read_csv(trades_path)
    trades['date'] = pd.to_datetime(trades['date'])

    stock_basic = pd.read_parquet('data/raw/stock_basic.parquet')
    name_map = dict(zip(stock_basic['ts_code'], stock_basic['name']))

    stocks_data = {}
    stock_list = []

    for ts_code in sorted(trades['symbol'].unique()):
        filepath = os.path.join('data', 'raw', 'daily', f'{ts_code}.parquet')
        if not os.path.exists(filepath):
            continue

        df = pd.read_parquet(filepath)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        df = df[(df['date'] >= '2020-01-01') & (df['date'] <= '2026-08-25')]

        if df.empty:
            continue

        # 计算布林带
        df['middle'] = df['close'].rolling(window=20).mean()
        df['std'] = df['close'].rolling(window=20).std()
        df['upper'] = df['middle'] + 2 * df['std']
        df['lower'] = df['middle'] - 2 * df['std']

        # 该股票的交易记录
        stock_trades = trades[trades['symbol'] == ts_code].sort_values('date')

        # 构建完整交易对
        round_trips = []
        current_buys = []
        for _, trade in stock_trades.iterrows():
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
                        'entry': current_buys[0]['date'].strftime('%Y-%m-%d'),
                        'exit': trade['date'].strftime('%Y-%m-%d'),
                        'levels': len(current_buys),
                        'avg_cost': round(avg_cost, 3),
                        'sell_price': round(trade['price'], 3),
                        'pnl': round(pnl, 0),
                        'pnl_pct': round(pnl_pct, 2),
                        'reason': trade['reason'],
                    })
                    current_buys = []

        # 转换为JSON友好格式
        kline_data = []
        for _, row in df.iterrows():
            kline_data.append({
                'date': row['date'].strftime('%Y-%m-%d'),
                'open': round(row['open'], 3),
                'high': round(row['high'], 3),
                'low': round(row['low'], 3),
                'close': round(row['close'], 3),
                'volume': int(row['vol']),
                'upper': round(row['upper'], 3) if pd.notna(row['upper']) else None,
                'middle': round(row['middle'], 3) if pd.notna(row['middle']) else None,
                'lower': round(row['lower'], 3) if pd.notna(row['lower']) else None,
            })

        buy_points = []
        sell_points = []
        for _, trade in stock_trades.iterrows():
            point = {
                'date': trade['date'].strftime('%Y-%m-%d'),
                'price': round(trade['price'], 3),
                'shares': int(trade['shares']),
                'level': int(trade['position_level']),
                'reason': trade['reason'],
            }
            if trade['action'] == 'BUY':
                buy_points.append(point)
            else:
                sell_points.append(point)

        name = name_map.get(ts_code, ts_code)
        stocks_data[ts_code] = {
            'name': name,
            'kline': kline_data,
            'buys': buy_points,
            'sells': sell_points,
            'round_trips': round_trips,
        }
        stock_list.append({'code': ts_code, 'name': name, 'trades': len(stock_trades)})

    return stocks_data, stock_list


def generate_html(stocks_data, stock_list, output_path):
    """生成HTML文件。"""
    stocks_json = json.dumps(stocks_data, ensure_ascii=False)
    stock_list_json = json.dumps(stock_list, ensure_ascii=False)

    html_template = open(os.path.join(os.path.dirname(__file__), 'kline_tool_template.html'), 'r', encoding='utf-8').read()
    html = html_template.replace('__STOCKS_DATA__', stocks_json).replace('__STOCK_LIST__', stock_list_json)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"交互式K线图工具已生成: {output_path}")
    print(f"包含 {len(stock_list)} 只股票的K线数据和交易记录")


if __name__ == '__main__':
    stocks_data, stock_list = load_all_traded_stocks()
    output_path = 'results/charts/策略交易复盘_K线图工具.html'
    generate_html(stocks_data, stock_list, output_path)
