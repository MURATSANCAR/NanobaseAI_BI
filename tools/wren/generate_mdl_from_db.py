#!/usr/bin/env python3
"""WrenAI `generate-mdl` skill'inin Faz 1-5'ini otomatik yürütür: canlı veritabanını tarar,
tipleri `wren.type_mapping.parse_types` ile normalleştirir, tam bir Wren projesi üretir
(wren_project.yml + models/* + relationships.yml + knowledge/ iskeleti), sonra validate/build/index.

Yeni müşteri onboarding'i budur — elle YAML yazılmaz.

Kullanım:
  python generate_mdl_from_db.py --connection /path/conn.json --out /path/project --name musteri \
      [--schema dbo] [--tables 'LG_411_%'] [--max-tables 200]
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys
from pathlib import Path

VENV = Path("/data/nanobaseai/bi/wren-venv/bin")


def q(v: object) -> str:
    return json.dumps(v, ensure_ascii=False)


def connect(conn: dict):
    ds = conn.get("datasource", "mssql")
    if ds == "mssql":
        import pyodbc
        cs = "DRIVER=%s;SERVER=%s,%s;DATABASE=%s;UID=%s;PWD=%s;TDS_Version=%s" % (
            conn.get("driver", "FreeTDS"), conn["host"], conn["port"], conn["database"], conn["user"], conn["password"], conn.get("tds_version", "7.4"))
        for k, v in (conn.get("kwargs") or {}).items():
            cs += ";%s=%s" % (k, v)
        return pyodbc.connect(cs, timeout=30), ds
    if ds in ("postgres", "postgresql"):
        import psycopg
        return psycopg.connect(host=conn["host"], port=conn["port"], dbname=conn["database"], user=conn["user"], password=conn["password"]), "postgres"
    raise SystemExit("desteklenmeyen datasource: %s (mssql/postgres)" % ds)


# INFORMATION_SCHEMA hem SQL Server hem PostgreSQL'de aynı: tek sorgu seti yeter.
Q_COLUMNS = """
SELECT c.TABLE_SCHEMA, c.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE, c.CHARACTER_MAXIMUM_LENGTH,
       c.NUMERIC_PRECISION, c.NUMERIC_SCALE, c.IS_NULLABLE, c.ORDINAL_POSITION
FROM INFORMATION_SCHEMA.COLUMNS c
JOIN INFORMATION_SCHEMA.TABLES t ON t.TABLE_SCHEMA = c.TABLE_SCHEMA AND t.TABLE_NAME = c.TABLE_NAME
WHERE t.TABLE_TYPE IN ('BASE TABLE','VIEW') AND c.TABLE_SCHEMA = ?{TABLE_FILTER}
ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION
"""
Q_PK = """
SELECT tc.TABLE_NAME, kcu.COLUMN_NAME
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu ON kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME AND kcu.TABLE_SCHEMA = tc.TABLE_SCHEMA
WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY' AND tc.TABLE_SCHEMA = ?
ORDER BY tc.TABLE_NAME, kcu.ORDINAL_POSITION
"""
Q_FK = """
SELECT tc.TABLE_NAME, kcu.COLUMN_NAME, ccu.TABLE_NAME AS REF_TABLE, ccu.COLUMN_NAME AS REF_COLUMN, tc.CONSTRAINT_NAME
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu ON kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME AND kcu.TABLE_SCHEMA = tc.TABLE_SCHEMA
JOIN INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE ccu ON ccu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
WHERE tc.CONSTRAINT_TYPE = 'FOREIGN KEY' AND tc.TABLE_SCHEMA = ?
"""


def raw_type(row: dict) -> str:
    t = (row["DATA_TYPE"] or "varchar").lower()
    if row.get("CHARACTER_MAXIMUM_LENGTH") and int(row["CHARACTER_MAXIMUM_LENGTH"]) > 0:
        return "%s(%d)" % (t, int(row["CHARACTER_MAXIMUM_LENGTH"]))
    if t in ("decimal", "numeric") and row.get("NUMERIC_PRECISION"):
        return "%s(%d,%d)" % (t, int(row["NUMERIC_PRECISION"]), int(row.get("NUMERIC_SCALE") or 0))
    return t


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--connection", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--schema", default="dbo")
    ap.add_argument("--tables", default=None, help="SQL LIKE deseni, ör. 'LG_411_%%'")
    ap.add_argument("--max-tables", type=int, default=300)
    a = ap.parse_args()

    conn_cfg = json.loads(Path(a.connection).read_text(encoding="utf-8"))
    con, ds = connect(conn_cfg)
    cur = con.cursor()

    # Faz 2 — şema keşfi
    sql = Q_COLUMNS.replace("{TABLE_FILTER}", " AND c.TABLE_NAME LIKE ?" if a.tables else "")
    cur.execute(sql, (a.schema, a.tables) if a.tables else (a.schema,))
    cols_desc = [d[0] for d in cur.description]
    rows = [dict(zip(cols_desc, r)) for r in cur.fetchall()]
    tables: dict[str, list[dict]] = {}
    for r in rows:
        tables.setdefault(r["TABLE_NAME"], []).append(r)
    keep = sorted(tables)[: a.max_tables]
    tables = {t: tables[t] for t in keep}

    cur.execute(Q_PK, (a.schema,))
    pks: dict[str, list[str]] = {}
    for t, c in cur.fetchall():
        pks.setdefault(t, []).append(c)
    try:
        cur.execute(Q_FK, (a.schema,))
        fks = [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    except Exception:
        fks = []
    con.close()
    print("keşif: %d tablo, %d kolon, %d PK, %d FK" % (len(tables), sum(len(v) for v in tables.values()), len(pks), len(fks)))

    # Faz 3 — tip normalizasyonu (WrenAI'nin kendi haritası)
    from wren.type_mapping import parse_types
    norm: dict[str, dict[str, str]] = {}
    for t, cs in tables.items():
        payload = [{"column": c["COLUMN_NAME"], "raw_type": raw_type(c)} for c in cs]
        try:
            out = parse_types(payload, dialect=ds)
            norm[t] = {p["column"]: (o.get("type") or "VARCHAR") for p, o in zip(payload, out)}
        except Exception as e:  # noqa: BLE001
            print("  parse_types düştü (%s): %s" % (t, str(e)[:120]))
            norm[t] = {p["column"]: "VARCHAR" for p in payload}

    # Faz 4 — proje iskeleti + model YAML'ları
    P = Path(a.out).resolve()
    P.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(VENV / "wren"), "context", "init", "--path", str(P)], capture_output=True, text=True)
    (P / "wren_project.yml").write_text(
        "schema_version: 5\nname: %s\nversion: \"1.0\"\ncatalog: wren\nschema: public\ndata_source: %s\n" % (q(a.name), ds), encoding="utf-8")

    model_name = lambda t: re.sub(r"[^A-Za-z0-9_]", "_", "%s_%s" % (a.schema, t))
    for t, cs in tables.items():
        mn = model_name(t)
        y = ["name: %s" % q(mn), "table_reference:"]
        if conn_cfg.get("database") and ds == "mssql":
            y.append("  catalog: %s" % q(conn_cfg["database"]))
        y += ["  schema: %s" % q(a.schema), "  table: %s" % q(t)]
        pk = pks.get(t, [])
        if len(pk) == 1:
            y.append("primary_key: %s" % q(pk[0]))
        y.append("columns:")
        for c in cs:
            cn = c["COLUMN_NAME"]
            y.append("  - name: %s" % q(cn))
            y.append("    type: %s" % q(norm[t].get(cn, "VARCHAR")))
            if str(c.get("IS_NULLABLE", "YES")).upper() == "NO":
                y.append("    not_null: true")
            if cn in pk and len(pk) == 1:
                y.append("    is_primary_key: true")
        d = P / "models" / mn
        d.mkdir(parents=True, exist_ok=True)
        (d / "metadata.yml").write_text("\n".join(y) + "\n", encoding="utf-8")

    # Faz 4/3 — FK'lerden ilişkiler
    rel_lines = ["relationships:"]
    seen = set()
    for fk in fks:
        src, dst = model_name(fk["TABLE_NAME"]), model_name(fk["REF_TABLE"])
        if src not in {model_name(t) for t in tables} or dst not in {model_name(t) for t in tables}:
            continue
        name = re.sub(r"[^A-Za-z0-9_]", "_", "%s_%s_%s" % (fk["TABLE_NAME"], fk["COLUMN_NAME"], fk["REF_TABLE"])).lower()
        if name in seen:
            continue
        seen.add(name)
        rel_lines += ["  - name: %s" % q(name), "    models:", "      - %s" % q(src), "      - %s" % q(dst),
                      "    join_type: MANY_TO_ONE",
                      "    condition: %s" % q('"%s".%s = "%s".%s' % (src, fk["COLUMN_NAME"], dst, fk["REF_COLUMN"]))]
    (P / "relationships.yml").write_text("\n".join(rel_lines) + "\n", encoding="utf-8")

    for sub in ("rules", "sql", "glossary", "metrics", "caveats"):
        (P / "knowledge" / sub).mkdir(parents=True, exist_ok=True)
    (P / "knowledge" / "knowledge.yml").write_text("schema_version: 1\n", encoding="utf-8")
    (P / "knowledge" / "rules" / "README.md").write_text(
        "# İş kuralları\n\nBu dosyayı `wren skills get enrich-context` ile doldurun: enum anlamları, birimler,\nvarsayılan filtreler, kanonik tablolar, para birimi ve zaman kuralları.\n", encoding="utf-8")
    (P / ".gitignore").write_text("target/\n.wren/\n", encoding="utf-8")
    print("proje yazıldı: %s (%d model, %d ilişki)" % (P, len(tables), len(seen)))

    # Faz 5 — doğrula / derle
    for step in (("context", "validate"), ("context", "build")):
        r = subprocess.run([str(VENV / "wren"), *step, "--path", str(P)] if step[0] == "context" else [str(VENV / "wren"), *step], cwd=P, capture_output=True, text=True)
        print("== wren %s: %s" % (" ".join(step), ((r.stdout + r.stderr).strip().splitlines() or [""])[-1][:160]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
