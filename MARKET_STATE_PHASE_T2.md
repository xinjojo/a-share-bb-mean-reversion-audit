# PHASE T2 — MARKET-STATE EXPLANATION & PROSPECTIVE PREDICTABILITY
## STRICT_C / FROZEN TEMPORAL CLUSTERS — Discovery-only market-state audit

**Date:** 2026-09-03
**Registry commit:** `0d5979b` (registry committed BEFORE any outcome analysis)
**Registry SHA256:** `b6860158c25e694546d0b625180d01543b5e17d9f1a9639af7a8f374cf0c8407`
**Result commit:** (filled at delivery)
**Old 104-cell HYPOTHESIS_REGISTRY:** untouched (SHA256 `5c5e451ad4eb3afd5e632b0019a3e02103e58e375e03cc231c5d8ca52b8c5195`)

---

## 0. Scope & red lines (all enforced)

- **DISCOVERY ONLY** for all inference and gates: signal days 2020-02-06 → 2022-12-30 (n=666).
- **VALIDATION 2023-2024: CLOSED.** Not inspected, not used, not tabulated per-feature anywhere in this report.
- **RETROSPECTIVE CONFIRMATION 2025-2026: NOT opened** for any selection. Only a `DESCRIPTIVE_ONLY` full-sample file is emitted (clearly labeled, never used for gates).
- **No composite regime, no filter, no ML, no threshold search, no post-hoc variable addition.**
- The 2024-05-15→07-01 bad segment (Validation) was NOT inspected; only the Discovery segment 2021-12-13→2022-03-07 is explained.

---

## 1. Research question

Given T1 established STRONG TEMPORAL CLUSTERING (A) of oversold mean-reversion trade quality on the frozen STRICT_C sample, T2 asks:

- **Q1 (Explanation):** what *T-day* market state corresponds to historically good/bad performance clusters?
- **Q2 (Prospective predictability):** using only information available at T close (`X_t`), can we predict the quality of BB-oversold signals in the future window t+1..t+k?

The answer is reported as **statistical regularity in Discovery**, NOT as a tradable filter (T3 required, not executed).

---

## 2. Frozen sample

- PRIMARY (Top10, V2A_FROZEN_STRICT): 299 realized episodes.
- SECONDARY (all eligible, V2A_FROZEN_STRICT): 89,046 realized + 124 censored — **frozen**, loaded from `results/fullmarket_episode_metrics.csv`.
- Signal-day series: 1,494 signal days (2020-02-06 .. 2026-08-24); Discovery subset = **666** signal days.
- Outcome anchor: `signal_date`.

### Outcome definitions (per instruction §3)

- Same-day outcome `R_t` = cross-sectional mean of `simple_return_pct` over frozen SECONDARY episodes with that signal_date (also `r_med`, `win`, `loss`, `mae`, `hold`).
- **Prospective outcomes Y5/Y10/Y20/Y40** = mean final return of episodes whose signal_date falls in the next k signal days after t.
  - **PRIMARY horizon: Y20.**
  - **Discovery purity:** all prospective windows are FULLY WITHIN Discovery — a signal day t is included only if all k future signal days also fall in 2020-2022 (`d_{i+k} <= 2022-12-31`). No 2023+ episode return enters any Discovery Y*. 20 of 666 Discovery days are excluded from Y20 for this reason.
- `Y20_bad = (Y20 <= 0)`.

`X_t` uses only information known at T close (all features PIT; MRH leak-audited, §11).

---

## 3. Pre-registered feature set (frozen, 27 features / 7 families)

Full formulas in `TEMPORAL_STATE_FEATURE_REGISTRY.csv` (committed before analysis, SHA256 above).

| Family | Feature IDs |
|---|---|
| TREND | F01 ALL_A_EW_RET20, F02 ALL_A_EW_RET60, F03 CSI300_RET20, F04 CSI1000_RET20, F05 ALL_A_DISTANCE_MA20, F06 ALL_A_MA20_SLOPE |
| BREADTH | F07 BREADTH_MA20, F08 BREADTH_UP1D, F09 BREADTH_NEWLOW20, F10 BREADTH_BELOW_BB |
| VOLATILITY | F11 ALL_A_RV20, F12 ALL_A_RV60, F13 CROSS_SECTION_RET_STD, F14 DOWN_VOL_SHARE |
| LIQUIDITY | F15 MARKET_AMOUNT_RATIO20, F16 MARKET_AMOUNT_Z60, F17 MEDIAN_STOCK_AMOUNT_RATIO20 |
| STRESS | F18 LIMIT_DOWN_SHARE, F19 DROP5_SHARE, F20 DROP7_SHARE, F21 CROSS_SECTION_P10_RET |
| CROWDING | F22 N_OVERSOLD_SIGNALS, F23 OVERSOLD_SIGNAL_SHARE, F24 N_OVERSOLD_Z60 |
| MRH | F25 MRH_20_REALIZED, F26 MRH_60_REALIZED, F27 MRH_WIN20_REALIZED |

**Universe (frozen):** PIT-eligible non-ST A-shares on day t: `list_date + 60` trading days ≤ t (real list_date from stock_basic), not ST (PIT `pit_st_daily`), valid quote that day — identical to the frozen engine's `valid` mask. BJ stocks follow the frozen engine's universe/limit rules (0 BJ episodes in the sample anyway). Daily return = `close/pre_close − 1`. Adjusted price = `close × adj_factor` (per-day factor, frozen engine semantics).

**Expected directions (pre-registered):**
- POSITIVE: F01–F08 (trend, breadth MA20, breadth UP1D)
- NEGATIVE: F09, F10, F18, F19, F20, F22, F23, F24
- POSITIVE (weak prior): F15, F16, F17
- POSITIVE: F21, F25, F26, F27
- UNKNOWN: F11, F12, F13, F14

**Feature construction windows (frozen, see registry):** RET20/60, RV20/60, MA20, amount-MA20 all on strict past windows; `MARKET_AMOUNT_RATIO20` = today / mean(t-20..t-1); `MARKET_AMOUNT_Z60` & `N_OVERSOLD_Z60` = z over past 60 trading days `[t-60, t-1]` (NaN until 60d history, pre-registered); MRH uses only episodes with `exit_date <= t`.

---

## 4. Statistics contract (as implemented)

- **Prospective test (primary):** Spearman IC (rank correlation) of `X_t` vs `Y20_t`, significance via **Newey-West HAC t** on the rank regression `Y20_rank ~ 1 + X_rank`, **fixed lag = 20** (pre-registered). Sensitivity lags 5/10/40.
- **Multiple testing:** Benjamini-Hochberg FDR on the **m=27** Y20 p-values (primary family = 27 tests). Y5/Y10/Y40 ICs are sensitivity only.
- **PIT expanding quintiles:** boundaries from history strictly `< t`, ≥100 prior observations required (else NA). Primary forward-test table uses these.
- **BAD20 classification:** single-variable AUROC on the **pre-registered bearish orientation** (`bearish_score = X · d`, d=+1 if expected NEGATIVE, d=−1 if expected POSITIVE, d=+1 if UNKNOWN).
- **Block bootstrap:** moving/circular blocks, **L=21 signal days, B=2000**, on the PIT (label, Y20) daily pairs → 95% CI of Q5−Q1 Y20 spread. NaN-safe (empty-quintile draws set to NaN, `nanpercentile`).
- **Leave-one-year-out (LYO):** drop 2020 / 2021 / 2022 each, recompute Y20 IC direction.
- **MRH leak audit:** ≥100 sampled dates, assert `max(exit_date − feature_date) ≤ 0`.

### Statistical verification (independent cross-check)

| Check | Result |
|---|---|
| My NW HAC t (lag 20) vs `statsmodels` OLS HAC (maxlags=20) | max |Δ| ≈ 1e-14 (6 features sampled: F01/F02/F07/F18/F25/F12) |
| My BH-FDR vs `statsmodels.multipletests(method='fdr_bh')` | max |Δ| ≈ 3e-16, all 27 q equal |
| Feature sanity (Discovery means) | breadth_ma20 0.46, up1d 0.47, below_bb 0.048, drop5 0.039, limit_down 0.003, amt_ratio20 0.998, n_oversold 52.6 — all plausible |
| Discovery bad segment | 2021-12-13..2022-03-07 (53 signal days) matches T1 PELT/CUSUM break |

---

## 5. T2-A — Contemporaneous explanation (Discovery, X vs same-day R_t)

Top associations (Spearman):

| feature | name | spearman_R |
|---|---|---|
| F07 | BREADTH_MA20 | −0.255 |
| F05 | ALL_A_DISTANCE_MA20 | −0.248 |
| F10 | BREADTH_BELOW_BB | +0.238 |
| F09 | BREADTH_NEWLOW20 | +0.218 |
| F18 | LIMIT_DOWN_SHARE | +0.214 |
| F02 | ALL_A_EW_RET60 | −0.210 |
| F20 | DROP7_SHARE | +0.188 |
| F01 | ALL_A_EW_RET20 | −0.184 |
| F22 | N_OVERSOLD_SIGNALS | +0.178 |

**Reading:** on the same day, "weaker" market states (more stocks below BB lower, more new 20-day lows, more limit-downs, lower breadth, lower index trend) coincide with **better** oversold-episode quality; "stronger" states coincide with worse quality. Full table: `results/t2_contemporaneous.csv`.

---

## 6. T2-B — Prospective predictability (Discovery, X_t → Y20)

**Master table:** `results/t2_master_table.csv` (all 27 rows, full column set).

### Headline

| Statistic | Value |
|---|---|
| Discovery signal days | 666 |
| Y20-valid days | 646 |
| Y20 mean / median | +5.59% / +5.76% |
| BAD20 rate (Y20 ≤ 0) | 1.80% |
| Features with **Y20 BH q < 0.05** | **7** |
| **DISCOVERY_PASS** | **0 / 27** |
| **BAD_STATE_PASS** | **0 / 27** |

### The 7 BH-significant features — ALL in the pre-registered-OPPOSITE direction

| feature | family | expected | Y20_IC | HAC t (lag20) | raw p | BH q | Q5−Q1 Y20 (pp) | LYO dir |
|---|---|---|---|---|---|---|---|---|
| F02 ALL_A_EW_RET60 | TREND | POS | **−0.441** | −4.16 | 3.2e-5 | **0.0009** | −3.20 | 0/3 |
| F01 ALL_A_EW_RET20 | TREND | POS | −0.332 | −2.71 | 0.0067 | 0.0473 | −2.66 | 0/3 |
| F06 ALL_A_MA20_SLOPE | TREND | POS | −0.331 | −2.62 | 0.0088 | 0.0473 | −2.36 | 0/3 |
| F08 BREADTH_UP1D | BREADTH | POS | −0.089 | −2.71 | 0.0068 | 0.0473 | −1.05 | 0/3 |
| F18 LIMIT_DOWN_SHARE | STRESS | NEG | **+0.192** | +2.69 | 0.0071 | 0.0473 | +1.68 | 0/3 |
| F21 CROSS_SECTION_P10_RET | STRESS | POS | −0.118 | −2.55 | 0.0107 | 0.0482 | −0.91 | 0/3 |
| F07 BREADTH_MA20 | BREADTH | POS | −0.285 | −2.49 | 0.0128 | 0.0495 | −2.29 | 0/3 |

(`LYO dir` = number of the 3 leave-one-year-out ICs with sign matching the **expected** direction; 0/3 means the reverse sign is consistent in ALL three year-drops.)

### Interpretation of the Discovery result — must be read carefully

- **Zero hypotheses survived the pre-registered directional gate.** The pre-registered POSITIVE trend/breadth/liquidity hypotheses and NEGATIVE stress/crowding hypotheses are **REJECTED** in Discovery.
- **A robust REVERSE regularity exists:** rising market trend / broad participation / fewer limit-downs / higher cross-section P10 **predict worse** future 20-day mean-reversion quality; falling/stressed conditions predict **better** quality. This is consistent across all three leave-one-year-out drops (LYO dir 0/3 = reverse sign everywhere) and in the full-sample DESCRIPTIVE_ONLY file.
- **By the pre-registration discipline, this reverse association is NOT a "discovery pass".** Declaring it a pass would mean flipping directions after seeing Discovery data — the exact data-snooping the protocol forbids. It is reported as a **NEW MATERIAL FINDING** requiring its own fresh preregistration and Validation before any further use.
- **Economic plausibility (reported as hypothesis, not conclusion):** this is a contrarian dip-buying signal family; in Discovery it benefits from market stress/rebounds and suffers when the few oversold names in strong markets are persistent underperformers ("falling knives").

### Quintile forward test (PIT expanding, ≥100 prior obs) — example F02 ALL_A_EW_RET60

| quintile | n_days | mean Y20 | median Y20 | bad rate |
|---|---|---|---|---|
| Q1 (lowest RET60) | 143 | +7.28% | +7.15% | 0.0% |
| Q2 | 93 | +5.22% | +5.55% | 0.0% |
| Q3 | 98 | +4.67% | +4.32% | 10.2% |
| Q4 | 123 | +5.31% | +5.15% | 1.6% |
| Q5 (highest RET60) | 59 | +4.07% | +4.08% | 0.0% |

Monotone-ish **decreasing** in RET60 (reverse of pre-registered expectation). Full 5-quintile tables for all features: `results/t2_quintiles_pit.csv`.

---

## 7. Bad-state detection (BAD20, AUROC, bearish orientation)

- **Best discriminator: F25 MRH_20_REALIZED** — BAD20_AUC = **0.753**, worst-quintile bad rate 2.86% vs best-quintile 0.0%, Q5−Q1 Y20 spread +2.25pp, LYO dir 3/3, block-bootstrap CI [+0.91, +3.82]. **However its Y20 BH q = 0.209 > 0.05 → fails the pre-registered q gate → NOT BAD_STATE_PASS.**
- F26 MRH_60_REALIZED: AUC 0.705, q = 0.415 → fails q.
- F11 ALL_A_RV20 (UNKNOWN): AUC 0.135 (i.e., high vol → *not* bad in Discovery), q = 0.356.
- No feature passes BAD_STATE_PASS. `results/t2_badstate_auc.csv`.

Note the low base rate: BAD20 (Y20≤0) occurs on only 1.8% of Discovery signal days, so worst-quintile bad rates of 2-4% represent meaningful relative lift but tiny absolute levels.

---

## 8. Leave-one-year-out (LYO)

- Reverse-sign findings (F01/F02/F06/F07/F08/F18/F21/F09/F19/F20) show reverse direction in ALL three year-drops → **not a single-year artifact**.
- UNKNOWN-direction features (F11-F14) show positive Y20 IC in all three drops (e.g., F14 DOWN_VOL_SHARE +0.12).
- `results/t2_leave_one_year_out.csv`.

---

## 9. Feature redundancy

19 pairs with |Spearman| > 0.85 in Discovery (`results/t2_feature_redundancy_pairs.csv`). Notable:
- Same-family: TREND F01-F04/F06, BREADTH F09-F10, LIQUIDITY F15-F17, STRESS F18-F20/F19-F20, CROWDING F22-F23-F24.
- Cross-family (market-state dimensions co-move): F05-F07 (dist_ma20 vs breadth_ma20, ρ=0.98), F08-F21, F09/F10-F22/F23 (new-lows & below-BB vs oversold crowding), F14-F19-F21 (down-vol vs drops vs P10).

Per protocol: no variable dropped; this is flagged so that T3 (if ever) keeps one representative per correlated family and does not feed the full set into a composite.

---

## 10. MRH leak audit (PIT)

- 120 sampled Discovery dates; all used episodes have `exit_date <= feature_date`.
- `max(exit_date − feature_date) = 0` days → **NO future leak in MRH construction** (P0 gate passed).
- `results/t2_mrh_leak_audit.csv`.

---

## 11. Discovery bad segment explanation (2021-12-13 → 2022-03-07, 53 signal days)

T1 located the longest negative performance segment here. Discovery feature profile vs the rest of Discovery:

| feature | name | in-segment mean | outside mean | delta |
|---|---|---|---|---|
| F04 | CSI1000_RET20 | −2.89% | +0.57% | −3.45pp |
| F03 | CSI300_RET20 | −2.37% | +0.11% | −2.48pp |
| F01 | ALL_A_EW_RET20 | −0.16% | +0.90% | −1.06pp |
| F22 | N_OVERSOLD_SIGNALS | 67.3 | 51.3 | +16.0 |
| F25 | MRH_20_REALIZED | 10.77% | 11.95% | −1.18pp |
| F16 | MARKET_AMOUNT_Z60 | −0.69 | +0.07 | −0.75 |
| F02 | ALL_A_EW_RET60 | +5.41% | +2.60% | +2.82pp |

**Factual profile:** the bad segment was an early-stage top (60-day trend still positive, 20-day turning negative), with **elevated oversold crowding, deteriorating realized strategy performance (MRH), and shrinking liquidity**. This is a descriptive observation of the Discovery bad period only — it is NOT used to build any filter, and it highlights that the simple "down market ⇒ good" reverse regularity does NOT hold uniformly (this specific down-drawdown was bad), i.e., the reverse IC is driven by other sub-periods (e.g., crash/rebound episodes) and the bad-state is better characterized by crowding + MRH deterioration than by trend alone. Full table: `results/t2_discovery_badsegment_explanation.csv`.

---

## 12. Full-sample 2020-2026 (DESCRIPTIVE ONLY — not for selection)

`results/t2_fullsample_DESCRIPTIVE_ONLY.csv`. The reverse-direction pattern persists through the full sample (e.g., BREADTH_MA20 vs Y20 Spearman −0.21, LIMIT_DOWN_SHARE +0.21, RET60 −0.25). This file and these numbers were **not** used to set any threshold or direction, and 2023-2024 Validation is not tabulated per-feature anywhere.

---

## 13. PRIMARY sensitivity

0 DISCOVERY_PASS features → no PRIMARY rows by construction (`results/t2_primary_sensitivity.csv` contains an explicit NONE note). PRIMARY Top10 (n=299) is intentionally not used for feature selection; its role is limited to direction checks for any future pass, per protocol.

---

## 14. Final classification

### **C — TEMPORAL CLUSTERING NOT EXPLAINED BY PRE-REGISTERED MARKET FEATURES**

Rationale:
1. **0 / 27 DISCOVERY_PASS** and **0 / 27 BAD_STATE_PASS** under the fully pre-registered directional gates.
2. The pre-registered directional hypotheses (trend/breadth/liquidity POSITIVE; stress/crowding NEGATIVE) are **rejected** in Discovery.
3. A **statistically robust reverse-direction regularity** exists (7 features BH q<0.05, LYO-consistent, full-sample-consistent), but per protocol it **cannot** be upgraded to a pass — that would be post-hoc direction flipping.

**Documented new finding (for a future, separately-preregistered branch):**
> In Discovery 2020-2022, stronger market states (higher index trend, higher breadth, fewer limit-downs) prospectively predict **worse** future 20-day oversold mean-reversion quality, and stressed states predict better quality — the **opposite** of the pre-registered expectation. The best single bad-period discriminator is the strategy's own recent realized performance (MRH_20, BAD20 AUC 0.75), which nonetheless fails the q<0.05 gate.

**Bottom line for the research question:** T1's temporal clustering exists and is strong, but **none of the 27 pre-registered market-state variables prospectively identifies the bad periods** under the pre-registered direction/gates. We therefore do **not** yet have a validated, forward-looking market-state explanation.

---

## 15. What this means for next steps (NOT executed here)

- **T3 (Frozen Composite Market-State Model) is NOT authorized by this result.** With 0 discovery-pass features, there is no positive set to composite.
- Any future branch wishing to exploit the **reverse-direction** regularity must: (a) write a NEW feature registry with the reversed directional hypotheses pre-registered **before** looking at Discovery again; (b) re-run Discovery; (c) open Validation only with external-audit approval.
- This step does not modify the strategy, the 104-cell Registry, any threshold, or any result from prior phases.

---

## 16. Red lines compliance

- ✅ Validation 2023-2024 not opened; 2025-2026 used only in `DESCRIPTIVE_ONLY` file.
- ✅ 2024-05→07 Validation bad segment not inspected.
- ✅ Registry 104 cells unchanged (SHA256 verified).
- ✅ No strategy / stop / exit / parameter modification.
- ✅ No ML, no composite, no threshold search.
- ✅ Registry committed (0d5979b) before outcome analysis.
- ✅ HAC & BH independently cross-validated against statsmodels.
- ✅ MRH leak audit clean (P0 gate passed).
