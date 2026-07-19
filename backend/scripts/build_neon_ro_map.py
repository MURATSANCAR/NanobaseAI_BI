#!/usr/bin/env python3
"""Build neon-ro.datasources.json + schema hints from connection.local.json (server-only)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg2

SECRETS = Path(os.environ.get("SECRETS_ROOT", "/data/nanobaseai/bi/secrets"))


def main() -> None:
    raw = json.loads((SECRETS / "connection.local.json").read_text(encoding="utf-8"))
    sources = raw.get("sources") or raw
    out: dict = {"sources": {}}

    for sid, s in sources.items():
        if not isinstance(s, dict):
            continue
        user = s.get("user") or s.get("username")
        pw = s.get("password") or ""
        host = s.get("host")
        port = int(s.get("port") or 5432)
        db = s.get("database") or "neondb"
        if not (host and user and pw):
            print("skip", sid)
            continue

        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=db,
            user=user,
            password=pw,
            sslmode="require",
            connect_timeout=20,
        )
        conn.set_session(readonly=True, autocommit=True)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_type = %s
              AND table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY 1, 2
            LIMIT 200
            """,
            ("BASE TABLE",),
        )
        tables = cur.fetchall()
        cur.execute(
            """
            SELECT table_schema, table_name
            FROM information_schema.views
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY 1, 2
            LIMIT 100
            """
        )
        views = cur.fetchall()
        sample_cols: dict[str, list[str]] = {}
        for sch, name in tables[:40]:
            cur.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
                LIMIT 12
                """,
                (sch, name),
            )
            sample_cols[f"{sch}.{name}"] = [f"{c}:{t}" for c, t in cur.fetchall()]
        cur.close()
        conn.close()

        allowed: set[str] = set()
        for sch, name in tables + views:
            allowed.add(name)
            allowed.add(f"{sch}.{name}")

        print(f"{sid}: tables={len(tables)} views={len(views)} allowlist={len(allowed)}")
        for k, v in list(sample_cols.items())[:6]:
            print(" ", k, ", ".join(v[:5]))

        pw_file = SECRETS / f"neon-{sid}.password"
        pw_file.write_text(pw.strip() + "\n", encoding="utf-8")
        pw_file.chmod(0o600)

        out["sources"][sid] = {
            "host": host,
            "port": port,
            "database": db,
            "user": user,
            "password_file": str(pw_file),
            "sslmode": "require",
            "allowed_tables": sorted(allowed),
            "label": s.get("label") or sid,
            "schema_sample": sample_cols,
            "note": "SELECT-only via Query Gateway; prefer dedicated RO role later",
        }

    gateway = {
        "sources": {
            sid: {k: v for k, v in cfg.items() if k != "schema_sample"}
            for sid, cfg in out["sources"].items()
        }
    }
    map_path = SECRETS / "neon-ro.datasources.json"
    map_path.write_text(json.dumps(gateway, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    map_path.chmod(0o600)

    hints = {sid: cfg.get("schema_sample") or {} for sid, cfg in out["sources"].items()}
    hints_path = SECRETS / "neon-schema-hints.json"
    hints_path.write_text(json.dumps(hints, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    hints_path.chmod(0o600)

    print("wrote", map_path)
    print("wrote", hints_path)


if __name__ == "__main__":
    main()
