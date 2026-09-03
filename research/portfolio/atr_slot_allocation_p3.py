"""PHASE P3 — VALIDATED SINGLE-FACTOR SLOT ALLOCATION (ATR20_PCT) PORTFOLIO COUNTERFACTUAL.
Development / portfolio-construction period ONLY: 2020-01-01 .. 2024-12-31.
2025-2026 Confirmation CLOSED.

Compares three initial-entry candidate-priority rules inside the frozen
STRICT_C_EXECUTABLE_TICK portfolio engine (run_fast_multi_strict_c semantics; only the
INITIAL ENTRY CANDIDATE PRIORITY differs — entry/exit/add/cash/fees all frozen):
  B0 = FROZEN_AMOUNT_TOP10  (turnover Top10, amount priority)  [= frozen G0 baseline]
  B1 = SAME_TOP10_ATR_REORDER (same Top10 universe, ATR20_PCT descending priority)  PRIMARY
  B2 = FULL_SIGNAL_ATR_RANK  (all eligible oversold, ATR20_PCT descending)            SECONDARY
PURE STOCK primary. ATR20_PCT = mean(TR last20 observed bars)/close, T-close info only.
Pre-registered: ATR_SLOT_ALLOCATION_REGISTRY.csv (commit 5eca01d, SHA 1e13f9f7).
"""
import os, sys, json
import numpy as np, pandas as pd
from collections import deque

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
sys.path.insert(0, ROOT)
from round51_audit import prepare_v51, stamp_rate, COMMISSION_RATE, MIN_COMMISSION, TRANSFER_FEE_RATE
sys.path.insert(0, REPO)
from cross_sectional_ranking_p1 import build_predictor_frame

RNG = np.random.default_rng(20260903)


# ---------------------------------------------------------------------------
# 1. ATR20_PCT lookup aligned to engine day frames (T close info)
# ---------------------------------------------------------------------------
def build_atr_lookup(days, D):
    pt = build_predictor_frame()[['ts_code', 'date', 'atr20_pct']]
    pt['date'] = pd.to_datetime(pt['date'])
    g = pt.groupby('date')
    out = {}
    nan_total = 0
    for d in days:
        dd = D[d]
        try:
            sub = g.get_group(d)
        except KeyError:
            out[d] = np.full(len(dd['ts']), np.nan); continue
        m = dict(zip(sub['ts_code'].to_numpy(), sub['atr20_pct'].to_numpy()))
        arr = np.fromiter((m.get(tc, np.nan) for tc in dd['ts']), dtype=float, count=len(dd['ts']))
        nan_total += int(np.isnan(arr).sum())
        out[d] = arr
    return out, nan_total


# ---------------------------------------------------------------------------
# 2. ATR-ranked engine (extension of frozen run_fast_multi_strict_c)
# ---------------------------------------------------------------------------
def run_fast_multi_strict_c_atr(days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
                                K=3, top_n=10, max_levels=5, level_cash=200_000,
                                min_listing_days=60, initial_cash=1_000_000,
                                slippage_bp=10, stamp_tax_mode='historical',
                                exit_bb_mode='dynamic_touch', open_fill='limit_conservative',
                                tick_mode='conservative', limit_slip_order='ref_first',
                                etf_enabled=True, etf_min_cash=5_000,
                                add_gap_days=1, day_range=None, record_actions=False,
                                flow_sink=None,
                                entry_rank_mode='amount_top10', atr_lookup=None,
                                ledger=None, cand_log=None,
                                day_log=None, exec_log=None, forced_first=None):
    """entry_rank_mode: 'amount_top10' (B0 frozen) | 'atr_top10' (B1) | 'atr_all' (B2).
    ledger: list of {sig_date, ts_code, state} for all enumerated oversold candidates.
    cand_log: list of {sig_date, ts_code, amount, amount_rank, atr20_pct} for oversold candidates.
    P3.1 PURELY-ADDITIVE diagnostics (no decision change when None):
      day_log:  per signal-day contention funnel record {date, all_eligible, oversold_all,
                top10_oversold, held_conflicts, pending_conflicts, available_slots,
                queueable_candidates} for the Top10-by-amount universe (B0/B1 semantics).
      exec_log: per pending-buy open attempt {sig_date, ts_code, attempt_date, outcome}
                (EXECUTED / CARRY_LIMITUP / MISSING / DROPPED_K_HELD / NO_LOT / NO_CASH).
      forced_first: {str(sig_date): [ts_code,...]} — reorders that day's candidate priority
                so the listed stocks queue first (used by P3.1 leave-one-swap attribution).
    """
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
    if ledger is None:
        ledger = []
    if cand_log is None:
        cand_log = []

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
                       'hold_days': hold_days, 'sig_date': pos.get('sig_date')})
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

        # ============ OPEN: 执行昨收挂单 ============
        if pending_sell:
            for tc in list(pending_sell):
                pos = find_pos(tc)
                j = dd['pos'].get(tc)
                if pos is None or j is None:
                    pending_sell.discard(tc); continue
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
                    pending_add.pop(tc, None); continue
                if pos['levels'] >= max_levels:
                    pending_add.pop(tc, None); continue
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
                        rec_action(d, j, 'ADD_POSITION', pos['levels'], buy_price, qty, amt, pos['avg_cost'],
                                   i - pos['entry_day_idx'], tc=tc)
                        if flow_sink is not None:
                            flow_sink.append(dict(date=str(d.date()), leg='stock', action='buy',
                                                  gross=amt, fee=fee, net=-(amt + fee), shares=qty, px=buy_price))
                pending_add.pop(tc, None)
        if pending_buy:
            held = {p['ts_code'] for p in positions}
            for pb in list(pending_buy):
                erec = dict(sig_date=pb.get('sig_date'), ts_code=pb['ts_code'],
                            attempt_date=str(d.date())) if exec_log is not None else None
                if len(positions) >= K or pb['ts_code'] in held:
                    if erec is not None:
                        erec['outcome'] = 'DROPPED_K_HELD'
                        exec_log.append(erec)
                    pending_buy = [x for x in pending_buy if x['ts_code'] != pb['ts_code']]
                    continue
                j = dd['pos'].get(pb['ts_code'])
                if j is None:
                    if erec is not None:
                        erec['outcome'] = 'MISSING'
                        exec_log.append(erec)
                    pending_buy = [x for x in pending_buy if x['ts_code'] != pb['ts_code']]
                    continue
                if open_fill == 'limit_conservative' and dd['open_'][j] >= dd['limit_up_px'][j]:
                    if erec is not None:
                        erec['outcome'] = 'CARRY_LIMITUP'
                        exec_log.append(erec)
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
                                'total_cost': amt + fee, 'entry_day_idx': i, 'last_add_i': i,
                                'sig_date': pb.get('sig_date')}
                        positions.append(npos)
                        init_raw_hist(pb['ts_code'], i)
                        rec_action(d, j, 'INITIAL_ENTRY', 1, buy_price, qty, amt, npos['avg_cost'], 0, tc=npos['ts_code'])
                        held.add(pb['ts_code'])
                        if flow_sink is not None:
                            flow_sink.append(dict(date=str(d.date()), leg='stock', action='buy',
                                                  gross=amt, fee=fee, net=-(amt + fee), shares=qty, px=buy_price))
                        if erec is not None:
                            erec['outcome'] = 'EXECUTED'
                            exec_log.append(erec)
                    elif erec is not None:
                        erec['outcome'] = 'NO_CASH'
                        exec_log.append(erec)
                else:
                    if erec is not None:
                        erec['outcome'] = 'NO_LOT'
                        exec_log.append(erec)
                pending_buy = [x for x in pending_buy if x['ts_code'] != pb['ts_code']]

        # ============ 盘中退出: STRICT_C 动态 touch ============
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
                high_adj = dd['high_adj'][j]
                open_adj = dd['open_'][j] * adjT
                if tick_mode == 'conservative':
                    threshold = np.ceil(Pstar_raw / 0.01) * 0.01
                    sell_ref = threshold
                else:
                    threshold = Pstar_raw
                    sell_ref = np.ceil(Pstar_raw / 0.01) * 0.01
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

        # ============ CLOSE ============
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

        # ============ 新买信号 (entry_rank_mode 决定候选优先级) ============
        li = gi - np.array([first_eligible_i.get(tc, 0) for tc in dd['ts']])
        valid = (li >= 0) & ~dd['is_st']
        if valid.any():
            cand_idx = np.where(valid)[0]
            amt = dd['amount'][cand_idx]
            atr = atr_lookup[d][cand_idx] if atr_lookup is not None else np.full(len(cand_idx), np.nan)
            if entry_rank_mode == 'amount_top10':
                order = np.argsort(-amt)[:top_n]
            elif entry_rank_mode == 'atr_top10':
                top_idx = np.argsort(-amt)[:top_n]
                atr_t = np.where(np.isnan(atr[top_idx]), -np.inf, atr[top_idx])
                order = top_idx[np.argsort(-atr_t, kind='stable')]
            elif entry_rank_mode == 'atr_all':
                atr_a = np.where(np.isnan(atr), -np.inf, atr)
                order = np.argsort(-atr_a, kind='stable')
            else:
                raise ValueError(entry_rank_mode)
            amt_rank = np.empty(len(cand_idx), dtype=int)
            amt_rank[np.argsort(-amt)] = np.arange(1, len(cand_idx) + 1)
            # ---- P3.1 forced_first override (additive; reorders candidate priority) ----
            if forced_first is not None and str(d.date()) in forced_first:
                ff = [c for c in forced_first[str(d.date())]]
                kmap = {dd['ts'][cand_idx[int(k)]]: int(k) for k in order}
                ff_k = [kmap[tc] for tc in ff if tc in kmap]
                rest = [k for k in order if int(k) not in ff_k]
                order = np.array(ff_k + list(rest), dtype=int)
            # ---- P3.1 contention funnel (additive; Top10-by-amount universe, B0/B1) ----
            if day_log is not None:
                bb_o = ((~np.isnan(dd['bb_lower'][cand_idx]))
                        & (dd['close_adj'][cand_idx] < dd['bb_lower'][cand_idx])
                        & (~dd['is_limit'][cand_idx]))
                top_amt = np.argsort(-amt)[:top_n]
                top_ov = [int(k) for k in top_amt if bb_o[k]]
                heldset = {p['ts_code'] for p in positions} | pending_sell
                pendset = {x['ts_code'] for x in pending_buy}
                day_log.append(dict(
                    date=str(d.date()),
                    all_eligible=int(len(cand_idx)),
                    oversold_all=int(bb_o.sum()),
                    top10_oversold=len(top_ov),
                    held_conflicts=sum(1 for k in top_ov if dd['ts'][cand_idx[k]] in heldset),
                    pending_conflicts=sum(1 for k in top_ov if dd['ts'][cand_idx[k]] in pendset),
                    available_slots=max(0, K - len(positions) - len(pending_buy)),
                    queueable_candidates=sum(1 for k in top_ov
                                             if (dd['ts'][cand_idx[k]] not in heldset)
                                             and (dd['ts'][cand_idx[k]] not in pendset))))
            held = {p['ts_code'] for p in positions} | pending_sell
            pending_set = {x['ts_code'] for x in pending_buy}
            for k in order:
                j = cand_idx[k]
                tc = dd['ts'][j]
                if (np.isnan(dd['bb_lower'][j]) or not (dd['close_adj'][j] < dd['bb_lower'][j])
                        or dd['is_limit'][j]):
                    continue
                cand_log.append(dict(sig_date=str(d.date()), ts_code=tc, amount=float(dd['amount'][j]),
                                     amount_rank=int(amt_rank[k]),
                                     atr20_pct=float(atr[k]) if np.isfinite(atr[k]) else np.nan))
                if tc in held or tc in pending_set:
                    ledger.append(dict(sig_date=str(d.date()), ts_code=tc, state='BLOCKED_HELD'))
                    continue
                if len(positions) + len(pending_buy) >= K:
                    ledger.append(dict(sig_date=str(d.date()), ts_code=tc, state='BLOCKED_K'))
                    continue
                pending_buy.append({'ts_code': tc, 'name': None, 'layer_cash': level_cash,
                                    'sig_date': str(d.date())})
                ledger.append(dict(sig_date=str(d.date()), ts_code=tc, state='QUEUED'))

        rebalance_close()

        etf_val = etf_sh * epx if not np.isnan(epx) else 0.0
        equity = cash + stock_val + etf_val
        equity_curve.append({'date': str(d.date()), 'equity': equity,
                             'cash': cash, 'stock_val': stock_val, 'etf_sh': etf_sh, 'etf_val': etf_val,
                             'n_pos': len(positions), 'invested': sum(p['total_cost'] for p in positions)})

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
                           'hold_days': hold_days, 'sig_date': pos.get('sig_date')})
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


def analytic_Pstar(x):
    from run_strict_c_math import analytic_Pstar as _f
    return _f(x)


# ---------------------------------------------------------------------------
# 3. Metrics
# ---------------------------------------------------------------------------
def portfolio_metrics(eq, tr, initial_cash=1_000_000):
    eq = eq.copy()
    ret = eq['equity'].pct_change().fillna(0)
    total = eq['equity'].iloc[-1] / initial_cash - 1
    years = len(eq) / 252
    ann = (1 + total) ** (1 / years) - 1 if years > 0 else 0
    ann_vol = ret.std() * np.sqrt(252) if len(ret) > 1 else 0
    peak = eq['equity'].cummax()
    dd = (eq['equity'] - peak) / peak
    mdd = dd.min()
    sharpe = ret.mean() / ret.std() * np.sqrt(252) if ret.std() > 0 else 0
    downside = ret[ret < 0]
    sortino = ret.mean() / downside.std() * np.sqrt(252) if downside.std() > 0 else 0
    calmar = ann / abs(mdd) if mdd < 0 else 0
    util = 1.0 - (eq['cash'] / eq['equity'].clip(lower=1))
    n = len(tr)
    wr = (tr['pnl'] > 0).mean() * 100 if n else 0
    pf = (tr.loc[tr['pnl'] > 0, 'pnl'].sum() / abs(tr.loc[tr['pnl'] <= 0, 'pnl'].sum())) if (tr['pnl'] <= 0).any() else np.inf
    return dict(total=total * 100, ann=ann * 100, ann_vol=ann_vol * 100, mdd=mdd * 100,
                sharpe=sharpe, sortino=sortino, calmar=calmar, n=n, wr=wr, pf=pf,
                cap_util_mean=float(util.mean()), cap_util_med=float(util.median()),
                fully_invested=float((eq['cash'] <= 100).mean()), cash_constrained=float((eq['cash'] < 200_000).mean()))


def yearly_returns(eq, initial_cash=1_000_000):
    eq = eq.copy()
    eq['date'] = pd.to_datetime(eq['date'])
    eq['year'] = eq['date'].dt.year
    rows = []
    prev_eq = initial_cash
    for y, g in eq.groupby('year'):
        ret = g['equity'].iloc[-1] / prev_eq - 1
        rows.append({'year': int(y), 'return_pct': ret * 100})
        prev_eq = g['equity'].iloc[-1]
    return pd.DataFrame(rows)


def ledger_agg(ledger):
    ld = pd.DataFrame(ledger)
    if len(ld) == 0:
        return {}
    c = ld['state'].value_counts().to_dict()
    return dict(total_candidates=len(ld), queued=c.get('QUEUED', 0),
                blocked_held=c.get('BLOCKED_HELD', 0), blocked_k=c.get('BLOCKED_K', 0))


if __name__ == '__main__':
    t0 = pd.Timestamp.now()
    os.makedirs(os.path.join(REPO, 'results'), exist_ok=True)
    os.makedirs(os.path.join(REPO, 'figures'), exist_ok=True)

    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51(
        limit_down_mode='correct', st_mode='pit')
    N2024 = sum(1 for d in days if d <= pd.Timestamp('2024-12-31'))
    print(f'[engine] n_days={len(days)} N2024={N2024} last-dev={days[N2024-1]}', flush=True)

    atr_lookup, nan_total = build_atr_lookup(days, D)
    print(f'[atr] lookup built, nan cells={nan_total}', flush=True)

    # frozen SECONDARY episodes (dev only) for frozen-episode diagnostics
    fm = pd.read_csv(os.path.join(REPO, 'results', 'fullmarket_episode_metrics.csv'))
    fm['signal_date'] = pd.to_datetime(fm['signal_date'])
    fm_dev = fm[fm['signal_date'] <= pd.Timestamp('2024-12-31')].copy()
    fm_lookup = dict(zip(zip(fm['signal_date'], fm['ts_code']), fm['simple_return_pct']))
    print(f'[episodes] dev n={len(fm_dev)}', flush=True)

    # ATR per (sig_date, ts_code) for diagnostics
    pt = build_predictor_frame()[['ts_code', 'date', 'atr20_pct']]
    pt['date'] = pd.to_datetime(pt['date'])
    atr_ep = dict(zip(zip(pt['date'], pt['ts_code']), pt['atr20_pct']))

    CFG = [('B0', 'amount_top10'), ('B1', 'atr_top10'), ('B2', 'atr_all')]
    results = {}
    CACHE = os.path.join(REPO, 'results', '_p3_cache')
    os.makedirs(CACHE, exist_ok=True)

    def engine_run(label, mode, bp):
        cpath = os.path.join(CACHE, f'{label}_bp{bp}.pkl')
        if os.path.exists(cpath):
            with open(cpath, 'rb') as f:
                return pd.read_pickle(f)
        ledger = []
        cand_log = []
        eq, tr, ac = run_fast_multi_strict_c_atr(
            days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
            K=3, top_n=10, max_levels=5, level_cash=200_000, initial_cash=1_000_000,
            slippage_bp=bp, stamp_tax_mode='historical', exit_bb_mode='dynamic_touch',
            open_fill='limit_conservative', tick_mode='conservative', limit_slip_order='ref_first',
            etf_enabled=False, day_range=(0, N2024), record_actions=True,
            entry_rank_mode=mode, atr_lookup=atr_lookup, ledger=ledger, cand_log=cand_log)
        payload = dict(eq=eq, tr=tr, ac=ac, ledger=ledger, cand_log=cand_log)
        with open(cpath, 'wb') as f:
            pd.to_pickle(payload, f)
        return payload

    for label, mode in CFG:
        payload = engine_run(label, mode, 10)
        eq, tr = payload['eq'], payload['tr']
        ledger, cand_log = payload['ledger'], payload['cand_log']
        m = portfolio_metrics(eq, tr)
        yr = yearly_returns(eq)
        stock_pnl = float(tr['pnl'].sum())
        slot_occ = float(eq['n_pos'].sum())
        cap_days = float(eq['invested'].sum())
        lagg = ledger_agg(ledger)
        results[label] = dict(eq=eq, tr=tr, ac=payload['ac'], metrics=m, yearly=yr, ledger=ledger,
                              cand_log=cand_log, stock_pnl=stock_pnl, slot_occ=slot_occ,
                              cap_days=cap_days, ledger_agg=lagg)
        print(f'[PORT {label}] total={m["total"]:.2f}% ann={m["ann"]:.2f}% mdd={m["mdd"]:.2f}% '
              f'sharpe={m["sharpe"]:.3f} n={m["n"]} wr={m["wr"]:.1f}% stock_pnl={stock_pnl:,.0f} '
              f'slot_occ={slot_occ:,.0f} pnl/slot-day={stock_pnl/slot_occ:.3f}', flush=True)

    # ---- B0 parity vs frozen G0 (t3) ----
    g0_ref = dict(total=30.295093786122408, ann=5.65643037176935, mdd=-30.78972881784398,
                  sharpe=0.3467648252149691, n=76, stock_pnl=302950.9378612245)
    eqb = results['B0']['eq']; trb = results['B0']['tr']
    print(f'[PARITY B0] total={results["B0"]["metrics"]["total"]:.4f} (ref {g0_ref["total"]:.4f}) '
          f'ann={results["B0"]["metrics"]["ann"]:.4f} mdd={results["B0"]["metrics"]["mdd"]:.4f} '
          f'sharpe={results["B0"]["metrics"]["sharpe"]:.4f} n={results["B0"]["metrics"]["n"]} '
          f'stock_pnl={results["B0"]["stock_pnl"]:.2f}', flush=True)
    assert abs(results['B0']['metrics']['total'] - g0_ref['total']) < 1e-6, 'B0 total parity FAIL'
    assert results['B0']['metrics']['n'] == g0_ref['n'], 'B0 trade count parity FAIL'
    assert abs(results['B0']['stock_pnl'] - g0_ref['stock_pnl']) < 1.0, 'B0 stock_pnl parity FAIL'
    assert abs(results['B0']['metrics']['mdd'] - g0_ref['mdd']) < 1e-4, 'B0 mdd parity FAIL'
    print('[PARITY B0] OK — matches frozen G0 (t3)', flush=True)

    # ---- save portfolio summary ----
    rows = []
    for label in ('B0', 'B1', 'B2'):
        m = results[label]['metrics']; r = results[label]
        rows.append(dict(version=label, total_return_pct=m['total'], cagr_pct=m['ann'],
                         ann_vol_pct=m['ann_vol'], maxdd_pct=m['mdd'], sharpe=m['sharpe'],
                         sortino=m['sortino'], calmar=m['calmar'], trades=m['n'],
                         win_rate_pct=m['wr'], pf=m['pf'], cap_util_mean=m['cap_util_mean'],
                         cap_util_med=m['cap_util_med'], stock_pnl=r['stock_pnl'],
                         slot_occ_days=r['slot_occ'], pnl_per_slot_day=r['stock_pnl'] / r['slot_occ'],
                         pnl_per_capital_day=r['stock_pnl'] / r['cap_days'],
                         total_candidates=r['ledger_agg'].get('total_candidates', 0),
                         queued=r['ledger_agg'].get('queued', 0),
                         blocked_held=r['ledger_agg'].get('blocked_held', 0),
                         blocked_k=r['ledger_agg'].get('blocked_k', 0)))
    pd.DataFrame(rows).to_csv(os.path.join(REPO, 'results', 'p3_portfolio_summary.csv'), index=False)

    # yearly
    yrows = []
    for label in ('B0', 'B1', 'B2'):
        for _, y in results[label]['yearly'].iterrows():
            yrows.append(dict(version=label, year=int(y['year']), return_pct=y['return_pct']))
    pd.DataFrame(yrows).to_csv(os.path.join(REPO, 'results', 'p3_yearly.csv'), index=False)

    # ---- trade diff (B0 vs B1) ----
    def tr_key(t):
        return (t['ts_code'], str(pd.Timestamp(t['entry_date']).date()))
    b0k = {tr_key(t): t for t in results['B0']['tr'].to_dict('records')}
    b1k = {tr_key(t): t for t in results['B1']['tr'].to_dict('records')}
    b0only = sorted(set(b0k) - set(b1k))
    b1only = sorted(set(b1k) - set(b0k))
    common = sorted(set(b0k) & set(b1k))
    def pnl_of(m, key):
        return m[key]['pnl'] if key in m else np.nan
    diff_rows = []
    for k in b0only:
        t = b0k[k]; diff_rows.append(dict(ts_code=t['ts_code'], entry_date=t['entry_date'],
                                          side='B0_ONLY', pnl=t['pnl'], ret_pct=t['return_pct'],
                                          exit_type=t['exit_type'], levels=t['levels_used']))
    for k in b1only:
        t = b1k[k]; diff_rows.append(dict(ts_code=t['ts_code'], entry_date=t['entry_date'],
                                          side='B1_ONLY', pnl=t['pnl'], ret_pct=t['return_pct'],
                                          exit_type=t['exit_type'], levels=t['levels_used']))
    for k in common:
        r0 = b0k[k]; r1 = b1k[k]
        diff_rows.append(dict(ts_code=r0['ts_code'], entry_date=r0['entry_date'], side='COMMON',
                              pnl_b0=r0['pnl'], pnl_b1=r1['pnl'], pnl_diff=r1['pnl'] - r0['pnl'],
                              ret_b0=r0['return_pct'], ret_b1=r1['return_pct'],
                              levels_b0=r0['levels_used'], levels_b1=r1['levels_used'],
                              exit_b0=r0['exit_type'], exit_b1=r1['exit_type']))
    td = pd.DataFrame(diff_rows)
    td.to_csv(os.path.join(REPO, 'results', 'p3_trade_diff.csv'), index=False)
    print(f'[trade diff B0vsB1] B0_ONLY={len(b0only)} B1_ONLY={len(b1only)} COMMON={len(common)}', flush=True)

    # ---- selection changed events (decision-level, queued-set comparison per signal date) ----
    def queued_by_date(ledger):
        q = {}
        for rec in ledger:
            if rec['state'] == 'QUEUED':
                q.setdefault(rec['sig_date'], []).append(rec['ts_code'])
        return q
    qb0 = queued_by_date(results['B0']['ledger'])
    qb1 = queued_by_date(results['B1']['ledger'])
    sel_rows = []
    for d in sorted(set(qb0) | set(qb1)):
        s0 = qb0.get(d, []); s1 = qb1.get(d, [])
        if set(s0) == set(s1):
            continue
        # replaced pairs: baseline-selected not in ATR, ATR-selected not in baseline
        b0_extra = [x for x in s0 if x not in s1]
        b1_extra = [x for x in s1 if x not in s0]
        atr_vals = {x: atr_ep.get((pd.Timestamp(d), x), np.nan) for x in set(s0) | set(s1)}
        k = max(len(s0), len(s1))
        for i in range(min(len(b0_extra), len(b1_extra))):
            b0s = b0_extra[i]; b1s = b1_extra[i]
            r0 = fm_lookup.get((pd.Timestamp(d), b0s), np.nan)
            r1 = fm_lookup.get((pd.Timestamp(d), b1s), np.nan)
            sel_rows.append(dict(signal_date=d, n_slots=k, baseline_stock=b0s, atr_stock=b1s,
                                 baseline_atr_pct=atr_vals.get(b0s, np.nan), atr_stock_atr_pct=atr_vals.get(b1s, np.nan),
                                 baseline_frozen_ret=r0, atr_frozen_ret=r1,
                                 diff_frozen_ret=r1 - r0 if np.isfinite(r0) and np.isfinite(r1) else np.nan))
    sel_df = pd.DataFrame(sel_rows)
    sel_df.to_csv(os.path.join(REPO, 'results', 'p3_selection_changed_events.csv'), index=False)
    if len(sel_df):
        both = sel_df.dropna(subset=['baseline_frozen_ret', 'atr_frozen_ret'])
        better = float((both['diff_frozen_ret'] > 0).mean()) if len(both) else np.nan
        print(f'[selection changed] events={len(sel_df)} ATR-better fraction={better:.3f} '
              f'mean diff={both["diff_frozen_ret"].mean():.3f}pp' if len(both) else '', flush=True)

    # ---- contested-signal diagnostic (§16) ----
    # use B0's ledger to define contested days: any day with a BLOCKED_K oversold candidate
    ld0 = pd.DataFrame(results['B0']['ledger'])
    cdays = set(ld0[ld0['state'] == 'BLOCKED_K']['sig_date']) if len(ld0) else set()
    # candidates per day (B0 cand_log) + frozen returns
    cl0 = pd.DataFrame(results['B0']['cand_log'])
    if len(cl0):
        cl0['sig_date'] = pd.to_datetime(cl0['sig_date'])
        cl0 = cl0[cl0['sig_date'].isin([pd.Timestamp(x) for x in cdays])].copy()
        cl0['frozen_ret'] = [fm_lookup.get((r['sig_date'], r['ts_code']), np.nan) for _, r in cl0.iterrows()]
        cont_rows = []
        for d, g in cl0.groupby('sig_date'):
            g = g.dropna(subset=['frozen_ret'])
            if len(g) < 2:
                continue
            kfill = len(qb0.get(str(d.date()), []))
            kfill = min(kfill, len(g))
            if kfill < 1:
                continue
            amt_o = g.sort_values('amount', ascending=False)
            atr_o = g.sort_values('atr20_pct', ascending=False, na_position='last')
            base_top = amt_o['frozen_ret'].iloc[:kfill].mean()
            atr_top = atr_o['frozen_ret'].iloc[:kfill].mean()
            # oriented pairwise accuracy: ATR higher -> return higher (POSITIVE direction)
            x = g['atr20_pct'].to_numpy(); y = g['frozen_ret'].to_numpy()
            ok = np.isfinite(x) & np.isfinite(y)
            if ok.sum() >= 5:
                xo, yo = x[ok], y[ok]
                n_pair = 0; agree = 0
                for a in range(len(xo)):
                    for b in range(a + 1, len(xo)):
                        if xo[a] == xo[b] or yo[a] == yo[b]:
                            continue
                        n_pair += 1
                        agree += int((xo[a] - xo[b]) * (yo[a] - yo[b]) > 0)
                pair_acc = agree / n_pair if n_pair else np.nan
            else:
                pair_acc = np.nan
            cont_rows.append(dict(signal_date=str(d.date()), n_candidates=len(g), k_filled=kfill,
                                  baseline_topk_mean=base_top, atr_topk_mean=atr_top,
                                  diff_pp=atr_top - base_top, pairwise_acc=pair_acc))
        cont_df = pd.DataFrame(cont_rows)
        cont_df.to_csv(os.path.join(REPO, 'results', 'p3_contested_signal_diagnostic.csv'), index=False)
        if len(cont_df):
            print(f'[contested] days={len(cont_df)} mean diff(ATR-baseline)={cont_df["diff_pp"].mean():.3f}pp '
                  f'ATR-better frac={float((cont_df["diff_pp"] > 0).mean()):.3f} '
                  f'mean pairwise={cont_df["pairwise_acc"].mean():.3f}', flush=True)
    else:
        cont_df = pd.DataFrame()

    # ---- blocked opportunities (§8) ----
    # from B0 ledger: BLOCKED_K candidates = opportunities blocked by full slots
    blk_rows = []
    for label in ('B0', 'B1', 'B2'):
        ld = pd.DataFrame(results[label]['ledger'])
        r = results[label]
        if len(ld):
            bk = ld[ld['state'] == 'BLOCKED_K'].copy()
            if len(bk):
                bk['sig_date'] = pd.to_datetime(bk['sig_date'])
                bk['frozen_ret'] = [fm_lookup.get((x['sig_date'], x['ts_code']), np.nan) for _, x in bk.iterrows()]
                pos_k = int((bk['frozen_ret'].fillna(0) > 0).sum())
                pos_k_n = int(bk['frozen_ret'].notna().sum())
            else:
                pos_k = 0; pos_k_n = 0
        else:
            pos_k = 0; pos_k_n = 0
        blk_rows.append(dict(version=label,
                             total_candidates=r['ledger_agg'].get('total_candidates', 0),
                             queued=r['ledger_agg'].get('queued', 0),
                             blocked_held=r['ledger_agg'].get('blocked_held', 0),
                             blocked_k=r['ledger_agg'].get('blocked_k', 0),
                             blocked_k_with_frozen=pos_k_n, blocked_k_positive_frozen=pos_k))
    pd.DataFrame(blk_rows).to_csv(os.path.join(REPO, 'results', 'p3_blocked_opportunities.csv'), index=False)

    # ---- capital efficiency (§8) ----
    ce_rows = []
    for label in ('B0', 'B1', 'B2'):
        r = results[label]
        ce_rows.append(dict(version=label, slot_occ_days=r['slot_occ'], cap_days=r['cap_days'],
                            stock_pnl=r['stock_pnl'], pnl_per_slot_day=r['stock_pnl'] / r['slot_occ'],
                            pnl_per_capital_day=r['stock_pnl'] / r['cap_days'],
                            avg_npos=r['slot_occ'] / len(r['eq'])))
    pd.DataFrame(ce_rows).to_csv(os.path.join(REPO, 'results', 'p3_capital_efficiency.csv'), index=False)

    # ---- path divergence top events (§15) ----
    eqb = results['B0']['eq'].copy(); eqb['date'] = pd.to_datetime(eqb['date'])
    eqb1 = results['B1']['eq'].copy(); eqb1['date'] = pd.to_datetime(eqb1['date'])
    mj = eqb[['date', 'equity']].merge(eqb1[['date', 'equity']], on='date', suffixes=('_b0', '_b1'))
    mj['diff'] = mj['equity_b1'] - mj['equity_b0']
    mj['absdiff'] = mj['diff'].abs()
    top20 = mj.nlargest(20, 'absdiff')[['date', 'equity_b0', 'equity_b1', 'diff']].copy()
    top20['date'] = top20['date'].dt.strftime('%Y-%m-%d')
    top20.to_csv(os.path.join(REPO, 'results', 'p3_path_divergence.csv'), index=False)
    print(f'[path divergence] max |B1-B0| = {mj["absdiff"].max():,.0f} on {mj.loc[mj["absdiff"].idxmax(),"date"].date()}', flush=True)

    # ---- liquidity risk (§17) ----
    liq_rows = []
    for label in ('B0', 'B1', 'B2'):
        cl = pd.DataFrame(results[label]['cand_log'])
        # selected = QUEUED candidates (they hold slots)
        ld = pd.DataFrame(results[label]['ledger'])
        queued = set()
        if len(ld):
            queued = set(zip(ld[ld['state'] == 'QUEUED']['sig_date'], ld[ld['state'] == 'QUEUED']['ts_code']))
        if len(cl):
            cl['key'] = list(zip(cl['sig_date'], cl['ts_code']))
            sel = cl[cl['key'].isin(queued)].copy()
        else:
            sel = pd.DataFrame()
        if len(sel):
            liq_rows.append(dict(version=label, n_selected=len(sel),
                                 med_amount=float(sel['amount'].median()),
                                 p10_amount=float(sel['amount'].quantile(0.10)),
                                 p5_amount=float(sel['amount'].quantile(0.05)),
                                 med_rank=float(sel['amount_rank'].median()),
                                 p50_amt_ratio=float((sel['amount'] / 200_000).median()),
                                 p90_amt_ratio=float((sel['amount'] / 200_000).quantile(0.90)),
                                 p95_amt_ratio=float((sel['amount'] / 200_000).quantile(0.95)),
                                 p99_amt_ratio=float((sel['amount'] / 200_000).quantile(0.99))))
        else:
            liq_rows.append(dict(version=label, n_selected=0))
    pd.DataFrame(liq_rows).to_csv(os.path.join(REPO, 'results', 'p3_liquidity_risk.csv'), index=False)
    print('[liquidity] done', flush=True)

    # ---- slippage stress (§18) ----
    slip_cfg = {'B0': [20, 50], 'B1': [20, 50], 'B2': [20, 50, 100]}
    mode_of = {'B0': 'amount_top10', 'B1': 'atr_top10', 'B2': 'atr_all'}
    slip_rows = []
    for label, bp_list in slip_cfg.items():
        for bp in bp_list:
            payload = engine_run(label, mode_of[label], bp)
            eqs, trs = payload['eq'], payload['tr']
            m = portfolio_metrics(eqs, trs)
            slip_rows.append(dict(version=label, slippage_bp=bp, total_return_pct=m['total'],
                                  mdd_pct=m['mdd'], sharpe=m['sharpe'], trades=m['n'],
                                  stock_pnl=float(trs['pnl'].sum())))
    pd.DataFrame(slip_rows).to_csv(os.path.join(REPO, 'results', 'p3_slippage_stress.csv'), index=False)
    print('[slippage stress] done', flush=True)

    print(f'[DONE] {(pd.Timestamp.now()-t0).total_seconds():.0f}s', flush=True)
