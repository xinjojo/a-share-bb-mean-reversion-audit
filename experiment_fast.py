"""
实验引擎快速版（numpy 加速，逻辑与 experiment_runner.py 完全一致，仅性能优化）
用于第三轮参数扫描等大量重复回测。
"""
import os
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
COMMISSION_RATE = 0.00025
MIN_COMMISSION = 5.0
STAMP_TAX_FLAT = 0.0005
TRANSFER_FEE_RATE = 0.00001
STAMP_CUTOFF = pd.Timestamp('2023-08-28')


def prepare_fast(limit_down_mode='old', bb_window=20, bb_std=2.0):
    """返回 numpy 化的每日数据结构 + etf 数组 + 全局上市索引"""
    df = pd.read_parquet(os.path.join(PROJECT_ROOT, 'data', 'combined_daily.parquet'))
    sb = pd.read_parquet(os.path.join(PROJECT_ROOT, 'data', 'raw', 'stock_basic.parquet'))
    df = df.merge(sb[['ts_code', 'name']], on='ts_code', how='left')
    df['date'] = pd.to_datetime(df['date'])
    df = df[(df['date'] >= '2020-01-01') & (df['date'] <= '2026-08-25')]
    df = df.sort_values(['ts_code', 'date']).reset_index(drop=True)
    df['is_st'] = df['name'].str.contains('ST', na=False)
    df['close_adj'] = df['close'] * df['adj_factor']
    df['high_adj'] = df['high'] * df['adj_factor']
    g = df.groupby('ts_code')['close_adj']
    df['ma'] = g.transform(lambda x: x.rolling(bb_window, min_periods=bb_window).mean())
    df['sd'] = g.transform(lambda x: x.rolling(bb_window, min_periods=bb_window).std())
    df['bb_lower'] = df['ma'] - bb_std * df['sd']
    df['bb_upper'] = df['ma'] + bb_std * df['sd']
    if limit_down_mode == 'correct':
        is_chi = df['ts_code'].str.startswith(('688', '689'))
        is_gem = df['ts_code'].str.startswith('30')
        is_st = df['is_st']
        gem_pct = np.where(df['date'] >= '2020-08-24', 0.20, 0.10)
        pct = np.where(is_chi, 0.20, np.where(is_gem, gem_pct, np.where(is_st, 0.05, 0.10)))
        df['is_limit_down'] = df['close'] <= (df['pre_close'] * (1 - pct)).round(2)
    else:
        df['is_limit_down'] = df['close'] <= df['pre_close'] * 0.905

    all_days = sorted(df['date'].unique())
    listing = {}
    for d, g in df.groupby('date'):
        di = all_days.index(d)
        for tc in g['ts_code']:
            listing.setdefault(tc, di)

    days = all_days
    # 每日数据
    D = {}
    for d, g in df.groupby('date'):
        D[d] = dict(
            ts=g['ts_code'].to_numpy(),
            close=g['close'].to_numpy(), open_=g['open'].to_numpy(),
            high_adj=g['high_adj'].to_numpy(), close_adj=g['close_adj'].to_numpy(),
            bb_lower=g['bb_lower'].to_numpy(), bb_upper=g['bb_upper'].to_numpy(),
            amount=g['amount'].to_numpy(), is_limit=g['is_limit_down'].to_numpy(),
            is_st=g['is_st'].to_numpy(), adj=g['adj_factor'].to_numpy(),
        )
        D[d]['pos'] = {tc: j for j, tc in enumerate(D[d]['ts'])}
    # ETF numpy 化
    m = pd.read_parquet(os.path.join(PROJECT_ROOT, 'data', 'etf_513500_merged.parquet'))
    m['trade_date'] = pd.to_datetime(m['trade_date'])
    m = m.sort_values('trade_date').reset_index(drop=True)
    m['unit_nav'] = m['unit_nav'].ffill()
    etf_idx = {r['trade_date']: i for i, r in m.iterrows()}
    etf_px = m['close'].to_numpy()
    etf_nav = m['unit_nav'].to_numpy()
    return days, D, etf_idx, etf_px, etf_nav, df, listing


def run_fast(days, D, etf_idx, etf_px, etf_nav, listing=None, top_n=10, max_levels=5, level_cash=200_000,
             time_stop_days=None, etf_enabled=True, etf_min_cash=5_000, etf_ratio=1.0,
             min_listing_days=60, initial_cash=1_000_000, execution_mode='close',
             slippage_bp=0, stamp_tax_mode='flat'):
    slip = slippage_bp / 10000.0
    n_days = len(days)
    if listing is None:
        listing = {}

    def stamp_rate(dt):
        return 0.001 if stamp_tax_mode == 'historical' and dt < STAMP_CUTOFF else STAMP_TAX_FLAT

    cash = initial_cash
    pos = None
    etf_sh = 0
    equity_curve = []
    trades = []
    round_no = 0
    last_close = {}
    pending_buy = None
    pending_add = None

    for i, d in enumerate(days):
        dd = D[d]
        ei = etf_idx.get(d)
        if ei is not None:
            epx, enav = etf_px[ei], etf_nav[ei]
        else:
            epx, enav = np.nan, np.nan

        def ensure_cash(need):
            nonlocal cash, etf_sh
            if cash >= need or not etf_enabled or etf_sh <= 0 or np.isnan(epx):
                return
            shortfall = need - cash
            sell_val = shortfall * 1.02
            sell_qty = int(np.ceil(sell_val / epx / 100)) * 100
            sell_qty = min(sell_qty, etf_sh)
            if sell_qty >= 100:
                amt = sell_qty * epx
                fee = max(amt * COMMISSION_RATE, MIN_COMMISSION)
                etf_sh -= sell_qty
                cash += amt - fee

        # next_open: 开盘执行前日信号
        if execution_mode == 'next_open' and (pending_add is not None or pending_buy is not None):
            if pending_add is not None and pos is not None:
                j = dd['pos'].get(pos['ts_code'])
                if j is not None:
                    buy_price = dd['open_'][j] * (1 + slip)
                    ensure_cash(level_cash)
                    qty = int(min(level_cash, cash) / buy_price / 100) * 100
                    if qty >= 100:
                        amt = buy_price * qty
                        fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * TRANSFER_FEE_RATE
                        if amt + fee <= cash:
                            cash -= amt + fee
                            old_cost = pos['shares'] * pos['avg_cost']
                            pos['shares'] += qty
                            pos['avg_cost'] = (old_cost + amt + fee) / pos['shares']
                            pos['total_cost'] += amt + fee
                            pos['levels'] += 1
                pending_add = None
            elif pending_buy is not None and pos is None:
                j = dd['pos'].get(pending_buy['ts_code'])
                if j is not None:
                    buy_price = dd['open_'][j] * (1 + slip)
                    ensure_cash(level_cash)
                    qty = int(min(level_cash, cash) / buy_price / 100) * 100
                    if qty >= 100:
                        amt = buy_price * qty
                        fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * TRANSFER_FEE_RATE
                        if amt + fee <= cash:
                            cash -= amt + fee
                            pos = {'ts_code': pending_buy['ts_code'], 'name': pending_buy['name'],
                                   'shares': qty, 'avg_cost': (amt + fee) / qty,
                                   'entry_date': str(d.date()), 'levels': 1,
                                   'total_cost': amt + fee, 'entry_day_idx': i}
                pending_buy = None

        sold_today = False
        stock_val = 0.0
        # 持仓处理
        if pos is not None:
            j = dd['pos'].get(pos['ts_code'])
            if j is not None:
                close = dd['close'][j]
                last_close[pos['ts_code']] = close
                hold_days = i - pos['entry_day_idx']
                bb_up = dd['bb_upper'][j]
                if not np.isnan(bb_up) and hold_days >= 1 and dd['high_adj'][j] >= bb_up:
                    sell_price = (bb_up / dd['adj'][j]) * (1 - slip)
                    amt = sell_price * pos['shares']
                    sr = stamp_rate(d)
                    fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
                    proceeds = amt - fee
                    pnl = proceeds - pos['total_cost']
                    return_pct = pnl / pos['total_cost'] * 100
                    trades.append({'round': round_no, 'ts_code': pos['ts_code'], 'name': pos['name'],
                                   'entry_date': pos['entry_date'], 'exit_date': str(d.date()),
                                   'exit_type': 'TAKE_PROFIT_UB', 'levels_used': pos['levels'],
                                   'shares': pos['shares'], 'pnl': pnl, 'return_pct': round(return_pct, 2),
                                   'hold_days': hold_days})
                    cash += proceeds
                    pos = None
                    round_no += 1
                    sold_today = True
                elif time_stop_days is not None and hold_days >= time_stop_days:
                    sell_price = close * (1 - slip)
                    amt = sell_price * pos['shares']
                    sr = stamp_rate(d)
                    fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
                    proceeds = amt - fee
                    pnl = proceeds - pos['total_cost']
                    return_pct = pnl / pos['total_cost'] * 100
                    trades.append({'round': round_no, 'ts_code': pos['ts_code'], 'name': pos['name'],
                                   'entry_date': pos['entry_date'], 'exit_date': str(d.date()),
                                   'exit_type': 'TIME_STOP', 'levels_used': pos['levels'],
                                   'shares': pos['shares'], 'pnl': pnl, 'return_pct': round(return_pct, 2),
                                   'hold_days': hold_days})
                    cash += proceeds
                    pos = None
                    round_no += 1
                    sold_today = True
                elif (not np.isnan(dd['bb_lower'][j]) and dd['close_adj'][j] < dd['bb_lower'][j]
                      and not dd['is_limit'][j] and pos['levels'] < max_levels):
                    if execution_mode == 'next_open':
                        pending_add = pos['ts_code']
                    else:
                        ensure_cash(level_cash)
                        buy_price = close * (1 + slip)
                        qty = int(min(level_cash, cash) / buy_price / 100) * 100
                        if qty >= 100:
                            amt = buy_price * qty
                            fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * TRANSFER_FEE_RATE
                            if amt + fee <= cash:
                                cash -= amt + fee
                                old_cost = pos['shares'] * pos['avg_cost']
                                pos['shares'] += qty
                                pos['avg_cost'] = (old_cost + amt + fee) / pos['shares']
                                pos['total_cost'] += amt + fee
                                pos['levels'] += 1
                if pos is not None:
                    stock_val = pos['shares'] * close
            else:
                stock_val = pos['shares'] * last_close.get(pos['ts_code'], pos['avg_cost'])

        # 空仓买入
        if pos is None and not sold_today:
            li = i - np.array([listing.get(tc, -999) for tc in dd['ts']])
            valid = (li >= min_listing_days) & ~dd['is_st']
            if valid.any():
                cand_idx = np.where(valid)[0]
                # 按 amount 取前 top_n
                amt = dd['amount'][cand_idx]
                order = np.argsort(-amt)
                order = order[:top_n]
                chosen = None
                for k in order:
                    j = cand_idx[k]
                    if (not np.isnan(dd['bb_lower'][j]) and dd['close_adj'][j] < dd['bb_lower'][j]
                            and not dd['is_limit'][j]):
                        chosen = j
                        break
                if chosen is not None:
                    if execution_mode == 'next_open':
                        pending_buy = {'ts_code': dd['ts'][chosen], 'name': None}
                    else:
                        ensure_cash(level_cash)
                        buy_price = dd['close'][chosen] * (1 + slip)
                        qty = int(min(level_cash, cash) / buy_price / 100) * 100
                        if qty >= 100:
                            amt = buy_price * qty
                            fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * TRANSFER_FEE_RATE
                            if amt + fee <= cash:
                                cash -= amt + fee
                                pos = {'ts_code': dd['ts'][chosen], 'name': dd.get('name', '') and '',
                                       'shares': qty, 'avg_cost': (amt + fee) / qty,
                                       'entry_date': str(d.date()), 'levels': 1,
                                       'total_cost': amt + fee, 'entry_day_idx': i}
                                stock_val = qty * buy_price

        # ETF 再平衡（空仓时）
        etf_val = etf_sh * enav if not np.isnan(enav) else etf_sh * epx
        if pos is None and etf_enabled and not np.isnan(epx):
            total_assets = cash + etf_val
            target_val = total_assets * etf_ratio
            diff = target_val - etf_val
            if diff > 100 * epx and cash >= 100 * epx:
                max_use = cash - etf_min_cash
                qty = int(min(diff, max_use) / (epx * (1 + slip)) / 100) * 100
                amt = qty * epx
                fee = max(amt * COMMISSION_RATE, MIN_COMMISSION)
                if amt + fee <= cash:
                    cash -= amt + fee
                    etf_sh += qty
                    etf_val += qty * enav
            elif diff < -100 * epx and etf_sh >= 100:
                sell_qty = int(-diff / (epx * (1 - slip)) / 100) * 100
                sell_qty = min(sell_qty, etf_sh)
                if sell_qty >= 100:
                    amt = sell_qty * epx
                    fee = max(amt * COMMISSION_RATE, MIN_COMMISSION)
                    cash += amt - fee
                    etf_sh -= sell_qty
                    etf_val -= sell_qty * enav

        etf_val = etf_sh * enav if not np.isnan(enav) else etf_sh * epx
        equity = cash + stock_val + etf_val
        equity_curve.append({'date': d, 'equity': equity, 'cash': cash,
                             'stock_val': stock_val, 'etf_val': etf_val, 'etf_shares': etf_sh,
                             'holding': pos['ts_code'] if pos else None})

    # 期末清仓
    last_d = days[-1]
    if pos is not None:
        dd = D[last_d]
        j = dd['pos'].get(pos['ts_code'])
        if j is not None:
            sell_price = dd['close'][j] * (1 - slip)
            amt = sell_price * pos['shares']
            sr = stamp_rate(last_d)
            fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
            proceeds = amt - fee
            pnl = proceeds - pos['total_cost']
            trades.append({'round': round_no, 'ts_code': pos['ts_code'], 'name': pos['name'],
                           'entry_date': pos['entry_date'], 'exit_date': str(last_d.date()),
                           'exit_type': 'FINAL_SETTLE', 'levels_used': pos['levels'],
                           'shares': pos['shares'], 'pnl': pnl, 'return_pct': round(pnl / pos['total_cost'] * 100, 2),
                           'hold_days': (n_days - 1) - pos['entry_day_idx']})
    if etf_sh > 0 and last_d in etf_idx:
        ei = etf_idx[last_d]
        amt = etf_px[ei] * etf_sh * (1 - slip)
        fee = max(amt * COMMISSION_RATE, MIN_COMMISSION)
        cash += amt - fee

    eq = pd.DataFrame(equity_curve)
    tr = pd.DataFrame(trades)
    return eq, tr


def stats(eq, tr, initial_cash=1_000_000):
    eq = eq.copy()
    ret = eq['equity'].pct_change().fillna(0)
    total = eq['equity'].iloc[-1] / initial_cash - 1
    years = len(eq) / 252
    ann = (1 + total) ** (1 / years) - 1 if years > 0 else 0
    peak = eq['equity'].cummax()
    dd = (eq['equity'] - peak) / peak
    sharpe = ret.mean() / ret.std() * np.sqrt(252) if ret.std() > 0 else 0
    n = len(tr)
    wr = (tr['pnl'] > 0).mean() * 100 if n else 0
    return {'total': total * 100, 'ann': ann * 100, 'mdd': dd.min() * 100, 'sharpe': sharpe,
            'n': n, 'wr': wr}


if __name__ == '__main__':
    import time
    t0 = time.time()
    days, D, etf_idx, epx, enav, df = prepare_fast()
    print(f'prepare {time.time()-t0:.0f}s')
    t0 = time.time()
    eq, tr = run_fast(days, D, etf_idx, epx, enav)
    print(f'run {time.time()-t0:.0f}s, trades={len(tr)}')
    print(stats(eq, tr))
