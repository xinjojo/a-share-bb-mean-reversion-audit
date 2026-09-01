#!/usr/bin/env python3
"""时间止损回测（优化内存版）：每次回测后释放内存，只跑关键参数。"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gc
import pandas as pd
from strategy.bb_turnover_top1 import BBTurnoverTop1Strategy
from data_loader.storage import DataStorage
from config.loader import load_config
from analysis.performance import PerformanceAnalyzer


def run_single(config, storage, time_stop_days=0, tp_ratio=0.015, sl_mode='fixed_percent',
               sl_ratio=0.10, max_levels=5, level_ratio=0.2):
    """运行单次回测，完成后释放内存。"""
    config['strategy']['time_stop_days'] = time_stop_days
    config['strategy']['take_profit']['ratio'] = tp_ratio
    config['strategy']['stop_loss']['mode'] = sl_mode
    config['strategy']['stop_loss']['fixed_percent']['ratio'] = sl_ratio
    config['strategy']['position']['max_levels'] = max_levels
    config['strategy']['position']['level_ratio'] = level_ratio

    strategy = BBTurnoverTop1Strategy(config, storage)
    result = strategy.run(start_date='2020-01-01', end_date='2026-08-25')

    analyzer = PerformanceAnalyzer(result['trades'], result['daily_nav'], initial_cash=1000000)
    metrics = analyzer.calc_all()
    metrics['time_stop_triggers'] = strategy._stats.get('time_stop_triggers', 0)

    # 释放内存
    del strategy
    del analyzer
    del result
    gc.collect()

    return metrics


def main():
    config = load_config()
    raw_dir = os.path.join(os.getcwd(), 'data', 'raw')
    storage = DataStorage(raw_dir)

    results = []

    # 只跑最关键的几组：基准参数 + 5天/7天/10天时间止损
    print("=" * 80)
    print("时间止损回测（基准参数 TP1.5% SL10% 5层）")
    print("=" * 80)

    test_cases = [
        (0, '无时间止损'),
        (5, '5天时间止损'),
        (7, '7天时间止损'),
        (10, '10天时间止损'),
        (14, '14天时间止损'),
    ]

    for days, label in test_cases:
        print(f"\n运行 {label}...", flush=True)
        m = run_single(config, storage, time_stop_days=days, tp_ratio=0.015,
                        sl_mode='fixed_percent', sl_ratio=0.10, max_levels=5, level_ratio=0.2)
        results.append({
            'group': '基准+时间止损', 'time_stop': label, 'tp': '1.5%', 'sl': '10%',
            'levels': 5,
            'total_return': m['total_return'], 'annual_return': m['annual_return'],
            'max_drawdown': m['max_drawdown'], 'sharpe': m['sharpe_ratio'],
            'win_rate': m['win_rate'], 'trades': m['total_round_trips'],
            'time_stop_triggers': m['time_stop_triggers'],
            'final_equity': m['final_equity'],
        })
        print(f"  {label}: 累计{m['total_return']:+.2f}% 回撤{m['max_drawdown']:.2f}% "
              f"Sharpe{m['sharpe_ratio']:.3f} 胜率{m['win_rate']:.1f}% "
              f"交易{m['total_round_trips']}笔 时间止损触发{m['time_stop_triggers']}次", flush=True)

        # 保存中间结果
        df = pd.DataFrame(results)
        df.to_csv('results/time_stop_sweep.csv', index=False)

    # 打印汇总
    print("\n" + "=" * 110)
    print("汇总结果")
    print("=" * 110)
    print(f"{'时间止损':<12} {'累计收益':>8} {'年化':>8} {'最大回撤':>8} {'Sharpe':>7} "
          f"{'胜率':>6} {'交易数':>6} {'时间止损触发':>10}")
    print("-" * 80)
    for r in results:
        print(f"{r['time_stop']:<12} {r['total_return']:>+7.2f}% {r['annual_return']:>+7.2f}% "
              f"{r['max_drawdown']:>7.2f}% {r['sharpe']:>7.3f} "
              f"{r['win_rate']:>5.1f}% {r['trades']:>6d} {r['time_stop_triggers']:>10d}")

    print(f"\n结果已保存: results/time_stop_sweep.csv")


if __name__ == '__main__':
    main()
