# PHASE D1 — PIT CONTEXT DATA FOUNDATION（SECTOR + FUNDAMENTAL READINESS）

**状态**：DEVELOPMENT DIAGNOSTIC / WAITING EXTERNAL AUDIT（未外审前不写入 README CURRENT TRUTH）

**Registry**：`research/context/registries/PIT_CONTEXT_D1_REGISTRY.csv`
**Registry SHA256**：`6168e104505ea230eb5291a88885d3e4eaed3ad08f2975fbcda2cea0072fca24`

---

## 0. 治理链

- **R1.5（commit `096e7ce`）**：正式接受 S1.1 = C — NO STABLE RANKING VALUE；关闭 CONTEMPORANEOUS BB DEPTH RANKING branch；REPEAT_HIT exploratory finding NOT REGISTERED FOR DEVELOPMENT；开启 **PIT CONTEXT DATA FOUNDATION（D1）**。
- **D1-A prereg（commit `f5bf5e9`）**：冻结 PIT sector 规则、financial as-of 规则、revision 语义、TTM 语义、coverage gates、spot checks、no-outcome rule、分类、2025–2026 CLOSED。
- **结果 commit**：见文末（D1: PIT sector + fundamental context foundation (sector B / fundamental A)）。

## 1. 目的

只回答两个问题（DATA FOUNDATION ONLY，禁止策略测试、禁止读取 outcome 后挑指标、2025–2026 CLOSED）：

1. 对 2020–2024 每个 B20 signal date，能否可靠知道该股票当时所属行业/板块（PIT SECTOR）？
2. 到该 signal date 为止，公司当时已公开披露了哪些财务信息（PIT FUNDAMENTAL）？

PIT 硬规则：feature 只能使用 publish/announcement/effective date ≤ T 的信息；**禁止按 report_period/end_date 直接 join**。

## 2. Signal Universe

S1 frozen B20 信号（2020-01-01..2024-12-31）**仅取 join keys**：n = 63,785，unique ts_code = 5,147。构建过程不加载任何 future episode return/MAE/MFE。

## 3. Sector 数据层

- 数据源：Tushare `index_classify(level='L1', src='SW2021')`（31 个申万 2021 一级行业）+ `index_member`（in_date/out_date 成分历史，覆盖可回溯至 1990s）。
- `stock_basic.industry` 明确视为 **CURRENT SNAPSHOT**，从未用于历史归属（Registry I3）。
- membership 有效性：`membership_start <= T AND (membership_end IS NULL OR membership_end > T)`。
- 同一股票在多个行业 interval 中按时间不重叠排序取命中。

## 4. Fundamental 数据层

- 数据源：Tushare `fina_indicator`（比率/指标）、`income`（累计营收/归母净利，含 ann_date/update_flag 修订历史）、`cashflow`（累计经营现金流，含修订历史）、`express`（业绩快报，按 period）、`forecast`（业绩预告，逐只）。
- **AS_OF_VERSION_SELECTOR**：对 (ts_code, end_date) 的多个版本，signal_date=T 时取 `ann_date <= T` 的最新版本（同 ann_date 时 update_flag 大者优先；fina_indicator 同公告日重复行去重）。修订后数值仅在修订公告日之后可见。
- **TTM**：`cum(P, Y) + cum(Q4, Y−1) − cum(P, Y−1)`，只用已公告季度；不足四季 → NA。
- Feature store（frozen，非过滤器）：REVENUE_TTM / NETPROFIT_TTM / OCF_TTM / REVENUE_YOY / NETPROFIT_YOY / ROE / GROSS_MARGIN / DEBT_TO_ASSET / CURRENT_RATIO / OCF_TO_NETPROFIT / LOSS_FLAG / NEGATIVE_OCF_FLAG / PROFIT_DECLINE_FLAG / REVENUE_DECLINE_FLAG / FORECAST_TYPE / EXPRESS_AVAILABLE_FLAG / LATEST_REPORT_PERIOD / LATEST_ANN_DATE / FINANCIAL_AGE_DAYS。
- Missing 保持 NA + availability flag（禁止全样本 median imputation）。

## 5. 结果摘要

### 5.1 Sector（申万 2021 L1，31 行业）

| 指标 | 值 |
|---|---|
| membership 行数 | 7,740（5,503 只股票） |
| B20 股票在申万 universe | 5,144/5,147（99.94%） |
| **信号级 PIT coverage** | **94.555%**（2020 96.41 / 2021 93.03 / 2022 91.58 / 2023 92.85 / 2024 99.98） |
| 缺失信号 | 3,473（98.7% 为**申万首次纳入日期晚于信号日**——真实 PIT 特性；24 只无 membership） |
| 行业变更股 | 3,214（区间可重建） |
| spot check | 300 行（60 股×5 日）：bad_interval=0；25 个变更边界 chg_fail=0 |
| 重叠区间 | 168 只存在 SW2021 切换残留开放区间 → sector_at 采用"命中区间取 in_date 最大"规则修复 |
| **分类** | **B — PARTIAL（PIT 语义可靠；coverage 70–<95% 因纳入滞后）** |

### 5.2 Fundamental（5 接口全覆盖 5,147 只）

| 指标 | 值 |
|---|---|
| financial PIT coverage | **100.0%**（63,785 信号全部有 as-of 财报） |
| TTM coverage | 98.80% |
| forecast coverage | 94.73%（预增 21,818 / 略增 9,213 / 预减 7,833 / 首亏 5,777 / 续亏 4,930 / 扭亏 4,718 / 略减 3,610 / 续盈 1,530） |
| express coverage | 37.16%（业绩快报为部分公司披露，正常） |
| revision 期数 | 57,680 个 (ts_code, end_date) 有多版本；AS_OF_VERSION_SELECTOR 取 ann_date<=T 最新版 |
| 100 例 PIT spot check | **0 fail**（selected_ann_date<=signal_date 全成立；无 next_later_announcement<=T） |
| financial age | mean 70.3d / median 58.0d |
| 标志位 | LOSS_FLAG 18.2% / NEGATIVE_OCF 20.4% / PROFIT_DECLINE 50.3% / REVENUE_DECLINE 36.2% / EXPRESS 37.2% |
| **分类** | **A — READY** |

### 5.3 News

**NOT_READY**：本地无 timestamped news corpus；Tushare news 接口无历史且当前权限不可用；Registry I11 禁止搜索引擎抓取历史新闻回填。

## 6. 红队检查

| 检查 | 状态 |
|---|---|
| rt1 end_date/report_period merge | CLEAN（全部 join 用 ann_date<=T） |
| rt2 update_flag=1 回填历史 | CLEAN（update_flag 仅作同公告日 tie-break） |
| rt3 跨公告 ffill | CLEAN（每个 signal date 重新选择 as-of 版本） |
| rt4 当前行业快照回填 | CLEAN（只用 index_member in/out；stock_basic.industry 从未用于 membership） |
| rt5 未来退市/ST/行业变化 | CLEAN（区间仅来自历史 in/out） |
| rt6 TTM 含未来披露季 | CLEAN（三个累计项均 ann_date<=T 选择） |
| rt7 forecast/express 发布后信息 | CLEAN（ann_date<=T 且 end_date<=T） |

## 7. 分类与 Next Gate

- **SECTOR = B（PARTIAL）**：coverage 94.555%（<95% 因申万季度纳入滞后，属真实 PIT 特性），PIT 语义可靠、变更可重建、spot check PASS。
- **FUNDAMENTAL = A（READY）**：100% coverage、revision 语义 PASS、spot check PASS。
- **NEWS = NOT_READY**。
- **Next gate**：SECTOR B → 允许 S2；FUNDAMENTAL A → 允许 S3；两者均 A/B → **下一阶段优先 S3 FUNDAMENTAL DISTRESS FILTER**（技术性错杀 vs 永久性基本面重估假设——本阶段未测试）。
- 2025–2026 **CLOSED / UNTOUCHED**。

## 8. Invariants

I1–I13 全部 PASS（`results/evidence/d1/d1_invariants.json`）：S1 B20 keys only；无 outcome 加载；current snapshot 未回填；ann_date<=signal_date；修订仅修订公告后可见；TTM 只用已披露期；missing 保持 NA；无阈值测试；无 RSI/MACD/BB 新测试；无 portfolio；无 news 回填；2025–2026 未读；前序 Registry SHA 未变。

**交付物**：`research/context/pit_context_d1.py`、`PIT_CONTEXT_D1.md`、`research/context/registries/PIT_CONTEXT_D1_REGISTRY.csv(.sha256)`、`results/evidence/d1/`（12 个证据文件）。
