# Faz 5 Rollback

1. Set on nanobase_api: `NANOBASE_TEXT2SQL_EXECUTION_MODE=PLAN_ONLY` and restart.
2. Optional: set `QG_USE_INTERNAL_API=false` to use legacy `/api/v1/query/*` only.
3. Optional: pin previous gateway git revision / image digest and restart `nanobase-query-gateway`.

Rollback **never** enables DB-GPT direct DB execute.
