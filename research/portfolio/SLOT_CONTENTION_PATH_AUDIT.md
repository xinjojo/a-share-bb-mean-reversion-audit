# SLOT_CONTENTION_PATH_AUDIT

**Phase:** P3.1 — SLOT CONTENTION & PATH-DEPENDENCE MECHANISM AUDIT
**Date:** 2026-09-03
**Type:** PURE DIAGNOSTIC. No new predictor / composite / threshold / stop / exit / K / layer tuning / ML.
**Red lines respected:** 2025-01-01 .. 2026-08-25 CONFIRMATION **CLOSED** (all engine runs use `day_range=(0, N2024)` = 2020-01-02..2024-12-31). P3 development classification `C — NO USEFUL PORTFOLIO RANKING` **kept unchanged**.
**Script:** `slot_contention_path_audit.py`. Engine instrumentation in `atr_slot_allocation_p3.py` is purely additive (`day_log` / `exec_log` / `forced_first` default to `None`).

---

## 0. P0 — Engine parity (frozen)

The instrumented B0 run is byte-identical to the frozen P3 `_p3_cache/B0_bp10.pkl`:

```
trades parity = True   (76 trades)
equity parity  = True  (final equity exact)
actions len    = True  (233)
n_trades=76  pnl=+302,951  total return = +30.30%
```

All numbers below come from that frozen path plus additive logging. 2020–2024 only.

---

## 1. The SLOT CONTENTION FUNNEL (per signal day, B0 Top10 universe)

For each of the 1,212 signal days in the dev window the funnel is:

```
A  all eligible A-share stocks             mean 4,424.6 / day
B  PIT-eligible / non-ST / listing60       (A==B; universe)
C  BB oversold (anywhere)                  mean 393.5 / day
D  Top10 by amount                         10
E  Top10 & oversold candidates             mean 1.53 / day (347 days >0)
F  not already held                        mean held_conflicts 0.33 / day
G  not already pending                     mean pending_conflicts ~0.00 / day
H  available slots at close                mean 0.35 / day (see §4)
I  actually queued                         mean 0.22 / day
J  executed next day                       mean 0.22 / day
```

`results/p31_contention_funnel_daily.csv` holds the full A..J series.

**Execution is almost never the bottleneck**: of 77 queued-entry attempts, 76
executed (98.7%) and 1 was NO_LOT; 0 CARRY_LIMITUP / MISSING / NO_CASH
(`p31_exec_outcomes.csv`). Pending-buy limit-up carries and missing days are not a
material constraint in this Top10 universe.

---

## 2. Contention taxonomy (1,212 signal days)

| taxonomy | days | % signal days | candidate events |
|---|---|---|---|
| NO_OVERSOLD_IN_TOP10 | 865 | 71.4% | 0 |
| FULL_BLOCK (K=3 full, candidates>0) | 225 | 18.6% | 371 |
| NO_CONTENTION (candidates ≤ slots) | 58 | 4.8% | 68 |
| HELD_CONFLICT_ONLY | 48 | 4.0% | 48 |
| **SOFT_CONTENTION (ranking actionable)** | **16** | **1.32%** | **43** |

**The portfolio gives ranking almost no chance to act.** On 71.4% of signal days the
Top10-by-amount contains **no** BB oversold stock at all; on a further 18.6% all three
slots are already full.

---

## 3. Ranking-actionable days (strict redefinition & re-count)

Per P3.1 §5, `ranking_actionable_day := (available_slots >= 1) & (queueable_candidates > available_slots)`.

- **Total 2020–2024: 16 days** (1.32% of 1,212 signal days; 1.32% of 1,212 trading days).
- All 16 have **exactly 1 free slot** (none with 2–3).
- Yearly (`p31_actionable_yearly.csv`):

| year | signal days | actionable | actionable % | full-block days |
|---|---|---|---|---|
| 2020 | 243 | 1 | 0.41% | 16 |
| 2021 | 243 | 10 | 4.12% | 40 |
| 2022 | 242 | 3 | 1.24% | 77 |
| 2023 | 242 | 0 | 0.00% | 45 |
| 2024 | 242 | 2 | 0.83% | 47 |

- Of the 16 actionable days, only **6 produced an actual B0 ≠ B1 selection difference**
  (`p3_selection_changed_events.csv`); on the other 10 both rankings picked the same stock.
  The P3 report's "7 contested days" referred to the k=1 diagnostic subset that had
  frozen returns for both candidates; the precise re-count is **16 actionable / 6
  selection-changed** (see `P3_MECHANISM_CORRECTION_NOTE.md`).

**Answer to P3.1 §6 — the #1 reason ranking is not actionable:**

1. **No empty slot (K=3 full): 668 signal days — 55.1% of all signal days** (55.9% of non-actionable).
2. **No oversold stock inside Top10: 459 days — 37.9%** of all signal days.
3. Insufficient competition (candidates ≤ slots): 58 days (4.8%).
4. Candidates all held: 11 days (0.9%).

(`p31_non_actionable_reasons.csv`)

---

## 4. K=3 saturation

Given a day with ≥1 Top10 oversold signal (`p31_slot_saturation.csv`):

| available slots | % of such signal days |
|---|---|
| 0 (K full) | **75.5%** |
| 1 | 16.1% |
| 2 | 6.3% |
| 3 | 2.0% |

Mean available slots on signal days: **0.35**. Over all 1,212 dev trading days, `n_pos=3`
on **55.1%** of days (`n_pos=0: 11.8%, 1: 13.9%, 2: 19.1%, 3: 55.1%`; `p31_slot_saturation.csv`).

---

## 5. Capital vs slot constraint

Capital is rarely binding: only **18 days (1.49% of trading days)** had an empty slot but
cash < 200k (`p31_capital_constraint_stats.json`); all 18 coincided with a signal day but
only a fraction had a queueable candidate. **The binding constraint is SLOTS (K=3 + long
holds), not cash.** `results/p31_capital_constraint.csv` has the full day series.

---

## 6. Slot occupancy and top slot blockers

`p31_slot_occupancy_trades.csv` attaches, to every B0 trade, its hold/levels/capital and
the queueable candidates it blocked while occupying a slot. Top blockers
(`p31_top_slot_blockers.csv`, ranked by `blocked_future_opportunities`):

| ts_code | entry | hold d | levels | return | MAE_intraday | blocked opportunities |
|---|---|---|---|---|---|---|
| 002594.SZ | 2021-12-17 | 88 | 4 | −2.2% | −26.3% | 57 |
| 300750.SZ | 2021-12-21 | 106 | 3 | −18.1% | −41.8% | 57 |
| 002594.SZ | 2022-07-13 | 76 | 5 | −0.7% | −23.8% | 54 |
| 300014.SZ | 2023-02-21 | 172 | 5 | −28.6% | n/a | 46 |
| 300750.SZ | 2023-10-17 | 81 | 3 | −1.6% | n/a | 33 |
| 000858.SZ | 2022-03-04 | 56 | 1 | −8.5% | n/a | 29 |

The portfolio bottleneck is **not "choosing the wrong stock" per se; it is the
holding-period + add-layer structure**: a handful of 80–170-day, 3–5-layer positions
with deep MAE occupy slots for months and block dozens of later queueable candidates
(including positive ones). This is a description, **not** a stop/exit design input.

---

## 7. Direct swap reconciliation (6 selection-changed events)

`p31_swap_reconciliation.csv` compares, per event, the frozen independent return and the
real portfolio trade for the B0 pick vs the B1 (ATR) pick, plus equity divergence at
+7/+20/+60 trading days.

| signal_date | B0 pick (ind / port) | B1 pick (ind / port) | port PnL B0 | port PnL B1 | eq_div 60d |
|---|---|---|---|---|---|
| 2021-02-25 | 300059 (− / −5.45%) | 002594 (− / +24.07%) | −10,815 | +137,850 | −16,265 |
| 2021-04-15 | 601166 (− / +10.16%) | 600276 (− / +2.98%) | +19,182 | +5,890 | −156,301 |
| 2021-05-24 | 000661 (+3.54 / +3.64%) | 002714 (−18.72 / −31.90%) | +18,777 | −132,078 | −231,398 |
| 2021-11-16 | 600030 (+7.94 / +7.94%) | 000625 (−22.23 / −21.58%) | +15,781 | −130,012 | −397,816 |
| 2022-03-03 | 000858 (− / −8.53%) | 300014 (− / +11.05%) | −16,907 | +21,516 | −393,730 |
| 2022-10-12 | 600519 (− / −3.85%) | 002371 (+10.60 / +10.60%) | −6,638 | +19,113 | −379,809 |

Three observations:

1. Where ATR changed the pick and both frozen returns exist, it was worse 2/3 times and by a
   large margin (2021-05-24, 2021-11-16).
2. Even on the three events where the ATR pick itself was *profitable* in isolation
   (2021-02-25, 2022-03-03, 2022-10-12), the **60-day portfolio divergence is strongly
   negative** (−16k, −394k, −380k). The slot released by the swap is filled by a different,
   worse subsequent trade; the independent-trade win does not survive the path.
3. Hence portfolio divergence is **not** primarily "ATR picked worse stocks"; it is the
   **path amplification** of any substitution under K=3.

## 8. Independent-episode coverage (why some frozen returns are missing)

`p31_independent_coverage.csv` explains each missing frozen return. **All 7 missing
(date, ts) pairs are absent because the frozen per-stock SECONDARY replay had an
already-open episode for that stock on that signal date** (per-stock sequential
held-blocking), e.g.:

- 300059.SZ on 2021-02-25 — overlapped by frozen episode sig 2021-02-22/exit 2021-04-02.
- 002594.SZ on 2021-02-25 — overlapped by frozen episode sig 2021-02-24/exit 2021-06-08.

The portfolio engine's holding state differs (Top10 + K=3), so it *can* enter these
names. Coverage: 2 events fully covered (2021-05-24, 2021-11-16), 1 partial
(2022-10-12), 3 none (2021-02-25, 2021-04-15, 2022-03-03). Where the frozen return is
missing we rely on the real portfolio trade return only; we never impute a frozen return.

---

## 9. Path cascade (60 trading days) — the two big divergences

`p31_path_cascade.csv`, `p31_path_cascade_<date>.csv`, `_events_b0/b1.csv`.

- **2021-05-24** (B0 picks 000661 +18.8k vs B1 002714 −132.1k): holdings first differ on
  the swap day itself; **never reconverges** within 60 trading days; B1 entered only 4
  trades vs B0's 7 in the window; eq divergence 7d −30.8k / 20d −84.6k / 60d −231.4k.
- **2021-11-16** (B0 600030 +15.8k vs B1 000625 −130.0k): holdings first differ 2021-11-17;
  **never reconverges**; B1 entered 3 trades vs B0's 4; eq divergence 7d −352.8k /
  20d −371.9k / 60d −397.8k.

Once the swap changes who holds which slot, the two portfolios never return to the same
holdings / cash / pending state inside 60 trading days — the divergence is permanent and
compounding.

---

## 10. Leave-one-swap attribution (6 forced runs, endogenous path)

`p31_leave_one_swap.csv`. For each observed contested decision, B0 is re-run with only
that one decision forced to the ATR pick (`forced_first`); everything else is
engine-endogenous.

| signal_date | forced ATR pick | ΔPnL vs B0 |
|---|---|---|
| 2021-02-25 | 002594.SZ | **−371,382** |
| 2021-04-15 | 600276.SH | **−436,315** |
| 2021-05-24 | 002714.SZ | −187,890 |
| 2021-11-16 | 000625.SZ | −149,344 |
| 2022-03-03 | 300014.SZ | −25,850 |
| 2022-10-12 | 002371.SZ | −68,808 |

**Every single forced ATR substitution is individually value-destructive**
(Δ in [−25.9k, −436k]). The two most negative (2021-04-15 −436k, 2021-02-25 −371k)
together sum to −807.7k, about 65% of the sum of all six deltas (−1,239.6k), which is
itself about 2.5x the realised B0→B1 total divergence (−489.6k: B0 +302.95k → B1
−186.6k). The deltas overlap heavily in downstream effects (each is computed
independently from B0), which is precisely the point: **the portfolio is so
path-dependent that even a single slot substitution cascades into a large PnL change,
and when several substitutions occur together they partially offset**. No single
decision is "the" cause; a handful of rare, large-loss choices dominate.

---

## 11. Ranking value decomposition

Following P3.1 §11, the portfolio value of a ranking rule is approximately

```
ranking value ≈ actionability × conditional selection edge × path amplification
```

Measured components:

| component | value |
|---|---|
| Actionability | **16/1212 signal days (1.32%)**; all k=1 |
| Conditional edge on contested days | observed ATR picks worse 2/3 on the days with full frozen returns; even profitable picks lose downstream |
| Path amplification | every leave-one-swap Δ < 0; divergence never reconverges within 60d |

The cross-sectional ATR edge (P2: validation mean daily CS IC ≈ +0.134) operates on the
**independent-episode level**; at the portfolio level the edge is almost never
actionable, and when it is, the path effect (slot release → different subsequent
trades, long-hold/deep-MAE slot lock) dominates the direct selection gain.

---

## 12. B2 (FULL-SIGNAL ATR) — formally NON-DEPLOYABLE

`p31_b2_liquidity_risk.csv` (55 selected trades, dev):

- median selected-stock signal-day amount ≈ **245k RMB**; P10 ≈ 85k; P5 ≈ 56k.
- A single 200k layer is **~82% of median daily amount**, **~235% of P10 amount**
  and **~358% of P5 amount**. Across the 55 selected trades, **63.6% have daily amount
  < 400k** (a 200k layer exceeds 50% of the stock's entire day turnover) and **43.6%
  have amount < 200k** (layer > 100% of turnover).

Under the frozen execution model (10bp slippage, 100-share lots, market order at open),
these are un-executable order sizes. **B2 is classified NON-DEPLOYABLE under the current
execution model** and retained only as a warning experiment for removing the liquidity
universe. Its PnL is not evidence about alpha.

---

## 13. Final mechanism classification

**C — BOTH**, defined as:

- **A. RANKING RARELY ACTIONABLE** — the K=3 architecture almost never lets a ranking
  rule act (ranking-actionable 16/1,212 signal days = 1.32%).
- **B. RARE HISTORICAL ADVERSE SELECTIONS ARE STRONGLY PATH-AMPLIFIED** — on the few
  actionable days, a small number of adverse choices were amplified by a portfolio path
  that never reconverges.

More precisely:

- **Actionability is the primary structural problem (A):** ranking can only decide who
  gets a slot on 16/1,212 signal days (1.32%); 71.4% of signal days have no Top10
  oversold at all and on 75.5% of Top10-oversold days K is already full. The portfolio
  architecture (K=3 + long, deep-MAE, multi-layer positions) is the binding constraint.
- **The observed actionable sample is too sparse to estimate population conditional ATR
  alpha (B):** only 6 selection-changed events over 2020–2024. Historically, a few
  adverse actionable selections were strongly amplified by portfolio path dependence
  (2/3 full-return swaps were large losses; all leave-one-swap re-runs are negative;
  no reconvergence; Δ −26k…−436k per swap). These are **historical path attribution
  results, not statistical evidence of systematic negative conditional ATR alpha** (see
  §13b).
- The two factors **compound**: the rare contested decisions that do occur are exactly
  the ones that unlock huge path cascades.

Therefore the answer to the P3.1 closing question is: **ATR "failed" because the K=3
architecture almost never lets a ranking rule act, and on the few days it does, a small
number of adverse historical choices were strongly amplified by a path that never
reconverges.** No claim is made that ATR has systematic negative conditional alpha.

P3's development verdict `C — NO USEFUL PORTFOLIO RANKING` is **kept**. 2025–2026
Confirmation remains **CLOSED**. No strategy design is proposed in this phase.

---

## 13b. External-audit wording reconciliation (R0)

Per external audit R0, the following wording is fixed:

**ACCEPTED**

- ranking-actionable days are extremely rare: **16 / 1,212 = 1.32%** of signal days.
- K=3 slot saturation is the primary bottleneck (P(K-full | Top10 oversold signal) = 75.5%).
- Capital constraint is rarely binding (18 / 1,212 days = 1.49%).
- A few selection differences are strongly amplified by portfolio path dependence
  (never reconverging within 60 trading days; all 6 leave-one-swap Δ < 0).

**NOT ACCEPTED**

- Any claim that "ATR has systematic negative alpha in the contested regime."

Reason: the selection-changed / actionable sample is extremely small (16 actionable
days, 6 selection-changed events over 2020–2024). The 6 negative leave-one-swap results
are **historical path attribution** (each a full endogenous re-run from B0), **not**
statistical conditional-alpha evidence. No population-level claim about ATR's conditional
edge is made or implied.

---

## 14. Files

- `results/p31_contention_funnel_daily.csv` · `p31_contention_taxonomy.csv` · `p31_exec_outcomes.csv`
- `results/p31_actionable_yearly.csv` · `p31_non_actionable_reasons.csv`
- `results/p31_slot_saturation.csv` · `p31_slot_saturation_stats.json`
- `results/p31_capital_constraint.csv` · `p31_capital_constraint_stats.json`
- `results/p31_slot_occupancy_trades.csv` · `p31_top_slot_blockers.csv`
- `results/p31_swap_reconciliation.csv` · `p31_independent_coverage.csv`
- `results/p31_path_cascade.csv` + `p31_path_cascade_<date>*.csv`
- `results/p31_leave_one_swap.csv` · `results/p31_slippage_path_diff.csv`
- `results/p31_b2_liquidity_risk.csv` · `results/p31_mechanism_summary.json`
