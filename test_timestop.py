"""
测试优化后的引擎 + 时间止损7天组合
"""
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.loader import load_config
from data_loader.storage import DataStorage
from strategy.bb_turnover_top1 import BBTurnoverTop1Strategy

def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(project_root, 'config', 'config.yaml')
    config = load_config(config_path)

    # ===== 时间止损7天组合参数 =====
    config['strategy']['take_profit']['ratio'] = 0.015      # 止盈1.5%
    config['strategy']['stop_loss']['mode'] = 'disabled'      # 关闭价格止损
    config['strategy']['position']['max_levels'] = 5          # 5层仓位
    config['strategy']['position']['level_ratio'] = 0.2       # 每层20%
    config['strategy']['time_stop_days'] = 7                   # 时间止损7天
    config['backtest']['start_date'] = '2020-01-01'
    config['backtest']['end_date'] = '2024-12-31'

    print("=" * 60)
    print("测试组合：止盈1.5% + 无价格止损 + 时间止损7天 + 5层")
    print("=" * 60)

    # 创建数据存储和策略
    raw_dir = os.path.join(project_root, 'data', 'raw')
    storage = DataStorage(raw_dir)
    strategy = BBTurnoverTop1Strategy(config, storage)

    # 运行回测并计时
    t0 = time.time()
    result = strategy.run()
    elapsed = time.time() - t0

    # 输出结果
    initial_cash = config['backtest']['initial_cash']
    final_equity = result['final_equity']
    total_return = (final_equity - initial_cash) / initial_cash * 100

    # 最大回撤
    nav_list = result['daily_nav']
    equities = [n['total_equity'] for n in nav_list]
    peak = equities[0]
    max_dd = 0
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = (eq - peak) / peak * 100
        if dd < max_dd:
            max_dd = dd

    # 交易统计
    trades = result['trades']
    buy_count = sum(1 for t in trades if t['action'] == 'BUY')
    sell_count = sum(1 for t in trades if t['action'] == 'SELL')
    tp_count = sum(1 for t in trades if t['reason'] == 'TAKE_PROFIT')
    sl_count = sum(1 for t in trades if t['reason'] == 'STOP_LOSS')
    ts_count = sum(1 for t in trades if t['reason'] == 'TIME_STOP')

    print(f"\n{'='*60}")
    print(f"回测完成！耗时: {elapsed:.1f}秒 ({elapsed/60:.1f}分钟)")
    print(f"{'='*60}")
    print(f"初始资金:     {initial_cash:,.0f}")
    print(f"最终权益:     {final_equity:,.2f}")
    print(f"累计收益:     {total_return:+.2f}%")
    print(f"最大回撤:     {max_dd:.2f}%")
    print(f"买入笔数:     {buy_count}")
    print(f"卖出笔数:     {sell_count}")
    print(f"  止盈:       {tp_count}")
    print(f"  价格止损:   {sl_count}")
    print(f"  时间止损:   {ts_count}")
    if sell_count > 0:
        print(f"胜率(止盈占比): {tp_count/sell_count*100:.1f}%")

    # 保存交易日志
    import pandas as pd
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    trades_path = os.path.join(project_root, 'results', 'trades', f'trades_timestop7_{timestamp}.csv')
    pd.DataFrame(trades).to_csv(trades_path, index=False, encoding='utf-8-sig')
    print(f"\n交易日志已保存: {trades_path}")

    # 保存净值曲线
    nav_path = os.path.join(project_root, 'results', 'reports', f'nav_timestop7_{timestamp}.csv')
    pd.DataFrame(nav_list).to_csv(nav_path, index=False, encoding='utf-8-sig')
    print(f"净值曲线已保存: {nav_path}")

if __name__ == '__main__':
    main()
