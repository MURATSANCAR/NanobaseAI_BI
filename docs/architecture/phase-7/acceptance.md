# Acceptance

## Vertical slice (unpaid_invoice_amount)

- [x] Domain status machine forbids DRAFT→PUBLISHED
- [x] Metric compiler applies mandatory CANCELLED/VOID filter
- [x] Compiler AST fingerprint stable across 1000 runs
- [x] Feedback does not auto-promote verified SQL
- [x] Dual approval required; same user blocked
- [x] Unauthorized publish rejected
- [x] Schema column removal marks metric STALE
- [x] AWEL prompt includes published semantic block before schema
- [x] Admin UI gated by `VITE_ENABLE_SEMANTIC_CATALOG`
- [x] Alembic 002–009 present
- [x] SQL write-through to `sc_*` (`SqlCatalogRepository`)

## Full GO gates

- [x] 300-question semantic benchmark (targets met offline)
- [x] 150 verified candidate suite (unauthorized/stale/version/cross-tenant = 0)
- [x] Perf microbench (compile + catalog read p95)
- [x] Chaos checks (Qdrant fail, active unchanged, schema lock)
- [x] Soak smoke (extend with `SOAK_SECONDS=14400` for 4h)

Evidence: `artifacts/phase-7/build-metadata.json` → `"verdict": "GO"`.

```bash
./scripts/server/verify-semantic-gov.sh
```
