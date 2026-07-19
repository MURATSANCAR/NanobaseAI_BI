# Nanobase BI — Faz 8 Oracle reporting RO connector

## Goal

Register an **Oracle Autonomous DB (SSB/SH)** read-only source in Query Gateway
so Text-to-SQL can validate/execute Oracle dialect SQL with the same guardrails
as Postgres (`SELECT`/`WITH` only, table allowlist, row caps).

## Secrets (never commit)

On the server:

```bash
# 1) password file
install -m 600 /dev/null /data/nanobaseai/bi/secrets/oracle-adb.password
# paste RO password, save

# 2) datasource map (from example)
cp configs/oracle-ro.datasources.json.example \
   /data/nanobaseai/bi/secrets/oracle-ro.datasources.json
chmod 600 /data/nanobaseai/bi/secrets/oracle-ro.datasources.json
# edit host / service_name / user
```

Optional full TNS: set `"dsn": "(description=...)"` and omit host/service.

## Gateway behaviour

| Item | Value |
|------|--------|
| Driver | `oracledb` thin (no Instant Client) |
| Dialect | sqlglot `oracle` → `FETCH FIRST n ROWS ONLY` |
| Default allowlist | SSB sample tables |
| Config path | `/data/nanobaseai/bi/secrets/oracle-ro.datasources.json` |
| Port | `:8792` (unchanged) |

Without the secrets file, Gateway behaves exactly as Faz 5 (Postgres only).

## Deploy

```bash
./scripts/server/deploy-query-gateway.sh   # installs oracledb
./scripts/server/verify-query-gateway.sh   # Postgres regression
./scripts/server/verify-oracle.sh          # Oracle if secrets present
```

## Acceptance

1. `GET /health` → `oracle_driver: true`
2. With secrets: `oracle_adb_ssb` listed in `/api/v1/query/datasources`
3. `SELECT COUNT(*) FROM ssb.customer` → 200 via Gateway
4. `INSERT` / non-allowlisted table → 400
5. Without secrets: verify script reports `SKIP (no oracle-ro.datasources.json)`
