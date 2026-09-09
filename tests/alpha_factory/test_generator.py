"""Factor generator constrained tests."""
import pytest

from alpha_factory import dsl, factor_generator


def test_template_combinations_all_valid():
    exprs = factor_generator.template_combinations()
    assert len(exprs) >= 20
    for e in exprs:
        n = dsl.parse(e)
        dsl.validate(n, universe='A')
        assert dsl.check_complexity(n) is None


def test_random_constrained_all_valid():
    exprs = factor_generator.random_constrained(n=20, seed=42)
    assert len(exprs) == 20
    for e in exprs:
        n = dsl.parse(e)
        dsl.validate(n, universe='A')
        assert dsl.check_complexity(n) is None


def test_random_deterministic_with_seed():
    a = factor_generator.random_constrained(n=5, seed=7)
    b = factor_generator.random_constrained(n=5, seed=7)
    assert a == b


def test_llm_proposed_valid():
    e = factor_generator.llm_proposed('ratio(ret_20,atr14_pct)')
    assert e == 'ratio(ret_20,atr14_pct)'


def test_llm_proposed_complexity_rejected():
    with pytest.raises(ValueError):
        factor_generator.llm_proposed(
            'interaction(interaction(interaction(bb_z,ret_5),ret_20),atr14_pct)')


def test_llm_proposed_future_rejected():
    with pytest.raises(ValueError):
        factor_generator.llm_proposed('lead(close,1)')
