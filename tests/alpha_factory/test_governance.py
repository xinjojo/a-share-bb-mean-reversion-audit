"""Phase 0.1 governance-hardening tests (13 new).

覆盖：status history append-only / immutable definition / graveyard dedup /
library gate / default dates / duplicate experiment / duplicate request counting /
attempt_id uniqueness / invalid expression logging / legacy import idempotency /
status transition machine / registry integrity audit / CSV-parquet parity。
"""
import os

import pandas as pd
import pytest

from alpha_factory import registry, legacy_import, audit_registry
from alpha_factory.registry import (Registry, Graveyard, Library, Candidates,
                                    Experiments, MultipleTestingLedger,
                                    StatusHistory, GovernanceEvents,
                                    DuplicateExperimentError,
                                    IllegalTransitionError,
                                    LibraryAdmissionError)


@pytest.fixture()
def reg(tmp_path, monkeypatch):
    base = str(tmp_path)
    monkeypatch.setattr(registry, 'BASE', base)
    for stem in ['FACTOR_REGISTRY', 'GRAVEYARD', 'LIBRARY', 'CANDIDATES',
                 'EXPERIMENTS', 'MT_LEDGER', 'STATUS_HISTORY', 'GOV_EVENTS']:
        monkeypatch.setattr(registry, stem, f'{base}/{stem}.parquet')
        monkeypatch.setattr(registry, f'{stem}_CSV', f'{base}/{stem}.csv')
    return registry


def _add_factor(r: Registry, name='f', formula='ret_5', uni='A',
                eh='h1', status='PROPOSED'):
    row, created = r.add(factor_name=name, formula=formula, universe=uni,
                         expression_hash=eh, status=status)
    return row['factor_id']


# ---- 1. status history append-only -------------------------------------
def test_status_history_append_only(reg):
    r = Registry()
    fid = _add_factor(r)
    r.set_status(fid, 'SCREENING', reason='screened')
    r.set_status(fid, 'VALIDATING', reason='validated')
    r.set_status(fid, 'KEEP', reason='approved')
    h = StatusHistory()
    evs = h.events_for(fid)
    assert list(evs['new_status']) == ['PROPOSED', 'SCREENING', 'VALIDATING', 'KEEP']
    old_filled = list(evs['old_status'].fillna('REGISTER'))
    assert old_filled == ['REGISTER', 'PROPOSED', 'SCREENING', 'VALIDATING']
    # reload from disk 后仍完整
    h2 = StatusHistory()
    assert len(h2.events_for(fid)) == 4
    assert h2.current(fid) == 'KEEP'


# ---- 2. registry definition immutable ----------------------------------
def test_registry_immutable_definition(reg):
    r = Registry()
    fid = _add_factor(r, formula='ret_5', eh='h1')
    r.set_status(fid, 'SCREENING', reason='screened')
    r.set_status(fid, 'VALIDATING', reason='validated')
    r.set_status(fid, 'KEEP', reason='approved')
    row = r.get(fid)
    assert row['formula'] == 'ret_5'
    assert row['expression_hash'] == 'h1'
    assert not hasattr(r, 'update')  # 不再有原地覆盖定义的方法
    r.annotate(fid, 'extra note')
    row2 = r.get(fid)
    assert row2['formula'] == 'ret_5'          # 定义字段未变
    assert 'extra note' in (row2['notes'] or '')
    assert 'NOTES_UPDATED' in GovernanceEvents().kinds()


# ---- 3. graveyard no duplicate -----------------------------------------
def test_graveyard_no_duplicate(reg):
    g = Graveyard()
    ok1 = g.bury(factor_id='AF_000001', factor_name='x', formula='y',
                 failure_stage='screening', failure_reason='NO_SIGNAL')
    ok2 = g.bury(factor_id='AF_000001', factor_name='x', formula='y',
                 failure_stage='screening', failure_reason='NO_SIGNAL')
    assert ok1 is True and ok2 is False
    assert len(g.df) == 1
    assert 'DUPLICATE_BURY_REQUEST' in GovernanceEvents().kinds()


# ---- 4. library gate ----------------------------------------------------
def test_library_gate(reg):
    r = Registry()
    fid = _add_factor(r, status='PROPOSED')
    lib = Library()
    # 未 KEEP → 拒绝
    with pytest.raises(LibraryAdmissionError):
        lib.approve(factor_id=fid, factor_name='f',
                    multiple_testing_status='PASS',
                    incremental_alpha_status='PASS', oos_audit=True,
                    leakage='PASS')
    assert len(lib.df) == 0
    assert 'LIBRARY_ADMISSION_REJECTED' in GovernanceEvents().kinds()
    # KEEP + 全门禁 → 准入
    r.set_status(fid, 'SCREENING')
    r.set_status(fid, 'VALIDATING')
    r.set_status(fid, 'KEEP')
    ok = lib.approve(factor_id=fid, factor_name='f',
                     multiple_testing_status='PASS',
                     incremental_alpha_status='PASS', oos_audit=True,
                     leakage='PASS')
    assert ok is True and len(lib.df) == 1
    # 门禁缺一项 → 拒绝
    r2 = Registry()
    fid2 = _add_factor(r2, name='g', eh='h2')
    r2.set_status(fid2, 'SCREENING')
    r2.set_status(fid2, 'VALIDATING')
    r2.set_status(fid2, 'KEEP')
    with pytest.raises(LibraryAdmissionError):
        lib.approve(factor_id=fid2, factor_name='g',
                    multiple_testing_status='PASS',
                    incremental_alpha_status='PASS', oos_audit=False,
                    leakage='PASS')


# ---- 5. default dates not null -----------------------------------------
def test_default_dates_not_null(reg):
    r = Registry()
    fid = _add_factor(r)
    assert r.get(fid)['created_date'] is not None
    g = Graveyard()
    g.bury(factor_id=fid, factor_name='f', formula='ret_5',
           failure_stage='screening', failure_reason='NO_SIGNAL')
    assert g.df.iloc[-1]['date_killed'] is not None
    r.set_status(fid, 'SCREENING'); r.set_status(fid, 'VALIDATING')
    r.set_status(fid, 'KEEP')
    lib = Library()
    lib.approve(factor_id=fid, factor_name='f', multiple_testing_status='PASS',
                incremental_alpha_status='PASS', oos_audit=True, leakage='PASS')
    assert lib.df.iloc[-1]['approved_date'] is not None
    e = Experiments()
    e.register('AFE_20260909_0001', universe='A')
    assert e.df.iloc[-1]['timestamp'] is not None
    mt = MultipleTestingLedger()
    mt.add(expression='ret_5', universe='A', horizon='D20', label='Y')
    assert mt.df.iloc[-1]['date'] is not None


# ---- 6. duplicate experiment rejected ----------------------------------
def test_duplicate_experiment_rejected(reg):
    e = Experiments()
    e.register('AFE_20260909_0001', universe='A')
    with pytest.raises(DuplicateExperimentError):
        e.register('AFE_20260909_0001', universe='B')
    assert len(e.df) == 1
    assert 'DUPLICATE_EXPERIMENT_REQUEST' in GovernanceEvents().kinds()


# ---- 7. duplicate request counted --------------------------------------
def test_duplicate_request_counted(reg):
    mt = MultipleTestingLedger()
    mt.add(expression='ret_5', expression_hash='h', universe='A', horizon='D20',
           label='Y', status='TESTED')
    mt.add(expression='ret_5', expression_hash='h', universe='A', horizon='D20',
           label='Y', status='DUPLICATE_REQUEST')
    mt.add(expression='ret_5', expression_hash='h', universe='A', horizon='D20',
           label='Y', status='DUPLICATE_REQUEST')
    mt.add(expression='ret_20', expression_hash='h2', universe='A', horizon='D20',
           label='Y', status='DUPLICATE_REQUEST')
    assert mt.request_attempts() == 4
    assert mt.unique_expressions() == 2
    assert mt.computed_hypotheses() == 1
    assert mt.duplicate_requests() == 3


# ---- 8. attempt_id unique ----------------------------------------------
def test_attempt_id_unique(reg):
    mt = MultipleTestingLedger()
    ids = mt.add_many([dict(expression='a', universe='A', horizon='D20', label='Y'),
                       dict(expression='b', universe='A', horizon='D20', label='Y'),
                       dict(expression='c', universe='A', horizon='D20', label='Y'),
                       dict(expression='d', universe='A', horizon='D20', label='Y'),
                       dict(expression='e', universe='A', horizon='D20', label='Y')])
    assert len(ids) == len(set(ids)) == 5
    assert ids == ['AFA_000000001', 'AFA_000000002', 'AFA_000000003',
                   'AFA_000000004', 'AFA_000000005']
    mt2 = MultipleTestingLedger()
    assert mt2.df['attempt_id'].notna().all()
    assert mt2.df['attempt_id'].is_unique


# ---- 9. invalid expression logged --------------------------------------
def test_invalid_expression_logged(reg):
    mt = MultipleTestingLedger()
    mt.record_rejected('E1', 'lead(close,5)', universe='A')            # leakage
    mt.record_rejected('E1', 'lag(ret_5,17)', universe='A')            # lookback
    mt.record_rejected('E1', 'mystery_field', universe='A')            # input
    mt.record_rejected('E1', 'ratio(ret_5', universe='A')              # syntax
    mt.record_rejected('E1', 'interaction(interaction(ret_5,atr14_pct),'
                             'interaction(bb_z,drawdown_20))', universe='A')  # complexity
    s = mt.status_counts()
    assert s.get('REJECTED_LEAKAGE', 0) == 1
    assert s.get('REJECTED_LOOKBACK', 0) == 1
    assert s.get('REJECTED_INPUT', 0) == 1
    assert s.get('REJECTED_SYNTAX', 0) == 1
    assert s.get('REJECTED_COMPLEXITY', 0) == 1
    assert mt.df['attempt_id'].notna().all()  # 非法候选也留下 attempt 痕迹


# ---- 10. legacy import idempotent --------------------------------------
def test_legacy_import_idempotent(reg):
    for _ in range(3):
        legacy_import.import_legacy()
    r = Registry()
    g = Graveyard()
    c = Candidates()
    lib = Library()
    assert len(r.df) == 14          # 12 LEGACY + 2 HOLD（幂等，不再增长）
    assert len(g.df) == 8           # 8 个 FAIL 各一条 canonical
    assert len(c.df) == 1           # breadth 只进 candidates
    assert len(lib.df) == 0         # breadth 不进 Library
    assert r.df['factor_id'].is_unique
    assert g.df['factor_id'].is_unique
    # 重复 import 不产生新的 factor_id / graveyard 行
    counts = legacy_import.import_legacy()
    assert counts['registered'] == 0
    assert len(r.df) == 14 and len(g.df) == 8


# ---- 11. status transition machine -------------------------------------
def test_status_transition_machine(reg):
    r = Registry()
    fid = _add_factor(r)
    with pytest.raises(IllegalTransitionError):
        r.set_status(fid, 'KEEP')                 # PROPOSED -> KEEP 非法
    r.set_status(fid, 'SCREENING')
    r.set_status(fid, 'VALIDATING')
    r.set_status(fid, 'KEEP')
    with pytest.raises(IllegalTransitionError):
        r.set_status(fid, 'FAIL')                 # KEEP 终态 -> FAIL 非法
    fid2 = _add_factor(r, name='g', eh='h2')
    r.set_status(fid2, 'LEAKAGE')
    with pytest.raises(IllegalTransitionError):
        r.set_status(fid2, 'KEEP')                # LEAKAGE 终态 -> KEEP 非法
    # force 只用于治理修复，仍留历史
    r.set_status(fid2, 'INVALID', force=True, reason='GOV_REPAIR')
    h = StatusHistory()
    assert list(h.events_for(fid2)['new_status']) == ['PROPOSED', 'LEAKAGE', 'INVALID']


# ---- 12. registry integrity audit --------------------------------------
def test_registry_integrity_audit(reg):
    p0, p1 = audit_registry._p0s()
    assert p0 == []                       # 干净库无 P0
    # 人为制造重复 factor_id → P0 检出
    r = Registry()
    fid = _add_factor(r)
    r.df.loc[r.df['factor_id'] == fid, 'factor_id'] = 'AF_999999'
    r.df = pd.concat([r.df, pd.DataFrame([{**r.df.iloc[-1].to_dict(),
                                           'factor_id': 'AF_999999',
                                           'factor_name': 'zz'}])],
                     ignore_index=True)
    r._save()
    p0b, _ = audit_registry._p0s()
    assert any('duplicated factor_id' in x for x in p0b)


# ---- 13. CSV/parquet parity --------------------------------------------
def test_csv_parquet_parity(reg):
    r = Registry()
    _add_factor(r)
    _add_factor(r, name='g', eh='h2')
    parq = registry.FACTOR_REGISTRY
    csvp = registry.FACTOR_REGISTRY_CSV
    assert len(pd.read_parquet(parq)) == len(pd.read_csv(csvp)) == 2
    # 破坏 CSV 镜像 → 重建恢复
    pd.DataFrame(columns=registry.FACTOR_COLS).to_csv(csvp, index=False)
    assert len(pd.read_csv(csvp)) == 0
    registry.rebuild_csv_mirrors()
    assert len(pd.read_csv(csvp)) == len(pd.read_parquet(parq)) == 2
    # 审计不再报 parity P0
    p0, _ = audit_registry._p0s()
    assert not any('parity' in x for x in p0)
