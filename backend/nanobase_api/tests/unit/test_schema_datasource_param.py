from __future__ import annotations

from nanobase_api.infrastructure.active_source import resolve_schema_datasource_id


def test_schema_datasource_id_honors_query_param():
    assert (
        resolve_schema_datasource_id(
            query_datasource_id="ds_a",
            memory_id="ds_fallback",
        )
        == "ds_a"
    )


def test_schema_datasource_id_falls_back_to_active():
    assert (
        resolve_schema_datasource_id(
            query_datasource_id=None,
            body_datasource_id=None,
            memory_id="ds_b",
        )
        == "ds_b"
    )


def test_schema_datasource_id_body_on_refresh():
    assert (
        resolve_schema_datasource_id(
            query_datasource_id=None,
            body_datasource_id="ds_b",
            memory_id="ds_fallback",
        )
        == "ds_b"
    )
