#!/usr/bin/env python3
"""时间止损回测：测试5天/7天/10天/14天时间止损的效果。"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from strategy.bb_turnover_top1 import BBTurnoverTop1Strategy
from data_loader.storage import DataStorage
from config.loader import load_config
from analysis.performance import PerformanceAnalyzer


def run_single(config, storage, time_stop_days=0, tp_ratio=0.015, sl_mode='fixed_percent',
               sl_ratio=0.10, max_levels=5, level_ratio=0.2):
    """运行单次回测。"""
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
    return metrics


def main():
    config = load_config()
    raw_dir = os.path.join(os.getcwd(), 'data', 'raw')
    storage = DataStorage(raw_dir)

    results = []

    # 第一组：基准参数 + 时间止损（TP1.5% SL10% 5层）
    print("=" * 80)
    print("第一组：基准参数 + 时间止损（TP1.5% SL10% 5层）")
    print("=" * 80)

    for days in [0, 5, 7, 10, 14, 20]:
        label = f"{days}天" if days > 0 else "无时间止损"
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

    # 第二组：优化参数 + 时间止损（TP5% 不止损 2层）
    print("\n" + "=" * 80)
    print("第二组：优化参数 + 时间止损（TP5% 不止损 2层）")
    print("=" * 80)

    for days in [0, 5, 7, 10, 14, 20]:
        label = f"{days}天" if days > 0 else "无时间止损"
        print(f"\n运行 {label}...", flush=True)
        m = run_single(config, storage, time_stop_days=days, tp_ratio=0.05,
                        sl_mode='disabled', sl_ratio=0, max_levels=2, level_ratio=0.2)
        results.append({
            'group': '优化+时间止损', 'time_stop': label, 'tp': '5%', 'sl': 'disabled',
            'levels': 2,
            'total_return': m['total_return'], 'annual_return': m['annual_return'],
            'max_drawdown': m['max_drawdown'], 'sharpe': m['sharpe_ratio'],
            'win_rate': m['win_rate'], 'trades': m['total_round_trips'],
            'time_stop_triggers': m['time_stop_triggers'],
            'final_equity': m['final_equity'],
        })
        print(f"  {label}: 累计{m['total_return']:+.2f}% 回撤{m['max_drawdown']:.2f}% "
              f"Sharpe{m['sharpe_ratio']:.3f} 胜率{m['win_rate']:.1f}% "
              f"交易{m['total_round_trips']}笔 时间止损触发{m['time_stop_triggers']}次", flush=True)

    # 保存
    df = pd.DataFrame(results)
    df.to_csv('results/time_stop_sweep.csv', index=False)

    # 打印汇总
    print("\n" + "=" * 110)
    print("汇总结果")
    print("=" * 110)
    print(f"{'组别':<14} {'时间止损':>8} {'止盈':>5} {'止损':>8} {'层数':>4} "
          f"{'累计收益':>8} {'年化':>8} {'最大回撤':>8} {'Sharpe':>7} {'胜率':>6} {'交易数':>6} {'时间止损':>8}")
    print("-" * 110)
    for _, r in df.iterrows():
        print(f"{r['group']:<14} {r['time_stop']:>8} {r['tp']:>5} {r['sl']:>8} "
              f"{r['levels']:>4} {r['total_return']:>+7.2f}% {r['annual_return']:>+7.2f}% "
              f"{r['max_drawdown']:>7.2f}% {r['sharpe']:>7.3f} "
              f"{r['win_rate']:>5.1f}% {r['trades']:>6d} {r['time_stop_triggers']:>8d}")

    print(f"\n结果已保存: results/time_stop_sweep.csv")


if __name__ == '__main__':
    main()
