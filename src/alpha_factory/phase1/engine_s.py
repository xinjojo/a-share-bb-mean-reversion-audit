"""Alpha Factory Phase 1 — Engine S：Symbolic 因子求值 + 筛选 + FDR + Val/Test。

冻结规则（manifest.py SYMBOLIC_300）：
- discovery 2020-2022: coverage>=70%, |RankIC|>=0.02 或 |Q5-Q1 median|>=1pp, 3年中>=2年方向一致
- 全家族统一 BH-FDR q=0.10（discovery 全部 300 请求）
- validation 2023 / test 2024 单次评估，2024 后不再修改
"""
from __future__ import annotations

import csv
import os
import sys

import numpy as np
import pandas as pd

REPO = "/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo"
sys.path.insert(0, os.path.join(REPO, "src"))

from alpha_factory import dsl  # noqa: E402
from alpha_factory.phase1 import manifest  # noqa: E402

DATASET = os.path.join(REPO, "results", "evidence", "alpha_factory", "phase1", "phase1_dataset_full.parquet")
MANIFEST_CSV = os.path.join(REPO, "research", "alpha_factory", "phase1", "PHASE1_SYMBOLIC_MANIFEST.csv")
OUT = os.path.join(REPO, "results", "evidence", "alpha_factory", "phase1")
os.makedirs(OUT, exist_ok=True)


# ---------------------------------------------------------------- evaluation
def eval_expr(node: dsl.Node, df: pd.DataFrame) -> pd.Series:
    """在信号面板上求值；cs_rank/cs_zscore 按 signal_date 横截面。"""
    if node.kind == "input":
        return df[node.name].astype(float)
    name, args = node.name, node.args
    if name == "abs":
        return eval_expr(args[0], df).abs()
    if name == "sign":
        return np.sign(eval_expr(args[0], df))
    if name == "cs_rank":
        x = eval_expr(args[0], df)
        return x.groupby(df["signal_date"]).rank(pct=True)
    if name == "cs_zscore":
        x = eval_expr(args[0], df)
        g = x.groupby(df["signal_date"])
        mu, sd = g.transform("mean"), g.transform("std")
        return (x - mu) / sd.replace(0, np.nan)
    a, b = eval_expr(args[0], df), eval_expr(args[1], df)
    if name == "ratio":
        return a / b.replace(0, np.nan)
    if name == "diff":
        return a - b
    if name == "interaction":
        return a * b
    if name == "min":
        return np.minimum(a, b)
    if name == "max":
        return np.maximum(a, b)
    raise ValueError(f"unsupported op {name}")


def daily_rank_ic(factor: pd.Series, y: pd.Series, dates: pd.Series) -> tuple[float, int, list[float]]:
    """按 signal_date 聚合的 daily Spearman RankIC；返回 (mean_ic, n_days, ic_list)。"""
    tmp = pd.DataFrame({"d": dates, "f": factor, "y": y}).dropna()
    ics = []
    for _, g in tmp.groupby("d"):
        if g["f"].nunique() < 5 or g["y"].nunique() < 5:
            continue
        ic = g["f"].corr(g["y"], method="spearman")
        if np.isfinite(ic):
            ics.append(ic)
    if not ics:
        return np.nan, 0, []
    return float(np.mean(ics)), len(ics), ics


def daily_q5q1_median(factor: pd.Series, y: pd.Series, dates: pd.Series) -> float:
    """按日分 5 桶，Q5-Q1 的未来 D20 中位数差（百分点）。"""
    tmp = pd.DataFrame({"d": dates, "f": factor, "y": y}).dropna()
    vals = []
    for _, g in tmp.groupby("d"):
        if g["f"].nunique() < 10:
            continue
        q = pd.qcut(g["f"].rank(method="first"), 5, labels=False)
        g = g.assign(q=q)
        med = g.groupby("q")["y"].median()
        if med.shape[0] == 5:
            vals.append(med.loc[4] - med.loc[0])
    return float(np.mean(vals)) if vals else np.nan


def bh_fdr(pvals: np.ndarray, q: float = 0.10) -> np.ndarray:
    """Benjamini-Hochberg：返回 boolean 数组（是否通过）。"""
    p = np.asarray(pvals, dtype=float)
    n = len(p)
    order = np.argsort(p)
    ranked = p[order]
    thresh = q * np.arange(1, n + 1) / n
    passed = ranked <= thresh
    # 最大 k 满足 p_(k) <= q*k/n
    k = np.where(passed)[0]
    cutoff = int(k.max()) if len(k) else -1
    keep = np.zeros(n, dtype=bool)
    keep[order[: cutoff + 1]] = True
    return keep


def main():
    df = pd.read_parquet(DATASET)
    df = df[~df["censored"]].copy()
    df["year"] = df["signal_date"].dt.year

    rows = list(csv.DictReader(open(MANIFEST_CSV, encoding="utf-8")))
    assert len(rows) == 300

    disc = df[df["year"] <= 2022]
    val = df[df["year"] == 2023]
    test = df[df["year"] == 2024]

    recs, pvals = [], []
    for i, r in enumerate(rows):
        try:
            node = dsl.parse(r["formula"])
            dsl.validate(node, universe="A")
        except Exception:
            recs.append({**r, "eval_status": "EVAL_ERROR"})
            continue
        f = eval_expr(node, df)
        cov = float(f.notna().mean())
        # discovery
        disc_ic, disc_days, disc_ics = daily_rank_ic(f[disc.index], df.loc[disc.index, "close_ret_D20"], df.loc[disc.index, "signal_date"])
        q5q1 = daily_q5q1_median(f[disc.index], df.loc[disc.index, "close_ret_D20"], df.loc[disc.index, "signal_date"])
        # yearly direction 2020/2021/2022
        yr_ic = {}
        for y in (2020, 2021, 2022):
            m = (df["year"] == y)
            if m.sum() >= 50:
                ic, _, _ = daily_rank_ic(f[m], df.loc[m, "close_ret_D20"], df.loc[m, "signal_date"])
                yr_ic[y] = ic
        signs = [np.sign(v) for v in yr_ic.values() if np.isfinite(v)]
        n_same_sign = max(signs.count(1.0), signs.count(-1.0)) if signs else 0
        # p-value: daily IC t-test（cluster by date 已内建在 daily IC 上）
        p = np.nan
        if len(disc_ics) >= 5:
            arr = np.asarray(disc_ics)
            t = np.mean(arr) / (np.std(arr, ddof=1) / np.sqrt(len(arr))) if np.std(arr, ddof=1) > 0 else 0
            # Student t 双尾近似（df 大时正态近似足够）
            from math import erf, sqrt
            p = 2 * (1 - 0.5 * (1 + erf(abs(t) / sqrt(2)))) if np.isfinite(t) else np.nan
        pass_disc = (cov >= 0.7) and np.isfinite(disc_ic) and (
            (abs(disc_ic) >= 0.02) or (np.isfinite(q5q1) and abs(q5q1) >= 1.0)
        ) and n_same_sign >= 2
        recs.append({**r, "eval_status": "OK", "coverage": cov,
                     "disc_ic": disc_ic, "disc_days": disc_days, "q5q1_disc": q5q1,
                     "ic_2020": yr_ic.get(2020), "ic_2021": yr_ic.get(2021), "ic_2022": yr_ic.get(2022),
                     "n_same_sign": n_same_sign, "disc_pval": p, "pass_discovery": pass_disc})
        pvals.append(p if np.isfinite(p) else 1.0)

    out = pd.DataFrame(recs)
    # FDR on discovery p-values (仅对 eval OK 且有 p 的)
    ok = out["eval_status"] == "OK"
    pv = np.where(ok, np.where(pd.isna(out["disc_pval"]), 1.0, out["disc_pval"]), 1.0)
    out["fdr_pass"] = False
    out.loc[ok, "fdr_pass"] = bh_fdr(pv[ok], q=0.10)

    # validation / test（仅对 discovery+FDR 通过的）
    for ph, sub in (("val", val), ("test", test)):
        ic_col, q_col = f"{ph}_ic", f"{ph}_q5q1"
        out[ic_col], out[q_col] = np.nan, np.nan
        mask = out["pass_discovery"] & out["fdr_pass"]
        for i in out.index[mask]:
            g = sub.index
            if len(g) < 50:
                continue
            fv = f_eval_series(df, out.loc[i, "formula"], g)
            ic, _, _ = daily_rank_ic(fv, sub["close_ret_D20"], sub["signal_date"])
            out.loc[i, ic_col] = ic
            out.loc[i, q_col] = daily_q5q1_median(fv, sub["close_ret_D20"], sub["signal_date"])

    out.to_csv(os.path.join(OUT, "phase1_symbolic_all.csv"), index=False)
    keep = out[out["pass_discovery"] & out["fdr_pass"]].copy()
    keep.to_csv(os.path.join(OUT, "phase1_symbolic_fdr.csv"), index=False)
    print("symbolic evaluated:", len(out), "| discovery pass:", int(out["pass_discovery"].sum()),
          "| FDR pass:", int((out["pass_discovery"] & out["fdr_pass"]).sum()))


def f_eval_series(df: pd.DataFrame, formula: str, idx: pd.Index) -> pd.Series:
    node = dsl.parse(formula)
    return eval_expr(node, df).loc[idx]


if __name__ == "__main__":
    main()
