"""Regression coverage for coordinated groupings and the independent acceptance oracle."""
import pytest
from enduser_10000 import corpus, fixture, expected, canonical, NoModel, SemanticSettings
from semantic_bridge.app import Runtime
from semantic_layer.profiler.connectors import SQLiteConnector
from semantic_layer.runtime.resolver import SemanticResolver


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv('SEMANTIC_REFRESH_SEC', '0')
    monkeypatch.setenv('SEMANTIC_TABLE_SELECTOR', 'off')
    monkeypatch.delenv('QDRANT_URL', raising=False)
    conn, store, facts = fixture()
    yield conn, store, facts
    conn.close()


@pytest.mark.parametrize('terms', ['müşteri, ürün', 'müşteri ve ürün', 'müşteri ile ürün'])
def test_coordinated_columns_share_grouping_marker(setup, terms):
    _, store, _ = setup
    sq = SemanticResolver(store, 'acceptance', 'acceptance', store.list_profiles('acceptance')).resolve(
        f'Ocak 2026 {terms} bazında satış tutarı')
    assert {s.mapping.entity for s in sq.group_by} == {'CLCARD', 'ITEMS'}


@pytest.mark.parametrize('separator', ['. ', '; ', ' filtresini kullanarak '])
def test_grouping_does_not_cross_sentence_or_filter_clause(setup, separator):
    _, store, _ = setup
    sq = SemanticResolver(store, 'acceptance', 'acceptance', store.list_profiles('acceptance')).resolve(
        'müşteri' + separator + 'ürün bazında Ocak 2026 satış tutarı')
    assert {s.mapping.entity for s in sq.group_by} == {'ITEMS'}


def test_eight_table_query_executes_without_fanout(setup):
    conn, store, facts = setup
    settings = SemanticSettings(tenant_id='acceptance', datasource_id='acceptance', dialect='sqlite',
                                context={'n0':'411','n1':'01'}, max_rows=10000, recall_enabled=False)
    model = NoModel()
    runtime = Runtime(settings, store=store, connector=SQLiteConnector(conn=conn), llm=model)
    case = next(c for c in corpus() if c['expected_table_count'] == 8 and c['metric'] == 'net satış tutarı' and not c['kind'])
    answer = runtime.ask(case['prompt'], thread_id=None, sample_size=10000)
    assert answer['type'] == 'TEXT_TO_SQL'
    assert canonical([list(row.values()) for row in answer['records']]) == canonical(expected(case, facts))
    import sqlglot
    from sqlglot import exp
    assert len(list(sqlglot.parse_one(answer['sql']).find_all(exp.Join))) == 7
    assert model.calls == 0


def test_corpus_balanced_and_oracle_rejects_wrong_values():
    cases = corpus()
    assert len(cases) == len({c['prompt'] for c in cases}) == 10000
    assert {c['year'] for c in cases} == set(range(2022, 2027))
    assert sum(c['expected_table_count'] == 8 for c in cases) == 1000
    assert sum(c['expected_table_count'] == 7 for c in cases) == 1000
    assert canonical([['customer-1', 10]]) != canonical([['customer-1', 1000]])
    assert canonical([['customer-1', 10]]) != canonical([['customer-2', 10]])


def test_indirect_path_rejects_missing_unique_key_and_ambiguity(setup):
    from semantic_layer.runtime.compiler import DeterministicCompiler
    from copy import deepcopy
    _, store, _ = setup
    profiles = deepcopy(store.list_profiles('acceptance'))
    compiler = DeterministicCompiler(profiles, {'n0':'411','n1':'01'}, 'sqlite')
    assert len(compiler._join_chain('STLINE', 'CLCARD')) == 2
    target = compiler.by_entity['CLCARD']
    target.primary_key = []
    for column in target.columns:
        column.is_primary_key = False
    assert compiler._join_chain('STLINE', 'CLCARD') is None
    target.primary_key = ['LOGICALREF']
    # An equally short second relationship cannot be selected arbitrarily.
    compiler.conventions.ref_columns['ITEMS']['CLIENTREF'] = ('CLCARD', 'LOGICALREF')
    assert compiler._join_chain('STLINE', 'CLCARD') is None
    # Header -> line -> unit would multiply a header measure and is not a safe path.
    assert compiler._join_chain('INVOICE', 'UNITSETL') is None
