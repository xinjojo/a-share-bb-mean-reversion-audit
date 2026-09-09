"""A-Share Alpha Factory — factor engine.

Evaluates DSL expressions on wide (Universe A: one row per signal) or
panel (Universe B: ts_code × date) frames.  PIT discipline: expressions may only
reference columns that are knowable at the anchor date (loader guarantees it).

Mode 'wide'   : per-row / cross-sectional ops only (cs_rank, cs_zscore, ratio, ...).
                 Time-series ops (lag/rolling_*) are NOT APPLICABLE and raise.
Mode 'panel'  : time-series ops computed per group (group_col, e.g. ts_code).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from alpha_factory import dsl

TIME_SERIES_OPS = {'lag', 'delta', 'return', 'rolling_mean', 'rolling_std',
                   'rolling_min', 'rolling_max', 'rolling_rank', 'ts_zscore', 'corr'}


def _ts(op: str, s: pd.Series, args) -> pd.Series:
    n = args[0] if isinstance(args[0], int) else None
    if op == 'lag':
        return s.shift(n)
    if op == 'delta':
        return s - s.shift(n)
    if op == 'return':
        return s / s.shift(n) - 1.0
    if op == 'rolling_mean':
        return s.rolling(n).mean()
    if op == 'rolling_std':
        return s.rolling(n).std()
    if op == 'rolling_min':
        return s.rolling(n).min()
    if op == 'rolling_max':
        return s.rolling(n).max()
    if op == 'rolling_rank':
        return s.rolling(n).apply(lambda v: (v.rank(pct=True).iloc[-1]), raw=False)
    if op == 'ts_zscore':
        m = s.rolling(n).mean()
        sd = s.rolling(n).std()
        return (s - m) / sd
    raise ValueError(f'unknown ts op {op}')


def _eval_node(node: dsl.Node, df: pd.DataFrame, date_col: str, mode: str,
               group_col: str | None) -> pd.Series:
    if node.kind == 'input':
        if node.name not in df.columns:
            raise ValueError(f'input field missing in frame: {node.name}')
        return df[node.name].astype(float)

    name = node.name
    spec = dsl.OPERATORS[name]

    if name in TIME_SERIES_OPS:
        if mode != 'panel':
            raise ValueError(
                f'operator {name} requires panel mode (time-series); not applicable in wide mode')
        arg = node.args[0]
        assert isinstance(arg, dsl.Node)
        s = _eval_node(arg, df, date_col, mode, group_col)
        if group_col is not None:
            tmp = pd.DataFrame({'_g': df[group_col].values, '_v': s.values},
                               index=df.index)
            tmp['_r'] = tmp.groupby('_g')['_v'].transform(lambda v: _ts(name, v, node.args))
            return tmp['_r']
        return _ts(name, s, node.args)

    if name in ('cs_rank', 'cs_zscore'):
        if mode != 'wide':
            raise ValueError(f'{name} requires wide (cross-sectional) mode')
        arg = node.args[0]
        assert isinstance(arg, dsl.Node)
        s = _eval_node(arg, df, date_col, mode, group_col)
        tmp = pd.DataFrame({'_d': df[date_col].values, '_v': s.values}, index=df.index)
        if name == 'cs_rank':
            tmp['_r'] = tmp.groupby('_d')['_v'].rank(pct=True)
        else:
            tmp['_r'] = tmp.groupby('_d')['_v'].transform(
                lambda v: (v - v.mean()) / v.std(ddof=0))
        return tmp['_r']

    if name == 'corr':
        a = _eval_node(node.args[0], df, date_col, mode, group_col)
        b = _eval_node(node.args[1], df, date_col, mode, group_col)
        n = node.args[2]
        assert isinstance(n, int)
        tmp = pd.DataFrame({'_g': df[group_col].values, '_a': a.values, '_b': b.values},
                           index=df.index)
        tmp['_r'] = tmp.groupby('_g').apply(
            lambda g: g['_a'].rolling(n).corr(g['_b']), include_groups=False)
        return tmp['_r'].reset_index(level=0, drop=True).reindex(df.index)

    # elementwise binary / unary
    if len(node.args) == 2 and all(isinstance(x, dsl.Node) for x in node.args):
        a = _eval_node(node.args[0], df, date_col, mode, group_col)
        b = _eval_node(node.args[1], df, date_col, mode, group_col)
        if name == 'ratio':
            return a / b
        if name == 'diff':
            return a - b
        if name == 'min':
            return np.minimum(a, b)
        if name == 'max':
            return np.maximum(a, b)
        if name == 'interaction':
            return a * b
    if len(node.args) == 1:
        a = _eval_node(node.args[0], df, date_col, mode, group_col)
        if name == 'abs':
            return a.abs()
        if name == 'sign':
            return np.sign(a)
    raise ValueError(f'unhandled expression node: {node}')


def compute(expr: str, df: pd.DataFrame, *, date_col: str = 'signal_date',
            mode: str = 'wide', group_col: str | None = None,
            universe: str = 'A') -> pd.Series:
    """Evaluate a DSL expression on a frame. Returns float Series aligned to df.index."""
    node = dsl.parse(expr)
    dsl.validate(node, universe=universe)
    reject = dsl.check_complexity(node)
    if reject:
        raise ValueError(reject)
    return _eval_node(node, df, date_col, mode, group_col)


def compute_many(exprs: list[str], df: pd.DataFrame, *, date_col: str = 'signal_date',
                 mode: str = 'wide', group_col: str | None = None,
                 universe: str = 'A') -> pd.DataFrame:
    """Evaluate many expressions; returns DataFrame indexed like df, one column each.
    Column name = expression (canonical hash available via dsl.expression_hash)."""
    out = {}
    for e in exprs:
        try:
            out[e] = compute(e, df, date_col=date_col, mode=mode,
                             group_col=group_col, universe=universe)
        except Exception as ex:
            out[e] = pd.Series(np.nan, index=df.index, dtype=float)
            out[e].attrs['error'] = str(ex)
    return pd.DataFrame(out, index=df.index)
