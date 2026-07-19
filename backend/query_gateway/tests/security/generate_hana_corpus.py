"""Generate ≥600 malicious HANA SQL fixtures (all must REJECT)."""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).parent / "corpus" / "hana_malicious.sql.jsonl"

TEMPLATES: list[tuple[str, str]] = [
    ("dml", "INSERT INTO NANOBASE_REPORTING.CV_FINANCE VALUES ({i})"),
    ("dml", "UPDATE NANOBASE_REPORTING.CV_FINANCE SET X={i}"),
    ("dml", "DELETE FROM NANOBASE_REPORTING.CV_FINANCE WHERE ID={i}"),
    ("dml", "UPSERT NANOBASE_REPORTING.CV_FINANCE VALUES ({i})"),
    ("dml", "MERGE INTO NANOBASE_REPORTING.CV_FINANCE USING DUAL ON 1=1 WHEN MATCHED THEN UPDATE SET X={i}"),
    ("ddl", "CREATE TABLE EVIL_{i} (ID INT)"),
    ("ddl", "DROP VIEW NANOBASE_REPORTING.CV_FINANCE"),
    ("ddl", "ALTER TABLE NANOBASE_REPORTING.CV_FINANCE ADD X{i} INT"),
    ("ddl", "TRUNCATE TABLE NANOBASE_REPORTING.CV_FINANCE"),
    ("ddl", "GRANT SELECT ON NANOBASE_REPORTING.CV_FINANCE TO PUBLIC"),
    ("sqlscript", "DO BEGIN SELECT {i}; END;"),
    ("sqlscript", "CALL PROC_{i}()"),
    ("sqlscript", "EXEC PROC_{i}"),
    ("sqlscript", "EXECUTE IMMEDIATE 'SELECT {i}'"),
    ("sqlscript", "BEGIN DECLARE X INT; X := {i}; END;"),
    ("dynamic_sql", "SELECT EXECUTE_DYNAMIC('{i}') FROM DUMMY"),
    ("remote", "SELECT * FROM REMOTE_SOURCE.EVIL_{i}"),
    ("remote", "CREATE REMOTE SOURCE RS_{i} ADAPTER 'odbc'"),
    ("virtual", "SELECT * FROM VIRTUAL TABLE VT_{i}"),
    ("admin", "BACKUP DATA USING FILE ('x{i}')"),
    ("admin", "EXPORT NANOBASE_REPORTING.CV_FINANCE AS CSV INTO '/tmp/{i}'"),
    ("admin", "IMPORT FROM '/tmp/{i}'"),
    ("function_abuse", "SELECT SESSION_CONTEXT('APPLICATIONUSER') FROM DUMMY"),
    ("comment_bypass", "SELECT 1 FROM DUMMY; INSERT INTO T VALUES ({i})"),
    ("comment_bypass", "INSERT /* select */ INTO T VALUES ({i})"),
    ("unicode_bypass", "INSERT INTO NANOBASE_REPORTING.CV_FINANCE VALUES ({i})"),
    ("join_dos", "CALL EXPENSIVE_JOIN_{i}()"),
    ("system_schema", "SELECT * FROM SYS.TABLES"),
    ("system_schema", "SELECT * FROM _SYS_STATISTICS.HOST_RESOURCE_UTILIZATION_STATISTICS"),
    ("monitoring", "SELECT * FROM M_CONNECTIONS; DELETE FROM T"),
    ("raw_table", "SELECT * FROM ACDOCA WHERE MANDT='{i}'"),
    ("raw_table", "SELECT * FROM BKPF WHERE BELNR='{i}'"),
    ("raw_table", "SELECT * FROM BSEG WHERE BUZEI={i}"),
    ("procedure", "CREATE PROCEDURE P_{i} AS BEGIN SELECT 1; END"),
    ("revoke", "REVOKE ALL ON NANOBASE_REPORTING.CV_FINANCE FROM PUBLIC"),
]


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cases: list[dict] = []
    i = 0
    while len(cases) < 600:
        cat, tmpl = TEMPLATES[i % len(TEMPLATES)]
        sql = tmpl.format(i=i)
        cases.append({"category": cat, "sql": sql, "expect": "REJECT"})
        i += 1
    with OUT.open("w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"wrote {len(cases)} -> {OUT}")


if __name__ == "__main__":
    main()
