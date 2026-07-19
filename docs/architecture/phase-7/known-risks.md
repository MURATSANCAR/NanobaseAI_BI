# Known risks

- SQL backend (`SEMANTIC_CATALOG_BACKEND=auto|sql`) persists to `sc_*` when Alembic 002–009 applied; falls back to memory if tables missing.
- Qdrant upsert still uses placeholder vectors until embedding pipeline is connected.
- Soak default in CI is 5s; full 4h: `SOAK_SECONDS=14400 ./scripts/server/verify-semantic-gov.sh`
- Legacy glossary UI still hits `/api/v1/bi/glossary` (read-only coexistence).
