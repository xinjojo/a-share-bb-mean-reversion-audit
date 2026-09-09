"""A-Share Alpha Factory — resource benchmark (Phase 0).

实测少量因子在 Universe A（SIGPATH）上的耗时/内存，外推 100/1000 因子的合理吞吐量。
不做正式大规模挖掘。
"""
from __future__ import annotations

import os
import time

import numpy as np
import pandas as pd

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                   'results', 'evidence', 'alpha_factory')


def run_benchmark(df: pd.DataFrame, factor_exprs: list[str], label_col: str = 'close_ret_D20',
                  date_col: str = 'signal_date') -> dict:
    from alpha_factory import factor_engine, screen_factor
    t0 = time.time()
    feat = factor_engine.compute_many(factor_exprs, df, date_col=date_col, mode='wide')
    t_compute = time.time() - t0
    t0 = time.time()
    n_dates = df[date_col].nunique()
    n_rows = len(df)
    results = {}
    for e in factor_exprs:
        s = screen_factor.screen(feat[e], df[label_col], df[date_col],
                                 horizon_label=label_col)
        results[e] = screen_factor.screen_row(s, e, label_col).to_dict()
    t_screen = time.time() - t0
    per_factor = (t_compute + t_screen) / max(len(factor_exprs), 1)
    mem_est_rows = n_rows
    return {
        'rows': n_rows, 'dates': n_dates, 'factors_measured': len(factor_exprs),
        'sec_compute': round(t_compute, 3), 'sec_screen': round(t_screen, 3),
        'sec_per_factor': round(per_factor, 4),
        'est_100_factors_min': round(per_factor * 100 / 60, 2),
        'est_1000_factors_min': round(per_factor * 1000 / 60, 2),
        'est_ram_100_factors_mb': round(mem_est_rows * 8 * 100 / 1e6, 1),
        'est_ram_1000_factors_mb': round(mem_est_rows * 8 * 1000 / 1e6, 1),
        'note': '外推假设：同数据集、单进程、向量化实现；未来可并行/多进程线性扩展',
    }


def write_benchmark(res: dict) -> str:
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, 'phase0_benchmark.csv')
    pd.Series(res).to_frame('value').to_csv(path)
    return path
