"""
Round5 独立红队修复与反事实验证
================================
审计员指出 P0(同bar未来信息) / P1(next_open) / P2(ETF滑点与估值) 等问题。
本引擎为审计专用：支持可配置 exit_bb_mode / buy_mode / ETF 滑点 / 估值口径，
不修改冻结基线 run_fast_multi（experiment_fast.py 保持原样）。
"""
import os
import sys
import time
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from experiment_fast import prepare_fast, stats, COMMISSION_RATE, MIN_COMMISSION, STAMP_TAX_FLAT, TRANSFER_FEE_RATE, STAMP_CUTOFF

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def load_and_extend(limit_down_mode='old', bb_window=20, bb_std=2.0):
    """加载数据并额外构造 bb_upper_prev（T-1 收盘后可确定的上轨，后复权口径）。
    返回 (days, D, etf_idx, etf_px, etf_open, etf_nav, df, listing)"""
    days, D, etf_idx, etf_px, etf_nav, df, listing = prepare_fast(
        limit_down_mode=limit_down_mode, bb_window=bb_window, bb_std=bb_std)
    # 每只股票 shift(1) 得到前一日 bb_upper
    df2 = df[['ts_code', 'date', 'bb_upper']].copy()
    df2['bb_upper_prev'] = df2.groupby('ts_code')['bb_upper'].shift(1)
    prev_map = {}
    for r in df2.itertuples(index=False):
        prev_map.setdefault(r.date, {})[r.ts_code] = r.bb_upper_prev
    for d in days:
        D[d]['bb_upper_prev'] = np.array([prev_map.get(d, {}).get(tc, np.nan) for tc in D[d]['ts']])
    # ETF open 数组
    m = pd.read_parquet(os.path.join(PROJECT_ROOT, 'data', 'etf_513500_merged.parquet'))
    m['trade_date'] = pd.to_datetime(m['trade_date'])
    m = m.sort_values('trade_date').reset_index(drop=True)
    etf_open = m['open'].to_numpy()
    return days, D, etf_idx, etf_px, etf_open, etf_nav, df, listing


def stamp_rate(dt, mode):
    return 0.001 if mode == 'historical' and dt < STAMP_CUTOFF else STAMP_TAX_FLAT


def run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav, listing=None,
                      K=2, top_n=10, max_levels=5, level_cash=200_000,
                      time_stop_days=None, etf_enabled=True, etf_min_cash=5_000,
                      etf_ratio=1.0, min_listing_days=60, initial_cash=1_000_000,
                      slippage_bp=0, stamp_tax_mode='flat', execution_constraints=False,
                      add_gap_days=1, buy_mode='close',          # 'close' | 'next_open'
                      exit_bb_mode='current',                     # 'current' | 'prev' | 'close_confirm_next'
                      etf_mark='nav',                             # 'nav' | 'close' 估值口径
                      skip_level5=False,                          # P3: 禁止第5层加仓(第4层后不再加)
                      day_range=None,                             # (start,end) 索引切片, 仅遍历 days[start:end]
                      pos_sort=None,                              # None|'oversold'|'amount'|'random' 持仓处理顺序
                      record_actions=False):
    """多持仓引擎（Round5 可配置版）。
    exit_bb_mode:
      current            : high_adj[T] >= bb_upper[T], 卖价 bb_upper[T]/adj[T]   (原逻辑, 含同bar未来)
      prev               : high_adj[T] >= bb_upper_prev[T], 卖价 bb_upper_prev[T]/adj[T]  (T-1 已知上轨)
      close_confirm_next : T 收盘 close_adj[T] >= bb_upper[T] -> T+1 open 卖出
    buy_mode:
      close              : T 收盘信号 -> T close 成交 (原逻辑)
      next_open          : T 收盘信号 -> T+1 open 成交
    """
    assert K >= 1
    slip = slippage_bp / 10000.0
    n_days = len(days)
    if listing is None:
        listing = {}

    cash = initial_cash
    positions = []
    etf_sh = 0
    equity_curve = []
    trades = []
    actions = []
    round_no = 0
    last_close = {}
    pending_buy = []          # [{ts_code, name}] next_open 待买入
    pending_add = {}          # ts_code -> 待加仓
    pending_sell = set()      # ts_code -> 待卖出 (close_confirm_next)

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
            hold_days=hold_days, ret_pct=round(ret, 2) if ret is not None else np.nan,
            tp_price=round(tp, 3) if tp else np.nan))

    for i, d in enumerate(days):
        if day_range is not None:
            if i < day_range[0] or i >= day_range[1]:
                continue
        dd = D[d]
        ei = etf_idx.get(d)
        if ei is not None:
            epx, eopx, enav = etf_px[ei], etf_open[ei], etf_nav[ei]
        else:
            epx, eopx, enav = np.nan, np.nan, np.nan
        # 当前用于成交的ETF价: next_open 用 open, close 用 close
        etf_trade_px = eopx if (buy_mode == 'next_open' or exit_bb_mode == 'close_confirm_next') and not np.isnan(eopx) else epx

        def ensure_cash(need):
            nonlocal cash, etf_sh
            if cash >= need or not etf_enabled or etf_sh <= 0 or np.isnan(etf_trade_px):
                return
            shortfall = need - cash
            sell_val = shortfall * 1.02
            # 卖出按当日成交价(close/open) 打滑点, 滑点进入现金
            sell_qty = int(np.ceil(sell_val / etf_trade_px / 100)) * 100
            sell_qty = min(sell_qty, etf_sh)
            if sell_qty >= 100:
                amt = sell_qty * etf_trade_px * (1 - slip)
                fee = max(amt * COMMISSION_RATE, MIN_COMMISSION)
                etf_sh -= sell_qty
                cash += amt - fee

        # ---------- T+1 开盘执行: 先卖 (close_confirm_next / time_stop 顺延), 再买 ----------
        if buy_mode == 'next_open' or exit_bb_mode == 'close_confirm_next':
            # 先执行待卖出 (close_confirm_next: 昨日收盘确认 -> 今日开盘卖)
            if exit_bb_mode == 'close_confirm_next' and pending_sell:
                for tc in list(pending_sell):
                    pos = next((p for p in positions if p['ts_code'] == tc), None)
                    j = dd['pos'].get(tc)
                    if pos is None or j is None:
                        pending_sell.discard(tc)
                        continue
                    sell_price = dd['open_'][j] * (1 - slip)
                    amt = sell_price * pos['shares']
                    sr = stamp_rate(d, stamp_tax_mode)
                    fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
                    proceeds = amt - fee
                    pnl = proceeds - pos['total_cost']
                    hold_days = i - pos['entry_day_idx']
                    trades.append({'round': round_no, 'ts_code': pos['ts_code'], 'name': pos.get('name'),
                                   'entry_date': pos['entry_date'], 'exit_date': str(d.date()),
                                   'exit_type': 'TAKE_PROFIT_UB', 'levels_used': pos['levels'],
                                   'shares': pos['shares'], 'pnl': pnl, 'return_pct': round(pnl / pos['total_cost'] * 100, 2),
                                   'hold_days': hold_days})
                    rec_action(d, j, 'TAKE_PROFIT', pos['levels'], sell_price, pos['shares'], amt, pos['avg_cost'], hold_days, ret=pnl / pos['total_cost'] * 100, tc=tc)
                    cash += proceeds
                    positions.remove(pos)
                    round_no += 1
                    pending_sell.discard(tc)
            # 再执行待买入/加仓 (next_open)
            if buy_mode == 'next_open' and (pending_buy or pending_add):
                # 先加仓
                if pending_add:
                    for tc in list(pending_add):
                        if tc not in pending_add:
                            continue
                        pos = next((p for p in positions if p['ts_code'] == tc), None)
                        j = dd['pos'].get(tc)
                        if pos is None or j is None:
                            pending_add.pop(tc, None)
                            continue
                        if (i - pos.get('last_add_i', pos['entry_day_idx'])) >= add_gap_days:
                            ensure_cash(level_cash)
                            buy_price = dd['open_'][j] * (1 + slip)
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
                                    rec_action(d, j, 'ADD_POSITION', pos['levels'], buy_price, qty, amt, pos['avg_cost'], i - pos['entry_day_idx'], tc=tc)
                        pending_add.pop(tc, None)
                # 再新买
                if pending_buy and len(positions) < K:
                    held = {p['ts_code'] for p in positions}
                    for pb in list(pending_buy):
                        if len(positions) >= K or pb['ts_code'] in held:
                            continue
                        j = dd['pos'].get(pb['ts_code'])
                        if j is None:
                            continue
                        # 一字涨停开盘无法买入（真实成交约束）
                        if execution_constraints and dd['is_limit_up'][j] and dd['one_word'][j]:
                            continue
                        ensure_cash(level_cash)
                        buy_price = dd['open_'][j] * (1 + slip)
                        qty = int(min(level_cash, cash) / buy_price / 100) * 100
                        if qty >= 100:
                            amt = buy_price * qty
                            fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * TRANSFER_FEE_RATE
                            if amt + fee <= cash:
                                cash -= amt + fee
                                npos = {'ts_code': pb['ts_code'], 'name': None,
                                        'shares': qty, 'avg_cost': (amt + fee) / qty,
                                        'l1_cost': (amt + fee) / qty,
                                        'entry_date': str(d.date()), 'levels': 1,
                                        'total_cost': amt + fee, 'entry_day_idx': i}
                                positions.append(npos)
                                rec_action(d, j, 'INITIAL_ENTRY', 1, buy_price, qty, amt, npos['avg_cost'], 0, tc=npos['ts_code'])
                                held.add(pb['ts_code'])
                        pending_buy = [x for x in pending_buy if x['ts_code'] != pb['ts_code']]

        sold_any = False
        stock_val = 0.0
        # ---------- 当日持仓处理 ----------
        proc_positions = list(positions)
        if pos_sort == 'oversold' and len(proc_positions) > 1:
            # 超卖程度: close_adj / bb_lower 越小越超卖, 优先处理(先加仓)
            def oversold_key(p):
                j = dd['pos'].get(p['ts_code'])
                if j is None or np.isnan(dd['bb_lower'][j]):
                    return 1e9
                return dd['close_adj'][j] / dd['bb_lower'][j]
            proc_positions.sort(key=oversold_key)
        elif pos_sort == 'amount' and len(proc_positions) > 1:
            def amt_key(p):
                j = dd['pos'].get(p['ts_code'])
                if j is None:
                    return -1e9
                return -dd['amount'][j]   # 成交额大优先
            proc_positions.sort(key=amt_key)
        elif pos_sort == 'random':
            rng = np.random.default_rng()
            rng.shuffle(proc_positions)
        for pos in proc_positions:
            j = dd['pos'].get(pos['ts_code'])
            if j is not None:
                close = dd['close'][j]
                last_close[pos['ts_code']] = close
                hold_days = i - pos['entry_day_idx']
                sellable = not (execution_constraints and dd['is_limit'][j])
                sold_here = False
                bb_cur = dd['bb_upper'][j]
                bb_prev = dd['bb_upper_prev'][j]
                # 退出判断
                do_exit = False
                exit_price = None
                if exit_bb_mode == 'current':
                    if not np.isnan(bb_cur) and hold_days >= 1 and dd['high_adj'][j] >= bb_cur and sellable:
                        do_exit = True
                        exit_price = (bb_cur / dd['adj'][j]) * (1 - slip)
                elif exit_bb_mode == 'prev':
                    if not np.isnan(bb_prev) and hold_days >= 1 and dd['high_adj'][j] >= bb_prev and sellable:
                        do_exit = True
                        exit_price = (bb_prev / dd['adj'][j]) * (1 - slip)
                elif exit_bb_mode == 'close_confirm_next':
                    # T 日收盘确认(收盘价站上T日上轨) -> 挂起, T+1 open 卖
                    if (not np.isnan(bb_cur) and hold_days >= 1
                            and dd['close_adj'][j] >= bb_cur and sellable
                            and pos['ts_code'] not in pending_sell):
                        pending_sell.add(pos['ts_code'])
                # 时间止损: 当日收盘价卖出（T日可执行, 收盘已知）
                if not do_exit and time_stop_days is not None and hold_days >= time_stop_days and sellable:
                    do_exit = True
                    exit_price = close * (1 - slip)
                    exit_type = 'TIME_STOP'
                if do_exit:
                    amt = exit_price * pos['shares']
                    sr = stamp_rate(d, stamp_tax_mode)
                    fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
                    proceeds = amt - fee
                    pnl = proceeds - pos['total_cost']
                    et = 'TIME_STOP' if exit_price == close * (1 - slip) else 'TAKE_PROFIT_UB'
                    trades.append({'round': round_no, 'ts_code': pos['ts_code'], 'name': pos.get('name'),
                                   'entry_date': pos['entry_date'], 'exit_date': str(d.date()),
                                   'exit_type': et, 'levels_used': pos['levels'],
                                   'shares': pos['shares'], 'pnl': pnl,
                                   'return_pct': round(pnl / pos['total_cost'] * 100, 2),
                                   'hold_days': hold_days})
                    rec_action(d, j, et, pos['levels'], exit_price, pos['shares'], amt, pos['avg_cost'], hold_days,
                               ret=pnl / pos['total_cost'] * 100, tc=pos['ts_code'])
                    cash += proceeds
                    positions.remove(pos)
                    round_no += 1
                    sold_any = True
                    sold_here = True
                elif (not do_exit and not np.isnan(dd['bb_lower'][j]) and dd['close_adj'][j] < dd['bb_lower'][j]
                      and not dd['is_limit'][j] and pos['levels'] < max_levels
                      and not (skip_level5 and pos['levels'] >= 4)
                      and (i - pos.get('last_add_i', pos['entry_day_idx'])) >= add_gap_days
                      and not (execution_constraints and dd['is_limit_up'][j] and dd['one_word'][j])):
                    if buy_mode == 'next_open':
                        pending_add[pos['ts_code']] = True
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
                                rec_action(d, j, 'ADD_POSITION', pos['levels'], buy_price, qty, amt, pos['avg_cost'], hold_days, tc=pos['ts_code'])
                if not sold_here:
                    stock_val += pos['shares'] * close
            else:
                stock_val += pos['shares'] * last_close.get(pos['ts_code'], pos['avg_cost'])

        # ---------- 新买入 ----------
        if not sold_any and len(positions) < K:
            li = i - np.array([listing.get(tc, -999) for tc in dd['ts']])
            valid = (li >= min_listing_days) & ~dd['is_st']
            if valid.any():
                cand_idx = np.where(valid)[0]
                amt = dd['amount'][cand_idx]
                order = np.argsort(-amt)
                order = order[:top_n]
                held = {p['ts_code'] for p in positions} | pending_sell
                for k in order:
                    if len(positions) >= K:
                        break
                    j = cand_idx[k]
                    if dd['ts'][j] in held:
                        continue
                    if (not np.isnan(dd['bb_lower'][j]) and dd['close_adj'][j] < dd['bb_lower'][j]
                            and not dd['is_limit'][j]
                            and not (execution_constraints and dd['is_limit_up'][j] and dd['one_word'][j])):
                        if buy_mode == 'next_open':
                            if not any(x['ts_code'] == dd['ts'][j] for x in pending_buy):
                                pending_buy.append({'ts_code': dd['ts'][j], 'name': None})
                            if len(pending_buy) >= K - len(positions):
                                break
                        else:
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
                                    rec_action(d, j, 'INITIAL_ENTRY', 1, buy_price, qty, amt, npos['avg_cost'], 0, tc=npos['ts_code'])

        # ---------- ETF 再平衡（资金永远满仓） ----------
        if etf_enabled and not np.isnan(etf_trade_px):
            excess = cash - etf_min_cash
            if excess > 100 * etf_trade_px:
                qty = int(excess / (etf_trade_px * (1 + slip)) / 100) * 100
                amt = qty * etf_trade_px * (1 + slip)     # 买入滑点进入现金
                fee = max(amt * COMMISSION_RATE, MIN_COMMISSION)
                if amt + fee <= cash:
                    cash -= amt + fee
                    etf_sh += qty

        # 估值
        if etf_mark == 'nav' and not np.isnan(enav):
            etf_val = etf_sh * enav
        else:
            etf_val = etf_sh * epx
        equity = cash + stock_val + etf_val
        equity_curve.append({'date': d, 'equity': equity, 'cash': cash,
                             'stock_val': stock_val, 'etf_val': etf_val, 'etf_shares': etf_sh,
                             'holding': [p['ts_code'] for p in positions] if positions else None})

    # ---------- 期末清仓（计入费用后同步到 equity 最后一行） ----------
    last_d = days[-1] if day_range is None else days[day_range[1] - 1]
    dd = D[last_d]
    for pos in list(positions):
        j = dd['pos'].get(pos['ts_code'])
        if j is not None:
            sell_price = dd['close'][j] * (1 - slip)
            amt = sell_price * pos['shares']
            sr = stamp_rate(last_d, stamp_tax_mode)
            fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
            proceeds = amt - fee
            pnl = proceeds - pos['total_cost']
            trades.append({'round': round_no, 'ts_code': pos['ts_code'], 'name': pos.get('name'),
                           'entry_date': pos['entry_date'], 'exit_date': str(last_d.date()),
                           'exit_type': 'FINAL_SETTLE', 'levels_used': pos['levels'],
                           'shares': pos['shares'], 'pnl': pnl,
                           'return_pct': round(pnl / pos['total_cost'] * 100, 2),
                           'hold_days': (n_days - 1) - pos['entry_day_idx']})
            cash += proceeds
    if etf_sh > 0 and last_d in etf_idx:
        ei = etf_idx[last_d]
        amt = etf_px[ei] * etf_sh * (1 - slip)
        fee = max(amt * COMMISSION_RATE, MIN_COMMISSION)
        cash += amt - fee
    # 把期末清仓后的 cash 同步到 equity 最后一行
    if equity_curve:
        equity_curve[-1]['equity'] = cash
        equity_curve[-1]['cash'] = cash
        equity_curve[-1]['stock_val'] = 0.0
        equity_curve[-1]['etf_val'] = 0.0
        equity_curve[-1]['etf_shares'] = 0
        equity_curve[-1]['holding'] = None

    eq = pd.DataFrame(equity_curve)
    tr = pd.DataFrame(trades)
    if record_actions:
        return eq, tr, pd.DataFrame(actions)
    return eq, tr


def full_stats(eq, tr, initial_cash=1_000_000):
    s = stats(eq, tr, initial_cash)
    return s


if __name__ == '__main__':
    t0 = time.time()
    days, D, etf_idx, etf_px, etf_nav, df, listing = load_and_extend()
    print(f'prepare {time.time()-t0:.0f}s')
    t0 = time.time()
    eq, tr = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_nav, listing, K=3,
                               exit_bb_mode='current', buy_mode='close', etf_mark='nav',
                               stamp_tax_mode='flat')
    print(f'run {time.time()-t0:.0f}s, trades={len(tr)}')
    print(full_stats(eq, tr))
