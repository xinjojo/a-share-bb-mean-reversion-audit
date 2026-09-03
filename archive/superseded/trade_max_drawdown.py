"""
逐笔持仓最大浮亏统计（按实际使用层数分组）
============================================
策略：BB下轨买/上轨卖（N=5，每层20万），与 export_trade_details.py 完全一致。
新增：对每笔回合，逐日（收盘后）计算持仓浮亏 = (当日持仓市值 - 累计成本含费)/累计成本，
     记录该笔持仓期间的最大浮亏（最深值，用后复权价）。
     加仓日：当天收盘买入后即更新成本与持仓，按加仓后状态计算当日浮亏。

输出：按 levels_used=1..5 分组，统计最大/平均/中位数/分位数浮亏，
     以及浮亏超过 -3/-5/-8/-10/-15/-20% 的比例（用于定止损）。
"""
import os, time
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

BB_PERIOD = 20
BB_STD = 2.0
INITIAL_CASH = 1_000_000
LEVEL_CASH = INITIAL_CASH / 5
N_LEVELS = int(os.environ.get('MAX_LEVELS', '5'))
COMMISSION_RATE = 0.00025
MIN_COMMISSION = 5.0
STAMP_TAX_RATE = 0.0005
TRANSFER_FEE_RATE = 0.00001
START_DATE = '2020-01-01'
END_DATE = '2026-08-25'


def calc_fee_buy(amount):
    return max(amount * COMMISSION_RATE, MIN_COMMISSION) + amount * TRANSFER_FEE_RATE


def calc_fee_sell(amount):
    return max(amount * COMMISSION_RATE, MIN_COMMISSION) + amount * STAMP_TAX_RATE + amount * TRANSFER_FEE_RATE


def main():
    t0 = time.time()
    print('加载数据...', flush=True)
    combined = pd.read_parquet(os.path.join(PROJECT_ROOT, 'data', 'combined_daily.parquet'))
    combined['date'] = pd.to_datetime(combined['date'])
    combined = combined[(combined['date'] >= START_DATE) & (combined['date'] <= END_DATE)]
    stocks = [g for _, g in combined.groupby('ts_code', sort=False)]
    print(f'股票数: {len(stocks)}', flush=True)

    trades = []   # 每笔回合：含最大浮亏

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
        shares = 0
        avg_cost = 0.0
        levels = 0
        buy_idx = -1
        total_cost = 0.0      # 累计买入成本含费
        max_dd = 0.0          # 当前回合最大浮亏%（最深负值）

        for i in range(n):
            is_limit_down = (pre_close[i] > 0) and (close_raw[i] <= pre_close[i] * 0.905)

            # 卖出：持仓 + 非买入当天(T+1) + 盘中触及上轨
            if shares > 0 and i > buy_idx and not np.isnan(bb_upper[i]) and high_adj[i] >= bb_upper[i]:
                sell_price = min(bb_upper[i], high_adj[i])
                amount = sell_price * shares
                fee = calc_fee_sell(amount)
                proceeds = amount - fee
                pnl = proceeds - total_cost
                return_pct = pnl / total_cost * 100 if total_cost > 0 else 0.0
                trades.append({
                    'ts_code': ts_code,
                    'levels_used': levels,
                    'entry_date': str(dates[buy_idx]),
                    'exit_date': str(dates[i]),
                    'exit_type': 'TAKE_PROFIT_UB',
                    'hold_days': i - buy_idx,
                    'pnl': pnl,
                    'cost': total_cost,
                    'return_pct': return_pct,
                    'max_drawdown_pct': round(max_dd, 4),
                })
                shares = 0
                avg_cost = 0.0
                levels = 0
                buy_idx = -1
                total_cost = 0.0
                max_dd = 0.0
                continue

            # 买入/加仓：收盘<下轨 + 非跌停 + 未满仓
            if not np.isnan(bb_lower[i]) and close_adj[i] < bb_lower[i] and not is_limit_down:
                if levels < N_LEVELS:
                    buy_price = close_adj[i]
                    qty = int(LEVEL_CASH / buy_price / 100) * 100
                    if qty >= 100:
                        amount = buy_price * qty
                        fee = calc_fee_buy(amount)
                        cost_add = amount + fee
                        if cost_add <= INITIAL_CASH:  # 足够（每配置独立现金足够）
                            old_cost = shares * avg_cost
                            shares += qty
                            avg_cost = (old_cost + cost_add) / shares
                            total_cost += cost_add
                            levels += 1
                            if levels == 1:
                                buy_idx = i
                                max_dd = 0.0
                            # 加仓后按当日收盘价更新浮亏
                            if shares > 0 and total_cost > 0:
                                dd = (shares * close_adj[i] - total_cost) / total_cost * 100
                                if dd < max_dd:
                                    max_dd = dd

            # 每个持仓日收盘后更新浮亏（非买入日也在内）
            if shares > 0 and total_cost > 0 and not np.isnan(close_adj[i]):
                dd = (shares * close_adj[i] - total_cost) / total_cost * 100
                if dd < max_dd:
                    max_dd = dd

        # 期末未平仓按最后收盘价结算
        if shares > 0:
            final_price = close_adj[-1]
            amount = final_price * shares
            fee = calc_fee_sell(amount)
            proceeds = amount - fee
            pnl = proceeds - total_cost
            return_pct = pnl / total_cost * 100 if total_cost > 0 else 0.0
            trades.append({
                'ts_code': ts_code,
                'levels_used': levels,
                'entry_date': str(dates[buy_idx]),
                'exit_date': str(dates[n - 1]),
                'exit_type': 'FINAL_SETTLE',
                'hold_days': n - 1 - buy_idx,
                'pnl': pnl,
                'cost': total_cost,
                'return_pct': return_pct,
                'max_drawdown_pct': round(max_dd, 4),
            })

        if (si + 1) % 1000 == 0:
            print(f'  已处理 {si+1}/{len(stocks)}，用时 {time.time()-t0:.0f}s', flush=True)

    df_t = pd.DataFrame(trades)
    df_t.to_parquet(os.path.join(PROJECT_ROOT, 'results', 'trades_with_maxdd.parquet'))
    print(f'总回合数: {len(df_t)}，用时 {time.time()-t0:.0f}s', flush=True)

    # ===== 按 levels_used 分组统计 =====
    print('\n===== 持仓最大浮亏统计（按实际使用层数） =====')
    thresholds = [3, 5, 8, 10, 15, 20]
    rows = []
    for lv in [1, 2, 3, 4, 5]:
        sub = df_t[df_t['levels_used'] == lv]
        dd = sub['max_drawdown_pct']
        r = {
            '层数': lv,
            '交易数': len(sub),
            '最大回撤%(最深)': round(dd.min(), 2),
            '平均回撤%': round(dd.mean(), 2),
            '中位回撤%': round(dd.median(), 2),
            '25分位%': round(dd.quantile(0.25), 2),
            '75分位%': round(dd.quantile(0.75), 2),
        }
        for t in thresholds:
            r[f'浮亏≤-{t}%占比'] = round((dd <= -t).mean() * 100, 1)
        rows.append(r)
    df_stat = pd.DataFrame(rows)
    print(df_stat.to_string(index=False))
    df_stat.to_csv(os.path.join(PROJECT_ROOT, 'results', 'maxdd_by_level.csv'), index=False)

    # ===== 整体 =====
    dd_all = df_t['max_drawdown_pct']
    print(f'\n整体: 交易数{len(df_t)}, 最深回撤{dd_all.min():.2f}%, 平均{dd_all.mean():.2f}%, 中位{dd_all.median():.2f}%')
    print('整体浮亏分布:')
    for t in thresholds:
        print(f'  浮亏≤-{t}%: {(dd_all <= -t).mean()*100:.1f}%')


if __name__ == '__main__':
    main()
