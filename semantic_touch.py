"""STRICT_C 交易级语义对照 + 归因
对每笔交易, 在 [entry+1, exit] 期间用日线数据分别计算各退出语义的首触发日:
  current  : high_adj[T] >= bb_upper[T]        (含当日close同Bar未来)
  prev     : high_adj[T] >= bb_upper_prev[T]   (T-1已知上轨)
  dynamic  : high_adj[T] >= P*(T)              (动态盘中上轨临界价)
  confirm  : close_adj[T] >= bb_upper[T] -> T+1卖
回答: INVALID 判卖事件中, dynamic 同日/更早/更晚/假触发; 反向亦然.
"""
import sys, os
import numpy as np, pandas as pd
ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
sys.path.insert(0, ROOT)
from round51_audit import prepare_v51
from run_strict_c_math import analytic_Pstar


def load_ctx():
    days, D, etf_idx, etf_px, etf_open, etf_nav, fie, off = prepare_v51(
        limit_down_mode='correct', st_mode='pit')
    di = {d: i for i, d in enumerate(days)}
    return days, D, di


def touch_first(days, D, di, ts_code, entry_date, exit_date, sem):
    """返回在持仓窗口 [entry+1, exit] 内 sem 语义首触发日(索引), 无则 None."""
    ei = di[pd.Timestamp(entry_date)]
    xi = di[pd.Timestamp(exit_date)]
    # 取该股窗口日线
    bars = []
    for k in range(ei + 1, xi + 1):
        d = days[k]
        j = D[d]['pos'].get(ts_code)
        if j is None:
            continue
        bars.append((k, d, j))
    if not bars:
        return None
    for k, d, j in bars:
        dd = D[d]
        if sem == 'current':
            if (not np.isnan(dd['bb_upper'][j]) and dd['high_adj'][j] >= dd['bb_upper'][j]):
                return k
        elif sem == 'prev':
            if (not np.isnan(dd['bb_upper_prev'][j]) and dd['high_adj'][j] >= dd['bb_upper_prev'][j]):
                return k
        elif sem == 'confirm':
            if (not np.isnan(dd['bb_upper'][j]) and dd['close_adj'][j] >= dd['bb_upper'][j]):
                return k
        elif sem == 'dynamic':
            # 前19日 close (T日 adj 口径)
            hist = []
            for kk in range(k - 1, max(k - 20, -1), -1):
                dk = days[kk]
                jk = D[dk]['pos'].get(ts_code)
                if jk is not None:
                    hist.append(float(D[dk]['close'][jk]))
                if len(hist) == 19:
                    break
            if len(hist) < 19:
                continue
            adj = dd['adj'][j]
            x = np.array(hist[::-1], dtype=float) * adj
            Ps = analytic_Pstar(x)
            if Ps is None or not np.isfinite(Ps):
                continue
            if dd['high_adj'][j] >= Ps:
                return k
    return None


def classify(main_tr, comp_sem, days, D, di, label):
    """main_tr 每笔(其 exit 由自身语义决定), 计算 comp_sem 首触发日并分类."""
    rows = []
    for _, t in main_tr.iterrows():
        if t['exit_type'] == 'FINAL_SETTLE':
            continue
        ec = touch_first(days, D, di, t['ts_code'], t['entry_date'], t['exit_date'], comp_sem)
        if ec is None:
            # comp 在窗口内未触发
            rows.append({'ts_code': t['ts_code'], 'entry': t['entry_date'], 'exit': t['exit_date'],
                         'cls': 'COMP_NEVER_TOUCHED', 'comp_i': None, 'exit_i': di[pd.Timestamp(t['exit_date'])]})
            continue
        exit_i = di[pd.Timestamp(t['exit_date'])]
        if ec == exit_i:
            cls = 'SAME_DAY'
        elif ec < exit_i:
            cls = 'COMP_EARLIER'
        else:
            cls = 'COMP_LATER'
        rows.append({'ts_code': t['ts_code'], 'entry': t['entry_date'], 'exit': t['exit_date'],
                     'cls': cls, 'comp_i': ec, 'exit_i': exit_i})
    df = pd.DataFrame(rows)
    print(f'\n[{label}] 对照语义={comp_sem}  (n={len(df)})')
    print(df['cls'].value_counts().to_string())
    # 日期差统计
    sub = df[df['comp_i'].notna()]
    if len(sub):
        sub['gap_days'] = (sub['comp_i'] - sub['exit_i']).astype(int)
        print(f'comp_i-exit_i 天数差: 早(负)=comp更早触发  均值={sub["gap_days"].mean():.2f} '
              f'中位={sub["gap_days"].median():.2f} min={sub["gap_days"].min()} max={sub["gap_days"].max()}')
    return df


def exit_price_compare(days, D, di, tr, label):
    """对每笔(entry,exit,ts_code): 若同日 different 语义也触发, 比较成交价假设."""
    rows = []
    for _, t in tr.iterrows():
        if t['exit_type'] == 'FINAL_SETTLE':
            continue
        ts = t['ts_code']; ed = pd.Timestamp(t['exit_date'])
        k = di[ed]; j = D[days[k]]['pos'].get(ts)
        if j is None:
            continue
        dd = D[days[k]]
        hist = []
        for kk in range(k - 1, max(k - 20, -1), -1):
            dk = days[kk]; jk = D[dk]['pos'].get(ts)
            if jk is not None:
                hist.append(float(D[dk]['close'][jk]))
            if len(hist) == 19:
                break
        if len(hist) < 19:
            continue
        adj = dd['adj'][j]
        x = np.array(hist[::-1], dtype=float) * adj
        Ps = analytic_Pstar(x)
        cur_price = dd['bb_upper'][j] / adj if not np.isnan(dd['bb_upper'][j]) else np.nan
        dyn_price = (Ps / adj) if (Ps is not None and np.isfinite(Ps)) else np.nan
        rows.append({'ts_code': ts, 'exit': t['exit_date'], 'current_exit_px': cur_price,
                     'dynamic_exit_px': dyn_price,
                     'open': dd['open_'][j], 'high': dd['high'][j], 'close': dd['close'][j]})
    df = pd.DataFrame(rows)
    if len(df):
        df['px_diff'] = df['current_exit_px'] - df['dynamic_exit_px']
        df['px_diff_pct'] = df['px_diff'] / df['dynamic_exit_px'] * 100
        print(f'\n[{label}] 同日(若两语义同日触发)卖出价差 current-dynamic: '
              f'均值={df["px_diff_pct"].mean():.2f}% 中位={df["px_diff_pct"].median():.2f}%')
        print('  (负=dynamic价格更高,即INVALID少卖; 正=INVALID多卖)')
    return df


if __name__ == '__main__':
    days, D, di = load_ctx()
    tin = pd.read_csv(os.path.join(ROOT, 'results', 'round5', 'strict_c_trades.csv'))
    tinv = pd.read_csv('/tmp/invalid_same_ds.csv')

    # 1) INVALID 每笔 -> dynamic 首触发
    df1 = classify(tinv, 'dynamic', days, D, di, 'INVALID(同口径) trades 的 dynamic 首触发')
    # 2) INVALID 每笔 -> prev 首触发
    classify(tinv, 'prev', days, D, di, 'INVALID(同口径) trades 的 prev 首触发')
    # 3) STRICT_C 每笔 -> current 首触发 (反向)
    df2 = classify(tin, 'current', days, D, di, 'STRICT_C trades 的 current 首触发')
    # 4) 同日触发者的卖出价差
    exit_price_compare(days, D, di, tinv, 'INVALID')
    df1.to_csv(os.path.join(ROOT, 'results', 'round5', 'semantic_invalid_vs_dynamic.csv'), index=False)
    df2.to_csv(os.path.join(ROOT, 'results', 'round5', 'semantic_strictc_vs_current.csv'), index=False)
    print('\nsaved semantic CSVs')
