# Chaos results

Pending full chaos suite. Design guarantees documented in architecture:

- Publish failure → active version unchanged
- Qdrant failure → not PUBLISHED
- Schema scan + publish lock → SCHEMA_VERSION_CONFLICT

See `artifacts/phase-7/chaos-results.json`.
