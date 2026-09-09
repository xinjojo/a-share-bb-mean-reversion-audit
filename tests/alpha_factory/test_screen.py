"""Screen engine tests: IC / RankIC / quantile / cluster bootstrap / yearly."""
import numpy as np
import pandas as pd

from alpha_factory import screen_factor


def _make_data(n_dates=30, per=10, seed=0):
    rng = np.random.default_rng(seed)
    dates = []
    f, y = [], []
    for d in range(n_dates):
        base = rng.normal(0, 0.02)
        for _ in range(per):
            dates.append(pd.Timestamp('2020-01-01') + pd.Timedelta(days=d))
            x = rng.normal(0, 1)
            f.append(x)
            y.append(0.02 * x + base + rng.normal(0, 0.02))
    return (pd.Series(f), pd.Series(y), pd.Series(dates, dtype='datetime64[ns]'))


def test_daily_ic_computation():
    f, y, d = _make_data()
    daily = screen_factor.daily_cross_sectional_ic(f, y, d)
    assert len(daily) == 30
    assert daily['ic'].notna().mean() > 0.9


def test_screen_summary_shape():
    f, y, d = _make_data()
    s = screen_factor.screen(f, y, d)
    assert 'ic_mean' in s and 'rank_ic_mean' in s and 'icir' in s
    assert s['n_dates'] == 30
    qt = s['quantile_table']
    assert list(qt['quantile']) == ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']
    assert len(s['yearly']) >= 1


def test_quantile_monotonic_flag():
    f, y, d = _make_data()
    qt = screen_factor.quantile_table(f, y, d)
    assert 'monotonic' in qt.attrs


def test_cluster_bootstrap_ci():
    f, y, d = _make_data()
    daily = screen_factor.daily_cross_sectional_ic(f, y, d)
    lo, hi = screen_factor.cluster_bootstrap_ci(daily, n_boot=50)
    assert lo <= hi


def test_turnover_bounded():
    f, y, d = _make_data()
    to = screen_factor.turnover(f, d)
    assert 0 <= to <= 1


def test_yearly_ic_years():
    f, y, d = _make_data()
    yic = screen_factor.yearly_ic(f, y, d)
    assert set(yic['year'].astype(int)) == {2020}
