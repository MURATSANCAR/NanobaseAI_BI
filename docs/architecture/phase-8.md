# Nanobase BI — Faz 8 Oracle reporting (connector + production cert)

## Two layers

1. **Connector (original)** — Oracle RO source in Query Gateway secrets map (`oracledb` Thin).
2. **Production certification** — hardened `/internal/v1` path, policy corpus, Plan/Result/VPD guards.
   See **[phase-8/](phase-8/)** for full architecture, acceptance, and rollback.

## Secrets (never commit)

```bash
cp configs/oracle-ro.datasources.json.example \
   /data/nanobaseai/bi/secrets/oracle-ro.datasources.json
# Use NANOBASE_QUERY_RO — never SYS/SYSTEM/ADMIN
```

## Quick verify

```bash
./scripts/server/deploy-query-gateway.sh
./scripts/server/verify-oracle.sh          # offline policy always; live SKIP without secrets
cd backend/query_gateway && make test-oracle-corpus
```

## Feature flags

| Env | Default | Meaning |
|-----|---------|---------|
| `ORACLE_EXECUTION_ENABLED` | `0` | API allows Oracle execute path |
| `ORACLE_EXECUTION_MODE` | `QUERY_GATEWAY` | Gateway: `PLAN_ONLY` disables execute |

## Acceptance (offline)

1. `GET /health` → `oracle_driver: true`
2. `make test-oracle-corpus` → 600/600 malicious REJECT
3. Without secrets: verify script SKIP after offline policy OK
