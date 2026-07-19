# Faz 8 results — Oracle RO connector

**Date:** 2026-07-19  
**Host:** `38.247.162.28`  
**Verdict:** PASS (connector + guardrails); live ADB **SKIP** (no secrets yet)

## Deployed

| Check | Result |
|-------|--------|
| `oracledb` in BI venv | 4.0.2 |
| sqlglot Oracle rewrite | `FETCH FIRST 500 ROWS ONLY` |
| Gateway health | `version 0.8.0`, `oracle_driver: true` |
| Postgres regression (`verify-query-gateway.sh`) | all OK |
| Live Oracle (`verify-oracle.sh`) | SKIP — missing `oracle-ro.datasources.json` |

## To enable live smoke

```bash
# on server
cp /data/nanobaseai/bi/frontend/configs/oracle-ro.datasources.json.example \
   /data/nanobaseai/bi/secrets/oracle-ro.datasources.json
# edit host / service_name / user
printf '%s' 'RO_PASSWORD' > /data/nanobaseai/bi/secrets/oracle-adb.password
chmod 600 /data/nanobaseai/bi/secrets/oracle-*
sudo systemctl restart nanobase-query-gateway
./scripts/server/verify-oracle.sh
```
