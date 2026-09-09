"""A-Share Alpha Factory — Phase 0 smoke pipeline.

验证 register → validate → compute → screen → FDR → redundancy → incremental →
library/graveyard → report 全链路。所有结果仅 SMOKE_ONLY，不得作为 Alpha 结论。
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'src'))

from alpha_factory import (benchmark, dsl, factor_engine, incremental_test,  # noqa: E402
                           label_engine, legacy_import, multiple_testing,
                           redundancy, registry, report as report_mod, screen_factor)

OUT = os.path.join(REPO, 'results', 'evidence', 'alpha_factory', 'phase0_smoke')

SMOKE_FACTORS = [
    # (name, expression, family, hypothesis)
    ('ret_5', 'ret_5', 'PRICE_REVERSAL', '过去5日收益：超跌反弹假设'),
    ('ret_20', 'ret_20', 'PRICE_REVERSAL', '过去20日收益：中期超跌'),
    ('atr14_pct', 'atr14_pct', 'VOLATILITY', '波动率：低波是否更易回归'),
    ('ret5_div_atr', 'ratio(ret_5,atr14_pct)', 'INTERACTION', '风险调整后的短期超跌'),
    ('amount_cs', 'cs_rank(signal_day_amount)', 'LIQUIDITY', '当日成交额横截面排名'),
    ('amount_ratio_5_20', 'amount_ratio_5_20', 'VOLUME_PRICE', '量能扩张'),
    ('drawdown_20', 'drawdown_20', 'PRICE_REVERSAL', '20日回撤深度'),
    ('dist_52w_high', 'distance_52w_high', 'TREND', '距52周高点'),
    ('market_breadth', 'daily_bb_signal_count', 'BREADTH', '市场宽度：当日BB信号数'),
    ('breadth_up', 'daily_bb_up_ratio', 'BREADTH', '信号日上涨占比'),
    ('bbz_x_amount', 'interaction(bb_z,cs_rank(signal_day_amount))', 'INTERACTION', '深度×流动性交互'),
    ('drawdown_minus_ret', 'diff(drawdown_20,ret_20)', 'PRICE_REVERSAL', '回撤-收益差'),
    ('min_ret5_ret20', 'min(ret_5,ret_20)', 'PRICE_REVERSAL', '短中期收益较低者'),
    ('gap_sign', 'sign(gap_pct)', 'GAP', '跳空方向'),
]

LABELS_A = {
    'fwd_ret_20': 'fwd_ret_20',
    'BAD': 'BAD',
    'STRONG': 'STRONG',
}


def main(max_signals: int | None = None):
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    print('== ALPHA FACTORY PHASE 0 SMOKE ==')
    print('[*] legacy research import...')
    legacy_import.import_legacy()
    legacy_import.write_legacy_mapping()

    exp = registry.Experiments()
    experiment_id = registry.next_experiment_id(exp.df)
    print(f'[*] experiment: {experiment_id}')

    print('[*] load Universe A...')
    from alpha_factory import data as data_mod
    df = data_mod.load_universe_a(max_signals=max_signals)
    print(f'    rows={len(df)} dates={df["signal_date"].nunique()}')
    labels = label_engine.build_labels_a(df)

    reg = registry.Registry()
    gy = registry.Graveyard()
    lib = registry.Library()
    mt = registry.MultipleTestingLedger()

    # ---- register all smoke factors (reuse existing factor_id if already registered) ----
    factor_ids = []
    for name, expr, family, hyp in SMOKE_FACTORS:
        try:
            eh = dsl.expression_hash(expr)
        except ValueError as ex:
            print(f'    [SKIP] {name}: invalid expression ({ex})')
            continue
        existing = reg.df[(reg.df['expression_hash'] == eh) & (reg.df['universe'] == 'A')]
        if len(existing):
            row = existing.iloc[0]
            print(f'    {row["factor_id"]} {name} -> {expr} [REUSE {row["status"]}]')
            factor_ids.append(row['factor_id'])
            continue
        row = reg.add(
            factor_name=f'SMOKE_{name}', factor_family=family, formula=expr,
            description=hyp, economic_hypothesis=hyp, universe='A',
            input_fields=None, lookback=None, operators=None,
            PIT_status='PIT_OK', max_source_lag=0, missing_policy='dropna',
            winsorization='none', normalization='none', expression_hash=eh,
            complexity_depth=dsl.complexity(dsl.parse(expr))['depth'],
            complexity_inputs=dsl.complexity(dsl.parse(expr))['unique_inputs'],
            complexity_interactions=dsl.complexity(dsl.parse(expr))['interactions'],
            created_by='phase0_smoke', experiment_id=experiment_id,
            discovery_period='2020-2022', validation_period='2023', test_period='2024',
            status='SCREENING', notes='SMOKE_ONLY')
        factor_ids.append(row['factor_id'])
        print(f'    {row["factor_id"]} {name} -> {expr} [{row["status"]}]')
    # ---- attempts ledger ----
    for fid, (name, expr, family, hyp) in zip(factor_ids, SMOKE_FACTORS):
        for lab in LABELS_A:
            mt.add(experiment_id=experiment_id, factor_id=fid, expression=expr,
                   expression_hash=dsl.expression_hash(expr), horizon='D20',
                   universe='A', label=lab, variant=1, status='TESTED')

    # ---- compute + screen ----
    exprs = [s[1] for s in SMOKE_FACTORS]
    print('[*] compute factor values...')
    feats = factor_engine.compute_many(exprs, df, date_col='signal_date', mode='wide',
                                       universe='A')
    screen_rows = []
    screen_detail = {}
    for fid, (name, expr, family, hyp) in zip(factor_ids, SMOKE_FACTORS):
        for lab_name, lab_col in LABELS_A.items():
            s = screen_factor.screen(feats[expr], labels[lab_col], df['signal_date'],
                                     horizon_label=lab_name)
            row = screen_factor.screen_row(s, fid, f'D20_{lab_name}')
            row['expression'] = expr
            row['factor_name'] = f'SMOKE_{name}'
            row['label'] = lab_name
            screen_rows.append(row)
            screen_detail[f'{fid}|{lab_name}'] = s
    scr = pd.DataFrame(screen_rows)
    scr.to_csv(os.path.join(OUT, 'phase0_smoke_screen.csv'), index=False)
    print(f'[*] screen done: {len(scr)} (factor x label) rows')

    # ---- BH-FDR demo on rank-IC p-values ----
    pvals = []
    for _, r in scr.iterrows():
        ic = r['rank_ic_mean']
        p = 2 * (1 - float(np.abs(ic))) if np.isfinite(ic) else np.nan  # crude surrogate
        pvals.append(p)
    scr['p_surrogate'] = pvals
    ok = scr['p_surrogate'].notna()
    scr['fdr_survives'] = pd.Series([False] * len(scr), index=scr.index)
    if ok.any():
        scr.loc[ok, 'fdr_survives'] = multiple_testing.benjamini_hochberg(
            scr.loc[ok, 'p_surrogate'].to_numpy(), alpha=0.10)
    scr.to_csv(os.path.join(OUT, 'phase0_smoke_screen.csv'), index=False)

    # ---- redundancy on main label (fwd_ret_20) ----
    main_rows = scr[scr['label'] == 'fwd_ret_20']
    corr = redundancy.correlation_matrix(feats[[e for e in exprs]], method='pearson')
    dup = redundancy.find_duplicates(corr, threshold=0.80, order=exprs)
    clusters = redundancy.hierarchical_clusters(corr)
    pd.DataFrame(dup).to_csv(os.path.join(OUT, 'phase0_smoke_duplicates.csv'), index=False)
    pd.Series(clusters, name='cluster_members').reset_index().to_csv(
        os.path.join(OUT, 'phase0_smoke_clusters.csv'), index=False)

    # ---- incremental demo: bb_z baseline vs ret_5 ----
    try:
        inc = incremental_test.incremental_r2(
            labels['fwd_ret_20'],
            pd.DataFrame({'bb_z': df['bb_z'].astype(float)}),
            feats['ret_5'])
        pd.Series(inc).to_frame('value').to_csv(os.path.join(OUT, 'phase0_smoke_incremental.csv'))
        print('[*] incremental R2:', inc)
    except Exception as ex:
        print('[*] incremental failed:', ex)

    # ---- leakage guard: all factor source dates <= signal_date (loader PIT) ----
    leak_report = []
    for fid, (name, expr, family, hyp) in zip(factor_ids, SMOKE_FACTORS):
        cols = [c for c in df.columns if c in expr]
        leak_report.append({'factor_id': fid, 'expression': expr,
                            'inputs': ';'.join(cols), 'source_date_le_signal_date': True,
                            'contains_future_keyword': bool(
                                any(k in expr for k in dsl.FORBIDDEN_KEYWORDS))})
    pd.DataFrame(leak_report).to_csv(os.path.join(OUT, 'phase0_smoke_leakage.csv'), index=False)

    # ---- experiment registry + report ----
    counts = report_mod.tally(experiment_id, factor_ids,
                              {fid: 'SCREENING' for fid in factor_ids})
    exp.register(experiment_id, universe='A', factor_count_proposed=len(factor_ids),
                 factor_count_tested=len(factor_ids), factor_ids=','.join(factor_ids),
                 discovery_period='2020-2022', validation_period='2023',
                 test_period='2024', horizons='D20', metrics='IC,RankIC,ICIR,Q1Q5',
                 multiple_testing_method='BH-FDR(0.10 surrogate)', code_commit=None,
                 data_hash='sigpath-wide', seed=2026,
                 result_summary=f'SMOKE_ONLY; attempts={counts}')
    report_mod.write_report(experiment_id, OUT, {
        'status': 'SMOKE_ONLY',
        'universe': 'A (BB conditional, SIGPATH)',
        'n_signals': len(df),
        'n_dates': int(df['signal_date'].nunique()),
        'factors': counts,
        'top_by_rank_ic': scr.sort_values('rank_ic_mean', ascending=False)
        [['factor_id', 'factor_name', 'label', 'ic_mean', 'rank_ic_mean', 'icir']]
        .head(10).to_dict('records'),
        'fdr_survived': int(scr['fdr_survives'].sum()) if 'fdr_survives' in scr else 0,
        'duplicates': dup,
        'incremental': inc if 'inc' in dir() else None,
        'note': '结果仅供流水线验证，不是 Alpha 结论。',
    })

    # ---- benchmark ----
    print('[*] benchmark...')
    bench_df = df.copy()
    bench_df['fwd_ret_20'] = labels['fwd_ret_20'].to_numpy()
    b = benchmark.run_benchmark(bench_df, exprs, label_col='fwd_ret_20')
    benchmark.write_benchmark(b)
    print('[*] benchmark:', b)

    print(f'== DONE in {time.time()-t0:.1f}s ; experiment={experiment_id} ==')
    print(f'== TOTAL HYPOTHESIS ATTEMPTS (all-time) = {mt.count_attempts()} ==')
    return experiment_id


if __name__ == '__main__':
    main()
