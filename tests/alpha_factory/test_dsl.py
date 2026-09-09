"""DSL parser / canonical hash / whitelist / complexity tests."""
import pytest

from alpha_factory import dsl


def test_parse_simple_input():
    n = dsl.parse('ret_5')
    assert n.kind == 'input' and n.name == 'ret_5'


def test_parse_nested():
    n = dsl.parse('ratio(ret_5,atr14_pct)')
    assert n.kind == 'op' and n.name == 'ratio'
    assert len(n.args) == 2


def test_parse_lookback_int():
    n = dsl.parse('lag(close,5)')
    assert n.args[1] == 5


def test_trailing_tokens_rejected():
    with pytest.raises(ValueError):
        dsl.parse('ret_5 extra')


def test_empty_rejected():
    with pytest.raises(ValueError):
        dsl.parse('   ')


def test_future_operator_rejected():
    for e in ['lead(close,1)', 'future(close,5)', 'fwd_ret_5']:
        with pytest.raises(ValueError):
            dsl.parse(e)


def test_negative_lag_forbidden():
    with pytest.raises(ValueError):
        dsl.validate(dsl.parse('lag(close,-1)'), universe='B')


def test_zero_lag_forbidden():
    with pytest.raises(ValueError):
        dsl.validate(dsl.parse('lag(close,0)'), universe='B')


def test_lookback_whitelist():
    with pytest.raises(ValueError):
        dsl.validate(dsl.parse('rolling_mean(close,17)'), universe='B')  # 17 not in whitelist


def test_lookback_whitelist_ok():
    dsl.validate(dsl.parse('rolling_mean(close,20)'), universe='B')
    dsl.validate(dsl.parse('ts_zscore(close,120)'), universe='B')


def test_unknown_operator_rejected():
    with pytest.raises(ValueError):
        dsl.parse('fancy_op(ret_5)')


def test_unknown_input_field_rejected():
    with pytest.raises(ValueError):
        dsl.validate(dsl.parse('ret_99'), universe='A')
    with pytest.raises(ValueError):
        dsl.validate(dsl.parse('close'), universe='A')  # close is Universe B only


def test_universe_b_fields():
    dsl.validate(dsl.parse('close'), universe='B')
    dsl.validate(dsl.parse('ratio(close,amount)'), universe='B')


def test_canonical_identical_expressions():
    a = dsl.canonical_string('ratio(ret_5,atr14_pct)')
    b = dsl.canonical_string('ratio( ret_5 , atr14_pct )')
    assert a == b


def test_canonical_commutative_sort():
    a = dsl.canonical_string('interaction(bb_z,ret_5)')
    b = dsl.canonical_string('interaction(ret_5,bb_z)')
    assert a == b
    c = dsl.canonical_string('min(ret_5,ret_20)')
    d = dsl.canonical_string('min(ret_20,ret_5)')
    assert c == d


def test_expression_hash_stable():
    h1 = dsl.expression_hash('ratio(ret_5,atr14_pct)')
    h2 = dsl.expression_hash('ratio( ret_5, atr14_pct )')
    assert h1 == h2 and len(h1) == 16


def test_hash_differs_for_different_expressions():
    assert dsl.expression_hash('ret_5') != dsl.expression_hash('ret_20')


def test_complexity_budget():
    # depth > 4
    e = 'interaction(interaction(interaction(bb_z,ret_5),ret_20),atr14_pct)'
    n = dsl.parse(e)
    assert dsl.check_complexity(n) is not None
    # interactions > 2
    e2 = 'ratio(diff(interaction(bb_z,ret_5),interaction(ret_20,atr14_pct)),ret_10)'
    assert dsl.check_complexity(dsl.parse(e2)) is not None
    # ok case
    assert dsl.check_complexity(dsl.parse('ratio(ret_5,atr14_pct)')) is None


def test_complexity_counts():
    c = dsl.complexity(dsl.parse('interaction(bb_z,cs_rank(signal_day_amount))'))
    assert c['depth'] == 3
    assert c['unique_inputs'] == 2
    assert c['interactions'] == 1


def test_infer_family():
    assert dsl.infer_family('bb_z') == 'BB_CONDITIONAL'
    assert dsl.infer_family('interaction(a,b)') == 'INTERACTION'
