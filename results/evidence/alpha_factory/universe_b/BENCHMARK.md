# UNIVERSE B — BENCHMARK (M2 Pro / 10 核 / 16GB RAM)

| part     | scope     |    rows |   cols |   discover_s |   read_s |      peak_rss_mb |
|:---------|:----------|--------:|-------:|-------------:|---------:|-----------------:|
| panel    | year=2020 |  942308 |     20 |            0 |     0.06 | 425872           |
| panel    | all       | 5558740 |     20 |            0 |     0.22 |      1.91021e+06 |
| features | year=2020 |  936269 |     86 |            0 |     0.19 |      2.77506e+06 |
| features | all       | 5540613 |     86 |            0 |     3.81 |      5.94306e+06 |
| labels   | all       | 5540613 |     18 |            0 |     0.56 |      5.94306e+06 |

说明：Pandas 并行读取 parquet（pyarrow）；peak_rss 为进程峰值常驻内存。
结论：若全量 ~6.5M 行×80 列可在 30s 内读入、峰值 <8GB，则 Pandas 足够 Phase 1；若 >60s 或内存吃紧，转 Polars（惰性计算）或 DuckDB（SQL 下推）。