# Security model

Trust boundaries:

- Internet → Nginx → React + Nanobase API
- API → DB-GPT/AWEL, Query Gateway, Schema Indexer, meta PG, Redis, Vault
- AWEL → Qwen, BGE-M3, Qdrant
- Query Gateway → approved customer DBs / SAP endpoints only

Fail-closed for: query policy, tenant policy, Vault credential, masking, audit (mandatory profile), VPD/RLS/analytic privilege.

NO-GO: Query Gateway bypass, cross-tenant leak, credential exposure, unmasked RESTRICTED, fail-open security controls.
