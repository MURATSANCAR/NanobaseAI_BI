# Known risks

- In-memory `CatalogStore` is process-local until SQL repositories are wired to `sc_*` tables in production deploy.
- Qdrant upsert uses placeholder vectors until embedding pipeline is connected.
- Full 300-question benchmark / 150 verified suite / soak / chaos remain for GO.
- Legacy glossary UI still hits `/api/v1/bi/glossary` (read-only coexistence).
