# Governance model

## Status machine

`DRAFT → VALIDATING → READY_FOR_REVIEW → APPROVED → PUBLISHED`

`DRAFT → PUBLISHED` is forbidden.

Production retrieval allows only `PUBLISHED`. `STALE`, `DRAFT`, `REJECTED` are excluded.

## Roles

| Role | Capability |
|------|------------|
| `DATA_ANALYST` | Draft, feedback → candidate |
| `BUSINESS_REVIEWER` | Business approve/reject |
| `TECHNICAL_REVIEWER` | Technical approve/reject |
| `SEMANTIC_PUBLISHER` / `ADMIN` | Publish / rollback |

Same user cannot approve both business and technical roles on one promotion.

## Feedback

Thumbs-up / `promote_verified` creates a `VerifiedQueryCandidate` and promotion
request only. It never writes `PUBLISHED` verified SQL.
