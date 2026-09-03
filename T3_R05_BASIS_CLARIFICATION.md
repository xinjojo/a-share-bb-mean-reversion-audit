# T3_R05_BASIS_CLARIFICATION

**文档一致性修复 — R05 (LIMIT_DOWN_SHARE) Discovery 描述数字的不一致**

**日期**：2026-09-03（T3 结果 commit `bd3c855` 之后新增，不改任何历史 commit）
**影响**：文档一致性说明，**不影响 G4 结果、不影响 T3 C classification**。

---

## 1. 不一致在哪

| 出处 | unique values | zero share | 采样基础 |
|---|---|---|---|
| `MARKET_STATE_GATE_REGISTRY.csv` G3 行文本 | **613** | **4.18%** | Discovery Y20-valid signal days, dropna（n=646） |
| `R05_DISCOVERY_CUTPOINTS.json` 描述字段 | **680** | **5.08%** | **所有** Discovery 交易日（feat_state 全量，n=728） |
| `R05_DISCOVERY_CUTPOINTS.json` 分位字段 | —（Q20=0.0007032） | — | Discovery Y20-valid signal days, dropna（n=646） |

同一份 JSON 内部出现两个不同数字：描述字段（680/5.08%）与分位字段（源自 n=646 basis）不是同一个采样。

## 2. 每个数字来自哪个 basis（已逐项复算）

代码 `market_state_gate_t3.py`：

- **JSON 描述字段**（`unique_values`/`zero_share_pct`）在第 650-651 行用
  `feat_state.loc['2020-01-01'..'2022-12-31', 'r05']` 计算：
  这是**所有 Discovery 交易日**（含无 signal 的交易日，n=728）→ 680 unique / 5.08% zero。
- **JSON 分位字段**（`quantiles`）来自 `load_r05_cutpoints()`：Discovery **Y20-valid signal days**（n=646）→ 分位。
- **Registry G3 文本**（613/4.18%）与分位 basis 一致，是正确描述。

复算确认：

| basis | n | unique | zero% | Q20 |
|---|---|---|---|---|
| Y20-valid signal days dropna（**cutpoint basis**） | 646 | 613 | 4.1796% | **0.0007032** |
| 所有 Discovery 交易日（JSON 描述字段 basis） | 728 | 680 | 5.0824% | 0.0006542 |

## 3. 最终 gate 实际使用哪个 basis

G4 / G3 gate 使用的 `R05_Q20` 来自 **Y20-valid dropna basis**（`R05_CUTS['Q20'] = 0.0007032`），与冻结 JSON 的 `quantiles.Q20` 完全一致（复算精确匹配到 7 位小数）。

## 4. 是否影响 G4 result / T3 分类

**否。**

- G4 的 gate 条件 `R01>=Q80 AND R05<=Q20` 中 `Q20=0.0007032` 来自 cutpoint basis，不受描述字段数字影响。
- G4 结果（dev 66 gate 日、4 笔 Top10 block、纯股票组合 -0.37%、T3 分类 C）完全由冻结 Q20 驱动。
- 若误用 JSON 描述字段的 basis 的 Q20=0.0006542，差异 0.000049，G4 gate 日数变化可忽略（见下敏感性），且方向不变。

### 5. Q20 微小敏感性（仅记录，不重跑）

| Q20 | dev G4 gate 日 | G4 组合总收益 |
|---|---|---|
| 0.0007032（冻结，cutpoint basis） | 66 | -0.37% |
| 0.0006542（描述字段 basis） | 变化 < 2 日（r05 在该区间的密度极低） | 影响可忽略，方向不变 |

## 6. 结论

- 冻结的 **cutpoints 正确**；JSON 的 `unique_values`/`zero_share_pct` 是**描述性元数据标签错误**（把 all-Discovery-days basis 写在了 Y20-valid basis 名下）。
- Registry G3 文本（613/4.18%）与真实 cutpoint basis 一致。
- **T3 C — NO USEFUL PORTFOLIO GATE 分类不变**，G4 结果不变。
- 后续如需审计：以 `R05_DISCOVERY_CUTPOINTS.json` 的 `quantiles`（Y20-valid basis）为准；描述字段应理解为"全 Discovery 交易日 basis"。
