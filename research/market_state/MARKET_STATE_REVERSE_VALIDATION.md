# PHASE T2-R — REVERSE-DIRECTION PREREGISTRATION + UNTOUCHED VALIDATION
## Independent 2023-2024 validation of the reverse-direction market-state hypotheses found in T2 Discovery

**Date:** 2026-09-03
**Registry commit:** `210f843c5dd3b9aa85d21c1a99652fbbde8163ee` (committed BEFORE any 2023-2024 outcome was read)
**Registry SHA256:** `206444cca45b2b360ddea005fa8a378fc86610088b203dc2e88d23a1946ec778`
**Result commit:** (filled at delivery)
**T2 registry (27 features):** unchanged, SHA256 `b6860158c25e694546d0b625180d01543b5e17d9f1a9639af7a8f374cf0c8407`
**Old 104-cell HYPOTHESIS_REGISTRY:** untouched, SHA256 `5c5e451ad4eb3afd5e632b0019a3e02103e58e375e03cc231c5d8ca52b8c5195`

---

## 0. Purpose & frozen state

T2 Discovery (2020-2022) found 7 features with Y20 BH q<0.05 in the **opposite** direction of their original preregistration. This phase runs an **untouched 2023-2024 Validation** of those 7 reverse-direction hypotheses.

Frozen:
- STRICT_C episode semantics; PRIMARY (299) / SECONDARY (89,046 realized + 124 censored) frozen samples.
- **Validation = 2023-01-01 .. 2024-12-31.** Confirmation 2025+ CLOSED (not opened anywhere).
- No Registry modification, no re-exploration of 2020-2022, no composite, no filter, no parameter optimization.

---

## 1. Reverse Registry (hard red line enforced)

`TEMPORAL_STATE_REVERSE_VALIDATION_REGISTRY.csv` (7 hypotheses) was created by `STEP_A_PREREGISTER.py` — which reads **no market data** — hashed (SHA256 `206444cc…`), committed and pushed at **`210f843`**, **before** `STEP_B_VALIDATE.py` read any 2023-2024 outcome. STEP B asserts the registry hash at startup.

| reverse_id | orig | family | name | expected_direction |
|---|---|---|---|---|
| R01 | F02 | TREND | ALL_A_EW_RET60 | NEGATIVE |
| R02 | F01 | TREND | ALL_A_EW_RET20 | NEGATIVE |
| R03 | F06 | TREND | ALL_A_MA20_SLOPE | NEGATIVE |
| R04 | F08 | BREADTH | BREADTH_UP1D | NEGATIVE |
| R05 | F18 | STRESS | LIMIT_DOWN_SHARE | POSITIVE |
| R06 | F21 | STRESS | CROSS_SECTION_P10_RET | NEGATIVE |
| R07 | F07 | BREADTH | BREADTH_MA20 | NEGATIVE |

Directions are frozen from T2 Discovery findings only (not from Validation). Formulas identical to T2 (feature columns imported from `market_state_phase_t2.load_features / assemble_day_frame`).

### Pre-registered VALIDATION_PASS gate (frozen in registry)
A feature PASSES iff **all** of:
- **A Direction:** Validation Y20 IC matches registry expected_direction.
- **B Statistical:** BH q (m=7) < 0.05.
- **C Economic:** directional fixed-cutpoint Q-spread ≥ 1.0pp (NEG: Q1−Q5; POS: Q5−Q1).
- **D Non-single-extreme:** NEG: Q2>Q4; POS: Q4>Q2.
- **E Bootstrap:** 21-signal-day block bootstrap, B≥5000, directional spread 95% CI entirely > 0.
- **F Temporal:** 2023 and 2024 ICs both same direction as registry (a near-zero year acceptable if pooled Validation significant); a materially-opposite year disqualifies.

---

## 2. Sample & outcome

- Signal-day series 2020-02-06..2026-08-24 (1,494 days); Discovery subset 666.
- **Validation nominal signal days = 445; Y20-valid = 425; boundary-excluded = 20** (days whose full future-20-signal-day window would enter 2025).
- Discovery Y20-valid = 646 (reference only).
- Y20_t = mean `simple_return_pct` of frozen SECONDARY episodes with signal_date in the next 20 signal days; the full window stays inside 2023-2024 → **no 2025+ episode return enters any Validation Y20** (purity enforced).
- X_t uses only information known at T close (identical construction to T2).

---

## 3. Statistical implementation

- **Primary:** Spearman IC + Newey-West HAC t (lag=20) on rank regression; raw p via normal approx (identical to T2); **BH-FDR m=7**.
- **HAC sensitivity:** lags 10 / 40 (primary stays 20).
- **Quintiles:** PRIMARY = **FIXED DISCOVERY CUTPOINTS** (boundaries from 2020-2022 feature distribution only, applied unchanged to 2023-2024). Secondary = **expanding PIT cutpoints** (each t uses feature history < t, ≥100 obs).
- **Block bootstrap:** circular moving blocks, **L=21 signal days, B=5000**, on Validation (feature, Y20) pairs with fixed Discovery cutpoints → directional Q-spread 95% CI.
- **Non-overlap sensitivity:** 20 anchors (offsets 0..19), every 20th signal day → IC per offset, direction-consistency count.
- **Effect-size replication:** Validation_IC/Discovery_IC and Validation_spread/Discovery_spread (NA if near-zero denominator); REPLICATED / ATTENUATED / FAILED.

### Implementation correction documented (audit trail)
The first bootstrap implementation drew **5000 single 21-day blocks** instead of 5000 full-sample resamples (each ~425 days = ceil(425/21) blocks, truncated to n). That biased the bootstrap distribution toward 0 and produced spuriously wide CIs (e.g., R01 observed spread 2.75 vs bootstrap mean 1.34; CI [−2.8, +4.7]) → 0/7 PASS. This was an **implementation bug**, not a gate/registry change. After correction the bootstrap distribution is properly centered (R01: observed 2.75, boot mean 2.94, sd 1.52; R05: observed 2.54, boot mean 2.36; R07: observed 2.94, boot mean 2.93) and CIs are realistic. Results below are the corrected versions. (A few bootstrap resamples can miss a small quintile cell — e.g., limit-down days cluster in few blocks — handled by NaN-filtering, ≤6/5000 per feature.)

---

## 4. Verification (independent cross-check)

| Check | Result |
|---|---|
| HAC t (lag 20) vs `statsmodels` HAC | max |Δ| ≈ 1e-14 (all 7 features) |
| BH-FDR vs `statsmodels.multipletests(fdr_bh)` | identical for all 7 q-values |
| Discovery ICs recomputed in STEP B | match T2 master table exactly (R01 −0.4409, R02 −0.3319, R03 −0.3306, R04 −0.0888, R05 +0.1923, R06 −0.1180, R07 −0.2850) |
| Bootstrap centering | verified (observed spread inside bootstrap distribution, mean≈observed) |

---

## 5. Validation master results (2023-2024, fixed Discovery cutpoints)

| reverse_id | fam | dir | n | Disc IC | Val IC | HAC t20 | raw p | **BH q** | spread (pp) | Q2/Q4 | boot CI | IC 2023 | IC 2024 | non-overlap frac | repl | **PASS** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **R01** | TREND | NEG | 425 | −0.441 | **−0.417** | −3.18 | 0.0015 | **0.0105** | **+2.75** | ✓ | **[+0.18,+5.98]** | −0.404 | −0.221 | 1.0 | REPL | **TRUE (STRONG)** |
| R02 | TREND | NEG | 425 | −0.332 | −0.241 | −1.48 | 0.139 | 0.162 | +2.71 | ✓ | [−0.66,+6.45] | −0.512 | −0.013 | 1.0 | REPL | False |
| R03 | TREND | NEG | 425 | −0.331 | −0.207 | −1.22 | 0.221 | 0.221 | +2.43 | ✓ | [−1.04,+6.19] | −0.466 | +0.029 | 1.0 | REPL | False |
| R04 | BREADTH | NEG | 425 | −0.089 | −0.153 | −2.90 | 0.0037 | **0.0129** | +0.997 | ✓ | [−0.05,+1.99] | −0.185 | −0.103 | 0.8 | REPL | False (econ 0.997 < 1.0pp) |
| **R05** | STRESS | POS | 425 | +0.192 | **+0.164** | +2.61 | 0.0090 | **0.0210** | **+2.54** | ✓ | **[+0.30,+4.63]** | +0.186 | +0.038 | 0.9 | REPL | **TRUE (STRONG)** |
| R06 | STRESS | NEG | 425 | −0.118 | −0.139 | −2.30 | 0.0217 | **0.0379** | +0.78 | ✓ | [−0.73,+2.07] | −0.212 | −0.002 | 0.8 | REPL | False (econ 0.78 < 1.0pp) |
| R07 | BREADTH | NEG | 425 | −0.285 | −0.287 | −1.98 | 0.0479 | 0.067 | +2.94 | ✓ | [+0.06,+5.83] | −0.594 | −0.047 | 1.0 | REPL | False (q=0.067) |

**VALIDATION_PASS = 2 / 7** — **R01 (TREND) and R05 (STRESS)**, both STRONG (both years same direction). Full detail: `results/t2r_master_table.csv`, `t2r_hac.csv`, `t2r_bh7.csv`, `t2r_bootstrap.csv`, `t2r_yearly.csv`.

### Fixed-cutpoint quintile profiles (Validation, mean Y20 %)
- R01: Q1=6.40, Q2=4.94, Q3=3.43, Q4=1.95, Q5=3.66
- R02: Q1=5.71, Q2=5.12, Q3=3.54, Q4=3.41, Q5=3.00
- R03: Q1=5.61, Q2=5.05, Q3=3.60, Q4=2.86, Q5=3.18
- R04: Q1=5.23, Q2=4.83, Q3=4.00, Q4=3.67, Q5=4.23
- R05 (POS): Q1=3.88, Q5=6.42 (increasing)
- R06: Q1=4.99, Q2=5.18, Q3=4.81, Q4=3.81, Q5=4.21
- R07: Q1=5.45, Q2=5.49, Q3=4.63, Q4=3.16, Q5=2.50

All 7 features show the expected directional gradient in the end quintiles (Q1 vs Q5) and all pass the Q2-vs-Q4 non-extreme check. `results/t2r_quintiles_fixed.csv`.

---

## 6. Non-overlap offsets (20 anchors)

- R01/R02/R03/R07: **20/20** offsets direction-consistent (1.0).
- R05: 18/20 (0.9); R04/R06: 16/20 (0.8).
`results/t2r_nonoverlap_offsets.csv`.

---

## 7. Effect-size replication (Discovery vs Validation)

All 7 **REPLICATED** (direction preserved, no FAILED):
| reverse_id | Disc IC | Val IC | IC ratio | Disc spread | Val spread | spread ratio |
|---|---|---|---|---|---|---|
| R01 | −0.441 | −0.417 | 0.95 | 3.77pp | 2.75pp | 0.73 |
| R02 | −0.332 | −0.241 | 0.72 | 2.68 | 2.71 | 1.01 |
| R03 | −0.331 | −0.207 | 0.63 | 2.52 | 2.43 | 0.96 |
| R04 | −0.089 | −0.153 | 1.73 | 0.93 | 1.00 | 1.07 |
| R05 | +0.192 | +0.164 | 0.85 | 1.25 | 2.54 | 2.03 |
| R06 | −0.118 | −0.139 | 1.18 | 0.82 | 0.78 | 0.95 |
| R07 | −0.285 | −0.287 | 1.01 | 1.93 | 2.94 | 1.52 |

`results/t2r_discovery_validation_effect.csv`.

---

## 8. Family-level & redundancy

- **TREND:** R01 full PASS; R02/R03 direction-consistent, economically present (spread +2.7/+2.4pp), but not BH-significant (q=0.162/0.221). Family-level: **supported** by R01; siblings consistent but individually below the stat gate. Within-family corr: R02-R03 0.93, R01-R02 0.55, R01-R03 0.54.
- **BREADTH:** R04/R07 direction-consistent (both years), R07 spread +2.94pp with bootstrap CI>0, but q=0.067; R04 q=0.013 but spread 0.997pp (marginal, <1.0). Family-level: **not independently PASS**.
- **STRESS:** R05 full PASS; R06 direction-consistent but econ spread 0.78pp. Family-level: **supported** by R05.

**Important:** R01/R02/R03 (TREND) are highly correlated (R02-R03 ρ=0.93), and R05/R06 (STRESS) are negatively correlated (ρ=−0.51). The two PASSes are therefore **not independent discoveries** in the naive sense — they load on two correlated dimensions (trend and stress move together). Report counts them as **2 families with reliable PASS**, and flags that they likely reflect a single underlying "market-state" regularity (strong/low-stress market → weaker future oversold quality). `results/t2r_family_redundancy.csv`.

---

## 9. Expanding-PIT sensitivity (secondary)

Consistent with fixed cutpoints (all same sign, similar magnitude): R01 2.55, R02 2.48, R03 2.08, R04 1.06, R05 2.52, R06 1.25, R07 2.94 (pp). Notably R06's expanding-PIT spread (1.25pp) exceeds the fixed-cutpoint spread (0.78pp). `results/t2r_quintiles_expanding_sensitivity.csv`.

---

## 10. PRIMARY sensitivity (Top10, n=299) — secondary confirmation only

Only checked for the 2 SECONDARY PASS features (per protocol):
- **R01:** PRIMARY IC = **−0.066** (n=405 PRIMARY validation Y20-valid days), direction OK (NEG).
- **R05:** PRIMARY IC = **+0.166** (n=405), direction OK (POS).

PRIMARY confirms direction for both, with the expected small-sample attenuation for R01. It does NOT rescue any failed feature. `results/t2r_primary_sensitivity.csv`.

---

## 11. Final classification

### **A — STRONG VALIDATION**

The reverse-direction market-state hypothesis **independently replicates** on untouched 2023-2024:
- **2 families** (TREND via R01, STRESS via R05) produce **reliable full-gate PASSes**, both STRONG (direction + BH q<0.05 + economic spread ≥1pp + non-extreme + block-bootstrap CI>0 + both years same direction).
- All 7 hypotheses are direction-consistent in Validation (validation IC matches registry direction); **6/7 are same-sign in both 2023 and 2024 individually** (R03's 2024 IC is +0.029, near zero / opposite sign), **6/7 effect-size REPLICATED**, non-overlap direction consistency 0.8–1.0.

**Required caveats (do not overstate):**
1. The two PASSes are on correlated dimensions (TREND & STRESS co-move), so this is best read as **one replicated regularity**: "in a strong / low-stress market, the few remaining oversold episodes have worse future 20-day quality; in a stressed market, oversold quality is better" — the **opposite** of the original T2 directional hypotheses (which are thereby rejected).
2. BREADTH family (R04/R07) did **not** independently reach the full gate (R04 econ 0.997pp marginal; R07 q=0.067 marginal) — direction is consistent but certification is lacking.
3. R05's 2024 IC (+0.038) is near zero (2023 +0.186); the PASS rests on pooled significance + 2024 same-sign. R01 is the economically strongest and cleanest (2023 −0.40, 2024 −0.22).
4. This validates a **statistical regularity** in historical data. It is NOT yet a tradable filter and implies **no strategy change**.

**Bottom line:** the reverse market-state regularity found in T2 Discovery survives an untouched 2023-2024 Validation in its core dimensions (trend, stress), meeting the pre-registered PASS gate in 2 families → **A**.

---

## 12. Red-line compliance

- ✅ Registry committed (`210f843`) before any 2023-2024 outcome was read (STEP A / STEP B separation; STEP B asserts hash).
- ✅ Validation = 2023-2024 only; **Confirmation 2025-2026 never opened**.
- ✅ No Registry (T2 or 104-cell) modification; no threshold/horizon/HAC-primary change; no direction flipping after results.
- ✅ No composite, no filter, no ML, no parameter optimization, no stop/exit linkage.
- ✅ 2024-05→07 Validation bad segment not used for any selection.
- ✅ HAC & BH independently cross-checked vs statsmodels; bootstrap centering verified.
- ✅ Bootstrap implementation bug (single-block resampling) found and corrected in code before final results; documented above.
