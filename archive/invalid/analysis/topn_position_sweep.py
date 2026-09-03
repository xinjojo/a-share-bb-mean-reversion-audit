#!/usr/bin/env python3
"""Top N和动态仓位参数扫描。"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from strategy.bb_turnover_top1 import BBTurnoverTop1Strategy
from data_loader.storage import DataStorage
from config.loader import load_config
from analysis.performance import PerformanceAnalyzer


def run_single(config, storage, top_n=1, tp_ratio=0.05, sl_mode='disabled',
               sl_ratio=0, max_levels=2, level_ratio=0.2):
    """运行单次回测。"""
    config['strategy']['top_n'] = top_n
    config['strategy']['take_profit']['ratio'] = tp_ratio
    config['strategy']['stop_loss']['mode'] = sl_mode
    config['strategy']['stop_loss']['fixed_percent']['ratio'] = sl_ratio
    config['strategy']['position']['max_levels'] = max_levels
    config['strategy']['position']['level_ratio'] = level_ratio

    strategy = BBTurnoverTop1Strategy(config, storage)
    result = strategy.run(start_date='2020-01-01', end_date='2026-08-25')

    analyzer = PerformanceAnalyzer(result['trades'], result['daily_nav'], initial_cash=1000000)
    return analyzer.calc_all()


def main():
    config = load_config()
    raw_dir = os.path.join(os.getcwd(), 'data', 'raw')
    storage = DataStorage(raw_dir)

    results = []

    # ===== 第一组：Top N测试（固定TP5%+不止损+2层）=====
    print("=" * 80)
    print("第一组：Top N测试（TP5% + 不止损 + 2层）")
    print("=" * 80)
    for top_n in [1, 2, 3, 5]:
        print(f"\n运行 Top{top_n}...")
        m = run_single(config, storage, top_n=top_n, tp_ratio=0.05,
                        sl_mode='disabled', max_levels=2, level_ratio=0.2)
        results.append({
            'group': 'TopN', 'top_n': top_n, 'tp': '5%', 'sl': 'disabled',
            'levels': 2, 'level_ratio': '20%',
            'total_return': m['total_return'], 'annual_return': m['annual_return'],
            'max_drawdown': m['max_drawdown'], 'sharpe': m['sharpe_ratio'],
            'win_rate': m['win_rate'], 'trades': m['total_round_trips'],
            'final_equity': m['final_equity'],
        })
        print(f"  Top{top_n}: 累计{m['total_return']:+.2f}% 回撤{m['max_drawdown']:.2f}% "
              f"Sharpe{m['sharpe_ratio']:.3f} 胜率{m['win_rate']:.1f}% 交易{m['total_round_trips']}笔")

    # ===== 第二组：动态仓位测试（固定Top1+TP5%+不止损）=====
    print("\n" + "=" * 80)
    print("第二组：动态仓位测试（Top1 + TP5% + 不止损）")
    print("=" * 80)

    # 方案A: 2层×20%（基准）
    print("\n运行 2层×20%...")
    m = run_single(config, storage, top_n=1, tp_ratio=0.05,
                    sl_mode='disabled', max_levels=2, level_ratio=0.2)
    results.append({
        'group': '动态仓位', 'top_n': 1, 'tp': '5%', 'sl': 'disabled',
        'levels': 2, 'level_ratio': '20%',
        'total_return': m['total_return'], 'annual_return': m['annual_return'],
        'max_drawdown': m['max_drawdown'], 'sharpe': m['sharpe_ratio'],
        'win_rate': m['win_rate'], 'trades': m['total_round_trips'],
        'final_equity': m['final_equity'],
    })
    print(f"  2层×20%: 累计{m['total_return']:+.2f}% 回撤{m['max_drawdown']:.2f}%")

    # 方案B: 2层×50%（初始50%，第二层加满）
    print("\n运行 2层×50%...")
    m = run_single(config, storage, top_n=1, tp_ratio=0.05,
                    sl_mode='disabled', max_levels=2, level_ratio=0.5)
    results.append({
        'group': '动态仓位', 'top_n': 1, 'tp': '5%', 'sl': 'disabled',
        'levels': 2, 'level_ratio': '50%',
        'total_return': m['total_return'], 'annual_return': m['annual_return'],
        'max_drawdown': m['max_drawdown'], 'sharpe': m['sharpe_ratio'],
        'win_rate': m['win_rate'], 'trades': m['total_round_trips'],
        'final_equity': m['final_equity'],
    })
    print(f"  2层×50%: 累计{m['total_return']:+.2f}% 回撤{m['max_drawdown']:.2f}%")

    # 方案C: 1层×100%（满仓买入，不加仓）
    print("\n运行 1层×100%...")
    m = run_single(config, storage, top_n=1, tp_ratio=0.05,
                    sl_mode='disabled', max_levels=1, level_ratio=1.0)
    results.append({
        'group': '动态仓位', 'top_n': 1, 'tp': '5%', 'sl': 'disabled',
        'levels': 1, 'level_ratio': '100%',
        'total_return': m['total_return'], 'annual_return': m['annual_return'],
        'max_drawdown': m['max_drawdown'], 'sharpe': m['sharpe_ratio'],
        'win_rate': m['win_rate'], 'trades': m['total_round_trips'],
        'final_equity': m['final_equity'],
    })
    print(f"  1层×100%: 累计{m['total_return']:+.2f}% 回撤{m['max_drawdown']:.2f}%")

    # 方案D: 3层×33%
    print("\n运行 3层×33%...")
    m = run_single(config, storage, top_n=1, tp_ratio=0.05,
                    sl_mode='disabled', max_levels=3, level_ratio=0.333)
    results.append({
        'group': '动态仓位', 'top_n': 1, 'tp': '5%', 'sl': 'disabled',
        'levels': 3, 'level_ratio': '33%',
        'total_return': m['total_return'], 'annual_return': m['annual_return'],
        'max_drawdown': m['max_drawdown'], 'sharpe': m['sharpe_ratio'],
        'win_rate': m['win_rate'], 'trades': m['total_round_trips'],
        'final_equity': m['final_equity'],
    })
    print(f"  3层×33%: 累计{m['total_return']:+.2f}% 回撤{m['max_drawdown']:.2f}%")

    # 保存结果
    df = pd.DataFrame(results)
    df.to_csv('results/topn_position_sweep.csv', index=False)

    # 打印汇总
    print("\n" + "=" * 100)
    print("汇总结果")
    print("=" * 100)
    print(f"{'组别':<10} {'TopN':>4} {'止盈':>5} {'止损':>8} {'层数':>4} {'每层':>5} "
          f"{'累计收益':>8} {'年化':>8} {'最大回撤':>8} {'Sharpe':>7} {'胜率':>6} {'交易数':>6}")
    print("-" * 100)
    for _, r in df.iterrows():
        print(f"{r['group']:<10} {r['top_n']:>4} {r['tp']:>5} {r['sl']:>8} "
              f"{r['levels']:>4} {r['level_ratio']:>5} "
              f"{r['total_return']:>+7.2f}% {r['annual_return']:>+7.2f}% "
              f"{r['max_drawdown']:>7.2f}% {r['sharpe']:>7.3f} "
              f"{r['win_rate']:>5.1f}% {r['trades']:>6d}")

    print(f"\n结果已保存: results/topn_position_sweep.csv")


if __name__ == '__main__':
    main()
