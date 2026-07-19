"""Generate ≥600 malicious Oracle SQL fixtures for security corpus."""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).parent / "corpus" / "oracle_malicious.sql.jsonl"

DML = [
    "INSERT INTO NANOBASE_REPORTING.V_INVOICE VALUES (1)",
    "UPDATE NANOBASE_REPORTING.V_INVOICE SET TOTAL_AMOUNT=0",
    "DELETE FROM NANOBASE_REPORTING.V_INVOICE",
    "MERGE INTO NANOBASE_REPORTING.V_INVOICE A USING NANOBASE_REPORTING.V_INVOICE B ON (A.INVOICE_ID=B.INVOICE_ID) WHEN MATCHED THEN UPDATE SET TOTAL_AMOUNT=0",
    "WITH X AS (DELETE FROM NANOBASE_REPORTING.V_INVOICE RETURNING *) SELECT * FROM X",
]

DDL = [
    "DROP TABLE NANOBASE_REPORTING.V_INVOICE",
    "CREATE TABLE NANOBASE_REPORTING.EVIL (ID NUMBER)",
    "ALTER TABLE NANOBASE_REPORTING.V_INVOICE ADD X NUMBER",
    "TRUNCATE TABLE NANOBASE_REPORTING.V_INVOICE",
    "GRANT SELECT ON NANOBASE_REPORTING.V_INVOICE TO PUBLIC",
    "REVOKE ALL ON NANOBASE_REPORTING.V_INVOICE FROM PUBLIC",
    "COMMENT ON TABLE NANOBASE_REPORTING.V_INVOICE IS 'x'",
    "ANALYZE TABLE NANOBASE_REPORTING.V_INVOICE COMPUTE STATISTICS",
]

PLSQL = [
    "BEGIN NULL; END;",
    "DECLARE X NUMBER; BEGIN NULL; END;",
    "BEGIN EXECUTE IMMEDIATE 'DROP TABLE X'; END;",
    "CALL DBMS_LOCK.SLEEP(10)",
    "EXEC DBMS_OUTPUT.PUT_LINE('x')",
    "EXECUTE IMMEDIATE 'SELECT 1 FROM DUAL'",
    "BEGIN DBMS_SQL.OPEN_CURSOR; END;",
]

PACKAGES = [
    "SELECT UTL_HTTP.REQUEST('https://example.com') FROM DUAL",
    "SELECT UTL_FILE.FOPEN('/tmp','x','R') FROM DUAL",
    "SELECT UTL_TCP.OPEN_CONNECTION('evil',80) FROM DUAL",
    "SELECT UTL_INADDR.GET_HOST_ADDRESS('evil') FROM DUAL",
    "SELECT DBMS_PIPE.RECEIVE_MESSAGE('P',1) FROM DUAL",
    "SELECT DBMS_LOCK.SLEEP(30) FROM DUAL",
    "SELECT DBMS_LDAP.INIT('x',389) FROM DUAL",
    "SELECT DBMS_JAVA.RUNJAVA('x') FROM DUAL",
    "SELECT DBMS_SCHEDULER.CREATE_JOB('J') FROM DUAL",
    "SELECT DBMS_JOB.SUBMIT(1,'x') FROM DUAL",
]

DBLINK = [
    "SELECT * FROM CUSTOMER@REMOTE_DATABASE",
    "SELECT * FROM NANOBASE_REPORTING.V_INVOICE@REMOTE_DB",
    "SELECT A.* FROM NANOBASE_REPORTING.V_INVOICE@DB_LINK A",
    "SELECT * FROM SYS.DUAL@REMOTE",
]

HINTS = [
    "SELECT /*+ PARALLEL(32) */ INVOICE_ID FROM NANOBASE_REPORTING.V_INVOICE",
    "SELECT /*+ FULL(I) */ * FROM NANOBASE_REPORTING.V_INVOICE I",
    "SELECT /*+ INDEX(I PK) */ INVOICE_ID FROM NANOBASE_REPORTING.V_INVOICE I",
    "SELECT /*+ LEADING(A B) */ A.ID FROM NANOBASE_REPORTING.V_INVOICE A",
]

LOCKS = [
    "SELECT INVOICE_ID FROM NANOBASE_REPORTING.V_INVOICE FOR UPDATE",
    "SELECT INVOICE_ID FROM NANOBASE_REPORTING.V_INVOICE FOR UPDATE NOWAIT",
    "LOCK TABLE NANOBASE_REPORTING.V_INVOICE IN EXCLUSIVE MODE",
    "SELECT INVOICE_ID FROM NANOBASE_REPORTING.V_INVOICE FOR UPDATE WAIT 10",
]

CONNECT = [
    "SELECT LEVEL FROM DUAL CONNECT BY LEVEL <= 10",
    "SELECT * FROM NANOBASE_REPORTING.V_INVOICE START WITH INVOICE_ID=1 CONNECT BY PRIOR INVOICE_ID=PARENT_ID",
    "SELECT * FROM NANOBASE_REPORTING.V_INVOICE SAMPLE(10)",
    "SELECT * FROM NANOBASE_REPORTING.V_INVOICE AS OF TIMESTAMP SYSTIMESTAMP",
]

SESSION = [
    "ALTER SESSION SET CONTAINER = PDB2",
    "ALTER SESSION SET CURRENT_SCHEMA = SYS",
    "SET TRANSACTION READ WRITE",
]

SYNONYM = [
    "SELECT * FROM PUBLIC.ALL_USERS",
    "SELECT * FROM ALL_USERS",
    "SELECT * FROM SYS.USER$",
]

CTE_BYPASS = [
    "WITH X AS (UPDATE NANOBASE_REPORTING.V_INVOICE SET TOTAL_AMOUNT=0) SELECT * FROM X",
    "WITH X AS (INSERT INTO NANOBASE_REPORTING.V_INVOICE SELECT * FROM NANOBASE_REPORTING.V_INVOICE) SELECT 1 FROM X",
    "WITH X AS (DELETE FROM NANOBASE_REPORTING.V_INVOICE) SELECT 1 FROM DUAL",
]

QUOTED = [
    'SELECT "InvoiceId" FROM "CustomTable"',
    'SELECT * FROM "NANOBASE_REPORTING"."V_INVOICE" FOR UPDATE',
]

UNICODE = [
    "SELECT UTL_HTTP.REQUEST('https://x') FROM DUAL\u200b",
    "SELECT /*+ PARALLEL(8) */ INVOICE_ID FROM NANOBASE_REPORTING.V_INVOICE\ufeff",
]

RESOURCE = [
    "SELECT * FROM NANOBASE_REPORTING.V_INVOICE",
    "SELECT /*+ PARALLEL(64) */ * FROM NANOBASE_REPORTING.V_INVOICE A, NANOBASE_REPORTING.V_CUSTOMER B",
]


def expand(category: str, seeds: list[str], n: int) -> list[dict]:
    out: list[dict] = []
    i = 0
    while len(out) < n:
        base = seeds[i % len(seeds)]
        variants = [
            base,
            base.upper(),
            f"  {base}  ",
            base.replace(" ", "  "),
            f"/*x*/ {base}",
        ]
        for v in variants:
            out.append({"category": category, "sql": v, "expect": "REJECT"})
            if len(out) >= n:
                break
        i += 1
    return out


def main() -> None:
    rows: list[dict] = []
    rows += expand("DML", DML, 60)
    rows += expand("DDL", DDL, 60)
    rows += expand("PLSQL", PLSQL, 70)
    rows += expand("PACKAGE", PACKAGES, 80)
    rows += expand("DBLINK", DBLINK, 50)
    rows += expand("SYNONYM", SYNONYM, 40)
    rows += expand("HINT", HINTS, 40)
    rows += expand("LOCK", LOCKS, 40)
    rows += expand("CTE", CTE_BYPASS, 50)
    rows += expand("QUOTED", QUOTED, 40)
    rows += expand("UNICODE", UNICODE, 40)
    rows += expand("RESOURCE", RESOURCE, 30)
    rows += expand("CONNECT", CONNECT, 30)
    rows += expand("SESSION", SESSION, 20)
    while len(rows) < 600:
        rows.append(
            {
                "category": "PAD",
                "sql": f"DELETE FROM NANOBASE_REPORTING.V_INVOICE WHERE INVOICE_ID={len(rows)}",
                "expect": "REJECT",
            }
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for r in rows[:620]:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {min(620, len(rows))} -> {OUT}")


if __name__ == "__main__":
    main()
