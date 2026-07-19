# Rollback plan

1. `POST /api/v1/semantic/versions/{id}/rollback` — reactivate prior immutable manifest.
2. Kill-switch: `SEMANTIC_CATALOG_ENABLED=0` → Faz 6 schema-only AWEL.
3. Query Gateway remains on; Chat Data / direct DB-GPT execution stay off.
4. In-flight executions keep pinned version or cancel per policy.
