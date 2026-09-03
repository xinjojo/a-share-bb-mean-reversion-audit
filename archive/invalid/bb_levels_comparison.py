"""
层数对比回测：BB下轨买/上轨卖 策略，最大层数 1/2/3/4/5 对比
============================================================
沿用与 export_trade_details.py 完全相同的策略逻辑：
- 每只股票独立初始资金100万，每层固定20万（LEVEL_CASH = 100万/5）
- 买入：收盘后复权价 < BB下轨(20,2) 且非跌停 → 买一层；最多N层
- 卖出：盘中复权最高价 >= BB上轨 → 全部卖出（T+1：买入当日不可卖）
- 100股整数倍、买不起100股跳过
- 跌停日不买入；期末未平仓按最后收盘价结算
- 费用：佣金0.025%最低5元、印花税0.05%卖出收、过户费0.001%
- 后复权价格（close*adj_factor）

一次遍历同时维护5个配置（N=1/2/3/4/5）的状态，只读一遍数据。
输出：每配置的回合级结果 → 用于统计对比。
"""
import os, time
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

BB_PERIOD = 20
BB_STD = 2.0
INITIAL_CASH = 1_000_000
LEVEL_CASH = INITIAL_CASH / 5          # 每层固定20万
COMMISSION_RATE = 0.00025
MIN_COMMISSION = 5.0
STAMP_TAX_RATE = 0.0005
TRANSFER_FEE_RATE = 0.00001
CONFIGS = [1, 2, 3, 4, 5]              # 最大层数
START_DATE = '2020-01-01'
END_DATE = '2026-08-25'


def calc_fee_buy(amount):
    commission = max(amount * COMMISSION_RATE, MIN_COMMISSION)
    transfer = amount * TRANSFER_FEE_RATE
    return commission + transfer


def calc_fee_sell(amount):
    commission = max(amount * COMMISSION_RATE, MIN_COMMISSION)
    stamp = amount * STAMP_TAX_RATE
    transfer = amount * TRANSFER_FEE_RATE
    return commission + stamp + transfer


def new_state():
    return {'cash': INITIAL_CASH, 'shares': 0, 'avg_cost': 0.0, 'levels': 0, 'buy_idx': -1}


def main():
    t0 = time.time()
    print('加载数据...', flush=True)
    combined = pd.read_parquet(os.path.join(PROJECT_ROOT, 'data', 'combined_daily.parquet'))
    combined['date'] = pd.to_datetime(combined['date'])
    combined = combined[(combined['date'] >= START_DATE) & (combined['date'] <= END_DATE)]
    # 按股票分组
    stocks = [g for _, g in combined.groupby('ts_code', sort=False)]
    subset = int(os.environ.get('STOCK_SUBSET', '0'))
    if subset > 0:
        stocks = stocks[:subset]
    print(f'股票数: {len(stocks)}，数据行: {len(combined)}', flush=True)

    # 每个配置收集回合
    results = {n: [] for n in CONFIGS}

    for si, df in enumerate(stocks):
        ts_code = df['ts_code'].iloc[0]
        close_adj = (df['close'] * df['adj_factor']).values
        high_adj = (df['high'] * df['adj_factor']).values
        pre_close = df['pre_close'].values
        close_raw = df['close'].values
        dates = df['date'].values

        ma = pd.Series(close_adj).rolling(BB_PERIOD).mean().values
        std = pd.Series(close_adj).rolling(BB_PERIOD).std().values
        bb_upper = ma + BB_STD * std
        bb_lower = ma - BB_STD * std

        n = len(df)
        states = {c: new_state() for c in CONFIGS}

        for i in range(n):
            is_limit_down = (pre_close[i] > 0) and (close_raw[i] <= pre_close[i] * 0.905)

            for c in CONFIGS:
                st = states[c]
                # 卖出：持仓 + 非买入当天(T+1) + 盘中触及上轨
                if st['shares'] > 0 and i > st['buy_idx'] and not np.isnan(bb_upper[i]) and high_adj[i] >= bb_upper[i]:
                    sell_price = min(bb_upper[i], high_adj[i])
                    amount = sell_price * st['shares']
                    fee = calc_fee_sell(amount)
                    proceeds = amount - fee
                    cost_amount = st['avg_cost'] * st['shares']
                    pnl = proceeds - cost_amount
                    return_pct = pnl / cost_amount * 100 if cost_amount > 0 else 0.0
                    results[c].append({
                        'ts_code': ts_code,
                        'entry_date': str(dates[st['buy_idx']]),
                        'exit_date': str(dates[i]),
                        'exit_type': 'TAKE_PROFIT_UB',
                        'levels_used': st['levels'],
                        'pnl': pnl,
                        'cost': cost_amount,
                        'return_pct': return_pct,
                        'hold_days': i - st['buy_idx'],
                    })
                    st['cash'] += proceeds
                    st['shares'] = 0
                    st['avg_cost'] = 0.0
                    st['levels'] = 0
                    st['buy_idx'] = -1
                    continue

                # 买入：收盘<下轨 + 非跌停 + 未满仓
                if not np.isnan(bb_lower[i]) and close_adj[i] < bb_lower[i] and not is_limit_down:
                    if st['levels'] < c:
                        buy_price = close_adj[i]
                        qty = int(LEVEL_CASH / buy_price / 100) * 100
                        if qty >= 100:
                            amount = buy_price * qty
                            fee = calc_fee_buy(amount)
                            total_cost = amount + fee
                            if total_cost <= st['cash']:
                                st['cash'] -= total_cost
                                old_cost = st['shares'] * st['avg_cost']
                                st['shares'] += qty
                                st['avg_cost'] = (old_cost + total_cost) / st['shares']
                                st['levels'] += 1
                                if st['levels'] == 1:
                                    st['buy_idx'] = i

        # 期末未平仓按最后收盘价结算
        for c in CONFIGS:
            st = states[c]
            if st['shares'] > 0:
                final_price = close_adj[-1]
                amount = final_price * st['shares']
                fee = calc_fee_sell(amount)
                proceeds = amount - fee
                cost_amount = st['avg_cost'] * st['shares']
                pnl = proceeds - cost_amount
                return_pct = pnl / cost_amount * 100 if cost_amount > 0 else 0.0
                results[c].append({
                    'ts_code': ts_code,
                    'entry_date': str(dates[st['buy_idx']]),
                    'exit_date': str(dates[n - 1]),
                    'exit_type': 'FINAL_SETTLE',
                    'levels_used': st['levels'],
                    'pnl': pnl,
                    'cost': cost_amount,
                    'return_pct': return_pct,
                    'hold_days': n - 1 - st['buy_idx'],
                })

        if (si + 1) % 1000 == 0:
            print(f'  已处理 {si+1}/{len(stocks)} 只，用时 {time.time()-t0:.0f}s', flush=True)

    out = {}
    for c in CONFIGS:
        d = pd.DataFrame(results[c])
        d.to_parquet(os.path.join(PROJECT_ROOT, 'results', f'levels_cmp_{c}layer.parquet'))
        out[c] = d
        print(f'配置 N={c}: 回合数={len(d)}', flush=True)

    print(f'完成，总用时 {time.time()-t0:.0f}s', flush=True)


if __name__ == '__main__':
    main()
