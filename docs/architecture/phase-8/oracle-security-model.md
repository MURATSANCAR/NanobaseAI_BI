# Oracle Security Model (immutable)

1. DB-GPT does not execute Oracle SQL in production.
2. SYS / SYSTEM / SYSBACKUP / SYSDG / SYSKM / DBSNMP / ADMIN forbidden.
3. Prefer `NANOBASE_REPORTING` reporting owner — no raw ERP schema exposure.
4. Database links (`@`, DB_LINK) rejected at AST/token layer.
5. PL/SQL (`BEGIN`, `DECLARE`, `CALL`, `EXEC`, `EXECUTE IMMEDIATE`, `DBMS_SQL`) rejected.
6. Optimizer hints (`/*+ */`) rejected.
7. `SELECT … FOR UPDATE` / `LOCK TABLE` rejected.
8. Owner allowlist enforced in scanner, Qdrant, AWEL retrieval, and Gateway policy.
