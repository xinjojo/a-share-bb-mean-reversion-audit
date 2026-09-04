# D1.2 — Official Semantics Evidence (Tushare income/cashflow)

## 1. Tushare official field definitions

Source: Tushare Pro documentation, retrieved 2026-09-04.

### 利润表 (income) — https://tushare.pro/document/2?doc_id=33
| 参数 | 类型 | 描述 |
|---|---|---|
| ann_date | str | 公告日期（YYYYMMDD格式，下同） |
| f_ann_date | str | **实际公告日期** |
| end_date | str | 报告期 |
| update_flag | str | 更新标识 |

### 现金流量表 (cashflow) — https://tushare.pro/document/2?doc_id=44
| 参数 | 类型 | 描述 |
|---|---|---|
| ann_date | str | 公告日期（YYYYMMDD格式，下同） |
| f_ann_date | str | **实际公告日期** |
| end_date | str | 报告期 |

## 2. Official semantics

- `ann_date` = 公告日期。在该数据集中实测表现为：**交易所/计划披露日**（对"晚间公告"场景为公告登记日）。
- `f_ann_date` = 实际公告日期。官方语义为**实际对外发布日**。

If `ann_date <= T` but `f_ann_date > T`, the version may not have been truly
visible at T — this is the D1.2 audit question.

## 3. Empirical defect found: f_ann_date mixes two meanings

Real-world spot-check against cninfo (巨潮资讯) official announcement records
reveals that in this token's data snapshot `f_ann_date` is **not a single
semantics field**:

### (a) Small-delta records (f_ann_date ≈ ann_date, typically +1 day)
`f_ann_date` is the **true actual disclosure date** (晚间公告 pattern:
ann_date = planned/registered date, f_ann_date = actual publication date).

Spot-check (11 cases, delta 1–30 days): **8/11 exactly match cninfo
official disclosure date (F_ANN)**.

Examples:
- 688733.SH 2022H1: ann=20220826, f_ann=20220827, cninfo actual=2022-08-27
- 300887.SZ 2022FY: ann=20230420, f_ann=20230421, cninfo actual=2023-04-21
- 600022.SH 2019Q1: ann=20190426, f_ann=20190427, cninfo actual=2019-04-27

### (b) Large-delta records (f_ann_date − ann_date ≥ ~180 days)
`f_ann_date` is a **data-warehouse refresh / load timestamp**, NOT a
disclosure date. Distinctive signature: **the same stock carries the same
f_ann_date across ALL report periods** (e.g. 600973.SH all periods = 20260314;
002462.SZ all periods = 20260314; 300091.SZ all periods = 20240208;
002726.SZ all periods = 20260131).

Spot-check (30 cases, delta 2905→1478 days): **0/30 match cninfo official
disclosure date**. 13/30 exactly match ann_date; 10/30 are OTHER (actual
disclosure within ~10–70 days AFTER ann_date — delayed annual-report
disclosures); 7/30 no matching cninfo record even with a widened window.

## 4. Signal-level consequence (63,785 B20 signals)

- FUTURE_ACTUAL_ANN_COMPONENT (selected component has ann<=T but f_ann>T):
  3,466 components / 2,262 signals (3.55%).
- Of these, **91.5% (3,172) are large-delta refresh timestamps — false
  alarms with no real visibility leakage**.
- True leakage candidates (small delta ≤30d, i.e. actual disclosure after T):
  **only 14 components / 12 stocks**.
- Mid range (31–180d): 280 components / 157 stocks — mixed; conservative
  upper bound of real leakage ≈ 14 + (cur-role mid) ≤ 249 components.

## 5. Rule comparison (per D1.2 Registry, only RULE_A / RULE_B allowed)

| Rule | Visible date | Large-delta rows | Small-delta rows | Verdict |
|---|---|---|---|---|
| RULE_A | ann_date | correct (ann is real disclosure date) | 1 day early (planned date) | reliable as visibility gate for 99.98% of signals |
| RULE_B | f_ann if present else ann | **catastrophically wrong** (2017 FY pushed to 2026) | correct (+1d) | single-field rule not usable |

RULE_B rebuild changes 381 signals (0.60%); by year 2020: 1.79% → 2024:
0.15% — these changes are dominated by erroneous large-delta removals.
RULE_A-has-value-but-RULE_B-not-visible at T: 0 signals.

## 6. Conclusion

Official semantics say `f_ann_date` = actual announcement date, but the data
itself mixes a true disclosure date (small delta) with a warehouse refresh
timestamp (large delta). Neither single rule is fully reliable:

**SEMANTICS_AMBIGUOUS (D1.2-C).**

Mitigating fact: under RULE_A the true visibility leakage is bounded at
~14–249 components (~0.02%–0.39% of signals); the large exposure count
(3,466) is dominated by warehouse timestamps, not real leakage. D1.1's
numeric corrections (revenue_ttm ~12.6% changed) come from the
update_flag/f_ann tie-break selecting the latest warehouse-refreshed row,
which is a version-choice policy, NOT a visibility leak.

## 7. Governing follow-up options (NOT executed this phase)

1. Hybrid rule (delta ≤30d → f_ann_date; delta >180d → ann_date) — requires
   a new preregistration and governance registration (Registry currently
   forbids a third rule without official-mandate + registration).
2. Canonical announcement-date source (exchange / cninfo daily snapshot)
   as authoritative visibility field — a new data layer.
3. Accept RULE_A as visibility gate with the documented ≤0.4% leakage bound
   and proceed to S3 — requires external-audit sign-off on the bound.
