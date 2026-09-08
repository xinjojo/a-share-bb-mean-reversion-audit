"""ML-BB Phase 1 正式特征构建（Registry 冻结，见 research/ml_bb/registries/ML_BB_PHASE1_REGISTRY.md）。

全部 38 个特征必须满足：来源日期 <= signal_date（signal_date 当时已知）。
物理隔离：本模块只读 <=signal_date 数据；标签由 build_labels 提供，merge 仅通过 signal_id。

输出：results/evidence/ml_bb/ml_signal_dataset_full.parquet（feature + label + 分片键）
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NEWCHAT = os.path.dirname(os.path.dirname(ROOT))
sys.path.insert(0, ROOT)

SIGPATH_WIDE = os.path.join(ROOT, "results", "evidence", "sigpath", "signal_path_20d_wide.parquet")
COMBINED = os.path.join(NEWCHAT, "data", "combined_daily.parquet")
IDX300 = os.path.join(NEWCHAT, "data", "index_000300.parquet")
IDX1000 = os.path.join(NEWCHAT, "data", "index_000852.parquet")
ML_OUT = os.path.join(ROOT, "results", "evidence", "ml_bb")

_WIDE_COLS = [
    "signal_id", "ts_code", "signal_date", "entry_role", "position_episode_id",
    "bb_z", "bb_mid", "bb_lower", "bb_upper", "BB_width", "distance_to_lower_band",
    "signal_day_amount", "signal_day_close", "entry_date",
]

# 冻结特征顺序（与 ML_FEATURE_REGISTRY.csv 一致）
FEATURE_COLS = [
    # A. price/location
    "bb_z", "distance_to_lower_band",
    "distance_ma5", "distance_ma10", "distance_ma20", "distance_ma60",
    "ret_1d", "ret_3d", "ret_5d", "ret_10d", "ret_20d",
    "drawdown_20", "drawdown_60", "distance_52w_high",
    # B. volatility
    "atr14_pct", "realized_vol_10", "realized_vol_20", "bb_width",
    "daily_range_pct", "gap_pct",
    # C. liquidity
    "log_amount", "amount_percentile", "volume_ratio_5_20", "amount_ratio_5_20",
    # D. signal state
    "signal_role", "level_no", "days_since_first_signal", "signal_count_last_20d",
    # E. market context
    "csi300_ret_5", "csi300_ret_20", "csi1000_ret_5", "csi1000_ret_20",
    "market_up_ratio", "market_down_ratio", "daily_bb_signal_count",
]

ROLE_MAP = {"NEW_ENTRY": 0}
ROLE_MAP.update({f"ADD_ON_{i}": i for i in range(1, 5)})


def _load_history() -> pd.DataFrame:
    cols = ["ts_code", "date", "open", "high", "low", "close", "vol", "amount", "adj_factor"]
    h = pd.read_parquet(COMBINED, columns=cols)
    h["date"] = pd.to_datetime(h["date"])
    for c in ["open", "high", "low", "close"]:
        h[c + "_adj"] = h[c] * h["adj_factor"]
    h = h.sort_values(["ts_code", "date"]).reset_index(drop=True)
    return h


def _per_stock_pit_features(hist: pd.DataFrame) -> pd.DataFrame:
    """按股票计算所有 <= 当日已知的滚动特征（向量化, 仅用 past/current 行）。"""
    g = hist.groupby("ts_code", sort=False)

    out = pd.DataFrame({"ts_code": hist["ts_code"], "date": hist["date"]})
    c = hist["close_adj"]

    # 收益
    out["ret_1d"] = g["close_adj"].pct_change(1) * 100
    out["ret_3d"] = g["close_adj"].pct_change(3) * 100
    out["ret_5d"] = g["close_adj"].pct_change(5) * 100
    out["ret_10d"] = g["close_adj"].pct_change(10) * 100
    out["ret_20d"] = g["close_adj"].pct_change(20) * 100

    # MA 距离
    for n, col in [(5, "distance_ma5"), (10, "distance_ma10"), (20, "distance_ma20"), (60, "distance_ma60")]:
        ma = g["close_adj"].transform(lambda s: s.rolling(n, min_periods=n).mean())
        out[col] = (c / ma - 1) * 100

    # drawdown（前 n 日最大回撤）
    def _dd(s, n):
        return (s / s.rolling(n, min_periods=n).max() - 1) * 100
    out["drawdown_20"] = g["close_adj"].transform(lambda s: _dd(s, 20))
    out["drawdown_60"] = g["close_adj"].transform(lambda s: _dd(s, 60))

    # 52w high
    out["distance_52w_high"] = (
        c / g["close_adj"].transform(lambda s: s.rolling(250, min_periods=60).max()) - 1
    ) * 100

    # ATR14 pct
    prev_close = hist["close_adj"].shift(1)
    tr = pd.concat([
        hist["high_adj"] - hist["low_adj"],
        (hist["high_adj"] - prev_close).abs(),
        (hist["low_adj"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr14 = tr.groupby(hist["ts_code"].values).transform(lambda s: s.rolling(14, min_periods=14).mean())
    out["atr14_pct"] = atr14 / c * 100

    # realized vol
    out["realized_vol_10"] = g["close_adj"].transform(lambda s: s.pct_change().rolling(10, min_periods=10).std() * 100)
    out["realized_vol_20"] = g["close_adj"].transform(lambda s: s.pct_change().rolling(20, min_periods=20).std() * 100)

    # 当日振幅与跳空
    out["daily_range_pct"] = (hist["high_adj"] - hist["low_adj"]) / hist["close_adj"] * 100
    out["gap_pct"] = (hist["open_adj"] / hist["close_adj"].shift(1) - 1) * 100

    # 量比
    def _ratio(s, a, b):
        return s.rolling(a, min_periods=a).mean() / s.rolling(b, min_periods=b).mean()
    out["volume_ratio_5_20"] = g["vol"].transform(lambda s: _ratio(s, 5, 20))
    out["amount_ratio_5_20"] = g["amount"].transform(lambda s: _ratio(s, 5, 20))

    return out


def build_full_features(
    wide_path: str = SIGPATH_WIDE,
    combined_path: str = COMBINED,
    sample_signals=None,
) -> pd.DataFrame:
    wide = pd.read_parquet(wide_path, columns=_WIDE_COLS)
    if sample_signals is not None:
        wide = wide[wide["signal_id"].isin(set(sample_signals))].copy()
    wide["signal_date"] = pd.to_datetime(wide["signal_date"])

    # ---- 快照类特征 ----
    feat = pd.DataFrame({"signal_id": wide["signal_id"], "ts_code": wide["ts_code"], "signal_date": wide["signal_date"]})
    feat["bb_z"] = wide["bb_z"].astype(float)
    feat["distance_to_lower_band"] = wide["distance_to_lower_band"].astype(float)
    feat["bb_width"] = wide["BB_width"].astype(float)
    feat["log_amount"] = np.log(wide["signal_day_amount"].replace(0, np.nan)).astype(float)
    feat["signal_role"] = wide["entry_role"].map(ROLE_MAP).astype(int)
    feat["level_no"] = feat["signal_role"]

    # days_since_first_signal：episode 内最早 signal_date
    first = wide.groupby("position_episode_id")["signal_date"].transform("min")
    feat["days_since_first_signal"] = (wide["signal_date"] - first).dt.days

    # signal_count_last_20d：该股前 20 自然日内信号数（用 wide 自身，<=signal_date 保证）
    sc = wide.sort_values("signal_date").copy()
    sc["cnt"] = 1
    # 对每个信号，统计同一股票在 [signal_date-20日, signal_date] 内信号数
    merged = sc[["ts_code", "signal_date", "cnt"]].merge(
        sc[["ts_code", "signal_date"]], on="ts_code", suffixes=("", "_b")
    )
    merged = merged[
        (merged["signal_date"] >= merged["signal_date_b"] - pd.Timedelta(days=20))
        & (merged["signal_date"] <= merged["signal_date_b"])
    ]
    cnt = merged.groupby(["signal_date_b"])["cnt"].sum()
    # 用 (ts_code, signal_date_b) 作为 key——pandas groupby 多列
    cnt = merged.groupby(["ts_code", "signal_date_b"])["cnt"].sum().rename("signal_count_last_20d")
    feat = feat.merge(cnt.reset_index(), left_on=["ts_code", "signal_date"], right_on=["ts_code", "signal_date_b"], how="left")
    feat = feat.drop(columns=["signal_date_b"])
    feat["signal_count_last_20d"] = feat["signal_count_last_20d"].fillna(1).astype(int)

    # ---- 历史窗口特征 ----
    hist = _load_history()
    pit = _per_stock_pit_features(hist)
    hist_groups = {ts: g for ts, g in pit.groupby("ts_code", sort=True)}

    need = wide[["ts_code", "signal_date"]].drop_duplicates()
    parts = []
    for ts, g in need.groupby("ts_code", sort=True):
        h = hist_groups.get(ts)
        out = pd.DataFrame({"ts_code": g["ts_code"].values, "signal_date": g["signal_date"].values})
        if h is None or h.empty:
            for c in FEATURE_COLS:
                if c not in out.columns:
                    out[c] = np.nan
        else:
            pos = np.searchsorted(h["date"].values, g["signal_date"].values, side="right") - 1
            valid = pos >= 0
            row = h.iloc[np.maximum(pos, 0)]
            for c in ["distance_ma5", "distance_ma10", "distance_ma20", "distance_ma60",
                      "ret_1d", "ret_3d", "ret_5d", "ret_10d", "ret_20d",
                      "drawdown_20", "drawdown_60", "distance_52w_high",
                      "atr14_pct", "realized_vol_10", "realized_vol_20",
                      "daily_range_pct", "gap_pct", "volume_ratio_5_20", "amount_ratio_5_20"]:
                out[c] = np.where(valid, row[c].values, np.nan)
        parts.append(out)
    pit_joined = pd.concat(parts, ignore_index=True)
    feat = feat.merge(pit_joined, on=["ts_code", "signal_date"], how="left")

    # ---- 市场横截面与指数 ----
    # 全市场 amount 百分位 / 涨跌占比（T 日横截面, 当日收盘已知）
    day_stat = _market_daily_stats(hist)
    feat = feat.merge(day_stat, on="signal_date", how="left")

    # 指数收益
    for path, p5, p20 in [(IDX300, "csi300_ret_5", "csi300_ret_20"), (IDX1000, "csi1000_ret_5", "csi1000_ret_20")]:
        idx = pd.read_parquet(path)
        idx["date"] = pd.to_datetime(idx["date"])
        idx = idx.sort_values("date").reset_index(drop=True)
        idx["_r5"] = idx["close"].pct_change(5) * 100
        idx["_r20"] = idx["close"].pct_change(20) * 100
        idx = idx.rename(columns={"_r5": p5, "_r20": p20})
        feat = feat.merge(idx[["date", p5, p20]], left_on="signal_date", right_on="date", how="left")
        feat = feat.drop(columns=["date"])

    # 当日 BB 信号数（wide 按日计数）
    sig_cnt = wide.groupby("signal_date").size().rename("daily_bb_signal_count")
    feat = feat.merge(sig_cnt.reset_index(), on="signal_date", how="left")
    feat["daily_bb_signal_count"] = np.log1p(feat["daily_bb_signal_count"].fillna(0))

    return feat[["signal_id", "ts_code", "signal_date"] + FEATURE_COLS]


def _market_daily_stats(hist: pd.DataFrame) -> pd.DataFrame:
    """T 日全市场 amount 百分位 + 上涨/下跌占比（横截面, 当日收盘可知）。"""
    d = hist[["date", "ts_code", "amount", "close_adj"]].copy()
    d["ret_d"] = d.groupby("ts_code")["close_adj"].pct_change()
    up = d.groupby("date")["ret_d"].apply(lambda s: (s > 0).mean()).rename("market_up_ratio")
    down = d.groupby("date")["ret_d"].apply(lambda s: (s < 0).mean()).rename("market_down_ratio")
    amt_pct = (
        d.groupby("date")["amount"].rank(pct=True) * 100
    ).groupby(d["date"]).mean().rename("amount_percentile")
    out = pd.DataFrame({"market_up_ratio": up, "market_down_ratio": down, "amount_percentile": amt_pct}).reset_index()
    return out


if __name__ == "__main__":
    f = build_full_features()
    print("full feature 表:", f.shape)
    print("缺失率 top5:", f[FEATURE_COLS].isna().mean().sort_values(ascending=False).head(5).round(4).to_dict())
    out = os.path.join(ML_OUT, "ml_features_full.parquet")
    f.to_parquet(out, index=False)
    print("已落盘:", out, f"{os.path.getsize(out)/1e6:.1f} MB")
