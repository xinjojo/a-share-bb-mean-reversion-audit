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
    # 涨停判定 (correct口径): 主板10%, ST5%, 创业板/科创板20%(创业板2020-08-24前10%)
    for d, g in df.groupby('date'):
        is_chi = g['ts_code'].str.startswith(('688', '689'))
        is_gem = g['ts_code'].str.startswith('30')
        gem_pct = np.where(g['date'] >= '2020-08-24', 0.20, 0.10)
        pct = np.where(is_chi, 0.20, np.where(is_gem, gem_pct, np.where(g['is_st'], 0.05, 0.10)))
        limit_up_px = (g['pre_close'] * (1 + pct)).round(2)
        D[d] = dict(
            ts=g['ts_code'].to_numpy(),
            close=g['close'].to_numpy(), open_=g['open'].to_numpy(),
            high=g['high'].to_numpy(), low=g['low'].to_numpy(),
            high_adj=g['high_adj'].to_numpy(), close_adj=g['close_adj'].to_numpy(),
            bb_lower=g['bb_lower'].to_numpy(), bb_upper=g['bb_upper'].to_numpy(), bb_mid=g['ma'].to_numpy(),
            amount=g['amount'].to_numpy(), is_limit=g['is_limit_down'].to_numpy(),
            is_st=g['is_st'].to_numpy(), adj=g['adj_factor'].to_numpy(),
            pre_close=g['pre_close'].to_numpy(),
            is_limit_up=(g['close'] >= limit_up_px).to_numpy(),
            one_word=((g['open'] == g['high']) & (g['high'] == g['low']) & (g['low'] == g['close'])).to_numpy(),
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
             slippage_bp=0, stamp_tax_mode='flat', execution_constraints=False,
             take_profit_mode='ub_intraday', record_actions=False,
             entry_drop20_max=None, add_gap_days=1, drop20_map=None, drop20_date_k=None,
             tp_after_maxlevels=None, tp_after_maxlevels_pct=0.0,
             rsi_map=None, rsi_ob_threshold=70):
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
    actions = []
    round_no = 0
    last_close = {}
    pending_buy = None
    pending_add = None

    def rec_action(d, j, action, level, price, shares, amount, avg_cost, hold_days, ret=None, tp=None):
        if not record_actions:
            return
        dd = D[d]
        actions.append(dict(
            date=str(d.date()), round=round_no, ts_code=dd['ts'][j],
            action=action, level=level,
            open=dd['open_'][j], high=dd['high'][j], low=dd['low'][j], close=dd['close'][j],
            bb_lower=round(dd['bb_lower'][j] / dd['adj'][j], 3) if not np.isnan(dd['bb_lower'][j]) else np.nan,
            bb_upper=round(dd['bb_upper'][j] / dd['adj'][j], 3) if not np.isnan(dd['bb_upper'][j]) else np.nan,
            price=round(price, 3), shares=shares, amount=round(amount, 2),
            avg_cost=round(avg_cost, 3) if avg_cost else np.nan,
            hold_days=hold_days,
            ret_pct=round(ret, 2) if ret is not None else np.nan,
            tp_price=round(tp, 3) if tp else np.nan,
        ))

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
            if pending_add is not None and pos is not None and (i - pos.get('last_add_i', pos['entry_day_idx'])) >= add_gap_days:
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
                            pos['last_add_i'] = i
                            rec_action(d, j, 'ADD_POSITION', pos['levels'], buy_price, qty, amt, pos['avg_cost'], i - pos['entry_day_idx'], tp=(dd['bb_upper'][j] / dd['adj'][j]) if not np.isnan(dd['bb_upper'][j]) else None)
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
                                   'l1_cost': (amt + fee) / qty,
                                   'entry_date': str(d.date()), 'levels': 1,
                                   'total_cost': amt + fee, 'entry_day_idx': i}
                            rec_action(d, j, 'INITIAL_ENTRY', 1, buy_price, qty, amt, pos['avg_cost'], 0, tp=(dd['bb_upper'][j] / dd['adj'][j]) if not np.isnan(dd['bb_upper'][j]) else None)
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
                sellable = not (execution_constraints and dd['is_limit'][j])
                if take_profit_mode == 'ub_close_confirm':
                    # 收盘确认 + 涨停顺延: 触上轨→等收盘; 涨停不卖顺延; 未涨停且收盘>上轨→收盘价卖
                    lim_up = dd['is_limit_up'][j]
                    hit_ub = (not np.isnan(bb_up)) and dd['high_adj'][j] >= bb_up
                    do_sell = False
                    if pos.get('tp_defer'):
                        if hold_days >= 1 and not lim_up:
                            do_sell = True  # 顺延中, 今日不涨停(涨跌皆可) → 收盘卖
                    elif hit_ub and hold_days >= 1:
                        if lim_up:
                            pos['tp_defer'] = True  # 涨停不卖, 挂起顺延
                        elif dd['close_adj'][j] > bb_up:
                            do_sell = True  # 收盘价>上轨 → 卖
                        # 影线触上轨(close<=ub) → 不卖
                    if do_sell and sellable:
                        sell_price = close * (1 - slip)
                        amt = sell_price * pos['shares']
                        sr = stamp_rate(d)
                        fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
                        proceeds = amt - fee
                        pnl = proceeds - pos['total_cost']
                        return_pct = pnl / pos['total_cost'] * 100
                        trades.append({'round': round_no, 'ts_code': pos['ts_code'], 'name': pos['name'],
                                       'entry_date': pos['entry_date'], 'exit_date': str(d.date()),
                                       'exit_type': 'TP_CLOSE_CONFIRM', 'levels_used': pos['levels'],
                                       'shares': pos['shares'], 'pnl': pnl, 'return_pct': round(return_pct, 2),
                                       'hold_days': hold_days})
                        rec_action(d, j, 'TAKE_PROFIT', pos['levels'], sell_price, pos['shares'], amt, pos['avg_cost'], hold_days, ret=return_pct, tp=(bb_up / dd['adj'][j]) if not np.isnan(bb_up) else None)
                        cash += proceeds
                        pos = None
                        round_no += 1
                        sold_today = True
                elif (take_profit_mode == 'ub_intraday' and tp_after_maxlevels is not None
                      and pos['levels'] >= max_levels and hold_days >= 1 and sellable):
                    adjf = dd['adj'][j]
                    hit = False
                    use_close = False
                    target_adj = np.nan
                    if tp_after_maxlevels == 'l1_cost':
                        target_adj = pos['l1_cost'] * adjf
                        hit = dd['high_adj'][j] >= target_adj
                    elif tp_after_maxlevels == 'avg_cost':
                        target_adj = pos['avg_cost'] * adjf
                        hit = dd['high_adj'][j] >= target_adj
                    elif tp_after_maxlevels == 'avg_cost_pct':
                        target_adj = pos['avg_cost'] * (1 + tp_after_maxlevels_pct) * adjf
                        hit = dd['high_adj'][j] >= target_adj
                    elif tp_after_maxlevels in ('bb_mid', 'ma20'):
                        target_adj = dd['bb_mid'][j]
                        hit = (not np.isnan(target_adj)) and dd['high_adj'][j] >= target_adj
                    elif tp_after_maxlevels == 'rsi_ob':
                        rsi = None
                        if rsi_map is not None:
                            m = rsi_map.get(pos['ts_code'])
                            rsi = m.get(d) if m else None
                        if rsi is not None and rsi >= rsi_ob_threshold:
                            hit = True
                            use_close = True  # RSI 收盘确认, 以收盘价成交(日线近似)
                    if hit:
                        sell_price = (close * (1 - slip)) if use_close else (target_adj / adjf) * (1 - slip)
                        amt = sell_price * pos['shares']
                        sr = stamp_rate(d)
                        fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
                        proceeds = amt - fee
                        pnl = proceeds - pos['total_cost']
                        return_pct = pnl / pos['total_cost'] * 100
                        trades.append({'round': round_no, 'ts_code': pos['ts_code'], 'name': pos['name'],
                                       'entry_date': pos['entry_date'], 'exit_date': str(d.date()),
                                       'exit_type': 'TP_AFTER_5L', 'levels_used': pos['levels'],
                                       'shares': pos['shares'], 'pnl': pnl, 'return_pct': round(return_pct, 2),
                                       'hold_days': hold_days})
                        rec_action(d, j, 'TAKE_PROFIT_5L', pos['levels'], sell_price, pos['shares'], amt, pos['avg_cost'], hold_days, ret=return_pct, tp=(target_adj / adjf) if not use_close else close)
                        cash += proceeds
                        pos = None
                        round_no += 1
                        sold_today = True
                elif not np.isnan(bb_up) and hold_days >= 1 and dd['high_adj'][j] >= bb_up and sellable:
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
                    rec_action(d, j, 'TAKE_PROFIT', pos['levels'], sell_price, pos['shares'], amt, pos['avg_cost'], hold_days, ret=return_pct, tp=(bb_up / dd['adj'][j]) if not np.isnan(bb_up) else None)
                    cash += proceeds
                    pos = None
                    round_no += 1
                    sold_today = True
                elif time_stop_days is not None and hold_days >= time_stop_days and sellable:
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
                    rec_action(d, j, 'TIME_STOP', pos['levels'], sell_price, pos['shares'], amt, pos['avg_cost'], hold_days, ret=return_pct)
                    cash += proceeds
                    pos = None
                    round_no += 1
                    sold_today = True
                elif (not np.isnan(dd['bb_lower'][j]) and dd['close_adj'][j] < dd['bb_lower'][j]
                      and not dd['is_limit'][j] and pos['levels'] < max_levels
                      and (i - pos.get('last_add_i', pos['entry_day_idx'])) >= add_gap_days
                      and not (execution_constraints and dd['is_limit_up'][j] and dd['one_word'][j])):
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
                                pos['last_add_i'] = i
                                rec_action(d, j, 'ADD_POSITION', pos['levels'], buy_price, qty, amt, pos['avg_cost'], hold_days, tp=(dd['bb_upper'][j] / dd['adj'][j]) if not np.isnan(dd['bb_upper'][j]) else None)
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
                    if entry_drop20_max is not None:
                        tc = dd['ts'][j]
                        m = drop20_date_k.get(tc)
                        arr = drop20_map.get(tc)
                        kk = m.get(d) if m else None
                        if kk is None or kk < 20 or arr is None:
                            continue
                        if arr[kk - 20] <= 0 or (arr[kk] / arr[kk - 20] - 1) * 100 < entry_drop20_max:
                            continue
                    if (not np.isnan(dd['bb_lower'][j]) and dd['close_adj'][j] < dd['bb_lower'][j]
                            and not dd['is_limit'][j]
                            and not (execution_constraints and dd['is_limit_up'][j] and dd['one_word'][j])):
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
                                       'l1_cost': (amt + fee) / qty,
                                       'entry_date': str(d.date()), 'levels': 1,
                                       'total_cost': amt + fee, 'entry_day_idx': i}
                                stock_val = qty * buy_price
                                rec_action(d, chosen, 'INITIAL_ENTRY', 1, buy_price, qty, amt, pos['avg_cost'], 0, tp=(dd['bb_upper'][chosen] / dd['adj'][chosen]) if not np.isnan(dd['bb_upper'][chosen]) else None)

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
            if record_actions:
                rec_action(last_d, j, 'FINAL_SETTLE', pos['levels'], sell_price, pos['shares'], amt, pos['avg_cost'], (n_days - 1) - pos['entry_day_idx'], ret=pnl / pos['total_cost'] * 100)
    if etf_sh > 0 and last_d in etf_idx:
        ei = etf_idx[last_d]
        amt = etf_px[ei] * etf_sh * (1 - slip)
        fee = max(amt * COMMISSION_RATE, MIN_COMMISSION)
        cash += amt - fee

    eq = pd.DataFrame(equity_curve)
    tr = pd.DataFrame(trades)
    if record_actions:
        return eq, tr, pd.DataFrame(actions)
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


def run_fast_multi(days, D, etf_idx, etf_px, etf_nav, listing=None, K=2, top_n=10, max_levels=5,
                   level_cash=200_000, time_stop_days=None, etf_enabled=True, etf_min_cash=5_000,
                   etf_ratio=1.0, min_listing_days=60, initial_cash=1_000_000,
                   slippage_bp=0, stamp_tax_mode='flat', execution_constraints=False,
                   add_gap_days=1, record_actions=False):
    """多持仓版本: 同时最多持有 K 只股票, 每只独立最多 max_levels 层×level_cash。
    共享资金池; 任一持仓当天止盈 -> 当天不再新买任何股票(延续单持仓 sold_today 语义);
    其他持仓的加仓不受影响; ETF 仅当全部空仓时再平衡。
    仅支持 execution_mode='close' (收盘价成交)。"""
    assert K >= 1
    slip = slippage_bp / 10000.0
    n_days = len(days)
    if listing is None:
        listing = {}

    def stamp_rate(dt):
        return 0.001 if stamp_tax_mode == 'historical' and dt < STAMP_CUTOFF else STAMP_TAX_FLAT

    cash = initial_cash
    positions = []
    etf_sh = 0
    equity_curve = []
    trades = []
    actions = []
    round_no = 0
    last_close = {}

    def rec_action(d, j, action, level, price, shares, amount, avg_cost, hold_days, ret=None, tp=None, tc=None):
        if not record_actions:
            return
        dd = D[d]
        actions.append(dict(
            date=str(d.date()), round=round_no, ts_code=tc if tc else dd['ts'][j],
            action=action, level=level,
            open=dd['open_'][j], high=dd['high'][j], low=dd['low'][j], close=dd['close'][j],
            bb_lower=round(dd['bb_lower'][j] / dd['adj'][j], 3) if not np.isnan(dd['bb_lower'][j]) else np.nan,
            bb_upper=round(dd['bb_upper'][j] / dd['adj'][j], 3) if not np.isnan(dd['bb_upper'][j]) else np.nan,
            price=round(price, 3), shares=shares, amount=round(amount, 2),
            avg_cost=round(avg_cost, 3) if avg_cost else np.nan,
            hold_days=hold_days,
            ret_pct=round(ret, 2) if ret is not None else np.nan,
            tp_price=round(tp, 3) if tp else np.nan,
        ))

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

        sold_any = False
        stock_val = 0.0
        # 持仓处理（每只独立）
        for pos in list(positions):
            j = dd['pos'].get(pos['ts_code'])
            if j is not None:
                close = dd['close'][j]
                last_close[pos['ts_code']] = close
                hold_days = i - pos['entry_day_idx']
                bb_up = dd['bb_upper'][j]
                sellable = not (execution_constraints and dd['is_limit'][j])
                sold_here = False
                if not np.isnan(bb_up) and hold_days >= 1 and dd['high_adj'][j] >= bb_up and sellable:
                    sell_price = (bb_up / dd['adj'][j]) * (1 - slip)
                    amt = sell_price * pos['shares']
                    sr = stamp_rate(d)
                    fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
                    proceeds = amt - fee
                    pnl = proceeds - pos['total_cost']
                    return_pct = pnl / pos['total_cost'] * 100
                    trades.append({'round': round_no, 'ts_code': pos['ts_code'], 'name': pos.get('name'),
                                   'entry_date': pos['entry_date'], 'exit_date': str(d.date()),
                                   'exit_type': 'TAKE_PROFIT_UB', 'levels_used': pos['levels'],
                                   'shares': pos['shares'], 'pnl': pnl, 'return_pct': round(return_pct, 2),
                                   'hold_days': hold_days})
                    rec_action(d, j, 'TAKE_PROFIT', pos['levels'], sell_price, pos['shares'], amt, pos['avg_cost'], hold_days, ret=return_pct, tp=(bb_up / dd['adj'][j]) if not np.isnan(bb_up) else None, tc=pos['ts_code'])
                    cash += proceeds
                    positions.remove(pos)
                    round_no += 1
                    sold_any = True
                    sold_here = True
                elif time_stop_days is not None and hold_days >= time_stop_days and sellable:
                    sell_price = close * (1 - slip)
                    amt = sell_price * pos['shares']
                    sr = stamp_rate(d)
                    fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
                    proceeds = amt - fee
                    pnl = proceeds - pos['total_cost']
                    return_pct = pnl / pos['total_cost'] * 100
                    trades.append({'round': round_no, 'ts_code': pos['ts_code'], 'name': pos.get('name'),
                                   'entry_date': pos['entry_date'], 'exit_date': str(d.date()),
                                   'exit_type': 'TIME_STOP', 'levels_used': pos['levels'],
                                   'shares': pos['shares'], 'pnl': pnl, 'return_pct': round(return_pct, 2),
                                   'hold_days': hold_days})
                    rec_action(d, j, 'TIME_STOP', pos['levels'], sell_price, pos['shares'], amt, pos['avg_cost'], hold_days, ret=return_pct, tc=pos['ts_code'])
                    cash += proceeds
                    positions.remove(pos)
                    round_no += 1
                    sold_any = True
                    sold_here = True
                elif (not np.isnan(dd['bb_lower'][j]) and dd['close_adj'][j] < dd['bb_lower'][j]
                      and not dd['is_limit'][j] and pos['levels'] < max_levels
                      and (i - pos.get('last_add_i', pos['entry_day_idx'])) >= add_gap_days
                      and not (execution_constraints and dd['is_limit_up'][j] and dd['one_word'][j])):
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
                            pos['last_add_i'] = i
                            rec_action(d, j, 'ADD_POSITION', pos['levels'], buy_price, qty, amt, pos['avg_cost'], hold_days, tp=(dd['bb_upper'][j] / dd['adj'][j]) if not np.isnan(dd['bb_upper'][j]) else None, tc=pos['ts_code'])
                if not sold_here:
                    stock_val += pos['shares'] * close
            else:
                stock_val += pos['shares'] * last_close.get(pos['ts_code'], pos['avg_cost'])

        # 新买入: 当天没有止盈时才扫描, 最多买到 K 只
        if not sold_any and len(positions) < K:
            li = i - np.array([listing.get(tc, -999) for tc in dd['ts']])
            valid = (li >= min_listing_days) & ~dd['is_st']
            if valid.any():
                cand_idx = np.where(valid)[0]
                amt = dd['amount'][cand_idx]
                order = np.argsort(-amt)
                order = order[:top_n]
                held = {p['ts_code'] for p in positions}
                for k in order:
                    if len(positions) >= K:
                        break
                    j = cand_idx[k]
                    if dd['ts'][j] in held:
                        continue
                    if (not np.isnan(dd['bb_lower'][j]) and dd['close_adj'][j] < dd['bb_lower'][j]
                            and not dd['is_limit'][j]
                            and not (execution_constraints and dd['is_limit_up'][j] and dd['one_word'][j])):
                        if cash < level_cash:
                            ensure_cash(level_cash)
                        if cash < level_cash:
                            break
                        buy_price = dd['close'][j] * (1 + slip)
                        qty = int(min(level_cash, cash) / buy_price / 100) * 100
                        if qty >= 100:
                            amt = buy_price * qty
                            fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * TRANSFER_FEE_RATE
                            if amt + fee <= cash:
                                cash -= amt + fee
                                npos = {'ts_code': dd['ts'][j], 'name': None,
                                        'shares': qty, 'avg_cost': (amt + fee) / qty,
                                        'l1_cost': (amt + fee) / qty,
                                        'entry_date': str(d.date()), 'levels': 1,
                                        'total_cost': amt + fee, 'entry_day_idx': i}
                                positions.append(npos)
                                stock_val += qty * buy_price
                                rec_action(d, j, 'INITIAL_ENTRY', 1, buy_price, qty, amt, npos['avg_cost'], 0, tp=(dd['bb_upper'][j] / dd['adj'][j]) if not np.isnan(dd['bb_upper'][j]) else None, tc=npos['ts_code'])

        # ETF 再平衡（资金永远满仓）: 持仓期剩余现金也买ETF, 需钱时由 ensure_cash 先卖ETF再买股票
        if etf_enabled and not np.isnan(epx):
            excess = cash - etf_min_cash
            if excess > 100 * epx:
                qty = int(excess / (epx * (1 + slip)) / 100) * 100
                amt = qty * epx
                fee = max(amt * COMMISSION_RATE, MIN_COMMISSION)
                if amt + fee <= cash:
                    cash -= amt + fee
                    etf_sh += qty

        etf_val = etf_sh * enav if not np.isnan(enav) else etf_sh * epx
        equity = cash + stock_val + etf_val
        equity_curve.append({'date': d, 'equity': equity, 'cash': cash,
                             'stock_val': stock_val, 'etf_val': etf_val, 'etf_shares': etf_sh,
                             'holding': [p['ts_code'] for p in positions] if positions else None})

    # 期末清仓
    last_d = days[-1]
    dd = D[last_d]
    for pos in list(positions):
        j = dd['pos'].get(pos['ts_code'])
        if j is not None:
            sell_price = dd['close'][j] * (1 - slip)
            amt = sell_price * pos['shares']
            sr = stamp_rate(last_d)
            fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
            proceeds = amt - fee
            pnl = proceeds - pos['total_cost']
            trades.append({'round': round_no, 'ts_code': pos['ts_code'], 'name': pos.get('name'),
                           'entry_date': pos['entry_date'], 'exit_date': str(last_d.date()),
                           'exit_type': 'FINAL_SETTLE', 'levels_used': pos['levels'],
                           'shares': pos['shares'], 'pnl': pnl, 'return_pct': round(pnl / pos['total_cost'] * 100, 2),
                           'hold_days': (n_days - 1) - pos['entry_day_idx']})
            rec_action(last_d, j, 'FINAL_SETTLE', pos['levels'], sell_price, pos['shares'], amt, pos['avg_cost'], (n_days - 1) - pos['entry_day_idx'], ret=pnl / pos['total_cost'] * 100, tc=pos['ts_code'])
            cash += proceeds
    if etf_sh > 0 and last_d in etf_idx:
        ei = etf_idx[last_d]
        amt = etf_px[ei] * etf_sh * (1 - slip)
        fee = max(amt * COMMISSION_RATE, MIN_COMMISSION)
        cash += amt - fee

    eq = pd.DataFrame(equity_curve)
    tr = pd.DataFrame(trades)
    if record_actions:
        return eq, tr, pd.DataFrame(actions)
    return eq, tr
