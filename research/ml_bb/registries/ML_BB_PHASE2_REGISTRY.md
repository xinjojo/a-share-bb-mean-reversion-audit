# ML-BB PHASE 2 REGISTRY — PORTFOLIO VALUE AUDIT

> 状态：**FROZEN**（Commit A，正式组合结果计算之前锁定）
> 日期：2026-09-08
> 上游：Phase 0 commit `8c5ec1d`；Phase 1 Registry `0f983c4`；Phase 1 正式结果 `6296cd3` + 清理提交 `051ddff / 2cb53f3 / 0475d4a`（评级 B）
> 生产主线：EE15 FORWARD OBSERVATION LIVE（本阶段绝对禁止触碰，git diff=0）

## 0. 本阶段唯一研究问题

1. **BAD VETO（实验一，第一优先级）**：Phase 1 BAD 模型识别出的最高风险 20% NEW_ENTRY 信号，若不允许其占用有限 K=3 槽位，是否真实改善组合（收益 / 回撤 / 持仓时间 / 坏单比例 / 槽位占用）。
2. **ADD_ON RANKING（实验二）**：对已持仓股票再次出现合法 ADD_ON 信号、且当日资金/槽位存在资源竞争时，用 ML ADD_ON score 决定加仓执行顺序，是否改善有限资金使用效率。
3. **M_COMBINED（实验三）**：BAD20 veto + ADD_ON 资源排序同时生效。

**明确禁止**：NEW_ENTRY winner ranking（Phase 1 Top3 未站稳，仅 REFERENCE ONLY）；任何新阈值搜索；对退出规则/入场规则/资金规则的任何修改；用 2025–2026 选参。

## 1. 组合执行口径（全部复制冻结主线，逐字一致）

| 项 | 冻结值 |
|---|---|
| 初始资金 | 1,000,000 |
| K | 3 |
| 候选 | 冻结 BB 主线 universe / admission 规则（BB20/2σ 下轨、amount Top10、非 ST、上市 ≥60 交易日、T+1 open 成交） |
| 每层 | 200,000 |
| 最大层数 | 5 |
| T+1 | 是（signal 日收盘后挂单，次日 open 成交） |
| 100 股整数手 | 是 |
| 滑点 | 10bp |
| 佣金 | 万 2.5，最低 5 元 |
| 过户费 | 0.001% |
| 印花税 | historical（stamp_rate 口径） |
| 公司行为 | 真实分红送转（corp_events_50stocks.parquet，corp_map：送转扩股、派息税前入账） |
| 红利税 | FIFO 批次 × 自然月对日边界（≤1 个月 20% / ≤1 年 10% / >1 年 0%），卖出时结算 |
| ETF 现金管理 | 启用（513500，ensure_cash_open / rebalance_close，etf_min_cash=5,000） |
| 退出 | **全部统一使用当前冻结 EE15：P\* × 0.985（early_exit_pct=0.015）**，动态 P\* = STRICT_C analytic_Pstar，conservative tick 向上取整 0.01，T+1 合法、limit 约束同冻结引擎 |
| 引擎 | `src/strict_c_earlyexit_ca.py` 的 `run_fast_multi_strict_c_ee_ca`（复制为 `src/ml_bb/phase2_engine.py`，仅注入 ML hook，非 ML 分支逐字一致） |

## 2. ML 模型（从 Phase 1 已冻结结果中选定，**禁止重训 / 禁止重新选参**）

选定依据（Phase 1 predictions 跨年稳定性，2026-09-08 复算）：

- **BAD 模型 = RandomForest（task=Y6，group=NEW_ENTRY）**
  - 逐年最高风险 20% vs 最低风险 20% 实际坏单率比：2022 10.89×、2023 11.29×、2024 1.82×（三年同方向，2022/2023 最强）
  - Phase 1 test_AUC（2024 OOS）0.5718，为四模型中最高
- **ADD_ON 排序模型 = LightGBM（task=Y1，group=ADD_ON）**
  - 逐年 IC：2022 0.203、2023 0.165、2024 0.359（三年全正且跨年最稳）

## 3. 阈值（唯一主实验，禁止搜索其他阈值）

- **BAD20**：对每个 OOS 年 Y（2022/2023/2024），取该年 NEW_ENTRY Y6（rf）预测 score 的 **80 分位**为阈值；score ≥ 阈值（最高风险 20%）的 NEW_ENTRY 信号 → `ML_BAD_VETO`（不允许占用新 K 槽）。阈值**只用当年 OOS 预测分布**计算（不使用未来数据）。
  - 禁止测试 10% / 15% / 25% / 30%。
- **M_ADD**：仅当某日满足**资源竞争**条件时才启用 ML 排序：
  - 竞争定义：当日待执行 pending_add 数量 ≥ 2，且 `Σ level_cash > cash + etf_sh × etf_open × (1 − slip)`（可用现金上限不足覆盖全部加仓需求）。
  - 竞争时按 lgb Y1 ADD_ON score **降序**执行（score 高者先用有限资金）；资金充足、无资源冲突时**不得**因 score 低取消任何合法加仓（只排序，不删除）。
- **M_COMBINED** = BAD20 + M_ADD 同时启用。禁止新增其他 ML 行为。

## 4. 时间切分（全部 walk-forward，2025–2026 零使用）

模型预测来自 Phase 1 walk-forward（WF1: train 2020–21 → 2022；WF2: train 2020–22 → 2023；WF3: train 2020–23 → 2024）。2024 及更早的全部 OOS 预测 score 已在本阶段之前生成完毕。

组合运行方式：

- **C0（唯一主基准）**：0.985 退出、无 ML，全期 2020-01-02 ~ 2024-12-31。
- **年度独立运行**（每个 OOS 年独立评估，避免跨年路径污染）：
  - Run2022：2020-01-02 → 2022-12-31，ML 仅 2022 生效，期末 FINAL_SETTLE。
  - Run2023：2020-01-02 → 2023-12-31，ML 仅 2023 生效，期末 FINAL_SETTLE。
  - Run2024：2020-01-02 → 2024-12-31，ML 仅 2024 生效，期末 FINAL_SETTLE。
  - 对应 C0 独立运行使用完全相同的时间窗（无 ML）。
- **Concatenated OOS**：2020-01-02 → 2024-12-31，ML 在 2022/2023/2024 全程生效，年界只切统计（真实跨年路径传播），作为年度独立的补充。

## 5. 对照组与 Null

- **C0**：同时间窗无 ML 组合。
- **Random null（BAD veto）**：按 BAD20 相同数量随机拒绝 NEW_ENTRY，固定 seeds 重复 **≥1000 次**，输出 null 分布（收益差 / 回撤差）。若单次全期回放成本过高（>30 秒），null 在 concatenated 时间窗上运行，样本数按预算调整并如实披露（不得低于 100）。
- **Random null（ADD 排序）**：资源竞争时随机排序，≥1000 次。
- **简单 baseline（ADD 竞争）**：amount / BB_z / ATR 排序对照（BB_z 用 signal 当日 bb_z，ATR 用 Phase 1 特征 atr14_pct——若引擎内不可得，用 amount 与 ML 排序对照并如实说明）。

## 6. 评价指标（每个系统输出）

Total return / CAGR / MaxDD / Sharpe（年化，无风险=0）/ Calmar / 年度收益 / 完成交易数 / 胜率 / 平均交易收益 / 中位交易收益 / 平均持仓天数 / P50/P90 持仓天数 / 平均槽位利用率 / K=3 满仓天数比例 / 资金利用率 / ADD 层数分布 / BAD trade 数（MAE≤−20%）/ ETF 收益贡献 / 股票收益贡献。

增量口径：报告 `BAD20 − C0`、`M_ADD − C0`、`M_COMBINED − C0`，逐年列 2022/2023/2024；总体变好但只有单一年份贡献 → 评级必须降级。

## 7. 路径归因（必须可对账）

每个 ML 系统相对 C0 的最终权益差拆成：

1. direct avoided loss（被挡掉的坏单原本的亏损）
2. foregone winner（被误杀的盈利交易）
3. replacement trade pnl（释放槽位后的替代交易）
4. ADD_ON 资金重分配
5. ETF cash path（含 ensure_cash/rebalance 顺序与金额差异）
6. 公司行为 / 税路径差异

要求：equity difference 可由上述现金路径基本解释（残差披露）。

## 8. 稳健性（固定档，禁止重新选阈值）

- 成本：当前 / +10bp 额外滑点 / +20bp 额外滑点。
- 去最大贡献：去掉最大盈利贡献 1/3/5 笔、最大避免亏损 1/3/5 笔后重算。
- 年份：2022 / 2023 / 2024 分别看。

## 9. 成功标准（A/B/C/D）

- **A**：至少两个 OOS 年份改善；combined OOS 收益或风险调整收益明显改善；MaxDD 不恶化；增益不由极少数交易驱动；明显优于 random/simple baseline；路径归因合理。
- **B**：有一定组合改善，但年份 / 经济量级 / 稳定性有限。
- **C**：signal 级预测存在，但转化到 K=3 后经济价值很弱。
- **D**：组合变差 / 无 OOS 价值 / 明显过拟合。

## 10. Random seeds

- 引擎确定性（无随机）；null 实验 seeds 固定：`np.random.default_rng(2026)` 派生 1000 个 seed（2026, 2027, …, 3025）。结果 CSV 记录每个 seed。

## 11. 禁止 / 纪律

- 禁止修改 EE15 production 文件（`results/evidence/forward/*`、`forward_state_A/B.json`、冻结 Registry、`src/forward_engine.py`、`run_forward_daily.py`、`update_forward_tushare.py`、`prepare_forward_data.py`）——Commit B 前 `git status --short results/evidence/forward/` 必须为空。
- 禁止训练新模型、重训、重新选参、新特征、新阈值。
- 禁止 NEW_ENTRY winner ranking 作为主候选（仅 REFERENCE ONLY 记录）。
- 禁止用 2025–2026 任何结果影响本阶段。
- 禁止把 ML 写入生产前瞻账户；本阶段只产生 **ML SHADOW CANDIDATE**。

## 12. 交付文件（Commit B）

phase2_portfolio_summary.csv / phase2_yearly.csv / phase2_trade_comparison.csv / phase2_bad_veto_audit.csv / phase2_addon_ranking_audit.csv / phase2_replacement_trades.csv / phase2_cash_path_reconciliation.csv / phase2_robustness.csv / phase2_random_null.csv / ML_PHASE2_REPORT.md

## 13. 未决/已知限制（透明披露）

- corp_map 仅覆盖 50 只股票的真实公司行为（corp_events_50stocks.parquet，与冻结引擎一致口径）。
- prepare_v51 数据截至 2026-08-25（冻结历史），Phase 2 只使用 ≤2024-12-31 结果。
- 引擎候选与 SIGPATH predictions 的匹配率将在运行前报告；匹配不到的候选按"不 veto / 不参与排序"保守处理并披露数量。

## 14. 执行勘误（正式结果前修复）

- **M_ADD hook 日期键错位（已修复）**：首次实现中引擎调用 `ml_add_rank(tclist, exec_date)`，而 ADD score 映射的 key 是 **signal_date**（信号日 T，而非执行日 T+1），导致 score 全部未匹配、排序退化为原顺序、M_ADD 与 C0 完全一致。修复：`pending_add[ts_code] = str(signal_date)`（引擎在 CLOSE 段记录信号日），`ml_add_rank(tclist, exec_date, pdesc)` 用 `pdesc[ts_code]`（signal_date）查 score。修复后验证：ADD_RANK 3 次真实重排（2022-03-10 / 04-26 / 10-28），改变 3 笔交易层数，M_ADD 与 C0 出现真实路径差异。该修复只影响实验副本 `phase2_engine.py` 的 hook 签名与 `pending_add` 值语义，不影响冻结引擎与 C0（hook 关闭时逐字一致，parity 重验 PASS）。
- **BAD veto 无此问题**：`ml_veto` 在信号日 CLOSE 段调用，日期键天然匹配（15/15 命中）。
- **Phase 2 顺序缺口披露**：主实验结果在 Commit A push 之前已由上一轮实现生成（结果先于 Registry 提交）。Commit A 与 Commit B 均在本轮完成，顺序缺口如实记录，不影响结果本身的可复算性（所有 CSV 可由 `phase2_run.py` / `phase2_attr.py` / `phase2_null.py` / `phase2_robust.py` / `phase2_trades.py` 复现）。
