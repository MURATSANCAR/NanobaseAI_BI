#!/usr/bin/env python3
"""Probe a SQL Server instance and list databases/tables.

Credentials are read from env (MSSQL_HOST, MSSQL_PORT, MSSQL_USER, MSSQL_PASSWORD,
optional MSSQL_DB), falling back to configs/.env.local (gitignored).
Never put the password on the command line or in git.
"""
import os, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
env_file = ROOT / "configs" / ".env.local"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

host = os.environ.get("MSSQL_HOST", "192.168.0.155")
port = int(os.environ.get("MSSQL_PORT", "1433"))
user = os.environ.get("MSSQL_USER")
pwd = os.environ.get("MSSQL_PASSWORD")
db = os.environ.get("MSSQL_DB", "master")
if not user or not pwd:
    sys.exit("MSSQL_USER / MSSQL_PASSWORD not set (put them in configs/.env.local)")

import pymssql
conn = pymssql.connect(server=host, port=port, user=user, password=pwd,
                       database=db, login_timeout=10, tds_version="7.4")
cur = conn.cursor()
cur.execute("SELECT @@VERSION")
print("VERSION:", cur.fetchone()[0].splitlines()[0])
cur.execute("SELECT name FROM sys.databases WHERE database_id > 4 ORDER BY name")
dbs = [r[0] for r in cur.fetchall()]
print("DATABASES:", dbs)
target = sys.argv[1] if len(sys.argv) > 1 else (dbs[0] if dbs else None)
if target:
    cur.execute(f"USE [{target}]")
    cur.execute("""SELECT s.name, t.name, SUM(p.rows)
                   FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id
                   JOIN sys.partitions p ON p.object_id=t.object_id AND p.index_id IN (0,1)
                   GROUP BY s.name, t.name ORDER BY 3 DESC""")
    rows = cur.fetchall()
    print(f"\n{target}: {len(rows)} tables")
    for s, t, n in rows[:60]:
        print(f"  {s}.{t}  ({n} rows)")
conn.close()
