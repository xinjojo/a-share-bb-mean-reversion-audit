"""Alpha Factory Phase 1 — Universe A 特征构建（PIT 保证）。

输入：
- results/evidence/ml_bb/ml_features_full.parquet (157,469 × 38: 37 特征 + signal_id) [已审计 PIT]
- results/evidence/sigpath/signal_path_20d_wide.parquet (标签与 turnover_rank)
- data/combined_daily.parquet (ret_60d, market breadth)
- data/index_000300/000905/000852.parquet (指数环境)

规则：
- 任何特征 source_date <= signal_date；禁止未来信息。
- 输出 phase1_dataset_full.parquet（signal_id + 特征 + 标签 + censored + entry_role）。
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = "/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat"
REPO = "/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo"
EVID = os.path.join(REPO, "results", "evidence")
sys.path.insert(0, os.path.join(REPO, "src"))

from alpha_factory.phase1 import manifest  # noqa: E402

OUT = os.path.join(EVID, "alpha_factory", "phase1")
os.makedirs(OUT, exist_ok=True)


def load_ml_features() -> pd.DataFrame:
    df = pd.read_parquet(os.path.join(EVID, "ml_bb", "ml_features_full.parquet"))
    assert len(df) == 157469, len(df)
    return df


def load_labels() -> pd.DataFrame:
    wide = pd.read_parquet(os.path.join(EVID, "sigpath", "signal_path_20d_wide.parquet"))
    cols = {
        "signal_id", "ts_code", "signal_date", "entry_role",
        "close_ret_D20", "MAE_D20", "turnover_rank",
    }
    keep = [c for c in cols if c in wide.columns]
    lab = wide[keep].copy()
    lab["signal_date"] = pd.to_datetime(lab["signal_date"]).astype("datetime64[us]")
    return lab


def load_hist() -> pd.DataFrame:
    h = pd.read_parquet(os.path.join(ROOT, "data", "combined_daily.parquet"),
                        columns=["date", "ts_code", "close", "adj_factor", "vol", "amount"])
    h["date"] = pd.to_datetime(h["date"]).astype("datetime64[us]")
    h["close_adj"] = h["close"] * h["adj_factor"]
    return h.sort_values(["ts_code", "date"]).reset_index(drop=True)


def load_index(name: str) -> pd.DataFrame:
    fname = {"300": "000300", "500": "000905", "1000": "000852"}[name]
    p = os.path.join(ROOT, "data", f"index_{fname}.parquet")
    if not os.path.exists(p):
        p = os.path.join(ROOT, "data", "monthly_bb", f"idx_{fname}.parquet")
    df = pd.read_parquet(p)
    dcol = "trade_date" if "trade_date" in df.columns else "date"
    df = df.rename(columns={dcol: "date"})
    df["date"] = pd.to_datetime(df["date"]).astype("datetime64[us]")
    df = df[["date", "close"]].dropna().sort_values("date").reset_index(drop=True)
    df = df.rename(columns={"close": f"idx_{name}_close"})
    for n in (1, 5, 20):
        df[f"csi{name}_ret_{n}"] = df[f"idx_{name}_close"].pct_change(n) * 100
    return df.drop(columns=[f"idx_{name}_close"])


def add_market_breadth(hist: pd.DataFrame, sig_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """每日全市场 BB20/2 上/下轨突破占比（当日 close_adj 相对当日 BB band）。"""
    g = hist.groupby("ts_code", group_keys=False)["close_adj"]
    mid = g.transform(lambda s: s.rolling(20, min_periods=20).mean())
    std = g.transform(lambda s: s.rolling(20, min_periods=20).std(ddof=1))
    hist = hist.assign(bb_mid=mid, bb_std=std)
    hist["bb_up"] = hist["close_adj"] > hist["bb_mid"] + 2 * hist["bb_std"]
    hist["bb_dn"] = hist["close_adj"] < hist["bb_mid"] - 2 * hist["bb_std"]
    daily = hist.groupby("date").agg(
        n_stock=("close_adj", "count"),
        n_up=("bb_up", "sum"),
        n_dn=("bb_dn", "sum"),
    )
    daily["daily_bb_up_ratio"] = daily["n_up"] / daily["n_stock"]
    daily["daily_bb_down_ratio"] = daily["n_dn"] / daily["n_stock"]
    # 当日收盘后才知道当日全市场占比；信号日收盘后可用 → <= signal_date
    daily = daily[["daily_bb_up_ratio", "daily_bb_down_ratio"]].reset_index()
    out = pd.DataFrame({"date": sig_dates})
    out = pd.merge_asof(out.sort_values("date"), daily.sort_values("date"), on="date", direction="backward")
    return out


def main():
    feats = load_ml_features()
    lab = load_labels()
    hist = load_hist()

    feats["signal_date"] = pd.to_datetime(feats["signal_date"]).astype("datetime64[us]")
    sig_dates = pd.DatetimeIndex(feats["signal_date"].unique())
    print("unique signal_dates:", len(sig_dates))

    # ---- 1) ret_60d (per stock, merge_asof <= signal_date)
    hist["ret_60d"] = hist.groupby("ts_code")["close_adj"].pct_change(60) * 100
    ret60 = hist[["ts_code", "date", "ret_60d"]].dropna(subset=["ret_60d"])
    feats = pd.merge_asof(
        feats.sort_values("signal_date"),
        ret60.sort_values("date"),
        left_on="signal_date", right_on="date", by="ts_code", direction="backward",
    ).drop(columns=["date"])

    # ---- 2) turnover_rank (从 combined_daily 重算：signal_date 当日全市场 amount 百分位，
    #          PIT 且全覆盖；SIGPATH 原列缺失 59.4%，弃用但保留列名口径)
    tr = hist.groupby("date", group_keys=False)["amount"].rank(pct=True).reset_index()
    tr.columns = ["idx", "turnover_rank_raw"]
    hist_tr = hist[["ts_code", "date"]].copy()
    hist_tr["turnover_rank"] = tr["turnover_rank_raw"]
    hist_tr = hist_tr.dropna(subset=["turnover_rank"])
    feats = pd.merge_asof(
        feats.sort_values("signal_date"),
        hist_tr.sort_values("date"),
        left_on="signal_date", right_on="date", by="ts_code", direction="backward",
    ).drop(columns=["date"])

    # ---- 3) index context
    idx = None
    for name in ("300", "500", "1000"):
        part = load_index(name)
        idx = part if idx is None else idx.merge(part, on="date", how="outer")
    idx = idx.sort_values("date")
    idx_dates = pd.DataFrame({"signal_date": sig_dates})
    idx_map = pd.merge_asof(idx_dates, idx, left_on="signal_date", right_on="date", direction="backward").drop(columns=["date"])
    new_idx_cols = [c for c in idx_map.columns if c not in feats.columns]
    feats = feats.merge(idx_map[["signal_date"] + new_idx_cols], on="signal_date", how="left")

    # ---- 4) market breadth (<= signal_date)
    brd = add_market_breadth(hist, sig_dates)
    brd = brd.rename(columns={"date": "signal_date"})
    feats = feats.merge(brd, on="signal_date", how="left")

    # ---- 5) labels
    feats = feats.merge(lab[["signal_id", "close_ret_D20", "MAE_D20", "entry_role"]], on="signal_id", how="left")
    feats["censored"] = feats["close_ret_D20"].isna() | feats["MAE_D20"].isna()

    # ---- final column set from frozen manifest (可用 44)
    available = [f["feature_name"] for f in manifest.BASE_FEATURES if f["source"] != "UNAVAILABLE"]
    missing = [c for c in available if c not in feats.columns]
    if missing:
        raise ValueError(f"missing features in dataset: {missing}")

    # ---- 6) 补入 SIGPATH 可用的 signal_day_* / bb_mid/lower/upper/BB_width 输入字段
    wide_all = pd.read_parquet(os.path.join(EVID, "sigpath", "signal_path_20d_wide.parquet"),
                               columns=["signal_id"] + [c for c in (
                                   "signal_day_open", "signal_day_high", "signal_day_low", "signal_day_close",
                                   "signal_day_amount", "signal_day_volume", "signal_day_adj_factor",
                                   "bb_mid", "bb_lower", "bb_upper", "BB_width",
                               )])
    extra_sig = [c for c in wide_all.columns if c != "signal_id"]
    feats = feats.merge(wide_all, on="signal_id", how="left")
    available += [c for c in extra_sig if c not in available]

    keep = ["signal_id", "ts_code", "signal_date", "entry_role"] + available + [
        "close_ret_D20", "MAE_D20", "censored",
    ]
    out = feats[keep].copy()
    out.to_parquet(os.path.join(OUT, "phase1_dataset_full.parquet"), index=False)

    # ---- missing-rate report per feature
    miss = {c: float(out[c].isna().mean()) for c in available}
    print("rows:", len(out), "| censored:", int(out["censored"].sum()))
    print("missing rates:")
    for c, m in sorted(miss.items(), key=lambda x: -x[1]):
        if m > 0.005:
            print(f"  {c}: {m:.3%}")
    return out


if __name__ == "__main__":
    main()
