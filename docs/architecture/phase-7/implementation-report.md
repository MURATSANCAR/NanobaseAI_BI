# Implementation report

Implemented inside `nanobase_api.semantic_catalog` (not `backend-python/`).

Delivered:

- Domain + status machine + dual-approval promotion
- Alembic 002–009
- Metric compiler (PostgreSQL) + unpaid slice seed
- Atomic-style Qdrant publisher (in-memory + optional client)
- Schema impact → STALE
- AWEL semantic context priority + chat compile path
- Feedback → candidate only
- Admin UI `/bi/semantic-catalog` behind `VITE_ENABLE_SEMANTIC_CATALOG`
- Verify script `scripts/server/verify-semantic-gov.sh`
