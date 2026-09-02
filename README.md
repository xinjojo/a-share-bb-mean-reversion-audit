# A股 BB 均值回归策略 · 研究级回测与审计仓库

> 成交额TopN + 布林带(20,2)下轨均值回归 + 5层分批建仓 + 布林上轨止盈 + 标普500ETF(513500)现金管理
> 回测区间：2020-01-02 ~ 2026-08-25 · 全市场 5765 只 A 股 · 7,731,551 行日线
> 本仓库用于外部审计（含 ChatGPT 红队审计），**不含任何真实 Token / 密钥 / 个人账号信息**。

---

## ⚠️ 最终结论（2026-09-02 · Round5.1 结案）

**原始 +354.9% 回测结果因发现同Bar未来信息、ETF执行时序错误以及PIT股票状态/上市时间问题而失效。**

修复全部已知问题后的严格因果版本（STRICT_V2）**未发现稳定、可重复的股票Alpha** —— 评级 **D / No evidence**：

- 股票策略自身（剥离 ETF 现金管理）：STRICT_V2_A（T-1上轨盘中退出）+5.2%、STRICT_V2_B（收盘确认T+1 open退出）+23.4%，**均低于同期直接满仓持有标普500ETF 的 +26.6%**；
- OOS 不稳定：A 的股票腿 Test(2024-2026) = **-11.2%**，B 的股票腿 Train(2020-2023) = **-5.4%**；
- 组合正收益（A +45%、B +74%）来自股票/ETF 动态配置 + 复利交互，而非股票 Alpha。

详细过程见 [REDTEAM_ROUND5_STRICT.md](REDTEAM_ROUND5_STRICT.md) 与 [REDTEAM_ROUND51_STRICT.md](REDTEAM_ROUND51_STRICT.md)。

> **这不等于"均值回归在A股不存在"，也不等于"所有BB类策略无效"**，仅表示当前这个具体策略假设（TopN + BB(20,2) + 分层加仓）没有通过红队验证。后续研究方向见 `REGIME_RESEARCH_PLAN.md`（市场状态 × 超跌程度 → 条件收益矩阵，先研究规律、不先写策略）。

---

## 一、结案状态

- 旧策略参数**已冻结**，禁止继续针对 2020-2026 历史数据调参：Top10 / BB(20,2) / K=3 / max_levels=5 / level_cash=20万。
- 回测不可违反规则见 [BACKTEST_INVARIANTS.md](BACKTEST_INVARIANTS.md)；自动测试见 `tests/test_backtest_invariants.py`（28 项，全部 PASS）。
- 本仓库完整保留研究演化与全部 negative results：BASELINE → Round1..5 → Round5.1 → STRICT_V2 → D/No evidence。

---

## 二、研究演化与关键发现

| 阶段 | 结果 | 结论 |
|---|---|---|
| 原始（K=3 + ETF满仓） | +354.9% | **INVALID**：含同Bar未来信息（当日盘中用当日收盘才确定的上轨止盈）、ETF open 时间倒流、PIT 状态/上市时间问题 |
| Round5 STRICT_V1 | close +52~62%、next_open +84% | 仍含 ETF open 倒流 + listing bug → **作废** |
| Round5.1 STRICT_V2（全部修复） | 组合 A +45.1% / B +74.4%；纯股票 A +5.2% / B +23.4% | **无独立股票 Alpha**：纯股票跑输 ETF buy&hold（+26.6%） |

**每个 bug 如何被发现**：见各轮 REDTEAM 报告。
- P0 同Bar未来信息：`experiment_fast.py:554` high[T] vs bb_upper[T]（含 close[T]）→ 修复后 383%→45-74%
- ETF 时序：`round5_audit.py:110` 单一 etf_trade_px → 事件驱动 ensure_cash_open/rebalance_close
- PIT ST：`prepare_fast:20-25` 快照 name → `pit_st_daily.parquet`（差异 46.6万股票日/683只）
- 上市日：切片首日误当上市日 → 2020 前 60 日候选 0→21.2万（完整交易日历 1990 起）

---

## 三、当前冻结的 STRICT_V2（唯一可交易口径）

买入：T 日收盘后确认信号（Top10 成交额、非ST、上市满60交易日、跌破布林下轨、非跌停）→ **T+1 开盘买入**（100股整数倍，每层20万，最多5层，K=3 共享100万；ETF 于 T+1 开盘筹资）。
退出（两种可交易策略，**不得合并**）：
- **A**：T 日盘中 high 触及 **T-1 收盘已确定**的布林上轨 → 按已知上轨成交（日线近似）
- **B**：T 日收盘确认 close ≥ 上轨 → **T+1 开盘卖出**

费用：佣金 0.025%（最低5元）、印花税 0.1%→0.05%（2023-08-28 前后）、过户费 0.001%、10bp 双腿滑点、T+1、100股、涨跌停/停牌过滤。

---

## 四、复现

```bash
# 1. 全部不变量测试 (28项, 必须 PASS)
python3 tests/test_backtest_invariants.py

# 2. STRICT_V2 (Round5.1 引擎)
python3 -c "
import sys; sys.path.insert(0,'.')
from round51_audit import prepare_v51, run_fast_multi_v51, full_stats
days,D,etf_idx,epx,eopx,enav,fel,off = prepare_v51(limit_down_mode='correct', st_mode='pit')
for mode, tag in [('prev','A'),('close_confirm_next','B')]:
    eq,tr,ac = run_fast_multi_v51(days,D,etf_idx,epx,eopx,enav,fel,off,K=3, exit_bb_mode=mode, open_fill='limit_conservative')
    print(tag, full_stats(eq,tr))
"

# 3. 历史基线 (含未来信息, 仅供对照): experiment_fast.py run_fast_multi
```

---

## 五、数据

- 来源：Tushare Pro（付费方案B）
- `data/combined_daily.parquet`：2020-01-02~2026-08-25，5765只，7,731,551行（open/high/low/close/volume/amount/adj_factor/pre_close；`amount`单位=**千元**）
- `data/raw/stock_basic.parquet`（当前快照 name/list_date/delist_date）、`data/raw/trade_cal_full.parquet`（1990起完整交易日历）、`data/raw/namechange_full.parquet`（PIT ST 源）、`data/pit_st_daily.parquet`（PIT 状态）、`data/etf_513500_merged.parquet`（场内 OHLCV）
- **⚠️ Survivorship bias**：数据为当前快照，2020 后退市股缺失 15 只（`NEED_EXTERNAL_DATA`），**所有结论含 survivorship bias 成分**，详见 AUDIT_GUIDE.md

---

## 六、目录

```
├── README.md                     # 本文件（结案结论）
├── BACKTEST_INVARIANTS.md        # 回测不可违反规则清单
├── REGIME_RESEARCH_PLAN.md       # 下一阶段：市场状态×超跌程度研究设计
├── REDTEAM_ROUND*.md             # 五轮红队审计记录（含 Round5.1）
├── AUDIT_GUIDE.md / CALLCHAIN.md / KLINE_DATA.md
├── round51/                      # STRICT_V2 引擎与运行脚本
├── round5/                       # Round5 反事实实验
├── tests/test_backtest_invariants.py  # 不变量自动测试 (28项)
├── data/                         # PIT ST / 完整日历 / K线分片
└── results/                      # 全部结果 CSV / JSON / PNG（含 negative results）
```

---

## 七、审计状态

已完成 5 轮外部红队审计（Round5 + Round5.1）：
- Round1-2：代码审计 + 六项反事实验证
- Round3-4：统计稳健性（曾误评 A，后被 P0 推翻）
- Round5：P0 同Bar未来信息确认 INVALID；STRICT_V1 首次全部修复 → C
- Round5.1：PIT ST / listing / ETF 时序 / open_fill 修复 → **STRICT_V2 → D / No evidence**

旧 +354.9% 及四轮 A 评级**均已正式归档为 INVALID**。本项目最有价值的部分是 negative result：完整记录了每一个 bug 如何被发现、修复后收益如何变化。
