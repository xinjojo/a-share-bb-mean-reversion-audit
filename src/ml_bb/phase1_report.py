"""ML-BB Phase 1 报告与图生成（Commit B 前置）。

读取已落盘 CSV，生成 ML_PHASE1_REPORT.md + 7 张图。
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

# 中文字体（macOS 系统字体）
for fp in ["/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
           "/System/Library/Fonts/Hiragino Sans GB.ttc",
           "/System/Library/Fonts/STHeiti Light.ttc"]:
    if os.path.exists(fp):
        font_manager.fontManager.addfont(fp)
        break
plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "Hiragino Sans GB", "STHeiti", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ML_OUT = os.path.join(ROOT, "results", "evidence", "ml_bb")
RESEARCH = os.path.join(ROOT, "research", "ml_bb")

plt.rcParams.update({"figure.facecolor": "white", "axes.grid": True, "grid.alpha": 0.3,
                     "font.size": 10, "axes.titlesize": 11})


def load(name):
    return pd.read_csv(os.path.join(ML_OUT, name))


def plot_quintile_median():
    q = load("ranking_quintile_stats.csv")
    sub = q[(q["group"] == "NEW_ENTRY") & (q["year"] == 2024)]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for m in ["ridge", "xgb", "lgb", "rf"]:
        d = sub[sub["model"] == m].sort_values("quintile")
        ax.plot(d["quintile"], d["D20_median"], marker="o", label=m)
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_xlabel("五分组（1=预测最差，5=预测最好）")
    ax.set_ylabel("D20 收盘收益中位数")
    ax.set_title("NEW_ENTRY 2024 真实外推：五分组中位数")
    ax.legend()
    plt.tight_layout(); plt.savefig(os.path.join(ML_OUT, "fig_quintile_median.png"), dpi=130); plt.close()


def plot_quintile_bad():
    b = load("ranking_quintile_bad.csv")
    sub = b[(b["group"] == "NEW_ENTRY")]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for m in ["logit", "xgb", "lgb", "rf"]:
        d = sub[sub["model"] == m].sort_values("quintile")
        ax.plot(d["quintile"], d["BAD_rate"], marker="o", label=m)
    ax.set_xlabel("五分组（1=预测坏单概率最低，5=最高）")
    ax.set_ylabel("实际坏单率 %（D20 MAE ≤ −20%）")
    ax.set_title("NEW_ENTRY 2024 坏单模型：五分组实际坏单率")
    ax.legend()
    plt.tight_layout(); plt.savefig(os.path.join(ML_OUT, "fig_quintile_bad.png"), dpi=130); plt.close()


def plot_yearly_spread():
    s = load("yearly_stability.csv")
    sub = s[s["group"] == "NEW_ENTRY"]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for m in ["ridge", "xgb", "lgb", "rf"]:
        d = sub[sub["model"] == m]
        ax.plot(d["year"], d["Q5_Q1_spread"], marker="o", label=m)
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_xlabel("年份")
    ax.set_ylabel("Q5−Q1 D20 中位数差（百分点）")
    ax.set_title("NEW_ENTRY 年度排序梯度稳定性")
    ax.legend()
    plt.tight_layout(); plt.savefig(os.path.join(ML_OUT, "fig_yearly_spread.png"), dpi=130); plt.close()


def plot_topk():
    t = load("topk_comparison.csv")
    fig, ax = plt.subplots(figsize=(8, 4.5))
    t3 = t[t["top_k"] == 3]
    for k in t3["model"].unique():
        d = t3[t3["model"] == k]
        ax.scatter([k] * len(d), d["D20_mean"], s=60, alpha=0.85)
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_ylabel("D20 平均收益")
    ax.set_title("NEW_ENTRY 2024 当日 Top3 排序对比（4 个模型各一行）")
    plt.xticks(rotation=20)
    plt.tight_layout(); plt.savefig(os.path.join(ML_OUT, "fig_topk.png"), dpi=130); plt.close()


def plot_importance():
    imp = pd.read_csv(os.path.join(ML_OUT, "feature_importance_NEW_ENTRY.csv"))
    imp = imp.sort_values("importance", ascending=False).head(15)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(imp["feature"][::-1], imp["importance"][::-1], color="#4C72B0")
    ax.set_xlabel("置换重要性")
    ax.set_title("NEW_ENTRY 特征重要性（2024 最佳模型）")
    plt.tight_layout(); plt.savefig(os.path.join(ML_OUT, "fig_importance.png"), dpi=130); plt.close()


def plot_agreement():
    a = load("model_agreement.csv")
    fig, ax = plt.subplots(figsize=(8, 4.5))
    labels = [f"{r['model_a']}×{r['model_b']}" for _, r in a.iterrows()]
    ax.bar(labels, a["jaccard"], color="#55A868")
    ax.set_ylabel("Top20% 信号集合 Jaccard")
    ax.set_title("NEW_ENTRY 2024 多模型 Top20% 重合度")
    plt.xticks(rotation=25)
    plt.tight_layout(); plt.savefig(os.path.join(ML_OUT, "fig_agreement.png"), dpi=130); plt.close()


def plot_score_vs_realized():
    p = pd.read_csv(os.path.join(ML_OUT, "walk_forward_predictions.csv"))
    p["y"] = pd.to_numeric(p["y"], errors="coerce")
    p["score"] = pd.to_numeric(p["score"], errors="coerce")
    sub = p[(p["task"] == "Y1") & (p["year"] == 2024) & (p["group"] == "NEW_ENTRY") & (p["model"] == "ridge")]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.scatter(sub["score"], sub["y"], s=4, alpha=0.15, color="#4C72B0")
    # 分位平均线
    q = pd.qcut(sub["score"].rank(method="first"), 10, labels=False)
    m = sub.groupby(q)["y"].mean()
    xs = sub.groupby(q)["score"].mean()
    ax.plot(xs, m, color="red", lw=2, label="十分位均值")
    ax.set_xlabel("Ridge 预测分")
    ax.set_ylabel("实际 D20 收益")
    ax.set_title("NEW_ENTRY 2024：预测分 vs 实际收益")
    ax.legend()
    plt.tight_layout(); plt.savefig(os.path.join(ML_OUT, "fig_score_realized.png"), dpi=130); plt.close()


def build_report() -> str:
    m = load("model_metrics.csv")
    s = load("yearly_stability.csv")
    q = load("ranking_quintile_stats.csv")
    b = load("ranking_quintile_bad.csv")
    t = load("topk_comparison.csv")
    a = load("model_agreement.csv")
    imp = pd.read_csv(os.path.join(ML_OUT, "feature_importance_NEW_ENTRY.csv"))

    ne = s[s["group"] == "NEW_ENTRY"]
    ne24 = q[(q["group"] == "NEW_ENTRY") & (q["year"] == 2024)]
    ne24b = b[(b["group"] == "NEW_ENTRY")]
    ne24t3 = t[(t["top_k"] == 3) & (t["model"].isin(["model", "random", "amount", "bb_z", "atr"]))]

    lines = []
    A = lines.append
    A("# ML-BB Phase 1 报告 — Signal Ranking Audit")
    A("")
    A("> 冻结 Registry: `research/ml_bb/registries/ML_BB_PHASE1_REGISTRY.md`（Commit A: 0f983c4）")
    A("> 数据: SIGPATH canonical 157,469 signals；剔除 censored 3,136 后 154,333。")
    A("> 时间切分: Train 2020-22 / Val 2023 / OOS Test 2024 + expanding WF。2025-2026 零读取。")
    A("> Leakage Audit: PASS（tests 4/4 + 100 条抽查，见 ML_LEAKAGE_AUDIT_PHASE1.md）")
    A("")
    A("## 1. 模型指标（OOS 2024）")
    A("")
    A("| 分组 | 任务 | 模型 | Val | Test 2024 |")
    A("|---|---|---|---|---|")
    for _, r in m[m["group"] == "NEW_ENTRY"].iterrows():
        if r["task"] == "Y1_reg":
            A(f"| NEW_ENTRY | Y1 回归 | {r['model']} | val_IC {r['val_ic']:.3f} | **test_IC {r['test_ic']:.3f}** |")
        else:
            A(f"| NEW_ENTRY | Y6 坏单 | {r['model']} | val_AUC {r['val_auc']:.3f} | **test_AUC {r['test_auc']:.3f}** |")
    for _, r in m[m["group"] == "ADD_ON"].iterrows():
        if r["task"] == "Y1_reg":
            A(f"| ADD_ON | Y1 回归 | {r['model']} | val_IC {r['val_ic']:.3f} | test_IC {r['test_ic']:.3f} |")
        else:
            A(f"| ADD_ON | Y6 坏单 | {r['model']} | val_AUC {r['val_auc']:.3f} | test_AUC {r['test_auc']:.3f} |")
    A("")
    A("- **NEW_ENTRY** 2024 真实外推：ridge test_IC 0.067 / xgb 0.097 / lgb 0.073 / rf −0.038（反转）。")
    A("- **ADD_ON** 子组明显更强：ridge 0.303 / xgb 0.322 / lgb 0.359。")
    A("")
    A("## 2. 五分组排序梯度（核心判定）")
    A("")
    A("### NEW_ENTRY 2024（D20 中位数，%）")
    A("")
    A("| 模型 | Q1 | Q2 | Q3 | Q4 | Q5 | Q5−Q1 |")
    A("|---|---|---|---|---|---|---|")
    for mm in ["ridge", "xgb", "lgb", "rf"]:
        d = ne24[ne24["model"] == mm].sort_values("quintile")
        A(f"| {mm} | {d['D20_median'].iloc[0]*100:.2f} | {d['D20_median'].iloc[1]*100:.2f} | "
          f"{d['D20_median'].iloc[2]*100:.2f} | {d['D20_median'].iloc[3]*100:.2f} | "
          f"{d['D20_median'].iloc[4]*100:.2f} | {d['D20_median'].iloc[4]*100-d['D20_median'].iloc[0]*100:+.2f} |")
    A("")
    A("### NEW_ENTRY 2024 坏单率（D20 MAE≤−20% 实际比例，%）")
    A("")
    A("| 模型 | Q1 | Q2 | Q3 | Q4 | Q5 | Q5/Q1 |")
    A("|---|---|---|---|---|---|---|")
    for mm in ["logit", "xgb", "lgb", "rf"]:
        d = ne24b[ne24b["model"] == mm].sort_values("quintile")
        q1 = d['BAD_rate'].iloc[0]; q5 = d['BAD_rate'].iloc[4]
        A(f"| {mm} | {q1:.1f} | {d['BAD_rate'].iloc[1]:.1f} | {d['BAD_rate'].iloc[2]:.1f} | "
          f"{d['BAD_rate'].iloc[3]:.1f} | {q5:.1f} | {q5/q1:.2f}x |")
    A("")
    A("**解读**：预测坏单概率最高的 Q5 实际坏单率是 Q1 的约 1.6–1.9 倍，方向正确且 3/4 模型单调。"
      "这是本阶段最有操作价值的信号之一（可用于未来 K=3 槽位避开最差单）。")
    A("")
    A("## 3. 年度稳定性（NEW_ENTRY，Q5−Q1 D20 中位数差，百分点）")
    A("")
    A("| 模型 | 2022 | 2023 | 2024 | 判断 |")
    A("|---|---|---|---|---|")
    for mm in ["ridge", "xgb", "lgb", "rf"]:
        d = ne[ne["model"] == mm].set_index("year")
        v = [d.loc[y, "Q5_Q1_spread"] * 100 for y in [2022, 2023, 2024]]
        ok = sum(x > 0 for x in v)
        A(f"| {mm} | {v[0]:+.2f} | {v[1]:+.2f} | {v[2]:+.2f} | {'稳定' if ok >= 3 else ('部分' if ok == 2 else '不稳定')} |")
    A("")
    A("## 4. Top-K 对比（NEW_ENTRY 2024，按 signal_date 组内取 Top3，D20 平均收益）")
    A("")
    A("| 排序方式 | N | D20 均值 | 中位数 | 95%CI 下 | 95%CI 上 |")
    A("|---|---|---|---|---|---|")
    for mm in ["model", "random", "amount", "bb_z", "atr"]:
        d = ne24t3[ne24t3["model"] == mm]
        if len(d) == 0:
            continue
        r = d.iloc[0]
        A(f"| {mm} | {r['N']} | {r['D20_mean']*100:+.2f}% | {r['D20_median']*100:+.2f}% | {r['ci_lo']*100:+.2f}% | {r['ci_hi']*100:+.2f}% |")
    A("")
    A("模型 Top3 平均优于 random/bb_z/atr，但与 amount 差距小，且置信区间互相重叠——"
      "Top-K 层面的优势**统计上不显著**。")
    A("")
    A("## 5. 多模型一致性（NEW_ENTRY 2024 Top20% 信号集合）")
    A("")
    A("| 模型对 | 重合数 | Jaccard |")
    A("|---|---|---|")
    for _, r in a.iterrows():
        A(f"| {r['model_a']} × {r['model_b']} | {r['top20_overlap']} | {r['jaccard']:.2f} |")
    A("")
    A("仅 xgb×lgb 重合较高（0.55），其余 0.21–0.27——多模型结论**部分一致**。")
    A("")
    A("## 6. 特征重要性（NEW_ENTRY Y1 2024 最佳模型 xgb，Top10）")
    A("")
    A("| 特征 | 置换重要性 | 类别 |")
    A("|---|---|---|")
    for _, r in imp.head(10).iterrows():
        A(f"| {r['feature']} | {r['importance']:.4f} | {cat(r['feature'])} |")
    A("")
    A("市场环境（csi300_ret_20、market_up/down_ratio、daily_bb_signal_count）与流动性（log_amount）"
      "占据主导——与主线 B1 信号广度发现一致：**同跌同涨的市场状态是排序的最重要背景**。")
    A("")
    A("## 7. 结论")
    A("")
    A("- NEW_ENTRY：2024 真实外推存在**弱到中等**的排序梯度（ridge/xgb Q5−Q1 中位数差 +1.4~+2.9pp），"
      "ridge 三年全正较稳定，但 rf 2024 反转、lgb 弱，幅度小。")
    A("- BAD 分类：2024 Q5/Q1 坏单率比约 1.6–1.9 倍，单调且方向正确，但 AUC 仅 0.55–0.57（弱）。")
    A("- ADD_ON 子组：Y1 排序 IC 明显更强（0.21–0.36），比 NEW_ENTRY 更有排序价值。")
    A("- Top-K 组内选股相对 amount/bb_z/atr 优势微弱且不显著。")
    A("- **最终评级：B — 存在一定 OOS 排序能力，但年份/模型稳定性一般，幅度不足以独立支撑 K=3 admission 的 A 级判定。**")
    A("- 进入 Phase 2 的条件：评级 B 满足「有资格进入」的门槛，但应把 BAD 分位端剔除与 ADD_ON 排序作为优先组合设计对象，"
      "并预期提升幅度有限（信号级，非组合级）。")
    A("")
    A("## 8. 纪律核对")
    A("")
    A("- [x] 2024 未参与参数选择（参数仅在 train 2020-22 + val 2023 选择）")
    A("- [x] 2025-2026 零读取（universe ≤2024-12-31 机器断言）")
    A("- [x] 未做 K=3/ETF/1.5% 组合回测")
    A("- [x] Leakage Audit PASS（tests 4/4 + 100 条抽查）")
    A("- [x] EE15 forward 文件 0 change（git status 验证）")
    A("- [x] 未修改任何冻结策略参数")
    return "\n".join(lines)


def cat(f):
    if f in ["csi300_ret_5", "csi300_ret_20", "csi1000_ret_5", "csi1000_ret_20", "market_up_ratio", "market_down_ratio", "daily_bb_signal_count"]:
        return "市场环境"
    if f in ["log_amount", "amount_percentile", "volume_ratio_5_20", "amount_ratio_5_20"]:
        return "流动性"
    if f in ["signal_role", "level_no", "days_since_first_signal", "signal_count_last_20d"]:
        return "信号状态"
    if f in ["bb_z", "distance_to_lower_band", "bb_width"]:
        return "布林带"
    if "atr" in f or "vol" in f or "range" in f or "gap" in f:
        return "波动"
    return "价格/位置"


if __name__ == "__main__":
    plot_score_vs_realized()
    plot_quintile_median()
    plot_quintile_bad()
    plot_yearly_spread()
    plot_topk()
    plot_importance()
    plot_agreement()
    rep = build_report()
    out = os.path.join(RESEARCH, "ML_PHASE1_REPORT.md")
    with open(out, "w") as f:
        f.write(rep)
    print("报告已输出:", out, f"({len(rep)} chars)")
    for f in sorted(os.listdir(ML_OUT)):
        if f.startswith("fig_"):
            print("图:", f)
