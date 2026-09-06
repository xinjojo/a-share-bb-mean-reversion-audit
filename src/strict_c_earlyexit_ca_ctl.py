"""REAL-ACCOUNT CORPORATE-ACTION ENGINE — STRICT_C + 真实券商账户式公司行为会计
基础 = src/strict_c_earlyexit.py 的 run_fast_multi_strict_c_ee (逐字一致, X=0 时除公司行为外完全相同)
新增 (真实账户):
  1. corp_map: {date_str: [dict(ts_code, song, zhuan, cash_div)]} — 真实送转/派息事件 (akshare fhps)
  2. 每日主循环开头 (挂单执行前) 处理公司行为:
       - 送转: shares += floor(shares*(song+zhuan)/10), 零股向下取整; 各层按比例, 末层吸收取整差
       - 派息: 现金分红按登记日持股(事件前股数) 税前全额入账, 逐批次(层)记入 div_hist
  3. 卖出时按先进先出批次结算红利税 (settle_div_tax):
       持股期限 = 该层买入日 -> 卖出交割日前一日, 按自然月对日边界:
       <=1个自然月(含恰好) 20%, >1个月且<=1年 10%, >1年 0%; 税从 cash 扣除
  4. pnl = 卖出净收入 - 总成本 + 累计税前分红 (div_income) - 结算红利税 (tax_due)
  5. real-account event ledger: 每次 buy/add/sell/div/split/tax 按日期顺序记录
本文件是实验副本, 不修改冻结引擎.
"""
import sys, os
import calendar
import numpy as np, pandas as pd
from datetime import date as _date, timedelta as _td

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from round51_audit import prepare_v51, full_stats, stamp_rate, \
    COMMISSION_RATE, MIN_COMMISSION, TRANSFER_FEE_RATE
from run_strict_c_math import analytic_Pstar

OPEN_FILL_DEFAULT = 'limit_conservative'


def holding_tax_rate(buy_dt, sell_excl_dt):
    """A股差别化股息红利税 — 按自然月对日边界(不是简单30天)。

    持股期限 = 买入日 -> 卖出交割日前一日。
    <=1个自然月(含恰好1个月) -> 20%; >1个月且<=1年(12个自然月) -> 10%; >1年 -> 0%。
    对日不存在时取目标月最后一天 (如1/31买入, 2/28满1个月)。
    """
    y1, m1, d1 = buy_dt.year, buy_dt.month, buy_dt.day
    y2, m2, d2 = sell_excl_dt.year, sell_excl_dt.month, sell_excl_dt.day
    months_raw = (y2 - y1) * 12 + (m2 - m1)
    d1_cap = min(d1, calendar.monthrange(y2, m2)[1])
    if d2 < d1_cap:
        months_raw -= 1
    if months_raw <= 0:
        return 0.20
    if months_raw == 1 and d2 == d1_cap:
        return 0.20  # 恰好满1个自然月 -> "1个月以内(含1个月)" -> 20%
    if months_raw < 12:
        return 0.10
    if months_raw == 12 and d2 == d1_cap:
        return 0.10  # 恰好满1年 -> "1年以上至1年(含1年)" -> 10%
    return 0.00  # 超过1年 -> 0%


def run_fast_multi_strict_c_ee_ca(days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
                                  K=3, top_n=10, max_levels=5, level_cash=200_000,
                                  min_listing_days=60, initial_cash=1_000_000,
                                  slippage_bp=10, stamp_tax_mode='historical',
                                  exit_bb_mode='dynamic_touch',
                                  open_fill=OPEN_FILL_DEFAULT,
                                  tick_mode='conservative',
                                  limit_slip_order='ref_first',
                                  etf_enabled=True, etf_min_cash=5_000,
                                  add_gap_days=1, day_range=None, record_actions=False,
                                  flow_sink=None, early_exit_pct=0.0, collect_daily_pstar=False,
                                  corp_map=None, ledger_sink=None, tax_sink=None,
                                  ctl_final_rate_map=None):
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

    def led(date_str, ts_code, name, etype, sh_b, sh_c, sh_a, c_b, c_c, c_a, price, fee, reason):
        if ledger_sink is not None:
            ledger_sink.append(dict(date=date_str, ts_code=ts_code, name=name, event_type=etype,
                                    shares_before=sh_b, shares_change=sh_c, shares_after=sh_a,
                                    cash_before=round(c_b, 2), cash_change=round(c_c, 2),
                                    cash_after=round(c_a, 2), price=price, fee=round(fee, 2), reason=reason))

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
            cb = cash
            etf_sh -= sell_qty
            cash += amt - fee
            led(str(d.date()), 'ETF', 'ETF', 'ETF_SELL', 0, 0, 0, cb, amt - fee, cash, eopx, fee, 'ensure_cash')
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
                cb = cash
                cash -= amt + fee
                etf_sh += qty
                led(str(d.date()), 'ETF', 'ETF', 'ETF_BUY', 0, 0, 0, cb, -(amt + fee), cash, epx, fee, 'rebalance')
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

    def settle_div_tax(pos, d, cb_in):
        """控制实验C: 分红日已按最终税率净额入账, 卖出时不结算。"""
        nonlocal cash
        if ctl_final_rate_map is not None:
            return 0.0, cash
        div_hist = pos.get('div_hist', [])
        if not div_hist:
            return 0.0, cash
        sell_dt = d.date() if hasattr(d, 'date') else d
        sell_excl = sell_dt - _td(days=1)
        layers_map = {li: q for (li, q) in (pos.get('layers') or [])}
        tax_due = 0.0
        for (li, div_dt, gross) in div_hist:
            buy_dt = days[li].date()
            rate = holding_tax_rate(buy_dt, sell_excl)
            t = round(gross * rate, 2)
            tax_due += t
            if tax_sink is not None:
                tax_sink.append(dict(
                    ts_code=pos['ts_code'], name=pos.get('name'), buy_date=str(buy_dt),
                    sell_date=str(sell_dt), shares_sold=layers_map.get(li, 0),
                    dividend_date=str(div_dt), dividend_gross=round(gross, 2),
                    holding_days=int((sell_excl - buy_dt).days),
                    tax_rate=rate, tax_due=t,
                    cash_before=round(cb_in, 2), cash_after=round(cb_in - tax_due, 2)))
        tax_due = round(tax_due, 2)
        cash -= tax_due
        if tax_due > 0 and ledger_sink is not None:
            led(str(sell_dt), pos['ts_code'], pos.get('name'), 'TAX_SETTLE',
                pos['shares'], 0, pos['shares'], cb_in, -tax_due, cash, np.nan, 0.0,
                f'div tax settlement FIFO rate={round(tax_due,2)}')
        return tax_due, cash

    def sell_pos(pos, d, j, price, exit_type):
        nonlocal cash, round_no
        amt = price * pos['shares']
        sr = stamp_rate(d, stamp_tax_mode)
        fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
        proceeds = amt - fee
        div_gross = pos.get('div_income', 0.0)
        cb = cash
        tax_due, cash = settle_div_tax(pos, d, cb)
        pnl = proceeds + div_gross - pos['total_cost'] - tax_due
        hold_days = i - pos['entry_day_idx']
        trades.append({'round': round_no, 'ts_code': pos['ts_code'], 'name': pos.get('name'),
                       'entry_date': pos['entry_date'], 'exit_date': str(d.date()),
                       'exit_type': exit_type, 'levels_used': pos['levels'],
                       'shares': pos['shares'], 'pnl': pnl,
                       'div_income': round(div_gross, 2), 'tax_due': round(tax_due, 2),
                       'return_pct': round(pnl / pos['total_cost'] * 100, 2),
                       'hold_days': hold_days})
        rec_action(d, j, exit_type, pos['levels'], price, pos['shares'], amt, pos['avg_cost'], hold_days,
                   ret=pnl / pos['total_cost'] * 100, tc=pos['ts_code'])
        cash += proceeds
        led(str(d.date()), pos['ts_code'], pos.get('name'), 'SELL', pos['shares'], -pos['shares'], 0,
            cb - tax_due, proceeds, cash, price, fee, exit_type)
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

        # ============ OPEN 1: 公司行为处理 (真实账户, 在挂单执行前) ============
        if corp_map is not None:
            evts = corp_map.get(str(d.date()))
            if evts:
                for ev in evts:
                    pos = find_pos(ev['ts_code'])
                    if pos is None:
                        continue
                    sh_before = pos['shares']
                    cb = cash
                    r_total = (ev.get('song', 0.0) + ev.get('zhuan', 0.0)) / 10.0
                    # ---- 现金分红: 先处理 (按股权登记日持股=事件前股数, 税前全额入账, 税在卖出时结算) ----
                    if ev.get('cash_div', 0.0) > 0:
                        div_gross = 0.0
                        div_net = 0.0
                        cash_per_sh = ev['cash_div'] / 10.0
                        for (li, q) in (pos.get('layers') or []):
                            g = round(q * cash_per_sh, 4)
                            div_gross += g
                            if ctl_final_rate_map is not None:
                                bd = str(days[li].date())
                                rate = ctl_final_rate_map.get((pos['ts_code'], bd), 0.0)
                                div_net += round(g * (1.0 - rate), 4)
                            else:
                                pos.setdefault('div_hist', []).append((li, d.date(), g))
                                div_net += g
                        pos['div_income'] = pos.get('div_income', 0.0) + div_gross
                        cash += div_net
                        if ctl_final_rate_map is not None:
                            led(str(d.date()), pos['ts_code'], pos.get('name'), 'DIVIDEND',
                                sh_before, 0, sh_before, cb, round(div_net, 2), cash, np.nan, 0.0,
                                f"CTL: cash_div={ev['cash_div']}/10 net={round(div_net,2)} (final-rate settled at div date)")
                        else:
                            led(str(d.date()), pos['ts_code'], pos.get('name'), 'DIVIDEND',
                                sh_before, 0, sh_before, cb, round(div_gross, 2), cash, np.nan, 0.0,
                                f"cash_div={ev['cash_div']}/10 gross={round(sh_before*cash_per_sh,2)} (tax settled at sell)")
                    # ---- 送转: 真实股数变化 (登记日持股按比例) ----
                    if r_total > 0:
                        new_total = sh_before + int(sh_before * r_total)
                        # 各层按比例, 末层吸收零股取整差
                        if pos.get('layers') is not None:
                            assigned = 0
                            nl = []
                            for k, (li, q) in enumerate(pos['layers']):
                                if k == len(pos['layers']) - 1:
                                    nq = new_total - assigned
                                else:
                                    nq = int(q * (1.0 + r_total))
                                nl.append((li, nq))
                                assigned += nq
                            pos['layers'] = nl
                        pos['shares'] = new_total
                        led(str(d.date()), pos['ts_code'], pos.get('name'), 'SPLIT',
                            sh_before, new_total - sh_before, new_total,
                            cb, 0.0, cb, np.nan, 0.0,
                            f"song={ev.get('song',0)}/10 zhuan={ev.get('zhuan',0)}/10")

        # ============ OPEN 2: 执行昨收挂单 ============
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
                        cb = cash
                        cash -= amt + fee
                        old_cost = pos['shares'] * pos['avg_cost']
                        pos['shares'] += qty
                        pos['avg_cost'] = (old_cost + amt + fee) / pos['shares']
                        pos['total_cost'] += amt + fee
                        pos['levels'] += 1
                        pos['last_add_i'] = i
                        if pos.get('layers') is not None:
                            pos['layers'].append((i, qty))
                        rec_action(d, j, 'ADD_POSITION', pos['levels'], buy_price, qty, amt, pos['avg_cost'], i - pos['entry_day_idx'], tc=tc)
                        led(str(d.date()), pos['ts_code'], pos.get('name'), 'BUY_ADD', pos['shares'] - qty, qty, pos['shares'],
                            cb, -(amt + fee), cash, buy_price, fee, f"level {pos['levels']}")
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
                        cb = cash
                        cash -= amt + fee
                        npos = {'ts_code': pb['ts_code'], 'name': None,
                                'shares': qty, 'avg_cost': (amt + fee) / qty,
                                'l1_cost': (amt + fee) / qty,
                                'entry_date': str(d.date()), 'levels': 1,
                                'total_cost': amt + fee, 'entry_day_idx': i, 'last_add_i': i,
                                'div_income': 0.0, 'layers': [(i, qty)], 'div_hist': []}
                        positions.append(npos)
                        init_raw_hist(pb['ts_code'], i)
                        rec_action(d, j, 'INITIAL_ENTRY', 1, buy_price, qty, amt, npos['avg_cost'], 0, tc=npos['ts_code'])
                        led(str(d.date()), npos['ts_code'], None, 'BUY', 0, qty, qty, cb, -(amt + fee), cash, buy_price, fee, 'initial entry')
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
                        float_pnl=round(float(dd['close'][j] * pos['shares'] - pos['total_cost'] + pos.get('div_income', 0.0)), 2),
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
            div_gross = pos.get('div_income', 0.0)
            cb = cash
            tax_due, cash = settle_div_tax(pos, d, cb)
            pnl = proceeds + div_gross - pos['total_cost'] - tax_due
            hold_days = (day_range[1] - 1 if day_range else len(days) - 1) - pos['entry_day_idx']
            trades.append({'round': round_no, 'ts_code': pos['ts_code'], 'name': pos.get('name'),
                           'entry_date': pos['entry_date'], 'exit_date': str(d.date()),
                           'exit_type': 'FINAL_SETTLE', 'levels_used': pos['levels'],
                           'shares': pos['shares'], 'pnl': pnl,
                           'div_income': round(div_gross, 2), 'tax_due': round(tax_due, 2),
                           'return_pct': round(pnl / pos['total_cost'] * 100, 2),
                           'hold_days': hold_days})
            cash += proceeds
            led(str(d.date()), pos['ts_code'], pos.get('name'), 'FINAL_SETTLE', pos['shares'], -pos['shares'], 0,
                cb - tax_due, proceeds, cash, sell_price, fee, 'end of data')
            positions.remove(pos)
            round_no += 1
            if flow_sink is not None:
                flow_sink.append(dict(date=str(d.date()), leg='stock', action='settle',
                                      gross=amt, fee=fee, net=proceeds, shares=pos['shares'], px=sell_price))
    if etf_sh > 0 and not np.isnan(epx):
        amt = etf_sh * epx * (1 - slip)
        fee = max(amt * COMMISSION_RATE, MIN_COMMISSION)
        cb = cash
        cash += amt - fee
        etf_sh = 0
        led(str(d.date()), 'ETF', 'ETF', 'ETF_SETTLE', 0, 0, 0, cb, amt - fee, cash, epx * (1 - slip), fee, 'end of data')
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
