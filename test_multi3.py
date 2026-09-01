"""
测试多股策略：3只同时持有 + 止盈5% + 止损10% + 时间止损7天 + 每只3层
回测区间：2020-01-01 ~ 2026-08-25
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.loader import load_config
from data_loader.storage import DataStorage
from strategy.bb_turnover_multi import BBTurnoverMultiStrategy
import pandas as pd

def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    config = load_config(os.path.join(project_root, 'config', 'config.yaml'))

    # 新策略参数
    config['strategy']['max_positions'] = 3           # 同时持有3只
    config['strategy']['max_levels_per_stock'] = 3     # 每只最多3层（初始+2加仓）
    config['strategy']['take_profit']['ratio'] = 0.05  # 止盈5%
    config['strategy']['stop_loss']['mode'] = 'fixed_percent'
    config['strategy']['stop_loss']['fixed_percent']['ratio'] = 0.10  # 止损10%
    config['strategy']['time_stop_days'] = 7            # 时间止损7天
    config['strategy']['top_n_scan'] = 30               # 每天扫描30只候选
    config['backtest']['start_date'] = '2020-01-01'
    config['backtest']['end_date'] = '2026-08-25'

    print("=" * 70)
    print("多股策略：3只同时持有 + 止盈5% + 止损10% + 时间止损7天 + 每只3层")
    print("回测区间：2020-01-01 ~ 2026-08-25")
    print("=" * 70)

    storage = DataStorage(os.path.join(project_root, 'data', 'raw'))
    strategy = BBTurnoverMultiStrategy(config, storage)

    t0 = time.time()
    result = strategy.run()
    elapsed = time.time() - t0

    # 结果分析
    initial = config['backtest']['initial_cash']
    final = result['final_equity']
    total_return = (final - initial) / initial * 100

    nav = result['daily_nav']
    equities = [n['total_equity'] for n in nav]
    peak = equities[0]
    max_dd = 0
    for eq in equities:
        if eq > peak: peak = eq
        dd = (eq - peak) / peak * 100
        if dd < max_dd: max_dd = dd

    # 年化
    days = len(nav)
    annual_return = ((final / initial) ** (252 / max(days, 1)) - 1) * 100

    # Sharpe
    daily_rets = []
    for i in range(1, len(equities)):
        if equities[i-1] > 0:
            daily_rets.append((equities[i] - equities[i-1]) / equities[i-1])
    import numpy as np
    sharpe = (np.mean(daily_rets) / np.std(daily_rets) * np.sqrt(252)) if daily_rets and np.std(daily_rets) > 0 else 0

    trades = result['trades']
    buy_count = sum(1 for t in trades if t['action'] == 'BUY')
    sell_count = sum(1 for t in trades if t['action'] == 'SELL')
    tp_count = sum(1 for t in trades if t['reason'] == 'TAKE_PROFIT')
    sl_count = sum(1 for t in trades if t['reason'] == 'STOP_LOSS')
    ts_count = sum(1 for t in trades if t['reason'] == 'TIME_STOP')

    print(f"\n{'='*70}")
    print(f"回测完成！耗时: {elapsed:.1f}秒 ({elapsed/60:.1f}分钟)")
    print(f"{'='*70}")
    print(f"初始资金:     {initial:,.0f}")
    print(f"最终权益:     {final:,.2f}")
    print(f"累计收益:     {total_return:+.2f}%")
    print(f"年化收益:     {annual_return:+.2f}%")
    print(f"最大回撤:     {max_dd:.2f}%")
    print(f"Sharpe:       {sharpe:.3f}")
    print(f"交易日数:     {days}")
    print(f"买入笔数:     {buy_count}")
    print(f"卖出笔数:     {sell_count}")
    print(f"  止盈:       {tp_count}")
    print(f"  价格止损:   {sl_count}")
    print(f"  时间止损:   {ts_count}")
    if sell_count > 0:
        print(f"胜率(止盈占比): {tp_count/sell_count*100:.1f}%")

    # 年度收益
    nav_df = pd.DataFrame(nav)
    nav_df['date'] = pd.to_datetime(nav_df['date'])
    nav_df['year'] = nav_df['date'].dt.year
    print(f"\n=== 年度收益 ===")
    for year in sorted(nav_df['year'].unique()):
        yd = nav_df[nav_df['year'] == year]
        ys = yd['total_equity'].iloc[0]
        ye = yd['total_equity'].iloc[-1]
        yr = (ye - ys) / ys * 100
        print(f"{year}: {yr:+.2f}% ({ys:,.0f} → {ye:,.0f})")

    # 保存
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    trades_path = os.path.join(project_root, 'results', 'trades', f'trades_multi3_tp5_sl10_ts7_{timestamp}.csv')
    nav_path = os.path.join(project_root, 'results', 'reports', f'nav_multi3_tp5_sl10_ts7_{timestamp}.csv')
    pd.DataFrame(trades).to_csv(trades_path, index=False, encoding='utf-8-sig')
    pd.DataFrame(nav).to_csv(nav_path, index=False, encoding='utf-8-sig')
    print(f"\n交易日志: {trades_path}")
    print(f"净值曲线: {nav_path}")

if __name__ == '__main__':
    main()
