# PHASE E0 — CSI A股 ETF Universe Audit 最终报告

> 生成日期: 2026-09-04 | Branch: etf-e0 | Worktree: etf_e0_wt
> 数据来源: Tushare Pro (fund_basic 2941只 / index_basic 8000只 / fund_daily 1345只 / fund_adj 1345只 / fund_share 1358只)
> 策略基准: 冻结 BB(20,2.0) / amount Top10 / 次日open / K=3 / 5层 / 200k / 100万 / 10bp / STRICT_C

---

## A. Repository / Branch / Commit

- 主仓库: `audit_package/github_repo`, master HEAD = `f698b1a` (P6), 工作树 clean
- E0 branch: `etf-e0`, worktree: `etf_e0_wt/`
- E0 已有 commit: `7cf2149` (identity layer)
- E0 产物目录: `results/etf/` (13 个结果文件), `research/etf/` (13 个脚本)
- 主任务文件只读，未触碰

## B. Data Sources and Coverage

| 数据集 | 行数/文件数 | 覆盖范围 | 状态 |
|--------|-----------|---------|------|
| fund_basic | 2941 只 (2205 L / 676 D) | 全市场基金 | 完整 |
| index_basic (CSI) | 8000 只 | 中证指数全部 | 完整 |
| fund_daily | 1345 只 ETF | 2004–2026.09 | 完整（55只2026新上市无数据） |
| fund_adj | 1345 只 | 复权因子 | 完整 |
| fund_share | 1358 只 | 基金份额（PIT AUM） | 完整 |
| index_daily | 下载中 | 指数日线（Model 2 用） | 部分（非 E0 关键路径） |

## C. CSI Index Universe

| 指标 | 数值 |
|------|------|
| 中证发布指数总数 | 8000 |
| 候选 ETF 总数（股票型交易所ETF） | 1400 |
| Eligible 且有 daily 数据 | 1137 |
| Unique index_key（全部候选） | 377 |
| Universe A（当前代表，按规模最大） | 328 个指数 |
| Universe A 中 CSI 发布且 eligible | 244 |
| Universe B（PIT 代表，B2 ADV60 规则） | 363 个指数 |
| PIT 最早可用月份 | 2006-02 |

**同指数多 ETF**: 377 个 unique index，其中 194 个有 >1 只 ETF 跟踪，183 个仅 1 只。平均 3.7 只/指数，最多 41 只（沪深300）。

## D. Historical Coverage

| 历史长度 | ETF 数量 | 占比(1345只有数据) |
|---------|---------|-------------------|
| ≥15 年 | 23 | 1.7% |
| ≥10 年 | 80 | 6.0% |
| ≥7 年 | 140 | 10.4% |
| ≥5 年 | 404 | 30.0% |
| ≥3 年 | 648 | 48.2% |
| ≥1 年 | 1052 | 78.2% |
| <1 年 | 293 | 21.8% |

- 中位数: 2.9 年 | 均值: 3.7 年 | P25: 1.17 年 | P75: 5.21 年
- **结论**: 宽基 ETF（沪深300/中证500/创业板等）有 10-15 年历史，足够统计检验；行业/主题 ETF 多数 <5 年，历史有限。

## E. Liquidity Coverage

### AUM（基金规模）

| 分层 | 数量 | 占比 |
|------|------|------|
| ≥10 亿 | 318 | 23.6% |
| 5-10 亿 | 127 | 9.4% |
| 2-5 亿 | 211 | 15.7% |
| 1-2 亿 | 216 | 16.1% |
| <1 亿 | 473 | 35.2% |

### ADV60（日均成交额）

| 分层 | 数量 | 占比 |
|------|------|------|
| ≥5 亿 | 74 | 5.5% |
| ≥1 亿 | 158 | 11.7% |
| ≥5000 万 | 105 | 7.8% |
| ≥2000 万 | 172 | 12.8% |
| ≥1000 万 | 192 | 14.3% |
| <1000 万 | 561 | 41.7% |
| 缺失 | 83 | 6.2% |

- **合理流动性过滤（ADV60 ≥ 5000万）后剩 437 只**；ADV60 ≥ 1亿剩 232 只；ADV60 ≥ 5亿剩 74 只。
- 零成交交易日: 0（全部候选 ETF 均有持续成交）

## F. Duplicate ETF / Index Mapping

- 377 个 unique index，194 个有多只 ETF 跟踪
- 最大重复: 沪深300 指数有 41 只 ETF 跟踪
- Universe A（当前规模最大代表）: 328 个
- Universe B（PIT ADV60 代表）: 363 个，B1(AUM) 覆盖 363 个，B2(ADV60) 覆盖 362 个
- **Model 2 设计**: 信号由 CSI index 本身产生（index close → BB → signal），交易由当时真实可交易代表 ETF 执行。指数历史远长于 ETF，但 ETF 未上市前不能生成实际可交易收益。E0 仅完成设计，E1 实施。

## G. Trading-Rule Findings

详见 `e0_trading_rules_audit.md`。要点:
- T+1 确认；Lot=100 份确认；Tick=0.001 确认
- 涨跌幅: 10% (1145只) / 20% STAR (163只) / 20% GEM (92只，2020-08-24起)
- **无卖出印花税**（ETF vs 股票的关键成本差异）
- E1 必须加入: tick round、涨跌停成交约束、amount>0 过滤

## H. PIT / Survivorship Audit

- Universe B 使用 list_date PIT 过滤，最早 2006-02
- fund_share 提供 PIT AUM（2018-06 起 Tushare 有数据），此前 AUM 不可得
- **已知缺口**: delist_date 大量缺失（开放式 ETF 无固定到期日），清盘日期需基金公告；跟踪指数历史变更未做 PIT 重建
- Survivorship: 已清盘 ETF 的 fund_daily 截止到最后交易日，回测中自然不可交易，无未来信息泄漏

## I. Correlation / Effective Independent Assets

- 534 个指数/ETF 有收益序列（PIT 代表面板）
- 109,532 对相关性（min_periods=250）

| 相关性阈值 | pair 数量 | 占比 |
|-----------|----------|------|
| \|rho\| > 0.95 | 719 | 0.66% |
| rho > 0.90 | 3,060 | 2.79% |
| rho > 0.80 | 12,237 | 11.17% |
| rho > 0.50 | 70,000 | 63.9% |

- 均值 0.555 | 中位数 0.572 | P90 0.811
- Hierarchical clustering (ward, 1-corr):
  - 距离阈值 0.2 (rho>0.8): **110 个独立簇**
  - 距离阈值 0.3: **79 个独立簇**
  - 距离阈值 0.5: **25 个独立簇**
- **结论**: 534 个收益序列但仅 ~79 个独立风险暴露（rho>0.8 水平），存在显著"伪多样化"。宽基/行业/主题间相关性高，真正独立的风险因子有限。

## J. BB Signal-Density Diagnostic（冻结 BB(20,2) 原样）

| 指标 | 数值 |
|------|------|
| 总交易日 | 4,941 |
| 日均 eligible ETF 数 | 101.3（中位数 70，最大 317） |
| 有信号交易日 | 1,537（31.1%） |
| 日均信号数 | 4.92 |
| 中位数日信号数 | **0** |
| P75 / P90 / 最大信号数 | 1 / 11 / 266 |
| 0 信号日占比 | **68.9%** |
| ≥1 信号日占比 | 31.1% |
| ≥3 信号日占比 | 20.4% |
| ≥5 信号日占比 | 16.2% |
| ≥10 信号日占比 | 11.0% |
| 平均信号比率 (signal/eligible) | 4.7% |

- **结论**: BB(20,2) 下轨突破在 ETF Universe 上信号稀疏——近 69% 的交易日无任何信号，中位数 0。信号集中在市场极端下跌期（最大 266 个同时信号），平时资金大量闲置。

## K. Capital-Utilization Diagnostic（K=3 / 5层 / 200k / 100万）

| 指标 | 数值 |
|------|------|
| 平均资金利用率 | 67.4% |
| 中位数资金利用率 | **99.97%** |
| 平均现金占比 | 37.4% |
| 满仓日（≥99%）占比 | 51.8% |
| <50% 仓位日占比 | 31.8% |
| 期末权益 | 434,164（初始 1,000,000） |
| 总收益 | **-56.6%**（诊断性，非优化） |

- **结论**: 资金利用率呈双峰分布——要么满仓（信号集中期），要么大量现金（无信号期）。中位数 99.97% 说明一旦有信号就迅速满仓，但 31.8% 的日子仓位不足一半。-56.6% 的总收益是冻结 baseline 的诊断结果（ETF 上 BB 下轨策略表现差），E0 不做优化，E1 将与股票 baseline 做 apples-to-apples 对比。

## L. Data Limitations

1. **index_daily 未完整下载**: Model 2（index signal + ETF execution）需要指数日线，当前仅部分下载。E1 前需补全。
2. **delist_date 缺失**: 多数 ETF 无清盘日期，PIT Universe 依赖 fund_daily 自然截止。
3. **跟踪指数变更 PIT**: 未重建历史跟踪指数变更，当前映射为最新 benchmark。
4. **PIT AUM 仅 2018-06 起**: fund_share 数据从 2018 年中开始，此前 AUM 不可得。B1(AUM) 规则在此前不可用。
5. **55 只 2026 新上市 ETF 无历史**: 不影响回测（list_date 过滤），但影响当前 Universe 统计。
6. **NAV/IOPV/折溢价**: 未下载，无法做折溢价异常过滤。

## M. Bugs / Uncertainties Discovered

1. 前序 agent 的 `e0_download_etf_data.py` 因 `KeyError: 'map_index_code'` 崩溃，导致 index_daily 完全未下载——已修复为独立脚本 `e0_download_index_daily.py`。
2. `e0_build_master_full.py` 缺少 `status`/`bench_idx_name`/`benchmark` 列——已补全。
3. `e0_universes.py` 中 `index_key` 创建顺序在 `cur` 子集之后导致 KeyError——已修复。
4. `e0_history_liquidity_dup.py` 中 `layered()` 函数 bounds 降序但按升序区间计算，导致 AUM/ADV60 分布全为 0——已修复。
5. `e0_correlation_cluster.py` 布尔运算优先级错误（`&` 先于 `==`）——已修复。
6. `e0_signal_capacity.py` 缺少 `price_limit_pit` 列（从 trading rules audit 合并）、`panel` 误用 `rep` 而非含 signal 的 `sd`——已修复。

## N. GO / CONDITIONAL GO / NO-GO

### **判定: CONDITIONAL GO**

**支持 GO 的证据**:
1. Universe 足够大: 1137 只 eligible ETF，363 个 PIT 指数暴露，最早 2006 年
2. 流动性充足: 437 只 ADV60 ≥ 5000万，232 只 ≥ 1亿，74 只 ≥ 5亿
3. 宽基 ETF 有 10-15 年历史，足够统计检验
4. 交易成本低于股票（无印花税），有利于策略实施
5. PIT Universe 可构建，无显著 survivorship bias 泄漏

**限制条件（CONDITIONAL）**:
1. **信号密度过低**: 68.9% 交易日零信号，中位数 0——K=3 组合大部分时间无法满仓，策略容量受限
2. **伪多样化严重**: 534 个收益序列仅 ~79 个独立风险簇，同信号期高度集中
3. **行业/主题 ETF 历史短**: 中位数仅 2.9 年，多数 <5 年，长期回测只能靠宽基
4. **冻结 baseline 诊断收益 -56.6%**: ETF 上纯 BB 下轨策略表现差，E1 需验证是否为 Universe 特性还是策略不适配
5. **数据缺口**: index_daily 未全、delist_date 缺失、跟踪指数变更未 PIT 化

## O. Exact Recommendation for E1

**批准 E1 的前提条件（全部满足后启动）**:

1. **补全 index_daily**: 下载全部 154 个 unique index 的日线，用于 Model 2
2. **冻结 Universe 选择规则**: 采用 **B2 (ADV60(t-1) 最大)** 作为 PIT 代表选择规则（B1 AUM 仅 2018 后可用，B2 覆盖更全），写入 Registry 并 freeze
3. **冻结流动性过滤**: E1 baseline 用 **ADV60 ≥ 2000万**（437→? 实际 701 只 ≥1000万，建议 ≥2000万 = 509 只），sensitivity 加测 ≥5000万
4. **实施 Model 1 + Model 2 双轨**:
   - Model 1: ETF price 产生信号 + ETF 执行（历史从 ETF 上市起）
   - Model 2: Index close 产生信号 + ETF 执行（信号历史更长，但可交易收益从 ETF 上市起）
5. **E1 必须加入的交易规则**: tick=0.001 round、涨跌停成交约束（10%/20% PIT）、amount>0 过滤、无印花税
6. **Benchmark 冻结**: CSI 300 buy & hold、CSI A500 buy & hold、equal-weight eligible ETF universe
7. **E1 是 baseline falsification，不是 optimization**: 禁止参数扫描，禁止看到结果差就调参

**E1 不做**: RSI/MACD/ATR优化、板块强度、新闻/基本面、momentum regime、2.5σ/3σ、ML、参数网格——这些是 E2 内容。

---

## 十问速答

| # | 问题 | 答案 |
|---|------|------|
| Q1 | 当前符合条件的 CSI A-share equity ETF 多少只？ | 1137 只（eligible 且有数据），从 1400 候选中 |
| Q2 | 去同指数重复后 unique index exposures？ | 363 个（PIT B2）/ 328 个（当前规模代表） |
| Q3 | 历史长度够不够 statistically meaningful？ | 宽基够（10-15年，23只≥15年），行业/主题不够（中位2.9年） |
| Q4 | 多少 ETF 有 ≥3y/5y/7y/10y？ | 648 / 404 / 140 / 80 |
| Q5 | 按合理流动性过滤后剩多少？ | ADV60≥2000万: 509 只；≥5000万: 437 只；≥1亿: 232 只 |
| Q6 | 冻结 BB baseline 平均每天多少信号？ | 均值 4.92，中位数 **0**，68.9% 天零信号 |
| Q7 | Top-N 平均资金利用率？ | 均值 67.4%，中位 99.97%，51.8% 天满仓，31.8% 天 <50% |
| Q8 | 是否"数量多但高度相关、实际风险资产少"？ | **是**: 534 序列仅 ~79 独立簇（rho>0.8），12,237 对 rho>0.80 |
| Q9 | 是否有明显数据/制度障碍？ | index_daily 未全、delist_date 缺失、跟踪指数变更未 PIT 化——可修复，非致命 |
| Q10 | GO / CONDITIONAL GO / NO-GO？ | **CONDITIONAL GO**（见 N/O 节） |
