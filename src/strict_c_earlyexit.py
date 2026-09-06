"""EARLY-EXIT AUDIT — STRICT_C dynamic-touch 实验副本
基础 = src/run_strict_c.py 的 run_fast_multi_strict_c（8c479f6 修正口径, 逐字一致）
新增:
  1. early_exit_pct: 提前退出比例 X. 当 X>0:
       early_threshold = ceil(Pstar_raw*(1-X)/0.01)*0.01
       触发判定 high_adj >= early_threshold*adjT (原规则 X=0 完全一致)
  2. daily_pstar 收集: 每个持仓日记录 P* / legal threshold / high / gap / 浮盈亏
  3. flow_sink 保留 (ETF 资金流水)
本文件是实验副本, 不修改冻结引擎 src/run_strict_c.py.
"""
import sys, os
import numpy as np, pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from round51_audit import prepare_v51, full_stats, stamp_rate, \
    COMMISSION_RATE, MIN_COMMISSION, TRANSFER_FEE_RATE
from run_strict_c_math import analytic_Pstar

OPEN_FILL_DEFAULT = 'limit_conservative'


def run_fast_multi_strict_c_ee(days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
                               K=3, top_n=10, max_levels=5, level_cash=200_000,
                               min_listing_days=60, initial_cash=1_000_000,
                               slippage_bp=10, stamp_tax_mode='historical',
                               exit_bb_mode='dynamic_touch',
                               open_fill=OPEN_FILL_DEFAULT,
                               tick_mode='conservative',
                               limit_slip_order='ref_first',
                               etf_enabled=True, etf_min_cash=5_000,
                               add_gap_days=1, day_range=None, record_actions=False,
                               flow_sink=None, early_exit_pct=0.0, collect_daily_pstar=False):
    slip = slippage_bp / 10000.0
    X = early_exit_pct
    cash = initial_cash
    positions = []
    etf_sh = 0
    equity_curve = []
    trades = []
    actions = []
    daily_pstar = []
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
        hist = __import__('collections').deque()
        hist_r = __import__('collections').deque()
        for k in range(1, 20):
            if i - k < 0:
                break
            dk = days[i - k]
            jk = D[dk]['pos'].get(tc)
            if jk is not None:
                hist.appendleft(float(D[dk]['close_adj'][jk]))
                hist_r.appendleft(float(D[dk]['close'][jk]))
        raw_hist[tc] = __import__('collections').deque(hist, 19)
        raw_hist_raw[tc] = __import__('collections').deque(hist_r, 19)

    for i, d in enumerate(days):
        if day_range is not None:
            if i < day_range[0] or i >= day_range[1]:
                continue
        dd = D[d]
        ei = etf_idx.get(d)
        epx = etf_px[ei] if ei is not None else np.nan
        eopx = etf_open[ei] if ei is not None else np.nan
        gi = offset + i

        # ============ OPEN: 执行昨收挂单 ============
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

        # ============ 盘中退出: STRICT_C 动态 touch (P0 修正) + early_exit ============
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
                old_trigger = False
                Pstar_old_raw = np.nan
                if hist_r is not None and len(hist_r) >= 19:
                    x_old = np.array(list(hist_r)[-19:], dtype=float) * adjT
                    _po = analytic_Pstar(x_old)
                    if _po is not None and np.isfinite(_po):
                        Pstar_old_raw = _po / adjT
                        old_trigger = dd['high_adj'][j] >= _po
                adj_vals = []
                for _k in range(1, 20):
                    if i - _k < 0 or tc not in D[days[i - _k]]['pos']:
                        continue
                    adj_vals.append(float(D[days[i - _k]]['adj'][D[days[i - _k]]['pos'][tc]]))
                adj_changed = (len(adj_vals) >= 19 and any(abs(a - adjT) > 1e-12 for a in adj_vals))

                high_adj = dd['high_adj'][j]
                open_adj = dd['open_'][j] * adjT
                if tick_mode == 'conservative':
                    threshold = np.ceil(Pstar_raw / 0.01) * 0.01
                    sell_ref = threshold
                elif tick_mode == 'optimistic':
                    threshold = Pstar_raw
                    sell_ref = np.ceil(Pstar_raw / 0.01) * 0.01
                else:
                    threshold = Pstar_raw
                    sell_ref = Pstar_raw
                # ---- EARLY EXIT: 提前触发线 (X=0 时与 threshold 完全一致) ----
                if X > 0:
                    eff_raw = Pstar_raw * (1.0 - X)
                    eff_threshold = np.ceil(eff_raw / 0.01) * 0.01
                else:
                    eff_threshold = threshold
                trig = dd['high_adj'][j] >= eff_threshold * adjT
                if collect_daily_pstar:
                    daily_pstar.append(dict(
                        ts_code=pos['ts_code'], date=str(d.date()), level=pos['levels'],
                        avg_cost=round(float(pos['avg_cost']), 4),
                        entry_date=pos['entry_date'], adjT=float(adjT),
                        pstar_raw=float(Pstar_raw), threshold=float(threshold),
                        eff_threshold=float(eff_threshold), early_exit_pct=float(X),
                        high_raw=float(dd['high'][j]), close_raw=float(dd['close'][j]),
                        gap_raw=float(Pstar_raw - dd['high'][j]),
                        gap_legal=float(threshold - dd['high'][j]),
                        gap_eff=float(eff_threshold - dd['high'][j]),
                        pct_legal=(float(threshold - dd['high'][j]) / threshold if threshold > 0 else np.nan),
                        pct_eff=(float(eff_threshold - dd['high'][j]) / eff_threshold if eff_threshold > 0 else np.nan),
                        triggered=bool(trig), hold_days=int(i - pos['entry_day_idx']),
                        float_pnl=round(float(dd['close'][j] * pos['shares'] - pos['total_cost']), 2),
                        adj_changed=bool(adj_changed), pstar_old=Pstar_old_raw))
                p0_audit.append(dict(ts_code=pos['ts_code'], date=str(d.date()),
                                     adj_changed=bool(adj_changed),
                                     pstar_old=Pstar_old_raw, pstar_correct=Pstar_raw,
                                     old_trigger=bool(old_trigger), corr_trigger=bool(trig)))
                if not trig:
                    continue
                if open_adj >= eff_threshold * adjT:
                    ref = dd['open_'][j]
                else:
                    ref = eff_threshold if X > 0 else sell_ref
                if limit_slip_order == 'ref_first':
                    if ref <= dd['limit_down_px'][j]:
                        continue
                    sell_price = ref * (1 - slip)
                else:
                    sell_price = ref * (1 - slip)
                    if sell_price <= dd['limit_down_px'][j]:
                        continue
                sell_pos(pos, d, j, sell_price, 'TAKE_PROFIT_DYN')

        # ============ CLOSE ============
        stock_val = 0.0
        for pos in positions:
            j = dd['pos'].get(pos['ts_code'])
            if j is None:
                stock_val += pos['shares'] * last_close.get(pos['ts_code'], pos['avg_cost'])
                continue
            close = dd['close'][j]
            last_close[pos['ts_code']] = close
            raw_hist.setdefault(pos['ts_code'], __import__('collections').deque([], 19)).append(float(dd['close_adj'][j]))
            raw_hist_raw.setdefault(pos['ts_code'], __import__('collections').deque([], 19)).append(float(close))
            hold_days = i - pos['entry_day_idx']
            bb_lo = dd['bb_lower'][j]
            if (not np.isnan(bb_lo) and dd['close_adj'][j] < bb_lo
                    and not dd['is_limit'][j] and pos['levels'] < max_levels
                    and (i - pos.get('last_add_i', pos['entry_day_idx'])) >= add_gap_days):
                pending_add[pos['ts_code']] = True
            stock_val += pos['shares'] * close

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
            if flow_sink is not None:
                flow_sink.append(dict(date=str(d.date()), leg='stock', action='settle',
                                      gross=amt, fee=fee, net=proceeds, shares=pos['shares'], px=sell_price))
    if etf_sh > 0 and not np.isnan(epx):
        amt = etf_sh * epx * (1 - slip)
        fee = max(amt * COMMISSION_RATE, MIN_COMMISSION)
        cash += amt - fee
        etf_sh = 0
        if flow_sink is not None:
            flow_sink.append(dict(date=str(d.date()), leg='etf', action='settle',
                                  gross=amt, fee=fee, net=amt - fee, shares=0, px=epx * (1 - slip)))
    if equity_curve:
        equity_curve[-1]['equity'] = cash
        equity_curve[-1]['cash'] = cash
        equity_curve[-1]['stock_val'] = 0.0
        equity_curve[-1]['etf_sh'] = 0
        equity_curve[-1]['etf_val'] = 0.0

    eq = pd.DataFrame(equity_curve)
    tr = pd.DataFrame(trades)
    ac = pd.DataFrame(actions) if actions else pd.DataFrame()
    pa = pd.DataFrame(p0_audit) if p0_audit else pd.DataFrame()
    dp = pd.DataFrame(daily_pstar) if daily_pstar else pd.DataFrame()
    return eq, tr, ac, pa, dp


if __name__ == '__main__':
    import json
    OUT = os.path.join(ROOT, 'audit_package', 'github_repo', 'results', 'evidence', 'ee_audit')
    os.makedirs(OUT, exist_ok=True)

    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51(
        limit_down_mode='correct', st_mode='pit')
    for _d in days:
        _dd = D[_d]
        _dd['one_word'] = ((_dd['open_'] == _dd['high']) & (_dd['low'] == _dd['close'])
                           & (_dd['open_'] == _dd['close']))
    rng_full = (0, len(days))
    flow = []

    # ===== BASE (X=0): 记录 actions + flow + daily_pstar =====
    eq0, tr0, ac0, pa0, dp0 = run_fast_multi_strict_c_ee(
        days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
        K=3, top_n=10, max_levels=5, level_cash=200_000, initial_cash=1_000_000,
        slippage_bp=10, stamp_tax_mode='historical', exit_bb_mode='dynamic_touch',
        open_fill='limit_conservative', day_range=rng_full, record_actions=True,
        flow_sink=flow, early_exit_pct=0.0, collect_daily_pstar=True)
    st0 = full_stats(eq0, tr0)
    print('[BASE X=0]', st0, 'stock_pnl=', round(float(tr0['pnl'].sum()), 2))
    tr0.to_csv(os.path.join(OUT, 'base_trades.csv'), index=False)
    eq0.to_csv(os.path.join(OUT, 'base_equity.csv'), index=False)
    ac0.to_csv(os.path.join(OUT, 'base_actions.csv'), index=False)
    pd.DataFrame(flow).to_csv(os.path.join(OUT, 'base_flows.csv'), index=False)
    dp0.to_csv(os.path.join(OUT, 'all_holding_days_pstar_distance.csv'), index=False)
    pa0.to_csv(os.path.join(OUT, 'base_p0_audit.csv'), index=False)

    # ===== EARLY EXIT VARIANTS =====
    xs = [0.001, 0.002, 0.003, 0.005, 0.0075, 0.01, 0.015, 0.02]
    rows = []
    yearly_rows = []
    for X in xs:
        f2 = []
        eq, tr, ac, pa, dp = run_fast_multi_strict_c_ee(
            days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
            K=3, top_n=10, max_levels=5, level_cash=200_000, initial_cash=1_000_000,
            slippage_bp=10, stamp_tax_mode='historical', exit_bb_mode='dynamic_touch',
            open_fill='limit_conservative', day_range=rng_full, record_actions=False,
            flow_sink=f2, early_exit_pct=X)
        st = full_stats(eq, tr)
        rows.append({'early_exit_pct': X * 100, 'total_return_pct': st['total'],
                     'cagr_pct': st['ann'], 'maxdd_pct': st['mdd'], 'sharpe': st['sharpe'],
                     'trades': st['n'], 'win_rate_pct': st['wr'],
                     'stock_pnl': round(float(tr['pnl'].sum()), 2)})
        tr.to_csv(os.path.join(OUT, f'trades_ee_{X*100:.2f}.csv'), index=False)
        eq.to_csv(os.path.join(OUT, f'equity_ee_{X*100:.2f}.csv'), index=False)
        print(f'[EE {X*100:.2f}%]', st)
        # 逐年
        eqy = eq.copy(); eqy['year'] = eqy['date'].str[:4]
        tr_y = tr.copy(); tr_y['year'] = tr_y['entry_date'].str[:4]
        for y in ['2020', '2021', '2022', '2023', '2024', '2025', '2026']:
            sub = eqy[eqy['year'] == y]
            if len(sub) == 0:
                continue
            ret = sub['equity'].iloc[-1] / sub['equity'].iloc[0] - 1
            sub_tr = tr_y[tr_y['year'] == y]
            yearly_rows.append({'early_exit_pct': X * 100, 'year': y, 'year_return_pct': ret * 100,
                                'trades': len(sub_tr), 'pnl': round(float(sub_tr['pnl'].sum()), 2)})
    pd.DataFrame(rows).to_csv(os.path.join(OUT, 'early_exit_parameter_results.csv'), index=False)
    # base 逐年
    eq0y = eq0.copy(); eq0y['year'] = eq0y['date'].str[:4]
    tr0y = tr0.copy(); tr0y['year'] = tr0y['entry_date'].str[:4]
    for y in ['2020', '2021', '2022', '2023', '2024', '2025', '2026']:
        sub = eq0y[eq0y['year'] == y]
        if len(sub) == 0:
            continue
        ret = sub['equity'].iloc[-1] / sub['equity'].iloc[0] - 1
        sub_tr = tr0y[tr0y['year'] == y]
        yearly_rows.append({'early_exit_pct': 0.0, 'year': y, 'year_return_pct': ret * 100,
                            'trades': len(sub_tr), 'pnl': round(float(sub_tr['pnl'].sum()), 2)})
    pd.DataFrame(yearly_rows).to_csv(os.path.join(OUT, 'early_exit_yearly_results.csv'), index=False)
    print('saved all.')
