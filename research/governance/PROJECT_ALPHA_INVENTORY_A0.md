# PROJECT_ALPHA_INVENTORY_A0.md — 项目 Alpha 盘点 & 盲测决策门

> 治理：外审 **M2.1 PASS / M2 FINAL = D — HARMFUL**；breadth→broad-market ETF carrier branch **CLOSED**（A0-G，commit `3de7615`）。
> 本阶段**停止一切新策略开发**，只对 2020–2024 development evidence 做最终证据盘点。2025–2026 保持 CLOSED/UNTOUCHED（本阶段机器验证：m11/b1/m2/m21/p7 等关键数据 max date ≤ 2024-12-31）。

---

## 1. 总览：四类归档（27 行主表）

`results/evidence/a0/a0_alpha_inventory.csv`（每行 = 一个 phase/finding，含 hypothesis/layer/metric/result/classification/统计/经济/执行/成本/PIT/是否进组合/是否执行/2025-26/分支状态/盲测资格/理由）。

| 类别 | 行数 | 内容 |
|---|---|---|
| **CATEGORY 1 — ROBUST SIGNAL-LEVEL EDGE** | 4 | Independent Trade Replay V2A、Full-Market Episode Replay、**B1/B1.1 Breadth（A FINAL）**、T2-R Reverse Validation |
| **CATEGORY 2 — PORTFOLIO / EXECUTION FAILURE** | 10 | first-gen（INVALID lookahead）、STRICT_C/A0（development-only baseline）、K999、ML1、fixed stops、P3 ranking、P5.1 queue、P6 wallet、P7 panic K6/Top20+K6、M2 ETF carrier |
| **CATEGORY 3 — DIAGNOSTIC / CONTEXT ONLY** | 13 | T2 discovery、P1/P2、P4、P4.1、F1.x、F2.x、F3、P5、S1、S1.1、W1、D1.x、M1.x |

**失败结果未被省略**：first-gen +354.9%（same-bar lookahead）标记 INVALID 并在 portfolio inventory 中保留；P7 两档负收益、M2 负净收益全部如实归档。

## 2. Signal Alpha 盘点（`a0_signal_alpha.csv`）

| 问题 | 答案 | 证据 | 可部署 |
|---|---|---|---|
| 1. BB 下轨 episode edge 是否 robust？ | **YES** | 独立 replay（无 same-bar lookahead）+ 全市场 replay 验证，episode 正期望 | 否（信号层） |
| 2. Breadth 环境效应是否 robust？ | **YES（signal-level）** | B1.1 A FINAL：Q5−Q1 +2.664pp、corrected boot CI [+1.102,+4.185]、rank-slope HAC [+0.00130,+0.00463]、条件 b1 +3.283 CI [+1.030,+5.537]、5/5 年正、单调、tail 不恶化 | 否（组合转换两次失败：P7/M2） |
| 3. ATR ranking 是否可执行？ | **NO** | P2 单因子 partial pass（ATR20_PCT），P3 有限 K 槽位分配无组合价值 | 否 |
| 4. Failure-state 预测是否经济可执行？ | **NO** | F3 C：OOF AUC 0.720 但稳定经济阈值 0/6 年；F2 +1.45pp 是未来标签上界 | 否 |
| 5. Market-level rebound 是否 robust？ | **NO** | M1.2 B FINAL：FWD5 +0.2752pp 但 HAC/boot CI 全跨 0、cluster-first −0.277pp、3/4 年；M2 carrier 扣成本净 −7.25% | 否 |

**signal alpha exists = YES；deployable portfolio alpha exists = NO。** 两者明确分离（J 节纪律）。

## 3. Portfolio Architecture 盘点（`a0_portfolio_architectures.csv`）

| architecture | return | MDD | Sharpe | after-cost | 真实执行 | 状态 | 失败机制 |
|---|---|---|---|---|---|---|---|
| First-gen K3 | +354.9% | — | — | 否 | 否 | **INVALID** | same-bar lookahead |
| **STRICT_C / A0 K3** | **+30.30%** | −30.79% | 0.347 | **是** | **是** | development-only baseline | 非 proven carrier |
| K999 | — | — | — | 是 | 是 | 失败（P4 消融） | 解除 K 摧毁共享资本路径 |
| ML1（5→1 层） | — | — | — | 是 | 是 | 失败（P4） | 移除加仓层有害 |
| Fixed stop variants | — | — | — | 是 | 是 | 失败（S0 审计稳健） | 止损不改善结果 |
| Wallet separation（P6） | +10.27%（A2） | — | — | 是 | 是 | **D HARMFUL** | 切掉 layer2/3 正 PnL（COMMON −163,660） |
| Deferred queue（P5.1） | — | — | — | — | — | **C STALE** | release 日仅 2.68% 仍可买 |
| Panic K6（P7 A1） | −20.81% | −46.94% | −0.047 | 是 | 是 | **D HARMFUL** | COMMON 稀释 −183,557、现金耗尽（77 次 no-cash） |
| Panic Top20/K6（P7 A2） | −22.79% | −44.57% | −0.094 | 是 | 是 | **D HARMFUL** | Top20 候选质量更差（MAE30 20%） |
| **ETF carrier 510300（M2/M2.1）** | **−7.25%** | −24.13% | −0.064 | **是** | **是** | **D HARMFUL** | gross +12.05% 被 ~19.3pp 成本吃光；p=0.145；2023 −17.35% |

## 4. 当前最好组合（H 节，诚实判定）

> **STRICT_C / A0 K3 baseline（development-only baseline，NOT proven alpha carrier）**
> Total +30.2950937861% / Trades 76 / MaxDD −30.7897288178% / Sharpe 0.3467648252（2020–2024，after-cost，真实 A 股执行：T+1、lot、PIT 可交易池、佣金+10bp 滑点）。

判定依据（H 节五维）：无 lookahead ✓（独立 replay 验证）、成本 ✓、PIT ✓、执行 ✓、资本约束 ✓——但它**不是**预注册冻结的部署架构：K=3 / amount Top10 / max_layers=5 / 200k 层 / 1M 共享资本都是 development 期反复消融比较后**保留**的 baseline，且同一 development 期 4 次 signal→portfolio 转换尝试（P3/P6/P7/M2）全部失败。因此只能如实写：**development-only baseline，不得升级为 proven alpha carrier。**

## 5. Blind-Test Eligibility Gate（I 节 10 项，`a0_blind_test_gate.csv`）

针对唯一候选（A0 K3 baseline）逐项判定：**6 项完整 YES，2 项 PARTIAL（#3 PIT 完全冻结、#8 组合层稳健性），2 项 NO（#7 风险可接受、#10 非反复调参未确认架构）**。

| # | 标准 | 判定 | 依据 |
|---|---|---|---|
| 1 | 完整规则冻结 | YES | A0 规则精确，P4–P7 各阶段 parity 复现 |
| 2 | 无 lookahead | YES | T 收盘信号 → T+1 open；独立 replay 验证 |
| 3 | PIT universe/data acceptable | **PARTIAL** | B20 PIT 池 OK；fundamental PIT HOLD（D1.2 C）→ context 层未完全冻结 |
| 4 | 真实 A 股 execution | YES | T+1、lot、ST 排除 |
| 5 | 真实成本 | YES | 佣金 + 10bp 滑点 |
| 6 | portfolio-level net return positive | YES | +30.2951%（after-cost） |
| 7 | risk acceptable | **NO** | Sharpe 0.347 弱、MaxDD −30.79%、深套 episodes 存在 |
| 8 | development robustness sufficient | **PARTIAL** | 信号层 robust；组合层 4 次转换全失败 → 转换机制未建立；A0 是比较幸存者 |
| 9 | 无 unresolved P0/P1 实质改变结果 | YES | A0 核心无已知 P0；D1.2 只影响 fundamental 分支 |
| 10 | 非反复调参后未确认架构 | **NO** | K3/Top10/layers/200k 从未作为部署配置预注册冻结 |

## 6. 最终决策

# **DECISION B — DO NOT OPEN BLIND TEST（2025–2026 保持 CLOSED）**

最核心原因：**A0 是 development 比较的 baseline 而非预注册冻结的部署架构**，且风险画像偏弱（Sharpe 0.347 / MaxDD −30.79%）；即使 B20 信号层与 breadth 广度层有 robust signal-level alpha，**没有任何一个组合架构把 signal alpha 转成可冻结的 portfolio alpha**（P3/P6/P7/M2 全部失败）。打开盲测只会把"未确认架构"与"真实策略好坏"混在一起，无法得到可解释结果。

## 7. 经验总结

**Cost / Execution lessons（K 节）：**
- M2：gross **+12.05%** → net **−7.25%**——thin edge（约 +0.33pp/笔相对优势）被 ~19.3pp 高频执行成本（滑点 15.4pp + 佣金 3.9pp）吞噬。**薄边际信号在真实成本下不成立。**
- First-gen：+354.9% 是 same-bar lookahead——**理论信号不能直接当可实现收益**，必须先独立 replay。
- P7：增加机会数量（K6/Top20）不等于增加组合 alpha——**signal breadth alpha 与 portfolio capacity alpha 是两回事**。

**Capital / Path lessons（L 节）：**
- K3 = protective admission constraint（S1/P5/P7 第 4 次一致证据）：解除 K 后，新信号自己的期望为正（A1_ONLY 独立 +5.77%），但**与旧持仓共享 1M 资本和加仓预算**，COMMON 交易路径被稀释（P7 COMMON −183,557；P4.1 A1_ONLY 实际 −118,610）。
- P4.1：**"更多正期望交易"导致"组合更差"的机制 = 共享资本 + 路径稀释 + 槽位置换**：新交易不是独立账户，它会挤掉（displace）原本会被 A0 持有的高价值交易（A0_ONLY 25 笔 +415,753 被挤掉），并让已持仓少加一层。
- P5/P5.1：瓶颈是 K 槽位而非现金；队列候选在 release 时几乎全部失效（2.68%），等待本身在消灭资格。
- P6：拆 NEW/ADD 钱包把 layer2/3 的正 PnL 切掉（COMMON −163,660）——共享池的时间弹性是 A0 经济性的一部分。

## 8. 科学价值（保留，非部署授权）

1. **信号层事实成立**：A 股日线 BB 下轨超卖后的独立 episode 均值回归存在正期望（经无 lookahead replay 验证）。
2. **广度效应成立（date-level）**：全市场同日 B20 候选数量（breadth）与该日信号质量正相关，5/5 年稳定（B1.1 A FINAL）。
3. **组合约束机制清楚**：K=3 在现有共享资本架构下是保护性约束；任何扩容/排队/拆账/ETF 载体的转译都失败，且失败机制（路径稀释、成本吞噬）已被逐层拆解。
4. **数据层已可审计**：PIT 行业覆盖 94.6%（B）、PIT 财务 100%（A）但 visibility 语义 AMBIGUOUS（D1.2 C）——未来若建 context 层仍需解决权威披露日问题。
5. **科研结论本身成立且可接受**：**有 signal alpha，无 deployable portfolio alpha。**

## 9. Outputs

- `results/evidence/a0/`：a0_alpha_inventory.csv（27 行）、a0_signal_alpha.csv（5 问）、a0_portfolio_architectures.csv（10 架构）、a0_branch_status.csv（14 分支）、a0_blind_test_gate.csv（10 项）、a0_summary.json、a0_invariants.json
- `research/governance/project_alpha_inventory_a0.py`（本盘点脚本）
- 2025–2026：未读取（机器验证 max date ≤ 2024-12-31）。
