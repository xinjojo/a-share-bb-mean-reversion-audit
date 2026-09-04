# PHASE P7 — PANIC-BREADTH CAPACITY ARCHITECTURE

**DEVELOPMENT DIAGNOSTIC（WAITING EXTERNAL AUDIT）** — portfolio architecture probe

- Registry: `research/portfolio/registries/PANIC_CAPACITY_P7_REGISTRY.csv`
- Registry SHA256: `db4d318ddc760e649acf14e93285345169313950de6822aaf9927981d439f909`
- Prereg commit: `979bd86` (P7-A)；Governance: R1.8 commit `fad8b10`（接受 B1.1=A，旧 CI 撤销）
- Sample: 2020–2024 Development；2025–2026 CLOSED；无参数扫描；共享 1M 资本

---

## 1. 530 vs 527 Bridge（exact closed）

P5 candidate events = 530（cand_log 重算确认）。B1.1 quintile-joined pipeline = 527。缺失 3 事件：

| date | ts_code | amount_rank | P5 state | 解释（为何不在 1110 B1 signal days）|
|---|---|---|---|---|
| 2022-05-13 | 002415.SZ | 2 | BLOCKED_HELD | **S1 replay held exclusion**：该股在 S1 全市场 replay 中已有活跃 episode（signal 05-06 → entry 05-09 → exit 06-06），replay 不重复建仓 → 无当日 B20 episode |
| 2023-11-09 | 601318.SH | 4 | QUEUED | **S1 replay held exclusion**：该股已有活跃 episode（signal 10-19 → entry 10-20 → exit 2024-01-25）；P5 组合（K=3）当日未持有故 QUEUED 后成交——replay-vs-portfolio 持仓状态差异 |
| 2024-12-31 | 600030.SH | 7 | QUEUED | **end-horizon**：T+1 entry = 2025-01-02 超出 dev N2024=1212（S1 冻结语义：期末信号不产生 episode）|

**530 = 527 + 3 exact closed**。差异全部是 signal-universe 语义（replay held exclusion ×2 + end-horizon ×1），非数据或定义错误。

## 2. P5 Funnel（冻结定义）

FULL LEGAL UNIVERSE → B20 signals（全市场，S1.1 n=63,785）→ **amount Top10（signal-date amount descending）** → P5 candidate pipeline（amount Top10 ∩ BB oversold ∩ valid；530 events）→ HELD/EXEC/K/CASH/LOT → ADMITTED（A0=76）。B1 全市场 B20_COUNT 与 P5 pipeline 的差距（Q5 日 46,310 → 201）由 amount Top10 截断造成；因 P5 ledger 在 Top10 之后聚合，该中间层标记 **NOT FULLY IDENTIFIABLE**（单层精确分解）。

## 3. PANIC80（live/as-of）

- EXPANDING_BREADTH_PERCENTILE：T 日只用 date<T 的历史 B20_BREADTH_PCT；T 不进自身参考分布；禁止 full-sample qcut。
- 252 prior trading days 门槛：T 前 <252 交易日 → PANIC_STATE=0。
- PANIC80 = breadth(T) ≥ 实时 80th percentile。**PANIC80 days = 188 / 1,110 signal days（16.9%）**；2020 全年 0 个 panic 日（252 日历史到 2021 年初才满足），与 A1/A2 2020 年 return 完全等于 A0 一致。

## 4. Baseline Parity

A0 exact parity **PASS**：Total +30.295094%、PnL 302,950.94、Trades 76、MaxDD −30.78973%、Sharpe 0.346765。

## 5. 结果总表

| 指标 | A0 baseline | A1 panic K6 | A2 panic Top20+K6 |
|---|---|---|---|
| Total Return | **+30.30%** | **−20.81%** | **−22.79%** |
| CAGR | +5.66% | −4.74% | −5.24% |
| MaxDD | −30.79% | **−46.94%** | −44.57% |
| Sharpe | 0.347 | **−0.047** | −0.094 |
| Stock PnL | +302,951 | −208,123 | −227,914 |
| Trades | 76 | 83 | 94 |
| Win rate | 68.4% | 62.7% | 60.6% |
| Profit factor | 1.30 | 0.81 | 0.79 |
| Peak positions | 3 | 5 | 6 |
| exec_no_cash | 0 | **77** | 85 |
| blocked_K | 336 | 236 | 333 |
| candidates | 530 | 530 | 678 |

- **A1−A0 delta：−51.11 万 PnL / −51.1pp Total / MaxDD 恶化 16.1pp / Sharpe −0.39**；逐年 **0/5 年改善**（2021 9.94 vs 31.86、2022 −6.86 vs +1.93、2023 −15.65 vs −10.65、2024 −15.21 vs +0.35；2020 相同）。
- A1 的 77 个 exec_no_cash：K6 放行更多候选但 1M 资本 + 加仓预算迅速耗尽，大量入场尝试因现金不足失败。

## 6. Path Bridge（A1 vs A0）—— 机制核心

| 组成 | 值 | 含义 |
|---|---|---|
| COMMON（51 笔同 key）PnL delta | **−183,557** | 同一批交易在 A1 少赚 18.4 万——**共享资本/槽位被 5 持仓摊薄，加仓减少、路径改变**（STRONG CAPITAL/PATH DILUTION）|
| A0_ONLY（25 笔）| **+415,753** | A1 因 panic 新仓占槽位而**丢掉的 A0 优质交易**——独立质量 +7.81% / win 83.3% / MAE30 0% |
| A1_ONLY（32 笔）| +88,236 | A1 新增交易——独立质量 +5.77% / win 73.3% / MAE30 6.7%（独立为正，但不足以补偿）|
| 合计 | −511,074 | 闭合（−18.4 −41.6 +8.8 = −51.2 万）|

**核心机制**：panic 日 K6 放开的候选（深超卖、独立 +5.77%）**挤掉了 A0 原本会做的更优质交易**（+7.81%、MAE30 0%），同时稀释 COMMON 路径——与 P4.1 的"新增信号自己很好、但稀释原有交易路径"完全同构，且幅度更大。

## 7. A2 mechanism（M4）

- A2−A1：COMMON delta +44,678、A1_ONLY −81,167、A2_ONLY −145,635；A2_ONLY 独立质量 **+0.75% / win 60% / MAE30 20%**（Top20 放开的候选质量明显更差）。
- **M4 — BREADTH ALPHA NOT PORTFOLIO-CONVERTIBLE**：K-only（A1）与 K+width（A2）两种容量杠杆在组合层面均失败；Top20 宽度进一步引入深套候选。

## 8. Risk / Cost / Concentration

- Risk：A1 MaxDD −46.94%（恶化 16.1pp）、worst5d −13.61% vs −13.02%、peak exposure 125 万 vs 160 万（分散后单笔投入减少、但组合亏损更大）。
- Cost：A1 buy_actions 144 vs A0 158（买入动作减少——资本被深套占用后加仓机会减少）；无成本假设放松。
- Concentration：A1 incremental 最大单日贡献 13.93%（**非单日/单笔踩雷，是系统性恶化**）。

## 9. 分类

**D — HARMFUL**（A1 Total Return < A0、Sharpe ≤ A0、MaxDD 恶化 16.1pp > 5pp；逐年 0/5 改善）。

A2 mechanism = **M4 — BREADTH ALPHA NOT PORTFOLIO-CONVERTIBLE**（两个容量杠杆均失败；A2 不得升级为 primary）。

## 10. 结论与后续

- **signal-level breadth alpha（B1.1 A）在本组合架构下不可通过"panic 日扩容"转化为收益**——K=3 再次被证明是 protective admission constraint（P4/P4.1/P6/P7 四次一致）。
- 两级漏斗中 amount Top10 截断虽大，但 A2（Top20）证明放宽它只会引入更差候选。
- 若未来要利用 breadth alpha，必须考虑不改 K 的架构（如 panic 日换质量而非数量——但 S1.1 已证同日横截面排序无价值），或彻底不同的执行载体（basket/指数级）。本阶段不做任何事后发明。
- Invariants I1–I15 全部 PASS；2025–2026 CLOSED。
