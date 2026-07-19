# Faz 6 architecture

Orchestration stays in `nanobase_api`. Structured workflows live in `nanobase_awel` (in-process; AWEL-contract shaped, not a DB-GPT AWEL DAG).

```text
React SSE → chat_gateway
  → authorized Qdrant retrieve
  → nanobase-sql-plan-v1
  → Query Gateway validate
  → nanobase-sql-repair-v1 (≤2, allowlist)
  → Query Gateway execute
  → nanobase-result-explain-v1 + fidelity
  → SSE events
```

Customer DB credentials never enter `nanobase_awel`. Execution is Gateway-only.

## Package layout

```text
backend/nanobase_awel/
  contracts/   # Pydantic request/result + error codes
  workflows/   # plan / repair / explain
  operators/   # parse, sanitize, fidelity, summarizer, …
  prompts/     # Jinja templates + output schemas
  retrieval/   # tenant+datasource Qdrant filters
  security/    # injection markers, budgets
```
