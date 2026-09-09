"""Registry append-only / duplicate detection / graveyard / attempt-count tests."""
import pandas as pd
import pytest

from alpha_factory import dsl, registry, multiple_testing


@pytest.fixture()
def reg(tmp_path, monkeypatch):
    # point registry paths to a temp dir to keep repo registries clean
    base = str(tmp_path)
    monkeypatch.setattr(registry, 'BASE', base)
    monkeypatch.setattr(registry, 'FACTOR_REGISTRY', f'{base}/FACTOR_REGISTRY.parquet')
    monkeypatch.setattr(registry, 'FACTOR_REGISTRY_CSV', f'{base}/FACTOR_REGISTRY.csv')
    monkeypatch.setattr(registry, 'GRAVEYARD', f'{base}/ALPHA_GRAVEYARD.parquet')
    monkeypatch.setattr(registry, 'GRAVEYARD_CSV', f'{base}/ALPHA_GRAVEYARD.csv')
    monkeypatch.setattr(registry, 'LIBRARY', f'{base}/ALPHA_LIBRARY.parquet')
    monkeypatch.setattr(registry, 'LIBRARY_CSV', f'{base}/ALPHA_LIBRARY.csv')
    monkeypatch.setattr(registry, 'EXPERIMENTS', f'{base}/EXPERIMENT_REGISTRY.parquet')
    monkeypatch.setattr(registry, 'EXPERIMENTS_CSV', f'{base}/EXPERIMENT_REGISTRY.csv')
    monkeypatch.setattr(registry, 'MT_LEDGER', f'{base}/MULTIPLE_TESTING_LEDGER.parquet')
    return registry


def test_factor_id_increments(reg):
    r = reg.Registry()
    a = r.add(factor_name='x', formula='ret_5', universe='A', expression_hash='h1')
    b = r.add(factor_name='y', formula='ret_20', universe='A', expression_hash='h2')
    assert a['factor_id'] == 'AF_000001'
    assert b['factor_id'] == 'AF_000002'


def test_duplicate_expression_marked(reg):
    r = reg.Registry()
    r.add(factor_name='a', formula='ret_5', universe='A', expression_hash='same')
    d = r.add(factor_name='b', formula='ret_5', universe='A', expression_hash='same')
    assert d['status'] == 'DUPLICATE'
    assert 'DUPLICATE_REQUEST of AF_000001' in (d['notes'] or '')


def test_registry_append_only_no_delete(reg):
    r = reg.Registry()
    a = r.add(factor_name='a', formula='ret_5', universe='A', expression_hash='h')
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


def test_hypothesis_attempt_count():
    assert multiple_testing.hypothesis_attempt_count(
        expressions=['a', 'b'], horizons=['D5', 'D20'], universes=['A'],
        labels=['Y1'], variants=1) == 4


def test_expression_reproducible(reg):
    """Registry expression hash must be reproducible via DSL."""
    r = reg.Registry()
    row = r.add(factor_name='z', formula='ratio(ret_5,atr14_pct)', universe='A',
                expression_hash=dsl.expression_hash('ratio(ret_5,atr14_pct)'))
    assert row['expression_hash'] == dsl.expression_hash('ratio( ret_5, atr14_pct )')
