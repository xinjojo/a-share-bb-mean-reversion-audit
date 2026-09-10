"""A-Share Alpha Factory — Factor DSL.

安全表达式解析、白名单校验、复杂度预算、canonicalization 与 expression_hash。
禁止 lead / future / 负 lag；禁止白名单外算子与 lookback。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------- whitelists
INPUT_FIELDS_A = {
    # signal-day fields (PIT, Universe A)
    'signal_day_open', 'signal_day_high', 'signal_day_low', 'signal_day_close',
    'signal_day_amount', 'signal_day_volume', 'signal_day_adj_factor',
    # BB state
    'bb_z', 'bb_mid', 'bb_lower', 'bb_upper', 'BB_width', 'distance_to_lower_band',
    # rank / listing
    'turnover_rank', 'listing_age_days',
    # market breadth (PIT, precomputed by loader)
    'daily_bb_signal_count', 'daily_bb_up_ratio',
    # lookback aggregates (PIT, precomputed by loader)
    'ret_1', 'ret_3', 'ret_5', 'ret_10', 'ret_20', 'ret_60',
    'vol_10', 'vol_20', 'atr14_pct', 'amount_ratio_5_20',
    'drawdown_20', 'drawdown_60', 'distance_52w_high',
    'gap_pct', 'daily_range_pct',
    # ---- Alpha Factory Phase 1 扩展（Universe A 特征池，PIT 已审计）----
    # 价格位置（带 d 后缀，与 Phase 1 特征列同名）
    'distance_ma5', 'distance_ma10', 'distance_ma20', 'distance_ma60',
    'ret_1d', 'ret_3d', 'ret_5d', 'ret_10d', 'ret_20d', 'ret_60d',
    # 波动 / 流动性扩展
    'bb_width', 'realized_vol_10', 'realized_vol_20', 'log_amount',
    'amount_percentile', 'volume_ratio_5_20',
    # 信号状态
    'level_no', 'days_since_first_signal', 'signal_count_last_20d',
    # 市场环境扩展
    'daily_bb_down_ratio', 'market_up_ratio', 'market_down_ratio',
    'csi300_ret_1', 'csi300_ret_5', 'csi300_ret_20',
    'csi500_ret_1', 'csi500_ret_5', 'csi500_ret_20',
    'csi1000_ret_1', 'csi1000_ret_5', 'csi1000_ret_20',
}
INPUT_FIELDS_B = {
    'open', 'high', 'low', 'close', 'volume', 'amount', 'adj_factor',
}

LOOKBACK_WHITELIST = {1, 2, 3, 5, 10, 20, 40, 60, 120, 250}

# operator: (min_args, max_args, commutative, is_binary_interaction)
OPERATORS: dict[str, tuple[int, int, bool, bool]] = {
    'lag':            (2, 2, False, False),
    'delta':          (2, 2, False, False),
    'return':         (2, 2, False, False),
    'rolling_mean':   (2, 2, False, False),
    'rolling_std':    (2, 2, False, False),
    'rolling_min':    (2, 2, False, False),
    'rolling_max':    (2, 2, False, False),
    'rolling_rank':   (2, 2, False, False),
    'ts_zscore':      (2, 2, False, False),
    'cs_rank':        (1, 1, False, False),
    'cs_zscore':      (1, 1, False, False),
    'ratio':          (2, 2, False, True),
    'diff':           (2, 2, False, True),
    'corr':           (3, 3, False, True),
    'min':            (2, 2, True, True),
    'max':            (2, 2, True, True),
    'abs':            (1, 1, False, False),
    'sign':           (1, 1, False, False),
    'interaction':    (2, 2, True, True),
}
FORBIDDEN_KEYWORDS = {'lead', 'future', 'fwd', 'shift(-', 'lag(-', 'delta(-', 'return(-'}

COMPLEXITY_MAX_DEPTH = 4
COMPLEXITY_MAX_UNIQUE_INPUTS = 5
COMPLEXITY_MAX_INTERACTIONS = 2

FAMILY_HINT = {
    # 专用 family 优先匹配（避免 generic 词提前命中）
    'BB_CONDITIONAL': ('bb_z', 'distance_to_lower_band'),
    'INTERACTION': ('interaction', 'ratio', 'diff', 'corr'),
    'CROSS_SECTIONAL': ('cs_', 'turnover_rank'),
    'PRICE_REVERSAL': ('ret_', 'drawdown', 'distance_52w_high', 'reversal'),
    'MOMENTUM': ('momentum', 'trend_ret'),
    'VOLATILITY': ('atr', 'vol_', 'bb_width', 'BB_width', 'ts_zscore', 'rolling_std'),
    'LIQUIDITY': ('amount', 'turnover', 'volume'),
    'VOLUME_PRICE': ('amount_ratio', 'volume'),
    'GAP': ('gap',),
    'RANGE': ('range',),
    'TREND': ('ma', 'rolling_mean', 'bb_mid', 'bb_upper', 'bb_lower'),
    'MARKET_CONTEXT': ('index_return', 'breadth'),
}

ALLOWED_STATUS = {'PROPOSED', 'SCREENING', 'VALIDATING', 'KEEP',
                  'DUPLICATE', 'FAIL', 'INVALID', 'LEAKAGE', 'ARCHIVED'}
FAILURE_REASONS = {'NO_SIGNAL', 'OOS_FAIL', 'UNSTABLE', 'DUPLICATE', 'HIGH_TURNOVER',
                   'COST_KILLED', 'LEAKAGE', 'REGIME_SPECIFIC', 'INSUFFICIENT_COVERAGE',
                   'MULTIPLE_TESTING_FAIL', 'NO_INCREMENTAL_ALPHA'}


# ---------------------------------------------------------------- AST
@dataclass(frozen=True)
class Node:
    kind: str          # 'input' | 'op'
    name: str          # field name or operator name
    args: tuple = ()   # for op: child Nodes or int lookback

    def canonical(self) -> str:
        if self.kind == 'input':
            return self.name
        parts = [self.name]
        for a in self.args:
            parts.append(str(a.canonical()) if isinstance(a, Node) else str(a))
        return '(' + ','.join(parts) + ')'


_TOKEN_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*|-?\d+|[(),]')


@dataclass
class _Parser:
    toks: list
    pos: int = 0

    def peek(self):
        return self.toks[self.pos] if self.pos < len(self.toks) else None

    def next(self):
        t = self.peek()
        self.pos += 1
        return t

    def parse(self) -> Node:
        t = self.next()
        if t is None:
            raise ValueError('empty expression')
        if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', t or ''):
            # either an input field or a function call
            if self.peek() == '(':
                return self._parse_call(t)
            if any(t.startswith(k) for k in ('lead', 'future', 'fwd')):
                raise ValueError(f'forbidden future-related input: {t}')
            return Node('input', t)
        raise ValueError(f'unexpected token: {t}')

    def _parse_call(self, name: str) -> Node:
        self.next()  # consume '('
        args = []
        while True:
            if self.peek() == ')':
                self.next()
                break
            if self.peek() is None:
                raise ValueError('unbalanced parentheses')
            nxt = self.peek()
            if re.fullmatch(r'-?\d+', nxt or ''):
                args.append(int(self.next()))
            else:
                args.append(self.parse())
            if self.peek() == ',':
                self.next()
        if name in FORBIDDEN_KEYWORDS:
            raise ValueError(f'forbidden operator: {name}')
        if name not in OPERATORS:
            raise ValueError(f'operator not in whitelist: {name}')
        if name == 'lag':
            lb = [a for a in args if isinstance(a, int)]
            if lb and lb[0] <= 0:
                raise ValueError('lag must be > 0 (future window forbidden)')
        return Node('op', name, tuple(args))


def parse(expr: str) -> Node:
    """Parse DSL expression into AST. Raises ValueError on syntax error."""
    if not isinstance(expr, str) or not expr.strip():
        raise ValueError('empty expression')
    toks = _TOKEN_RE.findall(expr)
    p = _Parser(toks)
    node = p.parse()
    if p.pos != len(toks):
        raise ValueError(f'trailing tokens near: {toks[p.pos:p.pos+3]}')
    return node


# ---------------------------------------------------------------- validation
def _lookback_args(node: Node):
    out = []
    for a in node.args:
        if isinstance(a, int):
            out.append(a)
        else:
            out.extend(_lookback_args(a))
    return out


def validate(node: Node, universe: str = 'A') -> None:
    """Validate operators / lookbacks / input fields. Raises ValueError."""
    allowed_inputs = INPUT_FIELDS_A if universe == 'A' else INPUT_FIELDS_B

    def walk(n: Node):
        if n.kind == 'input':
            if n.name not in allowed_inputs:
                raise ValueError(f'unknown input field for universe {universe}: {n.name}')
            return
        spec = OPERATORS.get(n.name)
        if spec is None:
            raise ValueError(f'operator not in whitelist: {n.name}')
        min_args, max_args, _comm, _inter = spec
        if not (min_args <= len(n.args) <= max_args):
            raise ValueError(f'{n.name} expects {min_args}-{max_args} args, got {len(n.args)}')
        for a in n.args:
            if isinstance(a, int):
                if n.name == 'lag' and a <= 0:
                    raise ValueError('lag must be > 0 (future window forbidden)')
                if a not in LOOKBACK_WHITELIST:
                    raise ValueError(f'lookback {a} not in whitelist')
            else:
                if n.name == 'corr' and len(n.args) == 3 and isinstance(n.args[2], int):
                    if n.args[2] not in LOOKBACK_WHITELIST:
                        raise ValueError(f'corr lookback {n.args[2]} not in whitelist')
                walk(a)

    walk(node)


def complexity(node: Node) -> dict:
    """Return dict(depth, unique_inputs, interactions)."""
    def walk(n: Node, depth: int, acc: dict):
        acc['depth'] = max(acc['depth'], depth)
        if n.kind == 'input':
            acc['inputs'].add(n.name)
            return
        if OPERATORS.get(n.name, (0, 0, False, False))[3]:  # interaction-like
            acc['interactions'] += 1
        for a in n.args:
            if isinstance(a, Node):
                walk(a, depth + 1, acc)

    acc = {'depth': 0, 'inputs': set(), 'interactions': 0}
    walk(node, 1, acc)
    return {'depth': acc['depth'], 'unique_inputs': len(acc['inputs']),
            'interactions': acc['interactions']}


def check_complexity(node: Node) -> Optional[str]:
    c = complexity(node)
    if c['depth'] > COMPLEXITY_MAX_DEPTH:
        return f'REJECT_COMPLEXITY: depth {c["depth"]}>{COMPLEXITY_MAX_DEPTH}'
    if c['unique_inputs'] > COMPLEXITY_MAX_UNIQUE_INPUTS:
        return f'REJECT_COMPLEXITY: unique_inputs {c["unique_inputs"]}>{COMPLEXITY_MAX_UNIQUE_INPUTS}'
    if c['interactions'] > COMPLEXITY_MAX_INTERACTIONS:
        return f'REJECT_COMPLEXITY: interactions {c["interactions"]}>{COMPLEXITY_MAX_INTERACTIONS}'
    return None


# ---------------------------------------------------------------- canonical / hash
def _canonical_args(node: Node, spec) -> tuple:
    if spec[2]:  # commutative -> sort canonical strings
        return tuple(sorted(a.canonical() if isinstance(a, Node) else str(a)
                            for a in node.args))
    return tuple(a.canonical() if isinstance(a, Node) else str(a) for a in node.args)


def canonical(node: Node) -> str:
    if node.kind == 'input':
        return node.name
    spec = OPERATORS.get(node.name)
    args = _canonical_args(node, spec)
    return f'{node.name}(' + ','.join(args) + ')'


def expression_hash(expr: str) -> str:
    """Canonical expression hash (sha256, first 16 hex chars)."""
    node = parse(expr)
    validate(node)
    canon = canonical(node)
    return hashlib.sha256(canon.encode('utf-8')).hexdigest()[:16]


def canonical_string(expr: str) -> str:
    return canonical(parse(expr))


def infer_family(expr: str) -> str:
    low = expr.lower()
    for fam, keys in FAMILY_HINT.items():
        if any(k in low for k in keys):
            return fam
    return 'PRICE_REVERSAL'
