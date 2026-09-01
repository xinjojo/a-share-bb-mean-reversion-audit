"""
多股策略：支持股票池过滤 + 成交额排序方向 + 同时持有N只
卖出逻辑：最小持仓5天 + 强阴线1% + 移动止盈3% + 最大30天
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
    POSITION_PER_LEVEL = 0.20  # 每只股票每层占总资金20%
    MIN_LISTING_DAYS = 60

    # 多股参数
    MAX_POSITIONS = 3       # 同时持有最多3只
    TOP_N = 3               # 每天候选池取Top N
    SORT_DIRECTION = 'desc'  # 'asc'=成交额从小到大, 'desc'=从大到小
    USE_INDEX_POOL = True   # 是否使用指数成分股池
    INDEX_CODE = '000905.SH'  # 中证500

    # 卖出参数
    MIN_HOLDING_DAYS = 5
    STRONG_BEARISH_DROP = 0.01
    TRAILING_STOP_PCT = 0.03
    MAX_HOLDING_DAYS = 30

    sort_desc = "成交额从大到小" if SORT_DIRECTION == 'desc' else "成交额从小到大"
    pool_desc = f"中证500" if USE_INDEX_POOL else "全A股"

    print("=" * 70)
    print(f"多股策略：{pool_desc} + {sort_desc} Top{TOP_N} + 同时持有{MAX_POSITIONS}只")
    print(f"卖出：最小持仓{MIN_HOLDING_DAYS}天 + 强阴线{STRONG_BEARISH_DROP:.0%} + 移动止盈{TRAILING_STOP_PCT:.0%} + 最大{MAX_HOLDING_DAYS}天")
    print(f"回测区间：{START_DATE} ~ {END_DATE}")
    print("=" * 70)

    t0 = time.time()

    # 加载指数成分股池
    index_pool = None
    if USE_INDEX_POOL:
        # 文件名格式：index_weight_<指数代码数字部分>.csv
        idx_num = INDEX_CODE.split('.')[0]
        idx_file = os.path.join(project_root, 'data', 'raw', f'index_weight_{idx_num}.csv')
        idx_df = pd.read_csv(idx_file)
        # 取最新一期的成分股（简化，不考虑历史调整）
        latest_date = idx_df['trade_date'].max()
        index_pool = set(idx_df[idx_df['trade_date']==latest_date]['con_code'].tolist())
        print(f"股票池：{INDEX_CODE}, 成分股数：{len(index_pool)}")

    # 交易日历
    cal = storage.load_trade_cal()
    cal['date'] = pd.to_datetime(cal['date'])
    trade_days = cal[(cal['is_open']==1) & (cal['date']>=START_DATE) & (cal['date']<=END_DATE)]['date'].sort_values().values
    print(f"交易日数: {len(trade_days)}")

    # 预计算每天候选池（按成交额排序，取Top N，可过滤股票池）
    print("预计算候选池...")
    daily_candidates = {}
    for i, d in enumerate(trade_days):
        if i % 200 == 0:
            print(f"  {i}/{len(trade_days)}")
        d_str = pd.Timestamp(d).strftime('%Y-%m-%d')
        # 取Top50，然后过滤股票池，再排序取Top N
        df = storage.get_top_n_by_amount(date=d_str, n=50, exclude_st=True, exclude_suspended=True)
        if df.empty:
            daily_candidates[d] = []
            continue
        # 过滤股票池
        if index_pool is not None:
            df = df[df['ts_code'].isin(index_pool)]
        # 排序
        if SORT_DIRECTION == 'asc':
            df = df.sort_values('amount', ascending=True)
        else:
            df = df.sort_values('amount', ascending=False)
        daily_candidates[d] = df['ts_code'].head(TOP_N).tolist()
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
        merged['adj_close'] = merged['close'] * merged['adj_factor']
        merged['bb_mid'] = merged['adj_close'].rolling(BB_PERIOD).mean()
        merged['bb_std'] = merged['adj_close'].rolling(BB_PERIOD).std()
        merged['bb_lower'] = merged['bb_mid'] - BB_STD * merged['bb_std']
        merged['is_limit_down'] = merged['close'] <= merged['pre_close'] * 0.905
        symbol_data[ts] = merged
    print(f"成功加载: {len(symbol_data)}只, 耗时: {time.time()-t0:.1f}s")

    # ===== 回测主循环 =====
    cash = INITIAL_CASH
    positions = {}  # {ts_code: {shares, avg_cost, level, entry_date, highest_high}}
    trades = []
    nav = []

    print("开始回测...")
    t1 = time.time()

    for i, d in enumerate(trade_days):
        d_ts = pd.Timestamp(d)

        # 当日权益
        total_position_value = 0
        for ts, pos in positions.items():
            if ts in symbol_data and d_ts in symbol_data[ts].index:
                total_position_value += pos['shares'] * symbol_data[ts].loc[d_ts, 'close']
            else:
                total_position_value += pos['shares'] * pos['avg_cost']
        total_equity = cash + total_position_value
        nav.append({'date': d_ts, 'total_equity': total_equity, 'cash': cash, 'position_value': total_position_value})

        # ===== 1. 处理已有持仓：卖出 + 加仓 =====
        to_sell = []
        for ts, pos in list(positions.items()):
            if ts not in symbol_data: continue
            sd = symbol_data[ts]
            if d_ts not in sd.index: continue  # 停牌
            row = sd.loc[d_ts]
            entry_date = pos['entry_date']
            days_held = (d_ts - entry_date).days

            # 更新最高价
            if row['high'] > pos['highest_high']:
                pos['highest_high'] = row['high']

            # 卖出判断
            sell = False
            sell_price = None
            reason = None

            if d_ts > entry_date:  # T+1
                if days_held >= MIN_HOLDING_DAYS:
                    # 强阴线
                    is_bearish = row['close'] < row['open']
                    drop_pct = (row['open'] - row['close']) / row['open']
                    if is_bearish and drop_pct >= STRONG_BEARISH_DROP:
                        sell = True; sell_price = row['close']; reason = 'STRONG_BEARISH'
                    # 移动止盈
                    if not sell and pos['highest_high'] > 0:
                        drawdown = (pos['highest_high'] - row['close']) / pos['highest_high']
                        if drawdown >= TRAILING_STOP_PCT:
                            sell = True; sell_price = row['close']; reason = 'TRAILING_STOP'
                # 最大持仓
                if not sell and days_held >= MAX_HOLDING_DAYS:
                    sell = True; sell_price = row['close']; reason = 'MAX_HOLDING'

            if sell:
                to_sell.append((ts, sell_price, reason, days_held))
                continue  # 卖出的当天不加仓

            # 加仓判断
            if pos['level'] < MAX_LEVELS:
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
                            old_cost = pos['avg_cost'] * pos['shares']
                            new_cost = fee.amount + fee.total_fee
                            total_shares = pos['shares'] + shares
                            pos['avg_cost'] = (old_cost + new_cost) / total_shares
                            pos['shares'] = total_shares
                            pos['level'] += 1
                            trades.append({
                                'date': d_ts, 'ts_code': ts, 'action': 'BUY',
                                'price': fee.price, 'shares': shares, 'amount': fee.amount,
                                'level': pos['level'], 'avg_cost': pos['avg_cost'],
                                'cash_before': cash - fee.net_cash_flow, 'cash_after': cash,
                                'commission': fee.commission, 'stamp_tax': 0,
                                'transfer_fee': fee.transfer_fee, 'slippage': fee.slippage_cost,
                                'pnl': 0, 'reason': 'ADD_POSITION', 'days_held': days_held,
                            })

        # 执行卖出
        for ts, sell_price, reason, days_held in to_sell:
            if ts in positions:
                pos = positions[ts]
                sellable = pos['shares']
                fee = fee_calc.calculate('sell', sell_price, sellable)
                cash += fee.net_cash_flow
                pnl = (fee.price - pos['avg_cost']) * sellable - fee.total_fee
                trades.append({
                    'date': d_ts, 'ts_code': ts, 'action': 'SELL',
                    'price': fee.price, 'shares': sellable, 'amount': fee.amount,
                    'level': pos['level'], 'avg_cost': pos['avg_cost'],
                    'cash_before': cash - fee.net_cash_flow, 'cash_after': cash,
                    'commission': fee.commission, 'stamp_tax': fee.stamp_tax,
                    'transfer_fee': fee.transfer_fee, 'slippage': fee.slippage_cost,
                    'pnl': pnl, 'reason': reason, 'days_held': days_held,
                })
                del positions[ts]

        # ===== 2. 新买入：有空仓位时，从候选池中选满足BB Lower的股票 =====
        if len(positions) < MAX_POSITIONS:
            candidates = daily_candidates.get(d, [])
            for ts in candidates:
                if len(positions) >= MAX_POSITIONS: break
                if ts in positions: continue  # 已持有
                if ts not in symbol_data: continue
                sd = symbol_data[ts]
                if d_ts not in sd.index: continue
                row = sd.loc[d_ts]

                if len(sd.loc[:d_ts]) < MIN_LISTING_DAYS: continue
                if pd.isna(row['bb_lower']) or row['adj_close'] >= row['bb_lower']: continue
                if row['is_limit_down']: continue

                buy_price = row['close']
                target_amount = total_equity * POSITION_PER_LEVEL
                shares = int(target_amount / buy_price / 100) * 100
                if shares < 100: continue

                fee = fee_calc.calculate('buy', buy_price, shares)
                if cash < -fee.net_cash_flow: continue

                cash += fee.net_cash_flow
                positions[ts] = {
                    'shares': shares,
                    'avg_cost': (fee.amount + fee.total_fee) / shares,
                    'level': 1, 'entry_date': d_ts,
                    'highest_high': row['high'],
                }
                trades.append({
                    'date': d_ts, 'ts_code': ts, 'action': 'BUY',
                    'price': fee.price, 'shares': shares, 'amount': fee.amount,
                    'level': 1, 'avg_cost': positions[ts]['avg_cost'],
                    'cash_before': cash - fee.net_cash_flow, 'cash_after': cash,
                    'commission': fee.commission, 'stamp_tax': 0,
                    'transfer_fee': fee.transfer_fee, 'slippage': fee.slippage_cost,
                    'pnl': 0, 'reason': 'INITIAL_ENTRY', 'days_held': 0,
                })

        if i % 200 == 0 and i > 0:
            print(f"  回测进度: {i}/{len(trade_days)}, 持仓数:{len(positions)}, 权益:{total_equity:,.0f}")

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
    print(f"回测结果：{pool_desc} + {sort_desc} Top{TOP_N} + 持有{MAX_POSITIONS}只")
    print("=" * 70)
    print(f"初始资金:     {INITIAL_CASH:,.0f}")
    print(f"最终权益:     {final_equity:,.2f}")
    print(f"累计收益:     {total_return:+.2f}%")
    print(f"年化收益:     {annual_return:+.2f}%")
    print(f"最大回撤:     {max_dd:.2f}%")
    print(f"Sharpe:       {sharpe:.3f}")
    print(f"买入笔数:     {len(buy_trades)}")
    print(f"卖出笔数:     {n_sells}")
    print(f"胜率:         {win_rate:.1f}%")
    print(f"平均盈利:     {avg_win:,.2f}")
    print(f"平均亏损:     {avg_lose:,.2f}")
    print(f"盈亏比:       {abs(avg_win/avg_lose):.2f}" if avg_lose!=0 else "盈亏比: N/A")
    print(f"Profit Factor:{profit_factor:.2f}")
    print(f"平均持仓天数: {avg_holding:.1f}")
    print(f"总盈亏:       {total_pnl:,.2f}")

    # 卖出原因
    if n_sells > 0:
        print(f"\n=== 卖出原因分布 ===")
        for reason in sorted(sell_trades['reason'].unique()):
            cnt = (sell_trades['reason']==reason).sum()
            sub = sell_trades[sell_trades['reason']==reason]
            wr = (sub['pnl']>0).mean()*100
            avg_pnl = sub['pnl'].mean()
            print(f"  {reason:<20}: {cnt:>4}笔 ({cnt/n_sells*100:>5.1f}%), 胜率{wr:>3.0f}%, 平均盈亏{avg_pnl:>8,.0f}")

    # 年度收益
    nav_df['year'] = nav_df.index.year
    print(f"\n=== 年度收益 ===")
    for year in sorted(nav_df['year'].unique()):
        yd = nav_df[nav_df['year']==year]
        if len(yd) > 1:
            ys = yd['total_equity'].iloc[0]
            ye = yd['total_equity'].iloc[-1]
            yr = (ye - ys) / ys * 100
            print(f"{year}: {yr:+.2f}%")

    # 保存
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    sort_tag = 'desc' if SORT_DIRECTION=='desc' else 'asc'
    pool_tag = 'zz500' if USE_INDEX_POOL else 'all'
    tag = f"multi_{pool_tag}_{sort_tag}_top{TOP_N}_p{MAX_POSITIONS}"
    nav_path = os.path.join(project_root, 'results', 'reports', f'nav_{tag}_{timestamp}.csv')
    trades_path = os.path.join(project_root, 'results', 'trades', f'trades_{tag}_{timestamp}.csv')
    nav_df.to_csv(nav_path)
    trades_df.to_csv(trades_path, index=False)
    print(f"\n净值曲线: {nav_path}")
    print(f"交易记录: {trades_path}")
    print(f"\n总耗时: {time.time()-t0:.1f}s")

if __name__ == '__main__':
    main()
