# Production readiness plan

Waves:

| Wave | Scope | Exit |
|------|-------|------|
| 0 | Docs + evidence index | Schemas + templates present |
| A | §51 vertical slice | Manifest + suites + acceptance scaffold green offline |
| B | Security corpora + leakage + rotation | 2800 SQL + 1000 AI + zero leakage |
| C | E2E 500, capacity, load, chaos | SLO targets met; fail-closed chaos |
| D | CI, K8s, DR, IR, cutover | DR RPO/RTO met; runbooks drilled |
| E | Pen-test, UAT, Go/No-Go | Signed GO |

Hybrid assumption: host/staging first; K8s PSS + multi-cluster DR required before production GO.
