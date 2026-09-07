"""Database connectors for profiling and execution. All read-only.

MSSQLConnector   — pyodbc/FreeTDS (SQL Server sources)
PostgresConnector— psycopg2 (nanobase datasources)
SQLiteConnector  — tests / local fixtures
ModelFileConnector — offline: a model export (models/*/metadata.yml + relationships.yml, optionally an enum
                   probe JSON); lets the whole pipeline run before a database connection exists
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
import logging
from typing import Any, Iterable, Optional, Protocol

import yaml


log = logging.getLogger(__name__)


class Connector(Protocol):
    dialect: str
    default_schema: str
    supports_execution: bool

    def list_tables(self, schema: str, like: Optional[str] = None) -> list[tuple[str, str]]: ...
    def columns(self, schema: str, table: str) -> list[dict[str, Any]]: ...
    def primary_keys(self, schema: str, table: str) -> list[str]: ...
    def foreign_keys(self, schema: str) -> list[dict[str, str]]: ...
    def top_values(self, schema: str, table: str, column: str, limit: int) -> list[tuple[str, int]]: ...
    def sample_rows(self, schema: str, table: str, limit: int) -> list[dict[str, Any]]: ...
    def row_count(self, schema: str, table: str) -> Optional[int]: ...
    def row_counts(self, schema: str) -> dict[str, int]: ...
    def descriptions(self, schema: str) -> dict[tuple[str, Optional[str]], str]: ...
    def execute(self, sql: str, limit: int) -> tuple[list[dict[str, str]], list[dict[str, Any]], bool]: ...
    def dry_run(self, sql: str) -> None: ...
    def close(self) -> None: ...


def _norm(v: Any) -> Any:
    import datetime as dt
    import decimal
    import math

    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (bytes, bytearray)):
        return v.decode(errors="replace")
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


class _DbApiBase:
    dialect = "generic"
    default_schema = ""
    supports_execution = True
    quote_l, quote_r = '"', '"'
    # A query that never returns must not hold the deploy or the service hostage: a customer database can
    # always be slow, blocked, or restarted under us.
    query_timeout = int(os.environ.get("SEMANTIC_QUERY_TIMEOUT_SEC", "120"))

    def row_counts(self, schema: str) -> dict[str, int]:
        """Row count for every table in the schema, in one query where the engine can do it.

        Deciding which tables matter needs all the counts before profiling any of them, and asking
        table by table is a query storm against a live source.
        """
        return {}

    def descriptions(self, schema: str) -> dict[tuple[str, Optional[str]], str]:
        """What the people who built this database wrote about it: table and column comments.

        Every engine keeps them somewhere different and none of them is optional to support — a
        deployment where someone documented the schema in the database is the deployment where the
        catalog has the most to learn. The key is (table, column) with column None for the table itself;
        an engine with no comment store returns nothing rather than pretending.
        """
        return {}

    def __init__(self) -> None:
        self._conn = None

    def conn(self):  # pragma: no cover - overridden
        raise NotImplementedError

    def q(self, ident: str) -> str:
        return f"{self.quote_l}{ident}{self.quote_r}"

    def _rows(self, sql: str, params: tuple = ()) -> tuple[list[str], list[tuple]]:
        cur = self.conn().cursor()
        try:
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchall()
            return cols, rows
        except Exception:
            self._drop_if_broken()
            raise
        finally:
            try:
                cur.close()
            except Exception:  # noqa: BLE001
                pass

    def execute(self, sql: str, limit: int) -> tuple[list[dict[str, str]], list[dict[str, Any]], bool]:
        cur = self.conn().cursor()
        try:
            cur.execute(sql)
            cols = [{"name": d[0], "type": str(d[1].__name__ if hasattr(d[1], "__name__") else d[1])} for d in (cur.description or [])]
            raw = cur.fetchmany(limit + 1)
        except Exception:
            self._drop_if_broken()
            raise
        finally:
            try:
                cur.close()
            except Exception:  # noqa: BLE001
                pass
        truncated = len(raw) > limit
        rows = [{c["name"]: _norm(v) for c, v in zip(cols, r)} for r in raw[:limit]]
        return cols, rows, truncated

    def _drop_if_broken(self) -> None:
        """Forget a connection the driver can no longer use, so the next call reconnects instead of
        failing forever after a network blip or a database restart."""
        conn = self._conn
        if conn is None:
            return
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
        except Exception:  # noqa: BLE001
            log.warning("database connection is broken — dropping it so the next call reconnects")
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            self._conn = None

    def sample_rows(self, schema: str, table: str, limit: int = 20) -> list[dict[str, Any]]:
        """A handful of real rows — the cheapest way to see what a column actually holds.
        One query per table; values are inspected in memory and never stored verbatim."""
        target = f"{self.q(schema)}.{self.q(table)}" if schema and self.dialect != "sqlite" else self.q(table)
        sql = f"SELECT TOP {int(limit)} * FROM {target}" if self.dialect == "tsql" else f"SELECT * FROM {target} LIMIT {int(limit)}"
        cols, rows, _ = self.execute(sql, limit)
        return rows

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass
            self._conn = None


class MSSQLConnector(_DbApiBase):
    dialect = "tsql"
    default_schema = "dbo"
    quote_l, quote_r = "[", "]"

    def __init__(self, cfg: dict[str, Any]):
        super().__init__()
        self.cfg = cfg

    def conn(self):
        if self._conn is None:
            import pyodbc  # lazy: only on the server

            c = self.cfg
            cs = "DRIVER=%s;SERVER=%s,%s;DATABASE=%s;UID=%s;PWD=%s;TDS_Version=%s" % (
                c.get("driver", "FreeTDS"), c["host"], c.get("port", 1433), c["database"], c["user"], c["password"], c.get("tds_version", "7.4"))
            for k, v in (c.get("kwargs") or {}).items():
                cs += f";{k}={v}"
            self._conn = pyodbc.connect(cs, timeout=30, readonly=True, autocommit=True)
            self._conn.timeout = self.query_timeout        # per-query timeout, not just login
            try:
                self._conn.setdecoding(pyodbc.SQL_CHAR, encoding="utf-8")
                self._conn.setdecoding(pyodbc.SQL_WCHAR, encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
        return self._conn

    def list_tables(self, schema: str, like: Optional[str] = None) -> list[tuple[str, str]]:
        sql = "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE IN ('BASE TABLE','VIEW') AND TABLE_SCHEMA = ?"
        params: tuple = (schema,)
        if like:
            sql += " AND TABLE_NAME LIKE ?"
            params = (schema, like)
        _, rows = self._rows(sql + " ORDER BY TABLE_NAME", params)
        return [(r[0], r[1]) for r in rows]

    def columns(self, schema: str, table: str) -> list[dict[str, Any]]:
        _, rows = self._rows(
            "SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=? AND TABLE_NAME=? ORDER BY ORDINAL_POSITION",
            (schema, table),
        )
        return [{"name": r[0], "data_type": (r[1] or "") + (f"({r[2]})" if r[2] and int(r[2]) > 0 else ""), "nullable": str(r[3]).upper() == "YES"} for r in rows]

    def primary_keys(self, schema: str, table: str) -> list[str]:
        _, rows = self._rows(
            """SELECT kcu.COLUMN_NAME FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
               JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu ON kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME AND kcu.TABLE_SCHEMA = tc.TABLE_SCHEMA
               WHERE tc.CONSTRAINT_TYPE='PRIMARY KEY' AND tc.TABLE_SCHEMA=? AND tc.TABLE_NAME=? ORDER BY kcu.ORDINAL_POSITION""",
            (schema, table),
        )
        if keys := [r[0] for r in rows]:
            return keys
        # Logo enforces its keys in the application, so the query above returns nothing for every
        # table it owns. The dictionary's unique indexes name the key the database keeps silent.
        from semantic_layer.profiler import logo_dictionary

        return logo_dictionary.primary_key(table, [c["name"] for c in self.columns(schema, table)])

    def foreign_keys(self, schema: str) -> list[dict[str, str]]:
        try:
            _, rows = self._rows(
                """SELECT tc.TABLE_NAME, kcu.COLUMN_NAME, ccu.TABLE_NAME, ccu.COLUMN_NAME FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                   JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu ON kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME AND kcu.TABLE_SCHEMA = tc.TABLE_SCHEMA
                   JOIN INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE ccu ON ccu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
                   WHERE tc.CONSTRAINT_TYPE='FOREIGN KEY' AND tc.TABLE_SCHEMA=?""",
                (schema,),
            )
        except Exception:  # noqa: BLE001
            rows = []
        declared = [{"table": r[0], "column": r[1], "ref_table": r[2], "ref_column": r[3]} for r in rows]
        # Logo declares no foreign keys at all, so the honest answer above is an empty graph and every
        # join has to be guessed from column names. The vendor's dictionary states the graph outright.
        # What the database itself declares always wins; the dictionary only fills what is missing.
        extra = self._dictionary_foreign_keys(schema)
        if not extra:
            return declared
        have = {(fk["table"].upper(), fk["column"].upper()) for fk in declared}
        return declared + [fk for fk in extra if (fk["table"].upper(), fk["column"].upper()) not in have]

    def _table_names(self, schema: str) -> list[str]:
        """The scanned table names, read once per schema — both dictionary lookups need them."""
        key = schema or self.default_schema
        cached = getattr(self, "_names_cache", None)
        if cached is None:
            cached = self._names_cache = {}
        if key not in cached:
            try:
                cached[key] = [t for _, t in self.list_tables(key)]
            except Exception as e:  # noqa: BLE001
                log.debug("table listing for the data dictionary failed: %s", e)
                cached[key] = []
        return cached[key]

    def _dictionary_foreign_keys(self, schema: str) -> list[dict[str, str]]:
        from semantic_layer.profiler import logo_dictionary

        names = self._table_names(schema)
        if not logo_dictionary.is_logo_schema(names):
            return []
        links = logo_dictionary.foreign_keys(names)
        if links:
            log.info("Logo data dictionary supplied %d joins the database does not declare", len(links))
        return links

    def row_counts(self, schema: str) -> dict[str, int]:
        try:
            _, rows = self._rows(
                """SELECT t.name, SUM(p.rows) FROM sys.partitions p
                   JOIN sys.tables t ON t.object_id = p.object_id
                   JOIN sys.schemas s ON s.schema_id = t.schema_id
                   WHERE s.name = ? AND p.index_id IN (0, 1) GROUP BY t.name""",
                (schema or self.default_schema,),
            )
        except Exception as e:  # noqa: BLE001
            log.debug("bulk row counts unavailable: %s", e)
            return {}
        return {str(r[0]): int(r[1] or 0) for r in rows}

    def descriptions(self, schema: str) -> dict[tuple[str, Optional[str]], str]:
        """SQL Server keeps them as the MS_Description extended property. One query for the schema."""
        try:
            _, rows = self._rows(
                """SELECT t.name AS tbl, c.name AS col, CAST(ep.value AS NVARCHAR(4000)) AS descr
                   FROM sys.extended_properties ep
                   JOIN sys.tables t ON t.object_id = ep.major_id
                   JOIN sys.schemas s ON s.schema_id = t.schema_id
                   LEFT JOIN sys.columns c ON c.object_id = ep.major_id AND c.column_id = ep.minor_id
                   WHERE ep.class = 1 AND ep.name = ? AND s.name = ?""",
                ("MS_Description", schema or self.default_schema),
            )
        except Exception as e:  # noqa: BLE001
            log.debug("extended properties unavailable: %s", e)
            rows = []
        written = {(str(r[0]), str(r[1]) if r[1] is not None else None): str(r[2]) for r in rows if r[2]}
        # Logo writes no extended properties, so the query above returns nothing on the source that
        # needs descriptions most: 8.900 columns named CLIENTREF, TRCODE, SIGN and no statement
        # anywhere in the database about what they hold. The dictionary answers for them — and
        # anything a person actually wrote into this database still takes precedence.
        from semantic_layer.profiler import logo_dictionary

        names = self._table_names(schema)
        if not logo_dictionary.is_logo_schema(names):
            return written
        merged = logo_dictionary.descriptions(names)
        merged.update(written)
        log.info("Logo data dictionary described %d tables/columns the database leaves unannotated",
                 len(merged) - len(written))
        return merged

    def top_values(self, schema: str, table: str, column: str, limit: int) -> list[tuple[str, int]]:
        sql = f"SELECT TOP {int(limit)} {self.q(column)} AS v, COUNT_BIG(*) AS n FROM {self.q(schema)}.{self.q(table)} GROUP BY {self.q(column)} ORDER BY n DESC"
        _, rows = self._rows(sql)
        return [(str(_norm(r[0])), int(r[1])) for r in rows]

    def row_count(self, schema: str, table: str) -> Optional[int]:
        try:
            _, rows = self._rows(
                "SELECT SUM(p.rows) FROM sys.partitions p JOIN sys.tables t ON t.object_id = p.object_id JOIN sys.schemas s ON s.schema_id = t.schema_id WHERE s.name=? AND t.name=? AND p.index_id IN (0,1)",
                (schema, table),
            )
            return int(rows[0][0]) if rows and rows[0][0] is not None else None
        except Exception:  # noqa: BLE001
            return None

    def dry_run(self, sql: str) -> None:
        """Name/type resolution without execution (sp_describe_first_result_set)."""
        cur = self.conn().cursor()
        try:
            cur.execute("EXEC sp_describe_first_result_set @tsql = ?", (sql,))
            cur.fetchall()
        finally:
            cur.close()


class PostgresConnector(_DbApiBase):
    dialect = "postgres"
    default_schema = "public"

    def __init__(self, cfg: dict[str, Any]):
        super().__init__()
        self.cfg = cfg

    def conn(self):
        if self._conn is None:
            import psycopg2

            c = self.cfg
            pw = c.get("password") or ""
            if not pw and c.get("password_file"):
                pw = Path(c["password_file"]).read_text(encoding="utf-8").strip()
            self._conn = psycopg2.connect(host=c["host"], port=int(c.get("port") or 5432), dbname=c.get("database") or c.get("dbname"), user=c["user"], password=pw, sslmode=c.get("sslmode") or "prefer", connect_timeout=10)
            self._conn.set_session(readonly=True, autocommit=True)
            with self._conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = {int(self.query_timeout) * 1000}")
        return self._conn

    def _rows(self, sql: str, params: tuple = ()) -> tuple[list[str], list[tuple]]:
        return super()._rows(sql.replace("?", "%s"), params)

    def list_tables(self, schema: str, like: Optional[str] = None) -> list[tuple[str, str]]:
        sql = "SELECT table_schema, table_name FROM information_schema.tables WHERE table_type IN ('BASE TABLE','VIEW') AND table_schema = ?"
        params: tuple = (schema,)
        if like:
            sql += " AND table_name ILIKE ?"
            params = (schema, like)
        _, rows = self._rows(sql + " ORDER BY table_name", params)
        return [(r[0], r[1]) for r in rows]

    def row_counts(self, schema: str) -> dict[str, int]:
        try:
            _, rows = self._rows(
                """SELECT c.relname, GREATEST(c.reltuples, 0)::bigint FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = %s AND c.relkind IN ('r', 'p')""",
                (schema or self.default_schema,),
            )
        except Exception as e:  # noqa: BLE001
            log.debug("bulk row counts unavailable: %s", e)
            return {}
        return {str(r[0]): int(r[1] or 0) for r in rows}

    def descriptions(self, schema: str) -> dict[tuple[str, Optional[str]], str]:
        """Postgres keeps them as object comments: obj_description for a table, col_description for a
        column. One query for the schema, same shape as every other engine's answer."""
        try:
            _, rows = self._rows(
                """SELECT c.relname AS tbl, a.attname AS col,
                          COALESCE(col_description(c.oid, a.attnum), obj_description(c.oid, 'pg_class')) AS descr,
                          (a.attnum IS NULL) AS is_table
                   FROM pg_class c
                   JOIN pg_namespace n ON n.oid = c.relnamespace
                   LEFT JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
                   WHERE n.nspname = %s AND c.relkind IN ('r', 'p', 'v', 'm')""",
                (schema or self.default_schema,),
            )
        except Exception as e:  # noqa: BLE001
            log.debug("pg comments unavailable: %s", e)
            return {}
        out: dict[tuple[str, Optional[str]], str] = {}
        for r in rows:
            table, column, descr = str(r[0]), (str(r[1]) if r[1] is not None else None), r[2]
            if not descr:
                continue
            out[(table, column)] = str(descr)
        try:
            _, trows = self._rows(
                """SELECT c.relname, obj_description(c.oid, 'pg_class')
                   FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = %s AND c.relkind IN ('r', 'p', 'v', 'm')""",
                (schema or self.default_schema,),
            )
            for r in trows:
                if r[1]:
                    out[(str(r[0]), None)] = str(r[1])
        except Exception:  # noqa: BLE001
            pass
        return out

    def columns(self, schema: str, table: str) -> list[dict[str, Any]]:
        _, rows = self._rows("SELECT column_name, data_type, character_maximum_length, is_nullable FROM information_schema.columns WHERE table_schema=? AND table_name=? ORDER BY ordinal_position", (schema, table))
        return [{"name": r[0], "data_type": (r[1] or "") + (f"({r[2]})" if r[2] else ""), "nullable": str(r[3]).upper() == "YES"} for r in rows]

    def primary_keys(self, schema: str, table: str) -> list[str]:
        _, rows = self._rows(
            """SELECT kcu.column_name FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu
               ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema
               WHERE tc.constraint_type='PRIMARY KEY' AND tc.table_schema=? AND tc.table_name=? ORDER BY kcu.ordinal_position""",
            (schema, table),
        )
        return [r[0] for r in rows]

    def foreign_keys(self, schema: str) -> list[dict[str, str]]:
        _, rows = self._rows(
            """SELECT tc.table_name, kcu.column_name, ccu.table_name, ccu.column_name FROM information_schema.table_constraints tc
               JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema
               JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
               WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_schema=?""",
            (schema,),
        )
        return [{"table": r[0], "column": r[1], "ref_table": r[2], "ref_column": r[3]} for r in rows]

    def top_values(self, schema: str, table: str, column: str, limit: int) -> list[tuple[str, int]]:
        _, rows = self._rows(f"SELECT {self.q(column)}::text AS v, COUNT(*) AS n FROM {self.q(schema)}.{self.q(table)} GROUP BY 1 ORDER BY n DESC LIMIT {int(limit)}")
        return [(str(r[0]), int(r[1])) for r in rows]

    def row_count(self, schema: str, table: str) -> Optional[int]:
        _, rows = self._rows("SELECT reltuples::bigint FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=? AND c.relname=?", (schema, table))
        return int(rows[0][0]) if rows else None

    def dry_run(self, sql: str) -> None:
        cur = self.conn().cursor()
        try:
            cur.execute("EXPLAIN " + sql)
        finally:
            cur.close()


class SQLiteConnector(_DbApiBase):
    dialect = "sqlite"
    default_schema = "main"

    def __init__(self, path: str = ":memory:", conn=None):
        super().__init__()
        self.path = path
        self._conn = conn

    def conn(self):
        if self._conn is None:
            import sqlite3

            self._conn = sqlite3.connect(self.path, check_same_thread=False)
        return self._conn

    def list_tables(self, schema: str, like: Optional[str] = None) -> list[tuple[str, str]]:
        sql = "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'"
        params: tuple = ()
        if like:
            sql += " AND name LIKE ?"
            params = (like,)
        _, rows = self._rows(sql + " ORDER BY name", params)
        return [(schema, r[0]) for r in rows]

    def columns(self, schema: str, table: str) -> list[dict[str, Any]]:
        _, rows = self._rows(f'PRAGMA table_info("{table}")')
        return [{"name": r[1], "data_type": r[2] or "", "nullable": not bool(r[3]), "pk": bool(r[5])} for r in rows]

    def primary_keys(self, schema: str, table: str) -> list[str]:
        return [c["name"] for c in self.columns(schema, table) if c.get("pk")]

    def foreign_keys(self, schema: str) -> list[dict[str, str]]:
        out = []
        for _, t in self.list_tables(schema):
            _, rows = self._rows(f'PRAGMA foreign_key_list("{t}")')
            out.extend({"table": t, "column": r[3], "ref_table": r[2], "ref_column": r[4]} for r in rows)
        return out

    def top_values(self, schema: str, table: str, column: str, limit: int) -> list[tuple[str, int]]:
        _, rows = self._rows(f'SELECT "{column}" AS v, COUNT(*) AS n FROM "{table}" GROUP BY 1 ORDER BY n DESC LIMIT {int(limit)}')
        return [(str(_norm(r[0])), int(r[1])) for r in rows]

    def row_count(self, schema: str, table: str) -> Optional[int]:
        _, rows = self._rows(f'SELECT COUNT(*) FROM "{table}"')
        return int(rows[0][0]) if rows else None

    def dry_run(self, sql: str) -> None:
        cur = self.conn().cursor()
        try:
            cur.execute("EXPLAIN " + sql)
        finally:
            cur.close()


class ModelFileConnector:
    supports_execution = False       # file-backed: it can describe the schema, it cannot query the data
    """Offline connector over an exported model directory: models/*/metadata.yml give tables/columns/
    descriptions, relationships.yml gives joins, and an optional enum probe JSON gives distinct/top values.
    Lets the whole pipeline run without a database (bootstrap, tests, air-gapped review)."""

    default_schema = ""

    dialect = "tsql"

    def __init__(self, project_dir: Path, enum_probe: Optional[Path] = None):
        self.project_dir = Path(project_dir)
        self.models: dict[str, dict[str, Any]] = {}
        for f in sorted((self.project_dir / "models").glob("*/metadata.yml")):
            m = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            tr = m.get("table_reference") or {}
            self.models[str(tr.get("table") or m.get("name"))] = m
        self.relationships: list[dict[str, Any]] = []
        rel = self.project_dir / "relationships.yml"
        if rel.exists():
            self.relationships = list((yaml.safe_load(rel.read_text(encoding="utf-8")) or {}).get("relationships") or [])
        self.enum: dict[tuple[str, str], dict[str, Any]] = {}
        if enum_probe and Path(enum_probe).exists():
            data = json.loads(Path(enum_probe).read_text(encoding="utf-8"))
            for e in data.get("enum_probe") or []:
                model = str(e.get("model") or "")
                table = model.split("_", 1)[1] if model.startswith("dbo_") else model
                self.enum[(table.upper(), str(e.get("column")).upper())] = e
        self._closed = False
        self._is_logo: Optional[bool] = None

    def list_tables(self, schema: str, like: Optional[str] = None) -> list[tuple[str, str]]:
        pat = None
        if like:
            pat = re.compile("^" + re.escape(like).replace("%", ".*").replace("_", ".") + "$", re.I)
        return [(schema, t) for t in sorted(self.models) if not pat or pat.match(t)]

    def columns(self, schema: str, table: str) -> list[dict[str, Any]]:
        m = self.models.get(table) or {}
        out = []
        for c in m.get("columns") or []:
            props = c.get("properties") or {}
            out.append({"name": c["name"], "data_type": str(c.get("type") or ""), "nullable": not bool(c.get("not_null")), "pk": bool(c.get("is_primary_key")), "description": self._describe(table, c["name"], props.get("description"))})
        return out

    #: A profiler annotation, not a sentence anybody wrote: "[enum] 3, 1, 4, 22 · 4 farklı değer".
    _ANNOTATION = re.compile(r"\[(?:enum|unit|time|pii)\]")

    @classmethod
    def _is_written(cls, text: Optional[str]) -> bool:
        """Whether a description carries prose, or is only the annotations a previous run derived."""
        return bool(cls._ANNOTATION.split(str(text or ""), 1)[0].strip())

    @property
    def _logo(self) -> bool:
        from semantic_layer.profiler import logo_dictionary

        if self._is_logo is None:
            self._is_logo = logo_dictionary.is_logo_schema(self._table_names())
        return self._is_logo

    def _describe(self, table: str, column: str, exported: Optional[str]) -> Optional[str]:
        """The export's own words, with the vendor dictionary supplying what it never had.

        A sentence someone typed is the last word: it carries the filters an answer needs — which
        rows count as cancelled, which document code is a sale — and no vendor line displaces it.
        A bare "[enum] 3, 1, 4, 22 · 4 farklı değer" is this pipeline's own earlier output, which
        says which codes occur and nothing about what any of them means; there the vendor's labels
        go in front, so the annotation keeps its place and the codes finally get their names.
        """
        if self._is_written(exported) or not self._logo:
            return exported
        from semantic_layer.profiler import logo_dictionary

        sentence = logo_dictionary.column_description(table, column)
        if not sentence:
            return exported
        return f"{sentence} {exported}".strip() if exported else sentence

    def table_description(self, table: str) -> Optional[str]:
        return ((self.models.get(table) or {}).get("properties") or {}).get("description")

    def _table_names(self) -> list[str]:
        return sorted(self.models)

    def descriptions(self, schema: str) -> dict[tuple[str, Optional[str]], str]:
        """Every table and column this export can speak for, in the shape a connector returns.

        The column text is already composed by `columns()` — the export's own words, with the vendor
        dictionary filling in what it never had. What is left for here is the table's own line.
        """
        out: dict[tuple[str, Optional[str]], str] = {}
        for table in self.models:
            for c in self.columns(schema, table):
                if text := c.get("description"):
                    out[(table, c["name"])] = str(text)
            if desc := self.table_description(table):
                out[(table, None)] = str(desc)
            elif self._logo:
                from semantic_layer.profiler import logo_dictionary

                if sentence := logo_dictionary.table_description(table):
                    out[(table, None)] = sentence
        return out

    def primary_keys(self, schema: str, table: str) -> list[str]:
        m = self.models.get(table) or {}
        pk = m.get("primary_key")
        if keys := ([pk] if pk else [c["name"] for c in self.columns(schema, table) if c.get("pk")]):
            return keys
        from semantic_layer.profiler import logo_dictionary

        return logo_dictionary.primary_key(table, [c["name"] for c in self.columns(schema, table)])

    def foreign_keys(self, schema: str) -> list[dict[str, str]]:
        out = []
        for r in self.relationships:
            cond = str(r.get("condition") or "")
            m = re.match(r'"?([\w.]+)"?\.(\w+)\s*=\s*"?([\w.]+)"?\.(\w+)', cond.replace('"', ""))
            if m:
                a, ca, b, cb = m.groups()
                out.append({"table": a.split("_", 1)[1] if a.startswith("dbo_") else a, "column": ca, "ref_table": b.split("_", 1)[1] if b.startswith("dbo_") else b, "ref_column": cb})
        # relationships.yml holds the joins someone exported — a dozen of them. The dictionary holds
        # the ones Logo never declared anywhere, and a join already exported is not added twice.
        from semantic_layer.profiler import logo_dictionary

        names = self._table_names()
        if not logo_dictionary.is_logo_schema(names):
            return out
        known = {(f["table"], f["column"]) for f in out}
        added = [f for f in logo_dictionary.foreign_keys(names) if (f["table"], f["column"]) not in known]
        if added:
            log.info("Logo data dictionary supplied %d joins the export does not declare", len(added))
        return out + added

    def top_values(self, schema: str, table: str, column: str, limit: int) -> list[tuple[str, int]]:
        e = self.enum.get((table.upper(), column.upper()))
        if e:
            return [(str(v), int(n)) for v, n in (e.get("top") or [])][:limit]
        # fall back to "[enum] 0=…, 1=… · N farklı değer" descriptions
        for c in self.columns(schema, table):
            if c["name"].upper() == column.upper() and c.get("description"):
                vals = re.findall(r"(?:^|[\s,])(-?\d+)(?==|,|\s·|$)", c["description"].split("[enum]")[-1]) if "[enum]" in c["description"] else []
                return [(v, 0) for v in dict.fromkeys(vals)][:limit]
        return []

    def distinct_hint(self, table: str, column: str) -> Optional[int]:
        e = self.enum.get((table.upper(), column.upper()))
        if e and e.get("distinct") is not None:
            return int(e["distinct"])
        for c in self.columns(self.default_schema, table):
            if c["name"].upper() == column.upper() and c.get("description"):
                m = re.search(r"(\d+) farkl", c["description"])
                if m:
                    return int(m.group(1))
        return None

    def row_count(self, schema: str, table: str) -> Optional[int]:
        return None

    def sample_rows(self, schema: str, table: str, limit: int = 20) -> list[dict[str, Any]]:
        return []          # offline: no rows to look at

    def execute(self, sql: str, limit: int):
        raise RuntimeError("ModelFileConnector is offline — no execution")

    def dry_run(self, sql: str) -> None:
        raise RuntimeError("ModelFileConnector is offline — no dry run")

    def close(self) -> None:
        self._closed = True


def connector_from_file(path: str) -> Connector:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "properties" in data and "datasource" in data:
        ds, cfg = str(data["datasource"]), dict(data["properties"])
    else:
        cfg = dict(data)
        ds = str(cfg.pop("datasource", "mssql"))
    ds = ds.lower()
    if ds in ("mssql", "sqlserver"):
        return MSSQLConnector(cfg)
    if ds in ("postgres", "postgresql", "pg"):
        return PostgresConnector(cfg)
    if ds == "sqlite":
        return SQLiteConnector(cfg.get("path", ":memory:"))
    raise ValueError(f"unsupported datasource: {ds}")


# Backwards-compatible alias for the previous name of ModelFileConnector.
MDLConnector = ModelFileConnector
