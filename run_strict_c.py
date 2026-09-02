"""STRICT_C — DYNAMIC INTRADAY BOLLINGER TOUCH (原策略语义复原审计)
T 日盘中实时上轨随价格变化: Upper(P)=mean(prev19,P)+2*sd(prev19,P), ddof=1
首次 P>=Upper(P) -> 卖出. 由数学证明: high>=P* (P* 为临界价) 等价于盘中曾触碰.
- gap-through: open>=P* -> 按 open 卖; open<P*<=high -> 按 P* 卖; high<P* -> 不卖.
沿用 STRICT_V2 全部基础设施: PIT ST / PIT listing / correct涨跌停 / T+1 / lot / 费用 / 滑点 / 事件驱动ETF / 期末清仓.
不触碰 HYPOTHESIS_REGISTRY.
"""
import sys, os
import numpy as np, pandas as pd
from collections import deque

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
sys.path.insert(0, ROOT)
from round51_audit import (prepare_v51, full_stats, stamp_rate,
                           COMMISSION_RATE, MIN_COMMISSION, TRANSFER_FEE_RATE)
from round5_audit import load_and_extend, run_fast_multi_v5
from run_strict_c_math import analytic_Pstar

OPEN_FILL_DEFAULT = 'limit_conservative'


def run_fast_multi_strict_c(days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
                            K=3, top_n=10, max_levels=5, level_cash=200_000,
                            min_listing_days=60, initial_cash=1_000_000,
                            slippage_bp=10, stamp_tax_mode='historical',
                            exit_bb_mode='dynamic_touch',
                            open_fill=OPEN_FILL_DEFAULT,
                            etf_enabled=True, etf_min_cash=5_000,
                            add_gap_days=1, day_range=None, record_actions=False):
    """事件驱动引擎, 买入 T收盘信号->T+1 open; 退出 STRICT_C 盘中动态 touch."""
    slip = slippage_bp / 10000.0
    cash = initial_cash
    positions = []
    etf_sh = 0
    equity_curve = []
    trades = []
    actions = []
    round_no = 0
    last_close = {}
    raw_hist = {}          # tc -> deque(最近 close_raw, maxlen=19) 截至 T-1
    pending_buy = []
    pending_add = {}
    pending_sell = set()

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

    def init_raw_hist(tc, i):
        """买入时用历史补齐前19日 close_raw"""
        hist = deque()
        for k in range(1, 20):
            if i - k < 0:
                break
            dk = days[i - k]
            jk = D[dk]['pos'].get(tc)
            if jk is not None:
                hist.appendleft(float(D[dk]['close'][jk]))
        raw_hist[tc] = deque(hist, 19)

    for i, d in enumerate(days):
        if day_range is not None:
            if i < day_range[0] or i >= day_range[1]:
                continue
        dd = D[d]
        ei = etf_idx.get(d)
        epx = etf_px[ei] if ei is not None else np.nan
        eopx = etf_open[ei] if ei is not None else np.nan
        gi = offset + i

        # ============ OPEN 时点: 执行昨收挂单 ============
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
                pending_buy = [x for x in pending_buy if x['ts_code'] != pb['ts_code']]

        # ============ 盘中退出: STRICT_C 动态 touch ============
        if exit_bb_mode == 'dynamic_touch':
            for pos in list(positions):
                j = dd['pos'].get(pos['ts_code'])
                if j is None:
                    continue
                if (i - pos['entry_day_idx']) < 1:
                    continue   # T+1
                hist = raw_hist.get(pos['ts_code'])
                if hist is None or len(hist) < 19:
                    continue
                adj = dd['adj'][j]
                x = np.array(list(hist)[-19:], dtype=float) * adj   # T 日口径
                Pstar_adj = analytic_Pstar(x)
                if Pstar_adj is None or not np.isfinite(Pstar_adj):
                    continue
                high_adj = dd['high_adj'][j]
                if high_adj < Pstar_adj:
                    continue   # 未触碰
                open_adj = dd['open_'][j] * adj
                if open_adj >= Pstar_adj:
                    sell_price = dd['open_'][j] * (1 - slip)   # gap-through
                else:
                    sell_price = (Pstar_adj / adj) * (1 - slip)
                if sell_price <= dd['limit_down_px'][j]:
                    continue   # 跌停卖不出, 顺延
                sell_pos(pos, d, j, sell_price, 'TAKE_PROFIT_DYN')

        # ============ CLOSE 时点 ============
        stock_val = 0.0
        for pos in positions:
            j = dd['pos'].get(pos['ts_code'])
            if j is None:
                stock_val += pos['shares'] * last_close.get(pos['ts_code'], pos['avg_cost'])
                continue
            close = dd['close'][j]
            last_close[pos['ts_code']] = close
            raw_hist.setdefault(pos['ts_code'], deque([], 19)).append(float(close))
            hold_days = i - pos['entry_day_idx']
            bb_lo = dd['bb_lower'][j]
            if (not np.isnan(bb_lo) and dd['close_adj'][j] < bb_lo
                    and not dd['is_limit'][j] and pos['levels'] < max_levels
                    and (i - pos.get('last_add_i', pos['entry_day_idx'])) >= add_gap_days):
                pending_add[pos['ts_code']] = True
            stock_val += pos['shares'] * close

        # 新买信号 (TopN): 收盘确认 -> T+1 open
        if len(positions) < K:
            li = gi - np.array([first_eligible_i.get(tc, 0) for tc in dd['ts']])
            valid = (li >= 0) & ~dd['is_st']
            if valid.any():
                cand_idx = np.where(valid)[0]
                amt = dd['amount'][cand_idx]
                order = np.argsort(-amt)[:top_n]
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

    # ============ 期末清仓 ============
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
    ac = pd.DataFrame(actions) if actions else pd.DataFrame()
    return eq, tr, ac


def match_trigger_diff(tr_invalid, tr_c, tol_days=2):
    """逐笔配对: INVALID ORIGINAL 卖出 vs STRICT_C 卖出.
    按 (ts_code, entry_date 相差<=tol_days 交易日近似) 配对."""
    if len(tr_invalid) == 0 or len(tr_c) == 0:
        return {}
    tin = tr_invalid[tr_invalid['exit_type'] != 'FINAL_SETTLE'].copy()
    tc_ = tr_c[tr_c['exit_type'] != 'FINAL_SETTLE'].copy()
    tin['e'] = pd.to_datetime(tin['entry_date'])
    tc_['e'] = pd.to_datetime(tc_['entry_date'])
    tin['x'] = pd.to_datetime(tin['exit_date'])
    tc_['x'] = pd.to_datetime(tc_['exit_date'])
    used = set()
    same_day = 0; changed = 0; price_diff_sum = 0.0; price_diff_n = 0
    changed_detail = []
    for _, a in tin.iterrows():
        cand = tc_[(tc_['ts_code'] == a['ts_code']) & (tc_['e'] >= a['e'] - pd.Timedelta(days=7))
                  & (tc_['e'] <= a['e'] + pd.Timedelta(days=7))]
        if len(cand) == 0:
            continue
        cand = cand[~cand.index.isin(used)]
        if len(cand) == 0:
            continue
        best = (cand['e'] - a['e']).abs().idxmin()
        used.add(best)
        b = tc_.loc[best]
        if b['x'] == a['x']:
            same_day += 1
        else:
            changed += 1
            changed_detail.append((a['ts_code'], str(a['x'].date()), str(b['x'].date()),
                                   int((b['x'] - a['x']).days)))
    # 未配对的 INVALID 卖出
    matched = len(used)
    unmatched_invalid = len(tin) - matched
    # STRICT_C 中 INVALID 未识别的
    missed = len(tc_) - matched
    return dict(invalid_total=len(tin), matched=matched, same_day=same_day, changed=changed,
                unmatched_invalid=unmatched_invalid, missed_c=missed,
                changed_detail=changed_detail)


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'

    # ===== 数据 =====
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51(
        limit_down_mode='correct', st_mode='pit')
    # round5 引擎需要 one_word 字段 (日线口径 open==high==low==close)
    for _d in days:
        _dd = D[_d]
        _dd['one_word'] = ((_dd['open_'] == _dd['high']) & (_dd['low'] == _dd['close'])
                           & (_dd['open_'] == _dd['close']))
    # round5 listing 语义: i-listing>=60 -> 传上市日索引(=首可交易-60)
    listing5 = {tc: v - 60 for tc, v in first_eligible_i.items()}
    full = (0, len(days))
    rng_full = (0, len(days))

    out = {}
    # ===== 1) INVALID ORIGINAL (round5 current, 同Bar未来信息, 对照) =====
    if mode in ('all', 'invalid'):
        # round5 用 load_and_extend 数据(默认 old 口径+snapshot ST); 为对照公平此处同样跑 current 语义
        eq5, tr5 = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav,
                                     listing=listing5, K=3, top_n=10, max_levels=5,
                                     level_cash=200_000, initial_cash=1_000_000,
                                     slippage_bp=0, stamp_tax_mode='flat',
                                     exit_bb_mode='current', buy_mode='close',
                                     etf_mark='close', etf_enabled=True,
                                     day_range=rng_full, record_actions=False)
        st5 = full_stats(eq5, tr5)
        out['INVALID_ORIGINAL'] = dict(stats=st5, eq=eq5, tr=tr5)
        print('[INVALID_ORIGINAL]', st5, 'stock_pnl=', round(float(tr5['pnl'].sum()), 2))

    # ===== 2) STRICT_A (prev) =====
    if mode in ('all', 'a'):
        from round51_audit import run_fast_multi_v51
        eqA, trA, _ = run_fast_multi_v51(days, D, etf_idx, etf_px, etf_open, etf_nav,
                                         first_eligible_i, offset, K=3, top_n=10, max_levels=5,
                                         level_cash=200_000, initial_cash=1_000_000,
                                         slippage_bp=10, stamp_tax_mode='historical',
                                         exit_bb_mode='prev', open_fill='limit_conservative',
                                         day_range=rng_full, record_actions=False)
        stA = full_stats(eqA, trA)
        out['STRICT_A'] = dict(stats=stA, eq=eqA, tr=trA)
        print('[STRICT_A]', stA, 'stock_pnl=', round(float(trA['pnl'].sum()), 2))

    # ===== 3) STRICT_B (close_confirm_next) =====
    if mode in ('all', 'b'):
        from round51_audit import run_fast_multi_v51
        eqB, trB, _ = run_fast_multi_v51(days, D, etf_idx, etf_px, etf_open, etf_nav,
                                         first_eligible_i, offset, K=3, top_n=10, max_levels=5,
                                         level_cash=200_000, initial_cash=1_000_000,
                                         slippage_bp=10, stamp_tax_mode='historical',
                                         exit_bb_mode='close_confirm_next', open_fill='limit_conservative',
                                         day_range=rng_full, record_actions=False)
        stB = full_stats(eqB, trB)
        out['STRICT_B'] = dict(stats=stB, eq=eqB, tr=trB)
        print('[STRICT_B]', stB, 'stock_pnl=', round(float(trB['pnl'].sum()), 2))

    # ===== 4) STRICT_C (dynamic touch) =====
    if mode in ('all', 'c'):
        eqC, trC, acC = run_fast_multi_strict_c(days, D, etf_idx, etf_px, etf_open, etf_nav,
                                                first_eligible_i, offset, K=3, top_n=10, max_levels=5,
                                                level_cash=200_000, initial_cash=1_000_000,
                                                slippage_bp=10, stamp_tax_mode='historical',
                                                exit_bb_mode='dynamic_touch',
                                                open_fill='limit_conservative',
                                                day_range=rng_full, record_actions=False)
        stC = full_stats(eqC, trC)
        out['STRICT_C'] = dict(stats=stC, eq=eqC, tr=trC, ac=acC)
        print('[STRICT_C]', stC, 'stock_pnl=', round(float(trC['pnl'].sum()), 2))
        trC.to_csv(os.path.join(ROOT, 'results', 'round5', 'strict_c_trades.csv'), index=False)
        eqC.to_csv(os.path.join(ROOT, 'results', 'round5', 'strict_c_equity.csv'), index=False)
        print('strict_c saved.')

    # ===== 触发差异 =====
    if mode in ('all', 'diff') and 'INVALID_ORIGINAL' in out and 'STRICT_C' in out:
        diff = match_trigger_diff(out['INVALID_ORIGINAL']['tr'], out['STRICT_C']['tr'])
        print('\n[触发差异 INVALID vs STRICT_C]', diff)

    # ===== 保存对照汇总 =====
    if mode == 'all':
        rows = []
        for k in ('INVALID_ORIGINAL', 'STRICT_A', 'STRICT_B', 'STRICT_C'):
            if k in out:
                s = out[k]['stats']; tr = out[k]['tr']
                rows.append({'version': k, 'total_return_pct': s['total'], 'ann_pct': s['ann'],
                             'maxdd_pct': s['mdd'], 'sharpe': s['sharpe'], 'trades': s['n'],
                             'win_rate_pct': s['wr'], 'stock_pnl': round(float(tr['pnl'].sum()), 2)})
        df = pd.DataFrame(rows)
        os.makedirs(os.path.join(ROOT, 'results', 'round5'), exist_ok=True)
        df.to_csv(os.path.join(ROOT, 'results', 'round5', 'strict_c_matrix.csv'), index=False)
        print('\n[汇总矩阵]'); print(df.to_string(index=False))
