"""A-Share Alpha Factory — factor generator (Phase 0: candidate generation only).

所有生成表达式必须过 DSL parser / operator whitelist / lookback whitelist /
PIT validator / complexity validator 才能进入计算。Phase 0 不做大规模正式生成。
"""
from __future__ import annotations

import itertools
import random

from alpha_factory import dsl

TEMPLATES = [
    ('ratio', lambda a, b: f'ratio({a},{b})'),
    ('diff', lambda a, b: f'diff({a},{b})'),
    ('interaction', lambda a, b: f'interaction({a},{b})'),
    ('min', lambda a, b: f'min({a},{b})'),
    ('max', lambda a, b: f'max({a},{b})'),
    ('cs_rank', lambda a: f'cs_rank({a})'),
    ('cs_zscore', lambda a: f'cs_zscore({a})'),
    ('abs', lambda a: f'abs({a})'),
    ('sign', lambda a: f'sign({a})'),
]

BASE_INPUTS_A = [
    'bb_z', 'distance_to_lower_band', 'BB_width', 'ret_5', 'ret_20',
    'atr14_pct', 'amount_ratio_5_20', 'drawdown_20', 'distance_52w_high',
    'gap_pct', 'daily_range_pct', 'turnover_rank',
]


def human(expr: str) -> str:
    """Register a human-hypothesis expression as-is (still validated downstream)."""
    node = dsl.parse(expr)
    dsl.validate(node, universe='A')
    return expr


def template_combinations(inputs: list[str] | None = None) -> list[str]:
    """Deterministic template combinations from base inputs (validated)."""
    inputs = inputs or BASE_INPUTS_A
    out = []
    for name, fn in TEMPLATES:
        arity = name.count(',') + 1 if fn.__code__.co_argcount == 2 else 1
        if fn.__code__.co_argcount == 2:
            for a, b in itertools.combinations(inputs, 2):
                e = fn(a, b)
                try:
                    dsl.validate(dsl.parse(e), universe='A')
                    out.append(e)
                except ValueError:
                    pass
        else:
            for a in inputs:
                e = fn(a)
                try:
                    dsl.validate(dsl.parse(e), universe='A')
                    out.append(e)
                except ValueError:
                    pass
    return out


def random_constrained(inputs: list[str] | None = None, n: int = 10,
                       seed: int = 2026) -> list[str]:
    """Random constrained generation from whitelist; all outputs validated.
    NOTE: every expression produced here counts as a hypothesis attempt."""
    inputs = inputs or BASE_INPUTS_A
    rng = random.Random(seed)
    unary = [fn for fn in TEMPLATES if fn[1].__code__.co_argcount == 1]
    binary = [fn for fn in TEMPLATES if fn[1].__code__.co_argcount == 2]
    out = []
    while len(out) < n:
        if rng.random() < 0.4:
            fn = rng.choice(unary)
            e = fn[1](rng.choice(inputs))
        else:
            fn = rng.choice(binary)
            a, b = rng.sample(inputs, 2)
            e = fn[1](a, b)
        try:
            node = dsl.parse(e)
            dsl.validate(node, universe='A')
            if dsl.check_complexity(node) is None:
                out.append(e)
        except ValueError:
            continue
    return out


def llm_proposed(expr: str) -> str:
    """LLM-proposed expression gate: same whitelist validation, no free-form code."""
    node = dsl.parse(expr)
    dsl.validate(node, universe='A')
    reject = dsl.check_complexity(node)
    if reject:
        raise ValueError(reject)
    return expr
