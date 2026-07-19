# Penetration test gate (§35)

Independent or operationally separated security team must complete testing before GO.

## Scope

React frontend, FastAPI backend, authn/z, SSE, datasource endpoints, schema scan,
file/export, Query Gateway internal API, service auth, request signatures, replay,
Vault, Kubernetes ingress, DB-GPT, AWEL, prompt injection, Semantic Catalog, Admin UI,
PostgreSQL/Oracle/SAP connector boundaries.

## Acceptance

- Critical: 0
- High: 0
- Medium: requires risk owner, remediation date, compensating control, security approval

## Artifact

Store signed summary at `artifacts/final-release-gate/penetration-test-summary.pdf`
(or `.json` interim) and reference hash in `go-no-go-decision.json`.
