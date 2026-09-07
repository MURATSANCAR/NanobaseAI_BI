"""Portal API for the Semantic Layer: detected tables/columns, catalog status, user annotations
(/api/v1/bi/semantic-layer/*). Shares the sl_* tables (bi_meta) with the semantic bridge."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from collections import OrderedDict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from nanobase_api.auth.principal import ROLE_ADMIN, ROLE_DATA_ENGINEER, RequestPrincipal, get_current_principal, has_role
from nanobase_api.config import get_settings
from nanobase_api.errors import ApiError

router = APIRouter(prefix="/api/v1/bi/semantic-layer", tags=["semantic-layer"])

# One catalog engine for this process, and a small bounded set of runtimes. The datasource id arrives
# from the client, so it is validated against what the catalog actually holds before anything is
# created — an unbounded cache keyed by a request parameter would exhaust the API's database pool.
_STORE: Any = None
_runtimes: "OrderedDict[str, Any]" = OrderedDict()
_MAX_RUNTIMES = 8


class SemanticSettingsDefault:
    datasource_id = os.environ.get("SEMANTIC_DATASOURCE_ID", "default")


def _settings_for(datasource_id: Optional[str], tenant_id: str):
    from semantic_layer.config import SemanticSettings

    s = SemanticSettings.from_env()
    s.store_dsn = os.environ.get("SEMANTIC_STORE_DSN") or get_settings().meta_dsn
    s.tenant_id = tenant_id or s.tenant_id
    if datasource_id:
        s.datasource_id = datasource_id
    return s


def _store():
    global _STORE
    if _STORE is None:
        from semantic_layer.store.catalog_store import open_store

        _STORE = open_store(os.environ.get("SEMANTIC_STORE_DSN") or get_settings().meta_dsn)
    return _STORE


def _known_datasources() -> set[str]:
    import sqlalchemy as sa

    from semantic_layer.store import schema as S

    with _store().engine.connect() as conn:
        return {r[0] for r in conn.execute(sa.select(S.sl_schema_profile.c.datasource_id).distinct())}


def _runtime(datasource_id: Optional[str], tenant_id: str):
    """One offline Runtime (no LLM, no ERP connection) per datasource, for inventory/annotation/certify."""
    from semantic_bridge.app import Runtime

    s = _settings_for(datasource_id, tenant_id)
    if datasource_id and datasource_id != s.datasource_id:
        s.datasource_id = datasource_id
    if datasource_id and datasource_id not in _known_datasources() | {SemanticSettingsDefault.datasource_id}:
        raise ApiError("NOT_FOUND", f"Bilinmeyen veri kaynağı: {datasource_id}", status_code=404)
    key = f"{s.tenant_id}:{s.datasource_id}"
    rt = _runtimes.get(key)
    if rt is None:
        rt = Runtime(s, store=_store(), connector=None, llm=None)
        _runtimes[key] = rt
        while len(_runtimes) > _MAX_RUNTIMES:
            _runtimes.popitem(last=False)
    else:
        _runtimes.move_to_end(key)
    return rt


def _ds(request: Request, body: Optional[dict[str, Any]] = None) -> Optional[str]:
    """Which catalog this page is about.

    The portal's data-source picker and the semantic catalog are different namespaces: a catalog exists
    only for a source that has been profiled. Asking for one the catalog never heard of used to return
    an empty page, which reads as "nothing was ever discovered" rather than "you are looking at the
    wrong source" — so fall back to a catalog that does exist and let the response name it.
    """
    asked = (body or {}).get("datasource_id") or request.query_params.get("datasource_id") or None
    try:
        known = _known_datasources()
    except Exception:  # noqa: BLE001
        return asked
    if asked and asked in known:
        return asked
    configured = os.environ.get("SEMANTIC_DATASOURCE_ID") or ""
    if configured in known:
        return configured
    return next(iter(sorted(known)), asked)


def _may_govern(principal: RequestPrincipal) -> bool:
    """Catalog-changing actions need a governing role. In dev auth mode the principal carries every role,
    so this is only meaningful with real tokens — the deployment must not run AUTH_MODE=dev in production
    (the deploy script warns), and the check stays here so it bites the moment tokens are on."""
    return has_role(principal, ROLE_ADMIN) or has_role(principal, ROLE_DATA_ENGINEER)


def _err(e: Exception, status: int = 500) -> JSONResponse:
    return JSONResponse({"ok": False, "code": type(e).__name__, "error": str(e)[:600]}, status_code=status)


@router.get("/status")
async def sl_status(request: Request, principal: RequestPrincipal = Depends(get_current_principal)) -> JSONResponse:
    try:
        rt = _runtime(_ds(request), principal.tenant_id)
        s = rt.settings
        return JSONResponse({
            "ok": True,
            "datasourceId": s.datasource_id,
            "status": rt.store.status_counts(s.tenant_id, s.datasource_id),
            "certifiedByType": rt.store.type_counts(s.tenant_id, s.datasource_id),
            "version": rt.store.latest_version(s.tenant_id, s.datasource_id),
            "profiles": len(rt.profiles),
            "queries": rt.store.query_stats(s.tenant_id, s.datasource_id),
            "unresolved": dict(list(rt.store.list_unresolved_terms(s.tenant_id, s.datasource_id).items())[:30]),
        })
    except Exception as e:  # noqa: BLE001
        return _err(e)


@router.get("/inventory")
async def sl_inventory(request: Request, principal: RequestPrincipal = Depends(get_current_principal)) -> JSONResponse:
    try:
        rt = _runtime(_ds(request), principal.tenant_id)
        rt.rebuild()
        return JSONResponse(rt.inventory())
    except Exception as e:  # noqa: BLE001
        return _err(e)


@router.get("/gaps")
async def sl_gaps(request: Request, days: int = 30, limit: int = 50, principal: RequestPrincipal = Depends(get_current_principal)) -> JSONResponse:
    """Terms real users asked for that the catalog could not place — the queue behind this page.

    A word here is not an error: it is a part of the business nobody has written down yet, which is
    exactly what an annotation on this page supplies.
    """
    try:
        rt = _runtime(_ds(request), principal.tenant_id)
        s = rt.settings
        gaps = rt.store.term_gaps(s.tenant_id, s.datasource_id, since_days=max(1, min(days, 365)), limit=max(1, min(limit, 200)))
        return JSONResponse({"ok": True, "days": days, "gaps": gaps,
                             "unmeasuredWindows": [p.entity for p in rt.profiles if p.time_window is None]})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@router.post("/annotations")
async def sl_add_annotation(request: Request, body: dict[str, Any], principal: RequestPrincipal = Depends(get_current_principal)) -> JSONResponse:
    text = str(body.get("text") or "").strip()
    table_pattern = str(body.get("tablePattern") or body.get("table_pattern") or "").strip()
    if not text or not table_pattern:
        return JSONResponse({"ok": False, "code": "VALIDATION", "error": "tablePattern ve text zorunlu."}, status_code=400)
    try:
        rt = _runtime(_ds(request, body), principal.tenant_id)
        out = rt.add_annotation(table_pattern, body.get("column"), text, principal.user_id or "portal")
        out["ok"] = True
        return JSONResponse(out)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@router.delete("/annotations/{annotation_id}")
async def sl_retire_annotation(annotation_id: str, request: Request, principal: RequestPrincipal = Depends(get_current_principal)) -> JSONResponse:
    try:
        rt = _runtime(_ds(request), principal.tenant_id)
        return JSONResponse({"ok": rt.store.retire_annotation(annotation_id)})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@router.get("/concepts")
async def sl_concepts(request: Request, status: Optional[str] = None, type: Optional[str] = None, q: Optional[str] = None, limit: int = 500, principal: RequestPrincipal = Depends(get_current_principal)) -> JSONResponse:
    try:
        rt = _runtime(_ds(request), principal.tenant_id)
        s = rt.settings
        rows = rt.store.search_concepts(s.tenant_id, s.datasource_id, q, limit) if q else rt.store.find_concepts(s.tenant_id, s.datasource_id, status=status, semantic_type=type, limit=limit)
        return JSONResponse({"items": [{"concept": c.to_dict(), "mappings": [m.to_dict() for m in rt.store.list_mappings(c.id)]} for c in rows]})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@router.get("/concepts/{concept_id}")
async def sl_concept(concept_id: str, request: Request, principal: RequestPrincipal = Depends(get_current_principal)) -> JSONResponse:
    try:
        rt = _runtime(_ds(request), principal.tenant_id)
        b = rt.store.concept_bundle(concept_id)
        if not b:
            return JSONResponse({"ok": False, "code": "NOT_FOUND"}, status_code=404)
        return JSONResponse(b)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@router.post("/concepts/{concept_id}/certify")
async def sl_certify_concept(concept_id: str, request: Request, body: dict[str, Any] | None = None, principal: RequestPrincipal = Depends(get_current_principal)) -> JSONResponse:
    if not (has_role(principal, ROLE_ADMIN) or has_role(principal, ROLE_DATA_ENGINEER)):
        return JSONResponse({"ok": False, "code": "FORBIDDEN", "error": "Sertifikasyon için admin / data engineer rolü gerekir."}, status_code=403)
    try:
        from semantic_layer.evidence.engine import EvidenceEngine

        rt = _runtime(_ds(request, body), principal.tenant_id)
        c = EvidenceEngine(rt.store).human_certify(concept_id, principal.user_id, str((body or {}).get("reason") or ""))
        rt.rebuild()
        return JSONResponse({"ok": c is not None, "concept": c.to_dict() if c else None})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@router.post("/concepts/{concept_id}/reject")
async def sl_reject_concept(concept_id: str, request: Request, body: dict[str, Any] | None = None, principal: RequestPrincipal = Depends(get_current_principal)) -> JSONResponse:
    if not (has_role(principal, ROLE_ADMIN) or has_role(principal, ROLE_DATA_ENGINEER)):
        return JSONResponse({"ok": False, "code": "FORBIDDEN"}, status_code=403)
    try:
        from semantic_layer.evidence.engine import EvidenceEngine

        rt = _runtime(_ds(request, body), principal.tenant_id)
        c = EvidenceEngine(rt.store).human_reject(concept_id, principal.user_id, str((body or {}).get("reason") or ""))
        rt.rebuild()
        return JSONResponse({"ok": c is not None, "concept": c.to_dict() if c else None})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@router.post("/certify-run")
async def sl_certify_run(request: Request, body: dict[str, Any] | None = None, principal: RequestPrincipal = Depends(get_current_principal)) -> JSONResponse:
    if not _may_govern(principal):
        return JSONResponse({"ok": False, "code": "FORBIDDEN", "error": "Sertifikasyon için admin / data engineer rolü gerekir."}, status_code=403)
    try:
        rt = _runtime(_ds(request, body), principal.tenant_id)
        rt.rebuild()          # certify against what the catalog holds now, not a snapshot from first use
        return JSONResponse({"ok": True, "report": rt.certify(note=f"portal:{principal.user_id}")})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@router.post("/pipeline")
async def sl_pipeline(request: Request, body: dict[str, Any] | None = None, principal: RequestPrincipal = Depends(get_current_principal)) -> JSONResponse:
    """Full offline pipeline (profile → mine → docs → certify). Profiles from the datasource connection
    when configured (SEMANTIC_CONNECTION_FILE / registered Postgres datasource), else from the project dir."""
    if not (has_role(principal, ROLE_ADMIN) or has_role(principal, ROLE_DATA_ENGINEER)):
        return JSONResponse({"ok": False, "code": "FORBIDDEN"}, status_code=403)
    try:
        from semantic_layer import pipeline as pl
        from semantic_layer.profiler.connectors import PostgresConnector

        rt = _runtime(_ds(request, body), principal.tenant_id)
        s = rt.settings
        connector = None
        try:
            from nanobase_api.infrastructure.datasource_registry import resolve_pg_connect_cfg

            cfg = resolve_pg_connect_cfg(s.datasource_id)
            if cfg:
                connector = PostgresConnector(cfg)
                s.schema_name = str((body or {}).get("schema") or s.schema_name or connector.default_schema)
                s.table_like = str((body or {}).get("tableLike") or s.table_like or "")
        except Exception:  # noqa: BLE001
            connector = None
        if connector is not None:
            profiles = pl.run_profile(rt.store, s, connector)
            connector.close()
            report: dict[str, Any] = {"profile": {"tables": len(profiles)}}
            report["mine"] = pl.run_mine(rt.store, s, profiles, s.project_dir)
            from semantic_layer.candidates.generator import CandidateGenerator

            gen = CandidateGenerator(rt.store, s.tenant_id, s.datasource_id, profiles)
            report["docs"] = gen.ingest_project_docs(s.project_dir)
            report["profile_evidence"] = gen.attach_profile_evidence()
            report["certify"] = rt.certify(note=f"portal pipeline:{principal.user_id}")
        else:
            enum_probe = os.environ.get("SEMANTIC_ENUM_PROBE")
            report = pl.run_pipeline(rt.store, s, enum_probe=Path(enum_probe) if enum_probe else None, note=f"portal pipeline:{principal.user_id}")
            rt.rebuild()
        return JSONResponse({"ok": True, "report": report})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@router.get("/explain")
async def sl_explain(request: Request, term: str, principal: RequestPrincipal = Depends(get_current_principal)) -> JSONResponse:
    try:
        rt = _runtime(_ds(request), principal.tenant_id)
        return JSONResponse(rt.resolver.explain_term(term))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@router.post("/resolve")
async def sl_resolve(request: Request, body: dict[str, Any], principal: RequestPrincipal = Depends(get_current_principal)) -> JSONResponse:
    try:
        rt = _runtime(_ds(request, body), principal.tenant_id)
        sq = rt.resolver.resolve(str(body.get("question") or ""))
        det = rt.router.deterministic
        out = det.compile(sq, rt.store) if det else None
        return JSONResponse({"query": sq.to_dict(), "sql": out.sql if out else None, "explain": out.explain if out else (det.plan(sq)[1] if det else None)})
    except Exception as e:  # noqa: BLE001
        return _err(e)
