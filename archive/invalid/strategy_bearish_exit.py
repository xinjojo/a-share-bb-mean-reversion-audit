"""
阳线持有阴线卖出策略（趋势跟踪型持仓）
- 选股：成交额Top1
- 买入：BB Lower信号，收盘价买入
- 加仓：持仓期间再次跌破BB Lower，加20%，最多5层
- 卖出：买入次日起，阴线(close<=open)则收盘价卖出
- 无止损，T+1，跌停不买
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import numpy as np
from data_loader.storage import DataStorage
from engine.trading_rules import TradingRules
from engine.commission import FeeCalculator

def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    storage = DataStorage(os.path.join(project_root, 'data', 'raw'))
    rules = TradingRules()
    fee_calc = FeeCalculator()

    START_DATE = '2020-01-01'
    END_DATE = '2026-08-25'
    INITIAL_CASH = 1_000_000
    BB_PERIOD = 20
    BB_STD = 2.0
    MAX_LEVELS = 5
    POSITION_PER_LEVEL = 0.20
    MIN_LISTING_DAYS = 60

    print("=" * 70)
    print("阳线持有阴线卖出策略：Top1 + BB Lower + 5层加仓 + 阴线收盘卖")
    print(f"回测区间：{START_DATE} ~ {END_DATE}")
    print("=" * 70)

    t0 = time.time()

    # 交易日历
    cal = storage.load_trade_cal()
    cal['date'] = pd.to_datetime(cal['date'])
    trade_days = cal[(cal['is_open']==1) & (cal['date']>=START_DATE) & (cal['date']<=END_DATE)]['date'].sort_values().values
    print(f"交易日数: {len(trade_days)}")

    # 预计算每天候选池（Top20备选）
    print("预计算候选池...")
    daily_candidates = {}
    for i, d in enumerate(trade_days):
        if i % 200 == 0:
            print(f"  {i}/{len(trade_days)}")
        d_str = pd.Timestamp(d).strftime('%Y-%m-%d')
        df = storage.get_top_n_by_amount(date=d_str, n=20, exclude_st=True, exclude_suspended=True)
        daily_candidates[d] = df['ts_code'].tolist() if not df.empty else []
    print(f"候选池预计算完成, 耗时: {time.time()-t0:.1f}s")

    # 加载所有可能用到的股票数据
    all_symbols = set()
    for syms in daily_candidates.values():
        all_symbols.update(syms)
    print(f"需加载股票数: {len(all_symbols)}")

    symbol_data = {}
    for ts in all_symbols:
        daily = storage.load_daily(ts)
        adj = storage.load_adj_factor(ts)
        if daily.empty or adj.empty: continue
        daily = daily.sort_values('date').reset_index(drop=True)
        daily['date'] = pd.to_datetime(daily['date'])
        adj = adj.sort_values('date').reset_index(drop=True)
        adj['date'] = pd.to_datetime(adj['date'])
        merged = pd.merge(daily[['date','open','high','low','close','vol','amount','pre_close']],
                          adj[['date','adj_factor']], on='date', how='inner')
        merged = merged.set_index('date')
        # 布林带（用后复权价计算指标）
        merged['adj_close'] = merged['close'] * merged['adj_factor']
        merged['bb_mid'] = merged['adj_close'].rolling(BB_PERIOD).mean()
        merged['bb_std'] = merged['adj_close'].rolling(BB_PERIOD).std()
        merged['bb_lower'] = merged['bb_mid'] - BB_STD * merged['bb_std']
        # 跌停判断（用不复权价）
        merged['is_limit_down'] = merged['close'] <= merged['pre_close'] * 0.905
        symbol_data[ts] = merged
    print(f"成功加载: {len(symbol_data)}只, 耗时: {time.time()-t0:.1f}s")

    # ===== 回测主循环 =====
    cash = INITIAL_CASH
    position = None  # {'ts_code', 'shares', 'avg_cost', 'level', 'entry_date', 'buy_dates': []}
    trades = []
    nav = []

    print("开始回测...")
    t1 = time.time()

    for i, d in enumerate(trade_days):
        d_ts = pd.Timestamp(d)
        d_str = d_ts.strftime('%Y-%m-%d')

        # 当日权益
        if position and position['ts_code'] in symbol_data:
            sd = symbol_data[position['ts_code']]
            if d_ts in sd.index:
                market_value = position['shares'] * sd.loc[d_ts, 'close']
            else:
                market_value = position['shares'] * position['avg_cost']
        else:
            market_value = 0
        total_equity = cash + market_value
        nav.append({'date': d_ts, 'total_equity': total_equity, 'cash': cash, 'position_value': market_value})

        # 如果停牌，跳过
        if position and position['ts_code'] in symbol_data:
            sd = symbol_data[position['ts_code']]
            if d_ts not in sd.index:
                continue

        # ===== 卖出判断（阴线卖出）=====
        if position:
            ts = position['ts_code']
            sd = symbol_data[ts]
            if d_ts in sd.index:
                row = sd.loc[d_ts]
                entry_date = position['entry_date']
                days_held = (d_ts - entry_date).days

                # T+1：买入当天不能卖，必须从次日开始判断
                if d_ts > entry_date:
                    # 阴线判断：close <= open（十字星算阴线）
                    is_bearish = row['close'] <= row['open']

                    if is_bearish:
                        # 收盘价卖出
                        sell_price = row['close']
                        sellable = position['shares']  # T+1已满足
                        if sellable > 0:
                            fee = fee_calc.calculate('sell', sell_price, sellable)
                            cash += fee.net_cash_flow
                            pnl = (fee.price - position['avg_cost']) * sellable - fee.total_fee
                            trades.append({
                                'date': d_ts, 'ts_code': ts, 'action': 'SELL',
                                'price': fee.price, 'shares': sellable, 'amount': fee.amount,
                                'level': position['level'], 'avg_cost': position['avg_cost'],
                                'cash_before': cash - fee.net_cash_flow, 'cash_after': cash,
                                'commission': fee.commission, 'stamp_tax': fee.stamp_tax,
                                'transfer_fee': fee.transfer_fee, 'slippage': fee.slippage_cost,
                                'pnl': pnl,
                                'reason': 'BEARISH_CLOSE', 'days_held': days_held,
                            })
                            position = None

        # ===== 加仓判断（持仓中，再次跌破BB Lower）=====
        if position and position['level'] < MAX_LEVELS:
            ts = position['ts_code']
            sd = symbol_data[ts]
            if d_ts in sd.index:
                row = sd.loc[d_ts]
                # 跌破布林带下轨（用后复权价判断）
                bb_signal = not pd.isna(row['bb_lower']) and row['adj_close'] < row['bb_lower']
                # 跌停不买
                not_limit_down = not row['is_limit_down']

                if bb_signal and not_limit_down:
                    buy_price = row['close']
                    target_amount = total_equity * POSITION_PER_LEVEL
                    shares = int(target_amount / buy_price / 100) * 100
                    if shares >= 100:
                        fee = fee_calc.calculate('buy', buy_price, shares)
                        if cash >= -fee.net_cash_flow:
                            cash += fee.net_cash_flow  # net_cash_flow为负
                            # 重新计算平均成本
                            old_cost = position['avg_cost'] * position['shares']
                            new_cost = fee.amount + fee.total_fee
                            total_shares = position['shares'] + shares
                            position['avg_cost'] = (old_cost + new_cost) / total_shares
                            position['shares'] = total_shares
                            position['level'] += 1
                            trades.append({
                                'date': d_ts, 'ts_code': ts, 'action': 'BUY',
                                'price': fee.price, 'shares': shares, 'amount': fee.amount,
                                'level': position['level'], 'avg_cost': position['avg_cost'],
                                'cash_before': cash - fee.net_cash_flow, 'cash_after': cash,
                                'commission': fee.commission, 'stamp_tax': 0,
                                'transfer_fee': fee.transfer_fee, 'slippage': fee.slippage_cost,
                                'pnl': 0,
                                'reason': 'ADD_POSITION', 'days_held': 0,
                            })

        # ===== 新买入判断（空仓时）=====
        if position is None:
            candidates = daily_candidates.get(d, [])
            for ts in candidates:
                if ts not in symbol_data: continue
                sd = symbol_data[ts]
                if d_ts not in sd.index: continue
                row = sd.loc[d_ts]

                # 上市天数过滤
                if len(sd.loc[:d_ts]) < MIN_LISTING_DAYS:
                    continue

                # BB Lower信号
                if pd.isna(row['bb_lower']) or row['adj_close'] >= row['bb_lower']:
                    continue

                # 跌停不买
                if row['is_limit_down']:
                    continue

                # 买入
                buy_price = row['close']
                target_amount = total_equity * POSITION_PER_LEVEL
                shares = int(target_amount / buy_price / 100) * 100
                if shares < 100:
                    continue

                amount = shares * buy_price
                fee = fee_calc.calculate('buy', buy_price, shares)
                if cash < -fee.net_cash_flow:
                    continue

                cash += fee.net_cash_flow  # net_cash_flow为负
                position = {
                    'ts_code': ts, 'shares': shares,
                    'avg_cost': (fee.amount + fee.total_fee) / shares,
                    'level': 1, 'entry_date': d_ts,
                }
                trades.append({
                    'date': d_ts, 'ts_code': ts, 'action': 'BUY',
                    'price': fee.price, 'shares': shares, 'amount': fee.amount,
                    'level': 1, 'avg_cost': position['avg_cost'],
                    'cash_before': cash - fee.net_cash_flow, 'cash_after': cash,
                    'commission': fee.commission, 'stamp_tax': 0,
                    'transfer_fee': fee.transfer_fee, 'slippage': fee.slippage_cost,
                    'pnl': 0,
                    'reason': 'INITIAL_ENTRY', 'days_held': 0,
                })
                break  # 只买Top1中第一个满足条件的

        if i % 200 == 0 and i > 0:
            print(f"  回测进度: {i}/{len(trade_days)}, 当前权益: {total_equity:,.0f}")

    print(f"回测完成, 耗时: {time.time()-t1:.1f}s")

    # ===== 结果分析 =====
    nav_df = pd.DataFrame(nav).set_index('date')
    trades_df = pd.DataFrame(trades)

    final_equity = nav_df['total_equity'].iloc[-1]
    total_return = (final_equity - INITIAL_CASH) / INITIAL_CASH * 100

    # 最大回撤
    equities = nav_df['total_equity'].values
    peak = equities[0]
    max_dd = 0
    for eq in equities:
        if eq > peak: peak = eq
        dd = (eq - peak) / peak * 100
        if dd < max_dd: max_dd = dd

    # 年化
    n_days = len(nav_df)
    annual_return = ((final_equity / INITIAL_CASH) ** (252 / max(n_days,1)) - 1) * 100

    # Sharpe
    daily_rets = nav_df['total_equity'].pct_change().dropna()
    sharpe = (daily_rets.mean() / daily_rets.std() * np.sqrt(252)) if len(daily_rets)>1 and daily_rets.std()>0 else 0

    # 交易统计
    sell_trades = trades_df[trades_df['action']=='SELL'] if len(trades_df)>0 else pd.DataFrame()
    n_sells = len(sell_trades)
    if n_sells > 0:
        win_trades = sell_trades[sell_trades['pnl'] > 0]
        win_rate = len(win_trades) / n_sells * 100
        avg_win = win_trades['pnl'].mean() if len(win_trades)>0 else 0
        lose_trades = sell_trades[sell_trades['pnl'] <= 0]
        avg_lose = lose_trades['pnl'].mean() if len(lose_trades)>0 else 0
        avg_holding = sell_trades['days_held'].mean()
        total_pnl = sell_trades['pnl'].sum()
    else:
        win_rate = avg_win = avg_lose = avg_holding = total_pnl = 0

    # 持仓时间分布
    if n_sells > 0:
        holding_dist = sell_trades['days_held'].describe()
    else:
        holding_dist = None

    print("\n" + "=" * 70)
    print("回测结果")
    print("=" * 70)
    print(f"初始资金:     {INITIAL_CASH:,.0f}")
    print(f"最终权益:     {final_equity:,.2f}")
    print(f"累计收益:     {total_return:+.2f}%")
    print(f"年化收益:     {annual_return:+.2f}%")
    print(f"最大回撤:     {max_dd:.2f}%")
    print(f"Sharpe:       {sharpe:.3f}")
    print(f"交易日数:     {n_days}")
    print(f"买入笔数:     {len(trades_df[trades_df['action']=='BUY']) if len(trades_df)>0 else 0}")
    print(f"卖出笔数:     {n_sells}")
    print(f"胜率:         {win_rate:.1f}%")
    print(f"平均盈利:     {avg_win:,.2f}")
    print(f"平均亏损:     {avg_lose:,.2f}")
    print(f"盈亏比:       {abs(avg_win/avg_lose):.2f}" if avg_lose!=0 else "盈亏比: N/A")
    print(f"平均持仓天数: {avg_holding:.1f}")
    print(f"总盈亏:       {total_pnl:,.2f}")

    # 年度收益
    nav_df['year'] = nav_df.index.year
    print(f"\n=== 年度收益 ===")
    for year in sorted(nav_df['year'].unique()):
        yd = nav_df[nav_df['year']==year]
        if len(yd) > 1:
            ys = yd['total_equity'].iloc[0]
            ye = yd['total_equity'].iloc[-1]
            yr = (ye - ys) / ys * 100
            print(f"{year}: {yr:+.2f}% ({ys:,.0f} → {ye:,.0f})")

    # 持仓时间分布
    if holding_dist is not None:
        print(f"\n=== 持仓时间分布（自然日）===")
        print(f"  平均: {holding_dist['mean']:.1f}天")
        print(f"  中位数: {holding_dist['50%']:.1f}天")
        print(f"  最短: {holding_dist['min']:.0f}天")
        print(f"  最长: {holding_dist['max']:.0f}天")
        # 分段统计
        print(f"\n  持仓天数分段:")
        bins = [0, 1, 3, 5, 7, 10, 15, 20, 30, 60, 9999]
        labels = ['1天', '2-3天', '4-5天', '6-7天', '8-10天', '11-15天', '16-20天', '21-30天', '31-60天', '>60天']
        sell_trades['holding_bin'] = pd.cut(sell_trades['days_held'], bins=bins, labels=labels, right=True)
        for label in labels:
            cnt = (sell_trades['holding_bin'] == label).sum()
            if cnt > 0:
                avg_pnl = sell_trades[sell_trades['holding_bin']==label]['pnl'].mean()
                wr = (sell_trades[sell_trades['holding_bin']==label]['pnl']>0).mean()*100
                print(f"    {label}: {cnt}笔 ({cnt/n_sells*100:.1f}%), 胜率{wr:.0f}%, 平均盈亏{avg_pnl:,.0f}")

    # 加仓层级分析
    if len(trades_df) > 0:
        buy_trades = trades_df[trades_df['action']=='BUY']
        print(f"\n=== 加仓层级分布 ===")
        for lvl in range(1, MAX_LEVELS+1):
            cnt = (buy_trades['level']==lvl).sum()
            if cnt > 0:
                print(f"  第{lvl}层: {cnt}次")

    # 保存
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    nav_path = os.path.join(project_root, 'results', 'reports', f'nav_bearish_exit_{timestamp}.csv')
    trades_path = os.path.join(project_root, 'results', 'trades', f'trades_bearish_exit_{timestamp}.csv')
    nav_df.to_csv(nav_path)
    trades_df.to_csv(trades_path, index=False)
    print(f"\n净值曲线: {nav_path}")
    print(f"交易记录: {trades_path}")
    print(f"\n总耗时: {time.time()-t0:.1f}s")

if __name__ == '__main__':
    main()
