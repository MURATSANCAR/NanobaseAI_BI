"""Budgets backed by bi_meta.bi_budgets (+ optional ERP sync)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from nanobase_api.budget_fx import convert_amount, list_fx_rates
from nanobase_api.infrastructure.budget_schema import ensure_budget_tables


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _health(used_pct: float | None, status: str) -> str | None:
    if status != "approved" or used_pct is None:
        return None
    if used_pct > 100:
        return "over"
    if used_pct >= 80:
        return "watch"
    return "ok"


def compute_fields(entry: dict[str, Any]) -> dict[str, Any]:
    """Derive remaining / used_pct / health / burn metrics (commitment-aware)."""
    row = dict(entry)
    allocated = _num(row.get("allocated"))
    committed = _num(row.get("committed"))
    actual_raw = row.get("actual")
    has_error = bool(row.get("actual_error"))
    actual = _num(actual_raw) if actual_raw is not None and not has_error else None
    remaining = None
    used_pct = None
    if actual is not None:
        remaining = round(allocated - actual - committed, 2)
        denom = allocated if allocated != 0 else None
        used_pct = (
            round(((actual + committed) / denom) * 100.0, 2)
            if denom
            else (0.0 if (actual + committed) == 0 else 100.0)
        )
    elif not has_error:
        remaining = round(allocated - committed, 2)
        denom = allocated if allocated != 0 else None
        used_pct = round((committed / denom) * 100.0, 2) if denom else 0.0
    status = str(row.get("status") or "draft")
    row["remaining"] = remaining
    row["used_pct"] = used_pct
    row["health"] = _health(used_pct, status) if actual is not None else None

    burn_rate_daily = None
    runway_days = None
    projected_year_end = None
    if actual is not None and status == "approved":
        now = datetime.now(timezone.utc)
        fy = int(row.get("fiscal_year") or now.year)
        fy_start = datetime(fy, 1, 1, tzinfo=timezone.utc)
        fy_end = datetime(fy, 12, 31, tzinfo=timezone.utc)
        days_elapsed = max((now.date() - fy_start.date()).days, 1)
        days_remaining = max((fy_end.date() - now.date()).days, 0)
        burn_rate_daily = round(actual / days_elapsed, 4)
        if burn_rate_daily > 0 and remaining is not None and remaining > 0:
            runway_days = int(remaining / burn_rate_daily)
        elif remaining is not None and remaining <= 0:
            runway_days = 0
        projected_year_end = round(actual + burn_rate_daily * days_remaining, 2)
    row["burn_rate_daily"] = burn_rate_daily
    row["runway_days"] = runway_days
    row["projected_year_end"] = projected_year_end
    return row


def _row_to_budget(r: Any) -> dict[str, Any]:
    payload = {}
    try:
        payload = json.loads(r["payload_json"] or "{}")
    except Exception:
        payload = {}
    base = {
        "id": r["id"],
        "tenant_id": r.get("tenant_id") or "default",
        "fiscal_year": int(r["fiscal_year"]),
        "cost_center": r["cost_center"] or "",
        "kind": r["kind"] or "opex",
        "name": r["name"],
        "allocated": float(r["allocated"] or 0),
        "currency": r["currency"] or "TRY",
        "committed": float(r["committed"] or 0),
        "actual": float(r["actual"]) if r["actual"] is not None else None,
        "actuals_sql": r["actuals_sql"] or "",
        "actual_error": r["actual_error"],
        "actuals_at": r["actuals_at"].isoformat() if r["actuals_at"] else None,
        "owner": r["owner"] or "",
        "status": r["status"] or "draft",
        "notes": r["notes"] or "",
        "scenario": r["scenario"] or "base",
        "locked": bool(r["locked"]),
        "approved_at": r["approved_at"].isoformat() if r["approved_at"] else None,
        "approved_by": r["approved_by"],
        "version": int(r["version"] or 1),
        "budget_code": payload.get("budget_code"),
        "match_source": payload.get("match_source"),
        "breakdown_sql": payload.get("breakdown_sql") or "",
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
    }
    return compute_fields(base)


def get_budget(
    engine: Engine, budget_id: str, *, tenant_id: str = "default"
) -> dict[str, Any] | None:
    ensure_budget_tables(engine)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT * FROM bi_budgets
                WHERE tenant_id = :tenant AND id = :id
                """
            ),
            {"tenant": tenant_id, "id": budget_id},
        ).mappings().first()
        return _row_to_budget(row) if row else None


def list_budgets(
    engine: Engine,
    *,
    tenant_id: str = "default",
    fiscal_year: Optional[int] = None,
    kind: Optional[str] = None,
    status: Optional[str] = None,
    scenario: Optional[str] = None,
) -> list[dict[str, Any]]:
    ensure_budget_tables(engine)
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
    reporting_currency: Optional[str] = None,
) -> dict[str, Any]:
    budgets = list_budgets(
        engine, tenant_id=tenant_id, fiscal_year=fiscal_year, scenario=scenario
    )
    years = sorted(
        {b["fiscal_year"] for b in list_budgets(engine, tenant_id=tenant_id)},
        reverse=True,
    )
    if fiscal_year is None and years:
        fiscal_year = years[0]
        budgets = [b for b in budgets if b["fiscal_year"] == fiscal_year]

    report_ccy = (reporting_currency or "").strip().upper() or None
    rates = list_fx_rates(engine, tenant_id=tenant_id) if report_ccy else []
    fx_missing: list[dict[str, Any]] = []

    def _amt(b: dict[str, Any], key: str) -> float:
        raw = float(b.get(key) or 0)
        if not report_ccy:
            return raw
        converted = convert_amount(
            raw, from_currency=str(b.get("currency") or "TRY"), to_currency=report_ccy, rates=rates
        )
        if converted is None:
            fx_missing.append(
                {"id": b.get("id"), "name": b.get("name"), "currency": b.get("currency")}
            )
            return 0.0
        return converted

    by_kind: dict[str, dict[str, float | int]] = {}
    totals = {"allocated": 0.0, "actual": 0.0, "committed": 0.0, "remaining": 0.0, "count": 0}
    watch = over = 0
    currencies: set[str] = set()
    seen_missing: set[str] = set()

    for b in budgets:
        k = b.get("kind") or "other"
        slot = by_kind.setdefault(
            k, {"allocated": 0.0, "actual": 0.0, "committed": 0.0, "remaining": 0.0, "count": 0}
        )
        allocated = _amt(b, "allocated")
        actual = _amt(b, "actual") if b.get("actual") is not None else 0.0
        committed = _amt(b, "committed")
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

    # de-dupe fx_missing by id
    unique_missing = []
    for m in fx_missing:
        mid = str(m.get("id") or "")
        if mid and mid in seen_missing:
            continue
        if mid:
            seen_missing.add(mid)
        unique_missing.append(m)

    if not report_ccy:
        report_ccy = next(iter(currencies), "TRY") if currencies else "TRY"

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
        "reporting_currency": report_ccy,
        "currencies": sorted(currencies),
        "fx_missing": unique_missing,
    }


def append_change(
    engine: Engine,
    *,
    tenant_id: str,
    budget_id: str,
    action: str,
    actor: str | None = None,
    field: str | None = None,
    old_value: Any = None,
    new_value: Any = None,
) -> None:
    ensure_budget_tables(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO bi_budget_change_log
                  (tenant_id, budget_id, action, actor, field, old_value, new_value, payload_json, created_at)
                VALUES
                  (:tenant, :bid, :action, :actor, :field, :old, :new, '{}', NOW())
                """
            ),
            {
                "tenant": tenant_id,
                "bid": budget_id,
                "action": action,
                "actor": (actor or "system")[:128],
                "field": field,
                "old": None if old_value is None else str(old_value)[:2000],
                "new": None if new_value is None else str(new_value)[:2000],
            },
        )


def list_change_log(
    engine: Engine, budget_id: str, *, tenant_id: str = "default", limit: int = 50
) -> list[dict[str, Any]]:
    ensure_budget_tables(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT action, actor, field, old_value, new_value, created_at
                FROM bi_budget_change_log
                WHERE tenant_id = :tenant AND budget_id = :bid
                ORDER BY created_at DESC
                LIMIT :lim
                """
            ),
            {"tenant": tenant_id, "bid": budget_id, "lim": limit},
        ).mappings()
        return [
            {
                "action": r["action"],
                "actor": r["actor"],
                "field": r["field"],
                "old_value": r["old_value"],
                "new_value": r["new_value"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]


def upsert_budget(
    engine: Engine,
    body: dict[str, Any],
    *,
    tenant_id: str = "default",
    actor: str | None = None,
) -> dict[str, Any]:
    ensure_budget_tables(engine)
    now = datetime.now(timezone.utc)
    bid = str(body.get("id") or f"bud-{uuid.uuid4().hex[:10]}")
    existing = get_budget(engine, bid, tenant_id=tenant_id)
    if existing:
        if existing.get("locked"):
            raise ValueError("bi_budget_locked")
        if str(existing.get("status") or "").lower() == "closed":
            raise ValueError("bi_budget_closed")

    # Merge payload
    old_payload: dict[str, Any] = {}
    if existing:
        with engine.connect() as conn:
            raw = conn.execute(
                text(
                    "SELECT payload_json FROM bi_budgets WHERE tenant_id = :t AND id = :id"
                ),
                {"t": tenant_id, "id": bid},
            ).scalar()
            try:
                old_payload = json.loads(raw or "{}")
            except Exception:
                old_payload = {}
    payload = {
        **old_payload,
        "budget_code": body.get("budget_code", old_payload.get("budget_code")),
        "match_source": body.get("match_source", old_payload.get("match_source")),
        "breakdown_sql": body.get("breakdown_sql", old_payload.get("breakdown_sql") or ""),
    }

    status = str(body.get("status") or (existing or {}).get("status") or "draft")
    # Don't allow free-form approve via upsert — use /approve
    if existing and status == "approved" and existing.get("status") != "approved":
        status = existing.get("status") or "draft"

    vals = {
        "id": bid,
        "tenant": tenant_id,
        "fy": int(body.get("fiscal_year") or (existing or {}).get("fiscal_year") or now.year),
        "cc": body.get("cost_center") if "cost_center" in body else (existing or {}).get("cost_center") or "",
        "kind": body.get("kind") or (existing or {}).get("kind") or "opex",
        "name": body.get("name") or (existing or {}).get("name") or bid,
        "alloc": float(body.get("allocated") if body.get("allocated") is not None else (existing or {}).get("allocated") or 0),
        "cur": body.get("currency") or (existing or {}).get("currency") or "TRY",
        "comm": float(body.get("committed") if body.get("committed") is not None else (existing or {}).get("committed") or 0),
        "asql": body.get("actuals_sql") if "actuals_sql" in body else (existing or {}).get("actuals_sql") or "",
        "owner": body.get("owner") if "owner" in body else (existing or {}).get("owner") or "",
        "status": status,
        "notes": body.get("notes") if "notes" in body else (existing or {}).get("notes") or "",
        "scenario": body.get("scenario") or (existing or {}).get("scenario") or "base",
        "payload": json.dumps(payload, ensure_ascii=False),
        "now": now,
        "ver": int((existing or {}).get("version") or 1) + (1 if existing else 0),
    }

    with engine.begin() as conn:
        if existing:
            conn.execute(
                text(
                    """
                    UPDATE bi_budgets SET
                      fiscal_year=:fy, cost_center=:cc, kind=:kind, name=:name,
                      allocated=:alloc, currency=:cur, committed=:comm,
                      actuals_sql=:asql, owner=:owner, status=:status, notes=:notes,
                      scenario=:scenario, payload_json=:payload, version=:ver, updated_at=:now
                    WHERE tenant_id=:tenant AND id=:id
                    """
                ),
                vals,
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
                vals,
            )
    if existing:
        append_change(
            engine,
            tenant_id=tenant_id,
            budget_id=bid,
            action="update",
            actor=actor,
            field="name",
            old_value=existing.get("name"),
            new_value=vals["name"],
        )
    row = get_budget(engine, bid, tenant_id=tenant_id)
    if not row:
        raise ValueError("bi_budget_not_found")
    return row


def delete_budget(
    engine: Engine, budget_id: str, *, tenant_id: str = "default"
) -> None:
    ensure_budget_tables(engine)
    existing = get_budget(engine, budget_id, tenant_id=tenant_id)
    if not existing:
        raise ValueError("bi_budget_not_found")
    if existing.get("locked"):
        raise ValueError("bi_budget_locked")
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM bi_budgets WHERE tenant_id = :t AND id = :id"),
            {"t": tenant_id, "id": budget_id},
        )


def patch_budget_fields(
    engine: Engine,
    budget_id: str,
    fields: dict[str, Any],
    *,
    tenant_id: str = "default",
    allow_locked: bool = False,
) -> dict[str, Any]:
    """Low-level field patch (approve/lock/actuals)."""
    ensure_budget_tables(engine)
    existing = get_budget(engine, budget_id, tenant_id=tenant_id)
    if not existing:
        raise ValueError("bi_budget_not_found")
    if existing.get("locked") and not allow_locked and "locked" not in fields:
        raise ValueError("bi_budget_locked")
    now = datetime.now(timezone.utc)
    cols = []
    params: dict[str, Any] = {"t": tenant_id, "id": budget_id, "now": now}
    allowed = {
        "status",
        "locked",
        "approved_at",
        "approved_by",
        "version",
        "actual",
        "actual_error",
        "actuals_at",
        "committed",
        "allocated",
    }
    for key, val in fields.items():
        if key not in allowed:
            continue
        cols.append(f"{key} = :{key}")
        params[key] = val
    if not cols:
        return existing
    cols.append("updated_at = :now")
    with engine.begin() as conn:
        conn.execute(
            text(f"UPDATE bi_budgets SET {', '.join(cols)} WHERE tenant_id = :t AND id = :id"),
            params,
        )
    row = get_budget(engine, budget_id, tenant_id=tenant_id)
    if not row:
        raise ValueError("bi_budget_not_found")
    return row


def sync_from_erp_butce(
    engine: Engine,
    erp_rows: list[dict[str, Any]],
    *,
    tenant_id: str = "default",
    datasource_id: str = "source",
    fiscal_year: Optional[int] = None,
    scenario: str = "base",
) -> dict[str, Any]:
    """Upsert butce_planlari rows into bi_budgets (any budget-capable datasource)."""
    ensure_budget_tables(engine)
    created = updated = skipped = 0
    now = datetime.now(timezone.utc)
    ds = str(datasource_id or "source").strip() or "source"
    scen = (scenario or "base").strip().lower() or "base"
    target_fy = int(fiscal_year) if fiscal_year else None

    with engine.begin() as conn:
        for r in erp_rows:
            fy = int(r.get("mali_yil") or now.year)
            if target_fy is not None and fy != target_fy:
                skipped += 1
                continue
            code = str(r.get("butce_kodu") or r.get("id"))
            bid = f"{ds}-{code}-{fy}"
            new_payload = {
                "budget_code": code,
                "match_source": f"{ds}.butce_planlari",
                "source_row_id": r.get("id"),
                "datasource_id": ds,
            }
            exists = conn.execute(
                text(
                    "SELECT id, status, locked, payload_json FROM bi_budgets WHERE tenant_id = :t AND id = :id"
                ),
                {"t": tenant_id, "id": bid},
            ).mappings().first()
            vals = {
                "id": bid,
                "tenant": tenant_id,
                "fy": fy,
                "cc": r.get("departman_kod") or "",
                "kind": str(r.get("tur") or "opex").lower(),
                "name": r.get("kalem_adi") or code,
                "alloc": float(r.get("planlanan_tutar") or 0),
                "cur": r.get("para_birimi") or "TRY",
                "scenario": scen,
                "now": now,
            }
            if exists:
                if exists.get("locked"):
                    skipped += 1
                    continue
                try:
                    old_p = json.loads(exists.get("payload_json") or "{}")
                except Exception:
                    old_p = {}
                merged = {**old_p, **new_payload}
                vals["payload"] = json.dumps(merged, ensure_ascii=False)
                # Preserve status — do not force approved
                conn.execute(
                    text(
                        """
                        UPDATE bi_budgets SET
                          fiscal_year = :fy, cost_center = :cc, kind = :kind, name = :name,
                          allocated = :alloc, currency = :cur, scenario = :scenario,
                          payload_json = :payload, updated_at = :now
                        WHERE tenant_id = :tenant AND id = :id
                        """
                    ),
                    vals,
                )
                updated += 1
            else:
                vals["payload"] = json.dumps(new_payload, ensure_ascii=False)
                vals["status"] = "approved"
                conn.execute(
                    text(
                        """
                        INSERT INTO bi_budgets (
                          id, tenant_id, fiscal_year, cost_center, kind, name, allocated, currency,
                          committed, actuals_sql, owner, status, notes, scenario, version, locked,
                          payload_json, created_at, updated_at
                        ) VALUES (
                          :id, :tenant, :fy, :cc, :kind, :name, :alloc, :cur,
                          0, '', 'erp-sync', :status, '', :scenario, 1, false,
                          :payload, :now, :now
                        )
                        """
                    ),
                    vals,
                )
                created += 1
    return {
        "ok": True,
        "fiscal_year": target_fy or now.year,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "match_count": created + updated,
        "source": f"{ds}.butce_planlari",
        "warnings": [],
        "refresh": None,
    }
