"""
SIGPATH-C bookkeeping cleanup.

This script only reads the existing SIGPATH raw outputs and writes audit
manifests. It does not rebuild signals, test parameters, classify regimes, or
read 2025+ market data.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO.parents[1]
OUT = REPO / "results" / "evidence" / "sigpath"
BOUNDARY = pd.Timestamp("2024-12-31")
EXPECTED_WIDE_ROWS = 157_469
EXPECTED_NEW_ENTRY = 63_887
EXPECTED_ADD_ON = 93_582
EXPECTED_ROLE_COUNTS = {
    "NEW_ENTRY": 63_887,
    "ADD_ON_1": 42_105,
    "ADD_ON_2": 25_652,
    "ADD_ON_3": 15_828,
    "ADD_ON_4": 9_997,
}
EXPECTED_SHORT_HISTORY = 3_135
EXPECTED_MISSING_HORIZON_ROWS = 43_031
HORIZON = 20
VALUE_ATOL = 1e-10
VALUE_RTOL = 1e-10
VALUE_FIELDS = ["open", "high", "low", "close", "open_ret", "high_ret", "low_ret", "close_ret", "MFE", "MAE"]
NAMECHANGE_PATH = SOURCE_ROOT / "data" / "raw" / "namechange_full.parquet"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_rev(rev: str) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", rev], cwd=REPO, text=True
    ).strip()


def git_subject(rev: str) -> str:
    return subprocess.check_output(
        ["git", "show", "--no-patch", "--format=%s", rev], cwd=REPO, text=True
    ).strip()


def git_commit_info(rev: str) -> dict[str, Any]:
    if not git_exists(rev):
        return {"exists": False}
    raw = subprocess.check_output(
        ["git", "show", "--no-patch", "--format=%H%n%ad%n%s", "--date=iso-strict", rev],
        cwd=REPO,
        text=True,
    ).splitlines()
    return {"exists": True, "full_sha": raw[0], "date": raw[1], "subject": raw[2]}


def git_remote_branches_containing(rev: str) -> list[str]:
    if not git_exists(rev):
        return []
    out = subprocess.check_output(["git", "branch", "-r", "--contains", rev], cwd=REPO, text=True)
    return [line.strip() for line in out.splitlines() if line.strip()]


def git_is_ancestor(ancestor: str, descendant: str) -> bool:
    if not git_exists(ancestor) or not git_exists(descendant):
        return False
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=REPO,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )


def git_exists(rev: str) -> bool:
    return (
        subprocess.run(
            ["git", "cat-file", "-e", f"{rev}^{{commit}}"],
            cwd=REPO,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )


def build_lineage() -> dict[str, Any]:
    canonical_b = "974fa2aef6fd9284ce50163d0d68a4fb13d3697e"
    bc = git_commit_info("bc7e989")
    if bc["exists"]:
        bc["remote_branches_containing"] = git_remote_branches_containing("bc7e989")
        bc["is_ancestor_of_canonical_SIGPATH_B"] = git_is_ancestor("bc7e989", canonical_b)
        bc["role"] = (
            "local preliminary SIGPATH-B result commit that added/tracked large CSV "
            "partitions and intermediate raw CSV audit files before the data-size "
            "policy cleanup; it is not the canonical GitHub result commit because "
            "origin/master contains the later data-policy result commit 974fa2a..., "
            "where wide/long raw tables are kept local and tracked Git artifacts are "
            "stats, sanity, charts, metadata, README, and generation code"
        )
    return {
        "SIGPATH-A": git_rev("94bd041"),
        "SIGPATH-A2": git_rev("8bb98867988bf2b8d3d0304974391ec9276a72ba"),
        "SIGPATH-A3": git_rev("ea36927"),
        "SIGPATH-B": git_rev(canonical_b),
        "erroneous_historical_references": {
            "483e72b7": {
                "exists": git_exists("483e72b7"),
                "status": "erroneous historical reference; no commit object exists in this repository",
            },
            "bc7e989": bc,
        },
    }


def json_dump(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def parquet_manifest(path: Path, df: pd.DataFrame, kind: str, signals: int | None = None) -> dict[str, Any]:
    null_counts = {k: int(v) for k, v in df.isna().sum().items()}
    manifest: dict[str, Any] = {
        "filename": path.name,
        "sha256": sha256_file(path),
        "bytes": int(path.stat().st_size),
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "column_names": list(df.columns),
        "schema_dtypes": {c: str(t) for c, t in df.dtypes.items()},
        "per_column_null_count": null_counts,
    }
    if kind == "wide":
        signal_unique = int(df["signal_id"].nunique(dropna=False))
        manifest.update(
            {
                "signal_id_unique_count": signal_unique,
                "duplicate_signal_id_count": int(len(df) - signal_unique),
                "min_signal_date": str(pd.to_datetime(df["signal_date"]).min().date()),
                "max_signal_date": str(pd.to_datetime(df["signal_date"]).max().date()),
                "min_entry_date": str(pd.to_datetime(df["entry_date"]).min().date()),
                "max_entry_date": str(pd.to_datetime(df["entry_date"]).max().date()),
                "total_null_cells": int(sum(null_counts.values())),
            }
        )
    elif kind == "long":
        signal_unique = int(df["signal_id"].nunique(dropna=False))
        duplicate_key_count = int(df.duplicated(["signal_id", "horizon_day"]).sum())
        manifest.update(
            {
                "unique_signal_id": signal_unique,
                "expected_rows_signals_x_20": int((signals or signal_unique) * HORIZON),
                "duplicate_key_count_signal_id_horizon_day": duplicate_key_count,
                "min_trade_date": str(pd.to_datetime(df["trade_date"]).min().date()),
                "max_trade_date": str(pd.to_datetime(df["trade_date"]).max().date()),
                "total_null_cells": int(sum(null_counts.values())),
            }
        )
    else:
        raise ValueError(kind)
    return manifest


def csv_part_manifest() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(OUT.glob("signal_path_20d_*.csv.part_*")):
        with path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            count = 0
            first_signal_id = None
            last_signal_id = None
            for row in reader:
                sid = row["signal_id"]
                if first_signal_id is None:
                    first_signal_id = sid
                last_signal_id = sid
                count += 1
        rows.append(
            {
                "filename": path.name,
                "sha256": sha256_file(path),
                "bytes": int(path.stat().st_size),
                "rows": int(count),
                "first_signal_id": first_signal_id,
                "last_signal_id": last_signal_id,
            }
        )
    return rows


def write_csv_part_manifest(rows: list[dict[str, Any]]) -> None:
    out = OUT / "raw_partition_manifest.csv"
    fields = ["filename", "sha256", "bytes", "rows", "first_signal_id", "last_signal_id"]
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def assert_item(name: str, actual: Any, expected: Any) -> dict[str, Any]:
    passed = actual == expected
    return {"name": name, "actual": actual, "expected": expected, "pass": bool(passed)}


def build_cross_table_parity(wide: pd.DataFrame, long: pd.DataFrame) -> dict[str, Any]:
    summary_path = OUT / "sigpath_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    role_counts = {k: int(v) for k, v in wide["entry_role"].value_counts().sort_index().items()}
    unique_pairs = int(long.drop_duplicates(["signal_id", "horizon_day"]).shape[0])

    horizon_set = set(int(x) for x in long["horizon_day"].dropna().unique())
    horizon_by_signal = long.groupby("signal_id")["horizon_day"].agg(["count", "nunique", "min", "max"])
    horizon_exact = bool(
        horizon_set == set(range(1, HORIZON + 1))
        and (horizon_by_signal["count"] == HORIZON).all()
        and (horizon_by_signal["nunique"] == HORIZON).all()
        and (horizon_by_signal["min"] == 1).all()
        and (horizon_by_signal["max"] == HORIZON).all()
    )

    checks = [
        assert_item("wide_rows", int(len(wide)), EXPECTED_WIDE_ROWS),
        assert_item("wide_unique_signal_id", int(wide["signal_id"].nunique(dropna=False)), EXPECTED_WIDE_ROWS),
        assert_item("long_rows", int(len(long)), EXPECTED_WIDE_ROWS * HORIZON),
        assert_item("long_unique_signal_id_horizon_day", unique_pairs, int(len(long))),
        assert_item("horizon_day_exactly_1_to_20_for_every_signal", horizon_exact, True),
        assert_item("NEW_ENTRY", int(role_counts.get("NEW_ENTRY", 0)), EXPECTED_NEW_ENTRY),
        assert_item("ADD_ON_total", int(len(wide) - role_counts.get("NEW_ENTRY", 0)), EXPECTED_ADD_ON),
    ]
    for role, expected in EXPECTED_ROLE_COUNTS.items():
        checks.append(assert_item(f"role_count_{role}", int(role_counts.get(role, 0)), expected))
    if summary:
        checks.extend(
            [
                assert_item("summary_wide_rows", int(summary.get("wide_rows")), int(len(wide))),
                assert_item("summary_long_rows", int(summary.get("long_rows")), int(len(long))),
                assert_item("summary_n_new_entry", int(summary.get("n_new_entry")), EXPECTED_NEW_ENTRY),
                assert_item("summary_n_add_on", int(summary.get("n_add_on")), EXPECTED_ADD_ON),
            ]
        )
        for role in ("ADD_ON_1", "ADD_ON_2", "ADD_ON_3", "ADD_ON_4"):
            key = "n_" + role.lower()
            checks.append(assert_item(f"summary_{key}", int(summary.get(key)), EXPECTED_ROLE_COUNTS[role]))

    report = {
        "phase": "SIGPATH-C",
        "scope": "bookkeeping_only_no_strategy_recalculation",
        "checks": checks,
        "role_counts": role_counts,
        "pass": bool(all(c["pass"] for c in checks)),
    }
    if not report["pass"]:
        raise AssertionError(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def build_missing_horizon(wide: pd.DataFrame, long: pd.DataFrame) -> list[dict[str, Any]]:
    available = wide[["signal_id", "available_future_days", "data_quality_flag"]].copy()
    available["available_future_days"] = available["available_future_days"].astype(int)
    merged = long[["signal_id", "horizon_day", "trade_date", "open", "high", "low", "close"]].merge(
        available[["signal_id", "available_future_days"]],
        on="signal_id",
        how="left",
        validate="many_to_one",
    )
    missing_row = merged["trade_date"].isna()
    expected_missing_row = merged["horizon_day"] > merged["available_future_days"]
    non_missing_row = ~missing_row
    ohlc_missing_any = merged[["open", "high", "low", "close"]].isna().any(axis=1)
    ohlc_missing_all = merged[["open", "high", "low", "close"]].isna().all(axis=1)

    flags = wide["data_quality_flag"].fillna("").astype(str)
    short_history_exact_count = int((flags == "SHORT_HISTORY").sum())
    short_history_any_count = int(flags.str.contains("SHORT_HISTORY", regex=False).sum())
    short_history_overlap_count = int((flags == "JUMP;SHORT_HISTORY").sum())
    missing_horizon_rows = int(missing_row.sum())
    join_loss_count = int((missing_row != expected_missing_row).sum())
    ohlc_gap_count = int((non_missing_row & ohlc_missing_any).sum())
    missing_not_all_null_count = int((missing_row & ~ohlc_missing_all).sum())

    checks = [
        assert_item("SHORT_HISTORY_exact_flag_signals", short_history_exact_count, EXPECTED_SHORT_HISTORY),
        assert_item("long_NaN_horizon_rows", missing_horizon_rows, EXPECTED_MISSING_HORIZON_ROWS),
        assert_item("missing_rows_match_available_future_days", join_loss_count, 0),
        assert_item("non_missing_horizon_has_complete_ohlc", ohlc_gap_count, 0),
        assert_item("missing_horizon_ohlc_all_null", missing_not_all_null_count, 0),
    ]
    if not all(c["pass"] for c in checks):
        raise AssertionError(json.dumps({"checks": checks}, ensure_ascii=False, indent=2))

    rows: list[dict[str, Any]] = []
    for afd, g in available.groupby("available_future_days", sort=True):
        signal_count = int(len(g))
        expected_missing = int(signal_count * max(0, HORIZON - int(afd)))
        actual_missing = int(merged.loc[merged["available_future_days"] == int(afd), "trade_date"].isna().sum())
        rows.append(
            {
                "available_future_days": int(afd),
                "signal_count": signal_count,
                "expected_missing_rows": expected_missing,
                "actual_missing_rows": actual_missing,
                "parity": bool(expected_missing == actual_missing),
            }
        )
    checks.append(
        {
            "name": "SHORT_HISTORY_any_flag_or_available_lt_20_signals",
            "actual": short_history_any_count,
            "expected": "informational: includes JUMP;SHORT_HISTORY overlap",
            "pass": True,
        }
    )
    checks.append(
        {
            "name": "JUMP_SHORT_HISTORY_overlap_signals",
            "actual": short_history_overlap_count,
            "expected": "informational",
            "pass": True,
        }
    )
    with (OUT / "missing_horizon_by_available_days.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "available_future_days",
                "signal_count",
                "expected_missing_rows",
                "actual_missing_rows",
                "parity",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return checks


def numeric_compare(a: pd.Series, b: pd.Series) -> tuple[int, float]:
    av = a.to_numpy(dtype=float)
    bv = b.to_numpy(dtype=float)
    a_nan = np.isnan(av)
    b_nan = np.isnan(bv)
    nan_mismatch = a_nan != b_nan
    finite = ~a_nan & ~b_nan
    mismatch = int(nan_mismatch.sum())
    max_abs_diff = 0.0
    if finite.any():
        diff = np.abs(av[finite] - bv[finite])
        tol = VALUE_ATOL + VALUE_RTOL * np.abs(bv[finite])
        mismatch += int((diff > tol).sum())
        if len(diff):
            max_abs_diff = float(np.max(diff))
    return mismatch, max_abs_diff


def date_compare(a: pd.Series, b: pd.Series) -> int:
    av = pd.to_datetime(a, errors="coerce").to_numpy(dtype="datetime64[ns]").view("int64")
    bv = pd.to_datetime(b, errors="coerce").to_numpy(dtype="datetime64[ns]").view("int64")
    return int((av != bv).sum())


def build_wide_long_value_parity(wide: pd.DataFrame, long: pd.DataFrame) -> dict[str, Any]:
    signal_ids = wide["signal_id"].to_numpy()
    long_idx = long.set_index(["signal_id", "horizon_day"], drop=False)
    date_mismatch_count = 0
    value_mismatch_count = 0
    max_abs_diff_by_field = {field: 0.0 for field in VALUE_FIELDS}
    mismatch_count_by_field = {"trade_date": 0, **{field: 0 for field in VALUE_FIELDS}}
    missing_long_rows = 0

    for horizon in range(1, HORIZON + 1):
        lh = long_idx.xs(horizon, level="horizon_day").reindex(signal_ids)
        missing_long_rows += int(lh["signal_id"].isna().sum())

        d_mismatch = date_compare(wide[f"trade_date_D{horizon}"], lh["trade_date"])
        date_mismatch_count += d_mismatch
        mismatch_count_by_field["trade_date"] += d_mismatch

        for field in VALUE_FIELDS:
            mismatch, max_abs_diff = numeric_compare(wide[f"{field}_D{horizon}"], lh[field])
            value_mismatch_count += mismatch
            mismatch_count_by_field[field] += mismatch
            max_abs_diff_by_field[field] = max(max_abs_diff_by_field[field], max_abs_diff)

    rows_checked = int(len(wide) * HORIZON)
    cells_checked = int(rows_checked * (1 + len(VALUE_FIELDS)))
    report = {
        "phase": "SIGPATH-C",
        "scope": "full_wide_long_value_parity_no_sampling",
        "signals_checked": int(len(wide)),
        "rows_checked": rows_checked,
        "cells_checked": cells_checked,
        "date_mismatch_count": int(date_mismatch_count),
        "value_mismatch_count": int(value_mismatch_count),
        "missing_long_rows_after_alignment": int(missing_long_rows),
        "mismatch_count_by_field": mismatch_count_by_field,
        "max_abs_diff_by_field": max_abs_diff_by_field,
        "atol": VALUE_ATOL,
        "rtol": VALUE_RTOL,
        "PASS": bool(date_mismatch_count == 0 and value_mismatch_count == 0 and missing_long_rows == 0),
    }
    json_dump(OUT / "wide_long_value_parity.json", report)
    if not report["PASS"]:
        raise AssertionError(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def formula_compare(actual: np.ndarray, expected: np.ndarray) -> tuple[int, float]:
    actual_nan = np.isnan(actual)
    expected_nan = np.isnan(expected)
    finite = ~actual_nan & ~expected_nan
    mismatch = int((actual_nan != expected_nan).sum())
    max_abs_diff = 0.0
    if finite.any():
        diff = np.abs(actual[finite] - expected[finite])
        tol = VALUE_ATOL + VALUE_RTOL * np.abs(expected[finite])
        mismatch += int((diff > tol).sum())
        max_abs_diff = float(np.max(diff))
    return mismatch, max_abs_diff


def build_path_math_invariants(wide: pd.DataFrame) -> dict[str, Any]:
    high_ret = np.column_stack([wide[f"high_ret_D{h}"].to_numpy(dtype=float) for h in range(1, HORIZON + 1)])
    low_ret = np.column_stack([wide[f"low_ret_D{h}"].to_numpy(dtype=float) for h in range(1, HORIZON + 1)])
    mfe = np.column_stack([wide[f"MFE_D{h}"].to_numpy(dtype=float) for h in range(1, HORIZON + 1)])
    mae = np.column_stack([wide[f"MAE_D{h}"].to_numpy(dtype=float) for h in range(1, HORIZON + 1)])

    mfe_pairs = np.isfinite(mfe[:, 1:]) & np.isfinite(mfe[:, :-1])
    mae_pairs = np.isfinite(mae[:, 1:]) & np.isfinite(mae[:, :-1])
    mfe_mono_mask = mfe_pairs & ((mfe[:, 1:] - mfe[:, :-1]) < -(VALUE_ATOL + VALUE_RTOL * np.abs(mfe[:, :-1])))
    mae_mono_mask = mae_pairs & ((mae[:, 1:] - mae[:, :-1]) > (VALUE_ATOL + VALUE_RTOL * np.abs(mae[:, :-1])))

    high_fill = np.where(np.isnan(high_ret), -np.inf, high_ret)
    low_fill = np.where(np.isnan(low_ret), np.inf, low_ret)
    expected_mfe = np.maximum.accumulate(high_fill, axis=1)
    expected_mae = np.minimum.accumulate(low_fill, axis=1)
    expected_mfe[expected_mfe == -np.inf] = np.nan
    expected_mae[expected_mae == np.inf] = np.nan

    mfe_formula_violations, mfe_max_diff = formula_compare(mfe, expected_mfe)
    mae_formula_violations, mae_max_diff = formula_compare(mae, expected_mae)
    report = {
        "phase": "SIGPATH-C",
        "scope": "full_mfe_mae_math_invariants_no_sampling",
        "signals_checked": int(len(wide)),
        "cells_checked_per_array": int(len(wide) * HORIZON),
        "mfe_monotonic_violations": int(mfe_mono_mask.sum()),
        "mae_monotonic_violations": int(mae_mono_mask.sum()),
        "mfe_monotonic_signal_violations": int(mfe_mono_mask.any(axis=1).sum()),
        "mae_monotonic_signal_violations": int(mae_mono_mask.any(axis=1).sum()),
        "mfe_formula_violations": int(mfe_formula_violations),
        "mae_formula_violations": int(mae_formula_violations),
        "mfe_formula_signal_violations": int(((np.isnan(mfe) != np.isnan(expected_mfe)) | (np.abs(np.nan_to_num(mfe - expected_mfe, nan=0.0)) > VALUE_ATOL)).any(axis=1).sum()),
        "mae_formula_signal_violations": int(((np.isnan(mae) != np.isnan(expected_mae)) | (np.abs(np.nan_to_num(mae - expected_mae, nan=0.0)) > VALUE_ATOL)).any(axis=1).sum()),
        "max_abs_formula_diff": float(max(mfe_max_diff, mae_max_diff)),
        "atol": VALUE_ATOL,
        "rtol": VALUE_RTOL,
        "PASS": bool(
            int(mfe_mono_mask.sum()) == 0
            and int(mae_mono_mask.sum()) == 0
            and mfe_formula_violations == 0
            and mae_formula_violations == 0
        ),
    }
    json_dump(OUT / "path_math_invariants.json", report)
    if not report["PASS"]:
        raise AssertionError(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def build_manual_index_parity(wide: pd.DataFrame) -> dict[str, Any]:
    manual = pd.read_csv(OUT / "manual_review_index.csv", dtype={"signal_id": "string"})
    manual_ids = set(manual["signal_id"].dropna().astype(str))
    wide_ids = set(wide["signal_id"].dropna().astype(str))
    report = {
        "phase": "SIGPATH-C",
        "scope": "manual_index_signal_id_parity",
        "rows": int(len(manual)),
        "unique_signal_id": int(manual["signal_id"].nunique(dropna=False)),
        "duplicate_signal_id": int(manual["signal_id"].duplicated().sum()),
        "missing_from_manual": int(len(wide_ids - manual_ids)),
        "extra_in_manual": int(len(manual_ids - wide_ids)),
        "PASS": bool(
            len(manual) == EXPECTED_WIDE_ROWS
            and manual["signal_id"].nunique(dropna=False) == EXPECTED_WIDE_ROWS
            and manual["signal_id"].duplicated().sum() == 0
            and manual_ids == wide_ids
        ),
    }
    json_dump(OUT / "manual_index_parity.json", report)
    if not report["PASS"]:
        raise AssertionError(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def parse_yyyymmdd(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series.astype("string").str.strip(), format="%Y%m%d", errors="coerce")


def unknown_count(series: pd.Series) -> int:
    text = series.fillna("UNKNOWN").astype(str).str.strip()
    return int((text == "UNKNOWN").sum() + (text == "").sum())


def build_pit_name_audit(wide: pd.DataFrame) -> dict[str, Any]:
    manual = pd.read_csv(OUT / "manual_review_index.csv", dtype={"signal_id": "string", "stock_name": "string"})
    if not NAMECHANGE_PATH.exists():
        raise FileNotFoundError(NAMECHANGE_PATH)
    namechange = pd.read_parquet(NAMECHANGE_PATH)
    nc = namechange[["ts_code", "name", "start_date", "end_date"]].copy()
    nc["start_ts"] = parse_yyyymmdd(nc["start_date"])
    nc["end_ts"] = parse_yyyymmdd(nc["end_date"])

    w = wide[["signal_id", "ts_code", "stock_code", "stock_name", "signal_date", "industry_snapshot", "list_date"]].copy()
    w["signal_ts"] = pd.to_datetime(w["signal_date"], errors="coerce")
    changed_codes = set(nc.groupby("ts_code")["name"].nunique().loc[lambda s: s > 1].index)
    with_name_history = set(nc["ts_code"].unique())
    w_hist = w[w["ts_code"].isin(with_name_history)].copy()
    merged = w_hist.merge(nc, on="ts_code", how="left")
    in_interval = (merged["signal_ts"] >= merged["start_ts"]) & (
        merged["end_ts"].isna() | (merged["signal_ts"] <= merged["end_ts"])
    )
    matched = merged[in_interval].copy()
    match_counts = matched.groupby("signal_id").size()
    interval_missing = int(len(w_hist) - match_counts.index.nunique())
    multiple_interval_matches = int((match_counts > 1).sum())
    matched_first = matched.sort_values(["signal_id", "start_ts"]).drop_duplicates("signal_id", keep="first")
    name_mismatch = int((matched_first["stock_name"].astype(str) != matched_first["name"].astype(str)).sum())

    manual_wide = manual[["signal_id", "stock_name"]].merge(
        w[["signal_id", "stock_name"]],
        on="signal_id",
        how="outer",
        suffixes=("_manual", "_wide"),
        indicator=True,
    )
    manual_wide_mismatches = int(
        (
            (manual_wide["_merge"] != "both")
            | (manual_wide["stock_name_manual"].fillna("").astype(str) != manual_wide["stock_name_wide"].fillna("").astype(str))
        ).sum()
    )

    random_pool = sorted((changed_codes & set(w["ts_code"].unique())) - {"300116.SZ", "300156.SZ"})
    rng = np.random.default_rng(42)
    random_codes = list(rng.choice(random_pool, size=min(8, len(random_pool)), replace=False)) if random_pool else []
    sample_codes = ["300116.SZ", "300156.SZ"] + sorted(random_codes)
    sample_rows: list[dict[str, Any]] = []
    sample_matched = matched_first[matched_first["ts_code"].isin(sample_codes)].copy()
    for (tc, name, start_date, end_date), g in sample_matched.groupby(
        ["ts_code", "name", "start_date", "end_date"], dropna=False, sort=True
    ):
        start = parse_yyyymmdd(pd.Series([start_date])).iloc[0]
        end = parse_yyyymmdd(pd.Series([end_date])).iloc[0]
        min_signal = g["signal_ts"].min()
        max_signal = g["signal_ts"].max()
        interval_pass = bool(min_signal >= start and (pd.isna(end) or max_signal <= end))
        sample_rows.append(
            {
                "ts_code": tc,
                "stock_name": name,
                "namechange_start_date": str(start.date()) if pd.notna(start) else None,
                "namechange_end_date": None if pd.isna(end) else str(end.date()),
                "signal_count": int(len(g)),
                "min_signal_date": str(min_signal.date()),
                "max_signal_date": str(max_signal.date()),
                "interval_pass": interval_pass,
            }
        )

    wide_unknown = unknown_count(w["stock_name"])
    manual_unknown = unknown_count(manual["stock_name"])
    report = {
        "phase": "SIGPATH-C",
        "scope": "pit_name_audit_no_raw_modification",
        "field_semantics": {
            "stock_name": "PIT as-of signal_date only when signal_date matches a namechange_full.parquet effective interval; otherwise fallback stock_basic current name is not PIT and is manual-reference-only; UNKNOWN retained",
            "industry_snapshot": "NON-PIT; current stock_basic field; manual-reference-only",
            "list_date": "NON-PIT/current stock_basic metadata in this artifact; manual-reference-only",
        },
        "wide_rows": int(len(w)),
        "wide_UNKNOWN_stock_name_count": wide_unknown,
        "wide_UNKNOWN_stock_name_pct": float(wide_unknown / len(w) * 100),
        "manual_rows": int(len(manual)),
        "manual_UNKNOWN_stock_name_count": manual_unknown,
        "manual_UNKNOWN_stock_name_pct": float(manual_unknown / len(manual) * 100),
        "manual_wide_stock_name_mismatch_count": manual_wide_mismatches,
        "namechange_rows": int(len(nc)),
        "signals_with_namechange_history_checked": int(len(w_hist)),
        "signals_with_interval_match": int(match_counts.index.nunique()),
        "interval_missing_count": interval_missing,
        "interval_missing_interpretation": "signal_date predates first available namechange_full interval for that ts_code; raw stock_name cannot be proven PIT for these rows and is treated as stock_basic fallback/manual-reference-only",
        "multiple_interval_match_count": multiple_interval_matches,
        "name_mismatch_count": name_mismatch,
        "mandatory_codes_checked": ["300116.SZ", "300156.SZ"],
        "random_changed_codes_checked": sorted(random_codes),
        "sample_interval_checks": sample_rows,
        "PASS": bool(
            len(w) == EXPECTED_WIDE_ROWS
            and len(manual) == EXPECTED_WIDE_ROWS
            and manual_wide_mismatches == 0
            and interval_missing == 0
            and multiple_interval_matches == 0
            and name_mismatch == 0
            and {"300116.SZ", "300156.SZ"}.issubset(set(sample_matched["ts_code"].unique()))
            and all(row["interval_pass"] for row in sample_rows)
        ),
    }
    json_dump(OUT / "pit_name_audit.json", report)
    return report


def date_like_columns(df: pd.DataFrame) -> list[str]:
    out: list[str] = []
    for col in df.columns:
        cl = col.lower()
        if "date" in cl or cl.endswith("_dt") or cl.startswith("dt_"):
            out.append(col)
    return out


def parse_dates(series: pd.Series) -> pd.Series:
    non_null = series.dropna()
    if non_null.empty:
        return pd.to_datetime(series, errors="coerce")
    as_string = non_null.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    digit8 = as_string.str.fullmatch(r"\d{8}").mean() >= 0.95
    if digit8:
        parsed_non_null = pd.to_datetime(as_string, format="%Y%m%d", errors="coerce")
        parsed = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
        parsed.loc[non_null.index] = parsed_non_null.to_numpy()
        return parsed
    return pd.to_datetime(series, errors="coerce")


def scan_date_boundaries(frames: dict[str, pd.DataFrame]) -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    total_gt = 0
    for name, df in frames.items():
        for col in date_like_columns(df):
            parsed = parse_dates(df[col])
            valid = parsed.dropna()
            gt = int((valid > BOUNDARY).sum())
            total_gt += gt
            fields.append(
                {
                    "table": name,
                    "column": col,
                    "rows": int(len(df)),
                    "parsed_non_null": int(len(valid)),
                    "null_or_unparseable": int(len(df) - len(valid)),
                    "min": None if valid.empty else str(valid.min().date()),
                    "max": None if valid.empty else str(valid.max().date()),
                    "gt_2024_12_31_count": gt,
                    "pass": bool(gt == 0),
                }
            )
    report = {
        "boundary": "2024-12-31",
        "scanned_tables": list(frames.keys()),
        "date_like_fields": fields,
        "gt_boundary_count": int(total_gt),
        "pass": bool(total_gt == 0),
    }
    if not report["pass"]:
        raise AssertionError(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def load_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def main() -> None:
    wide_path = OUT / "signal_path_20d_wide.parquet"
    long_path = OUT / "signal_path_20d_long.parquet"
    wide = pd.read_parquet(wide_path)
    long = pd.read_parquet(long_path)

    csv_parts = csv_part_manifest()
    raw_manifest = {
        "phase": "SIGPATH-C",
        "scope": "bookkeeping_cleanup_only",
        "lineage": build_lineage(),
        "wide": parquet_manifest(wide_path, wide, "wide"),
        "long": parquet_manifest(long_path, long, "long", signals=int(wide["signal_id"].nunique(dropna=False))),
        "csv_part_files": csv_parts,
    }
    json_dump(OUT / "raw_data_manifest.json", raw_manifest)
    write_csv_part_manifest(csv_parts)

    cross = build_cross_table_parity(wide, long)
    json_dump(OUT / "cross_table_parity.json", cross)

    short_history_checks = build_missing_horizon(wide, long)

    wide_long_value = build_wide_long_value_parity(wide, long)
    path_math = build_path_math_invariants(wide)
    manual_index = build_manual_index_parity(wide)
    pit_name = build_pit_name_audit(wide)

    frames = {
        "wide": wide,
        "long": long,
        "layers": load_csv_if_exists(OUT / "sigpath_layers_raw.csv"),
        "episodes": load_csv_if_exists(OUT / "sigpath_episodes_parity.csv"),
        "manual_index": load_csv_if_exists(OUT / "manual_review_index.csv"),
    }
    date_report = scan_date_boundaries(frames)
    date_report["short_history_checks"] = short_history_checks
    json_dump(OUT / "date_boundary_audit.json", date_report)

    all_pass = bool(
        cross["pass"]
        and wide_long_value["PASS"]
        and path_math["PASS"]
        and manual_index["PASS"]
        and pit_name["PASS"]
        and date_report["pass"]
    )
    if not all_pass:
        raise AssertionError("SIGPATH-C HOLD")

    print("SIGPATH-C bookkeeping PASS")
    print(f"wide_sha256={raw_manifest['wide']['sha256']}")
    print(f"long_sha256={raw_manifest['long']['sha256']}")
    print(f"wide_rows={raw_manifest['wide']['rows']}")
    print(f"long_rows={raw_manifest['long']['rows']}")
    print("wide_long_value_parity=PASS")
    print("path_math_invariants=PASS")
    print("manual_index_parity=PASS")
    print("pit_name_audit=PASS")
    print("date_boundary=PASS")


if __name__ == "__main__":
    main()
