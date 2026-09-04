# SIGNAL SELECTIVITY S1 — BB DEPTH / RSI14 / SECTOR STRENGTH

阶段：PHASE R1.3 + S1（SIGNAL SELECTIVITY AUDIT）
状态：DEVELOPMENT DIAGNOSTIC / WAITING EXTERNAL AUDIT
样本：2020-01-01 至 2024-12-31 Development；2025–2026 CLOSED（未读取）

---

## 0. 治理链

- R1.3 治理（P6=D 接受、ADD-BUDGET CLOSED、开启 S1）：`9ca40bf12b573ed35ee06c24b212807a41e565e9`（已 push）
- S1-A prereg：`227ab944a3f1038609ca20f51848f90e7b571eed`（已 push，先于任何结果）
- Registry：`research/signal/registries/SIGNAL_SELECTIVITY_S1_REGISTRY.csv` + `.sha256`
- Registry SHA256：`146accc2b3160067dd0d9685d3ca4e601ff065dc6a34272f58ca3455e0aae304`
- 结果 commit：见本报告末尾 git SHA（`S1-B: signal selectivity audit results`）

## 1. 目的

K=3 槽位是稀缺资源。S1 只研究**入场选择**：能否通过「更极端的 BB 深度」「RSI 过滤」「板块强度」让有限槽位装进更高质量信号。**不改 exit**（STRICT_C upper BB k=2.0 冻结），**不修改真实 K=3 组合**，**不组合多因素**，**不做参数扫描**（仅冻结的 2.0/2.5/3.0 与 RSI 30/25）。

## 2. 引擎与数据

- 全市场独立 replay（V2A_FROZEN_STRICT 语义，entry_k 参数化）：T 日 close 信号 → T+1 open 入场；pending CANCEL；Pstar dynamic_touch（k=2 固定，analytic_Pstar）；TAKE_PROFIT_UB；FINAL_SETTLE；censored；100 股整手；10bp 双腿；历史印花税；PIT ST；list>=60d；涨跌停排除。
- 信号条件：`close_adj < lower_BB(20, k)`（k=2.0/2.5/3.0）；BB_Z = (close_adj − MA20)/SD20（sample std，k=2 下 `sd=(bb_mid−bb_lower)/2`）。
- RSI：Wilder RSI14（lookup 5237 只，只读 <=2024-12-31）；MACD(12,26,9) ewm adjust=False，仅 diagnostic。
- 地平线：`days[0..1211]` = 2020-01-01..2024-12-31（N=1212/1611）。2025+ 一律不读。

## 3. I1 parity（B20 vs 冻结 fullmarket dev 截断）

冻结 CSV `results/evidence/fullmarket/fullmarket_episode_metrics.csv`（2020-2026 全历史）截断 `signal_date<=2024-12-31` 得 64,072 笔（全部 TAKE_PROFIT_DYN）；S1 B20 重放得 63,785 笔（TP 61,828 / FS 1,957 / censored 102）。

差异 287 笔已**完全分解归因**（机器断言通过，`s1_b20_parity.json`）：

| 来源 | n | 说明 |
|---|---|---|
| (a) 2024-12-31 信号 T+1 入场在 2025-01-02 | 283 | S1 硬约束不读 2025，不执行跨年信号 |
| (b) 2024-12-31 停牌末仓 → censored | 4 | 000777.SZ / 002252.SZ / 300807.SZ / 002494.SZ；冻结 CSV 中这些持仓 2025 复牌自然 TP 退出（有对应 episode），S1 按 censored 语义不计入 CSV |
| 合计 | 287 | = 64,072 − 63,785 ✓ |

引擎一致性佐证：
- 剔除 (b) 4 笔后，B20 与 frozen_dev_pre 的 `(ts_code, signal_date)` 信号集合**完全一致**（assert 通过）；
- 同信号 `entry_date` 匹配率 = 1.0（同信号同日 T+1 入场，assert 通过）；
- B20 TP=61,828 与 F2.1 natural-exit parity 引用的 61,828 同源一致；
- 其余 98 笔 censored（2024-12-31 停牌）在冻结 CSV 中同样不存在（frozen 中亦长期停牌至 2026-08-25 期末）→ 不构成数量差。

结论：**引擎信号逻辑与冻结 replay 完全一致；数量差异全部由 hard-horizon 语义解释**。I1 PASS（declared parity scope = horizon-semantics）。

## 4. BB DEPTH（PRIMARY TEST）

### 4.1 基础指标（episode 等权，独立归一化）

| family | n | 信号保留 | mean | median | win | PF | MAE | hold(med) | censored |
|---|---|---|---|---|---|---|---|---|---|
| B20 | 63,785 | 100% | +4.85% | +5.22% | 75.98% | 1.71 | −10.69% | 25d | 102 |
| B25 | 31,833 | 49.9% | +4.77% | +4.94% | 72.01% | 2.09 | −10.66% | 26d | 48 |
| B30 | 7,773 | 12.2% | +3.52% | +4.25% | 66.98% | 1.88 | −10.74% | 27d | 11 |

### 4.2 嵌套比较（signal-day 等权；HAC maxlags=10；full-calendar moving-block bootstrap L=21 B=2000 seed=0）

| pair | point(pp) | HAC 95% CI | calendar 95% CI |
|---|---|---|---|
| B25 − B20_ONLY | **−2.12** | [−2.60, −1.64] | [−2.64, −1.67] |
| B30 − B25_ONLY | **−1.91** | [−2.59, −1.22] | [−2.56, −1.22] |

两个嵌套增量均为显著负值：**要求更深 BB 阈值才入场（B25/B30），比保持 k=2.0 的同深度信号显著更差**。B20 内部按 BB_Z bin（均为 k=2.0 触发）mean 单调上升（[-2,-2.5) 4.75% → [-2.5,-3) 5.15% → [-3,-3.5) 5.47% → <-3.5 4.88%），而 B25/B30 的**同一 bin** 明显更低（B25 [-2.5,-3) 4.75% vs B20 5.15%；B30 [-3,-3.5) 3.52% vs B20 5.47%）。即：有害的不是「深度」本身，而是**提高 k 阈值带来的延迟入场**（把已阴跌多日的弱势股纳入、错过快速深跌反弹；B25 样本含大量自 -2.0 阴跌至 -2.5 才触发的事件，而 B20 深 bin 只含触发日即为深跌的事件）。此机制解释为推断性说明，非结论。

### 4.3 年度稳定性

- B20 mean：2020 4.39 / 2021 5.81 / 2022 5.83 / 2023 3.18 / 2024 5.19
- B25：2.97 / 5.38 / 5.46 / 3.14 / 6.13（仅 2024 年优于 B20；2020 显著差）
- B30：1.45 / 4.92 / 4.35 / 1.20 / 4.52（2020/2023 很差）
- B25_ONLY vs B20_ONLY 逐年：仅 2024 年正（6.22 vs 4.91），其余 4 年负 → **1/5 年方向为正**。

### 4.4 Tail risk

| family | MAE<=−10% | MAE<=−20% | MAE<=−30% | hold>60d | hold>90d |
|---|---|---|---|---|---|
| B20_ONLY | 38.92% | 18.20% | 8.87% | 12.14% | 3.25% |
| B25_ONLY | 38.31% | 19.35% | 9.62% | 12.48% | 3.49% |
| B30 | 39.24% | 21.00% | 9.65% | 14.01% | 3.62% |

MAE<-30 与 >90d lock 随深度提升略有恶化 → **TAIL-RISK TRADEOFF 标记**。

### 4.5 BB DEPTH 分类

**D — HARMFUL**：B25 vs B20_ONLY 与 B30 vs B25_ONLY 的 event-day delta 均显著 <0（HAC 与 calendar CI 全部排除 0），年度仅 1/5 年为正，tail 略恶化。B30 按 Registry 只作 extreme sensitivity，不因任何结果升级为 primary。

## 5. RSI（Wilder RSI14）

### 5.1 基础指标

| family | n | 保留 | mean | median | win | PF | MAE | hold(med) |
|---|---|---|---|---|---|---|---|---|
| R30（B20 ∩ RSI<30） | 4,271 | 6.70% | +7.70% | +7.22% | 80.96% | 2.68 | −12.07% | 28d |
| R25（B20 ∩ RSI<25） | 735 | 1.15% | +9.68% | +8.46% | 80.14% | 3.05 | −12.39% | 28d |

### 5.2 RSI 与 BB 深度相关性

Spearman(RSI14, BB_Z) = **0.243**（中等相关，非完全重复）。

### 5.3 matched-depth 增量（signal-day 等权；RSI<30 vs RSI>=30 于冻结 BB_Z bin 内）

| bin | n_lo | n_ge | point(pp) | HAC CI | calendar CI |
|---|---|---|---|---|---|
| [-2.0,-2.5) | 2,491 | 46,718 | +0.45 | [−0.42, +1.32] | [−0.44, +1.32] |
| [-2.5,-3.0) | 1,137 | 10,838 | −0.30 | [−1.95, +1.34] | [−2.03, +1.19] |
| [-3.0,-3.5) | 523 | 1,817 | −0.63 | [−2.57, +1.31] | [−2.57, +1.16] |
| <-3.5 | 120 | 141 | +0.07 | [−4.23, +4.37] | [−4.45, +3.86] |

四个 bin 全部跨 0，方向 2 正 2 负 → **同一 BB 深度内 RSI 无稳定增量**。R30 vs B20（day-等权）point −0.02pp（HAC [−0.78,+0.74]，calendar [−0.84,+0.76]），无差异。

### 5.4 描述性矛盾（须如实报告）

- R30/R25 的 **episode-等权** mean/win/PF 显著高于 B20（+7.70% vs +4.85%；80.96% vs 75.98%），slot efficiency 亦高（见 §8）；
- 但 **signal-day 等权**下 matched-depth 增量与 R30−B20 均无显著性；
- 年度（episode-等权）：R30 4.40/7.82/9.18/**2.68**/11.35；R25 5.73/8.41/13.43/**2.22**/13.70——2023 年崩塌（2.68/2.22），其余年份高；
- Tail：R30 MAE<=−30% 12.03%（vs B20 8.86%）、hold>90d 3.79%——**尾部更深**。

即「表面强、day-等权下无前瞻增量、尾部更深」的混合画像。按 Registry，RSI 分类以 matched-depth + day-等权为准。

### 5.5 RSI 分类

**C — 无独立增量（主要重复 BB depth，未达 A/B gate）**。描述性 episode-等权强度已如实记录；**不得**因表面数字升级为 portfolio candidate。若未来重启 RSI，需单独 prereg（并先解释 day-等权与 episode-等权的分歧、以及 2023 的稳定性问题）。

## 6. SECTOR

**NOT RUN — PIT DATA NOT READY**。仓库无 PIT 历史行业归属（`stock_basic.industry` 为当前快照；无申万/中信历史分类），按 Registry I5/I6 禁止当前行业分类回填历史。`s1_sector_strength.csv` 状态 `NOT RUN / PIT DATA NOT READY`。这不是失败，是数据门禁。

## 7. MACD（diagnostic only）

MACD(12,26,9)：hist>0 mean +4.78%（n=1,889）vs hist<=0 +4.85%（n=61,896）；DIF>DEA 与 DIF<=DEA 同构。**无明显关系**，不构成 gate，不参与 S1 分类。

## 8. Signal Slot Efficiency（independent diagnostic，非组合收益）

| family | ep/100 signal-days | mean/ep | pos/1000 hold-days | norm PnL/1000 hold-days |
|---|---|---|---|---|
| B20 | 5,746 | +4.85% | 23.83 | 1.52 |
| B25 | 3,228 | +4.77% | 21.77 | 1.44 |
| B30 | 1,146 | +3.52% | 19.28 | 1.01 |
| B20_ONLY | 4,498 | +4.75% | 24.00 | 1.50 |
| R30 | 705 | +7.70% | 23.23 | **2.21** |
| R25 | 272 | +9.68% | 22.54 | **2.72** |

B30 的每 1000 hold-days 独立 PnL 最低（1.01，较 B20 下降 34%）；R30/R25 最高（2.21/2.72，为 B20_ONLY 的 1.5–1.8 倍）。注意 R30 每年仅数百笔且 2023 年崩塌，此效率优势未通过 day-等权推断 gate。

## 9. Fundamental / News readiness

均 NOT_READY（无 announcement_date 约束的 PIT 基本面；无历史时间戳新闻语料）。本轮不测试。

## 10. 候选减少（相对 B20）

| family | 保留信号 | 减少 | signal-days 占比 |
|---|---|---|---|
| B25 | 49.9% | 50.1% | 88.8% |
| B30 | 12.2% | 87.8% | 61.1% |
| R30 | 6.70% | 93.3% | 54.6% |
| R25 | 1.15% | 98.8% | 24.3% |

减少信号**不等于改善**：B25/B30 显著降低 expectancy；R30 表面改善但无 day-等权增量且尾部更深。

## 11. 分类汇总

| 因素 | 分类 | 依据 |
|---|---|---|
| BB DEPTH | **D — HARMFUL** | 嵌套 delta 显著负（HAC+calendar 全 <0）；1/5 年正；tail 略恶化 |
| RSI | **C — 无稳定增量** | matched-depth 全跨 0、方向不一致；R30−B20 day-等权无差；描述性强度未过 gate |
| SECTOR | N/A — PIT DATA NOT READY | 无 PIT 行业归属，禁回填 |
| MACD | diagnostic only | 无明显关系 |

## 12. Next decision

按 Registry X：只有 A/B 才有资格进入 K=3 portfolio test。**本轮三个候选均未达 A/B → 无可进入组合测试的单因素。** 下一阶段不得将 BB depth / RSI 塞入组合；如需继续 RSI，必须单独 prereg 并以 day-等权推断 gate 为准。

## 13. Invariants（s1_invariants.json）

I1 parity PASS（声明式口径，见 §3）；I2 exit k=2 冻结；I3 仅 entry depth 变化；I4 RSI 仅用 signal-date 可见数据；I5 sector PIT gate（NOT RUN）；I6 无当前行业回填；I7 无组合；I8 MACD diagnostic only；I9 fundamental/news 非 filter；I10 无 K=3 组合优化；I11 无超冻结阈值扫描；I12 无 2025+ 读取（N=1212=2024-12-31）；I13 前序 Registry SHA 未变。

## 14. Governance

- F1.1 A / F2.x B / F3 C：保持不变。
- P6 D（ADD-BUDGET HARMFUL）：ACCEPTED；共享现金池保留；K=3 仍为机械瓶颈兼 protective admission constraint；queue、failure predictor 均保持关闭。
- S1 结果**未**写入 README CURRENT TRUTH（未外审）。
- 2025–2026 Confirmation：CLOSED / UNTOUCHED。

## 15. 输出文件

results/evidence/s1/：s1_b20_parity.json、s1_episodes_B20/B25/B30.csv、s1_signal_metrics.csv、s1_yearly.csv、s1_bb_depth_bins.csv、s1_rsi_incremental.csv、s1_rsi_corr.csv、s1_candidate_reduction.csv、s1_tail_risk.csv、s1_slot_efficiency.csv、s1_inference.csv、s1_macd_diagnostic.csv、s1_sector_strength.csv、s1_prior_research_audit.csv、s1_pit_data_readiness.csv、s1_summary.json、s1_invariants.json

research/signal/：signal_selectivity_s1.py、SIGNAL_SELECTIVITY_S1.md；registries/：SIGNAL_SELECTIVITY_S1_REGISTRY.csv + .sha256
