#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==========================================================
PHASE T2-R — STEP A: REVERSE-DIRECTION PREREGISTRATION
==========================================================
Creates TEMPORAL_STATE_REVERSE_VALIDATION_REGISTRY.csv from FROZEN constants
derived exclusively from the Phase T2 Discovery result (commit a386a35):

  7 variables that were BH q<0.05 in T2 Discovery Y20 prospective test but in
  the OPPOSITE direction of their ORIGINAL T2 pre-registered expectation.

  R01 = F02 ALL_A_EW_RET60      -> NEGATIVE   (TREND)
  R02 = F01 ALL_A_EW_RET20      -> NEGATIVE   (TREND)
  R03 = F06 ALL_A_MA20_SLOPE    -> NEGATIVE   (TREND)
  R04 = F08 BREADTH_UP1D        -> NEGATIVE   (BREADTH)
  R05 = F18 LIMIT_DOWN_SHARE    -> POSITIVE   (STRESS)
  R06 = F21 CROSS_SECTION_P10_RET -> NEGATIVE (STRESS)
  R07 = F07 BREADTH_MA20        -> NEGATIVE   (BREADTH)

HARD RED LINE: this script performs NO market-data reads, NO outcome reads,
NO 2023-2024 computation. It ONLY writes the registry + SHA256 so that the
registry can be committed BEFORE STEP B (validation) ever sees Validation
outcomes. If this script ever imports data modules, that is a violation.

Registry commit must precede any Validation outcome analysis.
==========================================================
"""
import os, hashlib, csv

REPO = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo'

# ---------------------------------------------------------------------------
# Frozen reverse-hypothesis spec. Directional expectations are taken verbatim
# from T2 Discovery significant-but-opposite findings (NOT derived from 2023-24).
# Formula text is copied verbatim from TEMPORAL_STATE_FEATURE_REGISTRY.csv (T2).
# ---------------------------------------------------------------------------
ROWS = [
    dict(
        reverse_id='R01', original_feature_id='F02', family='TREND',
        name='ALL_A_EW_RET60',
        formula="All-A EW index 60-trading-day compounded return (same index as F01)",
        expected_direction='NEGATIVE',
        validation_start='2023-01-01', validation_end='2024-12-31',
        primary_horizon='Y20', primary_test='Spearman_IC + NeweyWest_HAC_lag20 + BH_m7',
        hac_lag_primary=20, hac_lag_sensitivity='10,40',
        multiple_testing_family='BH m=7 (7 reverse hypotheses)',
        economic_effect_gate='directional fixed-cutpoint Q-spread >= 1.0 percentage point',
        directional_gate='NEGATIVE: (Q1_Y20 - Q5_Y20) >= +1.0pp AND Q2_Y20 > Q4_Y20',
        status='PREREGISTERED'),
    dict(
        reverse_id='R02', original_feature_id='F01', family='TREND',
        name='ALL_A_EW_RET20',
        formula="All-A EW index = equal-weight mean of PIT-eligible non-ST stock daily returns (close/pre_close-1) on each trading day; compounded over past 20 trading days: prod(1+mean_ret)-1",
        expected_direction='NEGATIVE',
        validation_start='2023-01-01', validation_end='2024-12-31',
        primary_horizon='Y20', primary_test='Spearman_IC + NeweyWest_HAC_lag20 + BH_m7',
        hac_lag_primary=20, hac_lag_sensitivity='10,40',
        multiple_testing_family='BH m=7 (7 reverse hypotheses)',
        economic_effect_gate='directional fixed-cutpoint Q-spread >= 1.0 percentage point',
        directional_gate='NEGATIVE: (Q1_Y20 - Q5_Y20) >= +1.0pp AND Q2_Y20 > Q4_Y20',
        status='PREREGISTERED'),
    dict(
        reverse_id='R03', original_feature_id='F06', family='TREND',
        name='ALL_A_MA20_SLOPE',
        formula="MA20(All-A EW index level) today / MA20 5 trading days ago - 1",
        expected_direction='NEGATIVE',
        validation_start='2023-01-01', validation_end='2024-12-31',
        primary_horizon='Y20', primary_test='Spearman_IC + NeweyWest_HAC_lag20 + BH_m7',
        hac_lag_primary=20, hac_lag_sensitivity='10,40',
        multiple_testing_family='BH m=7 (7 reverse hypotheses)',
        economic_effect_gate='directional fixed-cutpoint Q-spread >= 1.0 percentage point',
        directional_gate='NEGATIVE: (Q1_Y20 - Q5_Y20) >= +1.0pp AND Q2_Y20 > Q4_Y20',
        status='PREREGISTERED'),
    dict(
        reverse_id='R04', original_feature_id='F08', family='BREADTH',
        name='BREADTH_UP1D',
        formula="Fraction of PIT-eligible non-ST stocks with close > pre_close today",
        expected_direction='NEGATIVE',
        validation_start='2023-01-01', validation_end='2024-12-31',
        primary_horizon='Y20', primary_test='Spearman_IC + NeweyWest_HAC_lag20 + BH_m7',
        hac_lag_primary=20, hac_lag_sensitivity='10,40',
        multiple_testing_family='BH m=7 (7 reverse hypotheses)',
        economic_effect_gate='directional fixed-cutpoint Q-spread >= 1.0 percentage point',
        directional_gate='NEGATIVE: (Q1_Y20 - Q5_Y20) >= +1.0pp AND Q2_Y20 > Q4_Y20',
        status='PREREGISTERED'),
    dict(
        reverse_id='R05', original_feature_id='F18', family='STRESS',
        name='LIMIT_DOWN_SHARE',
        formula="Fraction of PIT-eligible non-ST stocks with close <= limit_down_px (limit-down per frozen engine rule: pre_close*(1-pct), pct=0.20/0.10/0.05)",
        expected_direction='POSITIVE',
        validation_start='2023-01-01', validation_end='2024-12-31',
        primary_horizon='Y20', primary_test='Spearman_IC + NeweyWest_HAC_lag20 + BH_m7',
        hac_lag_primary=20, hac_lag_sensitivity='10,40',
        multiple_testing_family='BH m=7 (7 reverse hypotheses)',
        economic_effect_gate='directional fixed-cutpoint Q-spread >= 1.0 percentage point',
        directional_gate='POSITIVE: (Q5_Y20 - Q1_Y20) >= +1.0pp AND Q4_Y20 > Q2_Y20',
        status='PREREGISTERED'),
    dict(
        reverse_id='R06', original_feature_id='F21', family='STRESS',
        name='CROSS_SECTION_P10_RET',
        formula="10th percentile of PIT-eligible non-ST stock daily returns today",
        expected_direction='NEGATIVE',
        validation_start='2023-01-01', validation_end='2024-12-31',
        primary_horizon='Y20', primary_test='Spearman_IC + NeweyWest_HAC_lag20 + BH_m7',
        hac_lag_primary=20, hac_lag_sensitivity='10,40',
        multiple_testing_family='BH m=7 (7 reverse hypotheses)',
        economic_effect_gate='directional fixed-cutpoint Q-spread >= 1.0 percentage point',
        directional_gate='NEGATIVE: (Q1_Y20 - Q5_Y20) >= +1.0pp AND Q2_Y20 > Q4_Y20',
        status='PREREGISTERED'),
    dict(
        reverse_id='R07', original_feature_id='F07', family='BREADTH',
        name='BREADTH_MA20',
        formula="Fraction of PIT-eligible non-ST stocks (listed>=60 trading days, valid quote today) with close_adj > MA20(close_adj)",
        expected_direction='NEGATIVE',
        validation_start='2023-01-01', validation_end='2024-12-31',
        primary_horizon='Y20', primary_test='Spearman_IC + NeweyWest_HAC_lag20 + BH_m7',
        hac_lag_primary=20, hac_lag_sensitivity='10,40',
        multiple_testing_family='BH m=7 (7 reverse hypotheses)',
        economic_effect_gate='directional fixed-cutpoint Q-spread >= 1.0 percentage point',
        directional_gate='NEGATIVE: (Q1_Y20 - Q5_Y20) >= +1.0pp AND Q2_Y20 > Q4_Y20',
        status='PREREGISTERED'),
]

FIELDS = ['reverse_id', 'original_feature_id', 'family', 'name', 'formula',
          'expected_direction', 'validation_start', 'validation_end',
          'primary_horizon', 'primary_test', 'hac_lag_primary',
          'hac_lag_sensitivity', 'multiple_testing_family',
          'economic_effect_gate', 'directional_gate', 'status']


def main():
    out = os.path.join(REPO, 'TEMPORAL_STATE_REVERSE_VALIDATION_REGISTRY.csv')
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in ROWS:
            w.writerow(r)
    with open(out, 'rb') as f:
        h = hashlib.sha256(f.read()).hexdigest()
    sha_path = out[:-4] + '.sha256'   # TEMPORAL_STATE_REVERSE_VALIDATION_REGISTRY.sha256
    with open(sha_path, 'w') as f:
        f.write(h + '  ' + os.path.basename(out) + '\n')
    print(f'registry written: {out}')
    print(f'SHA256: {h}')
    # self-check: no market data imports happened (static guarantee is in the
    # import block above — only os/hashlib/csv)


if __name__ == '__main__':
    main()
