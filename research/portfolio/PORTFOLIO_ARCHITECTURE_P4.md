# PHASE P4 — PORTFOLIO ARCHITECTURE CAUSAL DECOMPOSITION

**状态：ACCEPTED DIAGNOSTIC（外审通过：IMPLEMENTATION PASS / PREREGISTRATION PASS / A0 PARITY PASS；未写入 README CURRENT TRUTH）**

## 研究问题

Independent BB signal edge = A（已冻结）。Market-state predictive info = A（已冻结）。
Cross-sectional ATR ranking 有部分外部验证。但真实 K=3 有限资金组合无法兑现这些 edge
（P3 = C，P3.1 = C/BOTH：ranking-actionable 仅 16/1,212 = 1.32%）。

P4 不研究新因子。只回答：**到底是哪一个 portfolio-architecture component 阻碍 signal
edge 转化为 portfolio performance？** 通过结构性消融（STRUCTURAL ABLATION ONLY）分解
K=3 槽位限制、多层加仓（max_levels=5）资本锁定、以及二者的交互。

## 红线执行情况

- 2025–2026 Confirmation：**CLOSED**，全程未触碰。
- 无新 predictor / 无 ranking / 无 composite / 无 stop / 无新 exit / 无 market gate /
  无参数优化 / 无 grid scan / 无 K/layer scan / 无 ML。
- 四个架构全部使用 frozen amount-Top10 priority（**未混入 ATR**）。
- PURE STOCK 2020–2024 Development；10bp；1M/200k/5层；STRICT_C_EXECUTABLE_TICK。
- 引擎 = `run_fast_multi_strict_c_atr`（amount_top10 路径）从 P3 逐行复制，保证 parity。

## 预注册

- Registry：`research/portfolio/registries/PORTFOLIO_ARCHITECTURE_P4_REGISTRY.csv`
- SHA256：`5f30974cd45a2849a9f0bf1c3252f2a14ad1ea236c26a4f2f16a5f65f8ee6545`
- Commit：`70588a71ea6deeaaa60a8af9a4e2e7c4374c7ba3`（P4-A，push 于任何 outcome 之前）

## 四个冻结架构

| 架构 | K | max_levels | 语义 |
|---|---|---|---|
| A0 BASELINE | 3 | 5 | 冻结基线（= P3 B0） |
| A1 SLOT-RELAXED | 999 | 5 | 只解除 3 槽限制，资本仍 1M/200k |
| A2 NO-ADD | 3 | 1 | 只解除多层加仓，初始层仍 200k |
| A3 SLOT-RELAXED + NO-ADD | 999 | 1 | 同时解除 |

## 结果：A0 parity（硬性）

```
[PARITY A0] total=30.2951 (ref 30.2951) ann=5.6564 mdd=-30.7897 sharpe=0.3468
            n=76 stock_pnl=302950.94
[PARITY A0] OK — matches frozen P3 B0 / G0 (t3)
```

A0 与 P3 B0 / 原 frozen G0 逐项精确一致（total / CAGR / MDD / Sharpe / trade count /
stock pnl）。任何消融差异因此是纯架构效应。

## 主结果（2020–2024，PURE STOCK，10bp）

| 指标 | A0 (K3/ML5) | A1 (K999/ML5) | A2 (K3/ML1) | A3 (K999/ML1) |
|---|---|---|---|---|
| total return | **+30.30%** | −0.23% | −5.84% | −29.27% |
| CAGR | +5.66% | −0.05% | −1.24% | −6.95% |
| MaxDD | −30.79% | −36.23% | −25.18% | −46.67% |
| Sharpe | **0.347** | 0.126 | −0.008 | −0.185 |
| Sortino | 0.492 | 0.184 | −0.011 | −0.262 |
| Calmar | 0.184 | −0.001 | −0.049 | −0.149 |
| trades | 76 | 123 | 75 | 146 |
| win rate | 68.4% | 65.9% | 54.7% | 54.8% |
| PF | 1.30 | 1.00 | 0.92 | 0.74 |
| stock pnl | +302,951 | −2,283 | −58,431 | −292,731 |
| avg n_pos | 2.18 | 3.87 | 2.20 | 4.58 |
| avg layers | 2.08 | 1.69 | 1.00 | 1.00 |
| slot-days | 2,637 | 4,694 | 2,661 | 5,547 |
| PnL/slot-day | 114.88 | −0.49 | −21.96 | −52.77 |
| cash-constrained days | 33.4% | 54.1% | 0.0% | 55.0% |

**反直觉核心事实：解除任一架构约束，组合收益均大幅恶化。K=3 是实际容量瓶颈
（binding capacity constraint，candidate 530 / blocked_K 336），但在当前历史样本
和当前组合规则下，这个瓶颈同时表现出保护性的 admission constraint /
implicit capacity filter（A0 的 K=3 + 5 层加仓在测试路径上是产生正收益的结构）。**

## Causal decomposition（历史结构反事实，非严格因果）

| 效应 | total return | CAGR | MaxDD | Sharpe | stock pnl |
|---|---|---|---|---|---|
| A1−A0 SLOT EFFECT | −30.52pp | −5.70pp | +5.44pp 恶化 | −0.221 | −305,234 |
| A2−A0 LAYER EFFECT | −36.14pp | −6.90pp | −5.61pp 改善 | −0.355 | −361,382 |
| A3−A0 COMBINED | −59.57pp | −12.60pp | +15.88pp 恶化 | −0.532 | −595,682 |
| Interaction (A3−A2)−(A1−A0) | +7.09pp | −0.00pp | +16.05pp | +0.043 | +70,934 |

解读：
- **SLOT EFFECT（A1−A0）显著为负**：解除 3 槽限制后接入更多低质量信号（123 vs 76 笔），
  新增 58 笔均值 −2,045（62.1% win），而保留的 65 笔 +1,790（69.2% win）。额外信号系统性
  更差 + 资金被稀释 + 加仓被摊薄（avg layers 2.08→1.69），组合从 +30% 崩到 ~0%。
- **LAYER EFFECT（A2−A0）显著为负**：移除多层加仓后，**同一批 44 只股票、entry-level
  Jaccard 0.96**，但路径完全不同（NEVER_RECONVERGED），每笔均值从 A0 的 +3,986 降到 −298。
  多层加仓（multi-layer averaging-down）在测试路径下是重要的资金机制——它通过摊低持仓
  成本放大深度赢家（A0 最佳 5 笔中 4 笔为 2 层持仓）。注意措辞边界：P4 只验证
  “完全移除多层加仓（5→1 层）在测试路径下有害”，**不**断言 5 层最优、也**不**断言
  多层加仓在全市场范围内必要。
- **Interaction 对收益为正（+7.09pp）且实质小于两个主效应**：positive and materially
  smaller than the two main effects; no dominant adverse interaction amplification
  （无主导的负面交互放大）。

## 逐年（A0 vs 变体）

| 年份 | A0 | A1 | A2 | A3 |
|---|---|---|---|---|
| 2020 | +8.12% | +4.57% | −3.64% | +5.56% |
| 2021 | +31.86% | +15.86% | +14.23% | −8.47% |
| 2022 | +1.93% | +0.04% | −2.75% | −14.35% |
| 2023 | −10.65% | −14.90% | −7.44% | −6.83% |
| 2024 | +0.35% | −3.27% | −4.97% | −8.26% |

A0 在 5 个年份中 4 年优于各自变体；变体没有一个年份系统性优于 A0。改善不依赖单一年份
（A0 最大单年贡献 2021 +31.86%，但 2023/2024 亦相对抗跌）。

## Signal capture & 阻塞分解

| 指标 | A0 | A1 | A2 | A3 |
|---|---|---|---|---|
| candidate events | 530 | 530 | 530 | 530 |
| queued | 78 | 363 | 76 | 349 |
| executed initial | 76 | 123 | 75 | 146 |
| blocked_K | 336 | 0 | 336 | 0 |
| blocked_held | 116 | 167 | 118 | 181 |
| capture rate (exec/cand) | 14.3% | 23.2% | 14.2% | 27.5% |
| queueable capture | 97.4% | 33.9% | 98.7% | 41.8% |

- **A0 主导瓶颈 = K 槽位（BLOCKED_K 336/530 = 63.4%）**，其次已持仓（21.9%），
  资本约束罕见（cash-constrained 仅 33.4% 且多因 200k 层阈值判定）。
- A1/A3 解除 K 后 blocked_K→0，**capture 率翻倍**（14→23/27%），但组合收益反而崩——
  证明"多接信号 ≠ 组合更好"。queueable capture 从 97% 掉到 34%，说明 K=999 时大量
  queued 因资本/加仓占位未能成交（exec_NO_LOT 238 / 200 笔）。

## Ranking actionability（diagnostic，未应用 ATR）

| 架构 | signal days | actionable days | % |
|---|---|---|---|
| A0 | 1,212 | 16 | 1.32% |
| A1 | 1,212 | 0 | 0.00% |
| A2 | 1,212 | 17 | 1.40% |
| A3 | 1,212 | 0 | 0.00% |

A1/A3 解除 K 后 ranking-actionable 反而归零（有槽位时候选总 < 槽位，排序无实际选择）。
A2 的 17 天与 A0 的 16 天接近。**架构松弛不会让未来 ranking 信号更容易发挥作用。**

## 资本效率与机会成本

- A0 PnL/slot-day = 114.88，A1 −0.49，A2 −21.96，A3 −52.77。A0 是唯一资本效率为正的架构。
- A0 被阻塞候选（452 个，其中 123 个有 frozen episode 覆盖，coverage 27.2%）：
  mean ret +5.08%、win 74.8%——被 K/持仓阻塞的候选本身是高质量信号，但因槽位/加仓
  结构无法进入；coverage 不足，不得把缺失当 0（缺失未计入）。
- 但 A1 证明"强制接入这些候选"反而亏损——因此这些被阻塞信号的价值不能被简单相加。

## Deep-MAE 占用（A0，描述性，禁止据此设计 stop）

| MAE bucket | n | slot-days | slot % | pnl |
|---|---|---|---|---|
| < −30% | 4 | 214 | 12.3% | **−431,359** |
| −30~−20 | 7 | 388 | 22.4% | −91,827 |
| −20~−10 | 16 | 565 | 32.6% | +241,434 |
| −10~0 | 25 | 551 | 31.8% | +533,780 |
| ≥0 | 1 | 17 | 1.0% | +22,383 |

深 MAE（<−20%）11 笔仅占 34.7% slot-days，却贡献 −523,186 亏损（组合总盈利 +302,951）。
浅 MAE 交易贡献约 +826k。**少数深 MAE 长持仓（含 300014.SZ 172 天 5 层 −282k）是组合
主要拖累**——但这只描述占用结构，P4 禁止据此设计 stop / exit 修改。

## Path dependence

- A1/A2/A3 全部 **NEVER_RECONVERGED**（自首次 holdings/cash 分歧后不再回到 A0 路径）。
- 最大 equity divergence：A1 +346k，A2 +502k，A3 +688k。
- A2 与 A0 entry-level Jaccard 0.96（同一批股票），但首日现金分歧 2020-03-10、
  holdings 分歧 2023-08-15，最终差异 +502k——**同一选股、纯路径差异**即可产生 ±50 万级别
  组合差异。这量化了有限资金组合对路径的极端敏感性。

## 机制分类

**D — TESTED ARCHITECTURE BOTTLENECK NOT EXPLAINED BY SIMPLE K/LAYER REMOVAL**

重要边界：P4 只测试了两种**极端结构性消融**（K 3→999、levels 5→1），**并未搜索
architecture space**，因此本结论不构成"K/layer 结构不重要"的全局断言。更准确地说：
**K=3 是实际容量瓶颈，但在当前历史样本和当前组合规则下，这个瓶颈同时表现出保护性的
admission constraint（implicit capacity filter）。**
- 解除 K（A1）→ 接入更差信号 + 稀释资金 → 收益崩盘。
- 移除加仓（A2）→ 摧毁多层摊低成本引擎 → 收益转负。
- 双解除（A3）→ 最差。
- 二者交互对收益为正且实质小于两个主效应（interaction ≈ +7pp，无主导负面交互放大）。

因此 P3 中 ATR ranking 无法改善组合的原因**不是** K 槽位或加仓结构阻塞了好的排序机会
（解除它们反而更糟）。真正的局限在更深层：**单笔信号边缘 + 路径依赖 + 少数深 MAE 长持仓
的占用结构**（long holding / shared-capital path architecture）。P4 禁止进一步修改 exit，
此处不做对策建议。

## 2025–2026 Confirmation

**仍然 CLOSED。** P4 是架构诊断，不是冻结最终策略，任何情况下不打开 Confirmation。

## 仓库纪律

- 代码：`research/portfolio/portfolio_architecture_p4.py`
- Registry：`research/portfolio/registries/`
- 结果：`results/evidence/p4/`（12 个 CSV + 4 个 eq pkl）
- 本报告：`research/portfolio/PORTFOLIO_ARCHITECTURE_P4.md`
- P4 结果已更新 `CURRENT_STATUS.md` 与 `RESEARCH_MAP.md`（研究链节点）；**未写入
  README CURRENT TRUTH**（待外部审计通过）。
