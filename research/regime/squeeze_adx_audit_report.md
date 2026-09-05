# Squeeze / ADX Regime Attribution Audit — Final Report (REG1)

## 结论（先给答案）

**分类：HARMFUL**（`results/evidence/reg1/squeeze_adx_summary.json`）

- **BB Mean Reversion 的大亏损并没有集中在 "向下趋势扩张 / 波动率释放" 状态里。**
- Bearish DMI Expansion（G2）与 Strong Bear Expansion（G4）状态下，B20 交易的独立收益**反而略高于** Normal MR（+0.54pp / +0.44pp，bootstrap 95% CI 均不含 0），但 effect size 极小（Hedges' g ≈ 0.05），且 tail 无富集（enrichment ≈ 1.0×）。
- Bearish Squeeze Release（G3）与 Strong Bear Expansion + Recent Release（G5）与 Normal 无显著差异（CI 跨 0）。
- 四个独立 VETO（剔除对应状态）**全部显著伤害原策略**：PnL −11.6% ~ −62.1%；被剔除的交易 77.6%–78.7% 是盈利交易，foregone profit 是 avoided loss 的 1.7–1.8 倍。
- 因此：**Squeeze / DMI / ADX 状态变量没有资格进入下一阶段过滤器研究**；把它们作为入场 veto 会损害而不是帮助策略。

## 1. Baseline（冻结，未重新定义）

| 项 | 值 |
|---|---|
| 策略 | S1 frozen B20 independent signal framework（BB20/2, ddof=1, adj close；T+1 open 入场；自然退出 replay） |
| baseline commit | S1 result `1368584`；episode 文件迁移 `b343256`（R0-B） |
| 交易记录 | `results/evidence/fullmarket/fullmarket_episode_metrics.csv` |
| development 样本 | signal_date ≤ 2024-12-31 且 exit_date ≤ 2024-12-31 → **n = 61,828**（与 F2.1 `assert len(dev)==61828` parity 0 误差） |
| baseline 冻结统计 | mean return +5.0993% / win 77.89% / mean hold 32.62d |
| 价格数据 | `data/warmup_daily_2018_2019.parquet` + `data/combined_daily.parquet`（≤2024-12-31）；复权价 = raw×adj_factor（已验证跨文件连续） |
| PIT 语义 | REGIME_ASOF = signal_date（T）收盘；指标只用 date ≤ T；2025–2026 未读取（UNTOUCHED） |

## 2. 冻结参数（行业标准默认，无搜索）

- DMI/ADX：length=14，ADX smoothing=14（Wilder ewm）；ADX_LEVEL 五桶（<15 / 15–20 / 20–25 / 25–35 / ≥35）；ADX_SLOPE 1/3/5d；ADX_RISING = slope_1>0。
- BB：策略自身参数 period=20, k=2, ddof=1；BB_WIDTH_PCT = 过去 120 交易日窗口内（含当日）百分位。
- KC：EMA20（adjust=False）± 1.5×ATR20（Wilder ewm α=1/20）。
- SQUEEZE_ON = BB 全含于 KC；RELEASE = 前日 ON 今日 OFF；RECENT_RELEASE = 距最近 release ≤3 交易日；squeeze_days 连续计数。
- Momentum：LazyBear Squeeze Momentum 公开定义，length=20：MOM = (close_adj − close_adj[20]) / (0.5×(max20(high_adj) − min20(low_adj))) × 100；MOM_SIGN（≥0 positive）；MOM_SLOPE（>0 rising）；BEARISH_MOMENTUM = MOM<0 且 slope<0。
- **实现验证**：4 只抽样股票（000001/600519/300750/002594）全部 signal-date，独立慢速参考实现 vs 脚本输出相对误差 = 0（含 pdi/ndi/adx/bb_width/squeeze/mom）。

## 3. 预注册组与占比（组互斥性：非互斥标记，各自 vs G1）

| 组 | 定义 | n | 占比 |
|---|---|---|---|
| G1 Normal MR | NOT(−DI>+DI 且 ADX_RISING 且 MOM<0) | 27,955 | 45.21% |
| G2 Bearish DMI Expansion | −DI>+DI 且 ADX_RISING | 34,442 | 55.71% |
| G3 Bearish Squeeze Release | RECENT_RELEASE(0–3d) 且 MOM<0 | 14,884 | 24.07% |
| G4 Strong Bear Expansion | G2 且 MOM<0 且 MOM falling | 28,090 | 45.43% |
| G5 Strong Bear + Release | G4 且 RECENT_RELEASE(0–3d) | 7,015 | 11.35% |

注：B20 信号日天然处于 bearish DMI expansion 的占比高达 55.7%——超卖信号本身多发生在下跌趋势扩张日，这是该状态的"基础率"。

## 4. 分组表现（Task 2，全部组均报告）

| 组 | n | Win% | Avg% | Median% | P10% | P90% | Worst% | Hold d | Sum PnL（元） | PnL 占比 |
|---|---|---|---|---|---|---|---|---|---|---|
| ALL | 61,828 | 77.89 | 5.099 | 5.471 | −5.91 | 16.07 | −85.98 | 32.62 | 702,674,033 | 100% |
| G1 | 27,955 | 76.91 | 4.788 | 5.249 | −6.19 | 15.60 | −85.98 | 32.12 | 268,153,641 | 38.2% |
| G2 | 34,442 | 78.72 | 5.325 | 5.649 | −5.73 | 16.36 | −85.98 | 33.02 | 436,575,006 | 62.1% |
| G3 | 14,884 | 77.56 | 4.945 | 5.346 | −6.12 | 15.96 | −85.98 | 33.06 | 159,218,055 | 22.7% |
| G4 | 28,090 | 78.43 | 5.232 | 5.577 | −5.81 | 16.28 | −85.98 | 33.23 | 347,544,025 | 49.5% |
| G5 | 7,015 | 78.00 | 4.986 | 5.222 | −6.02 | 15.92 | −85.98 | 33.43 | 81,308,391 | 11.6% |

（G2/G3/G4/G5 非互斥，故 PnL 占比之和不等于 100%；Sum PnL 为每笔独立 200k 名义 replay 口径。）

## 5. 统计检验（Task 4，vs G1；bootstrap B=5000, seed=0）

| 组 | mean diff (pp) | 95% CI | Mann-Whitney p | Hedges' g |
|---|---|---|---|---|
| G2 | **+0.537** | [+0.377, +0.703] | 1.1e-14 | 0.052 |
| G3 | +0.157 | [−0.041, +0.354] | 0.0155 | 0.016 |
| G4 | **+0.444** | [+0.278, +0.614] | 5.1e-10 | 0.043 |
| G5 | +0.197 | [−0.068, +0.464] | 0.0676 | 0.020 |

- 方向语义：diff = bearish − G1。**正值 = bearish 组更好**。G2/G4 显著更好但 effect size 极小（<0.06）；G3/G5 无显著差异。
- Win-rate / tail-loss-prob 的 bootstrap 差异方向一致（详见 `squeeze_adx_inference.csv`）。

## 6. Tail Loss Attribution（Task 3）

| 状态 | 全体占比 | worst5% 占比 | Enrich× | worst10% 占比 | Enrich× | worst20% 占比 | Enrich× |
|---|---|---|---|---|---|---|---|
| G2 | 55.7% | 56.1% | 1.01 | 54.2% | 0.97 | 53.7% | 0.96 |
| G3 | 24.1% | 24.0% | 1.00 | 24.7% | 1.03 | 24.3% | 1.01 |
| G4 | 45.4% | 45.9% | 1.01 | 44.6% | 0.98 | 44.4% | 0.98 |
| G5 | 11.3% | 11.0% | 0.97 | 11.5% | 1.01 | 11.3% | 1.00 |

**大亏损无任何富集**：最差 5%/10%/20% 中 bearish 状态占比与全体基础占比一致（enrichment 0.96–1.03×）。

## 7. 反事实 VETO（4 个独立，禁止组合；signal-level 静态模拟）

| VETO | removed n | removed % | removed win% | removed avg% | PnL 变化 | kept total return% | kept MaxDD% | foregone/avoided |
|---|---|---|---|---|---|---|---|---|
| G2 | 34,442 | 55.71 | 78.72 | +5.325 | **−62.1%** | 1.97 | −13.1 | 184% |
| G3 | 14,884 | 24.07 | 77.56 | +4.945 | **−22.7%** | 2.35 | −30.3 | 169% |
| G4 | 28,090 | 45.43 | 78.43 | +5.232 | **−49.5%** | 2.15 | −10.8 | 182% |
| G5 | 7,015 | 11.35 | 78.00 | +4.986 | **−11.6%** | 2.30 | −16.3 | 176% |

- 全部 veto 移除的大多是盈利交易（removed win 77.6–78.7%），foregone profit 是 avoided loss 的 1.7–1.8 倍。
- 任何"改善"（如 G3/G5 exposure-adjusted 每千持仓日 PnL 微升 2.3%/0.06%）都来自少交易，绝对 PnL 与总收益显著下降；这不是可利用的过滤器，而是**剔除好交易**。
- 说明：本 veto 为 signal-level replay 静态模拟（每笔独立 200k 名义），不是真实 K=3 组合引擎重跑；真实组合下因 K 槽位再分配效果只会更弱，不会更有利。

## 8. 分级判定（Registry 冻结门限）

PASS-CANDIDATE 要求：某 bearish 组显著更差（CI 上界<0）+ veto 净改善 ≥1% + exposure-adjusted 为正 + foregone ≤30% of avoided + 非单一股票驱动。
**无一满足**；且 4 个 veto 的 PnL 变化均 ≤ −11.6%（≤ −1.0% 阈值）→ 按冻结决策树：

> **FINAL: HARMFUL**

## 9. 治理与文件

- Registry：`research/regime/registries/SQUEEZE_ADX_REGIME_REGISTRY.csv` SHA `ce8460a6c2c159c8b8119b28c5ae79d39822d928f4e857b3c03839fed69ae141`（commit `6b7dfb5` REG1-A，结果前冻结）。
- baseline commit：S1 result `1368584` / episode 迁移 `b343256`；analysis commit：见 REG1-B。
- 数据范围：2018-01-02 .. 2024-12-31（warmup + development）。**2025–2026 未触碰**（价格数据与 episodes 均以 2024-12-31 截断；invariants 机器记录）。
- 输出：`results/evidence/reg1/`（squeeze_adx_trade_attribution.csv / group_stats.csv / tail_attribution.csv / inference.csv / veto_results.csv / summary.json / invariants.json）。
- 未做：参数扫描、组合搜索、结果后新增 subgroup、策略修改、portfolio 重跑。

## 10. Future Hypotheses（只记录，不开发）

1. G2/G4 的微弱正差可能与 B1.1 的 date-level breadth edge 重叠（bearish expansion 日≈高 B20 breadth 日）；需跨阶段联合审计才能分离，本阶段禁止。
2. Squeeze release 在"入场后"而非"入场日"的动量结构，可能对 exit/持仓管理有信息（超出本阶段 attribution 范围）。

## 11. 下一步建议

**STOP**。Squeeze / DMI / ADX 不作为 BB Mean Reversion 的入场过滤器；该分支关闭。主策略保持 STRICT_C / A0 K3 冻结不变；A0 DECISION B（不开盲测）不受影响。
