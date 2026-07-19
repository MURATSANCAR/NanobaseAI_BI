# Faz 8 Rollback

1. Set `ORACLE_EXECUTION_MODE=PLAN_ONLY` on Query Gateway (and API).
2. Set `ORACLE_EXECUTION_ENABLED=0` on nanobase_api (default).
3. Optionally set `NANOBASE_TEXT2SQL_EXECUTION_MODE=PLAN_ONLY` for global chat rollback.
4. Do **not** delete Oracle datasource / metadata / conversations / semantic catalog.
5. Do **not** enable DB-GPT Chat Data or direct Oracle execution.

Pin previous gateway image digest from `artifacts/phase-8/image-digest.txt` if needed.
