"""
全网格回测：强制层数(1~5) × 止损档(无/2/3/5/7/8/10/12/15/20%) 组合对比
======================================================================
目标：找"期望值 × 资金利用率"的最优甜点（所有交易全包含，无事后分组）

止损规则（用户要求：影线也是浮亏 → 用最低价触发）：
- 止损价 = 加权成本 × (1 - 止损%)
- 触发：持仓期间某日 最低价(low_adj) ≤ 止损价 → 触发止损（盘中触及）
- 成交价：若当日开盘价 ≤ 止损价（跳空低开）→ 按开盘价成交；否则按止损价成交
- 止损优先于止盈（同日冲突取保守：假设低点晚于高点）
- T+1：买入当日不可卖（止损同样遵守）

止盈：盘中最高价 ≥ 布林上轨 → 按 min(high, 上轨) 成交（T+1）
加仓：收盘价 < 下轨 且 未满仓 且 未触发止损 → 买一层（每层20万，100股整数倍）
停牌/跌停：跌停日（is_limit_down）不买入

输出指标：回合数 / 简单平均收益 / 资金加权收益 / 胜率 / 平均盈利 / 平均亏损 / 盈亏比 / PF /
          平均持仓天数 / 年周转次数(252/平均持仓) / 线性年化资金回报(平均每笔收益×年周转)
"""
import os, time
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

BB_PERIOD = 20
BB_STD = 2.0
INITIAL_CASH = 1_000_000
LEVEL_CASH = INITIAL_CASH / 5
COMMISSION_RATE = 0.00025
MIN_COMMISSION = 5.0
STAMP_TAX_RATE = 0.0005
TRANSFER_FEE_RATE = 0.00001
CONFIG_N = [1, 2, 3, 4, 5]
STOP_PCTS = [None, 2, 3, 5, 7, 8, 10, 12, 15, 20]
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
    stocks = [g for _, g in combined.groupby("ts_code", sort=False)]
    _sub = int(os.environ.get("STOCK_SUBSET","0"))
    if _sub > 0: stocks = stocks[:_sub]
    print(f'股票数: {len(stocks)}', flush=True)

    combos = [(n, p) for n in CONFIG_N for p in STOP_PCTS]
    results = {c: [] for c in combos}

    for si, df in enumerate(stocks):
        ts_code = df['ts_code'].iloc[0]
        close_adj = (df['close'] * df['adj_factor']).values
        high_adj = (df['high'] * df['adj_factor']).values
        low_adj = (df['low'] * df['adj_factor']).values
        open_adj = (df['open'] * df['adj_factor']).values
        is_limit_down = df['is_limit_down'].values
        dates = df['date'].values

        ma = pd.Series(close_adj).rolling(BB_PERIOD).mean().values
        std = pd.Series(close_adj).rolling(BB_PERIOD).std().values
        bb_upper = ma + BB_STD * std
        bb_lower = ma - BB_STD * std

        n = len(df)
        states = {c: new_state() for c in combos}

        for i in range(n):
            for c in combos:
                nlev, spct = c
                st = states[c]
                # ===== 持仓：止损/止盈判定 =====
                if st['shares'] > 0:
                    stop_price = st['avg_cost'] * (1 - spct / 100) if spct is not None else None
                    stop_hit = (spct is not None) and (i > st['buy_idx']) and (stop_price is not None) \
                               and (low_adj[i] <= stop_price)
                    tp_hit = (i > st['buy_idx']) and (not np.isnan(bb_upper[i])) and (high_adj[i] >= bb_upper[i])
                    if stop_hit:
                        # 止损成交：跳空低开按开盘价，否则按止损价
                        sell_price = open_adj[i] if open_adj[i] <= stop_price else stop_price
                        exit_type = 'STOP_LOSS'
                    elif tp_hit:
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
                        results[c].append({'exit_type': exit_type, 'pnl': pnl, 'cost': st['total_cost'],
                                           'return_pct': return_pct, 'hold_days': i - st['buy_idx']})
                        st['shares'] = 0; st['avg_cost'] = 0.0; st['levels'] = 0
                        st['buy_idx'] = -1; st['total_cost'] = 0.0
                        continue
                    # ===== 加仓：未触发止损/止盈，收盘<下轨，未满仓 =====
                    if not np.isnan(bb_lower[i]) and close_adj[i] < bb_lower[i] and not is_limit_down[i]:
                        if st['levels'] < nlev:
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
                                continue
                # ===== 无持仓：新开仓 =====
                if st['shares'] <= 0 and not np.isnan(bb_lower[i]) and close_adj[i] < bb_lower[i] \
                        and not is_limit_down[i]:
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

        # 期末未平仓结算
        for c in combos:
            st = states[c]
            if st['shares'] > 0:
                final_price = close_adj[-1]
                amount = final_price * st['shares']
                fee = calc_fee_sell(amount)
                proceeds = amount - fee
                pnl = proceeds - st['total_cost']
                return_pct = pnl / st['total_cost'] * 100 if st['total_cost'] > 0 else 0.0
                results[c].append({'exit_type': 'FINAL_SETTLE', 'pnl': pnl, 'cost': st['total_cost'],
                                   'return_pct': return_pct, 'hold_days': n - 1 - st['buy_idx']})

        if (si + 1) % 1000 == 0:
            print(f'  已处理 {si+1}/{len(stocks)}，用时 {time.time()-t0:.0f}s', flush=True)

    # ===== 汇总 =====
    print('\n===== 全网格结果 =====', flush=True)
    rows = []
    for c in combos:
        nlev, spct = c
        d = pd.DataFrame(results[c])
        wins = d[d['pnl'] > 0]; loss = d[d['pnl'] <= 0]
        pf = wins['pnl'].sum() / abs(loss['pnl'].sum()) if loss['pnl'].sum() != 0 else np.inf
        avg_hold = d['hold_days'].mean()
        turnover = 252 / avg_hold if avg_hold > 0 else 0
        # 线性年化资金回报 = 平均每笔收益 × 年周转次数（机会成本视角）
        ann_linear = d['return_pct'].mean() * turnover
        rows.append({
            '层数': nlev,
            '止损%': '无' if spct is None else spct,
            '回合数': len(d),
            '简单平均收益%': round(d['return_pct'].mean(), 2),
            '资金加权收益%': round(d['pnl'].sum() / d['cost'].sum() * 100, 2),
            '胜率%': round((d['pnl'] > 0).mean() * 100, 1),
            '平均盈利%': round(wins['return_pct'].mean(), 2) if len(wins) else 0,
            '平均亏损%': round(loss['return_pct'].mean(), 2) if len(loss) else 0,
            '盈亏比': round(wins['return_pct'].mean() / abs(loss['return_pct'].mean()), 2) if len(loss) else 0,
            'ProfitFactor': round(pf, 2),
            '平均持仓天': round(avg_hold, 1),
            '年周转次数': round(turnover, 1),
            '年化资金回报%(线性)': round(ann_linear, 1),
            '止损单占比%': round((d['exit_type'] == 'STOP_LOSS').mean() * 100, 1),
        })
        d.to_parquet(os.path.join(PROJECT_ROOT, 'results', f'grid_n{nlev}_s{spct}.parquet'))
    df_res = pd.DataFrame(rows)
    df_res.to_csv(os.path.join(PROJECT_ROOT, 'results', 'grid_stop_nlevels.csv'), index=False)
    # 按层数分组打印
    for nlev in CONFIG_N:
        print(f'\n--- 层数 N={nlev} ---', flush=True)
        sub = df_res[df_res['层数'] == nlev][['止损%', '回合数', '简单平均收益%', '资金加权收益%', '胜率%',
                                               '盈亏比', 'ProfitFactor', '平均持仓天', '年周转次数', '年化资金回报%(线性)']]
        print(sub.to_string(index=False), flush=True)
    print(f'\n完成，总用时 {time.time()-t0:.0f}s', flush=True)


if __name__ == '__main__':
    main()
