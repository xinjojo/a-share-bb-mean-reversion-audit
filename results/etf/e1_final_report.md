# PHASE E1 — ETF BB Mean Reversion Baseline Falsification 最终报告

> 生成日期: 2026-09-04 | Branch: etf-e0 | Commit: (pending)
> 前置: E0 complete (CONDITIONAL GO), E0.1 PASS WITH KNOWN LIMITATIONS
> 本阶段目标: 验证股票 BB Mean Reversion edge 是否能在 ETF/index 层面独立复现。不是优化。

---

## 0. 工程实现说明

### 引擎选择
按 ponytail 原则（reuse > copy, adapter > fork），**未新建独立 backtest engine**，而是基于 E0 诊断模拟引擎（`e0_signal_capacity.py`）适配为 E1 正式 baseline 引擎，修复并补全：

| E0 诊断缺失 | E1 修复 |
|------------|---------|
| 代表切换 bug（按 index_key 跟踪，退出用当日代表） | 按 `(index_key, etf_code)` 跟踪，退出用实际持仓 ETF |
| 无 tick rounding | 所有成交价 round 到 0.001 元 |
| 无涨跌停约束 | PIT 10%/20% 规则，涨停 open 不买入，跌停日不盘中退出 |
| 无流动性过滤 | ADV60(t-1) ≥ 2000万元（Registry 冻结） |
| 无 amount>0 执行检查 | 成交前检查 amount>0 |
| 无完整交易日志 | 每笔 ENTRY/ADD/EXIT 记录价格/数量/费用/PnL/持仓天数 |

未触碰股票版共享引擎（`portfolio_architecture_p4.py`），无 shared-core regression 风险。

### 冻结参数（与股票 A0 baseline 完全一致，apples-to-apples）
BB(20,2) / amount Top10 / T+1 open / K=3 / max_levels=5 / level_cash=200k / initial=1M / slippage=10bp / commission=0.025% min 5元 / **无卖出印花税（ETF）** / STRICT_C dynamic_touch exit（Pstar=analytic_Pstar(近19日 close_adj)）

### Model 定义
- **Model 1**: ETF close → BB signal → ETF execution（信号与执行均用 ETF）
- **Model 2**: Index close → BB signal → PIT representative ETF execution（信号用指数，执行用 ETF）
- 两者仅信号源不同，其余完全相同

---

## 1. Model 1 结果（ETF Price Signal + ETF Execution）

### Full Window (2006-05 ~ 2026-09, 20.3年, 4941交易日)

| 指标 | 数值 |
|------|------|
| Total Return | **-60.77%** |
| CAGR | -4.50% |
| Annualized Vol | 16.50% |
| Sharpe | -0.2065 |
| MaxDD | -69.86% |
| Calmar | -0.0645 |
| 总交易 | 235 (ENTRY 101, ADD 33, EXIT 98, FINAL 3) |
| 完成交易 | 101 |
| 胜率 | 57.43% |
| 平均单笔 PnL | -6,016 |
| 中位单笔 PnL | +1,258 |
| Profit Factor | 0.5322 |
| 平均持仓天数 | 166.5 |
| 平均仓位 | 75.07% |
| 满仓日占比 | 60.39% |
| 年化换手率 | 1.02 |
| 日均信号 | 2.05 |
| 成本拖累 | 1.03% |

### Common Window (2020-2024, 1212交易日)

| 指标 | 数值 |
|------|------|
| Total Return | **-14.40%** |
| CAGR | -3.06% |
| Annualized Vol | 7.66% |
| Sharpe | -0.3838 |
| MaxDD | -21.85% |
| 交易 | 44 (完成 20) |
| 胜率 | 50.0% |
| Profit Factor | 0.4934 |

---

## 2. Model 2 结果（Index Signal + ETF Execution）

### Full Window (2006-05 ~ 2026-09)

| 指标 | 数值 |
|------|------|
| Total Return | **-43.44%** |
| CAGR | -2.77% |
| Annualized Vol | 14.78% |
| Sharpe | -0.1222 |
| MaxDD | -50.06% |
| 总交易 | 192 (ENTRY 73, ADD 46, EXIT 70, FINAL 3) |
| 完成交易 | 73 |
| 胜率 | 54.79% |
| 平均单笔 PnL | -5,951 |
| 中位单笔 PnL | +2,393 |
| Profit Factor | 0.5894 |
| 平均持仓天数 | 211.7 |
| 平均仓位 | 71.13% |
| 日均信号 | 0.52（指数信号远少于 ETF 信号） |

### Common Window (2020-2024)

| 指标 | 数值 |
|------|------|
| Total Return | **-11.22%** |
| CAGR | -2.35% |
| Annualized Vol | 6.97% |
| Sharpe | -0.3206 |
| MaxDD | -18.27% |

---

## 3. 三方对比：Stock A0 vs ETF Model1 vs ETF Model2

### Common Window (2020-2024) — 正式横向比较

| 指标 | Stock A0 (冻结baseline) | ETF Model 1 | ETF Model 2 |
|------|------------------------|-------------|-------------|
| Total Return | **+30.30%** | -14.40% | -11.22% |
| CAGR | **+5.66%** | -3.06% | -2.35% |
| Ann Vol | N/A | 7.66% | 6.97% |
| Sharpe | **0.347** | -0.384 | -0.321 |
| MaxDD | -30.79% | -21.85% | -18.27% |
| 交易数 | 76 | 44 | N/A |
| 信号源 | 个股 close | ETF close | Index close |

### Full Window (2006-2026)

| 指标 | ETF Model 1 | ETF Model 2 |
|------|-------------|-------------|
| Total Return | -60.77% | -43.44% |
| CAGR | -4.50% | -2.77% |
| Sharpe | -0.207 | -0.122 |
| MaxDD | -69.86% | -50.06% |

### Model 1 vs Model 2 对比
- Model 2（指数信号）在两个窗口均优于 Model 1（ETF 信号）：full window -43.44% vs -60.77%，common window -11.22% vs -14.40%
- Model 2 信号更少（0.52/天 vs 2.05/天），持仓更长（212天 vs 167天），波动率更低
- 但两者均为负收益，**Model 2 的"更好"只是"亏得更少"，不是 edge 复现**

---

## 4. E1-11 六问回答

### Q1: ETF 是否复现 edge？
**否。** 股票 A0 baseline 在 2020-2024 获得 +30.30%（Sharpe 0.347），而 ETF Model 1 为 -14.40%（Sharpe -0.384），Model 2 为 -11.22%（Sharpe -0.321）。两个 ETF 模型均显著跑输股票 baseline，且均为负收益。

### Q2: Model 1 与 Model 2 哪个更强？
**Model 2（指数信号）略强**，但两者均亏损。Model 2 信号更少、持仓更长、波动率更低、回撤更小，但收益仍为负。差异可能来自指数价格噪声更少（ETF 价格含跟踪误差/折溢价/流动性冲击）。

### Q3: ETF 版是否胜率更高但收益更低？
**是。** Model 1 胜率 57.4%（full）/ 50%（common），Model 2 胜率 54.8%，但平均单笔 PnL 均为负（-6,016 / -5,951），Profit Factor 均 < 0.6。这意味着**多次小赢被少数大亏吞噬**——与 STRICT_C 退出机制下尾部风险有关。

### Q4: ETF 版是否显著降低尾部风险？
**Common window 是，full window 否。** Common window 中 ETF MaxDD（-21.85% / -18.27%）小于股票（-30.79%），但 full window 中 ETF Model 1 MaxDD 达 -69.86%（2008 年金融危机），远超股票 baseline 的 -30.79%。ETF 版在极端系统性下跌中反而回撤更大，因为 BB 下轨信号在暴跌中集中触发且无法及时退出。

### Q5: ETF 版资金利用率是否成为瓶颈？
**不是主要瓶颈。** Model 1 平均仓位 75.1%，满仓日 60.4%；Model 2 平均仓位 71.1%。资金利用率与股票版相当（股票版 K=3 也有仓位限制）。资金利用率不是 edge 消失的主因。

### Q6: 股票版 edge 是否可能依赖个股横截面离散度？
**高度可能（机制解释，非因果证明）。** 关键证据：
1. E0 已证明 ETF/index 间高度相关（340 序列仅 49 独立簇，12,237 对 rho>0.80）
2. 信号爆发时 65-96% 的 Universe 同时触及 BB 下轨（E0.1-D），Top-N 选择无法提供多样化
3. 股票版 amount Top10 排序在个股横截面上有区分度（不同股票超卖程度不同），而 ETF 版中所有 ETF 同时超卖时排序接近随机
4. ETF 是分散化组合，个股层面的 idiosyncratic 均值回归在 ETF 层面被分散掉
5. Model 2（指数信号）优于 Model 1（ETF 信号），进一步说明 ETF 价格噪声（跟踪误差/折溢价）有害，但即使纯指数信号也无法产生正收益

**结论：股票 BB 均值回归 edge 很可能依赖个股横截面离散度和 idiosyncratic 超卖修复，这在 ETF/index 层面被分散化和高相关性消除。**

---

## 5. Cluster Exposure（E1-10）

| 指标 | 数值 |
|------|------|
| 平均持仓数 | 2.26 (K=3 max) |
| 平均独立簇数 | 2.08 (共 49 簇) |
| 平均最大簇权重 | 47.4% |
| 全在同一簇的天数 | 785 (15.9%) |
| ≥2 个独立簇的天数 | 3,617 (73.2%) |

Top-N 名义上持有多个 ETF，但 ~16% 的天数全部持仓在同一风险簇，平均最大簇权重 47.4%。**名义多样化 ≠ 实际风险分散。**

---

## 6. 数据与限制

### 数据覆盖
- ETF fund_daily: 1,345 只（2004-2026）
- Index daily: 70/71 成功下载（1 个申万指数空数据）
- PIT representative: B2 ADV60(t-1)，258 个指数通过流动性过滤
- 流动性过滤: ADV60 ≥ 2000万元（Registry 冻结）

### 已知限制
1. delist_date 大量缺失，清盘 ETF 依赖 fund_daily 自然截止
2. 跟踪指数历史变更未做 PIT 重建（当前映射为最新 benchmark）
3. PIT AUM 仅 2018-06 起可用（B2 ADV60 规则不受影响）
4. 涨跌停规则基于价格数据推断（open >= pre_close*(1+limit)*0.999），非交易所官方停牌数据
5. Model 2 指数信号仅覆盖 70 个有指数日线的 CSI 指数

---

## 7. FINAL VERDICT

### **NO REPLICATION**

股票 BB Mean Reversion baseline（A0, BB(20,2), amount Top10, STRICT_C, K=3）在 ETF/index 层面**未能复现**：

| 层面 | 2020-2024 Total Return | Sharpe |
|------|----------------------|--------|
| 股票 A0 (冻结) | +30.30% | 0.347 |
| ETF Model 1 | -14.40% | -0.384 |
| ETF Model 2 | -11.22% | -0.321 |

**失败本身就是有效研究结果。** 股票 edge 很可能依赖个股横截面离散度，在 ETF/index 高相关、低离散度的环境中被消除。

### 不建议的后续
- 不建议在 ETF 上做 BB 参数优化（2.5σ/3σ/window search）——edge 不存在，优化是过拟合
- 不建议 Top-N 搜索——信号高度同步，Top-N 无区分度
- 不建议 market regime filter——这是 E2 内容，且不能解决 edge 不存在的根本问题

### 可探索的方向（非本阶段）
- 个股 BB edge 的横截面离散度归因研究（为什么个股有效而 ETF 无效）
- ETF 上其他策略类型（非均值回归，如动量/波动率）
- 严格 PIT 下的行业轮动（利用 ETF 但非 BB 均值回归）

---

## 8. 输出文件清单

| 文件 | 说明 |
|------|------|
| `results/etf/e1_model1_summary.csv` | Model 1 完整指标 |
| `results/etf/e1_model1_trade_log.csv` | Model 1 每笔交易 |
| `results/etf/e1_model1_equity_curve.csv` | Model 1 权益曲线 |
| `results/etf/e1_model1_yearly_returns.csv` | Model 1 年度收益 |
| `results/etf/e1_model1_daily_panel.csv` | Model 1 日频面板 |
| `results/etf/e1_model2_summary.csv` | Model 2 完整指标 |
| `results/etf/e1_model2_trade_log.csv` | Model 2 每笔交易 |
| `results/etf/e1_model2_equity_curve.csv` | Model 2 权益曲线 |
| `results/etf/e1_model2_yearly_returns.csv` | Model 2 年度收益 |
| `results/etf/e1_model2_daily_panel.csv` | Model 2 日频面板 |
| `results/etf/e1_common_window_comparison.csv` | 三方 Common Window 对比 |
| `results/etf/e1_cluster_exposure.csv` | 聚类暴露日频 |
| `results/etf/e1_final_report.md` | 本报告 |
| `research/etf/e1_model1_backtest.py` | Model 1 引擎 |
| `research/etf/e1_model2_backtest.py` | Model 2 引擎 |
| `research/etf/PHASE_E1_REGISTRY.csv` | E1 预注册冻结 |
