# Cutover plan

T-7: RC freeze, full regression, pen-test closed, UAT, backup/restore, DR, Go/No-Go scheduled.  
T-24h: change freeze, prod backup, secrets/certs, capacity, dashboards, rollback artifact, on-call.  
T-1h: manifest/digest/migration preflight; traffic flags closed.

Deploy: control plane → health → migration → smoke → PLAN_ONLY → security smoke → pilot QUERY_GATEWAY.

Traffic: internal → 5% → 25% → 50% → 100% with checks between stages.
