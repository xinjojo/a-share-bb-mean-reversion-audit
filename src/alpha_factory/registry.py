"""A-Share Alpha Factory — append-only Registries.

Factor Registry / Alpha Graveyard / Alpha Library / Experiment Registry /
Multiple Testing Ledger。全部 append-only：加载 → 追加 → 原子写回。
禁止删除失败因子。factor_id 从 AF_000001 起自动分配，实验 ID 从 AFE_YYYYMMDD_0001 起。
"""
from __future__ import annotations

import os
import re
from datetime import datetime, date

import pandas as pd

try:  # allow direct-module execution in tests (src on sys.path)
    from alpha_factory.dsl import FAILURE_REASONS
except ImportError:  # pragma: no cover
    FAILURE_REASONS = None

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    'research', 'alpha_factory')

FACTOR_REGISTRY = os.path.join(BASE, 'FACTOR_REGISTRY.parquet')
FACTOR_REGISTRY_CSV = os.path.join(BASE, 'FACTOR_REGISTRY.csv')
GRAVEYARD = os.path.join(BASE, 'ALPHA_GRAVEYARD.parquet')
GRAVEYARD_CSV = os.path.join(BASE, 'ALPHA_GRAVEYARD.csv')
LIBRARY = os.path.join(BASE, 'ALPHA_LIBRARY.parquet')
LIBRARY_CSV = os.path.join(BASE, 'ALPHA_LIBRARY.csv')
EXPERIMENTS = os.path.join(BASE, 'EXPERIMENT_REGISTRY.parquet')
EXPERIMENTS_CSV = os.path.join(BASE, 'EXPERIMENT_REGISTRY.csv')
MT_LEDGER = os.path.join(BASE, 'MULTIPLE_TESTING_LEDGER.parquet')
MT_LEDGER_CSV = os.path.join(BASE, 'MULTIPLE_TESTING_LEDGER.csv')

FACTOR_COLS = ['factor_id', 'factor_name', 'factor_family', 'formula', 'description',
               'economic_hypothesis', 'universe', 'input_fields', 'lookback', 'operators',
               'PIT_status', 'max_source_lag', 'missing_policy', 'winsorization',
               'normalization', 'expression_hash', 'complexity_depth', 'complexity_inputs',
               'complexity_interactions', 'created_date', 'created_by', 'experiment_id',
               'discovery_period', 'validation_period', 'test_period', 'status', 'notes']
GRAVEYARD_COLS = ['factor_id', 'factor_name', 'formula', 'failure_stage', 'failure_reason',
                  'discovery_metric', 'validation_metric', 'test_metric', 'yearly_direction',
                  'correlation_with_existing', 'duplicate_of', 'leakage_detected',
                  'date_killed', 'notes']
LIBRARY_COLS = ['factor_id', 'factor_name', 'formula', 'IC_mean', 'RankIC_mean', 'ICIR',
                'Q5_Q1_mean', 'Q5_Q1_median', 'positive_year_ratio', 'turnover', 'coverage',
                'OOS_IC', 'OOS_RankIC', 'bootstrap_CI', 'multiple_testing_status',
                'incremental_alpha_status', 'max_corr_existing', 'robustness_grade',
                'approved_date', 'notes']
EXPERIMENT_COLS = ['experiment_id', 'timestamp', 'universe', 'factor_count_proposed',
                   'factor_count_tested', 'factor_ids', 'discovery_period',
                   'validation_period', 'test_period', 'horizons', 'metrics',
                   'multiple_testing_method', 'code_commit', 'data_hash', 'seed',
                   'result_summary']
MT_COLS = ['attempt_id', 'experiment_id', 'factor_id', 'expression', 'expression_hash',
           'horizon', 'universe', 'label', 'variant', 'date', 'status']


def _load(path: str, cols: list[str]) -> pd.DataFrame:
    if os.path.exists(path):
        df = pd.read_parquet(path)
        for c in cols:
            if c not in df.columns:
                df[c] = None
        return df[cols]
    return pd.DataFrame(columns=cols)


def _save(df: pd.DataFrame, path: str, csv_path: str | None = None) -> None:
    df.to_parquet(path, index=False)
    if csv_path:
        df.to_csv(csv_path, index=False)


def _today() -> str:
    return date.today().isoformat()


def next_factor_id(df: pd.DataFrame) -> str:
    if df.empty:
        return 'AF_000001'
    nums = [int(x[3:]) for x in df['factor_id'] if re.fullmatch(r'AF_\d{6}', str(x))]
    return f'AF_{max(nums, default=0) + 1:06d}'


def next_experiment_id(exp: pd.DataFrame, d: str | None = None) -> str:
    d = d or _today().replace('-', '')
    if exp.empty:
        return f'AFE_{d}_0001'
    ids = [x for x in exp['experiment_id'] if str(x).startswith(f'AFE_{d}_')]
    n = max([int(x.rsplit('_', 1)[1]) for x in ids], default=0)
    return f'AFE_{d}_{n + 1:04d}'


class Registry:
    """Append-only factor registry."""

    def __init__(self):
        self.df = _load(FACTOR_REGISTRY, FACTOR_COLS)

    def add(self, **kw) -> pd.Series:
        row = {c: None for c in FACTOR_COLS}
        row.update(kw)
        if row['factor_id'] is None:
            row['factor_id'] = next_factor_id(self.df)
        if row['created_date'] is None:
            row['created_date'] = _today()
        if row['status'] is None:
            row['status'] = 'PROPOSED'
        # duplicate expression check (same universe + expression_hash + status != DUPLICATE)
        dup = self.df[(self.df['expression_hash'] == row['expression_hash']) &
                      (self.df['universe'] == row['universe'])]
        if len(dup):
            dup_id = dup.iloc[0]['factor_id']
            row['status'] = 'DUPLICATE'
            row['notes'] = f'DUPLICATE_REQUEST of {dup_id}'
            self.df = pd.concat([self.df, pd.DataFrame([row])], ignore_index=True)
            self._save()
            return self.df.iloc[-1]
        self.df = pd.concat([self.df, pd.DataFrame([row])], ignore_index=True)
        self._save()
        return self.df.iloc[-1]

    def update(self, factor_id: str, **kw) -> None:
        """Update fields of an existing row (append-only: status transitions logged in notes)."""
        m = self.df['factor_id'] == factor_id
        if not m.any():
            raise KeyError(factor_id)
        for k, v in kw.items():
            if k in self.df.columns:
                self.df.loc[m, k] = v
        self._save()

    def _save(self):
        _save(self.df, FACTOR_REGISTRY, FACTOR_REGISTRY_CSV)

    def get(self, factor_id: str) -> pd.Series:
        m = self.df['factor_id'] == factor_id
        if not m.any():
            raise KeyError(factor_id)
        return self.df[m].iloc[-1]

    def all_ids(self) -> list[str]:
        return list(self.df['factor_id'])


class Graveyard:
    def __init__(self):
        self.df = _load(GRAVEYARD, GRAVEYARD_COLS)

    def bury(self, **kw) -> None:
        row = {c: None for c in GRAVEYARD_COLS}
        row.update(kw)
        row.setdefault('date_killed', _today())
        if FAILURE_REASONS is not None and row.get('failure_reason') not in FAILURE_REASONS:
            raise ValueError(f"unknown failure_reason: {row.get('failure_reason')}")
        self.df = pd.concat([self.df, pd.DataFrame([row])], ignore_index=True)
        _save(self.df, GRAVEYARD, GRAVEYARD_CSV)

    def exists(self, factor_id: str) -> bool:
        return bool(len(self.df[self.df['factor_id'] == factor_id]))


class Library:
    def __init__(self):
        self.df = _load(LIBRARY, LIBRARY_COLS)

    def approve(self, **kw) -> None:
        row = {c: None for c in LIBRARY_COLS}
        row.update(kw)
        row.setdefault('approved_date', _today())
        self.df = pd.concat([self.df, pd.DataFrame([row])], ignore_index=True)
        _save(self.df, LIBRARY, LIBRARY_CSV)

    def exists(self, factor_id: str) -> bool:
        return bool(len(self.df[self.df['factor_id'] == factor_id]))


class Experiments:
    def __init__(self):
        self.df = _load(EXPERIMENTS, EXPERIMENT_COLS)

    def register(self, experiment_id: str, **kw) -> None:
        row = {c: None for c in EXPERIMENT_COLS}
        row.update(kw)
        row['experiment_id'] = experiment_id
        self.df = pd.concat([self.df, pd.DataFrame([row])], ignore_index=True)
        _save(self.df, EXPERIMENTS, EXPERIMENTS_CSV)

    def exists(self, experiment_id: str) -> bool:
        return bool(len(self.df[self.df['experiment_id'] == experiment_id]))


class MultipleTestingLedger:
    def __init__(self):
        self.df = _load(MT_LEDGER, MT_COLS)

    def count_attempts(self) -> int:
        return len(self.df)

    def add(self, **kw) -> None:
        row = {c: None for c in MT_COLS}
        row.update(kw)
        row.setdefault('date', _today())
        self.df = pd.concat([self.df, pd.DataFrame([row])], ignore_index=True)
        _save(self.df, MT_LEDGER, MT_LEDGER_CSV)

    def add_many(self, rows: list[dict]) -> None:
        if not rows:
            return
        for r in rows:
            self.add(**r)
