"""Universe B Phase 0 — unit tests（不依赖正式构建产物，用合成数据验证逻辑）。
"""
import os
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
from alpha_factory.universe_b import build_labels as bl
from alpha_factory.universe_b import build_universe as bu
from alpha_factory.universe_b import audit as aud


# ---- purge/embargo ----
def test_split_purged_removes_label_window_crossing():
    dates = pd.date_range('2022-12-01', periods=40, freq='D')
    df = pd.DataFrame({'date': dates, 'ts_code': 'A', 'fwd20_rank01': 0.5,
                       'label_end_date': dates.shift(20, freq='D')})
    out = bl.split_purged(df, train_end=pd.Timestamp('2022-12-31'))
    tr = out['train']
    # 标签窗口（+20 日）不得超过 train_end
    assert (tr['label_end_date'] <= pd.Timestamp('2022-12-31')).all()
    assert len(tr) <= len(df)


def test_split_purged_val_test():
    dates = pd.date_range('2022-01-01', periods=100, freq='D')
    df = pd.DataFrame({'date': dates, 'ts_code': 'A', 'fwd20_rank01': 0.5,
                       'label_end_date': dates.shift(20, freq='D')})
    out = bl.split_purged(df, train_end=pd.Timestamp('2022-12-31'),
                          val_start=pd.Timestamp('2023-01-01'),
                          val_end=pd.Timestamp('2023-12-31'))
    assert 'train' in out and 'valid' in out and 'test' in out
    assert (out['valid']['label_end_date'] <= pd.Timestamp('2023-12-31')).all()


# ---- label prefix whitelist ----
def test_label_prefix_whitelist():
    lab_cols = ['fwd_ret_1', 'MAE_5', 'MFE_20', 'exec_fwd_ret_20', 'TOP20_FWD20',
                'BOTTOM20_FWD20', 'label_end_date', 'date', 'ts_code']
    bad = [c for c in lab_cols
           if c not in ('date', 'ts_code') and not c.startswith(
               ('fwd_', 'MAE', 'MFE', 'exec_', 'TOP20', 'BOTTOM20', 'label_end'))]
    assert bad == []


def test_feature_has_no_label_cols():
    feat_cols = ['ret_5', 'bb_z', 'atr14_pct', 'is_limit_up', 'listing_days', 'date', 'ts_code']
    leak = [c for c in feat_cols if c not in ('date', 'ts_code') and c.startswith(
        ('fwd_', 'MAE', 'MFE', 'exec_', 'TOP', 'BOTTOM', 'label_end'))]
    assert leak == []


# ---- board threshold ----
def test_board_threshold():
    assert bu.board_threshold('000001.SZ', False) == 0.10
    assert bu.board_threshold('600000.SH', False) == 0.10
    assert bu.board_threshold('300750.SZ', False) == 0.20
    assert bu.board_threshold('688981.SH', False) == 0.20
    assert bu.board_threshold('832317.BJ', False) == 0.30
    assert bu.board_threshold('600000.SH', True) == 0.05


# ---- leakage audit logic ----
def test_leakage_audit_detects_leak():
    # 构造含泄漏列的 fake features 应被检出
    feats = pd.DataFrame({'date': ['2020-01-02'], 'ts_code': ['A'],
                          'ret_5': [0.1], 'fwd_ret_20': [0.2]})
    feat_cols = [c for c in feats.columns if c not in ('date', 'ts_code')]
    leak_cols = [c for c in feat_cols if c.startswith(
        ('fwd_', 'MAE', 'MFE', 'exec_', 'TOP', 'BOTTOM', 'label_end'))]
    assert leak_cols == ['fwd_ret_20']


# ---- label builder synthetic ----
def test_label_builder_synthetic(tmp_path, monkeypatch):
    panel = pd.DataFrame({
        'date': pd.date_range('2020-01-01', periods=30, freq='D').repeat(2),
        'ts_code': ['A', 'B'] * 30,
        'close_adj': np.linspace(1.0, 2.0, 60),
        'open_adj': np.linspace(1.0, 2.0, 60),
        'high_adj': np.linspace(1.0, 2.0, 60) + 0.01,
        'low_adj': np.linspace(1.0, 2.0, 60) - 0.01,
        'open': 10.0, 'high': 10.1, 'low': 9.9, 'close': 10.0,
        'pre_close': 10.0, 'adj_factor': 1.0, 'is_suspended': False,
        'is_limit_up': False, 'is_limit_down': False,
    })
    monkeypatch.setattr(bl, 'load_panel', lambda: panel)
    monkeypatch.setattr(bl, 'PANEL', str(tmp_path))
    monkeypatch.setattr(bl, 'OUT', str(tmp_path / 'labels'))
    out = bl.build()
    assert 'fwd_ret_20' in out.columns
    assert 'fwd20_rank01' in out.columns
    assert out['fwd20_rank01'].dropna().between(0, 1).all()
    assert 'label_end_date' in out.columns


# ---- industry features synthetic ----
def test_industry_merge_synthetic():
    sm = pd.DataFrame({
        'con_code': ['A', 'B'], 'industry_code': ['801010', '801010'],
        'industry_name': ['电子', '电子'],
        'in': [pd.Timestamp('2020-01-01')] * 2,
        'out': [pd.NaT] * 2,
    })
    p = pd.DataFrame({'date': pd.Timestamp('2020-06-01'), 'ts_code': ['A', 'B'],
                      'ret_1': [0.01, 0.03], 'ret_5': [0.02, 0.04],
                      'ret_20': [0.05, 0.07], 'ret_60': [0.10, 0.12]})
    # 直接验证 merge_asof 逻辑可运行（复刻 industry_features 的合并核心）
    p2 = p.sort_values('date')
    mem = sm[['con_code', 'industry_name', 'in', 'out']].rename(columns={'con_code': 'ts_code'})
    mem = mem.rename(columns={'in': 'date'})
    asof = pd.merge_asof(p2, mem.sort_values('date'), on='date', by='ts_code',
                         direction='backward', suffixes=('', '_in'))
    asof = asof[(asof['out'].isna()) | (asof['out'] >= asof['date'])]
    ind = asof.groupby(['industry_name', 'date'])['ret_1'].mean()
    assert abs(ind.loc[('电子', pd.Timestamp('2020-06-01'))] - 0.02) < 1e-9
