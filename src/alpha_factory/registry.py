"""A-Share Alpha Factory — append-only Registries (Phase 0.1 governance-hardened).

治理规则（Phase 0.1 冻结）：
- FACTOR_REGISTRY 是 factor identity / immutable definition：factor_id、factor_name、
  formula、canonical_expression、expression_hash、factor_family、universe、
  input_fields、lookback、operators、created_date、created_by 创建后不得修改。
- 状态变化一律追加到 FACTOR_STATUS_HISTORY（append-only），FACTOR_REGISTRY 的
  status 列只是 derived current status。
- Graveyard：同一 factor_id 最多一条 canonical 记录；重复 bury 只记
  DUPLICATE_BURY_REQUEST governance event，不新增行。
- Library：只有 status==KEEP 且 multiple_testing/incremental/OOS/leakage 全 PASS
  才能进入；否则 LIBRARY_ADMISSION_REJECTED。
- ALPHA_CANDIDATES：VALIDAATING 候选（如 breadth），不属于正式 Library。
- Experiments：experiment_id 全局唯一，重复注册抛 DuplicateExperimentError 并记
  DUPLICATE_EXPERIMENT_REQUEST。
- MultipleTestingLedger：attempt_id（AFA_%09d）单调永久唯一；计数口径拆分：
  TOTAL_REQUEST_ATTEMPTS / TOTAL_UNIQUE_EXPRESSIONS / TOTAL_COMPUTED_HYPOTHESES /
  TOTAL_DUPLICATE_REQUESTS / TOTAL_REJECTED_COMPLEXITY / TOTAL_REJECTED_LEAKAGE /
  TOTAL_REJECTED_LOOKBACK / TOTAL_REJECTED_INPUT / TOTAL_REJECTED_SYNTAX。
- Crash safety：parquet 为 canonical（temp + fsync + atomic replace），CSV 是
  regenerated mirror；CSV/parquet 不一致时可自动重建 CSV。
- 状态机：PROPOSED→SCREENING→VALIDATING→KEEP / …→FAIL→ARCHIVED / DUPLICATE /
  INVALID / LEAKAGE；非法迁移禁止（除非显式 governance 修复 + force）。
- 不原地改写历史 failure_reason；更正走 CORRECTION governance event。
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime

import pandas as pd

try:  # allow direct-module execution in tests (src on sys.path)
    from alpha_factory import dsl
    FAILURE_REASONS = dsl.FAILURE_REASONS
except ImportError:  # pragma: no cover
    dsl = None
    FAILURE_REASONS = None

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    'research', 'alpha_factory')

FACTOR_REGISTRY = os.path.join(BASE, 'FACTOR_REGISTRY.parquet')
FACTOR_REGISTRY_CSV = os.path.join(BASE, 'FACTOR_REGISTRY.csv')
GRAVEYARD = os.path.join(BASE, 'ALPHA_GRAVEYARD.parquet')
GRAVEYARD_CSV = os.path.join(BASE, 'ALPHA_GRAVEYARD.csv')
LIBRARY = os.path.join(BASE, 'ALPHA_LIBRARY.parquet')
LIBRARY_CSV = os.path.join(BASE, 'ALPHA_LIBRARY.csv')
CANDIDATES = os.path.join(BASE, 'ALPHA_CANDIDATES.parquet')
CANDIDATES_CSV = os.path.join(BASE, 'ALPHA_CANDIDATES.csv')
EXPERIMENTS = os.path.join(BASE, 'EXPERIMENT_REGISTRY.parquet')
EXPERIMENTS_CSV = os.path.join(BASE, 'EXPERIMENT_REGISTRY.csv')
MT_LEDGER = os.path.join(BASE, 'MULTIPLE_TESTING_LEDGER.parquet')
MT_LEDGER_CSV = os.path.join(BASE, 'MULTIPLE_TESTING_LEDGER.csv')
STATUS_HISTORY = os.path.join(BASE, 'FACTOR_STATUS_HISTORY.parquet')
STATUS_HISTORY_CSV = os.path.join(BASE, 'FACTOR_STATUS_HISTORY.csv')
GOV_EVENTS = os.path.join(BASE, 'GOVERNANCE_EVENTS.parquet')
GOV_EVENTS_CSV = os.path.join(BASE, 'GOVERNANCE_EVENTS.csv')

# ---------------------------------------------------------------- schemas
FACTOR_COLS = ['factor_id', 'factor_name', 'factor_family', 'formula',
               'canonical_expression', 'description', 'economic_hypothesis',
               'universe', 'input_fields', 'lookback', 'operators',
               'PIT_status', 'max_source_lag', 'missing_policy', 'winsorization',
               'normalization', 'expression_hash', 'complexity_depth',
               'complexity_inputs', 'complexity_interactions', 'created_date',
               'created_by', 'experiment_id', 'discovery_period',
               'validation_period', 'test_period', 'status', 'notes']
GRAVEYARD_COLS = ['factor_id', 'factor_name', 'formula', 'failure_stage',
                  'failure_reason', 'discovery_metric', 'validation_metric',
                  'test_metric', 'yearly_direction', 'correlation_with_existing',
                  'duplicate_of', 'leakage_detected', 'date_killed', 'notes']
LIBRARY_COLS = ['factor_id', 'factor_name', 'formula', 'IC_mean', 'RankIC_mean',
                'ICIR', 'Q5_Q1_mean', 'Q5_Q1_median', 'positive_year_ratio',
                'turnover', 'coverage', 'OOS_IC', 'OOS_RankIC', 'bootstrap_CI',
                'multiple_testing_status', 'incremental_alpha_status',
                'oos_audit', 'leakage', 'max_corr_existing', 'robustness_grade',
                'approved_date', 'notes']
CANDIDATE_COLS = ['factor_id', 'factor_name', 'formula', 'status',
                  'candidate_reason', 'added_date', 'notes']
EXPERIMENT_COLS = ['experiment_id', 'timestamp', 'universe',
                   'factor_count_proposed', 'factor_count_tested', 'factor_ids',
                   'discovery_period', 'validation_period', 'test_period',
                   'horizons', 'metrics', 'multiple_testing_method', 'code_commit',
                   'data_hash', 'seed', 'result_summary']
MT_COLS = ['attempt_id', 'experiment_id', 'factor_id', 'expression',
           'expression_hash', 'horizon', 'universe', 'label', 'variant',
           'date', 'status', 'reason']
STATUS_HISTORY_COLS = ['event_id', 'factor_id', 'timestamp', 'old_status',
                       'new_status', 'experiment_id', 'reason', 'code_commit',
                       'notes']
GOV_COLS = ['event_id', 'timestamp', 'kind', 'factor_id', 'experiment_id',
            'detail', 'code_commit']

# 定义字段：创建后 immutable
IMMUTABLE_COLS = {'factor_id', 'factor_name', 'factor_family', 'formula',
                  'canonical_expression', 'expression_hash', 'universe',
                  'input_fields', 'lookback', 'operators', 'created_date',
                  'created_by'}

# ---------------------------------------------------------------- status machine
TERMINAL_STATUSES = {'KEEP', 'FAIL', 'ARCHIVED', 'DUPLICATE', 'INVALID', 'LEAKAGE'}
LEGAL_TRANSITIONS = {
    'PROPOSED': {'SCREENING', 'VALIDATING', 'FAIL', 'DUPLICATE', 'INVALID',
                 'LEAKAGE', 'ARCHIVED'},
    'SCREENING': {'VALIDATING', 'FAIL', 'DUPLICATE', 'INVALID', 'LEAKAGE',
                  'ARCHIVED'},
    'VALIDATING': {'KEEP', 'FAIL', 'DUPLICATE', 'INVALID', 'LEAKAGE', 'ARCHIVED'},
    'KEEP': set(),
    'FAIL': set(),
    'ARCHIVED': set(),
    'DUPLICATE': set(),
    'INVALID': set(),
    'LEAKAGE': set(),
}


class DuplicateExperimentError(Exception):
    pass


class IllegalTransitionError(Exception):
    pass


class LibraryAdmissionError(Exception):
    pass


# ---------------------------------------------------------------- io helpers
def _atomic_replace_parquet(df: pd.DataFrame, path: str) -> None:
    tmp = f'{path}.tmp'
    df.to_parquet(tmp, index=False)
    with open(tmp, 'rb') as f:
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _atomic_replace_csv(df: pd.DataFrame, path: str) -> None:
    tmp = f'{path}.tmp'
    df.to_csv(tmp, index=False)
    with open(tmp, 'rb') as f:
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _save(df: pd.DataFrame, path: str, csv_path: str | None = None) -> None:
    """parquet 为 canonical；CSV 是 derived mirror（写失败不阻塞，可重建）。"""
    _atomic_replace_parquet(df, path)
    if csv_path:
        try:
            _atomic_replace_csv(df, csv_path)
        except Exception:  # pragma: no cover - mirror regenerable
            pass


def _load(path: str, cols: list[str]) -> pd.DataFrame:
    if os.path.exists(path):
        df = pd.read_parquet(path)
        for c in cols:
            if c not in df.columns:
                df[c] = None
        return df[cols]
    return pd.DataFrame(columns=cols)


def _today() -> str:
    return date.today().isoformat()


def _now_ts() -> str:
    return datetime.now().isoformat(timespec='seconds')


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


def next_event_id(events: pd.DataFrame) -> str:
    if events.empty:
        return 'EVT_000000001'
    nums = [int(x[4:]) for x in events['event_id']
            if re.fullmatch(r'EVT_\d{9}', str(x))]
    return f'EVT_{max(nums, default=0) + 1:09d}'


def next_attempt_id(mt: pd.DataFrame) -> str:
    if mt.empty:
        return 'AFA_000000001'
    nums = [int(x[4:]) for x in mt['attempt_id']
            if re.fullmatch(r'AFA_\d{9}', str(x))]
    return f'AFA_{max(nums, default=0) + 1:09d}'


def classify_rejection(expr: str, universe: str = 'A') -> tuple[str, str]:
    """把非法候选表达式归类为 REJECTED_* 状态。返回 (status, reason)。"""
    if dsl is None:  # pragma: no cover
        return 'REJECTED_SYNTAX', 'dsl unavailable'
    try:
        node = dsl.parse(expr)
    except ValueError as ex:
        msg = str(ex)
        if any(k in msg for k in ('forbidden', 'future', 'lead', 'fwd')):
            return 'REJECTED_LEAKAGE', msg
        return 'REJECTED_SYNTAX', msg
    try:
        dsl.validate(node, universe=universe)
    except ValueError as ex:
        msg = str(ex)
        if 'lookback' in msg:
            return 'REJECTED_LOOKBACK', msg
        if 'unknown input field' in msg:
            return 'REJECTED_INPUT', msg
        if any(k in msg for k in ('forbidden', 'future', 'lead', 'fwd')):
            return 'REJECTED_LEAKAGE', msg
        return 'REJECTED_SYNTAX', msg
    reject = dsl.check_complexity(node)
    if reject:
        return 'REJECTED_COMPLEXITY', reject
    return 'PROPOSED', 'valid'


# ---------------------------------------------------------------- governance events
class GovernanceEvents:
    """append-only 治理事件账（DUPLICATE_BURY_REQUEST 等）。"""

    def __init__(self):
        self.df = _load(GOV_EVENTS, GOV_COLS)

    def log(self, kind: str, factor_id: str | None = None,
            experiment_id: str | None = None, detail: str | None = None,
            code_commit: str | None = None) -> str:
        row = {c: None for c in GOV_COLS}
        row['event_id'] = next_event_id(self.df)
        row['timestamp'] = _now_ts()
        row['kind'] = kind
        row['factor_id'] = factor_id
        row['experiment_id'] = experiment_id
        row['detail'] = detail
        row['code_commit'] = code_commit
        self.df = pd.concat([self.df, pd.DataFrame([row])], ignore_index=True)
        _save(self.df, GOV_EVENTS, GOV_EVENTS_CSV)
        return row['event_id']

    def kinds(self) -> dict:
        return self.df['kind'].fillna('UNKNOWN').value_counts().to_dict()


# ---------------------------------------------------------------- status history
class StatusHistory:
    """每一次状态变化的 append-only 记录。current status 由此推导。"""

    def __init__(self):
        self.df = _load(STATUS_HISTORY, STATUS_HISTORY_COLS)

    def append(self, factor_id: str, old_status: str | None, new_status: str,
               experiment_id: str | None = None, reason: str | None = None,
               code_commit: str | None = None, notes: str | None = None) -> str:
        row = {c: None for c in STATUS_HISTORY_COLS}
        row['event_id'] = next_event_id(self.df)
        row['factor_id'] = factor_id
        if row['timestamp'] is None:
            row['timestamp'] = _now_ts()
        row['old_status'] = old_status
        row['new_status'] = new_status
        row['experiment_id'] = experiment_id
        row['reason'] = reason
        row['code_commit'] = code_commit
        row['notes'] = notes
        self.df = pd.concat([self.df, pd.DataFrame([row])], ignore_index=True)
        _save(self.df, STATUS_HISTORY, STATUS_HISTORY_CSV)
        return row['event_id']

    def current(self, factor_id: str) -> str | None:
        m = self.df[self.df['factor_id'] == factor_id]
        if m.empty:
            return None
        return m.iloc[-1]['new_status']

    def events_for(self, factor_id: str) -> pd.DataFrame:
        return self.df[self.df['factor_id'] == factor_id].reset_index(drop=True)


# ---------------------------------------------------------------- Registry
class Registry:
    """Factor identity / immutable definition registry（一行一个 factor）。"""

    def __init__(self):
        self.df = _load(FACTOR_REGISTRY, FACTOR_COLS)
        self.history = StatusHistory()

    def add(self, force_distinct: bool = False, **kw) -> tuple[pd.Series, bool]:
        """追加一个 factor 定义。返回 (row, created)。
        同 expression_hash（无 hash 时用 formula）+ universe 已存在 → 返回既有行，
        created=False（调用方应把该请求记入 MT ledger 为 DUPLICATE_REQUEST）。
        force_distinct=True 仅限治理认可的 curated 导入：当 hash 撞上不同
        factor_name 的历史行时（如 legacy proxy 公式与信号定义字段同形），
        仍注册并记 EXPRESSION_HASH_AMBIGUITY governance event。
        """
        row = {c: None for c in FACTOR_COLS}
        row.update(kw)
        # 归一化 period 字段类型，防止 str/int 混入造成 parquet 写入崩溃
        for _c in ('validation_period', 'test_period'):
            _v = row.get(_c)
            if _v is not None and not isinstance(_v, (int, float)):
                try:
                    row[_c] = int(_v)
                except (TypeError, ValueError):
                    pass
        if row['factor_id'] is None:
            row['factor_id'] = next_factor_id(self.df)
        if row['created_date'] is None:
            row['created_date'] = _today()
        if row['status'] is None:
            row['status'] = 'PROPOSED'
        if row['canonical_expression'] is None:
            row['canonical_expression'] = row['formula']
            if dsl is not None and row['formula']:
                try:
                    row['canonical_expression'] = dsl.canonical_string(row['formula'])
                except Exception:
                    pass
        key_hash = row['expression_hash']
        if key_hash is not None:
            dup = self.df[(self.df['expression_hash'] == key_hash) &
                          (self.df['universe'] == row['universe'])]
        else:
            dup = self.df[(self.df['formula'] == row['formula']) &
                          (self.df['universe'] == row['universe'])]
        if len(dup):
            if force_distinct and dup.iloc[0]['factor_name'] != row['factor_name']:
                # curated 导入中的表达式同形（legacy proxy 与信号定义字段），
                # 允许注册但必须留治理痕迹，供 audit 识别为已记录例外。
                GovernanceEvents().log(
                    'EXPRESSION_HASH_AMBIGUITY', factor_id=row['factor_id'],
                    detail=(f"same expression_hash {key_hash} as "
                            f"{dup.iloc[0]['factor_id']} "
                            f"({dup.iloc[0]['factor_name']}); force_distinct "
                            f"registered for {row['factor_name']}"))
            else:
                return dup.iloc[0], False
        self.df = pd.concat([self.df, pd.DataFrame([row])], ignore_index=True)
        # 每次 append 前重新读取 history（避免陈旧实例覆盖其他写者）
        StatusHistory().append(factor_id=row['factor_id'], old_status=None,
                               new_status=row['status'],
                               experiment_id=row['experiment_id'],
                               reason='REGISTER', notes='initial status')
        self._save()
        return self.df.iloc[-1], True

    def set_status(self, factor_id: str, new_status: str,
                   experiment_id: str | None = None, reason: str | None = None,
                   code_commit: str | None = None, notes: str | None = None,
                   force: bool = False) -> None:
        """状态迁移：追加 history，更新 derived status。
        force=True 仅供治理修复/迁移使用（仍留下完整 history 记录）。
        """
        m = self.df['factor_id'] == factor_id
        if not m.any():
            raise KeyError(factor_id)
        h = StatusHistory()  # 重新读取最新 history（避免陈旧实例覆盖）
        old = h.current(factor_id) or self.df.loc[m, 'status'].iloc[-1]
        if not force and new_status not in LEGAL_TRANSITIONS.get(old, set()):
            raise IllegalTransitionError(
                f'illegal status transition {old} -> {new_status} for {factor_id}')
        h.append(factor_id=factor_id, old_status=old,
                 new_status=new_status, experiment_id=experiment_id,
                 reason=reason, code_commit=code_commit, notes=notes)
        self.df.loc[m, 'status'] = new_status
        self._save()

    def current_status(self, factor_id: str) -> str | None:
        m = self.df['factor_id'] == factor_id
        if not m.any():
            return None
        st = StatusHistory().current(factor_id)
        return st if st is not None else self.df.loc[m, 'status'].iloc[-1]

    def annotate(self, factor_id: str, notes: str, reason: str = 'NOTES_UPDATED') -> None:
        """非定义字段（notes）的审计式更新：不可改定义字段。"""
        m = self.df['factor_id'] == factor_id
        if not m.any():
            raise KeyError(factor_id)
        old = self.df.loc[m, 'notes'].iloc[-1]
        new = f'{old}; {notes}' if pd.notna(old) and old else notes
        self.df.loc[m, 'notes'] = new
        GovernanceEvents().log(reason, factor_id=factor_id, detail=f'notes: {notes}')
        self._save()

    def get(self, factor_id: str) -> pd.Series:
        m = self.df['factor_id'] == factor_id
        if not m.any():
            raise KeyError(factor_id)
        return self.df[m].iloc[-1]

    def all_ids(self) -> list[str]:
        return list(self.df['factor_id'])

    def _save(self):
        _save(self.df, FACTOR_REGISTRY, FACTOR_REGISTRY_CSV)


# ---------------------------------------------------------------- Graveyard
class Graveyard:
    """失败因子墓地。同一 factor_id 最多一条 canonical 记录。"""

    def __init__(self):
        self.df = _load(GRAVEYARD, GRAVEYARD_COLS)

    def bury(self, **kw) -> bool:
        """埋入失败因子。返回 True=新记录，False=重复请求（已记 governance event）。"""
        fid = kw.get('factor_id')
        if fid is None:
            raise ValueError('factor_id required')
        if self.exists(fid):
            GovernanceEvents().log('DUPLICATE_BURY_REQUEST', factor_id=fid,
                                   detail='duplicate bury request ignored '
                                          '(canonical record already exists)')
            return False
        row = {c: None for c in GRAVEYARD_COLS}
        row.update(kw)
        if row['date_killed'] is None:
            row['date_killed'] = _today()
        if FAILURE_REASONS is not None and row.get('failure_reason') not in FAILURE_REASONS:
            raise ValueError(f"unknown failure_reason: {row.get('failure_reason')}")
        self.df = pd.concat([self.df, pd.DataFrame([row])], ignore_index=True)
        _save(self.df, GRAVEYARD, GRAVEYARD_CSV)
        return True

    def correct_failure_reason(self, factor_id: str, new_reason: str, why: str) -> None:
        """不原地改写 failure_reason；只记 CORRECTION governance event。"""
        m = self.df[self.df['factor_id'] == factor_id]
        if m.empty:
            raise KeyError(factor_id)
        old = m.iloc[-1]['failure_reason']
        GovernanceEvents().log('FAILURE_REASON_CORRECTION', factor_id=factor_id,
                               detail=f'{old} -> {new_reason}; why={why}')

    def exists(self, factor_id: str) -> bool:
        return bool(len(self.df[self.df['factor_id'] == factor_id]))

    def _save(self):
        _save(self.df, GRAVEYARD, GRAVEYARD_CSV)


# ---------------------------------------------------------------- Library / Candidates
class Library:
    """正式 Alpha Library：只允许 fully approved factors。"""

    GATE_FIELDS = ['multiple_testing_status', 'incremental_alpha_status',
                   'oos_audit', 'leakage']

    def __init__(self):
        self.df = _load(LIBRARY, LIBRARY_COLS)

    def approve(self, **kw) -> bool:
        fid = kw.get('factor_id')
        if fid is None:
            raise ValueError('factor_id required')
        if self.exists(fid):
            GovernanceEvents().log('DUPLICATE_APPROVE_REQUEST', factor_id=fid,
                                   detail='duplicate approve request ignored')
            return False
        problems = []
        cur = Registry().current_status(fid)
        if cur != 'KEEP':
            problems.append(f'current status {cur} != KEEP')
        for f in self.GATE_FIELDS:
            v = kw.get(f)
            ok = (v is True) or (isinstance(v, str) and v.upper() == 'PASS')
            if not ok:
                problems.append(f'{f} not PASS ({v})')
        if problems:
            GovernanceEvents().log('LIBRARY_ADMISSION_REJECTED', factor_id=fid,
                                   detail='; '.join(problems))
            raise LibraryAdmissionError('; '.join(problems))
        row = {c: None for c in LIBRARY_COLS}
        row.update(kw)
        if row['approved_date'] is None:
            row['approved_date'] = _today()
        self.df = pd.concat([self.df, pd.DataFrame([row])], ignore_index=True)
        _save(self.df, LIBRARY, LIBRARY_CSV)
        return True

    def remove(self, factor_id: str, reason: str) -> None:
        """从 Library 移出（治理修复用）。移出前先留 governance event。"""
        m = self.df['factor_id'] == factor_id
        if not m.any():
            raise KeyError(factor_id)
        row = self.df[m].iloc[-1]
        GovernanceEvents().log('REMOVED_FROM_LIBRARY_NOT_APPROVED', factor_id=factor_id,
                               detail=f'{reason}; removed_row={row.to_dict()}')
        self.df = self.df[~m].reset_index(drop=True)
        _save(self.df, LIBRARY, LIBRARY_CSV)

    def exists(self, factor_id: str) -> bool:
        return bool(len(self.df[self.df['factor_id'] == factor_id]))


class Candidates:
    """VALIDATING 候选（ALPHA_CANDIDATES），不属于正式 Library。"""

    def __init__(self):
        self.df = _load(CANDIDATES, CANDIDATE_COLS)

    def add(self, **kw) -> bool:
        fid = kw.get('factor_id')
        if fid is None:
            raise ValueError('factor_id required')
        if self.exists(fid):
            return False
        row = {c: None for c in CANDIDATE_COLS}
        row.update(kw)
        if row['added_date'] is None:
            row['added_date'] = _today()
        if row['status'] is None:
            row['status'] = 'VALIDATING'
        self.df = pd.concat([self.df, pd.DataFrame([row])], ignore_index=True)
        _save(self.df, CANDIDATES, CANDIDATES_CSV)
        return True

    def exists(self, factor_id: str) -> bool:
        return bool(len(self.df[self.df['factor_id'] == factor_id]))


# ---------------------------------------------------------------- Experiments
class Experiments:
    def __init__(self):
        self.df = _load(EXPERIMENTS, EXPERIMENT_COLS)

    def register(self, experiment_id: str, **kw) -> None:
        if self.exists(experiment_id):
            GovernanceEvents().log('DUPLICATE_EXPERIMENT_REQUEST',
                                   experiment_id=experiment_id,
                                   detail='duplicate experiment_id rejected')
            raise DuplicateExperimentError(experiment_id)
        row = {c: None for c in EXPERIMENT_COLS}
        row.update(kw)
        row['experiment_id'] = experiment_id
        if row['timestamp'] is None:
            row['timestamp'] = _now_ts()
        self.df = pd.concat([self.df, pd.DataFrame([row])], ignore_index=True)
        _save(self.df, EXPERIMENTS, EXPERIMENTS_CSV)

    def exists(self, experiment_id: str) -> bool:
        return bool(len(self.df[self.df['experiment_id'] == experiment_id]))

    def _save(self):
        _save(self.df, EXPERIMENTS, EXPERIMENTS_CSV)


# ---------------------------------------------------------------- Multiple Testing Ledger
class MultipleTestingLedger:
    """attempt 账本：每次 proposed/duplicate/rejected/computed/screened 都留记录。
    attempt_id 单调永久唯一；计数口径见模块 docstring。
    """

    def __init__(self):
        self.df = _load(MT_LEDGER, MT_COLS)

    def add(self, **kw) -> str:
        row = {c: None for c in MT_COLS}
        row.update(kw)
        if row['attempt_id'] is None:
            row['attempt_id'] = next_attempt_id(self.df)
        if row['date'] is None:
            row['date'] = _today()
        if row['status'] is None:
            row['status'] = 'PROPOSED'
        self.df = pd.concat([self.df, pd.DataFrame([row])], ignore_index=True)
        _save(self.df, MT_LEDGER, MT_LEDGER_CSV)
        return row['attempt_id']

    def add_many(self, rows: list[dict]) -> list[str]:
        ids = []
        for r in rows:
            ids.append(self.add(**r))
        return ids

    def record_rejected(self, experiment_id: str, expression: str,
                        universe: str = 'A', horizon: str | None = None,
                        label: str | None = None, variant: int = 1,
                        factor_id: str | None = None) -> str:
        """非法候选也必须留 attempt 记录（REJECTED_* 状态）。"""
        status, reason = classify_rejection(expression, universe=universe)
        if status == 'PROPOSED':  # 合法表达式不该走这里
            status = 'REJECTED_SYNTAX'
            reason = 'record_rejected called on valid expression'
        eh = None
        if dsl is not None:
            try:
                eh = dsl.expression_hash(expression)
            except Exception:
                eh = None
        return self.add(experiment_id=experiment_id, factor_id=factor_id,
                        expression=expression, expression_hash=eh,
                        horizon=horizon, universe=universe, label=label,
                        variant=variant, status=status, reason=reason)

    # ---- counters（口径见模块 docstring）----
    def request_attempts(self) -> int:
        return len(self.df)

    def count_attempts(self) -> int:  # 兼容旧名
        return len(self.df)

    def unique_expressions(self) -> int:
        d = self.df['expression_hash'].dropna()
        return int(d.nunique())

    def computed_hypotheses(self) -> int:
        d = self.df[self.df['status'] == 'TESTED']
        if d.empty:
            return 0
        keys = d[['expression_hash', 'universe', 'horizon', 'label']].fillna('NA')
        return int(keys.agg(tuple, axis=1).nunique())

    def status_counts(self) -> dict:
        return self.df['status'].fillna('UNKNOWN').value_counts().to_dict()

    def duplicate_requests(self) -> int:
        return int(self.status_counts().get('DUPLICATE_REQUEST', 0))

    def rejected_complexity(self) -> int:
        return int(self.status_counts().get('REJECTED_COMPLEXITY', 0))

    def rejected_leakage(self) -> int:
        return int(self.status_counts().get('REJECTED_LEAKAGE', 0))

    def rejected_lookback(self) -> int:
        return int(self.status_counts().get('REJECTED_LOOKBACK', 0))

    def rejected_input(self) -> int:
        return int(self.status_counts().get('REJECTED_INPUT', 0))

    def rejected_syntax(self) -> int:
        return int(self.status_counts().get('REJECTED_SYNTAX', 0))

    def _save(self):
        _save(self.df, MT_LEDGER, MT_LEDGER_CSV)

    def summary(self) -> dict:
        return {
            'TOTAL_REQUEST_ATTEMPTS': self.request_attempts(),
            'TOTAL_UNIQUE_EXPRESSIONS': self.unique_expressions(),
            'TOTAL_COMPUTED_HYPOTHESES': self.computed_hypotheses(),
            'TOTAL_DUPLICATE_REQUESTS': self.duplicate_requests(),
            'TOTAL_REJECTED_COMPLEXITY': self.rejected_complexity(),
            'TOTAL_REJECTED_LEAKAGE': self.rejected_leakage(),
            'TOTAL_REJECTED_LOOKBACK': self.rejected_lookback(),
            'TOTAL_REJECTED_INPUT': self.rejected_input(),
            'TOTAL_REJECTED_SYNTAX': self.rejected_syntax(),
        }


# ---------------------------------------------------------------- mirror rebuild
def store_paths() -> list[tuple[str, str | None, list[str]]]:
    """动态读取当前模块路径（测试可 monkeypatch）。"""
    return [
        (FACTOR_REGISTRY, FACTOR_REGISTRY_CSV, FACTOR_COLS),
        (GRAVEYARD, GRAVEYARD_CSV, GRAVEYARD_COLS),
        (LIBRARY, LIBRARY_CSV, LIBRARY_COLS),
        (CANDIDATES, CANDIDATES_CSV, CANDIDATE_COLS),
        (EXPERIMENTS, EXPERIMENTS_CSV, EXPERIMENT_COLS),
        (MT_LEDGER, MT_LEDGER_CSV, MT_COLS),
        (STATUS_HISTORY, STATUS_HISTORY_CSV, STATUS_HISTORY_COLS),
        (GOV_EVENTS, GOV_EVENTS_CSV, GOV_COLS),
    ]


_ALL_STORES = store_paths()


def rebuild_csv_mirrors() -> dict[str, int]:
    """从 canonical parquet 重建全部 CSV mirror。返回 {name: rows}。"""
    out = {}
    for parq, csvp, cols in store_paths():
        if not os.path.exists(parq):
            continue
        df = _load(parq, cols)
        _atomic_replace_csv(df, csvp)
        out[os.path.basename(parq)] = len(df)
    return out
