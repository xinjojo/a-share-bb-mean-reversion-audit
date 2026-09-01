#!/usr/bin/env python3
"""
参数敏感性扫描：测试不同止盈/止损/加仓层数组合的效果。
基于止盈空间复盘的发现，重点测试更大的止盈比例和更少的加仓层数。
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import time
import json
from strategy.bb_turnover_top1 import BBTurnoverTop1Strategy
from data_loader.storage import DataStorage
from config.loader import load_config
from analysis.performance import PerformanceAnalyzer


def run_single_backtest(config, storage, tp_ratio, sl_mode, sl_ratio, max_levels,
                         start_date='2020-01-01', end_date='2026-08-25'):
    """运行单次回测，返回关键指标。"""
    # 修改配置
    config['strategy']['take_profit_ratio'] = tp_ratio
    config['strategy']['stop_loss']['mode'] = sl_mode
    config['strategy']['stop_loss']['fixed_percent'] = sl_ratio
    config['strategy']['max_position_levels'] = max_levels

    strategy = BBTurnoverTop1Strategy(config, storage)
    result = strategy.run(start_date=start_date, end_date=end_date)

    # 计算绩效
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
        'avg_profit': metrics['avg_profit'],
        'avg_loss': metrics['avg_loss'],
        'total_fees': metrics['total_fees'],
        'final_equity': metrics['final_equity'],
    }


def main():
    config = load_config()
    project_root = os.getcwd()
    raw_dir = os.path.join(project_root, 'data', 'raw')
    storage = DataStorage(raw_dir)

    # 参数组合（基于止盈空间复盘的发现）
    # 重点测试：更大的止盈比例 + 更少的加仓层数
    param_sets = [
        # 基准：当前参数
        {'tp_ratio': 0.015, 'sl_mode': 'fixed_percent', 'sl_ratio': 0.10, 'max_levels': 5, 'label': '基准: TP1.5% SL10% 5层'},
        # 更大的止盈
        {'tp_ratio': 0.02, 'sl_mode': 'fixed_percent', 'sl_ratio': 0.10, 'max_levels': 5, 'label': 'TP2% SL10% 5层'},
        {'tp_ratio': 0.03, 'sl_mode': 'fixed_percent', 'sl_ratio': 0.10, 'max_levels': 5, 'label': 'TP3% SL10% 5层'},
        {'tp_ratio': 0.05, 'sl_mode': 'fixed_percent', 'sl_ratio': 0.10, 'max_levels': 5, 'label': 'TP5% SL10% 5层'},
        # 不止损
        {'tp_ratio': 0.03, 'sl_mode': 'disabled', 'sl_ratio': 0, 'max_levels': 5, 'label': 'TP3% 不止损 5层'},
        {'tp_ratio': 0.05, 'sl_mode': 'disabled', 'sl_ratio': 0, 'max_levels': 5, 'label': 'TP5% 不止损 5层'},
        # 限制加仓到2层
        {'tp_ratio': 0.03, 'sl_mode': 'fixed_percent', 'sl_ratio': 0.10, 'max_levels': 2, 'label': 'TP3% SL10% 2层'},
        {'tp_ratio': 0.05, 'sl_mode': 'fixed_percent', 'sl_ratio': 0.10, 'max_levels': 2, 'label': 'TP5% SL10% 2层'},
        # 最优组合推测：大止盈 + 不止损 + 少加仓
        {'tp_ratio': 0.05, 'sl_mode': 'disabled', 'sl_ratio': 0, 'max_levels': 2, 'label': 'TP5% 不止损 2层'},
        {'tp_ratio': 0.03, 'sl_mode': 'disabled', 'sl_ratio': 0, 'max_levels': 2, 'label': 'TP3% 不止损 2层'},
    ]

    results = []
    total = len(param_sets)

    print(f"开始参数敏感性扫描，共 {total} 组参数")
    print("=" * 100)

    for i, params in enumerate(param_sets):
        label = params.pop('label')
        print(f"\n[{i+1}/{total}] {label}")
        start_time = time.time()

        try:
            result = run_single_backtest(config, storage, **params)
            result['label'] = label
            results.append(result)

            elapsed = time.time() - start_time
            print(f"  累计收益: {result['total_return']:>7.2f}% | "
                  f"年化: {result['annual_return']:>7.2f}% | "
                  f"最大回撤: {result['max_drawdown']:>7.2f}% | "
                  f"Sharpe: {result['sharpe']:>6.3f} | "
                  f"胜率: {result['win_rate']:>5.1f}% | "
                  f"交易数: {result['total_round_trips']:>4d} | "
                  f"耗时: {elapsed:.0f}s")
        except Exception as e:
            print(f"  错误: {e}")
            import traceback
            traceback.print_exc()

    # 保存结果
    df_results = pd.DataFrame(results)
    output_path = 'results/parameter_sweep.csv'
    df_results.to_csv(output_path, index=False)
    print(f"\n参数扫描结果已保存: {output_path}")

    # 打印排名
    print("\n" + "=" * 100)
    print("参数组合排名（按累计收益率）")
    print("=" * 100)
    df_sorted = df_results.sort_values('total_return', ascending=False)
    for idx, row in df_sorted.iterrows():
        print(f"  {row['label']:<25s} | 累计: {row['total_return']:>7.2f}% | "
              f"年化: {row['annual_return']:>7.2f}% | 回撤: {row['max_drawdown']:>7.2f}% | "
              f"Sharpe: {row['sharpe']:>6.3f} | 胜率: {row['win_rate']:>5.1f}%")

    return df_results


if __name__ == '__main__':
    main()
