#!/usr/bin/env python3
"""Sync erp/sigorta rows in bi_sources from neon-ro.datasources.json (RO + file secrets)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import psycopg2

SECRETS = Path(os.environ.get("SECRETS_ROOT", "/data/nanobaseai/bi/secrets"))
NEON_MAP = SECRETS / "neon-ro.datasources.json"
META_PW_FILE = SECRETS / "bi-meta-db.password"
TENANT_ID = os.environ.get("NANOBASE_TENANT_ID", "default")


def _meta_dsn() -> str:
    if os.environ.get("NANOBASE_META_DSN"):
        return os.environ["NANOBASE_META_DSN"]
    pw = META_PW_FILE.read_text(encoding="utf-8").strip()
    return (
        f"postgresql://bi_meta:{pw}@127.0.0.1:5434/bi_meta"
    )


def _secret_ref(password_file: str) -> str:
    p = Path(password_file)
    if p.is_absolute():
        return f"file:{p}"
    return f"file:{SECRETS / password_file}"


def main() -> int:
    if not NEON_MAP.is_file():
        print(f"missing {NEON_MAP}", file=sys.stderr)
        return 1

    raw = json.loads(NEON_MAP.read_text(encoding="utf-8"))
    sources = raw.get("sources") or {}
    if not sources:
        print("neon-ro map empty", file=sys.stderr)
        return 1

    conn = psycopg2.connect(_meta_dsn())
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO bi_tenants (id, name, status, created_at, updated_at)
        VALUES (%s, %s, 'active', NOW(), NOW())
        ON CONFLICT (id) DO NOTHING
        """,
        (TENANT_ID, TENANT_ID),
    )

    for sid, cfg in sources.items():
        if not isinstance(cfg, dict):
            continue
        host = cfg.get("host") or ""
        port = int(cfg.get("port") or 5432)
        database = cfg.get("database") or "neondb"
        username = cfg.get("user") or cfg.get("username") or ""
        label = cfg.get("label") or sid
        pw_file = cfg.get("password_file") or str(SECRETS / f"neon-{sid}.password")
        secret_ref = _secret_ref(str(pw_file))
        if not Path(pw_file if str(pw_file).startswith("/") else SECRETS / pw_file).is_file():
            # tolerate file: prefix already in password_file
            alt = Path(str(pw_file).removeprefix("file:"))
            if not alt.is_file():
                print(f"skip {sid}: password file missing ({pw_file})")
                continue
            secret_ref = f"file:{alt}"

        masked = f"postgresql://{username}:***@{host}:{port}/{database}"
        cur.execute(
            """
            INSERT INTO bi_sources (
              id, tenant_id, project_id, label, driver, host, port, database,
              username, secret_ref, ssl, dialect, connection_url_masked,
              created_at, updated_at
            ) VALUES (
              %s, %s, 'default', %s, 'postgresql', %s, %s, %s,
              %s, %s, TRUE, 'postgresql', %s,
              NOW(), NOW()
            )
            ON CONFLICT (tenant_id, id) DO UPDATE SET
              label = EXCLUDED.label,
              driver = EXCLUDED.driver,
              host = EXCLUDED.host,
              port = EXCLUDED.port,
              database = EXCLUDED.database,
              username = EXCLUDED.username,
              secret_ref = EXCLUDED.secret_ref,
              ssl = EXCLUDED.ssl,
              dialect = EXCLUDED.dialect,
              connection_url_masked = EXCLUDED.connection_url_masked,
              updated_at = NOW()
            """,
            (sid, TENANT_ID, label, host, port, database, username, secret_ref, masked),
        )
        print(f"synced {sid}: user={username} secret_ref={secret_ref}")

    cur.execute(
        """
        SELECT id, username, secret_ref
        FROM bi_sources
        WHERE tenant_id = %s AND id = ANY(%s)
        ORDER BY id
        """,
        (TENANT_ID, list(sources.keys())),
    )
    for row in cur.fetchall():
        print("row", row[0], "user=", row[1], "ref=", row[2])

    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
