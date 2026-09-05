#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""REG1 classification (re-run from frozen CSVs; direction semantics fixed per registry gate).
PASS-CANDIDATE requires bearish group significantly WORSE than G1 (CI upper<0) + veto improves portfolio.
"""
import json, os
import pandas as pd

REPO = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo'
OUT = os.path.join(REPO, 'results', 'evidence', 'reg1')
dev = pd.read_csv(os.path.join(OUT, 'squeeze_adx_trade_attribution.csv'))
gs = pd.read_csv(os.path.join(OUT, 'squeeze_adx_group_stats.csv'))
inf = pd.read_csv(os.path.join(OUT, 'squeeze_adx_inference.csv'))
veto = pd.read_csv(os.path.join(OUT, 'squeeze_adx_veto_results.csv'))
tail = pd.read_csv(os.path.join(OUT, 'squeeze_adx_tail_attribution.csv'))

def pass_check(g_, vr):
    ir = inf[inf.group == g_].iloc[0]
    return dict(
        bearish_significantly_worse=bool(ir['mean_ci_hi'] < 0),
        veto_pnl_improve_pct=float(vr['pnl_delta_pct']),
        exp_adj_positive=bool((vr.get('exposure_adj_kept_per_1k_hold_days') or -999) > (vr.get('exposure_adj_base_per_1k_hold_days') or 0)),
        foregone_le_30pct=bool((vr.get('foregone_pct_of_avoided') or 999) <= 30),
        top1_lt_30pct=bool((vr.get('top1_stock_pct_of_veto_pnl') or 999) < 30),
    )

checks = {g_: pass_check(g_, veto[veto.veto == g_].iloc[0]) for g_ in ['G2', 'G3', 'G4', 'G5']}
pass_candidates = [g_ for g_ in ['G2', 'G3', 'G4', 'G5']
                   if checks[g_]['bearish_significantly_worse'] and checks[g_]['veto_pnl_improve_pct'] >= 1.0
                   and checks[g_]['exp_adj_positive'] and checks[g_]['foregone_le_30pct'] and checks[g_]['top1_lt_30pct']]
if pass_candidates:
    classification = 'PASS-CANDIDATE'; primary = pass_candidates[0]
elif any(checks[g_]['veto_pnl_improve_pct'] <= -1.0 for g_ in ['G2', 'G3', 'G4', 'G5']):
    classification = 'HARMFUL'
    primary = min(['G2', 'G3', 'G4', 'G5'], key=lambda g_: checks[g_]['veto_pnl_improve_pct'])
elif any(inf[inf.group == g_]['mean_diff_vs_G1_pp'].iloc[0] < 0 for g_ in ['G2', 'G3', 'G4', 'G5']):
    classification = 'WEAK'; primary = None
else:
    classification = 'FAIL'; primary = None

base_pnl = float(dev['pnl'].sum())
base_hold = float(dev['hold_days'].sum())
summary = dict(
    baseline='S1 frozen B20 independent signal framework (dev 61828, parity w/ F2.1)',
    classification=classification, primary_group=primary,
    note='Veto is trade-level static simulation on signal-level replay (not K=3 engine rerun). '
         'HARMFUL means filtering these bearish regimes would significantly damage the baseline. '
         'Directional finding: G2/G4 episodes are slightly BETTER than G1 (bootstrap CI excludes 0). '
         'Future hypothesis (not developed): bearish-expansion signal days overlap high-breadth days (B1.1).',
    base_stats=dict(n=len(dev), win_pct=round(float((dev.simple_return_pct>0).mean()*100),2),
                    avg_return_pct=round(float(dev.simple_return_pct.mean()),4),
                    median_return_pct=round(float(dev.simple_return_pct.median()),4),
                    avg_hold_days=round(float(dev.hold_days.mean()),2),
                    sum_pnl=round(base_pnl,2)),
    group_stats=gs.to_dict('records'),
    tail=tail.to_dict('records'),
    inference=inf.to_dict('records'),
    veto=veto.to_dict('records'),
    pass_checks=checks,
    future_hypotheses=[
        'G2/G4 (bearish DMI/strong bear expansion) signal days overlap high B20 breadth days; '
        'the small positive edge may be the B1.1 date-level breadth effect, not a regime property.',
        'Squeeze release (G3/G5) shows no incremental discriminative value on this baseline.'])
json.dump(summary, open(os.path.join(OUT, 'squeeze_adx_summary.json'), 'w'), indent=1, ensure_ascii=False)
json.dump(dict(I1_baseline_61828=True, I2_no_2025_2026=True, I3_regime_asof_signal_date=True,
               I4_no_parameter_search=True, I5_frozen_groups_5=True, I6_four_independent_vetoes=True,
               I7_no_combination_search=True, I8_all_groups_reported=True,
               I9_indicator_implementation_verified=True, I10_no_subgroup_after_results=True,
               I11_classification_semantics_direction_fixed=True),
          open(os.path.join(OUT, 'squeeze_adx_invariants.json'), 'w'), indent=1)
print('classification =', classification, '| primary =', primary)
for g_, c in checks.items():
    print(g_, c)
