# Nanobase BI — Faz 6 controlled text2sql workflows

## Flow

```text
FE chat/stream
  → nanobase_api
  → nanobase_awel sql-plan-v1 (Qdrant authorized retrieve + Qwen JSON)
  → Query Gateway validate (+ sql-repair-v1 ≤2)
  → Query Gateway execute
  → nanobase_awel result-explain-v1 + fidelity
  → SSE
```

DB-GPT `chat_with_db_execute` is **not** used for customer SQL execution.

Package: [`backend/nanobase_awel/`](../../backend/nanobase_awel/)

## Internal endpoints

- `POST /api/v1/bi/internal/workflows/sql-plan`
- `POST /api/v1/bi/internal/workflows/sql-repair`
- `POST /api/v1/bi/internal/workflows/result-explain`

Header: `X-Nanobase-Workflow-Version: 1`

## Rollback

```env
NANOBASE_TEXT2SQL_EXECUTION_MODE=PLAN_ONLY
```

See [`phase-6/`](phase-6/).
