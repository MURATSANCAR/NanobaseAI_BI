# Faz 5 — Acceptance / GO-NO-GO

## Scope delivered (evolve-in-place)

- Internal API: `POST /internal/v1/queries/validate|execute`, `GET /internal/v1/queries/{id}`
- Health: `/health/live`, `/health/ready` (+ legacy `/health`)
- Service JWT + HMAC + Redis/in-memory replay
- SQLGlot parser, policy YAML, wildcard/join/function denylist
- Postgres pool + RO transaction + RLS GUC hook + EXPLAIN cost guard
- Result guard + masking
- `QueryGatewayClient` in nanobase_api; chat SSE `validated` / `QUERY_POLICY_REJECTED`
- Portal query proxies require principal
- 500 malicious SQL corpus — all rejected
- Rollback: `NANOBASE_TEXT2SQL_EXECUTION_MODE=PLAN_ONLY`

## Local verification

```bash
cd backend
PYTHONPATH=. QG_AUTH_REQUIRED=false QG_REPLAY_REQUIRED=false \
  .venv/bin/python -m pytest query_gateway/tests -q
```

## Production deploy

```bash
./scripts/server/deploy-query-gateway.sh
./scripts/server/verify-query-gateway.sh
# ensure nanobase_api.env has matching QG_SERVICE_JWT_SECRET / QG_HMAC_SECRET
```

## GO criteria (minimum)

| Check | Target | Status |
|-------|--------|--------|
| Malicious corpus | 500/500 rejected | Unit suite |
| Auth bypass on `/internal/v1` when auth on | 0 | Deploy with `QG_AUTH_REQUIRED=true` |
| DML/DDL via parser | 0 approved | Corpus + unit |
| Cross-tenant | RLS GUC set; fixture optional | Integration on staging |
| Masked email | Masked | Unit masking |
| Connection leak | Pool putconn/reset | Code path |
| PLAN_ONLY rollback | Documented | Config |

## NO-GO if

- Any corpus SQL APPROVED
- Unauthenticated FE → Gateway
- DB-GPT → customer DB direct execute
