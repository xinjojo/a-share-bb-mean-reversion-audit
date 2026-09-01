"""
全市场单股回测：布林带下轨买、上轨卖（分5层）
策略：
- 初始资金100万，每层20万（1/5）
- 买入信号：收盘复权价 < 布林带下轨 → 买一层，最多5层
- 加仓：后续交易日再次收盘<下轨 → 加一层（最多5层=满仓）
- 卖出信号：盘中复权最高价 >= 布林带上轨 → 全部卖出
- 卖出后空仓等待下一次买入信号
- 用后复权价格（close*adj_factor）计算，无未来函数
- T+1、跌停不买、100股整数倍
"""
import os, time
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 参数
BB_PERIOD = 20
BB_STD = 2.0
INITIAL_CASH = 1_000_000
N_LEVELS = 5
LEVEL_CASH = INITIAL_CASH / N_LEVELS
COMMISSION_RATE = 0.00025
MIN_COMMISSION = 5.0
STAMP_TAX_RATE = 0.0005
TRANSFER_FEE_RATE = 0.00001
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


def backtest_single(ts_code, df):
    """对单只股票执行BB下轨买/上轨卖策略"""
    close_adj = (df['close'] * df['adj_factor']).values
    high_adj = (df['high'] * df['adj_factor']).values
    pre_close = df['pre_close'].values
    close_raw = df['close'].values
    dates = df['date'].values

    # 布林带
    ma = pd.Series(close_adj).rolling(BB_PERIOD).mean().values
    std = pd.Series(close_adj).rolling(BB_PERIOD).std().values
    bb_upper = ma + BB_STD * std
    bb_lower = ma - BB_STD * std

    n = len(df)
    cash = INITIAL_CASH
    shares = 0
    avg_cost = 0.0
    levels = 0
    buy_idx = -1          # 当前回合第一次买入索引
    round_no = 0
    trades = []
    equity_curve = []

    for i in range(n):
        equity = cash + shares * close_adj[i]
        equity_curve.append(equity)

        is_limit_down = (pre_close[i] > 0) and (close_raw[i] <= pre_close[i] * 0.905)

        # ===== 卖出判断：持仓 + 非买入当天(T+1) + 盘中触及上轨 =====
        if shares > 0 and i > buy_idx and not np.isnan(bb_upper[i]) and high_adj[i] >= bb_upper[i]:
            sell_price = min(bb_upper[i], high_adj[i])
            amount = sell_price * shares
            fee = calc_fee_sell(amount)
            proceeds = amount - fee
            pnl = proceeds - avg_cost * shares
            trades.append({
                'round': round_no,
                'buy_date': str(dates[buy_idx]),
                'sell_date': str(dates[i]),
                'hold_days': i - buy_idx,
                'levels_used': levels,
                'pnl': pnl,
                'sell_price': sell_price,
            })
            cash += proceeds
            shares = 0
            levels = 0
            avg_cost = 0.0
            round_no += 1
            buy_idx = -1
            continue  # 卖出当日不再买入

        # ===== 买入判断：收盘<下轨 + 非跌停 + 未满仓 =====
        if not np.isnan(bb_lower[i]) and close_adj[i] < bb_lower[i] and not is_limit_down:
            if levels < N_LEVELS:
                buy_price = close_adj[i]
                qty = int(LEVEL_CASH / buy_price / 100) * 100
                if qty >= 100:
                    amount = buy_price * qty
                    fee = calc_fee_buy(amount)
                    total_cost = amount + fee
                    if total_cost <= cash:
                        cash -= total_cost
                        old_cost = shares * avg_cost
                        shares += qty
                        avg_cost = (old_cost + total_cost) / shares
                        levels += 1
                        if levels == 1:  # 新回合第一次买入
                            buy_idx = i

    # 未平仓按最后收盘价结算
    if shares > 0:
        final_price = close_adj[-1]
        amount = final_price * shares
        fee = calc_fee_sell(amount)
        proceeds = amount - fee
        pnl = proceeds - avg_cost * shares
        trades.append({
            'round': round_no,
            'buy_date': str(dates[buy_idx]),
            'sell_date': str(dates[-1]),
            'hold_days': n - 1 - buy_idx,
            'levels_used': levels,
            'pnl': pnl,
            'sell_price': final_price,
        })

    final_equity = cash + shares * close_adj[-1]
    total_return = (final_equity - INITIAL_CASH) / INITIAL_CASH * 100

    eq_arr = np.array(equity_curve)
    peak = np.maximum.accumulate(eq_arr)
    drawdown = (eq_arr - peak) / peak * 100
    max_dd = drawdown.min() if len(drawdown) > 0 else 0

    n_rounds = len(trades)
    if n_rounds > 0:
        pnls = np.array([t['pnl'] for t in trades])
        win_rate = (pnls > 0).mean() * 100
        avg_pnl = pnls.mean()
        total_pnl = pnls.sum()
        avg_hold = np.mean([t['hold_days'] for t in trades])
        max_hold = max(t['hold_days'] for t in trades)
        levels_used = [t['levels_used'] for t in trades]
        l1 = levels_used.count(1) / n_rounds * 100
        l2 = levels_used.count(2) / n_rounds * 100
        l3 = levels_used.count(3) / n_rounds * 100
        l4 = levels_used.count(4) / n_rounds * 100
        l5 = levels_used.count(5) / n_rounds * 100
    else:
        win_rate = avg_pnl = total_pnl = avg_hold = max_hold = 0
        l1 = l2 = l3 = l4 = l5 = 0

    years = n / 252
    if years > 0 and final_equity > 0:
        annual_return = ((final_equity / INITIAL_CASH) ** (1 / years) - 1) * 100
    else:
        annual_return = 0

    return {
        'ts_code': ts_code,
        'total_return': total_return,
        'annual_return': annual_return,
        'max_drawdown': max_dd,
        'n_rounds': n_rounds,
        'win_rate': win_rate,
        'avg_pnl': avg_pnl,
        'total_pnl': total_pnl,
        'avg_hold_days': avg_hold,
        'max_hold_days': max_hold,
        'l1_pct': l1, 'l2_pct': l2, 'l3_pct': l3, 'l4_pct': l4, 'l5_pct': l5,
        'final_equity': final_equity,
    }


def main():
    print('加载数据...', flush=True)
    combined = pd.read_parquet(os.path.join(PROJECT_ROOT, 'data', 'combined_daily.parquet'))
    combined['date'] = pd.to_datetime(combined['date'])
    combined = combined[(combined['date'] >= START_DATE) & (combined['date'] <= END_DATE)]

    basic = pd.read_csv(os.path.join(PROJECT_ROOT, 'data', 'raw', 'stock_basic.csv'))
    mv = pd.read_csv(os.path.join(PROJECT_ROOT, 'data', 'raw', 'daily_basic_20241231.csv'))
    mv['total_mv_yi'] = mv['total_mv'] / 10000
    info = basic[['ts_code', 'name', 'industry', 'market', 'list_date']].merge(
        mv[['ts_code', 'total_mv_yi']], on='ts_code', how='left')

    ts_codes = sorted(combined['ts_code'].unique())
    print(f'开始回测 {len(ts_codes)} 只股票...', flush=True)

    # 一次groupby分组，避免反复全表过滤
    grouped = {ts: g.sort_values('date') for ts, g in combined.groupby('ts_code')}

    results = []
    t0 = time.time()
    for idx, ts in enumerate(ts_codes):
        df = grouped[ts]
        if len(df) < BB_PERIOD + 10:
            continue
        try:
            res = backtest_single(ts, df)
            row_info = info[info['ts_code'] == ts]
            if len(row_info) > 0:
                res['name'] = row_info['name'].values[0]
                res['industry'] = row_info['industry'].values[0]
                res['market'] = row_info['market'].values[0]
                res['list_date'] = row_info['list_date'].values[0]
                res['total_mv_yi'] = row_info['total_mv_yi'].values[0]
            else:
                res['name'] = res['industry'] = res['market'] = res['list_date'] = res['total_mv_yi'] = None
            results.append(res)
        except Exception as e:
            print(f'  {ts} 回测失败: {e}', flush=True)

        if (idx + 1) % 1000 == 0:
            print(f'  进度 {idx+1}/{len(ts_codes)}, 耗时{time.time()-t0:.0f}s', flush=True)

    print(f'回测完成, {len(results)}只, 耗时{time.time()-t0:.1f}s', flush=True)

    df_res = pd.DataFrame(results)
    out_path = os.path.join(PROJECT_ROOT, 'results', 'bb_lower_upper_full_market.csv')
    df_res.to_csv(out_path, index=False)
    print(f'保存到: {out_path}', flush=True)

    print(f'\n{"="*60}', flush=True)
    print(f'全市场BB下轨买/上轨卖 策略统计', flush=True)
    print(f'{"="*60}', flush=True)
    print(f'回测股票: {len(df_res)}只', flush=True)
    print(f'盈利股票: {(df_res["total_return"]>0).sum()} ({(df_res["total_return"]>0).mean()*100:.1f}%)', flush=True)
    print(f'平均收益: {df_res["total_return"].mean():+.2f}%', flush=True)
    print(f'中位数:   {df_res["total_return"].median():+.2f}%', flush=True)
    print(f'平均胜率: {df_res["win_rate"].mean():.1f}%', flush=True)
    print(f'平均回合: {df_res["n_rounds"].mean():.1f}', flush=True)
    print(f'平均持仓: {df_res["avg_hold_days"].mean():.1f}天', flush=True)


if __name__ == '__main__':
    main()
