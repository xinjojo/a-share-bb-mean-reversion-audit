"""
SIGPATH-D full descriptive statistical audit.

This phase reads the frozen SIGPATH wide/long raw tables after verifying their
byte-level SHA256 hashes against raw_data_manifest.json. It only produces
descriptive tables, charts, a casebook, and a human-readable report.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[2]
RAW_DIR = REPO / "results" / "evidence" / "sigpath"
OUT = REPO / "results" / "evidence" / "sigpath_d"
REPORT = REPO / "research" / "sigpath" / "SIGPATH_D_DESCRIPTIVE_REPORT.md"
MANIFEST = RAW_DIR / "raw_data_manifest.json"
WIDE_PATH = RAW_DIR / "signal_path_20d_wide.parquet"
LONG_PATH = RAW_DIR / "signal_path_20d_long.parquet"
BOUNDARY = pd.Timestamp("2024-12-31")
EXPECTED_ROWS = 157_469
EXPECTED_LONG_ROWS = 3_149_380
EXPECTED_ROLE_COUNTS = {
    "NEW_ENTRY": 63_887,
    "ADD_ON_1": 42_105,
    "ADD_ON_2": 25_652,
    "ADD_ON_3": 15_828,
    "ADD_ON_4": 9_997,
}
HORIZON = 20
CORE_HORIZONS = [1, 2, 3, 5, 10, 15, 20]
CORE_VARS = ["open_ret", "high_ret", "low_ret", "close_ret", "MFE", "MAE"]
PATH_VARS = ["close_ret", "MFE", "MAE"]
PATH_PCTS = [5, 10, 25, 50, 75, 90, 95]
STAT_PCTS = [1, 5, 10, 20, 25, 30, 40, 50, 60, 70, 75, 80, 90, 95, 99]
MFE_THRESHOLDS = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30]
MAE_THRESHOLDS = [-0.01, -0.02, -0.03, -0.04, -0.05, -0.06, -0.08, -0.10, -0.12, -0.15, -0.20, -0.25, -0.30, -0.40]
FIRST_MFE_THRESHOLDS = [0.03, 0.05, 0.08, 0.10, 0.15, 0.20]
FIRST_MAE_THRESHOLDS = [-0.03, -0.05, -0.08, -0.10, -0.15, -0.20]
CLOSE_DIST_HORIZONS = [1, 3, 5, 10, 20]
CLOSE_DIST_EDGES = [-np.inf, -0.30, -0.20, -0.15, -0.10, -0.08, -0.05, -0.03, -0.01, 0.0, 0.01, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30, np.inf]
CLOSE_DIST_LABELS = [
    "< -30%",
    "[-30,-20)",
    "[-20,-15)",
    "[-15,-10)",
    "[-10,-8)",
    "[-8,-5)",
    "[-5,-3)",
    "[-3,-1)",
    "[-1,0)",
    "[0,1)",
    "[1,3)",
    "[3,5)",
    "[5,8)",
    "[8,10)",
    "[10,15)",
    "[15,20)",
    "[20,30)",
    ">=30%",
]
MAE_BUCKETS = [
    (">-3%", -0.03, np.inf),
    ("[-3,-5%)", -0.05, -0.03),
    ("[-5,-8%)", -0.08, -0.05),
    ("[-8,-10%)", -0.10, -0.08),
    ("[-10,-15%)", -0.15, -0.10),
    ("[-15,-20%)", -0.20, -0.15),
    ("[-20,-30%)", -0.30, -0.20),
    ("<=-30%", -np.inf, -0.30),
]
MFE_BUCKETS = [
    ("<0", -np.inf, 0.0),
    ("[0,3)", 0.0, 0.03),
    ("[3,5)", 0.03, 0.05),
    ("[5,8)", 0.05, 0.08),
    ("[8,10)", 0.08, 0.10),
    ("[10,15)", 0.10, 0.15),
    (">=15%", 0.15, np.inf),
]
BBZ_BUCKETS = [
    (">= -2.0", -2.0, np.inf),
    ("[-2.25,-2.0)", -2.25, -2.0),
    ("[-2.5,-2.25)", -2.5, -2.25),
    ("[-2.75,-2.5)", -2.75, -2.5),
    ("[-3.0,-2.75)", -3.0, -2.75),
    ("[-3.5,-3.0)", -3.5, -3.0),
    ("< -3.5", -np.inf, -3.5),
]
TURNOVER_BUCKETS = [
    ("1", 1, 1),
    ("2-3", 2, 3),
    ("4-5", 4, 5),
    ("6-10", 6, 10),
    ("11-20", 11, 20),
    ("21-50", 21, 50),
    (">50", 51, np.inf),
]
DOWN_UP_TEMPLATES = [
    ("MAE<=-3_then_MFE>=+3", -0.03, 0.03),
    ("MAE<=-5_then_MFE>=+5", -0.05, 0.05),
    ("MAE<=-8_then_MFE>=+5", -0.08, 0.05),
    ("MAE<=-10_then_MFE>=0", -0.10, 0.0),
    ("MAE<=-10_then_MFE>=+5", -0.10, 0.05),
    ("MAE<=-15_then_MFE>=0", -0.15, 0.0),
]
UP_DOWN_TEMPLATES = [
    ("MFE>=+3_then_MAE<=-3", 0.03, -0.03),
    ("MFE>=+5_then_MAE<=-5", 0.05, -0.05),
    ("MFE>=+8_then_MAE<=-5", 0.08, -0.05),
    ("MFE>=+10_then_MAE<=0", 0.10, 0.0),
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def json_dump(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def pct(x: float | int | np.floating | None) -> float | None:
    if x is None or pd.isna(x):
        return None
    return float(x) * 100.0


def fmt_pct(x: float | int | np.floating | None, digits: int = 2) -> str:
    if x is None or pd.isna(x):
        return "NA"
    return f"{float(x) * 100:.{digits}f}%"


def fmt_signed_pct(x: float | int | np.floating | None, digits: int = 2) -> str:
    if x is None or pd.isna(x):
        return "NA"
    return f"{float(x) * 100:+.{digits}f}%"


def stat_summary(values: pd.Series) -> dict[str, Any]:
    x = values.to_numpy(dtype=float)
    finite = x[np.isfinite(x)]
    out: dict[str, Any] = {
        "total_N": int(len(x)),
        "N": int(len(finite)),
        "missing_N": int(len(x) - len(finite)),
    }
    if len(finite) == 0:
        for key in ["mean", "median", "variance", "std", "min", "max", "range", "IQR", "skew", "kurtosis"]:
            out[key] = np.nan
        for p in STAT_PCTS:
            out[f"P{p}"] = np.nan
        return out
    q = np.percentile(finite, STAT_PCTS)
    out.update(
        {
            "mean": float(np.mean(finite)),
            "median": float(np.median(finite)),
            "variance": float(np.var(finite, ddof=1)) if len(finite) > 1 else 0.0,
            "std": float(np.std(finite, ddof=1)) if len(finite) > 1 else 0.0,
            "min": float(np.min(finite)),
            "max": float(np.max(finite)),
            "range": float(np.max(finite) - np.min(finite)),
            "IQR": float(np.percentile(finite, 75) - np.percentile(finite, 25)),
            "skew": float(pd.Series(finite).skew()) if len(finite) > 2 else np.nan,
            "kurtosis": float(pd.Series(finite).kurt()) if len(finite) > 3 else np.nan,
        }
    )
    out.update({f"P{p}": float(v) for p, v in zip(STAT_PCTS, q)})
    return out


def simple_outcome_stats(df: pd.DataFrame, close_col: str = "close_ret_D20") -> dict[str, Any]:
    close = df[close_col].to_numpy(dtype=float)
    valid = close[np.isfinite(close)]
    if len(valid) == 0:
        return {
            "D20_N": 0,
            "D20_close_mean": np.nan,
            "D20_close_median": np.nan,
            "D20_close_P10": np.nan,
            "D20_close_P90": np.nan,
            "D20_positive_pct": np.nan,
            "D20_ge_5pct": np.nan,
            "D20_ge_0pct": np.nan,
            "D20_le_minus_10pct": np.nan,
            "D20_le_minus_5pct": np.nan,
        }
    return {
        "D20_N": int(len(valid)),
        "D20_close_mean": float(np.mean(valid)),
        "D20_close_median": float(np.median(valid)),
        "D20_close_P10": float(np.percentile(valid, 10)),
        "D20_close_P90": float(np.percentile(valid, 90)),
        "D20_positive_pct": float(np.mean(valid > 0) * 100),
        "D20_ge_5pct": float(np.mean(valid >= 0.05) * 100),
        "D20_ge_0pct": float(np.mean(valid >= 0.0) * 100),
        "D20_le_minus_10pct": float(np.mean(valid <= -0.10) * 100),
        "D20_le_minus_5pct": float(np.mean(valid <= -0.05) * 100),
    }


def finite_hit_pct(values: pd.Series, threshold: float, direction: str) -> float:
    arr = values.to_numpy(dtype=float)
    valid = arr[np.isfinite(arr)]
    if len(valid) == 0:
        return np.nan
    if direction == "ge":
        return float(np.mean(valid >= threshold) * 100)
    if direction == "gt":
        return float(np.mean(valid > threshold) * 100)
    if direction == "le":
        return float(np.mean(valid <= threshold) * 100)
    raise ValueError(direction)


def verify_and_load() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, str]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    actual = {"wide": sha256_file(WIDE_PATH), "long": sha256_file(LONG_PATH)}
    expected = {"wide": manifest["wide"]["sha256"], "long": manifest["long"]["sha256"]}
    if actual != expected:
        raise SystemExit(f"STOP: raw SHA mismatch actual={actual} expected={expected}")
    wide = pd.read_parquet(WIDE_PATH)
    long = pd.read_parquet(LONG_PATH)
    return wide, long, manifest, actual


def validate_baseline(wide: pd.DataFrame, long: pd.DataFrame) -> dict[str, Any]:
    role_counts = {k: int(v) for k, v in wide["entry_role"].value_counts().sort_index().items()}
    date_checks = {
        "max_signal_date": str(pd.to_datetime(wide["signal_date"]).max().date()),
        "max_entry_date": str(pd.to_datetime(wide["entry_date"]).max().date()),
        "max_trade_date": str(pd.to_datetime(long["trade_date"]).max().date()),
        "wide_signal_2025_plus": int((pd.to_datetime(wide["signal_date"]) > BOUNDARY).sum()),
        "wide_entry_2025_plus": int((pd.to_datetime(wide["entry_date"]) > BOUNDARY).sum()),
        "long_trade_2025_plus": int((pd.to_datetime(long["trade_date"]) > BOUNDARY).sum()),
    }
    checks = {
        "wide_rows": int(len(wide)),
        "long_rows": int(len(long)),
        "role_counts": role_counts,
        **date_checks,
    }
    ok = (
        len(wide) == EXPECTED_ROWS
        and len(long) == EXPECTED_LONG_ROWS
        and role_counts == dict(sorted(EXPECTED_ROLE_COUNTS.items()))
        and date_checks["wide_signal_2025_plus"] == 0
        and date_checks["wide_entry_2025_plus"] == 0
        and date_checks["long_trade_2025_plus"] == 0
    )
    if not ok:
        raise SystemExit(f"STOP: baseline parity failed {checks}")
    return checks


def write_core_horizon_statistics(wide: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for horizon in CORE_HORIZONS:
        for var in CORE_VARS:
            row = {"horizon": f"D{horizon}", "variable": var}
            row.update(stat_summary(wide[f"{var}_D{horizon}"]))
            rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "core_horizon_statistics.csv", index=False)
    return df


def write_percentile_paths(wide: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for var in PATH_VARS:
        rows = []
        for horizon in range(1, HORIZON + 1):
            x = wide[f"{var}_D{horizon}"].to_numpy(dtype=float)
            finite = x[np.isfinite(x)]
            row = {
                "horizon": f"D{horizon}",
                "horizon_day": horizon,
                "N": int(len(finite)),
                "missing_N": int(len(x) - len(finite)),
                "mean": float(np.mean(finite)) if len(finite) else np.nan,
            }
            if len(finite):
                row.update({f"P{p}": float(np.percentile(finite, p)) for p in PATH_PCTS})
            else:
                row.update({f"P{p}": np.nan for p in PATH_PCTS})
            rows.append(row)
        df = pd.DataFrame(rows)
        filename = {
            "close_ret": "percentile_path_close.csv",
            "MFE": "percentile_path_mfe.csv",
            "MAE": "percentile_path_mae.csv",
        }[var]
        df.to_csv(OUT / filename, index=False)
        out[var] = df
    return out


def plot_percentile_path(df: pd.DataFrame, title: str, filename: str) -> None:
    fig, ax = plt.subplots(figsize=(9, 5.5))
    xs = df["horizon_day"].to_numpy()
    for col in ["P5", "P10", "P25", "P50", "P75", "P90", "P95"]:
        lw = 2.0 if col == "P50" else 1.1
        ax.plot(xs, df[col].to_numpy(dtype=float) * 100, marker="o", linewidth=lw, label=col)
    ax.axhline(0, linewidth=0.8, color="black", alpha=0.5)
    ax.set_title(title)
    ax.set_xlabel("Horizon day")
    ax.set_ylabel("Return (%)")
    ax.set_xticks(xs)
    ax.grid(alpha=0.25)
    ax.legend(ncol=4, fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / filename, dpi=140)
    plt.close(fig)


def write_close_distribution(wide: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for horizon in CLOSE_DIST_HORIZONS:
        x = wide[f"close_ret_D{horizon}"].to_numpy(dtype=float)
        finite = x[np.isfinite(x)]
        counts, _ = np.histogram(finite, bins=CLOSE_DIST_EDGES)
        total = int(len(finite))
        for label, count in zip(CLOSE_DIST_LABELS, counts):
            rows.append(
                {
                    "horizon": f"D{horizon}",
                    "bin": label,
                    "count": int(count),
                    "pct": float(count / total * 100) if total else np.nan,
                }
            )
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "close_return_distribution_bins.csv", index=False)
    return df


def plot_close_hist(wide: pd.DataFrame, horizon: int, filename: str) -> None:
    x = wide[f"close_ret_D{horizon}"].to_numpy(dtype=float)
    finite = x[np.isfinite(x)] * 100
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(finite, bins=120, range=(-50, 80), alpha=0.85)
    ax.axvline(np.median(finite), linewidth=1.2, linestyle="--", color="black")
    ax.set_title(f"Close Return Distribution D{horizon}")
    ax.set_xlabel("Close return (%)")
    ax.set_ylabel("Signal count")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(OUT / filename, dpi=140)
    plt.close(fig)


def write_hit_rate_matrix(wide: pd.DataFrame, kind: str) -> pd.DataFrame:
    thresholds = MFE_THRESHOLDS if kind == "MFE" else MAE_THRESHOLDS
    op = np.greater_equal if kind == "MFE" else np.less_equal
    rows = []
    for horizon in range(1, HORIZON + 1):
        values = wide[f"{kind}_D{horizon}"].to_numpy(dtype=float)
        finite = values[np.isfinite(values)]
        for threshold in thresholds:
            hit = int(op(finite, threshold).sum()) if len(finite) else 0
            rows.append(
                {
                    "horizon": f"D{horizon}",
                    "horizon_day": horizon,
                    "threshold": threshold,
                    "count": hit,
                    "total_N": int(len(finite)),
                    "pct": float(hit / len(finite) * 100) if len(finite) else np.nan,
                }
            )
    df = pd.DataFrame(rows)
    df.to_csv(OUT / f"{kind.lower()}_hit_rate_extended.csv", index=False)
    return df


def plot_hit_heatmap(df: pd.DataFrame, title: str, filename: str) -> None:
    matrix = df.pivot(index="threshold", columns="horizon_day", values="pct")
    fig, ax = plt.subplots(figsize=(11, 6))
    im = ax.imshow(matrix.to_numpy(dtype=float), aspect="auto", cmap="viridis")
    ax.set_title(title)
    ax.set_xlabel("Horizon day")
    ax.set_ylabel("Threshold")
    ax.set_xticks(range(HORIZON))
    ax.set_xticklabels([str(i) for i in range(1, HORIZON + 1)], fontsize=8)
    ax.set_yticks(range(len(matrix.index)))
    ax.set_yticklabels([f"{v * 100:+.0f}%" for v in matrix.index], fontsize=8)
    fig.colorbar(im, ax=ax, label="Hit rate (%)")
    fig.tight_layout()
    fig.savefig(OUT / filename, dpi=140)
    plt.close(fig)


def first_hit_days(arr: np.ndarray, threshold: float, mode: str) -> np.ndarray:
    if mode == "up":
        hit = arr >= threshold
    elif mode == "down":
        hit = arr <= threshold
    else:
        raise ValueError(mode)
    hit &= np.isfinite(arr)
    any_hit = hit.any(axis=1)
    first = np.full(arr.shape[0], np.nan)
    first[any_hit] = np.argmax(hit[any_hit], axis=1) + 1
    return first


def write_first_hit_stats(wide: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, np.ndarray], dict[str, np.ndarray]]:
    high_ret = np.column_stack([wide[f"high_ret_D{h}"].to_numpy(dtype=float) for h in range(1, HORIZON + 1)])
    low_ret = np.column_stack([wide[f"low_ret_D{h}"].to_numpy(dtype=float) for h in range(1, HORIZON + 1)])

    def stats(thresholds: list[float], arr: np.ndarray, mode: str) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
        rows = []
        first_by_threshold: dict[str, np.ndarray] = {}
        for threshold in thresholds:
            first = first_hit_days(arr, threshold, mode)
            key = f"{threshold:+.0%}"
            first_by_threshold[key] = first
            hit = first[np.isfinite(first)]
            rows.append(
                {
                    "threshold": threshold,
                    "threshold_label": key,
                    "hit_count": int(len(hit)),
                    "hit_pct": float(len(hit) / len(first) * 100),
                    "median_hit_day": float(np.median(hit)) if len(hit) else np.nan,
                    "P25_hit_day": float(np.percentile(hit, 25)) if len(hit) else np.nan,
                    "P75_hit_day": float(np.percentile(hit, 75)) if len(hit) else np.nan,
                    "D1_hit_pct": float(np.mean(first == 1) * 100),
                    "D3_cumulative_pct": float(np.mean(first <= 3) * 100),
                    "D5_cumulative_pct": float(np.mean(first <= 5) * 100),
                    "D10_cumulative_pct": float(np.mean(first <= 10) * 100),
                    "D20_cumulative_pct": float(np.mean(first <= 20) * 100),
                    "not_hit_count": int(np.isnan(first).sum()),
                }
            )
        return pd.DataFrame(rows), first_by_threshold

    mfe_df, mfe_first = stats(FIRST_MFE_THRESHOLDS, high_ret, "up")
    mae_df, mae_first = stats(FIRST_MAE_THRESHOLDS, low_ret, "down")
    mfe_df.to_csv(OUT / "first_hit_time_mfe.csv", index=False)
    mae_df.to_csv(OUT / "first_hit_time_mae.csv", index=False)
    return mfe_df, mae_df, mfe_first, mae_first


def plot_first_hit_distribution(first_by_threshold: dict[str, np.ndarray], title: str, filename: str) -> None:
    fig, ax = plt.subplots(figsize=(9, 5.5))
    xs = np.arange(1, HORIZON + 1)
    n = len(next(iter(first_by_threshold.values())))
    for label, first in first_by_threshold.items():
        ys = [float(np.mean(first <= h) * 100) for h in xs]
        ax.plot(xs, ys, marker="o", linewidth=1.2, label=label)
    ax.set_title(title)
    ax.set_xlabel("First hit by horizon day")
    ax.set_ylabel("Cumulative hit rate (%)")
    ax.set_xticks(xs)
    ax.grid(alpha=0.25)
    ax.legend(title=f"N={n}", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / filename, dpi=140)
    plt.close(fig)


def ordered_path(first_a: np.ndarray, second_arr: np.ndarray, threshold: float, mode: str) -> tuple[np.ndarray, np.ndarray]:
    second = np.full(len(first_a), np.nan)
    for idx in np.where(np.isfinite(first_a))[0]:
        start = int(first_a[idx])
        if start >= HORIZON:
            continue
        rest = second_arr[idx, start:]
        if mode == "up":
            hit = np.isfinite(rest) & (rest >= threshold)
        else:
            hit = np.isfinite(rest) & (rest <= threshold)
        if hit.any():
            second[idx] = start + int(np.argmax(hit)) + 1
    ok = np.isfinite(first_a) & np.isfinite(second) & (second > first_a)
    return ok, second


def write_path_order_stats(wide: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, np.ndarray]]:
    high_ret = np.column_stack([wide[f"high_ret_D{h}"].to_numpy(dtype=float) for h in range(1, HORIZON + 1)])
    low_ret = np.column_stack([wide[f"low_ret_D{h}"].to_numpy(dtype=float) for h in range(1, HORIZON + 1)])
    masks: dict[str, np.ndarray] = {}
    down_rows = []
    for name, down_th, up_th in DOWN_UP_TEMPLATES:
        down_first = first_hit_days(low_ret, down_th, "down")
        ok, up_after = ordered_path(down_first, high_ret, up_th, "up")
        masks[name] = ok
        days_to_recovery = up_after[ok] - down_first[ok]
        down_rows.append(
            {
                "template": name,
                "downside_threshold": down_th,
                "recovery_threshold": up_th,
                "count": int(ok.sum()),
                "pct": float(ok.mean() * 100),
                "median_downside_hit_day": float(np.median(down_first[ok])) if ok.any() else np.nan,
                "median_recovery_hit_day": float(np.median(up_after[ok])) if ok.any() else np.nan,
                "median_days_to_recovery": float(np.median(days_to_recovery)) if ok.any() else np.nan,
                "P25_recovery_days": float(np.percentile(days_to_recovery, 25)) if ok.any() else np.nan,
                "P75_recovery_days": float(np.percentile(days_to_recovery, 75)) if ok.any() else np.nan,
            }
        )

    up_rows = []
    for name, up_th, down_th in UP_DOWN_TEMPLATES:
        up_first = first_hit_days(high_ret, up_th, "up")
        ok, down_after = ordered_path(up_first, low_ret, down_th, "down")
        masks[name] = ok
        days_to_down = down_after[ok] - up_first[ok]
        up_rows.append(
            {
                "template": name,
                "upside_threshold": up_th,
                "downside_threshold": down_th,
                "count": int(ok.sum()),
                "pct": float(ok.mean() * 100),
                "median_upside_hit_day": float(np.median(up_first[ok])) if ok.any() else np.nan,
                "median_downside_hit_day": float(np.median(down_after[ok])) if ok.any() else np.nan,
                "median_days_to_downside": float(np.median(days_to_down)) if ok.any() else np.nan,
                "P25_downside_days": float(np.percentile(days_to_down, 25)) if ok.any() else np.nan,
                "P75_downside_days": float(np.percentile(days_to_down, 75)) if ok.any() else np.nan,
            }
        )
    down_df = pd.DataFrame(down_rows)
    up_df = pd.DataFrame(up_rows)
    down_df.to_csv(OUT / "down_then_up_path_stats.csv", index=False)
    up_df.to_csv(OUT / "up_then_down_path_stats.csv", index=False)
    return down_df, up_df, masks


def bucket_mask(values: pd.Series, low: float, high: float) -> pd.Series:
    x = values.astype(float)
    if low == -np.inf:
        return x < high
    if high == np.inf:
        return x >= low
    return (x >= low) & (x < high)


def write_recovery_tables(wide: pd.DataFrame) -> dict[int, pd.DataFrame]:
    out: dict[int, pd.DataFrame] = {}
    for anchor in [10, 5, 3]:
        rows = []
        anchor_col = f"MAE_D{anchor}"
        for label, low, high in MAE_BUCKETS:
            sub = wide[bucket_mask(wide[anchor_col], low, high)]
            st = simple_outcome_stats(sub)
            rows.append(
                {
                    "anchor": f"MAE_D{anchor}",
                    "MAE_bucket": label,
                    "N": int(len(sub)),
                    **st,
                    "MFE_D20_median": float(sub["MFE_D20"].median(skipna=True)) if len(sub) else np.nan,
                    "MAE_D20_median": float(sub["MAE_D20"].median(skipna=True)) if len(sub) else np.nan,
                }
            )
        df = pd.DataFrame(rows)
        df.to_csv(OUT / f"mae_d{anchor}_to_d20_outcome_table.csv", index=False)
        out[anchor] = df
    return out


def write_early_mfe_outcome(wide: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for anchor in [3, 5, 10]:
        col = f"MFE_D{anchor}"
        for label, low, high in MFE_BUCKETS:
            sub = wide[bucket_mask(wide[col], low, high)]
            st = simple_outcome_stats(sub)
            rows.append(
                {
                    "anchor": col,
                    "MFE_bucket": label,
                    "N": int(len(sub)),
                    "D20_mean": st["D20_close_mean"],
                    "D20_median": st["D20_close_median"],
                    "D20_P10": st["D20_close_P10"],
                    "D20_P90": st["D20_close_P90"],
                    "D20_positive_pct": st["D20_positive_pct"],
                    "D20_ge_5pct": st["D20_ge_5pct"],
                    "D20_le_minus_5pct": st["D20_le_minus_5pct"],
                    "D20_le_minus_10pct": st["D20_le_minus_10pct"],
                }
            )
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "early_mfe_to_d20_outcome.csv", index=False)
    return df


def write_role_stats(wide: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for role in EXPECTED_ROLE_COUNTS:
        sub = wide[wide["entry_role"] == role]
        row: dict[str, Any] = {"entry_role": role, "N": int(len(sub))}
        for horizon in [1, 3, 5, 10, 20]:
            close = sub[f"close_ret_D{horizon}"].to_numpy(dtype=float)
            close = close[np.isfinite(close)]
            mfe = sub[f"MFE_D{horizon}"].to_numpy(dtype=float)
            mfe = mfe[np.isfinite(mfe)]
            mae = sub[f"MAE_D{horizon}"].to_numpy(dtype=float)
            mae = mae[np.isfinite(mae)]
            row.update(
                {
                    f"D{horizon}_close_mean": float(np.mean(close)) if len(close) else np.nan,
                    f"D{horizon}_close_median": float(np.median(close)) if len(close) else np.nan,
                    f"D{horizon}_close_P10": float(np.percentile(close, 10)) if len(close) else np.nan,
                    f"D{horizon}_close_P25": float(np.percentile(close, 25)) if len(close) else np.nan,
                    f"D{horizon}_close_P75": float(np.percentile(close, 75)) if len(close) else np.nan,
                    f"D{horizon}_close_P90": float(np.percentile(close, 90)) if len(close) else np.nan,
                    f"D{horizon}_MFE_median": float(np.median(mfe)) if len(mfe) else np.nan,
                    f"D{horizon}_MAE_median": float(np.median(mae)) if len(mae) else np.nan,
                }
            )
        row.update(
            {
                "D20_positive_pct": finite_hit_pct(sub["close_ret_D20"], 0.0, "gt"),
                "D10_MFE_ge_5pct": finite_hit_pct(sub["MFE_D10"], 0.05, "ge"),
                "D10_MAE_le_minus_5pct": finite_hit_pct(sub["MAE_D10"], -0.05, "le"),
                "D20_MFE_ge_10pct": finite_hit_pct(sub["MFE_D20"], 0.10, "ge"),
                "D20_MAE_le_minus_10pct": finite_hit_pct(sub["MAE_D20"], -0.10, "le"),
            }
        )
        rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "role_descriptive_statistics.csv", index=False)
    return df


def plot_group_median_path(wide: pd.DataFrame, group_col: str, value_prefix: str, title: str, filename: str) -> None:
    fig, ax = plt.subplots(figsize=(9, 5.5))
    xs = np.arange(1, HORIZON + 1)
    groups = list(EXPECTED_ROLE_COUNTS) if group_col == "entry_role" else sorted(wide[group_col].dropna().unique())
    for group in groups:
        sub = wide[wide[group_col] == group]
        ys = [sub[f"{value_prefix}_D{h}"].median(skipna=True) * 100 for h in xs]
        ax.plot(xs, ys, marker="o", linewidth=1.2, label=str(group))
    ax.axhline(0, linewidth=0.8, color="black", alpha=0.5)
    ax.set_title(title)
    ax.set_xlabel("Horizon day")
    ax.set_ylabel("Median (%)")
    ax.set_xticks(xs)
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / filename, dpi=140)
    plt.close(fig)


def write_year_stats(wide: pd.DataFrame, new_entry_only: bool = False) -> pd.DataFrame:
    df = wide[wide["entry_role"] == "NEW_ENTRY"].copy() if new_entry_only else wide.copy()
    df["signal_year"] = pd.to_datetime(df["signal_date"]).dt.year
    rows = []
    for year in [2020, 2021, 2022, 2023, 2024]:
        sub = df[df["signal_year"] == year]
        row: dict[str, Any] = {"signal_year": year, "signal_count": int(len(sub))}
        for horizon in [5, 10, 20]:
            close = sub[f"close_ret_D{horizon}"].to_numpy(dtype=float)
            close = close[np.isfinite(close)]
            row.update(
                {
                    f"D{horizon}_close_mean": float(np.mean(close)) if len(close) else np.nan,
                    f"D{horizon}_close_median": float(np.median(close)) if len(close) else np.nan,
                    f"D{horizon}_close_P10": float(np.percentile(close, 10)) if len(close) else np.nan,
                    f"D{horizon}_close_P90": float(np.percentile(close, 90)) if len(close) else np.nan,
                }
            )
        row.update(
            {
                "D10_MFE_median": float(sub["MFE_D10"].median(skipna=True)) if len(sub) else np.nan,
                "D10_MAE_median": float(sub["MAE_D10"].median(skipna=True)) if len(sub) else np.nan,
                "D20_positive_pct": finite_hit_pct(sub["close_ret_D20"], 0.0, "gt") if len(sub) else np.nan,
                "D20_ge_10pct": finite_hit_pct(sub["close_ret_D20"], 0.10, "ge") if len(sub) else np.nan,
                "D20_le_minus_10pct": finite_hit_pct(sub["close_ret_D20"], -0.10, "le") if len(sub) else np.nan,
            }
        )
        rows.append(row)
    out = pd.DataFrame(rows)
    out.to_csv(OUT / ("new_entry_year_statistics.csv" if new_entry_only else "year_descriptive_statistics.csv"), index=False)
    return out


def plot_year_d20_distribution(wide: pd.DataFrame) -> None:
    df = wide.copy()
    df["signal_year"] = pd.to_datetime(df["signal_date"]).dt.year
    data = [
        df.loc[df["signal_year"] == year, "close_ret_D20"].dropna().to_numpy(dtype=float) * 100
        for year in [2020, 2021, 2022, 2023, 2024]
    ]
    fig, ax = plt.subplots(figsize=(8, 5.5))
    ax.boxplot(data, tick_labels=["2020", "2021", "2022", "2023", "2024"], showfliers=False)
    ax.axhline(0, linewidth=0.8, color="black", alpha=0.5)
    ax.set_title("D20 Close Return Distribution by Signal Year")
    ax.set_xlabel("Signal year")
    ax.set_ylabel("D20 close return (%)")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(OUT / "year_d20_distribution.png", dpi=140)
    plt.close(fig)


def write_bb_z_buckets(wide: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label, low, high in BBZ_BUCKETS:
        sub = wide[bucket_mask(wide["bb_z"], low, high)]
        rows.append(
            {
                "bucket": label,
                "N": int(len(sub)),
                "D5_median": float(sub["close_ret_D5"].median(skipna=True)) if len(sub) else np.nan,
                "D10_median": float(sub["close_ret_D10"].median(skipna=True)) if len(sub) else np.nan,
                "D20_median": float(sub["close_ret_D20"].median(skipna=True)) if len(sub) else np.nan,
                "D20_mean": float(sub["close_ret_D20"].mean(skipna=True)) if len(sub) else np.nan,
                "D20_P10": float(sub["close_ret_D20"].quantile(0.10)) if len(sub) else np.nan,
                "D20_P90": float(sub["close_ret_D20"].quantile(0.90)) if len(sub) else np.nan,
                "MFE_D10_median": float(sub["MFE_D10"].median(skipna=True)) if len(sub) else np.nan,
                "MAE_D10_median": float(sub["MAE_D10"].median(skipna=True)) if len(sub) else np.nan,
            }
        )
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "bb_z_descriptive_buckets.csv", index=False)
    return df


def write_turnover_rank_buckets(wide: pd.DataFrame) -> pd.DataFrame:
    rows = []
    rank = wide["turnover_rank"].astype(float)
    for label, low, high in TURNOVER_BUCKETS:
        if high == np.inf:
            mask = rank >= low
        elif low == high:
            mask = rank == low
        else:
            mask = (rank >= low) & (rank <= high)
        sub = wide[mask]
        rows.append(
            {
                "bucket": label,
                "rank_min": low,
                "rank_max": None if high == np.inf else high,
                "N": int(len(sub)),
                "D10_mean": float(sub["close_ret_D10"].mean(skipna=True)) if len(sub) else np.nan,
                "D10_median": float(sub["close_ret_D10"].median(skipna=True)) if len(sub) else np.nan,
                "D10_P10": float(sub["close_ret_D10"].quantile(0.10)) if len(sub) else np.nan,
                "D10_P90": float(sub["close_ret_D10"].quantile(0.90)) if len(sub) else np.nan,
                "D20_mean": float(sub["close_ret_D20"].mean(skipna=True)) if len(sub) else np.nan,
                "D20_median": float(sub["close_ret_D20"].median(skipna=True)) if len(sub) else np.nan,
                "D20_P10": float(sub["close_ret_D20"].quantile(0.10)) if len(sub) else np.nan,
                "D20_P90": float(sub["close_ret_D20"].quantile(0.90)) if len(sub) else np.nan,
                "MFE_D10_median": float(sub["MFE_D10"].median(skipna=True)) if len(sub) else np.nan,
                "MAE_D10_median": float(sub["MAE_D10"].median(skipna=True)) if len(sub) else np.nan,
            }
        )
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "turnover_rank_descriptive.csv", index=False)
    return df


def role_order(role: str) -> int:
    if role == "NEW_ENTRY":
        return 1
    if role.startswith("ADD_ON_"):
        return int(role.split("_")[-1]) + 1
    return 0


def write_episode_layer_structure(wide: pd.DataFrame) -> pd.DataFrame:
    df = wide.copy()
    df["_role_order"] = df["entry_role"].map(role_order)
    levels = df.groupby("position_episode_id")["_role_order"].max().rename("episode_levels")
    df = df.merge(levels, on="position_episode_id", how="left")
    rows = []
    for level in [1, 2, 3, 4, 5]:
        eps = set(levels[levels == level].index)
        new_rows = df[(df["position_episode_id"].isin(eps)) & (df["entry_role"] == "NEW_ENTRY")]
        last_rows = df[(df["position_episode_id"].isin(eps)) & (df["_role_order"] == level) & (df["_role_order"] > 1)]
        rows.append(
            {
                "episode_levels": level,
                "episode_count": int(len(eps)),
                "new_entry_signal_count": int(len(new_rows)),
                "last_add_signal_count": int(len(last_rows)),
                "new_entry_D20_median": float(new_rows["close_ret_D20"].median(skipna=True)) if len(new_rows) else np.nan,
                "last_add_D20_median": float(last_rows["close_ret_D20"].median(skipna=True)) if len(last_rows) else np.nan,
                "new_entry_D10_MFE_median": float(new_rows["MFE_D10"].median(skipna=True)) if len(new_rows) else np.nan,
                "last_add_D10_MFE_median": float(last_rows["MFE_D10"].median(skipna=True)) if len(last_rows) else np.nan,
                "new_entry_D10_MAE_median": float(new_rows["MAE_D10"].median(skipna=True)) if len(new_rows) else np.nan,
                "last_add_D10_MAE_median": float(last_rows["MAE_D10"].median(skipna=True)) if len(last_rows) else np.nan,
            }
        )
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "episode_layer_structure.csv", index=False)
    return out


def write_manual_casebook(wide: pd.DataFrame, masks: dict[str, np.ndarray]) -> pd.DataFrame:
    df = wide.copy()
    df["_orig_index"] = np.arange(len(df))
    fields = {
        "entry_role": "role",
        "bb_z": "BB_z",
        "close_ret_D5": "D5_close_ret",
        "close_ret_D10": "D10_close_ret",
        "close_ret_D20": "D20_close_ret",
        "MFE_D10": "D10_MFE",
        "MAE_D10": "D10_MAE",
        "MFE_D20": "D20_MFE",
        "MAE_D20": "D20_MAE",
    }
    base_cols = [
        "signal_id",
        "position_episode_id",
        "entry_role",
        "ts_code",
        "stock_code",
        "stock_name",
        "signal_date",
        "entry_date",
        "available_future_days",
        "close_ret_D5",
        "close_ret_D10",
        "close_ret_D20",
        "MFE_D10",
        "MAE_D10",
        "MFE_D20",
        "MAE_D20",
        "bb_z",
        "turnover_rank",
    ]

    level_map = df.groupby("position_episode_id")["entry_role"].apply(lambda s: max(role_order(x) for x in s))
    df["_episode_levels"] = df["position_episode_id"].map(level_map)
    median_d20 = df["close_ret_D20"].median(skipna=True)

    selectors = [
        ("A_D20_worst_50", df.sort_values("close_ret_D20", ascending=True).head(50)),
        ("B_D20_best_50", df.sort_values("close_ret_D20", ascending=False).head(50)),
        ("C_D10_MAE_worst_50", df.sort_values("MAE_D10", ascending=True).head(50)),
        ("D_D10_MFE_best_50", df.sort_values("MFE_D10", ascending=False).head(50)),
        ("E_down10_then_0_typical_50", df.loc[masks["MAE<=-10_then_MFE>=0"]].sort_values(["signal_date", "ts_code"]).head(50)),
        ("F_down10_then_5_typical_50", df.loc[masks["MAE<=-10_then_MFE>=+5"]].sort_values(["signal_date", "ts_code"]).head(50)),
        ("G_up10_then_0_typical_50", df.loc[masks["MFE>=+10_then_MAE<=0"]].sort_values(["signal_date", "ts_code"]).head(50)),
        (
            "H_5_layer_episode_typical_50",
            df[(df["_episode_levels"] == 5) & (df["entry_role"] == "NEW_ENTRY")].sort_values(["signal_date", "ts_code"]).head(50),
        ),
        (
            "I_near_overall_median_50",
            df.assign(_dist=(df["close_ret_D20"] - median_d20).abs()).sort_values(["_dist", "signal_date", "ts_code"]).head(50),
        ),
    ]
    rows = []
    for case_type, sub in selectors:
        tmp = sub[base_cols].copy()
        tmp.insert(0, "case_type", case_type)
        rows.append(tmp)
    out = pd.concat(rows, ignore_index=True)
    out = out.rename(columns=fields)
    out.to_csv(OUT / "manual_casebook.csv", index=False)
    return out


def plot_mae_d10_vs_d20_heatmap(wide: pd.DataFrame) -> None:
    mae = wide["MAE_D10"].to_numpy(dtype=float)
    d20 = wide["close_ret_D20"].to_numpy(dtype=float)
    valid = np.isfinite(mae) & np.isfinite(d20)
    y_edges = [-np.inf, -0.30, -0.20, -0.15, -0.10, -0.08, -0.05, -0.03, np.inf]
    y_labels = ["<=-30", "-30~-20", "-20~-15", "-15~-10", "-10~-8", "-8~-5", "-5~-3", ">-3"]
    x_edges = [-np.inf, -0.30, -0.20, -0.15, -0.10, -0.05, 0.0, 0.05, 0.10, 0.20, np.inf]
    x_labels = ["<-30", "-30~-20", "-20~-15", "-15~-10", "-10~-5", "-5~0", "0~5", "5~10", "10~20", ">=20"]
    mat, _, _ = np.histogram2d(mae[valid], d20[valid], bins=[y_edges, x_edges])
    row_sum = mat.sum(axis=1, keepdims=True)
    pct_mat = np.divide(mat, row_sum, out=np.zeros_like(mat), where=row_sum > 0) * 100
    fig, ax = plt.subplots(figsize=(10, 6))
    im = ax.imshow(pct_mat, aspect="auto", cmap="viridis")
    ax.set_title("MAE D10 vs D20 Close Return Distribution")
    ax.set_xlabel("D20 close return bucket (%)")
    ax.set_ylabel("MAE D10 bucket (%)")
    ax.set_xticks(range(len(x_labels)))
    ax.set_xticklabels(x_labels, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(y_labels)))
    ax.set_yticklabels(y_labels, fontsize=8)
    fig.colorbar(im, ax=ax, label="Row percentage (%)")
    fig.tight_layout()
    fig.savefig(OUT / "14_maeD10_vs_D20_heatmap.png", dpi=140)
    plt.close(fig)


def write_summary(
    wide: pd.DataFrame,
    raw_sha: dict[str, str],
    baseline: dict[str, Any],
    down_up: pd.DataFrame,
    up_down: pd.DataFrame,
) -> dict[str, Any]:
    year_counts = {str(k): int(v) for k, v in pd.to_datetime(wide["signal_date"]).dt.year.value_counts().sort_index().items()}
    horizons: dict[str, Any] = {}
    for horizon in [1, 5, 10, 20]:
        x = wide[f"close_ret_D{horizon}"].dropna().to_numpy(dtype=float)
        horizons[f"D{horizon}"] = {
            "mean": float(np.mean(x)),
            "median": float(np.median(x)),
            "P10": float(np.percentile(x, 10)),
            "P90": float(np.percentile(x, 90)),
        }
    summary = {
        "phase": "SIGPATH-D",
        "total_signals": int(len(wide)),
        "raw_sha256_match": {
            "wide": True,
            "long": True,
        },
        "baseline_checks": baseline,
        "role_counts": baseline["role_counts"],
        "year_counts": year_counts,
        "close_ret": horizons,
        "D10_MFE_median": float(wide["MFE_D10"].median(skipna=True)),
        "D10_MAE_median": float(wide["MAE_D10"].median(skipna=True)),
        "D20_positive_pct": finite_hit_pct(wide["close_ret_D20"], 0.0, "gt"),
        "MFE_plus_5_pct": {
            "D5": finite_hit_pct(wide["MFE_D5"], 0.05, "ge"),
            "D10": finite_hit_pct(wide["MFE_D10"], 0.05, "ge"),
            "D20": finite_hit_pct(wide["MFE_D20"], 0.05, "ge"),
        },
        "MAE_minus_5_pct": {
            "D5": finite_hit_pct(wide["MAE_D5"], -0.05, "le"),
            "D10": finite_hit_pct(wide["MAE_D10"], -0.05, "le"),
            "D20": finite_hit_pct(wide["MAE_D20"], -0.05, "le"),
        },
        "down_then_up": {
            "-10_to_0_pct": float(down_up.loc[down_up["template"] == "MAE<=-10_then_MFE>=0", "pct"].iloc[0]),
            "-10_to_5_pct": float(down_up.loc[down_up["template"] == "MAE<=-10_then_MFE>=+5", "pct"].iloc[0]),
        },
        "up_then_down": {
            "+10_to_0_pct": float(up_down.loc[up_down["template"] == "MFE>=+10_then_MAE<=0", "pct"].iloc[0]),
        },
        "raw_wide_sha256": raw_sha["wide"],
        "raw_long_sha256": raw_sha["long"],
        "raw_modified": False,
        "strategy_rerun": False,
        "parameter_optimization": False,
        "read_2025_2026_outcome": False,
    }
    json_dump(OUT / "sigpath_d_summary.json", summary)
    return summary


def monotonic_label(values: list[float]) -> str:
    finite = [v for v in values if not pd.isna(v)]
    if len(finite) < 3:
        return "样本不足"
    inc = all(a <= b for a, b in zip(finite, finite[1:]))
    dec = all(a >= b for a, b in zip(finite, finite[1:]))
    if inc:
        return "描述上递增"
    if dec:
        return "描述上递减"
    return "没有单调描述趋势"


def write_report(
    summary: dict[str, Any],
    core: pd.DataFrame,
    paths: dict[str, pd.DataFrame],
    mfe_hit: pd.DataFrame,
    mae_hit: pd.DataFrame,
    first_mfe: pd.DataFrame,
    first_mae: pd.DataFrame,
    down_up: pd.DataFrame,
    up_down: pd.DataFrame,
    recovery: dict[int, pd.DataFrame],
    early_mfe: pd.DataFrame,
    role_stats: pd.DataFrame,
    year_stats: pd.DataFrame,
    new_year_stats: pd.DataFrame,
    bbz: pd.DataFrame,
    turnover: pd.DataFrame,
    episode: pd.DataFrame,
    casebook: pd.DataFrame,
) -> None:
    d20 = summary["close_ret"]["D20"]
    d10 = summary["close_ret"]["D10"]
    d5 = summary["close_ret"]["D5"]
    d1 = summary["close_ret"]["D1"]
    new = role_stats.loc[role_stats["entry_role"] == "NEW_ENTRY"].iloc[0]
    add4 = role_stats.loc[role_stats["entry_role"] == "ADD_ON_4"].iloc[0]
    year_best = year_stats.sort_values("D20_close_median", ascending=False).iloc[0]
    year_worst = year_stats.sort_values("D20_close_median", ascending=True).iloc[0]
    bbz_trend = monotonic_label(bbz["D20_median"].tolist())
    turnover_trend = monotonic_label(turnover["D20_median"].tolist())
    ep1 = episode.loc[episode["episode_levels"] == 1].iloc[0]
    ep5 = episode.loc[episode["episode_levels"] == 5].iloc[0]

    lines = [
        "# SIGPATH-D — Full Descriptive Statistical Audit",
        "",
        "本报告只描述 2020-2024 已冻结 SIGPATH forward-path 数据的样本分布。报告未修改 raw parquet, 未重新生成 raw, 未重跑策略, 未做参数优化, 未读取 2025-2026 outcome。",
        "",
        "## 1. 数据范围",
        f"- total signals: {summary['total_signals']:,}",
        f"- role counts: {summary['role_counts']}",
        f"- raw wide SHA256: `{summary['raw_wide_sha256']}`",
        f"- raw long SHA256: `{summary['raw_long_sha256']}`",
        "- 结果目录: `results/evidence/sigpath_d/`",
        "",
        "## 2. 总体收益分布",
        f"- D1 close mean/median: {fmt_signed_pct(d1['mean'])} / {fmt_signed_pct(d1['median'])}",
        f"- D5 close mean/median: {fmt_signed_pct(d5['mean'])} / {fmt_signed_pct(d5['median'])}",
        f"- D10 close mean/median: {fmt_signed_pct(d10['mean'])} / {fmt_signed_pct(d10['median'])}",
        f"- D20 close mean/median/P10/P90: {fmt_signed_pct(d20['mean'])} / {fmt_signed_pct(d20['median'])} / {fmt_signed_pct(d20['P10'])} / {fmt_signed_pct(d20['P90'])}",
        f"- D20 positive pct: {summary['D20_positive_pct']:.2f}%",
        "- 完整 skew/kurtosis 和分位数见 `core_horizon_statistics.csv`。",
        "",
        "## 3. D1-D20 路径",
        "- `percentile_path_close.csv`, `percentile_path_mfe.csv`, `percentile_path_mae.csv` 给出 D1-D20 mean/P5/P10/P25/P50/P75/P90/P95。",
        "- 图 05/06/07 分别为 close_ret, MFE, MAE 的独立 percentile path。",
        "",
        "## 4. MFE / MAE",
        f"- D10 MFE median: {fmt_signed_pct(summary['D10_MFE_median'])}",
        f"- D10 MAE median: {fmt_signed_pct(summary['D10_MAE_median'])}",
        f"- By D10, MFE >= +5% pct: {summary['MFE_plus_5_pct']['D10']:.2f}%",
        f"- By D10, MAE <= -5% pct: {summary['MAE_minus_5_pct']['D10']:.2f}%",
        "- extended hit-rate matrices 见 `mfe_hit_rate_extended.csv` 与 `mae_hit_rate_extended.csv`。",
        "",
        "## 5. 首次触及时间",
        f"- MFE +5% D10 cumulative pct: {first_mfe.loc[first_mfe['threshold'] == 0.05, 'D10_cumulative_pct'].iloc[0]:.2f}%",
        f"- MAE -5% D10 cumulative pct: {first_mae.loc[first_mae['threshold'] == -0.05, 'D10_cumulative_pct'].iloc[0]:.2f}%",
        "- 完整首次触及统计见 `first_hit_time_mfe.csv` 与 `first_hit_time_mae.csv`。",
        "",
        "## 6. 先跌后涨",
        f"- 样本中先触及 -10% 后后续交易日触及 0% 的比例: {summary['down_then_up']['-10_to_0_pct']:.2f}%。",
        f"- 样本中先触及 -10% 后后续交易日触及 +5% 的比例: {summary['down_then_up']['-10_to_5_pct']:.2f}%。",
        "- 这些是固定模板的路径顺序描述, 不是操作规则。",
        "",
        "## 7. 先涨后跌",
        f"- 样本中先触及 +10% 后后续交易日触及 0% 的比例: {summary['up_then_down']['+10_to_0_pct']:.2f}%。",
        "- 完整路径顺序表见 `up_then_down_path_stats.csv`。",
        "",
        "## 8. 早期浮亏与 D20",
        "- `mae_d3_to_d20_outcome_table.csv`, `mae_d5_to_d20_outcome_table.csv`, `mae_d10_to_d20_outcome_table.csv` 给出早期 MAE 分桶后的 D20 描述统计。",
        f"- 描述上, MAE_D10 最深桶 `<=-30%` 的 D20 median 为 {fmt_signed_pct(recovery[10].iloc[-1]['D20_close_median'])}。",
        "",
        "## 9. 早期浮盈与 D20",
        "- `early_mfe_to_d20_outcome.csv` 给出 MFE_D3/D5/D10 固定分桶后的 D20 描述统计。",
        "",
        "## 10. NEW_ENTRY / ADD_ON 分层",
        f"- NEW_ENTRY D20 median: {fmt_signed_pct(new['D20_close_median'])}; ADD_ON_4 D20 median: {fmt_signed_pct(add4['D20_close_median'])}。",
        f"- 描述上, NEW_ENTRY 与 ADD_ON_4 的 D10 MFE median 分别为 {fmt_signed_pct(new['D10_MFE_median'])} / {fmt_signed_pct(add4['D10_MFE_median'])}。",
        "- 这里只描述分层路径差异, 不推导配置。",
        "",
        "## 11. 年度稳定性",
        f"- 描述上 D20 median 最高年份: {int(year_best['signal_year'])} ({fmt_signed_pct(year_best['D20_close_median'])}); 最低年份: {int(year_worst['signal_year'])} ({fmt_signed_pct(year_worst['D20_close_median'])})。",
        "- NEW_ENTRY 年度表单独见 `new_entry_year_statistics.csv`。",
        "",
        "## 12. BB_z 描述性分桶",
        f"- 固定 BB_z 桶的 D20 median 序列: {bbz_trend}。",
        "- 该表只作 descriptive stratification。",
        "",
        "## 13. turnover rank 描述性分桶",
        f"- 固定 turnover_rank 桶的 D20 median 序列: {turnover_trend}。",
        "- 该表只描述 turnover_rank 分桶中的样本分布。",
        "",
        "## 14. 多层 episode",
        f"- 1 层 episode count: {int(ep1['episode_count'])}; NEW_ENTRY D20 median: {fmt_signed_pct(ep1['new_entry_D20_median'])}。",
        f"- 5 层 episode count: {int(ep5['episode_count'])}; NEW_ENTRY D20 median: {fmt_signed_pct(ep5['new_entry_D20_median'])}; last ADD_ON D20 median: {fmt_signed_pct(ep5['last_add_D20_median'])}。",
        "- 这里只有 episode 内路径描述, 不推导配置。",
        "",
        "## 15. 极端样本",
        f"- `manual_casebook.csv` 已生成, rows={len(casebook)}。包含 D20 worst/best, D10 MAE/MFE, 路径顺序模板, 5 层 episode, 以及接近总体中位数的普通样本。",
        "",
        "## 16. 数据限制",
        "- stock_name 在 namechange_full 有效区间覆盖时可作为 PIT 名称; 不能覆盖的 fallback/UNKNOWN 只用于人工定位。",
        "- industry_snapshot / list_date 是 NON-PIT manual-reference-only 字段。",
        "- 本报告没有输出买卖建议、参数选择或组合模拟。",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def count_pngs() -> int:
    return len(list(OUT.glob("*.png")))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    wide, long, manifest, raw_sha = verify_and_load()
    baseline = validate_baseline(wide, long)

    core = write_core_horizon_statistics(wide)
    paths = write_percentile_paths(wide)
    plot_percentile_path(paths["close_ret"], "Close Return Percentile Path", "05_close_percentile_path.png")
    plot_percentile_path(paths["MFE"], "MFE Percentile Path", "06_mfe_percentile_path.png")
    plot_percentile_path(paths["MAE"], "MAE Percentile Path", "07_mae_percentile_path.png")

    close_bins = write_close_distribution(wide)
    plot_close_hist(wide, 1, "01_close_hist_D1.png")
    plot_close_hist(wide, 5, "02_close_hist_D5.png")
    plot_close_hist(wide, 10, "03_close_hist_D10.png")
    plot_close_hist(wide, 20, "04_close_hist_D20.png")
    plot_close_hist(wide, 3, "close_hist_D3.png")

    mfe_hit = write_hit_rate_matrix(wide, "MFE")
    mae_hit = write_hit_rate_matrix(wide, "MAE")
    plot_hit_heatmap(mfe_hit, "MFE Hit Rate Heatmap", "08_mfe_hit_rate_heatmap.png")
    plot_hit_heatmap(mae_hit, "MAE Hit Rate Heatmap", "09_mae_hit_rate_heatmap.png")

    first_mfe, first_mae, mfe_first, mae_first = write_first_hit_stats(wide)
    plot_first_hit_distribution(mfe_first, "First Hit MFE Distribution", "15_first_hit_mfe_distribution.png")
    plot_first_hit_distribution(mae_first, "First Hit MAE Distribution", "16_first_hit_mae_distribution.png")

    down_up, up_down, masks = write_path_order_stats(wide)
    recovery = write_recovery_tables(wide)
    early_mfe = write_early_mfe_outcome(wide)
    role_stats = write_role_stats(wide)
    plot_group_median_path(wide, "entry_role", "close_ret", "Role Close Median Path", "10_role_close_median_path.png")
    plot_group_median_path(wide, "entry_role", "MFE", "Role MFE Median Path", "11_role_mfe_median_path.png")
    plot_group_median_path(wide, "entry_role", "MAE", "Role MAE Median Path", "12_role_mae_median_path.png")

    year_stats = write_year_stats(wide)
    new_year_stats = write_year_stats(wide, new_entry_only=True)
    wide_year = wide.copy()
    wide_year["signal_year"] = pd.to_datetime(wide_year["signal_date"]).dt.year
    plot_year_d20_distribution(wide_year)
    plot_group_median_path(wide_year, "signal_year", "close_ret", "Year Close Median Path", "13_year_close_median_path.png")

    bbz = write_bb_z_buckets(wide)
    turnover = write_turnover_rank_buckets(wide)
    episode = write_episode_layer_structure(wide)
    casebook = write_manual_casebook(wide, masks)
    plot_mae_d10_vs_d20_heatmap(wide)

    summary = write_summary(wide, raw_sha, baseline, down_up, up_down)
    summary["png_count"] = count_pngs()
    json_dump(OUT / "sigpath_d_summary.json", summary)
    write_report(
        summary,
        core,
        paths,
        mfe_hit,
        mae_hit,
        first_mfe,
        first_mae,
        down_up,
        up_down,
        recovery,
        early_mfe,
        role_stats,
        year_stats,
        new_year_stats,
        bbz,
        turnover,
        episode,
        casebook,
    )

    print("SIGPATH-D PASS")
    print(f"wide_sha_match={raw_sha['wide'] == manifest['wide']['sha256']}")
    print(f"long_sha_match={raw_sha['long'] == manifest['long']['sha256']}")
    print(f"total_signals={len(wide)}")
    print(f"png_count={count_pngs()}")


if __name__ == "__main__":
    main()
