# A股单股布林带均值回归策略 — 审计仓库

本仓库为**独立审计**用途，供审计方（如另一个 AI agent）对回测结果做代码级核验。
策略本身：每交易日取成交额 Top10 的 A 股，买入收盘价跌破布林带下轨（MA20−2σ）的股票，持仓期间盘中触及布林上轨止盈（T+1 后），最多 5 层 × 20% 分批加仓，空仓期买入标普500ETF(513500) 做现金管理。

> ⚠️ **本仓库不含原始数据**（770 万行日线等体积过大）。回测所需数据已本地化，如需数据验证请按 `AUDIT_GUIDE.md` 第 9 节向数据方申请，或先只审代码调用链。

## 快速开始

```bash
pip install -r requirements.txt
python3 etf_live_backtest.py        # 复现最佳策略（Top10 + 5层 + ETF现金管理）
python3 etf_ratio_scan.py           # ETF目标比例扫描
```

**数据文件已全部本地化**（`combined_daily.parquet` 2020-01 ~ 2026-08，Tushare 下载），回测无需联网。数据不在此仓库。

## 仓库结构

```
├── AUDIT_GUIDE.md          ← 【审计入口】完整审计参考材料 + A1~D3 检查清单
├── README.md
├── requirements.txt
├── config/
│   └── config.yaml         ← 参数配置（token 已脱敏为 YOUR_TUSHARE_TOKEN）
├── etf_live_backtest.py    ← 【核心】当前最佳策略引擎（含ETF现金管理）
├── live_backtest.py        ← 无ETF版引擎（同策略核心，Top1/3/5/10扫描）
├── etf_ratio_scan.py       ← ETF目标比例扫描
├── engine/                 ← 早期规则模块（commission/trading_rules/position）
├── data_loader/            ← Tushare/AKShare 数据下载与校验
├── backtest/               ← 早期 VectorBT 尝试
├── analysis/               ← 各类研究脚本（参数扫描/持仓分析/K线工具/时间止损）
└── results/                ← 关键回测结果（CSV）
    ├── trades.csv                 交易明细（39笔轮次）
    ├── equity_curve.csv           账户净值曲线（1611行逐日）
    ├── etf_log.csv                ETF 交易日志
    ├── parameter_scan_etf_ratio.csv   ETF目标比例扫描
    ├── parameter_scan_bollinger.csv   布林参数敏感性
    └── yearly_returns.csv          五基准年度收益
```

## 策略要点（详见 AUDIT_GUIDE.md）

- **选股**：成交额 Top10 池 → 第一只收盘价(后复权) < 布林下轨(20,2) 且非跌停
- **买入**：收盘价成交，20 万/层（账户 100 万，最多 5 层）
- **加仓**：持仓中收盘 < 下轨且非跌停 → 加一层，重算加权平均成本（含费用）
- **止盈**：T+1 后盘中 High(后复权) ≥ 布林上轨 → 全部卖出（成交价=上轨/复权因子）
- **T+1**：当日买入不可卖
- **ETF现金管理**：空仓期买 513500，目标比例 100%
- **费用**：佣金万2.5（最低5元）+ 印花税万5（卖出）+ 过户费万0.1

## 关键结果（2020-01 ~ 2026-08-25）

| 指标 | 数值 |
|---|---|
| 累计收益（含ETF现金管理） | **+226.75%** |
| 年化 / 最大回撤 / Sharpe | +20.3% / -36.74% / 1.16 |
| 交易笔数 / 胜率 | 39 / 82.1% |
| 纯股票（无ETF）对照 | +114.83% / 回撤-16.79% |

**已知近似（审计重点）**：跌停卖不出/涨停买不进未实现；跌停判定用固定 9.5% 阈值未区分板块；历史费用用当前费率（印花税2023年才减半）；复权因子含"截至最新"信息的潜在未来函数风险——详见 `AUDIT_GUIDE.md` 第 4-6 节。
