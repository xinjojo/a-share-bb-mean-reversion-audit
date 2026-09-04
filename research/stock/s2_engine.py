"""S2 Engine — STRICT_C with selectable candidate selection mode.

Modifies run_fast_multi_strict_c to support:
- 'amount': frozen official baseline (amount descending Top-N)
- 'random': uniform random without replacement from same-day eligible candidates

All other logic identical to frozen STRICT_C engine.
"""
import sys, os
import numpy as np, pandas as pd
from collections import deque

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
sys.path.insert(0, ROOT)
from round51_audit import (prepare_v51, full_stats, stamp_rate,
                           COMMISSION_RATE, MIN_COMMISSION, TRANSFER_FEE_RATE)
from run_strict_c_math import analytic_Pstar

OPEN_FILL_DEFAULT = 'limit_conservative'


def run_fast_multi_strict_c_s2(days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
                                K=3, top_n=10, max_levels=5, level_cash=200_000,
                                min_listing_days=60, initial_cash=1_000_000,
                                slippage_bp=10, stamp_tax_mode='historical',
                                exit_bb_mode='dynamic_touch',
                                open_fill=OPEN_FILL_DEFAULT,
                                tick_mode='conservative',
                                limit_slip_order='ref_first',
                                etf_enabled=True, etf_min_cash=5_000,
                                add_gap_days=1, day_range=None, record_actions=False,
                                flow_sink=None,
                                selection_mode='amount', seed=42):
    """S2 engine: identical to STRICT_C except candidate selection.
    selection_mode='amount': frozen baseline (amount descending Top-N)
    selection_mode='random': uniform random permutation of eligible candidates, take Top-N
    """
    rng = np.random.RandomState(seed)
    slip = slippage_bp / 10000.0
    cash = initial_cash
    positions = []
    etf_sh = 0
    equity_curve = []
    trades = []
    actions = []
    round_no = 0
    last_close = {}
    raw_hist = {}
    raw_hist_raw = {}
    pending_buy = []
    pending_add = {}
    pending_sell = set()
    p0_audit = []

    def ensure_cash_open(need):
        nonlocal cash, etf_sh
        if cash >= need or not etf_enabled or etf_sh <= 0:
            return
        ei = etf_idx.get(d)
        if ei is None or np.isnan(etf_open[ei]):
            return
        eopx = etf_open[ei]
        shortfall = need - cash
        sell_val = shortfall * 1.02
        sell_qty = int(np.ceil(sell_val / eopx / 100)) * 100
        sell_qty = min(sell_qty, etf_sh)
        if sell_qty >= 100:
            amt = sell_qty * eopx * (1 - slip)
            fee = max(amt * COMMISSION_RATE, MIN_COMMISSION)
            etf_sh -= sell_qty
            cash += amt - fee
            if flow_sink is not None:
                flow_sink.append(dict(date=str(d.date()), leg='etf', action='sell',
                                      gross=amt, fee=fee, net=amt - fee, shares=sell_qty, px=eopx))

    def rebalance_close():
        nonlocal cash, etf_sh
        if not etf_enabled:
            return
        ei = etf_idx.get(d)
        if ei is None or np.isnan(etf_px[ei]):
            return
        epx = etf_px[ei]
        reserve = (len(pending_buy) + len(pending_add)) * level_cash
        excess = cash - reserve - etf_min_cash
        if excess > 100 * epx:
            qty = int(excess / (epx * (1 + slip)) / 100) * 100
            amt = qty * epx * (1 + slip)
            fee = max(amt * COMMISSION_RATE, MIN_COMMISSION)
            if amt + fee <= cash - reserve - etf_min_cash:
                cash -= amt + fee
                etf_sh += qty
                if flow_sink is not None:
                    flow_sink.append(dict(date=str(d.date()), leg='etf', action='buy',
                                          gross=amt, fee=fee, net=-(amt + fee), shares=qty, px=epx))

    def find_pos(tc):
        return next((p for p in positions if p['ts_code'] == tc), None)

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

    def sell_pos(pos, d, j, price, exit_type):
        nonlocal cash, round_no
        amt = price * pos['shares']
        sr = stamp_rate(d, stamp_tax_mode)
        fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
        proceeds = amt - fee
        pnl = proceeds - pos['total_cost']
        hold_days = i - pos['entry_day_idx']
        trades.append({'round': round_no, 'ts_code': pos['ts_code'], 'name': pos.get('name'),
                       'entry_date': pos['entry_date'], 'exit_date': str(d.date()),
                       'exit_type': exit_type, 'levels_used': pos['levels'],
                       'shares': pos['shares'], 'pnl': pnl,
                       'return_pct': round(pnl / pos['total_cost'] * 100, 2),
                       'hold_days': hold_days})
        rec_action(d, j, exit_type, pos['levels'], price, pos['shares'], amt, pos['avg_cost'], hold_days,
                   ret=pnl / pos['total_cost'] * 100, tc=pos['ts_code'])
        cash += proceeds
        positions.remove(pos)
        round_no += 1
        if flow_sink is not None:
            flow_sink.append(dict(date=str(d.date()), leg='stock', action='sell',
                                  gross=amt, fee=fee, net=proceeds, shares=pos['shares'], px=price))

    def init_raw_hist(tc, i):
        hist = deque(); hist_r = deque()
        for k in range(1, 20):
            if i - k < 0:
                break
            dk = days[i - k]
            jk = D[dk]['pos'].get(tc)
            if jk is not None:
                hist.appendleft(float(D[dk]['close_adj'][jk]))
                hist_r.appendleft(float(D[dk]['close'][jk]))
        raw_hist[tc] = deque(hist, 19)
        raw_hist_raw[tc] = deque(hist_r, 19)

    for i, d in enumerate(days):
        if day_range is not None:
            if i < day_range[0] or i >= day_range[1]:
                continue
        dd = D[d]
        ei = etf_idx.get(d)
        epx = etf_px[ei] if ei is not None else np.nan
        eopx = etf_open[ei] if ei is not None else np.nan
        gi = offset + i

        # OPEN: execute pending orders
        if pending_sell:
            for tc in list(pending_sell):
                pos = find_pos(tc)
                j = dd['pos'].get(tc)
                if pos is None or j is None:
                    pending_sell.discard(tc)
                    continue
                if open_fill == 'limit_conservative' and dd['open_'][j] <= dd['limit_down_px'][j]:
                    continue
                sell_price = dd['open_'][j] * (1 - slip)
                sell_pos(pos, d, j, sell_price, 'TAKE_PROFIT_UB')
                pending_sell.discard(tc)
        if pending_add:
            for tc in list(pending_add):
                pos = find_pos(tc)
                j = dd['pos'].get(tc)
                if pos is None or j is None:
                    pending_add.pop(tc, None)
                    continue
                if pos['levels'] >= max_levels:
                    pending_add.pop(tc, None)
                    continue
                if open_fill == 'limit_conservative' and dd['open_'][j] >= dd['limit_up_px'][j]:
                    continue
                ensure_cash_open(level_cash)
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
                        if flow_sink is not None:
                            flow_sink.append(dict(date=str(d.date()), leg='stock', action='buy',
                                                  gross=amt, fee=fee, net=-(amt + fee), shares=qty, px=buy_price))
                pending_add.pop(tc, None)
        if pending_buy:
            held = {p['ts_code'] for p in positions}
            for pb in list(pending_buy):
                if len(positions) >= K or pb['ts_code'] in held:
                    pending_buy = [x for x in pending_buy if x['ts_code'] != pb['ts_code']]
                    continue
                j = dd['pos'].get(pb['ts_code'])
                if j is None:
                    pending_buy = [x for x in pending_buy if x['ts_code'] != pb['ts_code']]
                    continue
                if open_fill == 'limit_conservative' and dd['open_'][j] >= dd['limit_up_px'][j]:
                    continue
                ensure_cash_open(level_cash)
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
                                'total_cost': amt + fee, 'entry_day_idx': i, 'last_add_i': i}
                        positions.append(npos)
                        init_raw_hist(pb['ts_code'], i)
                        rec_action(d, j, 'INITIAL_ENTRY', 1, buy_price, qty, amt, npos['avg_cost'], 0, tc=npos['ts_code'])
                        held.add(pb['ts_code'])
                        if flow_sink is not None:
                            flow_sink.append(dict(date=str(d.date()), leg='stock', action='buy',
                                                  gross=amt, fee=fee, net=-(amt + fee), shares=qty, px=buy_price))
                pending_buy = [x for x in pending_buy if x['ts_code'] != pb['ts_code']]

        # Intraday exit: STRICT_C dynamic touch
        if exit_bb_mode == 'dynamic_touch':
            for pos in list(positions):
                j = dd['pos'].get(pos['ts_code'])
                if j is None:
                    continue
                if (i - pos['entry_day_idx']) < 1:
                    continue
                hist = raw_hist.get(pos['ts_code'])
                if hist is None or len(hist) < 19:
                    continue
                adjT = dd['adj'][j]
                x_correct = np.array(list(hist)[-19:], dtype=float)
                Pstar_adj = analytic_Pstar(x_correct)
                if Pstar_adj is None or not np.isfinite(Pstar_adj):
                    continue
                Pstar_raw = Pstar_adj / adjT
                tc = pos['ts_code']
                hist_r = raw_hist_raw.get(tc)
                if hist_r is not None and len(hist_r) >= 19:
                    x_old = np.array(list(hist_r)[-19:], dtype=float) * adjT
                    _po = analytic_Pstar(x_old)
                high_adj = dd['high_adj'][j]
                open_adj = dd['open_'][j] * adjT
                if tick_mode == 'conservative':
                    threshold = np.ceil(Pstar_raw / 0.01) * 0.01
                    sell_ref = threshold
                else:
                    threshold = Pstar_raw
                    sell_ref = Pstar_raw
                trig = dd['high_adj'][j] >= threshold * adjT
                if not trig:
                    continue
                if open_adj >= threshold * adjT:
                    ref = dd['open_'][j]
                else:
                    ref = sell_ref
                if limit_slip_order == 'ref_first':
                    if ref <= dd['limit_down_px'][j]:
                        continue
                    sell_price = ref * (1 - slip)
                else:
                    sell_price = ref * (1 - slip)
                    if sell_price <= dd['limit_down_px'][j]:
                        continue
                sell_pos(pos, d, j, sell_price, 'TAKE_PROFIT_DYN')

        # CLOSE
        stock_val = 0.0
        for pos in positions:
            j = dd['pos'].get(pos['ts_code'])
            if j is None:
                stock_val += pos['shares'] * last_close.get(pos['ts_code'], pos['avg_cost'])
                continue
            close = dd['close'][j]
            last_close[pos['ts_code']] = close
            raw_hist.setdefault(pos['ts_code'], deque([], 19)).append(float(dd['close_adj'][j]))
            raw_hist_raw.setdefault(pos['ts_code'], deque([], 19)).append(float(close))
            hold_days = i - pos['entry_day_idx']
            bb_lo = dd['bb_lower'][j]
            if (not np.isnan(bb_lo) and dd['close_adj'][j] < bb_lo
                    and not dd['is_limit'][j] and pos['levels'] < max_levels
                    and (i - pos.get('last_add_i', pos['entry_day_idx'])) >= add_gap_days):
                pending_add[pos['ts_code']] = True
            stock_val += pos['shares'] * close

        # === S2 KEY MODIFICATION: candidate selection ===
        if len(positions) < K:
            li = gi - np.array([first_eligible_i.get(tc, 0) for tc in dd['ts']])
            valid = (li >= 0) & ~dd['is_st']
            if valid.any():
                cand_idx = np.where(valid)[0]
                if selection_mode == 'amount':
                    amt = dd['amount'][cand_idx]
                    order = np.argsort(-amt)[:top_n]
                else:  # random
                    perm = rng.permutation(len(cand_idx))
                    order = perm[:top_n]
                held = {p['ts_code'] for p in positions} | pending_sell
                for k in order:
                    if len(positions) + len(pending_buy) >= K:
                        break
                    j = cand_idx[k]
                    tc = dd['ts'][j]
                    if tc in held or any(x['ts_code'] == tc for x in pending_buy):
                        continue
                    if (not np.isnan(dd['bb_lower'][j]) and dd['close_adj'][j] < dd['bb_lower'][j]
                            and not dd['is_limit'][j]):
                        pending_buy.append({'ts_code': tc, 'name': None})

        rebalance_close()

        etf_val = etf_sh * epx if not np.isnan(epx) else 0.0
        equity = cash + stock_val + etf_val
        equity_curve.append({'date': str(d.date()), 'equity': equity,
                             'cash': cash, 'stock_val': stock_val, 'etf_sh': etf_sh, 'etf_val': etf_val})

    # Final settlement
    d = days[day_range[1] - 1] if day_range else days[-1]
    dd = D[d]
    ei = etf_idx.get(d)
    epx = etf_px[ei] if ei is not None else np.nan
    for pos in list(positions):
        j = dd['pos'].get(pos['ts_code'])
        if j is not None:
            sell_price = dd['close'][j] * (1 - slip)
            amt = sell_price * pos['shares']
            sr = stamp_rate(d, stamp_tax_mode)
            fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
            proceeds = amt - fee
            pnl = proceeds - pos['total_cost']
            hold_days = (day_range[1] - 1 if day_range else len(days) - 1) - pos['entry_day_idx']
            trades.append({'round': round_no, 'ts_code': pos['ts_code'], 'name': pos.get('name'),
                           'entry_date': pos['entry_date'], 'exit_date': str(d.date()),
                           'exit_type': 'FINAL_SETTLE', 'levels_used': pos['levels'],
                           'shares': pos['shares'], 'pnl': pnl,
                           'return_pct': round(pnl / pos['total_cost'] * 100, 2),
                           'hold_days': hold_days})
            cash += proceeds
            positions.remove(pos)
            round_no += 1
    if etf_sh > 0 and not np.isnan(epx):
        amt = etf_sh * epx * (1 - slip)
        fee = max(amt * COMMISSION_RATE, MIN_COMMISSION)
        cash += amt - fee
        etf_sh = 0
    if equity_curve:
        equity_curve[-1]['equity'] = cash
        equity_curve[-1]['cash'] = cash
        equity_curve[-1]['stock_val'] = 0.0
        equity_curve[-1]['etf_sh'] = 0
        equity_curve[-1]['etf_val'] = 0.0

    eq = pd.DataFrame(equity_curve)
    tr = pd.DataFrame(trades)
    return eq, tr
