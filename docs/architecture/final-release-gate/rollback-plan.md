# Rollback plan (Final Gate)

Safe first action: `QUERY_GATEWAY` → `PLAN_ONLY` (`NANOBASE_TEXT2SQL_EXECUTION_MODE`, Oracle/SAP flags).

Forbidden: routing execute to DB-GPT direct DB.

Full drill: deploy new → traffic → inject fault → PLAN_ONLY → previous digest → policy/semantic pointer revert → smoke.

Accept: data loss 0, cross-tenant 0, duplicate execution 0, within time target.
