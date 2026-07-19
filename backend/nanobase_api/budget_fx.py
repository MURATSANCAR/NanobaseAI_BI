"""FX conversion for budget reporting currency — never silent 1.0."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from nanobase_api.infrastructure.budget_schema import ensure_budget_tables


def _ccy(value: Any) -> str:
    return str(value or "TRY").strip().upper()[:8] or "TRY"


def convert_amount(
    amount: float,
    *,
    from_currency: str,
    to_currency: str,
    rates: list[dict[str, Any]],
    as_of: datetime | None = None,
) -> float | None:
    """Convert using latest rate with as_of <= target. Missing rate → None."""
    src = _ccy(from_currency)
    dst = _ccy(to_currency)
    if src == dst:
        return float(amount)
    cutoff = as_of or datetime.now(timezone.utc)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)

    best: dict[str, Any] | None = None
    best_at: datetime | None = None
    for row in rates:
        fr = _ccy(row.get("from_currency"))
        to = _ccy(row.get("to_currency"))
        raw_at = row.get("as_of")
        try:
            if isinstance(raw_at, datetime):
                at = raw_at
            else:
                at = datetime.fromisoformat(str(raw_at).replace("Z", "+00:00"))
            if at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if at > cutoff:
            continue
        rate = float(row.get("rate") or 0)
        if rate <= 0:
            continue
        if fr == src and to == dst:
            if best_at is None or at > best_at:
                best, best_at = row, at
        elif fr == dst and to == src:
            inv = {**row, "rate": 1.0 / rate, "from_currency": src, "to_currency": dst}
            if best_at is None or at > best_at:
                best, best_at = inv, at

    if not best:
        return None
    return float(amount) * float(best["rate"])


def list_fx_rates(engine: Engine, *, tenant_id: str = "default") -> list[dict[str, Any]]:
    ensure_budget_tables(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT pk AS id, from_currency, to_currency, rate, as_of
                FROM bi_fx_rates
                WHERE tenant_id = :tenant
                ORDER BY as_of DESC, from_currency, to_currency
                """
            ),
            {"tenant": tenant_id},
        ).mappings()
        out = []
        for r in rows:
            out.append(
                {
                    "id": r["id"],
                    "from_currency": r["from_currency"],
                    "to_currency": r["to_currency"],
                    "rate": float(r["rate"]),
                    "as_of": r["as_of"].isoformat() if r["as_of"] else None,
                }
            )
        return out


def upsert_fx_rate(
    engine: Engine,
    body: dict[str, Any],
    *,
    tenant_id: str = "default",
) -> dict[str, Any]:
    ensure_budget_tables(engine)
    fr = _ccy(body.get("from_currency"))
    to = _ccy(body.get("to_currency"))
    rate = float(body.get("rate") or 0)
    if rate <= 0 or fr == to:
        raise ValueError("bi_fx_rate_invalid")
    raw_as = body.get("as_of")
    if raw_as:
        try:
            as_of = datetime.fromisoformat(str(raw_as).replace("Z", "+00:00"))
        except Exception:
            as_of = datetime.now(timezone.utc)
    else:
        as_of = datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO bi_fx_rates (tenant_id, from_currency, to_currency, rate, as_of, created_at)
                VALUES (:tenant, :fr, :to, :rate, :as_of, NOW())
                ON CONFLICT (tenant_id, from_currency, to_currency, as_of)
                DO UPDATE SET rate = EXCLUDED.rate
                """
            ),
            {"tenant": tenant_id, "fr": fr, "to": to, "rate": rate, "as_of": as_of},
        )
    return {"from_currency": fr, "to_currency": to, "rate": rate, "as_of": as_of.isoformat()}
