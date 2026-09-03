"""
止损敏感性回测：BB下轨买/上轨卖（N=5）+ 固定百分比止损 对比
============================================================
止损规则：
- stop_loss_mode = fixed_percent，触发阈值 = avg_cost × (1 - stop_pct)
- 触发判定：持仓期间某交易日 收盘后复权价 <= 止损价（用收盘价触发，避免影线假突破）
- 执行：触发当日按收盘价卖出（与"收盘买入"口径一致；跌停可能卖不出的现实因素列为近似）
- 优先级：止损优先于加仓（当天收盘<=止损价则卖出，不再加仓）
- T+1：买入当日不可卖（止损同样遵守）
- 止损后当天不重新买入，次日重新扫描

档位：disabled / 3% / 5% / 7% / 10% / 15%
一次遍历同时跑6个配置。
"""
import os, time
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

BB_PERIOD = 20
BB_STD = 2.0
INITIAL_CASH = 1_000_000
LEVEL_CASH = INITIAL_CASH / 5
N_LEVELS = 5
COMMISSION_RATE = 0.00025
MIN_COMMISSION = 5.0
STAMP_TAX_RATE = 0.0005
TRANSFER_FEE_RATE = 0.00001
STOP_PCTS = [None, 3, 5, 7, 10, 15]   # None=disabled
START_DATE = '2020-01-01'
END_DATE = '2026-08-25'


def calc_fee_buy(amount):
    return max(amount * COMMISSION_RATE, MIN_COMMISSION) + amount * TRANSFER_FEE_RATE


def calc_fee_sell(amount):
    return max(amount * COMMISSION_RATE, MIN_COMMISSION) + amount * STAMP_TAX_RATE + amount * TRANSFER_FEE_RATE


def new_state():
    return {'shares': 0, 'avg_cost': 0.0, 'levels': 0, 'buy_idx': -1, 'total_cost': 0.0}


def main():
    t0 = time.time()
    print('加载数据...', flush=True)
    combined = pd.read_parquet(os.path.join(PROJECT_ROOT, 'data', 'combined_daily.parquet'))
    combined['date'] = pd.to_datetime(combined['date'])
    combined = combined[(combined['date'] >= START_DATE) & (combined['date'] <= END_DATE)]
    stocks = [g for _, g in combined.groupby('ts_code', sort=False)]
    subset = int(os.environ.get('STOCK_SUBSET', '0'))
    if subset > 0:
        stocks = stocks[:subset]
    print(f'股票数: {len(stocks)}', flush=True)

    results = {p: [] for p in STOP_PCTS}

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
        states = {p: new_state() for p in STOP_PCTS}

        for i in range(n):
            is_limit_down = (pre_close[i] > 0) and (close_raw[i] <= pre_close[i] * 0.905)

            for p in STOP_PCTS:
                st = states[p]
                if st['shares'] <= 0:
                    continue

                # 止损优先判定：收盘价 <= 止损价（仅当配置启用止损且非买入当天）
                stop_price = st['avg_cost'] * (1 - p / 100) if p is not None else None
                stop_hit = (p is not None) and (i > st['buy_idx']) and (stop_price is not None) \
                           and (close_adj[i] <= stop_price)

                # 上轨止盈判定
                tp_hit = (i > st['buy_idx']) and (not np.isnan(bb_upper[i])) and (high_adj[i] >= bb_upper[i])

                if stop_hit:
                    # 止损：按收盘价卖出
                    sell_price = close_adj[i]
                    exit_type = 'STOP_LOSS'
                elif tp_hit:
                    # 止盈：按上轨价卖出
                    sell_price = min(bb_upper[i], high_adj[i])
                    exit_type = 'TAKE_PROFIT_UB'
                else:
                    sell_price = None

                if sell_price is not None:
                    amount = sell_price * st['shares']
                    fee = calc_fee_sell(amount)
                    proceeds = amount - fee
                    pnl = proceeds - st['total_cost']
                    return_pct = pnl / st['total_cost'] * 100 if st['total_cost'] > 0 else 0.0
                    results[p].append({
                        'ts_code': ts_code,
                        'levels_used': st['levels'],
                        'entry_date': str(dates[st['buy_idx']]),
                        'exit_date': str(dates[i]),
                        'exit_type': exit_type,
                        'pnl': pnl,
                        'cost': st['total_cost'],
                        'return_pct': return_pct,
                        'hold_days': i - st['buy_idx'],
                    })
                    st['shares'] = 0
                    st['avg_cost'] = 0.0
                    st['levels'] = 0
                    st['buy_idx'] = -1
                    st['total_cost'] = 0.0
                    continue

                # 加仓：止损未触发、未止盈、收盘<下轨、未满仓
                if not np.isnan(bb_lower[i]) and close_adj[i] < bb_lower[i] and not is_limit_down:
                    if st['levels'] < N_LEVELS:
                        buy_price = close_adj[i]
                        qty = int(LEVEL_CASH / buy_price / 100) * 100
                        if qty >= 100:
                            amount = buy_price * qty
                            fee = calc_fee_buy(amount)
                            cost_add = amount + fee
                            old_cost = st['shares'] * st['avg_cost']
                            st['shares'] += qty
                            st['avg_cost'] = (old_cost + cost_add) / st['shares']
                            st['total_cost'] += cost_add
                            st['levels'] += 1
                            if st['levels'] == 1:
                                st['buy_idx'] = i
                            continue

            # 新开仓（无持仓时）：收盘<下轨 + 非跌停 → 买第一层
            for p in STOP_PCTS:
                st = states[p]
                if st['shares'] <= 0 and not np.isnan(bb_lower[i]) and close_adj[i] < bb_lower[i] and not is_limit_down:
                    buy_price = close_adj[i]
                    qty = int(LEVEL_CASH / buy_price / 100) * 100
                    if qty >= 100:
                        amount = buy_price * qty
                        fee = calc_fee_buy(amount)
                        cost_add = amount + fee
                        st['shares'] += qty
                        st['avg_cost'] = (amount + fee) / qty
                        st['total_cost'] += cost_add
                        st['levels'] = 1
                        st['buy_idx'] = i

        # 期末未平仓按最后收盘价结算
        for p in STOP_PCTS:
            st = states[p]
            if st['shares'] > 0:
                final_price = close_adj[-1]
                amount = final_price * st['shares']
                fee = calc_fee_sell(amount)
                proceeds = amount - fee
                pnl = proceeds - st['total_cost']
                return_pct = pnl / st['total_cost'] * 100 if st['total_cost'] > 0 else 0.0
                results[p].append({
                    'ts_code': ts_code,
                    'levels_used': st['levels'],
                    'entry_date': str(dates[st['buy_idx']]),
                    'exit_date': str(dates[n - 1]),
                    'exit_type': 'FINAL_SETTLE',
                    'pnl': pnl,
                    'cost': st['total_cost'],
                    'return_pct': return_pct,
                    'hold_days': n - 1 - st['buy_idx'],
                })

        if (si + 1) % 1000 == 0:
            print(f'  已处理 {si+1}/{len(stocks)}，用时 {time.time()-t0:.0f}s', flush=True)

    # 汇总
    print('\n===== 止损敏感性对比 =====')
    rows = []
    for p in STOP_PCTS:
        d = pd.DataFrame(results[p])
        wins = d[d['pnl'] > 0]
        loss = d[d['pnl'] <= 0]
        pf = wins['pnl'].sum() / abs(loss['pnl'].sum()) if loss['pnl'].sum() != 0 else np.inf
        label = '无止损' if p is None else f'-{p}%'
        rows.append({
            '止损': label,
            '回合数': len(d),
            '简单平均收益%': round(d['return_pct'].mean(), 2),
            '资金加权收益%': round(d['pnl'].sum() / d['cost'].sum() * 100, 2),
            '胜率%': round((d['pnl'] > 0).mean() * 100, 1),
            '平均盈利%': round(wins['return_pct'].mean(), 2) if len(wins) else 0,
            '平均亏损%': round(loss['return_pct'].mean(), 2) if len(loss) else 0,
            '盈亏比': round(wins['return_pct'].mean() / abs(loss['return_pct'].mean()), 2) if len(loss) else 0,
            'ProfitFactor': round(pf, 2),
            '总盈亏(万元)': round(d['pnl'].sum() / 1e4, 0),
            '止损单占比%': round((d['exit_type'] == 'STOP_LOSS').mean() * 100, 1),
            '平均持仓天': round(d['hold_days'].mean(), 1),
        })
        d.to_parquet(os.path.join(PROJECT_ROOT, 'results', f'stop_loss_{p}.parquet'))
    df_res = pd.DataFrame(rows)
    print(df_res.to_string(index=False))
    df_res.to_csv(os.path.join(PROJECT_ROOT, 'results', 'stop_loss_sensitivity.csv'), index=False)
    print(f'\n完成，总用时 {time.time()-t0:.0f}s', flush=True)


if __name__ == '__main__':
    main()
