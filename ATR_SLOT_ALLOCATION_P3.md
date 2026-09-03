# ATR_SLOT_ALLOCATION — PHASE P3 (VALIDATED SINGLE-FACTOR SLOT ALLOCATION)

**Status:** Development / portfolio-construction counterfactual on 2020–2024. 2025–2026
Confirmation **CLOSED** (per `P3_FUTURE_CONFIRMATION_RULE.md`, not opened because Development
is not classified A). PURE STOCK primary.

---

## 0. Freeze state

| Item | Value |
|---|---|
| P2 Ranking Validation | B — PARTIAL VALIDATION; unique full PASS = **V04 / F09 ATR20_PCT (POSITIVE)** |
| P3 Registry | `ATR_SLOT_ALLOCATION_REGISTRY.csv`, commit **`5eca01d`**, SHA **`1e13f9f7`** |
| Confirmation rule | `P3_FUTURE_CONFIRMATION_RULE.md` (frozen pre-Development) |
| Engine | frozen `STRICT_C_EXECUTABLE_TICK` (`run_fast_multi_strict_c`); only INITIAL ENTRY CANDIDATE PRIORITY changes; entry/exit/add/cash/fees identical |
| Candidates | B0/B1 = Top10-by-amount universe ∩ oversold (identical set); B2 = ALL eligible oversold |
| Priority | B0 amount desc (frozen); B1/B2 ATR20_PCT desc (relative ranking only, no threshold) |
| ATR | ATR20 = mean(TR last20 observed bars), TR = max(high−low,|high−pre_close|,|low−pre_close|); ATR20_PCT = ATR20/close; T-close info |
| Portfolio | 1,000,000 RMB, K=3, 200k/layer, max5, T+1, 100-lot, PIT ST, listing≥60d, 10bp slip, fees+historical stamp, STRICT_C tick, dynamic P*, add_gap=1 |
| Period | 2020-01-01 ~ 2024-12-31 (N2024=1212 days) |
| Red lines | no composite, no threshold search, no weight tuning, no ML, no Market Gate, no stop/exit tuning, no 2025+ data |

---

## 1. Portfolio results (PURE STOCK, 10bp, 2020–2024)

| | B0 (frozen) | B1 = P3-A SAME-TOP10 ATR REORDER | B2 = P3-B FULL-SIGNAL ATR RANK |
|---|---|---|---|
| Total return | **+30.30%** | **−18.66%** | **−89.15%** |
| CAGR | +5.66% | −4.20% | −36.99% |
| MaxDD | −30.79% | −42.40% | −91.62% |
| Sharpe | 0.347 | −0.023 | −0.652 |
| Sortino | 0.492 | −0.032 | −0.545 |
| Calmar | 0.184 | −0.099 | −0.404 |
| Trades | 76 | 68 | 55 |
| Win rate | 68.4% | 67.6% | 49.1% |
| Profit factor | 1.304 | 0.849 | 0.549 |
| Stock PnL | +302,951 | −186,625 | −566,888 |
| PnL / slot-day | +114.9 | −71.1 | −161.3 |
| Slot-occ days | 2,637 | 2,624 | 3,515 |

**B0 parity: PASS** — matches frozen G0 (t3) exactly (total 30.2951, ann 5.6564, mdd
−30.7897, Sharpe 0.3468, n=76, stock_pnl 302,950.94).

**Headline: ATR ranking does NOT improve the portfolio — it destroys it.** B1 (pure priority
reorder, identical universe) −18.66% vs +30.30% baseline; B2 (universe expansion to all
eligible oversold) −89.15%.

## 2. Yearly (B0 vs P3-A)

| year | B0 | B1 | B2 |
|---|---|---|---|
| 2020 | +8.12% | +9.23% | +1.70% |
| 2021 | +31.86% | −6.44% | −7.77% |
| 2022 | +1.93% | +5.70% | −34.98% |
| 2023 | −10.65% | −16.28% | −23.84% |
| 2024 | +0.35% | −10.06% | −76.65% |

B1 is better only in 2020 (+1.1pp) and 2022 (+3.8pp); much worse in 2021/2023/2024. The
2021 collapse (below) permanently depresses B1 equity (−490k to −506k vs B0 from 2022-03
onward; max divergence −505,860 on 2022-04-27).

## 3. Decision-level attribution (the core evidence)

### 3.1 Contested days are rare — and that's exactly where ranking flips

Top10 universe → only **7 contested signal days** in 2020–2024 (≥2 oversold Top10 candidates
competing for 1 slot), 336 BLOCKED_K candidates on those dates. On the days where ATR actually
changed the pick:

| signal_date | baseline pick | ATR pick | baseline realized | ATR realized | ATR better? |
|---|---|---|---|---|---|
| 2021-02-25 | 300059 | 002594 | −10,815 | **+137,850** | ATR (+148.7k) |
| 2021-04-15 | 601166 | 600276 | **+19,182** | +5,890 | baseline (+13.3k) |
| 2021-05-24 | 000661 | 002714 | **+18,777** | −132,078 | baseline (+150.9k) |
| 2021-11-16 | 600030 | 000625 | **+15,781** | −130,012 | baseline (+145.8k) |
| 2022-03-03 | 000858 | 300014 | −16,907 | **+21,516** | ATR (+38.4k) |
| 2022-10-12 | 600519 | 002371 | −6,638 | **+19,113** | ATR (+25.8k) |

6 direct swaps → **ATR net −97k**. ATR's wins are frequent but small (+178.5k); its two
catastrophes (002714 −31.9% and 000625 −21.6%, both ATR-high large caps on stress days)
cost −262k. Baseline's losses are small (−34k total) and wins modest (+53.7k). The payoff
asymmetry is the opposite of what a "high-volatility = better mean-reversion" hypothesis
needs.

### 3.2 Trade diff B0 vs B1

B0_ONLY 20 trades (PnL +205,817; winners 002594 +131.6k, 600519, 300274 +48k, 600111 +43.8k,
600031 +27.8k, 002340 +31.6k, 300750 +19.1k, 601166 +19.2k…) vs B1_ONLY 12 trades
(PnL −236,303; losers 002714 −132.1k, 000625 −130.0k, 000651 −124.8k, 300750 −105.6k…).
Net direct+cascade swing ≈ **−442k** on a 1M account; remaining delta comes from common-trade
path differences and subsequent slot availability (blocked-by-K 336→350).

## 4. Frozen-episode contested diagnostic (B0 slot-state anchored)

On the 7 contested days (k=1): ATR top-1 mean vs baseline top-1 mean — 2021-05-24 +3.54 vs
−18.72; 2021-11-16 +7.94 vs −22.23; 2021-12-20 +6.47 vs +1.84 (ATR better). Where ATR
changed the pick it was wrong more often and with far larger losses; pairwise accuracy NaN
(<5 valid pairs/day). **The positive pooled ATR IC (+0.134) does not survive the contested
tail** — on the days where the K=3 portfolio must choose, ATR-priority picks were worse.

## 5. Blocked opportunities & capital efficiency

| | B0 | B1 | B2 |
|---|---|---|---|
| candidates enumerated | 530 | 530 | 252,477 |
| queued | 78 | 85 | 58 |
| BLOCKED_K | 336 | 350 | 252,277 |
| PnL/slot-day | +114.9 | −71.1 | −161.3 |
| avg positions/day | 2.18 | 2.17 | 2.90 |

B2's 252k candidates are the full-universe oversold pool (Top10 enumeration is only 530):
removing the turnover restriction floods the pool with low-liquidity names.

## 6. Liquidity risk (§17) — B2 is an execution nightmare

| | B0 | B1 | B2 |
|---|---|---|---|
| n selected | 78 | 85 | 58 |
| median amount | 5.99M | 5.36M | **0.22M** |
| P10 amount | 3.64M | 3.43M | 0.056M |
| median amount-rank | 5 | 6 | **1,018** |
| amount / 200k-layer P50 | 29.9 | 26.8 | **1.10** |
| P95 amount/layer | 51.4 | 47.2 | 8.33 |

At the median, B2's 200k layer is ~90% of the stock's entire daily amount (ratio ≈1.1) —
the frozen 10bp slippage assumption is unrealistically benign there; actual execution would be
far worse than the −89% already recorded.

## 7. Slippage stress (§18)

| | 10bp | 20bp | 50bp | 100bp |
|---|---|---|---|---|
| B0 | +30.30% | +29.91% | +3.64% | — |
| B1 | −18.66% | −7.99% | −14.28% | — |
| B2 | −89.15% | −90.84% | −94.37% | −95.67% |

No slippage level rescues B1 or B2; B2 degrades monotonically to −95.7% at 100bp.

## 8. ETF secondary — NOT RUN

Per §19: "如果 P3-A 不改善，ETF 不需要救结果." P3-A is strongly negative → ETF secondary
explicitly skipped. No stock/ETF leg attribution produced.

---

## 9. Development classification (PRIMARY P3-A)

**C — NO USEFUL PORTFOLIO RANKING.**

All five A-gates fail hard: CAGR −4.20% vs +5.66%; Sharpe −0.023 vs +0.347 (Δ ≈ −0.37, no
improvement); MaxDD −42.40% vs −30.79% (11.6pp worse); PnL/slot-day −71 vs +115; years
improved 2/5 and the improvement is not the story — the 2021 collapse dominates.

**Interpretation (consistent with T3):** the validated signal-level ATR ranking
(mean daily CS IC +0.134, K3 lift +1.43pp on independent episodes) **does not translate to
the K=3 finite-capital portfolio**. The pooled IC is dominated by the many non-contested
days where ranking is irrelevant; on the rare contested days where slot allocation actually
bites, ATR-priority picks were systematically worse (payoff-asymmetric losses). Removing the
Top10 turnover restriction (B2) is catastrophic both economically (−89%) and in execution
reality (200k ≈ 90% of median daily amount).

## 10. Future confirmation — NOT opened

Per `P3_FUTURE_CONFIRMATION_RULE.md`: only if Development P3-A is classified **A**. It is C →
**2025–2026 Confirmation remains CLOSED**. No threshold search, no composite, no re-ranking.

## 11. Deliverables

- `ATR_SLOT_ALLOCATION_REGISTRY.csv` + `.sha256`, `P3_FUTURE_CONFIRMATION_RULE.md`
- `atr_slot_allocation_p3.py`
- `results/p3_portfolio_summary.csv`, `p3_yearly.csv`, `p3_trade_diff.csv`,
  `p3_selection_changed_events.csv`, `p3_contested_signal_diagnostic.csv`,
  `p3_blocked_opportunities.csv`, `p3_capital_efficiency.csv`, `p3_path_divergence.csv`,
  `p3_liquidity_risk.csv`, `p3_slippage_stress.csv`
