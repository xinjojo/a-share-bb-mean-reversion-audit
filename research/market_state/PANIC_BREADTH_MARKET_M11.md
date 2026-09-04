# PHASE M1.1 — EXTERNAL-PROTOCOL RECONCILIATION (PANIC-BREADTH → MARKET REBOUND)

**DEVELOPMENT DIAGNOSTIC（WAITING EXTERNAL AUDIT）** — restores external frozen protocol

- Registry: `research/market_state/registries/PANIC_BREADTH_MARKET_M11_PROTOCOL_REGISTRY.csv`
- Registry SHA256: `bf10c7498d6e19d5a360ff654ef2da153424144f14961d56c869938b8b93f5b3`
- Prereg commit: `852635a` (M1.1-A)；Governance: M1.1-G `8c66b21`（M1 标记 EXPLORATORY PROTOCOL-DEVIATED，M1=B 与 ETF YES withdrawn as final）
- Sample: 2020–2024（deployable 2021–2024）；2025–2026 CLOSED；无 portfolio/ETF run；无参数扫描

## 1. Protocol bridge（M1 → M1.1 修正）

| # | 外部冻结协议 | M1 实际 | M1.1 |
|---|---|---|---|
| D1 | PRIMARY = FWD5 | FWD20 | FWD5 restored |
| D2 | horizons 1/3/5/10/20 | 5/10/20/40 | 1/3/5/10/20（FWD40 不进 classification）|
| D3 | continuous = EXPANDING_BREADTH_RANK01 | raw Spearman + full-sample Q1-Q5 | EXPANDING_BREADTH_RANK01 |
| D4 | conditional = expanding rank + MARKET_RET_T | panic dummy | expanding rank + MARKET_RET_T（panic-dummy 保留为 secondary descriptive）|
| D5 | yearly 2021–2024 ≥3/4 | registry 2020–2024 ≥3/5 | 2021–2024 ≥3/4 |
| D6 | cluster-first robustness | missing | clusters merged, first-day only |
| D7 | FWD5 tail + future-5d drawdown | missing | both present |
| D8 | benchmark hierarchy official-first | not executed | official checked (000985 absent) → PIT equal-weight fallback recorded |

## 2. Primary market series

**PIT_EQUAL_WEIGHT_FALLBACK**。原因：仓库仅含官方 000300（沪深300）/000905（中证500）/000852（中证1000），**均非全市场覆盖宽基**；中证全指（000985）不在 data/。按冻结 fallback 定义重建：每日冻结合法 universe（listed≥60d & non-PIT-ST & BB20 warmup 非 NaN，与 B1 universe_size 同构造）的 equal-weight close-to-close 收益；universe_size 逐日 parity 断言通过。M1 原 all-A equal-weight（含 ST）不满足 fallback 定义，已替换。

## 3. Breadth state

PANIC80 与 P7 **exact parity：188 / 1,110 signal days**（expanding 80th percentile、date<T only、252 前交易日）。EXPANDING_BREADTH_RANK01 可用 903 天；deployable sample（FWD5 + rank 均非 NA）= **899 天（2021–2024；panic 187 / normal 712）**。2020 无 deployable panic（252 日 warmup）。

## 4. PRIMARY FWD5（deployable 2021–2024）

| | panic (n=187) | normal (n=712) |
|---|---|---|
| mean | **+0.326%** | +0.051% |
| median | +0.539% | +0.008% |
| win | 56.15% | 50.14% |
| P10 / P90 | −3.87% / +4.07% | −3.59% / +3.46% |

**delta = +0.275pp**（point 正，幅度温和）

- HAC（NW maxlags=10）：b=+0.275pp，SE 0.294，**CI [−0.300, +0.851]**（跨 0）；statsmodels parity ✓
- Calendar bootstrap（L=21, B=2000, seed=0）：mean +0.290 / median +0.296，**CI [−0.277, +0.787]**（跨 0）

## 5. Continuous primary-support（EXPANDING_BREADTH_RANK01）

- OLS slope = **−0.319pp**，CI [−1.473, +0.836]（跨 0）
- Spearman(rank, FWD5) = **+0.0038**（≈0，p=0.91）

**"越恐慌 → 未来 5 天反弹越多"的连续关系不存在**。panic dummy（80th 之上的极端日）有 +0.28pp 点迹象，但非连续单调关系。

## 6. Conditional（FWD5 ~ expanding_rank + MARKET_RET_T）

- b1_rank = −0.213pp，CI [−1.426, +1.000]（跨 0）
- b2_mkt = +0.037（不显著）
- **控制当日市场收益后连续 rank 仍无正增量**（点负）。panic-dummy 版（secondary descriptive）：与 M1 结构相同、不替代 continuous gate。

## 7. Yearly（2021–2024，分母 4）

| year | panic n | normal n | panic mean | normal mean | delta | Spearman(rank) |
|---|---|---|---|---|---|---|
| 2021 | 46 | 186 | +1.159% | +0.413% | **+0.746pp** | +0.135 |
| 2022 | 51 | 176 | −0.214% | −0.124% | **−0.091pp** | −0.062 |
| 2023 | 52 | 186 | +0.269% | +0.023% | **+0.246pp** | −0.023 |
| 2024 | 38 | 164 | +0.122% | −0.139% | **+0.261pp** | −0.038 |

**positive years = 3/4**（2022 为负）

## 8. Cluster-first robustness（SECONDARY）

188 panic 日合并为 **96 个连续 cluster**，每 cluster 仅取首个 panic 日：

- cluster-first mean = **−0.226%** vs normal +0.143% → **delta −0.369pp（负）**；median +0.118%、win 51.04%

**关键发现**：daily primary 的 +0.28pp 优势在"每段恐慌只算第一天"后消失甚至反转。daily 测量的大部分来自 panic 段内连续高广度日的**重复计数**——同一恐慌期内重复的 breadth 日放大了反弹测量，不是独立的逐日信息。

## 9. Horizons（全输出，classification 仅由 FWD5 决定）

| H | panic mean | normal mean | delta | HAC CI |
|---|---|---|---|---|
| 1 | −0.115% | +0.046% | −0.161pp | [−0.382, +0.060] |
| 3 | +0.058% | +0.050% | +0.009pp | [−0.457, +0.474] |
| **5（PRIMARY）** | +0.326% | +0.051% | **+0.275pp** | [−0.300, +0.851] |
| 10 | +0.808% | +0.090% | +0.718pp | [−0.195, +1.631] |
| 20 | +1.218% | +0.535% | +0.684pp | [−0.524, +1.892] |

FWD1 甚至为负；优势主要出现在 5 天以后；所有 CI 跨 0。**不得把 FWD10/20 提升为 primary**。

## 10. Tail（FWD5 + future-5d drawdown）

FWD5：panic P5 −4.78% vs normal −4.99%；panic min −12.35% vs normal −20.19% → **5 天 forward 尾部不更差**。

FUTURE_5D_DRAWDOWN（min close T+1..T+5 / close T − 1）：panic mean **−1.72%** vs normal −1.42%（平均回撤略深 0.30pp）；panic P5 −6.53% vs normal −6.04%；panic min −13.46% vs normal −20.19%（极端 min 反而 panic 浅）。→ **panic 后 5 天平均回撤略深，但无更严重的极端继续下跌尾部**。

## 11. 分类与 ETF gate

**B — NARROW MARKET TRANSLATION**：PANIC FWD5 point>0（+0.275pp）、2021–2024 3/4 年正、tail 无严重恶化；但 HAC/calendar CI 跨 0、continuous slope 为负、conditional 无增量、cluster-first 反转。

**ETF gate = YES（WORTHY OF FUTURE PREREG）**——精确含义：panic 日窄幅正迹象（+0.28pp）值得未来单独预注册一个 broad-market ETF / basket carrier 测试；**当前证据不足以直接构建**（CI 跨 0、无连续关系、cluster-first 反转、2022 为负）。

## 12. Invariants

I1–I15 全部 PASS；M1 结果保留为 exploratory（不删除）；无 portfolio/ETF run；无参数扫描；2025–2026 CLOSED。
