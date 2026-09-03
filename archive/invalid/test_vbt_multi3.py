"""
VectorBT快速版多股策略：3只同时持有 + 止盈5% + 止损10% + 时间止损7天 + 每只3层
回测区间：2020-01-01 ~ 2026-08-25

偏差说明（VectorBT限制）：
1. 同日同股票多笔订单会被合并（加仓+卖出不能同一天精确模拟）
2. 100股整数倍、涨跌停可成交性做了简化
3. T+1通过订单日期偏移实现
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import numpy as np
import vectorbt as vbt
from data_loader.storage import DataStorage
from engine.trading_rules import TradingRules

def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    storage = DataStorage(os.path.join(project_root, 'data', 'raw'))

    MAX_POSITIONS = 3
    MAX_LEVELS = 3
    TP_RATIO = 0.05
    SL_RATIO = 0  # 0 = 无价格止损
    TIME_STOP_DAYS = 20
    BB_PERIOD = 20
    BB_STD = 2.0
    START_DATE = '2020-01-01'
    END_DATE = '2026-08-25'
    INITIAL_CASH = 1_000_000

    sl_desc = f"止损{SL_RATIO:.0%}" if SL_RATIO > 0 else "无价格止损"
    print("=" * 70)
    print(f"VectorBT多股策略：{MAX_POSITIONS}只持有 + 止盈{TP_RATIO:.0%} + {sl_desc} + 时间止损{TIME_STOP_DAYS}天 + 每只{MAX_LEVELS}层")
    print(f"回测区间：{START_DATE} ~ {END_DATE}")
    print("=" * 70)

    # ===== 1. 加载交易日历 =====
    t0 = time.time()
    cal = storage.load_trade_cal()
    cal['date'] = pd.to_datetime(cal['date'])
    trade_days = cal[(cal['is_open']==1) & (cal['date']>=START_DATE) & (cal['date']<=END_DATE)]['date'].sort_values().values
    print(f"交易日数: {len(trade_days)}, 加载耗时: {time.time()-t0:.1f}s")

    # ===== 2. 预计算每天Top30候选股（成交额排名）=====
    t1 = time.time()
    trading_rules = TradingRules(min_listing_days=60, exclude_st=True, exclude_bse=True, conservative_fill=True)
    sb = storage.load_stock_basic()
    st_symbols = set(sb[sb['name'].str.contains('ST', na=False)]['ts_code'].tolist())
    bse_symbols = set(sb[sb['ts_code'].str.endswith('.BJ')]['ts_code'].tolist())
    info_dict = {row['ts_code']: row for _, row in sb.iterrows()}

    daily_candidates = {}  # date -> list of {ts_code, close, high, low, pre_close, amount}
    all_symbols = set()
    for i, d in enumerate(trade_days):
        date_str = pd.Timestamp(d).strftime('%Y-%m-%d')
        df = storage.get_top_n_by_amount(date=date_str, n=90, exclude_st=False, exclude_suspended=True)
        if df.empty:
            daily_candidates[d] = []
            continue
        cands = []
        for _, row in df.iterrows():
            ts = row['ts_code']
            if ts in st_symbols or ts in bse_symbols: continue
            if ts not in info_dict: continue
            info = info_dict[ts]
            list_date = pd.to_datetime(str(info.get('list_date','')))
            if (pd.Timestamp(d) - list_date).days < 60: continue
            cands.append({
                'ts_code': ts, 'close': row['close'], 'high': row['high'],
                'low': row['low'], 'pre_close': row['pre_close'], 'amount': row['amount'],
            })
            all_symbols.add(ts)
            if len(cands) >= 30: break
        daily_candidates[d] = cands
        if (i+1) % 200 == 0:
            print(f"  候选池预计算: {i+1}/{len(trade_days)}")
    print(f"候选池预计算完成: {len(all_symbols)}只股票, 耗时: {time.time()-t1:.1f}s")

    # ===== 3. 加载候选股数据 + 预计算BB =====
    t2 = time.time()
    symbol_data = {}  # ts_code -> DataFrame with date, open, high, low, close, volume, amount, bb_lower, bb_middle
    for i, ts in enumerate(all_symbols):
        daily = storage.load_daily(ts)
        adj = storage.load_adj_factor(ts)
        if daily.empty or adj.empty: continue
        daily = daily.sort_values('date').reset_index(drop=True)
        daily['date'] = pd.to_datetime(daily['date'])
        adj = adj.sort_values('date').reset_index(drop=True)
        adj['date'] = pd.to_datetime(adj['date'])
        merged = pd.merge(daily[['date','open','high','low','close','vol','amount','pre_close']],
                          adj[['date','adj_factor']], on='date', how='inner')
        merged['close_hfq'] = merged['close'] * merged['adj_factor']
        merged['bb_middle'] = merged['close_hfq'].rolling(BB_PERIOD).mean()
        merged['bb_std'] = merged['close_hfq'].rolling(BB_PERIOD).std(ddof=0)
        merged['bb_lower'] = merged['bb_middle'] - BB_STD * merged['bb_std']
        merged = merged.dropna(subset=['bb_lower'])
        merged = merged.set_index('date')
        symbol_data[ts] = merged
        if (i+1) % 100 == 0:
            print(f"  数据加载+BB: {i+1}/{len(all_symbols)}")
    print(f"数据加载+BB完成: {len(symbol_data)}只, 耗时: {time.time()-t2:.1f}s")

    # ===== 4. 生成订单（遍历交易日）=====
    t3 = time.time()
    orders = []  # list of {date, ts_code, side, size, price}
    positions = {}  # ts_code -> {shares, avg_cost, level, entry_date}

    for d in trade_days:
        d_ts = pd.Timestamp(d)
        cands = daily_candidates.get(d, [])

        # 4a. 处理已有持仓：止盈/止损/时间止损
        to_sell = []
        for ts, pos in list(positions.items()):
            if ts not in symbol_data: continue
            sd = symbol_data[ts]
            if d_ts not in sd.index: continue
            row = sd.loc[d_ts]
            avg_cost = pos['avg_cost']
            tp_price = avg_cost * (1 + TP_RATIO)
            sl_price = avg_cost * (1 - SL_RATIO) if SL_RATIO > 0 else None
            holding_days = (d_ts - pos['entry_date']).days

            sell = False
            sell_price = None
            reason = None
            # 止盈
            tp_triggered = row['high'] >= tp_price
            # 价格止损（仅当SL_RATIO>0时）
            sl_triggered = sl_price is not None and row['low'] <= sl_price

            if tp_triggered and sl_triggered:
                # 同日冲突用conservative（止损优先）
                sell = True; sell_price = sl_price; reason = 'SL'
            elif tp_triggered:
                sell = True; sell_price = tp_price; reason = 'TP'
            elif sl_triggered:
                sell = True; sell_price = sl_price; reason = 'SL'
            elif holding_days >= TIME_STOP_DAYS:
                sell = True; sell_price = row['close']; reason = 'TS'

            if sell:
                # T+1检查：当天买入的不能卖
                sellable = pos['shares']  # 简化：假设都可卖（实际T+1在买入时已偏移日期）
                to_sell.append((ts, sellable, sell_price, reason))

        # 执行卖出
        for ts, shares, price, reason in to_sell:
            if ts in positions:
                orders.append({'date': d_ts, 'ts_code': ts, 'side': 'sell', 'size': shares, 'price': price})
                del positions[ts]

        # 4b. 加仓（已有持仓且未满仓）
        for ts, pos in list(positions.items()):
            if pos['level'] >= MAX_LEVELS: continue
            if ts not in symbol_data: continue
            sd = symbol_data[ts]
            if d_ts not in sd.index: continue
            row = sd.loc[d_ts]
            # 跌停不加仓（简化：close <= pre_close*0.9）
            if row['close'] <= row['pre_close'] * 0.905: continue
            if row['close_hfq'] < row['bb_lower']:
                # 加仓
                budget = INITIAL_CASH / MAX_POSITIONS / MAX_LEVELS
                shares = int(budget / row['close'] / 100) * 100
                if shares >= 100:
                    total_cost = pos['shares'] * pos['avg_cost'] + shares * row['close']
                    pos['shares'] += shares
                    pos['avg_cost'] = total_cost / pos['shares']
                    pos['level'] += 1
                    orders.append({'date': d_ts, 'ts_code': ts, 'side': 'buy', 'size': shares, 'price': row['close']})

        # 4c. 开新仓（有空位）
        if len(positions) < MAX_POSITIONS:
            for c in cands:
                if len(positions) >= MAX_POSITIONS: break
                ts = c['ts_code']
                if ts in positions: continue
                if ts not in symbol_data: continue
                sd = symbol_data[ts]
                if d_ts not in sd.index: continue
                row = sd.loc[d_ts]
                # 跌停不买
                if row['close'] <= row['pre_close'] * 0.905: continue
                if row['close_hfq'] < row['bb_lower']:
                    budget = INITIAL_CASH / MAX_POSITIONS / MAX_LEVELS
                    shares = int(budget / row['close'] / 100) * 100
                    if shares >= 100:
                        positions[ts] = {'shares': shares, 'avg_cost': row['close'], 'level': 1, 'entry_date': d_ts}
                        orders.append({'date': d_ts, 'ts_code': ts, 'side': 'buy', 'size': shares, 'price': row['close']})

    print(f"订单生成完成: {len(orders)}笔, 耗时: {time.time()-t3:.1f}s")

    if not orders:
        print("无订单生成！")
        return

    # ===== 5. VectorBT回测 =====
    t4 = time.time()
    orders_df = pd.DataFrame(orders)
    orders_df['date'] = pd.to_datetime(orders_df['date'])

    # 用VectorBT from_orders - 宽表格式
    all_order_symbols = orders_df['ts_code'].unique()
    print(f"VectorBT回测中... 订单数: {len(orders_df)}, 股票数: {len(all_order_symbols)}")

    # 构建size和price宽表（时间×资产）
    size_wide = pd.DataFrame(0.0, index=trade_days, columns=all_order_symbols)
    price_wide = pd.DataFrame(np.nan, index=trade_days, columns=all_order_symbols)

    for _, row in orders_df.iterrows():
        d = pd.Timestamp(row['date'])
        ts = row['ts_code']
        s = row['size'] if row['side'] == 'buy' else -row['size']
        if d in size_wide.index:
            size_wide.loc[d, ts] = size_wide.loc[d, ts] + s  # 同日多笔合并
            price_wide.loc[d, ts] = row['price']

    # 构建close宽表
    close_dict = {}
    for ts in all_order_symbols:
        if ts in symbol_data:
            close_dict[ts] = symbol_data[ts]['close']
    close_prices = pd.DataFrame(close_dict)
    close_prices = close_prices.reindex(trade_days).ffill()

    # 确保所有DataFrame索引和列严格一致
    common_idx = close_prices.index
    common_cols = close_prices.columns
    size_wide = size_wide.reindex(index=common_idx, columns=common_cols).fillna(0)
    price_wide = price_wide.reindex(index=common_idx, columns=common_cols)
    close_prices = close_prices.reindex(index=common_idx, columns=common_cols).ffill()

    try:
        portfolio = vbt.Portfolio.from_orders(
            close=close_prices,
            size=size_wide,
            price=price_wide,
            init_cash=INITIAL_CASH,
            fees=0.00025,  # 佣金万2.5
            fixed_fees=0,
            slippage=0.001,  # 滑点万1
            cash_sharing=True,  # 3只股票共享现金池
            allow_partial=False,
            raise_reject=False,
        )
    except Exception as e:
        print(f"from_orders失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return

    print(f"VectorBT回测完成, 耗时: {time.time()-t4:.1f}s")

    # ===== 6. 结果分析 =====
    final_value = portfolio.value().iloc[-1]
    total_return = (final_value - INITIAL_CASH) / INITIAL_CASH * 100
    max_dd = portfolio.max_drawdown() * 100
    # 手动计算Sharpe避免freq问题
    nav_series = portfolio.value()
    daily_rets = nav_series.pct_change().dropna()
    sharpe = (daily_rets.mean() / daily_rets.std() * np.sqrt(252)) if len(daily_rets) > 1 and daily_rets.std() > 0 else 0
    n_days = len(portfolio.value())
    annual_return = ((final_value / INITIAL_CASH) ** (252 / max(n_days, 1)) - 1) * 100

    trades = portfolio.trades.records_readable
    n_trades = len(trades)
    if n_trades > 0 and 'PnL' in trades.columns:
        win_trades = trades[trades['PnL'] > 0]
        win_rate = len(win_trades) / n_trades * 100
    else:
        win_rate = 0

    print(f"\n{'='*70}")
    print(f"回测结果（VectorBT版）")
    print(f"{'='*70}")
    print(f"初始资金:     {INITIAL_CASH:,.0f}")
    print(f"最终权益:     {final_value:,.2f}")
    print(f"累计收益:     {total_return:+.2f}%")
    print(f"年化收益:     {annual_return:+.2f}%")
    print(f"最大回撤:     {max_dd:.2f}%")
    print(f"Sharpe:       {sharpe:.3f}")
    print(f"交易笔数:     {n_trades}")
    print(f"胜率:         {win_rate:.1f}%")

    # 年度收益
    nav = portfolio.value()
    nav_df = pd.DataFrame({'total_equity': nav})
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
    sl_tag = f"sl{int(SL_RATIO*100)}" if SL_RATIO > 0 else "nosl"
    tag = f"tp{int(TP_RATIO*100)}_{sl_tag}_ts{TIME_STOP_DAYS}_l{MAX_LEVELS}_p{MAX_POSITIONS}"
    nav_path = os.path.join(project_root, 'results', 'reports', f'nav_vbt_{tag}_{timestamp}.csv')
    trades_path = os.path.join(project_root, 'results', 'trades', f'trades_vbt_{tag}_{timestamp}.csv')
    nav_df.to_csv(nav_path)
    trades.to_csv(trades_path, index=False)
    print(f"\n净值曲线: {nav_path}")
    print(f"交易记录: {trades_path}")
    print(f"\n总耗时: {time.time()-t0:.1f}s")

if __name__ == '__main__':
    main()
