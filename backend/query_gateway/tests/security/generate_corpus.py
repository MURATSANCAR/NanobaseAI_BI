"""Generate ≥500 malicious SQL fixtures for security corpus."""

from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).parent / "corpus" / "malicious.sql.jsonl"

DML = [
    "INSERT INTO reporting.invoice VALUES (1)",
    "UPDATE reporting.invoice SET total=0",
    "DELETE FROM reporting.invoice",
    "MERGE INTO reporting.invoice a USING reporting.invoice b ON a.id=b.id WHEN MATCHED THEN UPDATE SET total=0",
    "WITH x AS (DELETE FROM reporting.invoice RETURNING *) SELECT * FROM x",
    "WITH x AS (UPDATE reporting.invoice SET total=0 RETURNING *) SELECT * FROM x",
    "WITH x AS (INSERT INTO reporting.invoice SELECT * FROM reporting.invoice RETURNING *) SELECT * FROM x",
]

DDL = [
    "DROP TABLE reporting.invoice",
    "CREATE TABLE reporting.evil (id int)",
    "ALTER TABLE reporting.invoice ADD COLUMN x int",
    "TRUNCATE reporting.invoice",
    "CREATE INDEX idx ON reporting.invoice(id)",
    "GRANT SELECT ON reporting.invoice TO public",
    "REVOKE ALL ON reporting.invoice FROM public",
]

MULTI = [
    "SELECT 1; DROP TABLE reporting.invoice",
    "SELECT 1; DELETE FROM reporting.invoice",
    "SELECT id FROM reporting.invoice; UPDATE reporting.invoice SET total=0",
    "SELECT 1;; SELECT 2",
]

CTE = [
    "WITH deleted AS (DELETE FROM reporting.invoice RETURNING *) SELECT * FROM deleted",
    "WITH u AS (UPDATE reporting.invoice SET total=1 RETURNING id) SELECT * FROM u",
    "WITH i AS (INSERT INTO reporting.invoice(id) VALUES (1) RETURNING *) SELECT * FROM i",
]

COMMENTS = [
    "SELECT 1 /* */; DROP TABLE reporting.invoice",
    "SELECT pg_sleep(1) -- comment\n",
    "SELECT 1;--\nDELETE FROM reporting.invoice",
]

FUNCS = [
    "SELECT pg_sleep(30)",
    "SELECT pg_read_file('/etc/passwd')",
    "SELECT pg_ls_dir('.')",
    "SELECT lo_import('/etc/passwd')",
    "SELECT dblink('host=x','select 1')",
    "SELECT set_config('app.tenant_id','x',false)",
    "SELECT pg_terminate_backend(1)",
    "SELECT pg_cancel_backend(1)",
    "SELECT current_setting('secret')",
]

LOCKS = [
    "SELECT * FROM reporting.invoice FOR UPDATE",
    "SELECT * FROM reporting.invoice FOR SHARE",
    "SELECT id FROM reporting.invoice FOR UPDATE NOWAIT",
]

SCHEMA = [
    "SELECT * FROM pg_catalog.pg_user",
    "SELECT * FROM pg_shadow",
    "SELECT * FROM information_schema.tables",
    "SELECT * FROM pg_authid",
    "COPY reporting.invoice TO '/tmp/x'",
    "SELECT * INTO evil FROM reporting.invoice",
]

SESSION = [
    "SET ROLE postgres",
    "RESET ALL",
    "SHOW ALL",
    "LISTEN x",
    "NOTIFY x",
    "VACUUM reporting.invoice",
    "ANALYZE reporting.invoice",
    "DISCARD ALL",
]

WILDCARD_JOIN = [
    "SELECT * FROM reporting.invoice",
    "SELECT * FROM reporting.invoice CROSS JOIN reporting.customer",
    "SELECT a.id FROM reporting.invoice a JOIN reporting.customer b ON TRUE",
]


def expand(category: str, seeds: list[str], n: int) -> list[dict]:
    out = []
    i = 0
    while len(out) < n:
        base = seeds[i % len(seeds)]
        variants = [
            base,
            base.upper(),
            f"  {base}  ",
            base.replace(" ", "  "),
            f"/*x*/{base}",
            base.replace("SELECT", "Select") if "SELECT" in base.upper() else base,
        ]
        for v in variants:
            out.append({"category": category, "sql": v})
            if len(out) >= n:
                break
        i += 1
    return out


def main() -> None:
    rows: list[dict] = []
    rows += expand("DML", DML, 50)
    rows += expand("DDL", DDL, 50)
    rows += expand("MULTI", MULTI, 40)
    rows += expand("CTE", CTE, 40)
    rows += expand("COMMENT", COMMENTS, 40)
    rows += expand("FUNCTION", FUNCS, 60)
    rows += expand("FILE", FUNCS[:4], 40)
    rows += expand("SESSION", SESSION, 40)
    rows += expand("LOCK", LOCKS, 40)
    rows += expand("SCHEMA", SCHEMA, 50)
    rows += expand("UNICODE", [s + "\u200b" for s in DML], 50)
    # pad to ≥500
    while len(rows) < 500:
        rows.append({"category": "PAD", "sql": f"DELETE FROM reporting.invoice WHERE id={len(rows)}"})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    import json

    with OUT.open("w", encoding="utf-8") as f:
        for r in rows[:520]:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {min(520, len(rows))} -> {OUT}")


if __name__ == "__main__":
    main()
