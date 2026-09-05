# Squeeze / ADX Regime Attribution Audit — Registry（结果前冻结）

> 阶段：REG1（候选 Alpha / Regime Filter 审计，post-A0）
> 治理边界：**不修改任何冻结主策略参数/入场/退出/仓位；不使用 2025–2026；只做 historical trade attribution；禁止参数搜索**。
> 本 Registry 在读取任何组级结果之前冻结全部规格。

## 1. Baseline（冻结，不重新定义）

- **正式冻结版本**：S1 frozen B20 independent signal framework（commit `1368584` S1 result；episode 文件经 R0-B 迁移 `b343256`）。
- **交易记录文件**：`results/evidence/fullmarket/fullmarket_episode_metrics.csv`
- **development 样本**：`signal_date <= 2024-12-31` 且 `exit_date <= 2024-12-31` → **n = 61,828**（与 F2.1 `assert len(dev)==61828` 完全一致；TP 自然退出 episodes）。
- **baseline 冻结统计（parity 目标）**：mean simple_return_pct = +5.0993%，win = 77.89%，mean hold_days = 32.62。
- 交易字段：ts_code / signal_date / entry_date / exit_date / simple_return_pct / pnl / total_cost / hold_days / turnover_rank（amount ranking，universe/ranking 信息）。

## 2. 价格数据与 PIT 语义（冻结）

- `data/combined_daily.parquet`（2020–2024，全市场 OHLCV+adj_factor）+ `data/warmup_daily_2018_2019.parquet`（2018–2019 warmup；adj_factor 已验证与主数据无缝衔接，同一基准）。
- 复权价：`px_adj = raw × adj_factor`（high/low/close 均复权）。
- **REGIME_ASOF = signal_date（T）收盘**：信号 T 收盘生成、入场 T+1 open；T 收盘是入场时最后可见快照。任何指标只使用 `date <= T` 的数据。禁止读取 T 之后任何价格。

## 3. 指标参数（全部冻结，行业标准默认值，不做优化）

| 指标 | 参数 | 公式 |
|---|---|---|
| DMI/ADX | length=14, ADX smoothing=14（Wilder） | TR=max(H−L,|H−C₋₁|,|L−C₋₁|)；+DM/−DM 标准定义；Wilder ewm(α=1/14) 平滑；+DI=100·sm(+DM)/sm(TR)；−DI=100·sm(−DM)/sm(TR)；DX=100·|+DI−−DI|/(+DI+−DI)；ADX=Wilder(α=1/14) of DX |
| ADX_LEVEL | 冻结 5 桶 | <15 / [15,20) / [20,25) / [25,35) / ≥35 |
| ADX_SLOPE | 1/3/5 日 | ADX_t − ADX_{t−1}、ADX_t − ADX_{t−3}、ADX_t − ADX_{t−5} |
| **ADX_RISING** | 冻结 | ADX_slope_1 > 0 |
| DI_BULL / DI_BEAR | 冻结 | +DI>−DI / −DI>+DI |
| BB | 策略本身参数 period=20, k=2, ddof=1 | mid=MA20(adj close)；upper/lower=mid±2·SD20；width=(upper−lower)/mid |
| BB_WIDTH_PCT | 120 交易日 | 当日 width 在过去 120 个交易日（含当日，date≤T）窗口内的百分位 |
| KC | EMA20 + 1.5·ATR20（LazyBear 标准） | EMA(20, close, adjust=False)；ATR(20)=Wilder ewm(α=1/20) of TR；KC_upper=EMA20+1.5·ATR20；KC_lower=EMA20−1.5·ATR20 |
| SQUEEZE_ON | 冻结 | BB_upper < KC_upper 且 BB_lower > KC_lower |
| SQUEEZE_RELEASE | 冻结 | 前一日 SQUEEZE_ON 且当日非 SQUEEZE_ON |
| RELEASE_RECENT | 冻结分桶 | release today(0d) / 1–3d / 4–10d / no recent release；**RECENT_RELEASE = 距最近一次 release ≤3 个交易日** |
| SQUEEZE_DAYS | 冻结 | 当前连续 SQUEEZE_ON 天数（当日 OFF 记 0） |
| MOM | LazyBear Squeeze Momentum 公开定义，length=20 | MOM = (close_adj − close_adj[20]) / (0.5×(rolling max(high_adj,20) − rolling min(low_adj,20))) × 100 |
| MOM_SIGN | 冻结 | positive if MOM ≥ 0 else negative |
| MOM_SLOPE | 冻结 | MOM_t − MOM_{t−1}；rising if >0 else falling |
| BEARISH_MOMENTUM | 冻结 | MOM < 0 且 MOM 继续下降（slope < 0） |

## 4. 预注册组（结果前冻结，禁止事后新增/修改）

| 组 | 定义 |
|---|---|
| G1 Normal MR Environment | NOT(−DI>+DI 且 ADX_RISING 且 MOM<0) |
| G2 Bearish DMI Expansion | −DI>+DI 且 ADX_RISING |
| G3 Bearish Squeeze Release | RECENT_RELEASE(0–3d) 且 MOM<0 |
| G4 Strong Bear Expansion | −DI>+DI 且 ADX_RISING 且 MOM<0 且 MOM falling |
| G5 Strong Bear Expansion + Recent Release | G4 且 RECENT_RELEASE(0–3d) |

主比较：G2/G3/G4/G5 各 vs G1。G5 为最重要高风险候选，但不得因结果好看自动升级为过滤规则。

## 5. 统计方法（冻结）

- 组级：N / Win Rate / Avg / Median / P10 / P25 / P75 / P90 / Worst / Avg Hold / Sum PnL / PnL 占比。
- **Bootstrap difference in mean / win rate / tail-loss probability**（组间独立重采样，B=5000，seed=0，percentile 95% CI）。
- Mann-Whitney U（scipy.stats）+ Hedges' g effect size（小<0.2 / 中 0.2–0.5 / 大>0.5）。
- Tail loss attribution：全部交易按 return 升序，worst 5% / 10% / 20%，统计各 bearish 状态占比 vs 全体基础占比 → **Tail Enrichment Ratio**。
- VETO（4 个独立，trade-level 静态过滤，不得组合）：A) G2；B) G3；C) G4；D) G5。报告原 baseline / filtered trades / removed n / removed % / total return(CAGR) / MaxDD / Sharpe / Win / Avg Trade / turnover(trades/yr) / exposure(持仓日占比)；removed 中盈利/亏损拆分（foregone profit / avoided loss / net effect）；**exposure-adjusted**（每 1000 持仓日归一化 PnL）判断"是否只因少交易而改善"。

## 6. 分级门槛（冻结）

- **PASS-CANDIDATE**：至少一个 bearish 组（主看 G4/G5，允许 G2/G3）满足全部：① vs G1 bootstrap mean-diff 95% CI 下界 > 0（显著更差）；② 对应 veto 后 net PnL 改善 ≥ +1.0%；③ exposure-adjusted 改善仍为正；④ foregone profit ≤ 30% of avoided loss；⑤ 最大单股 veto PnL 占比 < 30%。
- **WEAK**：方向一致但 CI 跨 0 / effect 小 / 样本不稳。
- **FAIL**：无法区分好坏交易。
- **HARMFUL**：veto 净效果为负或显著损伤。
- 任何新发现只记录为 Future hypothesis，本阶段不继续优化。

## 7. 硬性禁止与范围

- 禁止：搜索 ADX threshold / ATR multiplier / squeeze lookback / momentum length / 组合条件；使用 2025–2026；结果后新增 subgroup。
- 2025–2026：CLOSED / UNTOUCHED（本阶段不读取任何 2025+ 数据）。
- 输出：`results/evidence/reg1/`（attribution / group_stats / tail / veto / inference / summary / invariants）+ 本报告。
