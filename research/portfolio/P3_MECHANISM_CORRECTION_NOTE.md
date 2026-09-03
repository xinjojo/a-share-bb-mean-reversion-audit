# P3_MECHANISM_CORRECTION_NOTE

**Phase:** P3.1 — SLOT CONTENTION & PATH-DEPENDENCE MECHANISM AUDIT
**Date:** 2026-09-03
**Scope:** Documentation-error correction only. Historical result CSVs are NOT modified.
**P3 development classification `C — NO USEFUL PORTFOLIO RANKING` is unchanged.**

---

## 1. What was wrong

`ATR_SLOT_ALLOCATION_P3.md` §4 ("Frozen-episode contested diagnostic") had a
baseline / ATR label inversion in three of the per-date examples, plus an incorrect
number for the 2021-12-20 row. The CSV-authoritative values are:

| signal_date | baseline_topk_mean | atr_topk_mean | diff (ATR − baseline) |
|---|---|---|---|
| 2021-05-24 | **+3.543** | **−18.715** | −22.258 |
| 2021-11-16 | **+7.942** | **−22.230** | −30.172 |
| 2021-12-20 | **−14.233** | **+1.838** | +16.070 |

The doc had presented the first two rows as "ATR … vs baseline …" (labels reversed) and
had written "+6.47 vs +1.84" for 2021-12-20 (the +6.47 value belongs to the 2021-12-01
row, where baseline and ATR agree exactly; the true 2021-12-20 values are baseline
−14.233 / ATR +1.838).

## 2. Why it does not change the P3 verdict

- The contested sample is **extremely sparse**: only 16 ranking-actionable signal days
  in 2020–2024 (1.32% of 1,212 signal days), all with exactly 1 free slot (see
  `SLOT_CONTENTION_PATH_AUDIT.md` §4–§5). Of these, 6 produced an actual B0 ≠ B1
  selection difference (`p3_selection_changed_events.csv`).
- On the 3 days where ATR actually changed the pick with a measurable frozen return,
  ATR was worse 2/3 times and by a large margin (2021-05-24, 2021-11-16); it was
  better once (2021-12-20).
- The label error is cosmetic in a 7-row diagnostic table; it does not alter the
  aggregate P3 result (B0 +30.30% vs B1 −18.66% over 2020–2024, PURE STOCK) nor the
  `C` classification.

## 3. Pre-registered language fix (per P3.1 spec §2)

The P3 report no longer claims a "systematic contested-tail reversal". The corrected
wording, which is used in `SLOT_CONTENTION_PATH_AUDIT.md`, is:

> The observed contested sample is extremely sparse (16 actionable days / 6 actual
> selection changes over 2020–2024); a few large-loss choices dominate the portfolio
> divergence. No claim of a systematic "ATR fails on contested days" is made.

## 4. Files

- Corrected document: `ATR_SLOT_ALLOCATION_P3.md` §4 (in-place edit).
- Historical result CSVs (`p3_*.csv`, `_p3_cache/*.pkl`): untouched.
