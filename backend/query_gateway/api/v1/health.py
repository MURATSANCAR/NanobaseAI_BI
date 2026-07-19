from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from query_gateway.config.settings import get_settings
from query_gateway.infrastructure.database.datasources import load_datasources
from query_gateway.infrastructure.database.pool_registry import get_pool_registry
from query_gateway.infrastructure.policy.engine import load_policy_bundle

router = APIRouter(tags=["health"])


@router.get("/health/live")
def health_live() -> dict[str, Any]:
    return {"status": "UP", "service": "query_gateway"}


@router.get("/health/ready")
def health_ready() -> dict[str, Any]:
    settings = get_settings()
    checks: dict[str, str] = {}
    try:
        load_policy_bundle(settings)
        checks["policy"] = "UP"
    except Exception:
        checks["policy"] = "DOWN"

    checks["secretsRoot"] = "UP" if settings.secrets_root.exists() else "DOWN"

    redis_status = "DOWN"
    try:
        import redis

        redis.Redis.from_url(settings.redis_url, socket_timeout=1).ping()
        redis_status = "UP"
    except Exception:
        redis_status = "DOWN" if settings.replay_required and settings.auth_required else "DEGRADED"
    checks["redis"] = redis_status

    try:
        ds = load_datasources(settings)
        checks["datasources"] = "UP" if ds else "DEGRADED"
    except Exception:
        checks["datasources"] = "DOWN"

    critical_down = checks["policy"] == "DOWN" or (
        settings.auth_required and settings.replay_required and checks["redis"] == "DOWN"
    )
    status = "DOWN" if critical_down else "UP"
    return {
        "status": status,
        "checks": checks,
        "activePools": get_pool_registry().active_pools(),
        "policyVersion": settings.policy_version,
    }
