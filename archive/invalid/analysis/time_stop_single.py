#!/usr/bin/env python3
"""单组时间止损回测，通过命令行参数指定天数。"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from strategy.bb_turnover_top1 import BBTurnoverTop1Strategy
from data_loader.storage import DataStorage
from config.loader import load_config
from analysis.performance import PerformanceAnalyzer


def main():
    if len(sys.argv) < 2:
        print("用法: python3 time_stop_single.py <days>")
        print("  days=0 表示无时间止损")
        sys.exit(1)

    days = int(sys.argv[1])
    label = f"{days}天" if days > 0 else "无时间止损"

    config = load_config()
    raw_dir = os.path.join(os.getcwd(), 'data', 'raw')
    storage = DataStorage(raw_dir)

    config['strategy']['time_stop_days'] = days
    config['strategy']['take_profit']['ratio'] = 0.015
    config['strategy']['stop_loss']['mode'] = 'fixed_percent'
    config['strategy']['stop_loss']['fixed_percent']['ratio'] = 0.10
    config['strategy']['position']['max_levels'] = 5
    config['strategy']['position']['level_ratio'] = 0.2

    print(f"运行 {label}...", flush=True)
    strategy = BBTurnoverTop1Strategy(config, storage)
    result = strategy.run(start_date='2020-01-01', end_date='2026-08-25')

    analyzer = PerformanceAnalyzer(result['trades'], result['daily_nav'], initial_cash=1000000)
    m = analyzer.calc_all()
    time_stop_triggers = strategy._stats.get('time_stop_triggers', 0)

    print(f"  {label}: 累计{m['total_return']:+.2f}% 回撤{m['max_drawdown']:.2f}% "
          f"Sharpe{m['sharpe_ratio']:.3f} 胜率{m['win_rate']:.1f}% "
          f"交易{m['total_round_trips']}笔 时间止损触发{time_stop_triggers}次", flush=True)

    # 保存结果
    result_file = 'results/time_stop_sweep.csv'
    new_row = {
        'time_stop': label,
        'days': days,
        'total_return': m['total_return'],
        'annual_return': m['annual_return'],
        'max_drawdown': m['max_drawdown'],
        'sharpe': m['sharpe_ratio'],
        'win_rate': m['win_rate'],
        'trades': m['total_round_trips'],
        'time_stop_triggers': time_stop_triggers,
        'final_equity': m['final_equity'],
    }

    if os.path.exists(result_file):
        df = pd.read_csv(result_file)
        df = df[df['days'] != days]  # 移除旧结果
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    else:
        df = pd.DataFrame([new_row])

    df = df.sort_values('days')
    df.to_csv(result_file, index=False)
    print(f"  结果已保存到 {result_file}", flush=True)


if __name__ == '__main__':
    main()
