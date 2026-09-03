"""
参数扫描器 - 多进程并行回测

用法：
    python -m analysis.param_scan
    python -m analysis.param_scan --workers 8
"""
import sys
import os
import argparse
import logging
import time
from datetime import datetime
from multiprocessing import Pool, cpu_count
from itertools import product
import pandas as pd
import numpy as np
import copy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.loader import load_config
from data_loader.storage import DataStorage
from strategy.bb_turnover_top1 import BBTurnoverTop1Strategy


def suppress_logging():
    """抑制日志输出（子进程中使用）。"""
    logging.disable(logging.CRITICAL)
    # 禁用tqdm进度条，避免多进程输出混乱
    os.environ['TQDM_DISABLE'] = '1'
    os.environ['TQDM_MININTERVAL'] = '9999'


def run_single_backtest(params):
    """
    运行单组参数回测。

    Args:
        params: 参数字典 (tp_ratio, sl_ratio, max_levels, time_stop_days, top_n)

    Returns:
        结果字典
    """
    suppress_logging()

    try:
        # 加载配置
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(project_root, 'config', 'config.yaml')
        config = load_config(config_path)

        # 应用参数
        config['strategy']['take_profit']['ratio'] = params['tp_ratio']
        config['strategy']['stop_loss']['fixed_percent']['ratio'] = params['sl_ratio']
        config['strategy']['position']['max_levels'] = params['max_levels']
        config['strategy']['position']['level_ratio'] = 1.0 / params['max_levels']
        config['strategy']['time_stop_days'] = params.get('time_stop_days', 0)
        config['strategy']['top_n'] = params.get('top_n', 1)

        # 止损模式
        if params['sl_ratio'] <= 0:
            config['strategy']['stop_loss']['mode'] = 'disabled'
        else:
            config['strategy']['stop_loss']['mode'] = 'fixed_percent'

        # 回测区间
        config['backtest']['start_date'] = '2020-01-01'
        config['backtest']['end_date'] = '2024-12-31'

        # 创建数据存储和策略
        raw_dir = os.path.join(project_root, 'data', 'raw')
        storage = DataStorage(raw_dir)
        strategy = BBTurnoverTop1Strategy(config, storage)

        # 运行回测
        result = strategy.run()

        # 计算性能指标
        initial_cash = config['backtest']['initial_cash']
        final_equity = result['final_equity']
        total_return = (final_equity - initial_cash) / initial_cash * 100

        # 年化收益
        days = len(result['daily_nav'])
        annual_return = ((final_equity / initial_cash) ** (252 / max(days, 1)) - 1) * 100

        # 最大回撤
        nav_list = result['daily_nav']
        if nav_list:
            equities = [n['total_equity'] for n in nav_list]
            peak = equities[0]
            max_dd = 0
            for eq in equities:
                if eq > peak:
                    peak = eq
                dd = (eq - peak) / peak * 100
                if dd < max_dd:
                    max_dd = dd
        else:
            max_dd = 0

        # 交易统计
        trades = result['trades']
        buy_count = sum(1 for t in trades if t['action'] == 'BUY')
        sell_count = sum(1 for t in trades if t['action'] == 'SELL')
        tp_count = sum(1 for t in trades if t['reason'] == 'TAKE_PROFIT')
        sl_count = sum(1 for t in trades if t['reason'] == 'STOP_LOSS')

        # 胜率（基于完整交易对）
        win_rate = (tp_count / max(sell_count, 1)) * 100 if sell_count > 0 else 0

        # Sharpe（简化版）
        if nav_list and len(nav_list) > 1:
            daily_returns = []
            for i in range(1, len(nav_list)):
                prev_eq = nav_list[i-1]['total_equity']
                curr_eq = nav_list[i]['total_equity']
                if prev_eq > 0:
                    daily_returns.append((curr_eq - prev_eq) / prev_eq)
            if daily_returns:
                avg_ret = np.mean(daily_returns)
                std_ret = np.std(daily_returns)
                sharpe = (avg_ret / std_ret * np.sqrt(252)) if std_ret > 0 else 0
            else:
                sharpe = 0
        else:
            sharpe = 0

        # Calmar
        calmar = (annual_return / abs(max_dd)) if max_dd < 0 else 0

        return {
            'tp_ratio': params['tp_ratio'],
            'sl_ratio': params['sl_ratio'],
            'max_levels': params['max_levels'],
            'time_stop_days': params.get('time_stop_days', 0),
            'top_n': params.get('top_n', 1),
            'total_return': round(total_return, 2),
            'annual_return': round(annual_return, 2),
            'max_drawdown': round(max_dd, 2),
            'sharpe': round(sharpe, 3),
            'calmar': round(calmar, 3),
            'win_rate': round(win_rate, 1),
            'buy_count': buy_count,
            'sell_count': sell_count,
            'tp_count': tp_count,
            'sl_count': sl_count,
            'final_equity': round(final_equity, 2),
            'status': 'success',
        }

    except Exception as e:
        return {
            'tp_ratio': params.get('tp_ratio', 0),
            'sl_ratio': params.get('sl_ratio', 0),
            'max_levels': params.get('max_levels', 0),
            'time_stop_days': params.get('time_stop_days', 0),
            'top_n': params.get('top_n', 1),
            'total_return': 0,
            'annual_return': 0,
            'max_drawdown': 0,
            'sharpe': 0,
            'calmar': 0,
            'win_rate': 0,
            'buy_count': 0,
            'sell_count': 0,
            'tp_count': 0,
            'sl_count': 0,
            'final_equity': 0,
            'status': f'error: {str(e)[:100]}',
        }


def generate_param_combinations(scan_type='core'):
    """
    生成参数组合。

    Args:
        scan_type: 'core'（核心参数）或 'full'（全参数）

    Returns:
        参数组合列表
    """
    if scan_type == 'core':
        # 核心参数：止盈 × 止损 × 层数
        tp_ratios = [0.01, 0.015, 0.02, 0.03, 0.05]
        sl_ratios = [0, 0.05, 0.10, 0.15]  # 0 = disabled
        max_levels_list = [1, 2, 3, 5]
        time_stop_days_list = [0]
        top_n_list = [1]
    else:
        # 全参数
        tp_ratios = [0.005, 0.01, 0.015, 0.02, 0.03, 0.05]
        sl_ratios = [0, 0.03, 0.05, 0.07, 0.10, 0.15]
        max_levels_list = [1, 2, 3, 4, 5]
        time_stop_days_list = [0, 5, 7, 10, 14]
        top_n_list = [1, 2, 3, 5]

    combinations = []
    for tp, sl, levels, ts, tn in product(tp_ratios, sl_ratios, max_levels_list,
                                            time_stop_days_list, top_n_list):
        combinations.append({
            'tp_ratio': tp,
            'sl_ratio': sl,
            'max_levels': levels,
            'time_stop_days': ts,
            'top_n': tn,
        })

    return combinations


def main():
    parser = argparse.ArgumentParser(description='参数扫描 - 多进程并行回测')
    parser.add_argument('--workers', type=int, default=min(8, cpu_count()),
                        help='并行进程数（默认8）')
    parser.add_argument('--scan-type', type=str, default='core',
                        choices=['core', 'full'], help='扫描范围')
    parser.add_argument('--output', type=str, default=None, help='输出文件路径')
    args = parser.parse_args()

    # 生成参数组合
    params_list = generate_param_combinations(args.scan_type)
    total = len(params_list)
    print(f"=" * 70)
    print(f"参数扫描开始")
    print(f"=" * 70)
    print(f"扫描范围: {args.scan_type}")
    print(f"参数组合数: {total}")
    print(f"并行进程数: {args.workers}")
    print(f"预计耗时: ~{total * 5 / args.workers / 60:.1f} 小时（每组约5分钟）")
    print(f"=" * 70)

    start_time = time.time()
    results = []
    completed = 0

    # 准备增量保存的输出文件
    results_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'results')
    os.makedirs(results_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if args.output is None:
        output_path = os.path.join(results_dir, f'param_scan_{args.scan_type}_{timestamp}.csv')
    else:
        output_path = args.output

    # 写入CSV表头
    csv_columns = ['tp_ratio','sl_ratio','max_levels','time_stop_days','top_n',
                   'total_return','annual_return','max_drawdown','sharpe','calmar',
                   'win_rate','buy_count','sell_count','tp_count','sl_count',
                   'final_equity','status']
    with open(output_path, 'w', encoding='utf-8-sig') as f:
        f.write(','.join(csv_columns) + '\n')

    print(f"结果增量保存到: {output_path}")

    # 多进程执行 - 增量保存
    with Pool(processes=args.workers) as pool:
        for i, result in enumerate(pool.imap_unordered(run_single_backtest, params_list)):
            results.append(result)
            completed += 1
            elapsed = time.time() - start_time
            avg_time = elapsed / completed
            eta = avg_time * (total - completed)
            print(f"[{completed}/{total}] TP={result['tp_ratio']:.1%} "
                  f"SL={result['sl_ratio']:.1%} L={result['max_levels']} "
                  f"→ 收益={result['total_return']:.1f}% "
                  f"回撤={result['max_drawdown']:.1f}% "
                  f"Sharpe={result['sharpe']:.2f} "
                  f"({result['status']}) "
                  f"ETA={eta/60:.0f}min", flush=True)

            # 增量追加写入CSV
            with open(output_path, 'a', encoding='utf-8-sig') as f:
                row = [str(result.get(col, '')) for col in csv_columns]
                f.write(','.join(row) + '\n')

    df = pd.DataFrame(results)
    df = df.sort_values('total_return', ascending=False)
    df.to_csv(output_path, index=False, encoding='utf-8-sig')

    elapsed = time.time() - start_time
    print(f"\n{'=' * 70}")
    print(f"参数扫描完成！耗时 {elapsed/60:.1f} 分钟")
    print(f"结果已保存: {output_path}")
    print(f"{'=' * 70}")

    # 输出Top 10
    print(f"\n=== Top 10 参数组合（按累计收益排序）===")
    top10 = df.head(10)
    for i, (_, row) in enumerate(top10.iterrows()):
        print(f"{i+1}. TP={row['tp_ratio']:.1%} SL={row['sl_ratio']:.1%} "
              f"L={int(row['max_levels'])} → 收益={row['total_return']:.1f}% "
              f"回撤={row['max_drawdown']:.1f}% Sharpe={row['sharpe']:.2f} "
              f"胜率={row['win_rate']:.0f}% 交易={int(row['sell_count'])}笔")

    # 输出盈利组合统计
    profitable = df[df['total_return'] > 0]
    print(f"\n=== 盈利组合统计 ===")
    print(f"总组合数: {len(df)}")
    print(f"盈利组合数: {len(profitable)} ({len(profitable)/len(df)*100:.1f}%)")
    if len(profitable) > 0:
        print(f"最高收益: {profitable['total_return'].max():.1f}%")
        print(f"平均收益: {profitable['total_return'].mean():.1f}%")


if __name__ == '__main__':
    main()
