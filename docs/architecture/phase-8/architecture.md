# Faz 8 Architecture — Oracle Hardened Path

```text
React → Nanobase API → Semantic Catalog / AWEL Oracle Plan
                         ↓
              Query Gateway /internal/v1/queries/*
                         ↓
         Oracle Policy → Plan Guard → VPD → RO txn → Result Guard
                         ↓
              NANOBASE_REPORTING (Oracle PDB)
```

DB-GPT / AWEL never open Oracle connections.

## Adapter package

`backend/query_gateway/infrastructure/oracle/`

| Module | Role |
|--------|------|
| profile | SERVICE_NAME, Thin/Thick, forbidden users/owners |
| pool | Thin Mode sync pool (min=max=5) |
| parser_policy | hints, DB link, PL/SQL, packages |
| plan_guard | EXPLAIN PLAN + PLAN_TABLE (separate plan user) |
| executor | SET TRANSACTION READ ONLY → execute → rollback |
| result_normalizer | NUMBER Decimal, CLOB≤4KB, BLOB reject |
| vpd | NANOBASE_CTX tenant context |
| metadata_scanner | ALL_* only |
| synonym_resolver | private allowlist, no public/remote/circular |

## Execution modes

| Env | Behavior |
|-----|----------|
| `ORACLE_EXECUTION_MODE=QUERY_GATEWAY` | Full execute (requires `ORACLE_EXECUTION_ENABLED=1` on API) |
| `ORACLE_EXECUTION_MODE=PLAN_ONLY` | Gateway rejects execute |
| `ORACLE_EXECUTION_MODE=METADATA_ONLY` | Scan only (ops) |

Legacy `/api/v1/query/*` Oracle path remains for transition; new work targets `/internal/v1`.
