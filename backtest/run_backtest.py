"""
回测执行器

运行策略回测，保存交易日志和净值曲线，输出基本统计。

用法：
    python -m backtest.run_backtest
    python -m backtest.run_backtest --start 2020-01-01 --end 2024-12-31
"""
import sys
import os
import argparse
import logging
from datetime import datetime
import pandas as pd

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.loader import load_config
from data_loader.storage import DataStorage
from strategy.bb_turnover_top1 import BBTurnoverTop1Strategy


def setup_logging(verbose: bool = False):
    """配置日志。"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )


def run_backtest(config_path: str = None, start_date: str = None,
                 end_date: str = None, verbose: bool = False) -> dict:
    """
    运行回测。

    Args:
        config_path: 配置文件路径
        start_date: 开始日期（覆盖配置）
        end_date: 结束日期（覆盖配置）
        verbose: 是否输出详细日志

    Returns:
        回测结果字典
    """
    setup_logging(verbose)
    logger = logging.getLogger('run_backtest')

    # 加载配置
    if config_path is None:
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                     'config', 'config.yaml')
    config = load_config(config_path)

    # 覆盖日期
    if start_date:
        config['backtest']['start_date'] = start_date
    if end_date:
        config['backtest']['end_date'] = end_date

    # 创建数据存储
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_dir = os.path.join(project_root, 'data', 'raw')
    storage = DataStorage(raw_dir)

    # 创建策略
    strategy = BBTurnoverTop1Strategy(config, storage)

    # 运行回测
    logger.info("=" * 70)
    logger.info("开始回测")
    logger.info("=" * 70)

    start_time = datetime.now()
    result = strategy.run()
    elapsed = (datetime.now() - start_time).total_seconds()

    logger.info("=" * 70)
    logger.info(f"回测完成，耗时 {elapsed:.1f} 秒")
    logger.info("=" * 70)

    # 保存结果
    results_dir = os.path.join(project_root, 'results')
    trades_dir = os.path.join(results_dir, 'trades')
    reports_dir = os.path.join(results_dir, 'reports')
    os.makedirs(trades_dir, exist_ok=True)
    os.makedirs(reports_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # 保存交易日志
    if result['trades']:
        trades_df = pd.DataFrame(result['trades'])
        trades_path = os.path.join(trades_dir, f'trades_{timestamp}.csv')
        trades_df.to_csv(trades_path, index=False, encoding='utf-8-sig')
        logger.info(f"交易日志已保存: {trades_path} ({len(trades_df)} 笔)")
    else:
        logger.warning("无交易记录")

    # 保存净值曲线
    if result['daily_nav']:
        nav_df = pd.DataFrame(result['daily_nav'])
        nav_path = os.path.join(reports_dir, f'nav_{timestamp}.csv')
        nav_df.to_csv(nav_path, index=False, encoding='utf-8-sig')
        logger.info(f"净值曲线已保存: {nav_path} ({len(nav_df)} 天)")

    # 输出基本统计
    print_basic_stats(result, config)

    return result


def print_basic_stats(result: dict, config: dict):
    """输出基本回测统计。"""
    print("\n" + "=" * 70)
    print("回测基本统计")
    print("=" * 70)

    initial_cash = config['backtest']['initial_cash']
    final_equity = result['final_equity']
    total_return = (final_equity - initial_cash) / initial_cash * 100

    print(f"初始资金:     {initial_cash:>15,.2f} 元")
    print(f"最终权益:     {final_equity:>15,.2f} 元")
    print(f"累计收益率:   {total_return:>14.2f} %")

    # 交易统计
    trades = result['trades']
    if trades:
        buy_trades = [t for t in trades if t['action'] == 'BUY']
        sell_trades = [t for t in trades if t['action'] == 'SELL']
        tp_trades = [t for t in sell_trades if t['reason'] == 'TAKE_PROFIT']
        sl_trades = [t for t in sell_trades if t['reason'] == 'STOP_LOSS']

        print(f"买入笔数:     {len(buy_trades):>15d}")
        print(f"卖出笔数:     {len(sell_trades):>15d}")
        print(f"  止盈:       {len(tp_trades):>15d}")
        print(f"  止损:       {len(sl_trades):>15d}")

        # 费用统计
        total_commission = sum(t['commission'] for t in trades)
        total_stamp_tax = sum(t['stamp_tax'] for t in trades)
        total_transfer_fee = sum(t['transfer_fee'] for t in trades)
        total_slippage = sum(t['slippage'] for t in trades)
        total_fees = total_commission + total_stamp_tax + total_transfer_fee + total_slippage

        print(f"手续费总额:   {total_commission:>15,.2f} 元")
        print(f"印花税总额:   {total_stamp_tax:>15,.2f} 元")
        print(f"过户费总额:   {total_transfer_fee:>15,.2f} 元")
        print(f"滑点损失:     {total_slippage:>15,.2f} 元")
        print(f"费用合计:     {total_fees:>15,.2f} 元")

    # 策略统计
    stats = result['stats']
    print(f"\n信号统计:")
    print(f"  总信号数:   {stats['signals_total']:>15d}")
    print(f"  止盈触发:   {stats['take_profit_triggers']:>15d}")
    print(f"  止损触发:   {stats['stop_loss_triggers']:>15d}")
    print(f"  跌停跳过买: {stats['signals_skipped_limit_down']:>15d}")
    print(f"  涨停跳过买: {stats['signals_skipped_limit_up']:>15d}")
    print(f"  买不起跳过: {stats['signals_skipped_cannot_afford']:>15d}")
    print(f"  跌停卖不出: {stats['sell_skipped_limit_down']:>15d}")

    # 最大回撤
    if result['daily_nav']:
        max_dd = min(nav['drawdown'] for nav in result['daily_nav'])
        print(f"\n最大回撤:     {max_dd:>14.2f} %")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description='A股单股BB均值回归策略回测')
    parser.add_argument('--config', type=str, default=None, help='配置文件路径')
    parser.add_argument('--start', type=str, default=None, help='开始日期 YYYY-MM-DD')
    parser.add_argument('--end', type=str, default=None, help='结束日期 YYYY-MM-DD')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细日志')
    args = parser.parse_args()

    run_backtest(args.config, args.start, args.end, args.verbose)


if __name__ == '__main__':
    main()
