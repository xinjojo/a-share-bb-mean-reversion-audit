"""
全市场扫描：用方案C策略对每只股票从2020年逐个回测
统计策略在全市场的有效性分布
策略：BB Lower + 前10天跌>10% + 布林带宽度>15% + 止盈2% + 第1天跌全卖 + 前3天涨<2%全卖 + 时间止损20天
"""
import sys, os, time, gc
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import numpy as np
import glob
from engine.commission import FeeCalculator

def backtest_single_stock(daily_df, adj_df, fee_calc, start_date='2020-01-01', end_date='2026-08-25'):
    """
    单股回测方案C策略
    返回：交易记录列表 + 统计指标
    """
    # 合并数据
    daily = daily_df.sort_values('date').reset_index(drop=True)
    daily['date'] = pd.to_datetime(daily['date'])
    adj = adj_df.sort_values('date').reset_index(drop=True)
    adj['date'] = pd.to_datetime(adj['date'])
    merged = pd.merge(daily[['date','open','high','low','close','vol','amount','pre_close']],
                      adj[['date','adj_factor']], on='date', how='inner')
    merged = merged.set_index('date')
    merged = merged[(merged.index >= start_date) & (merged.index <= end_date)]
    if len(merged) < 60:
        return [], {}

    # 计算指标
    merged['adj_close'] = merged['close'] * merged['adj_factor']
    merged['bb_mid'] = merged['adj_close'].rolling(20).mean()
    merged['bb_std'] = merged['adj_close'].rolling(20).std()
    merged['bb_upper'] = merged['bb_mid'] + 2 * merged['bb_std']
    merged['bb_lower'] = merged['bb_mid'] - 2 * merged['bb_std']
    merged['bb_width'] = (merged['bb_upper'] - merged['bb_lower']) / merged['bb_mid'] * 100
    merged['ret_10d'] = merged['adj_close'].pct_change(10) * 100
    merged['is_limit_down'] = merged['close'] <= merged['pre_close'] * 0.905

    # 回测
    cash = 1_000_000
    position = None  # {'shares', 'avg_cost', 'entry_idx', 'max_gain_3d'}
    trades = []

    for i in range(len(merged)):
        row = merged.iloc[i]
        date = merged.index[i]

        # 卖出判断
        if position is not None:
            holding_trays = i - position['entry_idx']
            sell = False
            sell_price = None
            reason = None

            if holding_trays >= 1:  # T+1
                # 止盈2%
                tp_price = position['avg_cost'] * 1.02
                if row['high'] >= tp_price:
                    sell = True
                    sell_price = tp_price
                    reason = 'TAKE_PROFIT'

                # 动态止损1：第1天收盘下跌全卖
                if not sell and holding_trays == 1:
                    if row['close'] < position['avg_cost']:
                        sell = True
                        sell_price = row['close']
                        reason = 'DYNAMIC_STOP_DAY1'

                # 动态止损2：前3天最大涨幅<2%，第3天收盘全卖
                if not sell and holding_trays == 3:
                    if position['max_gain_3d'] < 2.0:
                        sell = True
                        sell_price = row['close']
                        reason = 'DYNAMIC_STOP_DAY3'

                # 时间止损20天
                if not sell and holding_trays >= 20:
                    sell = True
                    sell_price = row['close']
                    reason = 'TIME_STOP'

            if sell:
                shares = position['shares']
                fee = fee_calc.calculate('sell', sell_price, shares)
                cash += fee.net_cash_flow
                pnl = (fee.price - position['avg_cost']) * shares - fee.total_fee
                trades.append({
                    'date': date, 'action': 'SELL', 'price': fee.price,
                    'shares': shares, 'amount': fee.amount,
                    'avg_cost': position['avg_cost'], 'pnl': pnl,
                    'reason': reason, 'holding_trays': holding_trays,
                })
                position = None
                continue

            # 更新前3天最大涨幅
            if holding_trays >= 1:
                current_gain = (row['high'] / position['avg_cost'] - 1) * 100
                if current_gain > position['max_gain_3d']:
                    position['max_gain_3d'] = current_gain

        # 买入判断
        if position is None:
            # BB Lower信号
            if pd.isna(row['bb_lower']) or row['adj_close'] >= row['bb_lower']:
                continue
            # 前10天跌>10%
            if pd.isna(row['ret_10d']) or row['ret_10d'] > -10.0:
                continue
            # 布林带宽度>15%
            if pd.isna(row['bb_width']) or row['bb_width'] < 15.0:
                continue
            # 跌停不买
            if row['is_limit_down']:
                continue

            buy_price = row['close']
            shares = int(cash / buy_price / 100) * 100
            if shares < 100:
                continue

            fee = fee_calc.calculate('buy', buy_price, shares)
            if cash < -fee.net_cash_flow:
                continue

            cash += fee.net_cash_flow
            position = {
                'shares': shares,
                'avg_cost': (fee.amount + fee.total_fee) / shares,
                'entry_idx': i,
                'max_gain_3d': 0,
            }
            trades.append({
                'date': date, 'action': 'BUY', 'price': fee.price,
                'shares': shares, 'amount': fee.amount,
                'avg_cost': position['avg_cost'], 'pnl': 0,
                'reason': 'INITIAL_ENTRY', 'holding_trays': 0,
            })

    # 统计指标
    sell_trades = [t for t in trades if t['action'] == 'SELL']
    n_trades = len(sell_trades)
    if n_trades > 0:
        wins = [t for t in sell_trades if t['pnl'] > 0]
        losses = [t for t in sell_trades if t['pnl'] <= 0]
        win_rate = len(wins) / n_trades * 100
        avg_win = np.mean([t['pnl'] for t in wins]) if wins else 0
        avg_loss = np.mean([t['pnl'] for t in losses]) if losses else 0
        total_pnl = sum(t['pnl'] for t in sell_trades)
        total_return = total_pnl / 1_000_000 * 100
        avg_holding = np.mean([t['holding_trays'] for t in sell_trades])
        # 卖出原因分布
        reason_counts = {}
        for t in sell_trades:
            reason_counts[t['reason']] = reason_counts.get(t['reason'], 0) + 1
    else:
        win_rate = avg_win = avg_loss = total_pnl = total_return = avg_holding = 0
        reason_counts = {}

    stats = {
        'n_trades': n_trades,
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'total_pnl': total_pnl,
        'total_return': total_return,
        'avg_holding': avg_holding,
        'reason_counts': reason_counts,
    }

    return trades, stats


def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    fee_calc = FeeCalculator()

    # 获取所有股票文件
    daily_files = sorted(glob.glob(os.path.join(project_root, 'data', 'raw', 'daily', '*.parquet')))
    print(f"总股票数: {len(daily_files)}")

    # 检查是否有中间结果
    result_file = os.path.join(project_root, 'results', 'full_market_scan_planC.csv')
    if os.path.exists(result_file):
        existing = pd.read_csv(result_file)
        processed = set(existing['ts_code'].tolist())
        print(f"已处理: {len(processed)} 只，继续处理剩余...")
    else:
        existing = pd.DataFrame()
        processed = set()

    results = []
    t0 = time.time()
    count = 0
    error_count = 0

    for fpath in daily_files:
        ts_code = os.path.basename(fpath).replace('.parquet', '')
        if ts_code in processed:
            continue

        # 加载数据
        try:
            daily = pd.read_parquet(fpath)
            adj_path = os.path.join(project_root, 'data', 'raw', 'adj_factor', f'{ts_code}.parquet')
            if not os.path.exists(adj_path):
                continue
            adj = pd.read_parquet(adj_path)
        except Exception as e:
            error_count += 1
            if error_count % 100 == 0:
                print(f"  数据加载错误 {error_count} 只: {ts_code} {e}")
            continue

        # 回测
        try:
            trades, stats = backtest_single_stock(daily, adj, fee_calc)
        except Exception as e:
            error_count += 1
            print(f"  回测失败 {ts_code}: {e}")
            continue

        if not stats or stats.get('n_trades', 0) == 0:
            continue

        # 记录结果
        try:
            result_row = {
                'ts_code': ts_code,
                'n_trades': stats['n_trades'],
                'win_rate': stats['win_rate'],
                'avg_win': stats['avg_win'],
                'avg_loss': stats['avg_loss'],
                'total_pnl': stats['total_pnl'],
                'total_return': stats['total_return'],
                'avg_holding': stats['avg_holding'],
                'tp_count': stats['reason_counts'].get('TAKE_PROFIT', 0),
                'day1_count': stats['reason_counts'].get('DYNAMIC_STOP_DAY1', 0),
                'day3_count': stats['reason_counts'].get('DYNAMIC_STOP_DAY3', 0),
                'timestop_count': stats['reason_counts'].get('TIME_STOP', 0),
            }
            results.append(result_row)
            count += 1
        except Exception as e:
            print(f"  记录结果失败 {ts_code}: {e}")
            continue

        # 每200只保存一次
        if count % 200 == 0:
            elapsed = time.time() - t0
            speed = count / elapsed * 60
            remaining = (len(daily_files) - len(processed) - count) / max(speed, 1)
            print(f"  已处理 {count} 只有交易 (累计{len(processed)+count}), 速度{speed:.0f}只/分钟, 预计剩余{remaining:.1f}分钟, 错误{error_count}只", flush=True)
            # 保存中间结果
            new_df = pd.DataFrame(results)
            combined = pd.concat([existing, new_df], ignore_index=True)
            combined.to_csv(result_file, index=False)
            # 更新状态，避免重复
            existing = combined
            processed.update([r['ts_code'] for r in results])
            results = []
            # 强制垃圾回收
            gc.collect()

    # 保存最终结果
    if results:
        new_df = pd.DataFrame(results)
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = existing
    combined.to_csv(result_file, index=False)
    print(f"\n全市场扫描完成！共处理 {len(combined)} 只有交易的股票, 错误{error_count}只")
    print(f"结果保存到: {result_file}")
    print(f"总耗时: {time.time()-t0:.1f}秒")

    # 统计汇总
    if len(combined) > 0:
        print(f"\n{'='*70}")
        print("全市场统计汇总")
        print(f"{'='*70}")
        print(f"有交易的股票数: {len(combined)}")
        print(f"盈利股票数: {(combined['total_return']>0).sum()} ({(combined['total_return']>0).mean()*100:.1f}%)")
        print(f"亏损股票数: {(combined['total_return']<=0).sum()} ({(combined['total_return']<=0).mean()*100:.1f}%)")
        print(f"平均累计收益: {combined['total_return'].mean():.2f}%")
        print(f"中位数累计收益: {combined['total_return'].median():.2f}%")
        print(f"平均胜率: {combined['win_rate'].mean():.1f}%")
        print(f"平均交易次数: {combined['n_trades'].mean():.1f}")
        print(f"平均持仓天数: {combined['avg_holding'].mean():.1f}")

        # 按胜率分段
        print(f"\n胜率分布:")
        bins = [0, 20, 40, 50, 60, 80, 100]
        labels = ['0-20%', '20-40%', '40-50%', '50-60%', '60-80%', '80-100%']
        combined['wr_bin'] = pd.cut(combined['win_rate'], bins=bins, labels=labels)
        for label in labels:
            cnt = (combined['wr_bin']==label).sum()
            if cnt > 0:
                avg_ret = combined[combined['wr_bin']==label]['total_return'].mean()
                print(f"  胜率{label}: {cnt}只 ({cnt/len(combined)*100:.1f}%), 平均收益{avg_ret:+.2f}%")

if __name__ == '__main__':
    main()
