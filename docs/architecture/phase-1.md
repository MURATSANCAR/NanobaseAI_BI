# Nanobase BI — Faz 1 infra

## Scope

Production Text-to-SQL foundation on **`38.247.162.28`** (no Mac runtime).

| Component | How | Endpoint |
|-----------|-----|----------|
| Qdrant | Reused (contract stack) | `127.0.0.1:6333` |
| BGE-M3 | Reused embedding service | `127.0.0.1:8083` |
| Metadata Postgres | Existing `nanobase-bi-meta-db` | `127.0.0.1:5434` / `bi_meta` |
| Reporting Postgres | New compose service | `127.0.0.1:5435` / `bi_reporting` |

## Deploy

From repo on the server (`/data/nanobaseai/bi/frontend`):

```bash
./scripts/server/deploy-infra.sh
./scripts/server/verify-infra.sh
```

Secrets (chmod 600, never commit):

- `/data/nanobaseai/bi/secrets/reporting-admin.password`
- `/data/nanobaseai/bi/secrets/reporting-ro.password`
- `/data/nanobaseai/bi/secrets/bi-meta-db.password`

## Reporting RO contract

- Role: `bi_reporting_ro`
- Privileges: `CONNECT` + `USAGE` on `analytics` + `SELECT` on tables/views
- Writes must fail (verified by `verify-infra.sh`)

Seed schema: `analytics.customers|products|orders|order_items` + `analytics.v_order_revenue`.

## Notes

- Do **not** start a second Qdrant on `:6333`; BI collections share the existing instance (namespace by collection name, e.g. `bi_schema_*`).
- `bi_meta` data dir must be owned by UID **70** (postgres:16-alpine). `deploy-infra.sh` repairs ownership if needed.
- Live portal `/bi` and `nanobase-bi-bridge` are untouched in Faz 1.
