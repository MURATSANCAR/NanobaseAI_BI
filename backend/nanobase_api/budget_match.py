"""Discover OPEX/CAPEX plan lines and match them to AP spend invoices.

Operator flow: preview_matches → sync_envelopes_from_source → refresh_actuals.
Remaining = allocated − actual − committed (computed in budgets.compute_fields).
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy.engine import Engine

_IDENT = re.compile(r"^[A-Za-z_][\w]*$")
_QUALIFIED = re.compile(r"^[A-Za-z_][\w]*(\.[A-Za-z_][\w]*)?$")

_PLAN_TABLE = re.compile(r"butce|budget|opex|capex", re.I)
_AP_TABLE = re.compile(
    r"alis_fatura|alis_fatur|purchase.?bill|purchase.?invoice|ap[_]?bill|gider|masraf|expense",
    re.I,
)
_AR_SPEND_DENY = re.compile(
    r"^(faturalar|fatura_kalemleri|tahsilatlar|tahsilat|ar[_]?invoice|sales_invoice)$",
    re.I,
)

_KIND_COLS = ("tur", "kind", "budget_type", "butce_turu", "tip")
_AMOUNT_COLS = (
    "planlanan_tutar",
    "allocated",
    "plan_tutar",
    "planlanan",
    "tutar",
    "amount",
    "budget_amount",
)
_NAME_COLS = ("kalem_adi", "name", "ad", "aciklama", "description", "title")
_CODE_COLS = ("butce_kodu", "budget_code", "kalem_kod", "kalem_kodu", "kod", "code")
_CC_COLS = (
    "departman_kod",
    "cost_center",
    "maliyet_merkezi",
    "cc",
    "dept_code",
    "departman",
)
_YEAR_COLS = ("mali_yil", "fiscal_year", "yil", "year", "budget_year")
_SPEND_AMOUNT_COLS = (
    "genel_toplam",
    "toplam_tutar",
    "tutar",
    "amount",
    "total",
    "gross_amount",
)
_SPEND_DATE_COLS = (
    "fatura_tarihi",
    "bill_date",
    "invoice_date",
    "tarih",
    "date",
    "created_at",
)

_KIND_NORM = {
    "opex": "opex",
    "capex": "capex",
    "o": "opex",
    "c": "capex",
    "operating": "opex",
    "capital": "capex",
    "işletme": "opex",
    "yatırım": "capex",
    "yatirim": "capex",
}


def _load_schema(datasource_id: str) -> dict[str, Any]:
    from nanobase_api.schema_api import fetch_schema

    return fetch_schema(datasource_id)


def _safe_ident(name: str) -> str:
    raw = (name or "").strip()
    if not raw or not _IDENT.match(raw):
        raise ValueError("bi_budget_match_invalid_ident")
    return raw


def _safe_table(full: str) -> str:
    raw = (full or "").strip()
    if not raw or not _QUALIFIED.match(raw):
        raise ValueError("bi_budget_match_invalid_ident")
    return raw


def _col_names(table: dict[str, Any]) -> list[str]:
    return [str(c.get("name") or "") for c in (table.get("columns") or []) if c.get("name")]


def _pick_col(cols: list[str], candidates: tuple[str, ...]) -> str | None:
    lower = {c.lower(): c for c in cols if c}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def _table_short(table: dict[str, Any]) -> str:
    full = str(table.get("full_name") or table.get("name") or "")
    return str(table.get("name") or full.split(".")[-1])


def _table_full(table: dict[str, Any]) -> str:
    return str(table.get("full_name") or table.get("name") or "")


def discover_plan_source(schema: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Pick best budget-plan table and map columns."""
    if schema is None:
        raise ValueError("bi_budget_match_schema_required")
    best: dict[str, Any] | None = None
    best_score = 0
    for table in schema.get("tables") or []:
        short = _table_short(table)
        full = _table_full(table)
        if not short or not full:
            continue
        cols = _col_names(table)
        score = 0
        if _PLAN_TABLE.search(short):
            score += 100
        kind_c = _pick_col(cols, _KIND_COLS)
        amt_c = _pick_col(cols, _AMOUNT_COLS)
        name_c = _pick_col(cols, _NAME_COLS)
        if kind_c:
            score += 40
        if amt_c:
            score += 40
        if name_c:
            score += 30
        code_c = _pick_col(cols, _CODE_COLS)
        cc_c = _pick_col(cols, _CC_COLS)
        year_c = _pick_col(cols, _YEAR_COLS)
        if code_c:
            score += 25
        if cc_c:
            score += 15
        if year_c:
            score += 15
        if score < 120 or not amt_c or not name_c:
            continue
        if score > best_score:
            best_score = score
            best = {
                "table": full,
                "table_name": short,
                "score": score,
                "columns": {
                    "kind": kind_c,
                    "amount": amt_c,
                    "name": name_c,
                    "code": code_c,
                    "cost_center": cc_c,
                    "fiscal_year": year_c,
                },
            }
    return best


def discover_spend_source(schema: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Pick best AP / expense table for actuals (never AR sales invoices)."""
    if schema is None:
        raise ValueError("bi_budget_match_schema_required")
    best: dict[str, Any] | None = None
    best_score = 0
    for table in schema.get("tables") or []:
        short = _table_short(table)
        full = _table_full(table)
        if not short or not full:
            continue
        if _AR_SPEND_DENY.match(short):
            continue
        cols = _col_names(table)
        score = 0
        if _AP_TABLE.search(short):
            score += 200
        elif re.search(r"satin_alma|purchase_order|po_", short, re.I):
            # PO is commitment proxy — lower than invoices
            score += 60
        else:
            continue
        amt_c = _pick_col(cols, _SPEND_AMOUNT_COLS)
        date_c = _pick_col(cols, _SPEND_DATE_COLS)
        code_c = _pick_col(cols, _CODE_COLS)
        cc_c = _pick_col(cols, _CC_COLS)
        if not amt_c:
            continue
        score += 40
        if date_c:
            score += 20
        if code_c:
            score += 30
        if cc_c:
            score += 15
        if score > best_score:
            best_score = score
            best = {
                "table": full,
                "table_name": short,
                "score": score,
                "columns": {
                    "amount": amt_c,
                    "date": date_c,
                    "code": code_c,
                    "cost_center": cc_c,
                },
            }
    return best


def _normalize_kind(raw: Any) -> str | None:
    s = str(raw or "").strip().lower()
    if not s:
        return None
    return _KIND_NORM.get(s, s if s in ("opex", "capex", "other") else None)


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    text = str(value).replace("'", "''")
    return f"'{text}'"


def build_actuals_sql(
    *,
    spend: dict[str, Any],
    match_field: str,
    match_value: Any,
    fiscal_year: int,
) -> str:
    """Build a scalar SUM query filtered by match key + fiscal year when possible."""
    table = _safe_table(str(spend["table"]))
    cols = spend.get("columns") or {}
    amount = _safe_ident(str(cols.get("amount") or ""))
    field = _safe_ident(match_field)
    where = [f"{field} = {_sql_literal(match_value)}"]
    date_col = cols.get("date")
    if date_col and fiscal_year:
        d = _safe_ident(str(date_col))
        where.append(f"EXTRACT(YEAR FROM {d}) = {int(fiscal_year)}")
    return (
        f"SELECT COALESCE(SUM({amount}), 0) AS amount FROM {table} "
        f"WHERE {' AND '.join(where)}"
    )


def _resolve_match(
    plan_cols: dict[str, Any],
    spend_cols: dict[str, Any],
    row: dict[str, Any],
) -> tuple[str | None, Any, str]:
    """Return (spend_column, value, confidence)."""
    plan_code = plan_cols.get("code")
    spend_code = spend_cols.get("code")
    if plan_code and spend_code:
        val = row.get(plan_code)
        if val is not None and str(val).strip():
            return str(spend_code), val, "high"

    plan_cc = plan_cols.get("cost_center")
    spend_cc = spend_cols.get("cost_center")
    if plan_cc and spend_cc:
        val = row.get(plan_cc)
        if val is not None and str(val).strip():
            return str(spend_cc), val, "medium"

    return None, None, "none"


async def _qg_execute(
    sql: str,
    *,
    datasource_id: str,
    tenant_id: str | None,
) -> dict[str, Any]:
    from nanobase_api.infrastructure.query_gateway_client import QueryGatewayClient

    client = QueryGatewayClient()
    return await client.execute(sql=sql, datasource_id=datasource_id, tenant_id=tenant_id)


async def _fetch_plan_rows(
    plan: dict[str, Any],
    *,
    fiscal_year: int | None,
    datasource_id: str,
    tenant_id: str | None,
) -> list[dict[str, Any]]:
    table = _safe_table(str(plan["table"]))
    cols = plan["columns"]
    select_cols = [
        _safe_ident(str(cols[k]))
        for k in ("kind", "amount", "name", "code", "cost_center", "fiscal_year")
        if cols.get(k)
    ]
    # de-dupe while preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for c in select_cols:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    sql = f"SELECT {', '.join(ordered)} FROM {table}"
    year_col = cols.get("fiscal_year")
    if year_col and fiscal_year:
        sql += f" WHERE {_safe_ident(str(year_col))} = {int(fiscal_year)}"
    sql += " LIMIT 500"
    result = await _qg_execute(sql, datasource_id=datasource_id, tenant_id=tenant_id)
    rows = result.get("rows") or []
    return [r for r in rows if isinstance(r, dict)]


async def _spend_match_stats(
    spend: dict[str, Any],
    *,
    match_field: str,
    match_value: Any,
    fiscal_year: int,
    datasource_id: str,
    tenant_id: str | None,
) -> dict[str, Any]:
    table = _safe_table(str(spend["table"]))
    cols = spend.get("columns") or {}
    amount = _safe_ident(str(cols.get("amount") or ""))
    field = _safe_ident(match_field)
    where = [f"{field} = {_sql_literal(match_value)}"]
    date_col = cols.get("date")
    if date_col and fiscal_year:
        d = _safe_ident(str(date_col))
        where.append(f"EXTRACT(YEAR FROM {d}) = {int(fiscal_year)}")
    sql = (
        f"SELECT COUNT(*)::bigint AS invoice_count, "
        f"COALESCE(SUM({amount}), 0) AS invoice_total "
        f"FROM {table} WHERE {' AND '.join(where)}"
    )
    try:
        result = await _qg_execute(sql, datasource_id=datasource_id, tenant_id=tenant_id)
        rows = result.get("rows") or []
        row0 = rows[0] if rows else {}
        if not isinstance(row0, dict):
            return {"invoice_count": 0, "invoice_total": 0.0}
        return {
            "invoice_count": int(row0.get("invoice_count") or 0),
            "invoice_total": float(row0.get("invoice_total") or 0),
        }
    except Exception:
        return {"invoice_count": None, "invoice_total": None}


async def preview_matches(
    *,
    fiscal_year: int | None = None,
    datasource_id: str,
    tenant_id: str | None = None,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Discover sources and preview plan-line → invoice matches."""
    from datetime import datetime, timezone

    fy = int(fiscal_year or datetime.now(timezone.utc).year)
    schema = schema or _load_schema(datasource_id)
    plan = discover_plan_source(schema)
    spend = discover_spend_source(schema)
    out: dict[str, Any] = {
        "fiscal_year": fy,
        "plan_source": plan,
        "spend_source": spend,
        "matches": [],
        "warnings": [],
    }
    if not plan:
        out["warnings"].append("bi_budget_match_no_plan_table")
        return out
    if not spend:
        out["warnings"].append("bi_budget_match_no_spend_table")

    try:
        rows = await _fetch_plan_rows(
            plan, fiscal_year=fy, datasource_id=datasource_id, tenant_id=tenant_id
        )
    except Exception as exc:
        out["warnings"].append("bi_budget_match_plan_query_failed")
        out["error"] = str(exc)[:300]
        return out

    plan_cols = plan["columns"]
    spend_cols = (spend or {}).get("columns") or {}
    matches: list[dict[str, Any]] = []
    for row in rows:
        kind_raw = row.get(plan_cols["kind"]) if plan_cols.get("kind") else "opex"
        kind = _normalize_kind(kind_raw) or "opex"
        if kind not in ("opex", "capex", "other"):
            kind = "other"
        name = str(row.get(plan_cols["name"]) or "").strip()
        if not name:
            continue
        try:
            allocated = float(row.get(plan_cols["amount"]) or 0)
        except (TypeError, ValueError):
            allocated = 0.0
        if allocated < 0:
            allocated = 0.0
        cc = ""
        if plan_cols.get("cost_center"):
            cc = str(row.get(plan_cols["cost_center"]) or "").strip()
        code = ""
        if plan_cols.get("code"):
            code = str(row.get(plan_cols["code"]) or "").strip()

        match_field, match_value, confidence = ("", None, "none")
        actuals_sql = ""
        stats: dict[str, Any] = {"invoice_count": None, "invoice_total": None}
        if spend:
            match_field, match_value, confidence = _resolve_match(plan_cols, spend_cols, row)
            if match_field and match_value is not None and confidence != "none":
                actuals_sql = build_actuals_sql(
                    spend=spend,
                    match_field=match_field,
                    match_value=match_value,
                    fiscal_year=fy,
                )
                stats = await _spend_match_stats(
                    spend,
                    match_field=match_field,
                    match_value=match_value,
                    fiscal_year=fy,
                    datasource_id=datasource_id,
                    tenant_id=tenant_id,
                )
            else:
                confidence = "none"

        matches.append(
            {
                "name": name[:160],
                "kind": kind,
                "allocated": allocated,
                "cost_center": cc[:120],
                "budget_code": code[:64],
                "match_field": match_field or None,
                "match_value": None if match_value is None else str(match_value)[:120],
                "match_confidence": confidence,
                "match_source": "auto",
                "actuals_sql": actuals_sql,
                "invoice_count": stats.get("invoice_count"),
                "invoice_total": stats.get("invoice_total"),
                "projected_remaining": (
                    round(allocated - float(stats["invoice_total"] or 0), 2)
                    if stats.get("invoice_total") is not None
                    else None
                ),
            }
        )

    out["matches"] = matches
    if matches and all(m.get("match_confidence") == "none" for m in matches):
        out["warnings"].append("bi_budget_match_no_common_key")
    return out


def _can_overwrite_actuals(existing: dict[str, Any] | None) -> bool:
    if not existing:
        return True
    if str(existing.get("match_source") or "").strip().lower() == "auto":
        return True
    sql = str(existing.get("actuals_sql") or "").strip()
    return not sql


async def sync_envelopes_from_source(
    engine: Engine,
    *,
    fiscal_year: int | None = None,
    tenant_id: str = "default",
    refresh: bool = True,
    scenario: str = "base",
    actor: str | None = None,
    datasource_id: str,
) -> dict[str, Any]:
    """Upsert Nanobase envelopes from discovered plan rows + matched actuals SQL."""
    from nanobase_api.budget_actuals import refresh_one
    from nanobase_api.budgets import list_budgets, upsert_budget

    preview = await preview_matches(
        fiscal_year=fiscal_year,
        datasource_id=datasource_id,
        tenant_id=tenant_id,
    )
    fy = int(preview["fiscal_year"])
    tid = (tenant_id or "default").strip() or "default"
    existing = list_budgets(engine, fiscal_year=fy, scenario=scenario, tenant_id=tid)
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for b in existing:
        key = (
            str(b.get("name") or "").strip().lower(),
            str(b.get("kind") or "").strip().lower(),
            str(b.get("cost_center") or "").strip().lower(),
        )
        by_key[key] = b

    created = 0
    updated = 0
    skipped = 0
    envelopes: list[dict[str, Any]] = []

    for m in preview.get("matches") or []:
        name = str(m.get("name") or "").strip()
        kind = str(m.get("kind") or "opex")
        cc = str(m.get("cost_center") or "").strip()
        key = (name.lower(), kind.lower(), cc.lower())
        prev = by_key.get(key)
        if prev and prev.get("locked"):
            skipped += 1
            continue

        actuals_sql = str(m.get("actuals_sql") or "")
        if prev and not _can_overwrite_actuals(prev):
            actuals_sql = str(prev.get("actuals_sql") or "")
            skipped_sql = True
        else:
            skipped_sql = False

        body: dict[str, Any] = {
            "id": (prev or {}).get("id") or str(uuid.uuid4())[:10],
            "fiscal_year": fy,
            "scenario": scenario,
            "currency": "TRY",
            "status": (prev or {}).get("status") or "draft",
            "name": name,
            "kind": kind if kind in ("opex", "capex", "other") else "opex",
            "cost_center": cc,
            "allocated": float(m.get("allocated") or 0),
            "committed": float((prev or {}).get("committed") or 0),
            "actuals_sql": actuals_sql,
            "notes": (prev or {}).get("notes") or "",
            "match_source": "auto",
            "match_key": m.get("match_field"),
            "match_value": m.get("match_value"),
            "match_confidence": m.get("match_confidence") or "none",
            "budget_code": m.get("budget_code") or "",
        }
        if skipped_sql and prev:
            body["match_confidence"] = prev.get("match_confidence") or body["match_confidence"]

        saved = upsert_budget(engine, body, tenant_id=tid, actor=actor or "budget_match")
        if prev:
            updated += 1
        else:
            created += 1
        envelopes.append(saved)
        by_key[key] = saved

    refresh_result: dict[str, Any] | None = None
    if refresh and envelopes:
        refreshed = 0
        errors = 0
        for env in envelopes:
            if not str(env.get("actuals_sql") or "").strip():
                continue
            row = await refresh_one(
                engine,
                str(env["id"]),
                tenant_id=tid,
                datasource_id=datasource_id,
            )
            refreshed += 1
            if row.get("actual_error"):
                errors += 1
        refresh_result = {"refreshed": refreshed, "errors": errors}

    return {
        "fiscal_year": fy,
        "plan_source": preview.get("plan_source"),
        "spend_source": preview.get("spend_source"),
        "warnings": preview.get("warnings") or [],
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "match_count": len(preview.get("matches") or []),
        "refresh": refresh_result,
        "budgets": envelopes,
    }
