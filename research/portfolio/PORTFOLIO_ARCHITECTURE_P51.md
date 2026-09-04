# PORTFOLIO_ARCHITECTURE_P5.1 — DEFERRED-ADMISSION ELIGIBILITY DIAGNOSTIC

> Phase: P5.1（R1.1 之后的纯诊断）
> 状态：**DEVELOPMENT DIAGNOSTIC / WAITING EXTERNAL AUDIT**（不写入 README CURRENT TRUTH）
> Registry: `research/portfolio/registries/PORTFOLIO_ARCHITECTURE_P51_QUEUE_ELIGIBILITY_REGISTRY.csv`（SHA `7de0874e…838ec6`，prereg commit `dc5fb74`，**先 push 后跑结果**）
> 红线：未执行任何 delayed entry；未改 entry/exit；无参数扫描；无 predictor；2025–2026 CLOSED；P5 BLOCKED_K=336 事件原样沿用。

---

## 1. 研究问题

P5 虚拟队列显示：336 个 BLOCKED_K 候选全部最终有槽位可释放（never=0），释放前已自然触发 TP 的仅 16.3%，即“83.7% still active”。外部审计指出：**未达止盈 ≠ release 日仍是合法 BB 入场信号**。P5.1 只回答：等待期结束时，被挡候选是否仍满足原始入场条件。

## 2. 方法（严格 frozen）

- 样本：P5 BLOCKED_K 336 事件（signal_date, ts_code 原样）。
- release_date：P5 冻结定义不变——signal_date 后第一个 `n_pos<3 且 cash≥200000` 的交易日。
- release 日重新扫描（release 日可见信息，**无未来数据**）：PIT universe（listing≥60d 经 first_eligible_i、非 ST）、`close_adj < bb_lower`、非涨跌停、当日全池金额 Top10（engine amount_top10 规则）、一手可行（`floor(200000/(open×(1+0.001))/100)×100 ≥ 100` 股）。
- 状态互斥分类：Q0 EXPIRED_TP（有独立 episode 且其自然退出日 ≤ release 日）／Q1 EXACT_ELIGIBLE（release 日完整条件全满足）／Q2 OVERSOLD_NOT_TOP10／Q3 NO_LONGER_OVERSOLD。
- retrigger：signal 与 release 之间再次 `close_adj<bb_lower 且非跌停`；natural capture = 该 retrigger 日 (date, ts_code) 出现在 P5 engine cand_log（原系统当日已重新把它当候选扫描）。
- 独立 outcome 仅 ORIGINAL-ENTRY 口径（独立 replay 是原 signal 日入场，不能冒充 release 日入场）。

## 3. 核心结果

| 状态 | n | 占比 | 说明 |
|---|---|---|---|
| Q0 EXPIRED_TP | 20 | 5.95% | 等待期已自然止盈（独立 mean +7.76%、win 95%） |
| Q1 EXACT_ELIGIBLE | **9** | **2.68%** | release 日仍完全符合原始入场 |
| Q2 OVERSOLD_NOT_TOP10 | 8 | 2.38% | 仍超卖但不在 release 日金额 Top10 |
| Q3 NO_LONGER_OVERSOLD | **299** | **88.99%** | release 日已脱离 BB 下轨 |
| 合计 | 336 | 100% | |

- release 日仍 below lower band：仅 17 / 336 = 5.06%。
- release 日仍 exact original eligible：**2.68%**。
- release 距信号收盘 median 回报：**+0.47%**；release 收盘相对 release 日 LBB 中位 +5.54%（P25 +2.33%、P75 +10.83%、P90 +19.72%）——价格基本已回到信号位上方并脱离超卖区。
- 等待衰减（exact eligible）：1–5d 7.4% → 6–10d 0% → 11–20d 0.95% → 21–40d 0% → 40+d 0%。**资格随等待快速衰减**（描述性，不据此设 cutoff）。
- retrigger：65.18% 在等待期至少再次超卖；natural capture 37.50%（占重触发者的 57.53%）——原系统已把相当一部分重触发信号重新当作候选扫描处理；其余重触发者当时仍被槽位/持仓再次挡住。
- 独立 outcome（original-entry only）：Q0 mean +7.76%（coverage 100%）、Q1 mean +3.72%（coverage 33%）、Q2 mean +8.84%（coverage 37.5%）、Q3 mean +4.45%（coverage 32.4%）。样本量小，仅描述。

## 4. Q1–Q5 回答

- **Q1**（“83.7% still active”中真正 release 日仍合格的）：**2.68%（9/336）**。83.7% 的“still active”几乎全部是“尚未涨到止盈”，而非“还能买”。
- **Q2**（median wait=11d 时多数仍超卖还是已回升）：**已回升**——release 日 88.99% 不再超卖，median release 距 LBB +5.5%。
- **Q3**（资格是否随等待快速衰减）：**是**（7.4%→0%→0.95%→0%→0%）。
- **Q4**（原系统是否已自然实现部分 deferred admission）：**部分**——65.2% 等待期重新超卖，37.5% 的 BLOCKED_K 在重触发日已被原 engine 重新扫描为候选（自然捕获占重触发者 57.5%）；但未到“绝大多数”（<50% 全体），不满足冗余主导标准。
- **Q5**（显式 queue 是否值得进入真实回测）：**NO**（见分类）。

## 5. 分类（registry 冻结阈值自动判定）

**C — QUEUE MOSTLY STALE**

- release 日 exact eligible 2.68% < 25%；
- release 日不再超卖 88.99% > 50%；
- natural capture 37.5% < 50%，**不满足 D 的冗余主导条件**（C/D 并存时以冗余是否为主因判断，此处冗余非主因，故定 C）。

**QUEUE WORTH BACKTEST = NO**（按 registry 映射）。

## 6. 措辞边界

- 禁止：`queue 已证明值得部署`、`被挡信号 release 时还能买`、`83.7% 是有效信号`。
- 准确表述：P5 的“83.7% still active”只是**未达自然止盈**；release 日重新按原始规则扫描，**仅 2.68% 仍是合法 BB 入场信号**；88.99% 已脱离超卖区；显式 queue 的大部分价值被 (a) 资格快速衰减与 (b) 现有 retrigger 自然捕获（37.5%）共同消解。
- 结论不否定 P5 机械事实（K=3 是容量瓶颈、C 分类不变），仅说明 **deferred admission 作为下一阶段独立 lever 的经济基础不成立**。

## 7. Invariants

I1 BLOCKED_K=336 ✓｜I2 release 定义未变 ✓｜I3 BB 规则未变 ✓｜I4 amount Top10 未变 ✓｜I5 PIT/ST/listing 未变 ✓｜I6 无 delayed entry ✓｜I7 无路径修改 ✓｜I8 独立 outcome 仅诊断 ✓｜I9 无参数扫描 ✓｜I10 无 predictor ✓｜I11 无 2025+ 读取 ✓｜I12 前序 registry SHA 未变 ✓（脚本自动 assert 通过）
