# Faz 5 verification results

Date: 2026-07-19

## Automated (local)

```text
pytest query_gateway/tests/unit query_gateway/tests/property query_gateway/tests/security
→ passed (incl. 500 malicious SQL corpus — 0 APPROVED)
```

## Manual / prod

Run `./scripts/server/verify-query-gateway.sh` after deploy.

## Notes

- Staging: enable `QG_AUTH_REQUIRED=true` with mirrored JWT/HMAC secrets.
- Full Testcontainers RLS + Locust soak: staging gate (scripts/docs ready; 4h soak not run in this commit).
