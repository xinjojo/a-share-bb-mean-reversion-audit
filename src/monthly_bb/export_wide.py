"""MONTHLY-BB-MR: 导出全量信号宽表（含名称/行业/市值，供人工检查）
输入: data/monthly_bb/monthly_signals.parquet + stock_basic_all.parquet
输出: results/evidence/monthly_bb/monthly_signal_wide.parquet / .csv（分片）
"""
import os
import glob
import hashlib
import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(BASE, '..', '..', 'data', 'monthly_bb'))
OUT = os.path.abspath(os.path.join(BASE, '..', '..', 'results', 'evidence', 'monthly_bb'))

def main():
    sig = pd.read_parquet(os.path.join(DATA_DIR, 'monthly_signals.parquet'))
    sb = pd.read_parquet(os.path.join(DATA_DIR, 'stock_basic_all.parquet'))
    sb = sb[['ts_code', 'name', 'industry', 'list_date']].drop_duplicates('ts_code')

    sig['pm'] = sig['pm'].astype(str)
    sig['signal_date'] = sig['month_end_date']
    sig['entry_date'] = sig['next_month_end_date']
    sig['episode_id'] = sig['ts_code'] + '_' + sig['pm']
    sig['entry_role'] = np.where(sig['NEW_EPISODE'] == 1, 'NEW_EPISODE', 'REPEAT_SIGNAL')
    sig['month_open'] = sig['open_adj']
    sig['month_high'] = sig['high_adj']
    sig['month_low'] = sig['low_adj']
    sig['month_close'] = sig['close_adj']
    sig['month_n_days'] = sig['n_days']
    sig['amount_sum'] = sig['amount']
    sig['list_date'] = pd.to_datetime(sig['list_date_ts'], errors='coerce')
    # 与 stock_basic 合并（只取 name/industry，避免 list_date 冲突）
    sig = sig.merge(sb[['ts_code', 'name', 'industry']], on='ts_code', how='left')

    # 上市时长（以 signal_date 为基准，月数）
    sig['listing_age_months'] = (pd.to_datetime(sig['month_end_date']) - sig['list_date']).dt.days / 30.44

    cols = ['ts_code', 'name', 'industry', 'list_date', 'universe_clean', 'signal_date',
            'pm', 'entry_role', 'episode_id', 'listing_age_months',
            'month_open', 'month_high', 'month_low', 'month_close', 'month_n_days',
            'bb_mid', 'bb_upper', 'bb_lower', 'bb_width', 'bb_z',
            'total_mv', 'mv_rank', 'amount_sum',
            'ret_ec_1m', 'ret_ec_3m', 'ret_ec_6m', 'ret_ec_12m',
            'mfe_1m', 'mfe_3m', 'mfe_6m', 'mfe_12m',
            'mae_1m', 'mae_3m', 'mae_6m', 'mae_12m',
            'idx_ret_1m', 'idx_ret_3m', 'idx_ret_6m', 'idx_ret_12m',
            'excess_cc_1m', 'excess_cc_3m', 'excess_cc_6m', 'excess_cc_12m',
            'censored_1m', 'censored_3m', 'censored_6m', 'censored_12m']
    keep = [c for c in cols if c in sig.columns]
    w = sig[keep].copy()
    w = w.sort_values(['signal_date', 'ts_code']).reset_index(drop=True)

    parquet_path = os.path.join(OUT, 'monthly_signal_wide.parquet')
    w.to_parquet(parquet_path, index=False)

    # CSV 分片（每片 ~200 万字符内）
    n = max(1, (w.shape[0] + 2999) // 3000)
    part_paths = []
    for i in range(n):
        chunk = w.iloc[i * 3000:(i + 1) * 3000]
        p = os.path.join(OUT, f'monthly_signal_wide_part_{i + 1:03d}.csv')
        chunk.to_csv(p, index=False)
        part_paths.append(p)

    # 校验 hash / 行数
    def sha(p):
        h = hashlib.sha256()
        with open(p, 'rb') as f:
            for b in iter(lambda: f.read(1 << 20), b''):
                h.update(b)
        return h.hexdigest()

    manifest = {
        'wide_parquet': {'path': parquet_path, 'sha256': sha(parquet_path),
                         'bytes': os.path.getsize(parquet_path), 'rows': len(w)},
        'csv_parts': [{'path': p, 'sha256': sha(p), 'bytes': os.path.getsize(p),
                       'rows': len(pd.read_csv(p, usecols=['signal_date']))} for p in part_paths],
    }
    import json
    with open(os.path.join(OUT, 'wide_manifest.json'), 'w') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f'wide rows: {len(w)}')
    print(f'parquet: {parquet_path}')
    for p in part_paths:
        print(f'  {p}')
    print('manifest -> wide_manifest.json')

if __name__ == '__main__':
    main()
