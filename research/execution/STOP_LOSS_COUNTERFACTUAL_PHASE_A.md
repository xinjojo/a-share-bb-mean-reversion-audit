# STOP-LOSS COUNTERFACTUAL — PHASE A
## STRICT_C / FULL-MARKET SECONDARY + PRIMARY BENCHMARK

**Status:** frozen-episode price-stop counterfactual, descriptive + deterministic stress. No parameter optimization. Validation (2023-2024) remains **CLOSED**. Hypothesis Registry SHA256 unchanged: `5c5e451ad4eb3afd5e632b0019a3e02103e58e375e03cc231c5d8ca52b8c5195`.

---

## 1. Purpose & scope

Single research question:

> If a **fixed price stop** is attached to the **FIRST ENTRY EXECUTION PRICE** of the audited V2A_FROZEN_STRICT episodes, does it significantly improve left-tail risk and overall trade quality without over-killing future winners?

Frozen samples:

| sample | semantic | n realized | censored |
|---|---|---|---|
| PRIMARY (Top10) | V2A_FROZEN_STRICT | 299 (290 TP + 9 FS) | 0 |
| SECONDARY (all eligible) | V2A_FROZEN_STRICT | 89,046 (87,620 TP + 1,426 FS) | 124 |

Frozen-episode discipline:

- Initial signal / entry / adds are taken **from the frozen baseline** (re-recorded with per-layer + per-day path, verified 1:1 against `independent_v2a_episodes.pkl` and `fullmarket_episode_metrics.csv`).
- The counterfactual **never releases held slots** to generate new signals — it only re-plays each episode's own path under the stop. This is **not** a re-run of the portfolio/signal-generation system.
- STOP_TRIGGERED → **no further add**.
- Partial-sell **T+1 legal semantics**: only unlocked layers (buy day + 1 market day) are sold at each stop fill; locked layers liquidate at the first unlocked day.
- **Stop-market semantics**: if open < stop_price → gap-through, fill at open; else fill at stop_price. Fill price then × (1 − 10bp slippage). Reachability requires exec ref > limit_down price; otherwise STOP_PENDING carried forward.
- P\* TP (baseline exit) unchanged. Same-day stop/TP collision → two pre-registered bounds **STOP_FIRST** / **TP_FIRST**.
- Censored 124 → three 口径: REALIZED_ONLY / CENSORED_PESSIMISTIC / STOP_RESCUED_CENSORED.

Frozen grid (no finer thresholds added): NO STOP baseline + **−10 / −12.5 / −15 / −17.5 / −20 / −22.5 / −25 / −27.5 / −30 / −35 / −40%**.

Forbidden: changing exit P\* / BB / entry / Top10 / max levels / add rule; time/trailing/regime/ranking filters; joint optimization; picking "best" threshold.

---

## 2. Sample & engine verification (before any results)

1. **Frozen-sample parity**: PRIMARY re-record 299/299 (0 mismatch on ts_code+entry_date → exit_date/exit_type/return to 0.01pp); SECONDARY re-record 89,046/89,046 (0 mismatch); censored 124 = frozen-reported count.
2. **No-trigger path (internal sanity)**: with stop = −99%, **0/89,046 triggered** and `max|cf_ret − ret0| = 0.000000` — the baseline-return path reproduces the frozen baseline exactly, validating exit_row indexing and the no-stop return branch end-to-end.
3. **Hand-check of a triggered episode** (`300433.SZ`, 2020-03-10 entry, −20% stop):
   - base = 18.028 → stop_price = 14.422 (= 18.028 × 0.8 ✓)
   - L1 @18.028 (i=42), L2 @15.435 (i=48); trigger row i=51: open 15.030 > stop → ref = stop 14.422; limit_down 14.150 < ref ✓ executable; both layers unlocked (T+1 satisfied) → both sold at 14.422×0.999.
   - **manual ret = −13.4862 == engine cf_ret (delta 0.0000)**.
   - This episode is a baseline **winner** (+14.69%) that the stop cut at −13.5% — the canonical "killed winner" mechanism.

---

## 3. Headline results

### 3.1 SECONDARY (full market, STOP_FIRST)

| stop | mean% | median% | win% | PF | P5% | hold_med | trig% | exec% | agg PnL (M¥) |
|---|---|---|---|---|---|---|---|---|---|
| **NO STOP** | **5.282** | **5.452** | **77.66** | **1.816** | **−11.84** | **25** | – | – | **+1008.5** |
| −10.0 | 2.538 | 2.116 | 54.58 | 0.918 | −9.70 | 19 | 43.65 | 43.65 | −118.2 |
| −12.5 | 2.897 | 3.404 | 60.74 | 0.946 | −10.71 | 20 | 35.83 | 35.83 | −86.1 |
| −15.0 | 3.159 | 4.038 | 65.19 | 0.968 | −11.99 | 21 | 29.45 | 29.45 | −54.9 |
| −17.5 | 3.365 | 4.407 | 68.32 | 0.984 | −13.45 | 22 | 24.33 | 24.33 | −29.3 |
| −20.0 | 3.530 | 4.646 | 70.54 | 0.997 | −14.94 | 22 | 20.23 | 20.22 | −4.9 |
| −22.5 | 3.706 | 4.831 | 72.24 | 1.021 | −16.44 | 23 | 16.67 | 16.67 | +39.0 |
| −25.0 | 3.870 | 4.981 | 73.55 | 1.047 | −17.89 | 23 | 13.74 | 13.74 | +88.1 |
| −27.5 | 3.995 | 5.073 | 74.45 | 1.067 | −19.35 | 24 | 11.36 | 11.36 | +126.1 |
| −30.0 | 4.130 | 5.161 | 75.21 | 1.098 | −20.65 | 24 | 9.36 | 9.36 | +183.3 |
| −35.0 | 4.383 | 5.279 | 76.20 | 1.181 | −21.37 | 24 | 6.20 | 6.20 | +325.6 |
| −40.0 | 4.628 | 5.353 | 76.82 | 1.291 | −16.62 | 24 | 3.95 | 3.95 | +489.8 |

- **Every one of the 11 thresholds lowers mean return** (Δ −2.74pp at −10% → −0.65pp at −40%), monotonically approaching but **never exceeding** baseline.
- **Every threshold lowers PF** below baseline 1.816; PF only crosses 1.0 from −22.5% outward, and stays far below baseline.
- Aggregate PnL drops from **+1,008.5M¥** to **−118M¥** at −10% (net negative!), ≈0 at −20%, and only turns positive at −22.5%+.
- The only "improvements" are **mechanical left-tail truncations** (P5/ES/worst move up because losses are capped at the stop) — at the cost of cutting winners.

### 3.2 PRIMARY (Top10, STOP_FIRST)

Baseline: mean +4.955%, median +5.219%, win 75.92%, PF 1.593, P5 −17.21%, hold 28d.
Identical monotone pattern: mean 1.64% (−10%) → 4.62% (−40%), all below baseline 4.96%; PF < baseline at all 11; NET_STOP_VALUE negative at all 11. **Top10 does not change the stop verdict.**

### 3.3 Collision (STOP_FIRST vs TP_FIRST)

On the baseline TP exit day, `low ≤ stop` (true same-day collision) is essentially never observed: SECONDARY 2–34 of 87,620 TP exits (0.002–0.04%); PRIMARY 0. STOP_FIRST ≡ TP_FIRST to within noise → intraday ambiguity is **immaterial**.

---

## 4. NET_STOP_VALUE (the decisive metric)

`NET = saved_loss_from_baseline_losers − lost_future_profit_from_baseline_winners`

| stop | n_killed (winners cut) | killed % of winners | n_saved (losers improved) | saved % of losers | net (M¥) | net per 1000 ep (M¥) |
|---|---|---|---|---|---|---|
| −15.0 | 21,957 | 31.8 | 6,441 | 32.4 | −1,063 | −11.94 |
| −20.0 | 18,054 | 26.1 | 4,925 | 24.8 | −1,013 | −11.38 |
| −25.0 | 15,855 | 22.9 | 4,041 | 20.3 | −920 | −10.34 |
| −30.0 | 14,616 | 21.1 | 3,574 | 18.0 | −825 | −9.27 |

Baseline population: 77.7% winners (69,151) / 22.3% losers (19,895).

**NET_STOP_VALUE < 0 at all 11 thresholds.** At −20%, 26.1% of baseline winners are cut (lost upside) vs 24.8% of baseline losers improved — and in PnL the lost winner upside (−1.13B¥ cumulative across the grid's most damaging end) dwarfs the saved loser downside.

### Mechanism

The stop helps **only** the baseline losers deeper than the stop level (per-strata analysis: at −20% stop, baseline strata < −30% / −30~−20 / −20~−10 get +22.1 / +9.2 / +0.4pp mean Δ, with 97–100% trigger). But those strata are only **5,440 episodes = 6.1%** of the population. For everyone else — mild losers (−10~0: −3.35pp) and **all** winners (0~5: −1.56pp; 5~10: −1.43pp; >20: −5.14pp at −20%) — the stop interrupts the recovery-to-upper-band process that is precisely where this signal's positive expectancy comes from. The mean-reversion edge is the winner-recovery; a hard stop on the first-entry price cuts it.

---

## 5. Robustness / time-stability checks

- **EARLY (2020-2022) vs LATE (2023-2026):** net_stop_value negative in **both** periods at every threshold (EARLY −298M¥ to −73M¥; LATE −715M¥ to −446M¥ at −20/−40%). Direction consistent; no reversal.
- **Year-by-year:** net negative in every year 2020–2026 at every threshold.
- **2026 alone (weak period):** net negative at all 11 stops; even −40% lowers 2026 mean (2.32 vs baseline 2.75). **The stop does not help the deteriorating recent period either.**
- **Event-day inference (SECONDARY, primary unit):** `delta_daily_mean` (cf − baseline daily cross-sectional mean) is negative with HAC 95% CI entirely < 0 at all 11 thresholds (e.g., −20%: [−1.87, −1.08]pp). The signal's own daily mean stays positive at all stops (block-bootstrap CI > 0), i.e. the damage is statistically robust, not noise.
- **Levels diagnosis:** trigger rate rises steeply with baseline levels (L1 2.6% → L5 72% at −20%). The stop "rescues" L5 traps (saved_loss 274.5M¥ at −20%) but lost_winner_profit on L5 (−360.5M¥) exceeds it; L5 mean Δ is −2.7pp. Association only — no level re-optimization.
- **Censored sensitivity:** pessimistic −100% for un-rescued censored pulls the SECONDARY mean by only −0.05 to −0.12pp (rescued 35–91 of 124 depending on threshold). **Does not change the conclusion.**
- **STOP_FIRST vs TP_FIRST:** identical to within ≤0.04% collisions. **Does not change the conclusion.**

---

## 6. Conclusion

No threshold simultaneously improves mean, PF and tail metrics; no threshold produces NET_STOP_VALUE > 0; there is **no robust stop plateau** (mean/PF only monotonically approach the baseline as the stop loosens, never exceed it).

**Classification: C — NO USEFUL STOP.**

The stop only buys mechanical tail truncation (P5/ES improve because losses are capped) and pays for it with a strictly lower mean, lower PF, lower win rate and a large negative NET_STOP_VALUE at every one of the 11 pre-registered thresholds, in both samples, in both collision bounds, in every year, and in both EARLY/LATE periods. For a positive-expectancy mean-reversion signal whose edge is the recovery to the upper band, a fixed price stop on the first-entry price destroys more winner upside than it saves in loser downside.

Per audit discipline this report states **no** "best stop"; the honest summary is that no stop threshold in the frozen grid improves the strategy's economics. Following the phase discipline, **no** max-level or time-stop experiment is started; Validation remains closed.

---

## 7. Deliverables

- `stop_loss_counterfactual_phase_a.py` — recorder + counterfactual engine + all stats + figures
- `results/stop_phaseA_summary.csv`, `stop_phaseA_primary.csv`, `stop_phaseA_secondary.csv`
- `results/stop_phaseA_eventday.csv`, `stop_phaseA_early_late.csv`, `stop_phaseA_yearly.csv`
- `results/stop_phaseA_killed_winners.csv`, `stop_phaseA_saved_losers.csv`, `stop_phaseA_net_value.csv`
- `results/stop_phaseA_levels.csv`, `results/stop_phaseA_strata.csv`
- `results/stop_phaseA_tailrisk.csv`, `results/stop_phaseA_collisions.csv`, `results/stop_phaseA_censored_sensitivity.csv`
- `results/stop_phaseA_episode_detail.csv.gz` (full per-episode × 22 (threshold×bound) detail, 1,965,590 rows), `results/stop_phaseA_episode_detail_primary.csv` (plain, PRIMARY)
- `figures/stop_threshold_vs_{mean_return,profit_factor,p5_return,expected_shortfall,net_stop_value,killed_vs_saved,hold_days,early_vs_late,stopfirst_vs_tpfirst,by_baseline_levels}.png`, `figures/stop_return_distribution_comparison.png`
