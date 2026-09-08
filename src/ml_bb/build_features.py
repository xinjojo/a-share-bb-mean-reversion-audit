"""ML-BB feature builder（Phase 0）。

物理隔离原则（ML_ARCHITECTURE.md 第 2 节）：
- 本模块只能读取 <= signal_date 的数据（信号日及其之前的市场信息）。
- 绝不读取 D1-D20 / 未来 high/low/close / MFE / MAE / exit outcome。
- 输出：feature 表（signal_id + features），signal_id 为唯一键，供 build_dataset 与 labels 按 signal_id 合并。

输入：
- results/evidence/sigpath/signal_path_20d_wide.parquet（信号日快照列，仅取 <=T 的列）
- data/combined_daily.parquet（历史行情，用于 ret_5d / atr_pct 前视窗口特征）

口径：
- ret_5d   = signal_date 前 5 个该股实际交易日 close_adj 收益（pct）
- atr_pct  = 信号日前 20 日 ATR(14) / 当日 close_adj（pct）——使用 ATR14 简化实现
- bb_z     = (close_adj - bb_mid) / ((bb_upper - bb_mid)/2)（信号日 T 收盘，wide 快照）
- 其余特征直接来自 wide 快照（T 日收盘已知量）。
"""
from __future__ import annotations

import os
import sys
from typing import Optional

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # github_repo
NEWCHAT = os.path.dirname(os.path.dirname(ROOT))
sys.path.insert(0, ROOT)

SIGPATH_WIDE = os.path.join(ROOT, "results", "evidence", "sigpath", "signal_path_20d_wide.parquet")
COMBINED = os.path.join(NEWCHAT, "data", "combined_daily.parquet")

# 可从 wide 快照安全提取的列（全部为信号日 T 收盘已知量，<= signal_date）
_WIDE_SAFE = [
    "signal_id", "ts_code", "signal_date", "entry_role",
    "bb_z", "bb_mid", "bb_lower", "bb_upper", "BB_width", "distance_to_lower_band",
    "signal_day_close", "signal_day_amount", "signal_day_adj_factor", "turnover_rank",
]

_FEATURES = [
    "bb_z", "bb_width_pct", "distance_to_lower_band",
    "ret_5d", "atr_pct", "log_amount", "turnover_rank", "entry_role",
]


def _tr_wild_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """TR = max(high-low, |high-prev_close|, |low-prev_close|)；ATR = TR 的 rolling 均值。"""
    prev_close = df["close_adj"].shift(1)
    tr = pd.concat(
        [
            df["high_adj"] - df["low_adj"],
            (df["high_adj"] - prev_close).abs(),
            (df["low_adj"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def build_features(
    wide_path: str = SIGPATH_WIDE,
    combined_path: str = COMBINED,
    sample_signals: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """构建特征表。

    sample_signals: 可选；传入 signal_id 序列时只构建这些信号（smoke 用）。
    """
    wide = pd.read_parquet(wide_path, columns=_WIDE_SAFE)
    if sample_signals is not None:
        wide = wide[wide["signal_id"].isin(set(sample_signals))].copy()
    wide["signal_date"] = pd.to_datetime(wide["signal_date"])

    # ---- 从 wide 快照直接提取的安全特征 ----
    feat = pd.DataFrame({"signal_id": wide["signal_id"]})
    feat["ts_code"] = wide["ts_code"].astype(str)  # 内部 merge 键，最终输出前 drop
    feat["signal_date"] = wide["signal_date"]      # 内部 merge 键，最终输出前 drop
    feat["bb_z"] = wide["bb_z"].astype(float)
    feat["bb_width_pct"] = (wide["BB_width"] / wide["bb_mid"].replace(0, np.nan) * 100).astype(float)
    feat["distance_to_lower_band"] = wide["distance_to_lower_band"].astype(float)
    feat["log_amount"] = np.log(wide["signal_day_amount"].replace(0, np.nan)).astype(float)
    feat["turnover_rank"] = wide["turnover_rank"].astype(float)
    feat["entry_role"] = wide["entry_role"].astype(str)

    # ---- 历史窗口特征（combined_daily，<= signal_date）----
    need = wide[["ts_code", "signal_date"]].drop_duplicates()
    if need.empty:
        return feat

    hist_cols = ["ts_code", "date", "open", "high", "low", "close", "adj_factor"]
    hist = pd.read_parquet(combined_path, columns=hist_cols)
    hist["date"] = pd.to_datetime(hist["date"])
    # 复权 OHLC（与冻结引擎 close_adj=close*adj_factor 同口径）
    for col in ["open", "high", "low", "close"]:
        hist[col + "_adj"] = hist[col] * hist["adj_factor"]

    # 每只股票的历史序列（按 date 排序）
    hist = hist.sort_values(["ts_code", "date"]).reset_index(drop=True)

    # 用 merge_asof：对每个 (ts_code, signal_date)，取 <= signal_date 的最近窗口
    # 先按股票分组计算 rolling 指标，再 merge_asof 到信号日
    grouped = hist.groupby("ts_code", group_keys=False)
    hist["ret_5d"] = grouped["close_adj"].transform(lambda s: s.pct_change(5) * 100)
    hist["atr_pct"] = (
        grouped.apply(lambda g: _tr_wild_atr(g) / g["close_adj"] * 100).reset_index(level=0, drop=True)
    )

    # 每个信号只取 <= signal_date 的最近一条历史行
    # （pandas 3.0 的 merge_asof+by 组合异常，改用分组 searchsorted，语义等价：backward 最近行，绝不取未来行）
    hist_idx = hist[["ts_code", "date", "ret_5d", "atr_pct"]].sort_values(["ts_code", "date"])
    hist_groups = {ts: g for ts, g in hist_idx.groupby("ts_code", sort=True)}

    merged_parts = []
    for ts, g in need.groupby("ts_code", sort=True):
        h = hist_groups.get(ts)
        out = pd.DataFrame(
            {"ts_code": g["ts_code"].values, "signal_date": g["signal_date"].values}
        )
        if h is None or h.empty:
            out["ret_5d"] = np.nan
            out["atr_pct"] = np.nan
        else:
            pos = np.searchsorted(h["date"].values, g["signal_date"].values, side="right") - 1
            valid = pos >= 0
            rows = h.iloc[np.maximum(pos, 0)]
            out["ret_5d"] = np.where(valid, rows["ret_5d"].values, np.nan)
            out["atr_pct"] = np.where(valid, rows["atr_pct"].values, np.nan)
        merged_parts.append(out)
    merged = pd.concat(merged_parts, ignore_index=True)

    feat = feat.merge(
        merged[["ts_code", "signal_date", "ret_5d", "atr_pct"]],
        on=["ts_code", "signal_date"],
        how="left",
    )

    # 最终特征顺序（drop 内部键）
    feat = feat.drop(columns=["ts_code", "signal_date"])
    feat = feat[["signal_id"] + _FEATURES]
    return feat


if __name__ == "__main__":
    f = build_features()
    print("feature 表:", f.shape)
    print(f.head(3).to_string(index=False))
