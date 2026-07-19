# Final Production Release Gate

Cross-phase production readiness gate for Nanobase Text-to-SQL (Phases 1–9).

This is **not** a feature phase. It certifies that all components operate as one production system.

## Status model

`NOT_STARTED` → `PREPARING` → `RELEASE_CANDIDATE_FROZEN` → `VERIFYING` →
`SECURITY_REVIEW` → `PERFORMANCE_REVIEW` → `DR_REVIEW` → `CUSTOMER_ACCEPTANCE` →
`BLOCKED` | `REJECTED` | `CONDITIONAL_GO` | `GO` → `DEPLOYED` → `POST_RELEASE_VERIFIED`

Production traffic requires **`GO`** only. `CONDITIONAL_GO` is forbidden for tenant isolation,
SQL security, secrets, financial/SAP correctness, backup restore, rollback, critical/high findings, audit integrity.

## Layout

| Path | Purpose |
|------|---------|
| [docs in this folder](.) | Human-readable plans and decisions (§46) |
| [`artifacts/final-release-gate/`](../../../artifacts/final-release-gate/) | Machine evidence |
| [`tools/release-gate/`](../../../tools/release-gate/) | Generators and verifiers |
| [`tests/final-gate/`](../../../tests/final-gate/) | Isolation, bypass, E2E, leakage suites |
| [`.github/workflows/release-gate.yml`](../../../.github/workflows/release-gate.yml) | CI orchestration |

## Vertical slice (§51) — run locally

```bash
# From repo root
python3 tools/release-gate/run_vertical_slice.py --release 1.0.0-rc.1
```

## References

- NIST SSDF 1.1, OWASP ASVS 5.0.0, NIST AI RMF GenAI Profile, OWASP AI Testing Guide v1
- SLSA 1.2, Kubernetes Pod Security Standards `restricted`, OpenTelemetry
- NIST SP 800-61 Rev. 3 (IR), NIST SP 800-34 Rev. 1 (contingency)

See [gap-matrix.md](gap-matrix.md) and [phase-evidence-index.md](phase-evidence-index.md).
