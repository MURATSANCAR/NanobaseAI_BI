"""Oracle metadata scanner using ALL_* views (no DBA_*)."""

from __future__ import annotations

from typing import Any, Iterable

from query_gateway.infrastructure.oracle.synonym_resolver import resolve_synonym

# Controlled profiling templates — never SELECT *
PROFILE_COUNT = "SELECT COUNT(*) AS CNT FROM {owner}.{obj}"
PROFILE_DATE_RANGE = (
    "SELECT MIN({col}) AS DMIN, MAX({col}) AS DMAX FROM {owner}.{obj}"
)
PROFILE_STATUS = (
    "SELECT {col} AS STATUS, COUNT(*) AS CNT FROM {owner}.{obj} "
    "GROUP BY {col} FETCH FIRST 20 ROWS ONLY"
)


OBJECTS_SQL = """
SELECT OWNER, OBJECT_NAME, OBJECT_TYPE, STATUS, LAST_DDL_TIME
FROM ALL_OBJECTS
WHERE OWNER IN ({owners})
  AND OBJECT_TYPE IN ('TABLE', 'VIEW', 'MATERIALIZED VIEW', 'SYNONYM')
ORDER BY OWNER, OBJECT_NAME
"""

COLUMNS_SQL = """
SELECT OWNER, TABLE_NAME, COLUMN_NAME, DATA_TYPE, DATA_LENGTH,
       DATA_PRECISION, DATA_SCALE, NULLABLE, DATA_DEFAULT,
       VIRTUAL_COLUMN, HIDDEN_COLUMN, COLUMN_ID
FROM ALL_TAB_COLUMNS
WHERE OWNER IN ({owners})
ORDER BY OWNER, TABLE_NAME, COLUMN_ID
"""

TAB_COMMENTS_SQL = """
SELECT OWNER, TABLE_NAME, COMMENTS
FROM ALL_TAB_COMMENTS
WHERE OWNER IN ({owners})
"""

COL_COMMENTS_SQL = """
SELECT OWNER, TABLE_NAME, COLUMN_NAME, COMMENTS
FROM ALL_COL_COMMENTS
WHERE OWNER IN ({owners})
"""

CONSTRAINTS_SQL = """
SELECT C.OWNER, C.CONSTRAINT_NAME, C.CONSTRAINT_TYPE, C.TABLE_NAME,
       C.R_OWNER, C.R_CONSTRAINT_NAME, C.STATUS,
       CC.COLUMN_NAME, CC.POSITION
FROM ALL_CONSTRAINTS C
JOIN ALL_CONS_COLUMNS CC
  ON C.OWNER = CC.OWNER AND C.CONSTRAINT_NAME = CC.CONSTRAINT_NAME
WHERE C.OWNER IN ({owners})
  AND C.CONSTRAINT_TYPE IN ('P', 'U', 'R', 'C')
ORDER BY C.OWNER, C.TABLE_NAME, C.CONSTRAINT_NAME, CC.POSITION
"""

SYNONYMS_SQL = """
SELECT OWNER, SYNONYM_NAME, TABLE_OWNER, TABLE_NAME, DB_LINK
FROM ALL_SYNONYMS
WHERE OWNER IN ({owners})
"""

POLICIES_SQL = """
SELECT OBJECT_OWNER, OBJECT_NAME, POLICY_NAME, PF_OWNER, PACKAGE, FUNCTION, ENABLE, POLICY_TYPE
FROM ALL_POLICIES
WHERE OBJECT_OWNER IN ({owners})
"""

MVIEWS_SQL = """
SELECT OWNER, MVIEW_NAME, CONTAINER_NAME, QUERY, REWRITE_ENABLED, REFRESH_MODE
FROM ALL_MVIEWS
WHERE OWNER IN ({owners})
"""


def _owner_binds(owners: Iterable[str]) -> tuple[str, dict[str, str]]:
    owners_u = [o.upper() for o in owners]
    placeholders = ", ".join(f":o{i}" for i in range(len(owners_u)))
    binds = {f"o{i}": o for i, o in enumerate(owners_u)}
    return placeholders, binds


def _fetch_all(conn: Any, sql: str, binds: dict[str, Any]) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, binds)
        cols = [d[0].lower() for d in (cur.description or [])]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def scan_oracle_metadata(
    conn: Any,
    *,
    allowed_owners: list[str],
    allow_public_synonyms: bool = False,
    include_policies: bool = True,
) -> dict[str, Any]:
    """Scan ALL_* metadata for allowlisted owners only."""
    ph, binds = _owner_binds(allowed_owners)
    objects = _fetch_all(conn, OBJECTS_SQL.format(owners=ph), binds)
    columns = _fetch_all(conn, COLUMNS_SQL.format(owners=ph), binds)
    tab_comments = _fetch_all(conn, TAB_COMMENTS_SQL.format(owners=ph), binds)
    col_comments = _fetch_all(conn, COL_COMMENTS_SQL.format(owners=ph), binds)
    constraints = _fetch_all(conn, CONSTRAINTS_SQL.format(owners=ph), binds)
    synonyms_raw = _fetch_all(conn, SYNONYMS_SQL.format(owners=ph), binds)
    mviews = _fetch_all(conn, MVIEWS_SQL.format(owners=ph), binds)
    policies: list[dict[str, Any]] = []
    if include_policies:
        try:
            policies = _fetch_all(conn, POLICIES_SQL.format(owners=ph), binds)
        except Exception:
            policies = []

    # Object type lookup for synonym resolution
    type_map: dict[tuple[str, str], str] = {}
    for obj in objects:
        type_map[(obj["owner"].upper(), obj["object_name"].upper())] = str(
            obj["object_type"]
        ).upper()

    syn_index = {
        (r["owner"].upper(), r["synonym_name"].upper()): r for r in synonyms_raw
    }

    def fetch_synonym(o: str, n: str) -> dict[str, Any] | None:
        return syn_index.get((o.upper(), n.upper()))

    def fetch_object_type(o: str, n: str) -> str | None:
        return type_map.get((o.upper(), n.upper()))

    resolved_synonyms: list[dict[str, Any]] = []
    for syn in synonyms_raw:
        try:
            res = resolve_synonym(
                syn["owner"],
                syn["synonym_name"],
                allowed_owners=set(allowed_owners),
                allow_public=allow_public_synonyms,
                fetch_synonym=fetch_synonym,
                fetch_object_type=fetch_object_type,
            )
            resolved_synonyms.append(
                {
                    "document_type": "SYNONYM",
                    "owner": res.owner,
                    "synonym_name": res.synonym_name,
                    "resolved_owner": res.resolved_owner,
                    "resolved_object": res.resolved_object,
                    "resolved_type": res.resolved_type,
                    "chain": res.chain,
                }
            )
        except Exception:
            # Unresolved / rejected synonyms are not indexed
            continue

    return {
        "objects": objects,
        "columns": columns,
        "table_comments": tab_comments,
        "column_comments": col_comments,
        "constraints": constraints,
        "materialized_views": mviews,
        "policies": policies,
        "synonyms": resolved_synonyms,
        "allowed_owners": [o.upper() for o in allowed_owners],
    }


def to_qdrant_documents(
    scan: dict[str, Any],
    *,
    tenant_id: str,
    datasource_id: str,
    database_unique_name: str = "",
    container_name: str = "",
    schema_version: str = "",
    semantic_version: str = "8.0.0",
) -> list[dict[str, Any]]:
    """Build Oracle Qdrant payloads (TABLE/COLUMN/SYNONYM/RELATIONSHIP)."""
    docs: list[dict[str, Any]] = []
    base = {
        "tenant_id": tenant_id,
        "datasource_id": datasource_id,
        "database_type": "ORACLE",
        "database_unique_name": database_unique_name,
        "container_name": container_name,
        "schema_version": schema_version,
        "semantic_version": semantic_version,
        "status": "ACTIVE",
    }
    comments = {
        (c["owner"].upper(), c["table_name"].upper()): c.get("comments")
        for c in scan.get("table_comments") or []
    }
    col_comments = {
        (
            c["owner"].upper(),
            c["table_name"].upper(),
            c["column_name"].upper(),
        ): c.get("comments")
        for c in scan.get("column_comments") or []
    }

    for obj in scan.get("objects") or []:
        if str(obj.get("object_type")).upper() == "SYNONYM":
            continue
        if str(obj.get("status") or "VALID").upper() != "VALID":
            continue
        owner = obj["owner"].upper()
        name = obj["object_name"].upper()
        docs.append(
            {
                **base,
                "document_type": "TABLE"
                if obj["object_type"] == "TABLE"
                else obj["object_type"].upper().replace(" ", "_"),
                "owner": owner,
                "object_name": name,
                "object_type": str(obj["object_type"]).upper(),
                "description": comments.get((owner, name)),
                "text": f"{owner}.{name} {comments.get((owner, name)) or ''}".strip(),
            }
        )

    for col in scan.get("columns") or []:
        owner = col["owner"].upper()
        table = col["table_name"].upper()
        cname = col["column_name"].upper()
        docs.append(
            {
                **base,
                "document_type": "COLUMN",
                "owner": owner,
                "object_name": table,
                "object_type": "COLUMN",
                "column_name": cname,
                "oracle_data_type": str(col.get("data_type") or "").upper(),
                "precision": col.get("data_precision"),
                "scale": col.get("data_scale"),
                "nullable": col.get("nullable"),
                "description": col_comments.get((owner, table, cname)),
                "text": (
                    f"{owner}.{table}.{cname} "
                    f"{col.get('data_type')} {col_comments.get((owner, table, cname)) or ''}"
                ).strip(),
            }
        )

    for syn in scan.get("synonyms") or []:
        docs.append({**base, **syn, "text": f"{syn['owner']}.{syn['synonym_name']} -> "
                     f"{syn['resolved_owner']}.{syn['resolved_object']}"})

    return docs
