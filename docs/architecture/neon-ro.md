# Nanobase BI — Neon RO via Query Gateway (post-roadmap)

## Goal

`erp` / `sigorta` Neon databases are executable **only** through Query Gateway
(SELECT/WITH + table allowlist). Chat uses per-datasource schema hints from
`neon-schema-hints.json`.

## Deploy (server)

```bash
./scripts/server/deploy-neon-ro.sh
./scripts/server/verify-neon-ro.sh
./scripts/server/verify-query-gateway.sh
```

Reads `/data/nanobaseai/bi/secrets/connection.local.json` (never commit), writes:

| File | Purpose |
|------|---------|
| `neon-ro.datasources.json` | Gateway RO map |
| `neon-{erp,sigorta}.password` | password files |
| `neon-schema-hints.json` | LLM schema snippets |

## Security note

Prefer dedicated Neon roles `bi_erp_ro` / `bi_sigorta_ro` (SELECT-only grants):

```bash
./scripts/server/deploy-neon-ro.sh          # allowlist + hints
# then:
/data/nanobaseai/bi/frontend/backend/.venv/bin/python \
  /data/nanobaseai/bi/frontend/backend/scripts/provision_neon_ro_roles.py
sudo systemctl restart nanobase-query-gateway
./scripts/server/verify-neon-ro.sh
```

Owner credentials in `connection.local.json` stay for provisioning only; Gateway uses `neon-*.password` RO files.

`deploy-neon-ro.sh` also syncs `bi_sources` (username + `secret_ref`) from `neon-ro.datasources.json` so Connection **Test** uses the same RO secrets as Query Gateway.

