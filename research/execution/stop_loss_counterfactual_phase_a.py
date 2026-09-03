"""
==========================================================
STOP-LOSS COUNTERFACTUAL — PHASE A
STRICT_C / FULL-MARKET SECONDARY + PRIMARY BENCHMARK
==========================================================
FROZEN-EPISODE COUNTERFACTUAL on the audited V2A_FROZEN_STRICT episodes
(PRIMARY Top10 299; SECONDARY all-eligible 89,046 realized + 124 censored).

Only study: FIXED PRICE STOP on FIRST ENTRY EXECUTION PRICE.
Forbidden: exit P*, BB, entry, Top10, max levels, add rule changes; no time/trailing/
regime/ranking filter; no joint optimization.

Frozen-episode discipline:
  - initial signal / entry / adds are taken from the frozen baseline (re-recorded with
    per-layer + per-day path, verified against frozen pkl / fullmarket CSV).
  - The counterfactual NEVER releases held slots to create new signals (no re-run of the
    signal-generation system). It only re-plays each episode's own path under the stop.
  - STOP_TRIGGERED -> NO FURTHER ADD.
  - Partial-sell T+1 legal semantics (sell unlocked layers only; locked layers liquidated
    at first unlocked day).
  - Stop-market: gap-through at open if open<stop; else fill at stop; reachability
    requires exec ref > limit_down_px (else STOP_PENDING, carried).
  - P* TP (baseline exit) unchanged; same-day stop/TP collision -> STOP_FIRST / TP_FIRST
    bounds (collision only possible on the baseline TP exit day).
  - Censored 124 handled as 3 sensitivity口径 (REALIZED_ONLY / CENSORED_PESSIMISTIC /
    STOP_RESCUED_CENSORED).

No Validation opened. Registry frozen.
==========================================================
"""
import os, sys, pickle, time
import numpy as np, pandas as pd
from collections import Counter, deque

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT); sys.path.insert(0, REPO)
from round51_audit import prepare_v51, stamp_rate, COMMISSION_RATE, MIN_COMMISSION, TRANSFER_FEE_RATE
from run_strict_c_math import analytic_Pstar

OUT = os.path.join(REPO, 'results'); os.makedirs(OUT, exist_ok=True)
FIG = os.path.join(REPO, 'figures'); os.makedirs(FIG, exist_ok=True)
LEVEL_CASH = 200_000.0; MAX_LEVELS = 5; SLIP = 0.001; ADD_GAP = 1
STOPS = [-10.0, -12.5, -15.0, -17.5, -20.0, -22.5, -25.0, -27.5, -30.0, -35.0, -40.0]
BOUNDS = ['STOP_FIRST', 'TP_FIRST']
TAIL_CAP = 180


# ============================================================
# 1) Re-record frozen episodes with layers + per-day path
# ============================================================
def replay_record(days, D, first_eligible_i, offset, top10_only):
    N = len(days)
    pos = {}; pending_buy = []; pending_add = {}; pending_sell = set()
    raw_hist = {}; episodes = []; censored = []; last_close = {}
    episode_seq = [0]

    def day_row(i, dd, j, thr):
        return np.array([i, float(dd['open_'][j]), float(dd['high'][j]), float(dd['low'][j]),
                         float(dd['limit_down_px'][j]), float(dd['is_limit'][j]), thr,
                         float(stamp_rate(days[i], 'historical')), float(dd['close'][j])], dtype=np.float32)

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
            if i - k < 0:
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
            finalize(tc, d, dd['open_'][j] * (1 - SLIP), 'TAKE_PROFIT_UB', i, pos[tc])
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
                    pending_buy.remove(pb); continue     # CANCEL
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
    # ---- 期末 ----
    d_last = days[-1]; dd_last = D[d_last]
    for tc in list(pos.keys()):
        j = dd_last['pos'].get(tc)
        if j is not None:
            finalize(tc, d_last, dd_last['close'][j] * (1 - SLIP), 'FINAL_SETTLE', N - 1, pos[tc])
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
    print(f'[RECORD {tag} DONE] episodes={len(episodes)} '
          f'({Counter(e["exit_type"] for e in episodes)}) censored={len(censored)} ({time.time()-t0:.0f}s)', flush=True)
    return episodes, censored


# ============================================================
# 2) Counterfactual engine
# ============================================================
def build_i_to_r(ep):
    rows = ep['rows']; n = len(rows)
    return {int(rows[r, 0]): r for r in range(n)}


def run_cf(ep, stop_pct, bound, i_to_r, fetch_row, N_market):
    stop = ep['base'] * (1 + stop_pct)
    rows = ep['rows']; n = len(rows); exit_ri = ep['exit_ri']
    low = rows[:, 3]
    idx = np.where(low[:exit_ri + 1] <= stop)[0]
    mae0 = float(low[:exit_ri + 1].min() / ep['base'] - 1) * 100
    if len(idx) == 0:
        return dict(ret=ep['ret0'], hold=ep['hold0'], trig=0, exec=0, pending=0,
                    coll=0, gap=0, mae=mae0)
    trig_r = int(idx[0])
    trig_i = int(rows[trig_r, 0])
    coll = (trig_r == exit_ri) and ep['exit_type'] == 'TAKE_PROFIT_DYN'
    if coll and bound == 'TP_FIRST':
        return dict(ret=ep['ret0'], hold=ep['hold0'], trig=1, exec=0, pending=0,
                    coll=1, gap=0, mae=mae0)
    # ---- STOP path ----
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
            if int(layers[k, 0]) + 1 <= i_m:     # T+1 unlocked
                qty = float(layers[k, 2]); cost = float(layers[k, 3])
                amt = exec_price * qty
                fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * st + amt * TRANSFER_FEE_RATE
                proceeds += amt - fee
                sold[k] = True; exec_seen = True

    # phase 1: recorded rows from trig_r
    last_exit_i = trig_i
    r = trig_r
    while r < n and not all(sold):
        row = rows[r]
        i_m = int(row[0])
        liquidate(i_m, row)
        last_exit_i = i_m
        r += 1
    # phase 2: beyond recorded (rare)
    i_m = int(rows[-1, 0]) + 1
    while i_m <= cap_i and not all(sold):
        row = fetch_row(i_m)
        if row is not None:
            liquidate(i_m, row)
            last_exit_i = i_m
        i_m += 1
    if not all(sold):
        pending = True
        # best-effort settle remaining at last available close (only realized rare case)
        last_close_px = float(rows[-1, 8])
        if exec_seen:
            pass
        for k in range(L):
            if not sold[k]:
                qty = float(layers[k, 2]); cost = float(layers[k, 3])
                amt = last_close_px * (1 - SLIP) * qty
                st = float(rows[-1, 7])
                fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * st + amt * TRANSFER_FEE_RATE
                proceeds += amt - fee
                sold[k] = True
    ret = (proceeds - total_cost) / total_cost * 100
    hold = last_exit_i - ep['entry_i']
    return dict(ret=ret, hold=hold, trig=1, exec=1 if exec_seen else 0,
                pending=1 if pending else 0, coll=1 if coll else 0, gap=1 if gap_seen else 0, mae=mae)


# ============================================================
# 3) Stats helpers
# ============================================================
def q(x, p):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    return float(np.percentile(x, p * 100)) if len(x) else np.nan


def ed_inference(cf_ret, sd, delta=None):
    """event-day 日级截面均值序列 -> HAC + block bootstrap."""
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
    nblocks = int(np.ceil(n / L))
    bl = []
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


def main():
    print('prepare_v51 ...', flush=True)
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51()
    N = len(days)
    print(f'  days={N} {days[0].date()}..{days[-1].date()}', flush=True)

    # ---- re-record frozen episodes ----
    prim_ep, prim_cens = replay_record(days, D, first_eligible_i, offset, top10_only=True)
    sec_ep, sec_cens = replay_record(days, D, first_eligible_i, offset, top10_only=False)

    # ---- verify against frozen baseline ----
    frozen = pickle.load(open(os.path.join(OUT, 'independent_v2a_episodes.pkl'), 'rb'))
    fep = frozen['episodes']
    key_f = {(e['ts_code'], str(pd.Timestamp(e['entry_date']).date())): e for e in fep}
    mism = 0
    for e in prim_ep:
        k = (e['ts_code'], str(pd.Timestamp(e['entry_date']).date()))
        f = key_f.get(k)
        if f is None or str(pd.Timestamp(f['exit_date']).date()) != e['exit_date'] \
                or f['exit_type'] != e['exit_type'] or abs(float(f['return_pct']) - e['ret0']) > 0.01:
            mism += 1
    print(f'[VERIFY] PRIMARY re-record {len(prim_ep)} vs frozen {len(fep)} mismatch={mism}', flush=True)
    if mism:
        print('FATAL: PRIMARY re-record mismatch'); sys.exit(1)

    full = pd.read_csv(os.path.join(OUT, 'fullmarket_episode_metrics.csv'))
    fk = full.set_index(['ts_code', 'entry_date'])
    mism2 = 0; n_matched = 0
    for e in sec_ep:
        k = (e['ts_code'], e['entry_date'])
        if k in fk.index:
            row = fk.loc[k]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            n_matched += 1
            if row['exit_date'] != e['exit_date'] or row['exit_type'] != e['exit_type'] \
                    or abs(float(row['simple_return_pct']) - e['ret0']) > 0.01:
                mism2 += 1
    print(f'[VERIFY] SECONDARY re-record {len(sec_ep)} matched={n_matched}/{len(full)} mismatch={mism2}', flush=True)
    if n_matched != len(full) or mism2:
        print('FATAL: SECONDARY re-record mismatch'); sys.exit(1)
    # censored: frozen SECONDARY reported 124 censored (89,046 realized + 124 censored = 89,170);
    # no frozen censored detail file exists, so verify the count.
    print(f'[VERIFY] censored re-record {len(sec_cens)} vs frozen-reported 124', flush=True)
    if len(sec_cens) != 124:
        print('FATAL: censored count mismatch'); sys.exit(1)

    def build(eps):
        return {e['episode_id']: (e, build_i_to_r(e)) for e in eps}

    prim_map = build(prim_ep); sec_map = build(sec_ep)

    def fetch_factory(tc):
        def fetch_row(i_m):
            dd = D[days[i_m]]; j = dd['pos'].get(tc)
            if j is None:
                return None
            return np.array([i_m, float(dd['open_'][j]), float(dd['high'][j]), float(dd['low'][j]),
                             float(dd['limit_down_px'][j]), float(dd['is_limit'][j]), np.nan,
                             float(stamp_rate(days[i_m], 'historical')), float(dd['close'][j])], dtype=np.float32)
        return fetch_row

    # ---- run counterfactual ----
    res = {}   # (sample, stop, bound) -> DataFrame
    for sample, epmap in [('PRIMARY', prim_map), ('SECONDARY', sec_map)]:
        for stop in STOPS:
            for bound in BOUNDS:
                rows = []
                for e, itor in epmap.values():
                    f = fetch_factory(e['ts_code'])
                    rr = run_cf(e, stop / 100.0, bound, itor, f, N)
                    rows.append(dict(episode_id=e['episode_id'], ts_code=e['ts_code'],
                                     signal_date=e['signal_date'], exit_type=e['exit_type'],
                                     levels0=e['levels0'], ret0=e['ret0'], pnl0=e['pnl0'], cost=e['cost'],
                                     hold0=e['hold0'], mae0=e['mae0'],
                                     cf_ret=rr['ret'], cf_hold=rr['hold'], trig=rr['trig'], exec_=rr['exec'],
                                     pending=rr['pending'], coll=rr['coll'], gap=rr['gap'], mae_cf=rr['mae']))
                res[(sample, stop, bound)] = pd.DataFrame(rows)
    print('counterfactual done', flush=True)

    # ---- per-threshold headline summaries ----
    def summ_df(d):
        r = d['cf_ret']
        cf_pnl = d['cost'] * d['cf_ret'] / 100.0
        pos_ = cf_pnl[cf_pnl > 0].sum(); neg = cf_pnl[cf_pnl < 0].sum()
        pf = pos_ / abs(neg) if neg != 0 else np.inf
        return dict(n=len(d), mean=r.mean(), median=r.median(), win_rate=(cf_pnl > 0).mean() * 100,
                    pf=pf, total_pnl=cf_pnl.sum(), std=r.std(), p1=q(r, .01), p5=q(r, .05), p10=q(r, .10),
                    worst=r.min(), hold_med=d['cf_hold'].median(), hold_mean=d['cf_hold'].mean(),
                    hold_p90=q(d['cf_hold'], .90), mae_med=q(d['mae_cf'], .5),
                    trig_rate=d['trig'].mean() * 100, exec_rate=d['exec_'].mean() * 100,
                    pending_rate=d['pending'].mean() * 100, coll_rate=d['coll'].mean() * 100,
                    gap_rate=(d['gap']).sum() / max(1, d['trig'].sum()) * 100)

    summ_rows = []
    for (sample, stop, bound), d in res.items():
        s = summ_df(d)
        base = summ_df(d.assign(cf_ret=d['ret0'], cf_hold=d['hold0'], mae_cf=d['mae0']))
        s.update(dict(sample=sample, stop_pct=stop, bound=bound,
                      base_mean=base['mean'], base_median=base['median'], base_pf=base['pf'],
                      base_p5=base['p5'], base_p10=base['p10'], base_hold_med=base['hold_med'],
                      base_win=base['win_rate'],
                      d_mean=s['mean'] - base['mean'], d_median=s['median'] - base['median'],
                      d_pf=s['pf'] - base['pf'], d_p5=s['p5'] - base['p5'], d_p10=s['p10'] - base['p10'],
                      d_hold=s['hold_med'] - base['hold_med'], d_win=s['win_rate'] - base['win_rate']))
        summ_rows.append(s)
    summ = pd.DataFrame(summ_rows)
    summ.to_csv(os.path.join(OUT, 'stop_phaseA_summary.csv'), index=False)
    prim_sum = summ[summ['sample'] == 'PRIMARY'].copy()
    sec_sum = summ[summ['sample'] == 'SECONDARY'].copy()
    prim_sum.to_csv(os.path.join(OUT, 'stop_phaseA_primary.csv'), index=False)
    sec_sum.to_csv(os.path.join(OUT, 'stop_phaseA_secondary.csv'), index=False)
    print('\n[SECONDARY per-threshold headline (STOP_FIRST)]')
    print(sec_sum[sec_sum['bound'] == 'STOP_FIRST'][['stop_pct', 'mean', 'median', 'win_rate', 'pf',
                                                     'p5', 'trig_rate', 'd_mean', 'd_p5']].round(3).to_string(index=False))

    # ---- killed / saved / net ----
    kv_rows = []
    for stop in STOPS:
        for sample, epmap in [('PRIMARY', prim_map), ('SECONDARY', sec_map)]:
            d = res[(sample, stop, 'STOP_FIRST')]
            d = d.copy(); d['cf_pnl'] = d['cost'] * d['cf_ret'] / 100.0
            d['dpnl'] = d['cf_pnl'] - d['pnl0']
            wins = d[d['ret0'] > 0]; loss = d[d['ret0'] <= 0]
            killed = wins[wins['dpnl'] < 0]
            saved = loss[loss['dpnl'] > 0]
            lost_future = killed['dpnl'].sum()          # negative
            saved_loss = saved['dpnl'].sum()            # positive
            net = d['dpnl'].sum()
            kv_rows.append(dict(stop_pct=stop, sample=sample, n=len(d),
                                n_killed=len(killed), killed_pct_of_winners=len(killed) / max(1, len(wins)) * 100,
                                killed_base_mean=killed['ret0'].mean() if len(killed) else np.nan,
                                killed_cf_mean=killed['cf_ret'].mean() if len(killed) else np.nan,
                                lost_future_profit=lost_future,
                                n_saved=len(saved), saved_pct_of_losers=len(saved) / max(1, len(loss)) * 100,
                                saved_base_mean=loss['ret0'].mean() if len(loss) else np.nan,
                                saved_cf_mean=saved['cf_ret'].mean() if len(saved) else np.nan,
                                saved_loss=saved_loss, net_stop_value=net,
                                net_per_1000=net / (len(d) / 1000.0)))
    kv = pd.DataFrame(kv_rows)
    kv.to_csv(os.path.join(OUT, 'stop_phaseA_killed_winners.csv'), index=False)
    kv.to_csv(os.path.join(OUT, 'stop_phaseA_saved_losers.csv'), index=False)
    nv = kv[['stop_pct', 'sample', 'net_stop_value', 'net_per_1000', 'lost_future_profit', 'saved_loss',
             'n_killed', 'n_saved']].copy()
    nv.to_csv(os.path.join(OUT, 'stop_phaseA_net_value.csv'), index=False)
    print('\n[NET_STOP_VALUE SECONDARY (STOP_FIRST)]')
    print(kv[kv['sample'] == 'SECONDARY'][['stop_pct', 'net_stop_value', 'n_killed', 'n_saved']].round(0).to_string(index=False))

    # ---- baseline strata ----
    sr_rows = []
    for stop in STOPS:
        for sample, epmap in [('PRIMARY', prim_map), ('SECONDARY', sec_map)]:
            d = res[(sample, stop, 'STOP_FIRST')].copy()
            d['dret'] = d['cf_ret'] - d['ret0']
            strata = [('lt-30', d['ret0'] < -30), ('-30to-20', (d['ret0'] >= -30) & (d['ret0'] < -20)),
                      ('-20to-10', (d['ret0'] >= -20) & (d['ret0'] < -10)), ('-10to0', (d['ret0'] >= -10) & (d['ret0'] < 0)),
                      ('0to5', (d['ret0'] >= 0) & (d['ret0'] < 5)), ('5to10', (d['ret0'] >= 5) & (d['ret0'] < 10)),
                      ('10to20', (d['ret0'] >= 10) & (d['ret0'] < 20)), ('gt20', d['ret0'] >= 20)]
            for lab, m in strata:
                dd = d[m]
                sr_rows.append(dict(stop_pct=stop, sample=sample, stratum=lab, n=len(dd),
                                    mean_delta=dd['dret'].mean() if len(dd) else np.nan,
                                    trig_rate=dd['trig'].mean() * 100 if len(dd) else np.nan))
    sr = pd.DataFrame(sr_rows)
    sr.to_csv(os.path.join(OUT, 'stop_phaseA_strata.csv'), index=False)

    # ---- levels diagnosis ----
    lv_rows = []
    for stop in STOPS:
        for sample, epmap in [('PRIMARY', prim_map), ('SECONDARY', sec_map)]:
            d = res[(sample, stop, 'STOP_FIRST')].copy()
            d['dret'] = d['cf_ret'] - d['ret0']
            d['cf_pnl'] = d['cost'] * d['cf_ret'] / 100.0
            d['dpnl'] = d['cf_pnl'] - d['pnl0']
            for l in range(1, 6):
                dd = d[d['levels0'] == l]
                wins = dd[dd['ret0'] > 0]; loss = dd[dd['ret0'] <= 0]
                lv_rows.append(dict(stop_pct=stop, sample=sample, levels=l, n=len(dd),
                                    trig_rate=dd['trig'].mean() * 100 if len(dd) else np.nan,
                                    mean_delta=dd['dret'].mean() if len(dd) else np.nan,
                                    saved_loss=loss[loss['dpnl'] > 0]['dpnl'].sum(),
                                    lost_winner_profit=wins[wins['dpnl'] < 0]['dpnl'].sum()))
    lv = pd.DataFrame(lv_rows)
    lv.to_csv(os.path.join(OUT, 'stop_phaseA_levels.csv'), index=False)

    # ---- yearly ----
    yr_rows = []
    for stop in STOPS:
        for sample, epmap in [('PRIMARY', prim_map), ('SECONDARY', sec_map)]:
            d = res[(sample, stop, 'STOP_FIRST')].copy()
            d['yr'] = pd.to_datetime(d['signal_date']).dt.year
            d['cf_pnl'] = d['cost'] * d['cf_ret'] / 100.0
            d['dpnl'] = d['cf_pnl'] - d['pnl0']
            for y in range(2020, 2027):
                dd = d[d['yr'] == y]
                pos_ = dd['cf_pnl'][dd['cf_pnl'] > 0].sum(); neg = dd['cf_pnl'][dd['cf_pnl'] < 0].sum()
                yr_rows.append(dict(stop_pct=stop, sample=sample, year=y, n=len(dd),
                                    mean=dd['cf_ret'].mean() if len(dd) else np.nan,
                                    median=dd['cf_ret'].median() if len(dd) else np.nan,
                                    win_rate=(dd['cf_pnl'] > 0).mean() * 100 if len(dd) else np.nan,
                                    pf=(pos_ / abs(neg) if neg != 0 else np.inf) if len(dd) else np.nan,
                                    p5=q(dd['cf_ret'], .05), trig_rate=dd['trig'].mean() * 100 if len(dd) else np.nan,
                                    net_stop_value=dd['dpnl'].sum()))
    yr = pd.DataFrame(yr_rows)
    yr.to_csv(os.path.join(OUT, 'stop_phaseA_yearly.csv'), index=False)

    # ---- early/late ----
    el_rows = []
    for stop in STOPS:
        for sample, epmap in [('PRIMARY', prim_map), ('SECONDARY', sec_map)]:
            d = res[(sample, stop, 'STOP_FIRST')].copy()
            d['yr'] = pd.to_datetime(d['signal_date']).dt.year
            d['cf_pnl'] = d['cost'] * d['cf_ret'] / 100.0
            d['dpnl'] = d['cf_pnl'] - d['pnl0']
            for lab, m in [('EARLY', d['yr'] <= 2022), ('LATE', d['yr'] >= 2023)]:
                dd = d[m]
                pos_ = dd['cf_pnl'][dd['cf_pnl'] > 0].sum(); neg = dd['cf_pnl'][dd['cf_pnl'] < 0].sum()
                el_rows.append(dict(stop_pct=stop, sample=sample, period=lab, n=len(dd),
                                    mean=dd['cf_ret'].mean() if len(dd) else np.nan,
                                    median=dd['cf_ret'].median() if len(dd) else np.nan,
                                    win_rate=(dd['cf_pnl'] > 0).mean() * 100 if len(dd) else np.nan,
                                    pf=(pos_ / abs(neg) if neg != 0 else np.inf) if len(dd) else np.nan,
                                    p5=q(dd['cf_ret'], .05),
                                    net_stop_value=dd['dpnl'].sum()))
    el = pd.DataFrame(el_rows)
    el.to_csv(os.path.join(OUT, 'stop_phaseA_early_late.csv'), index=False)

    # ---- event-day inference (SECONDARY realized) ----
    ed_rows = []
    for stop in STOPS:
        for bound in BOUNDS:
            d = res[('SECONDARY', stop, bound)]
            d = d.copy()
            inf = ed_inference(d['cf_ret'].to_numpy(), d['signal_date'].to_numpy(),
                               delta=(d['cf_ret'] - d['ret0']).to_numpy())
            ed_rows.append(dict(stop_pct=stop, bound=bound, **inf))
    ed = pd.DataFrame(ed_rows)
    ed.to_csv(os.path.join(OUT, 'stop_phaseA_eventday.csv'), index=False)
    print('\n[EVENT-DAY SECONDARY]')
    print(ed[ed['bound'] == 'STOP_FIRST'][['stop_pct', 'n_event_days', 'daily_mean', 'hac_t',
                                           'block_boot_ci_lo', 'block_boot_ci_hi',
                                           'delta_daily_mean', 'delta_hac_ci_lo', 'delta_hac_ci_hi']].round(3).to_string(index=False))

    # ---- tail risk / ES ----
    es_rows = []
    for stop in STOPS:
        for sample, epmap in [('PRIMARY', prim_map), ('SECONDARY', sec_map)]:
            d = res[(sample, stop, 'STOP_FIRST')]
            r = d['cf_ret'].to_numpy()
            r = r[np.isfinite(r)]
            es = {}
            for a in (0.01, 0.05, 0.10):
                k = max(1, int(len(r) * a))
                es[f'es{a:.2f}'] = float(np.sort(r)[:k].mean())
            nw = int(min(100, len(r)))
            es_rows.append(dict(stop_pct=stop, sample=sample, n=len(r), p1=q(r, .01), p5=q(r, .05),
                                p10=q(r, .10), worst=r.min(),
                                worst100_mean=float(np.sort(r)[:nw].mean()),
                                worst1pct_mean=es['es0.01'], worst5pct_mean=es['es0.05'],
                                worst10pct_mean=es['es0.10']))
    esdf = pd.DataFrame(es_rows)
    esdf.to_csv(os.path.join(OUT, 'stop_phaseA_tailrisk.csv'), index=False)
    print('\n[ES SECONDARY STOP_FIRST]')
    print(esdf[esdf['sample'] == 'SECONDARY'][['stop_pct', 'p5', 'worst1pct_mean', 'worst5pct_mean',
                                               'worst10pct_mean']].round(3).to_string(index=False))

    # ---- collisions ----
    col_rows = []
    for stop in STOPS:
        for sample, epmap in [('PRIMARY', prim_map), ('SECONDARY', sec_map)]:
            d = res[(sample, stop, 'STOP_FIRST')]
            tp = d[d['exit_type'] == 'TAKE_PROFIT_DYN']
            col_rows.append(dict(stop_pct=stop, sample=sample, n=tp.shape[0],
                                 collision_count=int(tp['coll'].sum()),
                                 collision_pct=tp['coll'].mean() * 100 if len(tp) else np.nan))
    coldf = pd.DataFrame(col_rows)
    coldf.to_csv(os.path.join(OUT, 'stop_phaseA_collisions.csv'), index=False)

    # ---- censored sensitivity ----
    cens_rows = []
    for stop in STOPS:
        crows = []
        for c in sec_cens:
            e = dict(c)
            e['exit_type'] = 'CENSORED'
            e['ret0'] = 0.0; e['hold0'] = 0; e['pnl0'] = 0.0
            e['entry_i'] = int(e['rows'][0, 0]) if len(e['rows']) else e['entry_i']
            itor = build_i_to_r(e)
            f = fetch_factory(c['ts_code'])
            rr = run_cf(e, stop / 100.0, 'STOP_FIRST', itor, f, N)
            rescued = 1 if (rr['trig'] and rr['exec']) else 0
            crows.append(dict(cf_ret=rr['ret'] if rescued else -100.0, pnl=-(c['cost']) if not rescued else
                              (rr['ret'] / 100.0) * c['cost'], rescued=rescued, cost=c['cost']))
        cd = pd.DataFrame(crows)
        # realized headline
        rd = res[('SECONDARY', stop, 'STOP_FIRST')].copy()
        rd['cf_pnl'] = rd['cost'] * rd['cf_ret'] / 100.0
        real_ret = rd['cf_ret'].to_numpy(); real_pnl = rd['cf_pnl'].to_numpy()
        # A REALIZED_ONLY
        a = dict(n=len(real_ret), mean=real_ret.mean(), p5=q(real_ret, .05))
        # B CENSORED_PESSIMISTIC
        allr = np.concatenate([real_ret, cd['cf_ret'].to_numpy()])
        allp = np.concatenate([real_pnl, cd['pnl'].to_numpy()])
        b = dict(n=len(allr), mean=allr.mean(), p5=q(allr, .05), total_pnl=allp.sum())
        cens_rows.append(dict(stop_pct=stop, n_realized=len(real_ret), n_censored=len(cd),
                              n_rescued=int(cd['rescued'].sum()),
                              n_not_rescued=int((cd['rescued'] == 0).sum()),
                              rescued_mean_ret=cd[cd['rescued'] == 1]['cf_ret'].mean() if (cd['rescued'] == 1).any() else np.nan,
                              realized_only_mean=a['mean'], realized_only_p5=a['p5'],
                              pessimistic_mean=b['mean'], pessimistic_p5=b['p5'],
                              pessimistic_total_pnl=b['total_pnl'],
                              pessimistic_vs_realized_dmean=b['mean'] - a['mean']))
    censdf = pd.DataFrame(cens_rows)
    censdf.to_csv(os.path.join(OUT, 'stop_phaseA_censored_sensitivity.csv'), index=False)
    print('\n[CENSORED SENSITIVITY SECONDARY]')
    print(censdf[['stop_pct', 'n_rescued', 'realized_only_mean', 'pessimistic_mean',
                  'pessimistic_vs_realized_dmean']].round(3).to_string(index=False))

    # ---- episode detail (gz, full) ----
    det_rows = []
    for (sample, stop, bound), d in res.items():
        dd = d.copy()
        dd['sample'] = sample; dd['stop_pct'] = stop; dd['bound'] = bound
        dd['delta'] = dd['cf_ret'] - dd['ret0']
        det_rows.append(dd[['sample', 'episode_id', 'ts_code', 'signal_date', 'stop_pct', 'bound',
                            'ret0', 'cf_ret', 'delta', 'cf_hold', 'trig', 'exec_', 'pending',
                            'coll', 'gap', 'mae_cf']])
    det = pd.concat(det_rows, ignore_index=True)
    det.columns = [c.rstrip('_') if c.endswith('_') else c for c in det.columns]
    det.to_csv(os.path.join(OUT, 'stop_phaseA_episode_detail.csv.gz'), index=False, compression='gzip')
    det_prim = det[det['sample'] == 'PRIMARY']
    det_prim.to_csv(os.path.join(OUT, 'stop_phaseA_episode_detail_primary.csv'), index=False)
    print(f'episode detail rows: {len(det)} (gz saved)', flush=True)

    # ---- figures ----
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'figure.dpi': 110, 'savefig.bbox': 'tight'})
    s = sec_sum[sec_sum['bound'] == 'STOP_FIRST'].set_index('stop_pct').sort_index()

    def figline(col, name, ylab):
        fig, ax = plt.subplots(figsize=(7, 4.5))
        ax.axhline(0, color='k', lw=.8)
        ax.plot(s.index, s[col], 'o-')
        ax.set_xlabel('stop %'); ax.set_ylabel(ylab); ax.set_title(f'SECONDARY {col} vs stop')
        ax.grid(alpha=.3); fig.savefig(os.path.join(FIG, name)); plt.close(fig)

    figline('mean', 'stop_threshold_vs_mean_return.png', 'mean return %')
    figline('pf', 'stop_threshold_vs_profit_factor.png', 'profit factor')
    figline('p5', 'stop_threshold_vs_p5_return.png', 'P5 return %')
    # ES
    es2 = esdf[esdf['sample'] == 'SECONDARY'].set_index('stop_pct').sort_index()
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for col, lab in [('worst1pct_mean', 'ES1%'), ('worst5pct_mean', 'ES5%'), ('worst10pct_mean', 'ES10%')]:
        ax.plot(es2.index, es2[col], 'o-', label=lab)
    ax.set_xlabel('stop %'); ax.set_ylabel('ES (%)'); ax.set_title('Expected Shortfall vs stop (SECONDARY)')
    ax.legend(); ax.grid(alpha=.3); fig.savefig(os.path.join(FIG, 'stop_threshold_vs_expected_shortfall.png')); plt.close(fig)
    # net stop value
    nv2 = nv[nv['sample'] == 'SECONDARY'].set_index('stop_pct').sort_index()
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.axhline(0, color='k', lw=.8)
    ax.plot(nv2.index, nv2['net_stop_value'] / 1e6, 'o-', label='net stop value (M)')
    ax.plot(nv2.index, nv2['lost_future_profit'] / 1e6, 's--', label='lost winner profit (M)')
    ax.plot(nv2.index, nv2['saved_loss'] / 1e6, '^--', label='saved loser loss (M)')
    ax.set_xlabel('stop %'); ax.set_ylabel('PnL (M)'); ax.set_title('NET_STOP_VALUE vs stop (SECONDARY)')
    ax.legend(); ax.grid(alpha=.3); fig.savefig(os.path.join(FIG, 'stop_threshold_vs_net_stop_value.png')); plt.close(fig)
    # killed vs saved
    fig, ax = plt.subplots(figsize=(7, 4.5))
    kv2 = kv[kv['sample'] == 'SECONDARY'].set_index('stop_pct').sort_index()
    ax.plot(kv2.index, kv2['killed_pct_of_winners'], 'o-', label='killed winners % of baseline winners')
    ax.plot(kv2.index, kv2['saved_pct_of_losers'], 's-', label='saved losers % of baseline losers')
    ax.set_xlabel('stop %'); ax.set_ylabel('%'); ax.set_title('KILLED vs SAVED (SECONDARY)')
    ax.legend(); ax.grid(alpha=.3); fig.savefig(os.path.join(FIG, 'stop_threshold_killed_vs_saved.png')); plt.close(fig)
    # hold days
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(s.index, s['hold_med'], 'o-', label='cf hold median')
    ax.plot(s.index, s['base_hold_med'], 's--', label='baseline hold median')
    ax.set_xlabel('stop %'); ax.set_ylabel('holding days'); ax.set_title('Holding days vs stop (SECONDARY)')
    ax.legend(); ax.grid(alpha=.3); fig.savefig(os.path.join(FIG, 'stop_threshold_hold_days.png')); plt.close(fig)
    # early vs late
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for sample, c in [('PRIMARY', 'C0'), ('SECONDARY', 'C1')]:
        el2 = el[(el['sample'] == sample) & (el['period'] == 'EARLY')].set_index('stop_pct')['mean'].sort_index()
        el3 = el[(el['sample'] == sample) & (el['period'] == 'LATE')].set_index('stop_pct')['mean'].sort_index()
        ax.plot(el2.index, el2, 'o-', color=c, label=f'{sample} EARLY mean')
        ax.plot(el3.index, el3, 's--', color=c, label=f'{sample} LATE mean')
    ax.axhline(0, color='k', lw=.8)
    ax.set_xlabel('stop %'); ax.set_ylabel('mean return %'); ax.set_title('EARLY(2020-22) vs LATE(2023-26)')
    ax.legend(fontsize=8); ax.grid(alpha=.3); fig.savefig(os.path.join(FIG, 'stop_threshold_early_vs_late.png')); plt.close(fig)
    # STOP_FIRST vs TP_FIRST
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for b, c in [('STOP_FIRST', 'C0'), ('TP_FIRST', 'C1')]:
        bb = sec_sum[sec_sum['bound'] == b].set_index('stop_pct')['mean'].sort_index()
        ax.plot(bb.index, bb, 'o-', color=c, label=f'SECONDARY {b}')
    ax.axhline(0, color='k', lw=.8)
    ax.set_xlabel('stop %'); ax.set_ylabel('mean return %'); ax.set_title('STOP_FIRST vs TP_FIRST (SECONDARY)')
    ax.legend(); ax.grid(alpha=.3); fig.savefig(os.path.join(FIG, 'stop_threshold_stopfirst_vs_tpfirst.png')); plt.close(fig)
    # levels
    fig, ax = plt.subplots(figsize=(7, 4.5))
    lv2 = lv[(lv['sample'] == 'SECONDARY')]
    for l in range(1, 6):
        dd = lv2[lv2['levels'] == l].set_index('stop_pct')['mean_delta'].sort_index()
        ax.plot(dd.index, dd, 'o-', label=f'L{l}')
    ax.axhline(0, color='k', lw=.8)
    ax.set_xlabel('stop %'); ax.set_ylabel('mean Δreturn (pp)'); ax.set_title('Stop effect by baseline levels (SECONDARY)')
    ax.legend(); ax.grid(alpha=.3); fig.savefig(os.path.join(FIG, 'stop_threshold_by_baseline_levels.png')); plt.close(fig)
    # return distribution comparison
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for stop, c in [(-15.0, 'C0'), (-20.0, 'C1'), (-25.0, 'C2'), (-30.0, 'C3')]:
        r = res[('SECONDARY', stop, 'STOP_FIRST')]['cf_ret'].to_numpy()
        ax.hist(r.clip(-60, 80), bins=80, alpha=.4, density=True, label=f'stop {stop}%')
    r0 = res[('SECONDARY', STOPS[0], 'STOP_FIRST')]
    ax.hist(r0['ret0'].to_numpy().clip(-60, 80), bins=80, histtype='step', density=True, color='k', label='NO STOP baseline')
    ax.axvline(0, color='k', lw=1)
    ax.set_xlabel('return %'); ax.set_title('SECONDARY return distribution: NO STOP vs stops')
    ax.legend(fontsize=8); fig.savefig(os.path.join(FIG, 'stop_return_distribution_comparison.png')); plt.close(fig)

    print('DONE', flush=True)


if __name__ == '__main__':
    main()
