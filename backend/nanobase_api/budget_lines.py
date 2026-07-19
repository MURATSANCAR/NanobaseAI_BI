"""Budget periods + commitments (+ cost centers list/save)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from nanobase_api.infrastructure.budget_schema import ensure_budget_tables


def list_periods(
    engine: Engine, budget_id: str, *, tenant_id: str = "default"
) -> list[dict[str, Any]]:
    ensure_budget_tables(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT period_index, allocated, actual
                FROM bi_budget_periods
                WHERE tenant_id = :tenant AND budget_id = :bid
                """
            ),
            {"tenant": tenant_id, "bid": budget_id},
        ).mappings()
        by_i = {int(r["period_index"]): r for r in rows}
    out = []
    for i in range(1, 13):
        r = by_i.get(i)
        out.append(
            {
                "period_index": i,
                "allocated": float(r["allocated"]) if r else 0.0,
                "actual": float(r["actual"]) if r and r["actual"] is not None else None,
            }
        )
    return out


def save_periods(
    engine: Engine,
    budget_id: str,
    periods: list[dict[str, Any]],
    *,
    tenant_id: str = "default",
) -> list[dict[str, Any]]:
    ensure_budget_tables(engine)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        for p in periods:
            idx = int(p.get("period_index") or 0)
            if idx < 1 or idx > 12:
                continue
            alloc = float(p.get("allocated") or 0)
            actual = p.get("actual")
            actual_f = float(actual) if actual is not None else None
            conn.execute(
                text(
                    """
                    INSERT INTO bi_budget_periods
                      (tenant_id, budget_id, period_index, allocated, actual, updated_at)
                    VALUES (:tenant, :bid, :idx, :alloc, :actual, :now)
                    ON CONFLICT (tenant_id, budget_id, period_index)
                    DO UPDATE SET allocated = EXCLUDED.allocated,
                                  actual = EXCLUDED.actual,
                                  updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "tenant": tenant_id,
                    "bid": budget_id,
                    "idx": idx,
                    "alloc": alloc,
                    "actual": actual_f,
                    "now": now,
                },
            )
    return list_periods(engine, budget_id, tenant_id=tenant_id)


def list_commitments(
    engine: Engine, budget_id: str, *, tenant_id: str = "default"
) -> list[dict[str, Any]]:
    ensure_budget_tables(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, description, amount, currency, status, due_date, created_at, updated_at
                FROM bi_budget_commitments
                WHERE tenant_id = :tenant AND budget_id = :bid
                ORDER BY created_at DESC
                """
            ),
            {"tenant": tenant_id, "bid": budget_id},
        ).mappings()
        return [
            {
                "id": r["id"],
                "description": r["description"] or "",
                "amount": float(r["amount"] or 0),
                "currency": r["currency"] or "TRY",
                "status": r["status"] or "open",
                "due_date": r["due_date"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
            }
            for r in rows
        ]


def sum_open_commitments(
    engine: Engine, budget_id: str, *, tenant_id: str = "default"
) -> float:
    ensure_budget_tables(engine)
    with engine.connect() as conn:
        val = conn.execute(
            text(
                """
                SELECT COALESCE(SUM(amount), 0) AS total
                FROM bi_budget_commitments
                WHERE tenant_id = :tenant AND budget_id = :bid AND status = 'open'
                """
            ),
            {"tenant": tenant_id, "bid": budget_id},
        ).scalar()
        return float(val or 0)


def save_commitment(
    engine: Engine,
    budget_id: str,
    body: dict[str, Any],
    *,
    tenant_id: str = "default",
) -> dict[str, Any]:
    ensure_budget_tables(engine)
    cid = str(body.get("id") or f"cmt-{uuid.uuid4().hex[:10]}")
    amount = float(body.get("amount") or 0)
    if amount < 0:
        raise ValueError("bi_commitment_amount_invalid")
    status = str(body.get("status") or "open").lower()
    if status not in ("open", "released", "cancelled"):
        status = "open"
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        existing = conn.execute(
            text(
                "SELECT id FROM bi_budget_commitments WHERE tenant_id = :tenant AND id = :id"
            ),
            {"tenant": tenant_id, "id": cid},
        ).first()
        if existing:
            conn.execute(
                text(
                    """
                    UPDATE bi_budget_commitments SET
                      description = :desc, amount = :amount, currency = :cur,
                      status = :status, due_date = :due, updated_at = :now
                    WHERE tenant_id = :tenant AND id = :id
                    """
                ),
                {
                    "tenant": tenant_id,
                    "id": cid,
                    "desc": str(body.get("description") or "")[:256],
                    "amount": amount,
                    "cur": str(body.get("currency") or "TRY")[:8],
                    "status": status,
                    "due": body.get("due_date"),
                    "now": now,
                },
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO bi_budget_commitments (
                      id, tenant_id, budget_id, description, amount, currency, status, due_date,
                      created_at, updated_at
                    ) VALUES (
                      :id, :tenant, :bid, :desc, :amount, :cur, :status, :due, :now, :now
                    )
                    """
                ),
                {
                    "id": cid,
                    "tenant": tenant_id,
                    "bid": budget_id,
                    "desc": str(body.get("description") or "")[:256],
                    "amount": amount,
                    "cur": str(body.get("currency") or "TRY")[:8],
                    "status": status,
                    "due": body.get("due_date"),
                    "now": now,
                },
            )
    # Sync envelope committed from open lines
    total = sum_open_commitments(engine, budget_id, tenant_id=tenant_id)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE bi_budgets SET committed = :comm, updated_at = :now
                WHERE tenant_id = :tenant AND id = :bid AND locked = false
                """
            ),
            {"comm": total, "now": now, "tenant": tenant_id, "bid": budget_id},
        )
    items = list_commitments(engine, budget_id, tenant_id=tenant_id)
    return next(c for c in items if c["id"] == cid)


def delete_commitment(
    engine: Engine,
    budget_id: str,
    commitment_id: str,
    *,
    tenant_id: str = "default",
) -> None:
    ensure_budget_tables(engine)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                DELETE FROM bi_budget_commitments
                WHERE tenant_id = :tenant AND budget_id = :bid AND id = :id
                """
            ),
            {"tenant": tenant_id, "bid": budget_id, "id": commitment_id},
        )
    total = sum_open_commitments(engine, budget_id, tenant_id=tenant_id)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE bi_budgets SET committed = :comm, updated_at = :now
                WHERE tenant_id = :tenant AND id = :bid AND locked = false
                """
            ),
            {"comm": total, "now": now, "tenant": tenant_id, "bid": budget_id},
        )


def list_cost_centers(engine: Engine, *, tenant_id: str = "default") -> dict[str, Any]:
    ensure_budget_tables(engine)
    with engine.connect() as conn:
        rows = list(
            conn.execute(
                text(
                    """
                    SELECT id, code, name, parent_id, active
                    FROM bi_cost_centers
                    WHERE tenant_id = :tenant
                    ORDER BY code
                    """
                ),
                {"tenant": tenant_id},
            ).mappings()
        )
    items = [
        {
            "id": r["id"],
            "code": r["code"] or "",
            "name": r["name"] or "",
            "parent_id": r["parent_id"],
            "active": bool(r["active"]),
        }
        for r in rows
    ]
    return {"cost_centers": items, "tree": items}


def save_cost_center(
    engine: Engine, body: dict[str, Any], *, tenant_id: str = "default"
) -> dict[str, Any]:
    ensure_budget_tables(engine)
    cid = str(body.get("id") or f"cc-{uuid.uuid4().hex[:10]}")
    code = str(body.get("code") or "").strip()
    if not code:
        raise ValueError("bi_cost_center_code_required")
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM bi_cost_centers WHERE tenant_id = :t AND id = :id"),
            {"t": tenant_id, "id": cid},
        ).first()
        if existing:
            conn.execute(
                text(
                    """
                    UPDATE bi_cost_centers SET
                      code = :code, name = :name, parent_id = :parent,
                      active = :active, updated_at = :now
                    WHERE tenant_id = :t AND id = :id
                    """
                ),
                {
                    "t": tenant_id,
                    "id": cid,
                    "code": code[:64],
                    "name": str(body.get("name") or code)[:256],
                    "parent": body.get("parent_id"),
                    "active": bool(body.get("active", True)),
                    "now": now,
                },
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO bi_cost_centers
                      (id, tenant_id, code, name, parent_id, active, created_at, updated_at)
                    VALUES (:id, :t, :code, :name, :parent, :active, :now, :now)
                    ON CONFLICT (tenant_id, code) DO UPDATE SET
                      name = EXCLUDED.name, parent_id = EXCLUDED.parent_id,
                      active = EXCLUDED.active, updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "id": cid,
                    "t": tenant_id,
                    "code": code[:64],
                    "name": str(body.get("name") or code)[:256],
                    "parent": body.get("parent_id"),
                    "active": bool(body.get("active", True)),
                    "now": now,
                },
            )
    return {
        "id": cid,
        "code": code,
        "name": str(body.get("name") or code),
        "parent_id": body.get("parent_id"),
        "active": bool(body.get("active", True)),
    }
