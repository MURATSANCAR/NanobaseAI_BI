# Nanobase BI — Faz 2 schema index + quality

## What ran (server)

1. Controlled scan → BGE-M3 → Qdrant:
   - `bi_schema_bi_reporting` (200 points, analytics+public)
   - `bi_schema_erp` (280 points)
   - `bi_schema_sigorta` (213 points)
2. 20-question gate on `bi_schema_bi_reporting`:
   - retrieval hit-rate
   - NL2SQL via **nanobase_api** `/workflows/nl2sql-plan` (Gateway path; DB-GPT execute yok)
3. Pass threshold: overall ≥ 0.80

## Commands

```bash
# on server
./scripts/server/run-phase2.sh
```

## Acceptance (2026-07-19)

See [`phase-2-results.md`](phase-2-results.md): **overall 0.950 — PASS**
(18/20 retrieval, 20/20 SQL plan; q12/q19 retrieval miss but SQL ok).
