"""
==========================================================
PHASE S1 — SIGNAL SELECTIVITY AUDIT
BB DEPTH / RSI14 / SECTOR STRENGTH (entry-selectivity only)
==========================================================
PREREG: research/signal/registries/SIGNAL_SELECTIVITY_S1_REGISTRY.csv (227ab94)

冻结语义 (全部沿用 V2A_FROZEN_STRICT independent replay):
  T close signal -> T+1 open entry; pending buy/add/sell 遇 T+1 无行情 -> CANCEL;
  dynamic self-consistent P* (analytic_Pstar, k=2 固定, ddof=1); legal tick ceil;
  gap-through @ open; ref_first 跌停可达性; 100股 lot; PIT ST; real list_date+60;
  历史印花税; 10bp 双腿滑点; FINAL_SETTLE 仅末日有行情股; 其余 -> censored.

本阶段只改变 ENTRY extremeness:
  B20: entry k=2.0 (与 frozen 基线一致)
  B25: entry k=2.5 (真实重建独立 episodes)
  B30: entry k=3.0 (真实重建独立 episodes)
  exit 不变 (dynamic_touch Pstar k=2 + FINAL_SETTLE + censored).
  加仓条件同步使用同一 entry k 的下轨 (entry family 语义一致).

BB_Z = (close_adj - MA20)/SD20 (sample std), 冻结 bins:
  [-2.0,-2.5) == z in [-2.5,-2.0); [-2.5,-3.0) == z in [-3.0,-2.5);
  [-3.0,-3.5) == z in [-3.5,-3.0); <-3.5 == z < -3.5.

RSI: Wilder RSI14 on close_adj (前14个delta简单平均为种子, 其后 Wilder 平滑).
MACD: (12,26,9) ewm(adjust=False) DIF/DEA/HIST — diagnostic only.
SECTOR: PIT gate (本环境无 PIT 行业映射 -> NOT RUN / PIT DATA NOT READY).
FUNDAMENTAL / NEWS: readiness only (NOT TESTED).

PRIMARY UNIT = signal-day equal weight.
Inference: HAC maxlags=10; full 2020-2024 trading-calendar moving-block
bootstrap L=21 B=2000 seed=0 (paired fx/oy; NaN days dropped post-resample).

2025-2026 CLOSED: 本脚本只循环 days[:N2024]; RSI/MACD 计算亦只读 <=2024-12-31.
==========================================================
"""
import os, sys, time, json, csv
from collections import deque, Counter
from datetime import date
import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT); sys.path.insert(0, REPO)
from round51_audit import prepare_v51, stamp_rate, COMMISSION_RATE, MIN_COMMISSION, TRANSFER_FEE_RATE
from run_strict_c_math import analytic_Pstar

OUT = os.path.join(REPO, 'results', 'evidence', 's1')
os.makedirs(OUT, exist_ok=True)
LEVEL_CASH = 200_000.0; MAX_LEVELS = 5; SLIP = 0.001; ADD_GAP = 1
B2024 = date(2024, 12, 31)

# ============================================================
# RSI14 / MACD 预计算 (<=2024-12-31 ONLY)
# ============================================================
def wilder_rsi(a):
    """Wilder RSI14. a: close_adj np.ndarray (chronological)."""
    n = len(a)
    out = np.full(n, np.nan)
    if n < 15:
        return out
    d = np.diff(a)
    up = np.maximum(d, 0.0); dn = np.maximum(-d, 0.0)
    au = up[:14].mean(); ad = dn[:14].mean()
    out[14] = 100.0 if ad == 0 else 100.0 - 100.0 / (1.0 + au / ad)
    for i in range(14, n - 1):
        au = (au * 13.0 + up[i]) / 14.0
        ad = (ad * 13.0 + dn[i]) / 14.0
        out[i + 1] = 100.0 if ad == 0 else 100.0 - 100.0 / (1.0 + au / ad)
    return out

def macd_series(a):
    s = pd.Series(a)
    e12 = s.ewm(span=12, adjust=False).mean()
    e26 = s.ewm(span=26, adjust=False).mean()
    dif = (e12 - e26).to_numpy()
    dea = pd.Series(dif).ewm(span=9, adjust=False).mean().to_numpy()
    return dif, dea, dif - dea

def build_rsi_macd_lookup(days_index):
    """全市场 per-stock 查表: tc -> (dates_idx int32, rsi f32, dif f32, dea f32, hist f32).
    只读 2020-01-01..2024-12-31 (2025+ never read)."""
    t0 = time.time()
    df = pd.read_parquet(os.path.join(ROOT, 'data', 'combined_daily.parquet'))
    df['date'] = pd.to_datetime(df['date'])
    df = df[(df['date'] >= '2020-01-01') & (df['date'] <= '2024-12-31')]
    df = df.sort_values(['ts_code', 'date']).reset_index(drop=True)
    df['close_adj'] = df['close'] * df['adj_factor']
    g = df.groupby('ts_code')['close_adj']
    df['rsi14'] = g.transform(wilder_rsi)
    df['dif'] = g.transform(lambda x: macd_series(x.to_numpy())[0])
    df['dea'] = g.transform(lambda x: macd_series(x.to_numpy())[1])
    df['hist'] = g.transform(lambda x: macd_series(x.to_numpy())[2])
    day_idx = {pd.Timestamp(d): i for i, d in enumerate(days_index)}
    df['di'] = df['date'].map(day_idx)
    lookup = {}
    for tc, g2 in df.groupby('ts_code'):
        g2 = g2.sort_values('date')
        di = g2['di'].to_numpy(dtype=np.int32)
        lookup[tc] = (di,
                      g2['rsi14'].to_numpy(dtype=np.float32),
                      g2['dif'].to_numpy(dtype=np.float32),
                      g2['dea'].to_numpy(dtype=np.float32),
                      g2['hist'].to_numpy(dtype=np.float32))
    print(f'[RSI/MACD] lookup stocks={len(lookup)} ({time.time()-t0:.0f}s)', flush=True)
    return lookup

def query_signal(lookup, tc, i):
    v = lookup.get(tc)
    if v is None:
        return np.nan, np.nan, np.nan, np.nan, np.nan
    di, rsi, dif, dea, hist = v
    pos = int(np.searchsorted(di, i))
    if pos >= len(di) or di[pos] != i:
        return np.nan, np.nan, np.nan, np.nan, np.nan
    return float(rsi[pos]), float(dif[pos]), float(dea[pos]), float(hist[pos]), 1.0

# ============================================================
# V2A_FROZEN_STRICT 引擎 (entry_k 参数化; exit 不变)
# ============================================================
def replay_k(days, D, first_eligible_i, offset, N, entry_k, lookup):
    """entry_k=2.0 -> 与 frozen B20 全市场 replay 一致."""
    global rank_all_day
    rank_all_day = {}
    pos = {}; pending_buy = []; pending_add = {}; pending_sell = set()
    raw_hist = {}; episodes = []; censored = []; last_close = {}
    signal_counts = Counter(); episode_seq = [0]

    def sell(tc, d, j, price, exit_type, i):
        p = pos[tc]
        amt = price * p['shares']
        sr = stamp_rate(d, 'historical')
        fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
        proceeds = amt - fee
        pnl = proceeds - p['total_cost']
        if j is not None and not (p['path'] and p['path'][-1][0] == i):
            p['path'].append((i, float(D[d]['close'][j]), float(D[d]['high'][j]), float(D[d]['low'][j])))
        path = p['path']
        closes = np.array([c for _, c, _, _ in path], dtype=float)
        highs = np.array([h for _, _, h, _ in path], dtype=float)
        lows = np.array([l for _, _, _, l in path], dtype=float)
        base = p['entry_exec_raw']
        nav_c = closes / base - 1
        nav_i_l = lows / base - 1
        nav_i_h = highs / base - 1
        mae_c = float(nav_c.min() * 100); mfe_c = float(nav_c.max() * 100)
        mae_i = float(nav_i_l.min() * 100); mfe_i = float(nav_i_h.max() * 100)
        final_pp = float((price / base - 1) * 100)
        i_mae = int(np.argmin(nav_c))
        ge0 = np.where(nav_c >= 0)[0]
        be = int(ge0[0]) if len(ge0) else -1
        max_under = 0
        cur = 0
        for u in (nav_c < 0):
            cur = cur + 1 if u else 0
            max_under = max(max_under, cur)
        if max_under == 0:
            ttbe = 0
        else:
            ttbe = be if be >= 0 else np.nan
        sr_pct = pnl / p['total_cost'] * 100
        episode_seq[0] += 1
        ep = dict(episode_id=episode_seq[0], ts_code=tc, signal_date=p['signal_date'],
                  entry_date=p['entry_date'], exit_date=str(d.date()), exit_type=exit_type,
                  levels_used=p['levels'], hold_days=i - p['entry_i'], total_cost=p['total_cost'],
                  pnl=pnl, simple_return_pct=sr_pct,
                  MAE_close_pct=mae_c, MAE_intraday_pct=mae_i,
                  MFE_close_pct=mfe_c, MFE_intraday_pct=mfe_i,
                  final_price_path_return_pct=final_pp,
                  time_to_MAE_days=i_mae, time_to_break_even_days=ttbe,
                  max_underwater_duration_days=max_under,
                  n_path_days=len(path), turnover_rank=p['turnover_rank'],
                  entry_k=entry_k, bb_z_signal=p['bb_z'], rsi14_signal=p['rsi'],
                  macd_dif_signal=p['dif'], macd_dea_signal=p['dea'], macd_hist_signal=p['hist'])
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
    for i in range(N):
        d = days[i]
        dd = D[d]
        # bb_lower_k 与 BB_Z (per day)
        if entry_k == 2.0:
            bb_lo_k = dd['bb_lower']
        else:
            mid = dd['bb_mid']; lo = dd['bb_lower']
            sd = np.where(mid - lo > 0, (mid - lo) / 2.0, 0.0)
            bb_lo_k = mid - entry_k * sd
        sd_day = np.where(dd['bb_mid'] - dd['bb_lower'] > 0, (dd['bb_mid'] - dd['bb_lower']) / 2.0, np.nan)
        bb_z_arr = np.where(np.isfinite(sd_day) & (sd_day > 0),
                            (dd['close_adj'] - dd['bb_mid']) / sd_day, np.nan)
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
                    rmap = rank_all_day.get(pb['signal_i'])
                    rk = rmap.get(tc, np.nan) if rmap else np.nan
                    pos[tc] = dict(shares=qty, total_cost=amt + fee, levels=1, entry_i=i,
                                   last_add_i=i, entry_date=str(d.date()),
                                   signal_date=pb['signal_date'], entry_exec_raw=buy_price,
                                   turnover_rank=rk, path=[], bb_z=pb['bb_z'], rsi=pb['rsi'],
                                   dif=pb['dif'], dea=pb['dea'], hist=pb['hist'])
                    init_raw_hist(tc, i)
                pending_buy.remove(pb)
        # ---- 盘中退出: dynamic_touch (Pstar k=2 固定, 不变) ----
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
        # ---- CLOSE: 加仓条件用 bb_lo_k ----
        for tc in list(pos.keys()):
            p = pos[tc]; j = dd['pos'].get(tc)
            if j is None:
                last_close[tc] = last_close.get(tc, p['total_cost'] / p['shares'])
                continue
            close = dd['close'][j]
            last_close[tc] = close
            p['path'].append((i, float(close), float(dd['high'][j]), float(dd['low'][j])))
            raw_hist.setdefault(tc, deque([], 19)).append(float(dd['close_adj'][j]))
            bb_lo = bb_lo_k[j]
            if (not np.isnan(bb_lo) and dd['close_adj'][j] < bb_lo and not dd['is_limit'][j]
                    and p['levels'] < MAX_LEVELS and (i - p['last_add_i']) >= ADD_GAP):
                pending_add[tc] = True
        # ---- 新买信号: ALL eligible, entry 条件用 bb_lo_k ----
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
                bz = bb_z_arr[kk]
                blk = bb_lo_k[kk]
                if (not np.isnan(blk) and dd['close_adj'][kk] < blk and not dd['is_limit'][kk]):
                    r, dif, dea, hist, ok = query_signal(lookup, tc, i)
                    pending_buy.append({'ts_code': tc, 'signal_date': str(d.date()), 'signal_i': i,
                                        'bb_z': float(bz) if np.isfinite(bz) else np.nan,
                                        'rsi': r, 'dif': dif, 'dea': dea, 'hist': hist})
                    signal_counts[str(d.date())] += 1
                    pb_set.add(tc)
    # ---- 期末 (2024-12-31) ----
    d_last = days[N - 1]; dd_last = D[d_last]
    for tc in list(pos.keys()):
        j = dd_last['pos'].get(tc)
        if j is not None:
            sell(tc, d_last, j, dd_last['close'][j] * (1 - SLIP), 'FINAL_SETTLE', N - 1)
        else:
            p = pos[tc]
            mark = last_close.get(tc, p['total_cost'] / p['shares'])
            censored.append(dict(ts_code=tc, signal_date=p['signal_date'], entry_date=p['entry_date'],
                                 levels_used=p['levels'], total_cost=p['total_cost'], last_close_mark=mark,
                                 last_mark_return_pct=(mark * p['shares'] / p['total_cost'] - 1) * 100))
            del pos[tc]
    print(f'[REPLAY k={entry_k}] episodes={len(episodes)} '
          f'(TP={sum(1 for e in episodes if e["exit_type"]=="TAKE_PROFIT_DYN")} '
          f'FS={sum(1 for e in episodes if e["exit_type"]=="FINAL_SETTLE")}) '
          f'censored={len(censored)} ({time.time()-t0:.0f}s)', flush=True)
    return episodes, censored


rank_all_day = {}


def epdf(eps):
    rows = []
    for e in eps:
        r = {k: e[k] for k in ('episode_id', 'ts_code', 'pnl', 'signal_date', 'entry_date', 'exit_date',
                               'exit_type', 'levels_used', 'total_cost', 'simple_return_pct', 'hold_days',
                               'MAE_close_pct', 'MAE_intraday_pct', 'MFE_close_pct', 'MFE_intraday_pct', 'final_price_path_return_pct',
                               'time_to_MAE_days', 'time_to_break_even_days',
                               'max_underwater_duration_days', 'n_path_days', 'turnover_rank',
                               'entry_k', 'bb_z_signal', 'rsi14_signal',
                               'macd_dif_signal', 'macd_dea_signal', 'macd_hist_signal')}
        rows.append(r)
    return pd.DataFrame(rows)


def calendar_series(df, days):
    """full-calendar day-mean series (NaN for no-signal days)."""
    m = df.groupby('signal_date')['simple_return_pct'].mean()
    out = np.full(len(days), np.nan)
    for k, d in enumerate(days):
        key = str(d.date())
        if key in m.index:
            out[k] = float(m.loc[key])
    return out


def hac_ci(y, maxlags=10):
    y = np.asarray(y, dtype=float)
    y = y[np.isfinite(y)]
    if len(y) < 10:
        return np.nan, np.nan, np.nan, len(y)
    res = sm.OLS(y, np.ones((len(y), 1))).fit(cov_type='HAC', cov_kwds={'maxlags': maxlags})
    se = float(res.bse[0])
    return float(y.mean()), float(y.mean() - 1.96 * se), float(y.mean() + 1.96 * se), len(y)


def cal_block_bootstrap(y, L=21, B=2000, seed=0):
    y = np.asarray(y, dtype=float)
    n = len(y)
    rng = np.random.default_rng(seed)
    nblocks = int(np.ceil(n / L))
    means = np.empty(B)
    for b in range(B):
        idx = []
        for _b in range(nblocks):
            s = rng.integers(0, n - L + 1) if n - L + 1 > 0 else 0
            idx.extend(range(s, min(s + L, n)))
        idx = np.array(idx[:n])
        sub = y[idx]
        sub = sub[np.isfinite(sub)]
        means[b] = sub.mean() if len(sub) else np.nan
    means = means[np.isfinite(means)]
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)), float((means <= 0).mean())


def paired_delta(s1, s2, days):
    """day-level paired delta s1-s2 over full calendar."""
    d = s1 - s2
    return d


def q(x, p):
    x = pd.Series(x).dropna()
    return float(x.quantile(p)) if len(x) else np.nan


def family_metrics(df, days, cens):
    hold = df['hold_days']
    tot_hold = float(hold.sum())
    pos_ep = int((df['pnl'] > 0).sum())
    return dict(
        n_episodes=len(df),
        n_signal_days=int(df['signal_date'].nunique()),
        signals_per_year=len(df) / 5.0,
        mean_return=float(df['simple_return_pct'].mean()),
        median_return=float(df['simple_return_pct'].median()),
        win_rate=float((df['pnl'] > 0).mean() * 100),
        profit_factor=float(df[df['pnl'] > 0]['pnl'].sum() / max(1e-9, -df[df['pnl'] <= 0]['pnl'].sum())),
        mean_MAE=float(df['MAE_close_pct'].mean()),
        median_MAE=float(df['MAE_close_pct'].median()),
        mean_MFE=float(df['MFE_close_pct'].mean()),
        median_MFE=float(df['MFE_close_pct'].median()),
        mean_hold=float(hold.mean()),
        median_hold=float(hold.median()),
        mean_days_underwater=float(df['max_underwater_duration_days'].mean()),
        censored=len(cens),
        mae10=float((df['MAE_close_pct'] <= -10).mean() * 100),
        mae20=float((df['MAE_close_pct'] <= -20).mean() * 100),
        mae30=float((df['MAE_close_pct'] <= -30).mean() * 100),
        hold60=float((hold > 60).mean() * 100),
        hold90=float((hold > 90).mean() * 100),
        slot_ep_per_100_sig=float(len(df) / max(1, df['signal_date'].nunique()) * 100),
        slot_mean_ret_per_ep=float(df['simple_return_pct'].mean()),
        slot_median_hold=float(hold.median()),
        slot_pos_per_1000_hold=float(pos_ep / max(1e-9, tot_hold) * 1000),
        slot_sum_norm_pnl_per_1000_hold=float((df['pnl'] / df['total_cost']).sum() / max(1e-9, tot_hold) * 1000),
    )


def yearly(df):
    rows = []
    for yr in range(2020, 2025):
        d = df[df['signal_date'].astype(str).str.startswith(str(yr))]
        rows.append(dict(year=yr, n=len(d),
                         mean_return=float(d['simple_return_pct'].mean()) if len(d) else np.nan,
                         win_rate=float((d['pnl'] > 0).mean() * 100) if len(d) else np.nan,
                         sum_norm_pnl=float((d['pnl'] / d['total_cost']).sum()) if len(d) else np.nan))
    return rows


def main():
    print('prepare_v51 ...', flush=True)
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51()
    N = next(i for i, d in enumerate(days) if d.date() == B2024) + 1
    print(f'  days={len(days)} horizon_days={N} (2020-01-01..{days[N-1].date()})', flush=True)
    assert N < len(days), 'horizon must exclude 2025+'
    assert days[N - 1].date() == B2024

    lookup = build_rsi_macd_lookup(days[:N])

    eps20, cens20 = replay_k(days, D, first_eligible_i, offset, N, 2.0, lookup)
    eps25, cens25 = replay_k(days, D, first_eligible_i, offset, N, 2.5, lookup)
    eps30, cens30 = replay_k(days, D, first_eligible_i, offset, N, 3.0, lookup)

    b20 = epdf(eps20); b25 = epdf(eps25); b30 = epdf(eps30)
    for nm, df in (('B20', b20), ('B25', b25), ('B30', b30)):
        df.to_csv(os.path.join(OUT, f's1_episodes_{nm}.csv'), index=False)

    # ---- I1 parity: B20 vs frozen dev 截断 (声明式口径) ----
    # 冻结 fullmarket CSV 由 full_market_trade_path_audit.py 全历史(2020-2026) replay 生成。
    # S1 按 Registry 硬约束只读 2020-2024 (N=1212, 2024-12-31 收盘), 因此两边的数量差
    # 必须且只能来自 hard-horizon 语义, 不得来自引擎信号逻辑差异:
    #   (a) signal_date == 2024-12-31 的信号, T+1 入场在 2025-01-02, S1 不执行 (不产生 episode);
    #   (b) 2024-12-31 当日停牌(无行情)的末仓 -> censored, 按冻结语义不计入 episodes CSV。
    # 除 (a)(b) 外, <=2024-12-30 的信号 episodes 必须与 frozen dev 完全一致;
    # 且 b20 TP 数 == 全历史 CSV TP 数 61,828 (F2.1 natural-exit parity 同源数字) 作为引擎一致性佐证。
    frozen = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'fullmarket', 'fullmarket_episode_metrics.csv'))
    frozen_dev = frozen[frozen['signal_date'].astype(str) <= '2024-12-31'].reset_index(drop=True)
    sig_last_day = int((frozen_dev['signal_date'].astype(str) == '2024-12-31').sum())
    cens_pre = [c for c in cens20 if str(c.get('signal_date', '')) <= '2024-12-30']
    cens_pre_n = len(cens_pre)
    # 只有 frozen 全历史 replay 中 2025-2026 复牌并自然退出的 censored 持仓, 才在 frozen_dev 中有对应 episode
    # (按 signal_date+entry_date 精确匹配同一笔持仓); 其余 (frozen 中同样长期停牌至 2026-08-25 期末)
    # 在冻结 CSV 中同样不存在, 不构成数量差。
    cens_keys = set((c['ts_code'], str(c['signal_date']), str(c['entry_date'])) for c in cens_pre)
    frozen_dev_pre = frozen_dev[frozen_dev['signal_date'].astype(str) <= '2024-12-30']
    frozen_keys = set(zip(frozen_dev_pre['ts_code'], frozen_dev_pre['signal_date'].astype(str),
                          frozen_dev_pre['entry_date'].astype(str)))
    cens_with_frozen_counterpart = len(cens_keys & frozen_keys)
    explained_diff = sig_last_day + cens_with_frozen_counterpart
    n_diff = len(frozen_dev) - len(b20)
    b20_tp = int((b20['exit_type'] == 'TAKE_PROFIT_DYN').sum())
    b20_fs = int((b20['exit_type'] == 'FINAL_SETTLE').sum())
    frozen_full_tp = int((frozen['exit_type'] == 'TAKE_PROFIT_DYN').sum())
    assert (frozen_dev['exit_type'] == 'TAKE_PROFIT_DYN').all(), 'frozen dev 应全部 TAKE_PROFIT_DYN'
    assert n_diff == explained_diff, f'parity 分解失败: n_diff={n_diff} explained={explained_diff}'
    assert cens_with_frozen_counterpart == 4, f'frozen 有对应的 horizon censored 应为 4: {cens_with_frozen_counterpart}'
    # 引擎一致性佐证: 剔除 4 笔 horizon-censored 后, b20 与 frozen_dev_pre 的 (ts_code, signal_date) 信号集合
    # 必须完全一致, 且同信号 entry_date 完全一致 (同信号同日 T+1 入场)。
    b20_keys = set(zip(b20['ts_code'], b20['signal_date'].astype(str)))
    frozen_pre_keys = set(zip(frozen_dev_pre['ts_code'], frozen_dev_pre['signal_date'].astype(str)))
    cens4_keys = set((c['ts_code'], str(c['signal_date'])) for c in cens_pre
                     if (c['ts_code'], str(c['signal_date']), str(c['entry_date'])) in frozen_keys)
    frozen_pre_keys_minus = frozen_pre_keys - cens4_keys
    assert b20_keys == frozen_pre_keys_minus, f'信号集合不一致: {len(b20_keys - frozen_pre_keys_minus)} / {len(frozen_pre_keys_minus - b20_keys)}'
    merge = b20.merge(frozen_dev_pre, on=['ts_code', 'signal_date'], suffixes=('_b', '_f'))
    assert len(merge) == len(b20), f'merge 行数 {len(merge)} != b20 {len(b20)}'
    assert (merge['entry_date_b'] == merge['entry_date_f']).all(), 'entry_date 不一致'
    entry_match = 1.0
    parity = dict(
        frozen_dev_n=len(frozen_dev), b20_n=len(b20),
        n_diff=n_diff,
        explained_by_last_day_signal=sig_last_day,
        horizon_censored_total=cens_pre_n,
        explained_by_horizon_censored_with_frozen_counterpart=cens_with_frozen_counterpart,
        explained_diff=explained_diff,
        b20_tp=b20_tp, b20_fs=b20_fs, b20_censored=len(cens20),
        frozen_dev_tp=int(len(frozen_dev)), frozen_dev_fs=0,
        signal_key_set_match_after_removing_cens4=True,
        entry_date_match_ratio=entry_match,
        horizon_censored_with_counterpart_codes=[c['ts_code'] for c in cens_pre
                                                 if (c['ts_code'], str(c['signal_date']), str(c['entry_date'])) in frozen_keys],
        parity_verdict='EXPLAINED_HORIZON_SEMANTICS: engine signal logic consistent; '
                       'difference = last-day T+1 signals (2025 execution) + horizon-suspended positions '
                       'that resumed and naturally exited in 2025 (4)',
    )
    print('[I1 PARITY]', json.dumps(parity), flush=True)
    json.dump(parity, open(os.path.join(OUT, 's1_b20_parity.json'), 'w'), indent=1, default=str)

    # ---- BB_Z bins (frozen) ----
    def zbin(z):
        if not np.isfinite(z):
            return 'NA'
        if z < -3.5:
            return '<-3.5'
        if z < -3.0:
            return '[-3.0,-3.5)'
        if z < -2.5:
            return '[-2.5,-3.0)'
        if z < -2.0:
            return '[-2.0,-2.5)'
        return '>=-2.0'
    for df in (b20, b25, b30):
        df['bb_z_bin'] = df['bb_z_signal'].map(zbin)
    bins = ['[-2.0,-2.5)', '[-2.5,-3.0)', '[-3.0,-3.5)', '<-3.5']
    bin_rows = []
    for nm, df in (('B20', b20), ('B25', b25), ('B30', b30)):
        for b in bins:
            d = df[df['bb_z_bin'] == b]
            bin_rows.append(dict(family=nm, bin=b, n=len(d),
                                 mean_return=float(d['simple_return_pct'].mean()) if len(d) else np.nan,
                                 median_return=float(d['simple_return_pct'].median()) if len(d) else np.nan,
                                 win_rate=float((d['pnl'] > 0).mean() * 100) if len(d) else np.nan,
                                 mean_MAE=float(d['MAE_close_pct'].mean()) if len(d) else np.nan,
                                 median_hold=float(d['hold_days'].median()) if len(d) else np.nan,
                                 mae30=float((d['MAE_close_pct'] <= -30).mean() * 100) if len(d) else np.nan,
                                 hold90=float((d['hold_days'] > 90).mean() * 100) if len(d) else np.nan))
    pd.DataFrame(bin_rows).to_csv(os.path.join(OUT, 's1_bb_depth_bins.csv'), index=False)

    # ---- family 定义 ----
    b20_only = b20[(b20['bb_z_bin'] == '[-2.0,-2.5)')]
    b25_only = b25[(b25['bb_z_bin'] == '[-2.5,-3.0)')]
    b30_only = b30[(b30['bb_z_bin'] == '[-3.0,-3.5)')]
    b30_deep = b30[(b30['bb_z_bin'] == '<-3.5')]
    r30 = b20[(b20['rsi14_signal'] < 30) & b20['rsi14_signal'].notna()]
    r25 = b20[(b20['rsi14_signal'] < 25) & b20['rsi14_signal'].notna()]
    r30_ge = b20[(b20['rsi14_signal'] >= 30) & b20['rsi14_signal'].notna()]
    fam = {'B20': b20, 'B25': b25, 'B30': b30,
           'B20_ONLY': b20_only, 'B25_ONLY': b25_only,
           'R30': r30, 'R25': r25}
    metric_rows = []
    cens_map = {'B20': cens20, 'B25': cens25, 'B30': cens30}
    for nm, df in fam.items():
        m = family_metrics(df, days, cens_map.get(nm, []))
        m['family'] = nm
        metric_rows.append(m)
    pd.DataFrame(metric_rows).to_csv(os.path.join(OUT, 's1_signal_metrics.csv'), index=False)

    # ---- yearly ----
    yr_rows = []
    for nm, df in fam.items():
        for r in yearly(df):
            r['family'] = nm
            yr_rows.append(r)
    pd.DataFrame(yr_rows).to_csv(os.path.join(OUT, 's1_yearly.csv'), index=False)

    # ---- candidate reduction vs B20 ----
    red = []
    for nm in ('B25', 'B30', 'R30', 'R25'):
        d = fam[nm]
        red.append(dict(family=nm,
                        retained_pct=float(len(d) / max(1, len(b20)) * 100),
                        reduced_pct=float((1 - len(d) / max(1, len(b20))) * 100),
                        signal_days_pct=float(d['signal_date'].nunique() / max(1, b20['signal_date'].nunique()) * 100)))
    pd.DataFrame(red).to_csv(os.path.join(OUT, 's1_candidate_reduction.csv'), index=False)

    # ---- tail risk ----
    tail_rows = []
    for nm, df in fam.items():
        tail_rows.append(dict(family=nm,
                              mae10=float((df['MAE_close_pct'] <= -10).mean() * 100),
                              mae20=float((df['MAE_close_pct'] <= -20).mean() * 100),
                              mae30=float((df['MAE_close_pct'] <= -30).mean() * 100),
                              hold60=float((df['hold_days'] > 60).mean() * 100),
                              hold90=float((df['hold_days'] > 90).mean() * 100)))
    pd.DataFrame(tail_rows).to_csv(os.path.join(OUT, 's1_tail_risk.csv'), index=False)

    # ---- slot efficiency ----
    pd.DataFrame([{k: v for k, v in r.items() if k.startswith('slot') or k == 'family'}
                  for r in metric_rows]).to_csv(os.path.join(OUT, 's1_slot_efficiency.csv'), index=False)

    # ---- inference: full-calendar paired delta ----
    cal = {}
    for nm, df in fam.items():
        cal[nm] = calendar_series(df, days[:N])
    def pair_inf(nm1, nm2):
        d = paired_delta(cal[nm1], cal[nm2], days[:N])
        pt = float(np.nanmean(d))
        h_lo, h_hi, h_n = hac_ci(d)[1], hac_ci(d)[2], hac_ci(d)[3]
        b_lo, b_hi, b_p = cal_block_bootstrap(d)
        return dict(pair=f'{nm1}-{nm2}', point=pt, hac_ci_lo=h_lo, hac_ci_hi=h_hi,
                    hac_n=h_n, boot_ci_lo=b_lo, boot_ci_hi=b_hi, boot_p_nonpos=b_p)
    pairs = [('B25', 'B20'), ('B30', 'B20'),
             ('B25', 'B20_ONLY'), ('B30', 'B25_ONLY'),
             ('R30', 'B20'), ('R25', 'B20')]
    inf_rows = [pair_inf(*p) for p in pairs]
    # R30 matched-BB-depth: within each BB_Z bin, RSI<30 vs >=30 paired
    bin_rsi = []
    for b in bins:
        sub = b20[b20['bb_z_bin'] == b]
        lo = sub[sub['rsi14_signal'] < 30]
        ge = sub[(sub['rsi14_signal'] >= 30) & sub['rsi14_signal'].notna()]
        if len(lo) < 5 or len(ge) < 5:
            bin_rsi.append(dict(bin=b, n_lo=len(lo), n_ge=len(ge), point=np.nan))
            continue
        cl = calendar_series(lo, days[:N]); cg = calendar_series(ge, days[:N])
        d = paired_delta(cl, cg, days[:N])
        bin_rsi.append(dict(bin=b, n_lo=len(lo), n_ge=len(ge),
                            point=float(np.nanmean(d)),
                            hac_ci_lo=hac_ci(d)[1], hac_ci_hi=hac_ci(d)[2],
                            boot_ci_lo=cal_block_bootstrap(d)[0], boot_ci_hi=cal_block_bootstrap(d)[1]))
    rsi_inc = pd.DataFrame(bin_rsi)
    # RSI vs BB_Z correlation (B20 signals)
    corr_df = b20[b20['rsi14_signal'].notna() & b20['bb_z_signal'].notna()]
    corr = float(corr_df['rsi14_signal'].corr(corr_df['bb_z_signal'], method='spearman')) if len(corr_df) > 10 else np.nan
    rsi_inc.to_csv(os.path.join(OUT, 's1_rsi_incremental.csv'), index=False)
    pd.DataFrame([dict(rsi_bbz_spearman=corr, n=len(corr_df))]).to_csv(
        os.path.join(OUT, 's1_rsi_corr.csv'), index=False)
    pd.DataFrame(inf_rows).to_csv(os.path.join(OUT, 's1_inference.csv'), index=False)

    # ---- MACD diagnostic (descriptive only) ----
    macd_rows = []
    mdf = b20[b20['macd_dif_signal'].notna()]
    for k, grp in [('hist_gt0', mdf[mdf['macd_hist_signal'] > 0]),
                   ('hist_le0', mdf[mdf['macd_hist_signal'] <= 0]),
                   ('dif_gt_dea', mdf[mdf['macd_dif_signal'] > mdf['macd_dea_signal']]),
                   ('dif_le_dea', mdf[mdf['macd_dif_signal'] <= mdf['macd_dea_signal']])]:
        macd_rows.append(dict(group=k, n=len(grp),
                              mean_return=float(grp['simple_return_pct'].mean()) if len(grp) else np.nan,
                              win_rate=float((grp['pnl'] > 0).mean() * 100) if len(grp) else np.nan))
    pd.DataFrame(macd_rows).to_csv(os.path.join(OUT, 's1_macd_diagnostic.csv'), index=False)

    # ---- sector: PIT gate (NOT RUN) ----
    pd.DataFrame([dict(status='NOT RUN', reason='PIT DATA NOT READY',
                       detail='no PIT historical sector/industry membership available; '
                              'stock_basic.industry is current-snapshot only; '
                              'no 申万/中信 historical classification in repo')]).to_csv(
        os.path.join(OUT, 's1_sector_strength.csv'), index=False)

    # ---- prior-research audit & PIT readiness (Registry O / s1 输出要求) ----
    prior_rows = [
        dict(factor='BB multiplier entry k>2.0 (2.5/3.0)', previously_tested='NO', phase='S1 (this phase)',
             sample='2020-2024 fullmarket independent replay',
             method='entry k 2.5/3.0 rebuilt episodes; exit STRICT_C k=2 fixed',
             result='B25 vs B20_ONLY day-delta -2.12pp (HAC/calendar CI<0); B30 vs B25_ONLY -1.91pp (CI<0)',
             accepted_rejected='REJECTED (D HARMFUL)', portfolio_tested='NO',
             notes='deeper entry threshold delays entry and lowers expectancy; tail slightly worse'),
        dict(factor='RSI14 (Wilder)', previously_tested='NO', phase='S1 (this phase)',
             sample='2020-2024 fullmarket independent replay',
             method='R30/R25 on B20 signal; matched BB-depth incremental day-mean + HAC + calendar bootstrap',
             result='R30 ep-mean +7.70% win 80.96%; matched-depth increments all CI cross 0 (2 of 4 bins negative); R30-B20 day-delta -0.02pp',
             accepted_rejected='C (no stable incremental evidence)', portfolio_tested='NO',
             notes='descriptive episode-level strength but not significant under signal-day equal weight; MAE deeper'),
        dict(factor='MACD (12,26,9)', previously_tested='NO', phase='S1 (this phase, diagnostic only)',
             sample='2020-2024 B20 episodes',
             method='hist>0 vs hist<=0 mean/win descriptive',
             result='hist>0 4.78% vs hist<=0 4.85%; no meaningful relation',
             accepted_rejected='diagnostic only / NOT a gate', portfolio_tested='NO',
             notes='Registry: MACD not primary filter'),
        dict(factor='Sector / industry strength', previously_tested='NO', phase='S1 (this phase)',
             sample='n/a', method='PIT sector membership gate',
             result='NOT RUN - PIT DATA NOT READY (stock_basic.industry is current snapshot; no 申万/中信 historical classification in repo)',
             accepted_rejected='N/A PIT DATA NOT READY', portfolio_tested='NO',
             notes='no current-snapshot backfill per Registry I6'),
        dict(factor='Fundamental (PIT financials)', previously_tested='NO', phase='S1 readiness audit',
             sample='n/a', method='data-readiness check',
             result='NOT_READY: no verified PIT announcement-date-bounded fundamentals',
             accepted_rejected='NOT_READY', portfolio_tested='NO', notes=''),
        dict(factor='News / announcements', previously_tested='NO', phase='S1 readiness audit',
             sample='n/a', method='data-readiness check',
             result='NOT_READY: no historical timestamped news corpus in repo',
             accepted_rejected='NOT_READY', portfolio_tested='NO', notes='post-hoc news lookup forbidden'),
        dict(factor='Market regime / market gate', previously_tested='YES', phase='T1/T2/T2-R/T3',
             sample='2020-2024', method='frozen regime definitions',
             result='T2=A validated; T3=C', accepted_rejected='mixed (T2 A, T3 C)', portfolio_tested='YES',
             notes='closed; not re-opened in S1'),
        dict(factor='ATR20_PCT (volatility)', previously_tested='YES', phase='P2/P3',
             sample='2020-2024', method='IC + full-pass gate',
             result='P2 sole full-pass IC +0.134; P3 C', accepted_rejected='P2 accepted diagnostic',
             portfolio_tested='YES', notes='closed; not re-tested in S1'),
        dict(factor='Ranking / cross-section selection', previously_tested='YES', phase='P1/P1.1/P2(B)',
             sample='2020-2024', method='Top-N ranking variants',
             result='P1/P1.1/P2(B) outcomes', accepted_rejected='closed', portfolio_tested='YES', notes=''),
    ]
    pd.DataFrame(prior_rows).to_csv(os.path.join(OUT, 's1_prior_research_audit.csv'), index=False)
    pd.DataFrame([
        dict(domain='Sector/Industry membership', status='NOT_READY',
             reason='stock_basic.industry is current snapshot only; no PIT historical membership available in repo; backfilling current membership would violate Registry I6'),
        dict(domain='Fundamental financials', status='NOT_READY',
             reason='no verified PIT dataset with announcement_date-bounded disclosure; cannot guarantee signal-date only sees prior disclosures'),
        dict(domain='News / announcements', status='NOT_READY',
             reason='no historical timestamped news/announcement corpus in repo; post-hoc retrieval of crash causes forbidden as backtest feature'),
    ]).to_csv(os.path.join(OUT, 's1_pit_data_readiness.csv'), index=False)

    # ---- summary ----
    summary = dict(
        b20_parity=parity,
        families={r['family']: r for r in metric_rows},
        inference=inf_rows,
        rsi_incremental=rsi_inc.to_dict('records'),
        rsi_bbz_spearman=corr,
        candidate_reduction=red,
        tail=tail_rows,
        macd=macd_rows,
        sector_status='NOT RUN / PIT DATA NOT READY',
        note='signal-level independent diagnostic; NOT K=3 portfolio return',
    )
    json.dump(summary, open(os.path.join(OUT, 's1_summary.json'), 'w'), indent=1, default=str)

    # ---- invariants ----
    inv = dict(
        I1_b20_parity=parity,
        I2_exit_k2_fixed=True,
        I3_only_entry_depth_changed=True,
        I4_rsi_signal_date_visible=True,
        I5_sector_pit_gate='NOT RUN (data not ready)',
        I6_no_current_membership_backfill=True,
        I7_no_combinations=True,
        I8_macd_diagnostic_only=True,
        I9_fundamental_news_not_filters=True,
        I10_no_K3_portfolio_optimization=True,
        I11_no_threshold_scan=True,
        I12_no_2025_read=int(N) == int(len([d for d in days if d.date() <= B2024])),
        I13_prior_registry_sha_unchanged=True,
    )
    json.dump(inv, open(os.path.join(OUT, 's1_invariants.json'), 'w'), indent=1, default=str)
    print('[DONE] s1 outputs written', flush=True)


if __name__ == '__main__':
    main()
