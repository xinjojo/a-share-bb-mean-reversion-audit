#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A0 — PROJECT ALPHA INVENTORY & BLIND-TEST DECISION GATE
======================================================
Pure evidence inventory over all 2020-2024 development evidence. NO new research.
Governance: M2.1 PASS / M2 FINAL D / ETF branch CLOSED / 2025-2026 CLOSED.
This script only reads frozen evidence summaries (hard-coded from accepted stage records)
and produces the inventory CSVs, gate evaluation, and decision.
"""
import os, json, hashlib, pandas as pd

REPO = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo'
OUT = os.path.join(REPO, 'results', 'evidence', 'a0')
os.makedirs(OUT, exist_ok=True)

DEV = '2020-01-01..2024-12-31'

# ---------------------------------------------------------------- master table
M = []
def add(phase, hypothesis, layer, primary_metric, result, classification, cat, stat, econ,
        impl, cost, pit, port_tested, exec_tested, y26, branch, blind, reason):
    M.append(dict(phase=phase, hypothesis=hypothesis, layer=layer, development_period=DEV,
                  primary_metric=primary_metric, result=result, classification=classification,
                  category=cat, statistical_strength=stat, economic_strength=econ,
                  implementation_realism=impl, cost_included=cost, PIT_status=pit,
                  portfolio_tested=port_tested, execution_tested=exec_tested,
                  y2025_2026_touched=y26, branch_status=branch, can_enter_blind_test=blind, reason=reason))

# --- CATEGORY 1: robust signal-level edge
add('Independent Trade Replay V2A', 'BB lower-band episode edge is real (no lookahead)',
    'signal', 'episode mean return / HAC', 'STRICT_C signal layer survives independent replay; positive episode expectancy',
    'A — ROBUST SIGNAL EDGE', 1, 'STRONG (replay, no same-bar info)', 'POSITIVE episode-level', 'entry only (T+1 open)',
    'episode-level costs model', 'PIT OK', False, 'replay verified', False, 'OPEN (validated)',
    False, 'Robust signal-level edge; not a portfolio.')
add('Full-Market Episode Replay', 'BB edge generalizes across full market ~89k',
    'signal', 'replay parity', 'Full-market episode replay structure A; trade-path structure consistent',
    'A — ACCEPTED', 1, 'STRONG', 'POSITIVE', 'replay only', 'included in replay', 'PIT OK',
    False, 'replay verified', False, 'OPEN (validated)', False, 'Generalization of replay edge.')
add('B1/B1.1 Breadth', 'day-level B20 breadth predicts day mean episode return',
    'signal/date-level', 'Q5-Q1 day mean return / HAC / calendar boot / conditional b1',
    'Q5-Q1 +2.664291pp; corrected calendar boot CI [+1.102,+4.185]; rank-slope HAC [+0.00130,+0.00463]; conditional b1 +3.283183 CI [+1.030,+5.537]; 5/5 years positive; monotone; tail not worse',
    'A — STRONG BREADTH VALUE (FINAL)', 1, 'STRONG (corrected inference)', 'POSITIVE date-level',
    'date-level diagnostic', 'N/A (date-level)', 'PIT denominator OK', False, False, False,
    'OPEN (validated)', False, 'Robust date-level signal edge; portfolio translation failed (P7/M2).')
add('T2-R Reverse Validation', 'market-state reverse direction relation robust',
    'signal/context', 'validation classification', 'Reverse-direction market-state relationship validated A STRONG',
    'A STRONG VALIDATION (ACCEPTED)', 1, 'STRONG', 'context-level', 'context diagnostic',
    'N/A', 'PIT OK', False, False, False, 'OPEN (validated, context only)',
    False, 'Robust context relationship; T3 showed no gate-able form.')

# --- CATEGORY 2: portfolio / execution failure
add('Original First-Gen Strategy', 'raw BB mean-reversion is hugely profitable',
    'portfolio', 'total return', '+354.9% but same-bar close-close lookahead',
    'INVALID', 2, '—', '—', '—', 'not meaningful', '—', True, True, False,
    'INVALID (lookahead)', False, 'Same-bar future information; theory signal != tradeable return.')
add('STRICT_C Corrected Portfolio (A0 K3)', 'corrected-entry K3 system is the audited baseline',
    'portfolio', 'total/MDD/Sharpe', '+30.2950937861% / Trades 76 / MaxDD -30.7897288178% / Sharpe 0.3467648252',
    'DEVELOPMENT-ONLY BASELINE', 2, 'parity-stable across P4-P7', 'POSITIVE after-cost',
    'REALISTIC (T+1 open, lot, PIT pool, A-share costs/slippage)', 'YES', 'PIT OK',
    True, True, False, 'OPEN (development baseline)', False,
    'Best audited portfolio architecture, but development-only baseline, not a proven alpha carrier.')
add('K999 (no K constraint)', 'removing K ceiling improves capture',
    'portfolio', 'total return', 'Severely worse in P4 ablation (de-constraining K destroys path economics)',
    'D — TESTED BOTTLENECK (ablation)', 2, '—', 'NEGATIVE', 'tested', 'YES', 'PIT OK',
    True, True, False, 'CLOSED', False, 'K=3 is protective admission constraint.')
add('ML1 (max_layers=1)', 'fewer add-layers helps capital efficiency',
    'portfolio', 'total return', 'Removing multilayer adding (5->1) harmful in tested path (P4)',
    'D — HARMFUL (tested)', 2, '—', 'NEGATIVE', 'tested', 'YES', 'PIT OK', True, True,
    False, 'CLOSED', False, 'Add-layer structure is part of baseline economics.')
add('Fixed Stop Variants (S0/S0.1)', 'fixed stops reduce deep-MAE risk',
    'portfolio', 'deep-MAE rate / return', 'Old phase-A conclusion (stops do not help) robust under re-audit',
    'A — OLD CONCLUSION ROBUST (stops rejected)', 2, 'STRONG (audit)', 'NEGATIVE for stops',
    'tested', 'YES', 'PIT OK', True, True, False, 'CLOSED', False, 'Fixed stops rejected.')
add('P3 Finite-K ATR Ranking', 'ATR-based slot allocation beats amount ranking',
    'portfolio', 'portfolio PnL', 'ATR20_PCT passed single-factor screen (P2) but slot allocation adds no portfolio value',
    'C — NO USEFUL PORTFOLIO RANKING (CLOSED)', 2, 'weak', 'NEGATIVE', 'tested', 'YES',
    'PIT OK', True, True, False, 'CLOSED', False, 'Ranking edge did not convert to portfolio value.')
add('P5.1 Deferred Queue', 'queued blocked candidates recover eligibility',
    'portfolio', 'release-day eligibility', 'EXACT_ELIGIBLE only 2.68%; 88.99% no longer oversold; queue mostly stale',
    'C — QUEUE MOSTLY STALE (CLOSED)', 2, 'STRONG (diagnostic)', 'NEGATIVE', 'tested',
    'N/A', 'PIT OK', True, True, False, 'CLOSED', False, 'Queue admission not worth backtest.')
add('P6 Add-Budget Separation', 'separating NEW/ADD wallets protects path',
    'portfolio', 'total return', 'A1 +11.04% / A2 +10.27% / A3 -7.76% vs A0 +30.30%',
    'D — HARMFUL (ACCEPTED)', 2, '—', 'NEGATIVE', 'tested', 'YES', 'PIT OK', True, True,
    False, 'CLOSED', False, 'Shared-pool time elasticity is part of A0; split wallets hurt.')
add('P7 Panic K6 / Top20+K6', 'panic-day capacity expansion converts breadth alpha',
    'portfolio', 'total return / MDD / Sharpe', 'A1 (K6) -20.81% / -46.94% / -0.047; A2 (Top20+K6) -22.79% / -44.57% / -0.094; 0/5 years; COMMON dilution -183,557',
    'D — HARMFUL / M4 (ACCEPTED)', 2, '—', 'NEGATIVE', 'tested', 'YES', 'PIT OK', True,
    True, False, 'CLOSED', False, 'Capacity expansion worsens shared-capital path; K=3 retained.')
add('M2/M2.1 ETF Carrier (510300)', 'panic-breadth translates to broad-market ETF carrier',
    'portfolio', 'net total return', 'M2 net -5.309%; M2.1 corrected net -7.2514% (gross +12.05% eaten by ~19.3pp cost); p=0.145; 2/4 years',
    'D — HARMFUL (M2 FINAL, ACCEPTED)', 2, 'weak (perm p=0.145)', 'NEGATIVE after-cost',
    'REALISTIC (T+1 open, 5d hold, non-overlap, 100k, costs)', 'YES', 'PIT OK', True, True,
    False, 'CLOSED', False, 'Thin rebound edge eaten by execution costs; carrier translation failed.')

# --- CATEGORY 3: diagnostic / context only
add('Regime Discovery (T2)', 'market-state reverse direction relationship exists',
    'signal/context', 'discovery classification', 'Reverse-direction relationship discovered (ACCEPTED AS DISCOVERY)',
    'DISCOVERY', 3, 'discovery', 'context', 'diagnostic', 'N/A', 'PIT OK', False, False,
    False, 'OPEN (discovery)', False, 'Context discovery; basis of T2-R and B1.1.')
add('P1/P2 ATR Ranking', 'cross-sectional ranking has signal value',
    'signal', 'ranking validation', 'P1 A discovery; P2 B partial (ATR20_PCT only full pass)',
    'B — PARTIAL (P2, ACCEPTED)', 3, 'partial', 'partial', 'diagnostic', 'episode-level',
    'PIT OK', False, False, False, 'SUPERSEDED BY P3 FAILURE', False, 'Single-factor partial; not executable.')
add('P4 Architecture Ablation', 'structural bottleneck identification',
    'portfolio', 'ablation returns', 'K=3 is the binding capacity bottleneck and protective admission constraint; de-constraining any constraint worsens',
    'D — TESTED BOTTLENECK (ACCEPTED DIAGNOSTIC)', 3, 'STRONG (mechanism)', 'context', 'diagnostic',
    'YES', 'PIT OK', True, True, False, 'OPEN (diagnostic)', False, 'Explains why expansion fails.')
add('P4.1 PnL Bridge', 'why de-constraining K hurts',
    'portfolio', 'COMMON path PnL delta', 'Capital/path dilution dominant: COMMON 65 same trades, A1 earns -67k vs A0; A1_ONLY -118,610 actual PnL',
    'B — CAPITAL/PATH DILUTION DOMINANT (DEVELOPMENT DIAGNOSTIC)', 3, 'STRONG (H3 evidence)',
    'mechanism', 'diagnostic', 'YES', 'PIT OK', True, True, False, 'OPEN (diagnostic)', False,
    'More positive-expectancy trades can reduce portfolio return via shared capital/path.')
add('F1/F1.1 Recoverability', 'deep-MAE episodes recoverability predictable',
    'signal/risk', 'recoverability classification', 'Deep-MAE recoverability predictable (A STRONG) with corrected inference',
    'A — STRONG RECOVERABILITY PREDICTABILITY', 3, 'STRONG', 'diagnostic', 'diagnostic', 'N/A',
    'PIT OK', False, False, False, 'OPEN (diagnostic)', False, 'Context for risk understanding; not a deployable signal.')
add('F2/F2.1/F2.2/F2.3 Actionability', 'perfect-label early exit has value',
    'signal/risk', 'day-equal value', 'Perfect-label D20+1 exit +1.4486pp (HAC [+0.4767,+2.4205]); break-even precision 0.762',
    'B — NARROW POSITIVE ACTIONABILITY (ACCEPTED)', 3, 'STRONG (statistics)', 'UPPER BOUND only (future label)',
    'not deployable (future label)', 'N/A', 'PIT OK', False, False, False, 'OPEN (bound)', False,
    'Actionability upper bound; depends on future information.')
add('F3 Predictor Feasibility', 'real simple predictor achieves economic threshold',
    'signal/risk', 'OOF AUC / stable years', 'OOF AUC 0.720 but STABLE_SAFE/STABLE_POINT 0/6; 2024 only positive',
    'C — PREDICTIVE BUT ECONOMICALLY INSUFFICIENT (ACCEPTED)', 3, 'MODERATE (AUC)', 'INSUFFICIENT',
    'diagnostic', 'N/A', 'PIT OK', False, False, False, 'CLOSED', False,
    'Predictive but below economic threshold.')
add('P5 Capacity Diagnostic', 'where does capital get blocked',
    'portfolio', 'blocked reasons', 'K=3 blocks 63.4% of candidates, 55.1% of days K-full; cash never blocks; K protective',
    'C — BOTTLENECK DIAGNOSTIC (R1.1 corrected)', 3, 'STRONG (diagnostic)', 'context', 'diagnostic',
    'YES', 'PIT OK', True, False, False, 'OPEN (diagnostic)', False, 'K is binding bottleneck.')
add('S1 Signal Selectivity', 'deeper-entry threshold / RSI / sector add value',
    'signal', 'matched-depth comparisons', 'BB threshold D (B25 vs B20_ONLY -2.12pp, HAC [-2.60,-1.64]); RSI C; sector N/A',
    'D THRESHOLD / C RSI / N/A SECTOR (ACCEPTED)', 3, 'STRONG (threshold negative)',
    'negative evidence', 'diagnostic', 'N/A', 'PIT OK', False, False, False, 'CLOSED', False,
    'Waiting for deeper entry harmful; RSI no stable increment.')
add('S1.1 Depth Ranking', 'same-day deeper BB_Z ranks better for slots',
    'signal', 'DEEP30-SHALLOW30 day delta', '-0.023pp (HAC [-0.53,+0.48]); 2/5 years; non-monotone; Spearman ~0',
    'C — NO STABLE RANKING VALUE (ACCEPTED)', 3, 'weak', 'negative', 'diagnostic', 'N/A',
    'PIT OK', False, False, False, 'CLOSED', False, 'Contemporaneous depth cannot rank candidates.')
add('W1 Weekly BB Context', 'weekly lower-band resonance adds diagnostic value',
    'signal', 'touch vs no-touch paired delta', 'Pooled advantage is between-day composition effect; within-day negative; classified D',
    'D — HARMFUL (ACCEPTED)', 3, 'weak', 'negative', 'diagnostic', 'N/A', 'PIT OK', False,
    False, False, 'CLOSED', False, 'Weekly resonance has no incremental value.')
add('D1/D1.1/D1.2 PIT Context', 'auditable PIT sector and fundamental layers',
    'data', 'coverage / revision semantics', 'Sector B (94.555% coverage, historical rebuildable); financial A (100% / TTM 98.80% / forecast 94.73% / express 37.16%); D1.1 STRICT_SELECTOR PASS; D1.2 C SEMANTICS AMBIGUOUS',
    'DATA FOUNDATION (D1 HOLD; D1.1 PASS; D1.2 C)', 3, 'STRONG (audit)', 'context', 'data layer',
    'N/A', 'PIT semantics audited', False, False, False, 'HOLD (S3 forbidden)', False,
    'Data layer not strategy; fundamental visibility semantics unresolved.')
add('M1/M1.1/M1.2 Market Rebound', 'panic breadth predicts forward market rebound',
    'market', 'FWD5 delta / HAC / boot', 'M1 exploratory protocol-deviated (withdrawn); M1.1 provisional; M1.2 FINAL FWD5 +0.2752pp, boot CI [-0.288,+0.798] cross 0, cluster-first -0.2766pp, 3/4 years',
    'B — NARROW MARKET TRANSLATION (M1.2 FINAL, ACCEPTED)', 3, 'weak (CI cross 0)',
    'narrow, episode-dependent', 'diagnostic', 'N/A', 'PIT OK', False, False, False,
    'OPEN (narrow indication)', False, 'Weak market-level indication; ETF gate was one frozen carrier test (failed).')

# ---------------------------------------------------------------- signal alpha
SA = [
    dict(question='1. Independent BB lower-band episode edge robust?', answer='YES',
         evidence='Independent Trade Replay V2A + full-market replay: STRICT_C signal layer verified without same-bar lookahead; positive episode expectancy',
         robustness='ROBUST', deployable=False, note='Signal-level edge only; entry is signal, not portfolio.'),
    dict(question='2. Breadth environment effect robust?', answer='YES (signal-level)',
         evidence='B1.1 A FINAL: Q5-Q1 +2.664pp, corrected calendar boot [+1.102,+4.185], rank-slope HAC [+0.00130,+0.00463], conditional b1 +3.283 CI [+1.030,+5.537], 5/5 years, monotone, tail OK',
         robustness='ROBUST (corrected inference)', deployable=False,
         note='Date-level edge robust; portfolio conversion failed twice (P7 capacity, M2 carrier).'),
    dict(question='3. ATR ranking executable?', answer='NO',
         evidence='P2 B partial (ATR20_PCT single-factor full pass); P3 finite-K slot allocation C (no portfolio value)',
         robustness='PARTIAL (single factor)', deployable=False,
         note='Statistical partial pass did not convert to portfolio value under K=3.'),
    dict(question='4. Failure-state prediction economically executable?', answer='NO',
         evidence='F3 C: OOF AUC 0.720 but stable economic threshold 0/6 years; F2 perfect-label bound +1.45pp is future-dependent',
         robustness='MODERATE (predictive only)', deployable=False,
         note='Predictive but economically insufficient; actionability bound needs future label.'),
    dict(question='5. Market-level rebound robust?', answer='NO',
         evidence='M1.2 B FINAL: FWD5 +0.2752pp, HAC [-0.300,+0.851] and calendar boot [-0.288,+0.798] cross 0, cluster-first -0.2766pp (episode-dependent), 3/4 years; M2 carrier net -7.25%',
         robustness='WEAK (CI cross 0)', deployable=False,
         note='Narrow/weak/episode-dependent; single frozen carrier test failed after cost.'),
]
pd.DataFrame(SA).to_csv(os.path.join(OUT, 'a0_signal_alpha.csv'), index=False)

# ---------------------------------------------------------------- portfolio architectures
PA = [
    dict(architecture='First-gen K3', return_pct=354.9, mdd_pct=None, sharpe=None, after_cost=False,
         realistic_execution=False, status='INVALID', failure_mechanism='same-bar close-close lookahead'),
    dict(architecture='STRICT_C / A0 K3 baseline', return_pct=30.2951, mdd_pct=-30.7897, sharpe=0.3468,
         after_cost=True, realistic_execution=True, status='DEVELOPMENT-ONLY BASELINE',
         failure_mechanism='not a proven alpha carrier; development-comparison architecture; Sharpe weak'),
    dict(architecture='K999 (no K ceiling)', return_pct=None, mdd_pct=None, sharpe=None, after_cost=True,
         realistic_execution=True, status='FAILED (P4 ablation)', failure_mechanism='de-constraining K destroys shared-capital path'),
    dict(architecture='ML1 (max_layers=1)', return_pct=None, mdd_pct=None, sharpe=None, after_cost=True,
         realistic_execution=True, status='FAILED (P4/P6 tested)', failure_mechanism='removing add-layers hurts path economics'),
    dict(architecture='Fixed stop variants', return_pct=None, mdd_pct=None, sharpe=None, after_cost=True,
         realistic_execution=True, status='FAILED (S0 audit robust)', failure_mechanism='stops do not improve outcomes'),
    dict(architecture='Capital wallet separation (P6)', return_pct=10.27, mdd_pct=None, sharpe=None,
         after_cost=True, realistic_execution=True, status='D HARMFUL',
         failure_mechanism='split NEW/ADD wallets cut layer2/3 positive PnL (-163,660 on COMMON)'),
    dict(architecture='Deferred queue (P5.1)', return_pct=None, mdd_pct=None, sharpe=None, after_cost=True,
         realistic_execution=True, status='C STALE — not backtested',
         failure_mechanism='release-day eligibility only 2.68%; 88.99% no longer oversold'),
    dict(architecture='Panic K6 (P7 A1)', return_pct=-20.81, mdd_pct=-46.94, sharpe=-0.047, after_cost=True,
         realistic_execution=True, status='D HARMFUL',
         failure_mechanism='capacity expansion dilutes COMMON path (-183,557), cash exhaustion (77 no-cash blocks)'),
    dict(architecture='Panic Top20/K6 (P7 A2)', return_pct=-22.79, mdd_pct=-44.57, sharpe=-0.094, after_cost=True,
         realistic_execution=True, status='D HARMFUL',
         failure_mechanism='wider admission worsens candidate quality (A2_ONLY MAE30 20%)'),
    dict(architecture='ETF carrier 510300 (M2/M2.1)', return_pct=-7.2514, mdd_pct=-24.13, sharpe=-0.064,
         after_cost=True, realistic_execution=True, status='D HARMFUL',
         failure_mechanism='gross +12.05% eaten by ~19.3pp costs (slip 15.4pp + fee 3.9pp); p=0.145; 2023 -17.35%'),
]
pd.DataFrame(PA).to_csv(os.path.join(OUT, 'a0_portfolio_architectures.csv'), index=False)

# ---------------------------------------------------------------- branch status
BS = [
    dict(branch='STRICT_C daily B20 signal layer', status='VALIDATED (signal-level)', blind_candidate=False),
    dict(branch='B1.1 breadth date-level edge', status='VALIDATED (signal-level)', blind_candidate=False),
    dict(branch='T2/T2-R market-state reverse context', status='VALIDATED (context only)', blind_candidate=False),
    dict(branch='BB threshold / RSI / sector (S1)', status='CLOSED', blind_candidate=False),
    dict(branch='Contemporaneous depth ranking (S1.1)', status='CLOSED', blind_candidate=False),
    dict(branch='Weekly BB resonance (W1)', status='CLOSED', blind_candidate=False),
    dict(branch='Fundamental distress (S3)', status='HOLD (D1.2 C)', blind_candidate=False),
    dict(branch='ATR ranking (P3)', status='CLOSED', blind_candidate=False),
    dict(branch='Failure-state predictor (F3)', status='CLOSED', blind_candidate=False),
    dict(branch='Queue / deferred admission (P5.1)', status='CLOSED', blind_candidate=False),
    dict(branch='Add-budget separation (P6)', status='CLOSED', blind_candidate=False),
    dict(branch='Panic capacity expansion (P7)', status='CLOSED', blind_candidate=False),
    dict(branch='Panic-breadth market rebound (M1.2)', status='NARROW INDICATION (ETF gate consumed, failed)', blind_candidate=False),
    dict(branch='Broad-market ETF carrier (M2)', status='CLOSED', blind_candidate=False),
    dict(branch='A0 K3 baseline portfolio', status='DEVELOPMENT-ONLY BASELINE', blind_candidate=False),
]
pd.DataFrame(BS).to_csv(os.path.join(OUT, 'a0_branch_status.csv'), index=False)

# ---------------------------------------------------------------- blind-test gate (against STRICT_C / A0 K3 baseline)
GATE = [
    dict(no=1, criterion='complete frozen rules', verdict='YES', note='A0 rules exact: B20 T+1 open entry, STRICT_C exit, amount Top10, K3, max_layers 5, 200k/layer, 1M shared, A-share costs'),
    dict(no=2, criterion='no lookahead', verdict='YES', note='Independent replay verified; signal at T close, entry T+1 open'),
    dict(no=3, criterion='PIT universe/data acceptable', verdict='PARTIAL', note='B20 PIT tradeable pool OK; fundamental PIT HOLD (D1.2 C) -> context layer not fully frozen'),
    dict(no=4, criterion='realistic A-share execution', verdict='YES', note='T+1, lot, PIT ST/liquidity exclusions, CSI300 breadth'),
    dict(no=5, criterion='real costs', verdict='YES', note='commission + 10bp slippage included'),
    dict(no=6, criterion='portfolio-level net return positive', verdict='YES', note='+30.2951% after-cost 2020-2024'),
    dict(no=7, criterion='risk acceptable', verdict='NO', note='Sharpe 0.347 weak; MaxDD -30.79%; deep-MAE episodes persist'),
    dict(no=8, criterion='development robustness sufficient', verdict='PARTIAL', note='signal layer robust; portfolio layer: 4 conversion attempts all failed -> conversion mechanism not established; A0 kept by comparison, not pre-registered deployment'),
    dict(no=9, criterion='no unresolved P0/P1 materially changing outcome', verdict='YES', note='No known P0 for A0 core; D1.2 ambiguity affects fundamental branch, not A0'),
    dict(no=10, criterion='not a repeatedly-tuned unconfirmed architecture', verdict='NO', note='K3/Top10/layers/200k are development-comparison survivors, never pre-registered as deployable config'),
]
pd.DataFrame(GATE).to_csv(os.path.join(OUT, 'a0_blind_test_gate.csv'), index=False)

# ---------------------------------------------------------------- summary / invariants
summary = dict(
    governance='A0-G: close M2 ETF branch, open project alpha inventory gate',
    decision='DECISION B — DO NOT OPEN BLIND TEST',
    signal_alpha_exists=True,
    deployable_portfolio_alpha_exists=False,
    robust_signal_alpha=['Independent BB lower-band episode edge (replay V2A + full-market replay)',
                         'B1.1 date-level breadth edge (A FINAL, corrected inference)'],
    failed_architectures=['first-gen (+354.9% INVALID lookahead)', 'K999', 'ML1', 'fixed stops (S0)',
                          'wallet separation (P6 D)', 'deferred queue (P5.1 C)', 'panic K6 (P7 A1 -20.81%)',
                          'panic Top20/K6 (P7 A2 -22.79%)', 'ETF carrier 510300 (M2 D, net -7.25% corrected)'],
    current_best_portfolio=dict(name='STRICT_C / A0 K3 baseline', return_pct=30.2951, mdd_pct=-30.7897,
                                sharpe=0.3468, trades=76, after_cost=True, realistic_execution=True,
                                status='development-only baseline, NOT proven alpha carrier'),
    gate_pass_count='6/10 full YES (2 PARTIAL, 2 NO)',
    gate_failures=['#7 risk acceptable (Sharpe 0.347, MaxDD -30.79%)', '#10 not a tuned unconfirmed architecture'],
    gate_partials=['#3 PIT data fully frozen (D1 HOLD)', '#8 development robustness (conversion mechanism unestablished)'],
    core_reason_no_blind='A0 is a development-comparison baseline, not a pre-registered frozen deployment architecture; '
                         'risk profile weak; every signal-to-portfolio conversion attempt (P3/P6/P7/M2) failed; '
                         'therefore no deployable portfolio alpha exists to blind-test.',
    scientific_conclusions=['Signal alpha exists: BB lower-band episode edge and breadth date-level edge are robust facts.',
                            'Portfolio alpha does not exist: K3 constraint is protective; expansion/wallet/queue/ETF conversions all fail.',
                            'Why more positive-expectancy trades reduce portfolio return: shared capital + path dilution + slot displacement (P4.1/P5/P7).',
                            'Costs dominate thin edges: M2 gross +12.05% -> net -7.25% under ~19.3pp costs.',
                            'Theory signals are not tradeable returns: first-gen +354.9% was same-bar lookahead.'],
    no_2025_2026_read=True,
)
json.dump(summary, open(os.path.join(OUT, 'a0_summary.json'), 'w'), indent=1, ensure_ascii=False)
json.dump(dict(I1_no_new_factor=True, I2_no_new_etf=True, I3_no_new_threshold=True, I4_no_new_hold=True,
               I5_no_new_k=True, I6_no_new_ranking=True, I7_no_new_architecture=True, I8_no_new_ml=True,
               I9_no_2025_2026_read=True, I10_all_major_phases_included=True,
               I11_failures_not_omitted=True, I12_signal_vs_portfolio_distinct=True,
               I13_no_gate_lowering=True),
          open(os.path.join(OUT, 'a0_invariants.json'), 'w'), indent=1)

# write master table last
pd.DataFrame(M).to_csv(os.path.join(OUT, 'a0_alpha_inventory.csv'), index=False)
print('rows in master table:', len(M))
print('category counts:', pd.DataFrame(M).category.value_counts().to_dict())
print('DECISION:', summary['decision'])
print('[DONE]')
