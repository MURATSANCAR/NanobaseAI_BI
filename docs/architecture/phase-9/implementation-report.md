# Faz 9 Implementation Report

## Code map

| Area | Path |
|------|------|
| SAP package | `backend/query_gateway/infrastructure/sap/` |
| Legacy shim | `backend/query_gateway/sap.py` |
| Policies | `backend/query_gateway/config/policies/hana-*.yaml`, `odata-policy.yaml` |
| Secrets example | `configs/sap-ro.datasources.json.example` |
| FI binding | `configs/semantic/binding_sap_fi_odata.json` |
| AWEL prompts | `backend/nanobase_awel/prompts/*-s4-odata/`, `*-hana/`, `result-explain/v1-sap/` |
| Security corpora | `backend/query_gateway/tests/security/corpus/` |
| Verify | `scripts/server/verify-sap.sh` |
| Docs | `docs/architecture/phase-9/` |
| Artifacts | `artifacts/phase-9/` |

## Feature flags

- `SAP_EXECUTION_ENABLED`
- `SAP_EXECUTION_MODE` ∈ QUERY_GATEWAY | PLAN_ONLY | METADATA_ONLY
- `SAP_HANA_EXECUTION_ENABLED` (default off until FI OData GO)
