#!/usr/bin/env python3
"""Publish a deterministic semantic metric for a datasource (no code change per metric).

Example — Logo ERP sales revenue on SQL Server:
  python backend/scripts/publish_metric.py --datasource logo --code total_revenue --name "Toplam Ciro" \
    --table dbo.LG_411_01_INVOICE --column NETTOTAL --time-field DATE_ --agg SUM \
    --filter "sales_invoices_only|TRCODE|IN|7,8,9|Yalnızca satış faturaları (TRCODE 7,8,9)" \
    --filter "not_cancelled|CANCELLED|=|0|İptal edilmiş belgeler hariç" \
    --term "Ciro|satış geliri,satis geliri,toplam satış,revenue|Satış faturalarının KDV dahil net toplamı"

Run with the API environment sourced (NANOBASE_META_DSN etc.), then restart the API —
the catalog store hydrates at process start.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _coerce(v: str):
    v = v.strip()
    if v.lstrip("-").isdigit():
        return int(v)
    try:
        return float(v)
    except ValueError:
        return v


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tenant", default=os.environ.get("DEV_TENANT_ID", "default"))
    ap.add_argument("--datasource", required=True)
    ap.add_argument("--code", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--description", default="")
    ap.add_argument("--table", required=True, help="schema.table (or schema.view)")
    ap.add_argument("--column", required=True)
    ap.add_argument("--time-field", required=True, help="date/datetime column on the same table")
    ap.add_argument("--agg", default="SUM", choices=["SUM", "COUNT", "AVG", "MIN", "MAX"])
    ap.add_argument("--null-policy", default="ZERO", choices=["ZERO", "IGNORE", "REJECT"])
    ap.add_argument("--filter", action="append", default=[], help="code|column|op|values(csv)|description  (op: =,!=,IN,NOT_IN,>,<,>=,<=)")
    ap.add_argument("--term", action="append", default=[], help="name|synonyms(csv)|description")
    ap.add_argument("--draft", action="store_true", help="save as DRAFT instead of PUBLISHED")
    args = ap.parse_args()

    from nanobase_api.semantic_catalog.domain.business_term import BusinessTerm
    from nanobase_api.semantic_catalog.domain.filter_rule import FilterExpression, FilterRule
    from nanobase_api.semantic_catalog.domain.metric import Metric, SourceExpression, TimeSemantics
    from nanobase_api.semantic_catalog.domain.status import AssetStatus
    from nanobase_api.semantic_catalog.infrastructure.catalog_store import get_catalog_store

    status = AssetStatus.DRAFT if args.draft else AssetStatus.PUBLISHED
    store = get_catalog_store()
    out = {}

    filter_codes = []
    for spec in args.filter:
        parts = spec.split("|")
        if len(parts) < 4:
            ap.error(f"--filter format: code|column|op|values|description  ({spec})")
        code, column, op, values = parts[0].strip(), parts[1].strip(), parts[2].strip().upper(), parts[3]
        desc = parts[4].strip() if len(parts) > 4 else code
        vals = [_coerce(v) for v in values.split(",") if v.strip() != ""]
        fr = FilterRule(
            id=_id("fr"), tenant_id=args.tenant, datasource_id=args.datasource, code=code, description=desc,
            expression=FilterExpression(field=f"{args.table}.{column}", operator=op, values=vals),
            mandatory=True, status=status,
        )
        store.save_filter(fr)
        filter_codes.append(code)
        out[f"filter:{code}"] = fr.id

    for spec in args.term:
        parts = spec.split("|")
        name = parts[0].strip()
        syns = [x.strip() for x in (parts[1] if len(parts) > 1 else "").split(",") if x.strip()]
        desc = parts[2].strip() if len(parts) > 2 else name
        term = BusinessTerm(id=_id("bt"), tenant_id=args.tenant, datasource_id=args.datasource, name=name, description=desc, synonyms=syns, status=status)
        store.save_term(term)
        out[f"term:{name}"] = term.id

    metric = Metric(
        id=_id("met"), tenant_id=args.tenant, datasource_id=args.datasource, code=args.code, name=args.name,
        description=args.description or args.name, aggregation=args.agg,
        source=SourceExpression(table=args.table, column=args.column),
        default_filter_codes=filter_codes, null_policy=args.null_policy,
        time=TimeSemantics(time_field=f"{args.table}.{args.time_field}"),
        is_financial=False, status=status,
    )
    metric.validate_for_publish(known_filter_codes=set(filter_codes))
    store.save_metric(metric)
    out[f"metric:{args.code}"] = metric.id

    # Show what the compiler will emit for this datasource's dialect.
    from nanobase_api.semantic_catalog.application.services import compile_metric_sql

    try:
        compiled = compile_metric_sql(store, tenant_id=args.tenant, datasource_id=args.datasource, metric_code=args.code, time_grain="month")
        print("compiled (month grain):\n" + compiled["sql"])
    except Exception as e:  # noqa: BLE001
        print(f"compile preview failed: {e}")
    for k, v in out.items():
        print(f"{k} = {v}")
    print(f"status={status.value}. Restart the API so the catalog store reloads.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
