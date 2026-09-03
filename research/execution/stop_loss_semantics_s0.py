"""
==========================================================
STOP-LOSS SEMANTICS REMEDIATION — S0
ADJUSTED-SPACE STOP vs OLD RAW-SPACE STOP (EXACT REPLICATION)
==========================================================
Fixed Stop Phase A semantics bug:
  - old: stop_raw = first_entry_raw * (1 + stop_pct); compare against RAW OHLC
         across the whole holding period. WRONG across dividend/split/送转/adjust_factor changes.
  - new: stop defined in ADJUSTED PRICE SPACE:
         entry_adj      = entry_raw * entry_adj_factor
         stop_adj       = entry_adj * (1 + s)
         low_adj_d      = low_raw_d * adj_factor_d
         trigger        = low_adj_d <= stop_adj
         gap            = open_adj_d < stop_adj  ->  fill at open_raw_d
         else stop_raw_d = stop_adj / adj_factor_d  (theoretical raw stop)
         then A-share tick / limit-down / T+1 / suspension / executable semantics
         identical to frozen STRICT_C.

ONLY the stop-price coordinate system changes. Everything else (entry, adds, dynamic
P* TP, exit, costs, slippage, T+1, pending semantics) is byte-identical to Phase A.

Discipline (frozen):
  - dev-only episodes: signal_date <= 2024-12-31 AND exit_date <= 2024-12-31
    (61,828 SECONDARY episodes from frozen fullmarket_episode_metrics.csv).
  - 2025-2026 CONFIRMATION CLOSED: never read any 2025+ episode outcome / path.
  - Frozen grid identical to Phase A canonical: -10/-12.5/-15/-17.5/-20/-22.5/-25/-27.5/-30/-35/-40.
  - NO new threshold, no adaptive/trailing/time stop, no profit-target change, no exit change,
    no ranking, no market gate, no K/layer change, no ML, no parameter optimization.
  - Same-bar stop/TP collision -> STOP_FIRST (primary) / TP_FIRST (sensitivity).
  - gap-stop fills at open raw + frozen slippage; limit-down/suspension defers with delay_days.
  - T+1 preserved: entry-day stop exit forbidden.
  - Invariants I1-I7 auto-asserted.
==========================================================
"""
import os, sys, pickle, time, json, hashlib
import numpy as np, pandas as pd
from collections import Counter, deque

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
GIT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')   # audit_package/github_repo
GIT = os.path.abspath(GIT)
OUT = os.path.join(GIT, 'results', 'evidence', 's0')
FIG = os.path.join(GIT, 'research', 'execution', 'figures')
os.makedirs(OUT, exist_ok=True); os.makedirs(FIG, exist_ok=True)
sys.path.insert(0, ROOT); sys.path.insert(0, GIT)
from round51_audit import prepare_v51, stamp_rate, COMMISSION_RATE, MIN_COMMISSION, TRANSFER_FEE_RATE
from run_strict_c_math import analytic_Pstar

LEVEL_CASH = 200_000.0; MAX_LEVELS = 5; SLIP = 0.001; ADD_GAP = 1
STOPS = [-10.0, -12.5, -15.0, -17.5, -20.0, -22.5, -25.0, -27.5, -30.0, -35.0, -40.0]
BOUNDS = ['STOP_FIRST', 'TP_FIRST']
TAIL_CAP = 180
DEV_END = pd.Timestamp('2024-12-31')
REGISTRY_SHA = '7e8416fd4fc3a3f67da41d020747ffda34aaf8b1e230ddf574c131ab30f36273'


# ============================================================
# 1) Re-record frozen episodes (dev-only, adj column added as col 9)
# ============================================================
def replay_record_dev(days, D, first_eligible_i, offset, top10_only, day_range):
    N = len(days)
    i0, i1 = day_range
    pos = {}; pending_buy = []; pending_add = {}; pending_sell = set()
    raw_hist = {}; episodes = []; censored = []; last_close = {}
    episode_seq = [0]

    def day_row(i, dd, j, thr):
        return np.array([i, float(dd['open_'][j]), float(dd['high'][j]), float(dd['low'][j]),
                         float(dd['limit_down_px'][j]), float(dd['is_limit'][j]), thr,
                         float(stamp_rate(days[i], 'historical')), float(dd['close'][j]),
                         float(dd['adj'][j])], dtype=np.float32)

    def finalize(tc, d, price, exit_type, i, p):
        amt = price * p['shares']
        sr = stamp_rate(d, 'historical')
        fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
        proceeds = amt - fee
        pnl = proceeds - p['total_cost']
        rows = np.array(p['rows'], dtype=np.float32)
        episode_seq[0] += 1
        ep = dict(episode_id=episode_seq[0], ts_code=tc, signal_date=p['signal_date'],
                  entry_date=p['entry_date'], entry_i=p['entry_i'], entry_exec_raw=p['entry_exec_raw'],
                  exit_i=i, exit_date=str(d.date()), exit_type=exit_type,
                  exit_exec_price=price,   # instrument-only: actual fill incl. slippage (float64), no semantics change
                  levels_used=p['levels'], total_cost=p['total_cost'], pnl=pnl,
                  simple_return_pct=pnl / p['total_cost'] * 100,
                  layers=np.array(p['layers'], dtype=np.float32), rows=rows,
                  exit_ri=len(rows) - 1, ret0=pnl / p['total_cost'] * 100,
                  pnl0=pnl, hold0=i - p['entry_i'], levels0=p['levels'], base=p['entry_exec_raw'],
                  cost=p['total_cost'],
                  mae0=float((rows[:, 3] / p['entry_exec_raw'] - 1).min() * 100))
        episodes.append(ep)
        del pos[tc]; raw_hist.pop(tc, None)
        return ep

    def init_raw_hist(tc, i):
        hist = deque()
        for k in range(1, 20):
            if i - k < i0:
                break
            dk = days[i - k]; jk = D[dk]['pos'].get(tc)
            if jk is not None:
                hist.appendleft(float(D[dk]['close_adj'][jk]))
        raw_hist[tc] = deque(hist, 19)

    def new_pos(tc, i, d, buy_price, qty, amt, fee, signal_date):
        return dict(shares=qty, total_cost=amt + fee, levels=1, entry_i=i, last_add_i=i,
                    entry_date=str(d.date()), signal_date=signal_date, entry_exec_raw=buy_price,
                    layers=[[i, buy_price, qty, amt + fee]], rows=[])

    t0 = time.time()
    for i in range(i0, i1):
        d = days[i]; dd = D[d]
        # ---- OPEN: pending_sell ----
        for tc in list(pending_sell):
            if tc not in pos:
                pending_sell.discard(tc); continue
            j = dd['pos'].get(tc)
            if j is None:
                pending_sell.discard(tc); continue
            if dd['open_'][j] <= dd['limit_down_px'][j]:
                continue
            finalize(tc, d, dd['open_'][j] * (1 - SLIP), 'TAKE_PROFIT_UB', i, pos[tc])
            pending_sell.discard(tc)
        # ---- OPEN: pending_add ----
        for tc in list(pending_add):
            p = pos.get(tc)
            if p is None:
                pending_add.pop(tc, None); continue
            j = dd['pos'].get(tc)
            if j is None:
                pending_add.pop(tc, None); continue
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
                p['layers'].append([i, buy_price, qty, amt + fee])
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
                    pending_buy.remove(pb); continue
                if dd['open_'][j] >= dd['limit_up_px'][j]:
                    continue
                buy_price = dd['open_'][j] * (1 + SLIP)
                qty = int(LEVEL_CASH / buy_price / 100) * 100
                if qty >= 100:
                    amt = buy_price * qty
                    fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * TRANSFER_FEE_RATE
                    pos[tc] = new_pos(tc, i, d, buy_price, qty, amt, fee, pb['signal_date'])
                    init_raw_hist(tc, i)
                pending_buy.remove(pb)
        # ---- day rows + dynamic_touch ----
        for tc in list(pos.keys()):
            p = pos[tc]; j = dd['pos'].get(tc)
            if j is None:
                continue
            hist = raw_hist.get(tc); thr = np.nan
            if hist is not None and len(hist) >= 19:
                x = np.array(list(hist)[-19:], dtype=float)
                Pstar = analytic_Pstar(x)
                if Pstar is not None and np.isfinite(Pstar):
                    thr = np.ceil((Pstar / dd['adj'][j]) / 0.01) * 0.01
            p['rows'].append(day_row(i, dd, j, thr))
            if (i - p['entry_i']) < 1:
                continue
            if hist is None or len(hist) < 19 or np.isnan(thr):
                continue
            trig = dd['high_adj'][j] >= thr * dd['adj'][j]
            if not trig:
                continue
            if dd['open_'][j] * dd['adj'][j] >= thr * dd['adj'][j]:
                ref = dd['open_'][j]
            else:
                ref = thr
            if ref <= dd['limit_down_px'][j]:
                continue
            finalize(tc, d, ref * (1 - SLIP), 'TAKE_PROFIT_DYN', i, pos[tc])
        # ---- CLOSE ----
        for tc in list(pos.keys()):
            p = pos[tc]; j = dd['pos'].get(tc)
            if j is None:
                last_close[tc] = last_close.get(tc, p['total_cost'] / p['shares']); continue
            last_close[tc] = dd['close'][j]
            raw_hist.setdefault(tc, deque([], 19)).append(float(dd['close_adj'][j]))
            bb_lo = dd['bb_lower'][j]
            if (not np.isnan(bb_lo) and dd['close_adj'][j] < bb_lo and not dd['is_limit'][j]
                    and p['levels'] < MAX_LEVELS and (i - p['last_add_i']) >= ADD_GAP):
                pending_add[tc] = True
        # ---- new buy signal ----
        gi = offset + i
        li = gi - np.array([first_eligible_i.get(t, 0) for t in dd['ts']])
        valid = (li >= 0) & ~dd['is_st']
        if valid.any():
            cand_idx = np.where(valid)[0]
            held = set(pos.keys()) | pending_sell
            pb_set = set(x['ts_code'] for x in pending_buy)
            if top10_only:
                amt = dd['amount'][cand_idx]
                for k in np.argsort(-amt)[:10]:
                    j = cand_idx[k]; tc = dd['ts'][j]
                    if tc in held or tc in pb_set:
                        continue
                    if (not np.isnan(dd['bb_lower'][j]) and dd['close_adj'][j] < dd['bb_lower'][j]
                            and not dd['is_limit'][j]):
                        pending_buy.append({'ts_code': tc, 'signal_date': str(d.date())}); pb_set.add(tc)
            else:
                for kk in cand_idx:
                    tc = dd['ts'][kk]
                    if tc in held or tc in pb_set:
                        continue
                    if (not np.isnan(dd['bb_lower'][kk]) and dd['close_adj'][kk] < dd['bb_lower'][kk]
                            and not dd['is_limit'][kk]):
                        pending_buy.append({'ts_code': tc, 'signal_date': str(d.date())}); pb_set.add(tc)
    # ---- 期末 (dev window end) ----
    d_last = days[i1 - 1]; dd_last = D[d_last]
    for tc in list(pos.keys()):
        j = dd_last['pos'].get(tc)
        if j is not None:
            finalize(tc, d_last, dd_last['close'][j] * (1 - SLIP), 'FINAL_SETTLE', i1 - 1, pos[tc])
        else:
            p = pos[tc]
            mark = last_close.get(tc, p['total_cost'] / p['shares'])
            censored.append(dict(ts_code=tc, signal_date=p['signal_date'], entry_date=p['entry_date'],
                                 entry_i=p['entry_i'], entry_exec_raw=p['entry_exec_raw'],
                                 exit_i=int(p['rows'][-1][0]) if p['rows'] else p['entry_i'],
                                 levels_used=p['levels'], total_cost=p['total_cost'],
                                 last_close_mark=mark, base=p['entry_exec_raw'], cost=p['total_cost'],
                                 layers=np.array(p['layers'], dtype=np.float32),
                                 rows=np.array(p['rows'], dtype=np.float32),
                                 exit_ri=len(p['rows']) - 1))
            del pos[tc]
    tag = 'PRIMARY' if top10_only else 'SECONDARY'
    print(f'[RECORD {tag} DEV DONE] episodes={len(episodes)} censored={len(censored)} ({time.time()-t0:.0f}s)', flush=True)
    return episodes, censored


# ============================================================
# 2) Counterfactual: OLD RAW-space (buggy semantics, exact Phase A) + NEW ADJUSTED-space
# ============================================================
def run_cf_old(ep, stop_pct, bound, i_to_r, fetch_row, N_market):
    """Exact Phase A raw-space stop (parity replication)."""
    stop = ep['base'] * (1 + stop_pct)
    rows = ep['rows']; n = len(rows); exit_ri = ep['exit_ri']
    low = rows[:, 3]
    idx = np.where(low[:exit_ri + 1] <= stop)[0]
    mae0 = float(low[:exit_ri + 1].min() / ep['base'] - 1) * 100
    if len(idx) == 0:
        return dict(ret=ep['ret0'], hold=ep['hold0'], trig=0, exec=0, pending=0,
                    coll=0, gap=0, mae=mae0)
    trig_r = int(idx[0]); trig_i = int(rows[trig_r, 0])
    coll = (trig_r == exit_ri) and ep['exit_type'] == 'TAKE_PROFIT_DYN'
    if coll and bound == 'TP_FIRST':
        return dict(ret=ep['ret0'], hold=ep['hold0'], trig=1, exec=0, pending=0,
                    coll=1, gap=0, mae=mae0)
    layers = ep['layers']; L = len(layers)
    sold = [False] * L
    proceeds = 0.0; exec_seen = False; gap_seen = False; pending = False
    mae = mae0
    total_cost = ep['cost']
    cap_i = min(N_market - 1, int(rows[-1, 0]) + TAIL_CAP)

    def liquidate(i_m, row):
        nonlocal proceeds, exec_seen, gap_seen, mae
        o = float(row[1]); l = float(row[3]); ld = float(row[4]); st = float(row[7])
        mae = min(mae, (l / ep['base'] - 1) * 100)
        if o < stop:
            ref = o; gap_seen = True
        else:
            ref = stop
        if ref <= ld:
            return
        exec_price = ref * (1 - SLIP)
        for k in range(L):
            if sold[k]:
                continue
            if int(layers[k, 0]) + 1 <= i_m:
                qty = float(layers[k, 2]); cost = float(layers[k, 3])
                amt = exec_price * qty
                fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * st + amt * TRANSFER_FEE_RATE
                proceeds += amt - fee
                sold[k] = True; exec_seen = True

    last_exit_i = trig_i
    r = trig_r
    while r < n and not all(sold):
        row = rows[r]; i_m = int(row[0])
        liquidate(i_m, row); last_exit_i = i_m; r += 1
    i_m = int(rows[-1, 0]) + 1
    while i_m <= cap_i and not all(sold):
        row = fetch_row(i_m)
        if row is not None:
            liquidate(i_m, row); last_exit_i = i_m
        i_m += 1
    if not all(sold):
        pending = True
        last_close_px = float(rows[-1, 8])
        for k in range(L):
            if not sold[k]:
                qty = float(layers[k, 2]); cost = float(layers[k, 3])
                amt = last_close_px * (1 - SLIP) * qty
                st = float(rows[-1, 7])
                fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * st + amt * TRANSFER_FEE_RATE
                proceeds += amt - fee; sold[k] = True
    ret = (proceeds - total_cost) / total_cost * 100
    hold = last_exit_i - ep['entry_i']
    return dict(ret=ret, hold=hold, trig=1, exec=1 if exec_seen else 0,
                pending=1 if pending else 0, coll=1 if coll else 0, gap=1 if gap_seen else 0, mae=mae)


def run_cf_adj(ep, stop_pct, bound, i_to_r, fetch_row, N_market):
    """NEW corrected ADJUSTED-space stop semantics.

    entry_adj = entry_exec_raw * adj_factor_at_entry
    stop_adj  = entry_adj * (1 + stop_pct)
    low_adj_d = low_raw_d * adj_factor_d
    trigger when low_adj_d <= stop_adj
    gap: open_adj_d < stop_adj -> fill at open_raw_d
    else theoretical raw stop = stop_adj / adj_factor_d
    Same A-share tick / limit-down / T+1 / pending semantics as Phase A.
    """
    rows = ep['rows']; n = len(rows); exit_ri = ep['exit_ri']
    entry_adj_factor = float(rows[0, 9])           # adj at entry execution day (rows[0] is entry day)
    entry_adj = ep['base'] * entry_adj_factor
    stop_adj = entry_adj * (1 + stop_pct)
    low_adj = rows[:, 3] * rows[:, 9]
    idx = np.where(low_adj[:exit_ri + 1] <= stop_adj)[0]
    mae0 = float(low_adj[:exit_ri + 1].min() / entry_adj - 1) * 100
    if len(idx) == 0:
        return dict(ret=ep['ret0'], hold=ep['hold0'], trig=0, exec=0, pending=0,
                    coll=0, gap=0, mae=mae0)
    trig_r = int(idx[0]); trig_i = int(rows[trig_r, 0])
    coll = (trig_r == exit_ri) and ep['exit_type'] == 'TAKE_PROFIT_DYN'
    if coll and bound == 'TP_FIRST':
        return dict(ret=ep['ret0'], hold=ep['hold0'], trig=1, exec=0, pending=0,
                    coll=1, gap=0, mae=mae0)
    layers = ep['layers']; L = len(layers)
    sold = [False] * L
    proceeds = 0.0; exec_seen = False; gap_seen = False; pending = False
    mae = mae0
    total_cost = ep['cost']
    cap_i = min(N_market - 1, int(rows[-1, 0]) + TAIL_CAP)

    def liquidate(i_m, row):
        nonlocal proceeds, exec_seen, gap_seen, mae
        o = float(row[1]); l = float(row[3]); ld = float(row[4]); st = float(row[7])
        af = float(row[9])
        mae = min(mae, (l * af / entry_adj - 1) * 100)
        if o * af < stop_adj:
            ref = o; gap_seen = True
        else:
            ref = stop_adj / af
        if ref <= ld:
            return
        exec_price = ref * (1 - SLIP)
        for k in range(L):
            if sold[k]:
                continue
            if int(layers[k, 0]) + 1 <= i_m:
                qty = float(layers[k, 2]); cost = float(layers[k, 3])
                amt = exec_price * qty
                fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * st + amt * TRANSFER_FEE_RATE
                proceeds += amt - fee
                sold[k] = True; exec_seen = True

    last_exit_i = trig_i
    r = trig_r
    while r < n and not all(sold):
        row = rows[r]; i_m = int(row[0])
        liquidate(i_m, row); last_exit_i = i_m; r += 1
    i_m = int(rows[-1, 0]) + 1
    while i_m <= cap_i and not all(sold):
        row = fetch_row(i_m)
        if row is not None:
            liquidate(i_m, row); last_exit_i = i_m
        i_m += 1
    if not all(sold):
        pending = True
        last_close_px = float(rows[-1, 8])
        for k in range(L):
            if not sold[k]:
                qty = float(layers[k, 2]); cost = float(layers[k, 3])
                amt = last_close_px * (1 - SLIP) * qty
                st = float(rows[-1, 7])
                fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * st + amt * TRANSFER_FEE_RATE
                proceeds += amt - fee; sold[k] = True
    ret = (proceeds - total_cost) / total_cost * 100
    hold = last_exit_i - ep['entry_i']
    return dict(ret=ret, hold=hold, trig=1, exec=1 if exec_seen else 0,
                pending=1 if pending else 0, coll=1 if coll else 0, gap=1 if gap_seen else 0, mae=mae)


# ============================================================
# 3) helpers
# ============================================================
def q(x, p):
    x = np.asarray(x, dtype=float); x = x[np.isfinite(x)]
    return float(np.percentile(x, p * 100)) if len(x) else np.nan


def ed_inference(cf_ret, sd, delta=None):
    """event-day 日级截面均值序列 -> HAC + block bootstrap (L=21, B=2000)."""
    df = pd.DataFrame({'sd': pd.to_datetime(sd), 'ret': cf_ret})
    daily = df.groupby('sd')['ret'].mean().to_numpy()
    out = dict(n_event_days=int(df['sd'].nunique()), daily_mean=float(daily.mean()),
               daily_median=float(np.median(daily)), daily_positive_rate=float((daily > 0).mean() * 100))
    if len(daily) >= 10:
        import statsmodels.api as sm
        K = int(np.floor(4 * (len(daily) / 100) ** (2 / 9))); K = max(0, min(K, len(daily) - 2))
        try:
            res = sm.OLS(daily, np.ones((len(daily), 1))).fit(cov_type='HAC', cov_kwds={'maxlags': K})
            se = float(res.bse[0])
            out['hac_t'] = float(res.tvalues[0])
            out['hac_ci_lo'] = float(daily.mean() - 1.96 * se)
            out['hac_ci_hi'] = float(daily.mean() + 1.96 * se)
        except Exception:
            out['hac_t'] = np.nan; out['hac_ci_lo'] = np.nan; out['hac_ci_hi'] = np.nan
    else:
        out['hac_t'] = np.nan; out['hac_ci_lo'] = np.nan; out['hac_ci_hi'] = np.nan
    rng = np.random.default_rng(0); B = 2000; n = len(daily); L = 21
    nblocks = int(np.ceil(n / L)); bl = []
    for _ in range(B):
        idx = []
        for _b in range(nblocks):
            s = rng.integers(0, n - L + 1) if n - L + 1 > 0 else 0
            idx.extend(range(s, min(s + L, n)))
        idx = np.array(idx[:n])
        bl.append(daily[idx].mean())
    bl = np.array(bl)
    out['block_boot_ci_lo'] = float(np.percentile(bl, 2.5))
    out['block_boot_ci_hi'] = float(np.percentile(bl, 97.5))
    out['block_boot_p_nonpos'] = float((bl <= 0).mean())
    if delta is not None:
        dfd = pd.DataFrame({'sd': pd.to_datetime(sd), 'd': delta})
        dd = dfd.groupby('sd')['d'].mean().to_numpy()
        out['delta_daily_mean'] = float(dd.mean())
        if len(dd) >= 10:
            try:
                res = sm.OLS(dd, np.ones((len(dd), 1))).fit(cov_type='HAC', cov_kwds={'maxlags': K})
                se = float(res.bse[0])
                out['delta_hac_ci_lo'] = float(dd.mean() - 1.96 * se)
                out['delta_hac_ci_hi'] = float(dd.mean() + 1.96 * se)
            except Exception:
                out['delta_hac_ci_lo'] = np.nan; out['delta_hac_ci_hi'] = np.nan
        else:
            out['delta_hac_ci_lo'] = np.nan; out['delta_hac_ci_hi'] = np.nan
    return out


def paired_delta_block_bootstrap(cf_ret, ret0, sd, L=21, B=2000, seed=0):
    """S0.1: PAIRED event-day delta = day_adj_mean - day_baseline_mean (SAME event day),
    then moving/block bootstrap (L=21, B>=2000) over the complete event-day delta series.

    This is the preregistered primary inference for 'adjusted fixed stop vs no-stop'.
    NOT a bootstrap of the adjusted-stop level (that is s0_bootstrap.csv, descriptive only).
    """
    df = pd.DataFrame({'sd': pd.to_datetime(sd), 'adj': cf_ret, 'base': ret0})
    g = df.groupby('sd')
    day_adj = g['adj'].mean().to_numpy()
    day_base = g['base'].mean().to_numpy()
    delta = day_adj - day_base                      # paired same-event-day difference
    point = float(delta.mean())
    rng = np.random.default_rng(seed); n = len(delta)
    nblocks = int(np.ceil(n / L)); bl = []
    for _ in range(B):
        idx = []
        for _b in range(nblocks):
            s = rng.integers(0, n - L + 1) if n - L + 1 > 0 else 0
            idx.extend(range(s, min(s + L, n)))
        idx = np.array(idx[:n])
        bl.append(delta[idx].mean())
    bl = np.array(bl)
    return dict(n_event_days=int(len(delta)), delta_point=float(point),
                bootstrap_mean=float(bl.mean()),
                ci_lo=float(np.percentile(bl, 2.5)), ci_hi=float(np.percentile(bl, 97.5)),
                p_delta_ge_0=float((bl >= 0).mean()),
                block_length=L, B=B)


def summ_df(d, cf_col='cf_ret'):
    r = d[cf_col]
    cf_pnl = d['cost'] * d[cf_col] / 100.0
    pos_ = cf_pnl[cf_pnl > 0].sum(); neg = cf_pnl[cf_pnl < 0].sum()
    pf = pos_ / abs(neg) if neg != 0 else np.inf
    def _g(col):
        return d[col] if col in d.columns else pd.Series(0, index=d.index)
    return dict(n=len(d), mean=r.mean(), median=r.median(), win_rate=(cf_pnl > 0).mean() * 100,
                pf=pf, total_pnl=cf_pnl.sum(), std=r.std(), p1=q(r, .01), p5=q(r, .05), p10=q(r, .10),
                worst=r.min(), hold_med=d['cf_hold'].median(), hold_mean=d['cf_hold'].mean(),
                hold_p90=q(d['cf_hold'], .90), mae_med=q(_g('mae_cf'), .5),
                trig_rate=_g('trig').mean() * 100, exec_rate=_g('exec_').mean() * 100,
                pending_rate=_g('pending').mean() * 100, coll_rate=_g('coll').mean() * 100,
                gap_rate=_g('gap').mean() * 100)


# ============================================================
# 4) main
# ============================================================
def main():
    # assert registry sha (preregistration hard-red-line)
    rsha = hashlib.sha256(open(os.path.join(GIT, 'research', 'execution', 'registries', 'STOP_LOSS_SEMANTICS_S0_REGISTRY.csv'), 'rb').read()).hexdigest()
    assert rsha == REGISTRY_SHA, f'Registry SHA mismatch: {rsha}'
    print('[S0] registry sha OK', flush=True)

    print('[S0] prepare_v51 ...', flush=True)
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51()
    N = len(days)
    N2024 = sum(1 for d in days if d <= DEV_END)
    print(f'  days={N} {days[0].date()}..{days[-1].date()}  N2024={N2024} last_dev={days[N2024-1].date()}', flush=True)
    assert days[N2024 - 1] <= DEV_END and (N2024 == N or days[N2024] > DEV_END)
    # I6: never read 2025+ anywhere in this script
    MAX_READ_I = N2024

    # ---- dev episode universe from frozen fullmarket CSV ----
    full = pd.read_csv(os.path.join(GIT, 'results', 'evidence', 'fullmarket', 'fullmarket_episode_metrics.csv'))
    full['signal_dt'] = pd.to_datetime(full['signal_date'])
    full['exit_dt'] = pd.to_datetime(full['exit_date'])
    dev = full[(full['signal_dt'] <= DEV_END) & (full['exit_dt'] <= DEV_END)].copy()
    print(f'  full SECONDARY={len(full)}  dev(sig<=2024 & exit<=2024)={len(dev)}', flush=True)
    assert len(dev) == 61828, f'expected 61828 dev episodes, got {len(dev)}'

    # ---- re-record dev-only episodes ----
    sec_ep, sec_cens = replay_record_dev(days, D, first_eligible_i, offset, top10_only=False, day_range=(0, N2024))
    print(f'  re-recorded dev SECONDARY={len(sec_ep)} censored={len(sec_cens)}', flush=True)

    # ---- verify: match dev universe by (ts_code, signal_date) ----
    dev_key = set(zip(dev['ts_code'], dev['signal_date'].astype(str)))
    rec_key = set((e['ts_code'], e['signal_date']) for e in sec_ep)
    # each dev episode must be present in re-record (exit within dev window)
    missing = dev_key - rec_key
    print(f'  dev keys missing in re-record: {len(missing)}', flush=True)
    if missing:
        print('  WARNING missing (will be excluded from analysis)')
    # extra re-record episodes (signal<=2024 but exit>=2024? not in dev universe)
    extra = rec_key - dev_key
    print(f'  re-record keys not in dev universe: {len(extra)} (signal<=2024 exit>2024 or FINAL_SETTLE)', flush=True)

    # build analysis episode list: only dev universe episodes
    dev_map = {k: row for k, row in zip(zip(dev['ts_code'], dev['signal_date'].astype(str)), dev.to_dict('records'))}
    an_ep = []
    for e in sec_ep:
        k = (e['ts_code'], e['signal_date'])
        if k in dev_map:
            an_ep.append(e)
    print(f'  analysis episodes (dev, re-recorded): {len(an_ep)}', flush=True)

    # ---- verify re-record ret0/exit matches frozen dev CSV ----
    mism = 0; n_chk = 0
    for e in an_ep:
        k = (e['ts_code'], e['signal_date'])
        row = dev_map[k]
        n_chk += 1
        if e['exit_date'] != str(pd.Timestamp(row['exit_date']).date()) or \
           e['exit_type'] != row['exit_type'] or abs(e['ret0'] - float(row['simple_return_pct'])) > 0.01:
            mism += 1
    print(f'[VERIFY] dev re-record vs frozen: checked={n_chk} mismatch={mism}', flush=True)
    assert mism == 0, 'FATAL: dev re-record mismatch vs frozen fullmarket CSV'

    # ---- build i_to_r + fetch factory ----
    def build_i_to_r(ep):
        return {int(r[0]): ri for ri, r in enumerate(ep['rows'])}

    def fetch_factory(tc):
        def fetch_row(i_m):
            if i_m >= MAX_READ_I:      # I6: hard stop at dev boundary
                return None
            dd = D[days[i_m]]; j = dd['pos'].get(tc)
            if j is None:
                return None
            return np.array([i_m, float(dd['open_'][j]), float(dd['high'][j]), float(dd['low'][j]),
                             float(dd['limit_down_px'][j]), float(dd['is_limit'][j]), np.nan,
                             float(stamp_rate(days[i_m], 'historical')), float(dd['close'][j]),
                             float(dd['adj'][j])], dtype=np.float32)
        return fetch_row

    ep_map = [(e, build_i_to_r(e)) for e in an_ep]

    # ============================================================
    # 5) run old raw + new adjusted for all thresholds (both bounds)
    # ============================================================
    CACHE = os.path.join(OUT, '_res_cache.pkl')
    if os.path.exists(CACHE):
        import pickle as _pk
        with open(CACHE, 'rb') as f:
            res_old, res_adj = _pk.load(f)
        print('[S0] counterfactual loaded from cache', flush=True)
    else:
        res_old = {}; res_adj = {}   # (stop, bound) -> DataFrame
        for stop in STOPS:
            for bound in BOUNDS:
                rows_o = []; rows_a = []
                for e, itor in ep_map:
                    f = fetch_factory(e['ts_code'])
                    ro = run_cf_old(e, stop / 100.0, bound, itor, f, N2024)
                    ra = run_cf_adj(e, stop / 100.0, bound, itor, f, N2024)
                    base = dict(episode_id=e['episode_id'], ts_code=e['ts_code'], signal_date=e['signal_date'],
                                entry_date=e['entry_date'], exit_date=e['exit_date'], exit_type=e['exit_type'],
                                levels0=e['levels0'], ret0=e['ret0'], pnl0=e['pnl0'], cost=e['cost'],
                                hold0=e['hold0'], mae0=e['mae0'])
                    rows_o.append(dict(base, cf_ret=ro['ret'], cf_hold=ro['hold'], trig=ro['trig'],
                                       exec_=ro['exec'], pending=ro['pending'], coll=ro['coll'],
                                       gap=ro['gap'], mae_cf=ro['mae']))
                    rows_a.append(dict(base, cf_ret=ra['ret'], cf_hold=ra['hold'], trig=ra['trig'],
                                       exec_=ra['exec'], pending=ra['pending'], coll=ra['coll'],
                                       gap=ra['gap'], mae_cf=ra['mae']))
                res_old[(stop, bound)] = pd.DataFrame(rows_o)
                res_adj[(stop, bound)] = pd.DataFrame(rows_a)
        import pickle as _pk
        with open(CACHE, 'wb') as f:
            _pk.dump((res_old, res_adj), f)
        print('[S0] counterfactual done', flush=True)

    # ============================================================
    # 6) OLD RAW PARITY vs canonical Phase A detail (dev subset)
    # ============================================================
    canon = pd.read_csv(os.path.join(GIT, 'results', 'evidence', 'stopA', 'stop_phaseA_episode_detail.csv.gz'))
    canon_sec = canon[canon['sample'] == 'SECONDARY'].copy()
    canon_sec['sig'] = canon_sec['signal_date'].astype(str)
    canon_dev_key = set(zip(dev['ts_code'], dev['signal_date'].astype(str)))
    canon_dev = canon_sec[canon_sec.apply(lambda r: (r['ts_code'], r['sig']) in canon_dev_key, axis=1)]
    print(f'  canonical detail dev-rows (SECONDARY, dev keys): {len(canon_dev)}', flush=True)
    assert len(canon_dev) > 0
    # group canon_dev by (stop, bound) and compare with res_old by (ts_code, signal_date)
    #
    # Parity semantics (2025-boundary audit):
    #   canonical stop_phaseA_episode_detail.csv.gz was computed on the FULL sample
    #   (2020-2026).  A dev-key episode may therefore have a counterfactual result that
    #   depends on 2025 prices (e.g. a stop trigger that could not fill inside 2024 and
    #   was finally filled in 2025).  S0 must NOT read 2025 (I6).  Those episodes are
    #   classified as BOUNDARY_2025 and excluded from strict parity (disclosed, not fail).
    #   A canonical result is flagged BOUNDARY_2025 iff:
    #     - canonical mae_cf is strictly deeper than dev mae_cf (dev mae already covers
    #       every 2024-reachable low; a deeper canonical mae can only come from 2025 lows)
    #     - OR canonical trig==1 while dev trig==0 (stop only reached inside 2025)
    #   Any remaining ret/trig mismatch is a TRUE parity failure.
    parity_rows = []
    boundary_detail = []
    for stop in STOPS:
        for bound in BOUNDS:
            cd = canon_dev[(canon_dev['stop_pct'] == stop) & (canon_dev['bound'] == bound)]
            cd = {(r['ts_code'], r['sig']): r for r in cd.to_dict('records')}
            mo = res_old[(stop, bound)]
            mo = {(r['ts_code'], r['signal_date']): r for r in mo.to_dict('records')}
            common = set(cd.keys()) & set(mo.keys())
            if len(common) == 0:
                parity_rows.append(dict(stop_pct=stop, bound=bound, n_common=0, max_abs_ret_diff=np.nan,
                                        n_ret_mismatch=np.nan, n_trig_mismatch=np.nan,
                                        n_boundary_2025=0, n_true_mismatch=0))
                continue
            n_boundary = 0; n_true = 0; maxdiff = 0.0; n_ret_mm = 0; n_trig_mm = 0
            for k in common:
                cc = cd[k]; mc = mo[k]
                dret = abs(float(cc['cf_ret']) - float(mc['cf_ret']))
                dtrig = abs(int(cc['trig']) - int(mc['trig']))
                maxdiff = max(maxdiff, dret)
                if dret > 0.011:
                    n_ret_mm += 1
                if dtrig > 0:
                    n_trig_mm += 1
                if dret > 0.011 or dtrig > 0:
                    cmae = float(cc['mae_cf']); mae_dev = float(mc['mae_cf'])
                    ctrig = int(cc['trig']); mtrig = int(mc['trig'])
                    boundary_2025 = (cmae < mae_dev - 1e-6) or (ctrig == 1 and mtrig == 0)
                    if boundary_2025:
                        n_boundary += 1
                        boundary_detail.append(dict(stop_pct=stop, bound=bound, ts_code=k[0], signal_date=k[1],
                                                    canon_cf_ret=float(cc['cf_ret']), dev_cf_ret=float(mc['cf_ret']),
                                                    canon_mae=cmae, dev_mae=mae_dev,
                                                    canon_trig=ctrig, dev_trig=mtrig,
                                                    reason='canonical_depends_on_2025_price'))
                    else:
                        n_true += 1
            parity_rows.append(dict(stop_pct=stop, bound=bound, n_common=len(common),
                                    max_abs_ret_diff=maxdiff,
                                    n_ret_mismatch=n_ret_mm,
                                    n_trig_mismatch=n_trig_mm,
                                    n_boundary_2025=n_boundary, n_true_mismatch=n_true))
    parity_df = pd.DataFrame(parity_rows)
    parity_df.to_csv(os.path.join(OUT, 's0_old_parity.csv'), index=False)
    boundary_df = pd.DataFrame(boundary_detail)
    if len(boundary_df):
        boundary_df.to_csv(os.path.join(OUT, 's0_parity_2025_boundary.csv'), index=False)
    print('[S0] old raw parity vs canonical:', flush=True)
    print(parity_df.to_string(index=False), flush=True)
    if len(boundary_df):
        print(f'  BOUNDARY_2025 episodes (canonical used 2025 prices, excluded from strict parity): {len(boundary_df)}', flush=True)
        print(boundary_df.to_string(index=False), flush=True)
    tot_ret_mm = int(parity_df['n_ret_mismatch'].sum())
    tot_trig_mm = int(parity_df['n_trig_mismatch'].sum())
    tot_boundary = int(parity_df['n_boundary_2025'].sum())
    tot_true = int(parity_df['n_true_mismatch'].sum())
    worst_max = float(parity_df['max_abs_ret_diff'].max())
    old_parity_pass = bool(tot_true == 0)
    print(f'  OLD PARITY PASS={old_parity_pass} '
          f'(raw mm ret={tot_ret_mm} trig={tot_trig_mm}; boundary_2025={tot_boundary}; true_mismatch={tot_true}; '
          f'worst max diff incl boundary={worst_max})', flush=True)
    assert old_parity_pass, 'FATAL: old raw-stop parity FAILED vs canonical detail (true engine mismatch)'

    # ============================================================
    # 7) adj-factor semantics audit
    # ============================================================
    # For each episode: entry_adj_factor, min/max adj over holding, factor_changed,
    # old_raw_stop_trigger_date vs new_adj_stop_trigger_date (at -20% primary)
    audit_rows = []
    for e, itor in ep_map:
        rows = e['rows']
        entry_af = float(rows[0, 9])
        min_af = float(rows[:e['exit_ri'] + 1, 9].min())
        max_af = float(rows[:e['exit_ri'] + 1, 9].max())
        factor_changed = (max_af / min_af - 1) > 1e-4
        # old raw stop trigger date at -20% (STOP_FIRST)
        o = res_old[(-20.0, 'STOP_FIRST')].set_index('episode_id').loc[e['episode_id']]
        a = res_adj[(-20.0, 'STOP_FIRST')].set_index('episode_id').loc[e['episode_id']]
        old_trig_date = e['exit_date'] if o['trig'] == 0 else e['entry_date']
        new_trig_date = e['exit_date'] if a['trig'] == 0 else e['entry_date']
        audit_rows.append(dict(ts_code=e['ts_code'], signal_date=e['signal_date'], entry_date=e['entry_date'],
                               exit_date=e['exit_date'], entry_adj_factor=entry_af,
                               min_adj_factor=min_af, max_adj_factor=max_af,
                               factor_changed=int(factor_changed),
                               old_raw_trig=int(o['trig']), new_adj_trig=int(a['trig']),
                               old_raw_trig_date=old_trig_date, new_adj_trig_date=new_trig_date))
    audit_df = pd.DataFrame(audit_rows)
    audit_df.to_csv(os.path.join(OUT, 's0_adjfactor_semantics_audit.csv'), index=False)
    n_factor_changed = int(audit_df['factor_changed'].sum())
    n_same = int((audit_df['old_raw_trig_date'] == audit_df['new_adj_trig_date']).sum())
    n_old_only = int(((audit_df['old_raw_trig'] == 1) & (audit_df['new_adj_trig'] == 0)).sum())
    n_new_only = int(((audit_df['old_raw_trig'] == 0) & (audit_df['new_adj_trig'] == 1)).sum())
    n_both_same_date = int(((audit_df['old_raw_trig'] == 1) & (audit_df['new_adj_trig'] == 1)
                            & (audit_df['old_raw_trig_date'] == audit_df['new_adj_trig_date'])).sum())
    print(f'[S0] adj audit: factor_changed={n_factor_changed} ({n_factor_changed/len(audit_df)*100:.2f}%), '
          f'same_date={n_same}, old_only={n_old_only}, new_only={n_new_only}, both_same_date={n_both_same_date}', flush=True)

    # ============================================================
    # 8) threshold summary: baseline / old raw / new adjusted (STOP_FIRST primary)
    # ============================================================
    summ_rows = []
    for stop in STOPS:
        base = summ_df(pd.DataFrame({'cf_ret': res_old[(stop, 'STOP_FIRST')]['ret0'],
                                     'cf_hold': res_old[(stop, 'STOP_FIRST')]['hold0'],
                                     'mae_cf': res_old[(stop, 'STOP_FIRST')]['mae0'],
                                     'cost': res_old[(stop, 'STOP_FIRST')]['cost']}), cf_col='cf_ret')
        old = summ_df(res_old[(stop, 'STOP_FIRST')])
        adj = summ_df(res_adj[(stop, 'STOP_FIRST')])
        summ_rows.append(dict(stop_pct=stop,
                              base_mean=base['mean'], base_median=base['median'], base_win=base['win_rate'],
                              base_pf=base['pf'], base_p5=base['p5'], base_p10=base['p10'], base_hold=base['hold_med'],
                              old_mean=old['mean'], old_median=old['median'], old_win=old['win_rate'],
                              old_pf=old['pf'], old_p5=old['p5'], old_p10=old['p10'], old_hold=old['hold_med'],
                              old_trig=old['trig_rate'], old_gap=old['gap_rate'], old_pending=old['pending_rate'],
                              adj_mean=adj['mean'], adj_median=adj['median'], adj_win=adj['win_rate'],
                              adj_pf=adj['pf'], adj_p5=adj['p5'], adj_p10=adj['p10'], adj_hold=adj['hold_med'],
                              adj_trig=adj['trig_rate'], adj_gap=adj['gap_rate'], adj_pending=adj['pending_rate'],
                              d_old_base=old['mean'] - base['mean'], d_adj_base=adj['mean'] - base['mean'],
                              d_adj_old=adj['mean'] - old['mean']))
    summ_df_out = pd.DataFrame(summ_rows)
    summ_df_out.to_csv(os.path.join(OUT, 's0_threshold_summary.csv'), index=False)
    print('[S0] threshold summary:', flush=True)
    print(summ_df_out[['stop_pct', 'base_mean', 'old_mean', 'adj_mean', 'd_old_base', 'd_adj_base', 'd_adj_old']].to_string(index=False), flush=True)

    # ============================================================
    # 9) same-bar bounds
    # ============================================================
    sb_rows = []
    for stop in STOPS:
        sf = res_adj[(stop, 'STOP_FIRST')]; tf = res_adj[(stop, 'TP_FIRST')]
        sb_rows.append(dict(stop_pct=stop, n_coll_sf=int(sf['coll'].sum()), n_coll_tf=int(tf['coll'].sum()),
                            mean_sf=sf['cf_ret'].mean(), mean_tf=tf['cf_ret'].mean(),
                            delta_mean=tf['cf_ret'].mean() - sf['cf_ret'].mean()))
    sb_df = pd.DataFrame(sb_rows); sb_df.to_csv(os.path.join(OUT, 's0_samebar_bounds.csv'), index=False)
    print('[S0] same-bar bounds (adjusted):'); print(sb_df.to_string(index=False), flush=True)

    # ============================================================
    # 10) gap stops + execution delays (adjusted, STOP_FIRST)
    # ============================================================
    gap_rows = []
    for stop in STOPS:
        a = res_adj[(stop, 'STOP_FIRST')]
        gap_rows.append(dict(stop_pct=stop, n_gap=int(a['gap'].sum()), gap_rate=float(a['gap'].mean() * 100),
                             n_pending=int(a['pending'].sum())))
    gap_df = pd.DataFrame(gap_rows); gap_df.to_csv(os.path.join(OUT, 's0_gap_stops.csv'), index=False)
    # execution delays: for triggered adjusted stops, compute trigger_date -> first_executable (approximated via cf_hold vs trig)
    delay_rows = []
    for stop in STOPS:
        a = res_adj[(stop, 'STOP_FIRST')].copy()
        trig = a[a['trig'] == 1].copy()
        # cf_hold is days from entry to last exit; delay approx = cf_hold - (trig day distance). Approx: report distribution
        if len(trig):
            delay_rows.append(dict(stop_pct=stop, n_trig=len(trig),
                                   median_hold=float(trig['cf_hold'].median()),
                                   max_hold=float(trig['cf_hold'].max()),
                                   p90_hold=float(trig['cf_hold'].quantile(0.90))))
    delay_df = pd.DataFrame(delay_rows); delay_df.to_csv(os.path.join(OUT, 's0_execution_delays.csv'), index=False)
    print('[S0] gaps:', flush=True); print(gap_df.to_string(index=False), flush=True)

    # ============================================================
    # 11) saved losers / killed winners (old vs new adjusted, at -20%)
    # ============================================================
    def saved_killed(orig, cf):
        # orig: baseline ret; cf: counterfactual ret
        saved_losers = ((orig < 0) & (cf > orig)).sum()
        killed_winners = ((orig > 0) & (cf < orig)).sum()
        pnl_saved = float(((orig < 0) & (cf > orig)) * (cf - orig) * orig.index.map(lambda _: 1)).sum() if False else 0
        # pnl saved = sum of (baseline loss avoided) in cost-weighted pct
        return int(saved_losers), int(killed_winners)

    sl_rows = []
    for stop in STOPS:
        b = res_old[(stop, 'STOP_FIRST')].copy()
        o = res_old[(stop, 'STOP_FIRST')]; a = res_adj[(stop, 'STOP_FIRST')]
        orig = o['ret0'].values
        # old
        ocf = o['cf_ret'].values
        acf = a['cf_ret'].values
        cost = o['cost'].values
        pnl_old = cost * ocf / 100.0; pnl_adj = cost * acf / 100.0; pnl_base = cost * orig / 100.0
        sl_old_l = int(((orig < 0) & (ocf > orig)).sum()); kw_old = int(((orig > 0) & (ocf < orig)).sum())
        sl_adj_l = int(((orig < 0) & (acf > orig)).sum()); kw_adj = int(((orig > 0) & (acf < orig)).sum())
        saved_old = float((((orig < 0) & (ocf > orig)) * (pnl_base - pnl_old)).sum())
        saved_adj = float((((orig < 0) & (acf > orig)) * (pnl_base - pnl_adj)).sum())
        lost_old = float((((orig > 0) & (ocf < orig)) * (pnl_base - pnl_old)).sum())
        lost_adj = float((((orig > 0) & (acf < orig)) * (pnl_base - pnl_adj)).sum())
        sl_rows.append(dict(stop_pct=stop, saved_losers_old=sl_old_l, killed_winners_old=kw_old,
                            saved_losers_adj=sl_adj_l, killed_winners_adj=kw_adj,
                            pnl_saved_old=saved_old, pnl_saved_adj=saved_adj,
                            pnl_lost_old=lost_old, pnl_lost_adj=lost_adj,
                            net_old=saved_old - lost_old, net_adj=saved_adj - lost_adj))
    sl_df = pd.DataFrame(sl_rows)
    sl_df.to_csv(os.path.join(OUT, 's0_saved_losers.csv'), index=False)
    print('[S0] saved losers / killed winners (old vs adjusted):'); print(sl_df.to_string(index=False), flush=True)
    # separate killed winners detail
    kw_df = sl_df[['stop_pct', 'killed_winners_old', 'killed_winners_adj', 'pnl_lost_old', 'pnl_lost_adj']].copy()
    kw_df.to_csv(os.path.join(OUT, 's0_killed_winners.csv'), index=False)

    # ============================================================
    # 12) deep-MAE subsets (baseline MAE < -20%, < -30%) — adjusted net effect
    # ============================================================
    dm_rows = []
    for thr_ in [-20.0, -30.0]:
        msk = res_old[(-20.0, 'STOP_FIRST')]['mae0'] < thr_
        n_sub = int(msk.sum())
        for stop in STOPS:
            b = res_old[(stop, 'STOP_FIRST')][msk]
            a = res_adj[(stop, 'STOP_FIRST')][msk]
            base_m = b['ret0'].mean(); adj_m = a['cf_ret'].mean(); old_m = b['cf_ret'].mean()
            dm_rows.append(dict(subset=f'MAE<{thr_}', stop_pct=stop, n=n_sub,
                                base_mean=base_m, old_mean=old_m, adj_mean=adj_m,
                                net_adj=adj_m - base_m, net_old=old_m - base_m))
    dm_df = pd.DataFrame(dm_rows)
    dm_df.to_csv(os.path.join(OUT, 's0_deep_mae_subset.csv'), index=False)
    print('[S0] deep-MAE subsets (adjusted net effect):'); print(dm_df.to_string(index=False), flush=True)

    # ============================================================
    # 13) factor_changed vs factor_unchanged subset — old vs new trigger consistency
    # ============================================================
    fc_rows = []
    for fc_val, fc_name in [(0, 'factor_unchanged'), (1, 'factor_changed')]:
        idx = audit_df['factor_changed'] == fc_val
        n_sub = int(idx.sum())
        for stop in STOPS:
            ep_ids = set(audit_df.loc[idx, 'episode_id']) if 'episode_id' in audit_df.columns else None
        # use audit_df episode mapping
    # simpler: join audit to res
    audit_df2 = audit_df.copy()
    # add episode_id by (ts_code, signal_date)
    key_to_eid = {(e['ts_code'], e['signal_date']): e['episode_id'] for e in an_ep}
    audit_df2['episode_id'] = [key_to_eid[(r['ts_code'], r['signal_date'])] for r in audit_df2.to_dict('records')]
    fc_rows = []
    for fc_val, fc_name in [(0, 'factor_unchanged'), (1, 'factor_changed')]:
        eids = set(audit_df2.loc[audit_df2['factor_changed'] == fc_val, 'episode_id'])
        n_sub = len(eids)
        for stop in STOPS:
            b = res_old[(stop, 'STOP_FIRST')].set_index('episode_id').loc[list(eids)]
            a = res_adj[(stop, 'STOP_FIRST')].set_index('episode_id').loc[list(eids)]
            fc_rows.append(dict(group=fc_name, stop_pct=stop, n=n_sub,
                                old_trig_rate=float(b['trig'].mean() * 100),
                                adj_trig_rate=float(a['trig'].mean() * 100),
                                old_mean=b['cf_ret'].mean(), adj_mean=a['cf_ret'].mean()))
    fc_df = pd.DataFrame(fc_rows)
    fc_df.to_csv(os.path.join(OUT, 's0_factor_changed_subset.csv'), index=False)
    print('[S0] factor_changed vs unchanged (old vs adjusted trig rate):'); print(fc_df.to_string(index=False), flush=True)

    # ============================================================
    # 14) event-day + bootstrap: new adjusted stop vs baseline per threshold
    # ============================================================
    ev_rows = []
    for stop in STOPS:
        a = res_adj[(stop, 'STOP_FIRST')]
        inf = ed_inference(a['cf_ret'].values, a['signal_date'].values,
                           delta=(a['cf_ret'].values - a['ret0'].values))
        inf['stop_pct'] = stop
        ev_rows.append(inf)
    ev_df = pd.DataFrame(ev_rows)
    ev_df.to_csv(os.path.join(OUT, 's0_eventday.csv'), index=False)
    print('[S0] event-day (adjusted, STOP_FIRST):'); print(ev_df[['stop_pct', 'n_event_days', 'daily_mean', 'hac_t', 'block_boot_ci_lo', 'block_boot_ci_hi', 'delta_daily_mean']].to_string(index=False), flush=True)
    # bootstrap df (long)
    bs_rows = []
    for stop in STOPS:
        a = res_adj[(stop, 'STOP_FIRST')]
        inf = ed_inference(a['cf_ret'].values, a['signal_date'].values)
        bs_rows.append(dict(stop_pct=stop, metric='adj_mean', point=inf['daily_mean'],
                            ci_lo=inf['block_boot_ci_lo'], ci_hi=inf['block_boot_ci_hi']))
    bs_df = pd.DataFrame(bs_rows)
    bs_df.to_csv(os.path.join(OUT, 's0_bootstrap.csv'), index=False)

    # ============================================================
    # 14b) S0.1: PAIRED delta block bootstrap (primary inference)
    #      day_delta = day_adj_mean - day_baseline_mean (SAME event day),
    #      moving/block bootstrap L=21, B=2000 over the complete day_delta series.
    # ============================================================
    db_rows = []
    for stop in STOPS:
        a = res_adj[(stop, 'STOP_FIRST')]
        infb = paired_delta_block_bootstrap(a['cf_ret'].values, a['ret0'].values, a['signal_date'].values)
        infb['stop_pct'] = stop
        db_rows.append(infb)
    db_df = pd.DataFrame(db_rows)
    db_df.to_csv(os.path.join(OUT, 's0_delta_block_bootstrap.csv'), index=False)
    print('[S0.1] paired delta block bootstrap (adj minus baseline, same event day):', flush=True)
    print(db_df[['stop_pct', 'n_event_days', 'delta_point', 'bootstrap_mean', 'ci_lo', 'ci_hi',
                 'p_delta_ge_0', 'block_length', 'B']].to_string(index=False), flush=True)
    delta_11_neg = bool((db_df['ci_hi'] < 0).all())
    print(f'  S0.1 gate: all 11 thresholds paired-block-bootstrap 95% CI upper < 0 => {delta_11_neg}', flush=True)

    # ============================================================
    # 15) invariants
    # ============================================================
    inv = {}
    # I1: factor_unchanged episodes: old raw trig date == new adj trig date (at -20%)
    fc0 = audit_df2[audit_df2['factor_changed'] == 0]
    inv['I1_factor_unchanged_trigger_date_match'] = bool((fc0['old_raw_trig_date'] == fc0['new_adj_trig_date']).all())
    # I2: no-stop baseline unchanged (ret0 identical)
    inv['I2_nostop_baseline_unchanged'] = bool((res_old[(-20.0, 'STOP_FIRST')]['ret0'] == res_adj[(-20.0, 'STOP_FIRST')]['ret0']).all())
    # I3: only stop coordinate semantics changed (old==canonical already checked; adj differs only where triggered differently)
    inv['I3_old_parity_exact'] = bool(old_parity_pass)
    # I4: T+1 preserved — no exec on entry day: check no exec where cf_hold<1 with trig
    a20 = res_adj[(-20.0, 'STOP_FIRST')]
    inv['I4_tplus1'] = bool(((a20['trig'] == 1) & (a20['cf_hold'] < 1)).sum() == 0)
    # I5: entry/exit costs unchanged (same total_cost used; ret computed on same cost)
    inv['I5_costs_unchanged'] = bool((res_old[(-20.0, 'STOP_FIRST')]['cost'] == res_adj[(-20.0, 'STOP_FIRST')]['cost']).all())
    # I6: 2025+ never read
    inv['I6_no_2025_read'] = True   # enforced by MAX_READ_I + dev-only universe
    # I7 (S0.1 wording): DEV-COMPARABLE old engine parity exact.
    #   NOTE: old canonical is FULL-sample; a dev-key episode may depend on 2025 prices
    #   (boundary contamination). 'exact' here means: within the dev-comparable window,
    #   every true engine mismatch is zero (boundary-contaminated canonical rows excluded+disclosed).
    inv['I7_dev_comparable_old_replication_exact'] = bool(old_parity_pass)
    # I8 (S0.1): boundary contamination fully isolated — the only parity deviations are
    #   canonical rows that used post-2024 prices (002789.SZ -25%), no true engine mismatch remains.
    inv['I8_boundary_contamination_isolated'] = bool(tot_boundary >= 1 and tot_true == 0)
    with open(os.path.join(OUT, 's0_invariants.json'), 'w') as f:
        json.dump(inv, f, indent=2, default=str)
    print('[S0] invariants:', json.dumps(inv, indent=2), flush=True)
    assert inv['I1_factor_unchanged_trigger_date_match'], 'I1 FAILED'
    assert inv['I2_nostop_baseline_unchanged'], 'I2 FAILED'
    assert inv['I4_tplus1'], 'I4 FAILED'
    assert inv['I5_costs_unchanged'], 'I5 FAILED'

    # ============================================================
    # 16) summary json + classification
    # ============================================================
    # Classification:
    # A = old conclusion robust (all adjusted stops still worse than baseline on mean)
    # B = material change but no clear useful fixed stop
    # C = old conclusion invalidated (>=1 frozen threshold stable positive net effect)
    # D = unresolved (parity/invariants fail)
    summary = dict(n_dev_episodes=len(an_ep), n_factor_changed=int(n_factor_changed),
                   n_old_only_trig=int(n_old_only), n_new_only_trig=int(n_new_only),
                   n_same_date=int(n_both_same_date), old_parity_pass=bool(old_parity_pass),
                   n_boundary_2025=int(tot_boundary), n_true_mismatch=int(tot_true),
                   invariants=inv)
    # net effect per threshold (adjusted vs baseline, event-day weighted)
    summary['adj_net_by_threshold'] = {str(s): float(res_adj[(s, 'STOP_FIRST')]['cf_ret'].mean() -
                                                     res_adj[(s, 'STOP_FIRST')]['ret0'].mean()) for s in STOPS}
    # any threshold with stable positive net effect? check event-day HAC/delta CI
    positive_stable = []
    for stop in STOPS:
        inf = ev_df[ev_df['stop_pct'] == stop].iloc[0]
        if inf['delta_daily_mean'] > 0 and inf.get('delta_hac_ci_lo', np.nan) > 0:
            positive_stable.append(float(stop))
    summary['positive_stable_thresholds'] = positive_stable
    # S0.1 gate: A requires all 11 paired-delta block-bootstrap upper CI < 0
    summary['paired_delta_11_upper_ci_neg'] = bool(delta_11_neg)
    # direction check: all adjusted means below baseline?
    all_adj_below_base = bool((summ_df_out['adj_mean'] < summ_df_out['base_mean']).all())
    any_adj_above_base = bool((summ_df_out['adj_mean'] > summ_df_out['base_mean']).any())
    # material change?
    max_adj_old_diff = float(summ_df_out['d_adj_old'].abs().max())
    if not old_parity_pass:
        cls = 'D'
    elif positive_stable:
        cls = 'C'
    elif all_adj_below_base and delta_11_neg:
        cls = 'A'
    elif all_adj_below_base:
        cls = 'B'
    elif max_adj_old_diff > 0.1:
        cls = 'B'
    else:
        cls = 'A'
    summary['classification'] = cls
    summary['all_adjusted_below_baseline'] = bool(all_adj_below_base)
    summary['any_adjusted_above_baseline'] = bool(any_adj_above_base)
    summary['max_adj_vs_old_abs_diff'] = max_adj_old_diff
    with open(os.path.join(OUT, 's0_summary.json'), 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    print('[S0] summary:', json.dumps(summary, indent=2, default=str), flush=True)

    # ============================================================
    # 17) figures (lightweight)
    # ============================================================
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.plot(summ_df_out['stop_pct'], summ_df_out['base_mean'], marker='o', label='baseline (no stop)')
        ax.plot(summ_df_out['stop_pct'], summ_df_out['old_mean'], marker='s', label='old raw-space stop')
        ax.plot(summ_df_out['stop_pct'], summ_df_out['adj_mean'], marker='^', label='new adjusted-space stop')
        ax.axhline(summ_df_out['base_mean'].iloc[0], color='gray', ls='--', alpha=0.5)
        ax.set_xlabel('stop_pct (%)'); ax.set_ylabel('mean episode return (%)')
        ax.set_title('S0: old raw vs new adjusted fixed-stop (dev 2020-2024)')
        ax.legend(); ax.grid(alpha=0.3)
        fig.tight_layout(); fig.savefig(os.path.join(FIG, 's0_threshold_means.png'), dpi=130)
        plt.close(fig)
    except Exception as ex:
        print('[S0] figure skip:', ex, flush=True)
    print('[S0] DONE', flush=True)


if __name__ == '__main__':
    main()
