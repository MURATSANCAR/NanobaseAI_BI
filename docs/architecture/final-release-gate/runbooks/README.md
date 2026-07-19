# Final Gate runbooks

Each runbook must be **executed**, not only written. Record last test date, tester, result, evidence.

Minimum set (§39):

| Runbook | Script / doc |
|---------|----------------|
| Deploy | `scripts/server/deploy-*.sh` |
| Rollback | `scripts/server/release-gate/rollback-plan-only.sh` |
| Scale model server | capacity-plan.md |
| Restart DB-GPT | ops host systemd |
| Rotate secret | `tools/release-gate/run_secret_rotation_drill.py` |
| Restore PostgreSQL | `scripts/server/release-gate/restore-metadata.sh` |
| Rebuild Qdrant | `scripts/server/index-schema-qdrant.sh` |
| Recover Redis | ops |
| Disable execution / PLAN_ONLY | rollback-plan-only.sh |
| Suspend datasource | Gateway admin |
| Query timeout / policy spike / model saturation | incident-response-plan.md |
| SAP metadata conflict / Oracle RAC | phase-8/9 runbooks |

Evidence folder: `artifacts/final-release-gate/runbook-evidence/` (create per drill).
