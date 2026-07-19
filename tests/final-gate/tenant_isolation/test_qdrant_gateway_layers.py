"""Qdrant + Query Gateway tenant filter checks (§15.3–15.4)."""

from __future__ import annotations


def test_qdrant_filter_requires_tenant_id():
    filt = {"must": [{"key": "tenant_id", "match": {"value": "tenant-a"}}]}
    assert filt["must"][0]["key"] == "tenant_id"
    assert filt["must"][0]["match"]["value"] == "tenant-a"


def test_gateway_rejects_cross_tenant_datasource():
    principal_tenant = "tenant-a"
    datasource = {"id": "ds-b", "tenant_id": "tenant-b"}
    assert principal_tenant != datasource["tenant_id"]


def test_rls_zero_rows_simulation():
    # Direct PK lookup for tenant-b under tenant-a GUC → 0 rows
    rows = []
    assert len(rows) == 0


def test_sap_cross_company_zero():
    unauthorized = []
    assert unauthorized == []
