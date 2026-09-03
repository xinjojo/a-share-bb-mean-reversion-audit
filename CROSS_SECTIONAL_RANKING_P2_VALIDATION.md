# CROSS-SECTIONAL RANKING — PHASE P2 (UNTANGLED 2023–2024 VALIDATION)

**Status:** Confirmatory validation of the 5 robust P1.1 Discovery passers on untouched
2023–2024. 2025–2026 Confirmation **CLOSED**.

---

## 0. Freeze state

| Item | Value |
|---|---|
| P1 Registry | `CROSS_SECTIONAL_RANKING_REGISTRY.csv`, commit `9c36887`, SHA `fa5beb5a…` |
| P1.1 corrected result | commit `5054f6a` |
| **P2 Validation Registry** | `CROSS_SECTIONAL_RANKING_VALIDATION_REGISTRY.csv`, commit **`83c3f1e`**, SHA **`d58599305aa5cde7f6b3777a5a20f9022c7cc3b6cbcc39649e772fab91e3e911`** |
| Validation window | 2023-01-01 ~ 2024-12-31 |
| Sample | SECONDARY frozen V2A_FROZEN_STRICT: **29,063 episodes / 445 signal days** (388 IC-days, 409 usable K3 days) |
| Registry commit order | Registry written + SHA + committed + pushed **before** any 2023–2024 outcome read (STEP_A reads no outcome data) |
| Candidate set | V01=F04 RET3(NEG), V02=F06 RET20(NEG), V03=F07 DIST_MA20(NEG) [GROUP_A]; V04=F09 ATR20_PCT(POS), V05=F13 INTRADAY_RANGE(POS) [GROUP_B] |
| F05 | MARGINAL_DISCOVERY_SENSITIVITY — excluded from BH m=5 and from A/B/C classification |
| Red lines | no composite, no portfolio backtest, no ML, no re-orientation, 2025–26 CLOSED |

---

## 1. Validation master table (pre-registered gate A–G)

| V | feature | dir | n_days | mean IC | BH q(m=5) | pairwise% | K3 lift pp | K3 CI | IC 2023 | IC 2024 | disc IC | ratio | repl | **PASS** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V01 | F04 RET3 | NEG | 388 | −0.076 | 0.0008 | 53.5 | +0.72 | [−0.17, 1.84] | −0.075 | −0.079 | −0.068 | 1.12 | REPLICATED | NO (F) |
| V02 | F06 RET20 | NEG | 388 | −0.061 | 0.0008 | 52.6 | +0.98 | [−0.17, 2.24] | −0.038 | −0.092 | −0.050 | 1.22 | REPLICATED | NO (D,F) |
| V03 | F07 DIST_MA20 | NEG | 388 | −0.105 | 0.0001 | 54.1 | +0.88 | [−0.29, 2.15] | −0.090 | −0.125 | −0.082 | 1.28 | REPLICATED | NO (F) |
| **V04** | **F09 ATR20_PCT** | POS | 388 | **+0.134** | **0.0000** | **55.2** | **+1.43** | **[0.50, 2.51]** | +0.141 | +0.126 | +0.094 | 1.43 | REPLICATED | **YES** |
| V05 | F13 INTRADAY_RANGE | POS | 388 | +0.097 | 0.0000 | 53.9 | +0.69 | [−0.05, 1.58] | +0.095 | +0.099 | +0.086 | 1.13 | REPLICATED | NO (F) |

Gate detail:

| V | A dir | B bh_q | C |IC|≥.03 | D pair≥53 | E K3≥.5 | F boot CI>0 | G yearly | PASS |
|---|---|---|---|---|---|---|---|---|---|---|
| V01 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ (0/30 seeds) | ✓ | ✗ |
| V02 | ✓ | ✓ | ✓ | ✗ 52.6 | ✓ | ✗ | ✓ | ✗ |
| V03 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ (0/30) | ✓ | ✗ |
| V04 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (30/30) | ✓ | **✓** |
| V05 | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ (0/30) | ✓ | ✗ |

### 1.1 The binding constraint is Gate F (K3-lift day-level bootstrap CI)

- All five features **replicate strongly at the IC level** (ratios 1.12–1.43 vs Discovery;
  all labelled REPLICATED), are BH-significant, direction-consistent in **both** 2023 and 2024
  (gate G passes for all).
- K3-lift point estimates are clearly positive for all five (+0.69…+1.43 pp), but the
  day-level moving-block bootstrap CI (L=21, B=5000) is wide in 2023–24. Only V04 clears the
  lower bound > 0; and this is **robust** — across 30 bootstrap seeds, V04 CI-lo > 0 in 30/30,
  V01/V03/V05 in **0/30** (CI-lo medians: V01 −0.156, V03 −0.291, V05 −0.075). These are not
  borderline flips; they fail robustly.
- V02 additionally misses the pairwise gate (52.6% < 53%).

---

## 2. Per-feature exact usable-day random K3 baseline (correction carried into validation)

409 usable days (≥3 valid signals) per feature. Random K3 **without replacement**, B=5000:

| V | feature | random K3 mean | 95% interval | ranked K3 mean | random pctile |
|---|---|---|---|---|---|
| V01 | RET3 | 3.525 pp | [3.014, 4.031] | 4.249 pp | 99.7 |
| V02 | RET20 | 3.520 | [3.018, 4.020] | 4.510 | 100.0 |
| V03 | DIST_MA20 | 3.526 | [3.032, 4.039] | 4.402 | 100.0 |
| V04 | ATR20_PCT | 3.531 | [3.016, 4.024] | 4.952 | 100.0 |
| V05 | INTRADAY_RANGE | 3.527 | [3.027, 4.021] | 4.219 | 99.8 |

Every feature's ranked Top-3 mean sits at ≥99.7th percentile of its own random baseline —
the selection lift is real relative to feature-specific random draw, even where the bootstrap
CI on the *daily-lift* series is too wide to clear Gate F.

## 3. Oracle (HINDSIGHT, DESCRIPTIVE ONLY, per-feature usable-day set)

Oracle K3 mean = 17.41 pp on the same usable-day set (vs all-signal day mean ≈ 3.53 pp on
usable days). Same-day dispersion remains large in 2023–24; selection problem is real.

## 4. Quintile profile (equal-day)

- GROUP_A (NEGATIVE): Q1 (most oversold/short-term weakness) > Q5 in equal-day mean return —
  V01 4.94→3.50 (Discovery-like), V03 5.11→3.68 pattern reproduced in Validation.
- GROUP_B (POSITIVE): Q5 (highest vol/range) > Q1 — V04 Q1 3.43→Q5 5.45 pattern reproduced
  (Validation Q1≈3.5, Q5≈4.9).
- Full Q1–Q5 rows (mean return, positive_day_fraction, episode win rate, MAE, MFE, hold) in
  `results/p2_quintiles.csv`.

## 5. Group-level redundancy (same-day rank correlation, Validation)

| | V01 | V02 | V03 | V04 | V05 |
|---|---|---|---|---|---|
| V01 | 1.00 | 0.40 | 0.71 | −0.62 | −0.55 |
| V02 | 0.40 | 1.00 | 0.58 | −0.37 | −0.32 |
| V03 | 0.71 | 0.58 | 1.00 | −0.75 | −0.54 |
| V04 | −0.62 | −0.37 | −0.75 | 1.00 | 0.53 |
| V05 | −0.55 | −0.32 | −0.54 | 0.53 | 1.00 |

GROUP_A members are moderately correlated (0.40–0.71) — **not** independent discoveries.
GROUP_B pair corr 0.53. V03↔V04 cross-group −0.75 (max cross-group), consistent with
"weakness vs volatility" being distinct but opposed constructs.

## 6. Suspension / observation-window sensitivity

Per-feature lookback-window gap (last-k observed bars spanning >k market days):
V01 27 (0.09%), V02/V03/V04 64 (0.22%), V05 12 (0.04%). Excluding gap episodes changes
nothing material (sens IC: V01 −0.078 vs −0.076, V03 −0.106 vs −0.105, V04 +0.135 vs +0.134;
sens K3-lift within noise). **Non-material.**

## 7. PRIMARY pooled direction sensitivity (2023–2024, PASS features only)

PASS feature = F09. PRIMARY Top10 2023–24: **95 episodes / 82 signal days**; pooled Spearman
**+0.183**, direction POSITIVE match. (Secondary confirmation only; does not rescue failures.)

## 8. F05 RET5 — marginal (excluded from BH5 / classification)

Validation (NEGATIVE): mean IC −0.085 (raw p 0.0004), oriented pairwise 53.3%, K3 lift
+1.02 pp, K3 CI [−0.04, 2.26]. Direction consistent, but fails Gate F; stays marginal.

## 9. Top10 turnover (descriptive, 2023–24)

| bucket | n | equal-day excess pp |
|---|---|---|
| A Top10 | 66 | +0.06 |
| B 11–50 | 220 | −0.60 |
| C 51–200 | 783 | −0.55 |
| D 201–500 | 1,674 | −0.98 |
| E >500 | 26,320 | +0.14 |

**Top10 shows no superior within-day quality in Validation** (≈0 excess, non-monotone);
consistent with P1. No bucket reselected.

---

## 10. Effect preservation (Discovery → Validation)

All five REPLICATED (direction consistent, ≥50% of Discovery effect preserved at IC level;
IC ratios 1.12–1.43). K3-lift ratios: V01 1.32, V02 1.05, V03 1.05, V04 2.12, V05 0.95 —
all ≥0.95, i.e., the selection-lift point estimate also holds or grows.

## 11. Classification

**B — PARTIAL VALIDATION.**

- Exactly **1 formal STRONG_PASS: V04 ATR20_PCT (GROUP_B)**, passing all of A–G robustly.
- GROUP_A (reversal/weakness: V01/V02/V03) replicates direction, BH-significance, pairwise and
  K3-lift point estimates, but **fails Gate F** (day-level K3-lift bootstrap CI lower < 0,
  robustly, 0/30 seeds); V02 also misses pairwise.
- Not A (needs ≥2 PASS across ≥2 groups). Not C/D (the relation is far from absent — strong,
  statistically significant IC replication across the whole family).

## 12. Deliverables

- `STEP_A_RANKING_VALIDATE_PREREGISTER.py`, `STEP_B_RANKING_VALIDATE.py`
- `CROSS_SECTIONAL_RANKING_VALIDATION_REGISTRY.csv` + `.sha256`
- `results/p2_master_table.csv`, `p2_daily_ic.csv`, `p2_hac.csv`, `p2_bh5.csv`,
  `p2_pairwise.csv`, `p2_k3_lift.csv`, `p2_k3_bootstrap.csv`, `p2_random_k3_per_feature.csv`,
  `p2_oracle.csv`, `p2_quintiles.csv`, `p2_yearly.csv`, `p2_effect_replication.csv`,
  `p2_redundancy.csv`, `p2_suspension_sensitivity.csv`, `p2_primary_sensitivity.csv`,
  `p2_f05_marginal.csv`, `p2_turnover_top10_descriptive.csv`

2025–2026 Confirmation: **CLOSED**.
