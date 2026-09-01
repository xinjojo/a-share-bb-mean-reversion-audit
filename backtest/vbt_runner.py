#!/usr/bin/env python3
"""
VectorBT回测执行器：把订单列表转换成VectorBT格式，执行回测和分析。
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import vectorbt as vbt
from strategy.vbt_order_generator import VBTOrderGenerator
from data_loader.storage import DataStorage
from config.loader import load_config


class VBTBacktestRunner:
    """VectorBT回测执行器。"""

    def __init__(self, config: dict, storage: DataStorage):
        self.config = config
        self.storage = storage

    def run(self, start_date: str = None, end_date: str = None) -> dict:
        """
        运行回测。

        Returns:
            回测结果字典，包含portfolio, orders, metrics
        """
        # 1. 生成订单
        generator = VBTOrderGenerator(self.config, self.storage)
        orders = generator.generate(start_date, end_date)

        if not orders:
            return {'portfolio': None, 'orders': [], 'metrics': {}}

        # 2. 转换成VectorBT格式
        orders_df = pd.DataFrame(orders)
        orders_df['date'] = pd.to_datetime(orders_df['date'])

        # 获取所有涉及的股票和日期范围
        symbols = sorted(orders_df['symbol'].unique())
        all_dates = pd.date_range(
            start=orders_df['date'].min(),
            end=orders_df['date'].max(),
            freq='D'
        )

        # 3. 获取收盘价（用于估值和默认成交价）
        close = pd.DataFrame(np.nan, index=all_dates, columns=symbols, dtype=float)
        for symbol in symbols:
            daily = self.storage.load_daily(symbol)
            if not daily.empty:
                daily = daily.set_index('date')
                close[symbol] = daily['close'].reindex(all_dates)

        # 前向填充收盘价（停牌时用前一日收盘价估值）
        close = close.ffill()
        # 后向填充（开头的NaN）
        close = close.bfill()
        # 确保没有NaN
        close = close.fillna(1.0)

        # 构建size和price DataFrame
        size = pd.DataFrame(0, index=all_dates, columns=symbols, dtype=float)
        price = close.copy()  # 默认用收盘价，有订单时覆盖

        for _, order in orders_df.iterrows():
            d = order['date']
            s = order['symbol']
            size.loc[d, s] = order['size']
            price.loc[d, s] = order['price']

        # 4. 用VectorBT执行回测
        # 注意：订单价格已包含所有费用（佣金+印花税+过户费+滑点），所以fees设为0
        portfolio = vbt.Portfolio.from_orders(
            close=close,
            size=size,
            price=price,
            fees=0.0,  # 费用已包含在订单价格中
            fixed_fees=0.0,
            slippage=0.0,  # 滑点已包含在订单价格中
            min_size=100,
            init_cash=self.config['backtest']['initial_cash'],
            cash_sharing=True,
            freq='D',
        )

        # 5. 计算性能指标
        metrics = self._calculate_metrics(portfolio)

        return {
            'portfolio': portfolio,
            'orders': orders,
            'metrics': metrics,
            'orders_df': orders_df,
        }

    def _calculate_metrics(self, portfolio) -> dict:
        """计算性能指标。"""
        try:
            total_return = portfolio.total_return() * 100
        except:
            total_return = 0

        try:
            annual_return = portfolio.annualized_return() * 100
        except:
            annual_return = 0

        try:
            max_drawdown = portfolio.max_drawdown() * 100
        except:
            max_drawdown = 0

        try:
            sharpe = portfolio.sharpe_ratio()
        except:
            sharpe = 0

        try:
            sortino = portfolio.sortino_ratio()
        except:
            sortino = 0

        try:
            calmar = portfolio.calmar_ratio()
        except:
            calmar = 0

        try:
            volatility = portfolio.annualized_volatility() * 100
        except:
            volatility = 0

        try:
            trades = portfolio.trades
            total_trades = trades.count()
            win_rate = trades.win_rate() * 100 if total_trades > 0 else 0
            avg_win = trades.avg_win() * 100 if total_trades > 0 else 0
            avg_loss = trades.avg_loss() * 100 if total_trades > 0 else 0
            profit_factor = trades.profit_factor() if total_trades > 0 else 0
        except:
            total_trades = 0
            win_rate = 0
            avg_win = 0
            avg_loss = 0
            profit_factor = 0

        try:
            final_equity = portfolio.value().iloc[-1]
        except:
            final_equity = 0

        return {
            'total_return': round(total_return, 2),
            'annual_return': round(annual_return, 2),
            'max_drawdown': round(max_drawdown, 2),
            'sharpe_ratio': round(sharpe, 3),
            'sortino_ratio': round(sortino, 3),
            'calmar_ratio': round(calmar, 3),
            'annual_volatility': round(volatility, 2),
            'total_round_trips': total_trades,
            'win_rate': round(win_rate, 1),
            'avg_win_pct': round(avg_win, 2),
            'avg_loss_pct': round(avg_loss, 2),
            'profit_factor': round(profit_factor, 3),
            'final_equity': round(final_equity, 0),
        }


def main():
    """运行基准参数回测，验证结果。"""
    config = load_config()
    raw_dir = os.path.join(os.getcwd(), 'data', 'raw')
    storage = DataStorage(raw_dir)

    # 基准参数
    config['strategy']['top_n'] = 1
    config['strategy']['take_profit']['ratio'] = 0.015
    config['strategy']['stop_loss']['mode'] = 'fixed_percent'
    config['strategy']['stop_loss']['fixed_percent']['ratio'] = 0.10
    config['strategy']['position']['max_levels'] = 5
    config['strategy']['position']['level_ratio'] = 0.2
    config['strategy']['time_stop_days'] = 0

    print("=" * 80)
    print("VectorBT回测验证 - 基准参数（TP1.5% SL10% 5层）")
    print("=" * 80)

    runner = VBTBacktestRunner(config, storage)
    result = runner.run(start_date='2020-01-01', end_date='2024-12-31')

    print(f"\n订单数: {len(result['orders'])}")
    print(f"\n性能指标:")
    for k, v in result['metrics'].items():
        print(f"  {k}: {v}")

    # 对比自建引擎结果
    print("\n" + "=" * 80)
    print("对比自建引擎结果")
    print("=" * 80)
    print(f"{'指标':<20} {'VectorBT':>12} {'自建引擎':>12} {'差异':>12}")
    print("-" * 60)

    # 自建引擎基准结果（止盈后不重新买入，2020-2024）
    engine_results = {
        'total_return': -45.18,
        'annual_return': -9.0,
        'max_drawdown': -69.66,
        'total_round_trips': 146,
        'win_rate': 89.7,
        'final_equity': 548181,
    }

    for k in ['total_return', 'annual_return', 'max_drawdown', 'total_round_trips', 'win_rate', 'final_equity']:
        vbt_val = result['metrics'].get(k, 0)
        eng_val = engine_results.get(k, 0)
        diff = vbt_val - eng_val
        print(f"{k:<20} {vbt_val:>12.2f} {eng_val:>12.2f} {diff:>12.2f}")

    # 保存订单
    orders_df = result['orders_df']
    orders_df.to_csv('results/vbt_orders_baseline.csv', index=False)
    print(f"\n订单已保存: results/vbt_orders_baseline.csv")


if __name__ == '__main__':
    main()
