# Verification Plan

| Gate | Command / artifact |
|------|-------------------|
| Unit | `cd backend/query_gateway && make test-unit` |
| Oracle corpus (≥600) | `make test-oracle-corpus` |
| Benchmark skeleton (250) | `tests/text2sql/oracle-250.yaml` |
| Cross-dialect (100) | `tests/text2sql/cross-dialect-100.json` |
| Live smoke | `./scripts/server/verify-oracle.sh` (SKIP without secrets) |

Coverage targets: policy/parser critical 100%; result guard ≥95%; adapter ≥90%.
