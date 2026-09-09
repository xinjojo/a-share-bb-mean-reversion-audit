"""PIT / leakage guard tests: future operator, negative lag, feature source date,
feature-label separation, label build."""
import numpy as np
import pandas as pd
import pytest

from alpha_factory import dsl, label_engine, factor_engine


def test_no_future_operator():
    for e in ['lead(close,1)', 'future(close,5)', 'lag(close,-2)']:
        with pytest.raises(ValueError):
            dsl.parse(e)


def test_negative_lag_forbidden_in_validate():
    with pytest.raises(ValueError):
        dsl.validate(dsl.parse('lag(close,-1)'), universe='B')


def test_forbidden_keywords_in_expression():
    assert any(k in 'lead(close,1)' for k in dsl.FORBIDDEN_KEYWORDS)


def test_feature_source_date_smoke_fixture():
    """Feature columns must not include future-path columns (D1..D20)."""
    df = pd.DataFrame({
        'signal_date': pd.to_datetime(['2020-02-06', '2020-02-07'] * 5),
        'signal_day_close': np.linspace(10, 20, 10),
        'signal_day_amount': np.linspace(1e6, 2e6, 10),
        'bb_z': np.linspace(-3, -1, 10),
        'ret_5': np.linspace(-0.1, 0.05, 10),
        'atr14_pct': np.linspace(0.02, 0.06, 10),
        'close_ret_D1': np.linspace(0, 0.1, 10),
        'close_ret_D20': np.linspace(-0.2, 0.3, 10),
        'MFE_D20': np.linspace(0, 0.3, 10),
        'MAE_D20': np.linspace(-0.3, 0, 10),
    })
    feats = factor_engine.compute_many(
        ['bb_z', 'ratio(ret_5,atr14_pct)', 'cs_rank(signal_day_amount)'],
        df, date_col='signal_date', mode='wide', universe='A')
    future_names = [c for c in feats.columns
                    if any(c.startswith(f'{p}') for p in
                           ('close_ret_D', 'MFE_D', 'MAE_D', 'trade_date_D'))]
    assert future_names == []


def test_label_feature_separation():
    labels = {'close_ret_D1', 'close_ret_D20', 'MFE_D20', 'MAE_D20', 'BAD'}
    features = {'bb_z', 'ret_5', 'atr14_pct', 'signal_day_amount'}
    label_engine.assert_feature_label_separated(features, labels)
    with pytest.raises(ValueError):
        label_engine.assert_feature_label_separated(features | {'BAD'}, labels)


def test_build_labels_a():
    df = pd.DataFrame({
        'close_ret_D1': [0.01, -0.02], 'close_ret_D5': [0.02, -0.01],
        'close_ret_D10': [0.03, 0.0], 'close_ret_D20': [0.05, -0.25],
        'MFE_D20': [0.08, 0.02], 'MAE_D20': [-0.03, -0.25],
    })
    lab = label_engine.build_labels_a(df)
    assert list(lab['GOOD']) == [1, 0]
    assert list(lab['BAD']) == [0, 1]
    assert list(lab['STRONG']) == [1, 0]


def test_missing_outcome_raises():
    with pytest.raises(ValueError):
        label_engine.build_labels_a(pd.DataFrame({'close_ret_D1': [1.0]}))
