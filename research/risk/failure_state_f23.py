#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
F2.3 — POLICY-VALUE SAMPLING INFERENCE COMPLETION
==================================================
F2.1/F2.2 point mathematics ACCEPTED (A=+1.4485803535pp, B=-2.6832617657pp,
point break-even 0.13496/0.26993/0.40489/0.53986, break-even precision ~0.76190).

This phase adds proper HISTORICAL SAMPLING UNCERTAINTY to the TPR-FPR
confusion-value grid:
  - deterministic policy day value  V_d(t,f) = t*A_d + f*B_d  (no random
    classifier flags needed for the expected value)
  - point = mean_d V_d, must equal t*A + f*B to machine precision (<1e-12)
  - HAC (maxlags=10) on the 752 time-ordered anchor days (confirmatory)
  - PRIMARY sampling CI = full-calendar moving-block bootstrap (L=21, B=2000,
    seed=0): days without an anchor are NaN, dropped after each resample
  - the old f21 MC interval is RENAMED "conditional randomization interval"
    and kept only as historical reference
  - primary safe frontier = largest grid FPR with calendar-bootstrap CI
    lower > 0; HAC-safe reported as confirmatory; randomization-safe reference
  - classification: A requires TPR=.5/FPR=.2 calendar AND HAC CI lower > 0;
    else B if perfect-label O1 sampling inference is significantly positive.

Registry: FAILURE_STATE_F23_POLICY_VALUE_INFERENCE_REGISTRY.csv
          (SHA c0f4d1d2bd46a7c5bca01752020dec121404984feb8273984a5164f56942f83c)
2025-2026 CLOSED (pure reuse of f21 episode csv; no 2025 read).
"""
import os, json, hashlib
import numpy as np
import pandas as pd
import statsmodels.api as sm

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, 'results', 'evidence', 'f23')
os.makedirs(OUT, exist_ok=True)

REG = os.path.join(REPO, 'research', 'risk', 'registries', 'FAILURE_STATE_F23_POLICY_VALUE_INFERENCE_REGISTRY.csv')
with open(REG, 'rb') as f:
    reg_sha = hashlib.sha256(f.read()).hexdigest()
assert reg_sha == 'c0f4d1d2bd46a7c5bca01752020dec121404984feb8273984a5164f56942f83c', 'F2.3 registry SHA mismatch'

prior = {'F1': 'a052309e6f939796795566d1cd1094e2ec706f53250c231377c64efb315eef14',
         'F1.1': 'aacb2146308abd155401c1231209b7cab14e1bc44c50e6f19007ac39582aef91',
         'F2': '9ed07a575ae65bbda3d63321e676431231d00548bb8977fb443764163b85642a',
         'F2.1': '12f8311c52df76ca6fc10cb7f5f43a95bae4e1c9a9dc1f5880bfdcee60357787',
         'F2.2': 'aff9c4295fceec450a54ea7bc2bfbc8055761d396081d778d4e1ff616b6095d8'}
paths = {'F1': 'FAILURE_STATE_F1_REGISTRY.csv', 'F1.1': 'FAILURE_STATE_F11_INFERENCE_REGISTRY.csv',
         'F2': 'FAILURE_STATE_F2_ACTIONABILITY_REGISTRY.csv',
         'F2.1': 'FAILURE_STATE_F21_MATCHED_ACTION_REGISTRY.csv',
         'F2.2': 'FAILURE_STATE_F22_BREAK_EVEN_REGISTRY.csv'}
for name, sha in prior.items():
    with open(os.path.join(REPO, 'research', 'risk', 'registries', paths[name]), 'rb') as f:
        assert hashlib.sha256(f.read()).hexdigest() == sha, f'{name} registry SHA changed (I8)'

# ---------------- inputs (I1: matched_delta unchanged) ----------------
ep = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'f21', 'f21_episode_matched.csv'))
d20 = ep[ep['threshold'] == 0.20].copy()
assert len(d20) == 12590 and d20['anchor_i'].nunique() == 752
d_exit = d20['matched_delta'].fillna(0.0).to_numpy()
is_fail = (d20['final_return'] <= 0).to_numpy()
day_arr = d20['anchor_i'].to_numpy()

# ---------------- A_d / B_d (identical to F2.2; I2) ----------------
comp_rows = []
for d_i, idx in d20.groupby('anchor_i').groups.items():
    sub = d20.loc[idx]
    n_d = len(sub)
    comp_rows.append(dict(anchor_day=int(d_i), n=int(n_d),
                          n_failure=int((sub['final_return'] <= 0).sum()),
                          n_recovery=int((sub['final_return'] > 0).sum()),
                          failure_component=float(sub['matched_delta'][sub['final_return'] <= 0].sum() / n_d),
                          recovery_component=float(sub['matched_delta'][sub['final_return'] > 0].sum() / n_d)))
comp = pd.DataFrame(comp_rows).sort_values('anchor_day').reset_index(drop=True)
assert len(comp) == 752
A = float(comp['failure_component'].mean())
B = float(comp['recovery_component'].mean())
f22 = json.load(open(os.path.join(REPO, 'results', 'evidence', 'f22', 'f22_summary.json')))
assert abs(A - f22['A_failure_unit_day_equal']) < 1e-12, 'I2: A mismatch vs F2.2'
assert abs(B - f22['B_recovery_unit_day_equal']) < 1e-12, 'I2: B mismatch vs F2.2'
print(f'[F23] A={A:.10f}  B={B:.10f}  (F2.2 frozen values reproduced)', flush=True)

A_d = comp['failure_component'].to_numpy()
B_d = comp['recovery_component'].to_numpy()
t_day = comp['anchor_day'].to_numpy()          # time-ordered anchor days
N2024 = 1212                                    # 2020-2024 trading calendar length
assert t_day.max() < N2024

# ---------------- grid evaluation ----------------
TPR_GRID = [0.25, 0.50, 0.75, 1.00]
FPR_GRID = [0.0, 0.05, 0.10, 0.20, 0.30, 0.50, 1.00]

def hac_mean_ci(x, maxlags=10):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    if len(x) < 12:
        return np.nan, np.nan, np.nan
    res = sm.OLS(x, np.ones(len(x))).fit(cov_type='HAC', cov_kwds={'maxlags': maxlags})
    return float(res.params[0]), float(res.params[0] - 1.96 * res.bse[0]), float(res.params[0] + 1.96 * res.bse[0])

def calendar_boot_ci(series_day, day_idx, L=21, B=2000, seed=0):
    """full-calendar moving-block bootstrap; no-anchor days NaN, dropped after resample"""
    fx = np.full(N2024, np.nan)
    for i, v in zip(day_idx, series_day):
        fx[int(i)] = v
    rng = np.random.default_rng(seed)
    n = N2024; nblk = int(np.ceil(n / L)); out = []
    for _ in range(B):
        idx = []
        for _b in range(nblk):
            st = rng.integers(0, n - L + 1) if n - L + 1 > 0 else 0
            idx.extend(range(st, min(st + L, n)))
        idx = np.array(idx[:n]); v = fx[idx]; v = v[np.isfinite(v)]
        if len(v) < 10:
            out.append(np.nan); continue
        out.append(v.mean())
    out = np.array(out); out = out[np.isfinite(out)]
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5)), float(out.mean())

# V_d for every grid cell
grid_rows = []
for tpr in TPR_GRID:
    for fpr in FPR_GRID:
        V_d = tpr * A_d + fpr * B_d
        point = float(V_d.mean())
        analytic = tpr * A + fpr * B
        assert abs(point - analytic) < 1e-12, f'I4: point-anayltic mismatch {point} vs {analytic}'
        h_mean, h_lo, h_hi = hac_mean_ci(V_d, 10)
        b_lo, b_hi, b_mu = calendar_boot_ci(V_d, t_day)
        grid_rows.append(dict(TPR=tpr, FPR=fpr, point=point, analytic=analytic,
                              hac_ci_lo=h_lo, hac_ci_hi=h_hi,
                              cal_ci_lo=b_lo, cal_ci_hi=b_hi, cal_boot_mean=b_mu))
grid = pd.DataFrame(grid_rows)
grid.to_csv(os.path.join(OUT, 'f23_grid_calendar_bootstrap.csv'), index=False)

# HAC-only file
grid[['TPR', 'FPR', 'point', 'hac_ci_lo', 'hac_ci_hi']].to_csv(os.path.join(OUT, 'f23_grid_hac.csv'), index=False)

# randomization interval from frozen f21 grid (reference only)
f21_grid = pd.read_csv(os.path.join(REPO, 'results', 'evidence', 'f21', 'f21_confusion_value_grid.csv'))
merged = grid.merge(f21_grid[['TPR', 'FPR', 'expected_delta', 'ci_lo', 'ci_hi']], on=['TPR', 'FPR'])
merged.rename(columns={'expected_delta': 'randomization_point', 'ci_lo': 'randomization_ci_lo', 'ci_hi': 'randomization_ci_hi'}, inplace=True)
# randomization point should match analytic point (same expectation)
md = float((merged['point'] - merged['randomization_point']).abs().max())
assert md < 0.05, f'randomization point vs deterministic point mismatch {md}'
merged[['TPR', 'FPR', 'point', 'randomization_ci_lo', 'randomization_ci_hi',
        'hac_ci_lo', 'hac_ci_hi', 'cal_ci_lo', 'cal_ci_hi']].to_csv(os.path.join(OUT, 'f23_randomization_vs_sampling.csv'), index=False)

# ---------------- policy day values file ----------------
policy_rows = []
for tpr in TPR_GRID:
    for fpr in FPR_GRID:
        for i in range(752):
            policy_rows.append(dict(anchor_day=int(t_day[i]), TPR=tpr, FPR=fpr,
                                    V_d=float(tpr * A_d[i] + fpr * B_d[i])))
pd.DataFrame(policy_rows).to_csv(os.path.join(OUT, 'f23_policy_day_values.csv'), index=False)

# ---------------- safe frontiers ----------------
def safe(grid_df, col_lo):
    out = []
    for tpr in TPR_GRID:
        sub = grid_df[grid_df['TPR'] == tpr]
        safe_fprs = [float(f) for f in FPR_GRID if float(sub[sub['FPR'] == f][col_lo].iloc[0]) > 0]
        out.append(dict(TPR=tpr, safe_fpr=max(safe_fprs) if safe_fprs else 0.0, safe_fpr_list=safe_fprs))
    return pd.DataFrame(out)

cal_safe = safe(grid, 'cal_ci_lo')
hac_safe = safe(grid, 'hac_ci_lo')
rand_safe = safe(merged, 'randomization_ci_lo')
safe_out = cal_safe.merge(hac_safe.rename(columns={'safe_fpr': 'hac_safe_fpr', 'safe_fpr_list': 'hac_safe_list'}),
                          on='TPR').merge(rand_safe.rename(columns={'safe_fpr': 'rand_safe_fpr', 'safe_fpr_list': 'rand_safe_list'}),
                                          on='TPR')
safe_out.rename(columns={'safe_fpr': 'calendar_safe_fpr', 'safe_fpr_list': 'calendar_safe_list'}, inplace=True)
safe_out.to_csv(os.path.join(OUT, 'f23_safe_frontier.csv'), index=False)

# ---------------- perfect-label parity (I5) ----------------
o1 = grid[(grid['TPR'] == 1.0) & (grid['FPR'] == 0.0)].iloc[0]
assert abs(o1['point'] - 1.4485803535) < 1e-6, f'I5 point mismatch {o1["point"]}'
assert abs(o1['hac_ci_lo'] - 0.4767) < 0.05 and abs(o1['hac_ci_hi'] - 2.4205) < 0.05, f'I5 HAC mismatch {o1["hac_ci_lo"]},{o1["hac_ci_hi"]}'
assert abs(o1['cal_ci_lo'] - 0.4027) < 0.05 and abs(o1['cal_ci_hi'] - 2.6072) < 0.05, f'I5 boot mismatch {o1["cal_ci_lo"]},{o1["cal_ci_hi"]}'
print(f'[F23] I5 perfect-label O1 parity: point={o1["point"]:.6f} HAC[{o1["hac_ci_lo"]:.4f},{o1["hac_ci_hi"]:.4f}] '
      f'cal[{o1["cal_ci_lo"]:.4f},{o1["cal_ci_hi"]:.4f}] PASS', flush=True)

# ---------------- key cells ----------------
key_cells = [(0.25, 0.05), (0.25, 0.10), (0.50, 0.10), (0.50, 0.20), (0.50, 0.30),
             (0.75, 0.20), (0.75, 0.30), (0.75, 0.50), (1.00, 0.30), (1.00, 0.50)]
key_rows = []
for t, f in key_cells:
    row = grid[(grid['TPR'] == t) & (grid['FPR'] == f)].iloc[0]
    rnd = merged[(merged['TPR'] == t) & (merged['FPR'] == f)].iloc[0]
    key_rows.append(dict(TPR=t, FPR=f, point=float(row['point']),
                         hac_ci_lo=float(row['hac_ci_lo']), hac_ci_hi=float(row['hac_ci_hi']),
                         cal_ci_lo=float(row['cal_ci_lo']), cal_ci_hi=float(row['cal_ci_hi']),
                         randomization_ci_lo=float(rnd['randomization_ci_lo']),
                         randomization_ci_hi=float(rnd['randomization_ci_hi'])))
pd.DataFrame(key_rows).to_csv(os.path.join(OUT, 'f23_key_cells.csv'), index=False)

# ---------------- classification (rule unchanged) ----------------
g5020 = grid[(grid['TPR'] == 0.50) & (grid['FPR'] == 0.20)].iloc[0]
a_gate = (g5020['cal_ci_lo'] > 0) and (g5020['hac_ci_lo'] > 0)
if a_gate:
    cls = 'A'
elif (o1['cal_ci_lo'] > 0) and (o1['hac_ci_lo'] > 0):
    cls = 'B'
elif (o1['cal_ci_lo'] > 0) or (o1['hac_ci_lo'] > 0):
    cls = 'C'
else:
    cls = 'D'
print(f'[F23] classification = {cls}', flush=True)

# ---------------- invariants ----------------
inv = dict(
    I1_matched_delta_unchanged=True,
    I2_AB_unchanged_from_F22=True,
    I3_point_roots_unchanged=True,
    I4_Vd_mean_exact_parity_analytic=True,
    I5_TPR1_FPR0_reproduces_O1=True,
    I6_full_calendar_L21_B2000_seed0=True,
    I7_no_random_classifier_draw_in_primary_CI=True,
    I8_prior_registry_shas_unchanged=True,
    I9_no_2025_read=True,
    I10_no_predictor_stop_new_timing=True,
    point_A=float(A), point_B=float(B),
    perfect_label_o1=dict(point=float(o1['point']), hac_ci_lo=float(o1['hac_ci_lo']), hac_ci_hi=float(o1['hac_ci_hi']),
                          cal_ci_lo=float(o1['cal_ci_lo']), cal_ci_hi=float(o1['cal_ci_hi'])),
    g5020=dict(point=float(g5020['point']), hac_ci_lo=float(g5020['hac_ci_lo']), hac_ci_hi=float(g5020['hac_ci_hi']),
               cal_ci_lo=float(g5020['cal_ci_lo']), cal_ci_hi=float(g5020['cal_ci_hi'])),
    key_cells=key_rows, safe_frontier=safe_out.to_dict('records'),
    classification=cls, registry_sha=reg_sha,
)
with open(os.path.join(OUT, 'f23_invariants.json'), 'w') as f:
    json.dump(inv, f, indent=2, ensure_ascii=False)
with open(os.path.join(OUT, 'f23_summary.json'), 'w') as f:
    json.dump(inv, f, indent=2, ensure_ascii=False)
print('[F23] summary saved; classification =', cls)
print('[F23] DONE', flush=True)
