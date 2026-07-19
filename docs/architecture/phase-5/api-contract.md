# Query Gateway API contract (v1)

Header: `X-Nanobase-Contract-Version: 1`

## Validate

`POST /internal/v1/queries/validate`

Auth: Bearer service JWT (`query.validate`) + HMAC headers.

Response APPROVED includes `normalizedSql`, `sqlFingerprint`, `tables`, `policyVersion`.

Rejected: `{ code, message, executionId, traceId, retryable }`.

## Execute

`POST /internal/v1/queries/execute`

Auth scope: `query.execute`.

Response SUCCESS: columns `[{name,type,masked}]`, rows, rowCount, truncated, timings.
