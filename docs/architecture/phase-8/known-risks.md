# Known Risks

1. Live Oracle 19c PDB secrets not in CI — integration SKIP until provisioned.
2. Thick Mode / RAC HA not certified until vertical slice live GO.
3. Legacy `/api/v1/query/*` Oracle path still present during cutover.
4. VPD package `NANOBASE_CTX_PKG` must be installed by DBA; Gateway fails closed when `requireVpd=true`.
5. Plan Guard relative cost baselines need per-datasource tuning after first production plans.
