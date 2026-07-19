# SAP Source Policy

## Priority

1. Released SAP CDS View
2. Released SAP API
3. Approved Custom CDS View
4. Approved Custom Analytical Query
5. Approved HANA Calculation View
6. Approved SQL Reporting View

## Forbidden

Unreleased internal CDS, compatibility views, raw SAP tables (`ACDOCA`, `BKPF`, `BSEG`, `VBAK`, …),
temporary/generated tables, write-enabled or deprecated APIs, unapproved Z objects.

## Lifecycle

`DISCOVERED` → `TECHNICALLY_VALIDATED` → `FUNCTIONALLY_VALIDATED` → `APPROVED` → `PUBLISHED`

Only `PUBLISHED` sources enter production retrieval. `DEPRECATED` / `STALE` / `REJECTED` are excluded.
