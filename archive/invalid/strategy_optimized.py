"""
优化版阳线持有策略：
- 最小持仓5天（避免第1天被洗）
- 强阴线卖出（阴线+跌幅>1%）
- 移动止盈（从最高价回撤3%）
- 最大持仓30天
- BB Lower买入 + 5层加仓 + 跌停不买
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

    # ===== 策略参数 =====
    START_DATE = '2020-01-01'
    END_DATE = '2026-08-25'
    INITIAL_CASH = 1_000_000
    BB_PERIOD = 20
    BB_STD = 2.0
    MAX_LEVELS = 5
    POSITION_PER_LEVEL = 0.20
    MIN_LISTING_DAYS = 60

    # 优化参数
    MIN_HOLDING_DAYS = 5       # 最小持仓天数（自然日）
    STRONG_BEARISH_DROP = 0.01 # 强阴线：跌幅超过1%
    TRAILING_STOP_PCT = 0.03   # 移动止盈：从最高价回撤3%
    MAX_HOLDING_DAYS = 30       # 最大持仓30天

    print("=" * 70)
    print(f"优化版趋势策略：Top1 + BB Lower + 5层加仓")
    print(f"卖出规则：最小持仓{MIN_HOLDING_DAYS}天 + 强阴线(跌{STRONG_BEARISH_DROP:.0%}) + 移动止盈{TRAILING_STOP_PCT:.0%} + 最大{MAX_HOLDING_DAYS}天")
    print(f"回测区间：{START_DATE} ~ {END_DATE}")
    print("=" * 70)

    t0 = time.time()

    # 交易日历
    cal = storage.load_trade_cal()
    cal['date'] = pd.to_datetime(cal['date'])
    trade_days = cal[(cal['is_open']==1) & (cal['date']>=START_DATE) & (cal['date']<=END_DATE)]['date'].sort_values().values
    print(f"交易日数: {len(trade_days)}")

    # 预计算每天候选池
    print("预计算候选池...")
    daily_candidates = {}
    for i, d in enumerate(trade_days):
        if i % 200 == 0:
            print(f"  {i}/{len(trade_days)}")
        d_str = pd.Timestamp(d).strftime('%Y-%m-%d')
        df = storage.get_top_n_by_amount(date=d_str, n=20, exclude_st=True, exclude_suspended=True)
        daily_candidates[d] = df['ts_code'].tolist() if not df.empty else []
    print(f"候选池预计算完成, 耗时: {time.time()-t0:.1f}s")

    # 加载股票数据
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
        merged['adj_close'] = merged['close'] * merged['adj_factor']
        merged['bb_mid'] = merged['adj_close'].rolling(BB_PERIOD).mean()
        merged['bb_std'] = merged['adj_close'].rolling(BB_PERIOD).std()
        merged['bb_lower'] = merged['bb_mid'] - BB_STD * merged['bb_std']
        merged['is_limit_down'] = merged['close'] <= merged['pre_close'] * 0.905
        symbol_data[ts] = merged
    print(f"成功加载: {len(symbol_data)}只, 耗时: {time.time()-t0:.1f}s")

    # ===== 回测主循环 =====
    cash = INITIAL_CASH
    position = None
    trades = []
    nav = []

    print("开始回测...")
    t1 = time.time()

    for i, d in enumerate(trade_days):
        d_ts = pd.Timestamp(d)

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

        # 停牌跳过
        if position and position['ts_code'] in symbol_data:
            sd = symbol_data[position['ts_code']]
            if d_ts not in sd.index:
                continue

        # ===== 卖出判断 =====
        if position:
            ts = position['ts_code']
            sd = symbol_data[ts]
            if d_ts in sd.index:
                row = sd.loc[d_ts]
                entry_date = position['entry_date']
                days_held = (d_ts - entry_date).days

                # 更新持仓期间最高价
                if row['high'] > position['highest_high']:
                    position['highest_high'] = row['high']

                sell = False
                sell_price = None
                reason = None

                # T+1：买入当天不能卖
                if d_ts > entry_date:
                    # 1. 最小持仓期后才允许卖出
                    if days_held >= MIN_HOLDING_DAYS:
                        # 2. 强阴线卖出：阴线且跌幅超过阈值
                        is_bearish = row['close'] < row['open']
                        drop_pct = (row['open'] - row['close']) / row['open']
                        is_strong_bearish = is_bearish and drop_pct >= STRONG_BEARISH_DROP

                        if is_strong_bearish:
                            sell = True
                            sell_price = row['close']
                            reason = 'STRONG_BEARISH'

                        # 3. 移动止盈：从最高价回撤超过阈值
                        if not sell and position['highest_high'] > 0:
                            drawdown = (position['highest_high'] - row['close']) / position['highest_high']
                            if drawdown >= TRAILING_STOP_PCT:
                                sell = True
                                sell_price = row['close']
                                reason = 'TRAILING_STOP'

                    # 4. 最大持仓天数（不受最小持仓限制，但也要T+1）
                    if not sell and days_held >= MAX_HOLDING_DAYS:
                        sell = True
                        sell_price = row['close']
                        reason = 'MAX_HOLDING'

                if sell:
                    sellable = position['shares']
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
                            'pnl': pnl, 'reason': reason, 'days_held': days_held,
                            'highest_high': position['highest_high'],
                        })
                        position = None

        # ===== 加仓判断 =====
        if position and position['level'] < MAX_LEVELS:
            ts = position['ts_code']
            sd = symbol_data[ts]
            if d_ts in sd.index:
                row = sd.loc[d_ts]
                bb_signal = not pd.isna(row['bb_lower']) and row['adj_close'] < row['bb_lower']
                not_limit_down = not row['is_limit_down']

                if bb_signal and not_limit_down:
                    buy_price = row['close']
                    target_amount = total_equity * POSITION_PER_LEVEL
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
                            trades.append({
                                'date': d_ts, 'ts_code': ts, 'action': 'BUY',
                                'price': fee.price, 'shares': shares, 'amount': fee.amount,
                                'level': position['level'], 'avg_cost': position['avg_cost'],
                                'cash_before': cash - fee.net_cash_flow, 'cash_after': cash,
                                'commission': fee.commission, 'stamp_tax': 0,
                                'transfer_fee': fee.transfer_fee, 'slippage': fee.slippage_cost,
                                'pnl': 0, 'reason': 'ADD_POSITION', 'days_held': 0,
                                'highest_high': 0,
                            })

        # ===== 新买入判断 =====
        if position is None:
            candidates = daily_candidates.get(d, [])
            for ts in candidates:
                if ts not in symbol_data: continue
                sd = symbol_data[ts]
                if d_ts not in sd.index: continue
                row = sd.loc[d_ts]

                if len(sd.loc[:d_ts]) < MIN_LISTING_DAYS:
                    continue
                if pd.isna(row['bb_lower']) or row['adj_close'] >= row['bb_lower']:
                    continue
                if row['is_limit_down']:
                    continue

                buy_price = row['close']
                target_amount = total_equity * POSITION_PER_LEVEL
                shares = int(target_amount / buy_price / 100) * 100
                if shares < 100:
                    continue

                fee = fee_calc.calculate('buy', buy_price, shares)
                if cash < -fee.net_cash_flow:
                    continue

                cash += fee.net_cash_flow
                position = {
                    'ts_code': ts, 'shares': shares,
                    'avg_cost': (fee.amount + fee.total_fee) / shares,
                    'level': 1, 'entry_date': d_ts,
                    'highest_high': row['high'],
                }
                trades.append({
                    'date': d_ts, 'ts_code': ts, 'action': 'BUY',
                    'price': fee.price, 'shares': shares, 'amount': fee.amount,
                    'level': 1, 'avg_cost': position['avg_cost'],
                    'cash_before': cash - fee.net_cash_flow, 'cash_after': cash,
                    'commission': fee.commission, 'stamp_tax': 0,
                    'transfer_fee': fee.transfer_fee, 'slippage': fee.slippage_cost,
                    'pnl': 0, 'reason': 'INITIAL_ENTRY', 'days_held': 0,
                    'highest_high': row['high'],
                })
                break

        if i % 200 == 0 and i > 0:
            print(f"  回测进度: {i}/{len(trade_days)}, 当前权益: {total_equity:,.0f}")

    print(f"回测完成, 耗时: {time.time()-t1:.1f}s")

    # ===== 结果分析 =====
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
        avg_lose = lose_trades['pnl'].mean() if len(lose_trades)>0 else 0
        avg_holding = sell_trades['days_held'].mean()
        total_pnl = sell_trades['pnl'].sum()
        profit_factor = win_trades['pnl'].sum() / abs(lose_trades['pnl'].sum()) if len(lose_trades)>0 and lose_trades['pnl'].sum()!=0 else float('inf')
    else:
        win_rate = avg_win = avg_lose = avg_holding = total_pnl = profit_factor = 0

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
    print(f"买入笔数:     {len(buy_trades)}")
    print(f"卖出笔数:     {n_sells}")
    print(f"胜率:         {win_rate:.1f}%")
    print(f"平均盈利:     {avg_win:,.2f}")
    print(f"平均亏损:     {avg_lose:,.2f}")
    print(f"盈亏比:       {abs(avg_win/avg_lose):.2f}" if avg_lose!=0 else "盈亏比: N/A")
    print(f"Profit Factor:{profit_factor:.2f}")
    print(f"平均持仓天数: {avg_holding:.1f}")
    print(f"总盈亏:       {total_pnl:,.2f}")

    # 卖出原因分布
    if n_sells > 0:
        print(f"\n=== 卖出原因分布 ===")
        for reason in sell_trades['reason'].unique():
            cnt = (sell_trades['reason']==reason).sum()
            sub = sell_trades[sell_trades['reason']==reason]
            wr = (sub['pnl']>0).mean()*100
            avg_pnl = sub['pnl'].mean()
            avg_days = sub['days_held'].mean()
            print(f"  {reason}: {cnt}笔 ({cnt/n_sells*100:.1f}%), 胜率{wr:.0f}%, 平均盈亏{avg_pnl:,.0f}, 平均持仓{avg_days:.1f}天")

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
    if n_sells > 0:
        print(f"\n=== 持仓时间分布 ===")
        print(f"  平均: {sell_trades['days_held'].mean():.1f}天, 中位数: {sell_trades['days_held'].median():.1f}天")
        bins = [0, 5, 7, 10, 15, 20, 30, 9999]
        labels = ['<5天', '5-7天', '8-10天', '11-15天', '16-20天', '21-30天', '>30天']
        sell_trades = sell_trades.copy()
        sell_trades['holding_bin'] = pd.cut(sell_trades['days_held'], bins=bins, labels=labels, right=True)
        for label in labels:
            cnt = (sell_trades['holding_bin'] == label).sum()
            if cnt > 0:
                avg_pnl = sell_trades[sell_trades['holding_bin']==label]['pnl'].mean()
                wr = (sell_trades[sell_trades['holding_bin']==label]['pnl']>0).mean()*100
                print(f"    {label}: {cnt}笔 ({cnt/n_sells*100:.1f}%), 胜率{wr:.0f}%, 平均盈亏{avg_pnl:,.0f}")

    # 对比
    print(f"\n=== 对比 ===")
    print(f"  原始阴线卖出: -24.09%, 最大回撤-29.04%, 胜率39.2%")
    print(f"  优化版:       {total_return:+.2f}%, 最大回撤{max_dd:.2f}%, 胜率{win_rate:.1f}%")

    # 保存
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    tag = f"opt_min{MIN_HOLDING_DAYS}_drop{int(STRONG_BEARISH_DROP*100)}_trail{int(TRAILING_STOP_PCT*100)}_max{MAX_HOLDING_DAYS}"
    nav_path = os.path.join(project_root, 'results', 'reports', f'nav_{tag}_{timestamp}.csv')
    trades_path = os.path.join(project_root, 'results', 'trades', f'trades_{tag}_{timestamp}.csv')
    nav_df.to_csv(nav_path)
    trades_df.to_csv(trades_path, index=False)
    print(f"\n净值曲线: {nav_path}")
    print(f"交易记录: {trades_path}")
    print(f"\n总耗时: {time.time()-t0:.1f}s")

if __name__ == '__main__':
    main()
