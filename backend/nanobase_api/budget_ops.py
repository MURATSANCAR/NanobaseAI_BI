"""Approve / lock / clone / transfer / narrative for budgets."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.engine import Engine

from nanobase_api import budgets as budgets_mod
from nanobase_api.budget_actuals import validate_budget_sql


def _actor_label(actor: str | None) -> str:
    return (actor or "system")[:128]


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
