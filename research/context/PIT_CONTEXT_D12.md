# PHASE D1.2 — EFFECTIVE FINANCIAL VISIBILITY-DATE AUDIT

## Governance chain

| Step | Commit | Status |
|---|---|---|
| R1.5 open PIT context foundation | `096e7ce` | accepted |
| D1-A prereg | `f5bf5e9` (SHA `6168e104…`) | pushed |
| D1 result (sector B / fundamental A) | `1b2e3e0` | pushed |
| D1.1-A prereg | `bc20cd6` (SHA `414a1816…`) | pushed |
| D1.1 result (PASS) | `e2c4461` | pushed |
| **D1.2-A prereg** | `1be1992` (SHA `f4be40f9…`) | **pushed** |
| **D1.2 result** | TBD | **pending commit** |

External audit: D1.1 implementation PASS, but the D1/D1.1 Registry itself may
have a more fundamental PIT visibility problem: Tushare defines `ann_date`=公告
日期 and `f_ann_date`=实际公告日期. Using only `ann_date<=T` as the visibility
gate may be insufficient — if `ann_date<=T` but `f_ann_date>T`, the version may
not have been truly visible at T. D1 stays HOLD; S3 FUNDAMENTAL DISTRESS
FORBIDDEN until D1.2 resolves. This phase answers only: for income/cashflow,
which date truly means "market participants could see this version"?

## Registry (frozen before results)

- Two candidate rules only: RULE_A visible=ann_date; RULE_B visible=f_ann_date
  if present else ann_date. No third rule without official mandate + registration.
- PRIMARY P0: FUTURE_ACTUAL_ANN_COMPONENT (selected ann<=T but f_ann>T) count.
- Official semantics evidence; real-world spot check (>=30 distinct
  stock/period, cninfo official announcements); disclosure_date / anns_d
  cross-checks; RULE_B rebuild impact; TTM P0 (future_visible=0); fina
  AMBIGUOUS->NA unchanged; classification A (RULE_A valid) / B (RULE_B
  required) / C (semantics ambiguous); 2025-2026 CLOSED.

## B. Data profiling (raw income / cashflow)

| relation | income rows | cashflow rows |
|---|---|---|
| f_ann missing | 56,672 | 59,376 |
| f_ann == ann | 128,317 | 122,900 |
| f_ann < ann | 3,281 | 1,719 |
| **f_ann > ann** | **3,143 (1.64%)** | **2,036 (1.08%)** |

delta_days = f_ann − ann (f_ann>ann only):

| stat | income | cashflow |
|---|---|---|
| min | 1 | 1 |
| P1 | 2 | 2.35 |
| P5 | 17 | 14 |
| median | **295** | **182** |
| P95 | 1,095 | 898 |
| P99 | 1,467 | 1,219 |
| max | 2,905 | 1,902 |

Median delta ≈ 300 days — far beyond any plausible "actual disclosure" lag;
this is the first signal that `f_ann_date` is not a single-semantics field.

## C. Signal-level exposure (63,785 B20 signals, D1.1 STRICT selector)

- Components selected with ann<=T but f_ann>T: **3,466** (income cur 534 /
  income prev_full 1,742 / income prev_same 62 / cashflow cur 242 / cashflow
  prev_full 865 / cashflow prev_same 21).
- Signals hit: **2,262 / 63,785 (3.55%)**.
- **Decomposition by delta**: small (1–30d) **14**; mid (31–180d) **280**;
  large (>180d) **3,172 (91.5%)**.
- cur-role (latest component): small **14**, mid **235**, large **527**.

## E. Official semantics (see d12_official_semantics.md)

- `ann_date` = 公告日期; `f_ann_date` = 实际公告日期 (income doc_id=33 and
  cashflow doc_id=44, identical definitions).
- Data itself contradicts a single-field reading of f_ann_date (below).

## F/G/H. Real-world verification

### 30 large-delta cases (delta 2905→1478 days) vs cninfo official records
- **0/30 match f_ann_date**; 13/30 exactly match ann_date; 10/30 OTHER
  (actual disclosure 10–70 days AFTER ann_date — delayed annual reports);
  7/30 NO_HIT (even with widened window).
- Distinctive signature: the same stock has the **same f_ann_date across all
  report periods** (600973.SH all = 20260314; 002462.SZ all = 20260314;
  300091.SZ all = 20240208; 002726.SZ all = 20260131) ⇒ large-delta f_ann_date
  is a **warehouse refresh timestamp**, not a disclosure date.

### 11 small-delta cases (delta 1–30d) vs cninfo
- **8/11 exactly match f_ann_date** (e.g. 688733.SH 2022H1 ann=20220826
  f_ann=20220827 actual=2022-08-27; 300887.SZ 2022FY ann=20230420
  f_ann=20230421 actual=2023-04-21). 晚间公告 pattern: ann = registered date,
  f_ann = actual publication date.

### disclosure_date cross-check
- Interface available; returns earnings forecast/express disclosure plans
  (pre_date planned, actual_date actual). 37 rows for conflict-case stocks,
  all end_date=20241231 forecasts — **not comparable** to periodic-report
  announcement dates. No verdict contribution.

### anns_d
- **NOT_AVAILABLE** (no permission for this token). Not a failure per
  Registry.

## I/J. RULE_B rebuild impact

- Changed signal events (latest_report_period or latest_ann_date): **381 /
  63,785 (0.60%)**; by year 2020: 1.79%, 2021: 1.11%, 2022: 0.41%, 2023:
  0.14%, 2024: 0.15%.
- RULE_A-has-value-but-RULE_B-not-visible at T: **0**.
- These changes are dominated by **erroneous removals** of large-delta rows
  (RULE_B pushes e.g. 2017 FY visibility to 2026).

## K. TTM P0 check under RULE_B

- future_visible_component_count = **0** (rule is internally self-consistent;
  this does not make the rule correct for large-delta rows).

## L. fina_indicator

- Unchanged: AMBIGUOUS->NA (1,179 signal events, 1.85%). Visibility by
  ann_date only (interface field limitation).

## M. forecast / express

- forecast: no f_ann_date column in cached data (ann_date + update_flag);
  ann_date remains the public-date proxy. express: ann_date only. No strategy
  modification.

## Classification

**D1.2-C — SEMANTICS AMBIGUOUS.**

`f_ann_date` in this data mixes two meanings: (a) true actual disclosure date
(small delta; 8/11 cninfo matches) and (b) warehouse refresh timestamp (large
delta; 0/30 matches, same value across all periods per stock). Neither RULE_A
nor RULE_B is reliable as a single visibility gate:
- RULE_A is correct for 99.98% of signals; bounded leakage only from the 14
  small-delta cur components (≤0.02%) plus at most 235 mid cur components
  (≤0.39%).
- RULE_B catastrophically mis-dates 3,172 large-delta components.

**D1 FINAL ACCEPT: NO** (stays HOLD). Per Registry, income/cashflow PIT cannot
enter S3 until a more reliable announcement-date source exists.

## Honest bottom line

The 3,466-component exposure is dominated by warehouse timestamps, not real
leakage. The true "saw it before it was actually published" upper bound is
~0.4% of signals (14–249 components), concentrated in (i) 晚间公告 +1-day
cases and (ii) delayed annual-report disclosures. D1.1's ~12% numeric changes
come from the tie-break selecting the latest warehouse-refreshed row — a
version-choice policy, not visibility leakage. But the field ambiguity itself
is real and unresolvable with a single rule, so D1 stays HOLD until a
canonical announcement-date source (exchange / cninfo) or a registered hybrid
rule (small delta → f_ann, large delta → ann) is adopted.

## Invariants (d12_invariants.json, all True)

I1 no outcome access · I2 no strategy test · I3 no threshold search · I4 no
2025–2026 · I5 D1/D1.1 raw unchanged · I6 fina AMBIGUOUS->NA unchanged · I7
sector unchanged · I8 prior registry SHA unchanged (D1 `6168e104…`, D1.1
`414a1816…`).
