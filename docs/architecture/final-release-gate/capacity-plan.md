# Capacity plan

Local Qwen on CPU: measure concurrency 1/2/4/8 planners.

Certify `MODEL_MAX_CONCURRENCY`, `MODEL_QUEUE_LIMIT`, `MODEL_QUEUE_TIMEOUT`,
`TENANT_QUEUE_LIMIT`, `GLOBAL_QUEUE_LIMIT`.

One tenant must not consume entire model capacity. Overflow → 429, no double execution.
