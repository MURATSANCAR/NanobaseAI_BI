"""L1/L2 compiled plan cache — never bypasses Query Gateway."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from threading import RLock
from typing import Any


@dataclass
class CachedPlan:
    scenario_id: str
    dialect: str
    sql_template: str
    ast_fingerprint: str
    schema_version: str
    semantic_version: str
    policy_version: str
    bind_params: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenarioId": self.scenario_id,
            "dialect": self.dialect,
            "sqlTemplate": self.sql_template,
            "astFingerprint": self.ast_fingerprint,
            "schemaVersion": self.schema_version,
            "semanticVersion": self.semantic_version,
            "policyVersion": self.policy_version,
            "bindParams": list(self.bind_params),
        }


def cache_key(
    *,
    tenant_id: str,
    datasource_id: str,
    scenario_id: str,
    dialect: str,
    schema_version: str,
    semantic_version: str,
    policy_version: str,
) -> str:
    return "|".join(
        [
            tenant_id,
            datasource_id,
            scenario_id,
            dialect,
            schema_version,
            semantic_version,
            policy_version,
        ]
    )


class CompiledPlanCache:
    def __init__(self) -> None:
        self._l1: dict[str, CachedPlan] = {}
        self._lock = RLock()
        self._redis = None
        url = os.environ.get("REDIS_URL")
        if url:
            try:
                import redis

                self._redis = redis.Redis.from_url(url, decode_responses=True)
            except Exception:
                self._redis = None

    def get(self, key: str) -> CachedPlan | None:
        with self._lock:
            hit = self._l1.get(key)
            if hit:
                return hit
        if self._redis is not None:
            try:
                raw = self._redis.get(f"scn:plan:{key}")
                if raw:
                    d = json.loads(raw)
                    plan = CachedPlan(**{self._from_camel(k): v for k, v in d.items()})
                    with self._lock:
                        self._l1[key] = plan
                    return plan
            except Exception:
                return None
        return None

    @staticmethod
    def _from_camel(k: str) -> str:
        # simple map for known fields
        mapping = {
            "scenarioId": "scenario_id",
            "sqlTemplate": "sql_template",
            "astFingerprint": "ast_fingerprint",
            "schemaVersion": "schema_version",
            "semanticVersion": "semantic_version",
            "policyVersion": "policy_version",
            "bindParams": "bind_params",
            "dialect": "dialect",
        }
        return mapping.get(k, k)

    def put(self, key: str, plan: CachedPlan, ttl_seconds: int = 3600) -> None:
        with self._lock:
            self._l1[key] = plan
        if self._redis is not None:
            try:
                self._redis.setex(f"scn:plan:{key}", ttl_seconds, json.dumps(plan.to_dict()))
            except Exception:
                pass

    def invalidate_prefix(self, *, tenant_id: str, datasource_id: str) -> int:
        prefix = f"{tenant_id}|{datasource_id}|"
        removed = 0
        with self._lock:
            keys = [k for k in self._l1 if k.startswith(prefix)]
            for k in keys:
                del self._l1[k]
                removed += 1
        return removed


_CACHE: CompiledPlanCache | None = None


def get_plan_cache() -> CompiledPlanCache:
    global _CACHE
    if _CACHE is None:
        _CACHE = CompiledPlanCache()
    return _CACHE
