"""
V8多股组合回测：同时持有3只 + 市值过滤>=30亿
- 入场：BB Lower(20,2) + RSI(14)<30 + 市值>=30亿 + 非ST + 非停牌 + 非跌停
- 选股：按当日成交额从大到小排序，选Top候选
- 持仓：最多3只，每只最多3层（初始+2次加仓）
- 每层仓位：总资金 / 3 / 3 = 11.1%
- 出场：跟踪止损（绿的且收盘<前一日收盘）+ 时间止损20天
- 止损优先，触发止损当天不加仓
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import numpy as np
import glob
from engine.commission import FeeCalculator

def calc_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    rsi = pd.Series(np.nan, index=close.index)
    if len(close) <= period:
        return rsi
    avg_gain = gain.iloc[1:period+1].mean()
    avg_loss = loss.iloc[1:period+1].mean()
    if avg_loss == 0:
        rsi.iloc[period] = 100
    else:
        rsi.iloc[period] = 100 - (100 / (1 + avg_gain / avg_loss))
    for i in range(period+1, len(close)):
        avg_gain = (avg_gain * (period-1) + gain.iloc[i]) / period
        avg_loss = (avg_loss * (period-1) + loss.iloc[i]) / period
        if avg_loss == 0:
            rsi.iloc[i] = 100
        else:
            rsi.iloc[i] = 100 - (100 / (1 + avg_gain / avg_loss))
    return rsi

def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    fee_calc = FeeCalculator()
    INITIAL_CASH = 1_000_000
    MAX_POSITIONS = 3
    MAX_LEVELS = 3  # 每只最多3层
    POSITION_PER_LEVEL = 1.0 / MAX_POSITIONS / MAX_LEVELS  # 每层11.1%
    MAX_HOLDING_DAYS = 20
    MIN_MV = 30  # 亿

    print(f'参数: 最多{MAX_POSITIONS}只, 每只最多{MAX_LEVELS}层, 每层{POSITION_PER_LEVEL*100:.1f}%, 市值>={MIN_MV}亿', flush=True)

    # 加载市值
    mv_df = pd.read_csv(os.path.join(project_root, 'data', 'raw', 'daily_basic_20241231.csv'))
    mv_df['total_mv_yi'] = mv_df['total_mv'] / 10000
    mv_dict = dict(zip(mv_df['ts_code'], mv_df['total_mv_yi']))
    print(f'市值数据: {len(mv_dict)}只', flush=True)

    # 加载ST股票列表
    basic_df = pd.read_csv(os.path.join(project_root, 'data', 'raw', 'stock_basic.csv'))
    st_codes = set(basic_df[basic_df['name'].str.contains('ST', na=False)]['ts_code'].tolist())
    print(f'ST股票: {len(st_codes)}只', flush=True)

    # 预加载所有股票数据并计算指标
    daily_files = sorted(glob.glob(os.path.join(project_root, 'data', 'raw', 'daily', '*.parquet')))
    print(f'加载股票数据并计算指标...', flush=True)
    symbol_data = {}
    for fpath in daily_files:
        ts_code = os.path.basename(fpath).replace('.parquet', '')
        # 市值过滤
        if mv_dict.get(ts_code, 0) < MIN_MV:
            continue
        # ST过滤
        if ts_code in st_codes:
            continue
        try:
            daily = pd.read_parquet(fpath)
            adj_path = os.path.join(project_root, 'data', 'raw', 'adj_factor', f'{ts_code}.parquet')
            if not os.path.exists(adj_path):
                continue
            adj = pd.read_parquet(adj_path)
        except:
            continue

        daily = daily.sort_values('date').reset_index(drop=True)
        daily['date'] = pd.to_datetime(daily['date'])
        adj = adj.sort_values('date').reset_index(drop=True)
        adj['date'] = pd.to_datetime(adj['date'])
        merged = pd.merge(daily[['date','open','high','low','close','vol','amount','pre_close']],
                          adj[['date','adj_factor']], on='date', how='inner')
        merged = merged[(merged['date']>='2020-01-01') & (merged['date']<='2026-08-25')]
        if len(merged) < 60:
            continue
        merged = merged.set_index('date')
        merged['adj_close'] = merged['close'] * merged['adj_factor']
        merged['bb_mid'] = merged['adj_close'].rolling(20).mean()
        merged['bb_std'] = merged['adj_close'].rolling(20).std()
        merged['bb_lower'] = merged['bb_mid'] - 2 * merged['bb_std']
        merged['rsi'] = calc_rsi(merged['adj_close'], 14)
        merged['is_limit_down'] = merged['close'] <= merged['pre_close'] * 0.905
        merged['is_red'] = merged['close'] > merged['pre_close']
        symbol_data[ts_code] = merged

    print(f'加载完成: {len(symbol_data)}只股票（市值>={MIN_MV}亿，非ST）', flush=True)

    # 获取所有交易日
    all_dates = sorted(set().union(*[set(sd.index) for sd in symbol_data.values()]))
    all_dates = [d for d in all_dates if pd.Timestamp('2020-01-01') <= d <= pd.Timestamp('2026-08-25')]
    print(f'交易日数: {len(all_dates)}', flush=True)

    # 回测主循环
    cash = INITIAL_CASH
    positions = {}  # {ts_code: {shares, avg_cost, level, holding_days, prev_close}}
    trades = []
    nav = []

    t0 = time.time()
    for i, date in enumerate(all_dates):
        # 计算总权益
        total_position_value = 0
        for ts, pos in positions.items():
            if ts in symbol_data and date in symbol_data[ts].index:
                total_position_value += pos['shares'] * symbol_data[ts].loc[date, 'close']
            else:
                total_position_value += pos['shares'] * pos['avg_cost']
        total_equity = cash + total_position_value
        nav.append({'date': date, 'total_equity': total_equity, 'cash': cash, 'position_value': total_position_value, 'n_positions': len(positions)})

        # ===== 处理已有持仓：止损 + 加仓 =====
        to_sell = []
        for ts, pos in list(positions.items()):
            if ts not in symbol_data or date not in symbol_data[ts].index:
                # 停牌，跳过
                continue
            row = symbol_data[ts].loc[date]

            # 买入当日不判断（T+1）
            if pos['holding_days'] == 0:
                pos['holding_days'] += 1
                pos['prev_close'] = row['close']
                continue

            # 跌停无法卖出
            if row['is_limit_down']:
                pos['holding_days'] += 1
                pos['prev_close'] = row['close']
                continue

            sold = False

            # 1. 时间止损
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

            # 2. 跟踪止损（绿的且收盘<前一日收盘）
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

            # 3. 没触发止损 → 判断加仓（止损优先，触发止损当天不加仓）
            if not sold and pos['level'] < MAX_LEVELS:
                if not pd.isna(row['bb_lower']) and row['adj_close'] < row['bb_lower'] and row['rsi'] < 30 and not row['is_limit_down']:
                    buy_price = row['close']
                    target_amount = INITIAL_CASH * POSITION_PER_LEVEL  # 用初始资金计算每层仓位
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

            # 更新状态
            if ts in positions:
                pos['holding_days'] += 1
                pos['prev_close'] = row['close']

        # 执行卖出
        for ts in to_sell:
            if ts in positions:
                del positions[ts]

        # ===== 新买入 =====
        if len(positions) < MAX_POSITIONS:
            # 找当天满足入场条件的候选股票
            candidates = []
            for ts, sd in symbol_data.items():
                if ts in positions:
                    continue
                if date not in sd.index:
                    continue
                row = sd.loc[date]
                if pd.isna(row['bb_lower']) or pd.isna(row['rsi']):
                    continue
                if row['adj_close'] < row['bb_lower'] and row['rsi'] < 30 and not row['is_limit_down'] and row['vol'] > 0:
                    candidates.append((ts, row['amount']))
            # 按成交额排序
            candidates.sort(key=lambda x: x[1], reverse=True)

            for ts, amount in candidates:
                if len(positions) >= MAX_POSITIONS:
                    break
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

        if i % 200 == 0 and i > 0:
            elapsed = time.time() - t0
            print(f'  进度: {i}/{len(all_dates)}, 持仓{len(positions)}只, 权益{total_equity:,.0f}, 耗时{elapsed:.0f}s', flush=True)

    print(f'回测完成, 耗时{time.time()-t0:.1f}s', flush=True)

    # 结果分析
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
    print(f'V8多股组合回测结果（{MAX_POSITIONS}只, 每只{MAX_LEVELS}层, 市值>={MIN_MV}亿）', flush=True)
    print(f'{"="*70}', flush=True)
    print(f'最终权益:     {final_equity:,.2f}', flush=True)
    print(f'累计收益:     {total_return:+.2f}%', flush=True)
    print(f'年化收益:     {annual_return:+.2f}%', flush=True)
    print(f'最大回撤:     {max_dd:.2f}%', flush=True)
    print(f'Sharpe:       {sharpe:.3f}', flush=True)
    print(f'买入笔数:     {len(buy_trades)}', flush=True)
    print(f'卖出笔数:     {n_sells}', flush=True)
    print(f'胜率:         {win_rate:.1f}%', flush=True)
    print(f'平均盈利:     {avg_win:,.2f}', flush=True)
    print(f'平均亏损:     {avg_loss:,.2f}', flush=True)
    print(f'平均持仓:     {avg_holding:.1f}个交易日', flush=True)
    print(f'总盈亏:       {total_pnl:,.2f}', flush=True)

    if n_sells > 0:
        print(f'\n=== 卖出原因分布 ===', flush=True)
        for reason in sorted(sell_trades['reason'].unique()):
            cnt = (sell_trades['reason']==reason).sum()
            sub = sell_trades[sell_trades['reason']==reason]
            wr = (sub['pnl']>0).mean()*100
            avg_pnl = sub['pnl'].mean()
            print(f'  {reason:<20}: {cnt:>4}笔 ({cnt/n_sells*100:>5.1f}%), 胜率{wr:>3.0f}%, 平均盈亏{avg_pnl:>8,.0f}', flush=True)

    # 年度收益
    nav_df['year'] = nav_df.index.year
    print(f'\n=== 年度收益 ===', flush=True)
    for year in sorted(nav_df['year'].unique()):
        yd = nav_df[nav_df['year']==year]
        if len(yd) > 1:
            ys = yd['total_equity'].iloc[0]
            ye = yd['total_equity'].iloc[-1]
            yr = (ye - ys) / ys * 100
            print(f'{year}: {yr:+.2f}%', flush=True)

    # 保存
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    tag = f'v8_multi{MAX_POSITIONS}_mv{MIN_MV}'
    nav_path = os.path.join(project_root, 'results', 'reports', f'nav_{tag}_{timestamp}.csv')
    trades_path = os.path.join(project_root, 'results', 'trades', f'trades_{tag}_{timestamp}.csv')
    nav_df.to_csv(nav_path)
    trades_df.to_csv(trades_path, index=False)
    print(f'\n净值曲线: {nav_path}', flush=True)
    print(f'交易记录: {trades_path}', flush=True)

if __name__ == '__main__':
    main()
