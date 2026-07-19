"""VPD fail-closed behavior (no live DB)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.oracle.vpd import set_tenant_context


def test_vpd_required_without_tenant():
    conn = MagicMock()
    with pytest.raises(GatewayError):
        set_tenant_context(conn, tenant_id="", required=True)


def test_vpd_required_when_context_fails():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.execute.side_effect = RuntimeError("no package")
    with pytest.raises(GatewayError) as ei:
        set_tenant_context(conn, tenant_id="tenant-a", required=True)
    assert ei.value.code == "TENANT_POLICY_MISSING"
