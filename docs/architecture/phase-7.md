# Nanobase BI — Faz 7 Semantic catalog + verified SQL

## Goal

Business glossary / metrics / joins in `bi_meta`, plus a **verified SQL cache**
and thumbs feedback that can promote new verified entries. Chat hits the cache
before calling the LLM.

## Flow

```
FE chat/stream
  → nanobase_api
  → lookup bi_verified_sql (exact / soft match)
      ├─ hit  → Query Gateway validate + execute (+ EXPLAIN)
      └─ miss → llama.cpp SQL → Gateway
  → optional POST /api/v1/bi/query/feedback (promote_verified)
```

## Schema (`bi_meta`)

| Table | Purpose |
|-------|---------|
| `bi_glossary_entries` | Term → table/column definitions |
| `bi_metrics` | Certified metrics + golden SQL |
| `bi_joins` | Allowed join edges |
| `bi_verified_sql` | Question → SQL cache (new) |
| `bi_query_feedback` | ±1 ratings + promote flag (new) |

## API

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/v1/bi/semantic/status` | counts + enabled |
| GET | `/api/v1/bi/glossary` | `{ entries: BiGlossaryEntry[] }` |
| GET | `/api/v1/bi/semantic/metrics` | `{ metrics: [...] }` |
| GET | `/api/v1/bi/semantic/joins` | `{ joins: [...] }` |
| GET | `/api/v1/bi/semantic/verified-sql` | cache list |
| POST | `/api/v1/bi/query/feedback` | `{ question, rating±1, sql?, promote_verified? }` |

## Deploy (server)

```bash
# from /data/nanobaseai/bi/frontend after rsync
./scripts/server/deploy-semantic.sh
./scripts/server/deploy-nanobase-api.sh
./scripts/server/verify-semantic.sh
```

## Acceptance

1. `semantic/status` → `enabled: true`, glossary/metrics/verified_sql > 0
2. Chat `"Kaç müşteri var?"` → SSE `verified_cache_hit` / `sql_source=verified_sql`
3. Feedback with `promote_verified: true` inserts into `bi_verified_sql`
