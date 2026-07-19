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

## Full GO (remaining production gates)

- [ ] 300-question semantic benchmark ≥ targets
- [ ] 150 verified candidate suite
- [ ] Soak 4h / chaos / perf p95 targets
- [ ] Manual business + technical GO sign-off

See `artifacts/phase-7/` for unit/contract evidence from this implementation.
