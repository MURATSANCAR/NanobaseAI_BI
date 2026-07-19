"""Alerts backed by bi_meta.bi_alerts; check-now via Query Gateway."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from sqlalchemy import text
from sqlalchemy.engine import Engine


def _row_to_alert(r: Any) -> dict[str, Any]:
    try:
        meta = json.loads(r["payload_json"] or "{}")
    except Exception:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return {
        "id": r["id"],
        "title": r["title"],
        "sql": r["sql"],
        "column": r["column_name"],
        "condition": r["condition"] or "gt",
        "threshold": float(r["threshold"] or 0),
        "recipient": r["recipient"],
        "status": r["status"] or "active",
        "last_value": float(r["last_value"]) if r["last_value"] is not None else None,
        "last_triggered_at": r["last_triggered_at"].isoformat() if r["last_triggered_at"] else None,
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        "budget_id": meta.get("budget_id"),
        "budget_fingerprint": meta.get("budget_fingerprint"),
        "budget_threshold_pct": meta.get("budget_threshold_pct"),
        "channels": meta,
    }


def list_alerts(engine: Engine, *, tenant_id: str = "default") -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT * FROM bi_alerts
                WHERE tenant_id = :tenant
                ORDER BY updated_at DESC NULLS LAST, created_at DESC
                """
            ),
            {"tenant": tenant_id},
        ).mappings()
        return [_row_to_alert(r) for r in rows]


def save_alert(engine: Engine, body: dict[str, Any], *, tenant_id: str = "default") -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    aid = str(body.get("id") or f"al-{uuid.uuid4().hex[:10]}")
    payload = dict(body.get("channels") or {})
    for key in ("budget_id", "budget_fingerprint", "budget_threshold_pct"):
        if body.get(key) is not None:
            payload[key] = body[key]
    vals = {
        "id": aid,
        "tenant": tenant_id,
        "title": body.get("title") or aid,
        "sql": body.get("sql") or "SELECT 1 AS c",
        "col": body.get("column") or body.get("column_name") or "c",
        "cond": body.get("condition") or "gt",
        "thr": float(body.get("threshold") or 0),
        "recip": body.get("recipient"),
        "status": body.get("status") or "active",
        "payload": json.dumps(payload, ensure_ascii=False),
        "now": now,
    }
    with engine.begin() as conn:
        exists = conn.execute(text("SELECT id FROM bi_alerts WHERE id = :id"), {"id": aid}).first()
        if exists:
            conn.execute(
                text(
                    """
                    UPDATE bi_alerts SET
                      title=:title, sql=:sql, column_name=:col, condition=:cond,
                      threshold=:thr, recipient=:recip, status=:status,
                      payload_json=:payload, updated_at=:now
                    WHERE id=:id
                    """
                ),
                vals,
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO bi_alerts (
                      id, tenant_id, title, sql, column_name, condition, threshold,
                      recipient, status, payload_json, created_at, updated_at
                    ) VALUES (
                      :id, :tenant, :title, :sql, :col, :cond, :thr,
                      :recip, :status, :payload, :now, :now
                    )
                    """
                ),
                vals,
            )
    return next(a for a in list_alerts(engine, tenant_id=tenant_id) if a["id"] == aid)


def delete_alert(engine: Engine, alert_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM bi_alerts WHERE id = :id"), {"id": alert_id})


def _cmp(value: float, condition: str, threshold: float) -> bool:
    c = (condition or "gt").lower()
    if c in ("gt", ">"):
        return value > threshold
    if c in ("gte", ">="):
        return value >= threshold
    if c in ("lt", "<"):
        return value < threshold
    if c in ("lte", "<="):
        return value <= threshold
    if c in ("eq", "=", "=="):
        return value == threshold
    return value > threshold


async def check_alerts_now(
    engine: Engine,
    *,
    gateway_base: str,
    datasource_id: str,
    tenant_id: str = "default",
) -> dict[str, Any]:
    alerts = [a for a in list_alerts(engine, tenant_id=tenant_id) if a.get("status") == "active"]
    checked = triggered = 0
    errors: list[str] = []
    now = datetime.now(timezone.utc)
    async with httpx.AsyncClient(timeout=30.0) as client:
        for a in alerts:
            checked += 1
            try:
                r = await client.post(
                    f"{gateway_base.rstrip('/')}/api/v1/query/execute",
                    json={"datasource_id": datasource_id, "sql": a["sql"]},
                )
                data = r.json()
                if r.status_code >= 400 or not data.get("ok"):
                    errors.append(f"{a['id']}: {data.get('detail') or data.get('error') or r.status_code}")
                    continue
                rows = data.get("rows") or []
                if not rows:
                    continue
                col = a.get("column") or "c"
                row0 = rows[0]
                raw = row0.get(col)
                if raw is None and row0:
                    raw = next(iter(row0.values()))
                value = float(raw)
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            """
                            UPDATE bi_alerts
                            SET last_value = :v, updated_at = :now,
                                last_triggered_at = CASE WHEN :trig THEN :now ELSE last_triggered_at END
                            WHERE id = :id
                            """
                        ),
                        {
                            "v": value,
                            "now": now,
                            "trig": _cmp(value, a.get("condition") or "gt", float(a.get("threshold") or 0)),
                            "id": a["id"],
                        },
                    )
                if _cmp(value, a.get("condition") or "gt", float(a.get("threshold") or 0)):
                    triggered += 1
            except Exception as e:
                errors.append(f"{a['id']}: {e}")
    return {"checked": checked, "triggered": triggered, "errors": errors}
