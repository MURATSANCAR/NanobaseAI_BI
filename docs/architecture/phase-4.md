# Nanobase BI — Faz 4 FE cutover

## Change

- Nginx `bi_dbgpt_bridge` upstream: `127.0.0.1:8789` → **`127.0.0.1:8790`** (`nanobase-bi-api`)
- `nanobase-bi-bridge` **stopped + disabled**
- FE still uses `VITE_API_BASE=/bi-api` (no rebuild required)

## Deploy / cutover

```bash
./scripts/server/deploy-nanobase-api.sh
./scripts/server/cutover-nanobase-api.sh
```

## Rollback

```bash
sudo cp /tmp/portal.nanobase.ai.bak.<timestamp> /etc/nginx/sites-enabled/portal.nanobase.ai
sudo systemctl reload nginx
sudo systemctl enable --now nanobase-bi-bridge
```

## Verify

- `https://portal.nanobase.ai/bi/` → 200
- `https://portal.nanobase.ai/bi-api/health` → 200
- `https://portal.nanobase.ai/bi-api/api/v1/bi/status` → ready
