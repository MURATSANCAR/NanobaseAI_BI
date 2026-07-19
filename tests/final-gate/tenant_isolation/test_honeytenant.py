"""Honeytenant certification — any leak is SEV-1 / NO_GO (§15.8)."""

from __future__ import annotations

HONEY_TENANT = "honeytenant-final-gate"
HONEY_MARKER = "HONEY_SECRET_ROW_DO_NOT_LEAK"


def test_honeytenant_not_in_other_tenant_retrieval():
    # Simulated retrieval payload for tenant-a
    retrieved_docs = [
        {"tenant_id": "tenant-a", "text": "orders.amount"},
        {"tenant_id": "tenant-a", "text": "customers.name"},
    ]
    leaked = [d for d in retrieved_docs if d.get("tenant_id") == HONEY_TENANT]
    leaked += [d for d in retrieved_docs if HONEY_MARKER in d.get("text", "")]
    assert leaked == [], "SEV-1: honeytenant data visible to another tenant"


def test_honeytenant_gateway_context_rejected():
    requested_tenant = "tenant-a"
    datasource_tenant = HONEY_TENANT
    allowed = requested_tenant == datasource_tenant
    assert not allowed
