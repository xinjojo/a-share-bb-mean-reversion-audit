# MARKET_STATE_GATE_T3

**PHASE T3 — FROZEN MARKET-STATE GATE CONSTRUCTION AND PORTFOLIO COUNTERFACTUAL**
**Development period: 2020-01-01 → 2024-12-31 (DEVELOPMENT / CONSTRUCTION — NOT OOS)**
**2025-2026 Confirmation: CLOSED (never read in this phase)**

---

## 0. 预注册与冻结点（Gate Registry 先于所有 portfolio 运行 commit）

- `MARKET_STATE_GATE_REGISTRY.csv` + `MARKET_STATE_GATE_REGISTRY.sha256`
- **Gate Registry SHA256: `9ae9214e345ebca7b8235f21fba17e5cc77bac92f6b75f9cfe73d106d21650ba`**
- Registry commit **`15c740a`** — committed & pushed **before** any portfolio counterfactual was run (hard red-line satisfied).
- `R01_DISCOVERY_CUTPOINTS.json` / `R05_DISCOVERY_CUTPOINTS.json` frozen at the same commit; verified byte-identical to HEAD after all runs.
- 原 104-cell Registry SHA256 不变：`5c5e451ad4eb3afd5e632b0019a3e02103e58e375e03cc231c5d8ca52b8c5195`（未触碰）。
- T2 / T2-R Registry 未触碰。

## 1. 冻结 Gate 定义（Registry 原样，未改动）

| gate | 规则 | 状态 |
|---|---|---|
| G0 | 无 gate（CONTROL） | CONTROL |
| G1 | `R01 >= Discovery Q80` → 禁止 NEW INITIAL ENTRY | **PRIMARY（vs G0）** |
| G2 | 按 R01 Discovery quintile 分层 sizing：Q1-Q3=100%, Q4=75%, Q5=50%（同一仓位各层同 tier） | SENSITIVITY（参数冻结） |
| G3 | 规则与 G4 相同，引擎以 gate_mode='G4' 报告 | SENSITIVITY |
| G4 | `R01 >= Discovery Q80 AND R05 <= Discovery Q20`（强市+低压力=孤立超跌）→ 禁止 NEW INITIAL ENTRY | **SECONDARY（vs G0）** |

- 主语义：`ENTRY_ONLY_GATE`（已持仓照常按原策略 add）。`ENTRY_AND_ADD_GATE` 为 risk sensitivity。
- add 规则：加仓仍按原 `close_adj < BB lower && !is_limit && levels<5 && gap>=1`；gate 触发后（G1/G4 的 EA 变体）禁止新 add。
- 持仓退出完全沿用冻结 STRICT_C_EXECUTABLE_TICK（dynamic P* touch）。

## 2. 冻结 Discovery Cutpoints（T2-R 固定，未从 2023-24 重算）

**R01 = ALL_A_EW_RET60**（全A PIT eligible 等权指数 60 交易日收益率×100；Discovery 2020-2022 Y20-valid dropna，n=616）：
- Q20 = **-4.7005**，Q40 = **-0.5578**，Q60 = **4.8774**，Q80 = **9.9899**
- NaN 政策：R01 缺失 → 视为"非强市"放行（不 gate）。

**R05 = LIMIT_DOWN_SHARE**（收盘≤跌停价比例；Discovery 2020-2022 dropna）：
- Q20 = **0.0007032**，Q40 = 0.0013238，Q60 = 0.0022594，Q80 = 0.0044705
- 分布审计：Discovery 内 unique 680 个值、零值占比 5.08% → **连续 quintile 成立**；0-vs->0 binary 因退化被否决（记录在 R05 JSON）。

**Development 期 gate 日数（引擎语义，2020-2024）：**
- G1 gate 日（R01≥Q80）：**217 / 1212 日（17.9%）**
- G4 gate 日（R01≥Q80 且 R05≤Q20）：**66 / 1212 日**

## 3. 样本与引擎

- SECONDARY frozen episodes（独立交易 V2A_FROZEN_STRICT）：89,046 realized；development 2020-2024 子集 **n=64,072**（2025+ 未纳入）。
- PRIMARY Top10 frozen episodes：299（dev 245）。
- 组合引擎：`market_state_gate_t3.py::run_fast_multi_strict_c_gated` = 冻结 `run_strict_c.py::run_fast_multi_strict_c`（STRICT_C_EXECUTABLE_TICK）+ gate/layer_cash/ledger。
- **G0 parity（record_blocks=True 路径）：equity ✓ / trades ✓ / actions ✓ 与冻结引擎逐笔一致（assert 通过）。**
- 主组合口径：PURE STOCK（1,000,000 RMB，K=3，200,000/层，max5 层，T+1，100 股整手，PIT ST，listing≥60d，严格 tick，动态 P*，费用/印花税/10bp 滑点）。ETF 513500 仅 secondary 且 leg 拆分。

## 4. Episode-level counterfactual（frozen episodes，development 64,072 笔）

| gate | side | n | mean% | med% | win% | PF | MAE_med% | hold_med |
|---|---|---|---|---|---|---|---|---|
| G0 | accepted | 64,072 | +5.02 | +5.36 | 77.4 | 1.77 | -8.78 | 25 |
| G1 | accepted | 56,349 | +5.29 | +5.57 | 78.6 | 1.89 | -8.42 | 25 |
| G1 | **rejected** | **7,723** | **+3.10** | **+3.64** | **68.8** | **1.06** | **-11.42** | 27 |
| G4 | accepted | 63,544 | +5.05 | +5.37 | 77.5 | 1.78 | -8.75 | 25 |
| G4 | **rejected** | **528** | **+1.65** | **+3.31** | **64.4** | **0.72** | **-12.33** | 29 |
| G2 | tier Q1-Q3 (1.0) | 47,789 | +5.46 | +5.73 | 78.8 | — | — | — |
| G2 | tier Q4 (0.75) | 8,560 | +4.32 | +4.76 | 77.6 | — | — | — |
| G2 | tier Q5 (0.50) | 7,723 | +3.10 | +3.64 | 68.8 | — | — | — |

**信号级结论（frozen episode）：** G1 剔除的 7,723 笔 episode 平均 +3.10%（accepted +5.29%，Δmean -2.18pp）、胜率 68.8%（vs 78.6%）；G4 剔除的 528 笔平均 +1.65%（Δ -3.40pp）、**PF 0.72 < 1**。**Gate 在信号层确实排掉低质量 episode**（G4 排掉的甚至是负期望组）。G2 的 sizing 单调：turnover 排名 Q5（强市）档质量最低（+3.10%）。

## 5. Gate attribution（两口径）

**A. Frozen-episode diagnostic（64k 全 episode）：**

| gate | n_rejected | winner | loser | saved_loss | lost_profit | **NET_GATE_VALUE** |
|---|---|---|---|---|---|---|
| G1 | 7,723 | 5,317 | 2,406 | 142.6M | 150.6M | **-7.95M** |
| G4 | 528 | 340 | 188 | 14.4M | 10.3M | **+4.11M** |

- G1 冻结口径 NET 略负（错杀赢家的 lost profit 略超 saved loss）。
- G4 冻结口径 NET 为正（排掉的是 528 笔负期望/低质量组）。

**B. Path-dependent portfolio difference（纯股票，真实组合）：**

| gate | G0 stock_pnl | gate stock_pnl | Δ portfolio |
|---|---|---|---|
| G1_EO | +302,951 | -113,850 | **-416,801** |
| G4_EO | +302,951 | -3,663 | **-306,614** |

## 6. 真实组合反事实（PURE STOCK，dev 2020-2024，1M 起）

| gate | total% | ann% | MaxDD% | Sharpe | trades | win% | stock_pnl | slot_occ_days | pnl/slot-day |
|---|---|---|---|---|---|---|---|---|---|
| **G0** | **+30.30** | **+5.66** | **-30.79** | **0.347** | 76 | 68.4 | **+302,951** | 2,636 | **114.9** |
| **G1_EO** | **-11.38** | **-2.48** | **-40.70** | **0.041** | 70 | 65.7 | **-113,850** | 2,482 | **-45.9** |
| G1_EA | +7.66 | +1.55 | -28.44 | 0.189 | 71 | 67.6 | +76,617 | 2,496 | 30.7 |
| G2 | +20.50 | +3.95 | -33.61 | 0.281 | 74 | 68.9 | +204,966 | 2,632 | 77.9 |
| G4_EO | -0.37 | -0.08 | -34.35 | 0.129 | 74 | 64.9 | -3,663 | 2,648 | -1.4 |
| G4_EA | -6.32 | -1.35 | -40.40 | 0.083 | 72 | 66.7 | -63,180 | 2,602 | -24.3 |

**没有任何 gate 改善真实有限资金组合。** PRIMARY G1 是最差的：总收益 -11.4%（vs +30.3%）、MaxDD 恶化到 -40.7%、Sharpe 0.041、股票腿 -113.9k、PnL/slot-day 为负。G2（分层 sizing）损伤较小但仍低于基线。G4 几乎不改善。

## 7. 关键机制（G1 为什么有害）

冻结 PRIMARY（Top10）dev episode 按 R01 状态：
- strong（R01≥Q80）n=28：mean **+3.92%**，med +4.38%，win 78.6%，但 **RMB pnl 合计 -31.1k**；weak n=205：mean +4.68%，pnl +1,885k。
- **方向按年份不稳定**：2021 strong n=5 mean **+9.96%**（强市信号是该年最好子集）；2022 strong n=15 mean **+0.33%**（最差）；2020 +5.09%；2024 n=1 +19.32%。

组合逐笔 diff（G1 vs G0）：
- **19 笔 G0 交易被 gate 剔除，净 PnL +245.7k（正收益！）**——2021 年 6 笔被剔交易大多是大赢家（+27.8k/+31.6k/+20.5k/+47.0k/+19.1k/+20.5k）。
- 13 笔替代交易净 PnL **-62.8k**，含两笔灾难性 5 层深套：`002714.SZ` -168.8k（-20.3%）、`300750.SZ` -110.9k（-20.8%）。
- 其余差额来自后续持仓/加仓/资金路径级联。

**根本原因：** T2-R 在 SECONDARY 全样本上验证的"强市→未来信号质量更低"是真实的，但 (1) 在组合实际使用的 Top10 子集上方向按年不稳定（2021 强市 Top10 信号反而是最好的）；(2) 被 gate 剔除的 Top10 组合交易净为正收益；(3) 强市期（尤其 2021）正是该策略盈利最多的时段，gate 系统性删除后资金空置、释放的 slot 被更差的替代交易填补。这是**信号级可预测 ≠ 组合级可部署**的典型失败。

**G4 的 -30pp 摆动说明极端路径依赖：** 仅 4 笔 gate block 就把 +30.3% 打到 -0.4%（替代交易含 002714 5 层 -161k 巨亏）。与第一代 PATH_DEPENDENCE_ATTRIBUTION 结论（C — VALID BUT STRONGLY PATH-DEPENDENT PORTFOLIO DYNAMICS）一致。

## 8. 逐年 G0 vs G1（纯股票）

| 年份 | G0 | G1_EO | Δ |
|---|---|---|---|
| 2020 | +8.12% | +14.25% | +6.13pp |
| 2021 | +31.86% | +6.91% | **-24.95pp** |
| 2022 | +1.93% | -7.11% | -9.04pp |
| 2023 | -10.65% | -13.70% | -3.05pp |
| 2024 | +0.35% | -9.50% | -9.85pp |

G1 仅在 2020 胜出；2021 为主要驱动（-25pp），但 2022/2023/2024 均输 → **非单一年份驱动，是全周期系统性损伤**。

## 9. Blocked-opportunity / capital efficiency（dev，530 笔 Top10 总机会）

| gate | executed | BLOCKED_GATE | BLOCKED_K | BLOCKED_HELD | slot_occ | pnl/slot-day | cap_util% | cash_constrained% |
|---|---|---|---|---|---|---|---|---|
| G0 | 76 | 0 | 336 | 116 | 2,636 | 114.9 | 59.6 | 33.4 |
| G1_EO | 70 | **40** | 296 | 107 | 2,482 | -45.9 | 62.6 | 44.0 |
| G1_EA | 71 | 40 | 304 | 101 | 2,496 | 30.7 | 60.0 | 38.5 |
| G2 | 74 | 0 | 344 | 110 | 2,632 | 77.9 | 57.8 | 29.1 |
| G4_EO | 74 | 4 | 341 | 108 | 2,648 | -1.4 | 63.7 | 43.7 |

- K=3 是最大的机会拦截来源（G0 中 336/530 被 K 挡下）。
- G1 增加 40 笔 BLOCKED_GATE、执行数降到 70；slot 占用下降（2,482 vs 2,636）但 PnL/slot-day 转负 —— **gate 没有提升资本效率，反而让占用时间与收益同时恶化**。

## 10. ENTRY_ONLY vs ENTRY_AND_ADD

| 变体 | G1 | G4 |
|---|---|---|
| ENTRY_ONLY | total -11.38% / Sharpe 0.041 / stock_pnl -113.9k | total -0.37% / Sharpe 0.129 / stock_pnl -3.7k |
| ENTRY_AND_ADD | total +7.66% / Sharpe 0.189 / stock_pnl +76.6k | total -6.32% / Sharpe 0.083 / stock_pnl -63.2k |

- G1 下保留 add（EA）明显好于同时禁 add（EO），但仍不如 G0。
- G4 下 EO/EA 均差。两变体都不构成改善 → 结论对 add 语义稳健（都不 work）。

## 11. ETF 513500 secondary（仅归因，与股票腿严格拆分）

| gate | combo total% | stock_pnl | ETF_pnl | total_pnl | stock 占比 | ETF 占比 |
|---|---|---|---|---|---|---|
| G0_ETF | +40.00 | +193,238 | **+206,784** | +400,022 | 48.3% | 51.7% |
| G1_ETF | +17.41 | +4,165 | +169,942 | +174,107 | 2.4% | 97.6% |

**G1 vs G0（combo）归因（reconciliation 精确，residual ≈ 0）：**
ΔTotal Equity = **-225,915** = ΔStock **-189,073** + ΔETF **-36,842**。

- ETF funding leg 本身是 combo 收益的重要来源（G0 中 +206.8k，占 51.7%）。
- gate 在 combo 中同样有害：股票腿 -189k、ETF 腿 -36.8k。**ETF 路径不能救回 gate。**

## 12. 预注册 Confirmation gate（2025-2026，本轮不运行）

已冻结的 Confirmation 成功标准（G1 需满足 {MaxDD≥3pp、Sharpe≥+0.10、cap eff≥+10%} 至少 2 项 **且必须 CAGR ≥ G0-2pp**，且 rejected 均值<accepted）。

Dev 期 G1 已系统性失败（Sharpe 0.041 << 0.347；MaxDD -40.7% 更差；CAGR -2.48% << +5.66%；pnl/slot-day -45.9 << +114.9；rejected 均值 +3.10% < accepted +5.29% —— 唯一达标项）。**按指令，Dev 未通过则不得进入 2025-2026 Confirmation。2025-01-01 起的数据在本阶段从未被读取。**

## 13. 分类

**C — NO USEFUL PORTFOLIO GATE.**

- T2-R 的市场状态预测关系在信号层成立且可复现（A-STRONG VALIDATION，本阶段 frozen-episode 反事实再次确认 G1/G4 排掉低质量 episode）。
- 但把它做成真实有限资金组合的 Gate 后，**所有候选（G1/G2/G4 × EO/EA）在纯股票组合中均不如基线 G0**，在 ETF combo 中也更差。
- 原因非统计失效，而是**信号级可预测 → 组合级不可部署**：Top10 子集方向按年不稳定、被剔 Top10 交易本身净盈利、强市期为策略最赚钱时段、资金空置与替代交易级联放大损失。
- 第一代评级不受影响；本结论不改变已冻结的 `D — NO EVIDENCE OF ROBUST / REPEATABLE / EXTRAPOLATABLE ALPHA`。

## 14. 红线核对

- PRIMARY 冻结 299 笔 / SECONDARY 89,046+124 未改；V2A parity 未动。
- Registry（104-cell / T2 / T2-R / T3 Gate）均未修改；Gate Registry SHA256 不变。
- 未打开 Validation 2023-2024（其 Regime 数据未在本阶段用于任何调参）；2025-2026 Confirmation CLOSED（未生成任何 2025+ 对照表）。
- 未做阈值搜索、未补档、未调参数、未用 ML、未做 composite、未做 trading filter 落地。
- G0 parity 逐笔通过（equity/trades/actions）。

## 15. 交付物

- `MARKET_STATE_GATE_REGISTRY.csv(.sha256)`（commit `15c740a`）
- `R01_DISCOVERY_CUTPOINTS.json` / `R05_DISCOVERY_CUTPOINTS.json`（commit `15c740a`）
- `market_state_gate_t3.py`（本阶段运行引擎 + 全矩阵 + attribution + figures）
- `results/t3_cutpoints.csv` / `t3_episode_quality.csv` / `t3_rejected_vs_accepted.csv` / `t3_portfolio_summary.csv` / `t3_portfolio_yearly.csv` / `t3_capital_efficiency.csv` / `t3_blocked_opportunities.csv` / `t3_gate_attribution.csv` / `t3_entry_add_sensitivity.csv` / `t3_etf_secondary.csv` / `t3_etf_secondary_attribution.csv`
- `figures/t3_portfolio_equity.png` / `t3_yearly_returns.png` / `t3_blocked_opportunities.png` / `t3_accepted_vs_rejected.png`
