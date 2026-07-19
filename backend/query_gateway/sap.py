"""SAP HANA + CDS-OData RO helpers for Query Gateway (Faz 9)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode, urljoin

import httpx

# sqlglot has no HANA dialect — Postgres LIMIT rewrite is compatible enough for SELECT.
HANA_SQLGLOT_DIALECT = "postgres"

DEFAULT_HANA_TABLES: set[str] | None = None  # require explicit allowlist in secrets


def execute_hana(
    ds: dict[str, Any],
    sql: str,
    *,
    timeout_s: float,
    max_rows: int,
    max_cells: int,
    explain: bool,
) -> tuple[list[str], list[dict[str, Any]], bool]:
    try:
        from hdbcli import dbapi
    except ImportError as e:
        raise RuntimeError("hdbcli not installed — pip/uv install hdbcli") from e

    exec_sql = f"EXPLAIN PLAN FOR {sql}" if explain else sql
    conn = dbapi.connect(
        address=ds["host"],
        port=int(ds["port"]),
        user=ds["user"],
        password=ds["password"],
        encrypt=bool(ds.get("encrypt", True)),
        sslValidateCertificate=bool(ds.get("ssl_validate", False)),
        communicationTimeout=int(timeout_s * 1000),
    )
    try:
        cur = conn.cursor()
        cur.execute(exec_sql)
        if cur.description is None:
            return [], [], False
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchmany(max_rows + 1)
        dict_rows = [dict(zip(cols, r)) for r in rows]
        truncated = len(dict_rows) > max_rows
        dict_rows = dict_rows[:max_rows]
        cells = len(dict_rows) * max(len(cols), 1)
        if cells > max_cells:
            keep = max(1, max_cells // max(len(cols), 1))
            dict_rows = dict_rows[:keep]
            truncated = True
        # serialize
        out = []
        for r in dict_rows:
            item = {}
            for k, v in r.items():
                if hasattr(v, "isoformat"):
                    item[k] = v.isoformat()
                elif isinstance(v, (bytes, memoryview)):
                    item[k] = bytes(v).decode("utf-8", errors="replace")
                else:
                    item[k] = v
            out.append(item)
        return cols, out, truncated
    finally:
        conn.close()


_ODATA_SAFE = re.compile(r"^[A-Za-z0-9_./$-]+$")


def validate_odata_path(entity: str, allowed: set[str] | None) -> str | None:
    entity = (entity or "").strip().lstrip("/")
    if not entity or ".." in entity or ";" in entity:
        return "invalid entity path"
    if not _ODATA_SAFE.match(entity.split("(")[0].rstrip("/")):
        return "entity path has illegal characters"
    bare = entity.split("(")[0].rstrip("/").lower()
    if allowed is not None:
        allowed_n = {a.lower().rstrip("/") for a in allowed}
        if bare not in allowed_n and entity.lower() not in allowed_n:
            return f"entity not allowlisted: {bare}"
    return None


def execute_odata(
    ds: dict[str, Any],
    *,
    entity: str,
    query: dict[str, str],
    timeout_s: float,
    max_rows: int,
) -> dict[str, Any]:
    err = validate_odata_path(entity, ds.get("allowed_entities"))
    if err:
        raise ValueError(err)

    # Cap $top
    top = int(query.get("$top") or max_rows)
    top = max(1, min(top, max_rows))
    q = {k: v for k, v in query.items() if k.startswith("$") and k not in {"$format"}}
    # Deny mutating / dangerous options
    for bad in ("$batch", "$crossjoin", "$apply"):
        if bad in q:
            raise ValueError(f"forbidden OData option: {bad}")
    q["$top"] = str(top)
    q.setdefault("$format", "json")

    base = ds["base_url"].rstrip("/") + "/"
    url = urljoin(base, entity.lstrip("/"))
    if q:
        url = f"{url}?{urlencode(q)}"

    headers = {"Accept": "application/json"}
    auth = None
    token = ds.get("bearer_token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif ds.get("user") and ds.get("password"):
        auth = (ds["user"], ds["password"])

    with httpx.Client(timeout=timeout_s, verify=bool(ds.get("verify_tls", True))) as client:
        r = client.get(url, headers=headers, auth=auth)
        if r.status_code >= 400:
            raise RuntimeError(f"OData HTTP {r.status_code}: {r.text[:400]}")
        data = r.json()

    # OData V2: d.results / V4: value
    rows_raw = []
    if isinstance(data, dict):
        if isinstance(data.get("value"), list):
            rows_raw = data["value"]
        elif isinstance(data.get("d"), dict) and isinstance(data["d"].get("results"), list):
            rows_raw = data["d"]["results"]
        elif isinstance(data.get("d"), list):
            rows_raw = data["d"]
    truncated = len(rows_raw) > max_rows
    rows_raw = rows_raw[:max_rows]
    cols: list[str] = []
    rows: list[dict[str, Any]] = []
    for item in rows_raw:
        if not isinstance(item, dict):
            continue
        clean = {k: v for k, v in item.items() if not str(k).startswith("__")}
        rows.append(clean)
        for k in clean:
            if k not in cols:
                cols.append(k)
    return {
        "columns": cols,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
        "url": url.split("?")[0],
    }
