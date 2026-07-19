# Faz 8 Acceptance / Go-No-Go

## Vertical slice GO (code complete offline)

- [x] Oracle hardened path modules + internal execute dispatch
- [x] Policy YAML + 600-query corpus all REJECT
- [x] Metadata scanner + Qdrant payload shape
- [x] Oracle AWEL prompts + metric compiler dialect
- [x] Plan Guard / Result Guard / VPD helpers
- [x] Benchmark + cross-dialect skeletons
- [x] Docs + rollback flags

## Production GO (requires live PDB)

- [ ] 19c PDB with NANOBASE_* accounts + VPD
- [ ] Live verify-oracle.sh PASS
- [ ] Cross-tenant VPD test 0 rows
- [ ] 250-Q benchmark thresholds
- [ ] 100-metric cross-dialect equivalence
- [ ] Privilege review / soak / chaos / RAC
- [ ] Manual DBA + business approval

## Immediate NO_GO

SYS usage, DB link, PL/SQL, DML/DDL, cross-tenant leak, Plan Guard skip,
financial precision loss, corpus bypass, rollback failure, Critical/High findings.
