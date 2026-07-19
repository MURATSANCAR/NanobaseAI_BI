# Nanobase BI — Faz 5 Query Gateway (harden)

## Role

All customer/reporting SQL execution goes through **Query Gateway** (`:8792`):

- sqlglot AST parse → SELECT/WITH only (CTE-DML, INTO, FOR UPDATE rejected)
- Policy engine (tables, functions, joins, wildcard)
- Internal auth: service JWT + HMAC + replay
- Postgres RO transaction + `app.tenant_id` GUC (RLS) + EXPLAIN cost guard
- Result limit + sensitive column masking
- RO credentials from secrets/Vault (never from request body)

Legacy routes `/api/v1/query/*` remain for Oracle/SAP/alerts; Postgres chat path prefers `/internal/v1/queries/*` via `QueryGatewayClient`.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | legacy liveness + datasources |
| GET | `/health/live` | liveness |
| GET | `/health/ready` | policy/redis/secrets readiness |
| GET | `/metrics` | Prometheus |
| POST | `/internal/v1/queries/validate` | auth + policy |
| POST | `/internal/v1/queries/execute` | auth + validate + RO execute |
| GET | `/internal/v1/queries/{executionId}` | audit status |
| POST | `/api/v1/query/validate` | legacy |
| POST | `/api/v1/query/execute` | legacy (Oracle/HANA/OData too) |

## Deploy

```bash
./scripts/server/deploy-query-gateway.sh
./scripts/server/verify-query-gateway.sh
```

systemd: `nanobase-query-gateway`

Shared secrets (`QG_SERVICE_JWT_SECRET`, `QG_HMAC_SECRET`) written into gateway + nanobase API env.

## Rollback

```env
NANOBASE_TEXT2SQL_EXECUTION_MODE=PLAN_ONLY
```

Never: DB-GPT → customer DB.

## Docs

See [`phase-5/acceptance.md`](phase-5/acceptance.md) and sibling notes under `docs/architecture/phase-5/`.
