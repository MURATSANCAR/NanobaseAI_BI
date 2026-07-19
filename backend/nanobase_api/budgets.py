"""Budgets backed by bi_meta.bi_budgets (+ optional ERP sync)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine


def _row_to_budget(r: Any) -> dict[str, Any]:
    allocated = float(r["allocated"] or 0)
    committed = float(r["committed"] or 0)
    actual = r["actual"]
    actual_f = float(actual) if actual is not None else None
    remaining = None
    used_pct = None
    health = None
    if actual_f is not None:
        remaining = allocated - committed - actual_f
        used_pct = round(actual_f / allocated * 100.0, 2) if allocated else None
        if remaining < 0:
            health = "over"
        elif used_pct is not None and used_pct >= 80:
            health = "watch"
        else:
            health = "ok"
    payload = {}
    try:
        payload = json.loads(r["payload_json"] or "{}")
    except Exception:
        payload = {}
    return {
        "id": r["id"],
        "fiscal_year": int(r["fiscal_year"]),
        "cost_center": r["cost_center"],
        "kind": r["kind"] or "opex",
        "name": r["name"],
        "allocated": allocated,
        "currency": r["currency"] or "TRY",
        "committed": committed,
        "actual": actual_f,
        "actuals_sql": r["actuals_sql"],
        "actual_error": r["actual_error"],
        "actuals_at": r["actuals_at"].isoformat() if r["actuals_at"] else None,
        "owner": r["owner"],
        "status": r["status"] or "draft",
        "notes": r["notes"],
        "remaining": remaining,
        "used_pct": used_pct,
        "health": health,
        "scenario": r["scenario"] or "base",
        "locked": bool(r["locked"]),
        "approved_at": r["approved_at"].isoformat() if r["approved_at"] else None,
        "approved_by": r["approved_by"],
        "version": int(r["version"] or 1),
        "budget_code": payload.get("budget_code"),
        "match_source": payload.get("match_source"),
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
    }


def list_budgets(
    engine: Engine,
    *,
    tenant_id: str = "default",
    fiscal_year: Optional[int] = None,
    kind: Optional[str] = None,
    status: Optional[str] = None,
    scenario: Optional[str] = None,
) -> list[dict[str, Any]]:
    clauses = ["tenant_id = :tenant"]
    params: dict[str, Any] = {"tenant": tenant_id}
    if fiscal_year is not None:
        clauses.append("fiscal_year = :fy")
        params["fy"] = fiscal_year
    if kind:
        clauses.append("kind = :kind")
        params["kind"] = kind
    if status:
        clauses.append("status = :status")
        params["status"] = status
    if scenario:
        clauses.append("scenario = :scenario")
        params["scenario"] = scenario
    where = " AND ".join(clauses)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT * FROM bi_budgets
                WHERE {where}
                ORDER BY fiscal_year DESC, name
                """
            ),
            params,
        ).mappings()
        return [_row_to_budget(r) for r in rows]


def budget_summary(
    engine: Engine,
    *,
    tenant_id: str = "default",
    fiscal_year: Optional[int] = None,
    scenario: Optional[str] = None,
) -> dict[str, Any]:
    budgets = list_budgets(
        engine, tenant_id=tenant_id, fiscal_year=fiscal_year, scenario=scenario
    )
    years = sorted({b["fiscal_year"] for b in budgets}, reverse=True)
    if fiscal_year is None and years:
        fiscal_year = years[0]
        budgets = [b for b in budgets if b["fiscal_year"] == fiscal_year]
    by_kind: dict[str, dict[str, float | int]] = {}
    totals = {"allocated": 0.0, "actual": 0.0, "committed": 0.0, "remaining": 0.0, "count": 0}
    watch = over = 0
    currencies: set[str] = set()
    for b in budgets:
        k = b.get("kind") or "other"
        slot = by_kind.setdefault(
            k, {"allocated": 0.0, "actual": 0.0, "committed": 0.0, "remaining": 0.0, "count": 0}
        )
        allocated = float(b.get("allocated") or 0)
        actual = float(b.get("actual") or 0)
        committed = float(b.get("committed") or 0)
        remaining = allocated - committed - actual
        for dest in (slot, totals):
            dest["allocated"] = float(dest["allocated"]) + allocated
            dest["actual"] = float(dest["actual"]) + actual
            dest["committed"] = float(dest["committed"]) + committed
            dest["remaining"] = float(dest["remaining"]) + remaining
            dest["count"] = int(dest["count"]) + 1
        if b.get("health") == "watch":
            watch += 1
        elif b.get("health") == "over":
            over += 1
        if b.get("currency"):
            currencies.add(str(b["currency"]))
    return {
        "fiscal_year": fiscal_year or datetime.now(timezone.utc).year,
        "suggested_fiscal_year": fiscal_year,
        "available_fiscal_years": years,
        "by_kind": by_kind,
        "totals": totals,
        "watch_count": watch,
        "over_count": over,
        "budget_watch_count": watch,
        "mixed_currency": len(currencies) > 1,
        "reporting_currency": next(iter(currencies), "TRY") if currencies else "TRY",
        "currencies": sorted(currencies),
    }


def upsert_budget(engine: Engine, body: dict[str, Any], *, tenant_id: str = "default") -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    bid = str(body.get("id") or f"bud-{uuid.uuid4().hex[:10]}")
    payload = {
        "budget_code": body.get("budget_code"),
        "match_source": body.get("match_source"),
    }
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM bi_budgets WHERE id = :id"), {"id": bid}
        ).first()
        if existing:
            conn.execute(
                text(
                    """
                    UPDATE bi_budgets SET
                      fiscal_year=:fy, cost_center=:cc, kind=:kind, name=:name,
                      allocated=:alloc, currency=:cur, committed=:comm,
                      actuals_sql=:asql, owner=:owner, status=:status, notes=:notes,
                      scenario=:scenario, payload_json=:payload, updated_at=:now
                    WHERE id=:id
                    """
                ),
                {
                    "id": bid,
                    "fy": int(body.get("fiscal_year") or now.year),
                    "cc": body.get("cost_center"),
                    "kind": body.get("kind") or "opex",
                    "name": body.get("name") or bid,
                    "alloc": float(body.get("allocated") or 0),
                    "cur": body.get("currency") or "TRY",
                    "comm": float(body.get("committed") or 0),
                    "asql": body.get("actuals_sql") or "",
                    "owner": body.get("owner"),
                    "status": body.get("status") or "draft",
                    "notes": body.get("notes"),
                    "scenario": body.get("scenario") or "base",
                    "payload": json.dumps(payload, ensure_ascii=False),
                    "now": now,
                },
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO bi_budgets (
                      id, tenant_id, fiscal_year, cost_center, kind, name, allocated, currency,
                      committed, actuals_sql, owner, status, notes, scenario, version, locked,
                      payload_json, created_at, updated_at
                    ) VALUES (
                      :id, :tenant, :fy, :cc, :kind, :name, :alloc, :cur,
                      :comm, :asql, :owner, :status, :notes, :scenario, 1, false,
                      :payload, :now, :now
                    )
                    """
                ),
                {
                    "id": bid,
                    "tenant": tenant_id,
                    "fy": int(body.get("fiscal_year") or now.year),
                    "cc": body.get("cost_center"),
                    "kind": body.get("kind") or "opex",
                    "name": body.get("name") or bid,
                    "alloc": float(body.get("allocated") or 0),
                    "cur": body.get("currency") or "TRY",
                    "comm": float(body.get("committed") or 0),
                    "asql": body.get("actuals_sql") or "",
                    "owner": body.get("owner"),
                    "status": body.get("status") or "draft",
                    "notes": body.get("notes"),
                    "scenario": body.get("scenario") or "base",
                    "payload": json.dumps(payload, ensure_ascii=False),
                    "now": now,
                },
            )
    rows = list_budgets(engine, tenant_id=tenant_id)
    return next(b for b in rows if b["id"] == bid)


def delete_budget(engine: Engine, budget_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM bi_budgets WHERE id = :id"), {"id": budget_id})


def sync_from_erp_butce(
    engine: Engine,
    erp_rows: list[dict[str, Any]],
    *,
    tenant_id: str = "default",
    datasource_id: str = "source",
) -> dict[str, Any]:
    """Upsert butce_planlari rows into bi_budgets (any budget-capable datasource)."""
    created = updated = 0
    now = datetime.now(timezone.utc)
    ds = str(datasource_id or "source").strip() or "source"
    with engine.begin() as conn:
        for r in erp_rows:
            code = str(r.get("butce_kodu") or r.get("id"))
            bid = f"{ds}-{code}-{r.get('mali_yil')}"
            payload = json.dumps(
                {
                    "budget_code": code,
                    "match_source": f"{ds}.butce_planlari",
                    "source_row_id": r.get("id"),
                    "datasource_id": ds,
                },
                ensure_ascii=False,
            )
            vals = {
                "id": bid,
                "tenant": tenant_id,
                "fy": int(r.get("mali_yil") or now.year),
                "cc": r.get("departman_kod"),
                "kind": str(r.get("tur") or "opex").lower(),
                "name": r.get("kalem_adi") or code,
                "alloc": float(r.get("planlanan_tutar") or 0),
                "cur": r.get("para_birimi") or "TRY",
                "status": "approved",
                "payload": payload,
                "now": now,
            }
            exists = conn.execute(
                text("SELECT id FROM bi_budgets WHERE id = :id"), {"id": bid}
            ).first()
            if exists:
                conn.execute(
                    text(
                        """
                        UPDATE bi_budgets SET
                          fiscal_year = :fy, cost_center = :cc, kind = :kind, name = :name,
                          allocated = :alloc, currency = :cur, status = :status,
                          payload_json = :payload, updated_at = :now
                        WHERE id = :id
                        """
                    ),
                    vals,
                )
                updated += 1
            else:
                conn.execute(
                    text(
                        """
                        INSERT INTO bi_budgets (
                          id, tenant_id, fiscal_year, cost_center, kind, name, allocated, currency,
                          committed, actuals_sql, owner, status, notes, scenario, version, locked,
                          payload_json, created_at, updated_at
                        ) VALUES (
                          :id, :tenant, :fy, :cc, :kind, :name, :alloc, :cur,
                          0, '', 'erp-sync', :status, '', 'base', 1, false,
                          :payload, :now, :now
                        )
                        """
                    ),
                    vals,
                )
                created += 1
    return {
        "ok": True,
        "fiscal_year": now.year,
        "created": created,
        "updated": updated,
        "skipped": 0,
        "match_count": created + updated,
        "source": "erp.butce_planlari",
    }
