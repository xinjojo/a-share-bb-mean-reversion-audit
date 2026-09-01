"""
1层策略 + 紧止损 回测验证（用户方案：只做1层，止损放-0.05%）
=============================================================
验证问题：止损-0.05%能否"过滤亏损、保留高盈亏比"？
- 策略：BB下轨买/上轨卖，只买1层（每层20万），N_LEVELS=1
- 止损：收盘价<=成本×(1-止损%)触发，当日收盘价卖出；T+1；止损优先于加仓/止盈
- 对比档位：无止损 / -0.05% / -0.1% / -0.3% / -0.5% / -1% / -3%
"""
import os, time
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

BB_PERIOD = 20
BB_STD = 2.0
INITIAL_CASH = 1_000_000
LEVEL_CASH = INITIAL_CASH / 5
N_LEVELS = 1
COMMISSION_RATE = 0.00025
MIN_COMMISSION = 5.0
STAMP_TAX_RATE = 0.0005
TRANSFER_FEE_RATE = 0.00001
STOP_PCTS = [None, 0.05, 0.1, 0.3, 0.5, 1.0, 3.0]
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
                # 持仓：判定止损/止盈
                if st['shares'] > 0:
                    stop_price = st['avg_cost'] * (1 - p / 100) if p is not None else None
                    stop_hit = (p is not None) and (i > st['buy_idx']) and (close_adj[i] <= stop_price)
                    tp_hit = (i > st['buy_idx']) and (not np.isnan(bb_upper[i])) and (high_adj[i] >= bb_upper[i])
                    if stop_hit:
                        sell_price = close_adj[i]; exit_type = 'STOP_LOSS'
                    elif tp_hit:
                        sell_price = min(bb_upper[i], high_adj[i]); exit_type = 'TAKE_PROFIT_UB'
                    else:
                        sell_price = None
                    if sell_price is not None:
                        amount = sell_price * st['shares']
                        fee = calc_fee_sell(amount)
                        proceeds = amount - fee
                        pnl = proceeds - st['total_cost']
                        return_pct = pnl / st['total_cost'] * 100 if st['total_cost'] > 0 else 0.0
                        results[p].append({
                            'exit_type': exit_type, 'pnl': pnl, 'cost': st['total_cost'],
                            'return_pct': return_pct, 'hold_days': i - st['buy_idx'],
                        })
                        st['shares'] = 0; st['avg_cost'] = 0.0; st['levels'] = 0
                        st['buy_idx'] = -1; st['total_cost'] = 0.0
                        continue
                    # 1层已满，不加仓
                # 无持仓：新开仓
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

        for p in STOP_PCTS:
            st = states[p]
            if st['shares'] > 0:
                final_price = close_adj[-1]
                amount = final_price * st['shares']
                fee = calc_fee_sell(amount)
                proceeds = amount - fee
                pnl = proceeds - st['total_cost']
                return_pct = pnl / st['total_cost'] * 100 if st['total_cost'] > 0 else 0.0
                results[p].append({'exit_type': 'FINAL_SETTLE', 'pnl': pnl, 'cost': st['total_cost'],
                                   'return_pct': return_pct, 'hold_days': n - 1 - st['buy_idx']})

        if (si + 1) % 1000 == 0:
            print(f'  已处理 {si+1}/{len(stocks)}，用时 {time.time()-t0:.0f}s', flush=True)

    print('\n===== 1层策略 + 紧止损 回测对比 =====')
    rows = []
    for p in STOP_PCTS:
        d = pd.DataFrame(results[p])
        wins = d[d['pnl'] > 0]; loss = d[d['pnl'] <= 0]
        pf = wins['pnl'].sum() / abs(loss['pnl'].sum()) if loss['pnl'].sum() != 0 else np.inf
        label = '无止损' if p is None else f'-{p}%'
        rows.append({
            '止损': label, '回合数': len(d),
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
    df_res = pd.DataFrame(rows)
    print(df_res.to_string(index=False))
    df_res.to_csv(os.path.join(PROJECT_ROOT, 'results', 'level1_tightstop.csv'), index=False)
    print(f'\n完成，总用时 {time.time()-t0:.0f}s', flush=True)


if __name__ == '__main__':
    main()
