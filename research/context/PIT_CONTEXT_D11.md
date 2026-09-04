# PHASE D1.1 — PIT FINANCIAL VERSION-SELECTOR REMEDIATION

**状态：PASS（DEVELOPMENT DIAGNOSTIC / WAITING EXTERNAL AUDIT）**

- D1 外部审计结论：整体 PIT 架构合理，但 financial revision tie-break 与 D1 Registry 存在潜在不一致 → D1 **HOLD / REMEDIATION REQUIRED**，S3 禁止启动直至本阶段 PASS。
- 本阶段只修复版本选择器：完整实现 Registry 的 `ann_date<=T → latest ann_date → max update_flag → max f_ann_date → deterministic row-hash fallback`，并给 fina_indicator 同公告日重复行建立确定且 PIT-safe 的规则。
- **未改动**：sector 数据层（D1 sector B 不受影响）；未读取任何 outcome；未打开 2025–2026；未运行任何交易策略。

## 1. 治理链

- **R1.5** `096e7ce`：接受 S1.1=C，开启 D1。
- **D1-A prereg** `f5bf5e9`（Registry SHA `6168e104505ea230eb5291a88885d3e4eaed3ad08f2975fbcda2cea0072fca24`）。
- **D1 结果** `1b2e3e0`（sector B / fundamental A）。
- **D1.1-A prereg** `bc20cd6`（Registry SHA `414a1816fbe5bab5259a6f9c35f62f322a42bf384290354977d7da44535ac477`）——结果前 commit + push。
- **D1.1 结果 commit**：见文末。

## 2. D1.1 Registry 冻结要点

| 项目 | 冻结定义 |
|---|---|
| STRICT_SELECTOR（income/cashflow） | 候选 = ann_date<=T；取 max ann_date；tie1 max update_flag；tie2 max f_ann_date（**missing 排在 non-missing 之前**，即优先有正式披露日的版本）；仍相同 → 原始行 sha256 hash 确定性 tie-break（**不赋予经济含义**） |
| fina_indicator 规则 | 无可靠 update_flag/revision 标识；同 (ts_code,end_date,ann_date) 重复行：数值全同 → canonical dedup；存在不同值 → 量化并检查排序字段；无法 PIT 判定 → 标 **AMBIGUOUS，字段置 NA（宁可 NA，不能猜）** |
| 冲突扫描 | income/cashflow/fina 原始缓存：同 (tc,ed,ann) 多行组 / update_flag 不同组 / f_ann_date 不同组 / 数值不同组 |
| 抽查扩展 | 所有 conflict/ambiguous 命中事件全查（>500 时随机500+最大差异100 为下限；本阶段实际全查 1,179） |
| TTM 红队 | 全量信号：TTM 三个组件（cur/prev_same/prev_full）各自 ann_date<=signal_date，`future_component_count=0` |

## 3. 冲突扫描（原始缓存）

| 统计 | 数量 |
|---|---|
| income 同 (tc,end_date,ann_date) 多行组 | 57,838 |
| cashflow 同组 | 55,603 |
| fina_indicator 同组 | 101,904 |
| 其中 update_flag 不同的组 | 113,236（income+cashflow） |
| 其中 update_flag 相同但 **f_ann_date 不同** 的组 | **995** |
| 其中数值字段不同的组（三源合计） | 2,733 |
| fina_indicator 同日不同值 → AMBIGUOUS 组 | **2,020** |

明细：`results/evidence/d11/d11_version_conflicts.csv`。

## 4. OLD vs STRICT 信号级影响

**版本标识层面（latest_report_period / latest_ann_date / financial_age_days）：changed = 0 / 63,785（0.0000%）**——f_ann_date tie-break 从未改变任何信号选中的"报告期+公告日"。

但**同公告日多版本行的数值选择**存在真实差异：

| 字段 | changed n | changed % | max abs diff |
|---|---|---|---|
| revenue_ttm | 8,064 | 12.64% | 64.8 亿（收入口径实质差异） |
| netprofit_ttm | 8,348 | 13.09% | 6.74 亿 |
| ocf_ttm | 7,793 | 12.22% | 1.5e-5（仅浮点噪声） |
| revenue_yoy_pct | 7,363 | 11.54% | 42.66pp |
| netprofit_yoy_pct | 7,115 | 11.15% | 478.50pp |
| roe / gross_margin / debt_to_asset / current_ratio | ~1,133–1,176 | ~1.8% | AMBIGUOUS→NA |
| ocf_to_netprofit | 13,524 | 21.20% | 派生项 |
| loss_flag / profit_decline_flag / revenue_decline_flag / forecast_type | 1 / 1 / 5 / 25 | <0.04% | — |
| negative_ocf_flag / express_available_flag | 0 | 0 | — |

含义：D1 的 `drop_duplicates(ann_dt, update_flag, keep='last')` 在同公告日多版本行上**任意保留**，其中约 12% 的信号事件在 STRICT（f_ann_date 最新者）下取值不同——**income 重复行数值有实质差异（revenue 差 64.8 亿），cashflow 重复行几乎只是浮点噪声**。D1.1 已全量量化该差异，未隐藏。

fina_indicator：**1,179 个信号事件（1.85%）**命中同日不同值 → 按 Registry 置 AMBIGUOUS，roe/gross_margin/debt_to_asset/current_ratio 置 NA（D1 的 keep='last' 任意取值被废止）。

## 5. 抽查与红队

- **扩展抽查**：1,179 个 conflict/ambiguous 事件**全查**：`selected_ann_date <= signal_date` 全部成立；income/cashflow strict 选择（ann/update/f_ann 优先级）全部验证通过；fails=0。→ **PASS**
- **TTM 红队（全量 63,785 信号）**：249,636 个组件行；**future_component_count = 0**。→ **PASS**
- **fina AMBIGUOUS**：2,020 个 (tc,ed,ann) 组，命中 1,179 个信号事件；全部置 NA，无任意猜测。

## 6. Coverage（remediation 前后）

| 指标 | D1 | D1.1 STRICT |
|---|---|---|
| financial PIT coverage | 100.000% | 100.000% |
| TTM coverage | 98.804% | 98.804% |

## 7. 分类

- **SECTOR = B（PARTIAL）**——不受本阶段影响（sector 仅用 index_member）。
- **FUNDAMENTAL = A（READY）**——STRICT selector 全量通过：100% coverage、revision as-of 语义完整实现 Registry、1,179 全查 0 fail、TTM future=0。
- **D1.1 PASS = True**（7 项 gate 全部满足：STRICT 完整实现 Registry / tie 可复现 / fina 规则确定且 PIT-safe / spot checks PASS / TTM future=0 / 无 2025+ / 无 outcome access）。

## 8. 人话结论

财报历史版本的选择器已与 Registry 完全对齐：**同一天公告、多个版本存在时，现在严格按"公告日→更新标志→正式披露日"选择当时真实可见的版本**，不再依赖任何任意顺序；fina_indicator 同日不同值无法判定先后时一律标 AMBIGUOUS 并置 NA（宁可缺失不猜）。修正使约 12% 信号的收入/利润 TTM 数值、1.85% 信号的 fina 指标取值发生变化——**这是对 D1 数据层的真实修正**，但不改变任何选中版本的报告期/公告日标识，也不改变 sector 层。**D1 的基础数据结构是稳固的**，修正后更严格、更可复现。

**交付物**：`research/context/pit_context_d11.py`、`PIT_CONTEXT_D11.md`、`research/context/registries/PIT_CONTEXT_D11_VERSION_SELECTOR_REGISTRY.csv(.sha256)`、`results/evidence/d11/`（7 个证据文件）。
