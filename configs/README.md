# BI data sources & schema assets

Operator configs for the NanobaseAI BI stack. The FE talks to the runner API; these files document **ERP** and **Sigorta** Neon databases used in production.

## Layout

| Path | Purpose |
|------|---------|
| `sources/connection.example.json` | Named sources (`erp`, `sigorta`) — host/user/ssl + Vault `secret_ref` |
| `sources/connection.sanitized.json` | Snapshot from server (no passwords) |
| `schemas/erp.catalog.json` | Live ERP table/column catalog (slim) |
| `schemas/sigorta.catalog.json` | Live Sigorta table/column catalog (slim) |
| `schemas/schema_tr_erp*.json` | Text2SQL test schema fixtures |
| `seeds/neon-erp-seed.sql` | ERP DDL + demo seed (Neon 512MB-oriented; BT OPEX/CAPEX dahil) |
| `seeds/neon-erp-bt-budget-patch.sql` | Non-destructive BT bütçe plan + AP fatura zenginleştirme |
| `seeds/neon-sigorta-seed*.sql` | Sigorta DDL + demo seed parts |
| `semantic/binding_erp_*.json` | Certified semantic bindings for ERP |
| `bi.backend.env.example` | Standalone BI runner env template |
| `supabase-bi.env.example` / `superset-bi.env.example` | Optional stack env templates |

## Sources (production)

| `source_id` | Label | Neon host (aws) | Vault secret |
|-------------|--------|-----------------|--------------|
| `erp` | ERP (Neon) | `ep-little-hill-at81gpda…` | `bi/default/erp/password` |
| `sigorta` | Sigorta (Neon) | `ep-sweet-star-adwrp395…` | `bi/default/sigorta/password` |

- Database: `neondb`
- User: `neondb_owner`
- SSL: required
- Active source on server (last snapshot): `erp`

## Local secrets (dev)

Passwords are **not** in git. Sync from the Nanobase server vault into:

| Path | Purpose |
|------|---------|
| `sources/local/neon-dsns.env` | `BI_ERP_*` / `BI_SIGORTA_*` DSNs + passwords |
| `sources/local/connection.local.json` | Full registry with passwords (chmod 600) |

```bash
# Probe Neon (needs local/neon-dsns.env)
python3 -c "import psycopg2, pathlib; ..."  # or use backend scripts below

# DB-GPT: start sidecar, then register both sources
cd backend && ./scripts/start.sh
# other terminal:
./backend/.venv/bin/python backend/scripts/register_neon_datasources.py
```

## Security

- **Do not commit passwords** or full `BI_DATABASE_URL` with credentials.
- Server runtime registry: `/data/nanobaseai-mobile/bi/connection.json` (`chmod 600`).
- FE Connection UI uses `GET/PUT /api/v1/bi/sources` — passwords go to Vault via `secret_ref`.

## Apply seed (ops)

```bash
# Example — password from Vault / Neon console, not from git
psql "postgresql://neondb_owner:***@ep-….neon.tech/neondb?sslmode=require" \
  -f configs/seeds/neon-erp-seed.sql

# BT bütçe verisini canlı ERP'ye ekle (diğer tabloları silmez)
set -a && source configs/sources/local/neon-dsns.env && set +a
psql "$BI_ERP_DATABASE_URL" -f configs/seeds/neon-erp-bt-budget-patch.sql
# Sonra UI: /bi/budget → Sync from source (fiscal year 2026, refresh)
```

Runner still owns SQL execution; this repo holds FE + operator reference configs.
