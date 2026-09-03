"""INDEPENDENT TRADE REPLAY — ALL A SHARES (STRICT_C_EXECUTABLE_TICK 语义)
==========================================================
研究问题: "成交额筛选 + Bollinger 超跌均值回归" 作为一笔笔独立交易,
本身是否有稳定正向 expectancy.

不构建资金组合; 不考虑 portfolio capital / K / ETF / cash management / 资金竞争.
每只股票的每次 signal->entry->exit 作为一笔独立 trade (只测 SIGNAL/TRADE EDGE).

必须沿用当前已审计 STRICT_C_EXECUTABLE_TICK 语义:
  - PIT ST (pit_st_daily.parquet, is_st_pit)
  - real list_date + 60 trading days (stock_basic.list_date + 完整交易日历 1990 起)
  - correct price limits (科创20% / 创业20%(2020-08-24后) / ST5% / 主板10%; 北交所沿用审计版10%)
  - suspension: 每股只遍历有数据日; pending 顺延(复牌日执行), 与原组合引擎"停牌日丢弃"的差异见 md
  - A股 T+1
  - 100-share lot
  - historical stamp tax (2023-08-28 前 0.1%, 后 0.05%)
  - commission 0.025% min5 + 过户费 0.001%
  - slippage 10bp
  - dynamic Bollinger self-consistent P* (analytic, ddof=1, 各日自己 adj_factor)
  - legal tick ceil execution (threshold=ceil(P*_raw/0.01)*0.01; ref=open 若 gap-through else threshold)
  - corrected per-day adj_factor semantics (close_adj[k]=close_raw[k]*adj_factor[k])
  - final settlement (期末用该股最后有数据日 close)

交易定义:
  PRIMARY   : 成交额 Top10(当日 valid: 上市满60日 & 非ST PIT) 中, close_adj < bb_lower 且非跌停 -> 信号
  SECONDARY : 所有 PIT eligible A股满足上述超跌 -> 信号
  信号日 T 收盘确认 -> T+1 open 成交 (开盘涨停顺延); 加仓同(距上次加仓>=1交易日), 最多5层, 每层20万.

统计: TRADE_EPISODE (initial entry -> final exit) 为 PRIMARY; ENTRY_LAYER 单独输出.
"""
import os, sys, time, gc, pickle
import numpy as np, pandas as pd
from collections import deque

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from round51_audit import prepare_v51
from run_strict_c_math import analytic_Pstar

OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
os.makedirs(OUTDIR, exist_ok=True)
CACHE = os.path.join(OUTDIR, 'independent_replay_per.pkl')

LEVEL_CASH = 200_000.0
MAX_LEVELS = 5
SLIP = 0.001
COMM = 0.00025
MIN_COMM = 5.0
TRANSFER = 0.00001
ADD_GAP = 1  # 加仓间隔交易日

def stamp(d):
    return 0.001 if pd.Timestamp(d) < pd.Timestamp('2023-08-28') else 0.0005

# ============================================================
# 1. PREPARE
# ============================================================
def build_per_stock():
    print('prepare_v51 ...', flush=True)
    t0 = time.time()
    days, D, _eidx, _epx, _eopen, _enav, first_eligible_i, offset = prepare_v51()
    print(f'  days={len(days)} 切片 {days[0].date()}..{days[-1].date()}  ({time.time()-t0:.0f}s)', flush=True)

    # ---- top10_by_date: 当日 valid (上市满60 & 非ST) 成交额 Top10 ----
    print('build top10_by_date ...', flush=True)
    top10_by_date = {}
    for k, d in enumerate(days):
        dd = D[d]
        gi = offset + k
        li = gi - np.array([first_eligible_i.get(tc, 0) for tc in dd['ts']])
        valid = (li >= 0) & ~dd['is_st']
        if not valid.any():
            top10_by_date[d] = set()
            continue
        cand = np.where(valid)[0]
        amt = dd['amount'][cand]
        order = np.argsort(-amt)[:10]
        top10_by_date[d] = set(dd['ts'][cand[order]])

    # ---- per-stock 提取 (从 D 逐日) ----
    print('extract per-stock ...', flush=True)
    all_codes = sorted({tc for d in days for tc in D[d]['ts']})
    FIELDS = ['close', 'open_', 'high', 'low', 'pre_close', 'adj', 'close_adj', 'high_adj',
              'bb_lower', 'bb_upper', 'bb_mid', 'bb_upper_prev', 'is_st', 'is_limit',
              'limit_up_px', 'limit_down_px', 'amount']
    per = {}
    for tc in all_codes:
        cols = {f: [] for f in FIELDS}
        idxs = []
        dates = []
        for k, d in enumerate(days):
            j = D[d]['pos'].get(tc)
            if j is None:
                continue
            dd = D[d]
            idxs.append(k)
            dates.append(d)
            for f in FIELDS:
                cols[f].append(dd[f][j])
        if not idxs:
            continue
        arrs = {f: np.asarray(cols[f], dtype=float) for f in FIELDS}
        arrs['is_st'] = np.asarray(cols['is_st'], dtype=bool)
        arrs['is_limit'] = np.asarray(cols['is_limit'], dtype=bool)
        arrs['idxs'] = np.asarray(idxs, dtype=np.int64)
        arrs['dates'] = dates
        arrs['first_eligible_slice'] = first_eligible_i.get(tc, 0) - offset
        per[tc] = arrs
    print(f'  per-stock 股票数={len(per)}  ({time.time()-t0:.0f}s)', flush=True)
    with open(CACHE, 'wb') as f:
        pickle.dump({'days': days, 'per': per, 'top10_by_date': top10_by_date}, f)
    return days, per, top10_by_date

def load_per():
    if os.path.exists(CACHE):
        with open(CACHE, 'rb') as f:
            d = pickle.load(f)
        return d['days'], d['per'], d['top10_by_date']
    return build_per_stock()

# ============================================================
# 2. REPLAY — 单股状态机
# ============================================================
def replay_one(tc, r, mode, primary, top10_by_date, max_levels=MAX_LEVELS,
               final_settle_close=True):
    """mode: 'dynamic_touch' | 'prev' | 'close_confirm_next'"""
    n = len(r['idxs'])
    pos = None
    pending_buy = False
    pending_add = False
    pending_sell = False
    sig_date = None                # 触发 pending_buy 的信号日 T
    raw_hist = deque(maxlen=19)   # close_adj 最近(含已持仓日, 至前一交易日)
    ep = []

    def close_episode(pos_, m_, d_, sell_price, exit_type):
        amt = sell_price * pos_['shares']
        fee = max(amt * COMM, MIN_COMM) + amt * stamp(d_) + amt * TRANSFER
        proceeds = amt - fee
        pnl = proceeds - pos_['total_cost']
        hold_days = m_ - pos_['entry_m']
        # ENTRY_LAYER 分配: 每层 share_ratio*proceeds - layer_cost
        tot_sh = pos_['shares']
        layer_rows = []
        for (lv, bm, q, cst, bpx) in pos_['layers']:
            ratio = q / tot_sh
            lpnl = ratio * proceeds - cst
            layer_rows.append(dict(ep_ts_code=tc, ep_entry=pos_['entry_date'],
                                   level=lv, buy_m=bm, shares=q, cost=cst, buy_price=bpx,
                                   layer_pnl=lpnl,
                                   layer_return_pct=lpnl / cst * 100 if cst else np.nan))
        ep.append(dict(ts_code=tc, signal_date=pos_['signal_date'], entry_date=pos_['entry_date'],
                       exit_date=str(d_), exit_type=exit_type, levels_used=pos_['levels'],
                       hold_days=hold_days, total_cost=pos_['total_cost'], proceeds=proceeds,
                       pnl=pnl, return_pct=pnl / pos_['total_cost'] * 100,
                       layers=layer_rows))
        return ep[-1]

    for m in range(n):
        i = r['idxs'][m]
        d = r['dates'][m]
        eligible = (i >= r['first_eligible_slice']) and (not r['is_st'][m])

        # ---- OPEN: 昨收挂单 ----
        if pending_sell and pos is not None:
            if r['open_'][m] <= r['limit_down_px'][m]:
                pass  # 开盘跌停卖不出, 顺延
            else:
                sell_price = r['open_'][m] * (1 - SLIP)
                close_episode(pos, m, d, sell_price, 'TAKE_PROFIT_UB')
                pos = None
                pending_sell = False
                pending_add = False
                raw_hist.clear()
        if pos is not None and pending_add:
            if pos['levels'] >= max_levels:
                pending_add = False
            elif r['open_'][m] >= r['limit_up_px'][m]:
                pass  # 开盘涨停买不进, 顺延
            else:
                buy_price = r['open_'][m] * (1 + SLIP)
                qty = int(LEVEL_CASH / buy_price / 100) * 100
                if qty >= 100:
                    amt = buy_price * qty
                    fee = max(amt * COMM, MIN_COMM) + amt * TRANSFER
                    pos['shares'] += qty
                    pos['total_cost'] += amt + fee
                    pos['levels'] += 1
                    pos['last_add'] = i
                    pos['layers'].append((pos['levels'], m, qty, amt + fee, buy_price))
                pending_add = False
        if pos is None and pending_buy:
            if r['open_'][m] >= r['limit_up_px'][m]:
                pass  # 开盘涨停买不进, 顺延
            else:
                buy_price = r['open_'][m] * (1 + SLIP)
                qty = int(LEVEL_CASH / buy_price / 100) * 100
                if qty >= 100:
                    amt = buy_price * qty
                    fee = max(amt * COMM, MIN_COMM) + amt * TRANSFER
                    pos = {'shares': qty, 'total_cost': amt + fee, 'levels': 1,
                           'entry_i': i, 'entry_m': m, 'last_add': i,
                           'entry_date': str(d), 'signal_date': str(sig_date) if sig_date else str(d),
                           'layers': [(1, m, qty, amt + fee, buy_price)]}
                    raw_hist.clear()
                    for mm in range(max(0, m - 19), m):
                        raw_hist.append(r['close_adj'][mm])
                pending_buy = False

        # ---- 盘中 EXIT ----
        if pos is not None and (i - pos['entry_i']) >= 1:
            do_exit = False
            exit_price = None
            if mode == 'dynamic_touch':
                if len(raw_hist) >= 19:
                    x = np.array(list(raw_hist)[-19:], dtype=float)
                    Pstar_adj = analytic_Pstar(x)
                    if Pstar_adj is not None and np.isfinite(Pstar_adj):
                        Pstar_raw = Pstar_adj / r['adj'][m]
                        threshold = np.ceil(Pstar_raw / 0.01) * 0.01
                        if r['high_adj'][m] >= threshold * r['adj'][m]:
                            if r['open_'][m] * r['adj'][m] >= threshold * r['adj'][m]:
                                ref = r['open_'][m]
                            else:
                                ref = threshold
                            if ref > r['limit_down_px'][m]:
                                do_exit = True
                                exit_price = ref * (1 - SLIP)
            elif mode == 'prev':
                bprev = r['bb_upper_prev'][m]
                if not np.isnan(bprev) and r['high_adj'][m] >= bprev:
                    ref = bprev / r['adj'][m]
                    if ref > r['limit_down_px'][m]:
                        do_exit = True
                        exit_price = ref * (1 - SLIP)
            if do_exit:
                close_episode(pos, m, d, exit_price,
                              'TAKE_PROFIT_DYN' if mode == 'dynamic_touch' else 'TAKE_PROFIT_UB')
                pos = None
                pending_sell = False
                pending_add = False
                raw_hist.clear()

        # ---- CLOSE ----
        if pos is not None:
            raw_hist.append(r['close_adj'][m])
            bb_lo = r['bb_lower'][m]
            if mode == 'close_confirm_next':
                if (not np.isnan(r['bb_upper'][m]) and r['close_adj'][m] >= r['bb_upper'][m]):
                    pending_sell = True
                elif (not np.isnan(bb_lo) and r['close_adj'][m] < bb_lo
                      and not r['is_limit'][m] and pos['levels'] < max_levels
                      and (i - pos['last_add']) >= ADD_GAP):
                    pending_add = True
            else:
                if (not np.isnan(bb_lo) and r['close_adj'][m] < bb_lo
                        and not r['is_limit'][m] and pos['levels'] < max_levels
                        and (i - pos['last_add']) >= ADD_GAP):
                    pending_add = True

        # ---- ENTRY 信号 (pos 空 & 无挂单 & eligible) ----
        if pos is None and not pending_buy and eligible:
            ok = (not np.isnan(r['bb_lower'][m]) and r['close_adj'][m] < r['bb_lower'][m]
                  and not r['is_limit'][m])
            if ok and primary:
                ok = tc in top10_by_date.get(d, set())
            if ok:
                pending_buy = True
                sig_date = r['dates'][m]

    # ---- 期末 FINAL_SETTLE (用最后有数据日 close) ----
    if pos is not None and n > 0:
        m_last = n - 1
        sell_price = r['close'][m_last] * (1 - SLIP)
        close_episode(pos, m_last, r['dates'][m_last], sell_price, 'FINAL_SETTLE')
        pos = None
    return ep


# ============================================================
# 3. 主跑
# ============================================================
def run(mode, primary, tag):
    days, per, top10_by_date = load_per()
    print(f'[REPLAY] mode={mode} primary={primary} tag={tag} 股票数={len(per)}', flush=True)
    all_ep = []
    t0 = time.time()
    cnt = 0
    for tc, r in per.items():
        ep = replay_one(tc, r, mode, primary, top10_by_date)
        for e in ep:
            e['_tag'] = tag
        all_ep.extend(ep)
        cnt += 1
        if cnt % 1000 == 0:
            print(f'  {cnt}/{len(per)}  ep累计={len(all_ep)}  {time.time()-t0:.0f}s', flush=True)
    print(f'[REPLAY DONE] {tag}: episodes={len(all_ep)}  ({time.time()-t0:.0f}s)', flush=True)
    return all_ep


def flatten_episodes(eps):
    """episodes list -> DataFrame; 展开 layers"""
    rows = []
    layer_rows = []
    for k, e in enumerate(eps):
        rows.append(dict(episode_id=k, ts_code=e['ts_code'],
                         signal_date=e['signal_date'], entry_date=e['entry_date'],
                         exit_date=e['exit_date'], exit_type=e['exit_type'],
                         levels_used=e['levels_used'], hold_days=e['hold_days'],
                         total_cost=e['total_cost'], proceeds=e['proceeds'],
                         pnl=e['pnl'], return_pct=e['return_pct']))
        for lr in e['layers']:
            layer_rows.append(dict(episode_id=k, **{kk: vv for kk, vv in lr.items() if kk != 'ep_ts_code'}))
    return pd.DataFrame(rows), pd.DataFrame(layer_rows)


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--build', action='store_true')
    ap.add_argument('--primary-dyn', action='store_true')
    ap.add_argument('--primary-prev', action='store_true')
    ap.add_argument('--primary-confirm', action='store_true')
    ap.add_argument('--secondary', action='store_true')
    ap.add_argument('--all', action='store_true')
    a = ap.parse_args()

    if a.build or a.all:
        build_per_stock()
    else:
        load_per()

    if a.primary_dyn or a.all:
        eps = run('dynamic_touch', True, 'PRIMARY_DYN')
        with open(os.path.join(OUTDIR, 'independent_ep_PRIMARY_DYN.pkl'), 'wb') as f:
            pickle.dump(eps, f)
    if a.primary_prev or a.all:
        eps = run('prev', True, 'PRIMARY_PREV')
        with open(os.path.join(OUTDIR, 'independent_ep_PRIMARY_PREV.pkl'), 'wb') as f:
            pickle.dump(eps, f)
    if a.primary_confirm or a.all:
        eps = run('close_confirm_next', True, 'PRIMARY_CONFIRM')
        with open(os.path.join(OUTDIR, 'independent_ep_PRIMARY_CONFIRM.pkl'), 'wb') as f:
            pickle.dump(eps, f)
    if a.secondary or a.all:
        eps = run('dynamic_touch', False, 'SECONDARY_DYN')
        with open(os.path.join(OUTDIR, 'independent_ep_SECONDARY_DYN.pkl'), 'wb') as f:
            pickle.dump(eps, f)
    print('ALL DONE')
