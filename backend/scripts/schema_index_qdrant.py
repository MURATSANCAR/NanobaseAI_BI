#!/usr/bin/env python3
"""Faz 2: Controlled schema scan → BGE-M3 embed → Qdrant collection.

Indexes analytics (+ public aliases) from bi_reporting for retrieval-augmented NL2SQL.
Server-only; secrets from /data/nanobaseai/bi/secrets.
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
RO_PASSWORD_FILE = SECRETS / "reporting-ro.password"
OUT_DIR = Path(os.environ.get("PHASE2_OUT_DIR", "/data/nanobaseai/bi/frontend/docs/architecture"))

PG_HOST = os.environ.get("REPORTING_HOST", "127.0.0.1")
PG_PORT = int(os.environ.get("REPORTING_PORT", "5435"))
PG_DB = os.environ.get("REPORTING_DB", "bi_reporting")
PG_USER = os.environ.get("REPORTING_RO_USER", "bi_reporting_ro")

QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333").rstrip("/")
COLLECTION = os.environ.get("BI_SCHEMA_COLLECTION", "bi_schema_bi_reporting")
EMBED_URL = os.environ.get("BI_EMBED_URL", "http://127.0.0.1:8083/v1/embeddings")
VECTOR_SIZE = int(os.environ.get("BI_EMBED_DIM", "1024"))

SCHEMAS = ("analytics",)


@dataclass
class SchemaChunk:
    chunk_id: str
    kind: str  # table | column | view
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
    env_path = Path("/etc/nanobaseai/contract.env")
    if env_path.is_file() or os.access("/etc/nanobaseai/contract.env", os.R_OK):
        try:
            text = env_path.read_text(encoding="utf-8")
        except PermissionError:
            import subprocess

            text = subprocess.check_output(
                ["sudo", "grep", "-E", "^CONTRACT_API_KEY=", "/etc/nanobaseai/contract.env"],
                text=True,
            )
        for line in text.splitlines():
            if line.startswith("CONTRACT_API_KEY="):
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
            # OpenAI-ish
            vectors = [v["embedding"] for v in sorted(vectors, key=lambda x: x.get("index", 0))]
        if not isinstance(vectors, list) or len(vectors) != len(chunk):
            raise RuntimeError(f"bad embed response keys={list(res.keys())}")
        out.extend(vectors)
    return out


def connect():
    password = RO_PASSWORD_FILE.read_text(encoding="utf-8").strip()
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DB,
        user=PG_USER,
        password=password,
        connect_timeout=15,
    )


def scan(conn) -> list[SchemaChunk]:
    chunks: list[SchemaChunk] = []
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        """
        SELECT table_schema, table_name, table_type
        FROM information_schema.tables
        WHERE table_schema = ANY(%s)
          AND table_type IN ('BASE TABLE', 'VIEW')
        ORDER BY table_schema, table_name
        """,
        (list(SCHEMAS),),
    )
    tables = list(cur.fetchall())

    for t in tables:
        schema, name, ttype = t["table_schema"], t["table_name"], t["table_type"]
        fq = f"{schema}.{name}"

        # columns
        cur.execute(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s
            ORDER BY ordinal_position
            """,
            (schema, name),
        )
        cols = list(cur.fetchall())

        # row count (views/tables)
        row_count = None
        try:
            cur.execute(f'SELECT COUNT(*) AS n FROM "{schema}"."{name}"')
            row_count = int(cur.fetchone()["n"])
        except Exception:
            conn.rollback()

        # PK / FK hints
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
            if ttype == "BASE TABLE":
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

            col_text = (
                f"Column {fq}.{c['column_name']} type={c['data_type']} "
                f"nullable={c['is_nullable']} "
                f"samples={sample or []}"
            )
            cid = hashlib.sha1(f"col:{fq}.{c['column_name']}".encode()).hexdigest()[:16]
            chunks.append(
                SchemaChunk(
                    chunk_id=cid,
                    kind="column",
                    schema=schema,
                    table=name,
                    column=c["column_name"],
                    text=col_text,
                    meta={"data_type": c["data_type"], "samples": sample or [], "pk": c["column_name"] in pks},
                )
            )
            col_lines.append(f"- {c['column_name']} {c['data_type']}")

        table_text = (
            f"{'View' if ttype == 'VIEW' else 'Table'} {fq}\n"
            f"Row count: {row_count}\n"
            f"Primary key: {pks}\n"
            f"Columns:\n" + "\n".join(col_lines) + "\n"
            f"Use for NL2SQL over sales/customers/orders analytics."
        )
        tid = hashlib.sha1(f"table:{fq}".encode()).hexdigest()[:16]
        chunks.append(
            SchemaChunk(
                chunk_id=tid,
                kind="view" if ttype == "VIEW" else "table",
                schema=schema,
                table=name,
                column=None,
                text=table_text,
                meta={"row_count": row_count, "pk": pks, "table_type": ttype},
            )
        )

    cur.close()
    return chunks


def ensure_collection() -> None:
    try:
        _http_json("GET", f"{QDRANT_URL}/collections/{COLLECTION}")
        # recreate for idempotent clean index
        _http_json("DELETE", f"{QDRANT_URL}/collections/{COLLECTION}")
    except RuntimeError:
        pass
    _http_json(
        "PUT",
        f"{QDRANT_URL}/collections/{COLLECTION}",
        {
            "vectors": {"size": VECTOR_SIZE, "distance": "Cosine"},
        },
    )


def upsert(chunks: list[SchemaChunk], vectors: list[list[float]]) -> None:
    points = []
    for ch, vec in zip(chunks, vectors):
        # Qdrant point id: unsigned int from hash
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
                    **ch.meta,
                },
            }
        )
    # batch upsert
    for i in range(0, len(points), 64):
        batch = points[i : i + 64]
        _http_json("PUT", f"{QDRANT_URL}/collections/{COLLECTION}/points?wait=true", {"points": batch})


def main() -> None:
    if not RO_PASSWORD_FILE.is_file():
        raise SystemExit(f"Missing {RO_PASSWORD_FILE}")
    api_key = _embed_key()

    t0 = time.time()
    conn = connect()
    try:
        chunks = scan(conn)
    finally:
        conn.close()

    print(f"scanned {len(chunks)} chunks")
    ensure_collection()
    vectors = embed_texts([c.text for c in chunks], api_key)
    if vectors and len(vectors[0]) != VECTOR_SIZE:
        raise SystemExit(f"vector dim {len(vectors[0])} != {VECTOR_SIZE}")
    upsert(chunks, vectors)

    # verify
    info = _http_json("GET", f"{QDRANT_URL}/collections/{COLLECTION}")
    points_count = (info.get("result") or {}).get("points_count")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "collection": COLLECTION,
        "chunks": len(chunks),
        "points_count": points_count,
        "vector_size": VECTOR_SIZE,
        "elapsed_s": round(time.time() - t0, 2),
        "sample": [asdict(c) for c in chunks[:5]],
    }
    path = OUT_DIR / "phase-2-schema-index.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"indexed points={points_count} → {path}")


if __name__ == "__main__":
    main()
