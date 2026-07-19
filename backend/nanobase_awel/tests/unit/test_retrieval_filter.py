from __future__ import annotations

from nanobase_awel.retrieval.authorized import build_qdrant_filter


def test_filter_includes_tenant_and_datasource():
    f = build_qdrant_filter(tenant_id="t1", datasource_id="bi_reporting")
    assert f is not None
    keys = [m["key"] for m in f["must"]]
    assert "datasource_id" in keys
    assert "tenant_id" in keys
    assert "status" not in keys


def test_default_tenant_skips_tenant_key():
    f = build_qdrant_filter(tenant_id="default", datasource_id="bi_reporting")
    keys = [m["key"] for m in f["must"]]
    assert "datasource_id" in keys
    assert "tenant_id" not in keys
    # Neon/Postgres payloads have no status — must not filter by ACTIVE by default
    assert "status" not in keys


def test_explicit_status_included():
    f = build_qdrant_filter(tenant_id="default", datasource_id="ora1", status="ACTIVE")
    keys = [m["key"] for m in f["must"]]
    assert "status" in keys


def test_oracle_database_type_defaults_status_active():
    f = build_qdrant_filter(
        tenant_id="default", datasource_id="ora1", database_type="oracle"
    )
    keys = [m["key"] for m in f["must"]]
    assert "database_type" in keys
    assert "status" in keys
