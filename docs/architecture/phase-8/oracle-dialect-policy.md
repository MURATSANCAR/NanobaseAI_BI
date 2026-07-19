# Oracle Dialect Policy

- Parse: `sqlglot.parse_one(sql, read="oracle")` with unsupported_level RAISE intent (fail closed on unknown dangerous constructs via `parser_policy`).
- Row limit: `FETCH FIRST n ROWS ONLY` (Gateway rewrites to max_rows+1).
- Allowlist functions: see `backend/query_gateway/config/policies/oracle-functions.yaml`.
- Forbidden packages: UTL_*, DBMS_SQL, DBMS_LOCK, DBMS_PIPE, etc.
- Closed at launch: CONNECT BY, START WITH, MODEL, MATCH_RECOGNIZE, SAMPLE, XMLTABLE, Flashback.
- Controlled: PIVOT, UNPIVOT, JSON_TABLE, REGEXP_*.

AWEL profiles: `nanobase-oracle-sql-plan-v1`, `nanobase-oracle-sql-repair-v1`.
