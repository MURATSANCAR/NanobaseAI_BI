# Legacy Faz 7 (superseded)

The original lightweight catalog + verified SQL cache is **deprecated**.

- Auto-promote on feedback: **disabled**
- `lookup_verified_sql`: returns `None` (physical SQL no longer source of truth)
- Existing `bi_verified_sql` rows with status `verified` are migrated to `STALE` in Alembic `006`

Use `docs/architecture/phase-7/` and `/api/v1/semantic/*` instead.
