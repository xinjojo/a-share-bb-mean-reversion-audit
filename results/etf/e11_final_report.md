# PHASE E1.1 — ETF BB Mean Reversion FAILURE MECHANISM AUDIT

> 生成日期: 2026-09-04 | Branch: etf-e0 | Commit: (pending)
> 前置: E1 NO REPLICATION (commit 6789810)
> 本阶段目标: 精确解释为什么冻结的 ETF BB baseline 失败，以及失败机制能否反向理解股票版 edge 来源。
> **不是优化策略。所有 counterfactual 标记 POST-HOC DIAGNOSTIC ONLY。**

---

## A. FROZEN E1 REFERENCE

| 项目 | 值 |
|------|-----|
| E1 commit | `6789810` |
| E1 Registry SHA256 | `6cb7e9dd...7667eb` |
| Model1 trade_log SHA256 | `bf19b49f...a684a` |
| Model1 equity SHA256 | `18f608a3...852d5` |
| Model2 trade_log SHA256 | `a2283b19...38b2b` |
| Model2 equity SHA256 | `93ece2c4...e3bc2` |
| E1 verdict | NO REPLICATION (frozen; E1.1 不重新定义) |

E1.1 分析基于 E1 冻结 trade log，未重新运行策略。E1 frozen result 未被覆盖。

---

## B. E1.1 REGISTRY / SHA

Registry: `research/etf/PHASE_E1_1_REGISTRY.csv`
所有分析阈值在运行前冻结：tail levels (1/3/5/10/5%/10%), MAE/MFE 定义 (daily close from entry), BB mid/upper hit 定义, failure classification 阈值 (A/B/C/D/E), signal breadth bins (0-5/5-10/10-25/25-50/50%+), cluster concentration bins, forward horizons (1/3/5/10/20d), regime 定义 (CSI300 drawdown).

---

## C. TAIL CONCENTRATION

### Worst-N 贡献 (Model 1)

| 级别 | 交易数 | Sum PnL | 占 gross loss | 占 total gross |
|------|--------|---------|-------------|--------------|
| Worst 1 | 1 | -483,587 | **37.2%** | 79.6% |
| Worst 3 | 3 | -688,192 | **53.0%** | 113.3% |
| Worst 5 | 5 | -822,869 | 63.4% | 135.4% |
| Worst 10 | 10 | -1,004,664 | **77.4%** | 165.3% |

### Worst-N 贡献 (Model 2)

| 级别 | 交易数 | Sum PnL | 占 gross loss |
|------|--------|---------|-------------|
| Worst 1 | 1 | -229,557 | 21.7% |
| Worst 3 | 3 | -553,673 | **52.3%** |
| Worst 5 | 5 | -716,946 | 67.8% |
| Worst 10 | 10 | -885,856 | **83.7%** |

### Counterfactual Tail Removal (POST-HOC DIAGNOSTIC ONLY — NOT A TRADABLE STRATEGY)

| 排除 | Model1 剩余 Sum PnL | Model1 PF | Model1 均值收益 |
|------|-------------------|-----------|---------------|
| 全部 | -607,661 | 0.532 | -1.67% |
| 排除 worst 1 | -124,073 | 0.848 | -1.08% |
| **排除 worst 3** | **+80,532** | **1.132** | **-0.10%** |
| 排除 worst 5 | +215,208 | 1.452 | +0.59% |
| 排除 worst 10 | +397,003 | 2.350 | +1.56% |

**分类: TAIL-DOMINATED.** Worst 3 笔交易贡献了 53% 的 gross loss，排除后总 PnL 转正。但这是 post-hoc 诊断，不是可交易策略——事前无法识别哪 3 笔会成为 worst。

---

## D. PROFIT FACTOR DECOMPOSITION

| 指标 | Model 1 | Model 2 |
|------|---------|---------|
| Gross Profit | 691,196 | 623,559 |
| Gross Loss | 1,298,857 | 1,057,997 |
| Profit Factor | 0.532 | 0.589 |
| Winner count | 58 | 40 |
| Loser count | 43 | 33 |
| **Avg winner PnL** | **11,917** | **15,589** |
| **Avg loser PnL** | **-30,206** | **-32,061** |
| Median winner | 7,954 | 7,876 |
| Median loser | -11,897 | -10,189 |
| **Payoff ratio (avg win/avg loss)** | **0.395** | **0.486** |
| Breakeven win rate | 71.7% | 67.3% |
| **Actual win rate** | **57.4%** | **54.8%** |
| Expectancy per trade | -6,016 | -5,951 |
| **Failure due to** | **payoff_ratio** | **payoff_ratio** |

**核心结论: 策略失败不是因为胜率不够，而是因为 payoff ratio 太差。** 平均亏损是平均盈利的 2.5 倍（Model1）。胜率 57.4% 听起来不低，但需要 71.7% 才能盈亏平衡。亏损交易的幅度远大于盈利交易——这与 STRICT_C 退出机制直接相关：盈利交易在触及 upper band 时退出（锁定有限盈利），亏损交易则长期持有等待反弹（亏损不断扩大）。

---

## E. MAE / MFE

### 分布统计

| 指标 | Model 1 | Model 2 |
|------|---------|---------|
| Mean MAE | +2.05% | -3.97% |
| Mean MFE | +20.96% | +17.46% |
| Median MAE (all) | (见 trade distribution) | |
| P90 adverse excursion | (见 e11_mae_mfe files) | |

### 关键指标: MFE > 0 but final trade lost

| Model | 亏损交易中曾有正 MFE 的比例 |
|-------|--------------------------|
| Model 1 | **~95%** (几乎所有亏损交易都曾反弹) |
| Model 2 | ~94% |

**绝大多数亏损交易在持有期间曾明显反弹（MFE 为正），但因为 exit 目标（upper band / Pstar）太远而重新转亏。** 这是 exit-mismatch 的直接证据。

---

## F. BB MID / UPPER BAND HIT BEHAVIOR

| 指标 | Model 1 | Model 2 |
|------|---------|---------|
| **% trades hit mid (MA20)** | **100.0%** | **100.0%** |
| % trades hit upper (MA20+2σ) | 60.4% | 57.5% |
| % winners hit mid | 100.0% | 100.0% |
| % losers hit mid | 100.0% | 100.0% |
| % winners hit upper | 67.2% | 57.5% |
| % losers hit upper | 51.2% | 57.6% |
| Median days to mid | 20 days | 23 days |
| Median days to upper | 46 days | 52 days |
| **% hit mid but never upper** | **39.6%** | **42.5%** |
| **% hit mid then failed (final <=0)** | **42.6%** | **45.2%** |
| % never hit mid | 0.0% | 0.0% |
| **Mean MFE at mid hit** | **+16.45%** | **+13.51%** |

### 核心发现

1. **100% 的交易在持有期间触及 BB 中轨（MA20）**，触及中轨时平均已有 +16.5% 的浮盈（Model1）。
2. **只有 60% 触及上轨**——40% 的交易反弹到中轨后无法继续到上轨。
3. **43% 的交易触及中轨但最终亏损**——反弹到中轨后回落，未能达到 STRICT_C 的退出目标。
4. 中轨到上轨的中位数时间是 46 天——即使能到上轨，也需要长时间持有，期间回撤风险大。

**Hypothesis-generating diagnostic (NOT a strategy claim):** ETF 均值回归的自然回归尺度更接近中轨（MA20），而非上轨（MA20+2σ）。STRICT_C 的 Pstar/upper-band 退出目标对 ETF 来说过于激进。

---

## G. WORST 20 TRADE AUTOPSY

### Worst 5 (Model 1)

| # | 指数 | 收益 | 持仓 | MAE | MFE | 中轨 | 上轨 | 分类 | Regime | 信号比率 |
|---|------|------|------|-----|-----|------|------|------|--------|---------|
| 1 | 上证50 | -60.5% | 437d | -65.8% | +14.8% | ✓ | ✗ | REBOUND_RELAPSE | sideways | 60% |
| 2 | 上证红利 | -60.2% | 299d | -68.4% | +6.0% | ✓ | ✗ | REBOUND_RELAPSE | downtrend | 0% |
| 3 | 沪深300非银金融 | -38.1% | 115d | -48.2% | -0.4% | ✓ | ✓ | CRASH_CONTINUATION | downtrend | 63% |
| 4 | 深证100 | -34.8% | 169d | -44.1% | +7.6% | ✓ | ✗ | REBOUND_RELAPSE | downtrend | 0% |
| 5 | 中小企业100 | -32.0% | 104d | -42.8% | -0.3% | ✓ | ✓ | REBOUND_RELAPSE | stress | 0% |

### Worst 20 特征
- **全部为宽基/大盘指数**（上证50、沪深300、深证100、中证500、上证红利等），无行业/主题 ETF
- **持仓期极长**：中位数 >200 天，最长 5274 天（~14.5 年！）
- **全部触及中轨**，但多数未能触及上轨
- **入场时多为 downtrend/stress regime**（CSI300 drawdown < -15%）
- **5/20 入场时信号比率 >50%**（系统性暴跌中大量 ETF 同时超卖）
- 最差 1 笔（上证50，-60.5%）持有 437 天，MAE -65.8%，曾反弹 +14.8% 但未能到上轨

完整 Worst 20 见 `e11_worst20_trades.csv`，路径快照见 `e11_worst10_paths.csv`。

---

## H. FAILURE PATH CLASSIFICATION

### 分类规则（预注册冻结）
- **A. IMMEDIATE FAILURE**: MFE < 2% 且前 5 天 MAE < -5%
- **B. REBOUND THEN RELAPSE**: MFE ≥ 5%（或触及中轨）且最终收益 ≤ 0
- **C. SLOW BLEED**: 持仓 >60 天且 MFE < 5% 且非 A/D
- **D. CRASH CONTINUATION**: 前 10 天 MAE < -15%
- **E. OTHER**

### 结果

| 分类 | Model1 亏损交易数 | 占比 | 平均收益 | Model2 亏损交易数 | 占比 |
|------|-----------------|------|---------|-----------------|------|
| **B. REBOUND_RELAPSE** | **41** | **95.3%** | -10.4% | **31** | **93.9%** |
| D. CRASH_CONTINUATION | 2 | 4.7% | -22.5% | 2 | 6.1% | -17.3% |
| A. IMMEDIATE_FAILURE | 0 | 0% | - | 0 | 0% | - |
| C. SLOW_BLEED | 0 | 0% | - | 0 | 0% | - |

**压倒性结论: 95% 的亏损交易属于 REBOUND THEN RELAPSE。** 交易入场后曾明显反弹（触及中轨，MFE 为正），但因为退出目标太远而重新转亏。几乎没有"入场即崩"（A）或"长期阴跌"（C）的情况。

---

## I. HOLDING-PERIOD EFFECT

| 指标 | Model 1 | Model 2 |
|------|---------|---------|
| All mean holding | 166.5 days | 211.7 days |
| All median holding | 49.0 days | 51.0 days |
| **Winners mean holding** | **37.2 days** | **78.8 days** |
| **Losers mean holding** | **340.8 days** | **372.8 days** |
| Winners median | 30.5 days | 37.5 days |
| Losers median | 94.0 days | 69.0 days |
| corr(holding_days, trade_return) | -0.067 | +0.113 |
| **Longest 10 mean return** | **-22.4%** | **-2.9%** |
| Longest 10 % negative | **100%** | 80% |
| Longest 10 % hit upper | 60% | 80% |

**大亏与长期无法触达 upper band 强相关。** 亏损交易平均持有 341 天（Model1），是盈利交易（37 天）的 9 倍。最长 10 笔交易 Model1 全部亏损（平均 -22.4%），其中 60% 曾触及上轨但仍亏损——说明即使触及上轨，长期持有的回撤也可能吞噬盈利。

corr(holding, return) 弱负相关（-0.067），不构成因果声称，但描述性地说明长期持仓倾向于亏损。

---

## J. SIGNAL BREADTH / SYSTEMIC SELLOFF EFFECT

### Model 1 按信号比率分桶

| 信号比率桶 | 交易数 | 平均收益 | 中位收益 | 胜率 | PF | 平均 MAE | 平均 MFE |
|-----------|--------|---------|---------|------|-----|---------|---------|
| 0-5% (低宽度) | 54 | -0.77% | +2.38% | 68.5% | 0.891 | +13.1% | +35.6% |
| 5-10% | 4 | -0.39% | -1.33% | 50.0% | 0.929 | -2.9% | +7.3% |
| 10-25% | 15 | +1.49% | +2.26% | 53.3% | 2.409 | -5.6% | +7.0% |
| 25-50% | 9 | -3.23% | -5.11% | 33.3% | 0.223 | -8.8% | +1.0% |
| **50%+ (高宽度)** | **19** | **-6.26%** | **-1.64%** | **42.1%** | **0.174** | **-17.0%** | **+2.7%** |

### Low vs High Breadth 对比 (Model 1)

| 分类 | 交易数 | 平均收益 | 胜率 | PF |
|------|--------|---------|------|-----|
| Low breadth (<10%) | 58 | -0.74% | 67.2% | 0.892 |
| **High breadth (>=25%)** | **28** | **-5.29%** | **39.3%** | **0.179** |

**当大量 ETF 同时超卖（系统性暴跌）时，均值回归表现显著更差。** High breadth 入场平均收益 -5.29%，PF 仅 0.18；Low breadth 入场平均 -0.74%，PF 0.89。但注意：**即使 low breadth 也是负收益**——系统性拥挤加剧了失败，但不是唯一原因。

E0.1 已证明信号爆发日全在系统性暴跌阶段（2022-04、2023-10、2025-01/04、2026-03），信号比率 65-96%。

---

## K. RISK-CLUSTER CROWDING

| 聚类集中度 | Model1 交易数 | 平均收益 | 胜率 | PF |
|-----------|-------------|---------|------|-----|
| Medium (33-66%) | 23 | -3.97% | 65.2% | 0.306 |
| High (>66%) | 78 | -0.99% | 55.1% | 0.822 |

Model2 样本中 medium 仅 4 笔（不具统计意义），high 69 笔平均 -1.32%。

聚类集中度与收益的关系不明确（high concentration 反而略好于 medium），可能因为样本量小且聚类定义较粗。E1 已证明平均最大簇权重 47.4%，15.9% 天全在同一簇——**名义多样化不等于实际风险分散**，但聚类拥挤不是本阶段失败的主要驱动因素。

---

## L. TOP-N RANKING INFORMATION CONTENT

比较入选 Top-10（按 amount 排序）与未入选信号在固定 forward horizon 的表现（Model1，100 个信号日抽样）：

| Horizon | Selected Top-10 平均收益 | Non-selected 平均收益 | 差异 |
|---------|------------------------|---------------------|------|
| 1d | -0.114% | -0.147% | +0.033% |
| 3d | +0.008% | -0.107% | +0.115% |
| 5d | +0.135% | +0.152% | -0.017% |
| 10d | +0.549% | +0.537% | +0.012% |
| 20d | +0.172% | +0.234% | -0.062% |

**Top-N amount 排序在任何 horizon 上都没有显著区分度。** Selected 与 non-selected 的未来收益几乎相同（差异 < 0.12%，方向不一致）。这说明在 ETF 信号爆发时，按 amount（流动性）排序无法识别未来表现更好的 ETF——所有超卖 ETF 的未来收益分布几乎相同。

这与股票版形成对比（假设股票版 Top-N 有区分度，待验证）。股票层面的横截面离散度让 amount/BB_Z 排序有信息，而 ETF 层面高相关性消除了这种区分度。

---

## M. STOCK VS ETF CROSS-SECTIONAL DISPERSION

**Limitation:** 股票 baseline 每日候选/信号明细不在 ETF worktree 中，按 E1.1 规则未重建股票 pipeline。此项记录为 limitation。

ETF 侧可用数据：
- ETF 信号比率均值 4.68%，中位数 0%，最大 100%
- **78.1% 的交易日零信号**（E0 报告 68.9%，E1 流动性过滤后升至 78.1%）
- ETF 中位信号数/天 = 0，P90 = 4
- 信号高度集中在少数系统性暴跌日

**Hypothesis (待 E2 验证):** 股票层面拥有更大的横截面离散度（个股 idiosyncratic 超卖），让 Top-N 排序真正有信息；ETF 层面高相关性+低离散度导致信号要么没有、要么全市场同时超卖，排序无区分度。

---

## N. MODEL 1 VS MODEL 2 FAILURE DIFFERENCES

| 指标 | Model 1 | Model 2 |
|------|---------|---------|
| 总交易 | 101 | 73 |
| 胜率 | 57.4% | 54.8% |
| 平均收益 | -1.67% | -0.34% |
| 中位收益 | +0.96% | +1.20% |
| PF | 0.532 | 0.589 |
| 平均 MAE | +2.05% | -3.97% |
| 平均 MFE | +20.96% | +17.46% |
| % 触中轨 | 100% | 100% |
| % 触上轨 | 60.4% | 57.5% |
| 平均持仓 | 166.5d | 211.7d |
| Entry 重叠 | 18 | 18 |
| Worst5 ETF 重叠 | 1 | 1 |
| % 触中轨后失败 | 42.6% | 45.2% |

### Model 2 为什么只是"亏得少一点"？

1. **信号更少**（73 vs 101 笔）：指数信号比 ETF 信号更稀疏（0.52/天 vs 2.05/天），减少了交易次数和尾部暴露
2. **Entry 重叠仅 18 笔**：两个模型的入场时机差异很大，不是简单的噪声差异
3. **Worst5 ETF 重叠仅 1 只**：最大亏损交易不同，Model2 的 worst 1 仅 -22.9万（Model1 worst 1 -48.4万）
4. **平均 MAE 更低**（-3.97% vs +2.05%）：指数信号入场后短期回撤更小，可能因为指数价格更平滑
5. **但中位收益和触轨行为几乎相同**：两者的核心失败机制（REBOUND_RELAPSE, payoff ratio, exit-mismatch）完全一致

**结论: Model 2 的"更好"主要来自更少的交易和更小的尾部暴露，而非信号质量的根本提升。指数信号减少了 ETF 微观结构噪声（折溢价/流动性冲击），但没有修复负 expectancy。**

---

## O. MARKET REGIME DESCRIPTION

Worst 20 交易入场时的 CSI300 regime 分布：
- **downtrend (drawdown -15% ~ -25%)**: 最集中
- **stress (drawdown < -25%)**: 多笔
- **sideways (-5% ~ -15%)**: 少数
- **uptrend (> -5%)**: 几乎没有

ETF 大亏主要发生在市场已处于下跌趋势/压力状态时入场。BB 下轨信号在下跌趋势中频繁触发，但下跌趋势中的"超卖"往往不是均值回归机会，而是趋势延续的开始。

---

## P. CATEGORY / INDUSTRY PERSISTENCE

Worst 20 交易**全部为宽基/大盘指数**（上证50、沪深300、深证100、中证500、上证红利、中小板100等）。无行业/主题 ETF 进入 worst 20。

这可能因为：
1. 宽基 ETF 历史最长（2005-2006 上市），经历了 2008 金融危机和 2015 股灾
2. 宽基 ETF 在系统性暴跌中信号最集中（高宽度）
3. 行业/主题 ETF 上市较晚（多为 2019+），尚未经历极端长期下跌

此处仅做描述，**不据此从 universe 删除宽基 ETF**。

---

## Q. DATA LIMITATIONS

1. **股票 vs ETF 横截面离散度**: 股票信号明细不可得，记录为 limitation
2. **delist_date 大量缺失**: 清盘 ETF 依赖 fund_daily 自然截止
3. **涨跌停规则基于价格推断**: 非交易所官方停牌数据
4. **MAE/MFE 使用日频 close**: 未使用日内 high/low（intraday excursion 可能更大）
5. **Top-N info content 抽样 100 个信号日**: 非全量
6. **Model 2 仅覆盖 70 个有指数日线的 CSI 指数**

---

## R. OBSERVED EVIDENCE (按证据强度排序)

1. **EXIT-MISMATCH (最强)**: 100% 交易触中轨（平均 +16.5% MFE），仅 60% 触上轨，43% 触中轨后失败。95% 亏损交易 = REBOUND_RELAPSE。
2. **PAYOFF RATIO FAILURE (强)**: 平均亏损是平均盈利的 2.5 倍，breakeven WR 71.7% vs 实际 57.4%。失败归因于 payoff_ratio，非胜率。
3. **TAIL-DOMINATED (强)**: Worst 3 = 53% gross loss，排除后 PnL 转正。Worst 10 = 77-84% gross loss。
4. **TOP-N 排序无信息 (中)**: Selected vs non-selected 在所有 horizon 收益差异 < 0.12%。
5. **SYSTEMIC CROWDING 加剧失败 (中)**: High breadth 入场 PF=0.18 vs low breadth PF=0.89，但 low breadth 也负。
6. **长期持仓 = 亏损 (中)**: Losers 平均持仓 341 天 vs winners 37 天。Longest 10 全部亏损。
7. **聚类拥挤 (弱)**: 关系不明确，样本量小。
8. **股票横截面离散度 (limitation)**: 假设性解释，待验证。

---

## S. MECHANISM HYPOTHESES

### H1: ETF 均值回归的自然目标是中轨，不是上轨
- 证据: 100% 触中轨（+16.5% MFE），仅 60% 触上轨，43% 触中轨后失败
- 机制: ETF 是分散化组合，波动率低于个股，BB 上轨（MA20+2σ）对 ETF 来说过远
- STRICT_C 的 Pstar 退出目标基于个股历史校准，对 ETF 过于激进

### H2: 亏损幅度由"长期持有等待反弹"驱动
- 证据: Losers 持仓 341 天 vs winners 37 天；payoff ratio 0.39（avg loser 2.5x avg winner）
- 机制: 盈利交易快速触上轨退出（37 天），亏损交易长期持有等待（341 天），期间亏损不断扩大
- 这是 STRICT_C "让利润奔跑、亏损扛到反弹" 的不对称结果

### H3: 系统性暴跌中信号无区分度，Top-N 排序失效
- 证据: Top-N selected vs non-selected 收益无差异；high breadth 入场 PF=0.18
- 机制: 所有 ETF 同时超卖时，按 amount 排序无法识别未来表现更好的标的
- 股票版可能因横截面离散度大而有区分度（待验证）

### H4: 指数信号减少噪声但不修复负 expectancy
- 证据: Model2 亏损更少主要因为交易更少、尾部更小，核心失败机制相同
- 机制: 指数价格更平滑（无折溢价/流动性噪声），但均值回归 edge 在指数层面同样不存在

---

## T. FUTURE TESTABLE HYPOTHESES (E2 候选，不在本阶段测试)

| ID | 假设 | 可测试方式 |
|----|------|----------|
| H1 | ETF entry edge 存在，但 upper-band exit 太激进 | E2 预注册 midline/trailing exit，独立样本测试 |
| H2 | 均值回归仅在 low-breadth/idiosyncratic ETF 超卖中有效 | E2 预注册 breadth filter，比较有/无 filter |
| H3 | Top-N BB_Z 排序在系统性暴跌中失去信息 | E2 预注册 alternative ranking（BB_Z depth），比较 |
| H4 | 聚类分散比名义 ETF 数量更重要 | E2 预注册 cluster-aware selection |
| H5 | 指数信号减少微观结构噪声但不修复负 expectancy | 已部分验证，E2 可做更严格的 noise decomposition |
| H6 | 股票 edge 依赖个股横截面离散度 | E2 需获取股票信号明细，比较 stock vs ETF cross-sectional dispersion |

**以上仅为假设，禁止在 E1.1 测试。E2 需独立预注册后验证。**

---

## FINAL MECHANISM VERDICT

### **MULTI-MECHANISM FAILURE**

按证据强度排序：

1. **EXIT-MISMATCH DOMINATED** (最强证据): 100% 触中轨但仅 60% 触上轨，95% 亏损 = REBOUND_RELAPSE，平均亏损 2.5x 平均盈利
2. **TAIL-DOMINATED** (强): Worst 3 = 53% gross loss，Worst 10 = 77-84%
3. **SYSTEMIC-CROWDING AMPLIFIED** (中): High breadth 入场 PF=0.18，但 low breadth 也负
4. **RANKING INFORMATION LOSS** (中): Top-N 排序零区分度
5. **BROAD NEGATIVE EXPECTANCY** (基础): 即使排除尾部，core expectancy 仍接近零或微负

**核心一句话: ETF BB 均值回归策略失败，不是因为没有反弹（100% 触中轨），而是因为反弹不够远（仅 60% 触上轨），而 STRICT_C 退出机制要求必须到上轨/Pstar 才退出——导致 43% 的交易"曾经盈利但最终亏损"，平均亏损幅度是盈利的 2.5 倍。尾部 3 笔交易贡献了过半亏损。**

---

## 输出文件清单

| 文件 | 说明 |
|------|------|
| `e11_trade_distribution_model1.csv` | Model1 交易分布（P1-P99, best/worst） |
| `e11_trade_distribution_model2.csv` | Model2 交易分布 |
| `e11_tail_contribution.csv` | Worst-N 贡献分析 |
| `e11_tail_removal_diagnostic.csv` | Counterfactual 尾部移除（POST-HOC ONLY） |
| `e11_mae_mfe_model1.csv` | Model1 每笔 MAE/MFE/BB 路径 |
| `e11_mae_mfe_model2.csv` | Model2 每笔 MAE/MFE/BB 路径 |
| `e11_bb_path_stats.csv` | BB 中轨/上轨触及统计 |
| `e11_worst20_trades.csv` | Worst 20 交易尸检 |
| `e11_worst10_paths.csv` | Worst 10 路径快照 |
| `e11_failure_classification.csv` | 失败路径分类汇总 |
| `e11_holding_period_analysis.csv` | 持仓期分析 |
| `e11_signal_breadth_analysis.csv` | 信号宽度/系统性暴跌分析 |
| `e11_cluster_crowding_analysis.csv` | 聚类拥挤分析 |
| `e11_topn_information_content.csv` | Top-N 排序信息含量 |
| `e11_stock_vs_etf_dispersion.csv` | 股票 vs ETF 离散度（limitation） |
| `e11_model1_vs_model2.csv` | Model1 vs Model2 对比 |
| `e11_profit_factor_decomposition.csv` | PF 分解 |
| `e11_final_report.md` | 本报告 |
| `PHASE_E1_1_REGISTRY.csv` | E1.1 预注册冻结 |
