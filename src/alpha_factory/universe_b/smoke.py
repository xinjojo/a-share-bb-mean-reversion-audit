"""Universe B — SMOKE-ONLY ML pipeline check (Phase 0).
目标仅验证：数百万行 dataset -> loader -> purged split -> LightGBM 管道跑通。
禁止把本脚本任何输出作为研究结论（不报告 IC/收益/Alpha）。
训练：2020-2022 → 预测 2023 前 20000 行子集。
"""
import os
import time
import numpy as np
import pandas as pd

REPO = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo'
UB = os.path.join(REPO, 'results/evidence/alpha_factory/universe_b')
FEAT_DIR = os.path.join(UB, 'features')
LAB_DIR = os.path.join(UB, 'labels')

STATE_FEATS = ['is_st_pit', 'is_suspended', 'is_limit_up', 'is_limit_down', 'listing_days']


def read_partition(root, years):
    files = []
    for r, _, fs in os.walk(root):
        for f in fs:
            if f.endswith('.parquet') and any(f'year={y}' in r for y in years):
                files.append(os.path.join(r, f))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def run(limit_val=20000):
    t0 = time.time()
    fx = read_partition(FEAT_DIR, [2020, 2021, 2022, 2023])
    ly = read_partition(LAB_DIR, [2020, 2021, 2022, 2023])
    data = fx.merge(ly[['date', 'ts_code', 'fwd20_rank01', 'label_end_date']],
                    on=['date', 'ts_code'], how='inner')
    data = data[data['is_suspended'] == False]
    # drop fully-null columns
    data = data.dropna(axis=1, how='all')
    feat_cols = [c for c in data.columns
                 if c not in ('date', 'ts_code', 'fwd20_rank01', 'label_end_date')]
    data = data.dropna(subset=['fwd20_rank01'])

    tr = data[(data['date'] <= '2022-12-31') & (data['label_end_date'] <= '2022-12-31')]
    va = data[(data['date'] >= '2023-01-01') & (data['date'] <= '2023-12-31')].head(limit_val)

    import lightgbm as lgb
    t1 = time.time()
    model = lgb.LGBMRegressor(n_estimators=50, max_depth=4, learning_rate=0.1,
                              random_state=42, verbose=-1)
    model.fit(tr[feat_cols], tr['fwd20_rank01'])
    t2 = time.time()
    pred = model.predict(va[feat_cols])

    md = ['# UNIVERSE B — SMOKE ML PIPELINE (Phase 0, SMOKE_ONLY)', '',
          '**本页所有数字仅证明管道可运行，不代表任何研究结论。**', '',
          f'- train rows: {len(tr)}（2020-2022，purged label_end<=2022-12-31）',
          f'- validation subset rows: {len(va)}（2023 前 {limit_val} 行）',
          f'- features used: {len(feat_cols)}',
          f'- fit time: {round(t2 - t1, 2)}s；total: {round(t2 - t0, 2)}s',
          f'- prediction shape: {pred.shape}; NaN in pred: {int(pd.isna(pred).sum())}', '',
          '结论：SMOKE PASS（管道通）。禁止据此评估模型质量。']
    with open(os.path.join(UB, 'SMOKE_ML.md'), 'w') as f:
        f.write('\n'.join(md))
    print('smoke ok, train', len(tr), 'val', len(va), 'feats', len(feat_cols))
    return model


if __name__ == '__main__':
    run()
