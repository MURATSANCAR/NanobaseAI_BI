"""SuperSonic behind the same compiler interface — for a measured A/B, not as a dependency.

The engine keeps its own truth: the SemanticQuery produced by our resolver (certified metric,
dimension filters, time range, group-by) is translated into SuperSonic's *struct query* and SuperSonic
is asked for SQL. Nothing about SuperSonic reaches the production answer path unless the operator
switches the compiler explicitly (SEMANTIC_COMPILER=supersonic) or the A/B harness runs it.

Deployment differences are configuration, not code: base URL, auth and the three endpoint paths are
settings, and the entity → dataSet mapping comes from the catalog/ops config. When the mapping or the
service is missing the adapter returns None and the router simply falls through to the next compiler.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from semantic_layer.models import CompiledQuery, SemanticQuery, SemanticType
from semantic_layer.store.catalog_store import CatalogStore

log = logging.getLogger(__name__)


@dataclass
class SuperSonicSettings:
    base_url: str = ""
    token: str = ""
    user: str = ""
    password: str = ""
    timeout: float = 60.0
    struct_path: str = "/api/semantic/query/struct"
    sql_path: str = "/api/semantic/query/sql"
    login_path: str = "/api/auth/user/login"
    model_path: str = "/api/semantic/dataSet"
    datasets: dict[str, int] = field(default_factory=dict)   # entity → dataSetId
    date_field: dict[str, str] = field(default_factory=dict)  # entity → time dimension bizName

    @classmethod
    def from_env(cls) -> "SuperSonicSettings":
        raw = os.environ.get("SUPERSONIC_DATASETS", "")
        datasets: dict[str, int] = {}
        for item in raw.split(","):
            if "=" in item:
                k, v = item.split("=", 1)
                try:
                    datasets[k.strip().upper()] = int(v.strip())
                except ValueError:
                    continue
        dates: dict[str, str] = {}
        for item in os.environ.get("SUPERSONIC_DATE_FIELDS", "").split(","):
            if "=" in item:
                k, v = item.split("=", 1)
                dates[k.strip().upper()] = v.strip()
        return cls(
            base_url=os.environ.get("SUPERSONIC_BASE", "").rstrip("/"),
            token=os.environ.get("SUPERSONIC_TOKEN", ""),
            user=os.environ.get("SUPERSONIC_USER", ""),
            password=os.environ.get("SUPERSONIC_PASSWORD", ""),
            timeout=float(os.environ.get("SUPERSONIC_TIMEOUT_SEC", "60")),
            struct_path=os.environ.get("SUPERSONIC_STRUCT_PATH", "/api/semantic/query/struct"),
            sql_path=os.environ.get("SUPERSONIC_SQL_PATH", "/api/semantic/query/sql"),
            login_path=os.environ.get("SUPERSONIC_LOGIN_PATH", "/api/auth/user/login"),
            model_path=os.environ.get("SUPERSONIC_MODEL_PATH", "/api/semantic/dataSet"),
            datasets=datasets,
            date_field=dates,
        )

    @property
    def configured(self) -> bool:
        return bool(self.base_url)


class SuperSonicClient:
    """Thin HTTP client. `transport` is injectable so the adapter can be tested without the service."""

    def __init__(self, settings: SuperSonicSettings, *, transport: Any = None):
        self.s = settings
        self._transport = transport
        self._token = settings.token

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.s.base_url, timeout=self.s.timeout, transport=self._transport)

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
            h["token"] = self._token
        return h

    def login(self) -> Optional[str]:
        if self._token or not (self.s.user and self.s.password):
            return self._token
        with self._client() as c:
            r = c.post(self.s.login_path, json={"name": self.s.user, "password": self.s.password}, headers={"Content-Type": "application/json"})
        r.raise_for_status()
        data = r.json()
        self._token = str(((data.get("data") or {}) if isinstance(data, dict) else {}).get("token") or data.get("token") or "")
        return self._token or None

    def health(self) -> dict[str, Any]:
        try:
            with self._client() as c:
                r = c.get("/health", headers=self._headers())
            return {"ok": r.status_code < 400, "status": r.status_code}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)[:200]}

    def query_struct(self, struct: dict[str, Any], *, sql_only: bool = True) -> dict[str, Any]:
        payload = dict(struct)
        payload["sqlOnly"] = sql_only
        self.login()
        with self._client() as c:
            r = c.post(self.s.struct_path, json=payload, headers=self._headers())
        r.raise_for_status()
        return r.json()

    def query_sql(self, sql: str, dataset_id: Optional[int] = None) -> dict[str, Any]:
        self.login()
        body: dict[str, Any] = {"sql": sql}
        if dataset_id is not None:
            body["dataSetId"] = dataset_id
        with self._client() as c:
            r = c.post(self.s.sql_path, json=body, headers=self._headers())
        r.raise_for_status()
        return r.json()

    def upsert_dataset(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.login()
        with self._client() as c:
            r = c.post(self.s.model_path, json=payload, headers=self._headers())
        r.raise_for_status()
        return r.json()


def extract_sql(response: dict[str, Any]) -> Optional[str]:
    """SuperSonic returns the compiled statement under a few different keys across releases."""
    data = response.get("data") if isinstance(response, dict) else None
    for holder in (data, response):
        if not isinstance(holder, dict):
            continue
        for key in ("querySQL", "sql", "queryStatement", "correctorSql", "s2SQL"):
            value = holder.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().rstrip(";")
    return None


class SuperSonicCompilerAdapter:
    """SemanticQuery → SuperSonic struct query → SQL."""

    name = "supersonic"

    def __init__(self, client: SuperSonicClient, settings: Optional[SuperSonicSettings] = None):
        self.client = client
        self.s = settings or client.s

    # ------------------------------------------------------------------ translation
    def dataset_for(self, entity: str) -> Optional[int]:
        return self.s.datasets.get(entity.upper())

    def build_struct(self, q: SemanticQuery) -> tuple[Optional[dict[str, Any]], str]:
        metrics = [s for s in q.metrics if s.mapping]
        if not metrics:
            return None, "no certified metric to map"
        entity = metrics[0].mapping.entity
        dataset = self.dataset_for(entity)
        if dataset is None:
            return None, f"no SuperSonic dataSet configured for {entity}"
        struct: dict[str, Any] = {
            "dataSetId": dataset,
            "metrics": [str(s.explain.get("normalized") or s.term) for s in metrics],
            "dimensions": [str(s.explain.get("normalized") or s.term) for s in q.group_by if s.mapping],
            "dimensionFilters": [],
            "limit": q.limit or 200,
        }
        for s in q.filters:
            m = s.mapping
            if not m or not m.column:
                continue
            struct["dimensionFilters"].append({
                "bizName": str(s.explain.get("normalized") or s.term),
                "name": m.column,
                "operator": (m.operator or "IN").upper(),
                "value": list(m.values),
                "elementID": None,
            })
        for t in q.temporal:
            if t.start and t.end:
                struct["dateInfo"] = {
                    "dateMode": "BETWEEN",
                    "startDate": t.start.isoformat(),
                    "endDate": t.end.isoformat(),
                    "period": (t.grain or "DAY").upper(),
                }
                field_name = self.s.date_field.get(entity.upper())
                if field_name:
                    struct["dateInfo"]["dateField"] = field_name
                break
        if q.grain and "dateInfo" in struct:
            struct["dateInfo"]["period"] = q.grain.upper()
            struct["groupByTime"] = q.grain.upper()
        return struct, "ok"

    # ------------------------------------------------------------------ compiler interface
    def compile(self, query: SemanticQuery, catalog: CatalogStore) -> Optional[CompiledQuery]:
        struct, reason = self.build_struct(query)
        if struct is None:
            log.debug("supersonic adapter skipped: %s", reason)
            return None
        t0 = time.perf_counter()
        try:
            response = self.client.query_struct(struct, sql_only=True)
        except Exception as e:  # noqa: BLE001
            return CompiledQuery(sql="", compiler=self.name, catalog_version=query.catalog_version, explain=[f"SuperSonic hata: {str(e)[:200]}"], llm_ms=int((time.perf_counter() - t0) * 1000), certified=False)
        ms = int((time.perf_counter() - t0) * 1000)
        sql = extract_sql(response)
        if not sql:
            return CompiledQuery(sql="", compiler=self.name, catalog_version=query.catalog_version, explain=[f"SuperSonic SQL döndürmedi: {json.dumps(response, ensure_ascii=False)[:200]}"], llm_ms=ms, certified=False)
        certified = not query.unresolved and all(s.status in ("CERTIFIED", "EXPLICIT", "PROFILE", "COMPOSED") for s in query.slots)
        return CompiledQuery(sql=sql, compiler=self.name, catalog_version=query.catalog_version, explain=[f"SuperSonic struct sorgusu → SQL (dataSet {struct['dataSetId']})"], llm_ms=ms, certified=certified)


# ---------------------------------------------------------------------- catalog → SuperSonic model

def export_semantic_model(store: CatalogStore, tenant_id: str, datasource_id: str, profiles: list[Any], *, context: Optional[dict[str, str]] = None) -> list[dict[str, Any]]:
    """Our CERTIFIED catalog as SuperSonic dataSet/metric/dimension payloads, so an A/B compares the
    two compilers over the *same* knowledge instead of two different knowledge bases."""
    from semantic_layer.naming import physical_name

    by_entity: dict[str, dict[str, Any]] = {}
    for p in profiles:
        by_entity[p.entity] = {
            "name": p.entity,
            "bizName": p.entity.lower(),
            "tableName": physical_name(p.table_pattern, {**p.context, **(context or {})}),
            "schema": p.schema_name,
            "primaryKey": p.primary_key,
            "metrics": [],
            "dimensions": [],
            "defaultFilters": [],
            "identifiers": [{"name": r["column"], "type": "foreign", "reference": f'{r["ref_entity"]}.{r["ref_column"]}'} for r in p.relationships],
        }
    for c in store.find_concepts(tenant_id, datasource_id, status="CERTIFIED", limit=100000):
        for m in store.list_mappings(c.id):
            target = by_entity.get(m.entity)
            if target is None:
                continue
            if c.semantic_type == SemanticType.METRIC and m.formula:
                target["metrics"].append({"name": c.term, "bizName": c.normalized_term, "expr": m.formula, "aliases": list(c.synonyms), "scope": list((m.extra or {}).get("conditions") or [])})
            elif c.semantic_type == SemanticType.COLUMN and m.column:
                target["dimensions"].append({"name": c.term, "bizName": c.normalized_term, "expr": m.column, "aliases": list(c.synonyms), "values": list(c.explain.get("documented_values") or [])})
            elif c.semantic_type == SemanticType.DIMENSION_VALUE and m.column:
                target["dimensions"].append({"name": f"{c.term} ({m.column})", "bizName": c.normalized_term, "expr": m.column, "valueFilter": {"operator": m.operator, "values": list(m.values)}})
            elif c.semantic_type == SemanticType.DEFAULT_FILTER and m.column:
                target["defaultFilters"].append({"expr": m.column, "operator": m.operator, "values": list(m.values)})
    return [v for v in by_entity.values() if v["metrics"] or v["dimensions"]]


def build_adapter(settings: Optional[SuperSonicSettings] = None, *, transport: Any = None) -> Optional[SuperSonicCompilerAdapter]:
    s = settings or SuperSonicSettings.from_env()
    if not s.configured:
        return None
    return SuperSonicCompilerAdapter(SuperSonicClient(s, transport=transport), s)
