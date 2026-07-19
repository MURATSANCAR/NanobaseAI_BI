from __future__ import annotations

import psycopg2
import psycopg2.extras

from config import (
    COLUMN_DESCRIPTIONS,
    SAMPLE_ALLOWLIST,
    SAMPLE_BLOCKLIST,
    TABLE_DESCRIPTIONS,
    IndexerConfig,
)
from models import ColumnMeta, ForeignKey, RelationshipMeta, TableMeta


def connect(cfg: IndexerConfig):
    kw = cfg.pg_connect_kwargs()
    return psycopg2.connect(**kw)


def _comment(cur, schema: str, table: str, column: str | None = None) -> str:
    if column:
        cur.execute(
            """
            SELECT col_description(c.oid, a.attnum)
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid
            WHERE n.nspname = %s AND c.relname = %s AND a.attname = %s AND a.attnum > 0
            """,
            (schema, table, column),
        )
    else:
        cur.execute(
            """
            SELECT obj_description(c.oid)
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = %s AND c.relname = %s
            """,
            (schema, table),
        )
    row = cur.fetchone()
    if not row:
        return ""
    val = row[0] if not isinstance(row, dict) else next(iter(row.values()))
    return (val or "").strip()


def _table_desc(name: str, pg_comment: str) -> str:
    if pg_comment:
        return pg_comment
    return TABLE_DESCRIPTIONS.get(name.lower(), f"{name} tablosu / görünümü")


def _col_desc(table: str, column: str, pg_comment: str) -> str:
    if pg_comment:
        return pg_comment
    return COLUMN_DESCRIPTIONS.get((table.lower(), column.lower()), "")


def _may_sample(column_name: str) -> bool:
    c = column_name.lower()
    if c in SAMPLE_BLOCKLIST:
        return False
    if c in SAMPLE_ALLOWLIST:
        return True
    # suffix heuristics for status-like enums
    return c.endswith("_status") or c.endswith("_type") or c.endswith("_code")


def scan_metadata(cfg: IndexerConfig) -> tuple[list[TableMeta], list[RelationshipMeta]]:
    """Extract tables, columns, PK/FK from information_schema (read-only)."""
    conn = connect(cfg)
    tables: list[TableMeta] = []
    relationships: list[RelationshipMeta] = []
    try:
        conn.set_session(readonly=True, autocommit=True)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        schemas = list(cfg.schemas)
        cur.execute(
            """
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = ANY(%s)
              AND table_type IN ('BASE TABLE', 'VIEW')
            ORDER BY table_schema, table_name
            LIMIT %s
            """,
            (schemas, cfg.max_tables),
        )
        raw_tables = list(cur.fetchall())

        for t in raw_tables:
            schema, name, ttype = t["table_schema"], t["table_name"], t["table_type"]
            pg_t_comment = _comment(cur, schema, name, None)
            cur.execute(
                """
                SELECT column_name, data_type, is_nullable, ordinal_position
                FROM information_schema.columns
                WHERE table_schema=%s AND table_name=%s
                ORDER BY ordinal_position
                """,
                (schema, name),
            )
            cols_raw = list(cur.fetchall())

            cur.execute(
                """
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                WHERE tc.table_schema=%s AND tc.table_name=%s
                  AND tc.constraint_type='PRIMARY KEY'
                ORDER BY kcu.ordinal_position
                """,
                (schema, name),
            )
            pks = [r["column_name"] for r in cur.fetchall()]

            cur.execute(
                """
                SELECT
                  a.attname AS column_name,
                  nf.nspname AS foreign_table_schema,
                  clf.relname AS foreign_table_name,
                  af.attname AS foreign_column_name
                FROM pg_constraint c
                JOIN pg_class cl ON cl.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = cl.relnamespace
                JOIN LATERAL unnest(c.conkey, c.confkey) AS x(attnum, fattnum) ON true
                JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = x.attnum
                JOIN pg_class clf ON clf.oid = c.confrelid
                JOIN pg_namespace nf ON nf.oid = clf.relnamespace
                JOIN pg_attribute af ON af.attrelid = c.confrelid AND af.attnum = x.fattnum
                WHERE c.contype = 'f'
                  AND n.nspname = %s AND cl.relname = %s
                """,
                (schema, name),
            )
            fks: list[ForeignKey] = []
            for r in cur.fetchall():
                fk = ForeignKey(
                    column=r["column_name"],
                    target_schema=r["foreign_table_schema"],
                    target_table=r["foreign_table_name"],
                    target_column=r["foreign_column_name"],
                )
                fks.append(fk)
                relationships.append(
                    RelationshipMeta(
                        from_schema=schema,
                        from_table=name,
                        from_column=fk.column,
                        to_schema=fk.target_schema,
                        to_table=fk.target_table,
                        to_column=fk.target_column,
                        relationship_type="many-to-one",
                    )
                )

            columns: list[ColumnMeta] = []
            for c in cols_raw:
                cname = c["column_name"]
                pg_c = _comment(cur, schema, name, cname)
                samples: list[str] = []
                if (
                    not cfg.skip_samples
                    and ttype == "BASE TABLE"
                    and _may_sample(cname)
                ):
                    samples = _safe_samples(cur, conn, schema, name, cname)

                columns.append(
                    ColumnMeta(
                        schema_name=schema,
                        table_name=name,
                        column_name=cname,
                        data_type=c["data_type"],
                        nullable=str(c["is_nullable"]).upper() == "YES",
                        ordinal=int(c["ordinal_position"]),
                        is_pk=cname in pks,
                        description=_col_desc(name, cname, pg_c),
                        samples=samples,
                    )
                )

            tables.append(
                TableMeta(
                    schema_name=schema,
                    table_name=name,
                    table_type=ttype,
                    description=_table_desc(name, pg_t_comment),
                    primary_key=pks,
                    foreign_keys=fks,
                    columns=columns,
                )
            )
        cur.close()
    finally:
        conn.close()
    return tables, relationships


def _safe_samples(cur, conn, schema: str, table: str, column: str, limit: int = 8) -> list[str]:
    """DISTINCT samples — never SELECT *."""
    try:
        cur.execute(
            f'SELECT DISTINCT "{column}"::text AS v '
            f'FROM "{schema}"."{table}" '
            f'WHERE "{column}" IS NOT NULL '
            f"LIMIT %s",
            (limit,),
        )
        return [str(r["v"])[:80] for r in cur.fetchall()]
    except Exception:
        conn.rollback()
        return []
