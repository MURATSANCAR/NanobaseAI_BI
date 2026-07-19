#!/usr/bin/env python3
"""Create dedicated Neon RO roles (bi_{sid}_ro) and update neon-ro.datasources.json."""

from __future__ import annotations

import json
import os
import secrets
import string
from pathlib import Path

import psycopg2

SECRETS = Path(os.environ.get("SECRETS_ROOT", "/data/nanobaseai/bi/secrets"))


def gen_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "NbRo_" + "".join(secrets.choice(alphabet) for _ in range(24))


def main() -> None:
    raw = json.loads((SECRETS / "connection.local.json").read_text(encoding="utf-8"))
    results: dict[str, dict[str, str]] = {}

    for sid, s in (raw.get("sources") or {}).items():
        if not isinstance(s, dict):
            continue
        owner = s.get("user") or s.get("username")
        owner_pw = s.get("password") or ""
        host = s["host"]
        port = int(s.get("port") or 5432)
        db = s.get("database") or "neondb"
        ro_user = f"bi_{sid}_ro"
        ro_pw = gen_password()

        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=db,
            user=owner,
            password=owner_pw,
            sslmode="require",
            connect_timeout=20,
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (ro_user,))
        if cur.fetchone():
            cur.execute(f"ALTER ROLE {ro_user} WITH LOGIN PASSWORD %s", (ro_pw,))
            print(f"{sid}: updated {ro_user}")
        else:
            cur.execute(f"CREATE ROLE {ro_user} LOGIN PASSWORD %s", (ro_pw,))
            print(f"{sid}: created {ro_user}")

        cur.execute(f"GRANT CONNECT ON DATABASE {db} TO {ro_user}")
        cur.execute(f"GRANT USAGE ON SCHEMA public TO {ro_user}")
        cur.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {ro_user}")
        cur.execute(f"GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO {ro_user}")
        cur.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {ro_user}"
        )
        cur.execute(
            f"REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM {ro_user}"
        )
        cur.close()
        conn.close()

        # verify login + SELECT
        tconn = psycopg2.connect(
            host=host,
            port=port,
            dbname=db,
            user=ro_user,
            password=ro_pw,
            sslmode="require",
            connect_timeout=20,
        )
        tconn.set_session(readonly=True, autocommit=True)
        tcur = tconn.cursor()
        tcur.execute("SELECT current_user")
        assert tcur.fetchone()[0] == ro_user
        tcur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            LIMIT 1
            """
        )
        tname = tcur.fetchone()[0]
        tcur.execute(f"SELECT COUNT(*) FROM {tname}")
        _ = tcur.fetchone()
        tcur.close()
        tconn.close()

        # verify INSERT denied
        wconn = psycopg2.connect(
            host=host,
            port=port,
            dbname=db,
            user=ro_user,
            password=ro_pw,
            sslmode="require",
            connect_timeout=20,
        )
        wconn.autocommit = True
        wcur = wconn.cursor()
        denied = False
        try:
            wcur.execute(f"INSERT INTO {tname} DEFAULT VALUES")
        except Exception as e:
            denied = True
            print(f"  {sid}: INSERT denied OK ({str(e).splitlines()[0][:70]})")
        wcur.close()
        wconn.close()
        if not denied:
            raise SystemExit(f"{sid}: INSERT unexpectedly allowed on {tname}")

        pw_file = SECRETS / f"neon-{sid}.password"
        pw_file.write_text(ro_pw + "\n", encoding="utf-8")
        pw_file.chmod(0o600)
        results[sid] = {"user": ro_user, "password_file": str(pw_file), "sample_table": tname}

    map_path = SECRETS / "neon-ro.datasources.json"
    if map_path.is_file():
        m = json.loads(map_path.read_text(encoding="utf-8"))
    else:
        m = {"sources": {}}
    for sid, info in results.items():
        cfg = (m.setdefault("sources", {})).setdefault(sid, {})
        # preserve host/port/database/allowlist from existing map or connection.local
        src = (raw.get("sources") or {}).get(sid) or {}
        cfg.setdefault("host", src.get("host"))
        cfg.setdefault("port", int(src.get("port") or 5432))
        cfg.setdefault("database", src.get("database") or "neondb")
        cfg.setdefault("sslmode", "require")
        cfg["user"] = info["user"]
        cfg["password_file"] = info["password_file"]
        cfg["note"] = "dedicated RO role bi_*_ro; SELECT-only grants"
        cfg["label"] = src.get("label") or sid
    map_path.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    map_path.chmod(0o600)
    print("updated", map_path)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
