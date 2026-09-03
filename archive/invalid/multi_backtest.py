"""
多标的组合回测引擎：共享资金池 + 轮动
=======================================
账户初始100万，总仓位预算 = 5层 × 每层20万 = 100万。
同时最多持 K 只股票（max_positions），每只最多 L 层（max_levels_per_stock），
所有持仓的层数总和 <= 5层（max_total_levels），现金自然保留（留资金）。

每日逻辑（时间线推进，收盘后决策）：
1. 处理持仓：盘中触及布林上轨(T+1后) → 全部卖出，资金回池；收盘<下轨且非跌停且未满L层且总层数<5 → 加1层
2. 开新仓：若持仓数<K 且 总层数<5 → 扫描成交额Top10池，找"不在当前持仓、收盘<下轨且非跌停"的第1只 → 买1层
   （每天最多开1个新仓，真实操作性）
3. 止盈释放的资金自然用于次日补仓/开新仓（轮动）
规则：T+1、跌停不买、ST排除、100股整数倍、真实费用、停牌不交易、后复权算信号实际价成交
"""
import os
import numpy as np
import pandas as pd
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
COMMISSION_RATE = 0.00025
MIN_COMMISSION = 5.0
STAMP_TAX_RATE = 0.0005
TRANSFER_FEE_RATE = 0.00001


def calc_fee_buy(amount):
    return max(amount * COMMISSION_RATE, MIN_COMMISSION) + amount * TRANSFER_FEE_RATE


def calc_fee_sell(amount):
    return max(amount * COMMISSION_RATE, MIN_COMMISSION) + amount * STAMP_TAX_RATE + amount * TRANSFER_FEE_RATE


def prepare_data():
    df = pd.read_parquet(os.path.join(PROJECT_ROOT, 'data', 'combined_daily.parquet'))
    sb = pd.read_parquet(os.path.join(PROJECT_ROOT, 'data', 'raw', 'stock_basic.parquet'))
    df = df.merge(sb[['ts_code', 'name']], on='ts_code', how='left')
    df['date'] = pd.to_datetime(df['date'])
    _start = os.environ.get('BT_START', '2020-01-01')
    _end = os.environ.get('BT_END', '2026-08-25')
    df = df[(df['date'] >= _start) & (df['date'] <= _end)]
    df = df.sort_values(['ts_code', 'date']).reset_index(drop=True)
    df['is_st'] = df['name'].str.contains('ST', na=False)
    df['close_adj'] = df['close'] * df['adj_factor']
    df['high_adj'] = df['high'] * df['adj_factor']
    g = df.groupby('ts_code')['close_adj']
    df['ma20'] = g.transform(lambda x: x.rolling(20, min_periods=20).mean())
    df['std20'] = g.transform(lambda x: x.rolling(20, min_periods=20).std())
    df['bb_lower'] = df['ma20'] - 2 * df['std20']
    df['bb_upper'] = df['ma20'] + 2 * df['std20']
    return df


def run_multi(df, max_positions=3, max_levels_per_stock=2, top_n=10, level_cash=200_000,
              max_total_levels=5, min_listing_days=60, initial_cash=1_000_000):
    days = sorted(df['date'].unique())
    day_index = {d: i for i, d in enumerate(days)}
    listing_ok = {tc: (df[df['ts_code'] == tc]['date'].min()) for tc in df['ts_code'].unique()}
    list_idx = {}
    for tc, ld in listing_ok.items():
        list_idx[tc] = day_index.get(ld, -1)

    daily = {}
    for d, g in df.groupby('date'):
        daily[d] = g

    last_close = {}
    cash = initial_cash
    positions = []  # list of dicts
    equity_curve = []
    trades = []
    round_no = 0
    holding_history = {}  # date -> [codes]

    for i, d in enumerate(days):
        g = daily[d]
        # ===== 1. 处理持仓 =====
        for pos in positions[:]:
            row = g[g['ts_code'] == pos['ts_code']]
            if len(row) > 0:
                r = row.iloc[0]
                last_close[pos['ts_code']] = r['close']
                hold_days = i - pos['entry_day_idx']
                total_levels = sum(p['levels'] for p in positions)
                # 止盈：T+1后盘中触及上轨
                if not np.isnan(r['bb_upper']) and hold_days >= 1 and r['high_adj'] >= r['bb_upper']:
                    sell_price = r['bb_upper'] / r['adj_factor']
                    amount = sell_price * pos['shares']
                    fee = calc_fee_sell(amount)
                    proceeds = amount - fee
                    pnl = proceeds - pos['total_cost']
                    return_pct = pnl / pos['total_cost'] * 100
                    trades.append({
                        'round': round_no, 'ts_code': pos['ts_code'], 'name': pos['name'],
                        'entry_date': pos['entry_date'], 'exit_date': str(d.date()),
                        'exit_type': 'TAKE_PROFIT_UB', 'levels_used': pos['levels'],
                        'shares': pos['shares'], 'pnl': pnl, 'return_pct': round(return_pct, 2),
                        'hold_days': hold_days,
                    })
                    cash += proceeds
                    positions.remove(pos)
                    round_no += 1
                # 加仓：未止盈，收盘<下轨，非跌停，未满L层，总层数<5
                elif (not np.isnan(r['bb_lower']) and r['close_adj'] < r['bb_lower']
                      and not r['is_limit_down'] and pos['levels'] < max_levels_per_stock
                      and total_levels < max_total_levels):
                    buy_price = r['close']
                    qty = int(min(level_cash, cash) / buy_price / 100) * 100
                    if qty >= 100 and buy_price * qty + calc_fee_buy(buy_price * qty) <= cash:
                        amount = buy_price * qty
                        fee = calc_fee_buy(amount)
                        cost_add = amount + fee
                        old_cost = pos['shares'] * pos['avg_cost']
                        pos['shares'] += qty
                        pos['avg_cost'] = (old_cost + cost_add) / pos['shares']
                        pos['total_cost'] += cost_add
                        pos['levels'] += 1
                        cash -= cost_add
            # 停牌：无数据不交易，估值用last_close

        # ===== 2. 开新仓（每天最多1个）=====
        total_levels = sum(p['levels'] for p in positions)
        if len(positions) < max_positions and total_levels < max_total_levels:
            holding_codes = {p['ts_code'] for p in positions}
            pool = g[~g['is_st']].copy()
            if len(pool) > 0:
                li = pool['ts_code'].map(list_idx.get)
                pool = pool[(i - li) >= min_listing_days]
                pool = pool[~pool['ts_code'].isin(holding_codes)]
                if len(pool) > 0:
                    top = pool.nlargest(top_n, 'amount')
                    candidate = None
                    for _, r in top.iterrows():
                        if (not np.isnan(r['bb_lower']) and r['close_adj'] < r['bb_lower']
                                and not r['is_limit_down']):
                            candidate = r
                            break
                    if candidate is not None:
                        buy_price = candidate['close']
                        qty = int(min(level_cash, cash) / buy_price / 100) * 100
                        if qty >= 100:
                            amount = buy_price * qty
                            fee = calc_fee_buy(amount)
                            cost_add = amount + fee
                            if cost_add <= cash:
                                cash -= cost_add
                                positions.append({
                                    'ts_code': candidate['ts_code'], 'name': candidate['name'],
                                    'shares': qty, 'avg_cost': cost_add / qty,
                                    'entry_date': str(d.date()), 'levels': 1,
                                    'total_cost': cost_add, 'entry_day_idx': i,
                                })

        # ===== 3. 估值 =====
        pos_value = 0.0
        for pos in positions:
            row = g[g['ts_code'] == pos['ts_code']]
            if len(row) > 0:
                r = row.iloc[0]
                last_close[pos['ts_code']] = r['close']
                pos_value += pos['shares'] * r['close']
            else:
                pos_value += pos['shares'] * last_close.get(pos['ts_code'], pos['avg_cost'])
        equity = cash + pos_value
        equity_curve.append({'date': d, 'equity': equity, 'cash': cash,
                             'n_pos': len(positions),
                             'holding': ','.join(p['ts_code'] for p in positions)})

    # 期末清仓
    for pos in positions[:]:
        last_d = days[-1]
        r = daily[last_d][daily[last_d]['ts_code'] == pos['ts_code']]
        if len(r) > 0:
            r = r.iloc[0]
            sell_price = r['close']
            amount = sell_price * pos['shares']
            fee = calc_fee_sell(amount)
            proceeds = amount - fee
            pnl = proceeds - pos['total_cost']
            return_pct = pnl / pos['total_cost'] * 100
            trades.append({
                'round': round_no, 'ts_code': pos['ts_code'], 'name': pos['name'],
                'entry_date': pos['entry_date'], 'exit_date': str(last_d.date()),
                'exit_type': 'FINAL_SETTLE', 'levels_used': pos['levels'],
                'shares': pos['shares'], 'pnl': pnl, 'return_pct': round(return_pct, 2),
                'hold_days': day_index[last_d] - pos['entry_day_idx'],
            })
            cash += proceeds
            round_no += 1

    eq = pd.DataFrame(equity_curve)
    tr = pd.DataFrame(trades)
    return eq, tr


def calc_stats(eq, tr, initial_cash=1_000_000):
    eq = eq.copy()
    eq['ret'] = eq['equity'].pct_change().fillna(0)
    total_return = eq['equity'].iloc[-1] / initial_cash - 1
    years = len(eq) / 252
    ann_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
    peak = eq['equity'].cummax()
    dd = (eq['equity'] - peak) / peak
    max_dd = dd.min()
    vol = eq['ret'].std() * np.sqrt(252) if len(eq) > 1 else 0
    sharpe = eq['ret'].mean() / eq['ret'].std() * np.sqrt(252) if eq['ret'].std() > 0 else 0
    # 资金利用率：持仓占用市值占比（近似用n_pos>0）
    eq['util'] = eq['n_pos'] > 0
    util = eq['util'].mean() * 100
    # 平均持仓只数
    avg_pos = eq['n_pos'].mean()
    n_trades = len(tr)
    win_rate = (tr['pnl'] > 0).mean() * 100 if n_trades > 0 else 0
    avg_win = tr[tr['pnl'] > 0]['return_pct'].mean() if (tr['pnl'] > 0).any() else 0
    avg_loss = tr[tr['pnl'] <= 0]['return_pct'].mean() if (tr['pnl'] <= 0).any() else 0
    pf = tr[tr['pnl'] > 0]['pnl'].sum() / abs(tr[tr['pnl'] <= 0]['pnl'].sum()) if (tr['pnl'] <= 0).any() else np.inf
    eq['year'] = eq['date'].dt.year
    yearly = {}
    for y, gy in eq.groupby('year'):
        yearly[y] = (gy['equity'].iloc[-1] / gy['equity'].iloc[0] - 1) * 100
    return {
        '总收益%': round(total_return * 100, 2),
        '年化收益%': round(ann_return * 100, 2),
        '最大回撤%': round(max_dd * 100, 2),
        '年化波动%': round(vol * 100, 2),
        'Sharpe': round(sharpe, 2),
        '交易次数': n_trades,
        '胜率%': round(win_rate, 1),
        '平均盈利%': round(avg_win, 2) if n_trades else 0,
        '平均亏损%': round(avg_loss, 2) if n_trades else 0,
        '盈亏比': round(avg_win / abs(avg_loss), 2) if (tr['pnl'] <= 0).any() and avg_loss != 0 else np.inf,
        'ProfitFactor': round(pf, 2),
        '平均持仓只数': round(avg_pos, 2),
        '有持仓天数%': round(util, 1),
        '年度收益%': {str(k): round(v, 2) for k, v in yearly.items()},
    }


if __name__ == '__main__':
    t0 = time.time()
    print('准备数据...', flush=True)
    df = prepare_data()
    print(f'数据准备完成 {time.time()-t0:.0f}s', flush=True)

    configs = [
        # label: max_positions, max_levels_per_stock
        dict(max_positions=1, max_levels_per_stock=5, label='1只_最多5层(基准)'),
        dict(max_positions=2, max_levels_per_stock=3, label='2只_各最多3层'),
        dict(max_positions=2, max_levels_per_stock=2, label='2只_各最多2层(留1层)'),
        dict(max_positions=3, max_levels_per_stock=1, label='3只_各1层(留2层现金)'),
        dict(max_positions=3, max_levels_per_stock=2, label='3只_各最多2层'),
        dict(max_positions=3, max_levels_per_stock=3, label='3只_各最多3层'),
        dict(max_positions=4, max_levels_per_stock=1, label='4只_各1层(留1层现金)'),
        dict(max_positions=4, max_levels_per_stock=2, label='4只_各最多2层'),
        dict(max_positions=5, max_levels_per_stock=1, label='5只_各1层(满仓)'),
        dict(max_positions=5, max_levels_per_stock=2, label='5只_各最多2层'),
    ]
    summary = []
    for cfg in configs:
        label = cfg.pop('label')
        print(f'运行 {label} ...', flush=True)
        eq, tr = run_multi(df, **cfg)
        stats = calc_stats(eq, tr)
        stats['配置'] = label
        summary.append(stats)
        eq.to_parquet(os.path.join(PROJECT_ROOT, 'results', f'multi_{label}.parquet'))
        tr.to_csv(os.path.join(PROJECT_ROOT, 'results', f'multi_{label}_trades.csv'), index=False)
        print(f'  {label}: 总收益{stats["总收益%"]}%, 年化{stats["年化收益%"]}%, 回撤{stats["最大回撤%"]}%, '
              f'Sharpe{stats["Sharpe"]}, 交易{stats["交易次数"]}次, 胜率{stats["胜率%"]}%, '
              f'平均持仓{stats["平均持仓只数"]}只, 有持仓天数{stats["有持仓天数%"]}%', flush=True)

    sm = pd.DataFrame(summary)
    sm.to_csv(os.path.join(PROJECT_ROOT, 'results', 'multi_summary.csv'), index=False)
    print('\n===== 汇总 =====', flush=True)
    print(sm[['配置', '总收益%', '年化收益%', '最大回撤%', '年化波动%', 'Sharpe', '交易次数', '胜率%',
              '盈亏比', 'ProfitFactor', '平均持仓只数', '有持仓天数%']].to_string(index=False), flush=True)
