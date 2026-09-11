# UNIVERSE B — SMOKE ML PIPELINE (Phase 0, SMOKE_ONLY)

**本页所有数字仅证明管道可运行，不代表任何研究结论。**

- train rows: 2826740（2020-2022，purged label_end<=2022-12-31）
- validation subset rows: 20000（2023 前 20000 行）
- features used: 84
- fit time: 6.15s；total: 13.65s
- prediction shape: (20000,); NaN in pred: 0

结论：SMOKE PASS（管道通）。禁止据此评估模型质量。