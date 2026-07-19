# Known risks

| ID | Risk | Severity | Mitigation | Conditional allowed? |
|----|------|----------|------------|----------------------|
| KR-01 | Phases 1–4 evidence LEGACY | Medium | Index mapping + risk accept | Yes (docs only) |
| KR-02 | Oracle/SAP live PENDING | High | Sandbox before claiming connectors | No for claimed connectors |
| KR-03 | Host deploy without K8s PSS | High | Pre-prod K8s wave | No for prod GO |
| KR-04 | Soak stubs (5s) vs 8h | High | Wave C real soak | No |
| KR-05 | AI corpus incomplete until Wave B | High | Generate 1000 | No |
