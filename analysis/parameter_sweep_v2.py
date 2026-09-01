#!/usr/bin/env python3
"""简化版参数扫描：只跑4组最关键的参数组合。"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import time
from strategy.bb_turnover_top1 import BBTurnoverTop1Strategy
from data_loader.storage import DataStorage
from config.loader import load_config
from analysis.performance import PerformanceAnalyzer


def run_single(config, storage, tp_ratio, sl_mode, sl_ratio, max_levels,
               start_date='2020-01-01', end_date='2026-08-25'):
    config['strategy']['take_profit']['ratio'] = tp_ratio
    config['strategy']['stop_loss']['mode'] = sl_mode
    config['strategy']['stop_loss']['fixed_percent']['ratio'] = sl_ratio
    config['strategy']['position']['max_levels'] = max_levels

    strategy = BBTurnoverTop1Strategy(config, storage)
    result = strategy.run(start_date=start_date, end_date=end_date)

    analyzer = PerformanceAnalyzer(result['trades'], result['daily_nav'], initial_cash=1000000)
    metrics = analyzer.calc_all()

    return {
        'tp_ratio': tp_ratio,
        'sl_mode': sl_mode,
        'sl_ratio': sl_ratio,
        'max_levels': max_levels,
        'total_return': metrics['total_return'],
        'annual_return': metrics['annual_return'],
        'max_drawdown': metrics['max_drawdown'],
        'sharpe': metrics['sharpe_ratio'],
        'win_rate': metrics['win_rate'],
        'total_round_trips': metrics['total_round_trips'],
        'profit_factor': metrics['profit_factor'],
        'final_equity': metrics['final_equity'],
    }


def main():
    config = load_config()
    raw_dir = os.path.join(os.getcwd(), 'data', 'raw')
    storage = DataStorage(raw_dir)

    # 4组最关键的参数（基于复盘发现：大止盈+少加仓+不止损可能最优）
    param_sets = [
        {'tp_ratio': 0.03, 'sl_mode': 'disabled', 'sl_ratio': 0, 'max_levels': 2,
         'label': 'TP3% 不止损 2层'},
        {'tp_ratio': 0.05, 'sl_mode': 'disabled', 'sl_ratio': 0, 'max_levels': 2,
         'label': 'TP5% 不止损 2层'},
        {'tp_ratio': 0.03, 'sl_mode': 'fixed_percent', 'sl_ratio': 0.10, 'max_levels': 2,
         'label': 'TP3% SL10% 2层'},
        {'tp_ratio': 0.05, 'sl_mode': 'fixed_percent', 'sl_ratio': 0.10, 'max_levels': 2,
         'label': 'TP5% SL10% 2层'},
    ]

    results = []
    # 加入基准
    print("[基准] TP1.5% SL10% 5层 (已知: 累计-45.44%)")

    for i, params in enumerate(param_sets):
        label = params.pop('label')
        print(f"\n[{i+1}/4] {label}")
        start_time = time.time()

        try:
            result = run_single(config, storage, **params)
            result['label'] = label
            results.append(result)
            elapsed = time.time() - start_time
            print(f"  累计: {result['total_return']:>7.2f}% | 年化: {result['annual_return']:>7.2f}% | "
                  f"回撤: {result['max_drawdown']:>7.2f}% | Sharpe: {result['sharpe']:>6.3f} | "
                  f"胜率: {result['win_rate']:>5.1f}% | 交易: {result['total_round_trips']:>4d} | "
                  f"耗时: {elapsed:.0f}s")
        except Exception as e:
            print(f"  错误: {e}")
            import traceback
            traceback.print_exc()

    # 保存
    df = pd.DataFrame(results)
    df.to_csv('results/parameter_sweep_v2.csv', index=False)
    print(f"\n结果已保存: results/parameter_sweep_v2.csv")

    # 排名
    print("\n" + "=" * 90)
    print("参数组合排名（按累计收益率）")
    print("=" * 90)
    print(f"{'组合':<22s} | {'累计收益':>8s} | {'年化':>8s} | {'最大回撤':>8s} | {'Sharpe':>7s} | {'胜率':>6s} | {'交易数':>6s}")
    print("-" * 90)
    print(f"{'基准: TP1.5% SL10% 5层':<22s} | {'-45.44%':>8s} | {'-9.04%':>8s} | {'-69.66%':>8s} | {'-0.206':>7s} | {'89.9%':>6s} | {'178':>6s}")
    for _, row in df.sort_values('total_return', ascending=False).iterrows():
        print(f"{row['label']:<22s} | {row['total_return']:>7.2f}% | {row['annual_return']:>7.2f}% | "
              f"{row['max_drawdown']:>7.2f}% | {row['sharpe']:>7.3f} | {row['win_rate']:>5.1f}% | "
              f"{row['total_round_trips']:>6d}")


if __name__ == '__main__':
    main()
