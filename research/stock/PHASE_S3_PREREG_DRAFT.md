# S3 PREREGISTRATION DRAFT — Pyramid / Late-Add Contribution Test

**Status**: DRAFT ONLY — NOT APPROVED, DO NOT RUN
**Created**: 2026-09-04 (S2)
**Predecessor**: S2 = H8 NOT SUPPORTED (amount ranking not harmful at portfolio level)

---

## HYPOTHESIS

> **H_S3**: Later pyramid additions (Level 3+) have lower expectancy than initial/early lots and reduce frozen baseline portfolio quality.

## RATIONALE (from S1/S1.1 confirmed findings)

S1.1 lot attribution (max_levels=5, levels_used = total lots per position):

| Level | Description | Count | Mean Return | WR | Mean Hold |
|-------|-------------|-------|-------------|-----|-----------|
| 1 | initial only | 21 | +7.37% | 85.7% | 20d |
| 2 | initial + 1 add | 27 | +6.43% | 81.5% | 34d |
| 3 | initial + 2 adds | 18 | -0.56% | 55.6% | 38d |
| 4 | initial + 3 adds | 4 | -3.70% | 25.0% | 57d |
| 5 | initial + 4 adds (max) | 4 | -13.89% | 0.0% | 110d |

- Level 1-2 are strongly profitable (WR 81-86%)
- Level 3 breaks even (WR 55.6%, mean -0.56%)
- Level 4-5 are deeply unprofitable (WR 0-25%, 110d average hold)
- Level 5 positions alone contribute -515k PnL (more than total portfolio profit of +265k)
- Lot reconciliation PASS (sum lot PnL = position PnL, diff 0.01 RMB floating)

## TREATMENT DESIGN

### Control
- Frozen G0 baseline: max_levels=5, K=3 concurrent, level_cash=200k, initial_cash=1M
- All parameters identical to S2 Control

### Treatment: NO-ADD (initial only)
- Same initial entries, same entry signal, same ranking (amount), same exit
- NO ADD positions (max_levels=1)
- Initial position size UNCHANGED (200k per lot)
- Do NOT compensate with larger initial size (that would confound)

### Why no-add rather than cap-at-level-2?
- No-add is the cleanest test: removes ALL pyramid behavior
- If no-add > baseline, then pyramid adds are net harmful
- If no-add ≈ baseline, then adds are neutral
- Cap-at-level-2 can be a secondary sensitivity in a future phase, but primary test is no-add

## EVERYTHING ELSE FROZEN

- BB(20,2), amount Top-10, STRICT_C exit
- K=3 concurrent positions
- initial_cash=1M, level_cash=200k (initial only)
- T+1, lot=100, tick=0.01
- Price limits, suspension, amount>0
- 10bp slippage, 0.025% commission min 5元, historical stamp tax
- PIT universe, ADV60 threshold
- ETF cash management enabled

## SUCCESS CRITERIA (preregister before running)

### H_S3 STRONGLY SUPPORTED
- No-add Total Return > baseline by >= 5pp
- No-add MaxDD materially better (< baseline by >= 5pp absolute)
- No-add Sharpe > baseline
- No-add PF > baseline
- Improvement not driven by single year

### H_S3 PARTIALLY SUPPORTED
- No-add ≈ baseline return but better risk-adjusted (Sharpe/MaxDD)
- OR no-add slightly worse return but much better drawdown
- OR no-add has similar return with significantly lower exposure (better efficiency)

### H_S3 NOT SUPPORTED
- No-add < baseline by >= 5pp (pyramid adds are net beneficial)
- OR no-add ≈ baseline in all metrics

## IMPORTANT CAVEATS

1. **Exposure reduction**: No-add will have lower average exposure (fewer lots deployed). Must distinguish "better because less exposure" from "better because better edge". Report exposure-adjusted metrics (return per unit exposure).
2. **Cash drag**: Less deployed capital means more cash in ETF money market. This is a real portfolio effect, not a confound.
3. **No compensation**: Do NOT increase initial position size to "compensate" for no adds. That would change two variables at once.
4. **Path dependence**: No-add changes cash availability, which changes which subsequent entries can be made. This is a legitimate portfolio effect.

## FORBIDDEN

- Do NOT test max_levels=1,2,3,4 as separate treatments (parameter grid search)
- Do NOT increase initial position size
- Do NOT change exit, K, ranking, costs, BB params
- Do NOT run without full preregistration approval

## NEXT STEPS

1. Full preregistration with exact metrics and success criteria
2. Approval to run
3. Run Control reproduction first (must match S2 Control)
4. Run No-add treatment
5. Compare and verdict
