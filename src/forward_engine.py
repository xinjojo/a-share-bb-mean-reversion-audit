"""FORWARD OBSERVATION ENGINE — 逐日状态机前瞻引擎（EE15 前瞻观察期基础设施）。

设计（严格满足外部审计要求）：
1. 与冻结引擎 src/strict_c_earlyexit_ca.py 逐字同构：公司行为 → 挂单执行 → 盘中动态P*退出 → CLOSE段信号/加仓 → ETF rebalance → equity。
2. A/B 使用同一个 ForwardAccount 类，唯一差异 exit_multiplier（A=1.000, B=0.985），禁止复制两套策略实现。
3. 每日只使用截至当天的数据；从 state.last_processed_date 的次日开始逐日推进，绝不从2020重跑后回填 trades。
4. 状态完全持久化（json），每天只 append 台账，历史行只读。
5. 信号/订单/成交/权益/P*/输入hash 全部带 generated_at / data_available_through / backfilled。
"""
import os, sys, json, calendar, hashlib
import numpy as np, pandas as pd
from datetime import date as _date, timedelta as _td
from collections import deque

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # github_repo
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(ROOT))  # audit_package
sys.path.insert(0, os.path.dirname(os.path.dirname(ROOT)))  # new-chat
from round51_audit import stamp_rate, COMMISSION_RATE, MIN_COMMISSION, TRANSFER_FEE_RATE
from run_strict_c_math import analytic_Pstar

OPEN_FILL_DEFAULT = 'limit_conservative'


def compute_raw_candidates(d, dd, gi, first_eligible_i, top_n):
    """市场层原始候选（P0-1 第一层）：只依赖市场数据与冻结选股规则，
    不含账户 K 槽位 / 持仓 / 现金 / pending 判断。A/B 共用，每日只算一次。
    与冻结引擎 CLOSE 段候选扫描同公式（valid=上市合格&非ST → amount top_n → close_adj<bb_lower 且非跌停）。
    """
    li = gi - np.array([first_eligible_i.get(tc, 0) for tc in dd['ts']])
    valid = (li >= 0) & ~dd['is_st']
    raw = []
    if valid.any():
        cand_idx = np.where(valid)[0]
        amt = dd['amount'][cand_idx]
        order = np.argsort(-amt)[:top_n]
        amt_ranks = np.argsort(np.argsort(-amt)) + 1  # 候选在 amount 全排序中的名次
        for k in order:
            j = cand_idx[k]
            tc = dd['ts'][j]
            if (not np.isnan(dd['bb_lower'][j]) and dd['close_adj'][j] < dd['bb_lower'][j]
                    and not dd['is_limit'][j]):
                bb_mid = dd['bb_mid'][j]; bb_up = dd['bb_upper'][j]; bb_lo = dd['bb_lower'][j]
                sigma = (bb_up - bb_lo) / 4.0 if np.isfinite(bb_up - bb_lo) and bb_up > bb_lo else np.nan
                bb_z = (dd['close_adj'][j] - bb_mid) / sigma if sigma and not np.isnan(sigma) else np.nan
                raw.append(dict(signal_date=str(d.date()), ts_code=tc,
                                candidate_rank=int(k) + 1,
                                amount_rank=int(amt_ranks[k]),
                                close=float(dd['close'][j]),
                                bb_lower=float(bb_lo / dd['adj'][j]) if not np.isnan(bb_lo) else np.nan,
                                bb_z=float(bb_z) if np.isfinite(bb_z) else np.nan,
                                bb_width_pct=float((bb_up - bb_lo) / bb_mid * 100)
                                if np.isfinite(bb_up - bb_lo) and bb_mid > 0 else np.nan,
                                daily_high=float(dd['high'][j]),
                                note='new-entry candidate (T+1 open fill)'))
    return raw


def admit_new_entries(acct, d, dd, raw_candidates):
    """账户层接纳判定（P0-1 第二层）：由账户自身状态决定是否创建 BUY 订单。
    返回每候选 (ts_code, status, reason)。status ∈ {ADMITTED, K_FULL, ALREADY_HELD, PENDING_EXISTS}。
    A/B 允许合法分叉；raw candidate 本身必须 A/B 一致（由调用方保证同源）。
    """
    held = {p['ts_code'] for p in acct.positions} | acct.pending_sell
    pending_set = {x['ts_code'] for x in acct.pending_buy}
    out = []
    for rc in raw_candidates:
        tc = rc['ts_code']
        if len(acct.positions) + len(acct.pending_buy) >= acct.K:
            out.append((tc, 'REJECTED', 'K_FULL'))
        elif tc in held:
            out.append((tc, 'REJECTED', 'ALREADY_HELD'))
        elif tc in pending_set:
            out.append((tc, 'REJECTED', 'PENDING_EXISTS'))
        else:
            acct.pending_buy.append({'ts_code': tc, 'signal_date': str(d.date())})
            out.append((tc, 'ADMITTED', ''))
    return out


def holding_tax_rate(buy_dt, sell_excl_dt):
    y1, m1, d1 = buy_dt.year, buy_dt.month, buy_dt.day
    y2, m2, d2 = sell_excl_dt.year, sell_excl_dt.month, sell_excl_dt.day
    months_raw = (y2 - y1) * 12 + (m2 - m1)
    d1_cap = min(d1, calendar.monthrange(y2, m2)[1])
    if d2 < d1_cap:
        months_raw -= 1
    if months_raw <= 0:
        return 0.20
    if months_raw == 1 and d2 == d1_cap:
        return 0.20
    if months_raw < 12:
        return 0.10
    if months_raw == 12 and d2 == d1_cap:
        return 0.10
    return 0.00


class ForwardAccount:
    """A/B 影子账户逐日状态机。exit_multiplier: A=1.000 触发原P*；B=0.985 提前1.5%。"""

    def __init__(self, exit_multiplier=1.0, K=3, top_n=10, max_levels=5, level_cash=200_000,
                 min_listing_days=60, initial_cash=1_000_000, slippage_bp=10,
                 stamp_tax_mode='historical', etf_enabled=True, etf_min_cash=5_000,
                 add_gap_days=1, tick_mode='conservative'):
        self.exit_multiplier = float(exit_multiplier)
        self.X = 1.0 - float(exit_multiplier)  # 提前比例: A=0.0, B=0.015
        self.K = K; self.top_n = top_n; self.max_levels = max_levels
        self.level_cash = level_cash; self.min_listing_days = min_listing_days
        self.slip = slippage_bp / 10000.0
        self.stamp_tax_mode = stamp_tax_mode
        self.etf_enabled = etf_enabled; self.etf_min_cash = etf_min_cash
        self.add_gap_days = add_gap_days; self.tick_mode = tick_mode
        # ---- 账户状态 ----
        self.cash = initial_cash
        self.etf_sh = 0
        self.positions = []          # dict: ts_code/name/shares/avg_cost/l1_cost/entry_date/levels/total_cost/entry_day_idx/last_add_i/div_income/layers/div_hist
        self.pending_buy = []        # [{'ts_code','signal_date','seq'}]
        self.pending_add = {}        # {ts_code: True}
        self.pending_sell = set()    # {ts_code}
        self.raw_hist = {}           # {ts_code: deque(close_adj, maxlen=19)}
        self.raw_hist_raw = {}       # {ts_code: deque(close, maxlen=19)}
        self.last_close = {}
        self.round_no = 0
        self.last_processed_date = None

    # ---------- 序列化 ----------
    def snapshot(self):
        def prep_pos(p):
            return dict(ts_code=p['ts_code'], name=p.get('name'), shares=p['shares'],
                        avg_cost=float(p['avg_cost']), l1_cost=float(p.get('l1_cost', p['avg_cost'])),
                        entry_date=p['entry_date'], levels=p['levels'], total_cost=float(p['total_cost']),
                        entry_day_idx=p['entry_day_idx'], last_add_i=p.get('last_add_i', p['entry_day_idx']),
                        div_income=float(p.get('div_income', 0.0)),
                        layers=[[li, q] for (li, q) in (p.get('layers') or [])],
                        div_hist=[[li, str(dt), float(g)] for (li, dt, g) in (p.get('div_hist') or [])])
        return dict(exit_multiplier=self.exit_multiplier, cash=float(self.cash), etf_sh=self.etf_sh,
                    positions=[prep_pos(p) for p in self.positions],
                    pending_buy=list(self.pending_buy),
                    pending_add={k: True for k in self.pending_add},
                    pending_sell=sorted(self.pending_sell),
                    raw_hist={k: [float(v) for v in dq] for k, dq in self.raw_hist.items()},
                    raw_hist_raw={k: [float(v) for v in dq] for k, dq in self.raw_hist_raw.items()},
                    last_close={k: float(v) for k, v in self.last_close.items()},
                    round_no=self.round_no,
                    last_processed_date=str(self.last_processed_date.date()) if self.last_processed_date is not None else None)

    @classmethod
    def load(cls, snap):
        acct = cls(exit_multiplier=snap['exit_multiplier'])
        acct.cash = snap['cash']; acct.etf_sh = snap['etf_sh']
        acct.round_no = snap.get('round_no', 0)
        acct.last_processed_date = pd.Timestamp(snap['last_processed_date']) if snap.get('last_processed_date') else None
        for p in snap['positions']:
            acct.positions.append(dict(
                ts_code=p['ts_code'], name=p.get('name'), shares=p['shares'],
                avg_cost=p['avg_cost'], l1_cost=p.get('l1_cost', p['avg_cost']),
                entry_date=p['entry_date'], levels=p['levels'], total_cost=p['total_cost'],
                entry_day_idx=p['entry_day_idx'], last_add_i=p.get('last_add_i', p['entry_day_idx']),
                div_income=p.get('div_income', 0.0),
                layers=[(li, q) for li, q in p['layers']],
                div_hist=[(li, pd.Timestamp(dt), g) for li, dt, g in p['div_hist']]))
        acct.pending_buy = list(snap.get('pending_buy', []))
        acct.pending_add = {k: True for k in snap.get('pending_add', {})}
        acct.pending_sell = set(snap.get('pending_sell', []))
        acct.raw_hist = {k: deque(v, 19) for k, v in snap.get('raw_hist', {}).items()}
        acct.raw_hist_raw = {k: deque(v, 19) for k, v in snap.get('raw_hist_raw', {}).items()}
        acct.last_close = {k: v for k, v in snap.get('last_close', {}).items()}
        return acct

    # ---------- 内部工具 ----------
    def _find_pos(self, tc):
        return next((p for p in self.positions if p['ts_code'] == tc), None)

    def _ensure_cash_open(self, need, d, ei, eopx, events):
        """need 不足时按 ETF open 卖出筹资。返回事件列表。"""
        if self.cash >= need or not self.etf_enabled or self.etf_sh <= 0:
            return
        if ei is None or np.isnan(eopx):
            return
        shortfall = need - self.cash
        sell_val = shortfall * 1.02
        sell_qty = int(np.ceil(sell_val / eopx / 100)) * 100
        sell_qty = min(sell_qty, self.etf_sh)
        if sell_qty >= 100:
            amt = sell_qty * eopx * (1 - self.slip)
            fee = max(amt * COMMISSION_RATE, MIN_COMMISSION)
            cb = self.cash
            self.etf_sh -= sell_qty
            self.cash += amt - fee
            events.append(dict(date=str(d.date()), system='', ts_code='ETF', name='ETF', event_type='ETF_SELL',
                               order_id='', signal_id='', price=float(eopx), shares=sell_qty,
                               gross=float(amt), fee=float(fee), stamp_tax=0.0, transfer_fee=0.0,
                               slippage=float(amt * self.slip), dividend=0.0, split=0, tax_settle=0.0,
                               cash_before=float(cb), cash_after=float(self.cash),
                               position_shares_after=self.etf_sh, note='ensure_cash'))

    def _rebalance_close(self, d, ei, epx, events):
        if not self.etf_enabled:
            return
        if ei is None or np.isnan(epx):
            return
        reserve = (len(self.pending_buy) + len(self.pending_add)) * self.level_cash
        excess = self.cash - reserve - self.etf_min_cash
        if excess > 100 * epx:
            qty = int(excess / (epx * (1 + self.slip)) / 100) * 100
            amt = qty * epx * (1 + self.slip)
            fee = max(amt * COMMISSION_RATE, MIN_COMMISSION)
            if amt + fee <= self.cash - reserve - self.etf_min_cash:
                cb = self.cash
                self.cash -= amt + fee
                self.etf_sh += qty
                events.append(dict(date=str(d.date()), system='', ts_code='ETF', name='ETF', event_type='ETF_BUY',
                                   order_id='', signal_id='', price=float(epx), shares=qty,
                                   gross=float(amt), fee=float(fee), stamp_tax=0.0, transfer_fee=0.0,
                                   slippage=float(amt * self.slip), dividend=0.0, split=0, tax_settle=0.0,
                                   cash_before=float(cb), cash_after=float(self.cash),
                                   position_shares_after=self.etf_sh, note='rebalance'))

    def _settle_div_tax(self, pos, d, days):
        div_hist = pos.get('div_hist', [])
        if not div_hist:
            return 0.0
        sell_dt = d.date()
        sell_excl = sell_dt - _td(days=1)
        tax_due = 0.0
        for (li, div_dt, gross) in div_hist:
            buy_dt = days[li].date()
            rate = holding_tax_rate(buy_dt, sell_excl)
            tax_due += round(gross * rate, 2)
        tax_due = round(tax_due, 2)
        self.cash -= tax_due
        return tax_due

    def _sell_pos(self, pos, i, d, j, dd, price, exit_type, days, events):
        amt = price * pos['shares']
        sr = stamp_rate(d, self.stamp_tax_mode)
        fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
        proceeds = amt - fee
        div_gross = pos.get('div_income', 0.0)
        cb = self.cash
        tax_due = self._settle_div_tax(pos, d, days)
        pnl = proceeds + div_gross - pos['total_cost'] - tax_due
        hold_days = i - pos['entry_day_idx']
        self.cash += proceeds
        events.append(dict(date=str(d.date()), system='', ts_code=pos['ts_code'], name=pos.get('name'),
                           event_type='SELL', order_id='', signal_id=pos.get('signal_id', ''),
                           price=float(price),
                           shares=pos['shares'], gross=float(amt), fee=float(fee), stamp_tax=float(amt * sr),
                           transfer_fee=float(amt * TRANSFER_FEE_RATE), slippage=float(price * self.slip * pos['shares']),
                           dividend=float(div_gross), split=0, tax_settle=float(tax_due),
                           cash_before=float(cb - tax_due), cash_after=float(self.cash),
                           position_shares_after=0,
                           note=f'{exit_type} pnl={round(pnl,2)} ret={round(pnl/pos["total_cost"]*100,2)}% hold={hold_days}d levels={pos["levels"]}'))
        self.positions.remove(pos)
        self.round_no += 1

    def _init_raw_hist(self, tc, i, days, D):
        hist, hist_r = deque(), deque()
        for k in range(1, 20):
            if i - k < 0:
                break
            dk = days[i - k]
            jk = D[dk]['pos'].get(tc)
            if jk is not None:
                hist.appendleft(float(D[dk]['close_adj'][jk]))
                hist_r.appendleft(float(D[dk]['close'][jk]))
        self.raw_hist[tc] = deque(hist, 19)
        self.raw_hist_raw[tc] = deque(hist_r, 19)

    # ---------- 单日推进 ----------
    def process_day(self, i, d, dd, ei, epx, eopx, corp_evts, days, D, etf_idx, etf_px, etf_open,
                    first_eligible_i, offset, gi=None, raw_candidates=None):
        """处理一个交易日。返回 dict(signals, orders, trades, pstars, equity, note)。

        raw_candidates：市场层原始候选（compute_raw_candidates 一次计算，A/B 共用）。
        None 时内部自算（play_to / 独立运行路径），行为与冻结引擎等价。
        """
        gi = offset + i if gi is None else gi
        events = []   # 全部账户事件（trades 等）
        signals = []  # 新信号（候选/加仓，T日close生成）
        orders = []   # 订单生命周期事件
        pstars = []   # 每持仓当日 P* 检查
        eq = None

        # ===== OPEN 1: 公司行为 =====
        if corp_evts:
            for ev in corp_evts:
                pos = self._find_pos(ev['ts_code'])
                if pos is None:
                    continue
                sh_before = pos['shares']
                cb = self.cash
                r_total = (ev.get('song', 0.0) + ev.get('zhuan', 0.0)) / 10.0
                if ev.get('cash_div', 0.0) > 0:
                    div_gross = 0.0
                    cash_per_sh = ev['cash_div'] / 10.0
                    for (li, q) in (pos.get('layers') or []):
                        g = round(q * cash_per_sh, 4)
                        div_gross += g
                        pos.setdefault('div_hist', []).append((li, d.date(), g))
                    pos['div_income'] = pos.get('div_income', 0.0) + div_gross
                    self.cash += div_gross
                    events.append(dict(date=str(d.date()), system='', ts_code=ev['ts_code'], name=pos.get('name'),
                                       event_type='DIVIDEND', order_id='', signal_id='', price=np.nan,
                                       shares=sh_before, gross=float(div_gross), fee=0.0, stamp_tax=0.0,
                                       transfer_fee=0.0, slippage=0.0, dividend=float(div_gross), split=0,
                                       tax_settle=0.0, cash_before=float(cb), cash_after=float(self.cash),
                                       position_shares_after=sh_before, note='cash dividend (tax at sell)'))
                if r_total > 0:
                    new_total = sh_before + int(sh_before * r_total)
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
                    events.append(dict(date=str(d.date()), system='', ts_code=ev['ts_code'], name=pos.get('name'),
                                       event_type='SPLIT', order_id='', signal_id='', price=np.nan,
                                       shares=new_total, gross=0.0, fee=0.0, stamp_tax=0.0, transfer_fee=0.0,
                                       slippage=0.0, dividend=0.0, split=new_total - sh_before, tax_settle=0.0,
                                       cash_before=float(cb), cash_after=float(self.cash),
                                       position_shares_after=new_total,
                                       note=f"song={ev.get('song',0)}/10 zhuan={ev.get('zhuan',0)}/10"))

        # ===== OPEN 2: 执行昨收挂单 =====
        if self.pending_sell:
            for tc in list(self.pending_sell):
                pos = self._find_pos(tc)
                j = dd['pos'].get(tc)
                if pos is None or j is None:
                    self.pending_sell.discard(tc)
                    continue
                if OPEN_FILL_DEFAULT == 'limit_conservative' and dd['open_'][j] <= dd['limit_down_px'][j]:
                    orders.append(dict(date=str(d.date()), system='', ts_code=tc, event_type='SELL',
                                       status='DEFERRED', note='limit-down open, retry next day'))
                    continue
                sell_price = dd['open_'][j] * (1 - self.slip)
                self._sell_pos(pos, i, d, j, dd, sell_price, 'TAKE_PROFIT_UB', days, events)
                orders.append(dict(date=str(d.date()), system='', ts_code=tc, event_type='SELL',
                                   status='FILLED', price=float(sell_price), note='TAKE_PROFIT_UB'))
                self.pending_sell.discard(tc)
        if self.pending_add:
            for tc in list(self.pending_add):
                pos = self._find_pos(tc)
                j = dd['pos'].get(tc)
                if pos is None or j is None:
                    self.pending_add.pop(tc, None)
                    continue
                if pos['levels'] >= self.max_levels:
                    self.pending_add.pop(tc, None)
                    continue
                if OPEN_FILL_DEFAULT == 'limit_conservative' and dd['open_'][j] >= dd['limit_up_px'][j]:
                    orders.append(dict(date=str(d.date()), system='', ts_code=tc, event_type='ADD',
                                       created_date=self.pending_add.get(tc, str(d.date())),
                                       signal_id=pos.get('signal_id', ''),
                                       status='DEFERRED', note='limit-up open, retry next day'))
                    continue
                self._ensure_cash_open(self.level_cash, d, ei, eopx, events)
                buy_price = dd['open_'][j] * (1 + self.slip)
                qty = int(min(self.level_cash, self.cash) / buy_price / 100) * 100
                if qty >= 100:
                    amt = buy_price * qty
                    fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * TRANSFER_FEE_RATE
                    if amt + fee <= self.cash:
                        cb = self.cash
                        self.cash -= amt + fee
                        old_cost = pos['shares'] * pos['avg_cost']
                        pos['shares'] += qty
                        pos['avg_cost'] = (old_cost + amt + fee) / pos['shares']
                        pos['total_cost'] += amt + fee
                        pos['levels'] += 1
                        pos['last_add_i'] = i
                        if pos.get('layers') is not None:
                            pos['layers'].append((i, qty))
                        events.append(dict(date=str(d.date()), system='', ts_code=pos['ts_code'], name=pos.get('name'),
                                           event_type='BUY_ADD', order_id='', signal_id=pos.get('signal_id', ''),
                                           price=float(buy_price),
                                           shares=qty, gross=float(amt), fee=float(fee), stamp_tax=0.0,
                                           transfer_fee=float(amt * TRANSFER_FEE_RATE),
                                           slippage=float(amt * self.slip), dividend=0.0, split=0, tax_settle=0.0,
                                           cash_before=float(cb), cash_after=float(self.cash),
                                           position_shares_after=pos['shares'],
                                           note=f"level {pos['levels']}"))
                        orders.append(dict(date=str(d.date()), system='', ts_code=tc, event_type='ADD',
                                           created_date=self.pending_add.get(tc, str(d.date())),
                                           signal_id=pos.get('signal_id', ''),
                                           status='FILLED', price=float(buy_price), qty=qty, note='add-on'))
                self.pending_add.pop(tc, None)
        if self.pending_buy:
            held = {p['ts_code'] for p in self.positions}
            for pb in list(self.pending_buy):
                if len(self.positions) >= self.K or pb['ts_code'] in held:
                    self.pending_buy = [x for x in self.pending_buy if x['ts_code'] != pb['ts_code']]
                    orders.append(dict(date=str(d.date()), system='', ts_code=pb['ts_code'], event_type='BUY',
                                       created_date=pb.get('signal_date', str(d.date())),
                                       signal_id=pb.get('signal_id', ''),
                                       status='REJECTED', note='K-full or already held'))
                    continue
                j = dd['pos'].get(pb['ts_code'])
                if j is None:
                    self.pending_buy = [x for x in self.pending_buy if x['ts_code'] != pb['ts_code']]
                    orders.append(dict(date=str(d.date()), system='', ts_code=pb['ts_code'], event_type='BUY',
                                       created_date=pb.get('signal_date', str(d.date())),
                                       signal_id=pb.get('signal_id', ''),
                                       status='REJECTED', note='no quote'))
                    continue
                if OPEN_FILL_DEFAULT == 'limit_conservative' and dd['open_'][j] >= dd['limit_up_px'][j]:
                    orders.append(dict(date=str(d.date()), system='', ts_code=pb['ts_code'], event_type='BUY',
                                       created_date=pb.get('signal_date', str(d.date())),
                                       signal_id=pb.get('signal_id', ''),
                                       status='DEFERRED', note='limit-up open, retry next day'))
                    continue
                self._ensure_cash_open(self.level_cash, d, ei, eopx, events)
                buy_price = dd['open_'][j] * (1 + self.slip)
                qty = int(min(self.level_cash, self.cash) / buy_price / 100) * 100
                if qty >= 100:
                    amt = buy_price * qty
                    fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * TRANSFER_FEE_RATE
                    if amt + fee <= self.cash:
                        cb = self.cash
                        self.cash -= amt + fee
                        npos = {'ts_code': pb['ts_code'], 'name': None,
                                'shares': qty, 'avg_cost': (amt + fee) / qty,
                                'l1_cost': (amt + fee) / qty,
                                'entry_date': str(d.date()), 'levels': 1,
                                'total_cost': amt + fee, 'entry_day_idx': i, 'last_add_i': i,
                                'div_income': 0.0, 'layers': [(i, qty)], 'div_hist': [],
                                'signal_id': pb.get('signal_id', '')}
                        self.positions.append(npos)
                        self._init_raw_hist(pb['ts_code'], i, days, D)
                        events.append(dict(date=str(d.date()), system='', ts_code=npos['ts_code'], name=None,
                                           event_type='BUY', order_id='', signal_id=npos['signal_id'], price=float(buy_price),
                                           shares=qty, gross=float(amt), fee=float(fee), stamp_tax=0.0,
                                           transfer_fee=float(amt * TRANSFER_FEE_RATE),
                                           slippage=float(amt * self.slip), dividend=0.0, split=0, tax_settle=0.0,
                                           cash_before=float(cb), cash_after=float(self.cash),
                                           position_shares_after=qty, note='initial entry'))
                        orders.append(dict(date=str(d.date()), system='', ts_code=pb['ts_code'], event_type='BUY',
                                           created_date=pb.get('signal_date', str(d.date())),
                                           signal_id=pb.get('signal_id', ''),
                                           status='FILLED', price=float(buy_price), qty=qty,
                                           note=f"signal_date={pb.get('signal_date')}"))
                        held.add(pb['ts_code'])
                self.pending_buy = [x for x in self.pending_buy if x['ts_code'] != pb['ts_code']]

        # ===== 盘中退出: STRICT_C dynamic touch + early exit =====
        for pos in list(self.positions):
            j = dd['pos'].get(pos['ts_code'])
            if j is None:
                continue
            if (i - pos['entry_day_idx']) < 1:
                continue
            hist = self.raw_hist.get(pos['ts_code'])
            if hist is None or len(hist) < 19:
                continue
            adjT = dd['adj'][j]
            x_correct = np.array(list(hist)[-19:], dtype=float)
            Pstar_adj = analytic_Pstar(x_correct)
            if Pstar_adj is None or not np.isfinite(Pstar_adj):
                continue
            Pstar_raw = Pstar_adj / adjT
            if self.tick_mode == 'conservative':
                threshold = np.ceil(Pstar_raw / 0.01) * 0.01
                sell_ref = threshold
            else:
                threshold = Pstar_raw
                sell_ref = threshold
            if self.X > 0:
                eff_raw = Pstar_raw * (1.0 - self.X)
                eff_threshold = np.ceil(eff_raw / 0.01) * 0.01
            else:
                eff_threshold = threshold
            high_adj = dd['high_adj'][j]
            open_adj = dd['open_'][j] * adjT
            trig = high_adj >= eff_threshold * adjT
            pstars.append(dict(date=str(d.date()), ts_code=pos['ts_code'], level=pos['levels'],
                               avg_cost=round(float(pos['avg_cost']), 4), entry_date=pos['entry_date'],
                               adjT=float(adjT), pstar_raw=float(Pstar_raw), threshold=float(threshold),
                               eff_threshold=float(eff_threshold), exit_multiplier=float(self.exit_multiplier),
                               high_raw=float(dd['high'][j]), close_raw=float(dd['close'][j]),
                               gap_eff=float(eff_threshold - dd['high'][j]),
                               pct_eff=(float(eff_threshold - dd['high'][j]) / eff_threshold if eff_threshold > 0 else np.nan),
                               triggered=bool(trig), hold_days=int(i - pos['entry_day_idx']),
                               float_pnl=round(float(dd['close'][j] * pos['shares'] - pos['total_cost'] + pos.get('div_income', 0.0)), 2)))
            if not trig:
                continue
            if open_adj >= eff_threshold * adjT:
                ref = dd['open_'][j]
            else:
                ref = eff_threshold
            if ref <= dd['limit_down_px'][j]:
                orders.append(dict(date=str(d.date()), system='', ts_code=pos['ts_code'], event_type='SELL',
                                   created_date=str(d.date()), signal_id=pos.get('signal_id', ''),
                                   status='NO_FILL_LIMIT_DOWN', note='ref<=limit-down, no fill today, re-evaluate next day'))
                continue
            sell_price = ref * (1 - self.slip)
            self._sell_pos(pos, i, d, j, dd, sell_price, 'TAKE_PROFIT_DYN', days, events)
            orders.append(dict(date=str(d.date()), system='', ts_code=pos['ts_code'], event_type='SELL',
                               created_date=str(d.date()), signal_id=pos.get('signal_id', ''),
                               status='CREATED_AND_FILLED', price=float(sell_price),
                               intended_execution_date=str(d.date()),
                               note=f'P*={round(Pstar_raw,4)} eff={round(eff_threshold,4)} high={float(dd["high"][j])}'))

        # ===== CLOSE: 估值 + 加仓信号 + 新候选信号 =====
        stock_val = 0.0
        for pos in self.positions:
            j = dd['pos'].get(pos['ts_code'])
            if j is None:
                stock_val += pos['shares'] * self.last_close.get(pos['ts_code'], pos['avg_cost'])
                continue
            close = dd['close'][j]
            self.last_close[pos['ts_code']] = close
            self.raw_hist.setdefault(pos['ts_code'], deque([], 19)).append(float(dd['close_adj'][j]))
            self.raw_hist_raw.setdefault(pos['ts_code'], deque([], 19)).append(float(close))
            hold_days = i - pos['entry_day_idx']
            bb_lo = dd['bb_lower'][j]
            if (not np.isnan(bb_lo) and dd['close_adj'][j] < bb_lo
                    and not dd['is_limit'][j] and pos['levels'] < self.max_levels
                    and (i - pos.get('last_add_i', pos['entry_day_idx'])) >= self.add_gap_days):
                if not self.pending_add.get(pos['ts_code']):
                    self.pending_add[pos['ts_code']] = str(d.date())   # 值 = ADD_ON 信号日（订单创建日）
                    bb_mid = dd['bb_mid'][j]; bb_up = dd['bb_upper'][j]
                    sigma = (bb_up - bb_lo) / 4.0 if np.isfinite(bb_up - bb_lo) and bb_up > bb_lo else np.nan
                    bb_z = (dd['close_adj'][j] - bb_mid) / sigma if sigma and not np.isnan(sigma) else np.nan
                    signals.append(dict(signal_date=str(d.date()), ts_code=pos['ts_code'], name=pos.get('name'),
                                        signal_type='ADD_ON', level_target=pos['levels'] + 1,
                                        entry_target_date='', close=float(dd['close'][j]),
                                        bb_lower=float(bb_lo / dd['adj'][j]) if not np.isnan(bb_lo) else np.nan,
                                        bb_z=float(bb_z) if np.isfinite(bb_z) else np.nan,
                                        bb_width_pct=float((bb_up - bb_lo) / bb_mid * 100) if np.isfinite(bb_up - bb_lo) and bb_mid > 0 else np.nan,
                                        daily_high=float(dd['high'][j]), candidate_rank=np.nan,
                                        amount_rank=np.nan,
                                        note='add-on candidate (T+1 open fill)'))
            stock_val += pos['shares'] * close

        # ---- NEW_ENTRY 候选（P0-1 分层）：市场层 raw（A/B 共用，只算一次）→ 账户层 admission ----
        if raw_candidates is None:
            raw_candidates = compute_raw_candidates(d, dd, gi, first_eligible_i, self.top_n)
        for tc, status, reason in admit_new_entries(self, d, dd, raw_candidates):
            rc = next((x for x in raw_candidates if x['ts_code'] == tc), None)
            if rc is None:
                continue
            signals.append(dict(signal_date=rc['signal_date'], ts_code=tc, name=None,
                                signal_type='NEW_ENTRY', level_target=1,
                                entry_target_date='', close=rc['close'],
                                bb_lower=rc['bb_lower'], bb_z=rc['bb_z'],
                                bb_width_pct=rc['bb_width_pct'], daily_high=rc['daily_high'],
                                candidate_rank=rc['candidate_rank'], amount_rank=rc['amount_rank'],
                                admission_status=status, reject_reason=reason,
                                note='new-entry candidate (T+1 open fill)'))

        self._rebalance_close(d, ei, epx, events)

        etf_val = self.etf_sh * epx if not np.isnan(epx) else 0.0
        eq = dict(date=str(d.date()), cash=float(self.cash), stock_val=float(stock_val),
                  etf_sh=self.etf_sh, etf_val=float(etf_val), equity=float(self.cash + stock_val + etf_val))
        self.last_processed_date = d
        return dict(signals=signals, orders=orders, trades=events, pstars=pstars, equity=eq,
                    raw_candidates=raw_candidates)

    # ---------- 初始化回放 ----------
    def play_to(self, days, D, etf_idx, etf_px, etf_open, first_eligible_i, offset, target_date,
                corp_map=None, equity_sink=None, max_i=None):
        """从空账户逐日推进到 target_date（含），返回 equity 列表。用于：
        1) 对齐验证（与冻结引擎 equity 曲线逐日一致）；
        2) 前瞻启动状态（冻结日账户状态，不清仓 → PRE_EXISTING 持仓保留）。"""
        eqs = []
        for i, d in enumerate(days):
            if max_i is not None and i > max_i:
                break
            if d > target_date:
                break
            dd = D[d]
            ei = etf_idx.get(d)
            epx = etf_px[ei] if ei is not None else np.nan
            eopx = etf_open[ei] if ei is not None else np.nan
            corp = corp_map.get(str(d.date())) if corp_map else None
            r = self.process_day(i, d, dd, ei, epx, eopx, corp, days, D, etf_idx, etf_px, etf_open,
                                 first_eligible_i, offset)
            eqs.append(r['equity'])
            if equity_sink is not None:
                equity_sink.append(r['equity'])
        return eqs


def build_input_hash(d, dd, ei, epx, eopx, corp_evts):
    """当日输入数据指纹：daily 行 + ETF 行 + 公司行为。"""
    h = hashlib.sha256()
    h.update(str(d.date()).encode())
    for key in ('ts', 'close', 'open_', 'high', 'low', 'high_adj', 'close_adj', 'bb_lower', 'bb_upper',
                'bb_mid', 'amount', 'is_limit', 'is_st', 'adj', 'pre_close', 'limit_up_px', 'limit_down_px'):
        h.update(dd[key].tobytes())
    h.update(repr((ei, epx, eopx)).encode())
    h.update(repr(corp_evts).encode())
    return h.hexdigest()
