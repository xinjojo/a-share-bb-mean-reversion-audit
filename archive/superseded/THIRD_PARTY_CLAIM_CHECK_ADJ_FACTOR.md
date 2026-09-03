# THIRD_PARTY_CLAIM_CHECK — adj_factor Point-in-Time Leakage 核查

**任务**：验证第三方独立审计指控 —— "当前使用 Tushare `adj_factor` 构造历史 adjusted-price signal，可能因为复权因子包含未来公司行动信息而产生 point-in-time leakage"。
**原则**：只做 CLAIM VERIFICATION，不修复、不调参、不修改 Registry / 策略 / 代码。目标不是证明第三方错或对，而是回答："站在历史日期 T，当时可获得的信息是否足以构造当前回测使用的 adjusted-price BB / z-score 序列？"

---

## 0. 最终结论

> **PARTIALLY CONFIRMED**

按维度分解：

| 子维度 | 判定 | 依据 |
|---|---|---|
| 公司行动驱动的因子变化（分红/送转/拆分） | **REFUTED**（未发现泄漏） | 305/305 大幅跳变与 dividend 表 `ex_date` 100% 匹配；因子在除权日跳变、未来不提前进入；引擎用**后复权**口径，无"除以最新因子"的前复权式重基准 |
| 全市场"因子表维护微调"（非除权季同步微小调整） | **UNRESOLVED — CANNOT FALSIFY** | 存在 2021-01-07 / 2023-06-01 / 2024-06-25/26 等全市场同步微调日（中位 \|Δfactor\|≈0.002%），非公司行动驱动；**无历史多时点快照，无法独立重建 PIT 因子**，无法证实/证否其是否修订了历史因子值 |
| 对当前回测信号与交易的可操作影响 | **≈ 0（无可测量影响）** | 截断 PIT 自洽 0 差异；最坏情形（历史因子被 0.05% 重算）信号翻转 5/8400 天（0.06%）；实际微调中位 0.002% → 影响二阶更小；不影响 STRICT_C_EXECUTABLE_TICK 的 97 笔交易 |

**affected 计数（可验证路径）**：
- `affected_signal_days = 0`
- `affected_entry_days = 0`
- `affected_exit_days = 0`
- `affected_trades = 0`
- `performance impact ≈ 0`（无可测量影响）

> ⚠️ 上述 0 基于"截断自洽 + 维护微调影响上界"两条可验证路径；"维护微调是否修改历史因子值"本身无法用当前单一快照直接测量，故独立标注 **UNRESOLVED — CANNOT FALSIFY**，不以理论推测替代。

---

## 1. Tushare `adj_factor` 定义与复权机制

**官方口径**（Tushare doc_id=146 / wctapi documents/109.md）：

- **后复权价（hfq）** = 当日收盘价 × 当日复权因子，即 `close_adj = close × adj_factor`
- **前复权价（qfq）** = 当日收盘价 × 当日复权因子 ÷ **最新**复权因子，即 `close_adj = close × adj_factor / adj_factor[latest]`
- 复权机制：按 `end_date` 动态复权，**分红再投模式**；后复权序列以固定基准（上市初期≈1）为锚，**历史值不被未来除权改写**（前复权才会因"除以最新因子"让全部历史随每次新除权整体改写）。

**引擎实际使用的口径**（`round51_audit.py:46`）：
```python
df['close_adj'] = df['close'] * df['adj_factor']   # 后复权, 不含 /adj_factor[latest]
```
即引擎构造 signal 用的是 **后复权价**，没有做"除以最新因子"的前复权归一化。因此**不存在**"未来公司行动通过前复权重基准反向改写历史价格"的机制。

---

## 2. 三种信息时点区分（指控的 A/B/C）

- **A. 数据库中每一天的 `adj_factor[k]`**：2020-01-02 ~ 2026-08-31，每只股票每日一个值。
- **B. 历史时点 k 实际能获得的 PIT 复权信息**：后复权因子是"截至当日公司行动的累积倍数"。只要因子表未被未来维护重算，`adj_factor[k]` 就只依赖 ≤k 的公司行动 → `B == A[k]`。
- **C. 后续除权除息是否会改变早期日期的 `adj_factor` 数值**：
  - **公司行动维度**：不会。305 次大幅跳变全部发生在各自 `ex_date`，跳变前因子恒定（阶梯结构），**未来公司行动不提前进入历史因子**（见 §4）。
  - **维护微调维度**：不确定。发现全市场同步微调日（见 §5），是否存在对早期因子值的修订**无法用单一快照证实/证否**。

---

## 3. 技术指标的尺度不变性验证

设 20 日窗口内所有复权价统一乘常数 `c`（相当于因子序列整体缩放），则：

| 指标 | 变换 | 不变性 |
|---|---|---|
| BB mean | `mean(c·x) = c·mean(x)` | 同乘 c |
| BB std | `std(c·x) = c·std(x)` | 同乘 c |
| BB lower = mean − 2·std | `c·lower` | 同乘 c |
| **BB z-score** = (p − mean)/std | `(c·p − c·mean)/(c·std) = (p − mean)/std` | **不变** |
| close < lower 信号 | `c·p < c·lower ⇔ p < lower` | **不变** |
| 动态 P\*（解 `P = Upper(P)`） | 解析解 `P* = (562S + √Δ)/10678` 是 S、S2 的**齐次**函数（均 ×c 时 P\* 同 ×c） | P\*_raw = P\*_adj / adjT **不变** |

**结论**：BB mean/std/z-score、下轨信号、动态上轨 P\* 均对"整段窗口统一缩放"不变。`close_adj[k] = close_raw[k] × adj_factor[k]` 中各日因子若**整体同倍率变化**（如后复权基准调整），信号不变；**唯一能改变信号的情形是"20 日窗口内因子被非均匀修改"**（窗口中间跳变/部分天数被调）——这正是 §5 维护微调需要量化的情形。

---

## 4. Corporate-Action Case Study（METHOD CURRENT vs METHOD PIT）

### 4.1 样本与方法

- 选取 24 只 2020-2026 有多次公司行动的股票（`adj_factor` 大幅跳变 ≥5 次，覆盖主板/创业板/科创板、银行/白酒/新能源/医药等）。
- **METHOD CURRENT**：`close_adj[k] = close_raw[k] × adj_factor[k]`（各日自己的因子，即当前回测口径）。
- **METHOD PIT**：严格按历史 T 当时可得的公司行动构造 PIT-adjusted history。由于后复权因子累积只向前，**"截至 T 的因子序列"就是"全序列在 T 处的前缀"**；对每个历史日 T 用该前缀重算 BB/z/下轨/P\*，即为 PIT 口径下的值。

### 4.2 结果

**(a) 跳变 = 公司行动（dividend 交叉验证）** —— 决定性的正面证据：

| 指标 | 数值 |
|---|---|
| 选股数 | 24 只 |
| `adj_factor` 大幅跳变（\|Δfactor\| > 0.5%）总数 | **305** |
| 与 Tushare dividend 表 `ex_date` 匹配（±3 自然日） | **305 / 305 = 100%** |
| 无公司行动对应的跳变 | **0** |

→ 所有大幅跳变严格由分红/送转/拆分驱动，跳变日 = 除权除息日；**未来公司行动不提前进入历史因子**（因子在除权日前保持恒定，阶梯结构成立）。

**(b) 截断 PIT 自洽性（METHOD CURRENT vs METHOD PIT）**：

| 指标 | 数值 |
|---|---|
| 信号差异（全序列 vs 截断 PIT，24 股全历史） | **0 天** |
| 原因 | 相同前缀的 rolling(20) / P\* 输入完全一致（结构性 0 差异） |

→ 只要 `adj_factor[k]` 是"截至 k 的后复权累积"，BB/z/下轨/信号/P\* 在 PIT 口径下与当前回测**完全一致**。

**(c) 旧审计佐证**（`REDTEAM_STRICT_C_CORRECTED.md`）：修正 `raw_hist` 口径（由"前 19 日 raw × T 日因子"改为"各日自己的因子"）后，P\* 触发改变仅 5 天（0.15%）、退出日期 5 笔——即"窗口内因子非均匀不一致"对 P\* 的实际影响极小。

### 4.3 affected 汇总（本 case study 可验证路径）

```
affected_signal_days = 0
affected_entry_days  = 0
affected_exit_days   = 0
affected_trades      = 0
```

---

## 5. 全市场"因子表维护微调"——唯一未闭环的子维度

### 5.1 发现

按 `adj_factor` 逐日跳变做市场层面统计，发现**非除权季、全市场同步的极微小调整日**：

| 日期 | 同日跳变股票数 | 跳变中位 \|Δfactor\| | 跳变上界 | 性质 |
|---|---|---|---|---|
| 2021-01-07 | 3,401 | 0.000075 (0.0075%) | 0.027 | 1 月非除权季，全市场同步 |
| 2023-06-01 | 2,752 | 0.000131 (0.013%) | 0.508 | 6 月初，微调为主 |
| 2024-06-25 | 4,355 | 0.000094 (0.0094%) | 0.405 | 6 月末，微调为主 |
| 2024-06-26 | 4,455 | 0.000096 (0.0096%) | 0.126 | 6 月末，微调为主 |

对照真实除权季（如 2026-05-29 等，同日仅 140-180 只、中位 \|Δfactor\|≈1.2%），这些"数千只同日、中位 0.01%"的调整**不是公司行动驱动**（对选股样本抽查：119 条维护日记录中 117 条为纯微小跳变，中位 0.002%，仅 2 条为个股除权混入）。

**解释**：这些是 Tushare 因子表的数据维护/补录/精度归一化痕迹，可能（也可能不）对历史因子值做过统一修订。**无历史多时点快照，无法直接测量"维护日之前用户实际拿到的因子值"** → 按任务要求，此子维度判 **UNRESOLVED — CANNOT FALSIFY**。

### 5.2 即使存在修订，量化影响上界

对"历史因子被统一重算 ×(1+eps)"的最坏情形做信号翻转实验（跨维护日 20 日窗口，抽样 400 股/维护日）：

| 情形 | 评估窗口天数 | 信号翻转天数 | 翻转率 |
|---|---|---|---|
| eps = 0.05%（上界） | 8,400 | **5** | 0.0595% |
| 实际维护微调中位 0.002% | — | 二阶更小（∝ eps²） | << 0.01% |

z-score 扰动（0.05% 非均匀扰动，24 股）：中位 0.017、p95 0.039、max 0.046，**远小于 BB z 阈值间距（0.5）** → 信号翻转概率极低。当前 STRICT_C_EXECUTABLE_TICK 97 笔交易无涉及维护日关键窗口的可测影响。

---

## 6. 能否重建真正 PIT adj_factor？

**不能。** 当前仅持有 2026-08-31 的单一因子快照；重建"历史时点真实因子"需要多时点历史快照或 Tushare 内部维护日志，本项目不持有。因此对 §5 维护微调维度，严格按任务要求判：

> **UNRESOLVED — CANNOT FALSIFY**
> （公司行动维度已实证 REFUTED；维护微调维度无法证实/证否，但其对信号的量化影响上限已给出，≈0。）

---

## 7. 其他 6 项指控 — 只做事实核对表（不修代码）

| # | 指控项 | 判定 | 真实证据（FILE / FUNCTION / LINE） |
|---|---|---|---|
| 1 | **T+1 是否已实现** | ✅ **CONFIRMED** | `run_strict_c.py` L225 `if (i - pos['entry_day_idx']) < 1: continue  # T+1`——买入当日不可卖，次日起可卖；卖出按 lot 级遍历。 |
| 2 | **Survivorship / universe 构造** | 🟡 **PARTIAL** | 数据含 339 只带 `delist_date` 的股票历史；universe = `combined_daily.parquet` 历史面板全部 `ts_code` + PIT `list_date`+60 交易日 + PIT ST 过滤（`round51_audit.py` L68-77, L86-94）。**未做"当前上市股票反向回填"**；但 README 自认"2020 后退市股缺失 15 只（NEED_EXTERNAL_DATA），所有结论含 survivorship bias 成分"→ 该缺口本身是 KNOWN LIMITATION，未闭环。 |
| 3 | **Regime 是否使用 T+1 之后数据** | ✅ **CONFIRMED 未使用** | `regime_discovery_corrected.py`：特征 = `rolling(20)`/`shift(20)`/`rolling(252)`（均 ≤T，L53-54/L74/L83/L100）；outcome = `open_adj[T+1] → close_adj[T+5]/[T+10]`（L117-128，信号 T 收盘后从 T+1 开盘起算）。T 日决策不使用 T+1 及之后数据。 |
| 4 | **Registry commit 是否早于 Discovery run** | ✅ **CONFIRMED** | `11e2ab2` 2026-09-02 20:02:42（HYPOTHESIS_REGISTRY 104 条冻结, SHA256=5c5e451a…）< `1a0b1f7` 21:32:51（Discovery v1 首次 run）< `fa58758` 22:30:02（implementation correction）。预注册先于任何结果。 |
| 5 | **Price limit / suspension / 100 股整手** | 🟡 **PARTIAL** | correct 涨跌停（`round51_audit.py` L50-57：科创板 20%、创业板 20%(2020-08-24 后)/10%、ST 5%、主板 10%）已实现；100 股整手多处（`run_strict_c.py` L59/L78/L174/L202）；停牌日股票不在当日数据 → `dd['pos'].get(tc)` 返回 None → `continue` 跳过（L151-154/L163-166/L194-197）。**缺口：北交所（.BJ）30% 涨跌幅未按 30% 处理**（落入 else 的 10%）；实测北交所 341 只、**从未进入当日成交额 Top10（0 天）**、占全市场成交额中位仅 1.01% → 实际回测影响 ≈ 0。 |
| 6 | **P\* 是否实际进入 executable code** | ✅ **CONFIRMED** | `run_strict_c.py` L232 `Pstar_adj = analytic_Pstar(x_correct)`；L261-269 tick-constrained `threshold = ceil(Pstar_raw/0.01)*0.01`（conservative 主）；L283-288 用 `ref`（open 或 legal_trigger）与 `limit_down_px` 判断是否可成交、再乘滑点。continuous P\* 仅作 `NON_EXECUTABLE_REFERENCE`，optimistic tick 已标 `INVALID_DIAGNOSTIC`。 |

---

## 8. 回答核心问题

**"站在历史日期 T，当时可获得的信息是否足以构造当前回测使用的 adjusted-price BB / z-score 序列？"**

- **公司行动维度：是。** 后复权因子是截至当日公司行动的累积，跳变严格在 `ex_date`（305/305 验证），未来不提前进入；引擎用后复权口径、无前复权式重基准。截断 PIT 自洽 0 差异，信号与当前回测一致。
- **维护微调维度：无法完全回答（UNRESOLVED）。** 存在全市场同步微调日，无历史快照无法证实/证否其对早期因子值的修订；但其最坏量化影响 ≈0.06% 信号翻转率（实际二阶更小），不构成对当前回测结论的可操作扰动。
- **对 STRICT_C_EXECUTABLE_TICK（97 笔）：未发现任何一笔交易因该问题而改变。**

---

## 9. 验证方法、范围与缺口

- **验证方式**：官方文档口径核对（doc_id=146 / 109.md）＋ 全量数据形态分析（7.7M 行，2020-2026）＋ 24 股 case study（305 跳变与 dividend `ex_date` 交叉验证、截断 PIT 自洽、P\* 对比）＋ 维护微调最坏影响量化（8,400 窗口日）＋ 6 项指控逐条 FILE/FUNCTION/LINE 证据。
- **覆盖范围**：24 只高公司行动频次股票全覆盖验证；全市场层面只做了跳变统计与影响量化，未对全市场 5,000+ 只逐一拉 dividend（成本限制，且 305/305 已给出确定性结构证据）。
- **仍存在的缺口**：
  1. 无历史多时点因子快照 → 维护微调子维度无法闭环（UNRESOLVED — CANNOT FALSIFY）；
  2. 北交所涨跌幅规则实现不完整（实测影响≈0）；
  3. 退市股数据缺口（15 只，KNOWN LIMITATION，需外部数据闭环）；
  4. 未运行 Validation、未修改 Registry、未修改任何策略/代码（本任务约束）。
