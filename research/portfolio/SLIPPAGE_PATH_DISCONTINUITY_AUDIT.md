# SLIPPAGE_PATH_DISCONTINUITY_AUDIT

**Phase:** P3.1 — SLOT CONTENTION & PATH-DEPENDENCE MECHANISM AUDIT
**Date:** 2026-09-03
**Scope:** Pure sensitivity audit. **This is NOT evidence that any slippage level is "better".**

---

## 1. The anomaly to explain

P3 reported (PURE STOCK, 2020–2024, same frozen engine, only `slippage_bp` changed):

| version | 10bp | 20bp | 50bp |
|---|---|---|---|
| B0 (amount-top10) | +30.30% | +29.91% | +3.64% |
| B1 (ATR-top10)    | −18.66% | −7.99% | −14.28% |
| B2 (ATR-all)      | −56.69% | −50.83% | −54.36% |

B0 is monotone-ish (−0.39pp then −26.3pp, the 20→50 step reflecting many small
cost/quantity effects). **B1 is non-monotone: 20bp (−7.99%) is *better* than 10bp
(−18.66%).** B2 is also mildly non-monotone in the first step.

## 2. Mechanism: it is a path / integer-lot / slot-timing cascade, not a cost effect

Detailed trade-list diffs are in `results/p31_slippage_path_diff.csv`. The decisive
trade for B1 10→20bp:

- **10bp only:** `300750.SZ` entry **2023-09-11, −105,622 RMB (−23.61%, 5 levels)**.
- **20bp only:** `000625.SZ` entry 2024-01-05 (+29,390) and `601012.SH` entry
  2023-08-23 (−2,762).

Why CATL disappears at 20bp (verified against `ledger`/`eq` in `_p3_cache/B1_bp20.pkl`):

1. On **2023-09-08** (300750's signal date, entry T+1 2023-09-11), the 10bp path had
   `n_pos=2` + cash 598k → **1 free slot** → 300750 was **QUEUED**.
2. In the 20bp path, a different chain of earlier lot-sizings / add timings (higher buy
   prices → different `qty = int(min(level_cash,cash)/px/100)*100`, different avg-cost,
   different add/exit timing) had already pushed the portfolio to **`n_pos=3`** by
   2023-09-08 → 300750 was **BLOCKED_K** (never queued, never bought).
3. Avoiding the −105.6k CATL drawdown plus the two replacement trades and downstream
   changes net to the apparent "+106.8k" improvement (−186.6k → −79.9k).

So the 20bp "improvement" is the *portfolio accidentally being slot-blocked from a
catastrophic trade*, caused by a cumulative path difference that starts with small
lot-rounding at higher prices. It says nothing about 20bp being a better cost assumption.

The B1 20→50bp step is again chaotic: 5 trades dropped, 4 added, net −63k. B0's
20→50 step (−299.1k → −36.4k, i.e. −262.7k) is dominated by the same kind of
lot/cash/slot re-routing (top mover: `300014.SZ` 2023-02-21 −279k→−251k and
`601012.SH` 2024-01-30 +53k→+25k).

## 3. B2 (FULL-SIGNAL ATR): identical trade set, non-monotone PnL

B2 keeps the **same 55 trades** across 10/20/50/100bp (`only_low=0`, `only_high=0` at
every step), yet PnL moves −566.9k → −508.3k → −543.6k → −646.9k. With the same
(ts_code, entry_date) set, the only differences are **share quantities and add paths**
(higher buy price ⇒ fewer 100-share lots ⇒ smaller notional on the same names). B2 is
dominated by large losers, so "shrinking the position" mechanically reduces the losses
of the big losers at 20bp. This is a notional-shrinkage artifact, not an efficiency gain.

## 4. Conclusion

- **10 → 20 → 50bp is not a smooth cost function for B1/B2**; it is a
  path-discontinuity sensitivity driven by integer lot sizing, cash constraints and
  slot-timing cascades. No version's non-monotone step is evidence about slippage.
- Primary result remains the **10bp frozen baseline** (B0 +30.30%, B1 −18.66%).
- The extra 20/50bp runs (and 100bp for B2) are reported only as robustness band /
  discontinuity evidence, per P3.1 spec §16 and §18.

## 5. Files

- `results/p31_slippage_path_diff.csv` — full pair-wise trade-list diffs + top PnL movers.
