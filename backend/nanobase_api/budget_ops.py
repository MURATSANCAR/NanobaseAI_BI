"""Approve / lock / clone / transfer / narrative for budgets."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.engine import Engine

from nanobase_api import alerts as alerts_mod
from nanobase_api import budgets as budgets_mod
from nanobase_api.budget_actuals import validate_budget_sql
from nanobase_api.infrastructure.query_gateway_client import QueryGatewayClient

_AS_COL = re.compile(r"\bas\s+([a-z_][\w]*)\s*$", re.I | re.M)


def _actor_label(actor: str | None) -> str:
    return (actor or "system")[:128]


def _sql_result_column(sql: str) -> str:
    cleaned = (sql or "").strip().rstrip(";")
    m = _AS_COL.search(cleaned)
    if m:
        return m.group(1)
    return "amount"


def _fingerprint(budget_id: str, threshold_pct: float, condition: str) -> str:
    raw = f"{budget_id}|{threshold_pct:.4g}|{condition}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def create_alert_from_budget(
    engine: Engine,
    budget: dict[str, Any],
    *,
    tenant_id: str,
    threshold_pct: float = 80.0,
    condition: str = "gte",
    recipient: str | None = None,
) -> dict[str, Any]:
    """Idempotent: same budget+threshold+condition returns existing alert."""
    sql = str(budget.get("actuals_sql") or "").strip()
    if not sql:
        raise ValueError("bi_budget_sql_required")
    allocated = float(budget.get("allocated") or 0)
    if allocated < 0:
        raise ValueError("bi_budget_allocated_invalid")
    bid = str(budget.get("id") or "")
    if not bid:
        raise ValueError("bi_budget_not_found")
    cond = (condition or "gte").lower()
    if cond not in ("gt", "gte", "lt", "lte", "eq", "neq"):
        cond = "gte"
    pct = float(threshold_pct)
    if pct <= 0 or pct > 500:
        pct = 80.0
    threshold_amount = round(allocated * (pct / 100.0), 2)
    fp = _fingerprint(bid, pct, cond)
    column = _sql_result_column(sql)
    name = str(budget.get("name") or bid)
    title = f"[Budget] {name} ≥ {pct:g}% plan"

    existing = alerts_mod.list_alerts(engine, tenant_id=tenant_id)
    for a in existing:
        if a.get("budget_fingerprint") == fp:
            return {**a, "created": False}

    entry = {
        "title": title[:256],
        "sql": sql,
        "column": column,
        "condition": cond,
        "threshold": threshold_amount,
        "recipient": recipient,
        "status": "active",
        "budget_id": bid,
        "budget_fingerprint": fp,
        "budget_threshold_pct": pct,
    }
    saved = alerts_mod.save_alert(engine, entry, tenant_id=tenant_id)
    return {**saved, "created": True}


def encode_budget_pack_resource_id(
    fiscal_year: int,
    *,
    scenario: str = "base",
    reporting_currency: str | None = None,
    locale: str | None = None,
) -> str:
    """Compact share resource_id: ``YYYY`` / ``YYYY:scenario`` / ``YYYY:scenario:CCY`` / ``…:locale``."""
    scen = (scenario or "base").strip().lower() or "base"
    if scen not in ("base", "optimistic", "pessimistic"):
        scen = "base"
    ccy = (reporting_currency or "").strip().upper() or None
    loc = (locale or "").strip().lower()[:2] or None
    if loc and loc not in ("en", "tr", "ru", "uz"):
        loc = "en"
    if loc:
        return f"{int(fiscal_year)}:{scen}:{ccy or '_'}:{loc}"
    if ccy:
        return f"{int(fiscal_year)}:{scen}:{ccy}"
    if scen != "base":
        return f"{int(fiscal_year)}:{scen}"
    return str(int(fiscal_year))


def decode_budget_pack_resource_id(resource_id: str) -> dict[str, Any]:
    """Parse share resource_id; plain year stays backward-compatible."""
    raw = str(resource_id or "").strip()
    parts = raw.split(":")
    year = 0
    if parts and parts[0]:
        try:
            year = int(parts[0])
        except ValueError:
            year = 0
    scen = (parts[1] if len(parts) > 1 and parts[1] else "base").strip().lower() or "base"
    if scen not in ("base", "optimistic", "pessimistic"):
        scen = "base"
    ccy_raw = parts[2].strip() if len(parts) > 2 else ""
    ccy = ccy_raw.upper() if ccy_raw and ccy_raw != "_" else None
    loc_raw = parts[3].strip().lower()[:2] if len(parts) > 3 else ""
    locale = loc_raw if loc_raw in ("en", "tr", "ru", "uz") else None
    return {
        "fiscal_year": year,
        "scenario": scen,
        "reporting_currency": ccy,
        "locale": locale,
    }


async def run_budget_breakdown(
    budget: dict[str, Any],
    *,
    datasource_id: str,
    tenant_id: str | None = None,
    row_limit: int = 50,
) -> dict[str, Any]:
    """Execute envelope breakdown_sql (read-only, limited rows)."""
    sql = str(budget.get("breakdown_sql") or "").strip()
    if not sql:
        raise ValueError("bi_budget_breakdown_sql_required")
    validated = await validate_budget_sql(
        sql, datasource_id=datasource_id, tenant_id=tenant_id
    )
    cleaned = str(validated.get("sql") or sql).strip().rstrip(";")
    client = QueryGatewayClient()
    result = await client.execute(
        sql=cleaned, datasource_id=datasource_id, tenant_id=tenant_id
    )
    if not result.get("ok"):
        raise ValueError(result.get("error") or "bi_budget_breakdown_failed")
    columns = list(result.get("columns") or [])
    all_rows = list(result.get("rows") or [])
    lim = max(1, min(int(row_limit or 50), 50))
    rows = all_rows[:lim]
    return {
        "budget_id": budget.get("id"),
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": len(all_rows) > len(rows),
    }


def build_budget_pack_share_payload(
    engine: Engine,
    *,
    tenant_id: str,
    fiscal_year: int,
    scenario: str = "base",
    reporting_currency: str | None = None,
    locale: str | None = None,
) -> dict[str, Any]:
    """Read-only public board-pack payload (no SQL / owner emails)."""
    from nanobase_api.budget_export import display_budget_lines

    year = int(fiscal_year or datetime.now(timezone.utc).year)
    scen = (scenario or "base").strip().lower() or "base"
    if scen not in ("base", "optimistic", "pessimistic"):
        scen = "base"
    report_ccy = (reporting_currency or "").strip().upper() or None
    loc = (locale or "en").strip().lower()[:2] or "en"
    if loc not in ("en", "tr", "ru", "uz"):
        loc = "en"
    summary = budgets_mod.budget_summary(
        engine,
        fiscal_year=year,
        tenant_id=tenant_id,
        scenario=scen,
        reporting_currency=report_ccy,
    )
    rows_raw = display_budget_lines(
        engine,
        fiscal_year=year,
        tenant_id=tenant_id,
        scenario=scen,
        reporting_currency=report_ccy,
    )
    table = [
        {
            "id": r.get("id"),
            "name": r.get("name"),
            "kind": r.get("kind"),
            "cost_center": r.get("cost_center"),
            "allocated": r.get("allocated"),
            "committed": r.get("committed"),
            "actual": r.get("actual"),
            "remaining": r.get("remaining"),
            "used_pct": r.get("used_pct"),
            "health": r.get("health"),
            "status": r.get("status"),
            "currency": r.get("currency") or report_ccy or "TRY",
            "scenario": r.get("scenario") or scen,
        }
        for r in rows_raw
    ]
    title = f"Budget FY{year} · {scen}"
    if report_ccy:
        title = f"{title} · {report_ccy}"
    narrative = build_budget_narrative(
        engine,
        tenant_id=tenant_id,
        fiscal_year=year,
        locale=loc,
        scenario=scen,
        reporting_currency=report_ccy,
    )
    return {
        "type": "budget_pack",
        "resource_type": "budget_pack",
        "title": title,
        "fiscal_year": year,
        "scenario": scen,
        "reporting_currency": report_ccy,
        "locale": loc,
        "summary": summary,
        "rows": table,
        "narrative": narrative.get("text"),
    }


async def approve_budget(
    engine: Engine,
    budget_id: str,
    *,
    tenant_id: str = "default",
    actor: str | None = None,
    datasource_id: str | None = None,
) -> dict[str, Any]:
    budget = budgets_mod.get_budget(engine, budget_id, tenant_id=tenant_id)
    if not budget:
        raise ValueError("bi_budget_not_found")
    if budget.get("locked"):
        raise ValueError("bi_budget_locked")
    sql = str(budget.get("actuals_sql") or "").strip()
    if sql:
        await validate_budget_sql(sql, datasource_id=datasource_id, tenant_id=tenant_id)
    now = datetime.now(timezone.utc)
    saved = budgets_mod.patch_budget_fields(
        engine,
        budget_id,
        {
            "status": "approved",
            "approved_at": now,
            "approved_by": _actor_label(actor),
            "version": int(budget.get("version") or 1) + 1,
        },
        tenant_id=tenant_id,
        allow_locked=False,
    )
    budgets_mod.append_change(
        engine,
        tenant_id=tenant_id,
        budget_id=budget_id,
        action="approve",
        actor=actor,
        field="status",
        old_value=budget.get("status"),
        new_value="approved",
    )
    return saved


def set_budget_locked(
    engine: Engine,
    budget_id: str,
    *,
    locked: bool,
    tenant_id: str = "default",
    actor: str | None = None,
) -> dict[str, Any]:
    budget = budgets_mod.get_budget(engine, budget_id, tenant_id=tenant_id)
    if not budget:
        raise ValueError("bi_budget_not_found")
    fields: dict[str, Any] = {
        "locked": bool(locked),
        "version": int(budget.get("version") or 1) + 1,
    }
    if not locked and str(budget.get("status") or "").lower() == "closed":
        fields["status"] = "approved" if budget.get("approved_at") else "draft"
    saved = budgets_mod.patch_budget_fields(
        engine,
        budget_id,
        fields,
        tenant_id=tenant_id,
        allow_locked=True,
    )
    budgets_mod.append_change(
        engine,
        tenant_id=tenant_id,
        budget_id=budget_id,
        action="lock" if locked else "unlock",
        actor=actor,
        field="locked",
        old_value=budget.get("locked"),
        new_value=locked,
    )
    return saved


def clone_budgets_year(
    engine: Engine,
    *,
    tenant_id: str,
    from_year: int,
    to_year: int,
    copy_actuals_sql: bool = True,
    scenario: str | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    if int(from_year) == int(to_year):
        raise ValueError("bi_budget_clone_same_year")
    if to_year < 2000 or to_year > 2100 or from_year < 2000 or from_year > 2100:
        raise ValueError("bi_budget_clone_year_invalid")
    scen_filter = (scenario or "").strip().lower() or None
    if scen_filter and scen_filter not in ("base", "optimistic", "pessimistic"):
        scen_filter = "base"

    source = budgets_mod.list_budgets(
        engine, tenant_id=tenant_id, fiscal_year=from_year, scenario=scen_filter
    )
    dest = budgets_mod.list_budgets(engine, tenant_id=tenant_id, fiscal_year=to_year)
    dest_keys = {
        (
            str(d.get("name") or "").strip().lower(),
            str(d.get("kind") or "").lower(),
            str(d.get("cost_center") or "").strip().lower(),
            str(d.get("scenario") or "base").strip().lower(),
        )
        for d in dest
    }
    created = 0
    skipped = 0
    errors: list[dict[str, Any]] = []
    for src in source:
        src_scen = str(src.get("scenario") or "base").strip().lower() or "base"
        key = (
            str(src.get("name") or "").strip().lower(),
            str(src.get("kind") or "").lower(),
            str(src.get("cost_center") or "").strip().lower(),
            src_scen,
        )
        if key in dest_keys:
            skipped += 1
            continue
        try:
            budgets_mod.upsert_budget(
                engine,
                {
                    "fiscal_year": int(to_year),
                    "cost_center": src.get("cost_center") or "",
                    "kind": src.get("kind") or "opex",
                    "name": src.get("name"),
                    "allocated": float(src.get("allocated") or 0),
                    "currency": src.get("currency") or "TRY",
                    "committed": 0,
                    "actuals_sql": (src.get("actuals_sql") or "") if copy_actuals_sql else "",
                    "owner": src.get("owner") or "",
                    "status": "draft",
                    "notes": src.get("notes") or "",
                    "scenario": src_scen,
                    "budget_code": src.get("budget_code"),
                },
                tenant_id=tenant_id,
                actor=actor,
            )
            created += 1
            dest_keys.add(key)
        except ValueError as exc:
            errors.append({"name": src.get("name"), "code": str(exc)})
        except Exception as exc:
            errors.append(
                {
                    "name": src.get("name"),
                    "code": "bi_budget_clone_row_failed",
                    "detail": str(exc)[:120],
                }
            )
    return {
        "from_year": int(from_year),
        "to_year": int(to_year),
        "scenario": scen_filter,
        "created": created,
        "skipped": skipped,
        "errors": errors,
    }


def transfer_allocated(
    engine: Engine,
    *,
    tenant_id: str,
    from_budget_id: str,
    to_budget_id: str,
    amount: float,
    actor: str | None = None,
) -> dict[str, Any]:
    if from_budget_id == to_budget_id:
        raise ValueError("bi_budget_transfer_same")
    amt = float(amount)
    if amt <= 0:
        raise ValueError("bi_budget_transfer_amount_invalid")
    src = budgets_mod.get_budget(engine, from_budget_id, tenant_id=tenant_id)
    dst = budgets_mod.get_budget(engine, to_budget_id, tenant_id=tenant_id)
    if not src or not dst:
        raise ValueError("bi_budget_not_found")
    if src.get("locked") or dst.get("locked"):
        raise ValueError("bi_budget_locked")
    if str(src.get("status") or "").lower() == "closed" or str(dst.get("status") or "").lower() == "closed":
        raise ValueError("bi_budget_closed")
    src_alloc = float(src.get("allocated") or 0)
    if amt > src_alloc:
        raise ValueError("bi_budget_transfer_exceeds")
    new_src = budgets_mod.patch_budget_fields(
        engine,
        from_budget_id,
        {"allocated": round(src_alloc - amt, 2), "version": int(src.get("version") or 1) + 1},
        tenant_id=tenant_id,
    )
    new_dst = budgets_mod.patch_budget_fields(
        engine,
        to_budget_id,
        {
            "allocated": round(float(dst.get("allocated") or 0) + amt, 2),
            "version": int(dst.get("version") or 1) + 1,
        },
        tenant_id=tenant_id,
    )
    budgets_mod.append_change(
        engine,
        tenant_id=tenant_id,
        budget_id=from_budget_id,
        action="transfer_out",
        actor=actor,
        field="allocated",
        old_value=src_alloc,
        new_value=new_src.get("allocated"),
    )
    budgets_mod.append_change(
        engine,
        tenant_id=tenant_id,
        budget_id=to_budget_id,
        action="transfer_in",
        actor=actor,
        field="allocated",
        old_value=dst.get("allocated"),
        new_value=new_dst.get("allocated"),
    )
    return {"amount": amt, "from": new_src, "to": new_dst}


def build_budget_narrative(
    engine: Engine,
    *,
    tenant_id: str,
    fiscal_year: int,
    locale: str | None = None,
    scenario: str | None = None,
    reporting_currency: str | None = None,
) -> dict[str, Any]:
    loc = (locale or "en").split("-")[0].lower()
    scen = (scenario or "").strip().lower() or None
    if scen and scen not in ("base", "optimistic", "pessimistic"):
        scen = "base"
    report_ccy = (reporting_currency or "").strip().upper() or None
    items = budgets_mod.list_budgets(
        engine, tenant_id=tenant_id, fiscal_year=fiscal_year, scenario=scen
    )
    summary = budgets_mod.budget_summary(
        engine,
        tenant_id=tenant_id,
        fiscal_year=fiscal_year,
        scenario=scen,
        reporting_currency=report_ccy,
    )
    totals = summary.get("totals") or {}
    watched = [b for b in items if b.get("health") in ("watch", "over")]
    watched.sort(key=lambda x: float(x.get("used_pct") or 0), reverse=True)
    top = watched[:5]
    watch_n = int(summary.get("watch_count") or 0)
    over_n = int(summary.get("over_count") or 0)
    top_rows = [
        {
            "id": b.get("id"),
            "name": b.get("name"),
            "used_pct": b.get("used_pct"),
            "health": b.get("health"),
        }
        for b in top
    ]
    planned = totals.get("allocated")
    actual = totals.get("actual")
    remaining = totals.get("remaining")
    if loc.startswith("tr"):
        text = (
            f"{fiscal_year} bütçe özeti: {len(items)} kalem. "
            f"Planlanan {planned:,.0f}, gerçekleşen {actual:,.0f}, kalan {remaining:,.0f}. "
            f"İzleme: {watch_n}, aşım: {over_n}."
        )
        if top_rows:
            names = ", ".join(str(t.get("name") or t.get("id")) for t in top_rows[:3])
            text += f" Öncelikli kalemler: {names}."
    else:
        text = (
            f"{fiscal_year} budget summary: {len(items)} lines. "
            f"Planned {planned:,.0f}, actual {actual:,.0f}, remaining {remaining:,.0f}. "
            f"Watch: {watch_n}, over: {over_n}."
        )
        if top_rows:
            names = ", ".join(str(t.get("name") or t.get("id")) for t in top_rows[:3])
            text += f" Priority lines: {names}."

    return {
        "fiscal_year": fiscal_year,
        "locale": loc,
        "scenario": scen or "base",
        "reporting_currency": report_ccy or summary.get("reporting_currency"),
        "text": text[:1200],
        "source": "template",
        "watch_count": watch_n,
        "over_count": over_n,
        "totals": {
            "allocated": totals.get("allocated"),
            "actual": totals.get("actual"),
            "remaining": totals.get("remaining"),
            "count": totals.get("count") or len(items),
        },
        "top": top_rows,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
