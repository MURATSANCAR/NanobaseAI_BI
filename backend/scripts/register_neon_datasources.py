#!/usr/bin/env python3
"""Register ERP + Sigorta Neon datasources into a running DB-GPT instance."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
LOCAL_CONN = REPO / "configs" / "sources" / "local" / "connection.local.json"
LOCAL_ENV = REPO / "configs" / "sources" / "local" / "neon-dsns.env"

DEFAULT_BASE = os.environ.get("DBGPT_BASE", "http://127.0.0.1:5670")


def _load_sources() -> dict:
    if LOCAL_CONN.is_file():
        data = json.loads(LOCAL_CONN.read_text(encoding="utf-8"))
        return data.get("sources") or {}
    if not LOCAL_ENV.is_file():
        raise SystemExit(f"Missing {LOCAL_CONN} and {LOCAL_ENV}")
    vals: dict[str, str] = {}
    for line in LOCAL_ENV.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            vals[k] = v
    return {
        "erp": {
            "id": "erp",
            "label": "ERP (Neon)",
            "host": "ep-little-hill-at81gpda.c-9.us-east-1.aws.neon.tech",
            "port": 5432,
            "database": "neondb",
            "username": "neondb_owner",
            "password": vals["BI_ERP_PASSWORD"],
        },
        "sigorta": {
            "id": "sigorta",
            "label": "Sigorta (Neon)",
            "host": "ep-sweet-star-adwrp395.c-2.us-east-1.aws.neon.tech",
            "port": 5432,
            "database": "neondb",
            "username": "neondb_owner",
            "password": vals["BI_SIGORTA_PASSWORD"],
        },
    }


def _http_json(method: str, url: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} -> {e.code}: {raw}") from e


def _wait_ready(base: str, attempts: int = 60) -> None:
    url = f"{base.rstrip('/')}/api/v1/chat/db/support/type"
    for i in range(attempts):
        try:
            _http_json("GET", url)
            return
        except Exception:
            time.sleep(1)
            if i == attempts - 1:
                raise SystemExit(f"DB-GPT not ready at {base}")


def _upsert(base: str, src: dict) -> None:
    sid = src["id"]
    payload = {
        "db_type": "postgresql",
        "db_name": sid,
        "db_host": src["host"],
        "db_port": int(src.get("port") or 5432),
        "db_user": src["username"],
        "db_pwd": src["password"],
        "comment": src.get("label") or sid,
        "ext_config": {
            "database": src.get("database") or "neondb",
            "schema": "public",
        },
    }
    # Prefer v2 serve API (keeps ext_config)
    create_url = f"{base.rstrip('/')}/api/v2/serve/datasources"
    try:
        res = _http_json("POST", create_url, payload)
        print(f"created {sid}: ok={res.get('success', res)}")
        return
    except RuntimeError as e:
        msg = str(e)
        if "already exists" not in msg and "400" not in msg:
            # Try legacy add, then note
            print(f"v2 create {sid} failed ({e}); trying edit/update…")
        else:
            print(f"{sid} exists — updating…")
    try:
        res = _http_json("PUT", create_url, payload)
        print(f"updated {sid}: ok={res.get('success', res)}")
        return
    except RuntimeError as e:
        # Fallback: legacy add/edit (ext_config may be dropped — patch still needed for id≠db)
        legacy = {
            "db_type": payload["db_type"],
            "db_name": payload["db_name"],
            "db_host": payload["db_host"],
            "db_port": payload["db_port"],
            "db_user": payload["db_user"],
            "db_pwd": payload["db_pwd"],
            "comment": payload["comment"],
            "file_path": "",
        }
        try:
            res = _http_json("POST", f"{base.rstrip('/')}/api/v1/chat/db/add", legacy)
            print(f"legacy add {sid}: {res}")
        except RuntimeError:
            res = _http_json("POST", f"{base.rstrip('/')}/api/v1/chat/db/edit", legacy)
            print(f"legacy edit {sid}: {res}")
        # Persist ext_config into SQLite meta so the patch can remap database name
        _patch_sqlite_ext_config(sid, payload["ext_config"])


def _patch_sqlite_ext_config(db_name: str, ext_config: dict) -> None:
    import sqlite3

    db_path = ROOT / ".dbgpt" / "pilot" / "meta_data" / "dbgpt.db"
    if not db_path.is_file():
        print(f"warn: meta db not found at {db_path}; restart DB-GPT after register")
        return
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE connect_config SET ext_config = ? WHERE db_name = ?",
            (json.dumps(ext_config, ensure_ascii=False), db_name),
        )
        conn.commit()
        print(f"sqlite ext_config set for {db_name}")
    finally:
        conn.close()


def _probe_psycopg(src: dict) -> None:
    """Fast connectivity check (avoids DB-GPT full schema reflection timeout)."""
    try:
        import psycopg2
    except ImportError:
        print(f"skip probe {src['id']}: psycopg2 not installed")
        return
    host = src["host"]
    port = int(src.get("port") or 5432)
    user = src["username"]
    password = src["password"]
    database = src.get("database") or "neondb"
    dsn = (
        f"host={host} port={port} dbname={database} user={user} "
        f"password={password} sslmode=require connect_timeout=20"
    )
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("select current_database(), current_user")
    db, usr = cur.fetchone()
    cur.close()
    conn.close()
    print(f"probe {src['id']}: ok db={db} user={usr}")


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE
    sources = _load_sources()
    _wait_ready(base)
    for sid in ("erp", "sigorta"):
        src = sources.get(sid)
        if not src:
            raise SystemExit(f"missing source {sid}")
        # Ensure password present
        if not src.get("password"):
            raise SystemExit(f"{sid} password missing in local connection file")
        _upsert(base, src)
        _probe_psycopg(src)
    listed = _http_json("GET", f"{base.rstrip('/')}/api/v1/chat/db/list")
    names = [d.get("db_name") for d in (listed.get("data") or [])]
    print("registered datasources:", names)


if __name__ == "__main__":
    main()
