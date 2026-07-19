# Oracle VPD Design

Preference: separate PDB → separate owner → VPD → tenant-filtered views.

Gateway sets `NANOBASE_CTX.TENANT_ID` / `USER_ID` / `EXECUTION_ID` via
`DBMS_SESSION.SET_CONTEXT` or `NANOBASE_CTX_PKG.SET_TENANT`.

Fail-closed when `requireVpd=true` and context cannot be set.
Always clear context on pool return. Cross-tenant acceptance: Tenant A query for Tenant B PK → 0 rows.
