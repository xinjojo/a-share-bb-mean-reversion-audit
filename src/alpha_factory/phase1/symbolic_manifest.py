"""Alpha Factory Phase 1 — Symbolic Manifest 生成器（Commit A）。

生成 research/alpha_factory/phase1/PHASE1_SYMBOLIC_MANIFEST.csv：
300 个冻结请求 = 30 Human + 180 Template + 60 Random(seed) + 30 LLM。

所有表达式：
- 只使用 PHASE1 特征池（manifest.SYMBOLIC_INPUTS）+ DSL 白名单算子
- 通过 dsl.validate(universe='A') + complexity budget
- 唯一 canonical hash；重复请求在计算期记 DUPLICATE_REQUEST（不影响本 manifest）
Commit A 后禁止修改本文件生成结果。
"""
from __future__ import annotations

import csv
import hashlib
import itertools
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

from alpha_factory import dsl, factor_generator  # noqa: E402
from alpha_factory.phase1 import manifest  # noqa: E402

OUT = os.path.join(ROOT, "research", "alpha_factory", "phase1", "PHASE1_SYMBOLIC_MANIFEST.csv")

# ---------------------------------------------------------------------------
# Human 30（人工假设，经济直觉）
# ---------------------------------------------------------------------------
HUMAN_30: list[str] = [
    "ratio(ret_5d, atr14_pct)",                    # 5日超跌强度 / 波动率
    "interaction(bb_z, daily_bb_signal_count)",    # 下轨深度 x 市场广度
    "diff(ret_5d, csi300_ret_5)",                  # 个股5日相对沪深300
    "ratio(distance_to_lower_band, bb_width)",     # 距下轨 / 带宽
    "interaction(drawdown_20, daily_bb_up_ratio)", # 回撤 x 当日上涨广度
    "diff(bb_z, cs_zscore(ret_5d))",               # BB深度 - 截面动量
    "ratio(ret_10d, realized_vol_20)",             # 10日收益 / 已实现波动
    "interaction(distance_to_lower_band, amount_ratio_5_20)",  # 深度 x 量能
    "diff(ret_20d, csi1000_ret_20)",               # 个股20日相对中证1000
    "ratio(drawdown_60, atr14_pct)",               # 长回撤 / 波动率
    "interaction(bb_z, turnover_rank)",            # 深度 x 流动性排名
    "diff(ret_5d, ret_20d)",                       # 短动量 - 长动量（反转强度）
    "ratio(gap_pct, atr14_pct)",                   # 跳空 / 波动率
    "interaction(daily_bb_signal_count, daily_bb_down_ratio)",  # 广度 x 全市场超卖占比
    "diff(csi500_ret_5, csi300_ret_5)",            # 小盘相对大盘
    "ratio(log_amount, atr14_pct)",                # 流动性 / 波动率
    "interaction(distance_52w_high, ret_20d)",     # 距高点 x 20日动量
    "diff(ret_3d, cs_zscore(ret_10d))",            # 3日收益 - 截面10日
    "ratio(daily_range_pct, realized_vol_10)",     # 当日振幅 / 已实现波动
    "interaction(bb_width, daily_bb_signal_count)",# 带宽 x 市场信号数
    "diff(drawdown_20, drawdown_60)",              # 短回撤 - 长回撤
    "ratio(ret_20d, bb_width)",                    # 20日收益 / 带宽
    "interaction(signal_count_last_20d, bb_z)",    # 重复信号数 x 深度
    "diff(ret_5d, csi500_ret_5)",                  # 个股相对中证500
    "ratio(distance_ma20, atr14_pct)",             # 距MA20 / 波动率
    "interaction(market_up_ratio, bb_z)",          # 市场上涨占比 x 深度
    "diff(log_amount, cs_zscore(amount_ratio_5_20))",  # 流动性水平 - 截面量能
    "ratio(ret_60d, realized_vol_20)",             # 60日收益 / 波动
    "interaction(days_since_first_signal, bb_z)",  # 信号年龄 x 深度
    "diff(ret_1d, ret_5d)",                        # 1日动量 - 5日动量
]

# ---------------------------------------------------------------------------
# LLM 30（LLM 提出的发散假设，仍过白名单）
# ---------------------------------------------------------------------------
LLM_30: list[str] = [
    "ratio(bb_z, cs_zscore(atr14_pct))",
    "interaction(distance_to_lower_band, market_down_ratio)",
    "diff(csi1000_ret_20, csi300_ret_20)",
    "ratio(ret_3d, daily_range_pct)",
    "interaction(turnover_rank, amount_ratio_5_20)",
    "interaction(bb_z, csi500_ret_20)",
    "ratio(drawdown_60, realized_vol_20)",
    "interaction(ret_10d, csi1000_ret_5)",
    "diff(amount_ratio_5_20, volume_ratio_5_20)",
    "ratio(daily_bb_up_ratio, daily_bb_down_ratio)",
    "interaction(distance_52w_high, drawdown_60)",
    "diff(gap_pct, cs_zscore(gap_pct))",
    "ratio(ret_20d, distance_ma60)",
    "interaction(daily_bb_signal_count, market_down_ratio)",
    "diff(ret_60d, csi500_ret_20)",
    "ratio(signal_count_last_20d, days_since_first_signal)",
    "interaction(bb_width, atr14_pct)",
    "diff(log_amount, cs_zscore(bb_z))",
    "ratio(distance_ma5, realized_vol_10)",
    "interaction(ret_1d, ret_20d)",
    "diff(csi500_ret_1, csi300_ret_1)",
    "ratio(market_up_ratio, atr14_pct)",
    "interaction(drawdown_20, daily_bb_down_ratio)",
    "diff(realized_vol_20, realized_vol_10)",
    "ratio(days_since_first_signal, signal_count_last_20d)",
    "interaction(csi1000_ret_5, bb_width)",
    "diff(ret_5d, ret_1d)",
    "ratio(turnover_rank, bb_width)",
    "interaction(gap_pct, daily_bb_signal_count)",
    "diff(distance_52w_high, distance_ma20)",
]


def _validate_or_die(expr: str) -> None:
    node = dsl.parse(expr)
    dsl.validate(node, universe="A")
    err = dsl.check_complexity(node)
    if err:
        raise ValueError(f"complexity: {expr}: {err}")


def _hash(expr: str) -> str:
    return hashlib.sha256(dsl.canonical_string(expr).encode()).hexdigest()[:16]


def build_rows() -> list[dict]:
    rows: list[dict] = []

    def add(expr: str, generator: str, expected_direction: str = "NA") -> None:
        _validate_or_die(expr)
        fam = dsl.infer_family(expr)
        rows.append({
            "request_index": len(rows) + 1,
            "generator": generator,
            "formula": expr,
            "canonical_expression": dsl.canonical_string(expr),
            "expression_hash": _hash(expr),
            "family": fam,
            "expected_direction": expected_direction,
            "lookback": "NA",  # 横截面/快照运算；时序窗口由基础特征承担
            "status": "PROPOSED",
        })

    # Human 30
    for e in HUMAN_30:
        add(e, "HUMAN", expected_direction="负向（超跌越深/广度越大，D20 越高）")

    # Template 180：核心输入子集上的确定性组合（跳过已出现 hash）
    core = [
        "bb_z", "distance_to_lower_band", "ret_5d", "ret_20d", "atr14_pct",
        "bb_width", "drawdown_20", "distance_52w_high", "log_amount",
        "amount_ratio_5_20", "turnover_rank", "daily_bb_signal_count",
        "market_up_ratio", "csi300_ret_5", "csi500_ret_5", "gap_pct",
    ]
    seen_hashes = {r["expression_hash"] for r in rows}
    n_templ = 0
    bin_ops = ["ratio", "diff", "interaction", "min", "max"]
    op_idx = {"ratio": 0, "diff": 1, "interaction": 2, "min": 3, "max": 4}
    combos = list(itertools.combinations(core, 2))
    for a, b in combos:
        if n_templ >= 180:
            break
        for op in bin_ops:
            if n_templ >= 180:
                break
            e = factor_generator.TEMPLATES[op_idx[op]][1](a, b)
            try:
                _validate_or_die(e)
            except ValueError:
                continue
            if _hash(e) in seen_hashes:
                continue
            seen_hashes.add(_hash(e))
            add(e, "TEMPLATE", expected_direction="NA")
            n_templ += 1
    assert n_templ == 180, f"template count {n_templ} != 180"

    # Random 60（seed 冻结）
    rng = random.Random(manifest.SYMBOLIC_300["random_seed"])
    inputs = manifest.SYMBOLIC_INPUTS
    unary = ["cs_rank", "cs_zscore", "abs", "sign"]
    binary = ["ratio", "diff", "interaction", "min", "max"]
    n_rand = 0
    guard = 0
    seen = seen_hashes
    while n_rand < 60 and guard < 1000:
        guard += 1
        if rng.random() < 0.4:
            a = rng.choice(inputs)
            op = rng.choice(unary)
            e = factor_generator.TEMPLATES[{"cs_rank": 5, "cs_zscore": 6, "abs": 7, "sign": 8}[op]][1](a)
        else:
            a, b = rng.sample(inputs, 2)
            op = rng.choice(binary)
            e = factor_generator.TEMPLATES[{"ratio": 0, "diff": 1, "interaction": 2, "min": 3, "max": 4}[op]][1](a, b)
        try:
            _validate_or_die(e)
        except ValueError:
            continue
        if _hash(e) in seen:
            continue
        seen.add(_hash(e))
        add(e, "RANDOM", expected_direction="NA")
        n_rand += 1
    assert n_rand == 60, f"random count {n_rand} != 60"

    # LLM 30
    for e in LLM_30:
        add(e, "LLM", expected_direction="NA")

    assert len(rows) == 300, f"total {len(rows)} != 300"
    return rows


def main() -> None:
    rows = build_rows()
    hashes = [r["expression_hash"] for r in rows]
    assert len(set(hashes)) == len(hashes), "duplicate expression_hash in manifest!"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {OUT}")
    from collections import Counter
    print(Counter(r["generator"] for r in rows))


if __name__ == "__main__":
    main()
