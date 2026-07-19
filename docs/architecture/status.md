# Nanobase BI — production status (2026-07-19)

## Live stack

| Service | Port | systemd |
|---------|------|---------|
| nanobase_api | 8790 | `nanobase-bi-api` |
| query_gateway | 8792 | `nanobase-query-gateway` |
| DB-GPT | 5670 | `nanobase-dbgpt` |
| reporting PG | 5435 | docker `nanobase-bi-reporting-db` |
| bi_meta PG | 5434 | docker `nanobase-bi-meta-db` |

Portal: `https://portal.nanobase.ai/bi/` → `/bi-api` → `nanobase_api`.

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
```

## Still stub / empty (FE SaaS surfaces)

Shares, analytics/Superset dashboards — empty list stubs.

**Live now:** budgets, alerts, dual workflows (`nl2sql-plan` / `result-explain`), rich reporting schema (invoices/payments/…), secrets file(+optional Vault).

See [locked-architecture.md](locked-architecture.md).

