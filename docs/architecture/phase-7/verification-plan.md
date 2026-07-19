# Verification plan

```bash
cd backend
PYTHONPATH=. .venv/bin/python -m pytest nanobase_api/semantic_catalog/tests -q
./scripts/server/verify-semantic-gov.sh
```

Contract header: `X-Nanobase-Semantic-Contract-Version: 1`
