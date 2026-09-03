"""
V8多股组合回测（使用预计算候选列表）
- 同时持有3只，每只最多3层，每层11.1%
- 跟踪止损 + 时间止损20天
- 市值>=30亿，非ST
"""
import sys, os, time, pickle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import numpy as np
import glob
from engine.commission import FeeCalculator
from strategy_v8_multi import calc_rsi

def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    fee_calc = FeeCalculator()
    INITIAL_CASH = 1_000_000
    MAX_POSITIONS = 3
    MAX_LEVELS = 3
    POSITION_PER_LEVEL = 1.0 / MAX_POSITIONS / MAX_LEVELS
    MAX_HOLDING_DAYS = 20

    print(f'参数: {MAX_POSITIONS}只, 每只{MAX_LEVELS}层, 每层{POSITION_PER_LEVEL*100:.1f}%', flush=True)

    # 加载预计算候选
    with open(os.path.join(project_root, 'data', 'signal_dates_v8.pkl'), 'rb') as f:
        signal_dates = pickle.load(f)
    print(f'候选信号日: {len(signal_dates)}个', flush=True)

    # 只加载Top10候选股票的数据（减少内存）
    top10_codes = set()
    for date, cands in signal_dates.items():
        for ts, amt in cands[:10]:
            top10_codes.add(ts)
    print(f'Top10候选涉及股票: {len(top10_codes)}只', flush=True)

    symbol_data = {}
    for ts_code in top10_codes:
        try:
            daily = pd.read_parquet(os.path.join(project_root, 'data', 'raw', 'daily', f'{ts_code}.parquet'))
            adj = pd.read_parquet(os.path.join(project_root, 'data', 'raw', 'adj_factor', f'{ts_code}.parquet'))
            daily = daily.sort_values('date').reset_index(drop=True)
            daily['date'] = pd.to_datetime(daily['date'])
            adj = adj.sort_values('date').reset_index(drop=True)
            adj['date'] = pd.to_datetime(adj['date'])
            merged = pd.merge(daily[['date','open','high','low','close','vol','amount','pre_close']],
                              adj[['date','adj_factor']], on='date', how='inner')
            merged = merged[(merged['date']>='2020-01-01') & (merged['date']<='2026-08-25')]
            merged = merged.set_index('date')
            merged['is_limit_down'] = merged['close'] <= merged['pre_close'] * 0.905
            merged['is_red'] = merged['close'] > merged['pre_close']
            symbol_data[ts_code] = merged[['open','high','low','close','vol','amount','pre_close','is_limit_down','is_red']]
        except:
            continue
    print(f'加载完成: {len(symbol_data)}只', flush=True)

    # 所有交易日
    all_dates = sorted(set().union(*[set(sd.index) for sd in symbol_data.values()]))
    all_dates = [d for d in all_dates if pd.Timestamp('2020-01-01') <= d <= pd.Timestamp('2026-08-25')]
    print(f'交易日: {len(all_dates)}个', flush=True)

    # 回测主循环
    cash = INITIAL_CASH
    positions = {}
    trades = []
    nav = []

    t0 = time.time()
    for i, date in enumerate(all_dates):
        # 总权益
        total_position_value = 0
        for ts, pos in positions.items():
            if ts in symbol_data and date in symbol_data[ts].index:
                total_position_value += pos['shares'] * symbol_data[ts].loc[date, 'close']
            else:
                total_position_value += pos['shares'] * pos['avg_cost']
        total_equity = cash + total_position_value
        nav.append({'date': date, 'total_equity': total_equity, 'cash': cash, 'position_value': total_position_value, 'n_positions': len(positions)})

        # 处理持仓
        to_sell = []
        for ts, pos in list(positions.items()):
            if ts not in symbol_data or date not in symbol_data[ts].index:
                continue
            row = symbol_data[ts].loc[date]

            if pos['holding_days'] == 0:
                pos['holding_days'] += 1
                pos['prev_close'] = row['close']
                continue

            if row['is_limit_down']:
                pos['holding_days'] += 1
                pos['prev_close'] = row['close']
                continue

            sold = False

            # 时间止损
            if pos['holding_days'] >= MAX_HOLDING_DAYS:
                shares = pos['shares']
                fee = fee_calc.calculate('sell', row['close'], shares)
                cash += fee.net_cash_flow
                pnl = (fee.price - pos['avg_cost']) * shares - fee.total_fee
                trades.append({'date': date, 'ts_code': ts, 'action': 'SELL', 'price': fee.price,
                    'shares': shares, 'amount': fee.amount, 'level': pos['level'],
                    'avg_cost': pos['avg_cost'], 'pnl': pnl, 'reason': 'TIME_STOP',
                    'holding_days': pos['holding_days']})
                to_sell.append(ts)
                sold = True

            # 跟踪止损
            if not sold and not row['is_red'] and row['close'] < pos['prev_close']:
                shares = pos['shares']
                fee = fee_calc.calculate('sell', row['close'], shares)
                cash += fee.net_cash_flow
                pnl = (fee.price - pos['avg_cost']) * shares - fee.total_fee
                trades.append({'date': date, 'ts_code': ts, 'action': 'SELL', 'price': fee.price,
                    'shares': shares, 'amount': fee.amount, 'level': pos['level'],
                    'avg_cost': pos['avg_cost'], 'pnl': pnl, 'reason': 'TRAILING_STOP',
                    'holding_days': pos['holding_days']})
                to_sell.append(ts)
                sold = True

            # 加仓（需要BB+RSI信号，从预计算候选中判断）
            if not sold and pos['level'] < MAX_LEVELS:
                cands = signal_dates.get(date, [])
                cand_codes = set(ts for ts, amt in cands)
                if ts in cand_codes and not row['is_limit_down']:
                    buy_price = row['close']
                    target_amount = INITIAL_CASH * POSITION_PER_LEVEL
                    shares = int(target_amount / buy_price / 100) * 100
                    if shares >= 100:
                        fee = fee_calc.calculate('buy', buy_price, shares)
                        if cash >= -fee.net_cash_flow:
                            cash += fee.net_cash_flow
                            old_cost = pos['avg_cost'] * pos['shares']
                            new_cost = fee.amount + fee.total_fee
                            total_shares = pos['shares'] + shares
                            pos['avg_cost'] = (old_cost + new_cost) / total_shares
                            pos['shares'] = total_shares
                            pos['level'] += 1
                            trades.append({'date': date, 'ts_code': ts, 'action': 'BUY', 'price': fee.price,
                                'shares': shares, 'amount': fee.amount, 'level': pos['level'],
                                'avg_cost': pos['avg_cost'], 'pnl': 0, 'reason': 'ADD_POSITION',
                                'holding_days': pos['holding_days']})

            if ts in positions:
                pos['holding_days'] += 1
                pos['prev_close'] = row['close']

        for ts in to_sell:
            if ts in positions:
                del positions[ts]

        # 新买入
        if len(positions) < MAX_POSITIONS and date in signal_dates:
            for ts, amount in signal_dates[date]:
                if len(positions) >= MAX_POSITIONS:
                    break
                if ts in positions:
                    continue
                if ts not in symbol_data or date not in symbol_data[ts].index:
                    continue
                row = symbol_data[ts].loc[date]
                buy_price = row['close']
                target_amount = INITIAL_CASH * POSITION_PER_LEVEL
                shares = int(target_amount / buy_price / 100) * 100
                if shares < 100:
                    continue
                fee = fee_calc.calculate('buy', buy_price, shares)
                if cash < -fee.net_cash_flow:
                    continue
                cash += fee.net_cash_flow
                positions[ts] = {
                    'shares': shares,
                    'avg_cost': (fee.amount + fee.total_fee) / shares,
                    'level': 1,
                    'holding_days': 0,
                    'prev_close': row['close'],
                }
                trades.append({'date': date, 'ts_code': ts, 'action': 'BUY', 'price': fee.price,
                    'shares': shares, 'amount': fee.amount, 'level': 1,
                    'avg_cost': positions[ts]['avg_cost'], 'pnl': 0, 'reason': 'INITIAL_ENTRY',
                    'holding_days': 0})

        if i % 300 == 0 and i > 0:
            print(f'  进度{ i}/{len(all_dates)}, 持仓{len(positions)}只, 权益{total_equity:,.0f}, 耗时{time.time()-t0:.0f}s', flush=True)

    print(f'回测完成, 耗时{time.time()-t0:.1f}s', flush=True)

    # 分析
    nav_df = pd.DataFrame(nav).set_index('date')
    trades_df = pd.DataFrame(trades)
    final_equity = nav_df['total_equity'].iloc[-1]
    total_return = (final_equity - INITIAL_CASH) / INITIAL_CASH * 100
    equities = nav_df['total_equity'].values
    peak = equities[0]
    max_dd = 0
    for eq in equities:
        if eq > peak: peak = eq
        dd = (eq - peak) / peak * 100
        if dd < max_dd: max_dd = dd
    n_days = len(nav_df)
    annual_return = ((final_equity / INITIAL_CASH) ** (252 / max(n_days,1)) - 1) * 100
    daily_rets = nav_df['total_equity'].pct_change().dropna()
    sharpe = (daily_rets.mean() / daily_rets.std() * np.sqrt(252)) if len(daily_rets)>1 and daily_rets.std()>0 else 0
    sell_trades = trades_df[trades_df['action']=='SELL'] if len(trades_df)>0 else pd.DataFrame()
    n_sells = len(sell_trades)
    buy_trades = trades_df[trades_df['action']=='BUY'] if len(trades_df)>0 else pd.DataFrame()
    if n_sells > 0:
        win_trades = sell_trades[sell_trades['pnl'] > 0]
        win_rate = len(win_trades) / n_sells * 100
        avg_win = win_trades['pnl'].mean() if len(win_trades)>0 else 0
        lose_trades = sell_trades[sell_trades['pnl'] <= 0]
        avg_loss = lose_trades['pnl'].mean() if len(lose_trades)>0 else 0
        avg_holding = sell_trades['holding_days'].mean()
        total_pnl = sell_trades['pnl'].sum()
    else:
        win_rate = avg_win = avg_loss = avg_holding = total_pnl = 0

    print(f'\n{"="*70}', flush=True)
    print(f'V8多股组合（{MAX_POSITIONS}只, 每只{MAX_LEVELS}层, 市值>=30亿）', flush=True)
    print(f'{"="*70}', flush=True)
    print(f'最终权益: {final_equity:,.2f}', flush=True)
    print(f'累计收益: {total_return:+.2f}%', flush=True)
    print(f'年化收益: {annual_return:+.2f}%', flush=True)
    print(f'最大回撤: {max_dd:.2f}%', flush=True)
    print(f'Sharpe: {sharpe:.3f}', flush=True)
    print(f'买入: {len(buy_trades)}笔, 卖出: {n_sells}笔', flush=True)
    print(f'胜率: {win_rate:.1f}%', flush=True)
    print(f'平均盈利: {avg_win:,.2f}, 平均亏损: {avg_loss:,.2f}', flush=True)
    print(f'平均持仓: {avg_holding:.1f}天', flush=True)
    print(f'总盈亏: {total_pnl:,.2f}', flush=True)

    if n_sells > 0:
        print(f'\n卖出原因:', flush=True)
        for reason in sorted(sell_trades['reason'].unique()):
            cnt = (sell_trades['reason']==reason).sum()
            sub = sell_trades[sell_trades['reason']==reason]
            wr = (sub['pnl']>0).mean()*100
            avg_pnl = sub['pnl'].mean()
            print(f'  {reason}: {cnt}笔({cnt/n_sells*100:.1f}%), 胜率{wr:.0f}%, 平均盈亏{avg_pnl:,.0f}', flush=True)

    nav_df['year'] = nav_df.index.year
    print(f'\n年度收益:', flush=True)
    for year in sorted(nav_df['year'].unique()):
        yd = nav_df[nav_df['year']==year]
        if len(yd) > 1:
            yr = (yd['total_equity'].iloc[-1] - yd['total_equity'].iloc[0]) / yd['total_equity'].iloc[0] * 100
            print(f'  {year}: {yr:+.2f}%', flush=True)

    timestamp = time.strftime('%Y%m%d_%H%M%S')
    nav_df.to_csv(f'results/reports/nav_v8_multi3_mv30_{timestamp}.csv')
    trades_df.to_csv(f'results/trades/trades_v8_multi3_mv30_{timestamp}.csv', index=False)
    print(f'\n结果已保存', flush=True)

if __name__ == '__main__':
    main()
