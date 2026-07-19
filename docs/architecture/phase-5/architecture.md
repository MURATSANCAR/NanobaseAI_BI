# Faz 5 architecture

Evolve-in-place package `backend/query_gateway` on loopback `:8792`.

```text
nanobase_api (QueryGatewayClient)
  → JWT + HMAC + unique request id
  → /internal/v1/queries/*
  → parse → policy → pool → RO txn (+ RLS GUC) → EXPLAIN → execute → mask
  → audit jsonl + metrics
```

Oracle/SAP remain on legacy `/api/v1/query/execute` until later phases.
