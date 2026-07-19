# Disaster recovery plan

NIST SP 800-34 Rev. 1 aligned.

Initial RPO/RTO (business-approved):

| Component | RPO | RTO |
|-----------|-----|-----|
| Metadata PG | ≤ 5 min | ≤ 60 min |
| Audit | ≤ 1 min | ≤ 4 h |
| Vault | ≤ 5 min | ≤ 30 min |
| Qdrant | ≤ 24 h / last snapshot | ≤ 4 h |
| Images / prompts / policy | 0 | ≤ 30–60 min |

Full DR drill required before GO (primary cluster unavailable scenario).
