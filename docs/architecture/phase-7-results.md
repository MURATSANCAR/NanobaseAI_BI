# Faz 7 results — Semantic catalog + verified SQL

**Date:** 2026-07-19  
**Host:** `38.247.162.28`  
**Verdict:** PASS

## Seed

| Object | Count |
|--------|------:|
| glossary | 48 |
| metrics | 3 |
| joins | 3 |
| verified_sql (after smoke) | ≥4 |

## API smoke

| Check | Result |
|-------|--------|
| `GET /api/v1/bi/semantic/status` | `enabled: true`, engine `nanobase_api` |
| `GET /api/v1/bi/glossary` | 48 entries (FE shape) |
| `GET /api/v1/bi/semantic/metrics` | 3 |
| `GET /api/v1/bi/semantic/joins` | 3 |
| Chat `"Kaç müşteri var?"` | `verified_cache_hit` → `n=5`, `sql_source=verified_sql` |
| Feedback promote `"Toplam ürün sayısı"` | `verified_sql_id` created |
| Chat after promote | cache hit on products count |

## Notes

- Customer SQL still only via Query Gateway (`:8792`).
- LLM skipped on verified cache hits (sub-second vs generate path).
