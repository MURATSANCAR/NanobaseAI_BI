"""Chat-ready query templates backed by published scenario SQL."""

from __future__ import annotations

from typing import Any

from nanobase_api.suggestions import defaults_for, resolve_prepared_sql


def build_query_templates(
    *,
    tenant_id: str,
    datasource_id: str,
    limit: int = 24,
) -> dict[str, Any]:
    """Return BiQueryTemplate-shaped chips with sql_hint for the fast prepared_sql path."""
    from nanobase_api.infrastructure.active_source import prefer_datasource_id
    from nanobase_api.scenario_engine.application.param_resolver import resolve_parameters
    from nanobase_api.scenario_engine.domain.status import ScenarioStatus
    from nanobase_api.scenario_engine.infrastructure.store import get_scenario_store

    lim = max(1, min(int(limit or 24), 48))
    sid = prefer_datasource_id(datasource_id)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(
        *,
        tid: str,
        title: str,
        prompt: str,
        sql_hint: str | None,
        category: str | None = None,
        bind_params: dict[str, Any] | None = None,
        scenario_code: str | None = None,
        table_name: str | None = None,
        kind: str | None = None,
    ) -> None:
        key = (prompt or "").strip().lower()
        if not key or key in seen or len(out) >= lim:
            return
        if not (sql_hint or "").strip():
            return
        seen.add(key)
        row: dict[str, Any] = {
            "id": tid,
            "title": title,
            "prompt_tr": prompt,
            "prompt_en": prompt,
            "sql_hint": sql_hint,
            "category": category or "query",
            "widget_type": "kpi" if (kind or "").startswith("count") else "table",
            "source": "scenario",
            "kind": kind or "query",
            "table_name": table_name,
            "scenarioCode": scenario_code,
        }
        if bind_params:
            row["bind_params"] = bind_params
        out.append(row)

    # 1) Datasource defaults that resolve to precompiled SQL
    for q in defaults_for(sid):
        hit = resolve_prepared_sql(q, tenant_id=tenant_id, datasource_id=sid)
        if not hit:
            continue
        code = str(hit.get("scenarioCode") or "prepared")
        _add(
            tid=f"default:{code}:{len(out)}",
            title=q,
            prompt=q,
            sql_hint=str(hit.get("sql_hint") or ""),
            category="query",
            bind_params=hit.get("bind_params") if isinstance(hit.get("bind_params"), dict) else None,
            scenario_code=code,
            kind="count" if "count" in code else "query",
        )

    # 2) Published scenario catalog (simple families first)
    try:
        store = get_scenario_store()
        instances = store.list_instances(
            tenant_id=tenant_id, datasource_id=sid, status=ScenarioStatus.PUBLISHED
        )
        prefer = ("COUNT_ENTITY", "LIST_ENTITY", "SUM_MEASURE", "STATUS_FILTER")
        instances.sort(
            key=lambda i: (
                prefer.index(i.family) if i.family in prefer else 99,
                i.scenario_code,
            )
        )
        for inst in instances:
            if len(out) >= lim:
                break
            comp = store.get_compilation(inst.id, dialect="postgres")
            if comp is None or not (comp.sql_template or "").strip():
                continue
            q = (inst.canonical_question or "").strip()
            if not q:
                continue
            binds = resolve_parameters(q, inst.logical_plan).to_bind_dict()
            table = None
            try:
                table = getattr(inst.logical_plan, "physical_table", None) or getattr(
                    inst.logical_plan, "entity", None
                )
            except Exception:
                table = None
            _add(
                tid=f"scenario:{inst.scenario_code}",
                title=q,
                prompt=q,
                sql_hint=comp.sql_template,
                category=inst.category or "query",
                bind_params=dict(binds),
                scenario_code=inst.scenario_code,
                table_name=str(table) if table else None,
                kind="count" if inst.family == "COUNT_ENTITY" else "query",
            )
    except Exception:
        pass

    return {
        "templates": out,
        "meta": {
            "source_id": sid,
            "origin": "scenario_engine",
            "cached": False,
            "count": len(out),
        },
    }
