"""Budget board-pack shares — thin wrapper over unified bi shares store."""

from __future__ import annotations

from typing import Any

from nanobase_api import shares as shares_mod


def create_share(
    *,
    resource_type: str,
    resource_id: str,
    ttl_hours: float,
    password: str | None = None,
    tenant_id: str,
) -> dict[str, Any]:
    # Preserve previous default of ~24h when callers pass 0/None incorrectly;
    # budget pack UI sends explicit ttl (typically 72).
    hours = float(ttl_hours) if ttl_hours is not None else 24.0
    if hours <= 0:
        hours = 24.0
    return shares_mod.create_share(
        resource_type=str(resource_type or "budget_pack"),
        resource_id=str(resource_id or ""),
        ttl_hours=hours,
        password=password,
        tenant_id=tenant_id,
    )


def get_share(token: str) -> dict[str, Any] | None:
    return shares_mod.get_share(token)
