from __future__ import annotations

from typing import Any

from config import SAMPLE_ALLOWLIST, IndexerConfig
from models import TableMeta
from scanner.metadata import connect


def apply_controlled_profiling(cfg: IndexerConfig, tables: list[TableMeta]) -> list[TableMeta]:
    """COUNT / date range / status distribution — never SELECT *."""
    if cfg.skip_profile:
        return tables
    conn = connect(cfg)
    try:
        conn.set_session(readonly=True, autocommit=True)
        cur = conn.cursor()
        for t in tables:
            if t.table_type != "BASE TABLE":
                continue
            schema, name = t.schema_name, t.table_name
            # COUNT(*)
            try:
                cur.execute(f'SELECT COUNT(*) FROM "{schema}"."{name}"')
                t.row_count = int(cur.fetchone()[0])
            except Exception:
                conn.rollback()
                t.row_count = None

            # MIN/MAX date columns
            date_cols = [
                c.column_name
                for c in t.columns
                if c.data_type in ("date", "timestamp without time zone", "timestamp with time zone")
                or c.column_name.lower().endswith("_date")
                or c.column_name.lower().endswith("date")
            ]
            if date_cols:
                col = date_cols[0]
                try:
                    cur.execute(
                        f'SELECT MIN("{col}")::text, MAX("{col}")::text '
                        f'FROM "{schema}"."{name}"'
                    )
                    row = cur.fetchone()
                    if row:
                        t.date_min, t.date_max = row[0], row[1]
                except Exception:
                    conn.rollback()

            # status-like GROUP BY
            status_col = next(
                (
                    c.column_name
                    for c in t.columns
                    if c.column_name.lower() in SAMPLE_ALLOWLIST
                    and (
                        "status" in c.column_name.lower()
                        or c.column_name.lower() in ("segment", "category", "currency")
                    )
                ),
                None,
            )
            if status_col:
                try:
                    cur.execute(
                        f'SELECT "{status_col}"::text AS status, COUNT(*) AS n '
                        f'FROM "{schema}"."{name}" '
                        f'GROUP BY "{status_col}" '
                        f"ORDER BY COUNT(*) DESC LIMIT 20"
                    )
                    t.status_dist = [
                        {"status": r[0], "count": int(r[1])} for r in cur.fetchall() if r[0] is not None
                    ]
                except Exception:
                    conn.rollback()
        cur.close()
    finally:
        conn.close()
    return tables
