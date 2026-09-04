# PORTFOLIO ARCHITECTURE P5 — CAPACITY / CAPITAL-LOCK DIAGNOSTIC

**Status: DEVELOPMENT DIAGNOSTIC / WAITING EXTERNAL AUDIT**（未经外审，未写入 README CURRENT TRUTH）
**Preregistration: `research/portfolio/registries/PORTFOLIO_ARCHITECTURE_P5_REGISTRY.csv`**
SHA256 = `7415608a1003b612704e295a76427eba5c124607163a926fb514342c699f7ce7`（commit `e007979`，push 后才运行结果）
**Sample: 2020–2024 Development（1212 交易日）；2025–2026 CLOSED/UNTOUCHED**
**基线: P4 A0 exact parity**（引擎原样 import `portfolio_architecture_p4.py`）

---

## 0. 红线确认

本轮为纯结构诊断：不改 entry / natural exit / cost / slippage / T+1 / lot / PIT；无 predictor、无 market/layer gate、无新准入规则实际执行、无参数扫描。独立 episode outcome 只用于诊断（shadow / quality），从不影响组合路径（I9）。全部 12 项 invariant 自动 assert 通过（I1 parity PASS 等，见 `results/evidence/p5/p5_invariants.json`）。

## 1. 基线精确 parity（I1）

| 指标 | 冻结目标（P4 A0 / P3 B0 / G0 t3） | P5 复现 |
|---|---|---|
| Total Return | +30.295093786122408% | +30.295094% |
| Stock PnL | +302,950.94 RMB | +302,950.94 |
| Trades | 76 | 76 |
| MaxDD | −30.78972881784398% | −30.78973% |
| Sharpe | 0.3467648252149691 | 0.346765 |

**P0 STOP 未触发。**（`p5_baseline_parity.json`）

## 2. 候选事件阻塞结构（blocked-reason precedence: HELD > EXECUTION > K > CASH > LOT > OTHER）

| 分类 | n | 占 530 候选 % | 说明 |
|---|---|---|---|
| ADMITTED | 76 | 14.3% | = 组合实际成交初始入场 |
| BLOCKED_K | 336 | 63.4% | 当日 `len(positions)+len(pending_buy)>=K`，槽位满 |
| BLOCKED_HELD | 116 | 21.9% | 候选 ts_code 已在持仓或待卖（重复触发/加仓类信号走新买门被挡） |
| BLOCKED_CASH | 0 | 0.0% | **exec_log 从未出现 NO_CASH**（K=3 / 1M / 20万层下现金从不阻塞执行） |
| BLOCKED_LOT | 1 | 0.2% | NO_LOT（002594.SZ 2023-08-14） |
| BLOCKED_EXECUTION / OTHER | 1 | 0.2% | 2024-12-31 期末排队未执行（QUEUED 无次日 attempt） |

**K 槽位是绝对主导的机械容量瓶颈：** 63.4% 候选被 K 挡下；交易日层面 n_pos>=3 的天数 668/1212 = **55.1%**；n_pos<3 且 cash<20万的天数仅 18 天（1.49%）；K 满且现金不足天数 32.0%。K+HELD 合计占候选阻塞的 **85.3%**。现金约束在本组合参数下**从不构成执行瓶颈**。

## 3. 仓位锁定与占用集中度

- 持仓天数：median 28.5 天，mean 34.7 天。
- **Top 10% 持仓（8 只）占 slot-days 26.9%、capital-days 37.8%、持有期阻塞信号 32.3%；Top 20%（16 只）占 42.8% / 53.4% / 48.3%。** HHI(slot) = 0.0199（整体分散，但头部深亏长仓集中）。
- >60 天持仓占 slot-days 16.1%、capital-days 18.9%——**不是**“绝大多数资源被少数长仓锁死”，而是**少数 deep-MAE 长仓构成显著单点资本 sink**：
  - `300014.SZ` 2023-02-21：172 天、5 层、capital-days 1.48 亿元·天、持有期阻塞 72 个候选、PnL **−281,649**；
  - `300750.SZ` 2021-12-21：106 天、3 层、阻塞 80 候选、−97,944；
  - `002594.SZ` 2021-12-17：88 天、4 层、阻塞 82 候选、−15,161。
- 长持仓里 >60 天区间合计 realized PnL −42.3 万（61-90d −4.3 万、91-120d −9.8 万、120+d −28.2 万）；21-40d / 11-20d 区间是主要盈利带（+29.5 万 / +48.9 万）。

## 4. 层资本曲线（same-exit matched-share 口径，I10）

| layer | n 执行 | 投入资本 | 占总资本 % | 平均 layer 收益 | 层后平均持有 |
|---|---|---|---|---|---|
| 1 | 76 | 14,126,544 | 49.1% | −0.19% | 34.7d |
| 2 | 49 | 9,143,733 | 31.8% | **+2.69%** | 31.4d |
| 3 | 25 | 4,124,998 | 14.3% | **+3.62%** | 27.8d |
| 4 | 5 | 772,341 | 2.7% | −0.55% | 51.2d |
| 5 | 3 | 585,016 | 2.0% | +1.75% | 45.3d |

- **layer2+ 占总投入资本 50.9%，layer3+ 占 19.1%。**
- matched-share 下第 2、3 层平均为正收益——**加仓层不是单纯的“资本黑洞”**，这与 P4 A2（完全移除加仓有害）一致；layer4/5 样本极小（5/3 次）且包含 deep-MAE 尾部（300014 五层、002594 五层均为深亏）。

## 5. 阻塞信号独立质量（independent V2A join，事件日等权）

| 分类 | n | coverage | 独立 mean | median | win | PF | MAE | hold |
|---|---|---|---|---|---|---|---|---|
| ADMITTED | 76 | 69.7% | +3.53% | +3.77% | 75.5% | 2.61 | −12.8% | 33.0d |
| BLOCKED_K | 336 | 36.6% | +5.08% | +5.89% | 74.8% | 3.18 | −12.9% | 37.3d |
| BLOCKED_CASH | 0 | — | — | — | — | — | — | — |
| BLOCKED_HELD | 116 | 0% | — | — | — | — | — | — |

- **被 K 挡掉的信号独立质量并不更差（point 上略好：+5.08% vs +3.53%）。**
- 但推断受限：BLOCKED_K coverage 仅 36.6%（冻结数据源 `fullmarket_episode_metrics.csv` 只含独立 replay 的首次入场 episode，重复触发无对应条目）；与 ADMITTED 的共同事件日仅 7 天，HAC 因 n<12 无法计算；calendar bootstrap CI = **[−14.08, +4.79] pp，跨 0** → **“被挡信号更好/更差”均无统计结论**。
- 结论措辞（与 P4.1 / R0.2 一致）：K=3 的阻塞**不是**“系统过滤了内在更差的信号”的证据（blocked_K 全体不差）；其保护作用来自限制共享资本路径（见 §8）。

## 6. 资本影子价格（counterfactual，不可实现）

对 BLOCKED_K 有 coverage 的 123 个候选（200,000 元层归一化）：

| 项 | 值 |
|---|---|
| missed positive（独立收益>0 归一化 PnL 和） | +1,821,335 |
| avoided negative（独立收益<0 绝对值） | 571,959 |
| net（shadow） | +1,249,376 |

**必须强调：这是 SHADOW / COUNTERFACTUAL 诊断，不是可实现组合 PnL。** P4.1 已证明：把同样信号放入共享资本组合（A1 K=999）时，共同交易的资本/路径稀释（COMMON 65 单 PnL −67,116）与 marginal 入场拖累会使组合整体转负。影子净值为正只说明“单笔独立预期上是正机会”，不说明“放开 K 能多赚”。

## 7. 虚拟队列（诊断，无实际延迟入场）

- 336 个 BLOCKED_K 候选**全部**在后续某交易日出现“slot 释放 + 现金充足”状态（never=0）。
- 等待天数：P25=4、**median=11**、P75=18、P90=32。
- 释放前已自然触发 TP（independent exit 先于释放）比例：**16.3%**；即 83.7% 的阻塞候选在资源释放时仍是“活”的均值回归信号。
- 含义：延迟补位在时序上部分可行，且能自动跳过约 1/6 已错过最优回归窗口的信号；但队列不改变共享资本路径（补位信号进入后仍会与在持仓竞争未来的加仓/退出路径），P4.1 的稀释机制仍适用。

## 8. 主要问题回答（Q1–Q7）

**Q1 现有组合最主要的机械瓶颈：K slot（绝对主导）。** 63.4% 候选被 K 阻塞（336/530），55.1% 交易日 K 满；held 重复触发 21.9%；现金阻塞 0。

**Q2 资本占用是否高度集中于少数长期持仓？** 中等偏上：Top10% 占 capital-days 37.8%、Top20% 占 53.4%；>60 天整体只占 16-19%，但少数 deep-MAE 长仓（300014 等）是最大单点资本 sink 与阻塞源。

**Q3 后续加仓层占用多少 capital-days？** layer2+ 占总投入资本 50.9%（其中 layer3+ 19.1%）；matched-share 下加仓层平均正收益，因此加仓不是纯浪费，而是“高资本占用 + 历史上有效 + 尾部深亏”三合一。

**Q4 被 K/cash 挡掉的信号独立质量是否显著优于 admitted？** 不能下结论：point 上 BLOCKED_K 略好（+5.08 vs +3.53），但 coverage 36.6%、事件日交集 7 天、bootstrap 跨 0，**无统计显著差异**；现金从无阻塞样本。

**Q5 K=3 的保护作用来自挡掉差信号，还是限制资本扩张/path dilution？** 数据支持后者（P4.1 H3）：blocked_K 全体独立质量不差 → 不是“系统过滤差信号”；A1（K 解除）组合转负 → 保护来自限制共享资本路径与暴露扩张（R0.2 措辞成立：“K=3 是实际容量瓶颈，但在当前历史路径下同时是保护性 admission constraint”）。

**Q6 虚拟队列是否显示大量 blocked 信号等到释放时已失去入场意义？** 否——83.7% 释放时仍活跃，median 仅等 11 天；仅 16.3% 释放前已自然 TP（这部分可被队列天然过滤）。

**Q7 下一阶段最值得预注册的架构杠杆：D — QUEUE / DEFERRED ADMISSION（只登记，不执行）。**
理由：(a) 直击主导瓶颈 K（63.4% 阻塞）；(b) 保持 K=3 并发上限不变 → 保留 R0.2 认定的保护性 admission，不扩大并行暴露（与 P4.1 稀释证据不冲突）；(c) 现金从不阻塞（blocked_cash=0）→ 补位不撞资本墙；(d) 虚拟队列显示时序可行（median 11 天、83.7% 仍活、可自动过滤 16.3% 已过期信号）。
备选（不执行）：C add-budget separation（layer2+ 占 50.9% 资本，但加仓平均有效，需设计“保护初始资本”的预算分离，风险是削弱有益加仓）。

## 9. 分类（R1.1 修正，外部审计后）

**C — BOTTLENECK EXISTS BUT ECONOMIC RELEVANCE UNCLEAR。**

修正说明：P5 预注册定义 C = “机械阻塞明显，但 blocked signal quality / shadow value 不支持经济重要性”。当前证据：K 槽位是明确机械容量瓶颈（63.4% 候选、55.1% 交易日 K 满、现金从不阻塞），**但** independent coverage 仅 36.6%，BLOCKED_K vs ADMITTED 事件日 calendar bootstrap CI = [−14.08, +4.79]pp 跨 0（HAC 因共同事件日仅 7 天无法计算），无法证明被挡信号经济质量显著更优或更差；且 P4/P4.1 已证明简单解除 K 会恶化共享资本路径。因此不能定 A（经济相关性未建立），最终为 C。

措辞边界（禁止）：不得写“放开 K 会增加收益”“blocked_K 是更好的信号”“queue 已经证明值得部署”。保留：K=3 是实际容量瓶颈，同时是 protective admission constraint（R0.2）；blocked_K 独立质量 point 上不差（+5.08% vs +3.53%）但无统计结论；shadow net +1.25M 是 counterfactual、不可实现。

## 10. 交付物清单（`results/evidence/p5/`）

p5_baseline_parity.json · p5_daily_capital_ledger.csv · p5_position_lock.csv · p5_signal_collision.csv · p5_lock_age_curve.csv · p5_layer_capital_curve.csv · p5_blocked_signal_quality.csv · p5_blocked_signal_eventday.csv · p5_blocked_signal_bootstrap.csv · p5_capital_shadow.csv · p5_occupancy_concentration.csv · p5_virtual_queue.csv · p5_summary.json · p5_invariants.json

## 11. 治理

- P5：DEVELOPMENT DIAGNOSTIC / WAITING EXTERNAL AUDIT；未写入 README CURRENT TRUTH。
- 2025–2026：CLOSED（脚本硬限制 dev horizon）。
- 本轮未修改任何 ranking / exit / stop / K / layers / predictor；未做参数优化。
