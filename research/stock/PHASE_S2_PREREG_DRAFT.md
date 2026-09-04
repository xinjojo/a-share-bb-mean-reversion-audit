# S2 PREREGISTRATION DRAFT — Ranking-Neutral Selection Hypothesis

**Status**: DRAFT ONLY — NOT APPROVED, DO NOT RUN
**Created**: 2026-09-04 (S1.1)
**Predecessor**: S1 = MULTI-COMPONENT EDGE (confirmed with corrections), S1.1 = S1 CONFIRMED WITH CORRECTIONS

---

## HYPOTHESIS

> **H_S2**: Among frozen BB-oversold stock candidates, amount-descending selection reduces expected return relative to a ranking-neutral selection rule.

## RATIONALE (from S1/S1.1 confirmed findings)

1. Amount ranking is HARMFUL: Top-N amount 20d mean +0.04% vs all signals +2.71%
2. Daily percentile = 43.1% (only 42.3% of days beat random median)
3. Amount-selected stocks (official traded) have weaker raw signal: 20d +1.39% vs full panel +2.71%
4. Amount ranking selects larger, more liquid stocks which may have weaker mean reversion

## TREATMENT DESIGN (to be finalized)

### Control
- Frozen G0 baseline: BB(20,2), amount Top-10, STRICT_C exit, K=3 concurrent, max_levels=5, 200k/lot, 1M initial, 10bp slippage, 0.025% commission min 5元

### Treatment (SINGLE alternative, must choose ONE before running)

**Option A: Fixed-seed random Top-N**
- Same candidate set, same N=10, same day
- Random selection with fixed seed (preregistered)
- 1000 repetitions to get distribution, compare actual amount vs random distribution

**Option B: Equal-weight all eligible signals (no Top-N cap)**
- Invest equally in ALL eligible BB-oversold candidates each day
- Position size = available cash / number of signals (with lot rounding)
- This removes ranking AND Top-N cap (confounds two changes — NOT recommended)

**Option C: BB_Z ascending Top-N**
- Rank by deepest oversold (most negative BB_Z) instead of amount
- This was tested for ETF in E4 and found HARMFUL — but stock may differ
- Risk: confounds "remove amount" with "add BB_Z"

### RECOMMENDED: Option A (fixed-seed random)
- Cleanest test: removes amount ranking without introducing a new ranking factor
- Directly answers "is amount ranking worse than no ranking?"
- Lowest degree of freedom
- If random beats amount, then amount is actively harmful
- If random ≈ amount, then amount is neutral (not harmful)

## EVERYTHING ELSE FROZEN

- BB window=20, sigma=2
- Entry signal: close < bb_lower
- Exit: STRICT_C (upper band / Pstar)
- K=3 concurrent positions
- max_levels=5 lots
- level_cash=200k
- initial_cash=1M
- T+1 execution
- 100-unit lot
- 0.001 tick
- Price limits, suspension, amount>0
- 10bp slippage, 0.025% commission min 5元
- PIT universe
- ADV60 liquidity threshold

## SUCCESS CRITERIA (preregister before running)

### H_S2 STRONGLY SUPPORTED
- Random Top-N portfolio total return > amount Top-N by >= 5pp
- Random PF > amount PF
- Random daily percentile distribution centered > 50%
- Improvement not driven by single year

### H_S2 PARTIALLY SUPPORTED
- Random ≈ amount (within 2pp), but amount daily percentile < 45% confirms amount is weakly harmful
- OR random beats amount but improvement < 5pp

### H_S2 NOT SUPPORTED
- Random ≈ amount and amount daily percentile ~50% (amount is neutral)
- OR amount beats random (amount is helpful)

## FORBIDDEN
- Do NOT test multiple selection rules and pick best
- Do NOT change exit, K, pyramid, costs, BB params
- Do NOT use this as justification to switch to BB_Z or any other ranking
- Do NOT run without full preregistration approval

## NEXT STEPS
1. Finalize treatment choice (recommend Option A)
2. Full preregistration with exact seed, exact metrics
3. Approval to run
4. Run Control reproduction first (must match G0)
5. Run Treatment
6. Compare and verdict
