# Threat model (summary)

| Threat | Mitigation | Gate |
|--------|------------|------|
| Prompt injection → SQL | AWEL sanitizer + Gateway policy | AI + SQL corpora |
| Cross-tenant retrieval | Qdrant filters + API authz + honeytenant | Tenant suite |
| Direct DB from LLM stack | Network + no connectors + assert scripts | Bypass suite |
| Supply chain tamper | Digest-only deploy + SBOM + cosign | Supply-chain verify |
| Backup ransomware | Immutable backups + restore drills | Backup/DR |
| Credential theft | Vault/file rotation drills | Secret rotation |
