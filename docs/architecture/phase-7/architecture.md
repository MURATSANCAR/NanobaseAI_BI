# Faz 7 — Semantic Catalog (Governance)

## Status

Governance-grade Semantic Catalog replaces the lightweight Faz 7 cache
(`bi_verified_sql` auto-promote). Immutable rules:

1. LLM cannot publish semantic assets without human approval.
2. Feedback creates **candidates only** — never verified SQL.
3. Verified scope is tenant + datasource + semantic_version + schema_version + dialect.
4. Logical plan is the source of truth; physical SQL is compiler output / evidence.
5. All semantic changes are versioned (MAJOR.MINOR.PATCH).
6. Schema changes can mark dependent assets `STALE` (excluded from retrieval).

## Package layout

```text
backend/nanobase_api/semantic_catalog/
  domain/           # status machine, entities, promotion, conflicts
  application/      # validate, publish, seed unpaid slice, feedback→candidate
  infrastructure/   # metric_compiler, qdrant_publisher, schema_impact, catalog_store
  api/routes.py     # /api/v1/semantic/*
```

Alembic: `002`–`009` on `nanobase_alembic_version`.

## Vertical slice

`unpaid_invoice_amount` + mandatory `exclude_cancelled_invoices` + time field
+ dual review + immutable version `7.0.0` + Qdrant publish + AWEL priority context.

## Feature flags

| Flag | Purpose |
|------|---------|
| `SEMANTIC_CATALOG_ENABLED` | Master switch (default on) |
| `SEMANTIC_CATALOG_BACKEND` | `auto` (SQL if `sc_*` exist) / `sql` / `memory` |
| `SEMANTIC_SHADOW_MODE` | Compile/log without serving SQL to user |
| `SEMANTIC_METRIC_<code>=true` | Metric-based rollout |
| `VITE_ENABLE_SEMANTIC_CATALOG` | Admin UI |

## Persistence

`CatalogStore` write-through via `SqlCatalogRepository` → PostgreSQL `sc_*` tables
(Alembic 002–009). Hydrates on process start when tables are present.


## Docs in this folder

- architecture.md, governance-model.md, promotion-workflow.md, versioning.md
- rollback-plan.md, acceptance.md, verification-plan.md
