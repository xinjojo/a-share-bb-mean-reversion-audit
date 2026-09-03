#!/usr/bin/env python3
"""
STEP_A_RANKING_VALIDATE_PREREGISTER.py

Phase P2 — Cross-Sectional Ranking Validation (untouched 2023-2024).

THIS SCRIPT READS **NO** OUTCOME DATA. It only writes the frozen
CROSS_SECTIONAL_RANKING_VALIDATION_REGISTRY.csv + .sha256, so the registry is
committed BEFORE any 2023-2024 episode return is read (hard red line).

Candidate set = the 5 robust P1.1 Discovery passers, directions frozen from
Discovery. F05 RET5 is EXCLUDED from the confirmatory primary family (marginal
Discovery bootstrap sensitivity) and from BH m=5 and from A/B/C classification.
"""
import hashlib, os, sys

REPO = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo'
REG = os.path.join(REPO, 'CROSS_SECTIONAL_RANKING_VALIDATION_REGISTRY.csv')
SHAF = os.path.join(REPO, 'CROSS_SECTIONAL_RANKING_VALIDATION_REGISTRY.sha256')

ROWS = [
    # validation_id, original_feature_id, family, name, formula, direction, window_k
    ('V01', 'F04', 'GROUP_A', 'RET3',
     'close_adj[T] / close_adj[T-3 observed stock bars] - 1', 'NEGATIVE', 3),
    ('V02', 'F06', 'GROUP_A', 'RET20',
     'close_adj[T] / close_adj[T-20 observed stock bars] - 1', 'NEGATIVE', 20),
    ('V03', 'F07', 'GROUP_A', 'DIST_MA20',
     'close_adj[T] / MA20(close_adj) - 1', 'NEGATIVE', 20),
    ('V04', 'F09', 'GROUP_B', 'ATR20_PCT',
     'ATR20 / close; TR = max(high-low, |high-pre_close|, |low-pre_close|)', 'POSITIVE', 20),
    ('V05', 'F13', 'GROUP_B', 'INTRADAY_RANGE',
     '(high - low) / pre_close', 'POSITIVE', 1),
]

FIXED = dict(
    validation_start='2023-01-01',
    validation_end='2024-12-31',
    minimum_signals_per_day=5,
    primary_daily_IC='per-day cross-sectional Spearman(predictor rank, final return rank); '
                     'direction frozen from Discovery (NEGATIVE/POSITIVE), no re-orientation',
    HAC_lag='10 (primary); sensitivity 5 / 20',
    BH_family_size=5,
    pairwise_gate='oriented pairwise accuracy >= 53.0%; ties (dx==0 or dr==0) excluded; '
                  'PAIR_CAP=5000 pairs/day; RNG seed fixed',
    K3_gate='equal-day K3 selection lift >= +0.50 pp (signal days with >=3 valid signals)',
    bootstrap_rule='signal-day block bootstrap L=21, B>=5000, full-length moving block; '
                   'K3-lift 95% CI lower bound > 0',
    yearly_rule='2023 and 2024 both same direction, OR one same + the other |annual mean IC| '
                '< 0.02 (near-zero); a year opposite with |IC| >= 0.02 forbids STRONG PASS',
    effect_gate='|mean daily IC| >= 0.03',
    random_k3_baseline='PER-FEATURE exact usable-day random baseline, WITHOUT replacement, '
                       'B=5000, fixed seed; Gate E uses same-day K3_lift_t, random is reference only',
    oracle='HINDSIGHT ORACLE, DESCRIPTIVE ONLY, per-feature exact usable-day set, no replacement',
    composite='FORBIDDEN this round (no score/rank-average/linear/ML/PCA)',
    primary_sensitivity='PRIMARY_POOLED_DIRECTION_SENSITIVITY on frozen PRIMARY Top10 '
                        '2023-2024 episodes, direction-match only',
    f05_status='MARGINAL_DISCOVERY_SENSITIVITY - NOT in BH m=5, NOT in classification, '
               'cannot rescue failures, cannot be added to main model later based on validation',
    validation_status='PREREGISTERED',
)

def main():
    lines = ['validation_id,original_feature_id,family,name,exact_formula,direction,window_k']
    for vid, fid, fam, name, formula, direction, wk in ROWS:
        # quote formula (contains commas)
        lines.append(f'{vid},{fid},{fam},{name},"{formula}",{direction},{wk}')
    for k, v in FIXED.items():
        lines.append(f'# {k} = {v}')
    text = '\n'.join(lines) + '\n'
    with open(REG, 'w') as fh:
        fh.write(text)
    sha = hashlib.sha256(text.encode('utf-8')).hexdigest()
    with open(SHAF, 'w') as fh:
        fh.write(sha + '  ' + os.path.basename(REG) + '\n')
    print('wrote', REG)
    print('SHA256:', sha)
    print('NO OUTCOME DATA WAS READ BY THIS STEP.')

if __name__ == '__main__':
    main()
