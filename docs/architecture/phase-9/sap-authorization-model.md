# SAP Authorization Model

## Immutable rules

1. No SAP_ALL / SAP_NEW / HANA SYSTEM / schema-owner production users
2. Read-only communication scenario / view grants only
3. Company code enforcement via SAP auth + CDS filter + analytic privilege + Nanobase policy
4. LLM `WHERE CompanyCode=…` alone is not security
5. Cross-client / cross-company leakage = NO_GO

## Isolation options (HANA)

Separate database, separate schema/user, analytic privilege, tenant-filtered calculation view.
Shared views without row isolation cannot go to production.

## Mandatory cross-company test

Tenant/Company A context → request Company B by key → 0 rows.
