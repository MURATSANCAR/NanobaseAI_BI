# Phase 1–9 evidence index

Standard pack per phase:

- `acceptance.md` (or equivalent acceptance JSON)
- `verification-results` (or `verification-plan.md` + machine results)
- `security-results`
- `performance-results`
- `chaos-results`
- `rollback-plan`
- `build-metadata`

Verified by `tools/release-gate/verify_phase_evidence.py` against
`tools/release-gate/schemas/phase_evidence_schema.json`.

## Mapping

| Phase | Docs root | Artifacts | Notes |
|------:|-----------|-----------|-------|
| 1 | `docs/architecture/phase-1*.md|json` | (none — docs-only) | LEGACY_ACCEPTED allowed with risk entry |
| 2 | `docs/architecture/phase-2*` | (none) | LEGACY_ACCEPTED |
| 3 | `docs/architecture/phase-3*` | (none) | LEGACY_ACCEPTED |
| 4 | `docs/architecture/phase-4*` | (none) | Cutover in scripts |
| 5 | `docs/architecture/phase-5/` | `artifacts/phase-5/` | Gateway corpus present |
| 6 | `docs/architecture/phase-6/` | `artifacts/phase-6/` | Adversarial smoke only |
| 7 | `docs/architecture/phase-7/` | `artifacts/phase-7/` | Reference complete pack (GO) |
| 8 | `docs/architecture/phase-8/` | `artifacts/phase-8/` | Offline OK; live PENDING |
| 9 | `docs/architecture/phase-9/` | `artifacts/phase-9/` | Offline OK; live PENDING |

## Rules

1. Evidence without matching `release` / git commit hash is rejected for a new RC.
2. Phase 7 is the structural gold standard.
3. Phases 8–9 may be `OFFLINE_GO` but not production `GO` until live sandboxes pass.
