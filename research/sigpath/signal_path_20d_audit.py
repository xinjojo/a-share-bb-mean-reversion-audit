"""
=====================================================================
SIGPATH — A股 BB Mean Reversion 全量 Signal Forward Path Audit
=====================================================================
数据事实层 (post-A0, 无策略结论):
  - 复用 S1 frozen B20 引擎 (prepare_v51, entry_k=2.0) 完整重放 2020-2024,
    在每一层入场 (NEW_ENTRY / ADD_ON_1..4) 处记录 signal 明细;
  - 每层 signal 以 entry_cost 为基准, 观察未来 D1..D20 该股实际交易日,
    保存 raw OHLC + ret + MFE/MAE;
  - 输出 long / wide 双母表 (Parquet + CSV 分片), 统计/分桶/hit-rate/图,
    manual_review_index, sanity check, README。
  - 2025-2026 CLOSED: 只循环 signal_date<=2024-12-31, 未来路径只取 <=2024-12-31。
=====================================================================
"""
import os, sys, time, json, hashlib
from datetime import date, datetime
import numpy as np
import pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT); sys.path.insert(0, REPO)
from round51_audit import prepare_v51, stamp_rate, COMMISSION_RATE, MIN_COMMISSION, TRANSFER_FEE_RATE
from run_strict_c_math import analytic_Pstar

B2024 = date(2024, 12, 31)
OUT = os.path.join(REPO, 'results', 'evidence', 'sigpath')
CHART = os.path.join(OUT, 'charts')
os.makedirs(OUT, exist_ok=True); os.makedirs(CHART, exist_ok=True)

LEVEL_CASH = 200_000.0; MAX_LEVELS = 5; SLIP = 0.001; ADD_GAP = 1
HORIZON = 20
SEED = 42

# ============================================================
# 1. FROZEN REPLAY -> 全量信号层 (parity: 63,785 episodes)
# ============================================================
def replay_layers(days, D, first_eligible_i, offset, N):
    t0 = time.time()
    pos = {}; pending_buy = []; pending_add = {}; pending_sell = set()
    raw_hist = {}; last_close = {}
    episodes = []; censored = []; layers = []
    ep_counter = [0]
    rank_all_day = {}

    def record_layer(tc, sig_date, sig_i, sig_bbz, sig_bb_mid, sig_bb_lo, sig_bb_up,
                     sig_ohlc, entry_date, entry_i, buy_price, role, ep_id, rk):
        layers.append(dict(ts_code=tc, signal_date=sig_date, signal_i=sig_i, bb_z=sig_bbz,
                           bb_mid=sig_bb_mid, bb_lower=sig_bb_lo, bb_upper=sig_bb_up,
                           sig_open=sig_ohlc[0], sig_high=sig_ohlc[1], sig_low=sig_ohlc[2],
                           sig_close=sig_ohlc[3], sig_amount=sig_ohlc[4], sig_adj=sig_ohlc[5],
                           turnover_rank=rk,
                           entry_date=str(entry_date), entry_i=entry_i, entry_cost=float(buy_price),
                           entry_role=role, position_episode_id=ep_id))

    def sell(tc, d, j, price, exit_type, i):
        p = pos[tc]
        amt = price * p['shares']
        sr = stamp_rate(d, 'historical')
        fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * sr + amt * TRANSFER_FEE_RATE
        proceeds = amt - fee
        pnl = proceeds - p['total_cost']
        if j is not None and not (p['path'] and p['path'][-1][0] == i):
            p['path'].append((i, float(D[d]['close'][j]), float(D[d]['high'][j]), float(D[d]['low'][j])))
        episode_seq_used = p['ep_id']
        sr_pct = pnl / p['total_cost'] * 100
        episodes.append(dict(episode_id=episode_seq_used, ts_code=tc, signal_date=p['signal_date'],
                             entry_date=p['entry_date'], exit_date=str(d.date()), exit_type=exit_type,
                             levels_used=p['levels'], hold_days=i - p['entry_i'], total_cost=p['total_cost'],
                             pnl=pnl, simple_return_pct=sr_pct))
        del pos[tc]; raw_hist.pop(tc, None)
        return episode_seq_used

    def init_raw_hist(tc, i):
        hist = []
        for k in range(19, 0, -1):  # 旧 -> 新 (与 S1 deque+appendleft 等价)
            if i - k < 0:
                continue
            dk = days[i - k]; jk = D[dk]['pos'].get(tc)
            if jk is not None:
                hist.append(float(D[dk]['close_adj'][jk]))
        raw_hist[tc] = hist[-19:]

    for i in range(N):
        d = days[i]; dd = D[d]
        bb_lo_k = dd['bb_lower']
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
            pa = pending_add.pop(tc)
            buy_price = dd['open_'][j] * (1 + SLIP)
            qty = int(LEVEL_CASH / buy_price / 100) * 100
            if qty >= 100:
                amt = buy_price * qty
                fee = max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * TRANSFER_FEE_RATE
                p['shares'] += qty; p['total_cost'] += amt + fee; p['levels'] += 1
                p['last_add_i'] = i
                record_layer(tc, pa['signal_date'], pa['signal_i'], pa['bb_z'], pa['bb_mid'],
                             pa['bb_lower'], pa['bb_upper'], pa['sig_ohlc'],
                             d.date(), i, buy_price, 'ADD_ON_%d' % (p['levels'] - 1), p['ep_id'], pa['rk'])
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
                    ep_counter[0] += 1
                    pos[tc] = dict(shares=qty, total_cost=amt + fee, levels=1, entry_i=i,
                                   last_add_i=i, entry_date=str(d.date()),
                                   signal_date=pb['signal_date'], entry_exec_raw=buy_price,
                                   path=[], bb_z=pb['bb_z'], ep_id=ep_counter[0], turnover_rank=pb['rk'])
                    init_raw_hist(tc, i)
                    record_layer(tc, pb['signal_date'], pb['signal_i'], pb['bb_z'], pb['bb_mid'],
                                 pb['bb_lower'], pb['bb_upper'], pb['sig_ohlc'],
                                 d.date(), i, buy_price, 'NEW_ENTRY', ep_counter[0], pb['rk'])
                pending_buy.remove(pb)
        # ---- 盘中退出: dynamic_touch (Pstar k=2 固定) ----
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
            x = np.array(hist[-19:], dtype=float)
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
        # ---- CLOSE: 加仓条件 ----
        for tc in list(pos.keys()):
            p = pos[tc]; j = dd['pos'].get(tc)
            if j is None:
                last_close[tc] = last_close.get(tc, p['total_cost'] / p['shares'])
                continue
            close = dd['close'][j]
            last_close[tc] = close
            p['path'].append((i, float(close), float(dd['high'][j]), float(dd['low'][j])))
            raw_hist.setdefault(tc, []).append(float(dd['close_adj'][j]))
            if len(raw_hist[tc]) > 19:
                raw_hist[tc] = raw_hist[tc][-19:]
            bb_lo = bb_lo_k[j]
            if (not np.isnan(bb_lo) and dd['close_adj'][j] < bb_lo and not dd['is_limit'][j]
                    and p['levels'] < MAX_LEVELS and (i - p['last_add_i']) >= ADD_GAP):
                rmap = rank_all_day.get(i)
                rk = rmap.get(tc, np.nan) if rmap else np.nan
                bz = bb_z_arr[j]
                pending_add[tc] = dict(signal_date=str(d.date()), signal_i=i,
                                       bb_z=float(bz) if np.isfinite(bz) else np.nan,
                                       bb_mid=float(dd['bb_mid'][j]), bb_lower=float(dd['bb_lower'][j]),
                                       bb_upper=float(dd['bb_upper'][j]),
                                       sig_ohlc=(float(dd['open_'][j]), float(dd['high'][j]),
                                                 float(dd['low'][j]), float(dd['close'][j]),
                                                 float(dd['amount'][j]), float(dd['adj'][j])),
                                       rk=rk)
        # ---- 新买信号 (ALL eligible; TopN 仅记录 rank, 不删信号) ----
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
                    pending_buy.append(dict(ts_code=tc, signal_date=str(d.date()), signal_i=i,
                                            bb_z=float(bz) if np.isfinite(bz) else np.nan,
                                            bb_mid=float(dd['bb_mid'][kk]), bb_lower=float(dd['bb_lower'][kk]),
                                            bb_upper=float(dd['bb_upper'][kk]),
                                            sig_ohlc=(float(dd['open_'][kk]), float(dd['high'][kk]),
                                                      float(dd['low'][kk]), float(dd['close'][kk]),
                                                      float(dd['amount'][kk]), float(dd['adj'][kk])),
                                            rk=int(rmap[tc])))
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
                                 levels_used=p['levels'], total_cost=p['total_cost'], last_close_mark=mark))
            del pos[tc]
    print(f'[REPLAY] episodes={len(episodes)} (TP={sum(1 for e in episodes if e["exit_type"]=="TAKE_PROFIT_DYN")} '
          f'FS={sum(1 for e in episodes if e["exit_type"]=="FINAL_SETTLE")}) censored={len(censored)} '
          f'layers={len(layers)} ({time.time()-t0:.0f}s)', flush=True)
    return pd.DataFrame(episodes), pd.DataFrame(censored), pd.DataFrame(layers)

# ============================================================
# 2. 未来路径提取 (per-stock 实际交易日, <=2024-12-31)
# ============================================================
def build_stock_map():
    t0 = time.time()
    df = pd.read_parquet(os.path.join(ROOT, 'data', 'combined_daily.parquet'),
                         columns=['ts_code', 'date', 'open', 'high', 'low', 'close', 'vol', 'amount'])
    df['date'] = pd.to_datetime(df['date'])
    df = df[df['date'] <= pd.Timestamp('2024-12-31')].sort_values(['ts_code', 'date']).reset_index(drop=True)
    smap = {}
    for tc, g in df.groupby('ts_code'):
        smap[tc] = dict(
            dates=g['date'].to_numpy(),
            open=g['open'].to_numpy(), high=g['high'].to_numpy(),
            low=g['low'].to_numpy(), close=g['close'].to_numpy(),
            vol=g['vol'].to_numpy(), amount=g['amount'].to_numpy())
    print(f'[STOCKMAP] {len(smap)} stocks, {len(df):,} rows ({time.time()-t0:.0f}s)', flush=True)
    return smap

def extract_paths(layers, smap):
    t0 = time.time()
    n = len(layers)
    NAT = np.datetime64('NaT')
    D_DAYS = np.full((n, HORIZON), NAT, dtype='datetime64[ns]')
    D_O = np.full((n, HORIZON), np.nan); D_H = np.full((n, HORIZON), np.nan)
    D_L = np.full((n, HORIZON), np.nan); D_C = np.full((n, HORIZON), np.nan)
    avail = np.zeros(n, dtype=np.int32)
    entry_dates = layers['entry_date'].astype('datetime64[ns]').to_numpy()
    for tc, sm in smap.items():
        sel = np.where(layers['ts_code'].to_numpy() == tc)[0]
        if len(sel) == 0:
            continue
        pos = np.searchsorted(sm['dates'], entry_dates[sel])
        for k, p in enumerate(pos):
            rows = min(HORIZON, len(sm['dates']) - p)
            avail[sel[k]] = rows
            if rows <= 0:
                continue
            sl = slice(p, p + rows)
            D_DAYS[sel[k], :rows] = sm['dates'][sl]
            D_O[sel[k], :rows] = sm['open'][sl]
            D_H[sel[k], :rows] = sm['high'][sl]
            D_L[sel[k], :rows] = sm['low'][sl]
            D_C[sel[k], :rows] = sm['close'][sl]
    print(f'[PATHS] extracted {n:,} signal paths ({time.time()-t0:.0f}s)', flush=True)
    return D_DAYS, D_O, D_H, D_L, D_C, avail

def build_long_wide(layers, D_DAYS, D_O, D_H, D_L, D_C, avail, meta):
    t0 = time.time()
    n = len(layers)
    ec = layers['entry_cost'].to_numpy()
    # wide arrays
    w_dates, w_o, w_h, w_l, w_c = [], [], [], [], []
    w_or, w_hr, w_lr, w_cr, w_mfe, w_mae = [], [], [], [], [], []
    for h in range(HORIZON):
        od, oh, ol, oc = D_O[:, h], D_H[:, h], D_L[:, h], D_C[:, h]
        w_dates.append(D_DAYS[:, h]); w_o.append(od); w_h.append(oh); w_l.append(ol); w_c.append(oc)
        w_or.append(od / ec - 1.0); w_hr.append(oh / ec - 1.0)
        w_lr.append(ol / ec - 1.0); w_cr.append(oc / ec - 1.0)
    HR = np.column_stack(w_hr); LR = np.column_stack(w_lr)
    HR_ = np.where(np.isnan(HR), -np.inf, HR); LR_ = np.where(np.isnan(LR), np.inf, LR)
    MFE = np.maximum.accumulate(HR_, axis=1); MAE = np.minimum.accumulate(LR_, axis=1)
    MFE[MFE == -np.inf] = np.nan; MAE[MAE == np.inf] = np.nan
    for h in range(HORIZON):
        w_mfe.append(MFE[:, h]); w_mae.append(MAE[:, h])
    # 基础列重命名 + 派生
    base = layers.rename(columns={'sig_open': 'signal_day_open', 'sig_high': 'signal_day_high',
                                  'sig_low': 'signal_day_low', 'sig_close': 'signal_day_close',
                                  'sig_amount': 'signal_day_amount', 'sig_adj': 'signal_day_adj_factor'})
    base['BB_width'] = base['bb_upper'] - base['bb_lower']
    base['distance_to_lower_band'] = base['signal_day_close'] * base['signal_day_adj_factor'] - base['bb_lower']
    lid = base.groupby('position_episode_id').cumcount() + 1
    base['signal_id'] = ['SIG%d_%d' % (e, l) for e, l in zip(base['position_episode_id'], lid)]
    wide = pd.DataFrame({c: base[c].to_numpy() for c in base.columns})
    for h in range(HORIZON):
        hn = h + 1
        wide[f'trade_date_D{hn}'] = w_dates[h]
        wide[f'open_D{hn}'] = w_o[h]; wide[f'high_D{hn}'] = w_h[h]
        wide[f'low_D{hn}'] = w_l[h]; wide[f'close_D{hn}'] = w_c[h]
        wide[f'open_ret_D{hn}'] = w_or[h]; wide[f'high_ret_D{hn}'] = w_hr[h]
        wide[f'low_ret_D{hn}'] = w_lr[h]; wide[f'close_ret_D{hn}'] = w_cr[h]
        wide[f'MFE_D{hn}'] = w_mfe[h]; wide[f'MAE_D{hn}'] = w_mae[h]
    wide['available_future_days'] = avail
    # long (每 signal 固定 20 行; 缺失日 NaN 行保留, 与 wide 完全一致)
    sig_ids = wide['signal_id'].to_numpy()
    tsc = wide['ts_code'].to_numpy()
    sc = np.full(n, '', dtype=object)   # 占位, main 中 attach_meta 后回填
    sn = np.full(n, '', dtype=object)
    sgd = wide['signal_date'].to_numpy(); end = wide['entry_date'].to_numpy()
    role = wide['entry_role'].to_numpy(); epi = wide['position_episode_id'].to_numpy()
    flg = np.full(n, '', dtype=object)  # 占位, main 中 attach_meta 后统一赋值
    long_rows = []
    for h in range(HORIZON):
        hn = h + 1
        long_rows.append(pd.DataFrame({
            'signal_id': sig_ids, 'ts_code': tsc, 'stock_code': sc, 'stock_name': sn,
            'signal_date': sgd, 'entry_date': end, 'entry_cost': ec, 'entry_role': role,
            'position_episode_id': epi, 'horizon_day': np.full(n, hn, dtype=np.int32),
            'trade_date': w_dates[h], 'open': w_o[h], 'high': w_h[h], 'low': w_l[h], 'close': w_c[h],
            'open_ret': w_or[h], 'high_ret': w_hr[h], 'low_ret': w_lr[h], 'close_ret': w_cr[h],
            'MFE': w_mfe[h], 'MAE': w_mae[h], 'data_quality_flag': flg,
        }))
    long = pd.concat(long_rows, ignore_index=True)
    print(f'[TABLES] wide {wide.shape}, long {long.shape} ({time.time()-t0:.0f}s)', flush=True)
    return wide, long

def attach_meta(wide, layers, smap):
    # stock_name (PIT: namechange_full 按 signal_date 取当时名称; fallback stock_basic 当前名; 无 -> UNKNOWN)
    sb = pd.read_csv(os.path.join(ROOT, 'data', 'raw', 'stock_basic.csv'))
    sb_map = {r.ts_code: r for r in sb.itertuples()}
    sb_name = {t: (r.name if hasattr(r, 'name') else pd.NA) for t, r in sb_map.items()}
    nc = pd.read_parquet(os.path.join(ROOT, 'data', 'raw', 'namechange_full.parquet'))
    nc['start_date'] = pd.to_datetime(nc['start_date'])
    nc['end_date'] = pd.to_datetime(nc['end_date'])
    nc_map = {}
    for tc, g in nc.groupby('ts_code'):
        g = g.sort_values('start_date')
        nc_map[tc] = (g['start_date'].to_numpy(), g['end_date'].to_numpy(), g['name'].to_numpy())
    sd_arr = wide['signal_date'].to_numpy().astype('datetime64[ns]')
    names = []
    for tc, sd in zip(wide['ts_code'].to_numpy(), sd_arr):
        v = nc_map.get(tc)
        nm = None
        if v is not None:
            st, en, nmarr = v
            pos = int(np.searchsorted(st, sd, side='right')) - 1
            if pos >= 0 and (np.isnat(en[pos]) or en[pos] >= sd):
                nm = nmarr[pos]
        if nm is None:
            nm = sb_name.get(tc, pd.NA)
        names.append(nm if nm is not None else 'UNKNOWN')
    code = wide['ts_code'].str.split('.').str[0]
    lds = [sb_map.get(t).list_date if t in sb_map else pd.NA for t in wide['ts_code']]
    inds = [sb_map.get(t).industry if t in sb_map else pd.NA for t in wide['ts_code']]
    exs = [str(t).split('.')[1] if '.' in str(t) else pd.NA for t in wide['ts_code']]
    wide.insert(0, 'stock_code', code.to_numpy())
    wide.insert(1, 'stock_name', names)
    wide.insert(2, 'exchange', exs)
    wide.insert(3, 'list_date', lds)
    wide.insert(4, 'industry_snapshot', inds)
    # sector PIT (D1 context, signal-date 级)
    d1 = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'd1', 'd1_signal_context.csv'),
                     usecols=['ts_code', 'signal_date', 'sector_pit'])
    m = wide.merge(d1, on=['ts_code', 'signal_date'], how='left')
    # signal 日 volume (parquet) + 列序 (signal_id 最前)
    m['signal_day_volume'] = np.nan
    for tc, sm in smap.items():
        sel = np.where(m['ts_code'].to_numpy() == tc)[0]
        if len(sel) == 0:
            continue
        sd = m['signal_date'].to_numpy()[sel].astype('datetime64[ns]')
        pos = np.searchsorted(sm['dates'], sd)
        ok = (pos < len(sm['dates'])) & (sm['dates'][pos] == sd)
        m.loc[m.index[sel[ok]], 'signal_day_volume'] = sm['vol'][pos[ok]]
    cols = ['signal_id'] + [c for c in m.columns if c != 'signal_id']
    return m[cols]

# ============================================================
# 3. MAIN
# ============================================================
def main():
    t0 = time.time()
    resume = os.environ.get('SIGPATH_RESUME') == '1'
    layers_csv = os.path.join(OUT, 'sigpath_layers_raw.csv')
    if resume and os.path.exists(layers_csv):
        layers = pd.read_csv(layers_csv)
        print(f'[RESUME] loaded {len(layers):,} layers from csv', flush=True)
    else:
        print('prepare_v51 ...', flush=True)
        days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51()
        N = next(i for i, d in enumerate(days) if d.date() == B2024) + 1
        assert days[N - 1].date() == B2024
        print(f'[DAYS] {len(days)} total, N(<=2024) = {N}', flush=True)

        eps, cens, layers = replay_layers(days, D, first_eligible_i, offset, N)

        # ---- parity ----
        n_tp = int((eps['exit_type'] == 'TAKE_PROFIT_DYN').sum())
        n_fs = int((eps['exit_type'] == 'FINAL_SETTLE').sum())
        n_cen = len(cens)
        assert len(eps) == 63785, f'parity fail episodes: {len(eps)}'
        assert n_tp == 61828, f'TP parity fail: {n_tp}'
        assert n_fs == 1957, f'FS parity fail: {n_fs}'
        assert n_cen == 102, f'censored parity fail: {n_cen}'
        n_new = int((layers['entry_role'] == 'NEW_ENTRY').sum())
        assert n_new == 63887, f'NEW_ENTRY parity fail: {n_new} (expect 63785+102 censored)'
        sum_levels = int(eps['levels_used'].sum()) + int(cens['levels_used'].sum())
        assert len(layers) == sum_levels, f'layer count {len(layers)} != sum levels {sum_levels}'
        print(f'[PARITY] OK: episodes {len(eps)} (TP {n_tp} FS {n_fs}) censored {n_cen} '
              f'NEW_ENTRY {n_new} layers {len(layers)} (sum levels {sum_levels})', flush=True)

        layers.to_csv(os.path.join(OUT, 'sigpath_layers_raw.csv'), index=False)
        eps.to_csv(os.path.join(OUT, 'sigpath_episodes_parity.csv'), index=False)

    smap = build_stock_map()
    D_DAYS, D_O, D_H, D_L, D_C, avail = extract_paths(layers, smap)
    wide, long = build_long_wide(layers, D_DAYS, D_O, D_H, D_L, D_C, avail, None)

    # meta attach (name PIT/list/exchange/industry/sector/vol)
    wide = attach_meta(wide, layers, smap)
    # 回填 long 的 stock_code/stock_name
    cmap = dict(zip(wide['ts_code'], wide['stock_code']))
    nmap = dict(zip(wide['ts_code'], wide['stock_name']))
    long['stock_code'] = long['ts_code'].map(cmap).to_numpy()
    long['stock_name'] = long['ts_code'].map(nmap).to_numpy()
    # data_quality_flag
    flags = []
    for h in range(HORIZON):
        f = np.full(n := len(wide), '', dtype=object)
        # JUMP: 相邻 close 跳变 >=30%
        c = wide[f'close_D{h+1}'].to_numpy()
        if h == 0:
            prev = wide['signal_day_close'].to_numpy() if 'signal_day_close' in wide.columns else np.full(n, np.nan)
        else:
            prev = wide[f'close_D{h}'].to_numpy()
        jump = ~np.isnan(c) & ~np.isnan(prev) & (np.abs(c / prev - 1.0) >= 0.30)
        f[jump] = 'JUMP'
        flags.append(f)
    wf = np.full(len(wide), '', dtype=object)
    for h in range(HORIZON):
        for k in np.where(flags[h] == 'JUMP')[0]:
            wf[k] = 'JUMP' if wf[k] == '' else wf[k] + ';JUMP'
    short = avail < HORIZON
    for k in np.where(short)[0]:
        wf[k] = 'SHORT_HISTORY' if wf[k] == '' else wf[k] + ';SHORT_HISTORY'
    wide['data_quality_flag'] = wf
    long['data_quality_flag'] = long['signal_id'].map(
        dict(zip(wide['signal_id'], wide['data_quality_flag']))).to_numpy()

    # ---- save parquet + csv 分片 ----
    wide.to_parquet(os.path.join(OUT, 'signal_path_20d_wide.parquet'), index=False)
    long.to_parquet(os.path.join(OUT, 'signal_path_20d_long.parquet'), index=False)
    write_csv_shards(wide, 'signal_path_20d_wide.csv', 40000)
    write_csv_shards(long, 'signal_path_20d_long.csv', 400000)
    print(f'[SAVE] done ({time.time()-t0:.0f}s)', flush=True)

def write_csv_shards(df, name, rows_per):
    n = len(df)
    nsh = int(np.ceil(n / rows_per))
    for s in range(nsh):
        lo = s * rows_per; hi = min(n, lo + rows_per)
        fn = f'{name}.part_{s+1:03d}' if nsh > 1 else name
        df.iloc[lo:hi].to_csv(os.path.join(OUT, fn), index=False)
    print(f'[CSV] {name}: {n:,} rows -> {nsh} shard(s)', flush=True)

if __name__ == '__main__':
    main()
