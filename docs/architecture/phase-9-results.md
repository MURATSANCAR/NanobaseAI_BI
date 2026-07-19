# Faz 9 results — SAP HANA / CDS-OData

**Date:** 2026-07-19  
**Host:** `38.247.162.28`  
**Verdict:** PASS (connector); live SAP **SKIP** (no secrets)

## Deployed

| Check | Result |
|-------|--------|
| Gateway version | `0.9.0` |
| `odata_ready` | true (`httpx`) |
| `hana_driver` | false until `hdbcli` installed |
| Postgres regression | all OK |
| `verify-sap.sh` | SKIP — missing `sap-ro.datasources.json` |

## Enable

See [phase-8.md](phase-8.md) pattern; copy `configs/sap-ro.datasources.json.example` → secrets and restart gateway.
