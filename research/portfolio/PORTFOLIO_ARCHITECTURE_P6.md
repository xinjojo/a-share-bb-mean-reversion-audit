# PORTFOLIO_ARCHITECTURE_P6 — ADD-BUDGET SEPARATION（组合架构测试）

> Phase: P6（R1.2 之后）
> 状态：**DEVELOPMENT DIAGNOSTIC / WAITING EXTERNAL AUDIT**（不写入 README CURRENT TRUTH）
> Registry: `research/portfolio/registries/PORTFOLIO_ARCHITECTURE_P6_ADD_BUDGET_REGISTRY.csv`（SHA `907df83d…62f1e51`，prereg commit `407335e`，**先 push 后跑结果**）
> 红线：仅 A0/A1/A2/A3 四个冻结架构；无参数扫描（20/40/60% 是三个探针，禁止插值）；K=3/max_levels=5/200k/amount Top10/STRICT_C 退出全部不变；无 predictor/queue/stop/gate；2025–2026 CLOSED。

---

## 1. 研究问题

保留 averaging-down 的收益来源（P5：layer2+ 占投入资本 50.9%，matched-share 平均正），同时限制老仓对未来资本的侵占——把 100 万拆成"新仓池 + 加仓池"，卖出的钱按该仓历史来源比例回池，禁止跨池借款。问：这是否改善共享资本路径？

## 2. 冻结架构与执行语义

- A0 共享现金池（=P4 A0，必须 exact parity）；A1 NEW 600k / ADD 400k；A2 800k/200k；A3 400k/600k。
- INITIAL_ENTRY 只用 NEW 池；ADD_POSITION 只用 ADD 池；卖出净回款按该 episode 的 new_cost/add_cost 历史比例分别回 NEW/ADD 池；费用先扣再按同比例分摊。
- 整手语义与 baseline 一致：`qty = floor(min(200000, 可用池现金)/(open×(1+slip))/100)×100`，qty≥100 且 amt+fee≤池现金才执行；否则 NO_NEW_BUDGET / NO_ADD_BUDGET（从不借另一池）。

## 3. 核心结果（A0 parity 5 项全 PASS）

| 架构 | Total | MaxDD | Sharpe | stock PnL | n | adds | avg layers | NO_NEW | NO_ADD | blocked_K |
|---|---|---|---|---|---|---|---|---|---|---|
| A0 共享池 | **+30.30%** | −30.79% | 0.347 | +302,950.94 | 76 | 82 | 2.08 | 0 | 0 | 336 |
| A1 600/400 | +11.04% | −32.37% | 0.209 | +110,445.35 | 75 | 65 | 1.87 | **0** | **85** | 336 |
| A2 800/200 | +10.27% | −25.56% | 0.202 | +102,652.08 | 75 | 52 | 1.69 | 0 | 114 | 336 |
| A3 400/600 | −7.76% | −38.03% | 0.061 | −77,569.55 | 71 | 78 | 2.10 | 13 | 79 | 338 |

- **A1 vs A0：return −19.25pp；MaxDD 恶化 1.59pp；Sharpe −0.138；逐年 PnL 仅 2023 一年更好（1/5 年）。**
- A1 信号 bridge（(sig_date, ts_code)）：COMMON 74、A0_ONLY 2、**A1_ONLY 仅 1**、NO_NEW_BUDGET 0。
- A1 add bridge：lost adds 按层 = layer2 7 / layer3 11 / layer4 2 / layer5 2（共 22；adds 总数 82→65）。
- A1 path bridge：COMMON 74 个相同信号 PnL 合计 **−163,660**（约为 A0 总 PnL 的 54%）——同一批信号只因加仓受限即大幅贬值；A0_ONLY −10,343；A1_ONLY（唯一新信号）−39,188；fees −5,754；平均闲置现金 +42,608。
- 单 episode 最大贡献占 incremental 的 59.4%（>50%，即便只按浓度也不达标）。

## 4. 机制回答（K 部分 1–5）

1. **更多新信号进入？否。** A1_ONLY=1、NO_NEW_BUDGET=0：新仓池从不缺钱，预算隔离几乎没有带来任何新入场——瓶颈是 K 槽位（blocked_K 336 不变），不是钱（与 P5 的 blocked_cash=0 一致）。
2. **减少后续加仓？是，且这是主要伤害通道。** NO_ADD_BUDGET=85 次加仓被拒，adds 82→65、avg layers 2.08→1.87；而 P5 已证明 layer2/3 在 same-exit matched-share 下平均为正（+2.69%/+3.62%），预算隔离把正贡献加仓层切掉了 → COMMON 74 个相同信号 PnL −163,660。
3. **现金闲置增加？轻微。** A1 平均闲置现金比 A0 高 42,608（新仓池等信号时闲置），方向为负但金额小。
4. **持仓路径改变？是。** COMMON delta 已体现：相同 (ts_code, entry_date) 信号，因 add 路径不同，PnL 系统性下降。
5. **退出时间/episode composition？** 75 vs 76 episodes，结构几乎不变；主要变化在 add 路径而非退出。

**核心洞察：共享现金池的"时间弹性"本身就是 A0 的组成部分。** 加仓资金来自持仓释放与整体现金流的时间差，池隔离强制锁定资金用途，恰好切掉了正贡献的 averaging 层，而预留的新仓预算纯属冗余（K 才是入场瓶颈）。这与 P4/P4.1 一致：问题不是"钱被加仓吃掉"，而是共享资本路径下 deep-MAE 长仓的稀释；预算隔离不是正确解法。

## 5. 年度分解（A1 vs A0，PnL 按退出年）

2020 +67,713 vs +82,026；2021 +330,184 vs +342,403；2022 **−77,841 vs −16,195**；2023 −34,228 vs −57,948（唯一好年份）；2024 **−175,383 vs −47,335**（大幅恶化）。A2/A3 同样在 2022/2024 深度恶化。

## 6. 分类（registry 冻结规则，以 A1 为主）

**D — HARMFUL**：A1 Total Return（+11.04%）< A0（+30.30%）且 Sharpe（0.209）≤ A0（0.347），按预注册规则直接判 D；MaxDD 亦恶化 1.59pp。

敏感性（仅报告，不得升级为 winner）：A2 +10.27%（MaxDD −25.56% 是唯一改善项，但收益/Sharpe 全面低于 A0）与 A3 −7.76% 均为 D；三探针方向一致——**预算隔离方向有害，且越向"保护加仓"倾斜越差（A3 < A1 ≈ A2 << A0）**。20/40/60% 仅为探针，禁止据此插值"最优比例"。

## 7. 措辞边界

- 禁止："预算隔离证明有效""应给加仓预留 X%"。
- 正确表述：在冻结的 K=3/5 层/200k/STRICT_C 系统下，**新仓/加仓资本隔离对组合是净伤害（A1/A2/A3 全部劣于 A0）**；新仓预算从未构成约束（NO_NEW_BUDGET=0），而加仓预算短缺（85 次 NO_ADD_BUDGET）切掉了 P5 已证明为正的 layer2/3 贡献。add-budget separation **无正价值证据**（证据方向为负）。
- 结论不否定 P5（layer2+ 占资本 50.9% 且 matched-share 为正）——恰恰说明这些正贡献依赖共享池的灵活资本路径，隔离反而破坏之。

## 8. Invariants

I1 A0 exact parity（total/n/pnl/mdd/sharpe 全 PASS）✓｜I2 K=3 ✓｜I3 max_levels=5 ✓｜I4 200k ✓｜I5 entry ✓｜I6 exit ✓｜I7 ranking ✓｜I8 无 predictor ✓｜I9 无 queue ✓｜I10 无 stop/gate ✓｜I11 无 2025+ 读取 ✓｜I12 前序 registry SHA 未变 ✓（脚本自动 assert 通过）
