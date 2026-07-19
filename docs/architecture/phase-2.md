# Nanobase BI — Faz 2 schema index + quality

## What ran (server)

1. Controlled scan of `bi_reporting.analytics` (tables/views/columns + samples)
2. BGE-M3 embed → Qdrant collection `bi_schema_bi_reporting` (33 points)
3. 20-question gate: retrieval hit + NL2SQL token check (threshold 0.80)

## Commands

```bash
# on server
./scripts/server/run-phase2.sh
# or
.venv/bin/python backend/scripts/schema_index_qdrant.py
BI_EMBED_API_KEY=… .venv/bin/python -u backend/scripts/phase2_quality.py
```

## Acceptance (2026-07-19)

See [`phase-2-results.md`](phase-2-results.md): **overall 1.000 — PASS** (20/20 retrieval + SQL).
