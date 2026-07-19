# Nanobase BI — Faz 2 Schema Indexer

## Module

```
tools/schema-indexer/
├── scanner/          # metadata + controlled profiling
├── normalizer/       # TABLE / COLUMN / RELATIONSHIP docs
├── fingerprint/      # SHA-256 skip / re-embed
├── embedder/         # BGE-M3
├── qdrant_writer/    # upsert + soft-delete
└── cli/
```

## Pipeline

```
Test PostgreSQL (bi_reporting / nanobase_test alias)
      ↓
Metadata Scanner (tables, columns, PK/FK)
      ↓
Controlled profiling (COUNT, MIN/MAX date, status GROUP BY — never SELECT *)
      ↓
Normalizer → TABLE | COLUMN | RELATIONSHIP
      ↓
Fingerprint (SHA-256) → SKIP | RE-EMBED+UPSERT
      ↓
BGE-M3 → Qdrant
      ↓
Soft-delete stale keys → Scan Report
```

## Commands

```bash
# on server
SCHEMA_INDEX_RECREATE=1 ./scripts/server/run-phase2.sh bi_reporting

# or directly
PYTHONPATH=tools/schema-indexer \
  backend/.venv/bin/python -m cli.main \
  --datasource bi_reporting --schemas analytics,public --recreate
```

## Smoke suite

```
tests/text2sql/
├── smoke-questions.yaml
├── expected-results.yaml
└── run-smoke-tests.py
```

## Acceptance

See [`phase-2-results.md`](phase-2-results.md).
