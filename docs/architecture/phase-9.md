# Nanobase BI — Faz 9 SAP HANA / CDS-OData

Production pack: [phase-9/](phase-9/).

## Goal

Read-only SAP access through Query Gateway hardened path:

1. **S/4HANA CDS/OData** (primary) — logical plan → safe URL builder → Result Guard
2. **Approved HANA SQL** (`hdbcli`) — SELECT-only policy + Plan/Workload Guard

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

## Feature flags

```bash
export SAP_EXECUTION_ENABLED=1
export SAP_EXECUTION_MODE=QUERY_GATEWAY   # or PLAN_ONLY / METADATA_ONLY
export SAP_HANA_EXECUTION_ENABLED=0      # keep 0 until FI OData vertical slice GO
```

## API usage

OData logical plan (preferred, `/internal/v1`):

```json
{
  "datasource_id": "sap_cds_odata",
  "plan": {
    "sourceType": "SAP_ODATA",
    "service": "API_JOURNALENTRYITEM_SRV",
    "entitySet": "JournalEntryItem",
    "select": ["CompanyCode", "AmountInCompanyCodeCurrency"],
    "filters": [{"field": "CompanyCode", "operator": "EQ", "value": "1000"}],
    "top": 100
  }
}
```

Legacy OData (sql field carries entity + query):

```json
{"datasource_id":"sap_cds_odata","sql":"A_SalesOrder?$select=SalesOrder&$top=10"}
```

HANA (when enabled):

```json
{"datasource_id":"sap_hana_ro","sql":"SELECT COMPANY_CODE, OPEN_AMOUNT FROM NANOBASE_REPORTING.CV_OPEN_RECEIVABLE"}
```

## Deploy / verify

```bash
./scripts/server/deploy-query-gateway.sh
./scripts/server/verify-query-gateway.sh
./scripts/server/verify-sap.sh
```

Without `sap-ro.datasources.json`, verify exits `SKIP` (connector ready).

## Immutable rules

- No raw S/4 tables as production datasource
- OData GET / `$metadata` only
- No OData → raw HANA table fallback on failure
- Rollback: `SAP_EXECUTION_MODE=PLAN_ONLY`
