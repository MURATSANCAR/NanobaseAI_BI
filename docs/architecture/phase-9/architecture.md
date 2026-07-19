# Faz 9 Architecture — SAP Hardened Path

```text
React → Nanobase API → Semantic Catalog / AWEL SAP Plan
                         ↓
              Query Gateway /internal/v1/queries/*
                         ↓
    ┌─ OData Policy → Auth → Result Guard → S/4HANA
    └─ HANA Policy → Plan/Workload Guard → Approved Views
                         ↓
              SAP Business Validator → SSE
```

DB-GPT / AWEL / Frontend never open SAP connections.

## Adapter package

`backend/query_gateway/infrastructure/sap/`

| Module | Role |
|--------|------|
| contracts | datasource, query plan, result types |
| odata/ | client, metadata, query builder, policy, pagination |
| hana/ | pool, executor, parser_policy, plan_guard, workload |
| semantic/ | CDS/HANA bindings, fiscal, currency, reversal |
| security/ | authorization, company/client scope, masking |

## Profiles

| Profile | When |
|---------|------|
| A — S/4HANA CDS/OData | Primary (FI vertical slice first) |
| B — Approved HANA SQL | After FI OData GO + Basis/Security approval |

## Execution modes

| Env | Behavior |
|-----|----------|
| `SAP_EXECUTION_MODE=QUERY_GATEWAY` | Full execute (requires `SAP_EXECUTION_ENABLED=1`) |
| `SAP_EXECUTION_MODE=PLAN_ONLY` | Gateway rejects execute |
| `SAP_EXECUTION_MODE=METADATA_ONLY` | Scan only |
| `SAP_HANA_EXECUTION_ENABLED=0` | HANA path closed (default until FI GO) |

Legacy `/api/v1/query/*` SAP path remains for transition; production targets `/internal/v1`.
