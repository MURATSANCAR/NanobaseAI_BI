# Faz 9 Known Risks

| Risk | Mitigation |
|------|------------|
| sqlglot lacks native HANA dialect | Fail-closed subset parser + token guard; unparsed SQL rejected |
| OData service limits vary | Nanobase applies stricter Result Guard always |
| Analytic privilege drift | Scheduled privilege test → SUSPEND datasource |
| Metadata fingerprint change | `SAP_METADATA_VERSION_CONFLICT` → revalidation |
| Credential expiry | Fail closed; never auto-request write access |
| Accidental raw-table allowlist | Deny-list of known S/4 tables + PUBLISHED-only retrieval |
