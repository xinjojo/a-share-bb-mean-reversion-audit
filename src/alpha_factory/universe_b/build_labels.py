"""Universe B — label builder (Phase 0). Feature 与 Label 物理分离。
标签只读 > T 数据。输出 results/evidence/alpha_factory/universe_b/labels/year=YYYY/*.parquet
"""
import os
import numpy as np
import pandas as pd

REPO = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo'
PANEL = os.path.join(REPO, 'results/evidence/alpha_factory/universe_b', 'panel')
OUT = os.path.join(REPO, 'results/evidence/alpha_factory/universe_b', 'labels')


def load_panel():
    files = []
    for root, _, fs in os.walk(PANEL):
        for f in fs:
            if f.endswith('.parquet'):
                files.append(os.path.join(root, f))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def build():
    p = load_panel()
    p = p[p['is_suspended'] == False].copy()
    p = p.sort_values(['ts_code', 'date'])
    g = p.groupby('ts_code', sort=False)

    close = p['close_adj']
    open_adj = p['open_adj']

    lab = pd.DataFrame(index=p.index)
    for h in [1, 5, 10, 20, 60]:
        fwd = close.groupby(p['ts_code']).shift(-h) / close - 1.0
        lab[f'fwd_ret_{h}'] = fwd
    # MFE / MAE
    for h in [5, 20]:
        fwd_high = p['high_adj'].groupby(p['ts_code']).transform(
            lambda x: x[::-1].rolling(h, min_periods=h).max()[::-1])
        fwd_low = p['low_adj'].groupby(p['ts_code']).transform(
            lambda x: x[::-1].rolling(h, min_periods=h).min()[::-1])
        lab[f'MFE_{h}'] = fwd_high / close - 1.0
        lab[f'MAE_{h}'] = fwd_low / close - 1.0
    # executable: T+1 open entry -> T+1+h close
    next_open = open_adj.groupby(p['ts_code']).shift(-1)
    next_open_dt = p['date'].groupby(p['ts_code']).shift(-1)
    for h in [20]:
        close_h = close.groupby(p['ts_code']).shift(-(1 + h))
        lab['exec_fwd_ret_20'] = close_h / next_open - 1.0
    # executable feasibility
    n1 = p.groupby('ts_code').shift(-1)
    lab['exec_entry_possible'] = n1['is_suspended'].eq(False) & ~(
        n1['is_limit_up'] & (n1['open'] >= n1['pre_close'] * 1.0999))
    lab['exec_exit_possible'] = True  # T+1+h 非停牌（未平仓样本按需再评估）
    # label_end_date (purge/embargo key)：信号日 + 最大 horizon(60) 交易日
    # 用未来第 60 个交易日的日期
    lab['label_end_date'] = p['date'].groupby(p['ts_code']).shift(-60)
    # 横截面 rank 标签（用当日合法股票）
    date = p['date']
    fwd20 = lab['fwd_ret_20']
    lab['fwd20_rank01'] = fwd20.groupby(date).rank(pct=True)
    q80 = fwd20.groupby(date).transform(lambda s: s.quantile(0.80))
    q20 = fwd20.groupby(date).transform(lambda s: s.quantile(0.20))
    lab['TOP20_FWD20'] = fwd20 >= q80
    lab['BOTTOM20_FWD20'] = fwd20 <= q20

    out = pd.concat([p[['date', 'ts_code']], lab], axis=1)
    out['year'] = out['date'].dt.year
    os.makedirs(OUT, exist_ok=True)
    for y, g in out.groupby('year'):
        yd = os.path.join(OUT, f'year={y}')
        os.makedirs(yd, exist_ok=True)
        g.drop(columns=['year']).to_parquet(os.path.join(yd, 'part.parquet'), index=False)
    return out


def split_purged(df, train_end, val_start=None, val_end=None, embargo_days=60):
    """purge/embargo：训练样本的 label 窗口不得跨越 OOS 起点。
    df 需含 signal_date(date) 与 label_end_date（未来第 embargo_days 交易日）。
    返回 (train, valid, test) 时间切片 DataFrame（标签在原表）。
    若仅需 train/test 两段，val 返回 None。
    """
    out = {}
    tr = df[df['date'] <= train_end].copy()
    if 'label_end_date' in tr.columns:
        tr = tr[tr['label_end_date'] <= train_end]  # 60d 标签不穿 OOS 起点
    out['train'] = tr
    if val_start is not None:
        va = df[(df['date'] >= val_start) & (df['date'] <= val_end)].copy()
        if 'label_end_date' in va.columns:
            va = va[va['label_end_date'] <= val_end]
        out['valid'] = va
        te = df[df['date'] > val_end].copy()
        out['test'] = te
    return out


if __name__ == '__main__':
    o = build()
    print('label rows:', len(o), 'cols:', o.shape[1])
