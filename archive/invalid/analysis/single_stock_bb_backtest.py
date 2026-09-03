#!/usr/bin/env python3
"""
单股纯BB策略回测：对每只股票单独回测，不考虑选股，纯看BB下轨均值回归效果。
策略逻辑：收盘跌破BB下轨买入，盘中High达到成本×(1+止盈)卖出，支持多层加仓。
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from engine.commission import FeeCalculator
from engine.trading_rules import TradingRules
from engine.position import PositionManager
from config.loader import load_config


def backtest_single_stock(ts_code: str, name: str, df: pd.DataFrame,
                          bb_period=20, bb_std=2.0, tp_ratio=0.05,
                          max_levels=2, level_ratio=0.2, initial_cash=1000000):
    """
    对单只股票进行纯BB策略回测。

    Args:
        ts_code: 股票代码
        name: 股票名称
        df: 日线数据（含date, open, high, low, close, vol, amount）
        bb_period: 布林带周期
        bb_std: 布林带标准差倍数
        tp_ratio: 止盈比例
        max_levels: 最大加仓层数
        level_ratio: 每层仓位比例
        initial_cash: 初始资金

    Returns:
        回测结果字典
    """
    if df.empty or len(df) < bb_period + 10:
        return None

    df = df.sort_values('date').reset_index(drop=True).copy()

    # 计算布林带
    df['middle'] = df['close'].rolling(window=bb_period).mean()
    df['std'] = df['close'].rolling(window=bb_period).std()
    df['upper'] = df['middle'] + bb_std * df['std']
    df['lower'] = df['middle'] - bb_std * df['std']

    # 初始化
    cash = initial_cash
    fee_config = {
        'commission': {'rate': 0.00025, 'min': 5},
        'stamp_tax': {'rate': 0.0005},
        'transfer_fee': {'rate': 0.00001},
        'slippage': {'mode': 'percent', 'value': 0.0001},
    }
    commission_calc = FeeCalculator.from_config_dict(fee_config)
    trading_rules = TradingRules(min_listing_days=60, exclude_st=True, exclude_bse=True)
    position_mgr = PositionManager(max_levels=max_levels, level_ratio=level_ratio,
                                    take_profit_ratio=tp_ratio)

    trades = []
    daily_nav = []

    for i in range(bb_period, len(df)):
        row = df.iloc[i]
        current_date = row['date']
        close = row['close']
        high = row['high']
        low = row['low']
        lower = row['lower']

        if pd.isna(lower):
            continue

        # 1. 检查止盈
        if position_mgr.has_position:
            avg_cost = position_mgr.current_position.average_cost
            tp_price = avg_cost * (1 + tp_ratio)
            sellable = position_mgr.get_sellable_shares(current_date)

            if high >= tp_price and sellable > 0:
                # 止盈卖出
                fee_result = commission_calc.calculate_sell(tp_price, sellable)
                result = position_mgr.sell_all(current_date, fee_result.price, fee_result.total_fee)
                cash += fee_result.net_cash_flow
                trades.append({
                    'date': current_date, 'symbol': ts_code, 'action': 'SELL',
                    'price': tp_price, 'shares': sellable, 'reason': 'TAKE_PROFIT',
                })

        # 2. 检查买入/加仓
        if close < lower:
            if not position_mgr.has_position:
                # 开仓
                target_cash = initial_cash * level_ratio
                est_fee = commission_calc.calculate_buy(close, 100).total_fee
                available = min(cash, target_cash) - est_fee
                shares = trading_rules.calculate_shares(available, close)
                if shares >= 100:
                    fee_result = commission_calc.calculate_buy(close, shares)
                    position_mgr.open_position(ts_code, name, current_date, shares, fee_result.price, fee_result.total_fee)
                    cash -= fee_result.amount + fee_result.total_fee
                    trades.append({
                        'date': current_date, 'symbol': ts_code, 'action': 'BUY',
                        'price': close, 'shares': shares, 'reason': 'INITIAL_ENTRY',
                        'level': 1,
                    })
            elif not position_mgr.current_position.is_full:
                # 加仓
                target_cash = initial_cash * level_ratio
                est_fee = commission_calc.calculate_buy(close, 100).total_fee
                available = min(cash, target_cash) - est_fee
                shares = trading_rules.calculate_shares(available, close)
                if shares >= 100:
                    fee_result = commission_calc.calculate_buy(close, shares)
                    position_mgr.add_to_position(current_date, shares, fee_result.price, fee_result.total_fee)
                    cash -= fee_result.amount + fee_result.total_fee
                    trades.append({
                        'date': current_date, 'symbol': ts_code, 'action': 'BUY',
                        'price': close, 'shares': shares, 'reason': 'ADD_POSITION',
                        'level': position_mgr.current_position.current_level,
                    })

        # 3. 记录净值
        if position_mgr.has_position:
            market_value = close * position_mgr.current_position.total_shares
        else:
            market_value = 0
        total_equity = cash + market_value
        daily_nav.append({'date': current_date, 'total_equity': total_equity})

    # 计算结果
    if not daily_nav:
        return None

    final_equity = daily_nav[-1]['total_equity']
    total_return = (final_equity - initial_cash) / initial_cash * 100

    # 最大回撤
    nav_series = pd.Series([d['total_equity'] for d in daily_nav])
    peak = nav_series.cummax()
    drawdown = (nav_series - peak) / peak * 100
    max_drawdown = drawdown.min()

    # 交易统计
    buy_trades = [t for t in trades if t['action'] == 'BUY']
    sell_trades = [t for t in trades if t['action'] == 'SELL']

    # 构建完整交易对
    round_trips = []
    current_buys = []
    for t in trades:
        if t['action'] == 'BUY':
            current_buys.append(t)
        elif t['action'] == 'SELL' and current_buys:
            total_cost = sum(b['price'] * b['shares'] for b in current_buys)
            total_shares = sum(b['shares'] for b in current_buys)
            avg_cost = total_cost / total_shares if total_shares > 0 else 0
            sell_amount = t['price'] * t['shares']
            pnl = sell_amount - total_cost
            pnl_pct = pnl / total_cost * 100 if total_cost > 0 else 0
            round_trips.append({
                'entry': current_buys[0]['date'],
                'exit': t['date'],
                'levels': len(current_buys),
                'avg_cost': avg_cost,
                'sell_price': t['price'],
                'pnl': pnl,
                'pnl_pct': pnl_pct,
            })
            current_buys = []

    wins = [rt for rt in round_trips if rt['pnl'] > 0]
    losses = [rt for rt in round_trips if rt['pnl'] <= 0]
    win_rate = len(wins) / len(round_trips) * 100 if round_trips else 0
    avg_pnl = np.mean([rt['pnl_pct'] for rt in round_trips]) if round_trips else 0

    return {
        'ts_code': ts_code,
        'name': name,
        'total_return': round(total_return, 2),
        'final_equity': round(final_equity, 0),
        'max_drawdown': round(max_drawdown, 2),
        'total_trades': len(round_trips),
        'buy_count': len(buy_trades),
        'sell_count': len(sell_trades),
        'win_rate': round(win_rate, 1),
        'avg_pnl_pct': round(avg_pnl, 2),
        'wins': len(wins),
        'losses': len(losses),
        'round_trips': round_trips,
    }


def main():
    config = load_config()

    # 获取策略交易过的股票列表
    trades_path = 'results/trades/trades_20260826_011422.csv'
    trades = pd.read_csv(trades_path)
    stock_codes = sorted(trades['symbol'].unique())

    stock_basic = pd.read_parquet('data/raw/stock_basic.parquet')
    name_map = dict(zip(stock_basic['ts_code'], stock_basic['name']))

    print(f"将对 {len(stock_codes)} 只股票进行纯BB策略回测")
    print(f"参数: BB({20},{2.0}) + 止盈5% + 最多2层(每层20%) + 不止损")
    print("=" * 100)

    results = []
    for i, ts_code in enumerate(stock_codes):
        name = name_map.get(ts_code, ts_code)
        filepath = os.path.join('data', 'raw', 'daily', f'{ts_code}.parquet')
        if not os.path.exists(filepath):
            print(f"[{i+1}/{len(stock_codes)}] {ts_code} {name}: 无数据，跳过")
            continue

        df = pd.read_parquet(filepath)
        df['date'] = pd.to_datetime(df['date'])
        df = df[(df['date'] >= '2020-01-01') & (df['date'] <= '2026-08-25')]

        result = backtest_single_stock(ts_code, name, df, bb_period=20, bb_std=2.0,
                                         tp_ratio=0.05, max_levels=2, level_ratio=0.2)
        if result:
            results.append(result)
            print(f"[{i+1}/{len(stock_codes)}] {ts_code} {name}: "
                  f"累计{result['total_return']:+.2f}% 回撤{result['max_drawdown']:.2f}% "
                  f"胜率{result['win_rate']:.1f}% 交易{result['total_trades']}笔")
        else:
            print(f"[{i+1}/{len(stock_codes)}] {ts_code} {name}: 数据不足，跳过")

    # 汇总
    print("\n" + "=" * 100)
    print("汇总统计")
    print("=" * 100)

    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values('total_return', ascending=False)

    profitable = len(df_results[df_results['total_return'] > 0])
    total = len(df_results)
    avg_return = df_results['total_return'].mean()
    median_return = df_results['total_return'].median()
    avg_drawdown = df_results['max_drawdown'].mean()
    avg_win_rate = df_results['win_rate'].mean()
    total_trades = df_results['total_trades'].sum()

    print(f"回测股票数: {total}")
    print(f"盈利股票数: {profitable} ({profitable/total*100:.1f}%)")
    print(f"亏损股票数: {total - profitable} ({(total-profitable)/total*100:.1f}%)")
    print(f"平均累计收益: {avg_return:+.2f}%")
    print(f"中位数累计收益: {median_return:+.2f}%")
    print(f"平均最大回撤: {avg_drawdown:.2f}%")
    print(f"平均胜率: {avg_win_rate:.1f}%")
    print(f"总交易笔数: {total_trades}")

    print("\n" + "=" * 100)
    print("盈利TOP10")
    print("=" * 100)
    print(f"{'排名':>4} {'代码':<12} {'名称':<10} {'累计收益':>10} {'最大回撤':>10} {'胜率':>8} {'交易数':>6}")
    print("-" * 70)
    for i, (_, r) in enumerate(df_results.head(10).iterrows(), 1):
        print(f"{i:>4} {r['ts_code']:<12} {r['name']:<10} {r['total_return']:>+9.2f}% "
              f"{r['max_drawdown']:>9.2f}% {r['win_rate']:>7.1f}% {r['total_trades']:>6d}")

    print("\n" + "=" * 100)
    print("亏损TOP10")
    print("=" * 100)
    print(f"{'排名':>4} {'代码':<12} {'名称':<10} {'累计收益':>10} {'最大回撤':>10} {'胜率':>8} {'交易数':>6}")
    print("-" * 70)
    for i, (_, r) in enumerate(df_results.tail(10).iloc[::-1].iterrows(), 1):
        print(f"{i:>4} {r['ts_code']:<12} {r['name']:<10} {r['total_return']:>+9.2f}% "
              f"{r['max_drawdown']:>9.2f}% {r['win_rate']:>7.1f}% {r['total_trades']:>6d}")

    # 保存
    df_results.to_csv('results/single_stock_bb_backtest.csv', index=False)
    print(f"\n详细结果已保存: results/single_stock_bb_backtest.csv")


if __name__ == '__main__':
    main()
