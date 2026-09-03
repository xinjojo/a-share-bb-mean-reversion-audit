# LARGE_FILES_REPORT.md — 大文件清单（只报告，不迁移 LFS）

审计时间：R0-C 阶段。基于 `git ls-files` 实际字节数（`os.path.getsize`）。

## >100MB
无。

## >50MB（2 个）
| 大小 | 路径 | 说明 |
|---|---|---|
| 69.6MB | `results/evidence/stopA/stop_phaseA_episode_detail.csv.gz` | Stop Phase A 全 episode 明细（压缩） |
| 67.4MB | `results/evidence/fullmarket/fullmarket_episode_metrics.csv` | 全市场 89,046 笔 episode 路径指标 |

## >10MB（11 个）
除上述 2 个外：

| 大小 | 路径 | 说明 |
|---|---|---|
| 35.0MB | `data/kline/2025.parquet` | 原始 K 线分片（审计核实用，设计入库） |
| 32.1MB | `data/kline/2024.parquet` | 同上 |
| 31.9MB | `data/kline/2023.parquet` | 同上 |
| 30.3MB | `data/kline/2022.parquet` | 同上 |
| 27.8MB | `data/kline/2021.parquet` | 同上 |
| 24.4MB | `data/kline/2020.parquet` | 同上 |
| 23.9MB | `data/kline/2026.parquet` | 同上 |
| 23.0MB | `results/evidence/independent/independent_trade_episodes_secondary.csv` | SECONDARY 独立 episode（≈89k） |
| 21.3MB | `archive/invalid/results/drawdown_postexit_per_trade.csv` | 原系统产物（INVALID，保留证据） |

## 处置
- **不迁移 Git LFS**（用户红线：只报告）。
- `data/kline/*.parquet` 为原始数据，已在 `.gitignore` 中 `!data/kline/` 保留，供审计核实。
- 大文件分散在 `results/evidence/`（按 phase 归档）与 `archive/`（证据保留），不放入 `results/current/`（仅含 summary 小文件）。
