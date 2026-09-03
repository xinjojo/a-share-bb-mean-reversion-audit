# PHASE P4.1 — MARGINAL ADMISSION / CAPACITY SHADOW-PRICE AUDIT

**状态：DEVELOPMENT DIAGNOSTIC（WAITING EXTERNAL AUDIT，未写入 README CURRENT TRUTH）**

## 研究问题

解除 K=3（A1: K=999）后 signal capture 上升（76→123 笔），但组合从 +30.30% 崩到 −0.23%。
本轮区分四种机制：

- **H1**：边际新增信号本身更差（intrinsically worse）
- **H2**：信号相似，但在更差的组合/资金状态下入场
- **H3**：信号保留独立 edge，但共享资金/路径稀释毁掉组合价值
- **H4**：以上组合

## 红线执行

- 2020–2024 Development only；2025–2026 Confirmation **CLOSED**，全程未触碰。
- 无新 predictor / 无 ranking / 无 ATR / 无 gate / 无 stop / 无 exit 修改 / 无 K/layer/capital scan /
  无 threshold / 无优化 / 无 ML / 无 composite。
- 完全复用 P4 frozen 引擎（amount-top10、PURE STOCK、1M/200k/5层、10bp、STRICT_C_EXECUTABLE_TICK），
  只跑 A0（K=3）与 A1（K=999）。A0 parity 精确断言。

## 预注册

- Registry：`research/portfolio/registries/MARGINAL_ADMISSION_P41_REGISTRY.csv`
- SHA256：`6efc564f4cee1ba094ed3ef0510e48acb882c6ded0b388b8a353924cc3d6efed`
- Commit：`c6c2865f4c2d20b05a8b312390f8e4c7caa9b2c7`（P4.1-A，push 于任何 outcome 之前）

## A0 parity（硬性）

```
[PARITY A0] OK=True total=30.295094 n=76 pnl=302950.9379
```

与 P4 A0 / P3 B0 / 原 frozen G0 精确一致。

## 交易分组（primary key = (ts_code, entry_date)）

| 组 | n | 说明 |
|---|---|---|
| COMMON | 65 | A0 ∩ A1 同 key 交易 |
| A0_ONLY | 11 | A0 有、A1 没有 |
| A1_ONLY | 58 | A1 有、A0 没有（解除 K 后边际新增） |

ts_code 级：common 43 / A0_only 1 / A1_only 12。

## 独立 episode 覆盖率（frozen SECONDARY V2A，按 (signal_date, ts_code) 精确 join）

| arch | n | covered | coverage% |
|---|---|---|---|
| A0 | 76 | 53 | 69.7% |
| A1 | 123 | 80 | 65.0% |

| 组 | n | covered | cov% | ind_mean | ind_median | ind_win | PF |
|---|---|---|---|---|---|---|---|
| COMMON (A0/A1) | 65 | 48 | 73.8% | +4.11% | +4.10% | 79.2% | 3.17 |
| A0_ONLY | 11 | 5 | 45.5% | −1.97% | −4.04% | 40.0% | 0.61 |
| A1_ONLY | 58 | 32 | 55.2% | +3.28% | +6.29% | 68.8% | 2.00 |

**独立质量维度**：A1_ONLY 整体仍为正（mean +3.28%、win 68.8%、PF 2.00），略弱于 COMMON
（+4.11%、79.2%、3.17），A0_ONLY 独立质量最差（−1.97%、40%、0.61，但覆盖仅 45.5%）。

## Event-day 差异与 bootstrap（L=21, B=2000）

| 组 | event-days | mean | median | win |
|---|---|---|---|---|
| COMMON | 45 | +4.33% | +3.77% | 80.0% |
| A1_ONLY | 31 | +3.27% | +6.43% | 67.7% |
| A0_ONLY | 5 | −1.97% | −4.04% | 40.0% |

A1_ONLY 减 COMMON（event-day mean）：point = **−1.06pp**，bootstrap CI = **[−3.59, +1.73]**，
pct_positive = 23.1%。CI 跨 0 → **独立质量的边际恶化统计上不显著**，但方向为负。

## A1_ONLY 实际组合 PnL（与独立质量严格分开）

| n | sum_pnl | mean_pnl | median_pnl | win | mean_hold | mean_levels |
|---|---|---|---|---|---|---|
| 58 | **−118,609.52** | −2,044.99 | +397.51 | 62.1% | 42.1 | 1.66 |

**独立质量为正（+3.28%）但实际组合 PnL 为负（−118,610）**——这是 H3 的直接证据：
独立 edge 存在，但共享资金/路径下的实现被毁掉。但深挖后（见下）H1 也部分成立。

## A1_ONLY 深亏集中（temporal concentration）

按年：2020 +58,607 / 2021 −27,018 / 2022 −31,943 / **2023 −119,072** / 2024 +817。
top5 信号日占 13.8%、top10 占 22.4%。

最差 8 笔（含独立 episode 对照）：

| ts_code | sig_date | levels | hold | actual pnl | ind_ret | ind MAE |
|---|---|---|---|---|---|---|
| 002714.SZ | 2021-05-24 | 3 | 86 | −120,999 | **−18.72%** | −54.6% |
| 300750.SZ | 2023-09-08 | 5 | 101 | −81,966 | **−18.00%** | −36.9% |
| 603259.SH | 2022-07-27 | 4 | 51 | −54,887 | −6.55% | −28.3% |
| 000625.SZ | 2021-11-16 | 4 | 111 | −50,375 | **−22.23%** | −50.6% |
| 000063.SZ | 2023-08-07 | 2 | 129 | −47,284 | NO_EXACT | — |
| 601318.SH | 2021-04-15 | 2 | 123 | −44,237 | NO_EXACT | — |
| 601012.SH | 2022-03-29 | 1 | 42 | −42,371 | −12.75% | −24.3% |
| 601012.SH | 2023-03-16 | 3 | 68 | −33,946 | NO_EXACT | — |

**关键**：4 笔 < −50k 合计 −308,226，其余 54 笔合计 +189,616，净 −118,610 —— **深亏高度集中在
少数 deep-MAE 长持仓**。其中 002714/300750/000625 三笔的**独立 episode return 为 −18%~−22%、
MAE −37%~−55%**——这些**本来就被 MAE 深度标记为坏信号**（H1 成立：边际信号中含独立也差的
deep-MAE 长持仓）。但其余覆盖的 A1_ONLY 独立整体为正（+3.28%）→ 不全是 H1。

## COMMON matched 资本稀释（65 笔同 key 对比）

| metric | value |
|---|---|
| COMMON A0 pnl | +183,442.60 |
| COMMON A1 pnl | +116,326.54 |
| **COMMON delta** | **−67,116.06** |
| mean delta_pnl | −1,032.55 |
| median delta_pnl | 0.00 |
| mean delta_levels | −0.446 |
| same_exit_share | 100% |
| same_levels_share | 61.5% |

**同一批 65 笔交易**，在 A1 中因资金被更多持仓分散，deep-add 减少：深亏者少亏
（300014.SZ 5层 −281,649→−199,049；002475.SZ 3层→1层 −128,563→−58,659；000858.SZ 5层→2层
−54,013→+15,506），但赢家也被稀释（601012.SH 2层→1层 +49,916→+1,436；300122.SZ 2层
+82,452→+34,561）。**净效应 −67,116 = 赢家稀释损失 > 深亏减少收益**。

## PnL bridge（精确闭合）

| 分量 | 值 |
|---|---|
| A0 stock pnl | +302,950.94 |
| COMMON A0 pnl | +183,442.60 |
| COMMON A1 pnl | +116,326.54 |
| COMMON delta | −67,116.06 |
| A0_ONLY pnl | +119,508.34 |
| A1_ONLY pnl | −118,609.52 |
| A1 stock pnl（重算） | −2,282.99 |
| **residual** | **0.00** |

residual = 0 精确闭合，P0 检查通过。

## MAE / holding burden

| 组 | deep-MAE rate (<−20%) | mean MAE | mean hold | mean levels | total pnl |
|---|---|---|---|---|---|
| COMMON | 18.8% | −12.09% | 34.7d | 1.72 | +116,327 |
| A1_ONLY | **40.6%** | −15.18% | 42.1d | 1.66 | −118,610 |
| A0_ONLY | 40.0% | −19.72% | 34.8d | 1.55 | +119,508 |

**A1_ONLY 深 MAE 率 40.6% ≈ COMMON 的 2.2 倍**，持仓也更长（42.1d vs 34.7d）。A1_ONLY
实际亏损的来源是少数 deep-MAE 长持仓（与 P4 结论一致：deep-MAE 长持仓是组合核心负担）。

## 市场状态 overlay（描述性，R01/F02 RET60、R05/LIMIT_DOWN，均已冻结验证）

| 组 | n | R01 mean | R01 P75 | R05>0 share |
|---|---|---|---|---|
| COMMON | 65 | +1.81 | +5.32 | 95.4% |
| A1_ONLY | 58 | +0.96 | +4.66 | 94.8% |
| A0_ONLY | 11 | +0.73 | +6.32 | 90.9% |

三组 R01 分布接近（边际交易未系统性集中在已验证的坏市场状态），R05 均 >90% 有跌停。
**R01 不解释 A1_ONLY 的失败**——更支持机制在"信号个体质量 + 路径稀释"而非市场状态。

## 容量影子价格（历史诊断量，非预测）

| 指标 | 值 |
|---|---|
| PnL delta (A1−A0) | −305,233.92 |
| 额外成交笔数 | +47 |
| 额外 slot-days | +2,057 |
| 额外 capital-days | +16,937,795 |
| 每额外一笔的影子 PnL | −6,494 |
| 每额外 slot-day | −148.4 |
| 每额外 capital-day | −0.018 |

**解除 K 的边际成本：每多接 1 笔交易 ≈ −6,494 元、每多占 1 slot-day ≈ −148 元。**
这是历史路径下的影子成本，不是未来收益预测。

## 机制分类：**C — BOTH**

- **H1 成立（部分）**：A1_ONLY 独立质量略低（+3.28% vs +4.11%）、深 MAE 率 40.6%（2.2×）、
  最差几笔（002714/300750/000625）独立 return −18%~−22%、MAE −37%~−55%，本来就被坏信号标记。
- **H3 成立（部分）**：A1_ONLY 覆盖样本整体独立为正（+3.28%、win 68.8%），但实际组合 PnL
  为 −118,610；COMMON 同一批 65 笔在 A1 中因资金分散少赚 67,116（赢家稀释 > 深亏减少）。
- **H2**：A1_ONLY 进入时点无系统性的更差资金状态证据（A0_ONLY 反而最差），且 R01/R05 无差异。

**措辞边界**：A1_ONLY 实际 PnL 很差 ≠ "边际信号没有 alpha"。独立 episode 证据显示其整体
仍为正（+3.28%），其组合失败 = 少数 deep-MAE 长持仓（独立也差）的路径放大 + 赢家被共享
资金稀释。**P4 结论保持不变**：K=3 是实际容量瓶颈，但在当前历史样本与组合规则下表现为
保护性 admission constraint（排掉独立也差的 deep-MAE 长持仓边际信号）。

## 2025–2026 Confirmation

**仍然 CLOSED。** P4.1 是纯诊断，不打开 Confirmation。

## 交付物清单

- `research/portfolio/marginal_admission_p41.py`
- `research/portfolio/registries/MARGINAL_ADMISSION_P41_REGISTRY.csv` + `.sha256`
- `results/evidence/p41/p41_{trade_groups,independent_coverage,independent_quality,
  independent_eventday,independent_bootstrap,admission_state,marginal_rank,congestion,
  common_matched,common_matched_summary,pnl_bridge,a1only_actual,temporal_concentration,
  market_state_overlay,mae_holding,capacity_shadow}.csv`
- `results/evidence/p41/p41_summary.json`
