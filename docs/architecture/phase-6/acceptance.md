# Faz 6 acceptance

## Delivered

| Item | Status |
|------|--------|
| nanobase-sql-plan-v1 | Package + chat wired |
| nanobase-sql-repair-v1 | LLM repair, max 2, allowlist |
| nanobase-result-explain-v1 | Summarizer + fidelity fallback |
| Authorized retrieval filters | tenant + datasource |
| Context sanitizer labels | yes |
| No chat_with_db_execute in nanobase_api | assert script |
| Unit/adversarial smoke | pytest |

## Local verify

```bash
cd backend
PYTHONPATH=. ../backend/.venv/bin/python -m pytest nanobase_awel/tests -q
./scripts/server/assert-no-chat-data-execute.sh
```

## Staging gates (deferred full corpus)

- 200-question quality benchmark
- 500 adversarial
- 150 fidelity cases
