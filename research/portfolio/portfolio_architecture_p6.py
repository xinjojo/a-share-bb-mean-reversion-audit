#!/usr/bin/env python3
"""
PHASE P6 - ADD-BUDGET SEPARATION (PORTFOLIO ARCHITECTURE TEST)

Question: can separating NEW-ENTRY capital from ADD capital (preregistered pool
budgets) improve the shared-capital path while preserving averaging-down's positive
contribution? A0 shared pool (exact parity) + A1 600k/400k + A2 800k/200k +
A3 400k/600k NEW/ADD pools. INITIAL_ENTRY from NEW pool only, ADD_POSITION from
ADD pool only, no cross-pool borrowing; sell proceeds return to pools in
proportion to episode historical source share. K=3, max_levels=5, level 200k,
amount Top10, STRICT_C natural exit, ETF OFF, 10bp, 2020-2024 Development only.
PURE DIAGNOSTIC + frozen structural test; no parameter optimization (20/40/60%
are three preregistered probes, no scan). 2025-2026 CLOSED.

Question: which portfolio-architecture component prevents the signal edge from
converting into portfolio performance? K=3 slot limit? multi-layer averaging-down
capital lock? their interaction? or neither?

Frozen structural ablation (no new predictor / ranking / stop / exit / gate / param
search / ML):
  A0 BASELINE          : K=3,  max_levels=5   (must parity P3 B0 exactly)
  A1 SLOT-RELAXED      : K=999, max_levels=5  (slot limit lifted; capital still 1M/200k)
  A2 NO-ADD            : K=3,  max_levels=1   (no averaging-down multi-layer)
  A3 SLOT-RELAXED+NOADD: K=999, max_levels=1
All four use the frozen amount-Top10 candidate priority (ranking excluded this phase).
PURE STOCK 2020-2024 Development; 2025-2026 Confirmation CLOSED.
Engine = run_fast_multi_strict_c_atr copied line-for-line from P3 (amount_top10 path).

Preregistered BEFORE any outcome run:
  research/portfolio/registries/PORTFOLIO_ARCHITECTURE_P4_REGISTRY.csv
  SHA256 = 5f30974cd45a2849a9f0bf1c3252f2a14ad1ea236c26a4f2f16a5f65f8ee6545
  commit 70588a71ea6deeaaa60a8af9a4e2e7c4374c7ba3 (P4-A, pushed)
"""
import os, sys, json
import numpy as np, pandas as pd
from collections import deque

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
OUT = os.path.join(REPO, 'results', 'evidence', 'p6')
os.makedirs(OUT, exist_ok=True)
ROOT2 = ROOT
sys.path.insert(0, ROOT)
from round51_audit import prepare_v51, stamp_rate, COMMISSION_RATE, MIN_COMMISSION, TRANSFER_FEE_RATE
from run_strict_c_math import analytic_Pstar

RNG = np.random.default_rng(20260903)

def run_p6_engine(days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
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
                                day_log=None, exec_log=None, forced_first=None,
                                pool_split=None, pool_ledger=None, budget_counters=None):
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
    new_pool = 0.0
    add_pool = 0.0
    new_deployed = 0.0
    add_deployed = 0.0
    if pool_split is not None:
        new_pool = initial_cash * pool_split[0]
        add_pool = initial_cash * pool_split[1]
        cash = new_pool + add_pool
        if budget_counters is None:
            budget_counters = {}
        budget_counters.setdefault('no_new_budget', 0)
        budget_counters.setdefault('no_add_budget', 0)
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
        nonlocal cash, round_no, new_pool, add_pool
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
        if pool_split is None:
            cash += proceeds
        else:
            tc_ = pos['total_cost']
            nsh = (pos.get('new_cost', 0.0) / tc_) if tc_ > 0 else 1.0
            new_pool += proceeds * nsh
            add_pool += proceeds * (1.0 - nsh)
            cash = new_pool + add_pool
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
                if pool_split is None:
                    qty = int(min(level_cash, cash) / buy_price / 100) * 100
                    avail = cash
                else:
                    qty = int(min(level_cash, add_pool) / buy_price / 100) * 100
                    avail = add_pool
                if qty >= 100:
                    amt = buy_price * qty
                    fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * TRANSFER_FEE_RATE
                    if amt + fee <= avail:
                        if pool_split is None:
                            cash -= amt + fee
                        else:
                            add_pool -= amt + fee
                            cash = new_pool + add_pool
                            pos['add_cost'] = pos.get('add_cost', 0.0) + amt + fee
                            add_deployed += amt + fee
                        old_cost = pos['shares'] * pos['avg_cost']
                        pos['shares'] += qty
                        pos['avg_cost'] = (old_cost + amt + fee) / pos['shares']
                        pos['total_cost'] += amt + fee
                        pos['levels'] += 1
                        pos['last_add_i'] = i
                        pos['last_add_i'] = i
                        rec_action(d, j, 'ADD_POSITION', pos['levels'], buy_price, qty, amt, pos['avg_cost'],
                                   i - pos['entry_day_idx'], tc=tc)
                        if flow_sink is not None:
                            flow_sink.append(dict(date=str(d.date()), leg='stock', action='buy',
                                                  gross=amt, fee=fee, net=-(amt + fee), shares=qty, px=buy_price))
                    elif pool_split is not None:
                        budget_counters['no_add_budget'] += 1
                elif pool_split is not None:
                    budget_counters['no_add_budget'] += 1
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
                if pool_split is None:
                    qty = int(min(level_cash, cash) / buy_price / 100) * 100
                    avail = cash
                else:
                    qty = int(min(level_cash, new_pool) / buy_price / 100) * 100
                    avail = new_pool
                if qty >= 100:
                    amt = buy_price * qty
                    fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * TRANSFER_FEE_RATE
                    if amt + fee <= avail:
                        if pool_split is None:
                            cash -= amt + fee
                        else:
                            new_pool -= amt + fee
                            cash = new_pool + add_pool
                            new_deployed += amt + fee
                        npos = {'ts_code': pb['ts_code'], 'name': None,
                                'shares': qty, 'avg_cost': (amt + fee) / qty,
                                'l1_cost': (amt + fee) / qty,
                                'entry_date': str(d.date()), 'levels': 1,
                                'total_cost': amt + fee, 'entry_day_idx': i, 'last_add_i': i,
                                'sig_date': pb.get('sig_date')}
                        if pool_split is not None:
                            npos['new_cost'] = amt + fee
                            npos['add_cost'] = 0.0
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
                        if pool_split is None:
                            erec['outcome'] = 'NO_CASH'
                        else:
                            erec['outcome'] = 'NO_NEW_BUDGET'
                            budget_counters['no_new_budget'] += 1
                        exec_log.append(erec)
                else:
                    if erec is not None:
                        if pool_split is None:
                            erec['outcome'] = 'NO_LOT'
                        else:
                            erec['outcome'] = 'NO_NEW_BUDGET'
                            budget_counters['no_new_budget'] += 1
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
        if pool_ledger is not None:
            pool_ledger.append(dict(date=str(d.date()), new_pool=new_pool, add_pool=add_pool,
                                    new_deployed=new_deployed, add_deployed=add_deployed))

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
            if pool_split is None:
                cash += proceeds
            else:
                tc_ = pos['total_cost']
                nsh = (pos.get('new_cost', 0.0) / tc_) if tc_ > 0 else 1.0
                new_pool += proceeds * nsh
                add_pool += proceeds * (1.0 - nsh)
                cash = new_pool + add_pool
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

# ---------------------------------------------------------------------------
# portfolio metrics (identical to P3)
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


def exec_agg(exec_log):
    if not exec_log:
        return {}
    import collections
    c = collections.Counter(e['outcome'] for e in exec_log)
    return dict(c)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

# ===========================================================================
# P6 main
# ===========================================================================
if __name__ == '__main__':
    import hashlib, collections
    # registry integrity (I12)
    reg_path = os.path.join(REPO, 'research', 'portfolio', 'registries', 'PORTFOLIO_ARCHITECTURE_P6_ADD_BUDGET_REGISTRY.csv')
    with open(reg_path, 'rb') as f:
        reg_sha = hashlib.sha256(f.read()).hexdigest()
    assert reg_sha == '907df83d145b4e6918aa94c721c0da7ef34ab57be963c002687a88e1b62f1e51', 'P6 registry SHA mismatch'
    prior = {
     'F1': ('FAILURE_STATE_F1_REGISTRY.csv', 'a052309e6f939796795566d1cd1094e2ec706f53250c231377c64efb315eef14'),
     'F1.1': ('FAILURE_STATE_F11_INFERENCE_REGISTRY.csv', 'aacb2146308abd155401c1231209b7cab14e1bc44c50e6f19007ac39582aef91'),
     'F2': ('FAILURE_STATE_F2_ACTIONABILITY_REGISTRY.csv', '9ed07a575ae65bbda3d63321e676431231d00548bb8977fb443764163b85642a'),
     'F2.1': ('FAILURE_STATE_F21_MATCHED_ACTION_REGISTRY.csv', '12f8311c52df76ca6fc10cb7f5f43a95bae4e1c9a9dc1f5880bfdcee60357787'),
     'F2.2': ('FAILURE_STATE_F22_BREAK_EVEN_REGISTRY.csv', 'aff9c4295fceec450a54ea7bc2bfbc8055761d396081d778d4e1ff616b6095d8'),
     'F2.3': ('FAILURE_STATE_F23_POLICY_VALUE_INFERENCE_REGISTRY.csv', 'c0f4d1d2bd46a7c5bca01752020dec121404984feb8273984a5164f56942f83c'),
     'F3': ('FAILURE_STATE_F3_PREDICTOR_REGISTRY.csv', '803e15245746a90d542de1bd18889686dacf6e926b3ac931717c68335db2a032'),
     'P5': ('PORTFOLIO_ARCHITECTURE_P5_REGISTRY.csv', '7415608a1003b612704e295a76427eba5c124607163a926fb514342c699f7ce7'),
     'P5.1': ('PORTFOLIO_ARCHITECTURE_P51_QUEUE_ELIGIBILITY_REGISTRY.csv', '7de0874eba6fe49c370060851b1a3bbd13e9f65498a83c0a9b1dcf1376838ec6'),
    }
    for name, (fn, sha) in prior.items():
        pth = os.path.join(REPO, 'research', 'portfolio', 'registries', fn)
        if not os.path.exists(pth):
            pth = os.path.join(REPO, 'research', 'risk', 'registries', fn)
        assert os.path.exists(pth), f'{name} registry not found'
        with open(pth, 'rb') as f:
            assert hashlib.sha256(f.read()).hexdigest() == sha, f'{name} registry SHA changed (I12)'

    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51(
        limit_down_mode='correct', st_mode='pit')
    N2024 = sum(1 for d in days if d <= pd.Timestamp('2024-12-31'))
    assert N2024 == 1212 and all(d.year <= 2024 for d in days[:N2024]), 'I11'

    ARCHES = {'A0': None, 'A1': (0.6, 0.4), 'A2': (0.8, 0.2), 'A3': (0.4, 0.6)}
    res = {}
    for lbl, split in ARCHES.items():
        ledger, cand_log, day_log, exec_log = [], [], [], []
        pool_ledger = [] if split is not None else None
        bcount = {} if split is not None else None
        eq, tr, ac = run_p6_engine(
            days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
            K=3, top_n=10, max_levels=5, level_cash=200_000, initial_cash=1_000_000,
            slippage_bp=10, stamp_tax_mode='historical', exit_bb_mode='dynamic_touch',
            open_fill='limit_conservative', tick_mode='conservative', limit_slip_order='ref_first',
            etf_enabled=False, day_range=(0, N2024), record_actions=True,
            entry_rank_mode='amount_top10', atr_lookup=None, ledger=ledger, cand_log=cand_log,
            day_log=day_log, exec_log=exec_log, pool_split=split, pool_ledger=pool_ledger,
            budget_counters=bcount)
        m = portfolio_metrics(eq, tr)
        stock_pnl = float(tr['pnl'].sum())
        yearly = yearly_returns(eq)
        # yearly extras: maxdd per year, pnl by exit year, entries by entry year, adds by action year
        eqc = eq.copy(); eqc['date'] = pd.to_datetime(eqc['date']); eqc['year'] = eqc['date'].dt.year
        yrows = []
        prev_eq = 1_000_000.0
        for y in range(2020, 2025):
            g = eqc[eqc['year'] == y]
            if len(g) == 0:
                continue
            ret = g['equity'].iloc[-1] / prev_eq - 1
            peak = g['equity'].cummax(); mdd_y = float(((g['equity'] - peak) / peak).min() * 100)
            prev_eq = g['equity'].iloc[-1]
            trc = tr.copy(); trc['exit_date'] = pd.to_datetime(trc['exit_date']); trc['ey'] = trc['exit_date'].dt.year
            trc['entry_date'] = pd.to_datetime(trc['entry_date']); trc['ny'] = trc['entry_date'].dt.year
            pnl_y = float(trc.loc[trc['ey'] == y, 'pnl'].sum())
            ent_y = int((trc['ny'] == y).sum())
            if len(ac):
                acc = ac.copy(); acc['date'] = pd.to_datetime(acc['date']); acc['ay'] = acc['date'].dt.year
                adds_y = int(((acc['action'] == 'ADD_POSITION') & (acc['ay'] == y)).sum())
            else:
                adds_y = 0
            yrows.append(dict(year=y, return_pct=ret * 100, maxdd_pct=mdd_y, stock_pnl=pnl_y,
                              new_entries=ent_y, adds=adds_y))
        yr = pd.DataFrame(yrows)
        # blocked_K from ledger
        lagg = collections.Counter(x['state'] for x in ledger)
        res[lbl] = dict(eq=eq, tr=tr, ac=ac, metrics=m, yearly=yr, stock_pnl=stock_pnl,
                        ledger=ledger, cand_log=cand_log, exec_log=exec_log,
                        pool_ledger=pool_ledger, budget=bcount,
                        blocked_k=lagg.get('BLOCKED_K', 0),
                        cash_idle_pct=float((1.0 - eq['cash'] / eq['equity'].clip(lower=1)).mean() * 100),
                        median_hold=float(tr['hold_days'].median()) if len(tr) else np.nan,
                        avg_layers=float(tr['levels_used'].mean()) if len(tr) else np.nan)
        print(f'[P6 {lbl}] total={m["total"]:.4f}% mdd={m["mdd"]:.4f}% sharpe={m["sharpe"]:.4f} '
              f'n={m["n"]} pnl={stock_pnl:,.2f} blockK={res[lbl]["blocked_k"]}', flush=True)

    # ---- A0 parity (I1) ----
    a0 = res['A0']
    assert abs(a0['metrics']['total'] - 30.295093786122408) < 1e-6, 'A0 total parity FAIL'
    assert a0['metrics']['n'] == 76, 'A0 n parity FAIL'
    assert abs(a0['stock_pnl'] - 302950.9378612245) < 1.0, 'A0 pnl parity FAIL'
    assert abs(a0['metrics']['mdd'] - (-30.78972881784398)) < 1e-4, 'A0 mdd parity FAIL'
    assert abs(a0['metrics']['sharpe'] - 0.3467648252149691) < 1e-6, 'A0 sharpe parity FAIL'
    print('[P6] A0 parity PASS (total/n/pnl/mdd/sharpe)', flush=True)

    # ---- metrics csv ----
    mrows = []
    for lbl in ['A0', 'A1', 'A2', 'A3']:
        r = res[lbl]; m = r['metrics']
        mrows.append(dict(arch=lbl, total_return=m['total'], cagr=m['ann'], maxdd=m['mdd'], sharpe=m['sharpe'],
                          stock_pnl=r['stock_pnl'], n_episodes=m['n'], n_initial=len(r['tr']),
                          n_adds=int((r['ac']['action'] == 'ADD_POSITION').sum()) if len(r['ac']) else 0,
                          avg_layers=r['avg_layers'], blocked_k=r['blocked_k'],
                          cash_idle_pct=r['cash_idle_pct'], median_hold=r['median_hold'],
                          no_new_budget=(r['budget'] or {}).get('no_new_budget', 0),
                          no_add_budget=(r['budget'] or {}).get('no_add_budget', 0)))
        if r['pool_ledger'] is not None:
            pl = pd.DataFrame(r['pool_ledger'])
            mrows[-1]['new_pool_util_pct'] = float(pl['new_deployed'].iloc[-1] / 600000 * 100) if lbl != 'A2' else float(pl['new_deployed'].iloc[-1] / 800000 * 100)
            mrows[-1]['add_pool_util_pct'] = float(pl['add_deployed'].iloc[-1] / 400000 * 100) if lbl != 'A2' else float(pl['add_deployed'].iloc[-1] / 200000 * 100)
    pd.DataFrame(mrows).to_csv(os.path.join(OUT, 'p6_metrics.csv'), index=False)

    # ---- yearly ----
    yall = []
    for lbl in ['A0', 'A1', 'A2', 'A3']:
        y = res[lbl]['yearly'].copy(); y['arch'] = lbl
        yall.append(y)
    pd.concat(yall).to_csv(os.path.join(OUT, 'p6_yearly.csv'), index=False)

    # ---- pool ledger (A1) ----
    pd.DataFrame(res['A1']['pool_ledger']).to_csv(os.path.join(OUT, 'p6_pool_ledger.csv'), index=False)

    # ---- signal bridge (sig_date, ts_code) ----
    def sig_keys(r):
        t = r['tr'].copy(); t['sig_date'] = pd.to_datetime(t['sig_date'])
        return set(zip(t['sig_date'], t['ts_code']))
    a0k, a1k = sig_keys(res['A0']), sig_keys(res['A1'])
    sb = [dict(group='COMMON', n=len(a0k & a1k)), dict(group='A0_ONLY', n=len(a0k - a1k)),
          dict(group='A1_ONLY', n=len(a1k - a0k)),
          dict(group='A1_NO_NEW_BUDGET', n=(res['A1']['budget'] or {}).get('no_new_budget', 0))]
    pd.DataFrame(sb).to_csv(os.path.join(OUT, 'p6_signal_bridge.csv'), index=False)

    # ---- add bridge (ts_code, entry_date, level); entry_date back-solved via hold_days ----
    def add_keys(r):
        if not len(r['ac']):
            return set()
        a = r['ac'].copy(); a = a[a['action'] == 'ADD_POSITION']
        keys = set()
        for _, row in a.iterrows():
            hd = int(row['hold_days'])
            i_add = days.index(pd.Timestamp(row['date']))
            i_ent = i_add - hd
            ent_d = str(days[i_ent].date())
            keys.add((row['ts_code'], ent_d, int(row['level'])))
        return keys
    ab_rows = []
    for lbl in ['A1', 'A2', 'A3']:
        axk = add_keys(res[lbl]); a0k2 = add_keys(res['A0'])
        for lv in [2, 3, 4, 5]:
            a0_lv = {k for k in a0k2 if k[2] == lv}
            ax_lv = {k for k in axk if k[2] == lv}
            ab_rows.append(dict(arch=lbl, layer=lv, a0_adds=len(a0_lv), ax_adds=len(ax_lv),
                                preserved=len(a0_lv & ax_lv), lost=len(a0_lv - ax_lv)))
    pd.DataFrame(ab_rows).to_csv(os.path.join(OUT, 'p6_add_bridge.csv'), index=False)

    # ---- path bridge A0 vs A1 ----
    def tr_map(r):
        t = r['tr'].copy(); t['entry_date'] = pd.to_datetime(t['entry_date'])
        return {k: row for k, row in zip(zip(t['ts_code'], t['entry_date']), t.to_dict('records'))}
    m0, m1 = tr_map(res['A0']), tr_map(res['A1'])
    common = set(m0) & set(m1)
    common_delta = sum(m1[k]['pnl'] - m0[k]['pnl'] for k in common)
    a0_only_pnl = sum(m0[k]['pnl'] for k in set(m0) - set(m1))
    a1_only_pnl = sum(m1[k]['pnl'] for k in set(m1) - set(m0))
    # fees estimate: buy legs from actions + sell legs from exit actions
    def est_fees(r):
        fee = 0.0
        ac_ = r['ac']
        if len(ac_):
            buys = ac_[ac_['action'].isin(['INITIAL_ENTRY', 'ADD_POSITION'])]
            for _, row in buys.iterrows():
                amt = float(row['amount'])
                fee += max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * TRANSFER_FEE_RATE
            sells = ac_[ac_['action'].isin(['TAKE_PROFIT_DYN', 'TAKE_PROFIT_UB', 'FINAL_SETTLE'])]
            for _, row in sells.iterrows():
                g = float(row['price']) * float(row['shares'])
                d_ = pd.Timestamp(row['date'])
                fee += max(g * COMMISSION_RATE, MIN_COMMISSION) + g * stamp_rate(d_, 'historical') + g * TRANSFER_FEE_RATE
        # FINAL_SETTLE not in actions -> gross from pnl + total_cost
        t = r['tr'].copy(); fs = t[t['exit_type'] == 'FINAL_SETTLE']
        for _, row in fs.iterrows():
            rp = float(row['return_pct']) / 100.0
            if rp == 0:
                continue
            tc_ = float(row['pnl']) / rp  # total_cost back-solved from rounded return_pct
            g = float(row['pnl']) + tc_
            d_ = pd.Timestamp(row['exit_date'])
            fee += max(g * COMMISSION_RATE, MIN_COMMISSION) + g * stamp_rate(d_, 'historical') + g * TRANSFER_FEE_RATE
        return fee
    fee0, fee1 = est_fees(res['A0']), est_fees(res['A1'])
    idle0 = float(res['A0']['eq']['cash'].mean())
    idle1 = float(res['A1']['eq']['cash'].mean())
    pb = dict(common_n=len(common), common_pnl_delta=common_delta, a0_only_pnl=a0_only_pnl,
              a1_only_pnl=a1_only_pnl, fees_a0=fee0, fees_a1=fee1, fees_delta=fee1 - fee0,
              idle_cash_a0=idle0, idle_cash_a1=idle1, idle_cash_delta=idle1 - idle0,
              mechanism_note='COMMON delta reflects path/capital differences on same signals; '
                             'A1_ONLY reflects newly admitted signals; A0_ONLY reflects signals lost; '
                             'idle delta reflects NEW-pool cash sitting uninvested')
    json.dump(pb, open(os.path.join(OUT, 'p6_path_bridge.json'), 'w'), indent=2, default=float)

    # ---- episode concentration (A1 vs A0) ----
    inc = res['A1']['stock_pnl'] - res['A0']['stock_pnl']
    contribs = []
    for k in common:
        contribs.append(('COMMON', m1[k]['pnl'] - m0[k]['pnl']))
    for k in (set(m1) - set(m0)):
        contribs.append(('A1_ONLY', m1[k]['pnl']))
    for k in (set(m0) - set(m1)):
        contribs.append(('A0_ONLY', -m0[k]['pnl']))
    top = max(contribs, key=lambda x: abs(x[1]))
    top_pct = abs(top[1]) / abs(inc) * 100 if inc != 0 else np.nan
    ec = dict(incremental_pnl=inc, top_contribution_group=top[0], top_contribution_pnl=top[1],
              top_contribution_pct=top_pct)
    json.dump(ec, open(os.path.join(OUT, 'p6_episode_concentration.json'), 'w'), indent=2, default=float)

    # ---- classification (primary A1) ----
    A0, A1 = res['A0'], res['A1']
    m_a0, m_a1 = A0['metrics'], A1['metrics']
    y0 = A0['yearly'].set_index('year')['stock_pnl']; y1 = A1['yearly'].set_index('year')['stock_pnl']
    better_years = sum(1 for y in range(2020, 2025) if y1.get(y, -1e18) > y0.get(y, 1e18))
    both23_24_worse = (y1.get(2023, -1e18) < y0.get(2023, 1e18)) and (y1.get(2024, -1e18) < y0.get(2024, 1e18))
    mdd_worse_pp = m_a1['mdd'] - m_a0['mdd']  # negative = worse
    total_up = m_a1['total'] > m_a0['total']
    sharpe_up = m_a1['sharpe'] > m_a0['sharpe']
    conc_ok = (not np.isnan(top_pct)) and top_pct <= 50.0
    cls = None
    if total_up and mdd_worse_pp > -3 and sharpe_up and better_years >= 3 and (not both23_24_worse) and conc_ok:
        cls = 'A'
    elif total_up and mdd_worse_pp > -5 and better_years >= 3:
        cls = 'B'
    elif total_up and (mdd_worse_pp <= -5 or not sharpe_up) and better_years < 3:
        cls = 'D'
    elif not total_up and (not sharpe_up or mdd_worse_pp <= -5):
        cls = 'D'
    else:
        cls = 'C'
    # sensitivity A2/A3
    sens = {}
    for lbl in ['A2', 'A3']:
        mx = res[lbl]['metrics']
        sens[lbl] = dict(total=mx['total'], mdd=mx['mdd'], sharpe=mx['sharpe'],
                         n=mx['n'], pnl=res[lbl]['stock_pnl'])
    summary = dict(a0=dict(total=m_a0['total'], mdd=m_a0['mdd'], sharpe=m_a0['sharpe'], n=m_a0['n'], pnl=A0['stock_pnl']),
                   a1=dict(total=m_a1['total'], mdd=m_a1['mdd'], sharpe=m_a1['sharpe'], n=m_a1['n'], pnl=A1['stock_pnl'],
                           no_new_budget=(A1['budget'] or {}).get('no_new_budget', 0),
                           no_add_budget=(A1['budget'] or {}).get('no_add_budget', 0)),
                   deltas=dict(return_pp=m_a1['total'] - m_a0['total'], mdd_pp=mdd_worse_pp,
                               sharpe=m_a1['sharpe'] - m_a0['sharpe']),
                   yearly_better_years=better_years, both_23_24_worse=bool(both23_24_worse),
                   top_episode_contribution_pct=top_pct, signal_bridge=sb, add_bridge=ab_rows,
                   path_bridge=pb, sensitivity=sens, classification=cls, registry_sha=reg_sha)
    json.dump(summary, open(os.path.join(OUT, 'p6_summary.json'), 'w'), indent=2, ensure_ascii=False, default=float)
    inv = dict(I1_a0_parity=True, I2_k3=True, I3_maxlevels5=True, I4_level200k=True, I5_entry_unchanged=True,
               I6_exit_unchanged=True, I7_ranking_unchanged=True, I8_no_predictor=True, I9_no_queue=True,
               I10_no_stop_gate=True, I11_no_2025_read=True, I12_prior_registry_shas=True, registry_sha=reg_sha)
    json.dump(inv, open(os.path.join(OUT, 'p6_invariants.json'), 'w'), indent=2)
    print('[P6] A1 delta pp=%.4f mdd_pp=%.4f sharpe_delta=%.4f better_years=%d both23_24_worse=%s top_contrib=%s' % (
        m_a1['total'] - m_a0['total'], mdd_worse_pp, m_a1['sharpe'] - m_a0['sharpe'], better_years,
        both23_24_worse, f'{top_pct:.1f}%'), flush=True)
    print('[P6] classification =', cls, flush=True)
    print('[P6] DONE', flush=True)
