# Faz 9 Chaos Results

| Scenario | Expected | Status |
|----------|----------|--------|
| S/4 endpoint down | SAP_SERVICE_UNAVAILABLE, no raw HANA fallback | Coded |
| Metadata fingerprint change | SAP_METADATA_VERSION_CONFLICT | Coded |
| Credential expiry | Reject + alarm, no write escalate | Coded |
| Workload policy missing | HANA_WORKLOAD_POLICY_MISSING | Coded |
| Analytic privilege removed | SUSPENDED | PENDING live |
| Masking failure | No egress | Coded in Result Guard |

See `artifacts/phase-9/chaos-results.json`.
