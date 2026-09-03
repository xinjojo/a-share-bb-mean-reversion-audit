"""TRADE PATH QUALITY AUDIT — STRICT_C PRIMARY TOP10
==========================================================
对冻结 PRIMARY 样本(V2A_FROZEN_STRICT Top10, 299笔, 已与冻结引擎 parity 299/299)
做完整"持仓生命轨迹"描述性审计. 不调参 / 不优化止损止盈 / 不开 Validation / 不改 Registry.

每笔 episode 重建:
  A. FIRST_ENTRY_PRICE_PATH : 第一次买入执行价(open*(1+slip))为基准的纯价格路径 (raw close/high/low)
  B. EPISODE_ECONOMIC_NAV   : 多层加仓的真实经济净值 (TWR, 加仓作为外部现金流, 不改变瞬时 NAV)

产出:
  results/trade_path_episode_metrics.csv / _daily_nav / _mae_thresholds / _winner_loser_stats
        / _quantiles / _yearly / _levels / _exit_quality / _eventday_stats / _tail_risk
  figures/*.png (8张)
  TRADE_PATH_QUALITY_AUDIT.md
"""
import os, sys, pickle, time
import numpy as np, pandas as pd
from collections import deque

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT); sys.path.insert(0, REPO)
from round51_audit import prepare_v51, stamp_rate, COMMISSION_RATE, MIN_COMMISSION, TRANSFER_FEE_RATE
from run_strict_c_math import analytic_Pstar
import independent_trade_replay_v2 as v2

OUT = os.path.join(REPO, 'results'); os.makedirs(OUT, exist_ok=True)
FIG = os.path.join(REPO, 'figures'); os.makedirs(FIG, exist_ok=True)
LEVEL_CASH, MAX_LEVELS, SLIP, ADD_GAP = v2.LEVEL_CASH, v2.MAX_LEVELS, v2.SLIP, v2.ADD_GAP
POST_H = [1, 3, 5, 10, 20, 40, 60]


def replay_v2a_path(days, D, first_eligible_i, offset):
    """replay_v2a 的逐行复制 + 路径/加仓/退出后记录."""
    N = len(days)
    pos = {}; pending_buy = []; pending_add = {}; pending_sell = set()
    raw_hist = {}; episodes = []; censored = []; last_close = {}
    episode_seq = [0]

    def sell(tc, d, j, price, exit_type, i):
        p = pos[tc]
        amt = price * p['shares']
        sr = stamp_rate(d, 'historical')
        fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
        proceeds = amt - fee
        pnl = proceeds - p['total_cost']
        # --- 退出日路径数据 (去重: 若已由 CLOSE 循环追加则不再追加) ---
        if j is not None and not (p['path'] and p['path'][-1][0] == i):
            p['path'].append((i, str(d.date()), float(D[d]['close'][j]), float(D[d]['high'][j]), float(D[d]['low'][j])))
        # --- 退出后展望 (exit_i+1 .. +60) ---
        post_ret, post_mfe, post_mae = {}, {}, {}
        for h in POST_H:
            post_ret[h] = post_mfe[h] = post_mae[h] = np.nan
            if i + h >= N:
                continue
            jh = D[days[i + h]]['pos'].get(tc)
            if jh is None:
                continue
            c0 = float(D[days[i + h]]['close'][jh])
            post_ret[h] = (c0 / price - 1) * 100
        # MFE/MAE 在窗口内(有数据的天)
        mfe60, mae60, peakdd60, peak_gain60, peak_retrace = np.nan, np.nan, np.nan, np.nan, np.nan
        closes_after = []
        for h in range(1, 61):
            if i + h >= N:
                break
            jh = D[days[i + h]]['pos'].get(tc)
            if jh is not None:
                closes_after.append(float(D[days[i + h]]['close'][jh]))
        if closes_after:
            arr = np.array(closes_after) / price - 1
            for h in POST_H:
                if h <= len(closes_after):
                    post_mfe[h] = arr[:h].max() * 100
                    post_mae[h] = arr[:h].min() * 100
            mfe60 = arr.max() * 100; mae60 = arr.min() * 100
            peak_gain60 = mfe60
            pk = int(np.argmax(arr))
            if pk < len(arr) - 1:
                retr = (arr[pk] - arr[pk + 1:].min()) / (1 + arr[pk])
                peak_retrace = retr * 100
        episode_seq[0] += 1
        ep = dict(episode_id=episode_seq[0], ts_code=tc, signal_date=p['signal_date'],
                  entry_date=p['entry_date'], exit_date=str(d.date()), exit_type=exit_type,
                  levels_used=p['levels'], hold_days=i - p['entry_i'], total_cost=p['total_cost'],
                  proceeds=proceeds, pnl=pnl, return_pct=pnl / p['total_cost'] * 100,
                  entry_i=p['entry_i'], exit_i=i, entry_exec_raw=p['entry_exec_raw'],
                  entry_shares=p['entry_shares'], entry_fee=p['entry_fee'],
                  adds=p['adds'], path=p['path'], exit_sell_raw=price, exit_shares=p['shares'],
                  post_ret=post_ret, post_mfe=post_mfe, post_mae=post_mae,
                  post_mfe60=mfe60, post_mae60=mae60, post_peak_retrace60=peak_retrace)
        episodes.append(ep)
        del pos[tc]; raw_hist.pop(tc, None)
        return ep

    def init_raw_hist(tc, i):
        hist = deque()
        for k in range(1, 20):
            if i - k < 0:
                break
            dk = days[i - k]; jk = D[dk]['pos'].get(tc)
            if jk is not None:
                hist.appendleft(float(D[dk]['close_adj'][jk]))
        raw_hist[tc] = deque(hist, 19)
        return len(hist)

    for i, d in enumerate(days):
        dd = D[d]
        # ---- OPEN: pending_sell ----
        for tc in list(pending_sell):
            if tc not in pos:
                pending_sell.discard(tc); continue
            j = dd['pos'].get(tc)
            if j is None:
                pending_sell.discard(tc); continue
            if dd['open_'][j] <= dd['limit_down_px'][j]:
                continue
            sell(tc, d, j, dd['open_'][j] * (1 - SLIP), 'TAKE_PROFIT_UB', i)
            pending_sell.discard(tc)
        # ---- OPEN: pending_add ----
        for tc in list(pending_add):
            p = pos.get(tc)
            if p is None:
                pending_add.pop(tc, None); continue
            j = dd['pos'].get(tc)
            if j is None:
                pending_add.pop(tc, None); continue     # CANCEL
            if p['levels'] >= MAX_LEVELS:
                pending_add.pop(tc, None); continue
            if dd['open_'][j] >= dd['limit_up_px'][j]:
                continue
            buy_price = dd['open_'][j] * (1 + SLIP)
            qty = int(LEVEL_CASH / buy_price / 100) * 100
            if qty >= 100:
                amt = buy_price * qty
                fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * TRANSFER_FEE_RATE
                p['shares'] += qty; p['total_cost'] += amt + fee; p['levels'] += 1
                p['last_add_i'] = i
                p['adds'].append((i, buy_price, qty, fee, amt + fee))
            pending_add.pop(tc, None)
        # ---- OPEN: pending_buy ----
        if pending_buy:
            held = set(pos.keys())
            for pb in list(pending_buy):
                tc = pb['ts_code']
                if tc in held:
                    pending_buy.remove(pb); continue
                j = dd['pos'].get(tc)
                if j is None:
                    pending_buy.remove(pb); continue     # CANCEL
                if dd['open_'][j] >= dd['limit_up_px'][j]:
                    continue
                buy_price = dd['open_'][j] * (1 + SLIP)
                qty = int(LEVEL_CASH / buy_price / 100) * 100
                if qty >= 100:
                    amt = buy_price * qty
                    fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * TRANSFER_FEE_RATE
                    p = dict(shares=qty, total_cost=amt + fee, levels=1, entry_i=i, last_add_i=i,
                             entry_date=str(d.date()), signal_date=pb['signal_date'],
                             entry_exec_raw=buy_price, entry_shares=qty, entry_fee=fee,
                             adds=[], path=[])
                    pos[tc] = p
                    init_raw_hist(tc, i)
                pending_buy.remove(pb)
        # ---- 盘中退出: dynamic_touch ----
        for tc in list(pos.keys()):
            p = pos[tc]
            j = dd['pos'].get(tc)
            if j is None:
                continue
            if (i - p['entry_i']) < 1:
                continue
            hist = raw_hist.get(tc)
            if hist is None or len(hist) < 19:
                continue
            adjT = dd['adj'][j]
            x = np.array(list(hist)[-19:], dtype=float)
            Pstar_adj = analytic_Pstar(x)
            if Pstar_adj is None or not np.isfinite(Pstar_adj):
                continue
            Pstar_raw = Pstar_adj / adjT
            threshold = np.ceil(Pstar_raw / 0.01) * 0.01
            trig = dd['high_adj'][j] >= threshold * adjT
            if not trig:
                continue
            if dd['open_'][j] * adjT >= threshold * adjT:
                ref = dd['open_'][j]
            else:
                ref = threshold
            if ref <= dd['limit_down_px'][j]:
                continue
            sell(tc, d, j, ref * (1 - SLIP), 'TAKE_PROFIT_DYN', i)
        # ---- CLOSE ----
        for tc in list(pos.keys()):
            p = pos[tc]
            j = dd['pos'].get(tc)
            if j is None:
                last_close[tc] = last_close.get(tc, p['total_cost'] / p['shares'])
                continue
            close = dd['close'][j]
            last_close[tc] = close
            p['path'].append((i, str(d.date()), float(close), float(dd['high'][j]), float(dd['low'][j])))
            raw_hist.setdefault(tc, deque([], 19)).append(float(dd['close_adj'][j]))
            bb_lo = dd['bb_lower'][j]
            if (not np.isnan(bb_lo) and dd['close_adj'][j] < bb_lo
                    and not dd['is_limit'][j] and p['levels'] < MAX_LEVELS
                    and (i - p['last_add_i']) >= ADD_GAP):
                pending_add[tc] = True
        # ---- 新买信号 ----
        gi = offset + i
        li = gi - np.array([first_eligible_i.get(t, 0) for t in dd['ts']])
        valid = (li >= 0) & ~dd['is_st']
        if valid.any():
            cand_idx = np.where(valid)[0]
            amt = dd['amount'][cand_idx]
            order = np.argsort(-amt)[:10]
            held = set(pos.keys()) | pending_sell
            for k in order:
                j = cand_idx[k]
                tc = dd['ts'][j]
                if tc in held or any(x['ts_code'] == tc for x in pending_buy):
                    continue
                if (not np.isnan(dd['bb_lower'][j]) and dd['close_adj'][j] < dd['bb_lower'][j]
                        and not dd['is_limit'][j]):
                    pending_buy.append({'ts_code': tc, 'signal_date': str(d.date())})
    # ---- 期末 ----
    d_last = days[-1]; dd_last = D[d_last]
    for tc in list(pos.keys()):
        j = dd_last['pos'].get(tc)
        if j is not None:
            sell(tc, d_last, j, dd_last['close'][j] * (1 - SLIP), 'FINAL_SETTLE', N - 1)
        else:
            p = pos[tc]
            mark = last_close.get(tc, p['total_cost'] / p['shares'])
            censored.append(dict(ts_code=tc, signal_date=p['signal_date'], entry_date=p['entry_date'],
                                 levels_used=p['levels'], total_cost=p['total_cost'], last_close_mark=mark,
                                 last_mark_pnl=mark * p['shares'] - p['total_cost'],
                                 last_mark_return_pct=(mark * p['shares'] / p['total_cost'] - 1) * 100))
            del pos[tc]
    print(f'[PATH REPLAY DONE] episodes={len(episodes)} censored={len(censored)}')
    return episodes, censored


# ============================================================
# 路径指标
# ============================================================
def longest_underwater(nav):
    """nav: array of (nav-1) decimal. 返回最长连续 <0 的运行长度(观测日)."""
    if len(nav) == 0:
        return 0
    under = nav < 0
    best = cur = 0
    for u in under:
        cur = cur + 1 if u else 0
        best = max(best, cur)
    return best


def twr_nav(ep):
    """EPISODE_ECONOMIC_NAV — TWR, 加仓为外部现金流(仅价格与费用改变 NAV)."""
    path = ep['path']
    adds = ep['adds']
    exit_i = ep['exit_i']
    shares = ep['entry_shares']
    navs = [1.0]
    prev_close = None
    for k, (i, dt_, c, h, l) in enumerate(path):
        if prev_close is None:
            r = c / ep['entry_exec_raw'] - 1
        else:
            r = c / prev_close - 1
        for (ai, aexec, aqty, afee, acash) in adds:
            if ai == i:
                EMV = (shares + aqty) * c
                CF = aqty * aexec + afee
                r = (EMV - CF) / (shares * prev_close) - 1
                shares += aqty
        if i == exit_i:
            r = ep['proceeds'] / (shares * prev_close) - 1
            shares = 0
        navs.append(navs[-1] * (1 + r))
        prev_close = c
    return np.array(navs)


def ep_metrics(ep):
    path = ep['path']
    closes = np.array([c for _, _, c, _, _ in path], dtype=float)
    highs = np.array([h for _, _, _, h, _ in path], dtype=float)
    lows = np.array([l for _, _, _, _, l in path], dtype=float)
    base = ep['entry_exec_raw']
    nav_c = closes / base - 1
    nav_h = highs / base - 1
    nav_l = lows / base - 1
    mae_c = float(nav_c.min() * 100); mae_i = float(nav_l.min() * 100)
    mfe_c = float(nav_c.max() * 100); mfe_i = float(nav_h.max() * 100)
    final_pp = float((ep['exit_sell_raw'] / base - 1) * 100)
    i_mae = int(np.argmin(nav_c)); i_mfe = int(np.argmax(nav_c))
    ge0 = np.where(nav_c >= 0)[0]
    never_under = len(ge0) == len(nav_c) and (len(nav_c) == 0 or nav_c[0] >= 0 and not (nav_c < 0).any())
    be = int(ge0[0]) if len(ge0) else -1
    max_under = longest_underwater(nav_c)
    if max_under == 0:
        ttbe = 0; recov = 0
    else:
        ttbe = be if be >= 0 else np.nan
        recov = (be - i_mae) if (be >= 0 and be >= i_mae) else np.nan
    # economic NAV
    enav = twr_nav(ep)
    e_mae = float((enav.min() - 1) * 100); e_mfe = float((enav.max() - 1) * 100)
    e_exit = float((enav[-1] - 1) * 100)
    e_under = longest_underwater(enav - 1)
    # exit quality
    sr = ep['return_pct']
    giveback_i = mfe_i - sr; giveback_c = mfe_c - sr
    cap_c = (sr - mae_c) / (mfe_c - mae_c) if (mfe_c - mae_c) > 0 else np.nan
    cap_i = (sr - mae_i) / (mfe_i - mae_i) if (mfe_i - mae_i) > 0 else np.nan
    m = dict(episode_id=ep['episode_id'], ts_code=ep['ts_code'], pnl=ep['pnl'], signal_date=ep['signal_date'],
             entry_date=ep['entry_date'], exit_date=ep['exit_date'], exit_type=ep['exit_type'],
             levels_used=ep['levels_used'], total_cost=ep['total_cost'], simple_return_pct=sr,
             hold_days=ep['hold_days'],
             MAE_close_pct=mae_c, MAE_intraday_pct=mae_i, MFE_close_pct=mfe_c, MFE_intraday_pct=mfe_i,
             final_price_path_return_pct=final_pp, time_to_MAE_days=i_mae, time_to_MFE_days=i_mfe,
             time_to_break_even_days=ttbe, max_underwater_duration_days=max_under,
             first_recovery_after_MAE_days=recov,
             economic_MAE_pct=e_mae, economic_MFE_pct=e_mfe, economic_exit_nav=e_exit,
             economic_max_underwater_days=e_under,
             giveback_intraday_pct=giveback_i, giveback_close_pct=giveback_c,
             capture_ratio_close=cap_c, capture_ratio_intraday=cap_i,
             n_path_days=len(path))
    for h in POST_H:
        m[f'post_ret_{h}d'] = ep['post_ret'][h]
        m[f'post_mfe_{h}d'] = ep['post_mfe'][h]
        m[f'post_mae_{h}d'] = ep['post_mae'][h]
    m['post_peak_retrace60'] = ep['post_peak_retrace60']
    return m


def daily_nav_rows(eps, mdf):
    rows = []
    idxmap = {e['episode_id']: e for e in eps}
    for _, r in mdf.iterrows():
        e = idxmap[int(r['episode_id'])]
        base = e['entry_exec_raw']
        enav = twr_nav(e)
        for k, (i, dt_, c, h, l) in enumerate(e['path']):
            rows.append(dict(episode_id=e['episode_id'], ts_code=e['ts_code'], day_index=k,
                             date=dt_,
                             nav_close=c / base, nav_high=h / base, nav_low=l / base,
                             econ_nav=float(enav[k + 1])))
    return pd.DataFrame(rows)


def main():
    print('prepare_v51 ...', flush=True)
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51()
    print(f'  days={len(days)} {days[0].date()}..{days[-1].date()}', flush=True)
    eps, cens = replay_v2a_path(days, D, first_eligible_i, offset)

    # ---- parity assert: 必须与已提交 V2A pkl 完全一致 ----
    with open(os.path.join(OUT, 'independent_v2a_episodes.pkl'), 'rb') as f:
        ref = pickle.load(f)
    ref_eps = ref['episodes']
    assert len(ref_eps) == len(eps) == 299, f'episode count mismatch: {len(ref_eps)} vs {len(eps)}'
    rk = {(e['ts_code'], e['signal_date']): e for e in ref_eps}
    mism = 0
    for e in eps:
        r = rk.get((e['ts_code'], e['signal_date']))
        if r is None or r['exit_date'] != e['exit_date'] or r['exit_type'] != e['exit_type'] \
                or abs(r['return_pct'] - e['return_pct']) > 1e-6 or r['levels_used'] != e['levels_used']:
            mism += 1
    assert mism == 0, f'PARITY FAIL: {mism} mismatched episodes vs frozen V2A pkl'
    print(f'[PARITY] path-replay vs V2A pkl: 299/299 一致 ✓ (样本冻结确认)')
    global _idx_by_id
    _idx_by_id = {e['episode_id']: e for e in eps}

    mdf = pd.DataFrame([ep_metrics(e) for e in eps])
    mdf.to_csv(os.path.join(OUT, 'trade_path_episode_metrics.csv'), index=False)

    # ---- daily nav CSV ----
    dnav = daily_nav_rows(eps, mdf)
    dnav.to_csv(os.path.join(OUT, 'trade_path_daily_nav.csv'), index=False)

    # ---- winner/loser ----
    mdf['grp'] = np.where(mdf['simple_return_pct'] > 0, 'WINNER', 'LOSER')
    wl = []
    for g in ['WINNER', 'LOSER']:
        d = mdf[mdf['grp'] == g]
        wl.append(dict(group=g, n=len(d), ret_mean=d['simple_return_pct'].mean(),
                       ret_median=d['simple_return_pct'].median(),
                       MAE_intraday_p50=d['MAE_intraday_pct'].quantile(.5),
                       MAE_intraday_p75=d['MAE_intraday_pct'].quantile(.75),
                       MAE_intraday_p90=d['MAE_intraday_pct'].quantile(.9),
                       MAE_intraday_p95=d['MAE_intraday_pct'].quantile(.95),
                       MAE_intraday_p99=d['MAE_intraday_pct'].quantile(.99),
                       MAE_close_p50=d['MAE_close_pct'].quantile(.5),
                       MFE_intraday_p50=d['MFE_intraday_pct'].quantile(.5),
                       MFE_intraday_p75=d['MFE_intraday_pct'].quantile(.75),
                       MFE_intraday_p90=d['MFE_intraday_pct'].quantile(.9),
                       hold_p50=d['hold_days'].median(), hold_mean=d['hold_days'].mean(),
                       underwater_p50=d['max_underwater_duration_days'].median(),
                       ttbe_p50=d['time_to_break_even_days'].median(),
                       recov_p50=d['first_recovery_after_MAE_days'].median(),
                       giveback_p50=d['giveback_intraday_pct'].median()))
    pd.DataFrame(wl).to_csv(os.path.join(OUT, 'trade_path_winner_loser_stats.csv'), index=False)

    # ---- MAE→win prob ----
    thr = [-2, -3, -5, -7.5, -10, -12.5, -15, -20, -25, -30, -40, -50]
    rows = []
    for t in thr:
        d = mdf[mdf['MAE_intraday_pct'] <= t]
        rows.append(dict(threshold_pct=t, n_crossed=len(d),
                         win_rate=d['simple_return_pct'].gt(0).mean() * 100 if len(d) else np.nan,
                         mean_final_return=d['simple_return_pct'].mean() if len(d) else np.nan,
                         median_final_return=d['simple_return_pct'].median() if len(d) else np.nan,
                         mean_recovery_days=d['first_recovery_after_MAE_days'].mean() if len(d) else np.nan))
    bins = [(0, -5), (-5, -10), (-10, -15), (-15, -20), (-20, -30), (-30, -999)]
    for lo, hi in bins:
        if hi == -999:
            d = mdf[mdf['MAE_intraday_pct'] <= lo]
            lab = f'<={lo}'
        else:
            d = mdf[(mdf['MAE_intraday_pct'] > hi) & (mdf['MAE_intraday_pct'] <= lo)]
            lab = f'({lo},{hi}]'
        rows.append(dict(threshold_pct=lab, n_crossed=len(d),
                         win_rate=d['simple_return_pct'].gt(0).mean() * 100 if len(d) else np.nan,
                         mean_final_return=d['simple_return_pct'].mean() if len(d) else np.nan,
                         median_final_return=d['simple_return_pct'].median() if len(d) else np.nan,
                         mean_recovery_days=d['first_recovery_after_MAE_days'].mean() if len(d) else np.nan))
    pd.DataFrame(rows).to_csv(os.path.join(OUT, 'trade_path_mae_thresholds.csv'), index=False)

    # ---- winner MAE 分布 ----
    w = mdf[mdf['grp'] == 'WINNER']
    qp = [1, 5, 10, 25, 50, 75, 90, 95, 99]
    wmae = pd.DataFrame({'pct': qp,
                         'MAE_intraday': [w['MAE_intraday_pct'].quantile(q / 100) for q in qp],
                         'MAE_close': [w['MAE_close_pct'].quantile(q / 100) for q in qp]})
    crossed = {t: float((w['MAE_intraday_pct'] <= t).mean() * 100) for t in [-5, -10, -15, -20, -25, -30]}
    print('[WINNER MAE 分布]')
    print(wmae.round(2).to_string(index=False))
    print('  winner 曾跌破比例:', {k: round(v, 1) for k, v in crossed.items()})

    # ---- quantiles (calendar + normalized) ----
    # calendar: day 0,1,2,3,5,10,20,30,40,60,90,120
    cal_days = [0, 1, 2, 3, 5, 10, 20, 30, 40, 60, 90, 120]
    cal_rows = []
    for cd in cal_days:
        vals = []
        for _, r in mdf.iterrows():
            e = idx_by_id(int(r['episode_id']))
            if e['hold_days'] < cd or cd >= len(e['path']):
                continue
            navc = e['path'][cd][2] / e['entry_exec_raw']
            vals.append(navc)
        if not vals:
            continue
        a = np.array(vals)
        cal_rows.append(dict(day=cd, n_alive=len(a), p5=np.percentile(a, 5), p10=np.percentile(a, 10),
                             p25=np.percentile(a, 25), p50=np.percentile(a, 50), p75=np.percentile(a, 75),
                             p90=np.percentile(a, 90), p95=np.percentile(a, 95), mean=a.mean()))
    # normalized life path
    norm_rows = []
    for f in range(0, 101, 10):
        vals = []
        for _, r in mdf.iterrows():
            e = idx_by_id(int(r['episode_id']))
            npd = len(e['path'])
            if npd == 0:
                continue
            pos = min(f / 100 * (npd - 1), npd - 1)
            k0 = int(np.floor(pos)); k1 = min(k0 + 1, npd - 1)
            frac = pos - k0
            c0 = e['path'][k0][2] / e['entry_exec_raw']; c1 = e['path'][k1][2] / e['entry_exec_raw']
            vals.append(c0 * (1 - frac) + c1 * frac)
        a = np.array(vals)
        norm_rows.append(dict(life_pct=f, n=len(a), p10=np.percentile(a, 10), p25=np.percentile(a, 25),
                              p50=np.percentile(a, 50), p75=np.percentile(a, 75), p90=np.percentile(a, 90),
                              mean=a.mean()))
    pd.DataFrame(cal_rows).to_csv(os.path.join(OUT, 'trade_path_quantiles.csv'), index=False)
    pd.DataFrame(norm_rows).to_csv(os.path.join(OUT, 'trade_path_quantiles_norm.csv'), index=False)

    # ---- yearly ----
    mdf['entry_year'] = pd.to_datetime(mdf['entry_date']).dt.year
    yrows = []
    for y, d in mdf.groupby('entry_year'):
        yrows.append(dict(year=y, n=len(d), ret_mean=d['simple_return_pct'].mean(),
                          ret_median=d['simple_return_pct'].median(),
                          mae_p50=d['MAE_intraday_pct'].quantile(.5),
                          mae_p90=d['MAE_intraday_pct'].quantile(.9),
                          mae_p95=d['MAE_intraday_pct'].quantile(.95),
                          mfe_p50=d['MFE_intraday_pct'].quantile(.5),
                          hold_median=d['hold_days'].median(), under_median=d['max_underwater_duration_days'].median(),
                          ttbe_median=d['time_to_break_even_days'].median(),
                          giveback_median=d['giveback_intraday_pct'].median(),
                          win_rate=d['simple_return_pct'].gt(0).mean() * 100))
    pd.DataFrame(yrows).to_csv(os.path.join(OUT, 'trade_path_yearly.csv'), index=False)

    # ---- levels ----
    lrows = []
    for lv, d in mdf.groupby('levels_used'):
        lrows.append(dict(levels_used=lv, n=len(d), ret_mean=d['simple_return_pct'].mean(),
                          ret_median=d['simple_return_pct'].median(), win_rate=d['simple_return_pct'].gt(0).mean() * 100,
                          mae_median=d['MAE_intraday_pct'].median(), mfe_median=d['MFE_intraday_pct'].median(),
                          econ_mae_median=d['economic_MAE_pct'].median(), hold_median=d['hold_days'].median()))
    pd.DataFrame(lrows).to_csv(os.path.join(OUT, 'trade_path_levels.csv'), index=False)

    # ---- exit quality ----
    prof = mdf[mdf['simple_return_pct'] > 0]
    eq = []
    eq.append(dict(metric='n_profitable', value=len(prof)))
    for lab, cond in [('post5D_mfe_gt3pct', (prof['post_mfe_5d'] > 3).mean() * 100),
                      ('post5D_mfe_gt5pct', (prof['post_mfe_5d'] > 5).mean() * 100),
                      ('post10D_mfe_gt5pct', (prof['post_mfe_10d'] > 5).mean() * 100),
                      ('post20D_mfe_gt10pct', (prof['post_mfe_20d'] > 10).mean() * 100),
                      ('post40D_mfe_gt15pct', (prof['post_mfe_40d'] > 15).mean() * 100),
                      ('post60D_peak_retrace_gt50', (prof['post_peak_retrace60'] > 50).mean() * 100 if len(prof) else np.nan)]:
        eq.append(dict(metric=lab, value=float(cond)))
    # 全体退出质量
    eq.append(dict(metric='median_giveback_intraday', value=float(mdf['giveback_intraday_pct'].median())))
    eq.append(dict(metric='median_capture_ratio_intraday', value=float(mdf['capture_ratio_intraday'].median())))
    eq.append(dict(metric='median_post60D_mfe', value=float(mdf['post_mfe_60d'].median())))
    eq.append(dict(metric='mean_post60D_mfe', value=float(mdf['post_mfe_60d'].mean())))
    eq.append(dict(metric='pct_post60D_mfe_gt0', value=float((mdf['post_mfe_60d'] > 0).mean() * 100)))
    pd.DataFrame(eq).to_csv(os.path.join(OUT, 'trade_path_exit_quality.csv'), index=False)

    # ---- event-day stats + bootstrap ----
    s = mdf.copy(); s['sd'] = pd.to_datetime(s['signal_date'])
    daily = s.groupby('sd')['simple_return_pct'].mean()
    import statsmodels.api as sm
    y = daily.to_numpy(); n_d = len(y)
    K = int(np.floor(4 * (n_d / 100) ** (2 / 9))); K = max(0, min(K, n_d - 2))
    res = sm.OLS(y, np.ones((n_d, 1))).fit(cov_type='HAC', cov_kwds={'maxlags': K})
    rng = np.random.default_rng(42)
    B = 5000
    # episode-level bootstrap (描述性, 已知非严格独立)
    eb = np.empty(B); 
    r_ep = mdf['simple_return_pct'].to_numpy()
    N_ep = len(r_ep)
    for b in range(B):
        eb[b] = r_ep[rng.integers(0, N_ep, N_ep)].mean()
    # event-day block bootstrap
    db = np.empty(B); L = 21; nb = int(np.ceil(n_d / L))
    for b in range(B):
        st = rng.integers(0, n_d, size=nb); idx = np.empty(nb * L, dtype=np.int64)
        for jj, ss in enumerate(st):
            idx[jj * L:(jj + 1) * L] = np.arange(ss, ss + L) % n_d
        db[b] = y[idx[:n_d]].mean()
    ed_stat = dict(n_event_days=n_d, daily_mean=daily.mean(), daily_median=daily.median(),
                   daily_positive_rate=(daily > 0).mean() * 100, hac_t=float(res.tvalues[0]),
                   hac_ci_lo=float(daily.mean() - 1.96 * res.bse[0]), hac_ci_hi=float(daily.mean() + 1.96 * res.bse[0]),
                   episode_boot_ci_lo=float(np.percentile(eb, 2.5)), episode_boot_ci_hi=float(np.percentile(eb, 97.5)),
                   eventday_boot_ci_lo=float(np.percentile(db, 2.5)), eventday_boot_ci_hi=float(np.percentile(db, 97.5)),
                   eventday_boot_p_nonpos=float((db <= 0).mean() * 100),
                   mean_final_ret=mdf['simple_return_pct'].mean(), median_final_ret=mdf['simple_return_pct'].median(),
                   mean_MAE=mdf['MAE_intraday_pct'].mean(), median_MAE=mdf['MAE_intraday_pct'].median(),
                   mean_MFE=mdf['MFE_intraday_pct'].mean(), median_MFE=mdf['MFE_intraday_pct'].median())
    pd.DataFrame([ed_stat]).to_csv(os.path.join(OUT, 'trade_path_eventday_stats.csv'), index=False)

    # ---- tail risk ----
    worst20 = mdf.nsmallest(20, 'MAE_intraday_pct')
    tail_rows = []
    total_pnl = mdf['total_cost'].sum() * 0 + mdf['pnl'].sum()
    for qlab, q in [('bottom_1pct', 0.01), ('bottom_5pct', 0.05), ('bottom_10pct', 0.10)]:
        nq = max(1, int(np.ceil(len(mdf) * q)))
        dq = mdf.nsmallest(nq, 'simple_return_pct')
        tail_rows.append(dict(quantile=qlab, n=nq, pnl_sum=dq['pnl'].sum(),
                              pct_of_total_pnl=dq['pnl'].sum() / total_pnl * 100 if total_pnl else np.nan,
                              mean_ret=dq['simple_return_pct'].mean(), mean_mae=dq['MAE_intraday_pct'].mean()))
    pd.DataFrame(tail_rows).to_csv(os.path.join(OUT, 'trade_path_tail_risk.csv'), index=False)
    worst20[['episode_id', 'ts_code', 'MAE_intraday_pct', 'simple_return_pct', 'MFE_intraday_pct',
             'hold_days', 'levels_used', 'first_recovery_after_MAE_days', 'exit_type']].to_csv(
        os.path.join(OUT, 'trade_path_tail_risk_worst20.csv'), index=False)

    # ---- 描述统计 ----
    desc_cols = ['simple_return_pct', 'MAE_intraday_pct', 'MAE_close_pct', 'MFE_intraday_pct',
                 'MFE_close_pct', 'giveback_intraday_pct', 'hold_days', 'max_underwater_duration_days']
    dstat = mdf[desc_cols].describe(percentiles=[.01, .05, .1, .25, .5, .75, .9, .95, .99]).T
    dstat.to_csv(os.path.join(OUT, 'trade_path_desc_stats.csv'))
    print('\n[DESC STATS]')
    print(dstat.round(2).to_string())

    # ---- 总结输出 ----
    print('\n=== Q1..Q10 HEADLINE ===')
    print(f"Q1 median MAE_intraday: {mdf['MAE_intraday_pct'].median():.2f}%  mean: {mdf['MAE_intraday_pct'].mean():.2f}%")
    wq = mdf[mdf['grp'] == 'WINNER']
    print(f"Q2 MAE P50/P75/P90/P95: {mdf['MAE_intraday_pct'].quantile(.5):.2f}/{mdf['MAE_intraday_pct'].quantile(.75):.2f}/{mdf['MAE_intraday_pct'].quantile(.9):.2f}/{mdf['MAE_intraday_pct'].quantile(.95):.2f}")
    print(f"Q3 winner P95 MAE_intraday: {wq['MAE_intraday_pct'].quantile(.95):.2f}%")
    for t in [-10, -15, -20, -30]:
        d = mdf[mdf['MAE_intraday_pct'] <= t]
        wr = d['simple_return_pct'].gt(0).mean() * 100 if len(d) else np.nan
        print(f"Q4 MAE<={t}%: n={len(d)} win={wr:.1f}%")
    print(f"Q5 median MFE_intraday: {mdf['MFE_intraday_pct'].median():.2f}%")
    print(f"Q6 median actual exit: {mdf['simple_return_pct'].median():.2f}%  mean: {mdf['simple_return_pct'].mean():.2f}%")
    print(f"Q7 median giveback_intraday: {mdf['giveback_intraday_pct'].median():.2f}%")
    print(f"Q7b median capture_ratio_intraday: {mdf['capture_ratio_intraday'].median():.3f}")
    print(f"Q7c median underwater days: {mdf['max_underwater_duration_days'].median():.1f}")

    # ---- figures ----
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    make_figs(mdf, eps)

    print('\nALL PATH AUDIT DONE')


def idx_by_id(eid):
    return _idx_by_id[eid]


_idx_by_id = {}


def make_figs(mdf, eps):
    global _idx_by_id
    _idx_by_id = {e['episode_id']: e for e in eps}
    import matplotlib.pyplot as plt
    # 1. quantile band (calendar path)
    cal = pd.read_csv(os.path.join(OUT, 'trade_path_quantiles.csv'))
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.fill_between(cal['day'], cal['p10'], cal['p90'], alpha=.2, color='steelblue', label='P10-P90')
    ax.fill_between(cal['day'], cal['p25'], cal['p75'], alpha=.35, color='steelblue', label='P25-P75')
    ax.plot(cal['day'], cal['p50'], color='navy', lw=2, label='P50')
    ax.axhline(1.0, color='gray', ls='--', lw=1)
    ax.set_xlabel('holding day'); ax.set_ylabel('NAV (first-entry price path)')
    ax.set_title('FIRST_ENTRY_PRICE_PATH quantile band (n_alive at each day)')
    ax.legend(); fig.tight_layout(); fig.savefig(os.path.join(FIG, 'trade_path_quantile_band.png'), dpi=120)
    plt.close(fig)
    # 2. MAE dist winner vs loser
    fig, ax = plt.subplots(figsize=(9, 6))
    for g, c in [('WINNER', 'green'), ('LOSER', 'red')]:
        d = mdf[mdf['grp'] == g]['MAE_intraday_pct']
        ax.hist(d, bins=40, alpha=.5, color=c, label=f'{g} (n={len(d)})')
    ax.axvline(mdf['MAE_intraday_pct'].median(), color='black', ls='--', label='all median')
    ax.set_xlabel('MAE_intraday %'); ax.set_title('MAE distribution: winner vs loser'); ax.legend()
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 'mae_distribution_winner_loser.png'), dpi=120); plt.close(fig)
    # 3. MAE vs final return scatter
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.scatter(mdf['MAE_intraday_pct'], mdf['simple_return_pct'], s=14, alpha=.5,
               c=np.where(mdf['grp'] == 'WINNER', 'green', 'red'))
    ax.axhline(0, color='gray', ls='--'); ax.axvline(-10, color='orange', ls='--', lw=1)
    ax.set_xlabel('MAE_intraday %'); ax.set_ylabel('final return %'); ax.set_title('MAE vs final return')
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 'mae_vs_final_return.png'), dpi=120); plt.close(fig)
    # 4. MAE threshold win prob
    thr = pd.read_csv(os.path.join(OUT, 'trade_path_mae_thresholds.csv'))
    t = thr[pd.to_numeric(thr['threshold_pct'], errors='coerce').notna()].copy()
    t['x'] = pd.to_numeric(t['threshold_pct'])
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.plot(t['x'], t['win_rate'], 'o-', color='darkblue')
    ax.set_xlabel('MAE threshold (ever reached ≤ x%)'); ax.set_ylabel('P(win) %')
    ax.set_title('P(win | trade ever reached MAE ≤ x)'); ax.grid(alpha=.3)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 'mae_threshold_win_probability.png'), dpi=120); plt.close(fig)
    # 5. MFE vs actual return
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.scatter(mdf['MFE_intraday_pct'], mdf['simple_return_pct'], s=14, alpha=.5,
               c=np.where(mdf['grp'] == 'WINNER', 'green', 'red'))
    mm = max(mdf['MFE_intraday_pct'].max(), mdf['simple_return_pct'].max())
    ax.plot([0, mm], [0, mm], color='gray', ls='--', label='45°')
    ax.set_xlabel('MFE_intraday %'); ax.set_ylabel('actual return %'); ax.set_title('MFE vs actual return (giveback)')
    ax.legend(); fig.tight_layout(); fig.savefig(os.path.join(FIG, 'mfe_vs_actual_return.png'), dpi=120); plt.close(fig)
    # 6. post-exit opportunity
    fig, ax = plt.subplots(figsize=(9, 6))
    hs = [1, 3, 5, 10, 20, 40, 60]
    med = [mdf[f'post_mfe_{h}d'].median() for h in hs]
    mean = [mdf[f'post_mfe_{h}d'].mean() for h in hs]
    medr = [mdf[f'post_ret_{h}d'].median() for h in hs]
    ax.plot(hs, med, 'o-', label='median post-exit MFE')
    ax.plot(hs, mean, 's--', label='mean post-exit MFE')
    ax.plot(hs, medr, '^:', label='median post-exit close return')
    ax.axhline(0, color='gray', ls='--')
    ax.set_xlabel('days after exit'); ax.set_ylabel('% (vs exit price)')
    ax.set_title('POST-EXIT OPPORTUNITY (all 299)'); ax.legend()
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 'post_exit_opportunity.png'), dpi=120); plt.close(fig)
    # 7. underwater duration dist
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.hist(mdf['max_underwater_duration_days'], bins=40, color='steelblue', alpha=.8)
    ax.set_xlabel('max underwater duration (trading days)'); ax.set_title('Underwater duration distribution')
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 'underwater_duration_distribution.png'), dpi=120); plt.close(fig)
    # 8. levels vs quality
    lv = pd.read_csv(os.path.join(OUT, 'trade_path_levels.csv'))
    fig, ax = plt.subplots(figsize=(9, 6))
    x = lv['levels_used']
    ax.bar(x - .15, lv['ret_mean'], width=.3, label='mean return%', color='steelblue')
    ax.bar(x + .15, lv['mae_median'], width=.3, label='median MAE%', color='coral')
    ax2 = ax.twinx()
    ax2.plot(x, lv['win_rate'], 'o-', color='green', label='win rate%')
    ax.set_xticks(x); ax.set_xlabel('levels_used'); ax.set_ylabel('%')
    ax.set_title('Levels vs trade quality'); ax.legend(loc='upper left'); ax2.legend(loc='upper right')
    fig.tight_layout(); fig.savefig(os.path.join(FIG, 'levels_vs_quality.png'), dpi=120); plt.close(fig)
    print(f'[FIGS] saved 8 PNG to {FIG}')


if __name__ == '__main__':
    main()
