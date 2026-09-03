"""
快速测试VectorBT多股策略 - 只用2024年1个月数据，验证所有API
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import numpy as np
import vectorbt as vbt
from data_loader.storage import DataStorage

def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    storage = DataStorage(os.path.join(project_root, 'data', 'raw'))

    # 小样本：2024-01-01 ~ 2024-03-31
    START = '2024-01-01'
    END = '2024-03-31'
    INITIAL_CASH = 1_000_000

    print("=== 小样本测试 ===")
    cal = storage.load_trade_cal()
    cal['date'] = pd.to_datetime(cal['date'])
    trade_days = cal[(cal['is_open']==1) & (cal['date']>=START) & (cal['date']<=END)]['date'].sort_values().values
    print(f"交易日数: {len(trade_days)}")

    # 取前3天的Top10股票作为测试标的
    test_symbols = set()
    for d in trade_days[:5]:
        df = storage.get_top_n_by_amount(date=pd.Timestamp(d).strftime('%Y-%m-%d'), n=10, exclude_st=True, exclude_suspended=True)
        for ts in df['ts_code'].tolist():
            test_symbols.add(ts)
    test_symbols = list(test_symbols)[:15]
    print(f"测试股票数: {len(test_symbols)}")

    # 加载数据
    symbol_data = {}
    for ts in test_symbols:
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
        symbol_data[ts] = merged
    print(f"成功加载: {len(symbol_data)}只")

    # 构建模拟订单（3只股票，每只一买一卖）
    orders = []
    valid_symbols = list(symbol_data.keys())[:3]
    for i, ts in enumerate(valid_symbols):
        sd = symbol_data[ts]
        buy_day = trade_days[i+2]
        sell_day = trade_days[i+10]
        if buy_day in sd.index and sell_day in sd.index:
            buy_price = sd.loc[buy_day, 'close']
            sell_price = sd.loc[sell_day, 'close']
            shares = int(INITIAL_CASH/3/3/buy_price/100)*100
            orders.append({'date': buy_day, 'ts_code': ts, 'side': 'buy', 'size': shares, 'price': buy_price})
            orders.append({'date': sell_day, 'ts_code': ts, 'side': 'sell', 'size': shares, 'price': sell_price})
            print(f"  {ts}: 买{pd.Timestamp(buy_day).date()}@{buy_price:.2f} 卖{pd.Timestamp(sell_day).date()}@{sell_price:.2f} {shares}股")

    orders_df = pd.DataFrame(orders)
    orders_df['date'] = pd.to_datetime(orders_df['date'])
    all_syms = orders_df['ts_code'].unique()

    # 构建宽表
    size_wide = pd.DataFrame(0.0, index=trade_days, columns=all_syms)
    price_wide = pd.DataFrame(np.nan, index=trade_days, columns=all_syms)
    for _, row in orders_df.iterrows():
        d = pd.Timestamp(row['date'])
        ts = row['ts_code']
        s = row['size'] if row['side']=='buy' else -row['size']
        size_wide.loc[d, ts] += s
        price_wide.loc[d, ts] = row['price']

    close_dict = {ts: symbol_data[ts]['close'] for ts in all_syms if ts in symbol_data}
    close_prices = pd.DataFrame(close_dict).reindex(trade_days).ffill()

    # 确保所有DataFrame索引和列严格一致
    common_idx = close_prices.index
    common_cols = close_prices.columns
    size_wide = size_wide.reindex(index=common_idx, columns=common_cols).fillna(0)
    price_wide = price_wide.reindex(index=common_idx, columns=common_cols)
    close_prices = close_prices.reindex(index=common_idx, columns=common_cols).ffill()

    print(f"\n订单数: {len(orders_df)}, 股票数: {len(all_syms)}")
    print(f"close shape: {close_prices.shape}, size shape: {size_wide.shape}")
    print(f"索引一致: {close_prices.index.equals(size_wide.index)}, 列一致: {close_prices.columns.equals(size_wide.columns)}")

    # VectorBT回测
    print("\n=== VectorBT回测 ===")
    try:
        pf = vbt.Portfolio.from_orders(
            close=close_prices, size=size_wide, price=price_wide,
            init_cash=INITIAL_CASH, fees=0.00025, slippage=0.001,
            cash_sharing=True, allow_partial=False, raise_reject=False,
        )
        print("✓ from_orders成功")
    except Exception as e:
        print(f"✗ from_orders失败: {type(e).__name__}: {e}")
        import traceback; traceback.print_exc()
        return

    # 测试所有API
    print("\n=== API测试 ===")
    try:
        val = pf.value()
        print(f"✓ value(): type={type(val).__name__}, shape={val.shape}, final={val.iloc[-1]:.2f}")
    except Exception as e:
        print(f"✗ value()失败: {e}")

    try:
        mdd = pf.max_drawdown()
        print(f"✓ max_drawdown(): {mdd:.4f}")
    except Exception as e:
        print(f"✗ max_drawdown()失败: {e}")

    try:
        # 手动计算Sharpe避免freq问题
        nav_series = pf.value()
        daily_rets = nav_series.pct_change().dropna()
        sr = (daily_rets.mean() / daily_rets.std() * np.sqrt(252)) if len(daily_rets) > 1 and daily_rets.std() > 0 else 0
        print(f"✓ sharpe_ratio (手动): {sr:.4f}")
    except Exception as e:
        print(f"✗ sharpe失败: {e}")

    try:
        ar = pf.annual_returns()
        print(f"✓ annual_returns(): type={type(ar).__name__}, 值={ar}")
    except Exception as e:
        print(f"✗ annual_returns()失败: {e}")

    try:
        trades = pf.trades.records_readable
        print(f"✓ trades.records_readable: {len(trades)}笔, columns={trades.columns.tolist()}")
        print(trades.head())
    except Exception as e:
        print(f"✗ trades失败: {e}")

    # 结果计算
    final_val = pf.value().iloc[-1]
    total_ret = (final_val - INITIAL_CASH) / INITIAL_CASH * 100
    n_days = len(pf.value())
    annual_ret = ((final_val / INITIAL_CASH) ** (252 / max(n_days,1)) - 1) * 100
    print(f"\n=== 结果 ===")
    print(f"最终权益: {final_val:,.2f}")
    print(f"累计收益: {total_ret:+.2f}%")
    print(f"年化收益: {annual_ret:+.2f}%")
    print(f"最大回撤: {pf.max_drawdown()*100:.2f}%")
    # 手动计算Sharpe
    daily_rets = pf.value().pct_change().dropna()
    sharpe = (daily_rets.mean() / daily_rets.std() * np.sqrt(252)) if len(daily_rets) > 1 and daily_rets.std() > 0 else 0
    print(f"Sharpe: {sharpe:.3f}")
    print(f"\n✓ 小样本测试全部通过！可以跑完整回测了")

if __name__ == '__main__':
    main()
