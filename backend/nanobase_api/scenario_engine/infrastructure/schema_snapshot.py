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


def snapshot_from_pg(dsn: str, *, schemas: list[str] | None = None, datasource_id: str = "default") -> SchemaSnapshot:
    """Build SchemaSnapshot from a live Postgres information_schema."""
    import psycopg2
    import psycopg2.extras

    schemas = schemas or ["analytics", "public", "reporting"]
    pg = dsn.replace("postgresql+psycopg2://", "postgresql://")
    tables: list[TableSnap] = []
    fks: list[dict[str, str]] = []
    conn = psycopg2.connect(pg)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema = ANY(%s)
                ORDER BY 1, 2
                """,
                (schemas,),
            )
            for t in cur.fetchall():
                schema, name = t["table_schema"], t["table_name"]
                cur.execute(
                    """
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (schema, name),
                )
                cols = [
                    ColumnSnap(
                        name=c["column_name"],
                        data_type=c["data_type"],
                        nullable=c["is_nullable"] == "YES",
                    )
                    for c in cur.fetchall()
                ]
                # PKs
                cur.execute(
                    """
                    SELECT a.attname
                    FROM pg_index i
                    JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                    JOIN pg_class c ON c.oid = i.indrelid
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE i.indisprimary AND n.nspname = %s AND c.relname = %s
                    """,
                    (schema, name),
                )
                pks = {r["attname"] for r in cur.fetchall()}
                for col in cols:
                    if col.name in pks:
                        col.is_pk = True
                tables.append(TableSnap(schema=schema, name=name, columns=cols))

            cur.execute(
                """
                SELECT
                  nsp.nspname AS from_schema,
                  rel.relname AS from_table,
                  att.attname AS from_column,
                  fnsp.nspname AS to_schema,
                  frel.relname AS to_table,
                  fatt.attname AS to_column
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
                JOIN pg_class frel ON frel.oid = con.confrelid
                JOIN pg_namespace fnsp ON fnsp.oid = frel.relnamespace
                JOIN unnest(con.conkey) WITH ORDINALITY AS ck(attnum, ord) ON true
                JOIN unnest(con.confkey) WITH ORDINALITY AS fk(attnum, ord) ON fk.ord = ck.ord
                JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = ck.attnum
                JOIN pg_attribute fatt ON fatt.attrelid = con.confrelid AND fatt.attnum = fk.attnum
                WHERE con.contype = 'f'
                  AND nsp.nspname = ANY(%s)
                """,
                (schemas,),
            )
            for r in cur.fetchall():
                fks.append(
                    {
                        "from": f"{r['from_schema']}.{r['from_table']}.{r['from_column']}",
                        "to": f"{r['to_schema']}.{r['to_table']}.{r['to_column']}",
                    }
                )
                # mark FK columns
                fqn = f"{r['from_schema']}.{r['from_table']}"
                for t in tables:
                    if t.fqn == fqn:
                        for c in t.columns:
                            if c.name == r["from_column"]:
                                c.is_fk = True
                                c.fk_ref = f"{r['to_schema']}.{r['to_table']}.{r['to_column']}"
    finally:
        conn.close()
    return SchemaSnapshot(tables=tables, foreign_keys=fks, datasource_id=datasource_id)


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
