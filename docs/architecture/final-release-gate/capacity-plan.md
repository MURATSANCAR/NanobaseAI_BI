# Capacity plan

Local Qwen on CPU: measure concurrency 1/2/4/8 planners.

## Implemented (chat / LLM path)

| Env | Default | Role |
|-----|---------|------|
| `MODEL_MAX_CONCURRENCY` | 2 | Simultaneous LLM calls (plan/repair/explain) |
| `MODEL_QUEUE_LIMIT` / `GLOBAL_QUEUE_LIMIT` | 100 | Max waiting requests |
| `TENANT_QUEUE_LIMIT` | 20 | Max active+waiting per company/tenant |
| `MODEL_QUEUE_TIMEOUT` | 120s | Max wait in queue |

Code: `nanobase_awel/operators/model_queue.py` + SSE `phase=queued` from `chat_gateway`.

Waiting users see: *"Şu anda başka bir işlem yapıyorum; size en kısa zamanda cevap vereceğim."*

Overflow → controlled error (`MODEL_QUEUE_FULL` / `TENANT_QUEUE_FULL`), not silent crash.
Status: `GET /api/v1/bi/model-queue/status`
