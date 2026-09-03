"""
真实单账户组合回测引擎（事件驱动、时间线推进、共享资金）
============================================================
策略：每日收盘后扫描全市场成交额TopN，若TopN中满足"收盘后复权价<BB下轨(20,2)"且非跌停、
      且当前空仓 → 按收盘价买入第一层（每层固定20万，100股整数倍）。
      持仓期间：盘中触及布林上轨(T+1后) → 全部卖出；收盘再次<下轨 → 加仓一层（最多5层）。
      （可选）时间止损：持仓N个交易日后未止盈 → 收盘价清仓。
规则：
- 单账户共享资金100万；同时最多持1只；持仓期间不换仓、不因他股成交额更高而换仓
- T+1：买入当日不可卖
- 跌停日（is_limit_down）不买入
- 排除ST（当前快照近似）
- 费用：佣金0.025%最低5元、印花税0.05%卖出、过户费0.001%
- 信号与指标用后复权价（保证连续）；实际成交用当日实际价格（close/high）
- 止盈：盘中high(复权)≥上轨 → 成交价=上轨复权价转实际价
- 卖出/加仓优先：先止盈，后加仓；止盈后当日不再入场（保守）
- 分红送转：未单独处理（APPROXIMATION：信号用后复权保证连续性，现金流用实际价）
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
    df = df.merge(sb[['ts_code', 'name', 'market']], on='ts_code', how='left')
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


def run_backtest(df, top_n=1, max_levels=5, level_cash=200_000, time_stop_days=None,
                 allow_reentry_same_day=False, min_listing_days=60, initial_cash=1_000_000):
    """真实单账户回测。返回净值曲线、交易日志、统计。"""
    # 上市日期（新股过滤）
    list_date = df.groupby('ts_code')['date'].min().to_dict()
    # 上市满 min_listing_days 才允许入选
    listing_ok = {tc: (df[df['ts_code'] == tc]['date'].min()) for tc in df['ts_code'].unique()}

    days = sorted(df['date'].unique())
    day_index = {d: i for i, d in enumerate(days)}
    list_idx = {}
    for tc, ld in listing_ok.items():
        list_idx[tc] = day_index.get(ld, -1)

    cash = initial_cash
    pos = None  # dict: ts_code, shares, avg_cost, entry_date, levels, total_cost, entry_day_idx
    equity_curve = []
    trades = []
    round_no = 0

    # 预取每日数据字典（加速）
    daily = {}
    for d, g in df.groupby('date'):
        daily[d] = g

    # 停牌估值：维护每只股票最后已知收盘价
    last_close = {}

    for i, d in enumerate(days):
        g = daily[d]

        sold_today = False
        # ===== 持仓处理 =====
        if pos is not None:
            row = g[g['ts_code'] == pos['ts_code']]
            if len(row) > 0:
                r = row.iloc[0]
                last_close[pos['ts_code']] = r['close']
                hold_days = i - pos['entry_day_idx']
                # 1) 止盈：T+1后盘中触及上轨
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
                    pos = None
                    round_no += 1
                    sold_today = True
                # 2) 时间止损：持仓>=N天未止盈
                elif time_stop_days is not None and hold_days >= time_stop_days:
                    sell_price = r['close']
                    amount = sell_price * pos['shares']
                    fee = calc_fee_sell(amount)
                    proceeds = amount - fee
                    pnl = proceeds - pos['total_cost']
                    return_pct = pnl / pos['total_cost'] * 100
                    trades.append({
                        'round': round_no, 'ts_code': pos['ts_code'], 'name': pos['name'],
                        'entry_date': pos['entry_date'], 'exit_date': str(d.date()),
                        'exit_type': 'TIME_STOP', 'levels_used': pos['levels'],
                        'shares': pos['shares'], 'pnl': pnl, 'return_pct': round(return_pct, 2),
                        'hold_days': hold_days,
                    })
                    cash += proceeds
                    pos = None
                    round_no += 1
                    sold_today = True
                # 3) 加仓：未止盈未时间止损，收盘<下轨，非跌停，未满层
                elif (not np.isnan(r['bb_lower']) and r['close_adj'] < r['bb_lower']
                      and not r['is_limit_down'] and pos['levels'] < max_levels):
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
                # 持仓市值（收盘）
                if pos is not None:
                    pos_value = pos['shares'] * r['close']
                    equity = cash + pos_value
            else:
                # 停牌：按最后已知收盘价估值，持仓不动
                lc = last_close.get(pos['ts_code'], pos['avg_cost'])
                pos_value = pos['shares'] * lc
                equity = cash + pos_value

        # ===== 空仓：扫描买入 =====
        if pos is None and not sold_today:
            # 当日非ST候选，排除新股（上市<min_listing_days）
            pool = g[~g['is_st']].copy()
            if len(pool) > 0:
                # 上市满天数过滤（向量化）
                li = pool['ts_code'].map(list_idx.get)
                pool = pool[(i - li) >= min_listing_days]
                if len(pool) > 0:
                    # 先筛：跌破布林下轨且非跌停
                    super_pool = pool[(~np.isnan(pool['bb_lower'])) & (pool['close_adj'] < pool['bb_lower']) & (~pool['is_limit_down'])]
                    # 再从超跌股中选成交额最大的（绝对正确方法，计算量小）
                    candidate = None
                    if len(super_pool) > 0:
                        candidate = super_pool.nlargest(1, 'amount').iloc[0]
                    if candidate is not None:
                        buy_price = candidate['close']
                        qty = int(min(level_cash, cash) / buy_price / 100) * 100
                        if qty >= 100:
                            amount = buy_price * qty
                            fee = calc_fee_buy(amount)
                            cost_add = amount + fee
                            if cost_add <= cash:
                                cash -= cost_add
                                pos = {
                                    'ts_code': candidate['ts_code'], 'name': candidate['name'],
                                    'shares': qty, 'avg_cost': cost_add / qty,
                                    'entry_date': str(d.date()), 'levels': 1,
                                    'total_cost': cost_add, 'entry_day_idx': i,
                                }
            # 空仓无持仓市值
            if pos is None:
                equity = cash

        equity_curve.append({'date': d, 'equity': equity, 'cash': cash,
                             'holding': pos['ts_code'] if pos else None})

    # 期末清仓结算
    if pos is not None:
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

    eq = pd.DataFrame(equity_curve)
    tr = pd.DataFrame(trades)
    return eq, tr


def calc_stats(eq, tr, initial_cash=1_000_000):
    """计算回测统计指标"""
    eq = eq.copy()
    eq['ret'] = eq['equity'].pct_change().fillna(0)
    total_return = eq['equity'].iloc[-1] / initial_cash - 1
    years = len(eq) / 252
    ann_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
    # 最大回撤
    peak = eq['equity'].cummax()
    dd = (eq['equity'] - peak) / peak
    max_dd = dd.min()
    # 波动率/Sharpe（日收益）
    vol = eq['ret'].std() * np.sqrt(252) if len(eq) > 1 else 0
    sharpe = eq['ret'].mean() / eq['ret'].std() * np.sqrt(252) if eq['ret'].std() > 0 else 0
    # 资金利用率：持仓市值占比
    eq['holding_value'] = np.where(eq['holding'].notna(), 1, 0)  # 简化：有持仓即占用
    util = eq['holding'].notna().mean() * 100
    # 交易统计
    n_trades = len(tr)
    win_rate = (tr['pnl'] > 0).mean() * 100 if n_trades > 0 else 0
    avg_win = tr[tr['pnl'] > 0]['return_pct'].mean() if (tr['pnl'] > 0).any() else 0
    avg_loss = tr[tr['pnl'] <= 0]['return_pct'].mean() if (tr['pnl'] <= 0).any() else 0
    pf = tr[tr['pnl'] > 0]['pnl'].sum() / abs(tr[tr['pnl'] <= 0]['pnl'].sum()) if (tr['pnl'] <= 0).any() else np.inf
    # 年度收益
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
        '资金利用率%(持仓天数占比)': round(util, 1),
        '年度收益%': {str(k): round(v, 2) for k, v in yearly.items()},
    }


if __name__ == '__main__':
    t0 = time.time()
    print('准备数据...', flush=True)
    df = prepare_data()
    print(f'数据准备完成 {time.time()-t0:.0f}s', flush=True)

    configs = [
        dict(top_n=1, max_levels=5, time_stop_days=None, label='先超跌后成交额_5层'),
        dict(top_n=1, max_levels=5, time_stop_days=30, label='先超跌后成交额_5层_时间止损30'),
        dict(top_n=1, max_levels=5, time_stop_days=20, label='先超跌后成交额_5层_时间止损20'),
        dict(top_n=1, max_levels=3, time_stop_days=None, label='先超跌后成交额_3层'),
        dict(top_n=1, max_levels=1, time_stop_days=None, label='先超跌后成交额_1层'),
    ]
    summary = []
    for cfg in configs:
        label = cfg.pop('label')
        print(f'运行 {label} ...', flush=True)
        eq, tr = run_backtest(df, **cfg)
        stats = calc_stats(eq, tr)
        stats['配置'] = label
        summary.append(stats)
        eq.to_parquet(os.path.join(PROJECT_ROOT, 'results', f'live_{label}.parquet'))
        tr.to_csv(os.path.join(PROJECT_ROOT, 'results', f'live_{label}_trades.csv'), index=False)
        print(f'  {label}: 总收益{stats["总收益%"]}%, 年化{stats["年化收益%"]}%, 回撤{stats["最大回撤%"]}%, '
              f'交易{stats["交易次数"]}次, 胜率{stats["胜率%"]}%, 资金利用{stats["资金利用率%(持仓天数占比)"]}%', flush=True)

    sm = pd.DataFrame(summary)
    sm.to_csv(os.path.join(PROJECT_ROOT, 'results', 'revised_summary.csv'), index=False)
    print('\n===== 汇总 =====', flush=True)
    print(sm[['配置', '总收益%', '年化收益%', '最大回撤%', 'Sharpe', '交易次数', '胜率%', '盈亏比', 'ProfitFactor', '资金利用率%(持仓天数占比)']].to_string(index=False), flush=True)
