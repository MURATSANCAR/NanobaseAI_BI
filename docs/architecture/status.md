# Nanobase BI — production status (2026-07-19)

## Live stack

| Service | Port | systemd |
|---------|------|---------|
| nanobase_api | 8790 | `nanobase-bi-api` |
| query_gateway | 8792 | `nanobase-query-gateway` |
| DB-GPT | 5670 | `nanobase-dbgpt` |
| reporting PG | 5435 | docker `nanobase-bi-reporting-db` |
| bi_meta PG | 5434 | docker `nanobase-bi-meta-db` |
| Superset (analytics) | 8089 (internal) / 8443 (public embed) | docker `nanobase-superset` — enable with `BI_SUPERSET_*` |

Portal: `https://portal.nanobase.ai/bi/` → `/bi-api` → `nanobase_api`.
Analytics embed: `https://portal.nanobase.ai:8443` → Superset (`deploy/nginx/portal-analytics-8443.conf`).

## Datasources (Gateway)

- `bi_reporting` — local reporting RO
- `erp` / `sigorta` — Neon via **`bi_erp_ro` / `bi_sigorta_ro`** (SELECT-only)
- Oracle / SAP — connectors ready; secrets optional

## Verify

```bash
./scripts/server/verify-e2e.sh
./scripts/server/verify-query-gateway.sh
./scripts/server/verify-semantic.sh
./scripts/server/verify-neon-ro.sh
./scripts/server/verify-superset.sh
```

## Analytics (Superset)

- API bridge: `nanobase_api` `/api/v1/bi/analytics/*` (status, dashboards, guest-token, pin, charts).
- Compose: `infra/docker/superset/` + `configs/superset-bi.env.example`.
- When `BI_SUPERSET_ENABLED=0` (default): shaped `{ enabled: false, dashboards: [] }` so FE loads.
- When enabled: set matching `BI_SUPERSET_GUEST_SECRET` / audience on API and in `superset_config.py`, then `docker compose up` + nginx 8443.

## Still stub / empty (FE SaaS surfaces)

Shares — empty list stubs.

**Live now:** budgets, alerts, dual workflows, rich reporting schema, secrets file(+Vault opt), **Qdrant schema index for `bi_reporting` + `erp` + `sigorta`** (chat → retrieve → plan → Gateway), **Superset analytics bridge** (engine optional until secrets + compose are live).

See [locked-architecture.md](locked-architecture.md).

