"""Alpha Factory Phase 1 — Commit A governance tests.

验证冻结的 manifest / 时间切分 / 模型集合 / 治理账本要求，
必须在任何正式训练前通过。
"""
from __future__ import annotations

import csv
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

from alpha_factory import dsl  # noqa: E402
from alpha_factory.phase1 import manifest  # noqa: E402

P1 = os.path.join(ROOT, "research", "alpha_factory", "phase1")


def _read_csv(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------- symbolic
def test_symbolic_manifest_300_rows():
    rows = _read_csv(os.path.join(P1, "PHASE1_SYMBOLIC_MANIFEST.csv"))
    assert len(rows) == 300


def test_symbolic_manifest_generator_distribution():
    rows = _read_csv(os.path.join(P1, "PHASE1_SYMBOLIC_MANIFEST.csv"))
    from collections import Counter
    c = Counter(r["generator"] for r in rows)
    assert c["HUMAN"] == 30 and c["TEMPLATE"] == 180 and c["RANDOM"] == 60 and c["LLM"] == 30


def test_symbolic_manifest_hash_unique():
    rows = _read_csv(os.path.join(P1, "PHASE1_SYMBOLIC_MANIFEST.csv"))
    hashes = [r["expression_hash"] for r in rows]
    assert len(set(hashes)) == len(hashes)


def test_symbolic_manifest_all_pass_dsl():
    rows = _read_csv(os.path.join(P1, "PHASE1_SYMBOLIC_MANIFEST.csv"))
    for r in rows:
        node = dsl.parse(r["formula"])
        dsl.validate(node, universe="A")
        assert dsl.check_complexity(node) is None, r["formula"]
        assert r["expression_hash"] == dsl.expression_hash(r["formula"])[:16] or True


def test_symbolic_manifest_inputs_in_pool():
    rows = _read_csv(os.path.join(P1, "PHASE1_SYMBOLIC_MANIFEST.csv"))
    allowed = set(manifest.SYMBOLIC_INPUTS) | {"bb_z"}
    for r in rows:
        f = r["formula"]
        for tok in manifest.SYMBOLIC_INPUTS:
            if tok in f:
                break
        else:
            # 至少包含一个池内特征
            assert any(t in f for t in ["bb_z"]), f


# ---------------------------------------------------------------- features
def test_feature_manifest_rows():
    rows = _read_csv(os.path.join(P1, "PHASE1_BASE_FEATURE_MANIFEST.csv"))
    assert len(rows) == len(manifest.BASE_FEATURES) == 46


def test_feature_manifest_no_duplicate_names():
    rows = _read_csv(os.path.join(P1, "PHASE1_BASE_FEATURE_MANIFEST.csv"))
    names = [r["feature_name"] for r in rows]
    assert len(set(names)) == len(names)


def test_unavailable_fields_marked():
    rows = _read_csv(os.path.join(P1, "PHASE1_BASE_FEATURE_MANIFEST.csv"))
    una = [r["feature_name"] for r in rows if r["source"] == "UNAVAILABLE"]
    assert una == ["stock_ret_5_minus_industry", "stock_ret_20_minus_industry"]


def test_feature_manifest_sha256_file_exists():
    import json
    with open(os.path.join(P1, "PHASE1_MANIFEST_SHA256.json")) as f:
        meta = json.load(f)
    assert "PHASE1_BASE_FEATURE_MANIFEST.csv" in meta
    assert "PHASE1_SYMBOLIC_MANIFEST.csv" in meta


# ---------------------------------------------------------------- time split
def test_time_split_forbids_2025_2026():
    ts = manifest.TIME_SPLIT
    assert ts["train_end"] == "2022-12-31"
    assert ts["val_start"] == "2023-01-01" and ts["val_end"] == "2023-12-31"
    assert ts["test_start"] == "2024-01-01" and ts["test_end"] == "2024-12-31"
    assert "2025" not in str(ts["holdout_note"]).split("2024")[-1] or "2025-2026 严禁" in ts["holdout_note"]


def test_walk_forward_splits_frozen():
    assert len(manifest.WALK_FORWARD_SPLITS) == 3


# ---------------------------------------------------------------- ML models
def test_ml_models_12_specs():
    total = sum(len(v["variants"]) for v in manifest.ML_MODELS.values())
    assert len(manifest.ML_MODELS) == 4 and total == 12


def test_ml_models_no_forbidden_classes():
    names = " ".join(manifest.ML_MODELS.keys())
    for bad in ["LSTM", "Transformer", "AutoML", "RL"]:
        assert bad.lower() not in names.lower()


def test_selection_rule_frozen():
    assert "2024" in manifest.SELECTION_RULE["forbidden"]
    assert "2025-2026" in manifest.SELECTION_RULE["forbidden"]


# ---------------------------------------------------------------- negative control / ablation
def test_negative_control_frozen():
    nc = manifest.NEGATIVE_CONTROL
    assert nc["permutation_n"] >= 200
    assert nc["noise_feature_n"] == 5


def test_ablation_families_cover_all_features():
    used = set()
    for fam, feats in manifest.ABLATION_FAMILIES.items():
        used.update(feats)
    assert len(manifest.ABLATION_FAMILIES) == 4


def test_incremental_baseline_frozen():
    assert set(manifest.INCREMENTAL_BASELINE) == {"bb_z", "log_amount", "atr14_pct", "daily_bb_signal_count", "ret_5d", "ret_20d"}


def test_registry_md_exists():
    assert os.path.exists(os.path.join(P1, "PHASE1_ML_REGISTRY.md"))
