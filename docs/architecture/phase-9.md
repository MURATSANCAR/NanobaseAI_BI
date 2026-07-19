# Nanobase BI — Faz 9 SAP HANA / CDS-OData

## Goal

Read-only SAP access through Query Gateway:

1. **HANA SQL** (`hdbcli`) — SELECT guardrails via sqlglot (Postgres dialect rewrite)
2. **CDS-OData** (`httpx`) — GET entity sets only; `$top` capped; no `$batch`

## Secrets

```bash
cp configs/sap-ro.datasources.json.example \
   /data/nanobaseai/bi/secrets/sap-ro.datasources.json
# edit hosts / users / allowlists
printf '%s' 'RO_PASSWORD' > /data/nanobaseai/bi/secrets/sap-hana.password
printf '%s' 'RO_PASSWORD' > /data/nanobaseai/bi/secrets/sap-odata.password
chmod 600 /data/nanobaseai/bi/secrets/sap-*
# HANA only:
uv pip install --python backend/.venv/bin/python hdbcli
sudo systemctl restart nanobase-query-gateway
```

## API usage

HANA:

```json
{"datasource_id":"sap_hana_ro","sql":"SELECT * FROM sflight"}
```

OData (sql field carries entity + query):

```json
{"datasource_id":"sap_cds_odata","sql":"A_SalesOrder?$select=SalesOrder&$top=10"}
```

## Deploy / verify

```bash
./scripts/server/deploy-query-gateway.sh
./scripts/server/verify-query-gateway.sh
./scripts/server/verify-sap.sh
```

Without `sap-ro.datasources.json`, verify exits `SKIP` (connector ready).
