"""Alpha Factory Phase 1 — 7 张图（matplotlib，存 PNG 到 results/evidence/alpha_factory/phase1/charts/）。"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO = "/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo"
OUT = os.path.join(REPO, "results", "evidence", "alpha_factory", "phase1")
CH = os.path.join(OUT, "charts")
os.makedirs(CH, exist_ok=True)


def load(name):
    p = os.path.join(OUT, name)
    return pd.read_csv(p) if os.path.exists(p) else None


def main():
    # 1) symbolic funnel
    sym_all = load("phase1_symbolic_all.csv")
    sym_fdr = load("phase1_symbolic_fdr.csv")
    if sym_all is not None:
        fig, ax = plt.subplots(figsize=(7, 4))
        n = len(sym_all)
        labels = ["300 requested", "eval OK", "discovery pass", "FDR pass"]
        vals = [n, int(sym_all["eval_ok"].sum()) if "eval_ok" in sym_all else n,
                int((sym_all.get("disc_pass", pd.Series(0))).sum()),
                len(sym_fdr) if sym_fdr is not None else 0]
        ax.bar(labels, vals, color=["#9aa5b1", "#8bc8ea", "#7cb3a0", "#d4a06a"])
        for i, v in enumerate(vals):
            ax.text(i, v + 1, str(v), ha="center")
        ax.set_ylabel("count")
        ax.set_title("Symbolic funnel (300 requests)")
        fig.tight_layout()
        fig.savefig(os.path.join(CH, "symbolic_funnel.png"), dpi=140)
        plt.close(fig)

    # 2) ML model comparison: val vs test RankIC per family/target
    m = load("phase1_ml_model_summary.csv")
    if m is not None:
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
        for ax, t in zip(axes, ("Y_RETURN", "Y_RISK")):
            sub = m[m.target == t]
            fams = ["ridge", "rf", "xgb", "lgb"]
            x = np.arange(4)
            w = 0.22
            for j, v in enumerate(["SMALL", "MEDIUM", "REGULARIZED"]):
                vals = [sub[(sub.family == f) & (sub.variant == v)]["val_ic"].iloc[0] if len(sub[(sub.family == f) & (sub.variant == v)]) else np.nan for f in fams]
                ax.bar(x + (j - 1) * w, vals, w, label=v)
            ax.axhline(0, color="grey", lw=0.8)
            ax.set_xticks(x, fams)
            ax.set_title(f"{t} 2023 val RankIC")
            ax.legend(fontsize=8)
        fig.suptitle("ML model comparison (val 2023)")
        fig.tight_layout()
        fig.savefig(os.path.join(CH, "ml_model_comparison.png"), dpi=140)
        plt.close(fig)

    # 3) yearly RankIC
    yd = load("phase1_ml_yearly.csv")
    if yd is not None:
        fig, ax = plt.subplots(figsize=(7, 4))
        for t, c in (("Y_RETURN", "#d4a06a"), ("Y_RISK", "#7cb3a0")):
            s = yd[yd.target == t]
            ax.plot(s["year"], s["rank_ic"], marker="o", label=f"{t} ({s['family'].iloc[0]}/{s['variant'].iloc[0]})", color=c)
        ax.axhline(0, color="grey", lw=0.8)
        ax.set_xlabel("year"); ax.set_ylabel("RankIC / Spearman")
        ax.set_title("Yearly OOS stability (selected models)")
        ax.legend()
        fig.tight_layout()
        fig.savefig(os.path.join(CH, "yearly_rankic.png"), dpi=140)
        plt.close(fig)

    # 4) ML prediction quintile returns (Y_RETURN, 2023/2024) — 用 summary 的 q 字段
    if m is not None:
        fig, ax = plt.subplots(figsize=(7, 4))
        for t, c in (("Y_RETURN", "#8bc8ea"),):
            sub = m[m.target == t]
            x = ["SMALL", "MEDIUM", "REGULARIZED"]
            ax.plot(x, sub[sub.family == "ridge"]["test_q5_q1_med"].values, marker="o", label="ridge", color=c)
            ax.plot(x, sub[sub.family == "rf"]["test_q5_q1_med"].values, marker="s", label="rf", color="#7cb3a0")
            ax.plot(x, sub[sub.family == "xgb"]["test_q5_q1_med"].values, marker="^", label="xgb", color="#d4a06a")
        ax.axhline(0, color="grey", lw=0.8)
        ax.set_title("Y_RETURN 2024 OOS Q5-Q1 D20 median spread")
        ax.legend()
        fig.tight_layout()
        fig.savefig(os.path.join(CH, "quintile_returns.png"), dpi=140)
        plt.close(fig)

    # 5) permutation null vs real
    null = load("phase1_permutation_null.csv")
    if null is not None and m is not None:
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.hist(null["val_ic"], bins=30, color="#c9d4dd", alpha=0.9)
        real = float(m[(m.target == "Y_RETURN")]["val_ic"].max())
        ax.axvline(real, color="#d05a5a", lw=2, label=f"real val RankIC={real:.4f}")
        ax.set_xlabel("val RankIC (permuted labels)"); ax.set_ylabel("count")
        ax.set_title("Label permutation null vs real Y_RETURN")
        ax.legend()
        fig.tight_layout()
        fig.savefig(os.path.join(CH, "permutation_null.png"), dpi=140)
        plt.close(fig)

    # 6) feature importance
    imp = load("phase1_ml_feature_importance.csv")
    if imp is not None:
        for t in ("Y_RETURN", "Y_RISK"):
            s = imp[imp.target == t].sort_values("importance", ascending=False).head(15)
            fig, ax = plt.subplots(figsize=(8, 5))
            ax.barh(s["feature"][::-1], s["importance"][::-1], color="#8bc8ea")
            ax.set_title(f"Top15 importance ({t})")
            fig.tight_layout()
            fig.savefig(os.path.join(CH, f"feature_importance_{t}.png"), dpi=140)
            plt.close(fig)

    # 7) Engine S vs Engine M vs baseline (val/test RankIC)
    inc = load("phase1_incremental_ml.csv")
    if inc is not None:
        fig, ax = plt.subplots(figsize=(8, 4.5))
        base = inc[inc.model == "baseline_linear"]
        full = inc[inc.model == "full_ml"]
        x = np.arange(2)
        w = 0.3
        for j, t in enumerate(["Y_RETURN", "Y_RISK"]):
            bv = base[base.target == t]["val_ic"].iloc[0]
            bf = base[base.target == t]["test_ic"].iloc[0]
            fv = full[full.target == t]["val_ic"].iloc[0]
            ft = full[full.target == t]["test_ic"].iloc[0]
            ax.bar(x[0] + j * 2, bv, w, label=f"{t} baseline val", color="#c9d4dd")
            ax.bar(x[0] + j * 2 + w, fv, w, label=f"{t} full val", color="#8bc8ea")
            ax.bar(x[1] + j * 2, bf, w, color="#d4a06a")
            ax.bar(x[1] + j * 2 + w, ft, w, color="#7cb3a0")
        ax.set_xticks([0.15, 2.15, 4.15], ["val 2023", "test 2024", ""])
        ax.legend(fontsize=8, ncol=2)
        ax.set_title("Incremental: baseline linear vs full ML")
        fig.tight_layout()
        fig.savefig(os.path.join(CH, "engine_comparison.png"), dpi=140)
        plt.close(fig)

    print("charts saved to", CH)


if __name__ == "__main__":
    main()
