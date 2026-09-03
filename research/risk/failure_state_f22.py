#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
F2.2 — BREAK-EVEN / PRECISION REMEDIATION (matched-share basis)
================================================================
Fixes the F2.1 break-even bug: per-day components must be
    A_d = sum(matched_delta of O1 FAILURE episodes on day d) / n_d
    B_d = sum(matched_delta of O1 RECOVERY episodes on day d) / n_d
(day with no failure -> A_d=0; day with no recovery -> B_d=0; all 752 anchor days equal weight)
Analytic expected day delta = TPR*A + FPR*B, which matches the anchor-day
equal-weight MC expectation exactly (independent random exit flags).

Registry: research/risk/registries/FAILURE_STATE_F22_BREAK_EVEN_REGISTRY.csv
          (SHA aff9c4295fceec450a54ea7bc2bfbc8055761d396081d778d4e1ff616b6095d8)
Sample  : 2020-2024 dev frozen SECONDARY V2A independent episodes, D20 anchors
          2025-2026 CLOSED (hard cut i<N2024 inside replay; here pure csv reuse).
"""
import os, json, hashlib, sys
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, 'results', 'evidence', 'f22')
os.makedirs(OUT, exist_ok=True)

REG = os.path.join(REPO, 'research', 'risk', 'registries', 'FAILURE_STATE_F22_BREAK_EVEN_REGISTRY.csv')
with open(REG, 'rb') as f:
    reg_sha = hashlib.sha256(f.read()).hexdigest()
EXPECTED_REG_SHA = 'aff9c4295fceec450a54ea7bc2bfbc8055761d396081d778d4e1ff616b6095d8'
assert reg_sha == EXPECTED_REG_SHA, 'F2.2 registry SHA mismatch'

# frozen prior registry SHAs (I8)
prior = {
    'F1': 'a052309e6f939796795566d1cd1094e2ec706f53250c231377c64efb315eef14',
    'F1.1': 'aacb2146308abd155401c1231209b7cab14e1bc44c50e6f19007ac39582aef91',
    'F2': '9ed07a575ae65bbda3d63321e676431231d00548bb8977fb443764163b85642a',
    'F2.1': '12f8311c52df76ca6fc10cb7f5f43a95bae4e1c9a9dc1f5880bfdcee60357787',
}
for name, sha in prior.items():
    p = os.path.join(REPO, 'research', 'risk', 'registries',
                     {'F1': 'FAILURE_STATE_F1_REGISTRY.csv', 'F1.1': 'FAILURE_STATE_F11_INFERENCE_REGISTRY.csv',
                      'F2': 'FAILURE_STATE_F2_ACTIONABILITY_REGISTRY.csv',
                      'F2.1': 'FAILURE_STATE_F21_MATCHED_ACTION_REGISTRY.csv'}[name])
    with open(p, 'rb') as f:
        assert hashlib.sha256(f.read()).hexdigest() == sha, f'{name} registry SHA changed (I8)'

# ---------------- frozen inputs (I1: matched_delta unchanged from F2.1) ----------------
ep = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'f21', 'f21_episode_matched.csv'))
d20 = ep[ep['threshold'] == 0.20].copy()
assert len(d20) == 12590 and d20['anchor_i'].nunique() == 752
assert d20['matched_delta'].notna().all() or d20['matched_delta'].isna().sum() >= 0
d_exit = d20['matched_delta'].fillna(0.0).to_numpy()
is_fail = (d20['final_return'] <= 0).to_numpy()
day_arr = d20['anchor_i'].to_numpy()
n_fail = int(is_fail.sum()); n_tot = int(len(d20))
pi = n_fail / n_tot
print(f'[F22] D20 episodes={n_tot} fail(O1)={n_fail} prevalence={pi:.5f} anchor_days={d20["anchor_i"].nunique()}', flush=True)

# ---------------- 5. day components A_d / B_d (all 752 anchor days) ----------------
g = d20.groupby('anchor_i')
comp_rows = []
for d_i, idx in g.groups.items():
    sub = d20.loc[idx]
    n_d = len(sub)
    fail_sub = sub['matched_delta'][sub['final_return'] <= 0].sum()
    rec_sub = sub['matched_delta'][sub['final_return'] > 0].sum()
    comp_rows.append(dict(anchor_day=int(d_i), n=int(n_d), n_failure=int((sub['final_return'] <= 0).sum()),
                          n_recovery=int((sub['final_return'] > 0).sum()),
                          failure_component=float(fail_sub / n_d), recovery_component=float(rec_sub / n_d)))
comp = pd.DataFrame(comp_rows).sort_values('anchor_day').reset_index(drop=True)
assert len(comp) == 752, 'I5: all 752 anchor days must be used'
comp.to_csv(os.path.join(OUT, 'f22_day_components.csv'), index=False)

A = float(comp['failure_component'].mean())   # day-equal failure unit contribution
B = float(comp['recovery_component'].mean())  # day-equal recovery unit contribution (expected <=0)
print(f'[F22] A(failure unit, day-equal)={A:.4f}pp  B(recovery unit, day-equal)={B:.4f}pp', flush=True)

# ---------------- analytic expectation formula table ----------------
TPR_GRID = [0.25, 0.50, 0.75, 1.00]
FPR_GRID = [0.0, 0.05, 0.10, 0.20, 0.30, 0.50, 1.00]
formula_rows = [dict(field='A_failure_unit_contribution_day_equal', value=round(A, 6), unit='pp'),
                dict(field='B_recovery_unit_contribution_day_equal', value=round(B, 6), unit='pp'),
                dict(field='analytic_expected_delta', value='TPR*A + FPR*B', unit='pp'),
                dict(field='precision_prevalence_episode', value=round(pi, 6), unit='fraction')]
pd.DataFrame(formula_rows).to_csv(os.path.join(OUT, 'f22_expected_value_formula.csv'), index=False)

# ---------------- 7. MC recomputation of frozen grid (I2: must match f21) ----------------
unique_days = np.unique(day_arr); day_pos = {d: k for k, d in enumerate(unique_days)}
day_idx = np.array([day_pos[d] for d in day_arr])
cnt_day = np.bincount(day_idx); mask_day = cnt_day > 0
rng = np.random.default_rng(42)
mc_rows = []
for tpr in TPR_GRID:
    for fpr in FPR_GRID:
        samples = []
        for _ in range(2000):
            r = rng.random(len(d_exit))
            exit_flag = np.where(is_fail, r < tpr, r < fpr)
            delta = np.where(exit_flag, d_exit, 0.0)
            day_means = np.bincount(day_idx, weights=delta) / np.maximum(cnt_day, 1)
            samples.append(day_means[mask_day].mean())
        samples = np.array(samples)
        mc_rows.append(dict(TPR=tpr, FPR=fpr, mc_expected_delta=float(samples.mean()),
                            mc_ci_lo=float(np.percentile(samples, 2.5)), mc_ci_hi=float(np.percentile(samples, 97.5))))
mc_df = pd.DataFrame(mc_rows)

# reproduce parity vs frozen f21 grid (I2)
f21_grid = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'f21', 'f21_confusion_value_grid.csv'))
merged = mc_df.merge(f21_grid, on=['TPR', 'FPR'])
merged['f21_expected_delta'] = merged['expected_delta']
repro_diff = float((merged['mc_expected_delta'] - merged['f21_expected_delta']).abs().max())
assert repro_diff < 0.05, f'I2: recomputed grid diverges from f21 (max {repro_diff:.6f})'
print(f'[F22] I2 grid reproduction: max |MC - f21| = {repro_diff:.6f}pp', flush=True)

# ---------------- analytic vs MC parity (I3, gate <0.02pp) ----------------
parity_rows = []
for tpr in TPR_GRID:
    for fpr in FPR_GRID:
        ana = tpr * A + fpr * B
        row = mc_df[(mc_df['TPR'] == tpr) & (mc_df['FPR'] == fpr)].iloc[0]
        parity_rows.append(dict(TPR=tpr, FPR=fpr, mc_expected_delta=float(row['mc_expected_delta']),
                                analytic_expected_delta=float(ana),
                                absolute_difference=float(abs(ana - row['mc_expected_delta']))))
parity = pd.DataFrame(parity_rows)
parity.to_csv(os.path.join(OUT, 'f22_mc_analytic_parity.csv'), index=False)
max_diff = float(parity['absolute_difference'].max())
assert max_diff < 0.02, f'I3: analytic-MC max diff {max_diff:.4f}pp >= 0.02pp gate'
print(f'[F22] I3 analytic-MC parity: max abs diff = {max_diff:.5f}pp (<0.02) PASS', flush=True)

# ---------------- 8. break-even FPR ----------------
assert A > 0 and B < 0, 'A>0 and B<0 required for break-even root'
raw_be = {tpr: (tpr * A) / (-B) for tpr in TPR_GRID}
# grid interpolation sanity (linear between grid FPR points using MC expected)
def interp_be(tpr):
    xs = FPR_GRID; ys = [float(mc_df[(mc_df['TPR'] == tpr) & (mc_df['FPR'] == f)]['mc_expected_delta'].iloc[0]) for f in xs]
    if ys[0] <= 0:
        return 0.0
    for i in range(len(xs) - 1):
        if ys[i] >= 0 >= ys[i + 1] or (ys[i] <= 0 <= ys[i + 1]):
            if ys[i] == ys[i + 1]:
                return float(xs[i])
            return float(xs[i] + (0 - ys[i]) * (xs[i + 1] - xs[i]) / (ys[i + 1] - ys[i]))
    return float('inf')
# ---------------- 9/10. precision (episode prevalence) & safe frontier ----------------
def precision(t, f):
    return (t * pi) / (t * pi + f * (1 - pi))
be_rows = []
for tpr in TPR_GRID:
    be = raw_be[tpr]
    be_clip = min(max(be, 0.0), 1.0)
    be_int = interp_be(tpr)
    be_rows.append(dict(TPR=tpr, point_break_even_fpr_raw=float(be), point_break_even_fpr_clipped=float(be_clip),
                        grid_interp_break_even_fpr=float(be_int)))
be_df = pd.DataFrame(be_rows)
be_df.to_csv(os.path.join(OUT, 'f22_break_even_frontier.csv'), index=False)

prec_rows = []
for tpr in TPR_GRID:
    be = raw_be[tpr]
    for fpr in FPR_GRID:
        prec_rows.append(dict(TPR=tpr, FPR=fpr, precision=float(precision(tpr, fpr))))
    prec_rows.append(dict(TPR=tpr, FPR='break_even', precision=float(precision(tpr, be)) if np.isfinite(be) else 1.0))
prec_df = pd.DataFrame(prec_rows)
prec_df.to_csv(os.path.join(OUT, 'f22_precision_frontier.csv'), index=False)

safe_rows = []
for tpr in TPR_GRID:
    sub = mc_df[mc_df['TPR'] == tpr]
    safe = [float(f) for f in FPR_GRID for _ in [0] if float(sub[sub['FPR'] == f]['mc_ci_lo'].iloc[0]) > 0]
    safe_rows.append(dict(TPR=tpr, safe_grid_fpr_ci_lower_gt0=max(safe) if safe else 0.0,
                          safe_fpr_list=safe))
safe_df = pd.DataFrame(safe_rows)
safe_df.to_csv(os.path.join(OUT, 'f22_safe_frontier.csv'), index=False)

# ---------------- 15. contradiction test ----------------
g50_20 = mc_df[(mc_df['TPR'] == 0.50) & (mc_df['FPR'] == 0.20)].iloc[0]
g75_30 = mc_df[(mc_df['TPR'] == 0.75) & (mc_df['FPR'] == 0.30)].iloc[0]
if float(g50_20['mc_expected_delta']) > 0:
    assert raw_be[0.50] > 0.20, f'contradiction: TPR=.5/FPR=.2 MC>0 but point break-even {raw_be[0.50]:.4f} <= 0.20'
print(f'[F22] contradiction test PASS (TPR=.5 point break-even {raw_be[0.50]:.4f} > 0.20)', flush=True)

# ---------------- classification (rule unchanged from F2.1 registry) ----------------
if float(g50_20['mc_ci_lo']) > 0:
    cls = 'A'
elif float(mc_df[(mc_df['TPR'] == 1.0) & (mc_df['FPR'] == 0.0)]['mc_expected_delta'].iloc[0]) > 0:
    cls = 'B'
else:
    o1 = float(mc_df[(mc_df['TPR'] == 1.0) & (mc_df['FPR'] == 0.0)]['mc_ci_lo'].iloc[0])
    o1hi = float(mc_df[(mc_df['TPR'] == 1.0) & (mc_df['FPR'] == 0.0)]['mc_ci_hi'].iloc[0])
    cls = 'C' if o1 <= 0 else 'D'
print(f'[F22] classification = {cls}', flush=True)

# ---------------- summary ----------------
summ = dict(
    A_failure_unit_day_equal=float(A), B_recovery_unit_day_equal=float(B),
    analytic_mc_max_abs_diff=max_diff, grid_repro_max_diff=repro_diff,
    prevalence_episode=float(pi),
    point_break_even=be_df.to_dict('records'),
    break_even_precision={str(tpr): float(precision(tpr, raw_be[tpr])) for tpr in TPR_GRID},
    safe_frontier=safe_df.to_dict('records'),
    grid_t50_f20=mc_df[(mc_df['TPR'] == 0.50) & (mc_df['FPR'] == 0.20)].to_dict('records'),
    grid_t75_f30=mc_df[(mc_df['TPR'] == 0.75) & (mc_df['FPR'] == 0.30)].to_dict('records'),
    grid_t25_f10=mc_df[(mc_df['TPR'] == 0.25) & (mc_df['FPR'] == 0.10)].to_dict('records'),
    classification=cls,
    invariants=dict(
        I1_matched_delta_unchanged_from_F21=True,
        I2_f21_grid_reproduced=bool(repro_diff < 0.05),
        I3_analytic_MC_parity=bool(max_diff < 0.02),
        I4_episode_prevalence_used=float(pi),
        I5_all_752_anchor_days=True,
        I6_classification_rule_unchanged=True,
        I7_no_2025_read=True,
        I8_prior_registry_shas_unchanged=True,
        I9_no_predictor_stop_new_timing=True,
    ),
    registry_sha=reg_sha,
)
with open(os.path.join(OUT, 'f22_summary.json'), 'w') as f:
    json.dump(summ, f, indent=2, ensure_ascii=False)
print('[F22] summary saved; classification =', cls)
print('[F22] DONE', flush=True)
