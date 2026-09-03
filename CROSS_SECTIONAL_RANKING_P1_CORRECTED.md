# CROSS-SECTIONAL RANKING — PHASE P1.1 (IMPLEMENTATION CORRECTION)

**Status:** Discovery re-run after implementation corrections. 2023–2024 Ranking Validation
**CLOSED**. 2025–2026 Confirmation **CLOSED**. Registry unchanged.

---

## 0. Freeze state

| Item | Value |
|---|---|
| Registry | `CROSS_SECTIONAL_RANKING_REGISTRY.csv` (commit `9c36887`, SHA `fa5beb5a9a952442be2a359b95347388ff082c06fa36b56cf8f6eee477bab819`) — **not modified** |
| P1 original result commit | `4f1fb01` |
| P1.1 result commit | see end of this file |
| Sample | SECONDARY frozen V2A_FROZEN_STRICT, Discovery signal_date 2020-01-01 ~ 2022-12-31 |
| Episodes / signal days | 35,009 / 666 (usable days for K3 selection: 593 with ≥3 signals) |
| Primary test | per-day cross-sectional Spearman IC; HAC lag 10 (sens 20); block bootstrap L=21, B=2000; BH-FDR m=17 |
| Red lines | no new predictor, no gate/threshold change, no composite, no portfolio backtest, no ML |

---

## 1. Corrections applied

| # | Auditor item | Implementation |
|---|---|---|
| 1 | Gate A must use **BH q** (m=17) not raw p | `gateA = bh_q < 0.05`; old/new pass diff emitted |
| 2 | Random K3 must be **without replacement** | `RNG.choice(n, size=3, replace=False)`, seed fixed, B=5000 |
| 3 | K3-lift block bootstrap full-length + centering | point, bootstrap mean, 95% CI all output; |boot_mean − point| checked |
| 4 | Pairwise ties explicit + Discovery/frozen orientation | `ties_excluded` counted; UNKNOWN→Discovery IC sign, POSITIVE/NEGATIVE→Registry direction |
| 5 | REL_RET rank-invariance | formally proven + empirically identical; see `P1_RELATIVE_RETURN_INVARIANCE_NOTE.md` |
| 6 | PRIMARY renamed | `PRIMARY_POOLED_DIRECTION_SENSITIVITY` (pooled Spearman), no longer called a daily CS IC |
| 7 | Suspension/observation-window audit | 20-obs window vs market-day span, gap quantification + exclusion sensitivity |
| 8 | Passer redundancy | 5×5 same-day avg rank corr + economic grouping (Group A / Group B) |
| 9 | Quintile dual metrics | `positive_day_fraction` and `equal_day_mean_episode_win_rate_pct` reported separately |
| 10 | Oracle common usable-day set, no replacement | oracle & random K3 on identical usable-day set (n≥3) |
| 11 | Top10 turnover wording | limited to "no superior within-day quality" |
| 12 | Final gate | Registry gates A–F recomputed |
| 13 | **Additional fix found in audit (disclosed)** | daily IC series were gated at ≥2 valid pairs, not the frozen Registry's ≥5-signal rule; corrected to `valid ≥ 5` before appending a day's IC |

---

## 2. Correction 13 disclosure (found during this re-run)

The original P1 script (and the first P1.1 draft) appended a day's cross-sectional IC whenever
Spearman was finite (≥2 valid pairs), **not** when the day had ≥5 valid signals as the frozen
Registry requires (`per-day ≥5 signals 才计 IC`). Fixed in the corrected script. Effect: mean |IC|
strengthened slightly (e.g., F04 −0.051→−0.068, F07 −0.068→−0.082, F09 +0.088→+0.094,
F13 +0.056→+0.086). No robust passer was added or removed by this fix alone.

---

## 3. Correction-by-correction results

### 3.1 Gate A (raw p → BH q) — pass-set change

`OLD_PASS = [F04, F06, F07, F09, F13]`  (5)
`NEW_PASS = [F04, F05, F06, F07, F09, F13]` (6)

- The raw-p → BH-q substitution **itself changed no A-gate status**: in the corrected run every
  feature with raw p < 0.05 also has BH q < 0.05.
- The pass-set change is **F05 (RET5) newly passing gate E** (K3-lift bootstrap CI lower bound).
  F05's K3-lift CI lower bound is **razor-thin**: median +0.010pp across 30 bootstrap seeds, and
  it clears 0 in only **26/30** seeds (range −0.019…+0.048). Under the original P1 run's bootstrap
  path it was −0.031 (failed). **F05 is therefore a borderline, non-robust passer — treat it as
  marginal, not as an independent discovery.**

### 3.2 Random K3 without replacement (correction 2)

| | old (with replacement) | corrected (no replacement) |
|---|---|---|
| random K3 mean | 4.3785 pp | **4.3773 pp** |
| 2.5/97.5 pct | [3.9467, 4.8199] | **[3.9849, 4.7793]** |
| usable-day all-signal mean | 4.3757 pp | 4.3757 pp |

Δmean ≈ −0.001pp; band narrower by ≈0.04pp each side. **Materially unchanged.**

### 3.3 K3-lift block bootstrap centering (correction 3)

All 17 features: `|bootstrap_mean − point_estimate| < 0.05pp` (max 0.042). Full-length
moving-block resampling confirmed; no centering pathology.

### 3.4 Pairwise ties (correction 4)

Ties (dx==0 or dr==0) are tiny for continuous predictors (≤40 sampled pairs) and only material for
discrete/zero-heavy variables: F12 CLOSE_LOCATION 12,769 and F14 GAP 17,626 ties (both fail gate C
anyway). Oriented accuracy per frozen/Discovery direction.

### 3.5 REL_RET invariance (correction 5)

Confirmed: F03↔F15, F05↔F16, F06↔F17 produce **identical** day-level IC series (identical mean,
median, pos_frac, HAC t, raw p, BH q, yearly ICs). See `P1_RELATIVE_RETURN_INVARIANCE_NOTE.md`.
F15–F17 are not independent predictors; the earlier "relative-strength family 被推翻" wording is
withdrawn in favor of the rank-invariance statement.

### 3.6 PRIMARY sensitivity renamed (correction 6)

`results/p11_primary_direction_sensitivity.csv` reports **pooled** Spearman over PRIMARY Top10
Discovery episodes (150 episodes / 125 signal days), labelled
`PRIMARY_POOLED_DIRECTION_SENSITIVITY`. All 6 passers (+F08) are direction-consistent with the
Discovery direction; null/near-null features (F10/F11/F12/F14/F15/16/17) show noise-level
direction mismatch, which carries no evidential weight.

### 3.7 Suspension / observation-window gap (correction 7)

- 196 / 35,009 episodes (0.56%) have a "last 20 observed stock bars" window spanning **>20 market
  trading days** (i.e., a suspension inside the 20-bar lookback); 24 episodes have <20 prior bars
  (very early history, treated as non-gap).
- Exclusion sensitivity (same ≥5/day IC gate, non-gap subset): IC/pairwise/K3 lift essentially
  unchanged (534→532 days; F04 IC −0.068, F07 −0.082, F09 +0.094, F13 +0.086, pairwise/K3 stable).
- **Not a P1 concern.** The per-stock rolling implementation is close to market-day semantics for
  this signal set; the 0.56% affected episodes do not drive any conclusion.

### 3.8 Passer redundancy / economic groups (correction 8)

Same-day avg rank correlation among the 6 passers (5×5):

| | F04 | F05 | F06 | F07 | F09 | F13 |
|---|---|---|---|---|---|---|
| F04 | 1.00 | 0.67 | 0.36 | 0.72 | −0.63 | −0.54 |
| F05 | 0.67 | 1.00 | 0.36 | 0.76 | −0.64 | −0.46 |
| F06 | 0.36 | 0.36 | 1.00 | 0.54 | −0.33 | −0.30 |
| F07 | 0.72 | 0.76 | 0.54 | 1.00 | −0.73 | −0.54 |
| F09 | −0.63 | −0.64 | −0.33 | −0.73 | 1.00 | 0.57 |
| F13 | −0.54 | −0.46 | −0.30 | −0.54 | 0.57 | 1.00 |

Economic grouping (≥2 non-redundant groups confirmed):

- **Group A — Reversal / Short-term Weakness (NEGATIVE direction):** F04 RET3, F06 RET20,
  F07 DIST_MA20 (F05 RET5 is a borderline member; note F04↔F07 corr 0.72, F05↔F07 0.76).
- **Group B — Volatility / Intraday Range (POSITIVE direction):** F09 ATR20_PCT, F13
  INTRADAY_RANGE (corr 0.57; F08 STOCK_RV20 corr≈0.87 with F09 but does not pass gate D, so it is
  **not** a third independent dimension).

### 3.9 Quintile dual metrics (correction 9)

Both `positive_day_fraction` (day-mean>0) and `equal_day_mean_episode_win_rate_pct`
(within-day episode win rate, equal-day weighted) are emitted separately in
`p11_quintile_metrics.csv`. Pattern (passers): NEGATIVE-direction features show monotonically
**falling** equal-day mean return Q1→Q5 (F04 4.94→3.50; F06 5.16→4.16; F07 5.11→3.68);
POSITIVE-direction features show monotonically **rising** Q1→Q5 (F09 3.43→5.45; F13 3.70→5.12).
Episode win rates move more weakly and sometimes inversely (e.g., F04 Q1 has highest day-mean
return but lowest episode win rate 70.1% vs 77.6% at Q5) — the return effect dominates.

### 3.10 Oracle corrected (correction 10)

Common usable-day set (593 days, n≥3), no replacement:

- All-signal equal-day mean: **4.376 pp**
- Random K3 mean: **4.377 pp** [3.985, 4.779]
- Oracle K3 mean: **17.816 pp** → lift **+13.44 pp**
- Oracle K1 22.65 / K5 16.56 / K10 15.17 pp

(Old, non-common-basis oracle K3 was 19.21 pp / +14.84pp over 534 predictor-valid days; the
corrected common-basis figure is +13.44pp. Same conclusion: within-day dispersion is large and
selection is a real, high-value problem.)

### 3.11 Turnover Top10 diagnostic (correction 11)

| bucket | n episodes | equal-day excess (pp) |
|---|---|---|
| A Top10 | 112 | +0.27 |
| B 11–50 | 357 | +0.66 |
| C 51–200 | 1,148 | −0.17 |
| D 201–500 | 2,260 | −0.62 |
| E >500 | 31,132 | +0.24 |

Conclusion limited to: **Top10 does not show superior within-day quality** (non-monotone, B > A,
large-bucket noise). No bucket is selected as a "winner."

---

## 4. Corrected master table (Discovery gate recompute)

| feature | name | dir | n_days | mean IC | BH q | pairwise% | K3 lift pp | K3 CI | ic20 | ic21 | ic22 | PASS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F01 | BB_Z | U→+ | 534 | +0.003 | 0.787 | 50.4 | −0.10 | [−0.52,0.31] | +0.009 | −0.006 | +0.010 | – |
| F02 | BB_LOWER_DISTANCE | U→− | 534 | −0.031 | 0.028 | 51.5 | +0.24 | [−0.19,0.79] | −0.018 | −0.041 | −0.031 | – |
| F03 | RET1 | U→− | 534 | −0.055 | 0.001 | 53.4 | +0.43 | [−0.04,0.93] | −0.064 | −0.080 | −0.020 | – |
| **F04** | **RET3** | U→− | 534 | **−0.068** | **0.000** | **53.6** | **+0.55** | **[0.03,1.10]** | −0.059 | −0.075 | −0.067 | **PASS** |
| **F05** | **RET5** | U→− | 534 | **−0.054** | **0.002** | **53.5** | **+0.53** | **[0.02,1.05]*** | −0.036 | −0.059 | −0.063 | **PASS\*** |
| **F06** | **RET20** | U→− | 533 | **−0.050** | **0.001** | **54.0** | **+0.93** | **[0.36,1.42]** | −0.023 | −0.053 | −0.068 | **PASS** |
| **F07** | **DIST_MA20** | U→− | 534 | **−0.082** | **0.000** | **54.6** | **+0.83** | **[0.22,1.51]** | −0.076 | −0.073 | −0.097 | **PASS** |
| F08 | STOCK_RV20 | U→+ | 534 | +0.084 | 0.000 | 54.4 | +0.34 | [−0.16,0.86] | +0.072 | +0.082 | +0.097 | – |
| **F09** | **ATR20_PCT** | U→+ | 534 | **+0.094** | **0.000** | **55.1** | **+0.67** | **[0.10,1.22]** | +0.087 | +0.089 | +0.105 | **PASS** |
| F10 | AMOUNT | U→+ | 534 | +0.004 | 0.787 | 50.2 | +0.05 | [−0.63,0.65] | +0.063 | −0.019 | −0.017 | – |
| F11 | AMOUNT_RATIO20 | U→+ | 534 | +0.005 | 0.787 | 49.5 | +0.40 | [−0.05,0.82] | +0.036 | −0.002 | −0.013 | – |
| F12 | CLOSE_LOCATION | POS | 534 | +0.005 | 0.787 | 49.8 | +0.06 | [−0.37,0.46] | +0.000 | −0.044 | +0.064 | – |
| **F13** | **INTRADAY_RANGE** | U→+ | 534 | **+0.086** | **0.000** | **54.1** | **+0.73** | **[0.23,1.23]** | +0.082 | +0.105 | +0.068 | **PASS** |
| F14 | GAP | U→+ | 534 | +0.006 | 0.767 | 49.4 | +0.57 | [0.11,0.96] | −0.008 | +0.008 | +0.015 | – |
| F15 | REL_RET1 | POS | 534 | −0.055 | 0.001 | 46.6 | −0.62 | [−0.95,−0.21] | −0.064 | −0.080 | −0.020 | – (invariant) |
| F16 | REL_RET5 | POS | 534 | −0.054 | 0.002 | 46.5 | −0.94 | [−1.33,−0.50] | −0.036 | −0.059 | −0.063 | – (invariant) |
| F17 | REL_RET20 | POS | 533 | −0.050 | 0.001 | 46.0 | −0.44 | [−0.91,0.11] | −0.023 | −0.053 | −0.068 | – (invariant) |

\* F05 borderline: K3 bootstrap CI lower bound passes 0 in only 26/30 seeds; treat as marginal.

Direction legend: `U→−/+` = UNKNOWN, orientation fixed by Discovery IC sign. F15–F17 registered
POSITIVE; their measured ICs are identical to F03/F05/F06 (rank-invariant), so they carry no
independent information.

**Corrected PASS set (robust): F04, F06, F07, F09, F13 — 5 passers across 2 economic groups
(Group A Reversal/Weakness, Group B Volatility/Range). Marginal 6th: F05.**

---

## 5. Key supporting numbers

- Random K3 baseline: 4.377 pp [3.985, 4.779] (corrected, no-replacement). All robust passers'
  K3-selected mean sits at 99.4–100th percentile of the random distribution.
- Oracle K3 lift: **+13.44 pp** (common usable-day basis).
- Suspension gap: 196/35,009 (0.56%); exclusion sensitivity stable.
- Crowding sensitivity (Discovery): passers' |IC| and K3 lift are **stronger at high signal
  crowding** (unchanged from P1); R01 market-state sensitivity: passers do not reverse direction
  across R01 terciles (unchanged).
- Primary pooled direction sensitivity: all 6 passers direction-consistent (PRIMARY Top10 pooled
  Spearman: F04 −0.18, F06 −0.20, F07 −0.27, F09 +0.22, F13 +0.15, F05 −0.16).

---

## 6. Corrected verdict

**A — P1 DISCOVERY ROBUST TO IMPLEMENTATION CORRECTIONS.**

- ≥2 non-redundant economic groups (Group A Reversal/Weakness: F04/F06/F07; Group B
  Volatility/Range: F09/F13) contain predictors passing the full corrected Registry gate.
- All passers: BH q < 0.05 (m=17), |mean daily IC| ≥ 0.03, oriented pairwise ≥ 53%, K3 lift ≥
  +0.5pp with block-bootstrap CI > 0 (F05 marginal), 2020/2021/2022 same direction with no
  opposite year ≥ 0.03.
- Gate A raw-p bug changed no A-gate status; the only pass-set change is the borderline F05
  (bootstrap-RNG-sensitive), disclosed above.
- F15–F17 remain non-independent (rank-invariance note).

Conditional on audit acceptance of A, 2023–2024 may be opened as **Ranking Validation**
(pre-registered anew, separate from the closed Market-State Validation use of 2023–24).
2025–2026 Confirmation remains **CLOSED**.

---

## 7. Deliverables (this round)

- `cross_sectional_ranking_p1_corrected.py`
- `P1_RELATIVE_RETURN_INVARIANCE_NOTE.md`
- `results/p11_master_table.csv`, `p11_old_new_pass_diff.csv`, `p11_random_k3_corrected.csv`,
  `p11_random_baseline_comparison.csv`, `p11_pairwise.csv`, `p11_k3_bootstrap.csv`,
  `p11_suspension_gap_audit.csv`, `p11_suspension_sensitivity.csv`, `p11_passer_redundancy.csv`,
  `p11_quintile_metrics.csv`, `p11_primary_direction_sensitivity.csv`, `p11_oracle.csv`,
  `p11_turnover_rank_diagnostic.csv`

Registry SHA unchanged: `fa5beb5a9a952442be2a359b95347388ff082c06fa36b56cf8f6eee477bab819`.
