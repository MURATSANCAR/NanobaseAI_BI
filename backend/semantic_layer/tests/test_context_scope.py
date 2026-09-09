from datetime import date
from types import SimpleNamespace

import pytest

from semantic_bridge.app import Runtime
from semantic_layer.models import ColumnProfile, SchemaProfile
from semantic_layer.runtime.context_scope import extract_scope, execution_profiles, select_profiles


def profiles():
    return [SchemaProfile(datasource_id='d', entity='ACCOUNT', table_name=f'ERP_{code}_ACCOUNT',
                          table_pattern='ERP_{n0}_ACCOUNT', schema_name='dbo', context={'n0': code},
                          columns=[ColumnProfile('ID', is_primary_key=True), ColumnProfile('ACTIVE')])
            for code in ['211', '411']]


@pytest.mark.parametrize('question', ['411 firmasında kayıt sayısı', '411 firmasındaki kayıt sayısı', 'firma 411 kayıt sayısı'])
def test_explicit_scope_comes_from_source_labels(question):
    assert extract_scope(question, ['Firma'], profiles()) == ({'n0': '411'}, [])
    assert extract_scope(question, ['Bölge'], profiles()) == ({}, [])
    assert extract_scope('411 bölgesindeki kayıt sayısı', ['Bölge'], profiles()) == ({'n0': '411'}, [])


@pytest.mark.parametrize('question', ['999 firması', '211 ve 411 firmaları', 'firma 211 ve 411',
                                     '411 firması hariç', '411 firması değil 211 firması', '211-411 firmaları', '411 firması dışındaki kayıtlar'])
def test_unavailable_or_compound_scope_cannot_be_silently_narrowed(question):
    _, errors = extract_scope(question, ['Firma'], profiles())
    assert errors


def test_period_numbers_do_not_become_physical_context():
    assert extract_scope('2026 ilk 10 satış', ['Firma'], profiles()) == ({}, [])


def test_runtime_executes_only_the_explicit_context_and_keeps_global_tables():
    r = Runtime.__new__(Runtime)
    r.settings = SimpleNamespace(context={'n0': '211'}, dialect='tsql')
    r.profiles = profiles()
    sql = r._physical('SELECT COUNT(DISTINCT ID) FROM ACCOUNT WHERE ACTIVE=1',
                      (date(2026, 1, 1), date(2027, 1, 1)), scope={'n0': '411'})
    assert 'ERP_411_ACCOUNT' in sql and 'ERP_211_ACCOUNT' not in sql
    global_table = SchemaProfile(datasource_id='d', entity='GLOBAL', table_name='GLOBAL', table_pattern='GLOBAL')
    assert global_table in select_profiles(r.profiles + [global_table], {'n0': '411'})


@pytest.mark.parametrize('name', ['dbo.ERP_211_ACCOUNT', 'dbo_ERP_211_ACCOUNT'])
def test_explicit_sql_cannot_expand_back_out_of_question_scope(name):
    with pytest.raises(ValueError, match='kapsamının dışında'):
        execution_profiles('SELECT ID FROM ' + name, profiles(), {'n0': '411'}, 'tsql')


def test_unscoped_requests_keep_the_existing_profile_selection():
    ps = profiles()
    assert execution_profiles('SELECT ID FROM ACCOUNT', ps, {}, 'tsql') is ps
