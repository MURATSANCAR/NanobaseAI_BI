# Oracle Privilege Model

| Account | Purpose | Notes |
|---------|---------|-------|
| `NANOBASE_METADATA_RO` | ALL_* metadata + controlled profiling | No DML on business tables |
| `NANOBASE_PLAN_RO` | EXPLAIN PLAN + PLAN_TABLE | No business DML |
| `NANOBASE_QUERY_RO` | SELECT on reporting objects under VPD | Read-only transaction |

Query account must not hold PLAN_TABLE write if plan user is configured separately.
