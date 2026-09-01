"""
V8策略全市场扫描：BB Lower + RSI超卖 + 跟踪止损
- 入场：复权收盘 < BB Lower(20,2) 且 RSI(14) < 30
- 出场：跟踪止损（绿的且收盘<前一日收盘）+ 时间止损（20天）
- 加仓：BB Lower + RSI<30，最多5层，每层20%
- 止损优先，触发止损当天不加仓
- 全市场5777只股票，独立全仓回测
"""
import sys, os, time, gc
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import numpy as np
import glob
from engine.commission import FeeCalculator

def calc_rsi(close, period=14):
    """Wilder平滑法计算RSI"""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    rsi = pd.Series(np.nan, index=close.index)
    if len(close) <= period:
        return rsi
    # 初始平均
    avg_gain = gain.iloc[1:period+1].mean()
    avg_loss = loss.iloc[1:period+1].mean()
    if avg_loss == 0:
        rsi.iloc[period] = 100
    else:
        rsi.iloc[period] = 100 - (100 / (1 + avg_gain / avg_loss))
    # Wilder平滑
    for i in range(period+1, len(close)):
        avg_gain = (avg_gain * (period-1) + gain.iloc[i]) / period
        avg_loss = (avg_loss * (period-1) + loss.iloc[i]) / period
        if avg_loss == 0:
            rsi.iloc[i] = 100
        else:
            rsi.iloc[i] = 100 - (100 / (1 + avg_gain / avg_loss))
    return rsi

def backtest_single(daily_df, adj_df, fee_calc):
    """单股回测V8策略"""
    daily = daily_df.sort_values('date').reset_index(drop=True)
    daily['date'] = pd.to_datetime(daily['date'])
    adj = adj_df.sort_values('date').reset_index(drop=True)
    adj['date'] = pd.to_datetime(adj['date'])
    merged = pd.merge(daily[['date','open','high','low','close','vol','amount','pre_close']],
                      adj[['date','adj_factor']], on='date', how='inner')
    merged = merged[(merged['date']>='2020-01-01') & (merged['date']<='2026-08-25')]
    if len(merged) < 60:
        return [], {}

    # 计算指标
    merged['adj_close'] = merged['close'] * merged['adj_factor']
    merged['bb_mid'] = merged['adj_close'].rolling(20).mean()
    merged['bb_std'] = merged['adj_close'].rolling(20).std()
    merged['bb_lower'] = merged['bb_mid'] - 2 * merged['bb_std']
    merged['rsi'] = calc_rsi(merged['adj_close'], 14)
    merged['is_limit_down'] = merged['close'] <= merged['pre_close'] * 0.905
    merged['is_red'] = merged['close'] > merged['pre_close']  # 红的=收盘上涨

    # 回测
    cash = 1_000_000
    position = None  # {shares, avg_cost, level, entry_idx, holding_days, prev_close}
    trades = []

    for i in range(len(merged)):
        row = merged.iloc[i]
        date = merged.index[i]

        # 跳过数据不足的前几天
        if pd.isna(row['bb_lower']) or pd.isna(row['rsi']):
            continue

        if position is not None:
            # ===== 持仓处理 =====
            # 买入当日不判断（T+1），holding_days从0开始
            if position['holding_days'] == 0:
                position['holding_days'] += 1
                position['prev_close'] = row['close']
                continue

            # 停牌（成交量为0）→ 跳过，holding_days不增加
            if row['vol'] == 0:
                continue

            # 跌停 → 无法卖出，也不加仓
            if row['is_limit_down']:
                position['holding_days'] += 1
                position['prev_close'] = row['close']
                continue

            sold = False

            # Step 1: 时间止损（最高优先级）
            if position['holding_days'] >= 20:
                shares = position['shares']
                fee = fee_calc.calculate('sell', row['close'], shares)
                cash += fee.net_cash_flow
                pnl = (fee.price - position['avg_cost']) * shares - fee.total_fee
                trades.append({'date': merged['date'].iloc[i], 'action':'SELL', 'price':fee.price,
                    'shares':shares, 'amount':fee.amount, 'level':position['level'],
                    'avg_cost':position['avg_cost'], 'pnl':pnl, 'reason':'TIME_STOP',
                    'holding_days':position['holding_days']})
                position = None
                sold = True

            # Step 2: 跟踪止损（绿的且收盘<前一日收盘）
            if not sold and not row['is_red'] and row['close'] < position['prev_close']:
                shares = position['shares']
                fee = fee_calc.calculate('sell', row['close'], shares)
                cash += fee.net_cash_flow
                pnl = (fee.price - position['avg_cost']) * shares - fee.total_fee
                trades.append({'date': merged['date'].iloc[i], 'action':'SELL', 'price':fee.price,
                    'shares':shares, 'amount':fee.amount, 'level':position['level'],
                    'avg_cost':position['avg_cost'], 'pnl':pnl, 'reason':'TRAILING_STOP',
                    'holding_days':position['holding_days']})
                position = None
                sold = True

            # Step 3: 没触发止损 → 判断加仓
            if not sold and position['level'] < 5:
                if row['adj_close'] < row['bb_lower'] and row['rsi'] < 30 and not row['is_limit_down']:
                    buy_price = row['close']
                    target_amount = 1_000_000 * 0.20  # 每层20%
                    shares = int(target_amount / buy_price / 100) * 100
                    if shares >= 100:
                        fee = fee_calc.calculate('buy', buy_price, shares)
                        if cash >= -fee.net_cash_flow:
                            cash += fee.net_cash_flow
                            old_cost = position['avg_cost'] * position['shares']
                            new_cost = fee.amount + fee.total_fee
                            total_shares = position['shares'] + shares
                            position['avg_cost'] = (old_cost + new_cost) / total_shares
                            position['shares'] = total_shares
                            position['level'] += 1
                            trades.append({'date': merged['date'].iloc[i], 'action':'BUY', 'price':fee.price,
                                'shares':shares, 'amount':fee.amount, 'level':position['level'],
                                'avg_cost':position['avg_cost'], 'pnl':0, 'reason':'ADD_POSITION',
                                'holding_days':position['holding_days']})

            # 更新状态
            if position is not None:
                position['holding_days'] += 1
                position['prev_close'] = row['close']

        # ===== 空仓处理：判断入场 =====
        if position is None:
            # 状态过滤
            if row['is_limit_down']:
                continue
            # 入场信号：BB Lower + RSI<30
            if row['adj_close'] < row['bb_lower'] and row['rsi'] < 30:
                buy_price = row['close']
                target_amount = 1_000_000 * 0.20
                shares = int(target_amount / buy_price / 100) * 100
                if shares >= 100:
                    fee = fee_calc.calculate('buy', buy_price, shares)
                    if cash >= -fee.net_cash_flow:
                        cash += fee.net_cash_flow
                        position = {
                            'shares': shares,
                            'avg_cost': (fee.amount + fee.total_fee) / shares,
                            'level': 1,
                            'holding_days': 0,
                            'prev_close': row['close'],
                        }
                        trades.append({'date': merged['date'].iloc[i], 'action':'BUY', 'price':fee.price,
                            'shares':shares, 'amount':fee.amount, 'level':1,
                            'avg_cost':position['avg_cost'], 'pnl':0, 'reason':'INITIAL_ENTRY',
                            'holding_days':0})

    # 统计
    sell_trades = [t for t in trades if t['action']=='SELL']
    n_trades = len(sell_trades)
    if n_trades > 0:
        wins = [t for t in sell_trades if t['pnl']>0]
        losses = [t for t in sell_trades if t['pnl']<=0]
        win_rate = len(wins)/n_trades*100
        avg_win = np.mean([t['pnl'] for t in wins]) if wins else 0
        avg_loss = np.mean([t['pnl'] for t in losses]) if losses else 0
        total_pnl = sum(t['pnl'] for t in sell_trades)
        total_return = total_pnl / 1_000_000 * 100
        avg_holding = np.mean([t['holding_days'] for t in sell_trades])
        reason_counts = {}
        for t in sell_trades:
            reason_counts[t['reason']] = reason_counts.get(t['reason'], 0) + 1
    else:
        win_rate=avg_win=avg_loss=total_pnl=total_return=avg_holding=0
        reason_counts={}

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
    daily_files = sorted(glob.glob(os.path.join(project_root, 'data', 'raw', 'daily', '*.parquet')))
    print(f'总股票数: {len(daily_files)}', flush=True)

    result_file = os.path.join(project_root, 'results', 'full_market_v8_rsi_trailing.csv')
    existing = pd.DataFrame()
    processed = set()
    if os.path.exists(result_file):
        existing = pd.read_csv(result_file)
        processed = set(existing['ts_code'].tolist())
        print(f'已处理: {len(processed)} 只', flush=True)

    results = []
    t0 = time.time()
    count = 0
    error_count = 0

    for fpath in daily_files:
        ts_code = os.path.basename(fpath).replace('.parquet', '')
        if ts_code in processed:
            continue
        try:
            daily = pd.read_parquet(fpath)
            adj_path = os.path.join(project_root, 'data', 'raw', 'adj_factor', f'{ts_code}.parquet')
            if not os.path.exists(adj_path):
                continue
            adj = pd.read_parquet(adj_path)
            trades, stats = backtest_single(daily, adj, fee_calc)
        except Exception as e:
            error_count += 1
            continue

        if not stats or stats.get('n_trades', 0) == 0:
            continue

        results.append({
            'ts_code': ts_code,
            'n_trades': stats['n_trades'],
            'win_rate': stats['win_rate'],
            'avg_win': stats['avg_win'],
            'avg_loss': stats['avg_loss'],
            'total_pnl': stats['total_pnl'],
            'total_return': stats['total_return'],
            'avg_holding': stats['avg_holding'],
            'trailing_count': stats['reason_counts'].get('TRAILING_STOP', 0),
            'timestop_count': stats['reason_counts'].get('TIME_STOP', 0),
        })
        count += 1

        if count % 200 == 0:
            elapsed = time.time() - t0
            speed = count / elapsed * 60
            remaining = (len(daily_files) - len(processed) - count) / max(speed, 1)
            print(f'  已处理{count}只有交易(累计{len(processed)+count}), 速度{speed:.0f}只/分, 剩余{remaining:.1f}分, 错误{error_count}', flush=True)
            new_df = pd.DataFrame(results)
            combined = pd.concat([existing, new_df], ignore_index=True)
            combined.to_csv(result_file, index=False)
            existing = combined
            processed.update([r['ts_code'] for r in results])
            results = []
            gc.collect()

    if results:
        new_df = pd.DataFrame(results)
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = existing
    combined.to_csv(result_file, index=False)
    print(f'\n完成！共{len(combined)}只有交易的股票, 错误{error_count}只, 耗时{time.time()-t0:.1f}秒', flush=True)

if __name__ == '__main__':
    main()
