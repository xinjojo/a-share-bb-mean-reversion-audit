"""Redundancy / correlation clustering / BH-FDR / incremental tests."""
import numpy as np
import pandas as pd

from alpha_factory import multiple_testing, redundancy, incremental_test


def test_correlation_matrix_identity():
    df = pd.DataFrame({'a': np.arange(100.0), 'b': np.arange(100.0) + 1})
    corr = redundancy.correlation_matrix(df)
    assert abs(corr.loc['a', 'b']) > 0.99


def test_duplicate_detection():
    rng = np.random.default_rng(0)
    a = rng.normal(size=200)
    b = 0.99 * a + 0.01 * rng.normal(size=200)
    c = rng.normal(size=200)
    df = pd.DataFrame({'f1': a, 'f2': b, 'f3': c})
    corr = redundancy.correlation_matrix(df)
    dup = redundancy.find_duplicates(corr, order=['f1', 'f2', 'f3'])
    assert any(x['factor_id'] == 'f2' and x['duplicate_of'] == 'f1' for x in dup)
    assert not any(x['factor_id'] == 'f3' for x in dup)


def test_hierarchical_clusters():
    rng = np.random.default_rng(1)
    a = rng.normal(size=150)
    df = pd.DataFrame({'f1': a, 'f2': a + 0.01, 'f3': rng.normal(size=150)})
    corr = redundancy.correlation_matrix(df)
    cl = redundancy.hierarchical_clusters(corr)
    assert len(cl) >= 1
    assert all(len(v) >= 1 for v in cl.values())


def test_bh_fdr_basic():
    p = [0.001, 0.01, 0.2, 0.4, 0.9]
    rej = multiple_testing.benjamini_hochberg(p, alpha=0.05)
    assert rej[0] and rej[1] and not rej[2]


def test_bh_fdr_all_pass():
    p = [0.001, 0.002, 0.003]
    assert all(multiple_testing.benjamini_hochberg(p, alpha=0.05))


def test_bh_fdr_none_pass():
    p = [0.4, 0.5, 0.6]
    assert not any(multiple_testing.benjamini_hochberg(p, alpha=0.05))


def test_incremental_r2_delta():
    rng = np.random.default_rng(2)
    x1 = rng.normal(size=300)
    x2 = rng.normal(size=300)
    y = 0.5 * x1 + 0.8 * x2 + rng.normal(size=300)
    r = incremental_test.incremental_r2(
        pd.Series(y), pd.DataFrame({'x1': x1}), pd.Series(x2))
    assert r['delta_r2'] > 0.2
