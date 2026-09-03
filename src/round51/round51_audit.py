"""STRICT_V2 审计引擎 (Round5.1)
修复:
  PIT ST      : is_st 用 namechange 重建的 Point-in-Time 状态
  LISTING_60D : 上市满60日改用 stock_basic.list_date + 交易日历, 禁止用回测切片首日
  ETF 时点    : 事件驱动 ensure_cash_open / ensure_cash_close / rebalance_close
  ONE_WORD    : next_open 成交不用整日一字板(未来), 用 open_fill 上下界
"""
import os, sys
import numpy as np, pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

COMMISSION_RATE = 0.00025
MIN_COMMISSION = 5.0
TRANSFER_FEE_RATE = 0.00001   # 过户费 0.001%

def stamp_rate(d, mode):
    if mode == 'historical':
        return 0.001 if d < pd.Timestamp('2023-08-28') else 0.0005
    return 0.0005

def load_stamp_mode(name):
    return name


def prepare_v51(limit_down_mode='correct', st_mode='pit', bb_window=20, bb_std=2.0, min_listing_days=60):
    """返回 (days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset)"""
    df = pd.read_parquet(os.path.join(PROJECT_ROOT, 'data', 'combined_daily.parquet'))
    df['date'] = pd.to_datetime(df['date'])
    if st_mode == 'pit':
        pit = pd.read_parquet(os.path.join(PROJECT_ROOT, 'data', 'pit_st_daily.parquet'))
        pit['date'] = pd.to_datetime(pit['date'])
        df = df.merge(pit[['date', 'ts_code', 'is_st_pit']], on=['date', 'ts_code'], how='left')
        df['is_st'] = df['is_st_pit'].fillna(False)
    else:  # snapshot (当前快照, 对照)
        sb = pd.read_parquet(os.path.join(PROJECT_ROOT, 'data', 'raw', 'stock_basic.parquet'))
        df = df.merge(sb[['ts_code', 'name']], on='ts_code', how='left')
        df['is_st'] = df['name'].str.contains('ST', na=False)
    df = df[(df['date'] >= '2020-01-01') & (df['date'] <= '2026-08-25')]
    df = df.sort_values(['ts_code', 'date']).reset_index(drop=True)
    df['close_adj'] = df['close'] * df['adj_factor']
    df['high_adj'] = df['high'] * df['adj_factor']
    g = df.groupby('ts_code')['close_adj']
    df['ma'] = g.transform(lambda x: x.rolling(bb_window, min_periods=bb_window).mean())
    df['sd'] = g.transform(lambda x: x.rolling(bb_window, min_periods=bb_window).std())
    df['bb_lower'] = df['ma'] - bb_std * df['sd']
    df['bb_upper'] = df['ma'] + bb_std * df['sd']
    # 涨跌停价格 (correct口径, 用PIT ST)
    is_chi = df['ts_code'].str.startswith(('688', '689'))
    is_gem = df['ts_code'].str.startswith('30')
    is_st = df['is_st']
    gem_pct = np.where(df['date'] >= '2020-08-24', 0.20, 0.10)
    pct = np.where(is_chi, 0.20, np.where(is_gem, gem_pct, np.where(is_st, 0.05, 0.10)))
    df['limit_up_px'] = (df['pre_close'] * (1 + pct)).round(2)
    df['limit_down_px'] = (df['pre_close'] * (1 - pct)).round(2)
    df['is_limit_down'] = df['close'] <= df['limit_down_px']
    df['is_limit_up'] = df['close'] >= df['limit_up_px']

    days = sorted(df['date'].unique())

    # ===== listing 修复: 用 list_date + 完整交易日历(1990起) =====
    tc = pd.read_parquet(os.path.join(PROJECT_ROOT, 'data', 'raw', 'trade_cal_full.parquet'))
    cal = tc['date'].sort_values().reset_index(drop=True)
    cal_dates = cal.to_numpy()
    sb2 = pd.read_parquet(os.path.join(PROJECT_ROOT, 'data', 'raw', 'stock_basic.parquet'))[['ts_code', 'list_date']]
    first_eligible_i = {}
    for tc_code, ld in zip(sb2['ts_code'], sb2['list_date']):
        try:
            list_dt = pd.Timestamp(ld)
        except Exception:
            list_dt = pd.Timestamp('1990-01-01')
        pos = int(np.searchsorted(cal_dates, list_dt))
        first_eligible_i[tc_code] = pos + min_listing_days
    offset = int(np.searchsorted(cal_dates, days[0]))

    # ===== 每日 numpy 结构 =====
    D = {}
    for d, g in df.groupby('date'):
        D[d] = dict(
            ts=g['ts_code'].to_numpy(),
            close=g['close'].to_numpy(), open_=g['open'].to_numpy(),
            high=g['high'].to_numpy(), low=g['low'].to_numpy(),
            high_adj=g['high_adj'].to_numpy(), close_adj=g['close_adj'].to_numpy(),
            bb_lower=g['bb_lower'].to_numpy(), bb_upper=g['bb_upper'].to_numpy(), bb_mid=g['ma'].to_numpy(),
            amount=g['amount'].to_numpy(), is_limit=g['is_limit_down'].to_numpy(),
            is_st=g['is_st'].to_numpy(), adj=g['adj_factor'].to_numpy(),
            pre_close=g['pre_close'].to_numpy(),
            limit_up_px=g['limit_up_px'].to_numpy(), limit_down_px=g['limit_down_px'].to_numpy(),
            is_limit_up=g['is_limit_up'].to_numpy(), is_limit_down_arr=g['is_limit_down'].to_numpy(),
        )
        D[d]['pos'] = {tc: j for j, tc in enumerate(D[d]['ts'])}
    # bb_upper_prev: T-1 收盘已知上轨
    for k in range(1, len(days)):
        d0, d1 = days[k - 1], days[k]
        prev_bb = {tc: D[d0]['bb_upper'][j] for j, tc in enumerate(D[d0]['ts'])}
        cur = D[d1]
        cur['bb_upper_prev'] = np.array([prev_bb.get(tc, np.nan) for tc in cur['ts']])
    D[days[0]]['bb_upper_prev'] = np.full(len(D[days[0]]['ts']), np.nan)

    # ===== ETF =====
    m = pd.read_parquet(os.path.join(PROJECT_ROOT, 'data', 'etf_513500_merged.parquet'))
    m['trade_date'] = pd.to_datetime(m['trade_date'])
    m = m.sort_values('trade_date')
    etf_idx = {d: k for k, d in enumerate(m['trade_date'])}
    etf_px = m['close'].to_numpy()
    etf_open = m['open'].to_numpy()
    etf_nav = m['unit_nav'].to_numpy()
    return days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset


def run_fast_multi_v51(days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
                       K=3, top_n=10, max_levels=5, level_cash=200_000,
                       min_listing_days=60, initial_cash=1_000_000,
                       slippage_bp=10, stamp_tax_mode='historical',
                       exit_bb_mode='prev',            # 'prev'(A) | 'close_confirm_next'(B)
                       open_fill='limit_conservative', # 'optimistic' | 'limit_conservative'
                       etf_enabled=True, etf_min_cash=5_000,
                       add_gap_days=1, day_range=None, record_actions=False):
    """事件驱动 STRICT_V2 引擎.
    买入: T收盘信号 -> T+1 open 执行; ETF筹资 T+1 open
    退出 A(prev)    : T日盘中 high>=bb_upper_prev[T] -> 已知上轨成交(日线近似)
    退出 B(confirm) : T日收盘 close_adj>=bb_upper[T] -> T+1 open 卖出
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
    pending_buy = []       # T收盘新买信号 -> T+1 open 买入
    pending_add = {}       # T收盘加仓信号 -> T+1 open 加仓
    pending_sell = set()   # T收盘确认(exit B) -> T+1 open 卖出

    def ensure_cash_open(need):
        """T 日 open 时点卖 ETF(用 open 价) 筹资金"""
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
        """T 日 close 时点: 预留 pending 资金后, 剩余现金买 ETF(close 价)"""
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
        # 1. pending_sell (exit B: 昨收确认 -> 今开卖)
        if pending_sell:
            for tc in list(pending_sell):
                pos = find_pos(tc)
                j = dd['pos'].get(tc)
                if pos is None or j is None:
                    pending_sell.discard(tc)
                    continue
                if open_fill == 'limit_conservative' and dd['open_'][j] <= dd['limit_down_px'][j]:
                    continue   # 开盘即跌停, 卖不出, 顺延
                sell_price = dd['open_'][j] * (1 - slip)
                sell_pos(pos, d, j, sell_price, 'TAKE_PROFIT_UB')
                pending_sell.discard(tc)
        # 2. pending_add (昨收加仓 -> 今开加)
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
                    continue   # 开盘涨停买不进, 顺延
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
        # 3. pending_buy (昨收新买信号 -> 今开买入)
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
                    continue   # 开盘涨停买不进, 顺延
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
                        rec_action(d, j, 'INITIAL_ENTRY', 1, buy_price, qty, amt, npos['avg_cost'], 0, tc=npos['ts_code'])
                        held.add(pb['ts_code'])
                pending_buy = [x for x in pending_buy if x['ts_code'] != pb['ts_code']]

        # ============ 盘中/退出 (exit A: prev 上轨, T日盘中 high 触发) ============
        if exit_bb_mode == 'prev':
            for pos in list(positions):
                j = dd['pos'].get(pos['ts_code'])
                if j is None:
                    continue
                bb_prev = dd['bb_upper_prev'][j]
                if (not np.isnan(bb_prev) and (i - pos['entry_day_idx']) >= 1
                        and dd['high_adj'][j] >= bb_prev):
                    exit_price = (bb_prev / dd['adj'][j]) * (1 - slip)
                    sell_pos(pos, d, j, exit_price, 'TAKE_PROFIT_UB')

        # ============ CLOSE 时点: 收盘确认信号 ============
        stock_val = 0.0
        for pos in positions:
            j = dd['pos'].get(pos['ts_code'])
            if j is None:
                stock_val += pos['shares'] * last_close.get(pos['ts_code'], pos['avg_cost'])
                continue
            close = dd['close'][j]
            last_close[pos['ts_code']] = close
            hold_days = i - pos['entry_day_idx']
            bb_cur = dd['bb_upper'][j]
            bb_lo = dd['bb_lower'][j]
            # exit B: 收盘确认站上 T 日上轨 -> 挂 T+1 open 卖
            if (exit_bb_mode == 'close_confirm_next' and not np.isnan(bb_cur)
                    and hold_days >= 1 and dd['close_adj'][j] >= bb_cur):
                pending_sell.add(pos['ts_code'])
            # 加仓信号: 收盘 < 下轨 -> 挂 T+1 open 加仓
            elif (not np.isnan(bb_lo) and dd['close_adj'][j] < bb_lo
                  and not dd['is_limit'][j] and pos['levels'] < max_levels
                  and (i - pos.get('last_add_i', pos['entry_day_idx'])) >= add_gap_days):
                pending_add[pos['ts_code']] = True
            if pos['ts_code'] in pending_sell:
                # exit B 已确认, T+1 open 将卖出; 当日仍持仓, 市值按 close 计入(只禁止同日再加仓)
                stock_val += pos['shares'] * close
            else:
                stock_val += pos['shares'] * close

        # 新买信号 (TopN): 收盘确认 -> 挂 T+1 open 新买
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

        # rebalance: 收盘买 ETF (预留 pending 资金)
        rebalance_close()

        # 估值 (market close)
        etf_val = etf_sh * epx if not np.isnan(epx) else 0.0
        equity = cash + stock_val + etf_val
        equity_curve.append({'date': str(d.date()), 'equity': equity,
                             'cash': cash, 'stock_val': stock_val, 'etf_sh': etf_sh, 'etf_val': etf_val})

    # ============ 期末清仓 (同步到最后一行) ============
    d = days[day_range[1] - 1] if day_range else days[-1]
    dd = D[d]
    ei = etf_idx.get(d)
    epx = etf_px[ei] if ei is not None else np.nan
    # 期末股票清仓
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
    # 期末 ETF 清仓 (扣佣金)
    if etf_sh > 0 and not np.isnan(epx):
        amt = etf_sh * epx * (1 - slip)
        fee = max(amt * COMMISSION_RATE, MIN_COMMISSION)
        cash += amt - fee
        etf_sh = 0
    # 同步到最后一行
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


def full_stats(eq, tr):
    if len(eq) == 0:
        return {'total': 0, 'ann': 0, 'mdd': 0, 'sharpe': 0, 'n': 0, 'wr': 0}
    init = eq['equity'].iloc[0] / (1 + 0)  # 用首日
    total = eq['equity'].iloc[-1] / eq['equity'].iloc[0] - 1
    n_years = len(eq) / 245
    ann = (1 + total) ** (1 / n_years) - 1 if n_years > 0 else 0
    eq2 = eq['equity'].to_numpy()
    peak = np.maximum.accumulate(eq2)
    mdd = float(((eq2 - peak) / peak).min())
    r = np.diff(eq2) / eq2[:-1]
    sharpe = float(np.mean(r) / np.std(r) * np.sqrt(245)) if np.std(r) > 0 else 0
    n = len(tr)
    wr = float((tr['pnl'] > 0).mean() * 100) if n else 0
    return {'total': float(total * 100), 'ann': float(ann * 100), 'mdd': float(mdd * 100),
            'sharpe': sharpe, 'n': int(n), 'wr': wr}
