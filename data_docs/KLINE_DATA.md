# K 线数据说明（A股日线 2020-01-02 ~ 2026-08-31）

> 数据来源：Tushare Pro（付费方案B，`pro.daily` + `pro.adj_factor`）
> 用途：外部审计核实回测产出。**本目录只含公开市场行情数据，不含任何个人/账户信息。**

## 一、文件

| 文件 | 内容 | 大小 |
|---|---|---|
| `2020.parquet` ~ `2026.parquet` | 全A股日线，按年份拆分 | 各 23~33 MB |
| `etf_513500_merged.parquet` | 标普500ETF(513500) 日线（基金净值+价格） | 78 KB |
| `merge_kline.py` | 合并分片 → `combined_daily.parquet` | - |

> 单文件均 <100MB，规避 GitHub 单文件限制。合并后共 **7,731,551 行 / 5725 只股票**（2020-01-02~2026-08-31）。

## 二、Schema（列说明）

| 列 | 说明 |
|---|---|
| `date` | 交易日（拆分为片时已去掉，合并时由分片拼接补回，格式 YYYY-MM-DD） |
| `ts_code` | 股票代码，如 `600519.SH`（.SH上交所 / .SZ深交所 / .BJ北交所） |
| `open / high / low / close` | 原始（不复权）OHLC 价格，单位：元 |
| `vol` | 成交量（手） |
| `amount` | 成交额，**单位：千元**（Tushare daily 原始单位） |
| `pre_close` | 前收盘价（未复权） |
| `adj_factor` | 复权因子（Tushare adj_factor，后复权用 `close × adj_factor`） |
| `is_limit_down` | 是否跌停（`close ≤ pre_close × 0.905`，主板10%近似，布尔） |
| `is_red` | 当日是否上涨（`close > pre_close`，布尔） |

## 三、关键口径（务必与回测一致）

1. **复权**：回测中信号与收益均使用**后复权价** `close_adj = close × adj_factor`、`high_adj = high × adj_factor`，保证分红送转后价格连续；实际成交现金流用未复权实际价。
2. **成交额**：`amount` 单位为**千元**，回测排序直接用 Tushare 原始值。
3. **跌停**：`is_limit_down = close ≤ pre_close × 0.905`（10%主板近似；ST 为 5%、创业板/科创板 20%、北交所 30%，完整规则见 `AUDIT_GUIDE.md` 跌停章节）。
4. **停牌**：无当日行 = 停牌日；回测中停牌不交易、持仓按最后已知收盘价估值。

## 四、合并方法

```python
python3 data/kline/merge_kline.py   # 在仓库根目录执行
# 输出 combined_daily.parquet（7,731,551 行）
```

## 五、已知局限（如实声明）

- **幸存者偏差**：数据为 Tushare 当前快照回填，**已退市股票缺失**（约15只2020年后退市股不在其中）。历史回测中成交额TopN选股可能因此遗漏退市股——本仓库 README/AUDIT_GUIDE 已明确标注该偏差。
- `is_limit_down` 为统一 9.5% 阈值近似，未按 ST/创业板/科创板分市场精确判定（主引擎支持 `limit_down_mode`，审计 Round2 已验证修正后影响为+10.2pp，偏保守方向）。
- 不含实时数据、不含分钟级数据；回测为日线级别，止盈/加仓为日线近似（APPROXIMATION）。

## 六、抽查验证建议

审计方可随机抽查若干股票/日期，核对：
1. `close × adj_factor` 与后复权价连续（除权除息日不跳变）；
2. `amount` 与行情软件当日成交额一致（注意单位：原始Tushare为千元）；
3. 涨跌停日 `is_limit_down` 与当日 pct_chg 对应。
