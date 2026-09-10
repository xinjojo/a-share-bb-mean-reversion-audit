"""Registry append-only / duplicate detection / graveyard / attempt-count tests
(Phase 0.1: add() returns (row, created); DUPLICATE_REQUEST lives in MT ledger)."""
import pandas as pd
import pytest

from alpha_factory import dsl, registry, multiple_testing


@pytest.fixture()
def reg(tmp_path, monkeypatch):
    # point registry paths to a temp dir to keep repo registries clean
    base = str(tmp_path)
    monkeypatch.setattr(registry, 'BASE', base)
    for stem in ['FACTOR_REGISTRY', 'GRAVEYARD', 'LIBRARY', 'CANDIDATES',
                 'EXPERIMENTS', 'MT_LEDGER', 'STATUS_HISTORY', 'GOV_EVENTS']:
        monkeypatch.setattr(registry, stem, f'{base}/{stem}.parquet')
        monkeypatch.setattr(registry, f'{stem}_CSV', f'{base}/{stem}.csv')
    return registry


def test_factor_id_increments(reg):
    r = reg.Registry()
    a, _ = r.add(factor_name='x', formula='ret_5', universe='A', expression_hash='h1')
    b, _ = r.add(factor_name='y', formula='ret_20', universe='A', expression_hash='h2')
    assert a['factor_id'] == 'AF_000001'
    assert b['factor_id'] == 'AF_000002'


def test_duplicate_expression_marked(reg):
    r = reg.Registry()
    a, created1 = r.add(factor_name='a', formula='ret_5', universe='A',
                        expression_hash='same')
    assert created1 is True
    d, created2 = r.add(factor_name='b', formula='ret_5', universe='A',
                        expression_hash='same')
    assert created2 is False
    assert d['factor_id'] == a['factor_id']  # 返回既有 canonical 行，不新增
    assert len(r.df) == 1  # registry 无第二行
    # 重复请求进 MT ledger 计为 DUPLICATE_REQUEST
    mt = reg.MultipleTestingLedger()
    mt.add(experiment_id='E', factor_id=a['factor_id'], expression='ret_5',
           expression_hash='same', horizon='D20', universe='A', label='Y',
           status='DUPLICATE_REQUEST')
    assert mt.duplicate_requests() == 1
    assert mt.unique_expressions() == 1


def test_registry_append_only_no_delete(reg):
    r = reg.Registry()
    a, _ = r.add(factor_name='a', formula='ret_5', universe='A', expression_hash='h')
    assert len(r.df) == 1
    r.add(factor_name='b', formula='ret_20', universe='A', expression_hash='h2')
    r2 = reg.Registry()  # reload from disk
    assert len(r2.df) == 2
    assert r2.get(a['factor_id'])['factor_name'] == 'a'


def test_graveyard_unknown_reason_rejected(reg):
    g = reg.Graveyard()
    with pytest.raises(ValueError):
        g.bury(factor_id='AF_000001', factor_name='x', formula='y',
               failure_stage='screening', failure_reason='NOT_A_REASON')


def test_graveyard_append_only(reg):
    g = reg.Graveyard()
    g.bury(factor_id='AF_000001', factor_name='x', formula='y',
           failure_stage='screening', failure_reason='NO_SIGNAL')
    g2 = reg.Graveyard()
    assert len(g2.df) == 1


def test_experiment_id_sequence(reg):
    e = reg.Experiments()
    eid = reg.next_experiment_id(e.df, '20260909')
    assert eid == 'AFE_20260909_0001'
    e.register(eid, universe='A')
    eid2 = reg.next_experiment_id(e.df, '20260909')
    assert eid2 == 'AFE_20260909_0002'


def test_multiple_testing_ledger_count(reg):
    mt = reg.MultipleTestingLedger()
    assert mt.count_attempts() == 0
    mt.add_many([dict(expression='a', horizon='D20', universe='A', label='Y')] * 3)
    assert mt.count_attempts() == 3
    assert mt.request_attempts() == 3


def test_hypothesis_attempt_count():
    assert multiple_testing.hypothesis_attempt_count(
        expressions=['a', 'b'], horizons=['D5', 'D20'], universes=['A'],
        labels=['Y1'], variants=1) == 4


def test_expression_reproducible(reg):
    """Registry expression hash must be reproducible via DSL."""
    r = reg.Registry()
    row, _ = r.add(factor_name='z', formula='ratio(ret_5,atr14_pct)', universe='A',
                   expression_hash=dsl.expression_hash('ratio(ret_5,atr14_pct)'))
    assert row['expression_hash'] == dsl.expression_hash('ratio( ret_5, atr14_pct )')
