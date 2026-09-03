"""
==========================================================
FULL-MARKET TRADE PATH EXPANSION — SECONDARY ALL ELIGIBLE + PRIMARY TOP10 BENCHMARK
==========================================================
把 PRIMARY Top10 Trade Path Audit(冻结 V2A_FROZEN_STRICT, 299笔) 扩展到
SECONDARY 全市场 eligible oversold 大样本(同一冻结语义, 唯一差异=无 Top10 限制).

语义 = V2A_FROZEN_STRICT (与 frozen run_fast_multi_strict_c parity 验证过的引擎):
  T close signal -> T+1 open entry; pending buy/add/sell 遇 T+1 无行情/缺失 -> CANCEL;
  dynamic self-consistent P* (analytic_Pstar, ddof=1); legal tick ceil; gap-through @ open;
  ref_first 跌停可达性; 100股lot; PIT ST; real list_date+60; 历史印花税; 10bp 双腿滑点;
  FINAL_SETTLE 仅末日有行情股; 其余持仓 -> censored(单独报告, 不进 realized headline).

路径口径 = FIRST_ENTRY_PRICE_PATH ONLY:
  NAV(t)= raw_price_t / first_entry_execution_price (open*(1+slip)).
  TWR/economic NAV 已被外部审计判暂时 INVALID -> 本脚本不产出.

count gate:
  V1(per-stock resume, 89188) vs V2A(冻结, 89046 realized + 124 censored) 数量差异
  已在 _gate_count_check.py 定位并在此报告解释:
    (1) 23 笔 V1-only = pending buy 在 V2A 冻结语义下 CANCEL(V1 顺延); 其中 5 笔次日重新信号(V2A-only);
    (2) 124 笔 = 已知退市股末日持仓, V1 强制 FINAL_SETTLE, V2A 标 censored(不当作 realized).
  以 V2A_FROZEN_STRICT 为冻结基线; V1 仅作对照.

不调参 / 不优化 / 不新增规则 / 不开 Validation / 不改 Registry.
==========================================================
"""
import os, sys, pickle, time
import numpy as np, pandas as pd
from collections import deque, Counter

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT); sys.path.insert(0, REPO)
from round51_audit import prepare_v51, stamp_rate, COMMISSION_RATE, MIN_COMMISSION, TRANSFER_FEE_RATE
from run_strict_c_math import analytic_Pstar

OUT = os.path.join(REPO, 'results'); os.makedirs(OUT, exist_ok=True)
FIG = os.path.join(REPO, 'figures'); os.makedirs(FIG, exist_ok=True)
LEVEL_CASH = 200_000.0; MAX_LEVELS = 5; SLIP = 0.001; ADD_GAP = 1
POST_H = [1, 3, 5, 10, 20, 40, 60]


def longest_underwater(nav):
    if len(nav) == 0:
        return 0
    best = cur = 0
    for u in (nav < 0):
        cur = cur + 1 if u else 0
        best = max(best, cur)
    return best


# ============================================================
# V2A_FROZEN_STRICT 全市场 replay (无 Top10) + 路径指标 + 排名 + 聚集
# ============================================================
def replay_full(days, D, first_eligible_i, offset):
    N = len(days)
    pos = {}; pending_buy = []; pending_add = {}; pending_sell = set()
    raw_hist = {}; episodes = []; censored = []; last_close = {}
    signal_counts = Counter()          # signal_date -> 信号数(含后续取消)
    episode_seq = [0]
    rank_all_day = {}                  # day_i -> dict tc->rank(1-based, 全PIT eligible按amount降序)

    def sell(tc, d, j, price, exit_type, i):
        p = pos[tc]
        amt = price * p['shares']
        sr = stamp_rate(d, 'historical')
        fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
        proceeds = amt - fee
        pnl = proceeds - p['total_cost']
        # 退出日路径去重(若已由 CLOSE 追加则不再加)
        if j is not None and not (p['path'] and p['path'][-1][0] == i):
            p['path'].append((i, float(D[d]['close'][j]), float(D[d]['high'][j]), float(D[d]['low'][j])))
        # ---- FIRST_ENTRY_PRICE_PATH metrics ----
        path = p['path']
        closes = np.array([c for _, c, _, _ in path], dtype=float)
        highs = np.array([h for _, _, h, _ in path], dtype=float)
        lows = np.array([l for _, _, _, l in path], dtype=float)
        base = p['entry_exec_raw']
        nav_c = closes / base - 1; nav_h = highs / base - 1; nav_l = lows / base - 1
        mae_c = float(nav_c.min() * 100); mae_i = float(nav_l.min() * 100)
        mfe_c = float(nav_c.max() * 100); mfe_i = float(nav_h.max() * 100)
        final_pp = float((price / base - 1) * 100)
        i_mae = int(np.argmin(nav_c)); i_mfe = int(np.argmax(nav_c))
        ge0 = np.where(nav_c >= 0)[0]
        never_under = len(ge0) == len(nav_c)
        be = int(ge0[0]) if len(ge0) else -1
        max_under = longest_underwater(nav_c)
        if max_under == 0:
            ttbe = 0; recov = 0
        else:
            ttbe = be if be >= 0 else np.nan
            recov = (be - i_mae) if (be >= 0 and be >= i_mae) else np.nan
        sr_pct = pnl / p['total_cost'] * 100
        giveback_i = mfe_i - sr_pct; giveback_c = mfe_c - sr_pct
        cap_c = (sr_pct - mae_c) / (mfe_c - mae_c) if (mfe_c - mae_c) > 0 else np.nan
        cap_i = (sr_pct - mae_i) / (mfe_i - mae_i) if (mfe_i - mae_i) > 0 else np.nan
        # ---- post-exit opportunity ----
        post_ret, post_mfe, post_mae = {}, {}, {}
        for h in POST_H:
            post_ret[h] = post_mfe[h] = post_mae[h] = np.nan
            if i + h >= N:
                continue
            jh = D[days[i + h]]['pos'].get(tc)
            if jh is None:
                continue
            post_ret[h] = (float(D[days[i + h]]['close'][jh]) / price - 1) * 100
        closes_after = []
        for h in range(1, 61):
            if i + h >= N:
                break
            jh = D[days[i + h]]['pos'].get(tc)
            if jh is not None:
                closes_after.append(float(D[days[i + h]]['close'][jh]))
        mfe60 = mae60 = peak_retrace60 = np.nan
        if closes_after:
            arr = np.array(closes_after) / price - 1
            for h in POST_H:
                if h <= len(closes_after):
                    post_mfe[h] = arr[:h].max() * 100
                    post_mae[h] = arr[:h].min() * 100
            mfe60 = arr.max() * 100; mae60 = arr.min() * 100
            pk = int(np.argmax(arr))
            if pk < len(arr) - 1:
                peak_retrace60 = (arr[pk] - arr[pk + 1:].min()) / (1 + arr[pk]) * 100
        episode_seq[0] += 1
        ep = dict(episode_id=episode_seq[0], ts_code=tc, signal_date=p['signal_date'],
                  entry_date=p['entry_date'], exit_date=str(d.date()), exit_type=exit_type,
                  levels_used=p['levels'], hold_days=i - p['entry_i'], total_cost=p['total_cost'],
                  pnl=pnl, simple_return_pct=sr_pct,
                  MAE_close_pct=mae_c, MAE_intraday_pct=mae_i,
                  MFE_close_pct=mfe_c, MFE_intraday_pct=mfe_i,
                  final_price_path_return_pct=final_pp,
                  time_to_MAE_days=i_mae, time_to_MFE_days=i_mfe,
                  time_to_break_even_days=ttbe, max_underwater_duration_days=max_under,
                  first_recovery_after_MAE_days=recov,
                  giveback_intraday_pct=giveback_i, giveback_close_pct=giveback_c,
                  capture_ratio_close=cap_c, capture_ratio_intraday=cap_i,
                  n_path_days=len(path), turnover_rank=p['turnover_rank'],
                  post_ret=post_ret, post_mfe=post_mfe, post_mae=post_mae,
                  post_mfe60=mfe60, post_mae60=mae60, post_peak_retrace60=peak_retrace60)
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

    t0 = time.time()
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
                    pending_buy.remove(pb); continue     # CANCEL (冻结语义)
                if dd['open_'][j] >= dd['limit_up_px'][j]:
                    continue
                buy_price = dd['open_'][j] * (1 + SLIP)
                qty = int(LEVEL_CASH / buy_price / 100) * 100
                if qty >= 100:
                    amt = buy_price * qty
                    fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * TRANSFER_FEE_RATE
                    rmap = rank_all_day.get(pb['signal_i'])
                    rk = rmap.get(tc, np.nan) if rmap else np.nan
                    pos[tc] = dict(shares=qty, total_cost=amt + fee, levels=1, entry_i=i,
                                   last_add_i=i, entry_date=str(d.date()),
                                   signal_date=pb['signal_date'], entry_exec_raw=buy_price,
                                   turnover_rank=rk, path=[])
                    init_raw_hist(tc, i)
                pending_buy.remove(pb)
        # ---- 盘中退出: dynamic_touch ----
        for tc in list(pos.keys()):
            p = pos[tc]; j = dd['pos'].get(tc)
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
            p = pos[tc]; j = dd['pos'].get(tc)
            if j is None:
                last_close[tc] = last_close.get(tc, p['total_cost'] / p['shares'])
                continue
            close = dd['close'][j]
            last_close[tc] = close
            p['path'].append((i, float(close), float(dd['high'][j]), float(dd['low'][j])))
            raw_hist.setdefault(tc, deque([], 19)).append(float(dd['close_adj'][j]))
            bb_lo = dd['bb_lower'][j]
            if (not np.isnan(bb_lo) and dd['close_adj'][j] < bb_lo and not dd['is_limit'][j]
                    and p['levels'] < MAX_LEVELS and (i - p['last_add_i']) >= ADD_GAP):
                pending_add[tc] = True
        # ---- 新买信号: ALL eligible (无 Top10), 记录 amount rank ----
        gi = offset + i
        li = gi - np.array([first_eligible_i.get(t, 0) for t in dd['ts']])
        valid = (li >= 0) & ~dd['is_st']
        if valid.any():
            cand_idx = np.where(valid)[0]
            amt_valid = dd['amount'][cand_idx]
            order_desc = np.argsort(-amt_valid, kind='stable')
            rank_desc = np.empty(len(cand_idx), dtype=int)
            rank_desc[order_desc] = np.arange(1, len(cand_idx) + 1)
            rmap = {dd['ts'][cand_idx[k]]: int(rank_desc[k]) for k in range(len(cand_idx))}
            rank_all_day[i] = rmap
            held = set(pos.keys()) | pending_sell
            pb_set = set(x['ts_code'] for x in pending_buy)
            for kk in cand_idx:
                tc = dd['ts'][kk]
                if tc in held or tc in pb_set:
                    continue
                if (not np.isnan(dd['bb_lower'][kk]) and dd['close_adj'][kk] < dd['bb_lower'][kk]
                        and not dd['is_limit'][kk]):
                    pending_buy.append({'ts_code': tc, 'signal_date': str(d.date()), 'signal_i': i})
                    signal_counts[str(d.date())] += 1
                    pb_set.add(tc)
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
    print(f'[FULL REPLAY DONE] episodes={len(episodes)} (TP={sum(1 for e in episodes if e["exit_type"]=="TAKE_PROFIT_DYN")} '
          f'FS={sum(1 for e in episodes if e["exit_type"]=="FINAL_SETTLE")}) censored={len(censored)} '
          f'({time.time()-t0:.0f}s)', flush=True)
    return episodes, censored, signal_counts


def epdf(eps):
    rows = []
    for e in eps:
        r = {k: e[k] for k in ('episode_id', 'ts_code', 'pnl', 'signal_date', 'entry_date', 'exit_date',
                               'exit_type', 'levels_used', 'total_cost', 'simple_return_pct', 'hold_days',
                               'MAE_close_pct', 'MAE_intraday_pct', 'MFE_close_pct', 'MFE_intraday_pct',
                               'final_price_path_return_pct', 'time_to_MAE_days', 'time_to_MFE_days',
                               'time_to_break_even_days', 'max_underwater_duration_days',
                               'first_recovery_after_MAE_days', 'giveback_intraday_pct', 'giveback_close_pct',
                               'capture_ratio_close', 'capture_ratio_intraday', 'n_path_days', 'turnover_rank')}
        for h in POST_H:
            r[f'post_ret_{h}d'] = e['post_ret'][h]
            r[f'post_mfe_{h}d'] = e['post_mfe'][h]
            r[f'post_mae_{h}d'] = e['post_mae'][h]
        r['post_mfe60'] = e['post_mfe60']
        r['post_mae60'] = e['post_mae60']
        r['post_peak_retrace60'] = e['post_peak_retrace60']
        rows.append(r)
    return pd.DataFrame(rows)


def eventday_stats(df):
    """signal_date 日级截面均值序列 -> HAC / bootstrap."""
    out = dict(n_event_days=int(df['signal_date'].nunique()),
               daily_mean=np.nan, daily_median=np.nan, daily_positive_rate=np.nan,
               hac_t=np.nan, hac_ci_lo=np.nan, hac_ci_hi=np.nan,
               episode_boot_ci_lo=np.nan, episode_boot_ci_hi=np.nan,
               eventday_boot_ci_lo=np.nan, eventday_boot_ci_hi=np.nan,
               eventday_boot_p_nonpos=np.nan,
               mean_final_ret=df['simple_return_pct'].mean(), median_final_ret=df['simple_return_pct'].median(),
               mean_MAE=df['MAE_intraday_pct'].mean(), median_MAE=df['MAE_intraday_pct'].median(),
               mean_MFE=df['MFE_intraday_pct'].mean(), median_MFE=df['MFE_intraday_pct'].median(),
               mean_hold=df['hold_days'].mean(), median_hold=df['hold_days'].median(),
               win_rate=(df['pnl'] > 0).mean() * 100)
    daily = df.groupby('signal_date')['simple_return_pct'].mean()
    y = daily.to_numpy()
    out['daily_mean'] = y.mean()
    out['daily_median'] = np.median(y)
    out['daily_positive_rate'] = (y > 0).mean() * 100
    if len(y) >= 10:
        import statsmodels.api as sm
        K = int(np.floor(4 * (len(y) / 100) ** (2 / 9)))
        K = max(0, min(K, len(y) - 2))
        try:
            res = sm.OLS(y, np.ones((len(y), 1))).fit(cov_type='HAC', cov_kwds={'maxlags': K})
            se = float(res.bse[0])
            out['hac_t'] = float(res.tvalues[0])
            out['hac_ci_lo'] = float(y.mean() - 1.96 * se)
            out['hac_ci_hi'] = float(y.mean() + 1.96 * se)
        except Exception:
            pass
    rng = np.random.default_rng(0)
    # episode bootstrap B=5000
    r = df['simple_return_pct'].to_numpy()
    B = 5000
    bs = rng.choice(r, size=(B, len(r)), replace=True).mean(axis=1)
    out['episode_boot_ci_lo'] = float(np.percentile(bs, 2.5))
    out['episode_boot_ci_hi'] = float(np.percentile(bs, 97.5))
    # event-day bootstrap B=2000
    B2 = 2000
    bs2 = rng.choice(y, size=(B2, len(y)), replace=True).mean(axis=1)
    out['eventday_boot_ci_lo'] = float(np.percentile(bs2, 2.5))
    out['eventday_boot_ci_hi'] = float(np.percentile(bs2, 97.5))
    out['eventday_boot_p_nonpos'] = float((bs2 <= 0).mean())
    # block bootstrap L=21 B=2000 (真实日历顺序, 不打乱事件日间隔)
    n = len(y); L = 21
    nblocks = int(np.ceil(n / L))
    bl = []
    for _ in range(B2):
        idx = []
        for _b in range(nblocks):
            s = rng.integers(0, n - L + 1) if n - L + 1 > 0 else 0
            idx.extend(range(s, min(s + L, n)))
        idx = np.array(idx[:n])
        bl.append(y[idx].mean())
    bl = np.array(bl)
    out['block_boot_ci_lo'] = float(np.percentile(bl, 2.5))
    out['block_boot_ci_hi'] = float(np.percentile(bl, 97.5))
    out['block_boot_p_nonpos'] = float((bl <= 0).mean())
    return out


def q(x, p):
    x = pd.Series(x).dropna()
    return float(x.quantile(p)) if len(x) else np.nan


def mae_threshold_table(df):
    thr = [-5, -7.5, -10, -12.5, -15, -17.5, -20, -22.5, -25, -30, -35, -40, -50]
    rows = []
    mae = df['MAE_intraday_pct']
    for t in thr:
        d = df[mae <= t]
        rows.append(dict(kind='cumulative_le', threshold_pct=t, n_crossed=len(d),
                         win_rate=(d['pnl'] > 0).mean() * 100 if len(d) else np.nan,
                         mean_final_return=d['simple_return_pct'].mean() if len(d) else np.nan,
                         median_final_return=d['simple_return_pct'].median() if len(d) else np.nan,
                         mean_recovery_days=d['first_recovery_after_MAE_days'].mean() if len(d) else np.nan,
                         mean_hold=d['hold_days'].mean() if len(d) else np.nan,
                         p10_final=d['simple_return_pct'].quantile(.1) if len(d) else np.nan))
    bins = [(0, -5), (-5, -10), (-10, -15), (-15, -20), (-20, -25), (-25, -30), (-30, -40), (-40, -1e9)]
    for hi, lo in bins:
        if lo == -1e9:
            d = df[mae <= hi]
            lab = '<=-40'
        else:
            d = df[(mae > lo) & (mae <= hi)]     # lo < MAE <= hi (负值区间)
            lab = f'{lo}~{hi}'
        rows.append(dict(kind='bin', threshold_pct=lab, n_crossed=len(d),
                         win_rate=(d['pnl'] > 0).mean() * 100 if len(d) else np.nan,
                         mean_final_return=d['simple_return_pct'].mean() if len(d) else np.nan,
                         median_final_return=d['simple_return_pct'].median() if len(d) else np.nan,
                         mean_recovery_days=d['first_recovery_after_MAE_days'].mean() if len(d) else np.nan,
                         mean_hold=d['hold_days'].mean() if len(d) else np.nan,
                         p10_final=d['simple_return_pct'].quantile(.1) if len(d) else np.nan))
    return pd.DataFrame(rows)


def main():
    print('prepare_v51 ...', flush=True)
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51()
    print(f'  days={len(days)} {days[0].date()}..{days[-1].date()}', flush=True)

    eps, cens, sig_counts = replay_full(days, D, first_eligible_i, offset)
    df = epdf(eps)
    df.to_csv(os.path.join(OUT, 'fullmarket_episode_metrics.csv'), index=False)
    print(f'[SAVE] fullmarket_episode_metrics.csv {df.shape}', flush=True)

    # ---- count gate 汇总 ----
    v1 = pickle.load(open(os.path.join(OUT, 'independent_ep_SECONDARY_DYN.pkl'), 'rb'))
    v1n = len(v1)
    v1tp = sum(1 for e in v1 if e['exit_type'] == 'TAKE_PROFIT_DYN')
    v1fs = sum(1 for e in v1 if e['exit_type'] == 'FINAL_SETTLE')
    tp = int((df['exit_type'] == 'TAKE_PROFIT_DYN').sum())
    fs = int((df['exit_type'] == 'FINAL_SETTLE').sum())
    gate = dict(v1_episodes=v1n, v1_TP=v1tp, v1_FS=v1fs,
                v2a_realized=len(df), v2a_TP=tp, v2a_FS=fs, v2a_censored=len(cens),
                v2a_total_entries=len(df) + len(cens),
                delta_entries=v1n - (len(df) + len(cens)))
    pd.DataFrame([gate]).to_csv(os.path.join(OUT, 'fullmarket_gate_summary.csv'), index=False)

    # ---- PRIMARY 对照 ----
    prim = pd.read_csv(os.path.join(OUT, 'trade_path_episode_metrics.csv'))
    prim = prim[prim['simple_return_pct'].notna()]

    def summ(d):
        return dict(n=len(d), ret_mean=d['simple_return_pct'].mean(), ret_median=d['simple_return_pct'].median(),
                    win_rate=(d['pnl'] > 0).mean() * 100,
                    mae_med=q(d['MAE_intraday_pct'], .5), mae_p10=q(d['MAE_intraday_pct'], .1),
                    mae_p5=q(d['MAE_intraday_pct'], .05), mae_p1=q(d['MAE_intraday_pct'], .01),
                    mfe_med=q(d['MFE_intraday_pct'], .5), hold_med=q(d['hold_days'], .5),
                    under_med=q(d['max_underwater_duration_days'], .5), giveback_med=q(d['giveback_intraday_pct'], .5))
    cmp = pd.DataFrame([{**{'sample': 'PRIMARY_TOP10'}, **summ(prim)},
                        {**{'sample': 'SECONDARY_ALL'}, **summ(df)}])
    cmp.to_csv(os.path.join(OUT, 'fullmarket_primary_secondary_compare.csv'), index=False)
    print(cmp.to_string(), flush=True)

    # ---- 成交额排名分层 ----
    rb = []
    bdef = [('A_TOP10', df['turnover_rank'] <= 10), ('B_11_50', (df['turnover_rank'] > 10) & (df['turnover_rank'] <= 50)),
            ('C_51_200', (df['turnover_rank'] > 50) & (df['turnover_rank'] <= 200)),
            ('D_201_500', (df['turnover_rank'] > 200) & (df['turnover_rank'] <= 500)),
            ('E_gt500', df['turnover_rank'] > 500)]
    for name, m in bdef:
        d = df[m]
        rb.append(dict(bucket=name, n=len(d), ret_mean=d['simple_return_pct'].mean(),
                       ret_median=d['simple_return_pct'].median(), win_rate=(d['pnl'] > 0).mean() * 100,
                       mae_med=q(d['MAE_intraday_pct'], .5), mae_p10=q(d['MAE_intraday_pct'], .1),
                       mae_p5=q(d['MAE_intraday_pct'], .05), mfe_med=q(d['MFE_intraday_pct'], .5),
                       hold_med=q(d['hold_days'], .5), under_med=q(d['max_underwater_duration_days'], .5),
                       giveback_med=q(d['giveback_intraday_pct'], .5),
                       ed_mean=df[df['signal_date'].isin(d['signal_date'])]['simple_return_pct'].mean() if len(d) else np.nan))
    rdf = pd.DataFrame(rb)
    rdf.to_csv(os.path.join(OUT, 'fullmarket_turnover_rank_buckets.csv'), index=False)
    print(rdf.to_string(), flush=True)

    # ---- MAE 阈值: SECONDARY + PRIMARY 并排 ----
    st = mae_threshold_table(df); st.insert(0, 'sample', 'SECONDARY')
    pt = mae_threshold_table(prim); pt.insert(0, 'sample', 'PRIMARY')
    mtab = pd.concat([pt, st], ignore_index=True)
    mtab.to_csv(os.path.join(OUT, 'fullmarket_mae_thresholds.csv'), index=False)

    # ---- winner/loser ----
    wl = []
    for g, m in [('WINNER', df['simple_return_pct'] > 0), ('LOSER', df['simple_return_pct'] <= 0)]:
        d = df[m]
        wl.append(dict(group=g, n=len(d), ret_mean=d['simple_return_pct'].mean(),
                       ret_median=d['simple_return_pct'].median(),
                       MAE_intraday_p1=q(d['MAE_intraday_pct'], .01), MAE_intraday_p5=q(d['MAE_intraday_pct'], .05),
                       MAE_intraday_p10=q(d['MAE_intraday_pct'], .1), MAE_intraday_p25=q(d['MAE_intraday_pct'], .25),
                       MAE_intraday_p50=q(d['MAE_intraday_pct'], .5), MAE_intraday_p75=q(d['MAE_intraday_pct'], .75),
                       MAE_intraday_p90=q(d['MAE_intraday_pct'], .9), MAE_intraday_p95=q(d['MAE_intraday_pct'], .95),
                       MAE_intraday_p99=q(d['MAE_intraday_pct'], .99),
                       MFE_intraday_p50=q(d['MFE_intraday_pct'], .5), MFE_intraday_p75=q(d['MFE_intraday_pct'], .75),
                       MFE_intraday_p90=q(d['MFE_intraday_pct'], .9),
                       hold_p50=q(d['hold_days'], .5), hold_mean=d['hold_days'].mean(),
                       underwater_p50=q(d['max_underwater_duration_days'], .5),
                       ttbe_p50=q(d['time_to_break_even_days'], .5), recov_p50=q(d['first_recovery_after_MAE_days'], .5),
                       giveback_p50=q(d['giveback_intraday_pct'], .5)))
    wldf = pd.DataFrame(wl)
    wldf.to_csv(os.path.join(OUT, 'fullmarket_winner_loser.csv'), index=False)
    # 赢家深度突破比例
    wdf = df[df['simple_return_pct'] > 0]
    brk = []
    for t in [-5, -10, -15, -20, -25, -30]:
        brk.append(dict(winner_mae_le=t, n_winners_breached=int((wdf['MAE_intraday_pct'] <= t).sum()),
                        pct_of_winners=(wdf['MAE_intraday_pct'] <= t).mean() * 100))
    pd.DataFrame(brk).to_csv(os.path.join(OUT, 'fullmarket_winner_mae_breach.csv'), index=False)

    # ---- 年度 ----
    yy = []
    for y in range(2020, 2027):
        for sample, d in [('PRIMARY', prim), ('SECONDARY', df)]:
            dd = d[pd.to_datetime(d['signal_date']).dt.year == y]
            yy.append(dict(year=y, sample=sample, n=len(dd),
                           ret_mean=dd['simple_return_pct'].mean() if len(dd) else np.nan,
                           ret_median=dd['simple_return_pct'].median() if len(dd) else np.nan,
                           win_rate=(dd['pnl'] > 0).mean() * 100 if len(dd) else np.nan,
                           mae_p50=q(dd['MAE_intraday_pct'], .5), mae_p10=q(dd['MAE_intraday_pct'], .1),
                           mae_p5=q(dd['MAE_intraday_pct'], .05), mfe_p50=q(dd['MFE_intraday_pct'], .5),
                           hold_med=q(dd['hold_days'], .5), under_med=q(dd['max_underwater_duration_days'], .5),
                           giveback_med=q(dd['giveback_intraday_pct'], .5)))
    ydf = pd.DataFrame(yy)
    ydf.to_csv(os.path.join(OUT, 'fullmarket_yearly.csv'), index=False)
    print(ydf.pivot_table(index='year', columns='sample', values=['n', 'ret_mean', 'win_rate']).to_string(), flush=True)

    # ---- levels ----
    lv = []
    for l in range(1, 6):
        d = df[df['levels_used'] == l]
        lv.append(dict(levels_used=l, n=len(d), ret_mean=d['simple_return_pct'].mean(),
                       ret_median=d['simple_return_pct'].median(), win_rate=(d['pnl'] > 0).mean() * 100,
                       mae_med=q(d['MAE_intraday_pct'], .5), mae_p10=q(d['MAE_intraday_pct'], .1),
                       mae_p5=q(d['MAE_intraday_pct'], .05), mfe_med=q(d['MFE_intraday_pct'], .5),
                       hold_med=q(d['hold_days'], .5), under_med=q(d['max_underwater_duration_days'], .5)))
    lvdf = pd.DataFrame(lv)
    lvdf.to_csv(os.path.join(OUT, 'fullmarket_levels.csv'), index=False)
    print(lvdf.to_string(), flush=True)

    # ---- signal crowding ----
    sc = df.groupby('signal_date').size()
    crow = dict(p50=float(sc.quantile(.5)), p75=float(sc.quantile(.75)), p90=float(sc.quantile(.9)),
                p95=float(sc.quantile(.95)), p99=float(sc.quantile(.99)), max=int(sc.max()))
    crow['n_signal_dates'] = int(len(sc))
    cb = []
    for lo, hi, lab in [(1, 5, '1-5'), (6, 20, '6-20'), (21, 50, '21-50'), (51, 100, '51-100'), (101, 10 ** 9, '>100')]:
        dayset = sc[(sc >= lo) & (sc <= hi)].index
        d = df[df['signal_date'].isin(dayset)]
        cb.append(dict(crowding_bucket=lab, n_dates=len(dayset), n_episodes=len(d),
                       ret_mean=d['simple_return_pct'].mean() if len(d) else np.nan,
                       win_rate=(d['pnl'] > 0).mean() * 100 if len(d) else np.nan,
                       mae_med=q(d['MAE_intraday_pct'], .5), mfe_med=q(d['MFE_intraday_pct'], .5)))
    cbdf = pd.DataFrame(cb)
    cbdf.to_csv(os.path.join(OUT, 'fullmarket_signal_crowding.csv'), index=False)
    pd.DataFrame([{**{'metric': k}, **{'value': v}} for k, v in crow.items()]).to_csv(
        os.path.join(OUT, 'fullmarket_crowding_dist.csv'), index=False)
    print(cbdf.to_string(), flush=True)

    # ---- tail risk ----
    total_pnl = df['pnl'].sum()
    tr = []
    for lab, k in [('bottom_1pct', int(len(df) * 0.01)), ('bottom_5pct', int(len(df) * 0.05)),
                   ('bottom_10pct', int(len(df) * 0.1))]:
        d = df.nsmallest(max(k, 1), 'pnl')
        tr.append(dict(quantile=lab, n=len(d), pnl_sum=d['pnl'].sum(), pct_of_total_pnl=d['pnl'].sum() / total_pnl * 100,
                       mean_ret=d['simple_return_pct'].mean(), mean_mae=d['MAE_intraday_pct'].mean()))
    for lab, k in [('top_1pct', int(len(df) * 0.01)), ('top_5pct', int(len(df) * 0.05))]:
        d = df.nlargest(max(k, 1), 'pnl')
        tr.append(dict(quantile=lab, n=len(d), pnl_sum=d['pnl'].sum(), pct_of_total_pnl=d['pnl'].sum() / total_pnl * 100,
                       mean_ret=d['simple_return_pct'].mean(), mean_mae=d['MAE_intraday_pct'].mean()))
    trdf = pd.DataFrame(tr)
    trdf.to_csv(os.path.join(OUT, 'fullmarket_tail_risk.csv'), index=False)
    # remove best 1%/5%
    n1 = max(1, int(len(df) * 0.01)); n5 = max(1, int(len(df) * 0.05))
    r = df['simple_return_pct'].to_numpy()
    rem = dict(remove_best1pct_mean=float(np.sort(r)[:-n1].mean()), remove_best5pct_mean=float(np.sort(r)[:-n5].mean()),
               full_mean=float(r.mean()))
    pd.DataFrame([{**{'metric': k}, **{'value': v}} for k, v in rem.items()]).to_csv(
        os.path.join(OUT, 'fullmarket_remove_best.csv'), index=False)
    # worst 100/500/1000
    worst = []
    for k in [100, 500, 1000]:
        d = df.nsmallest(min(k, len(df)), 'pnl')
        worst.append(dict(k=k, n=len(d), mean_ret=d['simple_return_pct'].mean(),
                          mean_mae=d['MAE_intraday_pct'].mean(), mean_mfe=d['MFE_intraday_pct'].mean(),
                          mean_hold=d['hold_days'].mean(), mean_levels=d['levels_used'].mean(),
                          mean_under=d['max_underwater_duration_days'].mean()))
    pd.DataFrame(worst).to_csv(os.path.join(OUT, 'fullmarket_worst_episodes.csv'), index=False)
    # top10 股票贡献
    stk = df.groupby('ts_code')['pnl'].sum().sort_values(ascending=False)
    t10 = pd.DataFrame(dict(ts_code=stk.head(10).index, pnl_sum=stk.head(10).values))
    t10['pct_of_total_pnl'] = t10['pnl_sum'] / total_pnl * 100
    t10.to_csv(os.path.join(OUT, 'fullmarket_top10_stocks.csv'), index=False)

    # ---- exit quality ----
    prof = df[df['simple_return_pct'] > 0]
    eq = []
    def pctgt(col, thr):
        x = prof[col].dropna()
        return float((x > thr).mean() * 100) if len(x) else np.nan
    eq.append(dict(metric='n_profitable', value=len(prof)))
    eq.append(dict(metric='post5D_mfe_gt3pct', value=pctgt('post_mfe_5d', 3)))
    eq.append(dict(metric='post5D_mfe_gt5pct', value=pctgt('post_mfe_5d', 5)))
    eq.append(dict(metric='post10D_mfe_gt5pct', value=pctgt('post_mfe_10d', 5)))
    eq.append(dict(metric='post20D_mfe_gt10pct', value=pctgt('post_mfe_20d', 10)))
    eq.append(dict(metric='post40D_mfe_gt15pct', value=pctgt('post_mfe_40d', 15)))
    eq.append(dict(metric='capture_ratio_close_median', value=q(df['capture_ratio_close'], .5)))
    eq.append(dict(metric='capture_ratio_intraday_median', value=q(df['capture_ratio_intraday'], .5)))
    eq.append(dict(metric='giveback_median', value=q(df['giveback_intraday_pct'], .5)))
    eq.append(dict(metric='giveback_mean', value=df['giveback_intraday_pct'].mean()))
    eq.append(dict(metric='mfe60_median', value=q(df['post_mfe60'], .5)))
    eq.append(dict(metric='mae60_median', value=q(df['post_mae60'], .5)))
    eq.append(dict(metric='peak_retrace60_median', value=q(df['post_peak_retrace60'], .5)))
    eqdf = pd.DataFrame(eq)
    eqdf.to_csv(os.path.join(OUT, 'fullmarket_exit_quality.csv'), index=False)

    # ---- event-day stats ----
    ed = pd.DataFrame([eventday_stats(df)])
    ed.to_csv(os.path.join(OUT, 'fullmarket_eventday_stats.csv'), index=False)
    print(ed.T.to_string(), flush=True)

    # ---- figures ----
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'figure.dpi': 110, 'savefig.bbox': 'tight'})

    def save(fig, name):
        fig.savefig(os.path.join(FIG, name))
        plt.close(fig)

    # 1 primary vs secondary MAE
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.hist(prim['MAE_intraday_pct'].clip(-50, 0), bins=40, alpha=0.5, density=True, label=f'PRIMARY n={len(prim)}')
    ax.hist(df['MAE_intraday_pct'].clip(-50, 0), bins=60, alpha=0.5, density=True, label=f'SECONDARY n={len(df)}')
    ax.set_xlabel('MAE_intraday_pct'); ax.set_title('MAE distribution: PRIMARY vs SECONDARY'); ax.legend()
    save(fig, 'primary_vs_secondary_mae.png')

    # 2 primary vs secondary MFE
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.hist(prim['MFE_intraday_pct'].clip(0, 80), bins=40, alpha=0.5, density=True, label=f'PRIMARY n={len(prim)}')
    ax.hist(df['MFE_intraday_pct'].clip(0, 80), bins=60, alpha=0.5, density=True, label=f'SECONDARY n={len(df)}')
    ax.set_xlabel('MFE_intraday_pct'); ax.set_title('MFE distribution: PRIMARY vs SECONDARY'); ax.legend()
    save(fig, 'primary_vs_secondary_mfe.png')

    # 3 mae threshold winprob comparison
    thr = [-5, -7.5, -10, -12.5, -15, -17.5, -20, -22.5, -25, -30, -35, -40, -50]
    def wp(d):
        mae = d['MAE_intraday_pct']
        return [ (d[mae <= t]['pnl'] > 0).mean() * 100 for t in thr ]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(thr, wp(prim), 'o-', label='PRIMARY')
    ax.plot(thr, wp(df), 's-', label='SECONDARY')
    ax.set_xlabel('MAE_intraday <= threshold (%)'); ax.set_ylabel('Win rate (%)')
    ax.set_title('P(win | MAE<=threshold): PRIMARY vs SECONDARY'); ax.legend(); ax.grid(alpha=.3)
    save(fig, 'mae_threshold_winprob_comparison.png')

    # 4 turnover rank vs return
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar(rdf['bucket'], rdf['ret_mean'], label='mean')
    ax.bar(rdf['bucket'], rdf['ret_median'], alpha=.6, label='median')
    ax.set_xlabel('amount-rank bucket'); ax.set_ylabel('return (%)')
    ax.set_title('Turnover rank bucket vs return'); ax.legend(); ax.grid(alpha=.3)
    save(fig, 'turnover_rank_vs_return.png')

    # 5 turnover rank vs MAE
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar(rdf['bucket'], rdf['mae_med'], label='MAE median')
    ax.bar(rdf['bucket'], rdf['mae_p10'], alpha=.6, label='MAE P10')
    ax.set_xlabel('amount-rank bucket'); ax.set_ylabel('MAE_intraday (%)')
    ax.set_title('Turnover rank bucket vs MAE'); ax.legend(); ax.grid(alpha=.3)
    save(fig, 'turnover_rank_vs_mae.png')

    # 6 levels vs quality secondary
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar(lvdf['levels_used'].astype(str), lvdf['ret_mean'], label='mean ret')
    ax.plot(lvdf['levels_used'].astype(str), lvdf['win_rate'], 'o-', color='C2', label='win rate')
    ax.set_xlabel('levels_used'); ax.set_ylabel('ret % / win %')
    ax.set_title('SECONDARY: levels_used vs quality (ASSOCIATION ONLY)'); ax.legend(); ax.grid(alpha=.3)
    save(fig, 'levels_vs_quality_secondary.png')

    # 7 yearly quality
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for sample, c in [('PRIMARY', 'C0'), ('SECONDARY', 'C1')]:
        s = ydf[ydf['sample'] == sample]
        ax.plot(s['year'], s['ret_mean'], 'o-', color=c, label=f'{sample} mean')
    ax.set_xlabel('entry year'); ax.set_ylabel('mean return (%)')
    ax.set_title('Yearly mean return: PRIMARY vs SECONDARY'); ax.legend(); ax.grid(alpha=.3)
    save(fig, 'yearly_quality_primary_secondary.png')

    # 8 signal crowding vs quality
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar(cbdf['crowding_bucket'], cbdf['ret_mean'], label='mean ret')
    ax.plot(cbdf['crowding_bucket'], cbdf['win_rate'], 'o-', color='C2', label='win rate')
    ax.set_xlabel('signals per day bucket'); ax.set_ylabel('ret % / win %')
    ax.set_title('Signal crowding vs quality (SECONDARY)'); ax.legend(); ax.grid(alpha=.3)
    save(fig, 'signal_crowding_vs_quality.png')

    # 9 hexbin MAE vs final return
    fig, ax = plt.subplots(figsize=(7, 5))
    hb = ax.hexbin(df['MAE_intraday_pct'].clip(-60, 0), df['simple_return_pct'].clip(-60, 80),
                   gridsize=60, cmap='viridis', mincnt=1)
    ax.set_xlabel('MAE_intraday (%)'); ax.set_ylabel('final return (%)')
    ax.set_title('SECONDARY: MAE vs final return'); fig.colorbar(hb, ax=ax, label='count')
    save(fig, 'secondary_mae_vs_final_return_hexbin.png')

    # 10 secondary return distribution
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.hist(df['simple_return_pct'].clip(-60, 80), bins=80, density=True)
    ax.axvline(0, color='k', lw=1)
    ax.set_xlabel('simple_return_pct (%)'); ax.set_title(f'SECONDARY return distribution (n={len(df)})')
    save(fig, 'secondary_return_distribution.png')

    print('DONE', flush=True)


if __name__ == '__main__':
    main()
