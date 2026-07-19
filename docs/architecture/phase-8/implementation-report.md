# Implementation Report

## Code map

- `backend/query_gateway/infrastructure/oracle/*` — adapter
- `backend/query_gateway/config/policies/oracle-*.yaml`
- `backend/query_gateway/application/{validate,execute}_query.py` — Oracle dispatch
- `tools/schema-indexer/scanner/oracle.py`
- `backend/nanobase_awel/prompts/sql-plan/v1-oracle/`, `sql-repair/v1-oracle/`
- `backend/nanobase_api/semantic_catalog/infrastructure/metric_compiler.py` — oracle dialect
- `configs/semantic/binding_oracle_reporting.json`
- `configs/oracle-ro.datasources.json.example`
- Tests: `tests/unit/oracle/`, `tests/security/test_oracle_malicious_corpus.py`
- Corpus: `tests/security/corpus/oracle_malicious.sql.jsonl` (≥600)
- Benchmark: `tests/text2sql/oracle-250.yaml`, `cross-dialect-100.json`

## Offline verification (2026-07-19)

```text
make test-oracle-corpus → 25 passed (incl. 600/600 corpus reject)
```
