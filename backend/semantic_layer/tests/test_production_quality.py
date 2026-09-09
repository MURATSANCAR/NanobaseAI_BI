import json
from pathlib import Path
import pytest
from semantic_bridge.result_files import ResultFiles


def test_full_snapshot_is_not_preview_and_partial_failure_is_removed():
    store = ResultFiles()
    columns = [{'name': 'n', 'type': 'int'}]
    out = store.write(iter([(columns, [{'n': i} for i in range(1200)])]), 50)
    assert len(out['records']) == 50
    assert out['totalRows'] == 1200 and not out['truncated']
    assert len(store.read(out['_result_file'])) == 1200
    store.remove(out['_result_file'])
    store.max_rows = 5
    with pytest.raises(ValueError):
        store.write(iter([(columns, [{'n': i} for i in range(6)])]))
    assert not list(Path(store.directory.name).iterdir())


def test_monthly_frame_and_calendar_gap(catalog, profiles, logo_db):
    from semantic_layer.runtime.resolver import SemanticResolver
    from semantic_layer.runtime.compiler import DeterministicCompiler, default_filters_provider
    from semantic_layer.runtime.audit import unmet_obligations
    from semantic_layer.tests.conftest import TENANT, DS
    resolver = SemanticResolver(catalog, TENANT, DS, profiles)
    q = resolver.resolve('2026 yılında her ay için kanal net ciro göre sırala ve her kanal önceki aya göre yüzde değişimini göster.')
    assert q.analytics and not q.clarification, q.to_dict()
    compiler = DeterministicCompiler(profiles, {}, dialect='sqlite', default_filters=default_filters_provider(catalog, TENANT, DS))
    result = compiler.compile(q, catalog)
    assert result is not None, q.to_dict()
    assert not unmet_obligations(q, result.sql)
    assert unmet_obligations(q, result.sql.replace('DENSE_RANK()', 'ROW_NUMBER()'))
    rows = logo_db.execute(result.sql).fetchall()
    assert rows
    assert any(row[-1] is None for row in rows)


from semantic_layer.tests.test_runtime import catalog


def test_snapshot_identity_changes_with_mapping_not_just_count(catalog):
    from semantic_layer.tests.conftest import TENANT, DS
    index = catalog.certified_index(TENANT, DS)
    version, digest = catalog.publish_runtime_snapshot(TENANT, DS, index)
    assert catalog.publish_runtime_snapshot(TENANT, DS, index) == (version, digest)
    from copy import deepcopy
    changed = deepcopy(index)
    pair = next(p for pairs in changed.values() for p in pairs if p[1])
    pair[1][0].extra['reviewed_definition'] = 'changed'
    v2, d2 = catalog.publish_runtime_snapshot(TENANT, DS, changed)
    assert v2 > version and d2 != digest


def test_large_result_not_background_refreshed(catalog, profiles, settings, logo_db):
    from semantic_bridge.app import Runtime
    from semantic_layer.profiler.connectors import SQLiteConnector
    rt = Runtime(settings, store=catalog, connector=SQLiteConnector(conn=logo_db))
    rt._touch_hot('large', 'SELECT 1', 500)
    rt._remember('large', {'records': [{'n': i} for i in range(201)]}, 30)
    assert 'large' not in rt._hot


def test_complete_result_http_and_shared_snapshot_lifetime(catalog, profiles, settings, logo_db):
    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.profiler.connectors import SQLiteConnector
    from fastapi.testclient import TestClient
    rt = Runtime(settings, store=catalog, connector=SQLiteConnector(conn=logo_db))
    sql = 'SELECT LOGICALREF AS id FROM LG_411_01_INVOICE'
    first = rt.run_complete(sql)
    rt.remember_result(first, question='q', sql=sql)
    second = rt.run_complete(sql)
    rt.remember_result(second, question='q', sql=sql)
    assert second['cached'] and second['computedAt'] == first['computedAt']
    rt._discard_result(first['id'])
    client = TestClient(create_app(rt))
    response = client.get('/api/v1/result/' + second['id'])
    assert response.status_code == 200
    assert len(response.json()['records']) == second['totalRows']
    assert response.json()['computedAt'] == second['computedAt']
    rt._discard_result(second['id'])
    assert not Path(second['_result_file']).exists()


def test_disk_pressure_expires_old_snapshot_before_new_execution(catalog, profiles, settings, logo_db):
    from semantic_bridge.app import Runtime
    from semantic_layer.profiler.connectors import SQLiteConnector
    rt = Runtime(settings, store=catalog, connector=SQLiteConnector(conn=logo_db))
    sql = 'SELECT LOGICALREF AS id FROM LG_411_01_INVOICE'
    first = rt.run_complete(sql)
    rt.remember_result(first, question='q', sql=sql)
    size = Path(first['_result_file']).stat().st_size
    rt.result_files.max_bytes = size * 2
    rt.result_files.disk_budget = size * 2
    second = rt.run_complete(sql + ' ORDER BY LOGICALREF DESC')
    rt.remember_result(second, question='q', sql=sql)
    assert rt.stored_result(first['id']) is None
    assert len(rt.stored_result(second['id'])['records']) == second['totalRows']


def test_missing_result_file_returns_gone_not_server_error(catalog, profiles, settings, logo_db):
    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.profiler.connectors import SQLiteConnector
    from fastapi.testclient import TestClient
    rt = Runtime(settings, store=catalog, connector=SQLiteConnector(conn=logo_db))
    sql = 'SELECT LOGICALREF AS id FROM LG_411_01_INVOICE'
    result = rt.run_complete(sql)
    rt.remember_result(result, question='q', sql=sql)
    Path(result['_result_file']).unlink()
    assert TestClient(create_app(rt)).get('/api/v1/result/' + result['id']).status_code == 410


def test_cached_and_original_timestamps_use_single_clock_sample(catalog, profiles, settings, logo_db, monkeypatch):
    import itertools
    import semantic_bridge.app as module
    from semantic_layer.profiler.connectors import SQLiteConnector
    rt = module.Runtime(settings, store=catalog, connector=SQLiteConnector(conn=logo_db))
    clock = itertools.count(1000000, 0.01)
    with monkeypatch.context() as patch:
        patch.setattr(module.time, 'time', lambda: next(clock))
        sql = 'SELECT LOGICALREF AS id FROM LG_411_01_INVOICE'
        for execute in (lambda: rt.run_sql(sql, 50), lambda: rt.run_complete(sql)):
            first = execute()
            second = execute()
            assert second['cached']
            assert first['computedAt'] == second['computedAt']


def test_http_snapshot_chunk_boundaries_preserve_unicode_and_all_rows(catalog, profiles, settings, logo_db):
    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.profiler.connectors import SQLiteConnector
    from fastapi.testclient import TestClient
    rt = Runtime(settings, store=catalog, connector=SQLiteConnector(conn=logo_db))
    records = [{'id': i, 'name': 'İstanbul\nÇığlık', 'missing': None} for i in range(10000)]
    result = rt._served(rt.result_files.write(iter([([{'name': 'id'}, {'name': 'name'}, {'name': 'missing'}], records)])), 1)
    rt.remember_result(result, question='q', sql='SELECT 1')
    response = TestClient(create_app(rt)).get('/api/v1/result/' + result['id'])
    assert response.status_code == 200
    assert response.json()['records'] == records
