# FULL-MARKET TRADE PATH AUDIT — SECONDARY ALL ELIGIBLE + PRIMARY TOP10 BENCHMARK

> 描述性 / 结构性审计。不调参、不优化止损止盈层数、不新增规则、不开 Validation 2023-2024、不改 Registry。
> 冻结语义：**V2A_FROZEN_STRICT**（与 frozen `run_fast_multi_strict_c` 做过 PRIMARY 299/299 逐笔 parity）。
> 路径口径：**FIRST_ENTRY_PRICE_PATH only**（NAV = raw_price_t / 第一次买入执行价 open×(1+slip)）。TWR/economic NAV 已被外部审计判暂时 INVALID，本报告一律不用。

---

## 0. Count Gate —— 必须先解释的数量差异

指令要求：SECONDARY replay 数量与 V1 的 89,188 一致，不一致先 STOP 并解释。

**对账结果（V1 per-stock resume vs V2A frozen）：**

| 口径 | episodes | TP | FS | censored |
|---|---|---|---|---|
| V1（per-stock resume，诊断参考） | 89,188 | 87,638 | 1,550 | — |
| V2A（冻结语义，主基线） | **89,046** | 87,620 | 1,426 | **124** |
| V2A 总 entries（realized+censored） | 89,170 | | | |
| Δ entries | **18** | | | |

Entry-key 对账：both = 89,165；only_v1 = 23；only_v2 = 5。

**差异根因（两个机制，与 PRIMARY 600150.SH 同型，是 V1→V2A 已审计语义修正的规模化表现，非 bug）：**

1. **Pending-buy CANCEL（23 笔 V1-only）**：V2A 冻结语义下，T 日收盘信号 → T+1 若该股无行情/停牌/缺失，pending buy **取消**；V1 按 per-stock 有行情序列**顺延**。这 23 笔中有 5 笔在后续某日重新触发信号、以新 entry 入场（即 5 笔 V2A-only：000552.SZ 2022-12-23 / 000597.SZ 2020-09-30 / 002633.SZ 2025-09-03 / 601989.SH 2024-09-20 / 688165.SH 2026-02-12）；其余 18 笔未再触发、净消失。净效应 −23+5 = **−18**。
2. **退市股末日持仓 censoring（124 笔）**：V1 把这 124 笔（全部为已知退市股在数据末日的未平仓）按最后 close 强制 FINAL_SETTLE；V2A 按冻结语义标为 **censored（不计入 realized headline）**。V1 FS 1,550 = V2A FS 1,426 + 124 censored，精确自洽。

**Common realized 对账（89,041 笔，exit_date 一致、格式仅 ' 00:00:00' 后缀差异）：**
- 其中 **50 笔** 收益（2dp）不同：30 笔 levels_used 不同、46 笔 total_cost 不同、4 笔 exit_date 不同 —— 由 **pending-add CANCEL**（T+1 加仓日停牌/缺失则取消该层）驱动，是 V2A 与 V1 在加仓路径上的语义差异，非未来函数或 PIT 泄漏。
- 其余 88,991 笔 realized 在 V2A 与 V1 下完全一致。

**立场**：以 **V2A_FROZEN_STRICT（89,046 realized + 124 censored）为冻结主基线**；V1 89,188 仅作诊断对照。所有 headline 均基于 V2A。

---

## 1. 样本与执行语义

- PRIMARY：已冻结 V2A_FROZEN_STRICT Top10，299 笔（= 上轮 PATH AUDIT 样本，未改）。
- SECONDARY：同一冻结引擎、同一参数，**唯一差异 = 无 Top10**（全部 PIT eligible 且 close_adj < BB lower 即产生信号）。
  - 信号：T close 确认 → T+1 open 买入（100 股整手、10bp 双腿滑点、历史印花税、手续费、过户费）。
  - 退出：dynamic self-consistent P*（analytic_Pstar，ddof=1）+ legal tick ceil + ref_first 跌停可达性；TP 87,620 / FS 1,426（FINAL_SETTLE 仅末日有行情股，计入 realized；另有 124 censored 不进入 headline）。
  - PIT ST、真实 list_date+60 交易日、correct 涨跌停、T+1、加仓 gap=1、max 5 层 × 20 万。

---

## 2. Headline（SECONDARY, realized 89,046）

| 指标 | 值 |
|---|---|
| episodes | **89,046** |
| mean return | **+5.28%** |
| median return | **+5.45%** |
| win rate | **77.66%** |
| MAE_intraday median | **−8.36%**（mean −12.18%） |
| MFE_intraday median | +7.33% |
| hold median / mean | 25 / 31.1 天 |
| underwater median | 13 天 |
| giveback median | 1.96 pp |

**事件日统计（signal_date 日级截面均值，处理同日大量信号非独立）：**
- n_event_days = **1,494**
- daily mean = +3.94%，daily median = +4.11%，positive-day rate = 81.9%
- HAC t = **14.31**，95% CI **[+3.40%, +4.48%]**
- event-day bootstrap B=2000 CI [3.66, 4.24]，P(≤0) = 0
- block bootstrap L=21 B=2000 CI [3.28, 4.66]，P(≤0) = 0
- episode bootstrap B=5000 CI [5.21, 5.35]

（episode n=89k 不当作 89k 独立事件；显著性以 event-day 为主。）

---

## 3. PRIMARY vs SECONDARY 对照

| 指标 | PRIMARY_TOP10 (299) | SECONDARY_ALL (89,046) |
|---|---|---|
| mean return | +4.96% | **+5.28%** |
| median return | +5.22% | **+5.45%** |
| win rate | 75.9% | **77.7%** |
| MAE median | −10.37% | −8.36%（更浅） |
| MAE P10 / P5 | −30.8 / −37.2 | −29.2 / −37.5 |
| MFE median | 7.65% | 7.33% |
| hold median | 28 | 25 |
| underwater median | 15 | 13 |
| giveback median | 2.10 | 1.96 |

**结论：Top10 成交额筛选在本 trade-level 框架下不带来可测量的质量提升** —— 全市场在 mean/median/win 上反而略高，且 median MAE 更浅；PRIMARY 唯一略优的是 MFE（+7.65 vs +7.33）。这属于“Trade-level edge”观察，不代表组合层结论。

> 注意：SECONDARY 内的 A_TOP10 bucket（rank≤10，228 笔）≠ PRIMARY 独立样本（299 笔），因为全市场 replay 下 held/pending 会阻塞部分 Top10 信号；PRIMARY 299 仍为 Top10 的权威样本。

---

## 4. 成交额排名分层（SECONDARY，signal 当日 PIT eligible 内 amount 排名）

| bucket | n | ret_mean | ret_med | win | MAE_med | MFE_med | hold | giveback |
|---|---|---|---|---|---|---|---|---|
| A Top10 | 228 | 4.77 | 4.91 | 74.1 | −10.97 | 7.03 | 28 | 2.11 |
| B 11–50 | 701 | 4.77 | 5.01 | 71.6 | −10.87 | 7.43 | 26 | 2.49 |
| C 51–200 | 2,437 | 4.59 | 4.72 | 71.8 | −11.13 | 7.47 | 27 | 2.50 |
| D 201–500 | 5,136 | 4.70 | 4.63 | 71.6 | −10.35 | 7.41 | 26 | 2.36 |
| E >500 | 80,544 | **5.35** | **5.51** | **78.3** | **−8.17** | 7.32 | 25 | 1.92 |

观察（描述性，不据此选参）：最高成交额档（A–D）收益略低、MAE 更深；最低流动性档（E，占样本 90%）收益略高且 MAE 更浅。**不存在“越靠前越优”的单调结构**；E 档更优也叠加了小市值/低流动性可行性风险（见 §10 幸存者偏差），不得据此反推应放松 Top10。

---

## 5. MAE 阈值 —— 风险断点大样本确认

**累计 P(win | MAE_intraday ≤ threshold)：**

| 阈值 | PRIMARY 胜率 | SECONDARY 胜率 | SECONDARY n |
|---|---|---|---|
| −5 | 67.8 | 66.8 | 59,168 |
| −10 | 58.7 | 53.3 | 37,849 |
| −15 | 51.3 | 42.4 | 25,177 |
| −20 | 35.0 | 35.3 | 16,520 |
| −25 | 29.4 | 30.0 | 11,557 |
| −30 | 21.9 | 26.2 | 8,400 |
| −40 | 0.0 | 21.1 | 3,519 |
| −50 | 0.0 | 12.2 | 1,068 |

**互斥 bin（SECONDARY）：**

| MAE bin | n | 胜率 | mean 最终收益 |
|---|---|---|---|
| 0 ~ −5 | 29,862 | 99.2% | +10.15% |
| −5 ~ −10 | 20,312 | 92.4% | +7.88% |
| −10 ~ −15 | 12,650 | 76.0% | +4.87% |
| **−15 ~ −20** | 8,212 | **58.1%** | +2.59% |
| **−20 ~ −25** | 5,778 | **46.5%** | +0.72% |
| −25 ~ −30 | 3,901 | 38.1% | −1.72% |
| −30 ~ −40 | 4,812 | 29.9% | −5.07% |
| ≤ −40 | 3,519 | 21.1% | −13.86% |

**-20% 风险断点：CONFIRMED（全市场 8.9 万笔同样存在）** —— 胜率在 −15~−20 与 −20~−25 之间从 58% 跌到 47% 的断点，与 PRIMARY 299 笔观察一致；再深至 −30 后 mean 收益转负。此断点已从“小样本现象”升级为“普通规律”。

---

## 6. Winner / Loser（SECONDARY）

| group | n | ret_mean | ret_med | MAE_intraday P1/P5/P10/P25/P50 | MFE P50 | hold P50 | underwater P50 |
|---|---|---|---|---|---|---|---|
| WINNER | 69,151 | +9.07 | +7.45 | −40.5 / −25.6 / −19.2 / −11.4 / **−6.08** | 8.79 | 21 | 6 |
| LOSER | 19,895 | −7.90 | −4.91 | −60.0 / −49.5 / −43.5 / −32.9 / **−22.6** | 2.97 | 50 | 43 |

**赢家 MAE 下尾解读（lower-tail quantile，纠正上轮 P95 误标）：**
- 95% 的赢家**没有跌得比 P5（−25.6%）更深**；
- 75% 的赢家没有跌破 −11.4%；中位赢家最大浮亏 −6.1%。
- 赢家突破深度占比：曾破 −5% 的赢家 57.1%、破 −10% 30.0%、破 −15% 16.1%、破 −20% 9.2%、破 −25% 5.3%、破 −30% 3.2%。

---

## 7. 年度稳定性 & 时间切分

| year | SECONDARY n | ret_mean | ret_med | win | MAE_med | MAE_P10 | MFE_med | giveback | hold |
|---|---|---|---|---|---|---|---|---|---|
| 2020 | 8,963 | 4.39 | 4.62 | 76.1 | −8.33 | −26.9 | 6.73 | 2.15 | 26 |
| 2021 | 10,532 | 5.81 | 5.70 | 81.7 | −6.76 | −22.0 | 7.77 | 1.93 | 23 |
| 2022 | 15,514 | 5.83 | 6.18 | 80.6 | −8.79 | −29.2 | 7.71 | 1.68 | 25 |
| 2023 | 15,487 | 3.18 | 4.64 | 74.7 | −7.82 | −36.4 | 6.13 | 1.79 | 26 |
| 2024 | 13,576 | 6.01 | 5.74 | 74.5 | −12.11 | −34.4 | 7.80 | 2.23 | 26 |
| 2025 | 14,728 | 8.17 | 6.84 | 88.7 | −5.59 | −18.6 | 8.57 | 1.62 | 21 |
| 2026 YTD | 10,246 | **2.75** | 3.16 | **63.2** | **−13.59** | −33.4 | 6.78 | **3.45** | 28 |

**2026 是否恶化：YES（相对转弱但未崩塌）** —— 2026 YTD mean 降至 +2.75%、胜率 63%、MAE 加深（P50 −13.6，全样本最深）、giveback 升至 3.45pp、持有期拉长到 28 天。与 PRIMARY 299 笔观察一致：**持仓质量在 2026 明显转弱**（收益降、浮亏深、回吐大、恢复慢），但样本仍为正收益，不能据此说 edge 归零。

时间切分：2020–2023（n=50,496）mean 4.76 / MAE_med −7.99 / giveback 1.85；2024–2026（n=38,550）mean 5.97 / MAE_med −8.88 / giveback 2.12 —— 后段整体反而更强（2025 大年贡献），MAE 略深。

---

## 8. levels_used（ASSOCIATION ONLY，禁止因果表述）

| levels | n | ret_mean | ret_med | win | MAE_med | MAE_P10 | MFE_med | hold | underwater |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 32,468 | +9.75 | 8.75 | 92.6 | −2.75 | −10.3 | 11.59 | 15 | 1 |
| 2 | 23,431 | +6.50 | 5.89 | 86.1 | −7.94 | −20.1 | 7.04 | 23 | 12 |
| 3 | 13,660 | +3.89 | 3.77 | 74.9 | −12.77 | −27.5 | 4.98 | 33 | 24 |
| 4 | 7,655 | +2.07 | 2.04 | 63.9 | −17.43 | −35.1 | 4.29 | 44 | 33 |
| 5 | 11,832 | **−5.72** | −4.02 | **32.2** | −27.79 | −47.3 | 3.37 | 66 | 55 |

**大样本确认（CONFIRMED）**：levels_used 越高 → 收益、胜率、MFE 单调恶化，MAE 单调加深。但这是 **ASSOCIATION ONLY**：持续下跌本身触发更多加仓，不能写“加仓导致亏损”。L5 群体（n=11,832，占 13%）mean −5.7%/win 32%，是左尾风险的主要来源，与 PRIMARY 完全同构。

---

## 9. 同日信号聚集（crowding）

- 每 signal_date 信号数：P50=20，P75=55，P90=153，P95=256，P99=571，max=1,299；共 1,494 个 signal date。
- crowding bucket：

| signals/day | n_dates | n_episodes | ret_mean | win | MAE_med |
|---|---|---|---|---|---|
| 1–5 | 321 | 922 | 3.18 | 67.4 | −9.33 |
| 6–20 | 444 | 5,132 | 3.64 | 72.4 | −9.20 |
| 21–50 | 333 | 10,837 | 4.10 | 72.9 | −9.36 |
| 51–100 | 166 | 11,893 | 4.89 | 76.7 | −8.88 |
| >100 | 230 | 60,262 | **5.74** | 79.3 | −8.04 |

观察：市场极端恐慌日（单日 >100 信号）单笔 edge **反而略强**、MAE 更浅 —— 与“恐慌即机会”的均值回归直觉一致；但也需注意这些日子信号高度同源，事件日统计（§2）才是其显著性依据。

---

## 10. 尾部风险 & 集中度

- 总 PnL = +1.0085e9；bottom 1%（890 笔）= −28.8% 总 PnL；bottom 5%（4,452 笔）= −81.2%；bottom 10%（8,904 笔）= **−107.8%**（即深层左尾亏损超过全部净利，其余 ~90% 样本必须贡献 >100% 净利）。
- top 1%（890 笔）= +17.0%；top 5%（4,452 笔）= +52.9%。
- **去最佳 1% 后 mean = 4.93%（原 5.28%，仅 −0.35pp）；去最佳 5% 后 = 4.08%** → edge 不依赖少数超级赢家，主要由多数稳定小赚构成。
- worst 100 / 500 / 1000：mean_ret −33.8 / −22.7 / −19.4，mean_MAE −48 / −44 / −40，mean levels 4.0 / 4.2 / 4.4，mean hold 95 / 100 / 96 天。
- 收益贡献最大 10 只股票合计仅占总 PnL ~1%（每只 ~0.09–0.12%），无单一股票依赖。

**亏损结构：深层回撤尾部主导（大量普通小亏 + 少数超深浮亏），与 PRIMARY 一致。**

---

## 11. 退出质量（大样本确认）

- capture_ratio：close 中位 0.98、intraday 中位 0.87（退出捕获了绝大部分 MFE）。
- giveback：中位 1.96pp、mean 3.93pp。
- 盈利交易退出后机会成本：post-5D MFE>3% 占 40.1%、post-5D MFE>5% 占 28.4%、post-10D MFE>5% 占 40.2%、post-20D MFE>10% 占 33.7%、post-40D MFE>15% 占 34.1%。
- 退出后 60D 中位 MFE +11.5%、中位回撤后回吐 18.2%。

→ **“吃鱼身、留鱼尾”模式在 8.9 万笔中成立**：P* 退出有效锁定大部分收益，但确实系统性错过部分后续行情；属于描述性结论，本轮不据此改 exit。

---

## 12. 统计纪律

- 主推断以 **event-day level（signal_date 日级截面均值序列）** 为准：n=1,494，daily mean +3.94%，HAC t=14.31，CI [3.40, 4.48]；event-day bootstrap 与 block bootstrap（L=21）CI 均 >0、P(≤0)=0。
- episode-level 仅描述分布，**不因 n=89k 报极小 p 宣称“确定有效”**。
- 同日数百股票信号高度相关 → 已通过日级聚合 + HAC/block bootstrap 处理重叠依赖。

---

## 13. 结构性分类

**A. PRIMARY STRUCTURE GENERALIZES（结构性泛化）**，附一条重要限定：

- PRIMARY 观察到的 MAE/MFE/尾部结构在 8.9 万笔全市场样本中**稳定复现**：赢家浅浮亏/输家深浮亏的分离、−15~−20 到 −20~−25 的胜率断点、levels_used 越高质量越差、亏损由深回撤尾部主导、P* 退出“吃鱼身留鱼尾”。
- 但 **“Top10 成交额筛选提升交易质量”未获支持**：trade-level 上全市场反而略优于 Top10（mean/median/win 更高、median MAE 更浅）。这推翻了此前隐含的“Top10 是更优 signal subset”假设（至少在本独立交易框架下）。
- 2026 YTD 相对转弱（胜率 63%、MAE 加深、giveback 3.45pp），但正收益保持，未崩塌。

**禁止事项已遵守**：未调参、未跑止损/退出/层数/时间止损网格、未改 TopN/bucket 边界、未根据结果筛参数、未打开 Validation、未改 Registry（SHA256 仍为 `5c5e451a...`）、未使用 TWR。

---

## 14. 文件

- `full_market_trade_path_audit.py`
- `results/fullmarket_episode_metrics.csv`（89,046×51，逐笔全部路径指标）
- `results/fullmarket_gate_summary.csv` / `fullmarket_primary_secondary_compare.csv` / `fullmarket_turnover_rank_buckets.csv` / `fullmarket_mae_thresholds.csv` / `fullmarket_winner_loser.csv` / `fullmarket_winner_mae_breach.csv` / `fullmarket_yearly.csv` / `fullmarket_levels.csv` / `fullmarket_signal_crowding.csv` / `fullmarket_crowding_dist.csv` / `fullmarket_tail_risk.csv` / `fullmarket_worst_episodes.csv` / `fullmarket_remove_best.csv` / `fullmarket_top10_stocks.csv` / `fullmarket_exit_quality.csv` / `fullmarket_eventday_stats.csv`
- `figures/`：primary_vs_secondary_mae / primary_vs_secondary_mfe / mae_threshold_winprob_comparison / turnover_rank_vs_return / turnover_rank_vs_mae / levels_vs_quality_secondary / yearly_quality_primary_secondary / signal_crowding_vs_quality / secondary_mae_vs_final_return_hexbin / secondary_return_distribution（10 张）

## 15. 已知局限

- 幸存者偏差：与既往一致 —— 2020 后退市 229 只中 15 只完全缺失、147 只在库退市股数据截断；本报告无法声称消除 survivorship bias（E 档小市值结论需叠加此风险）。
- 无 PIT 市值/行业，截面分组仅按成交额排名（PIT 可得）。
- V2A 全市场与 V1 存在 18 笔 entry 差异 + 50 笔 common 收益差异（均源自 pending cancel 语义，见 §0）。
- 2024–2026 非 pristine OOS，仅 retrospective stability check。
