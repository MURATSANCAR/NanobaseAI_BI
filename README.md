# NanobaseAI BI Frontend

Standalone BI module extracted from the Nanobase QA portal. React + Vite app for analytics, Text2SQL chat, schema management, and Superset embed.

## Development

```bash
npm install
cp .env.example .env
# Backend stack (DB-GPT + bridge on :8787)
cd backend && ./scripts/setup.sh && ./scripts/start-stack.sh && cd ..
npm run dev
```

Dev server: **http://127.0.0.1:5174/bi/** — proxies `/api` and `/health` to the bridge (`:8787` → DB-GPT `:5670`).

## Portal path (production)

BI opens same-origin at **https://portal.nanobase.ai/bi** (not a separate subdomain by default).

| Piece | Role |
|-------|------|
| Vite `base` | `/bi/` ([vite.config.ts](vite.config.ts)) |
| Nginx | [deploy/nginx/portal-bi-path.conf](deploy/nginx/portal-bi-path.conf) |
| Portal hub | MobilTest `VITE_BI_APP_ORIGIN=` (empty) → `/bi` links stay on portal |

## Backend (DB-GPT)

See [`backend/README.md`](backend/README.md).

```bash
cd backend && ./scripts/setup.sh && cp .env.example .env && ./scripts/start-stack.sh
```

| Service | Port |
|---------|------|
| DB-GPT | 5670 |
| BI bridge (`/api/v1/bi/*`) | 8787 |
| LLM (Qwen llama.cpp) | 8010 local / 8015 public proxy |

LLM credentials (MobilTest `docs/LLM-SERVER.md`): key `nanobase-local`, model `nanobase-qwen36-35b-a3b-mtp`.

Neon ERP/Sigorta: `configs/sources/local/connection.local.json` (gitignored) → `./scripts/register-neon-sources.sh`.

## Configuration

| Variable | Purpose |
|----------|---------|
| `VITE_API_BASE` | Bridge origin when not using same-origin proxy. Empty = Vite/nginx → `/api`. |
| `VITE_BASE` | Asset/router base. Default `/bi/`. |

## Data sources (ERP + Sigorta)

Operator configs live under [`configs/`](configs/README.md):

- **Connection profiles** (Neon hosts + Vault `secret_ref`): `configs/sources/connection.example.json`
- Local passwords: `configs/sources/local/` (gitignored)
- **Schema catalogs**, seeds, semantic bindings — unchanged

## Routes

App routes under `/bi/*` (with Vite base `/bi/`):

- `/bi` — dashboard canvas
- `/bi/chat`, `/bi/budget`, `/bi/sources`, `/bi/connection`, `/bi/schema`, `/bi/settings`
- `/bi/public/:token` — public guest embed

## Production deploy

1. `npm run build` → `dist/` with `/bi/` asset paths  
2. Sync to `/data/nanobaseai/bi/portal/dist`  
3. Apply [deploy/nginx/portal-bi-path.conf](deploy/nginx/portal-bi-path.conf) (or merge `/bi/` locations into portal `:443`)  
4. Run `backend/scripts/start-stack.sh` on the server (LLM on `:8010`)  
5. Rebuild portal hub with `VITE_BI_APP_ORIGIN=` so home BI card opens `/bi`
