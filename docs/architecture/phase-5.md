# Nanobase BI — Faz 5 Query Gateway

## Role

All customer/reporting SQL execution goes through **Query Gateway** (`:8792`):

- sqlglot parse → SELECT/WITH only
- table allowlist
- LIMIT + `statement_timeout` + result size caps
- RO DB credentials from secrets (never from the request body)

Neon/ERP are **not** executable until registered in `/data/nanobaseai/bi/secrets/neon-ro.datasources.json`.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | liveness + registered datasources |
| GET | `/api/v1/query/datasources` | non-secret DS list |
| POST | `/api/v1/query/validate` | guardrails only |
| POST | `/api/v1/query/execute` | validate + RO execute |

## Deploy

```bash
./scripts/server/deploy-query-gateway.sh
./scripts/server/verify-query-gateway.sh
```

systemd: `nanobase-query-gateway`
