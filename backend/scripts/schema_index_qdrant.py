#!/usr/bin/env python3
"""Controlled schema scan → BGE-M3 embed → Qdrant (per datasource).

Env:
  BI_SCHEMA_DATASOURCE=bi_reporting|erp|sigorta
  BI_SCHEMA_COLLECTION=bi_schema_<id>   (default)
  BI_SCHEMA_SCHEMAS=analytics|public
  BI_SCHEMA_SKIP_SAMPLES=1
  BI_SCHEMA_SKIP_COUNTS=1
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

SECRETS = Path(os.environ.get("SECRETS_ROOT", "/data/nanobaseai/bi/secrets"))
OUT_DIR = Path(os.environ.get("PHASE2_OUT_DIR", "/data/nanobaseai/bi/frontend/docs/architecture"))

DATASOURCE = os.environ.get("BI_SCHEMA_DATASOURCE", "bi_reporting")
COLLECTION = os.environ.get("BI_SCHEMA_COLLECTION", f"bi_schema_{DATASOURCE}")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333").rstrip("/")
EMBED_URL = os.environ.get("BI_EMBED_URL", "http://127.0.0.1:8083/v1/embeddings")
VECTOR_SIZE = int(os.environ.get("BI_EMBED_DIM", "1024"))
SKIP_SAMPLES = os.environ.get("BI_SCHEMA_SKIP_SAMPLES", "0") == "1"
SKIP_COUNTS = os.environ.get("BI_SCHEMA_SKIP_COUNTS", "0") == "1"
MAX_TABLES = int(os.environ.get("BI_SCHEMA_MAX_TABLES", "200"))


@dataclass
class SchemaChunk:
    chunk_id: str
    kind: str
    schema: str
    table: str
    column: str | None
    text: str
    meta: dict[str, Any]


def _http_json(method: str, url: str, body: dict | None = None, headers: dict | None = None, timeout: int = 120) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} -> {e.code}: {raw[:600]}") from e


def _embed_key() -> str:
    key = os.environ.get("BI_EMBED_API_KEY") or os.environ.get("CONTRACT_API_KEY") or ""
    if key:
        return key
    # Prefer backend/.env (no sudo hang)
    for env_path in (
        Path("/data/nanobaseai/bi/frontend/backend/.env"),
        Path(__file__).resolve().parents[1] / ".env",
        Path("/etc/nanobaseai/contract.env"),
    ):
        if not env_path.is_file():
            continue
        try:
            text = env_path.read_text(encoding="utf-8")
        except PermissionError:
            continue
        for line in text.splitlines():
            if line.startswith("CONTRACT_API_KEY=") or line.startswith("BI_EMBED_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("Missing embedding API key (BI_EMBED_API_KEY / CONTRACT_API_KEY)")


def embed_texts(texts: list[str], api_key: str) -> list[list[float]]:
    out: list[list[float]] = []
    batch = 8
    for i in range(0, len(texts), batch):
        chunk = texts[i : i + batch]
        res = _http_json(
            "POST",
            EMBED_URL,
            {"texts": chunk},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        vectors = res.get("embeddings") or res.get("data")
        if isinstance(vectors, list) and vectors and isinstance(vectors[0], dict):
            vectors = [v["embedding"] for v in sorted(vectors, key=lambda x: x.get("index", 0))]
        if not isinstance(vectors, list) or len(vectors) != len(chunk):
            raise RuntimeError(f"bad embed response keys={list(res.keys())}")
        out.extend(vectors)
    return out


def _load_pg_cfg() -> tuple[dict[str, Any], tuple[str, ...]]:
    if DATASOURCE == "bi_reporting":
        pw = (SECRETS / "reporting-ro.password").read_text(encoding="utf-8").strip()
        schemas = tuple(
            s.strip()
            for s in os.environ.get("BI_SCHEMA_SCHEMAS", "analytics,public").split(",")
            if s.strip()
        )
        return (
            {
                "host": os.environ.get("REPORTING_HOST", "127.0.0.1"),
                "port": int(os.environ.get("REPORTING_PORT", "5435")),
                "dbname": os.environ.get("REPORTING_DB", "bi_reporting"),
                "user": os.environ.get("REPORTING_RO_USER", "bi_reporting_ro"),
                "password": pw,
                "sslmode": "disable",
            },
            schemas or ("analytics", "public"),
        )

    neon = json.loads((SECRETS / "neon-ro.datasources.json").read_text(encoding="utf-8"))
    cfg = (neon.get("sources") or {}).get(DATASOURCE)
    if not isinstance(cfg, dict):
        raise SystemExit(f"datasource not in neon-ro map: {DATASOURCE}")
    pw = cfg.get("password") or ""
    if not pw and cfg.get("password_file"):
        pw = Path(cfg["password_file"]).read_text(encoding="utf-8").strip()
    schemas = tuple(
        s.strip()
        for s in os.environ.get("BI_SCHEMA_SCHEMAS", "public").split(",")
        if s.strip()
    )
    return (
        {
            "host": cfg["host"],
            "port": int(cfg.get("port") or 5432),
            "dbname": cfg.get("database") or "neondb",
            "user": cfg["user"],
            "password": pw,
            "sslmode": cfg.get("sslmode") or "require",
        },
        schemas or ("public",),
    )


def connect(cfg: dict[str, Any]):
    return psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        dbname=cfg["dbname"],
        user=cfg["user"],
        password=cfg["password"],
        sslmode=cfg.get("sslmode") or "prefer",
        connect_timeout=20,
    )


def scan(conn, schemas: tuple[str, ...]) -> list[SchemaChunk]:
    chunks: list[SchemaChunk] = []
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT table_schema, table_name, table_type
        FROM information_schema.tables
        WHERE table_schema = ANY(%s)
          AND table_type IN ('BASE TABLE', 'VIEW')
        ORDER BY table_schema, table_name
        LIMIT %s
        """,
        (list(schemas), MAX_TABLES),
    )
    tables = list(cur.fetchall())
    domain = (
        "ERP / satış / fatura / stok / bütçe"
        if DATASOURCE == "erp"
        else "sigorta / poliçe / hasar / acente"
        if DATASOURCE == "sigorta"
        else "sales / customers / orders analytics"
    )

    for t in tables:
        schema, name, ttype = t["table_schema"], t["table_name"], t["table_type"]
        fq = f"{schema}.{name}"
        cur.execute(
            """
            SELECT column_name, data_type, udt_name, is_nullable,
                   character_maximum_length, numeric_precision, numeric_scale,
                   datetime_precision
            FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s
            ORDER BY ordinal_position
            """,
            (schema, name),
        )
        cols = list(cur.fetchall())

        row_count = None
        if not SKIP_COUNTS:
            try:
                cur.execute(f'SELECT COUNT(*) AS n FROM "{schema}"."{name}"')
                row_count = int(cur.fetchone()["n"])
            except Exception:
                conn.rollback()

        cur.execute(
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.table_schema=%s AND tc.table_name=%s AND tc.constraint_type='PRIMARY KEY'
            """,
            (schema, name),
        )
        pks = [r["column_name"] for r in cur.fetchall()]

        col_lines = []
        for c in cols:
            sample = None
            if not SKIP_SAMPLES and ttype == "BASE TABLE":
                try:
                    cur.execute(
                        f'SELECT DISTINCT "{c["column_name"]}"::text AS v '
                        f'FROM "{schema}"."{name}" '
                        f'WHERE "{c["column_name"]}" IS NOT NULL LIMIT 5'
                    )
                    sample = [r["v"] for r in cur.fetchall()]
                except Exception:
                    conn.rollback()
                    sample = None

            try:
                from nanobase_api.schema_api import format_column_type

                type_display = format_column_type(
                    data_type=str(c["data_type"] or ""),
                    udt_name=str(c.get("udt_name") or "") or None,
                    character_maximum_length=c.get("character_maximum_length"),
                    numeric_precision=c.get("numeric_precision"),
                    numeric_scale=c.get("numeric_scale"),
                    datetime_precision=c.get("datetime_precision"),
                )
            except Exception:
                type_display = str(c["data_type"] or "")
            col_text = (
                f"Column {fq}.{c['column_name']} type={type_display} "
                f"nullable={c['is_nullable']} "
                f"max_length={c.get('character_maximum_length')} "
                f"precision={c.get('numeric_precision')} scale={c.get('numeric_scale')} "
                f"samples={sample or []} "
                f"datasource={DATASOURCE} domain={domain}"
            )
            cid = hashlib.sha1(f"{DATASOURCE}:col:{fq}.{c['column_name']}".encode()).hexdigest()[:16]
            chunks.append(
                SchemaChunk(
                    chunk_id=cid,
                    kind="column",
                    schema=schema,
                    table=name,
                    column=c["column_name"],
                    text=col_text,
                    meta={
                        "datasource_id": DATASOURCE,
                        "data_type": c["data_type"],
                        "type_display": type_display,
                        "max_length": c.get("character_maximum_length"),
                        "precision": c.get("numeric_precision"),
                        "scale": c.get("numeric_scale"),
                        "samples": sample or [],
                        "pk": c["column_name"] in pks,
                    },
                )
            )
            col_lines.append(f"- {c['column_name']} {type_display}")

        table_text = (
            f"{'View' if ttype == 'VIEW' else 'Table'} {fq} datasource={DATASOURCE}\n"
            f"Domain: {domain}\n"
            f"Row count: {row_count}\n"
            f"Primary key: {pks}\n"
            f"Columns:\n" + "\n".join(col_lines)
        )
        tid = hashlib.sha1(f"{DATASOURCE}:table:{fq}".encode()).hexdigest()[:16]
        chunks.append(
            SchemaChunk(
                chunk_id=tid,
                kind="view" if ttype == "VIEW" else "table",
                schema=schema,
                table=name,
                column=None,
                text=table_text,
                meta={
                    "datasource_id": DATASOURCE,
                    "row_count": row_count,
                    "pk": pks,
                    "table_type": ttype,
                },
            )
        )

    cur.close()
    return chunks


def ensure_collection() -> None:
    try:
        _http_json("GET", f"{QDRANT_URL}/collections/{COLLECTION}")
        _http_json("DELETE", f"{QDRANT_URL}/collections/{COLLECTION}")
    except RuntimeError:
        pass
    _http_json(
        "PUT",
        f"{QDRANT_URL}/collections/{COLLECTION}",
        {"vectors": {"size": VECTOR_SIZE, "distance": "Cosine"}},
    )


def upsert(chunks: list[SchemaChunk], vectors: list[list[float]]) -> None:
    points = []
    for ch, vec in zip(chunks, vectors):
        pid = int(hashlib.sha1(ch.chunk_id.encode()).hexdigest()[:15], 16)
        points.append(
            {
                "id": pid,
                "vector": vec,
                "payload": {
                    "chunk_id": ch.chunk_id,
                    "kind": ch.kind,
                    "schema": ch.schema,
                    "table": ch.table,
                    "column": ch.column,
                    "text": ch.text,
                    "datasource_id": DATASOURCE,
                    **ch.meta,
                },
            }
        )
    for i in range(0, len(points), 64):
        batch = points[i : i + 64]
        _http_json("PUT", f"{QDRANT_URL}/collections/{COLLECTION}/points?wait=true", {"points": batch})


def main() -> None:
    api_key = _embed_key()
    cfg, schemas = _load_pg_cfg()
    t0 = time.time()
    conn = connect(cfg)
    try:
        conn.set_session(readonly=True, autocommit=True)
        chunks = scan(conn, schemas)
    finally:
        conn.close()

    print(f"datasource={DATASOURCE} schemas={schemas} scanned {len(chunks)} chunks → {COLLECTION}")
    ensure_collection()
    vectors = embed_texts([c.text for c in chunks], api_key)
    if vectors and len(vectors[0]) != VECTOR_SIZE:
        raise SystemExit(f"vector dim {len(vectors[0])} != {VECTOR_SIZE}")
    upsert(chunks, vectors)

    info = _http_json("GET", f"{QDRANT_URL}/collections/{COLLECTION}")
    points_count = (info.get("result") or {}).get("points_count")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "datasource_id": DATASOURCE,
        "collection": COLLECTION,
        "schemas": list(schemas),
        "chunks": len(chunks),
        "points_count": points_count,
        "vector_size": VECTOR_SIZE,
        "elapsed_s": round(time.time() - t0, 2),
        "sample": [asdict(c) for c in chunks[:5]],
    }
    path = OUT_DIR / f"schema-index-{DATASOURCE}.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    # keep legacy name for reporting
    if DATASOURCE == "bi_reporting":
        (OUT_DIR / "phase-2-schema-index.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(f"indexed points={points_count} → {path}")


if __name__ == "__main__":
    main()
