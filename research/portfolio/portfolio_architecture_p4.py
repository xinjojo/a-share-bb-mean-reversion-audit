#!/usr/bin/env python3
"""
PHASE P4 - PORTFOLIO ARCHITECTURE CAUSAL DECOMPOSITION (STRUCTURAL ABLATION ONLY)

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
OUT = os.path.join(REPO, 'results', 'evidence', 'p4')
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, ROOT)
from round51_audit import prepare_v51, stamp_rate, COMMISSION_RATE, MIN_COMMISSION, TRANSFER_FEE_RATE
from run_strict_c_math import analytic_Pstar

RNG = np.random.default_rng(20260903)

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
if __name__ == '__main__':
    t0 = pd.Timestamp.now()
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51(
        limit_down_mode='correct', st_mode='pit')
    N2024 = sum(1 for d in days if d <= pd.Timestamp('2024-12-31'))
    print(f'[engine] n_days={len(days)} N2024={N2024} last-dev={days[N2024-1]}', flush=True)

    atr_lookup = None  # amount_top10 path does not need ATR; engine handles None

    # frozen SECONDARY episodes (dev only) for blocked-candidate outcome coverage
    fm = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'fullmarket', 'fullmarket_episode_metrics.csv'))
    fm['signal_date'] = pd.to_datetime(fm['signal_date'])
    fm_dev = fm[fm['signal_date'] <= pd.Timestamp('2024-12-31')].copy()
    fm_lookup = dict(zip(zip(fm['signal_date'], fm['ts_code']), fm['simple_return_pct']))
    print(f'[episodes] dev n={len(fm_dev)}', flush=True)

    CFG = [('A0', 3, 5), ('A1', 999, 5), ('A2', 3, 1), ('A3', 999, 1)]
    results = {}
    for label, K, ML in CFG:
        ledger = []
        cand_log = []
        day_log = []
        exec_log = []
        eq, tr, ac = run_fast_multi_strict_c_atr(
            days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
            K=K, top_n=10, max_levels=ML, level_cash=200_000, initial_cash=1_000_000,
            slippage_bp=10, stamp_tax_mode='historical', exit_bb_mode='dynamic_touch',
            open_fill='limit_conservative', tick_mode='conservative', limit_slip_order='ref_first',
            etf_enabled=False, day_range=(0, N2024), record_actions=True,
            entry_rank_mode='amount_top10', atr_lookup=atr_lookup, ledger=ledger, cand_log=cand_log,
            day_log=day_log, exec_log=exec_log)
        m = portfolio_metrics(eq, tr)
        yr = yearly_returns(eq)
        stock_pnl = float(tr['pnl'].sum())
        slot_occ = float(eq['n_pos'].sum())
        cap_days = float(eq['invested'].sum())
        avg_npos = float(eq['n_pos'].mean())
        p_full = float((eq['n_pos'] >= K).mean()) if K < 100 else float((eq['invested'] >= 800000).mean())
        avg_layers = float(tr['levels_used'].mean()) if len(tr) else 0
        p_l2 = float((tr['levels_used'] >= 2).mean() * 100) if len(tr) else 0
        p_l4 = float((tr['levels_used'] >= 4).mean() * 100) if len(tr) else 0
        p_l5 = float((tr['levels_used'] == 5).mean() * 100) if len(tr) else 0
        lagg = ledger_agg(ledger)
        eagg = exec_agg(exec_log)
        results[label] = dict(eq=eq, tr=tr, ac=ac, metrics=m, yearly=yr, ledger=ledger,
                              cand_log=cand_log, day_log=day_log, exec_log=exec_log,
                              stock_pnl=stock_pnl, slot_occ=slot_occ, cap_days=cap_days,
                              avg_npos=avg_npos, p_full=p_full, avg_layers=avg_layers,
                              p_l2=p_l2, p_l4=p_l4, p_l5=p_l5, ledger_agg=lagg, exec_agg=eagg)
        print(f'[PORT {label}] K={K} ML={ML} total={m["total"]:.2f}% ann={m["ann"]:.2f}% mdd={m["mdd"]:.2f}% '
              f'sharpe={m["sharpe"]:.3f} n={m["n"]} wr={m["wr"]:.1f}% stock_pnl={stock_pnl:,.0f} '
              f'avg_npos={avg_npos:.3f} avg_layers={avg_layers:.3f}', flush=True)

    # ---- A0 parity vs frozen P3 B0 / G0 (t3) ----
    g0_ref = dict(total=30.295093786122408, ann=5.65643037176935, mdd=-30.78972881784398,
                  sharpe=0.3467648252149691, n=76, stock_pnl=302950.9378612245)
    eqb = results['A0']['eq']; trb = results['A0']['tr']
    a0 = results['A0']
    print(f'[PARITY A0] total={a0["metrics"]["total"]:.4f} (ref {g0_ref["total"]:.4f}) '
          f'ann={a0["metrics"]["ann"]:.4f} mdd={a0["metrics"]["mdd"]:.4f} '
          f'sharpe={a0["metrics"]["sharpe"]:.4f} n={a0["metrics"]["n"]} '
          f'stock_pnl={a0["stock_pnl"]:.2f}', flush=True)
    assert abs(a0['metrics']['total'] - g0_ref['total']) < 1e-6, 'A0 total parity FAIL'
    assert a0['metrics']['n'] == g0_ref['n'], 'A0 trade count parity FAIL'
    assert abs(a0['stock_pnl'] - g0_ref['stock_pnl']) < 1.0, 'A0 stock_pnl parity FAIL'
    assert abs(a0['metrics']['mdd'] - g0_ref['mdd']) < 1e-4, 'A0 mdd parity FAIL'
    print('[PARITY A0] OK -- matches frozen P3 B0 / G0 (t3)', flush=True)

    # ===== save results =====
    # 1) p4_portfolio_summary.csv
    rows = []
    for label in ('A0', 'A1', 'A2', 'A3'):
        m = results[label]['metrics']; r = results[label]
        rows.append(dict(arch=label, K=dict(A0=3,A1=999,A2=3,A3=999)[label],
                         max_levels=dict(A0=5,A1=5,A2=1,A3=1)[label],
                         total_return_pct=m['total'], cagr_pct=m['ann'],
                         ann_vol_pct=m['ann_vol'], maxdd_pct=m['mdd'], sharpe=m['sharpe'],
                         sortino=m['sortino'], calmar=m['calmar'], trades=m['n'],
                         win_rate_pct=m['wr'], pf=m['pf'], median_trade_ret_pct=float(r['tr']['pnl_pct'].median()) if 'pnl_pct' in r['tr'] else float((r['tr']['pnl']/200000*100).median()),
                         stock_pnl=r['stock_pnl'],
                         hold_median_days=float(r['tr']['hold_days'].median()) if 'hold_days' in r['tr'] else None,
                         hold_mean_days=float(r['tr']['hold_days'].mean()) if 'hold_days' in r['tr'] else None,
                         avg_npos=r['avg_npos'], p_full_pct=r['p_full']*100,
                         avg_layers=r['avg_layers'], p_levels2_pct=r['p_l2'],
                         p_levels4_pct=r['p_l4'], p_levels5_pct=r['p_l5'],
                         slot_days=r['slot_occ'], capital_days=r['cap_days'],
                         pnl_per_slot_day=r['stock_pnl']/r['slot_occ'] if r['slot_occ'] else 0,
                         pnl_per_capital_day=r['stock_pnl']/r['cap_days'] if r['cap_days'] else 0,
                         cash_idle_pct=(1-m['cap_util_mean'])*100, invested_pct=m['cap_util_mean']*100,
                         cap_util_med_pct=m['cap_util_med']*100,
                         fully_invested_pct=m['fully_invested']*100,
                         cash_constrained_pct=m['cash_constrained']*100))
    pd.DataFrame(rows).to_csv(os.path.join(OUT, 'p4_portfolio_summary.csv'), index=False)

    # 2) p4_yearly.csv
    yr_rows = []
    for label in ('A0','A1','A2','A3'):
        for _, r in results[label]['yearly'].iterrows():
            yr_rows.append(dict(arch=label, year=int(r['year']), return_pct=r['return_pct']))
    pd.DataFrame(yr_rows).to_csv(os.path.join(OUT, 'p4_yearly.csv'), index=False)

    # 3) p4_signal_capture.csv + block_reason
    cap_rows = []
    for label in ('A0','A1','A2','A3'):
        ld = pd.DataFrame(results[label]['ledger'])
        dl = pd.DataFrame(results[label]['day_log'])
        el = pd.DataFrame(results[label]['exec_log'])
        cand = pd.DataFrame(results[label]['cand_log'])
        n_cand = len(cand)
        queueable = int((ld['state']=='QUEUED').sum()) if len(ld) else 0
        # executed unique initial entries from trades (entry action)
        tr = results[label]['tr']
        n_exec = len(tr)
        cap_rows.append(dict(arch=label,
                             candidate_events=n_cand,
                             queued=queueable,
                             executed_initial=n_exec,
                             blocked_held=int((ld['state']=='BLOCKED_HELD').sum()) if len(ld) else 0,
                             blocked_k=int((ld['state']=='BLOCKED_K').sum()) if len(ld) else 0,
                             capture_rate_pct=(n_exec/n_cand*100) if n_cand else 0,
                             queueable_capture_pct=(n_exec/queueable*100) if queueable else 0))
        # exec outcome breakdown
        if len(el):
            ec = el['outcome'].value_counts().to_dict()
            for k,v in ec.items():
                cap_rows[-1][f'exec_{k}'] = v
    pd.DataFrame(cap_rows).to_csv(os.path.join(OUT, 'p4_signal_capture.csv'), index=False)

    # 4) p4_ranking_actionability.csv (diagnostic only)
    ra_rows = []
    for label in ('A0','A1','A2','A3'):
        dl = pd.DataFrame(results[label]['day_log'])
        if len(dl)==0: continue
        dl['available_slots'] = dl['available_slots'].clip(lower=0)
        actionable = int(((dl['queueable_candidates'] > dl['available_slots']) & (dl['available_slots'] >= 1)).sum())
        no_cand = int((dl['queueable_candidates']==0).sum())
        full_block = int(((dl['available_slots']==0) & (dl['queueable_candidates']>0)).sum())
        ra_rows.append(dict(arch=label, signal_days=len(dl),
                            ranking_actionable_days=actionable,
                            ranking_actionable_pct=actionable/len(dl)*100,
                            no_queueable_days=no_cand,
                            full_block_days=full_block))
    pd.DataFrame(ra_rows).to_csv(os.path.join(OUT, 'p4_ranking_actionability.csv'), index=False)

    # 5) p4_blocked_opportunities.csv - per-arch aggregate blocked
    bo_rows=[]
    for label in ('A0','A1','A2','A3'):
        dl = pd.DataFrame(results[label]['day_log'])
        if len(dl)==0: continue
        bo_rows.append(dict(arch=label,
                            full_block_days=int(((dl['available_slots']==0)&(dl['queueable_candidates']>0)).sum()),
                            blocked_k_ledger=int((pd.DataFrame(results[label]['ledger'])['state']=='BLOCKED_K').sum()) if len(pd.DataFrame(results[label]['ledger'])) else 0,
                            blocked_held_ledger=int((pd.DataFrame(results[label]['ledger'])['state']=='BLOCKED_HELD').sum()) if len(pd.DataFrame(results[label]['ledger'])) else 0))
    pd.DataFrame(bo_rows).to_csv(os.path.join(OUT, 'p4_blocked_opportunities.csv'), index=False)

    # 6) p4_position_occupancy.csv - per realized position per arch
    occ_rows=[]
    for label in ('A0','A1','A2','A3'):
        tr = results[label]['tr']
        for _, t in tr.iterrows():
            occ_rows.append(dict(arch=label, ts_code=t.get('ts_code'), entry_date=t.get('entry_date'),
                                 exit_date=t.get('exit_date'), hold_days=t.get('hold_days'),
                                 levels=t.get('levels_used'), pnl=t.get('pnl')))
    pd.DataFrame(occ_rows).to_csv(os.path.join(OUT, 'p4_position_occupancy.csv'), index=False)

    # 7) p4_path_divergence.csv - vs A0 (robust reconvergence check)
    for label in ('A0','A1','A2','A3'):
        results[label]['eq'].to_pickle(os.path.join(OUT, f'p4_eq_{label}.pkl'))
    eqA0 = results['A0']['eq'].set_index('date')
    pdv=[]
    for label in ('A1','A2','A3'):
        eqV = results[label]['eq'].set_index('date')
        common = eqA0.index.intersection(eqV.index)
        same = (abs(eqA0.loc[common,'cash']-eqV.loc[common,'cash'])<1000) & (eqA0.loc[common,'n_pos']==eqV.loc[common,'n_pos'])
        # reconverged = from some date t onward, holdings AND cash stay identical for the remainder
        n = len(common); arr = same.to_numpy()
        reconv_idx = None
        for i in range(n):
            if bool(arr[i:].all()):
                reconv_idx = i; break
        reconv_date = common[reconv_idx] if reconv_idx is not None else None
        hdiff = common[eqA0.loc[common,'n_pos'] != eqV.loc[common,'n_pos']]
        cdiff = common[abs(eqA0.loc[common,'cash']-eqV.loc[common,'cash'])>1000]
        maxdiv = float(abs(eqA0.loc[common,'equity']-eqV.loc[common,'equity']).max())
        # trade-level comparison by (ts_code, entry_date) tuples
        tA0=set(map(tuple, results['A0']['tr'][['ts_code','entry_date']].itertuples(index=False,name=None)))
        tV=set(map(tuple, results[label]['tr'][['ts_code','entry_date']].itertuples(index=False,name=None)))
        jac = len(tA0&tV)/len(tA0|tV) if (tA0|tV) else 0
        pdv.append(dict(arch=label,
                        first_holdings_diff_date=str(hdiff[0]) if len(hdiff) else None,
                        first_cash_diff_date=str(cdiff[0]) if len(cdiff) else None,
                        reconverged=bool(reconv_date is not None),
                        reconverge_date=str(reconv_date) if reconv_date is not None else 'NEVER_RECONVERGED',
                        max_equity_divergence=maxdiv, trade_set_jaccard=jac,
                        common_trades=len(tA0&tV), only_variant=len(tV-tA0), only_A0=len(tA0-tV)))
    pd.DataFrame(pdv).to_csv(os.path.join(OUT, 'p4_path_divergence.csv'), index=False)

    # 8) p4_trade_set_diff.csv  (pipe-separated: list fields contain commas, | avoids CSV tokenization issues)
    tset_rows=[]
    base=set(results['A0']['tr']['ts_code'])
    for label in ('A1','A2','A3'):
        tV=set(results[label]['tr']['ts_code'])
        tset_rows.append(dict(arch=label, common=sorted(base&tV), only_variant=sorted(tV-base), only_A0=sorted(base-tV)))
    with open(os.path.join(OUT,'p4_trade_set_diff.csv'),'w') as f:
        f.write('arch|common|only_variant|only_A0\n')
        for r in tset_rows:
            f.write('{0}|{1}|{2}|{3}\n'.format(
                r['arch'], ';'.join(r['common']), ';'.join(r['only_variant']), ';'.join(r['only_A0'])))

    # 9) p4_deep_mae_occupancy.csv (A0 positions only, descriptive)
    # MAE path info not directly in tr; approximate via frozen episode MAE lookup if available
    mae_col = None
    if 'MAE_close_pct' in fm.columns:
        mae_lookup = dict(zip(zip(fm['signal_date'], fm['ts_code']), fm['MAE_close_pct']))
    dm_rows=[]
    for label in ('A0',):
        tr = results[label]['tr']
        for _, t in tr.iterrows():
            sig = t.get('sig_date'); tc = t.get('ts_code')
            if sig is None or tc is None: continue
            mae = mae_lookup.get((pd.Timestamp(sig), tc), np.nan) if 'MAE_close_pct' in fm.columns else np.nan
            dm_rows.append(dict(arch=label, ts_code=tc, sig_date=sig, hold_days=t.get('hold_days'),
                                levels=t.get('levels_used'), mae=mae, pnl=t.get('pnl')))
    if dm_rows:
        pd.DataFrame(dm_rows).to_csv(os.path.join(OUT,'p4_deep_mae_occupancy.csv'), index=False)
    else:
        pd.DataFrame(columns=['arch','ts_code','sig_date','hold_days','levels','mae','pnl']).to_csv(os.path.join(OUT,'p4_deep_mae_occupancy.csv'), index=False)

    # 10) p4_full_block_ledger.csv (A0 FULL_BLOCK dates + held stocks + blocked candidates)
    dl0 = pd.DataFrame(results['A0']['day_log'])
    held_state = []
    if len(dl0):
        fb = dl0[(dl0['available_slots']==0)&(dl0['queueable_candidates']>0)]
        for _, r in fb.iterrows():
            held_state.append(dict(date=r['date'], all_eligible=r['all_eligible'],
                                   oversold_all=r['oversold_all'], top10_oversold=r['top10_oversold'],
                                   held_conflicts=r['held_conflicts'], pending_conflicts=r['pending_conflicts'],
                                   available_slots=r['available_slots'], queueable_candidates=r['queueable_candidates']))
    pd.DataFrame(held_state).to_csv(os.path.join(OUT,'p4_full_block_ledger.csv'), index=False)

    # 11) p4_blocked_episode_outcomes.csv - coverage of blocked candidates via frozen episode outcomes
    # reconstruct blocked candidates per day from cand_log minus queued
    candA0 = pd.DataFrame(results['A0']['cand_log'])
    ldA0 = pd.DataFrame(results['A0']['ledger'])
    cov_rows=[]
    if len(candA0) and len(ldA0):
        ldA0['sig_date'] = pd.to_datetime(ldA0['sig_date'])
        queued = set(map(tuple, ldA0[ldA0['state']=='QUEUED'][['sig_date','ts_code']].itertuples(index=False,name=None)))
        for _, c in candA0.iterrows():
            sd = pd.Timestamp(c['sig_date']); tc = c['ts_code']
            if (sd, tc) in queued: continue
            out = fm_lookup.get((sd, tc))
            cov_rows.append(dict(sig_date=str(sd.date()), ts_code=tc,
                                 has_episode=int(out is not None),
                                 episode_return_pct=out if out is not None else np.nan))
    cov = pd.DataFrame(cov_rows)
    if len(cov):
        cov.to_csv(os.path.join(OUT,'p4_blocked_episode_outcomes.csv'), index=False)
        print(f'[blocked coverage] n_blocked_candidates={len(cov)} with_episode={int(cov["has_episode"].sum())} '
              f'coverage={cov["has_episode"].mean()*100:.1f}% '
              f'mean_ret={cov.loc[cov["has_episode"]==1,"episode_return_pct"].mean():.2f}% '
              f'win={(cov.loc[cov["has_episode"]==1,"episode_return_pct"]>0).mean()*100:.1f}%', flush=True)
    else:
        cov.to_csv(os.path.join(OUT,'p4_blocked_episode_outcomes.csv'), index=False)

    # 12) p4_interaction_decomposition.csv
    def g(lab):
        return results[lab]['metrics']
    A0,A1,A2,A3 = g('A0'),g('A1'),g('A2'),g('A3')
    decomp = dict(
        metric=['total_return_pct','cagr_pct','maxdd_pct','sharpe','stock_pnl','avg_npos','avg_layers','slot_days','capital_days'],
        A0=[A0['total'],A0['ann'],A0['mdd'],A0['sharpe'],results['A0']['stock_pnl'],results['A0']['avg_npos'],results['A0']['avg_layers'],results['A0']['slot_occ'],results['A0']['cap_days']],
        A1=[A1['total'],A1['ann'],A1['mdd'],A1['sharpe'],results['A1']['stock_pnl'],results['A1']['avg_npos'],results['A1']['avg_layers'],results['A1']['slot_occ'],results['A1']['cap_days']],
        A2=[A2['total'],A2['ann'],A2['mdd'],A2['sharpe'],results['A2']['stock_pnl'],results['A2']['avg_npos'],results['A2']['avg_layers'],results['A2']['slot_occ'],results['A2']['cap_days']],
        A3=[A3['total'],A3['ann'],A3['mdd'],A3['sharpe'],results['A3']['stock_pnl'],results['A3']['avg_npos'],results['A3']['avg_layers'],results['A3']['slot_occ'],results['A3']['cap_days']],
    )
    df = pd.DataFrame(decomp)
    df['slot_effect_A1_A0'] = df['A1'] - df['A0']
    df['layer_effect_A2_A0'] = df['A2'] - df['A0']
    df['combined_A3_A0'] = df['A3'] - df['A0']
    df['interaction_A3A2_A1A0'] = (df['A3']-df['A2']) - (df['A1']-df['A0'])
    df.to_csv(os.path.join(OUT,'p4_interaction_decomposition.csv'), index=False)

    print('[DONE] P4 outputs written to', OUT, flush=True)
