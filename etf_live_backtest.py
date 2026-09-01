"""
真实单账户回测引擎 + 闲置资金现金管理（标普500ETF 513500）
============================================================
在 live_backtest.py 基础上，把空仓期的闲置现金买入 513500（博时标普500ETF，A股第一只标普500ETF，自2014年上市）。
- 华夏标普500ETF(159655) 2022-10 才上市，无法覆盖 2020-2026 完整区间，故用同标的 513500（跟踪标普500）。
- 买入股票需要资金时：先卖出 ETF 换现金（513500 为 QDII 跨境 ETF，支持 T+0，当日可卖）。
- 空仓且现金充裕时：收盘后买入 ETF（100份整数倍，佣金0.025%最低5元，无印花税/过户费）。
- 估值：ETF 持仓按单位净值(unit_nav)估值（公允，剔除溢价虚增）；买卖按市价(close)成交。
  => 溢价率影响 = 买入时市价/净值 - 卖出时市价/净值 的差值，真实计入。
- 账户净值 = 现金 + 股票市值(实际价) + ETF股数×单位净值。
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


def calc_fee_etf(amount):
    # ETF 仅佣金，无印花税/过户费
    return max(amount * COMMISSION_RATE, MIN_COMMISSION)


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


def prepare_etf_data():
    """加载513500：市价(close) + 单位净值(unit_nav)，按日期索引"""
    m = pd.read_parquet(os.path.join(PROJECT_ROOT, 'data', 'etf_513500_merged.parquet'))
    m['trade_date'] = pd.to_datetime(m['trade_date'])
    m = m.sort_values('trade_date').reset_index(drop=True)
    m['unit_nav'] = m['unit_nav'].ffill()  # 净值滞后缺失用前值近似
    return m.set_index('trade_date')[['close', 'unit_nav']]


def run_backtest(df, etf, top_n=10, max_levels=5, level_cash=200_000, time_stop_days=None,
                 etf_enabled=True, etf_min_cash=5_000, etf_ratio=1.0, min_listing_days=60,
                 initial_cash=1_000_000):
    """真实单账户回测 + ETF现金管理"""
    days = sorted(df['date'].unique())
    day_index = {d: i for i, d in enumerate(days)}
    listing_ok = {tc: df[df['ts_code'] == tc]['date'].min() for tc in df['ts_code'].unique()}
    list_idx = {tc: day_index.get(ld, -1) for tc, ld in listing_ok.items()}

    cash = initial_cash
    pos = None
    etf_shares = 0
    equity_curve = []
    trades = []
    etf_log = []
    round_no = 0
    last_close = {}

    daily = {}
    for d, g in df.groupby('date'):
        daily[d] = g

    for i, d in enumerate(days):
        g = daily[d]
        # 当日ETF行情（市价+净值）
        if d in etf.index:
            etf_px = etf.loc[d, 'close']
            etf_nav = etf.loc[d, 'unit_nav']
        else:
            etf_px, etf_nav = np.nan, np.nan

        def ensure_cash_needed(need):
            """确保现金>=need，不足则卖出ETF补足"""
            nonlocal cash, etf_shares
            if cash >= need or not etf_enabled or etf_shares <= 0 or np.isnan(etf_px):
                return
            shortfall = need - cash
            sell_val = shortfall * 1.02  # 2%缓冲（覆盖费用）
            sell_qty = int(np.ceil(sell_val / etf_px / 100)) * 100
            sell_qty = min(sell_qty, etf_shares)
            if sell_qty >= 100:
                amount = sell_qty * etf_px
                fee = calc_fee_etf(amount)
                proceeds = amount - fee
                # 卖出按市价，equity损耗=卖出时市价-净值
                etf_shares -= sell_qty
                cash += proceeds
                etf_log.append({
                    'date': str(d.date()), 'action': 'SELL_ETF', 'shares': sell_qty,
                    'price': round(etf_px, 4), 'nav': round(etf_nav, 4),
                    'premium_pct': round((etf_px / etf_nav - 1) * 100, 2) if not np.isnan(etf_nav) else np.nan,
                    'amount': round(amount, 2), 'fee': round(fee, 2), 'cash_after': round(cash, 2),
                })

        sold_today = False
        # ===== 持仓处理 =====
        if pos is not None:
            row = g[g['ts_code'] == pos['ts_code']]
            if len(row) > 0:
                r = row.iloc[0]
                last_close[pos['ts_code']] = r['close']
                hold_days = i - pos['entry_day_idx']
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
                elif (not np.isnan(r['bb_lower']) and r['close_adj'] < r['bb_lower']
                      and not r['is_limit_down'] and pos['levels'] < max_levels):
                    # 加仓需要资金（目标每层level_cash）
                    need = level_cash
                    ensure_cash_needed(need)
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
                if pos is not None:
                    pos_value = pos['shares'] * r['close']
                    stock_val = pos_value
                else:
                    stock_val = 0
            else:
                lc = last_close.get(pos['ts_code'], pos['avg_cost'])
                stock_val = pos['shares'] * lc
        else:
            stock_val = 0

        # ===== 空仓：扫描买入 =====
        if pos is None and not sold_today:
            pool = g[~g['is_st']].copy()
            if len(pool) > 0:
                li = pool['ts_code'].map(list_idx.get)
                pool = pool[(i - li) >= min_listing_days]
                if len(pool) > 0:
                    top = pool.nlargest(top_n, 'amount')
                    candidate = None
                    for _, r in top.iterrows():
                        if (not np.isnan(r['bb_lower']) and r['close_adj'] < r['bb_lower']
                                and not r['is_limit_down']):
                            candidate = r
                            break
                    if candidate is not None:
                        ensure_cash_needed(level_cash)
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
                                stock_val = qty * buy_price

        # ===== 收盘后：空仓时，ETF仓位再平衡到目标比例（真目标比例控制） =====
        # etf_val 用当日净值预估值
        etf_val = etf_shares * etf_nav if not np.isnan(etf_nav) else etf_shares * etf_px
        if pos is None and etf_enabled and not np.isnan(etf_px):
            total_assets = cash + etf_val
            target_val = total_assets * etf_ratio
            diff = target_val - etf_val
            if diff > 100 * etf_px and cash >= 100 * etf_px:
                max_cash_use = cash - etf_min_cash
                qty = int(min(diff, max_cash_use) / etf_px / 100) * 100
                amount = qty * etf_px
                fee = calc_fee_etf(amount)
                cost = amount + fee
                if cost <= cash:
                    cash -= cost
                    etf_shares += qty
                    etf_val += qty * etf_nav
                    etf_log.append({
                        'date': str(d.date()), 'action': 'BUY_ETF', 'shares': qty,
                        'price': round(etf_px, 4), 'nav': round(etf_nav, 4),
                        'premium_pct': round((etf_px / etf_nav - 1) * 100, 2) if not np.isnan(etf_nav) else np.nan,
                        'amount': round(amount, 2), 'fee': round(fee, 2), 'cash_after': round(cash, 2),
                    })
            elif diff < -100 * etf_px and etf_shares >= 100:
                sell_qty = int(-diff / etf_px / 100) * 100
                sell_qty = min(sell_qty, etf_shares)
                if sell_qty >= 100:
                    amount = sell_qty * etf_px
                    fee = calc_fee_etf(amount)
                    proceeds = amount - fee
                    etf_shares -= sell_qty
                    cash += proceeds
                    etf_val -= sell_qty * etf_nav
                    etf_log.append({
                        'date': str(d.date()), 'action': 'SELL_ETF', 'shares': sell_qty,
                        'price': round(etf_px, 4), 'nav': round(etf_nav, 4),
                        'premium_pct': round((etf_px / etf_nav - 1) * 100, 2) if not np.isnan(etf_nav) else np.nan,
                        'amount': round(amount, 2), 'fee': round(fee, 2), 'cash_after': round(cash, 2),
                    })

        # 估值：ETF按净值（重新计算）
        etf_val = etf_shares * etf_nav if not np.isnan(etf_nav) else etf_shares * etf_px
        equity = cash + stock_val + etf_val
        equity_curve.append({'date': d, 'equity': equity, 'cash': cash,
                             'stock_val': stock_val, 'etf_val': etf_val,
                             'etf_shares': etf_shares,
                             'holding': pos['ts_code'] if pos else None})

    # 期末清仓（股票+ETF按市价）
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
    if etf_shares > 0:
        last_d = days[-1]
        if last_d in etf.index:
            sell_price = etf.loc[last_d, 'close']
            amount = sell_price * etf_shares
            fee = calc_fee_etf(amount)
            proceeds = amount - fee
            cash += proceeds
            etf_log.append({
                'date': str(last_d.date()), 'action': 'FINAL_ETF', 'shares': etf_shares,
                'price': round(sell_price, 4), 'nav': round(etf.loc[last_d, 'unit_nav'], 4),
                'premium_pct': round((sell_price / etf.loc[last_d, 'unit_nav'] - 1) * 100, 2),
                'amount': round(amount, 2), 'fee': round(fee, 2), 'cash_after': round(cash, 2),
            })
            etf_shares = 0

    eq = pd.DataFrame(equity_curve)
    tr = pd.DataFrame(trades)
    etf_df = pd.DataFrame(etf_log)
    return eq, tr, etf_df


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
    util_stock = eq['holding'].notna().mean() * 100
    util_etf = (eq['etf_shares'] > 0).mean() * 100
    util_total = ((eq['holding'].notna()) | (eq['etf_shares'] > 0)).mean() * 100
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
        '股票利用率%': round(util_stock, 1),
        'ETF利用率%': round(util_etf, 1),
        '总资金利用率%': round(util_total, 1),
        '年度收益%': {str(k): round(v, 2) for k, v in yearly.items()},
    }


if __name__ == '__main__':
    t0 = time.time()
    print('准备数据...', flush=True)
    df = prepare_data()
    etf = prepare_etf_data()
    print(f'数据准备完成 {time.time()-t0:.0f}s', flush=True)

    configs = [
        dict(top_n=10, max_levels=5, time_stop_days=None, etf_enabled=True, label='Top10_5层_ETF现金管理'),
        dict(top_n=10, max_levels=5, time_stop_days=None, etf_enabled=False, label='Top10_5层_无ETF基准'),
    ]
    summary = []
    for cfg in configs:
        label = cfg.pop('label')
        print(f'运行 {label} ...', flush=True)
        eq, tr, etf_df = run_backtest(df, etf, **cfg)
        stats = calc_stats(eq, tr)
        stats['配置'] = label
        summary.append(stats)
        eq.to_parquet(os.path.join(PROJECT_ROOT, 'results', f'etf_{label}.parquet'))
        tr.to_csv(os.path.join(PROJECT_ROOT, 'results', f'etf_{label}_trades.csv'), index=False)
        if len(etf_df):
            etf_df.to_csv(os.path.join(PROJECT_ROOT, 'results', f'etf_{label}_etf_log.csv'), index=False)
        print(f'  {label}: 总收益{stats["总收益%"]}%, 回撤{stats["最大回撤%"]}%, 股票利用{stats["股票利用率%"]}%, '
              f'ETF利用{stats["ETF利用率%"]}%, 总资金利用{stats["总资金利用率%"]}%', flush=True)

    sm = pd.DataFrame(summary)
    sm.to_csv(os.path.join(PROJECT_ROOT, 'results', 'etf_summary.csv'), index=False)
    print(sm[['配置', '总收益%', '年化收益%', '最大回撤%', 'Sharpe', '交易次数', '胜率%', '股票利用率%', 'ETF利用率%', '总资金利用率%']].to_string(index=False), flush=True)
