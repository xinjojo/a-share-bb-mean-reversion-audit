"""REPLAY SEMANTICS AUDIT V2 — INDEPENDENT TRADE REPLAY
==========================================================
对比 V1(per-stock resume) 与 冻结 STRICT_C_EXECUTABLE_TICK 引擎的执行/censoring 语义差异.

V2A_FROZEN_STRICT : 全局市场交易日历; pending_buy/add/sell 遇 T+1 无行情/缺失 -> CANCEL(完全复制冻结语义);
                    FINAL_SETTLE 仅限末日(2026-08-25)有行情股; 其余持仓 -> censored(单独报告, 不当作 realized).
                    K 无限 / ETF off / 现金无限 -> 每只股票的每次 signal->entry->exit 独立, 无组合阻塞.
V2B_RESUME_ALLOWED: 保留 V1 per-stock resume 语义(=V1 输出), 标 ALTERNATIVE_EXECUTION_DIAGNOSTIC.

P3 censoring 分类: A=GLOBAL_END_SETTLE / B=EARLY_DATA_END / C=KNOWN_DELISTED / D=UNKNOWN_TRUNCATION.
P4 parity: 用冻结 run_fast_multi_strict_c(K=huge, etf off, 现金无限) 与 V2A 逐笔对账.
P5: 输出 V1/V2A/V2B/REALIZED_EXIT_ONLY/OPTIMISTIC_BOUND/PESSIMISTIC_BOUND 六口径 headline.

不调参 / 不新策略 / 不开 Validation / 不改 Registry.
"""
import os, sys, pickle, time
import numpy as np, pandas as pd
from collections import deque

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, REPO)
from round51_audit import prepare_v51, stamp_rate, COMMISSION_RATE, MIN_COMMISSION, TRANSFER_FEE_RATE
from run_strict_c_math import analytic_Pstar
import independent_trade_replay as v1mod
from run_strict_c import run_fast_multi_strict_c

OUT = os.path.join(REPO, 'results')
os.makedirs(OUT, exist_ok=True)

LEVEL_CASH = 200_000.0
MAX_LEVELS = 5
SLIP = 0.001
ADD_GAP = 1


# ============================================================
# V2A — FROZEN_STRICT (全局市场日历, pending 遇无行情取消)
# ============================================================
def replay_v2a(days, D, first_eligible_i, offset):
    N = len(days)
    pos = {}            # tc -> position dict
    pending_buy = []    # list of {'ts_code', 'signal_date'}
    pending_add = {}    # tc -> True
    pending_sell = set()
    raw_hist = {}       # tc -> deque(close_adj, maxlen=19) 截至前一交易日
    episodes = []
    censored = []
    last_close = {}
    # 用于 P2 flag: 每股最近19市场日有效数据日数(在入场日)
    entry_flag = []     # (tc, entry_i, n_data_in_prev19)

    def sell(tc, d, j, price, exit_type, i):
        p = pos[tc]
        amt = price * p['shares']
        sr = stamp_rate(d, 'historical')
        fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
        proceeds = amt - fee
        pnl = proceeds - p['total_cost']
        ep = dict(ts_code=tc, signal_date=p['signal_date'], entry_date=p['entry_date'],
                  exit_date=str(d.date()), exit_type=exit_type, levels_used=p['levels'],
                  hold_days=i - p['entry_i'], total_cost=p['total_cost'], proceeds=proceeds,
                  pnl=pnl, return_pct=pnl / p['total_cost'] * 100)
        episodes.append(ep)
        del pos[tc]
        raw_hist.pop(tc, None)
        return ep

    def init_raw_hist(tc, i):
        hist = deque()
        for k in range(1, 20):
            if i - k < 0:
                break
            dk = days[i - k]
            jk = D[dk]['pos'].get(tc)
            if jk is not None:
                hist.appendleft(float(D[dk]['close_adj'][jk]))
        raw_hist[tc] = deque(hist, 19)
        return len(hist)

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
                p['shares'] += qty
                p['total_cost'] += amt + fee
                p['levels'] += 1
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
                    p = dict(shares=qty, total_cost=amt + fee, levels=1,
                             entry_i=i, last_add_i=i, entry_date=str(d.date()),
                             signal_date=pb['signal_date'])
                    pos[tc] = p
                    n_hist = init_raw_hist(tc, i)
                    entry_flag.append((tc, i, n_hist))
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
            raw_hist.setdefault(tc, deque([], 19)).append(float(dd['close_adj'][j]))
            bb_lo = dd['bb_lower'][j]
            if (not np.isnan(bb_lo) and dd['close_adj'][j] < bb_lo
                    and not dd['is_limit'][j] and p['levels'] < MAX_LEVELS
                    and (i - p['last_add_i']) >= ADD_GAP):
                pending_add[tc] = True

        # ---- 新买信号 (Top10, 收盘确认) ----
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
    d_last = days[-1]
    dd_last = D[d_last]
    for tc in list(pos.keys()):
        j = dd_last['pos'].get(tc)
        if j is not None:
            sell(tc, d_last, j, dd_last['close'][j] * (1 - SLIP), 'FINAL_SETTLE', N - 1)
        else:
            p = pos[tc]
            mark = last_close.get(tc, p['total_cost'] / p['shares'])
            censored.append(dict(ts_code=tc, signal_date=p['signal_date'], entry_date=p['entry_date'],
                                 levels_used=p['levels'], total_cost=p['total_cost'],
                                 last_close_mark=mark,
                                 last_mark_pnl=mark * p['shares'] - p['total_cost'],
                                 last_mark_return_pct=(mark * p['shares'] / p['total_cost'] - 1) * 100))
            del pos[tc]
    print(f'[V2A DONE] episodes={len(episodes)} (TP={sum(1 for e in episodes if e["exit_type"]=="TAKE_PROFIT_DYN")} '
          f'FS={sum(1 for e in episodes if e["exit_type"]=="FINAL_SETTLE")}) censored={len(censored)} '
          f'({time.time()-t0:.0f}s)', flush=True)
    return episodes, censored, entry_flag


# ============================================================
# 统计工具
# ============================================================
def headline_stats(d):
    """d: DataFrame with return_pct, pnl, hold_days, signal_date"""
    if len(d) == 0:
        return dict(n=0, mean=np.nan, median=np.nan, win_rate=np.nan, pf=np.nan,
                    ed_hac_t=np.nan, ed_hac_ci_lo=np.nan, ed_hac_ci_hi=np.nan,
                    mean_2020_23=np.nan, mean_2024_26=np.nan)
    r = d['return_pct']; pnl = d['pnl']
    pos = pnl[pnl > 0].sum(); neg = pnl[pnl < 0].sum()
    pf = pos / abs(neg) if neg != 0 else np.inf
    # event-day HAC
    s = d[d['signal_date'].notna()].copy()
    s['sd'] = pd.to_datetime(s['signal_date'])
    daily = s.groupby('sd')['return_pct'].mean()
    n_days = len(daily)
    ed_t = np.nan; lo = np.nan; hi = np.nan
    if n_days >= 10:
        import statsmodels.api as sm
        y = daily.to_numpy()
        y = y[np.isfinite(y)]
        if len(y) >= 10:
            K = int(np.floor(4 * (len(y) / 100) ** (2 / 9)))
            K = max(0, min(K, len(y) - 2))
            try:
                res = sm.OLS(y, np.ones((len(y), 1))).fit(cov_type='HAC', cov_kwds={'maxlags': K})
                ed_t = float(res.tvalues[0])
                se = float(res.bse[0])
                lo = float(y.mean() - 1.96 * se); hi = float(y.mean() + 1.96 * se)
            except Exception:
                ed_t = np.nan; lo = np.nan; hi = np.nan
    a = d[d['signal_date'].notna() & (pd.to_datetime(d['signal_date']).dt.year <= 2023)]
    b = d[d['signal_date'].notna() & (pd.to_datetime(d['signal_date']).dt.year >= 2024)]
    return dict(n=len(d), mean=r.mean(), median=r.median(), win_rate=(pnl > 0).mean() * 100,
                pf=pf, ed_hac_t=ed_t, ed_hac_ci_lo=lo, ed_hac_ci_hi=hi,
                mean_2020_23=a['return_pct'].mean() if len(a) else np.nan,
                mean_2024_26=b['return_pct'].mean() if len(b) else np.nan)


def epdf(eps):
    return pd.DataFrame([{k: e[k] for k in ('ts_code', 'signal_date', 'entry_date', 'exit_date',
                                            'exit_type', 'levels_used', 'hold_days', 'total_cost',
                                            'proceeds', 'pnl', 'return_pct')} for e in eps])


# ============================================================
# 主
# ============================================================
if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--build', action='store_true')
    ap.add_argument('--run', action='store_true')
    ap.add_argument('--parity', action='store_true')
    ap.add_argument('--all', action='store_true')
    a = ap.parse_args()

    print('prepare_v51 ...', flush=True)
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51()
    print(f'  days={len(days)} {days[0].date()}..{days[-1].date()}')

    if a.build or a.all:
        # V2A replay
        eps_v2a, cens, flags = replay_v2a(days, D, first_eligible_i, offset)
        with open(os.path.join(OUT, 'independent_v2a_episodes.pkl'), 'wb') as f:
            pickle.dump(dict(episodes=eps_v2a, censored=cens, flags=flags), f)
        print('  V2A pkl saved.')

    if a.run or a.all:
        with open(os.path.join(OUT, 'independent_v2a_episodes.pkl'), 'rb') as f:
            v2a = pickle.load(f)
        eps_v2a, cens, flags = v2a['episodes'], v2a['censored'], v2a['flags']
        df_v2a = epdf(eps_v2a)
        df_v2a.to_csv(os.path.join(OUT, 'independent_v2a_episodes.csv'), index=False)
        _c_cols = ['ts_code', 'signal_date', 'entry_date', 'levels_used', 'total_cost',
                   'last_close_mark', 'last_mark_pnl', 'last_mark_return_pct']
        df_cens = pd.DataFrame(cens, columns=_c_cols) if len(cens) else pd.DataFrame(columns=_c_cols)
        df_cens.to_csv(os.path.join(OUT, 'independent_v2a_censored_raw.csv'), index=False)
        print('V2A episodes:', len(df_v2a), ' censored:', len(df_cens))

        # ---- V1 episodes (RESUME semantics) ----
        with open(os.path.join(OUT, 'independent_ep_PRIMARY_DYN.pkl'), 'rb') as f:
            v1eps = pickle.load(f)
        df_v1 = epdf(v1eps)

        # ---- censoring 分类 ----
        sb = pd.read_parquet(os.path.join(ROOT, 'data', 'raw', 'stock_basic.parquet'))
        meta = sb.set_index('ts_code')['delist_date'].to_dict()
        global_end = days[-1]
        # last_seen: 每股最后有数据日
        last_seen = {}
        for d_ in days:
            for tc_ in D[d_]['pos']:
                last_seen[tc_] = d_
        end_idx = {d_: k for k, d_ in enumerate(days)}
        def classify(tc):
            dd_ = meta.get(tc)
            dl = pd.Timestamp(dd_) if (isinstance(dd_, pd.Timestamp) or (isinstance(dd_, str) and dd_ != '')) else pd.NaT
            if pd.isna(dl):
                dl = np.nan
            else:
                dl = pd.Timestamp(dl)
            if not isinstance(dl, pd.Timestamp) or pd.isna(dl):
                dl = np.nan
            ls = last_seen.get(tc)
            if ls is None:
                return 'N/A'
            if ls >= global_end:
                return 'A_GLOBAL_END'
            if isinstance(dl, pd.Timestamp) and dl < global_end:
                return 'C_KNOWN_DELISTED'
            # 距末日市场日数
            gap = end_idx.get(global_end, len(days)) - end_idx.get(ls, 0)
            if gap <= 5:
                return 'D_UNKNOWN_TRUNCATION'
            return 'B_EARLY_DATA_END'
        if len(df_cens):
            df_cens['censoring_class'] = df_cens['ts_code'].map(classify)
        else:
            df_cens['censoring_class'] = []
        df_cens.to_csv(os.path.join(OUT, 'independent_v2_censored_episodes.csv'), index=False)
        print('\n[CENSORED 分类]')
        print(df_cens['censoring_class'].value_counts().to_string())
        # A (FINAL_SETTLE) 也归类
        fs = df_v2a[df_v2a['exit_type'] == 'FINAL_SETTLE'].copy()
        fs['censoring_class'] = 'A_GLOBAL_END_SETTLE'
        print('FINAL_SETTLE(A) count:', len(fs))

        # ---- 六口径 headline ----
        tp = df_v2a[df_v2a['exit_type'] == 'TAKE_PROFIT_DYN']
        # V2A_FROZEN: realized = TP + A
        v2a_real = pd.concat([tp, fs])
        # OPTIMISTIC: V2A realized + censored at last close
        if len(df_cens):
            c_opt = df_cens.copy()
            c_opt['exit_date'] = 'CENSORED'
            c_opt['hold_days'] = np.nan
            c_opt['return_pct'] = c_opt['last_mark_return_pct'].astype(float)
            c_opt['pnl'] = c_opt['last_mark_pnl'].astype(float)
            c_opt['exit_type'] = 'CENSORED_LAST_MARK'
            opt = pd.concat([v2a_real, c_opt[['ts_code', 'signal_date', 'entry_date', 'exit_date', 'exit_type',
                                              'levels_used', 'hold_days', 'total_cost', 'pnl', 'return_pct']]])
            # PESSIMISTIC: censored recovery=0 (pnl=-total_cost, return=-100%)
            c_pes = df_cens.copy()
            c_pes['exit_date'] = 'CENSORED'
            c_pes['hold_days'] = np.nan
            c_pes['return_pct'] = -100.0
            c_pes['pnl'] = -c_pes['total_cost'].astype(float)
            c_pes['exit_type'] = 'CENSORED_RECOVERY0'
            pes = pd.concat([v2a_real, c_pes[['ts_code', 'signal_date', 'entry_date', 'exit_date', 'exit_type',
                                              'levels_used', 'hold_days', 'total_cost', 'pnl', 'return_pct']]])
        else:
            opt = v2a_real.copy()
            pes = v2a_real.copy()
        # REALIZED_EXIT_ONLY: 仅 TP
        rows = []
        for lab, d_ in [('V1_CURRENT', df_v1),
                        ('V2A_FROZEN_STRICT', v2a_real),
                        ('V2B_RESUME_ALLOWED', df_v1),
                        ('REALIZED_EXIT_ONLY', tp),
                        ('OPTIMISTIC_BOUND', opt),
                        ('PESSIMISTIC_BOUND', pes)]:
            h = headline_stats(d_)
            rows.append(dict(version=lab, **h))
        summ = pd.DataFrame(rows)
        print('\n[PRIMARY 六口径]')
        print(summ.round(3).to_string(index=False))
        summ.to_csv(os.path.join(OUT, 'independent_v2_primary_summary.csv'), index=False)

        # ---- V1 vs V2A semantics diff ----
        # 匹配: (ts_code, signal_date) — signal_date 规范化到 YYYY-MM-DD
        df_v1k = df_v1.copy()
        df_v1k['sd_key'] = pd.to_datetime(df_v1k['signal_date']).dt.strftime('%Y-%m-%d')
        df_v2k = v2a_real.copy()
        df_v2k['sd_key'] = pd.to_datetime(df_v2k['signal_date']).dt.strftime('%Y-%m-%d')
        v1_key = df_v1k.set_index(['ts_code', 'sd_key'])
        v2_key = df_v2k.set_index(['ts_code', 'sd_key'])
        diff_rows = []
        for (tc, sd), row in v1_key.iterrows():
            if (tc, sd) in v2_key.index:
                r2 = v2_key.loc[(tc, sd)]
                diff_rows.append(dict(ts_code=tc, signal_date=sd,
                                      v1_entry=str(pd.to_datetime(row['entry_date']).date()), v2a_entry=str(pd.to_datetime(r2['entry_date']).date()),
                                      v1_exit=str(pd.to_datetime(row['exit_date']).date()), v2a_exit=str(pd.to_datetime(r2['exit_date']).date()),
                                      v1_type=row['exit_type'], v2a_type=r2['exit_type'],
                                      v1_ret=row['return_pct'], v2a_ret=r2['return_pct'],
                                      status='MATCHED'))
            else:
                diff_rows.append(dict(ts_code=tc, signal_date=sd, v1_entry=str(pd.to_datetime(row['entry_date']).date()),
                                      v1_exit=str(pd.to_datetime(row['exit_date']).date()), v1_type=row['exit_type'],
                                      v1_ret=row['return_pct'], v2a_entry=None, v2a_exit=None,
                                      v2a_type=None, v2a_ret=None, status='V1_ONLY_PENDING_CANCELLED'))
        v2_only = [(tc, sd) for (tc, sd) in v2_key.index if (tc, sd) not in v1_key.index]
        for (tc, sd) in v2_only:
            r2 = v2_key.loc[(tc, sd)]
            diff_rows.append(dict(ts_code=tc, signal_date=sd, v1_entry=None, v2a_entry=str(pd.to_datetime(r2['entry_date']).date()),
                                  v1_exit=None, v2a_exit=str(pd.to_datetime(r2['exit_date']).date()), v1_type=None, v2a_type=r2['exit_type'],
                                  v1_ret=None, v2a_ret=r2['return_pct'], status='V2A_ONLY'))
        df_diff = pd.DataFrame(diff_rows)
        # P2 flag: 入场时前19市场日有效数据<19
        flag_map = {(tc, days[i]): n for (tc, i, n) in flags}
        df_diff['p2_rawhist_lt19'] = df_diff.apply(
            lambda r: flag_map.get((r['ts_code'], pd.Timestamp(r['v2a_entry'])), np.nan) if pd.notna(r['v2a_entry']) else np.nan, axis=1)
        df_diff['p2_rawhist_affected'] = (df_diff['p2_rawhist_lt19'].notna() & (df_diff['p2_rawhist_lt19'] < 19))
        # 入场日差异(>0 => pending 顺延/resume 差异)
        df_diff['entry_date_diff'] = df_diff.apply(
            lambda r: (pd.to_datetime(r['v2a_entry']) - pd.to_datetime(r['v1_entry'])).days
            if pd.notna(r['v1_entry']) and pd.notna(r['v2a_entry']) else np.nan, axis=1)
        df_diff.to_csv(os.path.join(OUT, 'independent_v2_semantics_diff.csv'), index=False)
        n_v1only = (df_diff['status'] == 'V1_ONLY_PENDING_CANCELLED').sum()
        n_v2only = (df_diff['status'] == 'V2A_ONLY').sum()
        n_matched = (df_diff['status'] == 'MATCHED').sum()
        n_p2 = int(df_diff['p2_rawhist_affected'].sum())
        n_exit_diff = int(((df_diff['v1_exit'] != df_diff['v2a_exit']) & df_diff['status'].eq('MATCHED')).sum())
        n_ret_diff = int(((df_diff['v1_ret'] != df_diff['v2a_ret']) & df_diff['status'].eq('MATCHED')).sum())
        print(f'\n[V1 vs V2A] matched={n_matched} V1_only_cancelled={n_v1only} V2A_only={n_v2only}')
        print(f'  P2(raw_hist<19) affected entries={n_p2}  matched中 exit_date不同={n_exit_diff} return不同={n_ret_diff}')

    if a.parity or a.all:
        print('\n[PARITY] 冻结引擎 K=huge etf=off ...', flush=True)
        eqP, trP, acP, paP = run_fast_multi_strict_c(
            days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
            K=10 ** 6, top_n=10, max_levels=5, level_cash=200_000, initial_cash=10 ** 9,
            slippage_bp=10, stamp_tax_mode='historical', exit_bb_mode='dynamic_touch',
            open_fill='limit_conservative', tick_mode='conservative', limit_slip_order='ref_first',
            etf_enabled=False, day_range=(0, len(days)), record_actions=False)
        trP['ts_code'] = trP['ts_code'].astype(str)
        print(f'  冻结引擎 trades={len(trP)} exit_types:', trP['exit_type'].value_counts().to_dict())
        trP.to_csv(os.path.join(OUT, 'independent_v2_parity_frozen_trades.csv'), index=False)

        # V2A realized (TP+A) 对比
        with open(os.path.join(OUT, 'independent_v2a_episodes.pkl'), 'rb') as f:
            v2a = pickle.load(f)
        eps_v2a = v2a['episodes']
        df_v2a = epdf(eps_v2a)
        v2a_r = df_v2a[df_v2a['exit_type'].isin(['TAKE_PROFIT_DYN', 'FINAL_SETTLE'])].copy()
        frozen = trP[['ts_code', 'entry_date', 'exit_date', 'exit_type', 'levels_used', 'return_pct', 'pnl', 'hold_days']].copy()
        # 匹配 (ts_code, entry_date)
        fkey = frozen.set_index(['ts_code', 'entry_date'])
        vkey = v2a_r.set_index(['ts_code', 'entry_date'])
        fkeys = set(fkey.index); vkeys = set(vkey.index)
        both = fkeys & vkeys
        only_f = fkeys - vkeys
        only_v = vkeys - fkeys
        mismatch = []
        for key in sorted(both):
            fr = fkey.loc[key]; vr = vkey.loc[key]
            if isinstance(fr, pd.DataFrame):
                fr = fr.iloc[0]
            if isinstance(vr, pd.DataFrame):
                vr = vr.iloc[0]
            ok = (fr['exit_date'] == vr['exit_date'] and fr['exit_type'] == vr['exit_type']
                  and abs(float(fr['return_pct']) - round(float(vr['return_pct']), 2)) < 1e-6)
            mismatch.append(dict(ts_code=key[0], entry_date=key[1], match='MATCH',
                                 frozen_exit=fr['exit_date'], v2a_exit=vr['exit_date'],
                                 frozen_type=fr['exit_type'], v2a_type=vr['exit_type'],
                                 frozen_ret=fr['return_pct'], v2a_ret=vr['return_pct'],
                                 ok=bool(ok)))
        for key in sorted(only_f):
            fr = fkey.loc[key]
            if isinstance(fr, pd.DataFrame):
                fr = fr.iloc[0]
            mismatch.append(dict(ts_code=key[0], entry_date=key[1], match='ONLY_FROZEN',
                                 frozen_exit=fr['exit_date'], v2a_exit=None,
                                 frozen_type=fr['exit_type'], v2a_type=None,
                                 frozen_ret=fr['return_pct'], v2a_ret=None, ok=False))
        for key in sorted(only_v):
            vr = vkey.loc[key]
            if isinstance(vr, pd.DataFrame):
                vr = vr.iloc[0]
            mismatch.append(dict(ts_code=key[0], entry_date=key[1], match='ONLY_V2A',
                                 frozen_exit=None, v2a_exit=vr['exit_date'],
                                 frozen_type=None, v2a_type=vr['exit_type'],
                                 frozen_ret=None, v2a_ret=vr['return_pct'], ok=False))
        df_pc = pd.DataFrame(mismatch)
        df_pc.to_csv(os.path.join(OUT, 'independent_v2_parity_check.csv'), index=False)
        n_match = int((df_pc['match'] == 'MATCH').sum())
        n_ok = int((df_pc['ok'] == True).sum())
        n_only_f = int((df_pc['match'] == 'ONLY_FROZEN').sum())
        n_only_v = int((df_pc['match'] == 'ONLY_V2A').sum())
        print(f'[PARITY] 匹配={n_match} (其中完全一致={n_ok}) 仅冻结={n_only_f} 仅V2A={n_only_v}')
        if n_match > n_ok:
            bad = df_pc[(df_pc['match'] == 'MATCH') & (~df_pc['ok'])]
            print('不一致样本:')
            print(bad.head(15).to_string(index=False))

    print('\nALL V2 DONE')
