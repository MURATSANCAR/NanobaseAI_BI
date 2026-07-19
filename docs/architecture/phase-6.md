# Nanobase BI — Faz 6 chat via Gateway

## Flow

```
FE chat/stream
  → nanobase_api
  → llama.cpp (SQL JSON only)
  → Query Gateway validate + execute (+ EXPLAIN)
  → SSE done { sql, query_result, explain }
```

DB-GPT `chat_with_db_execute` is **not** used for customer SQL execution.

## Verify

```bash
curl -N -X POST https://portal.nanobase.ai/bi-api/api/v1/bi/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"message":"Kaç müşteri var?","session_id":"faz6-test"}'
```
