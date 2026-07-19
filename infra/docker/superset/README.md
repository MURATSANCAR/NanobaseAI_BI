# NanobaseAI — Apache Superset (analytics canvas)

Production embed path for `BiSupersetPage` / `@superset-ui/embedded-sdk`.

## Start

```bash
cd infra/docker/superset
cp ../../../configs/superset-bi.env.example .env
# edit BI_SUPERSET_PASSWORD, BI_SUPERSET_GUEST_SECRET, SUPERSET_SECRET_KEY
chmod +x docker-entrypoint.sh
docker compose --env-file .env up -d
```

Internal: `http://127.0.0.1:8089`  
Public (nginx): `https://portal.nanobase.ai:8443` → see `deploy/nginx/portal-analytics-8443.conf`

## Wire nanobase_api

Copy the same `BI_SUPERSET_*` values into the API env (`configs/bi.backend.env.example`), then restart `nanobase-bi-api`.

```bash
./scripts/server/verify-superset.sh
```

## First dashboard

1. Log into Superset UI as the service user.
2. Add a read-only database (e.g. reporting PG RO).
3. Create a dashboard (or use API `POST /api/v1/bi/analytics/dashboards`).
4. Open BI → Analytics; guest tokens are minted by the API.
