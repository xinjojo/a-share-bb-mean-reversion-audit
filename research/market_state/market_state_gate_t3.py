#!/usr/bin/env python3
"""PHASE T3 — FROZEN MARKET-STATE GATE CONSTRUCTION AND PORTFOLIO COUNTERFACTUAL
- Gated variant of the frozen STRICT_C_EXECUTABLE_TICK engine (run_fast_multi_strict_c).
- Frozen gates: G0 baseline, G1 R01 strong-market avoid, G2 R01 tiered size,
  G3/G4 systemic-vs-isolated (R01>=Q80 & R05<=Q20).
- Development period ONLY: signal_date <= 2024-12-31. 2025-2026 Confirmation CLOSED.
- Pure stock primary; ETF 513500 secondary with leg attribution.
- Gate decisions use ONLY T-close market state (R01/R05 from Discovery-frozen cutpoints).
"""
import os, sys, json, hashlib
import numpy as np, pandas as pd
from collections import deque

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.join(ROOT, 'audit_package', 'github_repo')
sys.path.insert(0, ROOT)
from round51_audit import prepare_v51, full_stats, stamp_rate, COMMISSION_RATE, MIN_COMMISSION, TRANSFER_FEE_RATE
sys.path.insert(0, REPO)
from market_state_phase_t2 import load_features, assemble_day_frame

RNG = np.random.default_rng(20260903)

# ---------------------------------------------------------------------------
# 1. Feature state: date -> (r01, r05, r01_quintile)
# ---------------------------------------------------------------------------
def build_feat_state():
    day_feats, days, offset = load_features()
    ix = assemble_day_frame(day_feats, days)
    ix = ix[['ret60_ea', 'limit_down']].copy()
    ix['r01'] = ix['ret60_ea']
    ix['r05'] = ix['limit_down']
    return ix[['r01', 'r05']]


# ---------------------------------------------------------------------------
# 2. Frozen cutpoints
# ---------------------------------------------------------------------------
with open(os.path.join(REPO, 'R01_DISCOVERY_CUTPOINTS.json')) as f:
    _jc = json.load(f)
R01_Q20, R01_Q40, R01_Q60, R01_Q80 = (_jc['quantiles'][f'Q{q}'] for q in (20, 40, 60, 80))
# R05 Discovery cutpoints (frozen, from same dropna basis)
_R05 = None  # set in main from feat_state to freeze exact values
R05_Q20 = None


def load_r05_cutpoints(feat_state):
    """Freeze R05 Discovery cutpoints from the EXACT T2-R basis:
    Discovery Y20-valid signal days with finite feature (dropna)."""
    fm = pd.read_csv(os.path.join(REPO, 'results', 'fullmarket_episode_metrics.csv'))
    fm['signal_date'] = pd.to_datetime(fm['signal_date'])
    r_by = fm.groupby('signal_date').agg(r_mean=('simple_return_pct', 'mean'))
    sig = r_by.join(feat_state, how='left')
    sig = sig[~sig.index.duplicated()].sort_index()
    n = len(sig); sig_idx = sig.index.to_numpy()
    yD = np.full(n, np.nan)
    ps = np.searchsorted(sig_idx, np.datetime64('2020-01-01'))
    pe = np.searchsorted(sig_idx, np.datetime64('2022-12-31'))
    for pos in range(ps, pe):
        if pos + 20 >= n or sig_idx[pos + 20] > np.datetime64('2022-12-31'):
            continue
        fut = np.arange(pos + 1, pos + 21)
        seg = fm[fm['signal_date'].isin(sig_idx[fut])]['simple_return_pct']
        if len(seg):
            yD[pos] = seg.mean()
    disc_mask = (sig.index >= '2020-01-01') & (sig.index <= '2022-12-31') & np.isfinite(yD)
    dD = sig.loc[disc_mask, ['r01', 'r05']].dropna()
    # sanity: R01 quantiles must match frozen JSON
    r01q = np.quantile(dD['r01'], [0.2, 0.4, 0.6, 0.8])
    for got, want in zip(r01q, [R01_Q20, R01_Q40, R01_Q60, R01_Q80]):
        assert abs(got - want) < 1e-9, f"R01 cutpoint mismatch: {got} vs {want}"
    q = np.quantile(dD['r05'], [0.2, 0.4, 0.6, 0.8])
    return dict(Q20=float(q[0]), Q40=float(q[1]), Q60=float(q[2]), Q80=float(q[3]))


# ---------------------------------------------------------------------------
# 3. Gate decision helpers
# ---------------------------------------------------------------------------
def gate_decide(mode, r01, r05, r01_q80, r05_q20):
    """returns (allow_entry, allow_add_tier)
    r01/r05 may be NaN -> treat as not strong / not low-stress (allow).
    mode: 'G0' | 'G1' | 'G2' | 'G4'
    add_gate handled by caller."""
    allow_entry = True
    if mode == 'G1':
        allow_entry = not (np.isfinite(r01) and r01 >= r01_q80)
    elif mode == 'G4':
        allow_entry = not (np.isfinite(r01) and r01 >= r01_q80 and np.isfinite(r05) and r05 <= r05_q20)
    # G0/G2 always allow entry; G2 sizes
    tier = 1.0
    if mode == 'G2':
        if np.isfinite(r01):
            if r01 < R01_Q60:
                tier = 1.0
            elif r01 < R01_Q80:
                tier = 0.75
            else:
                tier = 0.5
    return allow_entry, tier


# ---------------------------------------------------------------------------
# 4. Gated engine (copy of run_fast_multi_strict_c + gate + layer_cash + ledger)
# ---------------------------------------------------------------------------
def run_fast_multi_strict_c_gated(days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
                                  K=3, top_n=10, max_levels=5, level_cash=200_000,
                                  min_listing_days=60, initial_cash=1_000_000,
                                  slippage_bp=10, stamp_tax_mode='historical',
                                  exit_bb_mode='dynamic_touch', open_fill='limit_conservative',
                                  tick_mode='conservative', limit_slip_order='ref_first',
                                  etf_enabled=True, etf_min_cash=5_000,
                                  add_gap_days=1, day_range=None, record_actions=False,
                                  flow_sink=None,
                                  gate_mode='G0', add_gate=False,
                                  feat_state=None, r01_q80=R01_Q80, r05_q20=0.0,
                                  record_blocks=False, ledger=None):
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
    # block ledger: key (sig_date, ts_code) -> dict(sig_date, ts_code, state, exec_date)
    if ledger is None:
        ledger = []

    def feats_on(d):
        if feat_state is None:
            return np.nan, np.nan
        d64 = np.datetime64(d)
        if d64 in feat_state.index:
            return float(feat_state.at[d64, 'r01']), float(feat_state.at[d64, 'r05'])
        return np.nan, np.nan

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
        reserve = 0.0
        for pb in pending_buy:
            reserve += pb.get('layer_cash', level_cash)
        for tc in pending_add:
            p = find_pos(tc)
            reserve += p.get('layer_cash', level_cash) if p is not None else level_cash
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
        r01, r05 = feats_on(d)
        allow_entry, tier = gate_decide(gate_mode, r01, r05, r01_q80, r05_q20)
        allow_add = (not add_gate) or allow_entry

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
                ensure_cash_open(pos.get('layer_cash', level_cash))
                buy_price = dd['open_'][j] * (1 + slip)
                qty = int(min(pos.get('layer_cash', level_cash), cash) / buy_price / 100) * 100
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
                key = (pb['sig_date'], pb['ts_code'])
                if len(positions) >= K or pb['ts_code'] in held:
                    pending_buy = [x for x in pending_buy if x['ts_code'] != pb['ts_code']]
                    if record_blocks:
                        for e in ledger:
                            if e['sig_date'] == key[0] and e['ts_code'] == key[1] and e['state'] == 'QUEUED':
                                e['state'] = 'BLOCKED_K_OPEN'
                    continue
                j = dd['pos'].get(pb['ts_code'])
                if j is None:
                    pending_buy = [x for x in pending_buy if x['ts_code'] != pb['ts_code']]
                    if record_blocks:
                        for e in ledger:
                            if e['sig_date'] == key[0] and e['ts_code'] == key[1] and e['state'] == 'QUEUED':
                                e['state'] = 'BLOCKED_MISSING'
                    continue
                if open_fill == 'limit_conservative' and dd['open_'][j] >= dd['limit_up_px'][j]:
                    continue   # pending persists, retry next day
                ensure_cash_open(pb.get('layer_cash', level_cash))
                buy_price = dd['open_'][j] * (1 + slip)
                qty = int(min(pb.get('layer_cash', level_cash), cash) / buy_price / 100) * 100
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
                                'layer_cash': pb.get('layer_cash', level_cash)}
                        positions.append(npos)
                        init_raw_hist(pb['ts_code'], i)
                        rec_action(d, j, 'INITIAL_ENTRY', 1, buy_price, qty, amt, npos['avg_cost'], 0, tc=npos['ts_code'])
                        held.add(pb['ts_code'])
                        if flow_sink is not None:
                            flow_sink.append(dict(date=str(d.date()), leg='stock', action='buy',
                                                  gross=amt, fee=fee, net=-(amt + fee), shares=qty, px=buy_price))
                        if record_blocks:
                            for e in ledger:
                                if e['sig_date'] == key[0] and e['ts_code'] == key[1] and e['state'] == 'QUEUED':
                                    e['state'] = 'EXECUTED'; e['exec_date'] = str(d.date())
                                    break
                        else:
                            pass
                    else:
                        if record_blocks:
                            for e in ledger:
                                if e['sig_date'] == key[0] and e['ts_code'] == key[1] and e['state'] == 'QUEUED':
                                    e['state'] = 'BLOCKED_CAPITAL'
                        pending_buy = [x for x in pending_buy if x['ts_code'] != pb['ts_code']]
                        continue
                else:
                    if record_blocks:
                        for e in ledger:
                            if e['sig_date'] == key[0] and e['ts_code'] == key[1] and e['state'] == 'QUEUED':
                                e['state'] = 'BLOCKED_LOT'
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

        # ============ CLOSE 时点 ============
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
                if allow_add:
                    pending_add[pos['ts_code']] = True
            stock_val += pos['shares'] * close

        # 新买信号 (TopN): 收盘确认 -> T+1 open
        # NOTE: record_blocks=True enumerates ALL Top10 oversold candidates (incl. when slots
        # full) purely for the blocked-opportunity ledger; queueing semantics identical to frozen.
        if record_blocks:
            li = gi - np.array([first_eligible_i.get(tc, 0) for tc in dd['ts']])
            valid = (li >= 0) & ~dd['is_st']
            if valid.any():
                cand_idx = np.where(valid)[0]
                amt = dd['amount'][cand_idx]
                order = np.argsort(-amt)[:top_n]
                held = {p['ts_code'] for p in positions} | pending_sell
                pending_set = {x['ts_code'] for x in pending_buy}
                for k in order:
                    j = cand_idx[k]
                    tc = dd['ts'][j]
                    if not (not np.isnan(dd['bb_lower'][j]) and dd['close_adj'][j] < dd['bb_lower'][j]
                            and not dd['is_limit'][j]):
                        continue
                    if tc in held or tc in pending_set:
                        ledger.append(dict(sig_date=str(d.date()), ts_code=tc, state='BLOCKED_HELD'))
                        continue
                    if not allow_entry:
                        ledger.append(dict(sig_date=str(d.date()), ts_code=tc, state='BLOCKED_GATE'))
                        continue
                    if len(positions) + len(pending_buy) >= K:
                        ledger.append(dict(sig_date=str(d.date()), ts_code=tc, state='BLOCKED_K'))
                        continue
                    pending_buy.append({'ts_code': tc, 'name': None, 'layer_cash': level_cash * tier,
                                        'sig_date': str(d.date())})
                    ledger.append(dict(sig_date=str(d.date()), ts_code=tc, state='QUEUED'))
        elif len(positions) < K:
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
                    if not allow_entry:
                        continue
                    if (not np.isnan(dd['bb_lower'][j]) and dd['close_adj'][j] < dd['bb_lower'][j]
                            and not dd['is_limit'][j]):
                        pending_buy.append({'ts_code': tc, 'name': None,
                                            'layer_cash': level_cash * tier, 'sig_date': str(d.date())})

        rebalance_close()

        etf_val = etf_sh * epx if not np.isnan(epx) else 0.0
        equity = cash + stock_val + etf_val
        _npos = len(positions)
        _inv = sum(p['total_cost'] for p in positions)
        equity_curve.append({'date': str(d.date()), 'equity': equity,
                             'cash': cash, 'stock_val': stock_val, 'etf_sh': etf_sh, 'etf_val': etf_val,
                             'n_pos': _npos, 'invested': _inv})

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
        equity_curve[-1]['n_pos'] = 0
        equity_curve[-1]['invested'] = 0.0

    eq = pd.DataFrame(equity_curve)
    tr = pd.DataFrame(trades)
    ac = pd.DataFrame(actions) if actions else pd.DataFrame()
    return eq, tr, ac


# Analytic P* (frozen from run_strict_c_math)
from run_strict_c_math import analytic_Pstar


# ---------------------------------------------------------------------------
# 5. Portfolio metrics (extended)
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
    # capital utilization: (cash+stock+etf) - idle cash
    util = 1.0 - (eq['cash'] / eq['equity'].clip(lower=1))
    cap_util_mean = float(util.mean()); cap_util_med = float(util.median())
    fully_invested = float((eq['cash'] <= 100).mean())
    cash_constrained = float((eq['cash'] < 200_000).mean())
    slot_occ = None
    n = len(tr)
    wr = (tr['pnl'] > 0).mean() * 100 if n else 0
    pf = (tr.loc[tr['pnl'] > 0, 'pnl'].sum() / abs(tr.loc[tr['pnl'] <= 0, 'pnl'].sum())) if (tr['pnl'] <= 0).any() else np.inf
    fees = 0.0  # pnl already net of fees
    return dict(total=total * 100, ann=ann * 100, ann_vol=ann_vol * 100, mdd=mdd * 100,
                sharpe=sharpe, sortino=sortino, calmar=calmar, n=n, wr=wr, pf=pf,
                cap_util_mean=cap_util_mean, cap_util_med=cap_util_med,
                fully_invested=fully_invested, cash_constrained=cash_constrained)


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



# ---------------------------------------------------------------------------
# 6. Episode-level gate classification + ledger aggregation helpers
# ---------------------------------------------------------------------------
def gate_episode_class(gm, r01, r05):
    """returns (accept, tier) for a frozen episode's signal date state."""
    accept, tier = gate_decide(gm, r01, r05, R01_Q80, R05_Q20)
    return accept, tier


def ep_stats(df, label):
    if len(df) == 0:
        return dict(group=label, n=0)
    pnl = df['pnl'].to_numpy()
    r = df['simple_return_pct'].to_numpy()
    win = (pnl > 0).mean() * 100
    pf = pnl[pnl > 0].sum() / abs(pnl[pnl <= 0].sum()) if (pnl <= 0).any() else np.inf
    return dict(group=label, n=len(df), mean_ret=float(r.mean()), med_ret=float(np.median(r)),
                win_rate=float(win), pf=float(pf) if np.isfinite(pf) else np.inf,
                mae_mean=float(df['MAE_intraday_pct'].mean()), mae_med=float(df['MAE_intraday_pct'].median()),
                mfe_mean=float(df['MFE_intraday_pct'].mean()), mfe_med=float(df['MFE_intraday_pct'].median()),
                hold_mean=float(df['hold_days'].mean()), hold_med=float(df['hold_days'].median()),
                total_pnl=float(pnl.sum()))


def ledger_agg(ledger, fm_lookup):
    ld = pd.DataFrame(ledger)
    total = len(ld)
    counts = ld['state'].value_counts().to_dict()
    executed = counts.get('EXECUTED', 0)
    gate = counts.get('BLOCKED_GATE', 0)
    k_full = counts.get('BLOCKED_K', 0) + counts.get('BLOCKED_K_OPEN', 0)
    held = counts.get('BLOCKED_HELD', 0)
    capital = counts.get('BLOCKED_CAPITAL', 0)
    missing = counts.get('BLOCKED_MISSING', 0)
    lot = counts.get('BLOCKED_LOT', 0)
    queued = counts.get('QUEUED', 0)
    bk = ld[ld['state'].isin(['BLOCKED_K', 'BLOCKED_K_OPEN'])].copy()
    if len(bk):
        bk['key'] = list(zip(pd.to_datetime(bk['sig_date']), bk['ts_code']))
        bk['ep_ret'] = bk['key'].map(fm_lookup)
        pos_k = int((bk['ep_ret'].fillna(0) > 0).sum())
        pos_k_n = int(bk['ep_ret'].notna().sum())
    else:
        pos_k = 0; pos_k_n = 0
    return dict(total_signal_opportunities=total, executed_initial=executed,
                blocked_gate=gate, blocked_by_k=k_full, blocked_by_held=held,
                blocked_capital=capital, blocked_missing=missing, blocked_lot=lot,
                unfilled_eop=queued,
                blocked_k_with_frozen_episode=pos_k_n, blocked_k_positive_frozen=pos_k)


if __name__ == '__main__':
    t0 = pd.Timestamp.now()
    os.makedirs(os.path.join(REPO, 'results'), exist_ok=True)
    os.makedirs(os.path.join(REPO, 'figures'), exist_ok=True)

    feat_state = build_feat_state()
    R05_CUTS = load_r05_cutpoints(feat_state)
    R05_Q20 = R05_CUTS['Q20']
    with open(os.path.join(REPO, 'R05_DISCOVERY_CUTPOINTS.json'), 'w') as f:
        json.dump({"feature_id": "R05", "feature": "LIMIT_DOWN_SHARE", "column": "limit_down",
                   "basis": "2020-01-01..2022-12-31 Discovery Y20-valid days (dropna)",
                   "unique_values": int(feat_state.loc[(feat_state.index >= '2020-01-01') & (feat_state.index <= '2022-12-31'), 'r05'].nunique()),
                   "zero_share_pct": float(((feat_state.loc[(feat_state.index >= '2020-01-01') & (feat_state.index <= '2022-12-31'), 'r05'] == 0).mean() * 100)),
                   "quantiles": {f"Q{q}": float(v) for q, v in zip([20, 40, 60, 80], [R05_CUTS['Q20'], R05_CUTS['Q40'], R05_CUTS['Q60'], R05_CUTS['Q80']])},
                   "decision": "continuous quintile (not heavy-zero; 0-vs->0 binary rejected as degenerate)",
                   "low_stress_definition": "R05 <= Discovery Q20",
                   "note": "Frozen before Confirmation. Not recomputed from 2023-2024."}, f, indent=2, ensure_ascii=False)
    print(f'[R05 frozen] Q20={R05_Q20:.6f} Q80={R05_CUTS["Q80"]:.6f}', flush=True)
    print(f'[feat_state] {len(feat_state)} days, {(pd.Timestamp.now()-t0).total_seconds():.0f}s', flush=True)

    # ---- prepare engine data ----
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51(
        limit_down_mode='correct', st_mode='pit')
    N2024 = sum(1 for d in days if d <= pd.Timestamp('2024-12-31'))
    print(f'[engine] n_days={len(days)} N2024={N2024} last-dev={days[N2024-1]}', flush=True)

    # ---- frozen SECONDARY episodes (dev only) ----
    fm = pd.read_csv(os.path.join(REPO, 'results', 'fullmarket_episode_metrics.csv'))
    fm['signal_date'] = pd.to_datetime(fm['signal_date'])
    fm_dev = fm[fm['signal_date'] <= pd.Timestamp('2024-12-31')].copy()
    fm_dev = fm_dev.join(feat_state, on='signal_date', how='left')
    fm_lookup = dict(zip(zip(fm['signal_date'], fm['ts_code']), fm['simple_return_pct']))
    print(f'[episodes] dev SECONDARY n={len(fm_dev)} (of {len(fm)} total; 2025+ excluded)', flush=True)

    # =================================================================
    # PART A — Episode-level counterfactual (frozen episodes, section 7)
    # =================================================================
    ep_rows = []
    reject_rows = []
    gates_ep = ['G0', 'G1', 'G2', 'G4']
    for gm in gates_ep:
        acc = np.array([gate_episode_class(gm, r1, r5)[0] for r1, r5 in zip(fm_dev['r01'], fm_dev['r05'])])
        tiers = np.array([gate_episode_class(gm, r1, r5)[1] for r1, r5 in zip(fm_dev['r01'], fm_dev['r05'])])
        acc_ep = fm_dev[acc]
        rej_ep = fm_dev[~acc]
        ep_rows.append(dict(gate=gm, side='accepted', **ep_stats(acc_ep, 'accepted')))
        ep_rows.append(dict(gate=gm, side='rejected', **ep_stats(rej_ep, 'rejected')))
        if gm == 'G2':
            for tier, nm in [(1.0, 'Q1-Q3'), (0.75, 'Q4'), (0.5, 'Q5')]:
                sel = fm_dev[np.isclose(tiers, tier)]
                ep_rows.append(dict(gate='G2', side=f'tier_{nm}', **ep_stats(sel, f'tier_{nm}')))
    ep_df = pd.DataFrame(ep_rows)
    ep_df.to_csv(os.path.join(REPO, 'results', 't3_episode_quality.csv'), index=False)
    for gm in gates_ep:
        a = ep_df[(ep_df['gate'] == gm) & (ep_df['side'] == 'accepted')]
        r_ = ep_df[(ep_df['gate'] == gm) & (ep_df['side'] == 'rejected')]
        if len(a) and len(r_) and a.iloc[0]['n'] and r_.iloc[0]['n']:
            reject_rows.append(dict(gate=gm, n_acc=int(a.iloc[0]['n']), n_rej=int(r_.iloc[0]['n']),
                                    mean_acc=a.iloc[0]['mean_ret'], mean_rej=r_.iloc[0]['mean_ret'],
                                    delta_mean=r_.iloc[0]['mean_ret'] - a.iloc[0]['mean_ret'],
                                    med_acc=a.iloc[0]['med_ret'], med_rej=r_.iloc[0]['med_ret'],
                                    delta_med=r_.iloc[0]['med_ret'] - a.iloc[0]['med_ret'],
                                    win_acc=a.iloc[0]['win_rate'], win_rej=r_.iloc[0]['win_rate'],
                                    mae_acc=a.iloc[0]['mae_med'], mae_rej=r_.iloc[0]['mae_med'],
                                    hold_acc=a.iloc[0]['hold_med'], hold_rej=r_.iloc[0]['hold_med']))
    pd.DataFrame(reject_rows).to_csv(os.path.join(REPO, 'results', 't3_rejected_vs_accepted.csv'), index=False)
    print('[PART A] episode counterfactual done', flush=True)

    # =================================================================
    # PART B — Portfolio runs (pure stock PRIMARY)
    # =================================================================
    CFG = [('G0', 'G0', False), ('G1_EO', 'G1', False), ('G1_EA', 'G1', True),
           ('G2', 'G2', False), ('G4_EO', 'G4', False), ('G4_EA', 'G4', True)]
    results = {}
    for label, gm, ag in CFG:
        ledger = []
        eq, tr, ac = run_fast_multi_strict_c_gated(
            days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
            K=3, top_n=10, max_levels=5, level_cash=200_000, initial_cash=1_000_000,
            slippage_bp=10, stamp_tax_mode='historical', exit_bb_mode='dynamic_touch',
            open_fill='limit_conservative', tick_mode='conservative', limit_slip_order='ref_first',
            etf_enabled=False, day_range=(0, N2024), record_actions=True,
            gate_mode=gm, add_gate=ag, feat_state=feat_state, r01_q80=R01_Q80, r05_q20=R05_Q20,
            record_blocks=True, ledger=ledger)
        m = portfolio_metrics(eq, tr)
        yr = yearly_returns(eq)
        stock_pnl = float(tr['pnl'].sum())
        slot_occ = float(eq['n_pos'].sum())
        cap_days = float(eq['invested'].sum())
        lagg = ledger_agg(ledger, fm_lookup)
        results[label] = dict(eq=eq, tr=tr, ac=ac, metrics=m, yearly=yr, ledger=ledger,
                              stock_pnl=stock_pnl, slot_occ=slot_occ, cap_days=cap_days, ledger_agg=lagg)
        print(f'[PORT {label}] total={m["total"]:.2f}% ann={m["ann"]:.2f}% mdd={m["mdd"]:.2f}% '
              f'sharpe={m["sharpe"]:.3f} n={m["n"]} wr={m["wr"]:.1f}% stock_pnl={stock_pnl:,.0f}', flush=True)

    # ---- G0 (record_blocks=True path) vs frozen engine parity ----
    from run_strict_c import run_fast_multi_strict_c as frozen_engine
    eqf, trf, acf, _ = frozen_engine(days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
                                     K=3, top_n=10, max_levels=5, level_cash=200_000, initial_cash=1_000_000,
                                     slippage_bp=10, stamp_tax_mode='historical', exit_bb_mode='dynamic_touch',
                                     open_fill='limit_conservative', tick_mode='conservative',
                                     limit_slip_order='ref_first', etf_enabled=False,
                                     day_range=(0, N2024), record_actions=True)
    g0 = results['G0']
    eq_match = np.allclose(g0['eq']['equity'].to_numpy(), eqf['equity'].to_numpy())
    tr_match = len(g0['tr']) == len(trf) and np.allclose(g0['tr']['pnl'].to_numpy(), trf['pnl'].to_numpy())
    ac_match = len(g0['ac']) == len(acf) and np.allclose(g0['ac']['price'].to_numpy(), acf['price'].to_numpy())
    print(f'[PARITY G0 (record_blocks=True)] equity={eq_match} trades={tr_match} actions={ac_match}', flush=True)
    assert eq_match and tr_match and ac_match, "G0 parity (ledger path) failed!"

    # ---- portfolio summary table ----
    rows = []
    for label, _gm, _ag in CFG:
        m = results[label]['metrics']
        la = results[label]['ledger_agg']
        rows.append(dict(gate=label, total_return_pct=m['total'], cagr_pct=m['ann'], ann_vol_pct=m['ann_vol'],
                         maxdd_pct=m['mdd'], sharpe=m['sharpe'], sortino=m['sortino'], calmar=m['calmar'],
                         trades=m['n'], win_rate_pct=m['wr'], pf=m['pf'],
                         cap_util_mean=m['cap_util_mean'], cap_util_med=m['cap_util_med'],
                         stock_pnl=results[label]['stock_pnl'],
                         slot_occ_days=results[label]['slot_occ'],
                         pnl_per_slot_day=results[label]['stock_pnl'] / results[label]['slot_occ'] if results[label]['slot_occ'] else 0,
                         total_signal_opp=la['total_signal_opportunities'],
                         executed_initial=la['executed_initial'], blocked_gate=la['blocked_gate'],
                         blocked_by_k=la['blocked_by_k'], blocked_held=la['blocked_by_held'],
                         blocked_capital=la['blocked_capital'], blocked_missing=la['blocked_missing'],
                         blocked_k_positive_frozen=la['blocked_k_positive_frozen']))
    pd.DataFrame(rows).to_csv(os.path.join(REPO, 'results', 't3_portfolio_summary.csv'), index=False)
    print('[PART B] portfolio summary saved', flush=True)

    # ---- yearly ----
    yr_rows = []
    for label, _gm, _ag in CFG:
        y = results[label]['yearly']
        y['gate'] = label
        yr_rows.append(y)
    pd.concat(yr_rows).to_csv(os.path.join(REPO, 'results', 't3_portfolio_yearly.csv'), index=False)

    # ---- capital efficiency (section 8) ----
    cap_rows = []
    for label, _gm, _ag in CFG:
        r = results[label]
        cap_rows.append(dict(gate=label, slot_occ_days=r['slot_occ'], capital_days=r['cap_days'],
                             stock_pnl=r['stock_pnl'],
                             pnl_per_slot_day=r['stock_pnl'] / r['slot_occ'] if r['slot_occ'] else 0,
                             pnl_per_capital_day=r['stock_pnl'] / r['cap_days'] if r['cap_days'] else 0,
                             cap_util_mean=r['metrics']['cap_util_mean'],
                             fully_invested_pct=r['metrics']['fully_invested'] * 100,
                             cash_constrained_pct=r['metrics']['cash_constrained'] * 100))
    pd.DataFrame(cap_rows).to_csv(os.path.join(REPO, 'results', 't3_capital_efficiency.csv'), index=False)

    # ---- blocked opportunities (section 8) ----
    bk_rows = []
    for label, _gm, _ag in CFG:
        la = results[label]['ledger_agg']
        la['gate'] = label
        bk_rows.append(la)
    pd.DataFrame(bk_rows).to_csv(os.path.join(REPO, 'results', 't3_blocked_opportunities.csv'), index=False)

    # =================================================================
    # PART C — Gate attribution (section 11)
    # =================================================================
    att_rows = []
    for gm in ['G1', 'G4']:
        rej = fm_dev[np.array([not gate_episode_class(gm, r1, r5)[0] for r1, r5 in zip(fm_dev['r01'], fm_dev['r05'])])]
        winners = rej[rej['pnl'] > 0]; losers = rej[rej['pnl'] <= 0]
        lost_profit = float(winners['pnl'].sum())
        saved_loss = float(-losers['pnl'].sum())
        att_rows.append(dict(gate=gm, n_rejected=int(len(rej)), n_rejected_winner=len(winners),
                             n_rejected_loser=len(losers), saved_loss=saved_loss,
                             lost_profit=lost_profit, net_gate_value=saved_loss - lost_profit,
                             rej_mean=float(rej['simple_return_pct'].mean())))
    att_df = pd.DataFrame(att_rows)
    for gm, label in [('G1_EO', 'G1'), ('G4_EO', 'G4')]:
        g0_pnl = results['G0']['stock_pnl']
        gx_pnl = results[gm]['stock_pnl']
        att_df.loc[att_df['gate'] == label, 'pathdep_portfolio_stockpnl_delta'] = gx_pnl - g0_pnl
    att_df.to_csv(os.path.join(REPO, 'results', 't3_gate_attribution.csv'), index=False)
    print('[PART C] gate attribution done', flush=True)

    # =================================================================
    # PART D — entry/add sensitivity (section 6)
    # =================================================================
    sens_rows = []
    for base in ['G1', 'G4']:
        for sfx in ['EO', 'EA']:
            label = f'{base}_{sfx}'
            m = results[label]['metrics']
            sens_rows.append(dict(gate=label, total_return_pct=m['total'], cagr_pct=m['ann'],
                                  maxdd_pct=m['mdd'], sharpe=m['sharpe'], trades=m['n'],
                                  win_rate_pct=m['wr'], stock_pnl=results[label]['stock_pnl']))
    pd.DataFrame(sens_rows).to_csv(os.path.join(REPO, 'results', 't3_entry_add_sensitivity.csv'), index=False)

    # =================================================================
    # PART E — ETF secondary (section 9) with leg attribution
    # =================================================================
    etf_rows = []
    etf_att = []
    for label, gm, ag in [('G0_ETF', 'G0', False), ('G1_ETF', 'G1', False)]:
        flow = []
        ledger_e = []
        eq, tr, ac = run_fast_multi_strict_c_gated(
            days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
            K=3, top_n=10, max_levels=5, level_cash=200_000, initial_cash=1_000_000,
            slippage_bp=10, stamp_tax_mode='historical', exit_bb_mode='dynamic_touch',
            open_fill='limit_conservative', tick_mode='conservative', limit_slip_order='ref_first',
            etf_enabled=True, day_range=(0, N2024), record_actions=True,
            gate_mode=gm, add_gate=ag, feat_state=feat_state, r01_q80=R01_Q80, r05_q20=R05_Q20,
            record_blocks=True, ledger=ledger_e, flow_sink=flow)
        m = portfolio_metrics(eq, tr)
        stock_pnl = float(tr['pnl'].sum())
        fl = pd.DataFrame(flow) if flow else pd.DataFrame()
        etf_net = float(fl.loc[fl['leg'] == 'etf', 'net'].sum()) if len(fl) else 0.0
        etf_pnl = etf_net   # sum of ETF-leg net cash flows = ETF contribution to final equity
        total = float(eq['equity'].iloc[-1]) - 1_000_000
        etf_rows.append(dict(gate=label, total_return_pct=m['total'], cagr_pct=m['ann'],
                             maxdd_pct=m['mdd'], sharpe=m['sharpe'], stock_pnl=stock_pnl,
                             etf_pnl=etf_pnl, total_pnl=total,
                             stock_pnl_share=stock_pnl / total if total else 0,
                             etf_pnl_share=etf_pnl / total if total else 0))
        etf_att.append(dict(gate=label, final_equity=float(eq['equity'].iloc[-1]), stock_pnl=stock_pnl, etf_pnl=etf_pnl))
    pd.DataFrame(etf_rows).to_csv(os.path.join(REPO, 'results', 't3_etf_secondary.csv'), index=False)
    g0e = etf_att[0]; g1e = etf_att[1]
    att_etf = dict(gate='G1_ETF_vs_G0_ETF',
                   delta_total_equity=g1e['final_equity'] - g0e['final_equity'],
                   delta_stock_pnl=g1e['stock_pnl'] - g0e['stock_pnl'],
                   delta_etf_pnl=g1e['etf_pnl'] - g0e['etf_pnl'],
                   delta_other=g1e['final_equity'] - g0e['final_equity'] - (g1e['stock_pnl'] - g0e['stock_pnl']) - (g1e['etf_pnl'] - g0e['etf_pnl']))
    pd.DataFrame([att_etf]).to_csv(os.path.join(REPO, 'results', 't3_etf_secondary_attribution.csv'), index=False)
    print('[PART E] ETF secondary done', flush=True)

    # =================================================================
    # Figures
    # =================================================================
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    plt.figure(figsize=(10, 6))
    for label in ['G0', 'G1_EO', 'G2', 'G4_EO']:
        eq = results[label]['eq']
        plt.plot(pd.to_datetime(eq['date']), eq['equity'] / 1_000_000, label=label)
    plt.legend(); plt.title('T3 Development 2020-2024 Pure-Stock Portfolio Equity (1M start)')
    plt.ylabel('Equity (M RMB)'); plt.grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(os.path.join(REPO, 'figures', 't3_portfolio_equity.png'), dpi=110)
    plt.close()

    plt.figure(figsize=(10, 5))
    y0 = results['G0']['yearly'].set_index('year')['return_pct']
    y1 = results['G1_EO']['yearly'].set_index('year')['return_pct']
    x = np.arange(len(y0))
    plt.bar(x - 0.2, y0.values, width=0.4, label='G0')
    plt.bar(x + 0.2, y1.values, width=0.4, label='G1_EO')
    plt.xticks(x, y0.index); plt.legend(); plt.title('Yearly Return G0 vs G1')
    plt.ylabel('%'); plt.grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(os.path.join(REPO, 'figures', 't3_yearly_returns.png'), dpi=110)
    plt.close()

    bk_df = pd.read_csv(os.path.join(REPO, 'results', 't3_blocked_opportunities.csv'))
    bk_df.set_index('gate', inplace=True)
    bk_df[['executed_initial', 'blocked_gate', 'blocked_by_k', 'blocked_by_held', 'blocked_capital']].plot(
        kind='bar', stacked=True, figsize=(10, 5))
    plt.title('Blocked/executed opportunities by gate (dev 2020-2024)')
    plt.ylabel('count'); plt.grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(os.path.join(REPO, 'figures', 't3_blocked_opportunities.png'), dpi=110)
    plt.close()

    ep = pd.read_csv(os.path.join(REPO, 'results', 't3_episode_quality.csv'))
    piv = ep[ep['side'].isin(['accepted', 'rejected'])].pivot(index='gate', columns='side', values='mean_ret')
    piv.plot(kind='bar', figsize=(9, 5))
    plt.title('Frozen-episode mean return: accepted vs rejected by gate')
    plt.ylabel('mean episode return %'); plt.grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(os.path.join(REPO, 'figures', 't3_accepted_vs_rejected.png'), dpi=110)
    plt.close()

    print('[figures] saved', flush=True)
    print('\nALL DONE')
