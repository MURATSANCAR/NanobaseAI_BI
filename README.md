# NanobaseAI BI Frontend

Standalone BI module extracted from the Nanobase QA portal. React + Vite app for analytics, Text2SQL chat, schema management, and Superset embed.

## Development

```bash
npm install
npm run dev
```

Dev server: **http://127.0.0.1:5174** — proxies `/api` and `/health` to the runner (default `http://127.0.0.1:8787`).

## Configuration

| Variable | Purpose |
|----------|---------|
| `VITE_API_BASE` | Runner API origin when not using same-origin proxy. Empty = Vite/nginx proxy to `/api`. |

Copy `.env.example` to `.env` and adjust as needed.

Portal (`portal.nanobase.ai`) redirects `/bi/*` to this app via `VITE_BI_APP_ORIGIN` (e.g. `https://bi.nanobase.ai`). Backend stays on the MobilTest runner (`/api/v1/bi/*`).

## Data sources (ERP + Sigorta)

Operator configs live under [`configs/`](configs/README.md):

- **Connection profiles** (Neon hosts + Vault `secret_ref`, no passwords): `configs/sources/connection.example.json`
- **Schema catalogs**: `configs/schemas/erp.catalog.json`, `sigorta.catalog.json`
- **Seed SQL**: `configs/seeds/neon-erp-seed.sql`, `neon-sigorta-seed*.sql`
- **Semantic bindings**: `configs/semantic/binding_erp_*.json`

Passwords stay in Vault (`bi/default/erp/password`, `bi/default/sigorta/password`). Runtime registry on server: `/data/nanobaseai-mobile/bi/connection.json`.

## Routes

All app routes live under `/bi/*`:

- `/bi` — Superset dashboard canvas
- `/bi/chat`, `/bi/budget`, `/bi/sources`, `/bi/connection`, `/bi/schema`, `/bi/settings`
- `/bi/queries`, `/bi/templates`, `/bi/glossary`, `/bi/alerts`, `/bi/shares`, `/bi/audit`, `/bi/schedules`
- `/bi/public/:token` — public guest embed (no auth)

Legacy portal aliases (`/bi/superset`, `/bi/dashboard`, etc.) redirect to `/bi`.

## Build

```bash
npm run build
npm run preview
```
