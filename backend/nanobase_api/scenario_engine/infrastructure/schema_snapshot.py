"""Immutable schema snapshot fingerprinting."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ColumnSnap:
    name: str
    data_type: str
    nullable: bool = True
    is_pk: bool = False
    is_fk: bool = False
    fk_ref: str | None = None


@dataclass
class TableSnap:
    schema: str
    name: str
    columns: list[ColumnSnap] = field(default_factory=list)

    @property
    def fqn(self) -> str:
        return f"{self.schema}.{self.name}"


@dataclass
class SchemaSnapshot:
    tables: list[TableSnap]
    foreign_keys: list[dict[str, str]] = field(default_factory=list)
    datasource_id: str = "default"

    def fingerprint(self) -> str:
        payload = {
            "tables": [
                {
                    "fqn": t.fqn,
                    "columns": [
                        {
                            "name": c.name,
                            "type": c.data_type,
                            "nullable": c.nullable,
                            "pk": c.is_pk,
                            "fk": c.is_fk,
                            "fk_ref": c.fk_ref,
                        }
                        for c in sorted(t.columns, key=lambda x: x.name)
                    ],
                }
                for t in sorted(self.tables, key=lambda x: x.fqn)
            ],
            "fks": sorted(self.foreign_keys, key=lambda x: json.dumps(x, sort_keys=True)),
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def table(self, fqn: str) -> TableSnap | None:
        for t in self.tables:
            if t.fqn == fqn or t.name == fqn:
                return t
        return None


def invoice_analytics_snapshot() -> SchemaSnapshot:
    """Canonical vertical-slice snapshot matching analytics.invoices rich schema."""
    invoices = TableSnap(
        schema="analytics",
        name="invoices",
        columns=[
            ColumnSnap("invoice_id", "integer", nullable=False, is_pk=True),
            ColumnSnap("order_id", "integer", nullable=False, is_fk=True, fk_ref="analytics.sales_orders.order_id"),
            ColumnSnap("invoice_date", "date", nullable=False),
            ColumnSnap("due_date", "date", nullable=False),
            ColumnSnap("currency", "text", nullable=False),
            ColumnSnap("gross_amount", "numeric", nullable=False),
            ColumnSnap("remaining_amount", "numeric", nullable=False),
            ColumnSnap("status", "text", nullable=False),
        ],
    )
    orders = TableSnap(
        schema="analytics",
        name="sales_orders",
        columns=[
            ColumnSnap("order_id", "integer", nullable=False, is_pk=True),
            ColumnSnap("customer_id", "integer", nullable=False, is_fk=True, fk_ref="analytics.customers.customer_id"),
            ColumnSnap("branch_id", "integer", nullable=True, is_fk=True),
            ColumnSnap("order_date", "date", nullable=False),
            ColumnSnap("status", "text", nullable=False),
            ColumnSnap("currency", "text", nullable=False),
        ],
    )
    customers = TableSnap(
        schema="analytics",
        name="customers",
        columns=[
            ColumnSnap("customer_id", "integer", nullable=False, is_pk=True),
            ColumnSnap("customer_name", "text", nullable=False),
        ],
    )
    addresses = TableSnap(
        schema="analytics",
        name="customer_addresses",
        columns=[
            ColumnSnap("address_id", "integer", nullable=False, is_pk=True),
            ColumnSnap("customer_id", "integer", nullable=False, is_fk=True, fk_ref="analytics.customers.customer_id"),
            ColumnSnap("city", "text", nullable=False),
            ColumnSnap("line1", "text", nullable=False),
            ColumnSnap("is_primary", "boolean", nullable=False),
        ],
    )
    return SchemaSnapshot(
        tables=[invoices, orders, customers, addresses],
        foreign_keys=[
            {
                "from": "analytics.invoices.order_id",
                "to": "analytics.sales_orders.order_id",
            },
            {
                "from": "analytics.sales_orders.customer_id",
                "to": "analytics.customers.customer_id",
            },
            {
                "from": "analytics.customer_addresses.customer_id",
                "to": "analytics.customers.customer_id",
            },
        ],
        datasource_id="bi_reporting",
    )


def snapshot_from_dict(raw: dict[str, Any]) -> SchemaSnapshot:
    tables: list[TableSnap] = []
    for tname, tmeta in (raw.get("tables") or {}).items():
        parts = tname.split(".", 1)
        schema, name = (parts[0], parts[1]) if len(parts) == 2 else ("public", parts[0])
        cols = []
        for cname, cmeta in (tmeta.get("columns") or {}).items():
            if isinstance(cmeta, dict):
                cols.append(
                    ColumnSnap(
                        name=cname,
                        data_type=str(cmeta.get("type") or "text"),
                        nullable=bool(cmeta.get("nullable", True)),
                        is_pk=bool(cmeta.get("pk") or cmeta.get("is_pk")),
                        is_fk=bool(cmeta.get("fk") or cmeta.get("is_fk")),
                        fk_ref=cmeta.get("fk_ref"),
                    )
                )
            else:
                cols.append(ColumnSnap(name=cname, data_type=str(cmeta)))
        tables.append(TableSnap(schema=schema, name=name, columns=cols))
    return SchemaSnapshot(
        tables=tables,
        foreign_keys=list(raw.get("foreign_keys") or []),
        datasource_id=str(raw.get("datasource_id") or "default"),
    )
