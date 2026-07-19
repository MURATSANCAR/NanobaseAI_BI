# Nanobase BI — Faz 3 (nanobase_api evolve)

## Decisions

- Evolve [`backend/nanobase_api/`](../../backend/nanobase_api/) — no `backend-python/`
- FE contract `/api/v1/bi/*` preserved
- Keycloak deferred; `AUTH_MODE=dev|jwt` (HS256)
- SQL execute via Query Gateway (default); `NANOBASE_TEXT2SQL_EXECUTION_MODE=PLAN_ONLY` optional
- Schema scans via ARQ (Redis) with asyncio fallback
- Alembic uses `nanobase_alembic_version` (does not disturb existing `006_bi_cost_centers`)

## New endpoints

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/v1/bi/health/live` | process up |
| GET | `/api/v1/bi/health/ready` | meta / gateway / redis |
| PUT | `/api/v1/bi/sources/{id}` | tenant-scoped + secret_ref |
| POST | `/api/v1/bi/sources/{id}/test` | connection test |
| POST | `/api/v1/bi/sources/{id}/scan` | queue schema scan |
| GET | `/api/v1/bi/schema-scans/{id}` | scan status |

## Migrations

```bash
cd backend/nanobase_api
NANOBASE_META_DSN=... alembic -c alembic.ini upgrade head
```

## ARQ worker

```bash
REDIS_URL=redis://127.0.0.1:6379/0 \
PYTHONPATH=backend \
  arq nanobase_api.infrastructure.arq_worker.WorkerSettings
```

## Env

```env
AUTH_MODE=dev
JWT_SECRET=...
NANOBASE_TEXT2SQL_EXECUTION_MODE=QUERY_GATEWAY
ARQ_ENABLED=1
REDIS_URL=redis://127.0.0.1:6379/0
```
