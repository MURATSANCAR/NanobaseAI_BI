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


def test_model_sql_must_keep_default_row_scope(setup):
    from semantic_layer.runtime.audit import unmet_obligations
    from semantic_layer.runtime.compiler import ExistingCompiler
    _, store, _ = setup
    sq = SemanticResolver(store, 'acceptance', 'acceptance', store.list_profiles('acceptance')).resolve('Ocak 2026 satılan adet')
    base = "SELECT SUM(s.AMOUNT) FROM LG_411_01_STLINE s WHERE s.DATE_ >= '2026-01-01' AND s.DATE_ < '2026-02-01' AND s.TRCODE IN (7,8)"
    missing = unmet_obligations(sq, base)
    assert any('CANCELLED' in reason for reason in missing)
    assert any('LINETYPE' in reason for reason in missing)
    assert not unmet_obligations(sq, base + ' AND s.CANCELLED=0 AND s.LINETYPE=0')
    # A condition in a comment or unused CTE is not proof of filtering output rows.
    assert unmet_obligations(sq, base + ' /* CANCELLED=0 AND LINETYPE=0 */')


def test_unsolicited_outer_limit_does_not_truncate_report(setup):
    from semantic_layer.runtime.compiler import ExistingCompiler
    from semantic_layer.models import SemanticQuery
    from semantic_layer.candidates.llm_client import FakeLlm
    _, store, _ = setup
    compiler = ExistingCompiler(FakeLlm(), store.list_profiles('acceptance'), {}, dialect='sqlite')
    q = SemanticQuery(question='satış raporu', tenant_id='acceptance', datasource_id='acceptance')
    import sqlite3
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE report (value INT)')
    conn.executemany('INSERT INTO report VALUES (?)', [(i,) for i in range(60)])
    sql = 'SELECT value FROM report ORDER BY value LIMIT 50'
    assert len(conn.execute(compiler._requested_row_limit(sql, q)).fetchall()) == 60
    q.limit = 50
    assert len(conn.execute(compiler._requested_row_limit(sql, q)).fetchall()) == 50
    q.limit = None
    nested = 'SELECT value FROM (SELECT value FROM report ORDER BY value DESC LIMIT 1) AS latest LIMIT 50'
    assert conn.execute(compiler._requested_row_limit(nested, q)).fetchall() == [(59,)]
    conn.close()


@pytest.mark.parametrize("global_table,multi_firm", [(False,False),(True,False),(True,True)])
@pytest.mark.parametrize("missing_header", [False, True])
def test_effective_reference_uses_line_override_then_header(setup, missing_header, global_table, multi_firm):
    from semantic_layer.models import ColumnProfile, Mapping, SemanticType
    from semantic_layer.runtime.audit import unmet_obligations
    conn, store, facts = setup
    conn.execute('ALTER TABLE LG_411_01_STLINE ADD COLUMN PAYDEFREF INTEGER DEFAULT 0')
    conn.execute('UPDATE LG_411_01_STLINE SET PAYDEFREF=6 WHERE LOGICALREF % 3=0')
    if missing_header:
        conn.execute('UPDATE LG_411_01_INVOICE SET PAYDEFREF=0')
    conn.commit()
    profiles = store.list_profiles('acceptance')
    payment_pattern='LG_{n0}_PAYPLANS'
    if global_table:
        conn.execute('ALTER TABLE LG_411_PAYPLANS RENAME TO LG_PAYPLANS')
        pay=next(p for p in profiles if p.entity=='PAYPLANS')
        pay.table_name=pay.table_pattern=payment_pattern='LG_PAYPLANS'
        pay.context={}
        store.upsert_profile(pay)
        store.prune_profiles('acceptance',[p.table_pattern for p in profiles])
    st = next(p for p in profiles if p.entity=='STLINE')
    st.columns.append(ColumnProfile('PAYDEFREF','INTEGER'))
    st.relationships.append({'column':'PAYDEFREF','ref_entity':'PAYPLANS','ref_column':'LOGICALREF'})
    store.upsert_profile(st)
    mapping=Mapping('', 'PAYPLANS', payment_pattern, column='DEFINITION_', operator='COLUMN', extra={'join_kind':'LEFT',
        'reference_resolution': {'STLINE': {'via':'INVOICE','via_column':'INVOICEREF','via_key':'LOGICALREF','primary_column':'PAYDEFREF',
            'fallback_column':'PAYDEFREF','target_column':'LOGICALREF','empty_value':0}}})
    concept,_=store.upsert_concept('acceptance','acceptance','ödeme planı',SemanticType.COLUMN,status='CERTIFIED',mapping=mapping)
    store.replace_mappings(concept.id,[mapping])
    if multi_firm:
        from copy import deepcopy
        for original in store.list_profiles('acceptance'):
            if not original.context:continue
            copy=deepcopy(original);copy.table_name=original.table_name.replace('_411_','_211_');copy.context={**original.context,'n0':'211'}
            conn.execute(f'CREATE TABLE {copy.table_name} AS SELECT * FROM {original.table_name}')
            if copy.entity=='STLINE':
                original.time_window=('2026-01-01','2026-01-15');store.upsert_profile(original)
                copy.time_window=('2025-12-01','2026-01-31')
                conn.execute(f"UPDATE {copy.table_name} SET AMOUNT=AMOUNT*2, DATE_='2026-01-20' WHERE DATE_='2026-01-15'")
            store.upsert_profile(copy)
    settings=SemanticSettings(tenant_id='acceptance',datasource_id='acceptance',dialect='sqlite',context={} if multi_firm else {'n0':'411','n1':'01'},max_rows=10000,recall_enabled=False)
    runtime=Runtime(settings,store=store,connector=SQLiteConnector(conn=conn),llm=NoModel())
    question='Ocak 2026 ödeme planı bazında satılan adet'
    answer=runtime.ask(question,thread_id=None,sample_size=10000)
    assert answer['type']=='TEXT_TO_SQL',answer
    # Independent arithmetic: every third line explicitly overrides the header.
    from collections import defaultdict
    truth=defaultdict(float)
    for idx,row in enumerate(facts,1):
        if row['year']==2026 and row['month']==1 and row['code'] in (7,8) and not row['cancelled'] and not row['line_type']:
            truth['payment-6' if idx%3==0 else None if missing_header else row['payment']]+=row['quantity']*(3 if multi_firm else 1)
    assert canonical([list(r.values()) for r in answer['records']])==canonical([[k,v] for k,v in truth.items()])
    sq=runtime.resolver.resolve(question)
    assert not unmet_obligations(sq,answer['sql'])
    wrong=answer['sql'].replace('COALESCE(NULLIF(STLINE."PAYDEFREF", 0), INVOICE."PAYDEFREF")','INVOICE."PAYDEFREF"')
    assert unmet_obligations(sq,wrong)

    assert unmet_obligations(sq,answer['sql'].replace('LEFT JOIN', 'JOIN'))


@pytest.mark.parametrize('separator,expected_metrics', [(' ',1),(', ',2),(' ve ',2)])
def test_ambiguous_value_modifies_adjacent_explicit_measure(setup,separator,expected_metrics):
    from semantic_layer.models import Mapping,SemanticType
    conn,store,facts=setup
    store.upsert_concept('acceptance','acceptance','perakende',SemanticType.METRIC,status='CERTIFIED',
        mapping=Mapping('','INVOICE','LG_{n0}_{n1}_INVOICE',formula='COUNT(INVOICE.LOGICALREF)'))
    q=SemanticResolver(store,'acceptance','acceptance',store.list_profiles('acceptance')).resolve(
        'Ocak 2026 perakende'+separator+'satılan adet nedir?')
    assert len(q.metrics)==expected_metrics
    if expected_metrics==1:
        assert any(s.mapping.entity=='STLINE' and s.mapping.values==['7'] for s in q.filters)
