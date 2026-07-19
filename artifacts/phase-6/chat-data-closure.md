# Chat Data execute closure (Faz 6.8)

Production BI chat path does **not** call DB-GPT `chat_with_db_execute`.

## Evidence

1. `backend/nanobase_api/chat_gateway.py` — Gateway validate/execute only; header comment documents Chat Data exclusion.
2. `backend/nanobase_api/workflows.py` / `infrastructure/text2sql_adapter.py` — plan/repair/explain via `nanobase_awel` only.
3. Script: `scripts/server/assert-no-chat-data-execute.sh` (PASS on nanobase_api + FE).
4. Legacy bridge may still contain the string; it is not on the `/bi` public chat path.

## Locked architecture

Customer SQL → Query Gateway (`:8792`) only. AWEL package has no DB connector or credentials.
